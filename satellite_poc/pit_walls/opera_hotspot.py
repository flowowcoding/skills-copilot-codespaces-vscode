"""Exploratory (post-hoc, NOT pre-registered) hotspot statistic for OPERA DISP-S1 wall segments.

A sector median dilutes a movement confined to a few hundred metres of wall. Here, per epoch,
we count the share of a segment's valid points whose LOS displacement fell by more than
THRESH mm over the trailing 60 days (control-ring median removed). Reported for every year
so that the 2024 episode can be compared against ordinary years.

Usage:
  python opera_hotspot.py LONG.csv OUT.csv FIG.png [--direction DESCENDING] [--thresh 20]
"""
import argparse
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import style

SEGS = ["N", "NE", "SE", "S", "SW", "W"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("long"); ap.add_argument("out"); ap.add_argument("fig")
    ap.add_argument("--direction", default="DESCENDING"); ap.add_argument("--thresh", type=float, default=20)
    a = ap.parse_args()
    df = pd.read_csv(a.long, parse_dates=["date"]); df = df[df.direction == a.direction]
    if a.direction == "ASCENDING":
        df = df[df.frame.notna()]
    W = df.pivot_table(index="date", columns="pid", values="disp_mm").where(
        ~df.pivot_table(index="date", columns="pid", values="masked").astype(bool))
    sec = df.drop_duplicates("pid").set_index("pid").sector
    ctrl = [c for c in W.columns if sec[c] == "control"]
    rows = []
    for t in W.index:
        prev = W.index[(W.index <= t - pd.Timedelta(days=60)) & (W.index >= t - pd.Timedelta(days=84))]
        if len(prev) == 0:
            continue
        ch = W.loc[t] - W.loc[prev[-1]]
        ch = ch - ch[ctrl].median()
        r = {"date": t.date(), "from": prev[-1].date()}
        for s in SEGS:
            v = ch[[c for c in W.columns if sec[c] == s]].dropna()
            r[s + "|n"] = len(v); r[s + "|share_below"] = round((v < -a.thresh).mean(), 3) if len(v) >= 10 else np.nan
        rows.append(r)
    R = pd.DataFrame(rows); R.to_csv(a.out, index=False)
    R["date"] = pd.to_datetime(R.date)
    print(R.groupby(R.date.dt.year)[[s + "|share_below" for s in SEGS]].max().round(2))
    style.apply()
    fig, ax = plt.subplots(figsize=(8.5, 3.4))
    for s in SEGS:
        if s in ("S",):
            continue
        ax.plot(R.date, R[s + "|share_below"], color=style.MUTED, lw=0.9, marker=".", ms=2)
    ax.plot(R.date, R["S|share_below"], color=style.PRIMARY, lw=1.8, marker=".", ms=4)
    ax.text(R.date.iloc[-1], R["S|share_below"].iloc[-1], "  S wall", color=style.INK, fontsize=8, va="center")
    ax.text(pd.Timestamp("2016-10-01"), 0.95, "grey: other wall sectors", transform=ax.get_xaxis_transform(), color=style.INK, fontsize=7.5)
    style.mark(ax, pd.Timestamp("2024-07-16"), "Q2 2024 disclosure", y=0.86)
    style.mark(ax, pd.Timestamp("2021-05-31"), "Leo failure (SE)", y=0.86, ls=":")
    ax.set_ylabel(f"share of points down > {a.thresh:.0f} mm in 60 d")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_title(f"Bingham Canyon wall hotspots, OPERA DISP-S1 {a.direction.lower()} (exploratory, winters missing)")
    fig.tight_layout(); fig.savefig(a.fig, dpi=150); plt.close(fig)


if __name__ == "__main__":
    main()
