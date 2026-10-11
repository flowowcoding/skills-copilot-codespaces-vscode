"""Figures for the weather-events track (one axis per figure, shared plotstyle).

* car_<MARKET>.png        mean abnormal CAR around the first hurricane-threat advisory (day 0),
                          hits vs misses; dashed lines at day 0 and the median landfall day of hits
* event_<storm>_<MKT>.png price path (rebased) for selected storms, with dashed lines at first-threat
                          day and landfall / closest-approach day
* overlap_<storm>.png     point-in-time threat series: share of region in the 3-day cone and GEFS
                          member share within 100 km, with the same dashed lines
* rules.png               pre-registered rule net returns, design vs holdout, by market

Usage: python plot_results.py --data ../data --results ../results --out ../figures \
          --events Irma:2017:OJ Ian:2022:OJ Milton:2024:OJ Katrina:2005:NG Ida:2021:NG Laura:2020:CL
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plotstyle import C, MUTED, TEXT, setup  # noqa: E402

LABEL = {"OJ": "orange juice", "NG": "natural gas", "CL": "WTI crude", "RB": "RBOB gasoline",
         "CT": "cotton", "ZR": "rough rice"}


def vline(ax, x, label, side="left"):
    """Dashed event line; label to the right (side='left' anchor) or to the left of the line."""
    ax.axvline(x, color=TEXT, ls="--", lw=1)
    txt = " " + label + " " if side == "left" else label + " "
    ax.text(x, 1.0, txt, transform=ax.get_xaxis_transform(), va="top", ha=side,
            fontsize=8, color=TEXT)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--events", nargs="*", default=[])
    a = ap.parse_args()
    plt = setup()
    ev = pd.read_csv(os.path.join(a.results, "events.csv"), parse_dates=["day0", "closest_day", "exitE1"])
    cp = pd.read_csv(os.path.join(a.results, "car_paths.csv"))
    ov = pd.read_csv(os.path.join(a.data, "forecast_overlap.csv"), parse_dates=["init", "avail_utc"])

    # --- CAR paths, all years pooled (sample-specific numbers are in car_paths.csv)
    for tk in ["OJ", "NG", "CL", "RB", "CT", "ZR"]:
        e = ev[ev.market == tk]
        if e.empty:
            continue
        fig, ax = plt.subplots(figsize=(6.4, 3.8))
        for j, hit in enumerate([True, False]):
            g = e[e.hit_pit == hit]
            if g.empty:
                continue
            # recompute pooled mean across samples, weighted by n
            c = cp[(cp.market == tk) & (cp.hit == hit) & (cp.anchor == "day0")]
            w = c.groupby("k").apply(lambda x: np.average(x["mean"], weights=x.n), include_groups=False)
            ax.plot(w.index, w.values * 100, color=C[j],
                    label=f"{'hits' if hit else 'misses'} (n={len(g)})")
        ax.axhline(0, color=MUTED, lw=0.8)
        vline(ax, 0, "first threat", "right")
        hits = e[e.hit_pit]
        if len(hits):
            lag = int(np.median([np.busday_count(d0.date(), dl.date()) for d0, dl in zip(hits.day0, hits.closest_day)]))
            vline(ax, lag, "landfall (median)")
        ax.set_xlabel("trading days from first hurricane-threat advisory")
        ax.set_ylabel("mean abnormal return, %")
        ax.set_title(f"{LABEL[tk]} ({tk}=F) around NHC 3-day cone threat to the {e.region.iloc[0]} region")
        ax.legend(loc="upper left")
        fig.tight_layout()
        fig.savefig(os.path.join(a.out, f"car_{tk}.png"), dpi=130)
        plt.close(fig)

    # --- single-event price paths and overlap series
    for item in a.events:
        name, yr, tk = item.split(":")
        e = ev[(ev.name == name) & (ev.year == int(yr)) & (ev.market == tk)]
        if e.empty:
            print("no event", item)
            continue
        e = e.iloc[0]
        px = pd.read_csv(os.path.join(a.data, "prices", f"{tk}.csv"), parse_dates=["date"]).set_index("date").close
        i0 = px.index.get_loc(e.day0)
        iL = px.index.get_loc(e.closest_day)
        seg = px.iloc[max(0, i0 - 15): i0 + 26]
        x = np.arange(len(seg)) - min(15, i0)
        fig, ax = plt.subplots(figsize=(6.4, 3.8))
        ax.plot(x, seg.values / seg.iloc[min(15, i0)] * 100, color=C[0])
        vline(ax, 0, f"first threat {e.day0:%d %b}", "right")
        vline(ax, iL - i0, f"landfall {e.closest_day:%d %b}" if e.hit_pit else f"closest {e.closest_day:%d %b}")
        ax.set_xlabel("trading days from first hurricane-threat advisory")
        ax.set_ylabel("front-month price, day 0 = 100")
        ax.set_title(f"{name} {yr}: {LABEL[tk]} ({tk}=F, unadjusted continuous)")
        fig.tight_layout()
        fig.savefig(os.path.join(a.out, f"event_{name.lower()}{yr}_{tk}.png"), dpi=130)
        plt.close(fig)

        o = ov[(ov.storm_id == e.storm_id) & (ov.region == e.region)].sort_values("init")
        fig, ax = plt.subplots(figsize=(6.4, 3.8))
        ax.plot(o.avail_utc, o.cone72_frac * 100, color=C[0], label="region area inside 3-day cone, %")
        ax.plot(o.avail_utc + pd.Timedelta(hours=3), o.gefs_p72 * 100, color=C[1],
                label="GEFS members within 100 km by 72 h, %")
        ax.plot(o.avail_utc, o.cone120.astype(int) * 100, color=C[2], lw=1, label="inside 5-day cone (0/100)")
        trig = pd.Timestamp(e.trigger_avail_utc)
        vline(ax, trig, "first threat", "right")
        if pd.notna(e.bt_t_closest):
            vline(ax, pd.Timestamp(e.bt_t_closest), "landfall" if e.hit_pit else "closest")
        ax.set_ylim(-3, 112)
        ax.set_ylabel("%")
        ax.set_title(f"{name} {yr}: point-in-time forecast threat to the {e.region} region")
        ax.legend(loc="center left", fontsize=7.5)
        fig.autofmt_xdate()
        fig.tight_layout()
        fig.savefig(os.path.join(a.out, f"overlap_{name.lower()}{yr}_{e.region}.png"), dpi=130)
        plt.close(fig)

    # --- rule results
    rr = pd.read_csv(os.path.join(a.results, "rule_results.csv"))
    sel = rr[rr.cell == "selected"]
    mk = list(dict.fromkeys(sel.market))
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    w = 0.38
    for j, smp in enumerate(["design", "holdout"]):
        s = sel[sel["sample"] == smp].set_index("market").reindex(mk)
        ax.bar(np.arange(len(mk)) + (j - 0.5) * w, s.net_mean, w, color=C[j],
               label=f"{smp} ({'2005-17' if smp == 'design' else '2018-26'})")
        for k, (v, n) in enumerate(zip(s.net_mean, s.n)):
            ax.text(k + (j - 0.5) * w, v + (0.1 if v >= 0 else -0.1), f"n={int(n)}", ha="center",
                    va="bottom" if v >= 0 else "top", fontsize=7, color=TEXT)
    lab = [f"{m}\n{d} {e}" for m, d, e in sel[sel["sample"] == "design"][["market", "direction", "exit"]].values]
    ax.set_xticks(range(len(mk)), lab)
    ax.axhline(0, color=MUTED, lw=0.8)
    ax.set_ylabel("mean net return per trade, %")
    ax.set_title("Design-selected rule per market: design vs holdout, after costs")
    lo, hi = ax.get_ylim()
    ax.set_ylim(lo, hi + 0.25 * (hi - lo))
    ax.legend(loc="upper left", ncol=2)
    fig.tight_layout()
    fig.savefig(os.path.join(a.out, "rules.png"), dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    main()
