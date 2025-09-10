@echo off
chcp 65001 >nul
setlocal

REM ========================================
REM DEM Stitch Tool - Virtual Environment Setup
REM ========================================

echo [INFO] DEM Stitch Tool virtual environment setup...

REM === Script directory ===
set SCRIPT_DIR=%~dp0
set SCRIPT_DIR=%SCRIPT_DIR:~0,-1%

REM === Virtual environment directory ===
set VENV_DIR=%SCRIPT_DIR%\venv

REM === Python executable (try relative path first, then system) ===
set PY_EXE=%SCRIPT_DIR%\..\Python\env\Python311.4\python.exe

REM === Check Python executable ===
if not exist "%PY_EXE%" (
    echo [WARN] Specific Python not found: %PY_EXE%
    echo [INFO] Trying to use system Python...
    
    where python >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] No Python found in system PATH either
        echo [INFO] Please install Python or check the path in this script
        pause
        exit /b 1
    )
    
    set PY_EXE=python
    echo [INFO] Using system Python from PATH
)

REM === Create virtual environment ===
echo [INFO] Creating virtual environment... (%VENV_DIR%)
"%PY_EXE%" -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment.
    pause
    exit /b 1
)

REM === Virtual environment Python path ===
set VENV_PYTHON=%VENV_DIR%\Scripts\python.exe

REM === Upgrade pip ===
echo [INFO] Upgrading pip...
"%VENV_PYTHON%" -m pip install --upgrade pip
if errorlevel 1 (
    echo [WARN] Failed to upgrade pip, but continuing.
)

REM === Install required libraries ===
echo [INFO] Installing required libraries...
"%VENV_PYTHON%" -m pip install -r "%SCRIPT_DIR%\requirements.txt"
if errorlevel 1 (
    echo [ERROR] Failed to install libraries.
    pause
    exit /b 1
)

echo.
echo [SUCCESS] Setup completed!
echo [INFO] Virtual environment: %VENV_DIR%
echo [INFO] Usage: Drag XML folder to stitch.bat
echo.
pause
endlocal