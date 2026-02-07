@echo off
setlocal
cd /d %~dp0

echo Starting CapsWriter-Offline Server...
start "CapsWriter-Server" python start_server.py

timeout /t 2 /nobreak > nul

echo Starting CapsWriter-Offline Client...
start "CapsWriter-Client" python start_client.py

echo Both Server and Client have been launched in separate windows.
pause
