# -*- coding: utf-8 -*-
"""
dem_stitch_multi.py
複数のZIP/フォルダを再帰的に走査し、GSIのDEM XMLを収集・結合して
1枚のEXR（float32, 1ch）として出力します。

仕様:
- 入力: ZIPまたはフォルダ（複数可、入れ子ZIP可）
- dem_stitch.py と同じフォルダに置くこと（必須）。dem_stitch.parse_tile を使用（フォールバック無し）
- 解像度は揃っている前提（リサンプル無し）
- 欠損補間はしない。NaN は 0 に置換して出力（海や欠損=0）
- 出力先: 既定は「最初にドロップしたパスの親フォルダ」
- 出力名: 指定が無ければ stitch_YYYYmmdd_HHMM.exr
"""

import sys, argparse, tempfile, shutil, zipfile, datetime, math
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import partial
import os

import numpy as np
import OpenEXR, Imath

# ------------------------------------------------------------
# dem_stitch.py を強制的に import（フォールバック無し）
# ------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import dem_stitch as DS   # 失敗したら例外で落ちてOK

# ------------------------------------------------------------
# EXR書き出し（1ch, R）
# ------------------------------------------------------------
def save_exr_float32_R(path, arr: np.ndarray):
    h, w = arr.shape
    header = OpenEXR.Header(w, h)
    header['channels'] = {'R': Imath.Channel(Imath.PixelType(Imath.PixelType.FLOAT))}
    exr = OpenEXR.OutputFile(str(path), header)
    exr.writePixels({'R': arr.astype('float32').tobytes()})
    exr.close()

