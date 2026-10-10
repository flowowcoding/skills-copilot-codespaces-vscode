"""Figures for the Chilean copper test.

Usage:
    python plots.py RESULTS_DIR FIG_DIR [--variant R]

Writes
  FIG_DIR/chile_mines_index_vs_production.png  small multiples, quarterly index vs copper output
  FIG_DIR/chile_aggregate_yoy.png               aggregate YoY index vs YoY production
  FIG_DIR/chile_events.png                      monthly index around known events
Both series in a panel are standardised (z-scores over 2019-2024) so they share one axis.
"""
import argparse
import json
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

BLUE, ORANGE, GREEN, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, INK2, BG, GRID, AX = "#0b0b0b", "#52514e", "#fcfcfb", "#e8e7e3", "#c3c2b7"
HOLD0 = pd.Timestamp("2025-01-01")
plt.rcParams.update({"font.size": 8, "axes.titlesize": 9, "text.color": INK, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "figure.facecolor": BG, "axes.facecolor": BG})


def style(ax):
    for sp in ["top", "right"]:
        ax.spines[sp].set_visible(False)
    for sp in ["left", "bottom"]:
        ax.spines[sp].set_color(AX)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def z(s, ref=("2019-01-01", "2024-12-31")):
    r = s[(s.index >= ref[0]) & (s.index <= ref[1])]
    return (s - r.mean()) / r.std()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results"); ap.add_argument("figdir"); ap.add_argument("--variant", default="R")
    a = ap.parse_args()
    here = Path(__file__).parent
    import evaluate
    iq, im, cfg = evaluate.load_index(a.results, a.variant)
    cfg = {k: v for k, v in cfg.items() if k in iq}
    pq, pm = evaluate.load_production(cfg)
    ts = lambda s: s.set_axis(s.index.to_timestamp(how="start") + pd.Timedelta(days=45))

    # 1. small multiples: quarterly level, both z-scored
    names = list(cfg)
    nc = 4
    nr = int(np.ceil(len(names) / nc))
    fig, axes = plt.subplots(nr, nc, figsize=(11, 2.0 * nr + 0.6), dpi=150, sharex=True)
    for ax, k in zip(axes.flat, names):
        i = ts(iq[k].dropna()); p = ts(pq[k].dropna())
        p = p[p.index >= "2019-01-01"]
        ax.axvspan(HOLD0, pd.Timestamp("2026-10-01"), color="#f1f0ec", lw=0)
        ax.plot(z(p).index, z(p), color=ORANGE, lw=2, label="copper produced (Cochilco)")
        ax.plot(z(i).index, z(i), color=BLUE, lw=2, label=f"pit activity index ({a.variant})")
        ax.set_title(k.replace("_", " ").title(), loc="left", color=INK)
        ax.set_ylim(-4, 4)
        style(ax)
    for ax in axes.flat[len(names):]:
        ax.axis("off")
    h, l = axes.flat[0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper right", frameon=False, ncol=2, fontsize=8)
    fig.suptitle("Quarterly pit activity vs copper output, 15 Chilean mines (z-scores over 2019-2024; shaded = holdout)",
                 x=0.01, ha="left", fontsize=10, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(Path(a.figdir) / "chile_mines_index_vs_production.png")

    # 2. aggregate YoY
    s = pd.read_csv(Path(a.results) / f"eval_{a.variant}_all_aggregate_series.csv", index_col=0)
    s.index = pd.PeriodIndex(s.index, freq="Q")
    s = ts(s)
    fig, ax = plt.subplots(figsize=(9, 3.6), dpi=150)
    ax.axvspan(HOLD0, pd.Timestamp("2026-10-01"), color="#f1f0ec", lw=0)
    ax.text(HOLD0 + pd.Timedelta(days=20), 3.1, "holdout", color=INK2, fontsize=8)
    ax.axhline(0, color=AX, lw=1)
    ax.plot(s.index, z(s.covered_prod_yoy_log), color=ORANGE, lw=2, marker="o", ms=4, label="copper output of the 15 mines, YoY")
    ax.plot(s.index, z(s.agg_index_yoy), color=BLUE, lw=2, marker="o", ms=4, label="aggregate pit activity, YoY")
    ax.set_ylim(-3.5, 3.5)
    ax.set_ylabel("standardised YoY change")
    ax.legend(frameon=False, loc="lower left")
    ax.set_title("Aggregate pit activity vs output, year-on-year, quarterly", loc="left", color=INK)
    style(ax)
    fig.tight_layout()
    fig.savefig(Path(a.figdir) / "chile_aggregate_yoy.png")


if __name__ == "__main__":
    main()
