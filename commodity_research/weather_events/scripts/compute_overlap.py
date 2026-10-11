"""Point-in-time forecast-threat time series: NHC-style cones and GEFS ensemble vs production regions.

For every NHC official forecast (ATCF technique OFCL, one per advisory, 6-hourly) of every Atlantic
storm 2005-2026 we rebuild the advisory's track-forecast cone and test it against each region in
data/regions.geojson. Nothing here uses information from after the advisory, except the cone radii,
which (like NHC's own) come from the PREVIOUS five seasons' official track errors.

Cone reconstruction (NHC method, https://www.nhc.noaa.gov/aboutcone.shtml):
  radius(tau) = 67th percentile of OFCL great-circle track errors at tau over the previous 5 years
  (verified against HURDAT2, tropical/subtropical stages only), taus 12-120 h, 0 at tau 0,
  linear in between; cone = union of convex hulls of consecutive 3-hourly circles along the OFCL
  track. 3-day cone = taus 0-72 h, 5-day cone = 0-120 h. Checked against the published NHC GIS cones
  in plot_cone_maps.py.

Timing: the OFCL forecast for synoptic time T is published in the advisory at T+3 h; the GEFS member
tracks (late, raw model guidance) are treated as available at T+6 h.

Per (storm, advisory, region) columns:
  avail_utc, lat0, lon0, vmax0          advisory position and intensity (kt)
  dist0_km                              current centre to region (0 = inside)
  cone72, cone120                       cone intersects region
  cone72_frac                           fraction of region area inside the 3-day cone
  dmin72_km, dmin120_km                 closest OFCL track point to region within 72 / 120 h
  tau_near, vmax_near                   forecast hour and intensity at closest OFCL point (<=120 h)
  vmax72                                max OFCL intensity 0-72 h
  gefs_n, gefs_p72, gefs_p120           # GEFS members; share passing within 100 km of region by 72/120 h

Also writes per (storm, region) best-track verification (HINDSIGHT, for hit/miss labels only).

Usage: python compute_overlap.py --scratch DIR --regions ../data/regions.geojson --out ../data
"""
import argparse
import glob
import os

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer
from shapely.geometry import Point
from shapely.ops import unary_union

PROJ = "+proj=laea +lat_0=28 +lon_0=-80 +datum=WGS84 +units=m"
TAUS = [12, 24, 36, 48, 72, 96, 120]
TC = {"TD", "TS", "HU", "SS", "SD"}
NM = 1.852


def gc_km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def read_hurdat(path):
    rows, sid, names = [], None, {}
    for line in open(path):
        f = [x.strip() for x in line.split(",")]
        if f[0][:2] in ("AL", "EP", "CP") and len(f) <= 4:
            sid = f[0]
            names[sid] = f[1].title()
            continue
        t = pd.Timestamp(f"{f[0]} {f[1][:2]}:{f[1][2:]}")
        lat = float(f[4][:-1]) * (1 if f[4][-1] == "N" else -1)
        lon = float(f[5][:-1]) * (-1 if f[5][-1] == "W" else 1)
        rows.append([sid, t, f[2], f[3], lat, lon, int(f[6])])
    return pd.DataFrame(rows, columns=["storm_id", "time", "rec", "status", "lat", "lon", "vmax"]), names


