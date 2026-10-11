"""Build point-in-time features for the field-level model: per-pixel phenology, in-season crop classification,
county aggregates, and county weather. Every feature for (year Y, report R) uses only data public at the
forecast date T = NASS Crop Production release date - 5 days:
  * Sentinel-2 L2A acquisitions with date + 3 days <= T; Landsat C2 L2 with date + 8 days <= T
  * gridMET days d with d + 3 <= T
  * CDL year Y-1 and Y-2 (masks, field interiors); CDL labels of years < Y for the crop classifier

Steps (subcommands):
  offsets   sensor harmonisation: NDVI and NIR of each sensor shifted onto Landsat 8/9 OLI by the median
            difference of near-coincident clear pairs (same point, |dt| <= 1 day; Landsat 7 / S2A / S2B / S2C vs L8/L9;
            years <= 2021 only) -> features/sensor_offsets.csv
  pixels    per year: field-interior sample points (CDL Y-1 centre is corn or soy and >= 23 of its 5 x 5
            neighbours share the class), per-pixel smoothed NDVI / NIRv curves to the cutoff and phenology
            metrics, for each report -> <work>/pix/pix_<Y>_<report>.parquet
  classify  walk-forward in-season corn/soy classifier (LightGBM on CDL Y-1/Y-2 classes + the smoothed
            NDVI curve sampled every 10 days to the cutoff), trained on years < Y with CDL-Y labels; years
            with < 2 training years use the rotation rule -> adds p_corn to the pixel files
  county    county x crop x year x report medians of the pixel metrics over pixels classified as the crop
            (p >= 0.7) -> features/county_vi.csv
  weather   county weather to the cutoff -> features/county_weather.csv

Curves: all clear observations (harmonised) on a daily grid DOY 100..cutoff, Gaussian-kernel smoothing
(sigma 8 days) with two upper-envelope passes (observations > 0.05 below the curve get weight 0.2, the usual
treatment of residual cloud / shadow). Metrics per pixel and index (NDVI, NIRv = NDVI x NIR):
  gu_doy    first DOY the smoothed NDVI reaches 0.5 (green-up)
  peak      max of the smoothed curve up to the cutoff; peak_doy its DOY
  auc       sum over DOY 120..cutoff of (curve - 0.2)+ for NDVI (curve for NIRv), per day
  jul       mean of the curve over DOY 182-212 (July)
  last      mean of the curve over the last 15 days before the cutoff
  ndre_jul  mean NDRE = (B8A - B05) / (B8A + B05) of clear S2 observations, DOY 182..cutoff (S2 only)
  nobs      clear observations used
Usage: python build_features.py --work <scratch>/field offsets|pixels|classify|county|weather [--years 2013-2026]
"""
import argparse, glob, os
import numpy as np, pandas as pd
from common import DATA, FEAT, WIN, MARGIN, CORN, SOY, point_offsets

LAT = {"s2": 3, "landsat": 8}
D0 = 100  # first DOY of the daily grid
SIG = 8.0


def forecast_dates():
    r = pd.read_csv(f"{DATA}/release_dates.csv")
    out = []
    for x in r.itertuples():
        for rep in ["aug", "sep"]:
            rel = getattr(x, f"{rep}_release")
            if isinstance(rel, str):
                out.append(dict(year=x.year, report=rep, release=pd.Timestamp(rel), forecast_date=pd.Timestamp(rel) - pd.Timedelta(days=5)))
    return pd.DataFrame(out)


# ---------------------------------------------------------------- observations
def load_obs(work, y, sources=("landsat", "s2")):
    """stack Landsat and S2 observations of year y: dict of arrays (rows = window x acquisition)"""
    parts = []
    for src in sources:
        fn = f"{work}/obs/{src}_{y}.npz"
        if not os.path.exists(fn):
            continue
        z = np.load(fn)
        n = len(z["win_id"])
        re1 = z["re1"] if z["re1"].size else np.full(z["red"].shape, -32768, np.int16)
        parts.append(dict(win_id=z["win_id"].astype(int), date=z["date"], sensor=z["sensor"].astype(int), src=np.full(n, src),
                          red=z["red"], nir=z["nir"], re1=re1))
    if not parts:
        return None
    return {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}


