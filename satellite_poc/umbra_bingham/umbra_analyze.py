"""Mobile-equipment counts at Bingham Canyon from umbra_detect.py output, and the
pre-registered test.

Steps
1. Quality rule: drop collects steeper than MIN_INCIDENCE (20 deg). At such steep angles
   the pit walls lay over and detections were visibly dominated by stretched bench
   crests (decided from detection galleries before any counts were looked at).
2. Common footprint: only detections inside pixels covered by every kept image count.
3. Static mask: 20 m cells holding a detection in more than 25 % of images are fixed
   structures or parked fleets and are dropped. What is left is the "mobile" count.
4. Geometry correction: OLS of the mobile count on viewing geometry (sin/cos azimuth,
   incidence, look side) over all kept images; the corrected count is the residual
   plus the overall mean (so it stays in "objects" units).
5. Pre-registered test: corrected count in Apr-Dec 2024 vs Jul 2023-Mar 2024,
   hypothesis "lower". Welch t-test, a permutation test on the mean difference and a
   Mann-Whitney rank test. 2025 is reported separately.
6. Robustness (not part of the pre-registration): period dummies inside the
   regression (ANCOVA), an incidence-matched subset, and no incidence filter.

Usage:
  python umbra_analyze.py INDEX.csv DETS.json CACHE_DIR OUT_DIR
Writes per_image_counts.csv, quarterly_means.csv, test_results.csv, figure PNGs.
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

CELL, STATIC_SHARE, MIN_INCIDENCE = 20, 0.25, 20.0
PRE = ("2023-07-01", "2024-04-01")
POST = ("2024-04-01", "2025-01-01")
BREAK = pd.Timestamp("2024-04-01")
N_PERM = 20000


def key(t):
    return pd.Timestamp(t).strftime("%Y%m%dT%H%M%S")


def design(df):
    az = np.radians(df.azimuth.values)
    return np.column_stack([np.ones(len(df)), np.sin(az), np.cos(az), df.incidence.values,
                            (df.look == "RIGHT").astype(float).values])


def correct(df, extra=None):
    X = design(df)
    if extra is not None:
        X = np.column_stack([X, extra])
    beta, *_ = np.linalg.lstsq(X, df.mobile.values, rcond=None)
    return beta, X


def period(t):
    if pd.Timestamp(PRE[0]) <= t < pd.Timestamp(PRE[1]):
        return "pre"
    if pd.Timestamp(POST[0]) <= t < pd.Timestamp(POST[1]):
        return "post"
    return "2025" if t.year == 2025 else "other"


def tests(a, b, rng):
    """Hypothesis: mean(b) < mean(a). Returns dict with one-sided p values."""
    t = stats.ttest_ind(b, a, equal_var=False, alternative="less")
    diff = b.mean() - a.mean()
    pool = np.concatenate([a, b])
    perm = np.empty(N_PERM)
    for i in range(N_PERM):
        p = rng.permutation(pool)
        perm[i] = p[len(a):].mean() - p[:len(a)].mean()
    mw = stats.mannwhitneyu(b, a, alternative="less")
    return dict(n_pre=len(a), n_post=len(b), mean_pre=a.mean(), mean_post=b.mean(),
                diff=diff, pct=100 * diff / a.mean(), welch_t=t.statistic, welch_p=t.pvalue,
                perm_p=(perm <= diff).mean(), mannwhitney_p=mw.pvalue)


def build(idx, dets, cache, min_inc):
    df = pd.DataFrame([d for d in dets["images"] if "error" not in d])
    df["time"] = pd.to_datetime(df["time"])
    df = df.merge(idx, on="time")
    df = df[df.incidence >= min_inc].reset_index(drop=True)
    common = None
    for t in df.time:
        m = np.load(os.path.join(cache, key(t) + ".npy")) > 0
        common = m if common is None else common & m
    rc = [[(r, c) for r, c, _ in d if common[r, c]] for d in df.rc]
    cells = [set((r // CELL, c // CELL) for r, c in x) for x in rc]
    n = {}
    for s in cells:
        for c in s:
            n[c] = n.get(c, 0) + 1
    static = {c for c, k in n.items() if k > STATIC_SHARE * len(df)}
    df["objects"] = [len(x) for x in rc]
    df["mobile"] = [sum((r // CELL, c // CELL) not in static for r, c in x) for x in rc]
    df["mobile_rc"] = [[(r, c) for r, c in x if (r // CELL, c // CELL) not in static] for x in rc]
    beta, X = correct(df)
    df["corrected"] = df.mobile - X @ beta + df.mobile.mean()
    df["period"] = df.time.map(period)
    return df, static, common, beta


def main(index_csv, dets_json, cache, out):
    os.makedirs(out, exist_ok=True)
    rng = np.random.default_rng(42)
    idx = pd.read_csv(index_csv, parse_dates=["time"])
    dets = json.load(open(dets_json))
    df, static, common, beta = build(idx, dets, cache, MIN_INCIDENCE)
    fit = df.mobile - df.corrected + df.mobile.mean()
    r2 = 1 - np.var(df.mobile - fit) / np.var(df.mobile)
    print(f"images {len(df)} (incidence >= {MIN_INCIDENCE}), common footprint "
          f"{common.mean():.2f} of grid, static cells {len(static)}, geometry R^2 {r2:.2f}")
    print("geometry coefficients [const, sin az, cos az, incidence, right-look]:",
          np.round(beta, 2))

    rows = []
    pre, post = df[df.period == "pre"], df[df.period == "post"]
    rows.append(dict(test="PRE-REGISTERED: geometry-corrected count, Apr-Dec 2024 vs "
                          "Jul 2023-Mar 2024", **tests(pre.corrected.values, post.corrected.values, rng)))
    rows.append(dict(test="raw mobile count (no geometry correction)",
                     **tests(pre.mobile.values, post.mobile.values, rng)))
    y25 = df[df.period == "2025"]
    rows.append(dict(test="2025 vs Jul 2023-Mar 2024 (corrected, hypothesis lower)",
                     **tests(pre.corrected.values, y25.corrected.values, rng)))
    # ANCOVA: geometry + period dummies fitted together
    d3 = df[df.period.isin(["pre", "post", "2025"])].reset_index(drop=True)
    dum = np.column_stack([(d3.period == "post").astype(float), (d3.period == "2025").astype(float)])
    b, X = correct(d3, dum)
    res = d3.mobile.values - X @ b
    dof = len(d3) - X.shape[1]
    cov = np.linalg.inv(X.T @ X) * (res @ res) / dof
    for j, name in ((-2, "post (Apr-Dec 2024)"), (-1, "2025")):
        se = np.sqrt(cov[j, j]); tval = b[j] / se
        rows.append(dict(test=f"ANCOVA: {name} effect vs pre, geometry in same model",
                         diff=b[j], pct=100 * b[j] / pre.mobile.mean(), welch_t=tval,
                         welch_p=stats.t.cdf(tval, dof), n_pre=len(pre),
                         n_post=int((d3.period == name.split()[0]).sum()) if name == "2025"
                         else len(post)))
    # incidence-matched: only collects in the incidence band both periods share
    lo, hi = 20, 30
    pm, qm = pre[(pre.incidence >= lo) & (pre.incidence <= hi)], post[(post.incidence >= lo) & (post.incidence <= hi)]
    rows.append(dict(test=f"incidence-matched {lo}-{hi} deg, raw mobile count",
                     **tests(pm.mobile.values, qm.mobile.values, rng)))
    # no incidence filter
    dfa, *_ = build(idx, dets, cache, 0)
    rows.append(dict(test="no incidence filter (all collects), corrected",
                     **tests(dfa[dfa.period == "pre"].corrected.values,
                             dfa[dfa.period == "post"].corrected.values, rng)))
    res_df = pd.DataFrame(rows)
    res_df.to_csv(os.path.join(out, "test_results.csv"), index=False, float_format="%.4g")
    with pd.option_context("display.width", 250, "display.max_colwidth", 80):
        print(res_df[["test", "n_pre", "n_post", "mean_pre", "mean_post", "diff", "pct",
                      "welch_p", "perm_p", "mannwhitney_p"]].round(3).to_string())

    df[["time", "azimuth", "incidence", "look", "cover", "objects", "mobile", "corrected",
        "period"]].to_csv(os.path.join(out, "per_image_counts.csv"), index=False,
                          float_format="%.3f")
    q = df.groupby(df.time.dt.to_period("Q")).agg(
        n=("mobile", "size"), incidence_mean=("incidence", "mean"), mobile=("mobile", "mean"),
        corrected=("corrected", "mean"), corrected_se=("corrected", "sem"))
    q.index = q.index.astype(str)
    q.round(2).to_csv(os.path.join(out, "quarterly_means.csv"))
    print(q.round(1).to_string())
    json.dump({"static_cells": len(static), "geometry_r2": r2, "beta": list(beta)},
              open(os.path.join(out, "analysis_meta.json"), "w"))
    plot_series(df, q, os.path.join(out, "bingham_equipment_timeseries.png"))
    spatial(df, common, os.path.join(out, "bingham_spatial_shift.png"), out)


def plot_series(df, q, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    blue, ink, bg = "#2a78d6", "#52514e", "#fcfcfb"
    fig, ax = plt.subplots(figsize=(10, 4.6), dpi=150)
    fig.patch.set_facecolor(bg); ax.set_facecolor(bg)
    ax.scatter(df.time, df.corrected, s=12, color=blue, alpha=0.35, lw=0)
    qt = pd.PeriodIndex(q.index, freq="Q").to_timestamp(how="start") + pd.Timedelta(days=45)
    ax.plot(qt, q.corrected, color=blue, lw=2, marker="o", ms=5)
    ax.axvline(BREAK, color=ink, ls="--", lw=1)
    top = ax.get_ylim()[1]
    ax.text(BREAK + pd.Timedelta(days=6), top * 0.97,
            "Q2 2024: Rio Tinto discloses pit-wall\n(geotechnical) constraints at Kennecott", color=ink,
            fontsize=8.5, va="top")
    ax.grid(axis="y", color="#e6e5e1", lw=0.6); ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#c9c8c3")
    ax.tick_params(colors=ink, labelsize=8.5)
    ax.set_ylabel("objects in pit core (geometry-corrected)", color=ink, fontsize=9)
    ax.set_title("Bingham Canyon: mobile-equipment detections per Umbra SAR image "
                 "(dots) and quarterly mean (line)", color="#22211f", fontsize=10, loc="left")
    fig.tight_layout(); fig.savefig(path, facecolor=bg); plt.close(fig)


def spatial(df, common, path, out):
    """Exploratory: share of mobile detections in the southern third of the pit core."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    h = common.shape[0]
    south0 = int(h * 2 / 3)
    df["south_share"] = [np.mean([r >= south0 for r, _ in x]) if x else np.nan for x in df.mobile_rc]
    s = df.groupby("period").south_share.agg(["mean", "count"])
    a, b = df[df.period == "pre"].south_share.dropna(), df[df.period == "post"].south_share.dropna()
    p = stats.ttest_ind(b, a, equal_var=False).pvalue
    print("south-third share of mobile detections by period:\n", s.round(3), f"\nWelch p (post vs pre) {p:.3f}")
    s.assign(welch_p_post_vs_pre=p).to_csv(os.path.join(out, "spatial_south_share.csv"))
    blue, ink, bg = "#2a78d6", "#52514e", "#fcfcfb"
    fig, axs = plt.subplots(1, 3, figsize=(12, 4.4), dpi=130)
    fig.patch.set_facecolor(bg)
    for ax, per, lab in zip(axs, ["pre", "post", "2025"],
                            ["Jul 2023-Mar 2024", "Apr-Dec 2024", "2025"]):
        pts = np.array([rc for x in df[df.period == per].mobile_rc for rc in x])
        nimg = (df.period == per).sum()
        H, _, _ = np.histogram2d(pts[:, 0], pts[:, 1], bins=[h // 100, common.shape[1] // 100],
                                 range=[[0, h], [0, common.shape[1]]])
        ax.imshow(H / nimg, cmap="Blues", vmin=0, vmax=0.25)
        ax.axhline(south0 / 100, color=ink, ls="--", lw=0.8)
        ax.set_title(f"{lab} ({nimg} images)", color=ink, fontsize=9)
        ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle("Mobile detections per image per 100 m cell (north up; dashed = start of "
                 "southern third). Not terrain-corrected: positions shift with viewing geometry.",
                 color=ink, fontsize=8.5)
    fig.tight_layout(); fig.savefig(path, facecolor=bg); plt.close(fig)


if __name__ == "__main__":
    main(*sys.argv[1:5])
