"""Render figures to ../figures (one axis each, recessive grid, fixed series colour order).

fig1_cocoa_price.png          ICE NY cocoa front month (CC=F), log scale
fig2_icco_vintages_2023_24.png ICCO world / CIV / GHA estimates of 2023/24 by release date (% of latest)
fig3_maincrop_vs_dry.png       Pre-registered test a1: main-crop arrivals y/y vs DRY at 15 Oct
fig4_weather_2021_2026.png     Monthly composites and components, 2021-10 .. 2026-09
fig5_holdout_strategy.png      Test b holdout: cumulative net log return of B1 / B2 sign rules and buy-and-hold
fig6_cocoa_mask.png            Cocoa-area weights on the 0.05° grid
Usage: python plot.py
"""
import os
import numpy as np, pandas as pd
from plotstyle import setup, C, TEXT, MUTED, GRID

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data"); RES = os.path.join(HERE, "..", "results"); FIG = os.path.join(HERE, "..", "figures")
plt = setup(); os.makedirs(FIG, exist_ok=True)


def save(fig, name):
    fig.tight_layout(); fig.savefig(f"{FIG}/{name}", dpi=150); plt.close(fig)


def label_end(ax, x, y, txt, color):
    ax.annotate(txt, (x, y), xytext=(4, 0), textcoords="offset points", va="center", fontsize=8, color=TEXT)
    ax.plot([x], [y], "o", ms=4, color=color)


def fig1():
    p = pd.read_csv(f"{DATA}/prices_cc.csv", parse_dates=["date"])
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.axvspan(pd.Timestamp("2023-10-01"), pd.Timestamp("2024-09-30"), color=GRID, alpha=0.6, lw=0)
    ax.axvline(pd.Timestamp("2022-10-01"), color=MUTED, lw=0.8, ls="--")
    ax.plot(p.date, p.close, color=C[0], lw=1.2)
    ax.set_yscale("log"); ax.set_yticks([1000, 2000, 4000, 8000, 12000]); ax.set_yticklabels(["1,000", "2,000", "4,000", "8,000", "12,000"])
    ax.text(pd.Timestamp("2022-11-01"), 1000, "holdout →", color=TEXT, fontsize=8)
    ax.text(pd.Timestamp("2023-10-15"), 14000, "2023/24", color=TEXT, fontsize=8)
    ax.set_title("ICE NY cocoa, front-month continuous (CC=F), US$/t, log scale")
    save(fig, "fig1_cocoa_price.png")


def fig2():
    w = pd.read_csv(f"{DATA}/icco_world_vintages.csv", parse_dates=["pub_date"])
    c = pd.read_csv(f"{DATA}/icco_country_vintages.csv", parse_dates=["pub_date"])
    s = "2023/24"
    ww = w[(w.season == s)].dropna(subset=["world_production_kt"]); cc = c[c.season == s].dropna(subset=["civ_kt"])
    fig, ax = plt.subplots(figsize=(7, 3.6))
    series = [("World", ww.pub_date, ww.world_production_kt), ("Côte d'Ivoire", cc.pub_date, cc.civ_kt), ("Ghana", cc.pub_date, cc.gha_kt)]
    for i, (lab, x, y) in enumerate(series):
        rel = 100 * (y.values / y.values[-1] - 1)
        ax.plot(x, rel, color=C[i], marker="o", ms=4, lw=2, label=f"{lab} (latest {y.values[-1]:,.0f} kt)")
    ax.axhline(0, color=MUTED, lw=0.8)
    ax.set_ylabel("% above latest estimate"); ax.legend(loc="upper right")
    ax.set_title("ICCO estimates of 2023/24 production, by release date")
    save(fig, "fig2_icco_vintages_2023_24.png")


