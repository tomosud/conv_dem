@echo off
setlocal enabledelayedexpansion

REM =======================================
REM  stitch_multi.bat
REM  複数ZIP/フォルダをD&Dして一括ステッチ（欠損=0）
REM =======================================

set SCRIPT_DIR=%~dp0
set VENV_PYTHON=%SCRIPT_DIR%venv\Scripts\python.exe
if not exist "%VENV_PYTHON%" (
    where python >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Python not found.
        pause
        exit /b 1
    )
    set VENV_PYTHON=python
)

if "%~1"=="" (
    echo [USAGE] Drag&Drop zip or folder(s) onto this .bat
    pause
    exit /b 0
)

echo [INFO] Running: "%VENV_PYTHON%" -X utf8 "%SCRIPT_DIR%dem_stitch_multi.py" %*
echo.

"%VENV_PYTHON%" -X utf8 "%SCRIPT_DIR%dem_stitch_multi.py" %*
set EXIT_CODE=%errorlevel%

echo.
if %EXIT_CODE% neq 0 (
    echo [ERROR] dem_stitch_multi.py failed with exit code: %EXIT_CODE%
    echo Check the error messages above for details.
    pause
    exit /b %EXIT_CODE%
)

echo [SUCCESS] Completed successfully.
pause
endlocal
