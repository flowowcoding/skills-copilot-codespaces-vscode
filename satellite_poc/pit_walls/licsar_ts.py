"""LOS displacement time series for a mine segment from COMET LiCSAR interferograms (free, no login).

LiCSAR (Univ. Leeds / COMET) publishes Sentinel-1 interferograms, ~100 m (0.001 deg) geocoded,
for many frames worldwide at
  https://gws-access.jasmin.ac.uk/public/nceo_geohazards/LiCSAR_products/<track>/<frame>/interferograms/
(recent pairs; older pairs are served from the CEDA archive https://dap.ceda.ac.uk/neodc/comet/data/licsar_products/).
For each epoch we take the shortest available pair to the next epoch (<= MAXDT days), read the
unwrapped phase and coherence over the site box (windowed HTTP reads, no full download) and
compute   inc = median(segment, coh >= COH) - median(control, coh >= COH)   in mm towards the
satellite (mm = -unw * lambda / 4 pi, LiCSBAS convention). Increments are cumulated into a
displacement series; a pair is dropped (gap) if less than MINFRAC of the segment is coherent.

Usage:
  python licsar_ts.py SITE FRAME START END OUT.csv [--coh 0.3] [--minfrac 0.3] [--maxdt 48]
SITE is a key of prereg.json (segment polygons and control box are taken from there).
"""
import argparse, json, os, re
import numpy as np, pandas as pd, requests, rasterio
from rasterio.windows import from_bounds
from matplotlib.path import Path
from concurrent.futures import ThreadPoolExecutor

BASE = "https://gws-access.jasmin.ac.uk/public/nceo_geohazards/LiCSAR_products"
CEDA = "https://dap.ceda.ac.uk/neodc/comet/data/licsar_products"
LAM = 55.465763  # mm, Sentinel-1 C-band
HERE = os.path.dirname(os.path.abspath(__file__))


def parse_box(txt):
    """'pixels in A..B E, C..D N outside the mine box E0..E1, N0..N1' -> outer, inner boxes."""
    nums = [float(v) for v in re.findall(r"(?<![\d])-?\d+\.\d+", txt)]
    outer = (nums[0], nums[2], nums[1], nums[3]); inner = (nums[4], nums[6], nums[5], nums[7])
    return outer, inner


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("site"); ap.add_argument("frame"); ap.add_argument("start"); ap.add_argument("end"); ap.add_argument("out")
    ap.add_argument("--coh", type=float, default=0.3); ap.add_argument("--minfrac", type=float, default=0.3)
    ap.add_argument("--maxdt", type=int, default=48); ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--save-maps", help="npz path: also save the per-pair LOS increment maps over the box")
    a = ap.parse_args()
    site = json.load(open(os.path.join(HERE, "prereg.json")))["sites"][a.site]
    outer, inner = parse_box(site["control"])          # (lon0, lat0, lon1, lat1)
    track = int(a.frame[:3])
    html = requests.get(f"{BASE}/{track}/{a.frame}/interferograms/", timeout=120).text
    pairs = sorted(set(re.findall(r"(\d{8})_(\d{8})", html)))
    df = pd.DataFrame(pairs, columns=["d1", "d2"]).apply(pd.to_datetime)
    df["dt"] = (df.d2 - df.d1).dt.days
    df = df[(df.d1 >= a.start) & (df.d2 <= a.end) & (df.dt <= a.maxdt)]
    # chain: from each epoch the shortest pair forward
    chain = df.sort_values("dt").groupby("d1").head(1).sort_values("d1")
    sel, t = [], chain.d1.min()
    for r in chain.itertuples():
        if r.d1 >= t:
            sel.append(r); t = r.d2
    print(a.frame, len(df), "pairs in range;", len(sel), "in chain")

    def read(r):
        tag = f"{r.d1:%Y%m%d}_{r.d2:%Y%m%d}"
        urls = [f"/vsicurl/{BASE}.public/{track}/{a.frame}/interferograms/{tag}/{tag}",
                f"/vsicurl/{CEDA}/{track}/{a.frame}/{tag}/{tag}"]   # older pairs live only in the CEDA archive
        for u in urls:
            out = _read(u, tag)
            if out[1] is not None:
                return out
        print("fail", tag); return tag, None, None, None

    def _read(u, tag):
        try:
            with rasterio.open(u + ".geo.unw.tif") as s:
                w = from_bounds(*outer, s.transform); unw = s.read(1, window=w, boundless=True, fill_value=np.nan)
                tr = s.window_transform(w)
            with rasterio.open(u + ".geo.cc.tif") as s:
                cc = s.read(1, window=from_bounds(*outer, s.transform), boundless=True, fill_value=0) / 255.0
            return tag, unw, cc, tr
        except Exception:
            return tag, None, None, None

    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="4", GDAL_HTTP_RETRY_DELAY="2"):
        with ThreadPoolExecutor(a.workers) as ex:
            got = list(ex.map(read, sel))
    rows, maps = [], {}
    for r, (tag, unw, cc, tr) in zip(sel, got):
        if unw is None:
            continue
        H, W = unw.shape
        lon = tr.c + (np.arange(W) + 0.5) * tr.a; lat = tr.f + (np.arange(H) + 0.5) * tr.e
        LON, LAT = np.meshgrid(lon, lat)
        mm = -unw * LAM / (4 * np.pi)
        good = (cc >= a.coh) & np.isfinite(mm) & (unw != 0)
        inmine = (LON >= inner[0]) & (LON <= inner[2]) & (LAT >= inner[1]) & (LAT <= inner[3])
        ctrl = good & ~inmine
        ref = np.median(mm[ctrl]) if ctrl.sum() > 50 else np.nan
        row = {"d1": r.d1.date(), "d2": r.d2.date(), "dt": r.dt, "ctrl_px": int(ctrl.sum())}
        for name, poly in site["segments"].items():
            m = Path(poly).contains_points(np.c_[LON.ravel(), LAT.ravel()]).reshape(H, W)
            g = m & good
            row[f"{name}|frac_coh"] = g.sum() / max(m.sum(), 1)
            row[f"{name}|inc_mm"] = (np.median(mm[g]) - ref) if g.sum() / max(m.sum(), 1) >= a.minfrac else np.nan
            row[f"{name}|n_px"] = int(m.sum())
        rows.append(row)
        if a.save_maps:
            maps[tag] = np.where(good, mm - ref, np.nan).astype(np.float32)
    out = pd.DataFrame(rows)
    if out.empty:
        raise SystemExit("no pairs could be read")
    for name in site["segments"]:
        out[f"{name}|cum_mm"] = out[f"{name}|inc_mm"].fillna(0).cumsum()
    out.round(3).to_csv(a.out, index=False)
    if a.save_maps and maps:
        np.savez_compressed(a.save_maps, tags=np.array(list(maps)), maps=np.stack(list(maps.values())),
                            transform=np.array(tuple(tr)[:6]))
    print(out.tail(3).to_string())


if __name__ == "__main__":
    main()
