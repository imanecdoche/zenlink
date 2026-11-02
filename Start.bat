@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
title PhoneLink

set "VENV=%~dp0.venv"
set "PY=%VENV%\Scripts\python.exe"
set "PYW=%VENV%\Scripts\pythonw.exe"
set "STAMP=%VENV%\.requirements"

rem Fast path: environment exists and requirements.txt hasn't changed.
if exist "%PY%" if exist "%STAMP%" (
    fc /b "%~dp0requirements.txt" "%STAMP%" >nul 2>&1 && goto :launch
)

echo PhoneLink - first-time setup
echo.

if not exist "%PY%" (
    set "SYS_PY="
    for %%V in (3.13 3.12 3.11) do (
        if not defined SYS_PY (
            py -%%V -c "import sys" >nul 2>&1 && set "SYS_PY=py -%%V"
        )
    )
    if not defined SYS_PY (
        python -c "import sys; raise SystemExit(0 if (3,11) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>&1 && set "SYS_PY=python"
    )
    if not defined SYS_PY (
        echo Python 3.11, 3.12 or 3.13 is required.
        echo Install it from https://www.python.org/downloads/ or run:
        echo     winget install -e --id Python.Python.3.13
        echo then open Start.bat again.
        echo.
        pause
        exit /b 1
    )
    echo [1/2] Creating the Python environment...
    !SYS_PY! -m venv "%VENV%" || goto :failed
)

echo [2/2] Installing components (about a minute the first time)...
"%PY%" -m pip install --disable-pip-version-check -q --upgrade pip >nul 2>&1
"%PY%" -m pip install --disable-pip-version-check -q -r "%~dp0requirements.txt" || goto :failed
copy /y "%~dp0requirements.txt" "%STAMP%" >nul
echo.
echo Setup complete.

:launch
rem Administrator: prepare the USB driver (libusb0, as TikTok LIVE Studio uses).
rem Without it the app opens and asks to be started as administrator.
net session >nul 2>&1
if not errorlevel 1 (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\prepare_usb.ps1"
)
if exist "%PYW%" (
    start "" "%PYW%" -m phonelink
) else (
    start "" "%PY%" -m phonelink
)
exit /b 0

:failed
echo.
echo Setup failed. Check the internet connection and run Start.bat again.
pause
exit /b 1
