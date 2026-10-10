"""Point-in-time soybean mask + state-level feature tables from the extracted pixel series.

Season Y = harvest year (Y=2016 means crop year 2015/16).

Mask for season Y (decided before the season starts, nothing from season Y itself):
  1. per pixel and per PAST season, a phenology test on quality-screened NDVI (MODIS reliability 0/1):
       pre-season minimum  (composites starting Aug 12 - Dec 2)  = premin
       summer peak         (composites starting Nov 16 - Mar 21) = peak
       "summer annual crop" if peak >= 0.78 and peak - premin >= 0.35
  2. pixel in the season-Y mask if it passed in >= 2 of seasons Y-1, Y-2, Y-3
  3. pixel weight = PAM soybean planted area of its municipality in year Y-2 (latest PAM published by
     the start of season Y) / number of mask pixels of that municipality. Municipalities with no PAM
     soy area in Y-2 get zero weight.

Per state and composite we aggregate (weighted, valid obs only):
  ndvi, evi            levels
  ndvi_anom, evi_anom  per-pixel anomaly vs that pixel's mean at the same composite slot over ALL
                       PRIOR seasons (expanding window, >= 3 valid years), then aggregated
  valid_frac           share of mask weight with a valid observation
LST (MOD11A2, 8-day) and CHIRPS (monthly) are aggregated the same way (per-pixel anomaly vs prior
seasons). Each row carries `available_date`, the first date the input would have been public:
  MOD13A1 composite end + 14 d, MOD11A2 composite end + 10 d, CHIRPS month M -> day 20 of M+1.

Outputs (soy_research/satellite/features/): modis_vi_state.csv, lst_state.csv, precip_state.csv,
mask_summary.csv, and <work>/mask_<Y>.csv for selected seasons (for map checks).
Usage: python build_features.py --work <scratch>/soy_sat
"""
import argparse, glob, os
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PEAK_MIN, AMP_MIN = 0.78, 0.35


