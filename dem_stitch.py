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

# 欠損値補間の設定
MAX_HOLE_SIZE = 20  # 補間する最大穴サイズ（ピクセル）
INTERPOLATION_KERNEL_SIZE = 5  # 補間時の周辺参照サイズ

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

        # GridFunctionのstartPointを確認（部分データの場合）
        start_point = None
        grid_func = root.find(".//gml:coverageFunction/gml:GridFunction/gml:startPoint", ns)
        if grid_func is not None:
            start_coords = grid_func.text.strip().split()
            start_x, start_y = int(start_coords[0]), int(start_coords[1])
            start_point = (start_x, start_y)
            print(f"[INFO] StartPoint detected: {os.path.basename(xml_path)} -> ({start_x}, {start_y})")

        expected_size = rows * cols
        
        # 値の数が期待値と異なる場合の処理
        if vals.size != expected_size:
            print(f"[INFO] Partial data detected: {os.path.basename(xml_path)} -> {vals.size}/{expected_size} values")
            
            # 不足分を0で埋めた配列を作成
            full_vals = np.zeros(expected_size, dtype=np.float32)
            
            if start_point is not None:
                # startPointが指定されている場合の配置計算
                start_x, start_y = start_point
                
                # sequenceRule "+x-y" に従って配置
                val_idx = 0
                for y in range(start_y, rows):
                    for x in range(start_x, cols):
                        if val_idx < vals.size:
                            linear_idx = y * cols + x
                            if linear_idx < expected_size:
                                full_vals[linear_idx] = vals[val_idx]
                            val_idx += 1
                        else:
                            break
                    if val_idx >= vals.size:
                        break
                    # 次の行は x=0 から開始
                    start_x = 0
            else:
                # startPointが無い場合は先頭から配置
                copy_size = min(vals.size, expected_size)
                full_vals[:copy_size] = vals[:copy_size]
            
            vals = full_vals

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

def interpolate_small_holes(data):
    """
    高速な欠損値補間：ランダムサンプリングによる周囲探索
    """
    import random
    
    print("[INFO] Starting fast hole interpolation...")
    
    result = data.copy()
    H, W = result.shape
    
    total_missing = np.sum(result == 0.0)
    print(f"[INFO] Total missing pixels: {total_missing}")
    
    # 欠損ピクセルが多すぎる場合は処理をスキップ
    if total_missing > 1000000:  # 100万ピクセル以上
        print(f"[INFO] Too many missing pixels ({total_missing}), skipping interpolation")
        return result
    
    # 30回の反復処理
    for iteration in range(30):
        try:
            # 欠損値位置を取得
            missing_indices = np.where(result == 0.0)
            missing_count = len(missing_indices[0])
            
            if missing_count == 0:
                print(f"[INFO] No missing values remaining after iteration {iteration + 1}")
                break
            
            print(f"[INFO] Iteration {iteration + 1}/30: Processing {missing_count} missing pixels")
            
            interpolated_this_round = 0
            
            # 各欠損ピクセルを処理
            for idx in range(missing_count):
                y, x = missing_indices[0][idx], missing_indices[1][idx]
                
                if result[y, x] != 0.0:  # 既に補間済みの場合はスキップ
                    continue
                
                # ランダムに周囲を探索して2つの有効値を見つける
                valid_values = []
                search_radius = 5
                max_attempts = 20
                
                for _ in range(max_attempts):
                    # ランダムなオフセットを生成
                    dy = random.randint(-search_radius, search_radius)
                    dx = random.randint(-search_radius, search_radius)
                    
                    ny, nx = y + dy, x + dx
                    
                    # 境界チェック
                    if 0 <= ny < H and 0 <= nx < W:
                        value = result[ny, nx]
                        if value != 0.0:  # 有効値
                            valid_values.append(value)
                            
                            # 2つの有効値が見つかったら終了
                            if len(valid_values) >= 2:
                                break
                
                # 2つ以上の有効値が見つかった場合は平均で補間
                if len(valid_values) >= 2:
                    result[y, x] = np.mean(valid_values)
                    interpolated_this_round += 1
            
            print(f"[INFO] Iteration {iteration + 1}: Interpolated {interpolated_this_round} pixels")
            
            # 補間できるピクセルがなくなったら終了
            if interpolated_this_round == 0:
                break
                
        except Exception as e:
            print(f"[WARN] Error in iteration {iteration + 1}: {e}")
            break
    
    # 残った欠損値を0で埋める（実質的には既に0なので処理不要）
    final_missing = np.sum(result == 0.0)
    print(f"[INFO] Fast interpolation completed. Remaining missing pixels: {final_missing}")
    
    return result

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

    # 補間前の欠損マスクを作成（0=欠損、1=有効データ）
    original_mask = (out != 0.0).astype(np.float32)

    # 高速欠損値補間処理
    try:
        out = interpolate_small_holes(out)
    except Exception as e:
        print(f"[WARN] Hole interpolation failed: {e}")

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

    # 緯度経度範囲を全体から計算
    all_lat_min = min(t["lat_min"] for t in tiles)
    all_lat_max = max(t["lat_max"] for t in tiles)
    all_lon_min = min(t["lon_min"] for t in tiles)
    all_lon_max = max(t["lon_max"] for t in tiles)
    
    # スケール係数を計算
    scale_x = compute_scale_x_from_latlon(all_lat_min, all_lat_max, all_lon_min, all_lon_max, H, W)
    print(f"[INFO] Computed scale_x = {scale_x:.6f}")
    
    # スケール係数の逆数を使用（1.0/scale_x）
    corrected_scale_x = 1.0 / scale_x
    print(f"[INFO] Corrected scale_x (1.0/scale_x) = {corrected_scale_x:.6f}")
    
    # リサイズ後の横幅を計算
    new_w = max(1, int(round(W * corrected_scale_x)))
    print(f"[INFO] Resizing width from {W} to {new_w}")

    # OpenEXRで保存（リサイズ前）
    exr_path = os.path.join(in_dir, f"{folder_name}.exr")
    save_exr_float32_R(exr_path, out)
    print(f"[INFO] saved EXR: {exr_path}")
    
    # 補間前の欠損マスクを別ファイルで保存（リサイズ前）
    mask_exr_path = os.path.join(in_dir, f"{folder_name}_mask.exr")
    save_exr_float32_R(mask_exr_path, original_mask)
    print(f"[INFO] saved mask EXR: {mask_exr_path}")
    
    # リサイズ処理
    out_resized = resize_width_linear(out, new_w)
    original_mask_resized = resize_width_linear(original_mask, new_w)
    
    # OpenEXRで保存（リサイズ後）
    exr_resized_path = os.path.join(in_dir, f"{folder_name}_resized.exr")
    save_exr_float32_R(exr_resized_path, out_resized)
    print(f"[INFO] saved resized EXR: {exr_resized_path}")
    
    # 補間前の欠損マスクを別ファイルで保存（リサイズ後）
    mask_resized_exr_path = os.path.join(in_dir, f"{folder_name}_mask_resized.exr")
    save_exr_float32_R(mask_resized_exr_path, original_mask_resized)
    print(f"[INFO] saved resized mask EXR: {mask_resized_exr_path}")

