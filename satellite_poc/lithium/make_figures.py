"""Figures for the lithium section (one y-axis each, recessive grid, fixed series colours).

Usage:
    python make_figures.py RESULTS_DIR FIG_DIR [TP_S2.npz GB_S2.npz]
The two Sentinel-2 stacks (from s2bands.py) are optional and only used for the zone maps.
"""
import json
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
TXT, BG, GRID = "#52514e", "#fcfcfb", "#e6e5e1"
plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
    "text.color": TXT, "axes.labelcolor": TXT, "xtick.color": TXT, "ytick.color": TXT,
    "axes.edgecolor": GRID, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "font.size": 9.5, "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "lines.linewidth": 2, "legend.frameon": False})


def label_end(ax, x, y, text, color):
    ax.annotate(text, (x, y), xytext=(4, 0), textcoords="offset points", va="center", color=TXT, fontsize=8.5)
    ax.plot([x], [y], "o", ms=4, color=color)


def events(ax, items, ymax):
    for d, t in items:
        ax.axvline(pd.Timestamp(d), color="#b9b8b3", lw=0.8, ls=(0, (3, 3)), zorder=0)
        ax.text(pd.Timestamp(d), ymax, " " + t, rotation=90, va="top", ha="left", fontsize=7.5, color=TXT)


def thacker_footprint(R, F):
    fp = pd.read_csv(f"{R}/thacker_footprint_seasonal.csv", index_col=0)
    fp = fp[fp["threshold"] <= 0.45]
    fp.index = pd.PeriodIndex(fp.index, freq="M").to_timestamp() + pd.Timedelta(days=14)
    fig, ax = plt.subplots(figsize=(9, 4.6))
    for i, (col, name) in enumerate([("plant_km2", "plant site"), ("east_km2", "east (ponds, laydown)"),
                                     ("west_pit_road_km2", "west (haul road, pit area)")]):
        s = fp[col].clip(lower=0)
        ax.plot(s.index, s.values, color=C[i], marker="o", ms=3)
        label_end(ax, s.index[-1], s.values[-1], name, C[i])
    events(ax, [("2023-03-02", "construction starts"), ("2023-06-15", "earthworks start"),
                ("2024-03-15", "capex cut until DOE loan"), ("2025-04-01", "FID"),
                ("2025-11-13", "first steel (reported)")], 2.6)
    ax.set_ylim(-0.1, 2.7)
    ax.set_xlim(pd.Timestamp("2019-01-01"), pd.Timestamp("2027-06-01"))
    ax.set_ylabel("disturbed ground, km²")
    ax.set_title("Thacker Pass: Sentinel-2 disturbed area by zone (snow-free months)")
    fig.text(0.01, 0.01, "Change vs same-season 2018-21 baseline, above the 99.5th percentile of control ground. "
             "Dec-Feb mostly unusable (snow).", fontsize=7.5)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(f"{F}/thacker_footprint.png", dpi=150)


def thacker_structures(R, F):
    st = pd.read_csv(f"{R}/thacker_s1_structures.csv", index_col=0, parse_dates=True)
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.plot(st.index, st["zone_bright_ha"], color=C[0], lw=0.8, alpha=0.35)
    ax.plot(st.index, st["bright_ha_smooth"], color=C[0])
    label_end(ax, st.index[-1], st["bright_ha_smooth"].iloc[-1], "plant zone, 5-pass median", C[0])
    events(ax, [("2023-03-02", "construction starts"), ("2025-05-15", "concrete started (reported)"),
                ("2025-11-13", "first steel (reported)"), ("2026-08-13", ">85% steel delivered")], 12)
    ax.set_ylim(-1, 18)
    ax.set_xlim(pd.Timestamp("2019-01-01"), pd.Timestamp("2027-06-01"))
    ax.set_ylabel("bright radar structures, hectares")
    ax.set_title("Thacker Pass: Sentinel-1 bright-structure area in the plant zone")
    fig.text(0.01, 0.01, "VV backscatter above the 99.9th percentile of pre-2023 control pixels; "
             "expected false positives subtracted. Faint line = single passes.", fontsize=7.5)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(f"{F}/thacker_structures.png", dpi=150)


