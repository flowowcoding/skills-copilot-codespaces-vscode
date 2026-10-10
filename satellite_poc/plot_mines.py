"""Small-multiple chart of the activity index at the three halted mines -> figures/mines_activity.png"""
import pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

MINES = [("cobre", "Cobre Panamá (First Quantum)", "2023-11-24", "production halted"),
         ("eagle", "Eagle, Yukon (Victoria Gold)", "2024-06-24", "heap-leach failure, halted"),
         ("copler", "Çöpler, Turkey (SSR Mining)", "2024-02-13", "heap-leach failure, halted")]
fig, axes = plt.subplots(3, 1, figsize=(9, 8), dpi=150, sharex=True, sharey=True)
fig.patch.set_facecolor("#fcfcfb")
for ax, (k, title, halt, lab) in zip(axes, MINES):
    s = pd.read_csv(f"results/{k}_activity.csv", index_col=0, parse_dates=True).activity * 100
    h = pd.Timestamp(halt)
    ax.set_facecolor("#fcfcfb")
    ax.scatter(s.index, s, s=8, color="#2a78d6", alpha=.3, linewidths=0)
    ax.plot(s.rolling(5, center=True).median(), color="#2a78d6", lw=2)
    ax.axhline(0, color="#c3c2b7", lw=1)
    ax.axvline(h, color="#52514e", lw=1, ls="--")
    ax.text(h + pd.Timedelta(days=12), 15, lab, fontsize=8, color="#52514e", va="top")
    ax.set_title(title, loc="left", fontsize=9.5, color="#0b0b0b")
    for sp in ["top", "right"]: ax.spines[sp].set_visible(False)
    for sp in ["left", "bottom"]: ax.spines[sp].set_color("#c3c2b7")
    ax.tick_params(colors="#52514e", labelsize=8)
    ax.grid(axis="y", color="#e8e7e3", lw=.8); ax.set_axisbelow(True)
    ax.set_ylim(-21, 17)
axes[1].set_ylabel("Activity index (pts, mine minus surroundings)", color="#52514e", fontsize=9)
fig.suptitle("Radar mine activity index, 2022–2026 (dots = passes, line = 5-pass median; pixels picked on 2021 data)",
             x=0.01, ha="left", fontsize=10, color="#0b0b0b")
fig.tight_layout(); fig.savefig("figures/mines_activity.png")
