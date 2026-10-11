#!/usr/bin/env python3
"""Build the satellite and weather inputs: per-pixel phenology masks (winter vs spring crop),
region x year x composite EVI means with availability dates, and region daily weather.

Masks (no CDL equivalent exists for Russia/Ukraine/Kazakhstan):
  * Frame: WorldCover-2021 cropland cells (build_frame.py).
  * Winter crop in harvest year Y: Aqua EVI in spring, before spring-sown crops emerge, above a
    threshold. Two point-in-time definitions:
        w89  : EVI of the composite starting DOY 89 (Mar 30-Apr 14), usable from ~Apr 28
        w121 : max EVI of composites 105 and 121 (Apr 15-May 16), usable from ~May 30
    Thresholds are calibrated once on ESA WorldCereal 2021 (10 m winter-cereal map, sampled
    at the pixels by sample_worldcereal.py): pixels with WorldCereal winter share >= 0.6 vs
    <= 0.2, threshold maximising balanced accuracy, separately for the south (RU_South,
    UA_South, UA_CentralNorth) and the north (all other regions).  Written to
    results/mask_calibration.csv.  WorldCereal has no yield information; using a 2021 map to
    calibrate a spectral threshold applied to all years is documented as a caveat.
  * Spring crop (proxy for spring wheat) = frame cell that is not winter crop in that year.
    In RU_Volga / RU_UralsSiberia / KZ_* this is mostly spring cereals (WorldCereal spring
    share reported); in the south it is mostly sunflower/maize, so spring features are only
    used for those spring-wheat regions.
  QA: MODIS pixel reliability 0 (good) or 1 (marginal) kept; 2 (snow), 3 (cloud) dropped.

Outputs (data/features/):
  pixel_class.csv            pixel_id, year, evi89, evi121, w89, w121, cls (w121 if known else w89)
  modis_region.csv           region, year (harvest year), doy, comp_start, comp_end,
                             available_date (= end + 14 d), mask (winter89/winter121/spring),
                             evi_mean, n_valid, n_mask
  weather_region_daily.csv   region, date, tmax, tmin, prcp, snow_cm (POWER, n_px-weighted)
Autumn composites (DOY 281, 297 of year Y-1) are attached to harvest year Y.

Usage: python build_features.py --work SCRATCH [--power SCRATCH/raw/power]
"""
import argparse
import glob
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "..", "data")
RES = os.path.join(HERE, "..", "results")
SOUTH = {"RU_South", "UA_South", "UA_CentralNorth"}


def load_modis(work):
    rows = []
    for f in sorted(glob.glob(os.path.join(work, "modis_MYD", "*.npz"))):
        if f.endswith(".tmp.npz"):
            continue
        d = np.load(f)
        key = os.path.basename(f)[:7]
        y, doy = int(key[:4]), int(key[4:])
        rows.append(pd.DataFrame({"pixel_id": d["pixel_id"], "cal_year": y, "doy": doy,
                                  "evi": d["evi"].astype(np.float32) / 10000.0, "rel": d["rel"],
                                  "start": str(d["start"]), "end": str(d["end"])}))
    m = pd.concat(rows, ignore_index=True)
    m.loc[~m.rel.isin([0, 1]) | (m.evi < -0.2), "evi"] = np.nan
    m["year"] = np.where(m.doy >= 265, m.cal_year + 1, m.cal_year)  # autumn composites -> next harvest
    return m


def calibrate(m, px, wc_path):
    wc = pd.read_csv(wc_path)
    k = m[(m.year == 2021) & m.doy.isin([89, 105, 121])].pivot_table(index="pixel_id", columns="doy", values="evi")
    k = k.reindex(columns=[89, 105, 121])
    k["e89"], k["e121"] = k[89], k[[105, 121]].max(axis=1)
    k = k.join(px.set_index("pixel_id").region).join(wc.set_index("pixel_id").wc_winter_frac)
    k = k[(k.wc_winter_frac >= 0.6) | (k.wc_winter_frac <= 0.2)]
    k["lab"] = (k.wc_winter_frac >= 0.6).astype(int)
    rows = []
    for zone, g in [("south", k[k.region.isin(SOUTH)]), ("north", k[~k.region.isin(SOUTH)])]:
        for var in ["e89", "e121"]:
            gg = g.dropna(subset=[var])
            best = (0, None, None, None)
            for t in np.arange(0.10, 0.60, 0.005):
                p = gg[var] >= t
                tpr = (p & (gg.lab == 1)).sum() / max(1, (gg.lab == 1).sum())
                tnr = (~p & (gg.lab == 0)).sum() / max(1, (gg.lab == 0).sum())
                ba = (tpr + tnr) / 2
                if ba > best[0]:
                    best = (ba, t, tpr, tnr)
            rows.append(dict(zone=zone, var=var, threshold=round(best[1], 3), balanced_acc=best[0], tpr=best[2],
                             tnr=best[3], n_pos=int((gg.lab == 1).sum()), n_neg=int((gg.lab == 0).sum())))
    return pd.DataFrame(rows)