def greenbushes(R, F):
    q = pd.read_csv(f"{R}/greenbushes_quarterly.csv", index_col=0, parse_dates=["quarter_end"])
    z = lambda s: (s - s.mean()) / s.std()
    fig, ax = plt.subplots(figsize=(9, 4.4))
    series = [("total_material_Mbcm", "material mined (IGO)", C[0], "-"),
              ("pit", "pit index, frozen method (B1)", C[1], "-"),
              ("pit_minus_plant", "pit minus plant (post hoc)", C[2], "--")]
    q["pit_minus_plant"] = q["pit"] - q["plant"]
    for col, name, c, ls in series:
        s = z(q[col])
        ax.plot(q["quarter_end"], s, color=c, ls=ls, marker="o", ms=3.5)
        label_end(ax, q["quarter_end"].iloc[-1], s.iloc[-1], name, c)
    ax.axvspan(pd.Timestamp("2024-07-01"), pd.Timestamp("2026-07-01"), color="#efeeea", zorder=0)
    ax.text(pd.Timestamp("2024-07-15"), 2.45, "B2 holdout quarters", fontsize=7.5)
    ax.set_xlim(pd.Timestamp("2021-07-01"), pd.Timestamp("2027-09-01"))
    ax.set_ylim(-2.3, 2.7)
    ax.set_ylabel("standard deviations from own mean")
    ax.set_title("Greenbushes: quarterly material mined vs Sentinel-2 activity index")
    r = json.load(open(f"{R}/greenbushes_results.json"))["B1_frozen"]["pit"]
    fig.text(0.01, 0.01, f"Frozen pit index vs material mined: r = {r['r']:+.2f} (pre-registered pass: r >= 0.5), "
             f"quarter-on-quarter r = {r['r_diff']:+.2f}. Each series standardised to compare shapes.", fontsize=7.5)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(f"{F}/greenbushes_index_vs_material.png", dpi=150)


def umbra_thacker(R, F):
    u = pd.read_csv(f"{R}/umbra_thacker_plant_bright.csv", parse_dates=["date"])
    fig, ax = plt.subplots(figsize=(8, 4))
    for i, ((o, l), g) in enumerate(u.groupby(["orbit", "look"])):
        ax.plot(g["date"], g["bright_excess_pct"], "o", ms=5, color=C[i], label=f"{o}, {l}-looking")
    ax.axhline(0, color="#b9b8b3", lw=0.8)
    ax.legend(loc="upper right", fontsize=8)
    ax.set_ylabel("plant pixels above control p95, minus 5%")
    ax.set_title("Thacker Pass: Umbra 2025 bright-pixel excess in the plant zone")
    fig.tight_layout()
    fig.savefig(f"{F}/umbra_thacker_bright.png", dpi=150)


def zone_map(stack, zones, title, out, gain):
    d = np.load(stack)
    r, dates = d["refl"], pd.to_datetime(d["dates"])
    bad = (r[:, 0] == 0).mean((1, 2))
    i = int(np.argmin(np.where(bad < 0.01, -dates.values.astype("int64"), np.inf)))
    rgb = np.clip((r[i, [2, 1, 0]].astype(float).transpose(1, 2, 0) / gain) ** 0.8, 0, 1)
    fig, ax = plt.subplots(figsize=(7, 7 * rgb.shape[0] / rgb.shape[1] + 0.4))
    ax.imshow(rgb)
    ax.grid(False)
    for k, (name, (x0, x1, y0, y1)) in enumerate(zones.items()):
        ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec=C[k % 4], lw=1.6))
        ax.text(x0 + 2, y0 + 8, name, color="white", fontsize=8, fontweight="bold")
    ax.set_title(f"{title} ({dates[i].date()}, 20 m pixels)")
    fig.tight_layout()
    fig.savefig(out, dpi=130)


def main():
    R, F = sys.argv[1], sys.argv[2]
    thacker_footprint(R, F)
    thacker_structures(R, F)
    greenbushes(R, F)
    umbra_thacker(R, F)
    if len(sys.argv) > 4:
        zone_map(sys.argv[3], {"plant": [310, 410, 155, 250], "east": [411, 490, 165, 255],
                               "west (road, pit)": [100, 309, 100, 250]},
                 "Thacker Pass zones", f"{F}/thacker_zones.png", 3500)
        zone_map(sys.argv[4], {"pit": [195, 268, 160, 300], "dumps": [262, 312, 140, 330],
                               "plant": [150, 194, 190, 250], "tailings": [130, 235, 251, 400]},
                 "Greenbushes zones", f"{F}/greenbushes_zones.png", 2500)


if __name__ == "__main__":
    main()
