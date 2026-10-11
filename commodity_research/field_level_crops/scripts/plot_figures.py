"""Figures for the field-level study (shared style: one axis, recessive grid, fixed colour order).

  sample   figures/sample_map.png        windows (4 per county) over IA/IL counties
           figures/window_example.png    one window: CDL Y-1 classes and the interior sample points used
  curves   figures/curves_<year>.png     smoothed NDVI of classified corn vs soy pixels in one county + raw obs
  results  figures/accuracy_<period>.png mean |error| by source (states, IA+IL, US)
           figures/county_scatter_<period>.png  predicted vs actual county anomalies (ridge, Sep)
           figures/paths_<crop>.png      IA+IL yield: final, USDA Aug/Sep, model Aug/Sep, trend
Usage: python plot_figures.py sample|curves|results --work <scratch>/field [--geo <dir>] [--period holdout] [--tag v1]
"""
import argparse, os
import numpy as np, pandas as pd
from plotstyle import setup, C, TEXT, GRID, MUTED
from common import DATA, FIG, RES, SIG, FEAT, STFIPS, STATES, MARGIN, point_offsets

plt = setup()


def cmd_sample(a):
    import geopandas as gpd
    w = pd.read_csv(f"{DATA}/windows.csv", dtype={"fips": str})
    c = gpd.read_file(f"zip://{a.geo}/cb_2020_us_county_500k.zip")
    c = c[c.STATEFP.isin([STFIPS[s] for s in STATES])].to_crs(5070)
    fig, ax = plt.subplots(figsize=(7.5, 6))
    c.boundary.plot(ax=ax, color=GRID, linewidth=0.5)
    c.dissolve("STATEFP").boundary.plot(ax=ax, color=MUTED, linewidth=1)
    ax.scatter(w.x0 + 720, w.y0 - 720, s=4, color=C[0], label=f"{len(w)} windows of 1.44 km ({w.fips.nunique()} counties)")
    ax.set_axis_off(); ax.legend(loc="lower left")
    ax.set_title("Sampling windows, Iowa and Illinois (4 per county, >= 50% corn+soy in CDL 2015)", color=TEXT)
    fig.savefig(f"{FIG}/sample_map.png", dpi=130, bbox_inches="tight"); plt.close(fig)
    # window example
    y = 2024; wid = int(a.window)
    z1 = np.load(f"{a.work}/cdl/cdl_{y - 1}.npz")["cdl"][wid]
    zy = np.load(f"{a.work}/cdl/cdl_{y}.npz")["cdl"][wid]
    pix = pd.read_parquet(f"{a.work}/pix/pix_{y}_aug.parquet")
    pix = pix[pix.win_id == wid]
    r, cc = point_offsets()
    fig, axes = plt.subplots(1, 2, figsize=(9, 4.6))
    from matplotlib.colors import ListedColormap
    for ax, arr, ttl in [(axes[0], z1, f"CDL {y - 1} (mask year) + interior points"), (axes[1], zy, f"CDL {y} (truth) + classifier: corn o / soy x")]:
        img = np.full(arr.shape, 2); img[arr == 1] = 0; img[arr == 5] = 1
        ax.imshow(img, cmap=ListedColormap([C[3], C[2], "#e9e8e4"]), vmin=0, vmax=2, interpolation="nearest")
        ax.set_xticks([]); ax.set_yticks([]); ax.set_title(ttl, color=TEXT, fontsize=9); ax.grid(False)
    pr, pc_ = r[pix.pt.values] + MARGIN, cc[pix.pt.values] + MARGIN
    axes[0].scatter(pc_, pr, s=5, color=TEXT)
    corn = pix.p_corn.values >= 0.7; soy = pix.p_corn.values <= 0.3
    axes[1].scatter(pc_[corn], pr[corn], s=9, facecolors="none", edgecolors=TEXT, linewidths=0.6)
    axes[1].scatter(pc_[soy], pr[soy], s=9, marker="x", color=TEXT, linewidths=0.6)
    fig.suptitle(f"Window {wid}: yellow = corn, green = soy, grey = other", color=TEXT, fontsize=9)
    fig.savefig(f"{FIG}/window_example.png", dpi=130, bbox_inches="tight"); plt.close(fig)


def cmd_curves(a):
    from build_features import load_obs, indices, D0
    y = int(a.year)
    w = pd.read_csv(f"{DATA}/windows.csv", dtype={"fips": str})
    offs = pd.read_csv(f"{FEAT}/sensor_offsets.csv").set_index("sensor")
    pix = pd.read_parquet(f"{a.work}/pix/pix_{y}_sep.parquet")
    o = load_obs(a.work, y, ("landsat",))
    ndvi, _, _, _ = indices(o, offs)
    wid = int(a.window)
    p = pix[pix.win_id == wid]
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    doy = pd.to_datetime(o["date"].astype(str)).dayofyear.values
    rows = np.where(o["win_id"] == wid)[0]
    for k, (lab, sel) in enumerate([("corn (classified)", p.p_corn >= 0.7), ("soybeans (classified)", p.p_corn <= 0.3)]):
        pts = p[sel].pt.values
        vals = ndvi[rows][:, pts]
        for j, i in enumerate(rows):
            v = vals[j]; v = v[np.isfinite(v)]
            if len(v):
                ax.scatter(np.full(len(v), doy[i]) + (k - 0.5) * 0.8, v, s=1.5, color=C[k], alpha=0.08, linewidths=0)
        ax.plot([], [], color=C[k], label=lab)
        cols = [c for c in p.columns if c.startswith("c_")]
        ax.plot([int(c[2:]) for c in cols], p[sel][cols].median().values, color=C[k], lw=2)
    ax.set_xlabel("day of year"); ax.set_ylabel("NDVI (Landsat 7/8/9, harmonised to OLI)")
    ax.set_title(f"{y}, window {wid} (county {w.fips[wid]}): raw clear observations and smoothed median curve", color=TEXT)
    ax.legend(loc="lower right"); ax.set_ylim(0, 1)
    fig.savefig(f"{FIG}/curves_{y}.png", dpi=130, bbox_inches="tight"); plt.close(fig)


