# EXR Heightmap Viewer & DEM Tools

国土地理院のDEMデータをOpenEXR形式に変換し、ブラウザで3D可視化するツールセット

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

2. **XMLフォルダを変換**
   ```
   XMLフォルダを stitch.bat にドラッグ&ドロップ
   ```

### 出力ファイル

- `{フォルダ名}_resized.exr` - 3Dビューア用EXRファイル
- `{フォルダ名}.exr` - オリジナル解像度EXR
- その他処理ログファイル

---

## ❓ トラブルシューティング

### EXR Heightmap Viewer

- **ファイルが読み込めない**: EXRファイル形式を確認
- **動作が重い**: 5mグリッドモードを使用
- **表示がおかしい**: ブラウザを最新版に更新

### DEM Stitch Tool

- **"Virtual environment not found"**: `setup.bat`を先に実行
- **OpenEXRエラー**: `setup.bat`を再実行

---

## 📋 動作環境

- **ブラウザ**: Chrome, Firefox, Safari, Edge (WebGL対応)
- **Windows**: Python 3.11

---

*このプロジェクトは教育・研究目的で作成されました*