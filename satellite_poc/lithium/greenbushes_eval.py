"""Greenbushes: optical mine-activity index vs IGO-reported material mined (tests B1-B3).

The index is the Karlawinda optical index (../optical_zones.py), re-implemented here as a
function so the threshold can be varied for B2. At THRESH=0.12 and SHADOW=-0.3 it reproduces
optical_zones.py exactly (checked in the run log).

For each pair of consecutive clear Sentinel-2 images: the share of the zone's busy pixels
whose red+SWIR brightness changed by more than THRESH in log terms, after normalising by
natural-ground control, minus the same share in control. Busy pixels are picked before
CALIB_END and scored after it. Each pair is assigned to the IGO fiscal quarter of its later
image (FY ends 30 June).

Tests (pre-registered in README.md):
  B1  frozen settings: Pearson r of quarterly mean pit index vs total material mined (BCM), and r of
      quarter-on-quarter differences.
  B2  tune zone {pit, pit+dumps} x THRESH {0.08, 0.12, 0.16} on 1Q22-4Q24, score once on 1Q25-4Q26.
  B3  per-pair Welch t-tests: 2 quarters before vs after 29 Jan 2024; Jan-Jun 2025 vs Jul-Dec 2025.

Usage:
    python greenbushes_eval.py STACK_RED_SWIR.npz ZONES_JSON PRODUCTION.csv OUT_PREFIX
writes OUT_PREFIX_pairs.csv, OUT_PREFIX_quarterly.csv, OUT_PREFIX_results.json
"""
import json
import sys

import numpy as np
import pandas as pd
from scipy import stats

BUF = 15
CALIB_END = "2021-07-01"
TUNE_END = "2024-06-30"


def index(stack, zones, calib_end=CALIB_END, thresh=0.12, shadow=-0.3):
    """Per-pair index for each zone. zones: name -> list of [x0,x1,y0,y1] boxes."""
    d = np.load(stack)
    refl, dates = d["refl"].astype(np.float32), pd.to_datetime(d["dates"])
    keep = ~dates.duplicated(keep="last")
    refl, dates = refl[keep], dates[keep]
    b = refl.sum(1)
    b[(refl == 0).any(1)] = np.nan
    H, W = b.shape[1:]
    yy, xx = np.mgrid[:H, :W]
    box = lambda x0, x1, y0, y1, p=0: (xx >= x0 - p) & (xx <= x1 + p) & (yy >= y0 - p) & (yy <= y1 + p)
    near = np.zeros((H, W), bool)
    for boxes in zones.values():
        for bb in boxes:
            near |= box(*bb, BUF)
    ctrl = ~near
    lb = np.log(b) - np.nanmedian(np.log(b)[:, ctrl], axis=1)[:, None, None]
    ch = np.abs(np.diff(lb, axis=0))
    dark = lb < shadow
    ok = np.isfinite(ch) & ~dark[1:] & ~dark[:-1]
    big = (ch > thresh) & ok
    dd = dates[1:]
    cal = dd < pd.Timestamp(calib_end)
    freq = big[cal].sum(0) / np.maximum(ok[cal].sum(0), 1)
    busy = freq > np.quantile(freq[ctrl], 0.9)
    share = lambda m: big[~cal][:, m].sum(1) / np.maximum(ok[~cal][:, m].sum(1), 1)
    c = share(ctrl)
    taken, res = np.zeros((H, W), bool), {}
    for name, boxes in zones.items():
        m = np.zeros((H, W), bool)
        for bb in boxes:
            m |= box(*bb)
        if "+" not in name:            # plain zones are exclusive, in order; combos are unions
            m &= ~taken
            taken |= m
        res[name] = (share(m & busy) - c) * 100
    df = pd.DataFrame(res, index=dd[~cal])
    df.index.name = "date"
    df["days_since_prev"] = (dd[~cal] - dates[:-1][~cal]).days
    return df


def fiscal_quarter(ts):
    q = (ts.month - 1) // 3 + 1                         # calendar quarter
    fq = {1: 3, 2: 4, 3: 1, 4: 2}[q]
    fy = ts.year + (1 if q >= 3 else 0)
    return f"{fq}Q{fy % 100:02d}"


