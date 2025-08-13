# -*- coding: utf-8 -*-
"""
DEM(GML/XML) タイル群を結合して NumPy 配列化し、OpenEXR(float32, 1ch)で書き出すスクリプト。
使い方: dem_stitch.bat に XML群フォルダをドラッグ＆ドロップ
"""

import sys
import os
import glob
import math
import xml.etree.ElementTree as ET

# OpenEXRを先にimportしてから、numpyをimport
try:
    import OpenEXR
    import Imath
except ImportError as e:
    print(f"[ERROR] OpenEXRライブラリのimportに失敗しました: {e}")
    print("[INFO] 'pip install OpenEXR' または 'pip install PyOpenEXR' を試してください。")
    sys.exit(1)

import numpy as np

# -----------------------------------------
# 設定（必要に応じて調整）
# -----------------------------------------
# タイルサイズは最初のXMLから自動取得する
EXPECTED_COLS = None   # X 方向点数（1タイル） - 自動取得
EXPECTED_ROWS = None   # Y 方向点数（1タイル） - 自動取得

# tupleList の走査順が想定と逆だった場合に備えた強制フリップ
FORCE_FLIP_Y = False

# 緯度・経度クラスタリングの丸め（同一行/列の判断用）
ROUND_DECIMALS = 10   # 小数10桁程度で丸め

# 欠損値文字列（従来の-9999パターン）
MISSING_TOKENS = {"", "-9999", "-9999.0", "-9999.00"}

# 欠損値の数値判定閾値（-9990以下は欠損値とみなす）
MISSING_THRESHOLD = -9990

# -----------------------------------------
def parse_tile(xml_path, expected_cols=None, expected_rows=None):
    """
    1タイルXMLから:
      - lat_min, lon_min, lat_max, lon_max（float）
      - data2d: (rows, cols) の np.float32
      - cols, rows (実際のサイズ)
    を返す。失敗時は None を返す。
    expected_cols/rowsが指定されていない場合は、XMLから取得したサイズをそのまま使用。
    """
    try:
        # XMLファイルの読み込み（文字化け対策）
        with open(xml_path, 'r', encoding='utf-8') as f:
            tree = ET.parse(f)
        root = tree.getroot()
        ns = {
            "gml": "http://www.opengis.net/gml/3.2",
            "fgd": "http://fgd.gsi.go.jp/spec/2008/FGD_GMLSchema",
        }

        # Envelope 取得
        env = root.find(".//gml:boundedBy/gml:Envelope", ns)
        lower = env.find("gml:lowerCorner", ns).text.strip().split()
        upper = env.find("gml:upperCorner", ns).text.strip().split()

        # GMLのcorner順序は "緯度 経度" 想定（例: 34 135.25）
        lat_min, lon_min = float(lower[0]), float(lower[1])
        lat_max, lon_max = float(upper[0]), float(upper[1])

        # Gridサイズ確認
        low = root.find(".//gml:Grid/gml:limits/gml:GridEnvelope/gml:low", ns).text.strip().split()
        high = root.find(".//gml:Grid/gml:limits/gml:GridEnvelope/gml:high", ns).text.strip().split()
        low_x, low_y = int(low[0]), int(low[1])
        high_x, high_y = int(high[0]), int(high[1])

        cols = high_x - low_x + 1
        rows = high_y - low_y + 1

        # expected_cols/rowsが指定されている場合のみサイズチェック
        if expected_cols is not None and expected_rows is not None:
            if cols != expected_cols or rows != expected_rows:
                print(f"[WARN] Grid size mismatch: {os.path.basename(xml_path)} -> ({rows},{cols}), expected ({expected_rows},{expected_cols})")
                return None

        # 標高値の抽出（gml:tupleList）
        tlist = root.find(".//gml:rangeSet/gml:DataBlock/gml:tupleList", ns)
        raw = tlist.text.strip().splitlines()

        vals = []
        for line in raw:
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 2:
                # まれに「値だけ」など崩れた行に保険
                token = parts[-1] if parts else ""
            else:
                token = parts[-1]

            if token in MISSING_TOKENS:
                vals.append(0.0)
            else:
                try:
                    val = float(token)
                    # -9990以下は欠損値として0に変換
                    if val <= MISSING_THRESHOLD:
                        vals.append(0.0)
                    else:
                        vals.append(val)
                except:
                    vals.append(0.0)

        vals = np.array(vals, dtype=np.float32)

        # 行優先で reshape（x が速く、次いで y が進む想定）
        if vals.size != rows * cols:
            print(f"[WARN] Value count mismatch: {os.path.basename(xml_path)} -> {vals.size} values")
            return None

        data2d = vals.reshape((rows, cols))

        if FORCE_FLIP_Y:
            data2d = np.flipud(data2d)

        return {
            "path": xml_path,
            "lat_min": lat_min, "lon_min": lon_min,
            "lat_max": lat_max, "lon_max": lon_max,
            "rows": rows, "cols": cols,
            "data": data2d
        }

    except Exception as e:
        print(f"[ERROR] parse failed: {xml_path} -> {e}")
        return None

def unique_sorted_with_round(values, reverse=False):
    """
    浮動小数の微小差を吸収するために丸めてからユニーク化。
    reverse=True のとき降順（北を上＝緯度は降順ソートに使う）。
    """
    rounded = [round(v, ROUND_DECIMALS) for v in values]
    uniq = sorted(set(rounded), reverse=reverse)
    # 丸め後の値→元値の代表 という対応は不要（行列インデックス化だけに使う）
    return uniq

