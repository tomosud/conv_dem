# -*- coding: utf-8 -*-
"""
dem_stitch_multi.py
複数のZIP/フォルダを再帰的に走査し、GSIのDEM XMLを収集・結合して
1枚のEXR（float32, 1ch）として出力します。
前提：すべて同一解像度（同一グリッド）であること。欠損補間は行いません（0埋め）。

使い方（例）:
    python dem_stitch_multi.py <zip_or_dir> [<zip_or_dir> ...] [--out OUTNAME] [--outdir OUTDIR]

出力:
    OUTDIR/OUTNAME.exr  （デフォルトは最初の入力の親フォルダに stitch_YYYYmmdd_HHMM.exr）
"""

import sys, os, argparse, tempfile, shutil, zipfile, datetime
from pathlib import Path

import numpy as np
import OpenEXR, Imath


# -----------------------------------------
# EXR書き出し（1ch, R）
# -----------------------------------------
def save_exr_float32_R(path, arr):
    h, w = arr.shape
    header = OpenEXR.Header(w, h)
    header['channels'] = {'R': Imath.Channel(Imath.PixelType(Imath.PixelType.FLOAT))}
    exr = OpenEXR.OutputFile(str(path), header)
    exr.writePixels({'R': arr.astype('float32').tobytes()})
    exr.close()


# -----------------------------------------
# DEM XML 判定（軽量）
# -----------------------------------------
def looks_like_dem_xml_name(name: str) -> bool:
    n = name.lower()
    if not n.endswith(".xml"):
        return False
    if n.startswith("fmdid") or "metadata" in n or n.endswith("_index.xml"):
        return False
    if n.startswith("fg-gml-") and "dem" in n:
        return True
    return True

def looks_like_dem_xml_head(text_head: str) -> bool:
    return ("<DEM" in text_head or "ElevationModel" in text_head or
            "tupleList" in text_head or "doubleOrNilReasonTupleList" in text_head)


# -----------------------------------------
# ZIP の選択的展開：必要な .xml と 内包 .zip のみ
# -----------------------------------------
def selective_extract_zip(zip_path: Path, out_dir: Path, sniff_kb: int = 8):
    with zipfile.ZipFile(zip_path, 'r') as z:
        for info in z.infolist():
            name = info.filename
            low = name.lower()
            if low.endswith(".zip"):
                z.extract(info, path=out_dir)
                continue
            if looks_like_dem_xml_name(low):
                with z.open(info, 'r') as f:
                    head = f.read(sniff_kb * 1024).decode("utf-8", errors="ignore")
                if looks_like_dem_xml_head(head):
                    z.extract(info, path=out_dir)


# -----------------------------------------
# 入力群から DEM XML を収集（テンポラリ使用）
# -----------------------------------------
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

    changed = True
    while changed:
        changed = False
        for base in list(work_dirs):
            for inner_zip in list(base.rglob("*.zip")):
                sub = inner_zip.with_suffix("")
                sub.mkdir(exist_ok=True)
                selective_extract_zip(inner_zip, sub)
                inner_zip.unlink(missing_ok=True)
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
    return xmls, tmp_root


