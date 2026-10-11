@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto environment_ready
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m venv .venv
) else (
    where python >nul 2>nul
    if errorlevel 1 goto python_missing
    python -m venv .venv
)
if errorlevel 1 goto setup_failed

:environment_ready
if not exist ".venv\.repackq-requirements-installed" (
    echo Installing RePack-Q dependencies. This may take a few minutes...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto setup_failed
    type nul > ".venv\.repackq-requirements-installed"
)

start "RePack-Q local server" cmd /k ""%CD%\.venv\Scripts\python.exe" "%CD%\run_repackq_web.py""
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8000/"
exit /b 0

:python_missing
echo Python 3.10 or newer is required. Install Python, then double-click this launcher again.
pause
exit /b 1

:setup_failed
echo RePack-Q setup did not complete. Read the error above, fix the local Python or network issue, and try again.
pause
exit /b 1