def indices(o, offs=None):
    """NDVI, NIR, NIRv, NDRE per obs row x point (NaN where not clear), harmonised to OLI if offs given"""
    ok = o["red"] > -32768
    r = np.where(ok, o["red"] / 1e4, np.nan); n = np.where(ok, o["nir"] / 1e4, np.nan)
    with np.errstate(all="ignore"):
        ndvi = (n - r) / (n + r)
        e = np.where(o["re1"] > -32768, o["re1"] / 1e4, np.nan)
        ndre = (n - e) / (n + e)
    if offs is not None:
        for s in np.unique(o["sensor"]):
            if s in offs.index:
                m = o["sensor"] == s
                ndvi[m] = offs.loc[s, "a_ndvi"] + offs.loc[s, "b_ndvi"] * ndvi[m]
                n[m] = offs.loc[s, "a_nir"] + offs.loc[s, "b_nir"] * n[m]
    return ndvi.astype(np.float32), n.astype(np.float32), (ndvi * n).astype(np.float32), ndre.astype(np.float32)


def cmd_offsets(a):
    rows = []
    for y in range(2013, 2022):
        o = load_obs(a.work, y)
        if o is None:
            continue
        ndvi, nir, _, _ = indices(o)
        dt = pd.to_datetime(o["date"].astype(str)).values.astype("datetime64[D]").astype(int)
        ref = np.isin(o["sensor"], [8, 9])
        for s in [7, 21, 22, 23]:
            ms = np.where(o["sensor"] == s)[0]
            for i in ms:
                cand = np.where(ref & (o["win_id"] == o["win_id"][i]) & (np.abs(dt - dt[i]) <= 1))[0]
                for j in cand:
                    ok = np.isfinite(ndvi[i]) & np.isfinite(ndvi[j])
                    if ok.sum() >= 50:
                        rows.append(pd.DataFrame(dict(sensor=s, year=y, ndvi_s=ndvi[i][ok], ndvi_r=ndvi[j][ok], nir_s=nir[i][ok], nir_r=nir[j][ok])))
        print("offsets: year", y, "pairs so far", len(rows), flush=True)
    d = pd.concat(rows)
    out = []
    for s, g in d.groupby("sensor"):
        g = g.sample(min(len(g), 200000), random_state=0)
        res = dict(sensor=s, n=len(g), years=g.year.nunique())
        for v in ["ndvi", "nir"]:
            # additive offset = median paired difference (robust to the cloud/shadow and 1-day-lag noise in the
            # pairs; the RMA slope is reported for information only)
            x, yv = g[f"{v}_s"].values, g[f"{v}_r"].values
            b_rma = np.sign(np.corrcoef(x, yv)[0, 1]) * yv.std() / x.std()
            res.update({f"a_{v}": np.median(yv - x), f"b_{v}": 1.0, f"rma_slope_{v}": b_rma, f"bias_{v}": (yv - x).mean(), f"r_{v}": np.corrcoef(x, yv)[0, 1]})
        out.append(res)
    out.append(dict(sensor=8, n=0, years=0, a_ndvi=0, b_ndvi=1, a_nir=0, b_nir=1, bias_ndvi=0, bias_nir=0, r_ndvi=1, r_nir=1))
    out.append(dict(sensor=9, n=0, years=0, a_ndvi=0, b_ndvi=1, a_nir=0, b_nir=1, bias_ndvi=0, bias_nir=0, r_ndvi=1, r_nir=1))
    o = pd.DataFrame(out)
    if 23 not in set(o.sensor) and {21, 22} <= set(o.sensor):  # S2C (launched 2024): mean of S2A/S2B offsets
        s2 = o[o.sensor.isin([21, 22])].mean(numeric_only=True)
        o = pd.concat([o, pd.DataFrame([dict(s2, sensor=23, n=0, years=0)])])
    o.to_csv(f"{FEAT}/sensor_offsets.csv", index=False, float_format="%.4f")
    print(o.to_string())


