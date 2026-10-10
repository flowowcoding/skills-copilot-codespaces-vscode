"""Shared matplotlib style: one axis, recessive grid, #2a78d6 primary series,
#52514e annotation text, background #fcfcfb."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PRIMARY = "#2a78d6"
INK = "#52514e"
MUTED = "#b9b8b3"
BG = "#fcfcfb"


def apply():
    plt.rcParams.update({
        "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
        "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK,
        "text.color": INK, "axes.grid": True, "grid.color": "#ebeae6", "grid.linewidth": 0.6,
        "axes.spines.top": False, "axes.spines.right": False, "font.size": 9,
        "axes.titlesize": 10, "axes.titleweight": "regular", "axes.titlelocation": "left",
        "legend.frameon": False, "lines.linewidth": 1.8,
    })


def mark(ax, x, label, y=0.98, ls="--"):
    """Vertical event marker with a small label in annotation ink."""
    ax.axvline(x, color=INK, lw=0.9, ls=ls)
    ax.text(x, y, " " + label, transform=ax.get_xaxis_transform(), color=INK, fontsize=8, va="top", ha="left")
