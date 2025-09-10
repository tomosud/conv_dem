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

### 🔸 単一フォルダ処理 (標準版)

1. **初回セットアップ**
   ```
   setup.bat を実行
   ```

2. **DEMデータを変換**
   ```
   XML群の入ったフォルダを stitch.bat にドラッグ&ドロップ
   ```
<img width="687" height="203" alt="image" src="https://github.com/user-attachments/assets/3f9bf9b4-acc6-4af4-a160-166a27fdfa2b" />

**出力ファイル:**
- `{フォルダ名}_resized.exr` - 3Dビューア用EXRファイル（アスペクト比補正）
- `{フォルダ名}.exr` - オリジナル解像度EXR
- `{フォルダ名}_mask.exr` / `{フォルダ名}_mask_resized.exr` - 欠損マスクファイル
- その他処理ログファイル

**特徴:**
- 欠損値補間処理（高品質）
- アスペクト比補正
- 部分データ対応

### 🔸 複数ファイル/ZIP処理 (マルチ版)

1. **初回セットアップ**
   ```
   setup.bat を実行
   ```

2. **複数のZIP/フォルダを一括変換**
   ```
   ZIP/フォルダ群を stitch_multi.bat にドラッグ&ドロップ
   ```

**出力ファイル:**
- `stitch_YYYYmmdd_HHMM.exr` - オリジナル解像度EXR
- `stitch_YYYYmmdd_HHMM_resized.exr` - アスペクト比補正版EXR

**特徴:**
- 複数ZIP/フォルダ対応
- 入れ子ZIP自動展開
- 高速処理（補間なし、欠損=0埋め）
- アスペクト比補正あり

---

## ❓ トラブルシューティング

### DEM Stitch Tool

- **"Virtual environment not found"**: `setup.bat`を先に実行
- **OpenEXRエラー**: `setup.bat`を再実行

### 標準版 vs マルチ版の使い分け

| 用途 | 標準版 (stitch.bat) | マルチ版 (stitch_multi.bat) |
|------|---------------------|------------------------------|
| **入力** | 単一フォルダ | 複数ZIP/フォルダ |
| **品質** | 高品質（補間処理あり） | 高速（補間なし） |
| **ファイル数** | 4つ（マスク含む） | 2つ（オリジナル+リサイズ） |
| **処理時間** | やや時間がかかる | 高速 |
| **用途** | 精密な地形解析 | 大量データの一括処理 |

---

## 📋 動作環境

- **ブラウザ**: Chrome, Firefox, Safari, Edge (WebGL対応)
- **Windows**: Python 3.11

---

