"""Point-in-time corn / soybean masks and state-level MODIS VI series from the extracted pixel data.

Mask for crop year Y (uses only CDLs public by the forecast date; CDL Y-1 is released ~end of Jan Y):
  per 30 m CDL cell, predicted crop in Y from the two previous CDLs (corn = code 1; soybeans = 5, 26, 254):
      Y-1 corn & Y-2 corn  -> corn (continuous corn)      Y-1 corn & Y-2 not corn -> soybeans (rotation)
      Y-1 soy  & Y-2 soy   -> soybeans (continuous soy)   Y-1 soy  & Y-2 not soy  -> corn (rotation)
      anything else in Y-1 -> neither
  a sample pixel is in the corn (soy) mask for Y if >= 60 % of its 9 x 9 CDL cells are predicted corn (soy).
  Exceptions (training years only, documented): Y = 2009 has no CDL 2007, so Y-1 alone is used with the
  pure-rotation rule; Y = 2008 has no prior CDL on PC, so the 2008 CDL itself is used (look-ahead in a
  training-only year).
  All mask pixels get equal weight within a state (the candidate sample is already drawn in proportion to
  county corn+soy acres).
  Ex-post check (not used by the model): share of masked pixels' cells that CDL Y actually shows as the
  predicted crop -> features/mask_summary.csv.

VI series, per crop x state x Aqua composite: mean NDVI and EVI over mask pixels with a good or marginal
MODIS pixel-reliability flag (0/1), valid fraction, composite start/end, and
  available_date = composite end + 14 days (MODIS 13Q1 standard products post ~8-10 days after the period).
Optional HLS gap fill (--hls): for composites missing from Planetary Computer, a state value predicted from
HLS (see extract_hls.py), with the substitution flagged in `source`.

Outputs: features/modis_state.csv, features/mask_summary.csv, <work>/mask_<Y>.csv (pixel masks for maps)
Usage: python build_features.py --work <scratch>/us_sat [--hls]
"""
import argparse, glob, os
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CORN, SOY = [1], [5, 26, 254]
PURITY = 0.6
LATENCY_DAYS = 14


def predicted(c1, c2):
    """per-cell predicted crop for Y from CDL Y-1 (c1) and Y-2 (c2; None = unavailable): 1 corn, 2 soy, 0 none"""
    corn1, soy1 = np.isin(c1, CORN), np.isin(c1, SOY)
    if c2 is None:
        return np.where(corn1, 2, np.where(soy1, 1, 0)).astype(np.uint8)
    corn2, soy2 = np.isin(c2, CORN), np.isin(c2, SOY)
    return np.where(corn1 & corn2, 1, np.where(corn1, 2, np.where(soy1 & soy2, 2, np.where(soy1, 1, 0)))).astype(np.uint8)


def masks(work, years):
    cdl = {int(os.path.basename(f)[4:8]): np.load(f)["win"] for f in glob.glob(f"{work}/cdl/cdl_*.npz")}
    out, summ = {}, []
    for Y in years:
        if Y == 2008:
            pred = np.where(np.isin(cdl[2008], CORN), 1, np.where(np.isin(cdl[2008], SOY), 2, 0)).astype(np.uint8); rule = "same-year CDL (training only)"
        elif Y == 2009:
            pred = predicted(cdl[2008], None); rule = "Y-1 only, pure rotation"
        else:
            if Y - 1 not in cdl or Y - 2 not in cdl:
                continue
            pred = predicted(cdl[Y - 1], cdl[Y - 2]); rule = "Y-1 and Y-2 rotation"
        fc, fs = (pred == 1).mean(1), (pred == 2).mean(1)
        mc, ms = fc >= PURITY, fs >= PURITY
        out[Y] = (mc, ms)
        r = dict(year=Y, rule=rule, n_corn=int(mc.sum()), n_soy=int(ms.sum()))
        if Y in cdl and Y > 2008:  # ex-post accuracy
            r["corn_mask_actual_corn_share"] = float(np.isin(cdl[Y][mc], CORN).mean())
            r["soy_mask_actual_soy_share"] = float(np.isin(cdl[Y][ms], SOY).mean())
            r["cell_rotation_accuracy_corn"] = float(np.isin(cdl[Y][pred == 1], CORN).mean())
            r["cell_rotation_accuracy_soy"] = float(np.isin(cdl[Y][pred == 2], SOY).mean())
        summ.append(r)
    return out, pd.DataFrame(summ)