def vi_slot(key):
    y, d = int(key[:4]), int(key[4:])
    return (y + 1, (d - 193) // 16) if d >= 193 else (y, 11 + (d - 1) // 16)


def lst_slot(key):
    y, d = int(key[:4]), int(key[4:])
    return (y + 1, (d - 241) // 8) if d >= 241 else (y, 16 + (d - 1) // 8)


def load_stack(files, fields, npix):
    keys = sorted({os.path.basename(f).split("_")[0] for f in files})
    kidx = {k: i for i, k in enumerate(keys)}
    out = {f: None for f in fields}
    meta = {}
    for fn in files:
        k = os.path.basename(fn).split("_")[0]
        z = np.load(fn)
        for f in fields:
            if out[f] is None:
                out[f] = np.zeros((len(keys), npix), dtype=z[f].dtype)
                if f == "rel":
                    out[f][:] = 255
            out[f][kidx[k], z["pixel_id"] if "pixel_id" in z else slice(None)] = z[f]
        meta[k] = (str(z["start"]), str(z["end"]))
    return keys, out, meta


def wmean(vals, valid, w):
    """weighted mean over pixels for each row of vals (rows = time); returns mean, valid weight share"""
    ww = valid * w[None, :]
    s = ww.sum(1)
    m = np.where(s > 0, (np.where(valid, vals, 0) * ww).sum(1) / np.maximum(s, 1e-12), np.nan)
    return m, s / w.sum()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--data", default=os.path.join(HERE, "data"))
    ap.add_argument("--out", default=os.path.join(HERE, "features"))
    ap.add_argument("--skip-lst", action="store_true")
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    px = pd.read_csv(f"{a.data}/pixels.csv").sort_values("pixel_id").reset_index(drop=True)
    npix = len(px)
    # municipal PAM area
    mu = pd.read_csv(f"{a.data}/pam_muni_area.csv")
    area = mu.pivot_table(index="muni", columns="year", values="area_ha", fill_value=0)

    # ---------------- MODIS VI ----------------
    # pixel_id is stored per file; build stacks by pixel_id
    files = sorted(glob.glob(f"{a.work}/modis/*.npz"))
    keys, st, meta = load_stack(files, ["ndvi", "evi", "rel"], npix)
    print("composites", len(keys), keys[0], keys[-1])
    good = (st["rel"] <= 1) & (st["ndvi"] > -2000)
    ndvi = np.where(good, st["ndvi"] / 1e4, np.nan).astype(np.float32)
    evi = np.where(good, st["evi"] / 1e4, np.nan).astype(np.float32)
    del st
    sl = [vi_slot(k) for k in keys]
    seasons = sorted({s for s, _ in sl})
    pos = {(s, j): i for i, (s, j) in enumerate(sl)}

    # phenology class per season
    cls = {}
    for Y in seasons:
        pre = [pos[(Y, j)] for j in range(2, 10) if (Y, j) in pos]
        pk = [pos[(Y, j)] for j in range(8, 17) if (Y, j) in pos]
        if len(pre) < 6 or len(pk) < 7:
            continue
        with np.errstate(all="ignore"):
            premin = np.nanmin(ndvi[pre], 0); peak = np.nanmax(ndvi[pk], 0)
        cls[Y] = (peak >= PEAK_MIN) & ((peak - premin) >= AMP_MIN)
        print("class", Y, round(float(np.nanmean(cls[Y])), 3))

    # expanding per-pixel climatology per slot
    csum = {v: np.zeros((21, npix), np.float64) for v in ("ndvi", "evi")}
    ccnt = {v: np.zeros((21, npix), np.int16) for v in ("ndvi", "evi")}
    rows, msum, masks = [], [], {}
    for Y in seasons:
        prev = [cls[y] for y in (Y - 1, Y - 2, Y - 3) if y in cls]
        idx = [pos[(Y, j)] for j in range(21) if (Y, j) in pos]
        jj = [j for j in range(21) if (Y, j) in pos]
        if len(prev) >= 2:
            m = np.sum(prev, 0) >= 2
            yr = Y - 2
            mA = area[yr] if yr in area.columns else pd.Series(dtype=float)
            amuni = px.muni.map(mA).fillna(0).values
            m &= amuni > 0
            nm = pd.Series(m).groupby(px.muni.values).transform("sum").values
            w = np.where(m, amuni / np.maximum(nm, 1), 0.0)
            masks[Y] = m
            for state in sorted(px.state.unique()):
                sel = (px.state.values == state) & m
                if sel.sum() < 50:
                    continue
                ws = w[sel]
                msum.append(dict(season=Y, state=state, n_mask_px=int(sel.sum()), n_candidate_px=int((px.state.values == state).sum()),
                                 pam_area_lag2_ha=float(pd.Series(amuni[sel], index=px.muni.values[sel]).groupby(level=0).first().sum())))
                out = {}
                for v, arr in (("ndvi", ndvi), ("evi", evi)):
                    X = arr[idx][:, sel]
                    val = ~np.isnan(X)
                    out[v], out["valid_frac"] = wmean(X, val, ws)
                    cnt = ccnt[v][jj][:, sel]; clim = csum[v][jj][:, sel] / np.maximum(cnt, 1)
                    an = X - clim; okc = val & (cnt >= 3)
                    out[v + "_anom"], out[v + "_anom_cov"] = wmean(an, okc, ws)
                for t, (i, j) in enumerate(zip(idx, jj)):
                    k = keys[i]; s0, e0 = meta[k]
                    rows.append(dict(season=Y, state=state, composite=k, slot=j, start=s0, end=e0,
                                     available_date=(pd.Timestamp(e0) + pd.Timedelta(days=14)).date().isoformat(),
                                     ndvi=out["ndvi"][t], evi=out["evi"][t], ndvi_anom=out["ndvi_anom"][t],
                                     evi_anom=out["evi_anom"][t], valid_frac=out["valid_frac"][t], anom_cov=out["evi_anom_cov"][t]))
        # update climatology with season Y AFTER using it
        for v, arr in (("ndvi", ndvi), ("evi", evi)):
            X = arr[idx]; val = ~np.isnan(X)
            csum[v][jj] += np.where(val, X, 0); ccnt[v][jj] += val
    vi = pd.DataFrame(rows)
    vi.to_csv(f"{a.out}/modis_vi_state.csv", index=False, float_format="%.4f")
    pd.DataFrame(msum).to_csv(f"{a.out}/mask_summary.csv", index=False)
    for Y in (2012, 2016, 2020, 2024):
        if Y in masks:
            pd.DataFrame({"pixel_id": px.pixel_id.values[masks[Y]]}).to_csv(f"{a.work}/mask_{Y}.csv", index=False)
    # mask sanity: municipal mask fraction vs PAM share
    del ndvi, evi

    def weights(Y):
        m = masks[Y]; amuni = px.muni.map(area[Y - 2] if Y - 2 in area.columns else {}).fillna(0).values
        nm = pd.Series(m).groupby(px.muni.values).transform("sum").values
        return np.where(m, amuni / np.maximum(nm, 1), 0.0)

    # ---------------- LST ----------------
    lfiles = [] if a.skip_lst else sorted(glob.glob(f"{a.work}/lst/*.npz"))
    rows = []
    if lfiles:
        # LST files are stored per tile in pixels.csv tile order; attach pixel ids
        tile_ids = {t: g.pixel_id.values for t, g in px.groupby("tile")}
        lkeys = sorted({os.path.basename(f).split("_")[0] for f in lfiles}); lk = {k: i for i, k in enumerate(lkeys)}
        L = np.zeros((len(lkeys), npix), np.uint16); lmeta = {}
        for fn in lfiles:
            k, t = os.path.basename(fn)[:-4].split("_"); z = np.load(fn)
            L[lk[k], tile_ids[t]] = z["lst"]; lmeta[k] = (str(z["start"]), str(z["end"]))
        lsl = [lst_slot(k) for k in lkeys]; lpos = {s: i for i, s in enumerate(lsl)}
        lsum = np.zeros((32, npix)); lcnt = np.zeros((32, npix), np.int16)
        for Y in sorted({s for s, _ in lsl}):
            jj = [j for j in range(32) if (Y, j) in lpos]; idx = [lpos[(Y, j)] for j in jj]
            X = np.where(L[idx] > 0, L[idx] * 0.02 - 273.15, np.nan); val = ~np.isnan(X)
            if Y in masks:
                w = weights(Y)
                for state in sorted(px.state.unique()):
                    sel = (px.state.values == state) & masks[Y]
                    if sel.sum() < 50:
                        continue
                    ws = w[sel]; Xs = X[:, sel]; vs = val[:, sel]
                    lev, vf = wmean(Xs, vs, ws)
                    cnt = lcnt[jj][:, sel]; clim = lsum[jj][:, sel] / np.maximum(cnt, 1)
                    an, cov = wmean(Xs - clim, vs & (cnt >= 3), ws)
                    for t, (i, j) in enumerate(zip(idx, jj)):
                        s0, e0 = lmeta[lkeys[i]]
                        rows.append(dict(season=Y, state=state, composite=lkeys[i], slot=j, start=s0, end=e0,
                                         available_date=(pd.Timestamp(e0) + pd.Timedelta(days=10)).date().isoformat(),
                                         lst_c=lev[t], lst_anom=an[t], valid_frac=vf[t], anom_cov=cov[t]))
            lsum[jj] += np.where(val, X, 0); lcnt[jj] += val
        del L
    pd.DataFrame(rows).to_csv(f"{a.out}/lst_state.csv", index=False, float_format="%.4f")

    # ---------------- CHIRPS ----------------
    cfiles = sorted(glob.glob(f"{a.work}/chirps/*.npz"))
    rows = []
    if cfiles:
        months = [os.path.basename(f)[:6] for f in cfiles]
        P = np.stack([np.load(f)["p10"] for f in cfiles]).astype(np.float32)
        P[P == 65535] = np.nan; P /= 10
        # season Y month slot: Aug(Y-1)=0 .. Jun(Y)=10
        def mslot(ym):
            y, m = int(ym[:4]), int(ym[4:])
            return (y + 1, m - 8) if m >= 8 else ((y, m + 4) if m <= 6 else (None, None))
        ms = [mslot(m) for m in months]; mpos = {s: i for i, s in enumerate(ms) if s[0]}
        psum = np.zeros((11, npix)); pcnt = np.zeros((11, npix), np.int16)
        for Y in sorted({s for s, _ in ms if s}):
            jj = [j for j in range(11) if (Y, j) in mpos]; idx = [mpos[(Y, j)] for j in jj]
            X = P[idx]; val = ~np.isnan(X)
            if Y in masks:
                w = weights(Y)
                for state in sorted(px.state.unique()):
                    sel = (px.state.values == state) & masks[Y]
                    if sel.sum() < 50:
                        continue
                    ws = w[sel]; cnt = pcnt[jj][:, sel]
                    lev, _ = wmean(X[:, sel], val[:, sel], ws)
                    clim, cov = wmean(psum[jj][:, sel] / np.maximum(cnt, 1), cnt >= 3, ws)
                    for t, (i, j) in enumerate(zip(idx, jj)):
                        ym = months[i]; y, m = int(ym[:4]), int(ym[4:])
                        nxt = pd.Timestamp(year=y + (m == 12), month=m % 12 + 1, day=20)
                        rows.append(dict(season=Y, state=state, month=ym, slot=j, available_date=nxt.date().isoformat(),
                                         precip_mm=lev[t], precip_clim_mm=clim[t], clim_cov=cov[t]))
            psum[jj] += np.where(val, X, 0); pcnt[jj] += val
    pd.DataFrame(rows).to_csv(f"{a.out}/precip_state.csv", index=False, float_format="%.3f")
    print("done")


if __name__ == "__main__":
    main()
