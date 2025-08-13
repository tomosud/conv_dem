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

import numpy as np
import OpenEXR, Imath

# -----------------------------------------
# 設定（必要に応じて調整）
# -----------------------------------------
EXPECTED_COLS = 225   # X 方向点数（1タイル）
EXPECTED_ROWS = 150   # Y 方向点数（1タイル）

# tupleList の走査順が想定と逆だった場合に備えた強制フリップ
FORCE_FLIP_Y = False

# 緯度・経度クラスタリングの丸め（同一行/列の判断用）
ROUND_DECIMALS = 10   # 小数10桁程度で丸め

# 欠損値文字列
MISSING_TOKENS = {"", "-9999", "-9999.0", "-9999.00"}

# -----------------------------------------
def parse_tile(xml_path):
    """
    1タイルXMLから:
      - lat_min, lon_min, lat_max, lon_max（float）
      - data2d: (rows, cols) = (EXPECTED_ROWS, EXPECTED_COLS) の np.float32
    を返す。失敗時は None を返す。
    """
    try:
        tree = ET.parse(xml_path)
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

        if cols != EXPECTED_COLS or rows != EXPECTED_ROWS:
            print(f"[WARN] Grid size mismatch: {os.path.basename(xml_path)} -> ({rows},{cols})")
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
                vals.append(np.nan)
            else:
                try:
                    vals.append(float(token))
                except:
                    vals.append(np.nan)

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

    tiles = []
    for x in xmls:
        t = parse_tile(x)
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
    print(f"[INFO] Tiling grid (Tx,Ty) = ({Tx},{Ty})  -> output shape = ({Ty*EXPECTED_ROWS}, {Tx*EXPECTED_COLS})")

    H = Ty * EXPECTED_ROWS
    W = Tx * EXPECTED_COLS
    out = np.full((H, W), np.nan, dtype=np.float32)

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

        y0, y1 = r * EXPECTED_ROWS, (r + 1) * EXPECTED_ROWS
        x0, x1 = c * EXPECTED_COLS, (c + 1) * EXPECTED_COLS

        tile = t["data"]
        if tile.shape != (EXPECTED_ROWS, EXPECTED_COLS):
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

    # npy保存（任意）
    np.save(os.path.join(in_dir, "dem_merged.npy"), out)

    # OpenEXRで保存（単チャンネルR, float32）
    exr_path = os.path.join(in_dir, "dem_merged.exr")
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
