"""Figures for the smelter study (one axis per panel, recessive grid, fixed colour order).

Usage:
    python plots.py
Writes figures/*.png from data/index, results/ and data/s3frp.
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figures")
C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
TEXT, BG, GRID = "#52514e", "#fcfcfb", "#e6e5e1"
plt.rcParams.update({"figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG, "text.color": TEXT,
                     "axes.labelcolor": TEXT, "xtick.color": TEXT, "ytick.color": TEXT, "axes.edgecolor": GRID,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
                     "axes.spines.right": False, "font.size": 9, "axes.titlesize": 9, "lines.linewidth": 1.6})


def small_multiples():
    m = pd.read_csv(os.path.join(HERE, "data", "index", "monthly.csv"))
    sm = pd.read_csv(os.path.join(HERE, "smelters.csv"))
    ev = pd.read_csv(os.path.join(HERE, "events.csv"))
    fr = None
    p = os.path.join(HERE, "results", "s3frp_monthly.csv")
    if os.path.exists(p):
        fr = pd.read_csv(p)
    ids = [i for i in sm.id if i in set(m.smelter)]
    n = len(ids); cols = 5; rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(15, 1.9 * rows), sharex=True, sharey=True)
    for ax, sid in zip(axes.flat, ids):
        d = m[m.smelter == sid].copy(); d["t"] = pd.to_datetime(d.month)
        d = d.set_index("t").active_share.resample("MS").mean()
        ax.plot(d.index, d.rolling(3, min_periods=1).mean(), color=C[0], label="Sentinel-2 day (SWIR)")
        if fr is not None and sid in set(fr.smelter):
            f = fr[fr.smelter == sid].copy(); f["t"] = pd.to_datetime(f.month)
            f = f.set_index("t").active_share.resample("MS").mean()
            ax.plot(f.index, f.rolling(3, min_periods=1).mean(), color=C[1], label="Sentinel-3 night (FRP)")
        for e in ev[ev.smelter == sid].itertuples():
            ax.axvspan(pd.Timestamp(e.start), pd.Timestamp(e.end), color="#d9d8d3", lw=0, zorder=0)
        row = sm[sm.id == sid].iloc[0]
        ax.set_title(f"{row['name']} ({row.country})", loc="left")
        ax.set_ylim(0, 1.02)
    for ax in axes.flat[n:]:
        ax.axis("off")
    h, l = axes.flat[0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper right", frameon=False, ncol=2)
    fig.suptitle("Share of clear passes with a hot pixel on the furnace mask, 3-month mean (grey = documented outage window)",
                 x=0.01, ha="left", color=TEXT)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(os.path.join(FIG, "smelters_small_multiples.png"), dpi=110)
    plt.close(fig)


def events_scenes():
    ev = pd.read_csv(os.path.join(HERE, "events.csv"))
    ev = ev[ev.expected == "off"]
    n = len(ev); cols = 4; rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(14, 2.1 * rows))
    for ax, e in zip(axes.flat, ev.itertuples()):
        f = os.path.join(HERE, "data", "index", f"{e.smelter}_scenes.csv")
        if not os.path.exists(f):
            ax.axis("off"); continue
        s = pd.read_csv(f); s = s[s.valid]; s["t"] = pd.to_datetime(s.date)
        a, b = pd.Timestamp(e.baseline_start), pd.Timestamp(e.end) + pd.Timedelta(days=120)
        s = s[(s.t >= a) & (s.t <= b)]
        ax.axvspan(pd.Timestamp(e.start), pd.Timestamp(e.end), color="#d9d8d3", lw=0, zorder=0)
        ax.scatter(s.t, s.n_mask_hot, s=10, color=C[0], zorder=3)
        ax.set_title(e.event_id.replace("_", " "), loc="left")
        ax.tick_params(axis="x", labelrotation=30, labelsize=7)
    for ax in axes.flat[n:]:
        ax.axis("off")
    fig.suptitle("Hot pixels on the furnace mask per clear Sentinel-2 pass; grey = outage window", x=0.01, ha="left", color=TEXT)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(os.path.join(FIG, "events_scenes.png"), dpi=110)
    plt.close(fig)


def kennecott():
    p = os.path.join(HERE, "results", "kennecott_quarterly_vs_index.csv")
    if not os.path.exists(p):
        return
    k = pd.read_csv(p)
    fig, ax = plt.subplots(figsize=(6, 4))
    for (lab, d), c in zip([("2017Q1-2024Q4 (development)", k[k.quarter < "2025Q1"]), ("2025Q1-2026Q2 (holdout)", k[k.quarter >= "2025Q1"])], C):
        ax.scatter(d.active_share, d.conc_smelted_kt, s=28, color=c, label=lab, edgecolor=BG, linewidth=1)
        for r in d.itertuples():
            if r.conc_smelted_kt < 110:
                ax.annotate(r.quarter, (r.active_share, r.conc_smelted_kt), xytext=(4, 2), textcoords="offset points", fontsize=7, color=TEXT)
    ax.set_xlabel("share of clear Sentinel-2 passes with a furnace-mask hot pixel")
    ax.set_ylabel("concentrate smelted, kt per quarter (Rio Tinto)")
    ax.set_title("Kennecott: satellite activity vs reported smelter throughput", loc="left")
    ax.legend(frameon=False, loc="lower right")
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "kennecott_quarterly.png"), dpi=130); plt.close(fig)


def china():
    p = os.path.join(HERE, "results", "china_index_vs_nbs.csv")
    if not os.path.exists(p):
        return
    c = pd.read_csv(p).dropna(subset=["yoy_pts", "yoy_pct"])
    fig, ax = plt.subplots(figsize=(6, 4))
    for (lab, d), col in zip([("to 2024-12 (development)", c[c.month < "2025-01"]), ("2025-01 on (holdout)", c[c.month >= "2025-01"])], C):
        ax.scatter(d.yoy_pts * 100, d.yoy_pct, s=26, color=col, label=lab, edgecolor=BG, linewidth=1)
    ax.set_xlabel("China smelter index, YoY change of 3-month mean (percentage points of active share)")
    ax.set_ylabel("NBS refined copper output, YoY %")
    ax.set_title("China: satellite smelter index vs official refined output", loc="left")
    ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "china_vs_nbs.png"), dpi=130); plt.close(fig)


if __name__ == "__main__":
    os.makedirs(FIG, exist_ok=True)
    small_multiples(); events_scenes(); kennecott(); china()
    print("ok")
