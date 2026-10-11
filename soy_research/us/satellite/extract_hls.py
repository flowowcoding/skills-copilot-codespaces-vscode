"""HLS v2 (Landsat 8/9 + Sentinel-2, 30 m) gap fill for Aqua MODIS composites missing from Planetary Computer.

Why: Planetary Computer has no MODIS 13Q1/13A1 (Terra or Aqua) from 2025-07 to 2025-11, and no Aqua
composites starting DOY 137-169 or 233 in 2026. HLS (collections hls2-l30 / hls2-s30, 2020-present, no
auth) covers those dates.

Method (decided before any holdout evaluation):
  * tiles: the MGRS tiles holding the most candidate pixels, up to --per-state tiles per state (a fixed
    spatial sub-sample; pixels are assigned to one tile with >= 2 km margin)
  * for each Aqua composite window [start, start + 15 d] (slots 169, 185, 201, 217; years 2020-2026),
    every L30 / S30 scene of the tile with eo:cloud_cover <= 80 is read at the 8x COG overview (240 m,
    close to MODIS 250 m): blue, red, NIR (L30 B05, S30 B8A) and Fmask
  * clear = Fmask bits 1-5 (cloud, adjacent, shadow, snow, water) all zero
  * per pixel the composite is the clear observation with the highest NDVI (MODIS-like max-value
    compositing); its NDVI and EVI = 2.5 (nir - red) / (nir + 6 red - 7.5 blue + 1) are kept
  * state value = mean over the year's mask pixels (same masks as MODIS) inside the sampled tiles
  * calibration to the MODIS state series: per crop, OLS over states and slots with state intercepts,
    MODIS_evi = a_state + b HLS_evi (same for NDVI), fitted on all years < Y where both exist
    (point-in-time), then applied in year Y: to composites MODIS lacks (fills), and to every composite
    (hls_cal_state.csv, used by the drift guard in model.py)
Outputs: <work>/hls/<year>_<doy>_<tile>.npz (pixel_id, ndvi, evi, nobs)
         features/hls_state.csv (raw HLS state values, all slots/years)
         features/hls_fill_state.csv (calibrated fills for missing MODIS composites; source = HLS-cal)
         features/hls_cal_state.csv (calibrated HLS for every composite, with the MODIS value alongside)
         features/hls_calibration.csv
Usage: python extract_hls.py --work <scratch>/us_sat [--per-state 4] [--threads 16]
       python extract_hls.py --work <scratch>/us_sat --calibrate   (after build_features.py)
"""
import argparse, os, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np, pandas as pd, rasterio
import planetary_computer as pc, pystac_client
from pyproj import Transformer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SLOTS = [169, 185, 201, 217]
YEARS = range(2020, 2027)
F = 8  # overview factor
NIR = {"L30": "B05", "S30": "B8A"}


def tile_grid(px):
    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
    tiles = {}
    for col in ["hls2-s30", "hls2-l30"]:
        for it in cat.search(collections=[col], datetime="2024-07-01/2024-07-20", bbox=[-104.1, 36.9, -80.5, 49.1]).items():
            t = it.id.split(".")[2]
            tiles.setdefault(t, (it.properties["proj:code"], it.properties["proj:transform"][2], it.properties["proj:transform"][5]))
    rows = []
    for t, (code, x0, y1) in tiles.items():
        x, y = Transformer.from_crs("EPSG:4326", code, always_xy=True).transform(px.lon.values, px.lat.values)
        inside = (x > x0 + 2000) & (x < x0 + 109800 - 2000) & (y < y1 - 2000) & (y > y1 - 109800 + 2000)
        for i in np.where(inside)[0]:
            rows.append((px.pixel_id.values[i], px.state.values[i], t, code, (y1 - y[i]) / (30 * F), (x[i] - x0) / (30 * F)))
    d = pd.DataFrame(rows, columns=["pixel_id", "state", "tile", "code", "orow", "ocol"]).drop_duplicates("pixel_id")
    return d