def load_modis(work, plat, npix):
    files = sorted(glob.glob(f"{work}/modis_{plat}/*.npz"))
    keys = sorted({os.path.basename(f).split("_")[0] for f in files})
    k = {kk: i for i, kk in enumerate(keys)}
    ndvi = np.full((len(keys), npix), np.nan, np.float32); evi = ndvi.copy()
    meta = {}
    for fn in files:
        kk = os.path.basename(fn).split("_")[0]; z = np.load(fn)
        good = (z["rel"] >= 0) & (z["rel"] <= 1) & (z["ndvi"] > -2000)
        pid = z["pixel_id"]
        ndvi[k[kk], pid] = np.where(good, z["ndvi"] / 1e4, np.nan); evi[k[kk], pid] = np.where(good, z["evi"] / 1e4, np.nan)
        meta[kk] = (str(z["start"]), str(z["end"]))
    return keys, ndvi, evi, meta


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--data", default=os.path.join(HERE, "data"))
    ap.add_argument("--out", default=os.path.join(HERE, "features"))
    ap.add_argument("--platform", default="MYD")
    ap.add_argument("--hls", action="store_true", help="add HLS-based fills for missing composites")
    a = ap.parse_args()
    px = pd.read_csv(f"{a.data}/pixels.csv").sort_values("pixel_id").reset_index(drop=True)
    npix = len(px); st = px.state.values
    years = list(range(2008, 2027))
    mk, summ = masks(a.work, years)
    summ.to_csv(f"{a.out}/mask_summary.csv", index=False, float_format="%.3f")
    print(summ.to_string())
    for Y in (2012, 2024, 2026):
        if Y in mk:
            pd.DataFrame(dict(pixel_id=px.pixel_id, corn=mk[Y][0].astype(int), soy=mk[Y][1].astype(int))).to_csv(f"{a.work}/mask_{Y}.csv", index=False)
    keys, ndvi, evi, meta = load_modis(a.work, a.platform, npix)
    rows = []
    for i, kk in enumerate(keys):
        Y = int(kk[:4])
        if Y not in mk:
            continue
        for ci, crop in enumerate(["corn", "soy"]):
            m = mk[Y][ci]
            for s in sorted(set(st)):
                sel = m & (st == s)
                v = np.isfinite(evi[i, sel])
                rows.append(dict(year=Y, doy=int(kk[4:]), crop=crop, state=s, ndvi=np.nanmean(ndvi[i, sel]) if v.any() else np.nan,
                                 evi=np.nanmean(evi[i, sel]) if v.any() else np.nan, n_mask=int(sel.sum()), valid_frac=v.mean() if sel.any() else 0,
                                 start=meta[kk][0], end=meta[kk][1], source=a.platform))
    d = pd.DataFrame(rows)
    d["available_date"] = (pd.to_datetime(d.end) + pd.Timedelta(days=LATENCY_DAYS)).dt.strftime("%Y-%m-%d")
    if a.hls and os.path.exists(f"{a.out}/hls_fill_state.csv"):
        h = pd.read_csv(f"{a.out}/hls_fill_state.csv")
        have = set(zip(d.year, d.doy, d.crop, d.state))
        h = h[[(r.year, r.doy, r.crop, r.state) not in have for r in h.itertuples()]]
        d = pd.concat([d, h[d.columns]], ignore_index=True)
        print("HLS fills added", len(h))
    d.sort_values(["crop", "state", "year", "doy"]).to_csv(f"{a.out}/modis_state.csv", index=False, float_format="%.4f")
    print(d.groupby(["year"]).valid_frac.mean())


if __name__ == "__main__":
    main()