# ------------------------------------------------------------
# 緯度経度からアスペクト比補正用スケール係数を計算
# ------------------------------------------------------------
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
    画像の横幅のみをリニア補間でリサイズ（高速化版）
    """
    H, W = img.shape
    if new_w == W:
        return img.copy()
    
    # ベクトル化された高速リサイズ
    x_old = np.linspace(0.0, 1.0, W, endpoint=True)
    x_new = np.linspace(0.0, 1.0, new_w, endpoint=True)
    
    # 全行を一度に補間（メモリ効率とのバランスを考慮）
    chunk_size = min(H, 1000)  # メモリ使用量制限
    out = np.empty((H, new_w), dtype=img.dtype)
    
    for start in range(0, H, chunk_size):
        end = min(start + chunk_size, H)
        chunk = img[start:end]
        for i, row in enumerate(chunk):
            out[start + i] = np.interp(x_new, x_old, row)
    
    return out

# ------------------------------------------------------------
# DEM XML 判定（軽量）
# ------------------------------------------------------------
def looks_like_dem_xml_name(name: str) -> bool:
    n = name.lower()
    if not n.endswith(".xml"):
        return False
    # 明確に除外
    if n.startswith("fmdid") or "metadata" in n or n.endswith("_index.xml"):
        return False
    # 典型的DEM名は早期採用
    if n.startswith("fg-gml-") and "dem" in n:
        return True
    return True  # 最終判定はヘッダを見る

def looks_like_dem_xml_head(text_head: str) -> bool:
    h = text_head
    return ("<DEM" in h or "ElevationModel" in h or
            "tupleList" in h or "doubleOrNilReasonTupleList" in h)

# ------------------------------------------------------------
# ZIP の選択的展開：必要な .xml と 内包 .zip のみ
# ------------------------------------------------------------
def selective_extract_zip(zip_path: Path, out_dir: Path, sniff_kb: int = 8):
    extracted_count = 0
    with zipfile.ZipFile(zip_path, 'r') as z:
        for info in z.infolist():
            name = info.filename
            low = name.lower()
            # 内包zipは抽出（後で再帰）
            if low.endswith(".zip"):
                z.extract(info, path=out_dir)
                extracted_count += 1
                continue
            # xml名で一次判定
            if looks_like_dem_xml_name(low):
                # ヘッダだけ読んで最終判定
                with z.open(info, 'r') as f:
                    head = f.read(sniff_kb * 1024).decode("utf-8", errors="ignore")
                if looks_like_dem_xml_head(head):
                    z.extract(info, path=out_dir)
                    extracted_count += 1
    return extracted_count

def extract_zip_worker(args):
    """ZIP展開のワーカー関数"""
    zip_path, out_dir = args
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        count = selective_extract_zip(zip_path, out_dir)
        return str(out_dir), count, None
    except Exception as e:
        return None, 0, f"{zip_path.name}: {e}"

# ------------------------------------------------------------
# 入力群から DEM XML を収集（テンポラリ使用）
# ------------------------------------------------------------
def collect_dem_xmls_from_inputs(inputs, max_workers=None):
    if max_workers is None:
        max_workers = min(4, os.cpu_count() or 2)  # ZIP展開はI/O律速なので控えめ
    
    tmp_root = tempfile.TemporaryDirectory()
    tmp_dir = Path(tmp_root.name)
    work_dirs = []

    # 初期展開（並列処理）
    zip_jobs = []
    for p in inputs:
        p = Path(p)
        if p.is_file() and p.suffix.lower() == ".zip":
            out = tmp_dir / p.stem
            zip_jobs.append((p, out))
        elif p.is_dir():
            out = tmp_dir / p.name
            if out.exists():
                shutil.rmtree(out)
            shutil.copytree(p, out)
            work_dirs.append(out)
        else:
            print(f"[WARN] Unsupported path: {p}")

    if zip_jobs:
        print(f"[INFO] Extracting {len(zip_jobs)} ZIP files...")
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(extract_zip_worker, zip_jobs))
        
        for result_dir, count, error in results:
            if error:
                print(f"[WARN] {error}")
            else:
                work_dirs.append(Path(result_dir))
                if count > 0:
                    print(f"[INFO] Extracted {count} files from {Path(result_dir).name}")

    # 内包ZIPを再帰展開
    iteration = 1
    while True:
        inner_zips = []
        for base in work_dirs:
            inner_zips.extend(list(base.rglob("*.zip")))
        
        if not inner_zips:
            break
            
        print(f"[INFO] Recursion {iteration}: processing {len(inner_zips)} inner ZIPs...")
        
        zip_jobs = []
        for inner_zip in inner_zips:
            sub = inner_zip.with_suffix("")
            zip_jobs.append((inner_zip, sub))
        
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(extract_zip_worker, zip_jobs))
        
        for result_dir, count, error in results:
            if error:
                print(f"[WARN] {error}")
            else:
                work_dirs.append(Path(result_dir))
        
        # 元のZIPファイルを削除
        for inner_zip in inner_zips:
            try:
                inner_zip.unlink()
            except Exception:
                pass
        
        iteration += 1
        if iteration > 10:  # 無限ループ防止
            print("[WARN] Too many recursion levels, stopping")
            break

    # XML収集
    xmls = []
    for d in work_dirs:
        for x in d.rglob("*.xml"):
            n = x.name.lower()
            if looks_like_dem_xml_name(n):
                try:
                    head = x.read_text("utf-8", errors="ignore")[:8*1024]
                except Exception:
                    continue
                if looks_like_dem_xml_head(head):
                    xmls.append(x)

    print(f"[INFO] Collected {len(xmls)} DEM XML files")
    return xmls, tmp_root

# ------------------------------------------------------------
# 既存 parse_tile() を用いて1XML→タイル辞書に変換（NaN→0）
# ------------------------------------------------------------
def parse_one(xml_path: Path):
    t = DS.parse_tile(str(xml_path), expected_cols=None, expected_rows=None)
    if t is None:
        raise ValueError("parse_tile returned None")
    arr = np.asarray(t["data"], dtype=np.float32)
    t["data2d"] = np.nan_to_num(arr, nan=0.0)  # 欠損は0
    return t

def parse_one_worker(xml_path_str):
    """並列処理用のワーカー関数"""
    try:
        xml_path = Path(xml_path_str)
        return parse_one(xml_path), None
    except Exception as e:
        return None, f"{Path(xml_path_str).name}: {e}"

def parse_tiles_parallel(xml_paths, max_workers=None):
    """XMLファイルを並列処理でパース"""
    if max_workers is None:
        max_workers = min(len(xml_paths), os.cpu_count() or 4)
    
    tiles = []
    errors = []
    
    print(f"[INFO] Parsing {len(xml_paths)} XML files using {max_workers} workers...")
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(parse_one_worker, str(xml)): xml for xml in xml_paths}
        
        completed = 0
        for future in as_completed(futures):
            completed += 1
            xml_path = futures[future]
            tile, error = future.result()
            
            if tile:
                tiles.append(tile)
            else:
                errors.append(error)
            
            # プログレス表示（10%刻み）
            progress = (completed * 100) // len(xml_paths)
            if completed % max(1, len(xml_paths) // 10) == 0 or completed == len(xml_paths):
                print(f"[PROGRESS] {completed}/{len(xml_paths)} ({progress}%) parsed")
    
    if errors:
        print(f"[WARN] Skipped {len(errors)} files with errors")
        if len(errors) <= 5:  # エラーが少ない場合のみ詳細表示
            for err in errors:
                print(f"[WARN] {err}")
    
    return tiles

# ------------------------------------------------------------
# タイル結合（行=北→南, 列=西→東）
# ------------------------------------------------------------
def _unique_sorted(arr, decimals=10, reverse=False):
    return sorted({round(a, decimals) for a in arr}, reverse=reverse)

def build_mosaic(tiles, round_decimals=10):
    # キー抽出（代表点: 北端lat_max / 西端lon_min）
    lat_keys = [t["lat_max"] for t in tiles]
    lon_keys = [t["lon_min"] for t in tiles]
    row_bands = _unique_sorted(lat_keys, decimals=round_decimals, reverse=True)   # 北→南
    col_bands = _unique_sorted(lon_keys, decimals=round_decimals, reverse=False)  # 西→東

    # 各帯の最大サイズを採用（同解像度前提）
    row_heights = {rk: max(t["rows"] for t in tiles if round(t["lat_max"], round_decimals) == rk) for rk in row_bands}
    col_widths  = {ck: max(t["cols"] for t in tiles if round(t["lon_min"],  round_decimals) == ck) for ck in col_bands}

    total_h = sum(row_heights.values())
    total_w = sum(col_widths.values())
    mosaic = np.zeros((total_h, total_w), dtype=np.float32)  # 欠損=0

    # オフセット
    y_off, acc = {}, 0
    for rk in row_bands:
        y_off[rk] = acc
        acc += row_heights[rk]
    x_off, acc = {}, 0
    for ck in col_bands:
        x_off[ck] = acc
        acc += col_widths[ck]

    # 配置（重複は後勝ち）
    for t in tiles:
        rk = round(t["lat_max"], round_decimals)
        ck = round(t["lon_min"],  round_decimals)
        y0, x0 = y_off[rk], x_off[ck]
        h, w = t["rows"], t["cols"]
        mosaic[y0:y0+h, x0:x0+w] = t["data2d"]

    return mosaic

# ------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", help="ZIPまたはフォルダ（複数可）")
    ap.add_argument("--out", default=None, help="出力ファイル名（拡張子不要）")
    ap.add_argument("--outdir", default=None, help="出力先ディレクトリ（省略時: 最初の入力の親）")
    ap.add_argument("--round", type=int, default=10, help="タイル境界丸め桁（既定=10）")
    ap.add_argument("--workers", type=int, default=None, help="並列処理ワーカー数（省略時: 自動）")
    args = ap.parse_args()

    print(f"[INFO] Processing {len(args.inputs)} input(s)...")
    inputs = [Path(p) for p in args.inputs]
    xmls, tmp_keeper = collect_dem_xmls_from_inputs(inputs, max_workers=args.workers)
    if not xmls:
        print("[ERROR] No DEM XML files found")
        return 1

    tiles = parse_tiles_parallel(xmls, max_workers=args.workers)
    if not tiles:
        print("[ERROR] No valid tiles processed")
        return 1

    print(f"[INFO] Building mosaic from {len(tiles)} tiles...")
    mosaic = build_mosaic(tiles, round_decimals=args.round)

    # 出力先
    if args.outdir:
        out_dir = Path(args.outdir)
    else:
        # 「ドロップ元のフォルダ」= 最初の入力の親
        first = inputs[0]
        out_dir = (first.parent if first.is_file() else first)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 出力名
    if args.out:
        out_base = args.out
    else:
        now = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        out_base = f"stitch_{now}"

    # 緯度経度範囲を計算
    all_lat_min = min(t["lat_min"] for t in tiles)
    all_lat_max = max(t["lat_max"] for t in tiles)
    all_lon_min = min(t["lon_min"] for t in tiles)
    all_lon_max = max(t["lon_max"] for t in tiles)
    
    H, W = mosaic.shape
    
    # スケール係数を計算
    scale_x = compute_scale_x_from_latlon(all_lat_min, all_lat_max, all_lon_min, all_lon_max, H, W)
    corrected_scale_x = 1.0 / scale_x
    new_w = max(1, int(round(W * corrected_scale_x)))
    
    print(f"[INFO] Aspect correction: {W} -> {new_w} pixels (scale={corrected_scale_x:.4f})")

    # OpenEXRで保存（オリジナル）
    print("[INFO] Saving original EXR...")
    out_path = out_dir / f"{out_base}.exr"
    save_exr_float32_R(out_path, mosaic)
    
    # リサイズ処理
    print("[INFO] Applying aspect correction...")
    mosaic_resized = resize_width_linear(mosaic, new_w)
    
    # OpenEXRで保存（リサイズ後）
    print("[INFO] Saving corrected EXR...")
    out_resized_path = out_dir / f"{out_base}_resized.exr"
    save_exr_float32_R(out_resized_path, mosaic_resized)
    
    print(f"[COMPLETE] Original: {out_path} ({mosaic.shape})")
    print(f"[COMPLETE] Corrected: {out_resized_path} ({mosaic_resized.shape})")
    return 0

if __name__ == "__main__":
    sys.exit(main())
