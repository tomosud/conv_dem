D:\KTN\SourceAssets\Tools\Python\env\Python311.4\python.exe
上を使う。

ここにmoduleがすでにあるのでpathを通す
D:\KTN\SourceAssets\Tools\Python\script\tom_oda\module\3.11

import OpenEXR
import Imath
numpy pandasなども使用可能。

ただしpathはこのフォルダからの相対pathで。




作成指示書
目的
国土地理院の DEM5A（FGD GML, XML）タイル群（例：各タイル 225×150 点）を、自動的に**結合（モザイク）**して 2D の 標高 NumPy 配列を作成。

作成した配列を **OpenEXR（単チャンネル, float32）**として出力。

想定
ドロップするのは XMLファイル群が入ったフォルダ。

例：最終の完成サイズが 2250 × 1500（= 10×10 タイル）になるケースを含む。

## 2025-08-13 更新: 仮想環境対応

**変更理由**: numpy ライブラリの破損エラー対応のため、仮想環境を使用する方式に変更

**Python 実行方式**:
- 仮想環境: .\venv\ （ローカル仮想環境）
- ベースPython: D:\KTN\SourceAssets\Tools\Python\env\Python311.4\python.exe

**追加ファイル**:
- requirements.txt: 必要ライブラリの定義
- setup.bat: 仮想環境作成とライブラリインストール

**使用モジュール**: numpy, OpenEXR, Imath, chardet（文字化け対策）

**セットアップ手順**:
1. setup.bat を実行（初回のみ）
2. XMLフォルダを stitch.bat にドラッグ&ドロップ

**ファイル配置**:
```
<作業フォルダ>\
  setup.bat                    ← 初回セットアップ用
  stitch.bat                   ← XMLフォルダドロップ用BAT
  dem_stitch.py                ← 本体スクリプト
  requirements.txt             ← ライブラリ定義
  venv\                        ← 仮想環境（setup.bat実行後に作成）
    Scripts\
      python.exe               ← 仮想環境のPython
    Lib\
      site-packages\           ← インストール済みライブラリ
```
**動作フロー**:
1. ユーザーが XML群の入ったフォルダを stitch.bat にドラッグ＆ドロップ
2. stitch.bat が仮想環境のPython（.\venv\Scripts\python.exe）で dem_stitch.py を起動
3. 引数でドロップフォルダの絶対パスを渡す

dem_stitch.py が以下を実施：

フォルダ内の *.xml を再帰的に収集

各XMLから以下を取得

タイルの範囲（gml:boundedBy/gml:Envelope の lowerCorner / upperCorner）

格子サイズ（gml:GridEnvelope の low/high → 点数 = high - low + 1）

標高値（gml:tupleList の行：地表面,<float> 形式）

各タイルを (rows, cols) = (150, 225) の np.float32 配列に整形
（行優先で reshape。欠損は np.nan にする）

タイルの Y方向（緯度）: 降順（北を上）、**X方向（経度）: 昇順（東を右）**で並べ替え、行列位置を自動割付

しきい値付きクラスタリング（緯度/経度の固有値を丸めてユニーク化）で行・列インデックスに変換

配列貼り込み時は タイルの重複境界を除かず、1タイル＝そのまま 225×150 として敷き詰め
（※ユーザーの「結合すると 2250×1500 になる」前提に合わせる）

すべてのタイルを貼り込み、全体配列を生成

例：X方向タイル数 Tx、Y方向タイル数 Ty → 出力形状 = (Ty*150, Tx*225)

不足タイルがあって穴が空く場合は np.nan のまま（EXRには float32 で書き出し）

出力先：ドロップしたフォルダの直下に

dem_merged.exr（OpenEXR, 単チャンネル R, FLOAT）

dem_merged.npy（NumPy バイナリ；任意）

dem_merged_shape.txt（形状やタイル配置のログ；任意）

エッジケース仕様
orientation（上下反転の可能性）：仕様上、tupleList の走査順は「x が速く増え、その後 y」を想定。北が上になるよう、緯度が大きい列（北側）を小さい row インデックスに割付。万一上下が逆に見える場合は、スクリプト先頭の FORCE_FLIP_Y フラグで反転可能にしておく。

欠損値：-9999 や空欄に遭遇したら np.nan に変換。

サイズ検証：各タイルが (rows, cols) = (150, 225) でない場合は警告ログを出しつつスキップ（データ混在対策）。

タイル座標のクラスタ閾値：緯度・経度は微小な浮動小数のズレがあり得るため、丸め（例：1e-9～1e-7オーダー）を使って列挙→ユニーク化する。

**使い方（ユーザー向け）**:
1. 初回のみ: setup.bat を実行して仮想環境をセットアップ
2. XML群の入ったフォルダを stitch.bat にドラッグ＆ドロップ
3. 完了後、ドロップしたフォルダに dem_merged.exr が生成される

**トラブルシューティング**:
- "仮想環境が見つかりません" エラー: setup.bat を先に実行してください
- OpenEXRエラー: requirements.txt の内容を確認し、再度 setup.bat を実行してください