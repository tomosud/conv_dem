# EXR Heightmap Viewer & DEM Tools

国土地理院のDEMデータをOpenEXR形式に変換し、ブラウザで3D可視化するツールセット

**[https://service.gsi.go.jp/kiban/app/](https://service.gsi.go.jp/kiban/app/)**

数値標高モデルのDEMデータ（1ｍ/5ｍグリッド）のXML群からhightMapを書き出す変換ツール、およびビュワー。
変換Toolはpythonで。ビュワーはwebビュワーとしてそのまま使用できます。

---

## 🌐 EXR Heightmap Viewer

**ブラウザでEXRファイルを3D地形として表示**

### アクセス

**[https://tomosud.github.io/conv_dem/viewer/](https://tomosud.github.io/conv_dem/viewer/)**

<img width="1495" alt="EXR Heightmap Viewer" src="https://github.com/user-attachments/assets/be01063a-31ed-4c1d-8026-ffc335e02054">

### 使い方

1. **上記URLをブラウザで開く**
2. **EXRファイルをドラッグ&ドロップ**
3. **3D地形が表示されます**

### 操作方法

- **マウス左ドラッグ**: 視点回転
- **マウスホイール**: ズーム
- **マウス右ドラッグ**: 移動
- **1m/5mボタン**: グリッド解像度切り替え
- **視点リセット**: 初期位置に戻る

---

## 🔧 DEM Stitch Tool

**XMLタイルをEXRに変換**

### 使用方法

1. **初回セットアップ**
   ```
   setup.bat を実行
   ```

2. **DEMデータを変換**
   ```
   XML群の入ったフォルダを stitch.bat にドラッグ&ドロップ
   ```
<img width="687" height="203" alt="image" src="https://github.com/user-attachments/assets/3f9bf9b4-acc6-4af4-a160-166a27fdfa2b" />

### 出力ファイル

- `{フォルダ名}_resized.exr` - 3Dビューア用EXRファイル
- `{フォルダ名}.exr` - オリジナル解像度EXR
- その他処理ログファイル

---

## ❓ トラブルシューティング

### DEM Stitch Tool

- **"Virtual environment not found"**: `setup.bat`を先に実行
- **OpenEXRエラー**: `setup.bat`を再実行

---

## 📋 動作環境

- **ブラウザ**: Chrome, Firefox, Safari, Edge (WebGL対応)
- **Windows**: Python 3.11

---

