"""Result figures (run after `evaluate.py --mode final`).

  fig_revision_gap.png  : satellite gap at each GoI first estimate vs the later revision to final
  fig_shocks_tur.png    : tur satellite estimate path vs official vintages, shock seasons (% of final)
  fig_shocks_gram.png   : same for gram
  fig_sugar_pnl.png     : cumulative net P&L of the incremental SB=F trades, dev and holdout

Usage: python plot_results.py [--signal ../signal --results ../results --data ../data --out ../figures]
"""
import argparse
import numpy as np, pandas as pd
from plotstyle import setup, C, TEXT, MUTED


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--signal", default="../signal"); ap.add_argument("--results", default="../results")
    ap.add_argument("--data", default="../data"); ap.add_argument("--out", default="../figures")
    a = ap.parse_args()
    plt = setup()
    # 1 revision gap
    r = pd.read_csv(f"{a.results}/revision_test_rows_final.csv")
    r = r[r["first"]]
    fig, ax = plt.subplots(figsize=(6.8, 5.8))
    for k, crop in enumerate(["gram", "tur", "sugarcane"]):
        d = r[r.crop == crop]
        for per, fc in [("dev", "none"), ("holdout", C[k])]:
            e = d[d.period == per]
            ax.scatter(100 * e.gap, 100 * e.y, s=40, edgecolor=C[k], facecolor=fc, lw=1.3,
                       label=f"{crop} ({'holdout' if per == 'holdout' else 'development'})")
            for _, q in e.iterrows():
                ax.annotate(q.season[2:], (100 * q.gap, 100 * q.y), fontsize=6.5, color=MUTED, xytext=(3, 3), textcoords="offset points")
    ax.axhline(0, color=TEXT, lw=0.7); ax.axvline(0, color=TEXT, lw=0.7)
    ax.set_xlabel("satellite − first official estimate, day before release (%)")
    ax.set_ylabel("final − first official estimate (%)")
    ax.set_title("Does the satellite gap predict the official revision?", color=TEXT)
    ax.legend(fontsize=7, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.13)); fig.tight_layout(); fig.savefig(f"{a.out}/fig_revision_gap.png", dpi=130)
    # 2/3 shock paths
    s = pd.read_csv(f"{a.signal}/india_signal_v1.csv", parse_dates=["asof"])
    v = pd.read_csv(f"{a.data}/ae_vintages.csv", parse_dates=["release_date"])
    fin = v[v.stage == "FINAL"].set_index(["crop", "season"]).value
    for crop, seasons in [("tur", ["2014-15", "2015-16", "2018-19", "2023-24"]), ("gram", ["2014-15", "2021-22", "2022-23", "2023-24"])]:
        fig, ax = plt.subplots(figsize=(7.4, 5))
        for k, se in enumerate(seasons):
            f = fin.get((crop, se), np.nan)
            d = s[(s.crop == crop) & (s.season == se) & (s.asof_kind == "month_end")].sort_values("asof")
            Y = int(se[:4]) + 1
            x0 = pd.Timestamp(Y - 1, 7, 1)
            xs = (d["asof"] - x0).dt.days / 30.44
            ax.plot(xs, 100 * (d.sat_pred / f - 1), "-o", color=C[k], ms=3.5, label=f"{se} satellite")
            o = v[(v.crop == crop) & (v.season == se) & v.stage.str.startswith("AE")]
            if len(o):
                ax.plot((o.release_date - x0).dt.days / 30.44, 100 * (o.value / f - 1), "s", color=C[k], ms=6, mfc="none", mew=1.4,
                        label=f"{se} official AE")
        ax.axhline(0, color=TEXT, lw=0.7)
        ticks = np.arange(0, 15, 1); labs = ["Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep"]
        ax.set_xticks(ticks); ax.set_xticklabels(labs)
        ax.set_ylabel("estimate / final − 1 (%)"); ax.set_xlabel("as-of date (ticks = 1st of month; month-end points sit just left of the next tick)")
        ax.set_title(f"{crop}: satellite estimate path vs official estimates (shock seasons)", color=TEXT)
        ax.legend(fontsize=7, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.1)); fig.tight_layout(); fig.savefig(f"{a.out}/fig_shocks_{crop}.png", dpi=130)
    # 4 sugar pnl
    p = pd.read_csv(f"{a.results}/price_test_rows_final.csv", parse_dates=["asof"])
    p = p[p.crop == "sugarcane"]
    fig, ax = plt.subplots(figsize=(7, 4))
    for k, h in enumerate([1, 2, 3]):
        d = p[p.h == h].sort_values("asof")
        ax.plot(d["asof"], 100 * d.pnl.cumsum(), color=C[k], label=f"h = {h} month{'s' if h > 1 else ''}")
    ax.axvline(pd.Timestamp("2023-07-01"), color=MUTED, lw=1, ls="--"); ax.text(pd.Timestamp("2023-08-01"), ax.get_ylim()[1] * 0.9, "holdout →", color=MUTED, fontsize=8)
    ax.set_ylabel("cumulative net log return (%)")
    ax.set_title("SB=F: trading the satellite increment (full − baseline forecast), net of 0.15%", color=TEXT)
    ax.legend(fontsize=8); fig.tight_layout(); fig.savefig(f"{a.out}/fig_sugar_pnl.png", dpi=130)


if __name__ == "__main__":
    main()