def main():
    if len(sys.argv) < 2:
        print("[ERROR] 入力フォルダパスがありません。BATにXMLフォルダをドロップしてください。")
        sys.exit(1)

    in_dir = os.path.abspath(sys.argv[1])
    if not os.path.isdir(in_dir):
        print(f"[ERROR] 指定パスがフォルダではありません: {in_dir}")
        sys.exit(1)

    # XML収集
    xmls = glob.glob(os.path.join(in_dir, "**", "*.xml"), recursive=True)
    if not xmls:
        print(f"[ERROR] XMLが見つかりません: {in_dir}")
        sys.exit(1)

    print(f"[INFO] XML files: {len(xmls)}")

    # 最初のXMLからタイルサイズを自動取得
    first_tile = None
    for x in xmls:
        t = parse_tile(x)  # まず最初の1つを解析してサイズを決定
        if t is not None:
            first_tile = t
            break
    
    if first_tile is None:
        print("[ERROR] No valid XML files found for size detection.")
        sys.exit(1)
    
    # 標準タイルサイズを設定
    standard_cols = first_tile["cols"]
    standard_rows = first_tile["rows"]
    print(f"[INFO] Standard tile size detected: ({standard_rows}, {standard_cols})")

    tiles = []
    for x in xmls:
        t = parse_tile(x, standard_cols, standard_rows)
        if t is not None:
            tiles.append(t)

    if not tiles:
        print("[ERROR] 有効なタイルがありません。終了します。")
        sys.exit(1)

    # タイル位置決定：
    # 行インデックス: 緯度で決定（北=大→小の順で並べ、0 行目が最北）
    # 列インデックス: 経度で決定（西=小→大の順で並べ、0 列目が最西）
    # 代表点として lat_max（北端）、lon_min（西端）を使うと安定しやすい
    lat_keys = [t["lat_max"] for t in tiles]  # 北端で行クラスタ
    lon_keys = [t["lon_min"] for t in tiles]  # 西端で列クラスタ

    row_bands = unique_sorted_with_round(lat_keys, reverse=True)   # 北→南
    col_bands = unique_sorted_with_round(lon_keys, reverse=False)  # 西→東

    Ty = len(row_bands)
    Tx = len(col_bands)
    print(f"[INFO] Tiling grid (Tx,Ty) = ({Tx},{Ty})  -> output shape = ({Ty*standard_rows}, {Tx*standard_cols})")

    H = Ty * standard_rows
    W = Tx * standard_cols
    out = np.full((H, W), 0.0, dtype=np.float32)

    # タイルを貼り込む
    placed = 0
    for t in tiles:
        # 行・列の決定
        r_key = round(t["lat_max"], ROUND_DECIMALS)   # 北端で行
        c_key = round(t["lon_min"], ROUND_DECIMALS)   # 西端で列
        try:
            r = row_bands.index(r_key)
            c = col_bands.index(c_key)
        except ValueError:
            # 丸めの差が極端な場合は近傍検索
            r = min(range(Ty), key=lambda i: abs(row_bands[i] - r_key))
            c = min(range(Tx), key=lambda i: abs(col_bands[i] - c_key))

        y0, y1 = r * standard_rows, (r + 1) * standard_rows
        x0, x1 = c * standard_cols, (c + 1) * standard_cols

        tile = t["data"]
        if tile.shape != (standard_rows, standard_cols):
            print(f"[WARN] Skip irregular tile size: {os.path.basename(t['path'])}")
            continue

        out[y0:y1, x0:x1] = tile
        placed += 1

    print(f"[INFO] placed tiles: {placed}/{len(tiles)}")

    # 形状ログ
    with open(os.path.join(in_dir, "dem_merged_shape.txt"), "w", encoding="utf-8") as f:
        f.write(f"tiles_in: {len(tiles)}\n")
        f.write(f"placed: {placed}\n")
        f.write(f"grid: Tx={Tx}, Ty={Ty}\n")
        f.write(f"shape: H={H}, W={W}\n")

    # フォルダ名を取得してファイル名に使用
    folder_name = os.path.basename(os.path.abspath(in_dir))
    
    # npy保存（任意）
    npy_path = os.path.join(in_dir, f"{folder_name}.npy")
    np.save(npy_path, out)

    # OpenEXRで保存（単チャンネルR, float32）
    exr_path = os.path.join(in_dir, f"{folder_name}.exr")
    save_exr_float32_R(exr_path, out)
    print(f"[INFO] saved EXR: {exr_path}")

def save_exr_float32_R(path, img2d):
    """
    img2d: (H,W) float32
    単チャンネル 'R' として保存。圧縮は ZIP（デフォルト）。
    """
    H, W = img2d.shape
    header = OpenEXR.Header(W, H)
    # ピクセルタイプ（32-bit float）
    pt = Imath.PixelType(Imath.PixelType.FLOAT)

    # EXR はスキャンライン上から下なので、そのまま書ける
    # NumPy -> bytes
    # OpenEXR はチャネルごとにバイト列を要求
    # メモリは行連続を仮定
    chan_R = img2d.astype(np.float32).tobytes()

    header['channels'] = {'R': Imath.Channel(pt)}
    exr = OpenEXR.OutputFile(path, header)
    exr.writePixels({'R': chan_R})
    exr.close()

if __name__ == "__main__":
    main()
