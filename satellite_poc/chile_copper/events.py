"""Known-event checks for the Chilean pit activity index (expected directions pre-registered
in README).

Usage:
    python events.py RESULTS_DIR FIG.png [--variant R]

Needs RESULTS_DIR/<mine>_pairs.csv and, for the 2017 Escondida strike,
RESULTS_DIR/escondida_event_pairs.csv (activity_index.py in event mode on a 2016-17 stack).
Prints one line per event and writes a small-multiple figure of the pair-level index
(dots) with a 5-pair rolling median (line).
"""
import argparse
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from plots import BLUE, ORANGE, INK, INK2, style

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("results"); ap.add_argument("fig"); ap.add_argument("--variant", default="R")
a = ap.parse_args()
R = Path(a.results)
v = a.variant


def pairs(m, event=False):
    df = pd.read_csv(R / (f"{m}_event_pairs.csv" if event else f"{m}_pairs.csv"), index_col=0, parse_dates=True)
    col = "F" if event else v
    return df[col].where(df[f"n_{col}"] >= 20).dropna()


def mean(s, a0, a1):
    x = s[a0:a1]
    return x.mean(), len(x)


rows = []
esc = pairs("escondida")
for name, s, (a0, a1), (b0, b1), expect in [
    ("Escondida COVID crew cuts 2020Q2 vs 2019Q2", esc, ("2020-04-01", "2020-06-30"), ("2019-04-01", "2019-06-30"), "lower"),
    ("Spence 2024Q1 vs 2023Q1", pairs("spence"), ("2024-01-01", "2024-03-31"), ("2023-01-01", "2023-03-31"), "lower"),
    ("Escondida July 2026 storms vs July 2025 (not pre-registered)", esc, ("2026-07-01", "2026-07-31"), ("2025-07-01", "2025-07-31"), "lower"),
]:
    m1, n1 = mean(s, a0, a1); m0, n0 = mean(s, b0, b1)
    rows.append(dict(event=name, event_mean=m1, n_event=n1, reference_mean=m0, n_ref=n0, expected=expect,
                     seen="yes" if (m1 < m0) == (expect == "lower") else "no"))
if (R / "escondida_event_pairs.csv").exists():
    e = pairs("escondida", event=True)
    st = e["2017-02-09":"2017-03-24"]
    rest = e["2017-01-01":"2017-12-31"].drop(st.index)
    rows.append(dict(event="Escondida strike 9 Feb-24 Mar 2017 vs rest of 2017", event_mean=st.mean(), n_event=len(st),
                     reference_mean=rest.mean(), n_ref=len(rest), expected="lower",
                     seen="yes" if st.mean() < rest.mean() else "no"))
ann = {}
for m in ["quebrada_blanca", "chuquicamata", "los_pelambres"]:
    s = pairs(m)
    ann[m] = s.groupby(s.index.year).mean().round(1)
tab = pd.DataFrame(rows)
pd.set_option("display.width", 180)
print(tab.round(2).to_string(index=False))
print("\nAnnual mean index (pts):\n", pd.DataFrame(ann).to_string())
tab.round(3).to_csv(R / f"events_{v}.csv", index=False)
pd.DataFrame(ann).to_csv(R / f"events_{v}_annual.csv")

# figure
panels = [("escondida", "Escondida: COVID crew cuts 2020Q2; July 2026 storms", [("2020-04-01", "2020-06-30"), ("2026-07-01", "2026-07-31")]),
          ("spence", "Spence: material mined -36% YoY in 2024Q1", [("2024-01-01", "2024-03-31")]),
          ("quebrada_blanca", "Quebrada Blanca: QB2 mine ramp-up", []),
          ("chuquicamata", "Chuquicamata: pit winding down (underground since 2019)", []),
          ("los_pelambres", "Los Pelambres: drought limited the plant 2019-22", [])]
has_ev = (R / "escondida_event_pairs.csv").exists()
n = len(panels) + has_ev
fig, axes = plt.subplots(n, 1, figsize=(9, 1.9 * n + 0.5), dpi=150)
for ax, (m, title, spans) in zip(axes, panels):
    s = pairs(m)
    for a0, a1 in spans:
        ax.axvspan(pd.Timestamp(a0), pd.Timestamp(a1), color="#f6dccd", lw=0)
    ax.scatter(s.index, s, s=5, color=BLUE, alpha=0.3, linewidths=0)
    ax.plot(s.rolling(5, center=True).median(), color=BLUE, lw=2)
    ax.axhline(0, color="#c3c2b7", lw=1)
    ax.set_title(title, loc="left", color=INK)
    style(ax)
if has_ev:
    ax = axes[-1]
    e = pairs("escondida", event=True)
    ax.axvspan(pd.Timestamp("2017-02-09"), pd.Timestamp("2017-03-24"), color="#f6dccd", lw=0)
    ax.plot(e.index, e, color=BLUE, lw=2, marker="o", ms=4)
    ax.axhline(0, color="#c3c2b7", lw=1)
    ax.set_title("Escondida 2017 (calibrated on 2016 H2): strike 9 Feb - 24 Mar shaded", loc="left", color=INK)
    style(ax)
axes[len(axes) // 2].set_ylabel("pit activity index (pts)")
fig.suptitle(f"Known events: pair-level index (variant {v}); dots = image pairs, line = 5-pair median",
             x=0.01, ha="left", fontsize=10, color=INK)
fig.tight_layout(rect=(0, 0, 1, 0.97))
fig.savefig(a.fig)
