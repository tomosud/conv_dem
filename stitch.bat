@echo off
setlocal

REM === このBATと同じフォルダを基準に相対パスを解決 ===
set SCRIPT_DIR=%~dp0
set SCRIPT_DIR=%SCRIPT_DIR:~0,-1%

REM === 追加モジュール（相対）をPYTHONPATHに通す ===
set REL_MODULE_PATH=script\tom_oda\module\3.11
set PYTHONPATH=%SCRIPT_DIR%\%REL_MODULE_PATH%;%PYTHONPATH%

REM === Python実行ファイル（絶対パス指定：固定） ===
set PY_EXE=D:\KTN\SourceAssets\Tools\Python\env\Python311.4\python.exe

REM === 引数チェック（ドラッグ＆ドロップでフォルダが渡される想定）===
if "%~1"=="" (
    echo [ERROR] フォルダをこのBATにドラッグ＆ドロップしてください。
    pause
    exit /b 1
)

REM === ドロップされたパスを取得 ===
set TARGET_DIR=%~1

REM === 実行 ===
"%PY_EXE%" -X utf8 "%SCRIPT_DIR%\dem_stitch.py" "%TARGET_DIR%"
if errorlevel 1 (
    echo [ERROR] dem_stitch.py 実行でエラーが発生しました。
    pause
    exit /b 1
)

echo 完了: %TARGET_DIR%\dem_merged.exr
pause
endlocal
