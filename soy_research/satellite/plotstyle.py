"""Shared matplotlib style: one axis, recessive grid, fixed series colour order."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
TEXT, BG, GRID, MUTED = "#52514e", "#fcfcfb", "#e6e5e1", "#a3a29d"


def setup():
    plt.rcParams.update({
        "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
        "text.color": TEXT, "axes.labelcolor": TEXT, "xtick.color": TEXT, "ytick.color": TEXT,
        "axes.edgecolor": GRID, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
        "axes.spines.top": False, "axes.spines.right": False, "axes.titlelocation": "left",
        "axes.titlesize": 11, "font.size": 9, "lines.linewidth": 2, "legend.frameon": False,
        "axes.prop_cycle": matplotlib.cycler(color=C),
    })
    return plt
