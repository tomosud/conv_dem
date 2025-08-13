@echo off
chcp 65001 >nul
setlocal

REM === このBATと同じフォルダを基準に相対パスを解決 ===
set SCRIPT_DIR=%~dp0
set SCRIPT_DIR=%SCRIPT_DIR:~0,-1%

REM === Virtual environment Python ===
set VENV_PYTHON=%SCRIPT_DIR%\venv\Scripts\python.exe

REM === Check virtual environment ===
if not exist "%VENV_PYTHON%" (
    echo [ERROR] Virtual environment not found. Run setup.bat first.
    pause
    exit /b 1
)

REM === Check arguments (folder drag and drop) ===
if "%~1"=="" (
    echo [ERROR] Drag and drop XML folder to this BAT file.
    pause
    exit /b 1
)

REM === Get dropped path ===
set TARGET_DIR=%~1

REM === Execute ===
"%VENV_PYTHON%" -X utf8 "%SCRIPT_DIR%\dem_stitch.py" "%TARGET_DIR%"
if errorlevel 1 (
    echo [ERROR] dem_stitch.py execution failed.
    pause
    exit /b 1
)

echo Completed: Check output files in %TARGET_DIR%
pause
endlocal
