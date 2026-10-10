"""Shared matplotlib style: one axis per panel, recessive grid, fixed series
colour order, text #52514e on background #fcfcfb."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402,F401
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
TEXT = "#52514e"
BG = "#fcfcfb"
GRID = "#e4e3df"

plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
    "text.color": TEXT, "axes.labelcolor": TEXT, "xtick.color": TEXT, "ytick.color": TEXT,
    "axes.edgecolor": GRID, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.axisbelow": True, "axes.spines.top": False, "axes.spines.right": False,
    "axes.spines.left": False, "axes.titlesize": 9, "axes.titlecolor": TEXT, "axes.labelsize": 8,
    "xtick.labelsize": 7.5, "ytick.labelsize": 7.5, "legend.fontsize": 8, "font.size": 8,
    "axes.prop_cycle": matplotlib.cycler(color=C), "xtick.major.size": 0, "ytick.major.size": 0,
})


def single(w=7.5, h=3.0):
    fig, ax = plt.subplots(figsize=(w, h))
    return fig, ax


def grid(n, ncols=4, w=2.6, h=2.0, sharey=False):
    nrows = -(-n // ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(w * ncols, h * nrows), sharey=sharey, squeeze=False)
    return fig, list(axes.ravel())


def legend_top(fig, labels, colors):
    handles = [Line2D([0], [0], color=c, lw=2) for c in colors]
    fig.legend(handles, labels, loc="upper right", ncol=len(labels), frameon=False, bbox_to_anchor=(0.99, 1.0))


def save(fig, path):
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(path, dpi=150)
    plt.close(fig)