# ---------------------------------------------------------------- pixels
def sample_points(work, y):
    """field-interior points for year y from CDL y-1 (and y-2): DataFrame win_id, pt, c1, c2, cY"""
    r, c = point_offsets()
    r, c = r + MARGIN, c + MARGIN
    z1 = np.load(f"{work}/cdl/cdl_{y - 1}.npz")["cdl"]
    z2 = np.load(f"{work}/cdl/cdl_{y - 2}.npz")["cdl"]
    fy = f"{work}/cdl/cdl_{y}.npz"
    zy = np.load(fy)["cdl"] if os.path.exists(fy) else None
    c1 = z1[:, r, c]
    same = np.zeros(c1.shape, int)
    for dr in range(-2, 3):
        for dc in range(-2, 3):
            same += (z1[:, r + dr, c + dc] == c1)
    interior = (same >= 23) & np.isin(c1, [CORN, SOY])
    wi, pi = np.where(interior)
    d = pd.DataFrame(dict(win_id=wi, pt=pi, c1=c1[wi, pi], c2=z2[:, r, c][wi, pi]))
    d["cY"] = zy[:, r, c][wi, pi] if zy is not None else 0
    return d


def smooth(Y, M, ngrid, iters=2):
    """Gaussian kernel smoothing of daily arrays Y (values, NaN-free) with weights M -> [npix, ngrid]"""
    t = np.arange(ngrid)
    K = np.exp(-0.5 * ((t[:, None] - t[None, :]) / SIG) ** 2).astype(np.float32)
    W = M.copy()
    for k in range(iters + 1):
        num = (Y * W) @ K; den = W @ K
        with np.errstate(all="ignore"):
            Z = num / den
        if k < iters:
            low = (M > 0) & (Y < Z - 0.05)
            W = np.where(low, 0.2 * M, M)
    return Z


def daily(vals, dayidx, ngrid, npix):
    """mean of observation values per pixel and grid day -> (Y, M) dense [npix, ngrid]"""
    S = np.zeros((npix, ngrid), np.float32); N = np.zeros((npix, ngrid), np.float32)
    for j, di in enumerate(dayidx):
        v = vals[:, j]; ok = np.isfinite(v)
        S[ok, di] += v[ok]; N[ok, di] += 1
    with np.errstate(all="ignore"):
        Yd = np.where(N > 0, S / np.maximum(N, 1), 0)
    return Yd.astype(np.float32), (N > 0).astype(np.float32)


def metrics(Z, cut_i, prefix, base):
    t = np.arange(Z.shape[1]) + D0
    Zc = Z[:, :cut_i + 1]; tc = t[:cut_i + 1]
    out = {}
    pk = np.nanargmax(np.where(np.isfinite(Zc), Zc, -9), axis=1)
    out[f"{prefix}_peak"] = Zc[np.arange(len(Zc)), pk]
    out[f"{prefix}_peak_doy"] = tc[pk]
    s = (tc >= 120)
    out[f"{prefix}_auc"] = np.nansum(np.clip(Zc[:, s] - base, 0, None), axis=1) / 100.0
    j = (tc >= 182) & (tc <= 212)
    out[f"{prefix}_jul"] = np.nanmean(Zc[:, j], axis=1) if j.any() else np.nan
    out[f"{prefix}_last"] = np.nanmean(Zc[:, -15:], axis=1)
    return out


