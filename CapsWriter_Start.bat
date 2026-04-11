@echo off
setlocal
cd /d %~dp0

set "BASE_DIR=%~dp0"
if "%BASE_DIR:~-1%"=="\" set "BASE_DIR=%BASE_DIR:~0,-1%"

set "PYTHON_EXE="
if exist "D:\anaconda3\envs\capswriter\python.exe" set "PYTHON_EXE=D:\anaconda3\envs\capswriter\python.exe"
if not defined PYTHON_EXE if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PYTHON_EXE for %%I in (python.exe) do set "PYTHON_EXE=%%~$PATH:I"

if not defined PYTHON_EXE (
    echo Python executable not found.
    echo Please install Python or edit this launcher to point to your Python.
    pause
    exit /b 1
)

echo Restarting CapsWriter-Offline as administrator...
"%PYTHON_EXE%" -c "from util.tools.windows_privilege import request_admin_restart; raise SystemExit(0 if request_admin_restart(r'%BASE_DIR%', r'%PYTHON_EXE%') else 1)"
if %errorlevel% neq 0 (
    echo Failed to start CapsWriter-Offline.
    pause
    exit /b %errorlevel%
)

exit /b 0