def read_bdecks(d):
    out, names = [], {}
    for p in glob.glob(os.path.join(d, "bal*.dat")):
        for line in open(p):
            f = [x.strip() for x in line.split(",")]
            if len(f) < 11:
                continue
            if len(f) > 27 and f[27] and f[27] not in ("INVEST",) and not f[27].startswith(("ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "TEN")):
                names[f"AL{int(f[1]):02d}{f[2][:4]}"] = f[27].title()
            lat = float(f[6][:-1]) / 10 * (1 if f[6][-1] == "N" else -1)
            lon = float(f[7][:-1]) / 10 * (-1 if f[7][-1] == "W" else 1)
            out.append([f"AL{int(f[1]):02d}{f[2][:4]}", pd.Timestamp(f[2][:8] + " " + f[2][8:10] + ":00"),
                        "", f[10], lat, lon, int(f[8])])
    b = pd.DataFrame(out, columns=["storm_id", "time", "rec", "status", "lat", "lon", "vmax"])
    return b.drop_duplicates(["storm_id", "time"]), names


def best_at(bt, sid, times):
    """Linear interpolation of best track (lat, lon, status, vmax) at given times; NaN outside."""
    g = bt.get(sid)
    if g is None:
        return None
    x = g.time.values.astype("datetime64[s]").astype(float)
    tt = np.asarray(times, dtype="datetime64[s]").astype(float)
    inside = (tt >= x[0]) & (tt <= x[-1])
    lat = np.where(inside, np.interp(tt, x, g.lat.values), np.nan)
    lon = np.where(inside, np.interp(tt, x, g.lon.values), np.nan)
    idx = np.clip(np.searchsorted(x, tt, side="right") - 1, 0, len(x) - 1)
    tc = np.where(inside, g.status.isin(TC).values[idx], False)
    return lat, lon, tc


def cone_radii(ofcl, bt):
    """Per year: 67th pct of OFCL track error (n mi) at TAUS over the previous 5 seasons."""
    o = ofcl[ofcl.tau.isin([0] + TAUS)].copy()
    o["valid"] = o.init_t + pd.to_timedelta(o.tau, unit="h")
    errs = []
    for sid, g in o.groupby("storm_id"):
        r = best_at(bt, sid, g.valid.values)
        r0 = best_at(bt, sid, g.init_t.values)
        if r is None:
            continue
        e = gc_km(g.lat.values, g.lon.values, r[0], r[1]) / NM
        errs.append(pd.DataFrame({"year": g.init_t.dt.year.values, "tau": g.tau.values, "err": e,
                                  "ok": r[2] & r0[2]}))
    e = pd.concat(errs)
    e = e[e.ok & e.err.notna()]
    rad = {}
    for y in range(2005, 2027):
        w = e[(e.year >= y - 5) & (e.year <= y - 1)]
        rad[y] = {t: float(np.percentile(w[w.tau == t].err, 67)) for t in TAUS}
    return pd.DataFrame(rad).T.rename_axis("year")


def track_pts(g, tmax, step=3):
    """Interpolate a forecast track (tau, lat, lon, vmax) to `step`-hour taus up to tmax."""
    g = g[g.tau <= tmax].sort_values("tau")
    if len(g) == 0:
        return None
    taus = np.arange(0, g.tau.max() + 1, step)
    return (taus, np.interp(taus, g.tau, g.lat), np.interp(taus, g.tau, g.lon),
            np.interp(taus, g.tau, g.vmax))


def build_cone(pts, rad_nm, fwd):
    taus, lat, lon, _ = pts
    x, y = fwd.transform(lon, lat)
    rtau = [0] + TAUS
    r = np.interp(taus, rtau, [0] + [rad_nm[t] for t in TAUS]) * NM * 1000
    circles = [Point(xi, yi).buffer(max(ri, 1000), 32) for xi, yi, ri in zip(x, y, r)]
    if len(circles) == 1:
        return circles[0]
    return unary_union([unary_union([a, b]).convex_hull for a, b in zip(circles[:-1], circles[1:])])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--regions", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    fwd = Transformer.from_crs(4326, PROJ, always_xy=True)
    reg = gpd.read_file(a.regions).to_crs(PROJ)
    R = dict(zip(reg.region, reg.geometry))
    for g in R.values():
        shapely.prepare(g)

    hd, names = read_hurdat(os.path.join(a.scratch, "hurdat2.txt"))
    hd = hd[hd.storm_id.str.startswith("AL") & (hd.time.dt.year >= 2000)]
    b26, n26 = read_bdecks(os.path.join(a.scratch, "bdeck_2026"))
    names.update(n26)
    bt_all = pd.concat([hd, b26], ignore_index=True)
    bt = {k: g.sort_values("time").reset_index(drop=True) for k, g in bt_all.groupby("storm_id")}

    ad = pd.read_csv(os.path.join(a.scratch, "atcf_filtered.csv.gz"), dtype={"init": str},
                     usecols=["storm_id", "init", "tech", "tau", "lat", "lon", "vmax"])
    ad = ad[(ad.lat.abs() > 0) & (ad.lon.abs() > 0) & (ad.tau <= 120) & (ad.tech != "AEMN")]
    ofcl = ad[ad.tech == "OFCL"].copy()
    ofcl["init_t"] = pd.to_datetime(ofcl.init, format="%Y%m%d%H")
    gefs = ad[(ad.tech != "OFCL") & (ad.init.str[:4].astype(int) >= 2005) & (ad.tau % 6 == 0)].copy()
    del ad
    gefs = gefs.sort_values(["storm_id", "init", "tech", "tau"]).reset_index(drop=True)
    gkey = (gefs.storm_id + "|" + gefs.init).values
    brk = np.flatnonzero(np.r_[True, gkey[1:] != gkey[:-1], True])
    gidx = {gkey[s0]: (s0, s1) for s0, s1 in zip(brk[:-1], brk[1:])}

    rad = cone_radii(ofcl, bt)
    rad.round(1).to_csv(os.path.join(a.out, "cone_radii_nm.csv"))
    print(rad.round(0))

    adv = ofcl[ofcl.init_t.dt.year >= 2005].groupby(["storm_id", "init_t"]).agg(
        lat0=("lat", "first"), lon0=("lon", "first"), vmax0=("vmax", "first")).reset_index()
    adv["avail_utc"] = adv.init_t + pd.Timedelta(hours=3)
    adv.to_csv(os.path.join(a.out, "advisories.csv.gz"), index=False)
    rows = []
    groups = ofcl[ofcl.init_t.dt.year >= 2005].groupby(["storm_id", "init"])
    for n_adv, ((sid, init), g) in enumerate(groups):
        if n_adv % 1000 == 0:
            print("advisory", n_adv, "of", groups.ngroups, flush=True)
        p120 = track_pts(g, 120)
        if p120 is None or p120[0][-1] < 12:
            continue
        X, Y = fwd.transform(p120[2], p120[1])
        pts = shapely.points(X, Y)
        dist = {name: shapely.distance(pts, geom) / 1000 for name, geom in R.items()}
        near = {name: d for name, d in dist.items() if d.min() <= 2000}
        if not near:
            continue
        t0 = g.init_t.iloc[0]
        rr = rad.loc[t0.year].to_dict()
        # the widest cone radius is < 700 km, so cones only matter when the track gets that close
        if min(d.min() for d in near.values()) <= 750:
            c72, c120 = build_cone(track_pts(g, 72), rr, fwd), build_cone(p120, rr, fwd)
        else:
            c72 = c120 = None
        se = gidx.get(f"{sid}|{init}")
        gm = gefs.iloc[se[0]:se[1]] if se else None
        mem = []
        if gm is not None:
            for _, m in gm.groupby("tech"):
                mp = track_pts(m, 120, step=6)
                if mp is not None and mp[0][-1] >= 24:
                    mx, my = fwd.transform(mp[2], mp[1])
                    mem.append((mp[0], shapely.points(mx, my)))
        x0, y0 = fwd.transform(p120[2][0], p120[1][0])
        for name, d in near.items():
            geom = R[name]
            k = int(np.argmin(d))
            m72 = p120[0] <= 72
            hit72 = hit120 = 0
            for mt, mpts in mem:
                dm = shapely.distance(mpts, geom) / 1000
                hit72 += bool((dm[mt <= 72] <= 100).any())
                hit120 += bool((dm <= 100).any())
            inter72 = c72 is not None and c72.intersects(geom)
            rows.append(dict(
                storm_id=sid, name=names.get(sid, ""), init=t0, avail_utc=t0 + pd.Timedelta(hours=3), region=name,
                lat0=p120[1][0], lon0=p120[2][0], vmax0=int(g[g.tau == g.tau.min()].vmax.iloc[0]),
                dist0_km=round(shapely.distance(Point(x0, y0), geom) / 1000, 1),
                cone72=bool(inter72), cone120=bool(c120 is not None and c120.intersects(geom)),
                cone72_frac=round(c72.intersection(geom).area / geom.area, 4) if inter72 else 0.0,
                dmin72_km=round(d[m72].min(), 1), dmin120_km=round(d.min(), 1),
                tau_near=int(p120[0][k]), vmax_near=int(p120[3][k]), vmax72=int(p120[3][m72].max()),
                gefs_n=len(mem), gefs_p72=round(hit72 / len(mem), 3) if mem else np.nan,
                gefs_p120=round(hit120 / len(mem), 3) if mem else np.nan))
    ov = pd.DataFrame(rows).sort_values(["region", "init", "storm_id"])
    ov.to_csv(os.path.join(a.out, "forecast_overlap.csv"), index=False)
    print("overlap rows", len(ov))

    # ---- best-track verification (hindsight) per storm x region ----
    ver = []
    for sid, g in bt.items():
        if int(sid[-4:]) < 2005:
            continue
        # 1-hourly interpolation so fast storms crossing small regions are not skipped
        tt = pd.date_range(g.time.iloc[0], g.time.iloc[-1], freq="1h")
        x = g.time.values.astype("datetime64[s]").astype(float)
        tf = tt.values.astype("datetime64[s]").astype(float)
        lat, lon = np.interp(tf, x, g.lat), np.interp(tf, x, g.lon)
        vm = np.interp(tf, x, g.vmax)
        idx = np.clip(np.searchsorted(x, tf, side="right") - 1, 0, len(x) - 1)
        tc = g.status.isin(TC).values[idx]
        X, Y = fwd.transform(lon, lat)
        pts = shapely.points(X, Y)
        for name, geom in R.items():
            d = shapely.distance(pts, geom) / 1000
            if d.min() > 600:
                continue
            k = int(np.argmin(d))
            near = (d <= 100) & tc
            hu = near & (vm >= 64)
            land = g[(g.rec == "L")]
            if len(land):
                lx, ly = fwd.transform(land.lon.values, land.lat.values)
                ld = shapely.distance(shapely.points(lx, ly), geom) / 1000
                j = int(np.argmin(ld))
                lf_t, lf_v, lf_d = land.time.iloc[j], int(land.vmax.iloc[j]), round(ld[j], 1)
            else:
                lf_t, lf_v, lf_d = pd.NaT, np.nan, np.nan
            ver.append(dict(storm_id=sid, name=names.get(sid, ""), region=name, bt_dmin_km=round(d.min(), 1),
                            bt_t_closest=tt[k], bt_vmax_closest=int(vm[k]),
                            bt_vmax_within100=int(vm[near].max()) if near.any() else 0,
                            bt_first_within100_ts=tt[near][0] if near.any() else pd.NaT,
                            bt_hit_hu=bool(hu.any()), bt_hit_ts=bool((near & (vm >= 34)).any()),
                            landfall_utc=lf_t, landfall_vmax=lf_v, landfall_dist_km=lf_d))
    pd.DataFrame(ver).to_csv(os.path.join(a.out, "besttrack_verification.csv"), index=False)
    pd.Series(names, name="name").rename_axis("storm_id").loc[lambda x: x.index.str.startswith("AL")] \
        .to_csv(os.path.join(a.out, "storm_names.csv"))


if __name__ == "__main__":
    main()