def pixel_year(work, y, offs, fd, sources=("landsat", "s2"), pixdir="pix"):
    o = load_obs(work, y, sources)
    if o is None:
        return
    pts = sample_points(work, y)
    ndvi, nir, nirv, ndre = indices(o, offs)
    dates = pd.to_datetime(o["date"].astype(str))
    avail = dates + pd.to_timedelta([LAT[s] for s in o["src"]], unit="D")
    doy = dates.dayofyear.values
    # map each obs row to the pixels of its window
    pix_index = {w: g.index.values for w, g in pts.groupby("win_id")}
    for rep in ["aug", "sep"]:
        f = fd[(fd.year == y) & (fd.report == rep)]
        if f.empty:
            continue
        T = f.forecast_date.iloc[0]
        use = np.asarray(avail <= T) & (doy >= D0)
        cut_doy = int(min(doy[use].max(), T.dayofyear)) if use.any() else T.dayofyear - 3
        ngrid = cut_doy - D0 + 1
        npx = len(pts)
        V = {k: np.full((npx, 0), np.nan, np.float32) for k in ["ndvi", "nirv"]}
        # gather obs per pixel: build sparse lists (row of obs, pixel)
        rows = np.where(use)[0]
        obs_pix, obs_day, obs_nd, obs_nv, obs_re = [], [], [], [], []
        for i in rows:
            idx = pix_index.get(o["win_id"][i])
            if idx is None:
                continue
            p = pts.pt.values[idx]
            obs_pix.append(idx); obs_day.append(np.full(len(idx), doy[i] - D0)); obs_nd.append(ndvi[i, p]); obs_nv.append(nirv[i, p])
            obs_re.append(ndre[i, p] if o["src"][i] == "s2" and doy[i] >= 182 else np.full(len(idx), np.nan, np.float32))
        P = np.concatenate(obs_pix); Dd = np.concatenate(obs_day); ND = np.concatenate(obs_nd); NV = np.concatenate(obs_nv); RE = np.concatenate(obs_re)
        ok = np.isfinite(ND) & (ND > -0.2) & (ND < 1.0)
        P, Dd, ND, NV, RE = P[ok], Dd[ok], ND[ok], NV[ok], RE[ok]
        res = pts[["win_id", "pt", "c1", "c2", "cY"]].copy()
        res["nobs"] = np.bincount(P, minlength=npx)
        with np.errstate(all="ignore"):
            rs = np.bincount(P, weights=np.nan_to_num(RE), minlength=npx); rn = np.bincount(P, weights=np.isfinite(RE), minlength=npx)
            res["ndre_jul"] = np.where(rn > 0, rs / np.maximum(rn, 1), np.nan)
            res["n_s2re"] = rn
        for name, vals, base in [("ndvi", ND, 0.2), ("nirv", NV, 0.0)]:
            Yd = np.zeros((npx, ngrid), np.float32); N = np.zeros((npx, ngrid), np.float32)
            np.add.at(Yd, (P, Dd), vals); np.add.at(N, (P, Dd), 1)
            Yd = np.where(N > 0, Yd / np.maximum(N, 1), 0).astype(np.float32); M = (N > 0).astype(np.float32)
            Z = np.empty((npx, ngrid), np.float32)
            for s0 in range(0, npx, 20000):
                Z[s0:s0 + 20000] = smooth(Yd[s0:s0 + 20000], M[s0:s0 + 20000], ngrid)
            for k, v in metrics(Z, ngrid - 1, name, base).items():
                res[k] = v
            if name == "ndvi":
                gu = np.argmax(Z >= 0.5, axis=1).astype(float) + D0
                gu[~(Z >= 0.5).any(axis=1)] = np.nan
                res["gu_doy"] = gu
                for dd in range(130, cut_doy + 1, 10):  # classifier inputs
                    res[f"c_{dd}"] = Z[:, dd - D0]
        res["cut_doy"] = cut_doy
        res = res[res.nobs >= 4]
        os.makedirs(f"{work}/{pixdir}", exist_ok=True)
        res.to_parquet(f"{work}/{pixdir}/pix_{y}_{rep}.parquet", index=False)
        print(y, rep, "T", T.date(), "cut_doy", cut_doy, "pixels", len(res), "median nobs", res.nobs.median(), flush=True)


def cmd_pixels(a):
    offs = pd.read_csv(f"{FEAT}/sensor_offsets.csv").set_index("sensor")
    fd = forecast_dates()
    y0, y1 = map(int, a.years.split("-"))
    for y in range(y0, y1 + 1):
        if all(os.path.exists(f"{a.work}/{a.pixdir}/pix_{y}_{r}.parquet") for r in ["aug", "sep"]) and not a.force:
            continue
        pixel_year(a.work, y, offs, fd, a.sources.split(","), a.pixdir)