def save_exr_float32_RG(path, dem_data, mask_data):
    """
    2チャンネル EXR として保存
    dem_data: (H,W) float32 - DEMデータ（Rチャンネル）
    mask_data: (H,W) float32 - 欠損マスク（Gチャンネル、0=欠損、1=有効）
    """
    H, W = dem_data.shape
    header = OpenEXR.Header(W, H)
    # ピクセルタイプ（32-bit float）
    pt = Imath.PixelType(Imath.PixelType.FLOAT)

    # NumPy -> bytes
    chan_R = dem_data.astype(np.float32).tobytes()
    chan_G = mask_data.astype(np.float32).tobytes()

    header['channels'] = {
        'R': Imath.Channel(pt),  # DEMデータ
        'G': Imath.Channel(pt)   # 欠損マスク
    }
    exr = OpenEXR.OutputFile(path, header)
    exr.writePixels({'R': chan_R, 'G': chan_G})
    exr.close()

def compute_scale_x_from_latlon(lat_min, lat_max, lon_min, lon_max, rows, cols):
    """
    緯度経度範囲から横方向のスケール係数を計算
    縦解像度はそのまま、横を拡大してアスペクト比を補正
    """
    lat_span = lat_max - lat_min
    lon_span = lon_max - lon_min
    dlat = lat_span / rows
    dlon = lon_span / cols
    phi = 0.5 * (lat_min + lat_max)  # 中央緯度
    # 横方向のみ拡大する係数（縦=1.0）
    scale_x = (dlat / dlon) * (1.0 / math.cos(math.radians(phi)))
    return scale_x

def resize_width_linear(img, new_w):
    """
    画像の横幅のみをリニア補間でリサイズ
    """
    H, W = img.shape
    if new_w == W:
        return img.copy()
    
    x_old = np.linspace(0.0, 1.0, W, endpoint=True)
    x_new = np.linspace(0.0, 1.0, new_w, endpoint=True)
    out = np.empty((H, new_w), dtype=img.dtype)
    for y in range(H):
        out[y] = np.interp(x_new, x_old, img[y])
    return out

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
