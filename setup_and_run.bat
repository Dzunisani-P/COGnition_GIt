@echo off
cd /d %~dp0
set VENV_DIR=venv
set PYTHON_EXE=%VENV_DIR%\Scripts\python.exe

REM Check if virtual environment exists
if not exist %PYTHON_EXE% (
    echo Creating virtual environment...
    python -m venv %VENV_DIR%

    REM Activate the environment (cmd-specific)
    call %VENV_DIR%\Scripts\activate.bat

    REM Display the Python path and version
    echo === Python being used ===
    echo %PYTHON_EXE%
    %PYTHON_EXE% --version

    REM Install dependencies
    echo === Installing dependencies... ===
    %PYTHON_EXE% -m pip install --upgrade pip
    %PYTHON_EXE% -m pip install aiohttp pandas plotly shinywidgets tqdm scp

) else (
    REM Activate the environment (cmd-specific)
    call %VENV_DIR%\Scripts\activate.bat

    REM Display the Python path and version
    echo === Python being used ===
    echo %PYTHON_EXE%
    %PYTHON_EXE% --version

    echo Dependencies installation skipped since virtual environment exists.
)

REM Run the app
echo === Launching the app in your browser... ===
%PYTHON_EXE% app.py

REM Pause to keep window open if the script crashes
pause