def cmd_results(a):
    acc = pd.read_csv(f"{RES}/accuracy_{a.period}_{a.tag}.csv")
    srcs = [("ridge", "field model"), ("trend", "trend"), ("modis", "MODIS v1"), ("usda", "USDA")]
    fig, axes = plt.subplots(1, 1, figsize=(9, 4.4))
    ax = axes
    lab = []; x = 0; xt = []
    for (crop, rep), g in acc.groupby(["crop", "report"], sort=False):
        for lvl in ["states (IA, IL)", "IA+IL", "US proxy"]:
            q = g[g.level == lvl]
            if q.empty:
                continue
            for k, (s, nm) in enumerate(srcs):
                ax.bar(x + k * 0.2, q[s].iloc[0], width=0.18, color=C[k], label=nm if x == 0 else None)
            xt.append(x + 0.3); lab.append(f"{crop} {rep}\n{lvl.split(' ')[0]}")
            x += 1
    ax.set_xticks(xt); ax.set_xticklabels(lab, fontsize=7)
    ax.set_ylabel("mean |error| vs January final, %")
    ax.set_title(f"Accuracy, {a.period} ({'2022-2025' if a.period == 'holdout' else '2016-2021'})", color=TEXT)
    ax.legend(ncol=4, loc="upper left")
    fig.savefig(f"{FIG}/accuracy_{a.period}.png", dpi=130, bbox_inches="tight"); plt.close(fig)
    # county scatter
    cp = pd.read_csv(f"{FEAT}/county_predictions_{a.tag}.csv", dtype={"fips": str})
    yrs = range(2022, 2026) if a.period == "holdout" else range(2016, 2022)
    cp = cp[cp.year.isin(yrs) & (cp.model == "ridge") & (cp.report == "sep") & cp.dev.notna()]
    fig, ax = plt.subplots(figsize=(6.5, 5))
    for k, (crop, g) in enumerate(cp.groupby("crop")):
        ax.scatter(100 * g.pred, 100 * g.dev, s=6, color=C[k], alpha=0.5, label=crop, linewidths=0)
    lim = [-45, 30]
    ax.plot(lim, lim, color=MUTED, lw=1); ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_xlabel("predicted county anomaly vs trend, % (September date)"); ax.set_ylabel("actual NASS county anomaly, %")
    ax.set_title(f"County yield anomalies, {a.period}", color=TEXT); ax.legend()
    fig.savefig(f"{FIG}/county_scatter_{a.period}.png", dpi=130, bbox_inches="tight"); plt.close(fig)
    # paths
    s = pd.read_csv(f"{SIG}/field_signal_{a.tag}.csv")
    rr = pd.concat([pd.read_csv(f"{RES}/region_rows_{p}_{a.tag}.csv") for p in ["dev", "holdout"] if os.path.exists(f"{RES}/region_rows_{p}_{a.tag}.csv")])
    for crop in ["corn", "soy"]:
        fig, ax = plt.subplots(figsize=(7.5, 4))
        q = rr[(rr.crop == crop) & (rr.region == "IA+IL")]
        f = q[q.report == "sep"].sort_values("year")
        ax.plot(f.year, f.final, color=TEXT, lw=2, label="January final")
        for k, rep in enumerate(["aug", "sep"]):
            g = q[q.report == rep].sort_values("year")
            ax.plot(g.year, g.ridge, color=C[0], ls="-" if rep == "sep" else ":", marker="o", ms=3, label=f"field model {rep}")
            ax.plot(g.year, g.usda, color=C[1], ls="-" if rep == "sep" else ":", marker="s", ms=3, label=f"USDA {rep}")
        ax.plot(f.year, f.trend, color=MUTED, lw=1, label="trend")
        s26 = s[(s.crop == crop) & (s.region == "IA+IL") & (s.year == 2026) & (s.model == "ridge")]
        for rep, mk in [("aug", "^"), ("sep", "v")]:
            v = s26[s26.report == rep]
            if len(v):
                ax.errorbar([2026], v.predicted_yield, yerr=v.uncertainty, color=C[0], marker=mk, ms=5, capsize=2)
        ax.axvspan(2021.5, 2025.5, color=GRID, alpha=0.5, lw=0)
        ax.set_title(f"IA+IL {crop} yield (bu/ac); shaded = holdout; 2026 = frozen live forecast ±1 sd", color=TEXT)
        ax.legend(ncol=3, fontsize=7, loc="lower left")
        fig.savefig(f"{FIG}/paths_{crop}.png", dpi=130, bbox_inches="tight"); plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["sample", "curves", "results"])
    ap.add_argument("--work")
    ap.add_argument("--geo")
    ap.add_argument("--window", default="40")
    ap.add_argument("--year", default="2019")
    ap.add_argument("--period", default="holdout")
    ap.add_argument("--tag", default="v1")
    a = ap.parse_args()
    {"sample": cmd_sample, "curves": cmd_curves, "results": cmd_results}[a.cmd](a)


if __name__ == "__main__":
    main()
