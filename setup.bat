@echo off
chcp 65001 >nul
setlocal

REM ========================================
REM DEM Stitch Tool - 仮想環境セットアップ
REM ========================================

echo [INFO] DEM Stitch Tool の仮想環境をセットアップします...

REM === このBATと同じフォルダを基準に相対パスを解決 ===
set SCRIPT_DIR=%~dp0
set SCRIPT_DIR=%SCRIPT_DIR:~0,-1%

REM === 仮想環境ディレクトリ ===
set VENV_DIR=%SCRIPT_DIR%\venv

REM === Python実行ファイル（システムのPython3.11を使用） ===
set PY_EXE=D:\KTN\SourceAssets\Tools\Python\env\Python311.4\python.exe

REM === Python実行ファイルの存在確認 ===
if not exist "%PY_EXE%" (
    echo [ERROR] Python実行ファイルが見つかりません: %PY_EXE%
    pause
    exit /b 1
)

REM === 仮想環境の作成 ===
echo [INFO] 仮想環境を作成中... (%VENV_DIR%)
"%PY_EXE%" -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo [ERROR] 仮想環境の作成に失敗しました。
    pause
    exit /b 1
)

REM === 仮想環境のPythonパス ===
set VENV_PYTHON=%VENV_DIR%\Scripts\python.exe

REM === pipのアップグレード ===
echo [INFO] pipをアップグレード中...
"%VENV_PYTHON%" -m pip install --upgrade pip
if errorlevel 1 (
    echo [WARN] pipのアップグレードに失敗しましたが、続行します。
)

REM === 必要なライブラリをインストール ===
echo [INFO] 必要なライブラリをインストール中...
"%VENV_PYTHON%" -m pip install -r "%SCRIPT_DIR%\requirements.txt"
if errorlevel 1 (
    echo [ERROR] ライブラリのインストールに失敗しました。
    pause
    exit /b 1
)

echo.
echo [SUCCESS] セットアップが完了しました！
echo [INFO] 仮想環境: %VENV_DIR%
echo [INFO] 使用方法: XMLフォルダを stitch.bat にドラッグ&ドロップしてください。
echo.
pause
endlocal