def read(href):
    for k in range(5):
        try:
            with rasterio.open(pc.sign(href)) as s:
                return s.read(1, out_shape=(s.height // F, s.width // F))
        except Exception as e:  # noqa
            err = e; time.sleep(3 * (k + 1))
    raise RuntimeError(err)


def scene_values(it, rr, cc):
    kind = it.id.split(".")[1]
    b = read(it.assets["B02"].href); r = read(it.assets["B04"].href); n = read(it.assets[NIR[kind]].href); fm = read(it.assets["Fmask"].href)
    rr = np.clip(rr, 0, r.shape[0] - 1); cc = np.clip(cc, 0, r.shape[1] - 1)
    b, r, n, fm = b[rr, cc] / 1e4, r[rr, cc] / 1e4, n[rr, cc] / 1e4, fm[rr, cc]
    clear = (fm != 255) & ((fm & 0b111110) == 0) & (r > 0) & (n > 0) & (b > -0.1)
    with np.errstate(all="ignore"):
        ndvi = (n - r) / (n + r); evi = 2.5 * (n - r) / (n + 6 * r - 7.5 * b + 1)
    ok = clear & np.isfinite(ndvi) & (evi > -1) & (evi < 1.5)
    return np.where(ok, ndvi, np.nan), np.where(ok, evi, np.nan)


def window(y, doy):
    s = pd.Timestamp(y, 1, 1) + pd.Timedelta(days=doy - 1)
    return s, s + pd.Timedelta(days=15)


def task(t, y, doy, g, out):
    fn = f"{out}/{y}_{doy}_{t}.npz"
    if os.path.exists(fn):
        return 0
    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
    s, e = window(y, doy)
    lon, lat = g.lon.mean(), g.lat.mean()
    its = [it for it in cat.search(collections=["hls2-l30", "hls2-s30"], datetime=f"{s:%Y-%m-%d}/{e:%Y-%m-%d}T23:59:59Z",
                                   bbox=[lon - 0.01, lat - 0.01, lon + 0.01, lat + 0.01]).items()
           if it.id.split(".")[2] == t and (it.properties.get("eo:cloud_cover") or 0) <= 80]
    rr, cc = g.orow.values.astype(int), g.ocol.values.astype(int)
    best_n = np.full(len(g), -9.0); best_e = np.full(len(g), np.nan); nobs = np.zeros(len(g), np.int16)
    for it in its:
        nd, ev = scene_values(it, rr, cc)
        upd = np.isfinite(nd) & (nd > best_n)
        best_n = np.where(upd, nd, best_n); best_e = np.where(upd, ev, best_e); nobs += np.isfinite(nd)
    np.savez(fn, pixel_id=g.pixel_id.values, ndvi=np.where(best_n > -9, best_n, np.nan).astype(np.float32), evi=best_e.astype(np.float32),
             nobs=nobs, nscenes=len(its))
    return 1


def calibrate(a):
    from build_features import masks
    px = pd.read_csv(f"{a.data}/pixels.csv").sort_values("pixel_id").reset_index(drop=True)
    mk, _ = masks(a.work, list(YEARS))
    st = px.state.values
    rows = []
    import glob
    for fn in sorted(glob.glob(f"{a.work}/hls/*.npz")):
        y, doy, t = os.path.basename(fn)[:-4].split("_")
        z = np.load(fn); pid = z["pixel_id"]
        for ci, crop in enumerate(["corn", "soy"]):
            m = mk[int(y)][ci][pid]
            for s in set(st[pid]):
                sel = m & (st[pid] == s)
                rows.append(dict(year=int(y), doy=int(doy), crop=crop, state=s, tile=t, n=int(np.isfinite(z["evi"][sel]).sum()),
                                 evi_sum=np.nansum(z["evi"][sel]), ndvi_sum=np.nansum(z["ndvi"][sel]), n_mask=int(sel.sum())))
    h = pd.DataFrame(rows).groupby(["year", "doy", "crop", "state"]).sum(numeric_only=True).reset_index()
    h["hls_evi"] = h.evi_sum / h.n.replace(0, np.nan); h["hls_ndvi"] = h.ndvi_sum / h.n.replace(0, np.nan)
    h["hls_valid_frac"] = h.n / h.n_mask.replace(0, np.nan)
    h = h[["year", "doy", "crop", "state", "hls_evi", "hls_ndvi", "hls_valid_frac", "n_mask"]]
    h.to_csv(f"{a.out}/hls_state.csv", index=False, float_format="%.4f")
    m = pd.read_csv(f"{a.out}/modis_state.csv")
    m = m[m.source == "MYD"]
    j = h.merge(m[["year", "doy", "crop", "state", "evi", "ndvi", "valid_frac"]], on=["year", "doy", "crop", "state"], how="left")
    fills, cal, allc = [], [], []
    for Y in YEARS:
        for crop in ["corn", "soy"]:
            tr = j[(j.year < Y) & (j.crop == crop) & j.evi.notna() & j.hls_evi.notna() & (j.hls_valid_frac >= 0.3) & (j.valid_frac >= 0.3)]
            cur = j[(j.year == Y) & (j.crop == crop) & j.hls_evi.notna()]
            if len(cur) == 0:
                continue
            if len(tr) < 20 or tr.year.nunique() < 2:
                print("not enough overlap for", Y, crop); continue
            states = sorted(tr.state.unique())
            for v in ["evi", "ndvi"]:
                # MODIS = a_state + b * HLS  (state intercepts absorb the tile sub-sample's offset)
                X = np.column_stack([tr[f"hls_{v}"].values] + [(tr.state == s_).values.astype(float) for s_ in states])
                coef = np.linalg.lstsq(X, tr[v].values, rcond=None)[0]
                res = tr[v].values - X @ coef
                cal.append(dict(year=Y, crop=crop, var=v, b=coef[0], **{f"a_{s_}": c_ for s_, c_ in zip(states, coef[1:])}, n=len(tr),
                                r2=1 - res.var() / tr[v].var(), rmse=res.std()))
                aa = dict(zip(states, coef[1:]))
                cur = cur.assign(**{f"cal_{v}": [aa.get(r.state, np.nan) + coef[0] * getattr(r, f"hls_{v}") for r in cur.itertuples()]})
            for r in cur.itertuples():
                s, e = window(Y, r.doy)
                row = dict(year=Y, doy=r.doy, crop=crop, state=r.state, ndvi=r.cal_ndvi, evi=r.cal_evi, n_mask=r.n_mask, valid_frac=r.hls_valid_frac,
                           start=f"{s:%Y-%m-%d}", end=f"{e:%Y-%m-%d}", source="HLS-cal", available_date=f"{e + pd.Timedelta(days=14):%Y-%m-%d}")
                allc.append(dict(row, modis_evi=r.evi))
                if not np.isfinite(r.evi):
                    fills.append(row)
    pd.DataFrame(cal).to_csv(f"{a.out}/hls_calibration.csv", index=False, float_format="%.4f")
    pd.DataFrame(fills).to_csv(f"{a.out}/hls_fill_state.csv", index=False, float_format="%.4f")
    pd.DataFrame(allc).to_csv(f"{a.out}/hls_cal_state.csv", index=False, float_format="%.4f")
    print(pd.DataFrame(cal)[["year", "crop", "var", "b", "n", "r2", "rmse"]].to_string()); print(len(fills), "fills")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--data", default=os.path.join(HERE, "data"))
    ap.add_argument("--out", default=os.path.join(HERE, "features"))
    ap.add_argument("--per-state", type=int, default=4)
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument("--calibrate", action="store_true")
    a = ap.parse_args()
    if a.calibrate:
        return calibrate(a)
    px = pd.read_csv(f"{a.data}/pixels.csv")
    gf = f"{a.work}/hls_pixels.csv"
    if os.path.exists(gf):
        g = pd.read_csv(gf)
    else:
        g = tile_grid(px)
        top = g.groupby(["state", "tile"]).size().rename("n").reset_index().sort_values("n", ascending=False).groupby("state").head(a.per_state)
        g = g.merge(top[["state", "tile"]], on=["state", "tile"]).merge(px[["pixel_id", "lon", "lat"]], on="pixel_id")
        g.to_csv(gf, index=False)
    print(g.groupby("state").agg(tiles=("tile", "nunique"), pixels=("pixel_id", "size")))
    out = f"{a.work}/hls"; os.makedirs(out, exist_ok=True)
    jobs = [(t, y, d, gg) for t, gg in g.groupby("tile") for y in YEARS for d in SLOTS]
    t0 = time.time(); n = 0
    with ThreadPoolExecutor(a.threads) as ex:
        futs = [ex.submit(task, t, y, d, gg, out) for t, y, d, gg in jobs]
        for i, f in enumerate(as_completed(futs)):
            try:
                n += f.result()
            except Exception as e:  # noqa
                print("FAILED", e, flush=True)
            if i % 20 == 0:
                print(i, len(futs), f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
