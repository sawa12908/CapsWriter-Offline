# coding: utf-8
"""
Audio stream manager for microphone input.

Key goals:
- Follow current Windows default input device automatically.
- Use event-based detection (no polling loop).
- Reopen stream safely when device/config changes.
"""

from __future__ import annotations

import asyncio
import threading
import time
from platform import system
from typing import TYPE_CHECKING, Any, List, Optional, Tuple

import numpy as np
import sounddevice as sd

from . import logger
from util.client.state import console
from util.common.lifecycle import lifecycle

if TYPE_CHECKING:
    from util.client.state import ClientState


DeviceSignature = Tuple[int, int, str]


class AudioStreamManager:
    """Manage microphone input stream lifecycle."""

    SAMPLE_RATE = 48000
    BLOCK_DURATION = 0.05  # 50ms

    def __init__(self, state: "ClientState"):
        self.state = state
        self._channels = 1
        self._running = False

        self._reopen_lock = threading.Lock()
        self._stream_lock = threading.RLock()
        self._default_input_signature: Optional[DeviceSignature] = None
        self._current_input_index: Optional[int] = None
        self._current_input_name = "unknown"

        # Debounce reopen requests from system events.
        self._last_event_reopen_ts = 0.0
        self._event_reopen_interval_seconds = 0.8
        self._event_reopen_timer: Optional[threading.Timer] = None
        self._event_verify_timer: Optional[threading.Timer] = None

        # Win32 message listener
        self._listener_mode: Optional[str] = None
        self._winmsg_listener_thread: Optional[threading.Thread] = None
        self._winmsg_listener_ready = threading.Event()
        self._winmsg_listener_thread_id: Optional[int] = None
        self._winmsg_listener_hwnd: Optional[int] = None
        self._winmsg_listener_class_name: Optional[str] = None

    # ---------- audio callback ----------

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info,
        status: sd.CallbackFlags,
    ) -> None:
        if not self.state.recording:
            return

        if self.state.loop and self.state.queue_in:
            asyncio.run_coroutine_threadsafe(
                self.state.queue_in.put(
                    {
                        "type": "data",
                        "time": time.time(),
                        "data": indata.copy(),
                    }
                ),
                self.state.loop,
            )

    def _on_stream_finished(self) -> None:
        if not threading.main_thread().is_alive():
            return

        if self._running and not lifecycle.is_shutting_down:
            logger.info("audio stream finished unexpectedly; reopening")
            self.reopen(reason="stream finished unexpectedly")
        else:
            logger.debug("audio stream closed")

    # ---------- default input resolution ----------

    @staticmethod
    def _normalize_device_name(name: str) -> str:
        return "".join(ch.lower() for ch in str(name) if ch.isalnum())

    @staticmethod
    def _signature_to_text(signature: Optional[DeviceSignature]) -> str:
        if signature is None:
            return "unknown"
        index, hostapi, name = signature
        return f"index={index}, hostapi={hostapi}, name={name}"

    def _get_hostapi_index(self, hostapi_name: str) -> Optional[int]:
        try:
            for idx, api in enumerate(sd.query_hostapis()):
                if str(api.get("name", "")) == hostapi_name:
                    return idx
        except Exception:
            return None
        return None

    def _get_default_input_index(self) -> Optional[int]:
        try:
            default_device = sd.default.device
            if isinstance(default_device, (list, tuple)) and len(default_device) >= 1:
                idx = int(default_device[0])
                return idx if idx >= 0 else None
        except Exception:
            pass
        return None

    def _build_input_info_from_index(self, index: int, source: str) -> Optional[dict]:
        try:
            info = sd.query_devices(int(index))
            if int(info.get("max_input_channels", 0)) <= 0:
                return None
            return {
                "index": int(index),
                "hostapi": int(info.get("hostapi", -1)),
                "name": str(info.get("name", "")),
                "max_input_channels": int(info.get("max_input_channels", 1)),
                "default_samplerate": float(info.get("default_samplerate", self.SAMPLE_RATE)),
                "source": source,
            }
        except Exception as e:
            logger.debug(f"query input by index failed: index={index}, source={source}, err={e}")
            return None

    def _collect_default_input_candidates(self) -> List[dict]:
        candidates: List[dict] = []
        seen: set = set()

        def _add(candidate: Optional[dict]) -> None:
            if not candidate:
                return
            sig = (
                int(candidate.get("index", -1)),
                int(candidate.get("hostapi", -1)),
                str(candidate.get("name", "")),
            )
            if sig in seen:
                return
            seen.add(sig)
            candidates.append(candidate)

        # 1) PortAudio global default input (what device=None uses).
        try:
            info = sd.query_devices(kind="input")
            if isinstance(info, dict) and int(info.get("max_input_channels", 0)) > 0:
                idx = int(info.get("index", -1))
                _add(
                    {
                        "index": idx if idx >= 0 else -1,
                        "hostapi": int(info.get("hostapi", -1)),
                        "name": str(info.get("name", "")),
                        "max_input_channels": int(info.get("max_input_channels", 1)),
                        "default_samplerate": float(
                            info.get("default_samplerate", self.SAMPLE_RATE)
                        ),
                        "source": "kind-input",
                    }
                )
        except Exception as e:
            logger.debug(f"resolve kind='input' failed: {e}")

        # 2) PortAudio default input index tuple.
        default_index = self._get_default_input_index()
        if default_index is not None:
            _add(self._build_input_info_from_index(default_index, "default-index"))

        # 3) Windows WASAPI default input index.
        if system() == "Windows":
            wasapi_api_index = self._get_hostapi_index("Windows WASAPI")
            if wasapi_api_index is not None:
                try:
                    hostapi = sd.query_hostapis(wasapi_api_index)
                    default_index = int(hostapi.get("default_input_device", -1))
                    if default_index >= 0:
                        _add(self._build_input_info_from_index(default_index, "wasapi-default"))
                except Exception as e:
                    logger.debug(f"resolve WASAPI default input failed: {e}")

        return candidates

    def _resolve_default_input_info(self, allow_first_available: bool = False) -> Optional[dict]:
        """
        Resolve current system default input device.
        Priority:
        1) PortAudio kind='input'
        2) PortAudio default input index
        3) Windows WASAPI default input
        4) First available input (optional fallback)
        """
        candidates = self._collect_default_input_candidates()
        if candidates:
            if len(candidates) > 1:
                summary = " | ".join(
                    f"{c.get('source')}:{c.get('index')}:{c.get('name')}" for c in candidates
                )
                logger.debug(f"default input candidates: {summary}")
            return candidates[0]

        if not allow_first_available:
            return None

        # 4) First available input (only when explicitly allowed).
        try:
            for idx, info in enumerate(sd.query_devices()):
                if int(info.get("max_input_channels", 0)) > 0:
                    return {
                        "index": int(idx),
                        "hostapi": int(info.get("hostapi", -1)),
                        "name": str(info.get("name", "")),
                        "max_input_channels": int(info.get("max_input_channels", 1)),
                        "default_samplerate": float(
                            info.get("default_samplerate", self.SAMPLE_RATE)
                        ),
                        "source": "first-available-fallback",
                    }
        except Exception:
            pass

        return None

    def _find_input_device_index_by_name(self, device_name: str) -> Optional[int]:
        if not device_name:
            return None

        target = self._normalize_device_name(device_name)
        best_idx: Optional[int] = None
        best_score = -1
        try:
            devices = sd.query_devices()
        except Exception:
            return None

        for idx, dev in enumerate(devices):
            if int(dev.get("max_input_channels", 0)) <= 0:
                continue
            name = str(dev.get("name", ""))
            if name == device_name:
                return int(idx)

            n = self._normalize_device_name(name)
            if not target or not n:
                continue
            score = 0
            if target in n or n in target:
                score = 1000
            else:
                for a, b in zip(target, n):
                    if a != b:
                        break
                    score += 1
            if score > best_score:
                best_score = score
                best_idx = int(idx)

        if best_idx is not None and best_score >= 6:
            return best_idx
        return None

    def _get_default_input_signature(self) -> Optional[DeviceSignature]:
        try:
            info = self._resolve_default_input_info()
            if not info:
                return None
            return (
                int(info.get("index", -1)),
                int(info.get("hostapi", -1)),
                str(info.get("name", "")),
            )
        except Exception as e:
            logger.debug(f"resolve input signature failed: {e}")
            return None

    # ---------- system event listener (no polling) ----------

    def _handle_possible_default_input_change(self, reason: str, force: bool = False) -> None:
        if lifecycle.is_shutting_down:
            return

        if force:
            now = time.monotonic()
            if (now - self._last_event_reopen_ts) < self._event_reopen_interval_seconds:
                logger.debug(f"skip frequent reopen event: {reason}")
                return
            self._last_event_reopen_ts = now
            logger.info(f"detected default input change event; reopening stream: {reason}")
            self.reopen(reason=reason)
            return

        if not self._running:
            return

        current = self._get_default_input_signature()
        if current is None:
            return

        if self._default_input_signature is None:
            self._default_input_signature = current
            return

        if current == self._default_input_signature:
            return

        previous = self._default_input_signature
        self._default_input_signature = current
        logger.info(
            "default input changed: "
            f"{self._signature_to_text(previous)} -> {self._signature_to_text(current)}"
        )
        self.reopen(reason=reason)

    def ensure_default_input_synced(self, reason: str = "on-demand verify") -> None:
        """
        Opportunistic check path for user-driven events (for example: hotkey press).
        This is event-triggered and avoids background polling.
        """
        if lifecycle.is_shutting_down:
            return
        if not self._running:
            return

        # Most reliable path for user-triggered recording start:
        # refresh and reopen immediately so we don't depend on stale defaults.
        if reason.startswith("shortcut:"):
            now = time.monotonic()
            if (now - self._last_event_reopen_ts) < 0.35:
                return
            self._last_event_reopen_ts = now
            logger.info(f"on-demand input sync: reopening stream, reason: {reason}")
            self.reopen(reason=reason)
            return

        info = self._resolve_default_input_info()
        if not info:
            logger.warning(f"default input resolve failed during sync, reason: {reason}")
            return

        default_index = int(info.get("index", -1))
        default_sig: DeviceSignature = (
            default_index if default_index >= 0 else -1,
            int(info.get("hostapi", -1)),
            str(info.get("name", "")),
        )

        opened_sig: Optional[DeviceSignature] = None
        try:
            if self._current_input_index is not None and self._current_input_index >= 0:
                opened = sd.query_devices(int(self._current_input_index))
                opened_sig = (
                    int(self._current_input_index),
                    int(opened.get("hostapi", -1)),
                    str(opened.get("name", self._current_input_name or "")),
                )
            elif self._current_input_name:
                idx = self._find_input_device_index_by_name(self._current_input_name)
                if idx is not None and idx >= 0:
                    opened = sd.query_devices(int(idx))
                    opened_sig = (int(idx), int(opened.get("hostapi", -1)), str(opened.get("name", "")))
        except Exception as e:
            logger.debug(f"query opened input info failed: {e}")

        if opened_sig is None:
            logger.info(
                "on-demand input sync has unknown opened device; reopening stream: "
                f"reason={reason}, default={self._signature_to_text(default_sig)}"
            )
            self._default_input_signature = default_sig
            self.reopen(reason=reason)
            return

        if opened_sig == default_sig:
            self._default_input_signature = default_sig
            return

        logger.info(
            "on-demand input sync detected mismatch; reopening stream: "
            f"reason={reason}, opened={self._signature_to_text(opened_sig)}, "
            f"default={self._signature_to_text(default_sig)}"
        )
        self._default_input_signature = default_sig
        self.reopen(reason=reason)

    def _schedule_forced_reopen(
        self,
        reason: str,
        delay_seconds: float = 0.35,
        verify_delay_seconds: float = 1.10,
    ) -> None:
        if lifecycle.is_shutting_down:
            return

        timer = self._event_reopen_timer
        if timer and timer.is_alive():
            timer.cancel()

        verify_timer = self._event_verify_timer
        if verify_timer and verify_timer.is_alive():
            verify_timer.cancel()

        def _fire() -> None:
            self._handle_possible_default_input_change(reason=reason, force=True)
            verify = threading.Timer(
                verify_delay_seconds,
                lambda: self._handle_possible_default_input_change(
                    reason=f"{reason} (post-event verify)",
                    force=False,
                ),
            )
            verify.daemon = True
            self._event_verify_timer = verify
            verify.start()

        timer = threading.Timer(delay_seconds, _fire)
        timer.daemon = True
        self._event_reopen_timer = timer
        timer.start()

    def _try_start_winmsg_listener(self) -> bool:
        if self._winmsg_listener_thread and self._winmsg_listener_thread.is_alive():
            return True

        try:
            import win32api  # noqa: F401
            import win32con  # noqa: F401
            import win32gui  # noqa: F401
        except Exception as e:
            logger.debug(f"win32 listener unavailable: {e}")
            return False

        self._winmsg_listener_ready.clear()
        self._winmsg_listener_thread = threading.Thread(
            target=self._run_winmsg_listener,
            name="CapsWriterAudioWinMsgListener",
            daemon=True,
        )
        self._winmsg_listener_thread.start()
        self._winmsg_listener_ready.wait(timeout=2.0)
        return self._winmsg_listener_hwnd is not None

    def _run_winmsg_listener(self) -> None:
        import win32api
        import win32con
        import win32gui

        class_name = f"CapsWriterAudioWinMsgListener_{id(self)}"
        self._winmsg_listener_class_name = class_name

        def _wnd_proc(hwnd, msg, wparam, lparam):
            if msg == win32con.WM_DEVICECHANGE:
                self._schedule_forced_reopen(reason=f"WM_DEVICECHANGE:{wparam}")
                return 0
            if msg == win32con.WM_SETTINGCHANGE:
                self._schedule_forced_reopen(reason="WM_SETTINGCHANGE")
                return 0
            if msg == win32con.WM_CLOSE:
                win32gui.DestroyWindow(hwnd)
                return 0
            if msg == win32con.WM_DESTROY:
                win32gui.PostQuitMessage(0)
                return 0
            return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

        hwnd = None
        class_registered = False
        hinstance = win32api.GetModuleHandle(None)
        try:
            wnd_class = win32gui.WNDCLASS()
            wnd_class.hInstance = hinstance
            wnd_class.lpszClassName = class_name
            wnd_class.lpfnWndProc = _wnd_proc
            win32gui.RegisterClass(wnd_class)
            class_registered = True

            hwnd = win32gui.CreateWindowEx(
                0,
                class_name,
                class_name,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                hinstance,
                None,
            )

            self._winmsg_listener_hwnd = hwnd
            self._winmsg_listener_thread_id = win32api.GetCurrentThreadId()
            self._winmsg_listener_ready.set()
            win32gui.PumpMessages()
        except Exception as e:
            logger.debug(f"win32 listener failed: {e}")
            self._winmsg_listener_ready.set()
        finally:
            if hwnd:
                try:
                    win32gui.DestroyWindow(hwnd)
                except Exception:
                    pass
            if class_registered and self._winmsg_listener_class_name:
                try:
                    win32gui.UnregisterClass(self._winmsg_listener_class_name, hinstance)
                except Exception:
                    pass

            self._winmsg_listener_thread_id = None
            self._winmsg_listener_hwnd = None
            self._winmsg_listener_class_name = None

    def _stop_winmsg_listener(self) -> None:
        thread = self._winmsg_listener_thread
        if thread is None:
            return

        if thread.is_alive():
            try:
                import win32api
                import win32con
                import win32gui

                if self._winmsg_listener_hwnd:
                    try:
                        win32gui.PostMessage(self._winmsg_listener_hwnd, win32con.WM_CLOSE, 0, 0)
                    except Exception:
                        pass
                if self._winmsg_listener_thread_id:
                    try:
                        win32api.PostThreadMessage(self._winmsg_listener_thread_id, win32con.WM_QUIT, 0, 0)
                    except Exception:
                        pass
            except Exception:
                pass

            if threading.current_thread() is not thread:
                thread.join(timeout=1.5)

        self._winmsg_listener_thread = None
        self._winmsg_listener_thread_id = None
        self._winmsg_listener_hwnd = None
        self._winmsg_listener_class_name = None

    def _start_default_input_listener(self) -> None:
        if system() != "Windows":
            return

        started = self._try_start_winmsg_listener()
        if started:
            self._listener_mode = "winmsg"
            logger.info("default input listener started: Win32 message")
        else:
            self._listener_mode = None
            logger.warning("default input listener unavailable; auto-switch disabled")

    def _stop_default_input_listener(self) -> None:
        timer = self._event_reopen_timer
        if timer and timer.is_alive():
            timer.cancel()
        self._event_reopen_timer = None

        verify_timer = self._event_verify_timer
        if verify_timer and verify_timer.is_alive():
            verify_timer.cancel()
        self._event_verify_timer = None

        self._stop_winmsg_listener()
        self._listener_mode = None

    # ---------- stream open/close/reopen ----------

    def _try_open_stream(
        self,
        device_index: Optional[int],
        max_input_channels: int,
        default_rate: float,
    ) -> Tuple[Optional[sd.InputStream], int, int, Optional[Exception]]:
        preferred_channels = min(2, max(1, int(max_input_channels or 1)))
        candidate_channels: List[int] = [preferred_channels]
        if preferred_channels > 1:
            candidate_channels.append(1)

        candidate_rates: List[int] = [int(self.SAMPLE_RATE)]
        dr = int(float(default_rate or self.SAMPLE_RATE))
        if dr > 0 and dr not in candidate_rates:
            candidate_rates.append(dr)
        if 44100 not in candidate_rates:
            candidate_rates.append(44100)
        if 16000 not in candidate_rates:
            candidate_rates.append(16000)

        last_error: Optional[Exception] = None
        for rate in candidate_rates:
            for ch in candidate_channels:
                try:
                    blocksize = max(1, int(self.BLOCK_DURATION * rate))
                    stream = sd.InputStream(
                        samplerate=rate,
                        blocksize=blocksize,
                        device=device_index if device_index is not None and device_index >= 0 else None,
                        dtype="float32",
                        channels=ch,
                        callback=self._audio_callback,
                        finished_callback=self._on_stream_finished,
                    )
                    stream.start()
                    return stream, ch, rate, None
                except Exception as e:
                    last_error = e
                    logger.debug(
                        "open InputStream failed: "
                        f"device={device_index}, channels={ch}, rate={rate}, err={e}"
                    )
        return None, preferred_channels, int(self.SAMPLE_RATE), last_error

    def open(
        self,
        preferred_input_index: Optional[int] = None,
        preferred_input_name: Optional[str] = None,
        fallback_to_default: bool = True,
        allow_first_available_fallback: bool = True,
    ) -> Optional[sd.InputStream]:
        with self._stream_lock:
            candidates: List[Tuple[Optional[int], dict, str, bool]] = []

            # Preferred by explicit index.
            if preferred_input_index is not None:
                try:
                    info = sd.query_devices(preferred_input_index)
                    if int(info.get("max_input_channels", 0)) > 0:
                        candidates.append((int(preferred_input_index), info, "preferred(index)", True))
                except Exception:
                    logger.debug(f"preferred index unavailable: {preferred_input_index}")

            # Preferred by name.
            if not candidates and preferred_input_name:
                idx = self._find_input_device_index_by_name(preferred_input_name)
                if idx is not None:
                    try:
                        info = sd.query_devices(idx)
                        if int(info.get("max_input_channels", 0)) > 0:
                            candidates.append((idx, info, "preferred(name)", True))
                    except Exception:
                        logger.debug(f"preferred name unavailable: {preferred_input_name}")

            # Current system default.
            if not candidates or fallback_to_default:
                info = self._resolve_default_input_info(
                    allow_first_available=allow_first_available_fallback
                )
                if info is not None:
                    idx = int(info.get("index", -1))
                    source = str(info.get("source", "system-default"))
                    try:
                        query_index = idx if idx >= 0 else None
                        dev = (
                            sd.query_devices(query_index, "input")
                            if query_index is not None
                            else sd.query_devices(kind="input")
                        )
                        if isinstance(dev, dict):
                            dev = dict(dev)
                            dev["source"] = source
                        candidates.append((idx if idx >= 0 else None, dev, f"system-default:{source}", False))
                    except Exception:
                        # Keep original resolved info if query by kind failed.
                        candidates.append((idx if idx >= 0 else None, info, f"system-default:{source}", False))

            # De-duplicate by signature.
            deduped: List[Tuple[Optional[int], dict, str, bool]] = []
            seen = set()
            for idx, dev, label, is_preferred in candidates:
                name = str(dev.get("name", "")) if isinstance(dev, dict) else ""
                hostapi = int(dev.get("hostapi", -1)) if isinstance(dev, dict) else -1
                sig = (int(idx) if idx is not None else -1, hostapi, name)
                if sig in seen:
                    continue
                seen.add(sig)
                deduped.append((idx, dev, label, is_preferred))

            if not deduped:
                console.print("no input device found", end="\n\n", style="bright_red")
                logger.error("no input device found")
                return None

            for device_index, device, label, is_preferred in deduped:
                if not isinstance(device, dict) or int(device.get("max_input_channels", 0)) <= 0:
                    continue

                stream, used_channels, used_rate, last_error = self._try_open_stream(
                    device_index=device_index,
                    max_input_channels=int(device.get("max_input_channels", 1)),
                    default_rate=float(device.get("default_samplerate", self.SAMPLE_RATE)),
                )
                if stream is None:
                    logger.warning(
                        f"open stream failed on {label}: "
                        f"name={device.get('name', 'unknown')}, index={device_index}, err={last_error}"
                    )
                    continue

                # Resolve actual opened device info.
                actual_info = None
                try:
                    if device_index is None:
                        actual_info = sd.query_devices(kind="input")
                    else:
                        actual_info = sd.query_devices(int(device_index), "input")
                except Exception:
                    actual_info = device

                actual_name = str(actual_info.get("name", "unknown"))
                actual_index = int(actual_info.get("index", device_index if device_index is not None else -1))

                self.state.stream = stream
                self._running = True
                self._channels = used_channels
                self._current_input_index = actual_index if actual_index >= 0 else device_index
                self._current_input_name = actual_name
                self._default_input_signature = self._get_default_input_signature()
                self._start_default_input_listener()

                console.print(
                    f"using input device: {actual_name}, channels: {used_channels}",
                    end="\n\n",
                )
                logger.info(
                    "input device opened: "
                    f"name={actual_name}, device={self._current_input_index}, "
                    f"channels={used_channels}, rate={used_rate}, mode={label}"
                )
                return stream

            logger.error("all candidate input devices failed to open")
            return None

    def close(self, stop_listener: bool = True) -> None:
        self._running = False

        if stop_listener:
            self._stop_default_input_listener()

        with self._stream_lock:
            stream = self.state.stream
            if stream is not None:
                try:
                    try:
                        stream.abort(ignore_errors=True)
                    except TypeError:
                        stream.abort()
                    except Exception:
                        pass

                    try:
                        stream.stop(ignore_errors=True)
                    except TypeError:
                        stream.stop()
                    except Exception:
                        pass

                    try:
                        stream.close(ignore_errors=True)
                    except TypeError:
                        stream.close()
                    except Exception:
                        pass
                    logger.debug("audio stream closed")
                except Exception as e:
                    logger.debug(f"error while closing stream: {e}")
                finally:
                    self.state.stream = None

        if stop_listener:
            self._default_input_signature = None

    def _refresh_portaudio(self, reason: str) -> None:
        try:
            sd._terminate()
            sd._ffi.dlclose(sd._lib)
            sd._lib = sd._ffi.dlopen(sd._libname)
            sd._initialize()
            logger.debug(f"PortAudio refreshed: {reason}")
        except Exception as e:
            logger.warning(f"PortAudio refresh warning ({reason}): {e}")

    def reopen(self, reason: str = "manual") -> Optional[sd.InputStream]:
        if lifecycle.is_shutting_down:
            return None

        if not self._reopen_lock.acquire(blocking=False):
            logger.debug("reopen already in progress")
            return self.state.stream

        try:
            logger.info(f"reopening audio stream, reason: {reason}")
            strict_default_follow = reason.startswith("shortcut:") or reason.startswith("WM_")

            previous_index = self._current_input_index
            previous_name = self._current_input_name

            # Keep listener alive during reopen to avoid event gaps.
            self.close(stop_listener=False)
            time.sleep(0.08)

            if strict_default_follow:
                self._refresh_portaudio(reason=f"pre-reopen:{reason}")
                time.sleep(0.05)

            if reason == "stream finished unexpectedly":
                stream = self.open(
                    preferred_input_index=previous_index,
                    preferred_input_name=previous_name,
                    fallback_to_default=True,
                    allow_first_available_fallback=not strict_default_follow,
                )
                if stream is not None:
                    return stream

            stream = self.open(allow_first_available_fallback=not strict_default_follow)
            if stream is not None:
                return stream

            logger.warning("regular reopen failed, try reloading PortAudio")
            self._refresh_portaudio(reason=f"retry:{reason}")

            time.sleep(0.15)
            return self.open(allow_first_available_fallback=True)
        finally:
            self._reopen_lock.release()