def corr(x, y):
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 4:
        return np.nan, np.nan, int(m.sum())
    r, p = stats.pearsonr(x[m], y[m])
    return float(r), float(p / 2 if r > 0 else 1 - p / 2), int(m.sum())     # one-sided


def main():
    stack, zones_json, prod_csv, out = sys.argv[1:5]
    zones = {k: [v] for k, v in json.loads(zones_json).items()}
    zones["pit+dumps"] = zones["pit"] + zones["dumps"]
    prod = pd.read_csv(prod_csv, index_col=0, parse_dates=["quarter_end"])
    y = prod["total_material_bcm"] / 1e6
    res = {}

    pairs = index(stack, zones)
    pairs.round(2).to_csv(f"{out}_pairs.csv")
    pairs["fq"] = [fiscal_quarter(t) for t in pairs.index]
    zc = [c for c in pairs.columns if c not in ("days_since_prev", "fq")]
    q = pairs.groupby("fq")[zc].mean()
    q["n_pairs"] = pairs.groupby("fq").size()
    q = q.reindex(prod.index)
    q.insert(0, "quarter_end", prod["quarter_end"].dt.date)
    q["total_material_Mbcm"] = y
    q["ore_mined_Mt"] = prod["ore_mined_t"] / 1e6
    q.round(3).to_csv(f"{out}_quarterly.csv")
    print(q.round(2).to_string())

    # B1 frozen
    b1 = {}
    for z in zc:
        r, p, n = corr(q[z].values, y.values)
        rd, pd_, nd = corr(np.diff(q[z].values), np.diff(y.values))
        b1[z] = dict(r=r, p_one_sided=p, n=n, r_diff=rd, p_diff=pd_, n_diff=nd)
    res["B1_frozen"] = b1
    res["B1_pass"] = bool(b1["pit"]["r"] >= 0.5 and b1["pit"]["p_one_sided"] < 0.05 and b1["pit"]["r_diff"] > 0.3)

    # B2 tune / holdout
    tune = prod["quarter_end"] <= TUNE_END
    grid = []
    for th in (0.08, 0.12, 0.16):
        pp = pairs if th == 0.12 else index(stack, zones, thresh=th)
        pp = pp.assign(fq=[fiscal_quarter(t) for t in pp.index])
        qq = pp.groupby("fq")[["pit", "pit+dumps"]].mean().reindex(prod.index)
        for z in ("pit", "pit+dumps"):
            rt = corr(qq[z][tune].values, y[tune].values)[0]
            rh, ph, nh = corr(qq[z][~tune].values, y[~tune].values)
            grid.append(dict(zone=z, thresh=th, r_tune=rt, r_holdout=rh, p_holdout=ph, n_holdout=nh))
    g = pd.DataFrame(grid)
    best = g.loc[g["r_tune"].idxmax()].to_dict()
    res["B2_grid"] = grid
    res["B2_selected"] = best
    print(g.round(3).to_string())

    # B3 level changes
    def welch(a0, a1, b0, b1_, z="pit"):
        s = pairs[z]
        x0, x1 = s[a0:a1].dropna(), s[b0:b1_].dropna()
        t, p = stats.ttest_ind(x1, x0, equal_var=False)
        return dict(before_mean=float(x0.mean()), after_mean=float(x1.mean()), n_before=len(x0), n_after=len(x1),
                    t=float(t), p=float(p))
    res["B3_jan2024_guidance_cut"] = {z: welch("2023-07-29", "2024-01-29", "2024-01-30", "2024-07-29", z)
                                      for z in ("pit", "pit+dumps")}
    res["B3_2025_fleet_cut"] = {z: welch("2025-01-01", "2025-06-30", "2025-07-01", "2025-12-31", z)
                                for z in ("pit", "pit+dumps")}
    json.dump(res, open(f"{out}_results.json", "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "B2_grid"}, indent=1))


if __name__ == "__main__":
    main()
