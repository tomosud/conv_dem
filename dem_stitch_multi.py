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

import sys, argparse, tempfile, shutil, zipfile, datetime
from pathlib import Path

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
    with zipfile.ZipFile(zip_path, 'r') as z:
        for info in z.infolist():
            name = info.filename
            low = name.lower()
            # 内包zipは抽出（後で再帰）
            if low.endswith(".zip"):
                z.extract(info, path=out_dir)
                continue
            # xml名で一次判定
            if looks_like_dem_xml_name(low):
                # ヘッダだけ読んで最終判定
                with z.open(info, 'r') as f:
                    head = f.read(sniff_kb * 1024).decode("utf-8", errors="ignore")
                if looks_like_dem_xml_head(head):
                    z.extract(info, path=out_dir)

# ------------------------------------------------------------
# 入力群から DEM XML を収集（テンポラリ使用）
# ------------------------------------------------------------
def collect_dem_xmls_from_inputs(inputs):
    tmp_root = tempfile.TemporaryDirectory()
    tmp_dir = Path(tmp_root.name)
    work_dirs = []

    for p in inputs:
        p = Path(p)
        if p.is_file() and p.suffix.lower() == ".zip":
            out = tmp_dir / p.stem
            out.mkdir(parents=True, exist_ok=True)
            selective_extract_zip(p, out)
            work_dirs.append(out)
        elif p.is_dir():
            out = tmp_dir / p.name
            if out.exists():
                shutil.rmtree(out)
            shutil.copytree(p, out)
            work_dirs.append(out)
        else:
            print(f"[WARN] Unsupported path: {p}")

    # 内包ZIPを再帰展開（zipが無くなるまで）
    changed = True
    while changed:
        changed = False
        for base in list(work_dirs):
            for inner_zip in list(base.rglob("*.zip")):
                sub = inner_zip.with_suffix("")
                sub.mkdir(exist_ok=True)
                selective_extract_zip(inner_zip, sub)
                try:
                    inner_zip.unlink()
                except Exception:
                    pass
                work_dirs.append(sub)
                changed = True

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

    print(f"[INFO] collected DEM XML: {len(xmls)} files")
    return xmls, tmp_root  # tmp_root は呼び出し側のスコープが保持している間、生存

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
    args = ap.parse_args()

    inputs = [Path(p) for p in args.inputs]
    xmls, tmp_keeper = collect_dem_xmls_from_inputs(inputs)
    if not xmls:
        print("[ERROR] DEM XML が見つかりませんでした。")
        return 1

    tiles = []
    for x in xmls:
        try:
            tiles.append(parse_one(x))
        except Exception as e:
            print(f"[WARN] skip {x.name}: {e}")

    if not tiles:
        print("[ERROR] 有効なタイルがありません。")
        return 1

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

    out_path = out_dir / f"{out_base}.exr"
    save_exr_float32_R(out_path, mosaic)
    print(f"[OK] wrote {out_path}  shape={mosaic.shape}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