# ---------------------------------------------------------------- classification
def rotation_rule(c1, c2):
    """corn after soy or after corn-corn; soy after corn (unless corn-corn) or soy-soy"""
    return np.where(c1 == SOY, np.where(c2 == SOY, 0.0, 1.0), np.where(c2 == CORN, 1.0, 0.0))


def cmd_classify(a):
    import lightgbm as lgb
    y0, y1 = map(int, a.years.split("-"))
    rows = []
    for rep in ["aug", "sep"]:
        files = {int(os.path.basename(f).split("_")[1]): f for f in glob.glob(f"{a.work}/{a.pixdir}/pix_*_{rep}.parquet")}
        data = {y: pd.read_parquet(f) for y, f in sorted(files.items())}
        for y in range(y0, y1 + 1):
            if y not in data:
                continue
            d = data[y]
            d["p_rot"] = rotation_rule(d.c1.values, d.c2.values)
            tr_years = [t for t in data if t < y and (data[t].cY > 0).any()]
            ccols = [c for c in d.columns if c.startswith("c_")]
            if len(tr_years) >= 2:
                tr = pd.concat([data[t].assign(year=t) for t in tr_years])
                tr = tr[tr.cY.isin([CORN, SOY])].sample(frac=1, random_state=0).groupby("year").head(60000)
                common = [c for c in ccols if c in tr.columns and tr[c].notna().mean() > 0.9]
                X = lambda df: np.column_stack([(df.c1 == CORN), (df.c1 == SOY), (df.c2 == CORN), (df.c2 == SOY)] + [df[c].values for c in common])
                m = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=50, subsample=0.8, subsample_freq=1,
                                       colsample_bytree=0.8, verbose=-1, n_jobs=1)
                m.fit(X(tr), (tr.cY == CORN).astype(int))
                d["p_corn"] = m.predict_proba(X(d))[:, 1]
                method = "lgbm"
            else:
                d["p_corn"] = d.p_rot; method = "rotation"
            d.to_parquet(files[y], index=False)
            lab = d[d.cY.isin([CORN, SOY])]
            if len(lab):
                acc = ((lab.p_corn >= 0.5) == (lab.cY == CORN)).mean(); acc_rot = ((lab.p_rot >= 0.5) == (lab.cY == CORN)).mean()
                conf = lab[(lab.p_corn >= 0.7) | (lab.p_corn <= 0.3)]
                acc_conf = ((conf.p_corn >= 0.5) == (conf.cY == CORN)).mean()
                rows.append(dict(year=y, report=rep, method=method, n_train_years=len(tr_years), acc=acc, acc_rotation=acc_rot,
                                 acc_confident=acc_conf, share_confident=len(conf) / len(lab), n=len(lab)))
                print(rows[-1], flush=True)
    pd.DataFrame(rows).to_csv(f"{FEAT}/classifier_accuracy{a.tag}.csv", index=False, float_format="%.4f")


# ---------------------------------------------------------------- county aggregation
MET = ["ndvi_peak", "ndvi_peak_doy", "ndvi_auc", "ndvi_jul", "ndvi_last", "nirv_peak", "nirv_auc", "nirv_jul", "nirv_last", "gu_doy", "ndre_jul", "nobs"]


