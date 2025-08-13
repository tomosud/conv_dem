@echo off
chcp 65001 >nul
setlocal

REM === このBATと同じフォルダを基準に相対パスを解決 ===
set SCRIPT_DIR=%~dp0
set SCRIPT_DIR=%SCRIPT_DIR:~0,-1%

REM === 仮想環境のPython実行ファイル ===
set VENV_PYTHON=%SCRIPT_DIR%\venv\Scripts\python.exe

REM === 仮想環境の存在確認 ===
if not exist "%VENV_PYTHON%" (
    echo [ERROR] 仮想環境が見つかりません。先に setup.bat を実行してください。
    pause
    exit /b 1
)

REM === 引数チェック（ドラッグ＆ドロップでフォルダが渡される想定）===
if "%~1"=="" (
    echo [ERROR] フォルダをこのBATにドラッグ＆ドロップしてください。
    pause
    exit /b 1
)

REM === ドロップされたパスを取得 ===
set TARGET_DIR=%~1

REM === 実行 ===
"%VENV_PYTHON%" -X utf8 "%SCRIPT_DIR%\dem_stitch.py" "%TARGET_DIR%"
if errorlevel 1 (
    echo [ERROR] dem_stitch.py 実行でエラーが発生しました。
    pause
    exit /b 1
)

echo 完了: %TARGET_DIR%\dem_merged.exr
pause
endlocal