def fig3():
    T = pd.read_csv(f"{RES}/test_a1_sample.csv").dropna(subset=["MC_yoy", "DRY_oct"])
    fig, ax = plt.subplots(figsize=(6.5, 4))
    for hold, col, lab in [(False, C[0], "training seasons"), (True, C[1], "holdout seasons")]:
        d = T[T.holdout == hold]
        ax.scatter(d.DRY_oct, d.MC_yoy, s=40, color=col, label=lab, edgecolor="#fcfcfb", linewidth=1.5, zorder=3)
        for r in d.itertuples():
            off = (5, -10) if r.season == "2015/16" else (5, 3)
            ax.annotate(r.season, (r.DRY_oct, r.MC_yoy), xytext=off, textcoords="offset points", fontsize=7.5, color=TEXT)
    ax.axhline(0, color=MUTED, lw=0.8); ax.axvline(0, color=MUTED, lw=0.8)
    ax.set_xlabel("DRY composite at 15 Oct (z; higher = wetter, cooler, greener)")
    ax.set_ylabel("CIV main-crop arrivals y/y at ~31 Mar (%)")
    ax.legend(loc="lower left"); ax.set_title("Test a1: start-of-season weather vs main-crop arrivals")
    save(fig, "fig3_maincrop_vs_dry.png")


def fig4():
    F = pd.read_csv(f"{DATA}/features_monthly.csv", parse_dates=["as_of"])
    F = F[(F.zone == "ALL") & (F.as_of >= "2021-10-01")]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.axvspan(pd.Timestamp("2023-10-01"), pd.Timestamp("2024-09-30"), color=GRID, alpha=0.6, lw=0)
    for i, (c, lab) in enumerate([("DRY", "DRY composite"), ("rain_3m_z", "rain 3m"), ("soil_3m_z", "root-zone soil wetness 3m"), ("evi_3m_z", "EVI 3m")]):
        ax.plot(F.as_of, F[c], color=C[i], lw=1.6, label=lab)
    ax.axhline(0, color=MUTED, lw=0.8)
    ax.set_ylim(-5, 6); ax.set_ylabel("z-score vs 2003–2021")
    ax.legend(ncol=4, loc="upper left", fontsize=7.5)
    ax.text(pd.Timestamp("2023-10-15"), -4.6, "2023/24 season", fontsize=8, color=TEXT)
    ax.set_title("Cocoa-belt weather and vegetation as known at each month end (CIV + Ghana)")
    save(fig, "fig4_weather_2021_2026.png")


def fig5():
    s = pd.read_csv(f"{RES}/test_b_holdout_positions.csv", parse_dates=["t"])
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    x = s.t + pd.offsets.MonthEnd(1)
    for i, (col, lab) in enumerate([("net_B1", "B1 rule (momentum + arrivals)"), ("net_B2", "B2 rule (+ weather)"), ("r1", "buy and hold")]):
        cum = 100 * s[col].cumsum()
        ax.plot(x, cum, color=C[i], lw=2, label=lab)
        label_end(ax, x.values[-1], cum.values[-1], f"{cum.values[-1]:+.0f}", C[i])
    ax.axhline(0, color=MUTED, lw=0.8); ax.axvspan(pd.Timestamp("2023-10-01"), pd.Timestamp("2024-09-30"), color=GRID, alpha=0.6, lw=0)
    ax.set_ylabel("cumulative net log return (%)"); ax.legend(loc="upper left")
    ax.set_title("Test b holdout (Oct 2022–Sep 2026): monthly sign rules, 15 bp per unit traded")
    save(fig, "fig5_holdout_strategy.png")


def fig6():
    m = pd.read_csv(f"{DATA}/mask_grid.csv")
    fig, ax = plt.subplots(figsize=(7, 4.2))
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("b", ["#e3eefb", "#2a78d6", "#123a6b"])
    sc = ax.scatter(m.lon, m.lat, c=m.w_ha, s=2.2, marker="s", cmap=cmap, vmax=np.percentile(m.w_ha, 98), linewidths=0)
    cb = fig.colorbar(sc, ax=ax, shrink=0.8); cb.set_label("cocoa ha per 0.05° cell", color=TEXT); cb.outline.set_visible(False)
    ax.axvline(-5.5, color=MUTED, lw=0.8, ls="--"); ax.text(-8.5, 9.0, "CIV_W", fontsize=8); ax.text(-5.3, 9.0, "CIV_E", fontsize=8); ax.text(-2.0, 9.0, "GHA", fontsize=8)
    ax.set_aspect("equal"); ax.set_xlabel("longitude"); ax.set_ylabel("latitude")
    ax.set_title("Cocoa-area weights per 0.05° cell (Kalischek et al. 2023 via Trase)")
    save(fig, "fig6_cocoa_mask.png")


if __name__ == "__main__":
    for f in (fig1, fig2, fig3, fig4, fig5, fig6):
        f()
    print("figures ->", FIG)