def cmd_county(a):
    w = pd.read_csv(f"{DATA}/windows.csv", dtype={"fips": str})
    out = []
    for f in sorted(glob.glob(f"{a.work}/{a.pixdir}/pix_*_*.parquet")):
        _, y, rep = os.path.basename(f)[:-8].split("_")
        d = pd.read_parquet(f)
        if "p_corn" not in d:
            continue
        d["fips"] = w.fips.values[d.win_id.values]
        for crop, sel in [("corn", d.p_corn >= 0.7), ("soy", d.p_corn <= 0.3)]:
            g = d[sel].groupby("fips")
            m = g[MET].median()
            m["npix"] = g.size()
            m["n_re"] = g.ndre_jul.count()
            m.loc[m.n_re < 20, "ndre_jul"] = np.nan
            m["cut_doy"] = d.cut_doy.iloc[0]
            m = m.reset_index().assign(year=int(y), report=rep, crop=crop)
            out.append(m)
    c = pd.concat(out)
    c = c[c.npix >= 30]
    cols = ["year", "report", "crop", "fips", "npix", "cut_doy"] + MET + ["n_re"]
    c[cols].sort_values(["crop", "report", "year", "fips"]).to_csv(f"{FEAT}/county_vi{a.tag}.csv", index=False, float_format="%.4f")
    print(c.groupby(["crop", "report", "year"]).agg(n=("fips", "size"), npix=("npix", "median"), peak=("ndvi_peak", "mean")).to_string())


# ---------------------------------------------------------------- weather
def cmd_weather(a):
    fd = forecast_dates()
    w = pd.read_csv(f"{DATA}/windows.csv", dtype={"fips": str})
    fips = set(w.fips)
    out = []
    for fn in sorted(glob.glob(f"{a.work}/weather/county_*.csv.gz")):
        d = pd.read_csv(fn, dtype={"fips": str}, parse_dates=["date"])
        d = d[d.fips.isin(fips)]
        y = d.date.dt.year.iloc[0]
        d["hdd30"] = (d.tmax_c - 30).clip(lower=0)
        d["gdd"] = ((d.tmax_c.clip(10, 30) + d.tmin_c.clip(10, 30)) / 2 - 10).clip(lower=0)
        for rep in ["aug", "sep"]:
            f = fd[(fd.year == y) & (fd.report == rep)]
            if f.empty:
                # pre-2012 release dates are missing in the source; use the typical dates (training only)
                T = pd.Timestamp(y, 8, 7) if rep == "aug" else pd.Timestamp(y, 9, 6)
            else:
                T = f.forecast_date.iloc[0]
            Tw = T - pd.Timedelta(days=3)
            g = d[d.date <= Tw]
            def win(m0, d0, m1, d1):
                return g[(g.date >= pd.Timestamp(y, m0, d0)) & (g.date <= min(pd.Timestamp(y, m1, d1), Tw))].groupby("fips")
            r = pd.DataFrame(dict(prcp_jun=win(6, 1, 6, 30).prcp_mm.sum(), prcp_jul=win(7, 1, 7, 31).prcp_mm.sum(),
                                  prcp_aug=win(8, 1, 8, 31).prcp_mm.sum(), hdd_jul=win(7, 1, 7, 31).hdd30.sum(),
                                  hdd_aug=win(8, 1, 8, 31).hdd30.sum(), vpd_jja=win(6, 1, 8, 31).vpd_kpa.mean(),
                                  gdd=win(5, 1, 9, 30).gdd.sum(), tmax_jul=win(7, 1, 7, 31).tmax_c.mean()))
            if rep == "aug":
                r["prcp_aug"] = np.nan; r["hdd_aug"] = np.nan
            r = r.reset_index().assign(year=y, report=rep, weather_cutoff=Tw.date())
            out.append(r)
    o = pd.concat(out)
    o.to_csv(f"{FEAT}/county_weather.csv", index=False, float_format="%.3f")
    print(o.groupby(["report", "year"]).size().tail(6))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["offsets", "pixels", "classify", "county", "weather"])
    ap.add_argument("--work", required=True)
    ap.add_argument("--years", default="2013-2026")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--sources", default="landsat,s2", help="pixels: imagery sources to use")
    ap.add_argument("--pixdir", default="pix", help="pixels/classify/county: sub-directory of --work for pixel files")
    ap.add_argument("--tag", default="", help="county: suffix of features/county_vi<tag>.csv")
    a = ap.parse_args()
    {"offsets": cmd_offsets, "pixels": cmd_pixels, "classify": cmd_classify, "county": cmd_county, "weather": cmd_weather}[a.cmd](a)


if __name__ == "__main__":
    main()
