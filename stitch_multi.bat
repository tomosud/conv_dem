@echo off

REM Simple version - always pause to see errors
set SCRIPT_DIR=%~dp0
set VENV_PYTHON=%SCRIPT_DIR%venv\Scripts\python.exe

echo [INFO] Script directory: %SCRIPT_DIR%
echo [INFO] Python path: %VENV_PYTHON%
echo [INFO] Input file: %1
echo.

if not exist "%VENV_PYTHON%" (
    echo [ERROR] Virtual environment Python not found: %VENV_PYTHON%
    echo [INFO] Run setup.bat first
    goto END
)

if "%~1"=="" (
    echo [USAGE] Drag and drop a ZIP file onto this batch file
    goto END
)

echo [INFO] Executing Python script...
"%VENV_PYTHON%" "%SCRIPT_DIR%dem_stitch_multi.py" "%~1"
echo [INFO] Python script finished with exit code: %errorlevel%

:END
echo.
echo Press any key to close...
pause >nul