# -----------------------------------------
# 軽量 parse_tile（NaN→0）
# -----------------------------------------
def parse_tile_light(xml_path):
    import xml.etree.ElementTree as ET
    txt = Path(xml_path).read_text("utf-8", errors="ignore")
    root = ET.fromstring(txt)
    ns = {"gml": "http://www.opengis.net/gml/3.2"}

    env = root.find(".//gml:boundedBy/gml:Envelope", ns)
    lower = env.find("gml:lowerCorner", ns).text.strip().split()
    upper = env.find("gml:upperCorner", ns).text.strip().split()
    lat_min, lon_min = float(lower[0]), float(lower[1])
    lat_max, lon_max = float(upper[0]), float(upper[1])

    grid = root.find(".//gml:Grid", ns)
    high = grid.find("gml:limits/gml:GridEnvelope/gml:high", ns).text.strip().split()
    rows, cols = int(high[0]) + 1, int(high[1]) + 1

    tuple_list = root.find(".//gml:tupleList", ns)
    if tuple_list is not None:
        val_text = tuple_list.text or ""
    else:
        dnrt = root.find(".//gml:doubleOrNilReasonTupleList", ns)
        val_text = dnrt.text if dnrt is not None else ""

    values = []
    for line in val_text.splitlines():
        s = line.strip()
        if not s:
            continue
        if "," in s:
            try:
                v = float(s.split(",")[-1])
            except Exception:
                continue
            values.append(v)
        else:
            try:
                values.append(float(s))
            except Exception:
                continue
    vals = np.asarray(values, dtype=np.float32)

    data2d = np.zeros((rows, cols), dtype=np.float32)
    if vals.size == rows * cols:
        data2d = vals.reshape((rows, cols))
    else:
        data2d.flat[:vals.size] = vals

    return {
        "lat_min": lat_min, "lon_min": lon_min,
        "lat_max": lat_max, "lon_max": lon_max,
        "rows": rows, "cols": cols,
        "data2d": np.nan_to_num(data2d, nan=0.0),
    }


# -----------------------------------------
# タイル結合
# -----------------------------------------
def unique_sorted(arr, decimals=10, reverse=False):
    return sorted({round(a, decimals) for a in arr}, reverse=reverse)

def build_mosaic(tiles, round_decimals=10):
    lat_keys = [t["lat_max"] for t in tiles]
    lon_keys = [t["lon_min"] for t in tiles]
    row_bands = unique_sorted(lat_keys, decimals=round_decimals, reverse=True)
    col_bands = unique_sorted(lon_keys, decimals=round_decimals, reverse=False)

    row_heights = {rk: max(t["rows"] for t in tiles if round(t["lat_max"], round_decimals) == rk) for rk in row_bands}
    col_widths = {ck: max(t["cols"] for t in tiles if round(t["lon_min"], round_decimals) == ck) for ck in col_bands}

    total_h = sum(row_heights.values())
    total_w = sum(col_widths.values())
    mosaic = np.zeros((total_h, total_w), dtype=np.float32)

    y_off, acc = {}, 0
    for rk in row_bands:
        y_off[rk] = acc
        acc += row_heights[rk]
    x_off, acc = {}, 0
    for ck in col_bands:
        x_off[ck] = acc
        acc += col_widths[ck]

    for t in tiles:
        rk = round(t["lat_max"], round_decimals)
        ck = round(t["lon_min"], round_decimals)
        y0, x0 = y_off[rk], x_off[ck]
        h, w = t["rows"], t["cols"]
        mosaic[y0:y0+h, x0:x0+w] = t["data2d"]

    return mosaic


# -----------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", help="ZIPまたはフォルダ（複数可）")
    ap.add_argument("--out", default=None, help="出力ファイル名（拡張子不要）")
    ap.add_argument("--outdir", default=None, help="出力先ディレクトリ")
    args = ap.parse_args()

    inputs = [Path(p) for p in args.inputs]
    xmls, tmp_keeper = collect_dem_xmls_from_inputs(inputs)
    if not xmls:
        print("[ERROR] DEM XML が見つかりませんでした。")
        return 1

    tiles = []
    for x in xmls:
        try:
            tiles.append(parse_tile_light(x))
        except Exception as e:
            print(f"[WARN] skip {x.name}: {e}")

    if not tiles:
        print("[ERROR] 有効なタイルがありません。")
        return 1

    mosaic = build_mosaic(tiles)

    if args.outdir:
        out_dir = Path(args.outdir)
    else:
        out_dir = inputs[0].parent if inputs[0].is_file() else inputs[0]
    out_dir.mkdir(parents=True, exist_ok=True)

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
