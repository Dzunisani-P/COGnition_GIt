@echo off
cd /d %~dp0
set VENV_DIR=venv

REM Check if virtual environment exists
if not exist %VENV_DIR%\Scripts\activate.bat (
    echo Creating virtual environment...
    python -m venv %VENV_DIR%
)

REM Activate the environment
call %VENV_DIR%\Scripts\activate.bat

REM Install dependencies
echo Installing dependencies...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt >nul

REM Run the app
echo Launching the app in your browser...
python app.py

REM Pause to keep window open if the script crashes
pause