def classify(m, px, cal):
    k = m[m.doy.isin([89, 105, 121])].pivot_table(index=["pixel_id", "year"], columns="doy", values="evi")
    k = k.reindex(columns=[89, 105, 121])
    out = pd.DataFrame({"evi89": k[89], "evi121": k[[105, 121]].max(axis=1)}).reset_index()
    out = out.merge(px[["pixel_id", "region"]], on="pixel_id")
    out["zone"] = np.where(out.region.isin(SOUTH), "south", "north")
    th = cal.set_index(["zone", "var"]).threshold
    t89 = out.zone.map(lambda z: th[(z, "e89")])
    t121 = out.zone.map(lambda z: th[(z, "e121")])
    out["w89"] = np.where(out.evi89.isna(), np.nan, (out.evi89 >= t89).astype(float))
    out["w121"] = np.where(out.evi121.isna(), np.nan, (out.evi121 >= t121).astype(float))
    fin = out.w121.fillna(out.w89)
    out["cls"] = np.where(fin.isna(), "unknown", np.where(fin == 1, "winter", "spring"))
    return out.drop(columns=["zone"])


def region_means(m, px, cls):
    m = m.merge(px[["pixel_id", "region"]], on="pixel_id")
    c = cls[["pixel_id", "year", "w89", "w121"]]
    m = m.merge(c, on=["pixel_id", "year"], how="left")
    m["w121f"] = m.w121.fillna(m.w89)
    out = []
    for mask, sel in [("winter89", m.w89 == 1), ("winter121", m.w121f == 1), ("spring", m.w121f == 0)]:
        g = m[sel].groupby(["region", "year", "doy", "start", "end"])
        out.append(pd.DataFrame({"evi_mean": g.evi.mean(), "n_valid": g.evi.count(), "n_mask": g.size()})
                   .reset_index().assign(mask=mask))
    r = pd.concat(out)
    r["available_date"] = (pd.to_datetime(r.end) + pd.Timedelta(days=14)).dt.date
    return r.rename(columns={"start": "comp_start", "end": "comp_end"})


def weather(power_dir):
    pts = pd.read_csv(os.path.join(D, "features", "weather_points.csv"))
    rows = []
    for cell, g in pts.groupby("cell"):
        fn = os.path.join(power_dir, f"{cell}.csv")
        if not os.path.exists(fn):
            continue
        w = pd.read_csv(fn).replace(-999.0, np.nan)
        w["date"] = pd.to_datetime(w.YEAR.astype(str), format="%Y") + pd.to_timedelta(w.DOY - 1, unit="D")
        for r in g.itertuples():
            rows.append(w.assign(region=r.region, wt=r.n_px)[["region", "date", "wt", "T2M_MAX", "T2M_MIN", "PRECTOTCORR", "SNODP"]])
    w = pd.concat(rows)
    out = []
    for v, n in [("T2M_MAX", "tmax"), ("T2M_MIN", "tmin"), ("PRECTOTCORR", "prcp"), ("SNODP", "snow_cm")]:
        ok = w[v].notna()
        s = (w[v].where(ok, 0) * w.wt).groupby([w.region, w.date]).sum() / (w.wt * ok).groupby([w.region, w.date]).sum()
        out.append(s.rename(n))
    return pd.concat(out, axis=1).reset_index().dropna(subset=["tmax"])


def main():
    import argparse as _a
    ap = _a.ArgumentParser(description=__doc__, formatter_class=_a.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--power", default=None)
    a = ap.parse_args()
    px = pd.read_csv(os.path.join(D, "reference", "pixels.csv"))
    fdir = os.path.join(D, "features")
    os.makedirs(fdir, exist_ok=True)
    os.makedirs(RES, exist_ok=True)
    wr = weather(a.power or os.path.join(a.work, "raw", "power"))
    wr.to_csv(os.path.join(fdir, "weather_region_daily.csv"), index=False, float_format="%.2f")
    print("weather", wr.shape, wr.date.min(), wr.date.max(), flush=True)
    m = load_modis(a.work)
    print("modis rows", len(m), flush=True)
    cal = calibrate(m, px, os.path.join(D, "reference", "worldcereal_2021_at_pixels.csv"))
    cal.to_csv(os.path.join(RES, "mask_calibration.csv"), index=False, float_format="%.3f")
    print(cal.round(3).to_string())
    cls = classify(m, px, cal)
    cls.to_csv(os.path.join(fdir, "pixel_class.csv"), index=False, float_format="%.4f")
    print(cls.groupby(["region"]).cls.value_counts(normalize=True).unstack().round(2))
    r = region_means(m, px, cls)
    r.to_csv(os.path.join(fdir, "modis_region.csv"), index=False, float_format="%.4f")
    print("region means", r.shape)


if __name__ == "__main__":
    main()
