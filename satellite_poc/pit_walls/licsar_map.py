"""Exploratory (NOT pre-registered) maps of summed LiCSAR LOS increments over a window, for the
same calendar window in several years, to see where on a heap/wall any motion concentrates.

Usage:
  python licsar_map.py MAPS.npz SITE OUT.png MMDD_START MMDD_END YEAR [YEAR ...] [--minfrac 0.7]
MAPS.npz comes from licsar_ts.py --save-maps. A pixel is drawn if it was coherent in >= MINFRAC
of the pairs inside the window. Window may wrap the new year (e.g. 0901 0210 2024 = Sep 2023-Feb 2024).
"""
import sys, json, os
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
import style

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    minfrac = float(sys.argv[sys.argv.index("--minfrac") + 1]) if "--minfrac" in sys.argv else 0.7
    if "--minfrac" in sys.argv:
        args.remove(str(minfrac)) if str(minfrac) in args else None
    npz, site, out, m0, m1 = args[:5]; years = [int(y) for y in args[5:]]
    d = np.load(npz); tags = d["tags"]; maps = d["maps"]; t = d["transform"]
    d1 = pd.to_datetime([s.split("_")[0] for s in tags]); d2 = pd.to_datetime([s.split("_")[1] for s in tags])
    H, W = maps.shape[1:]
    ext = [t[2], t[2] + W * t[0], t[5] + H * t[4], t[5]]
    seg = json.load(open(os.path.join(HERE, "prereg.json")))["sites"][site]["segments"]
    style.apply()
    fig, axs = plt.subplots(1, len(years), figsize=(3.4 * len(years), 3.4)); axs = np.atleast_1d(axs)
    for ax, y in zip(axs, years):
        t1 = pd.Timestamp(f"{y}-{m1[:2]}-{m1[2:]}"); t0 = pd.Timestamp(f"{y}-{m0[:2]}-{m0[2:]}")
        if t0 > t1:
            t0 -= pd.DateOffset(years=1)
        sel = (d1 >= t0) & (d2 <= t1)
        stack = maps[sel]
        cov = np.isfinite(stack).mean(0) if sel.sum() else np.zeros((H, W))
        tot = np.where(cov >= minfrac, np.nansum(stack, 0) / np.maximum(cov, 1e-6) * 1.0, np.nan) if sel.sum() else np.full((H, W), np.nan)
        im = ax.imshow(tot, extent=ext, cmap="RdBu", vmin=-40, vmax=40, interpolation="nearest", aspect=1 / np.cos(np.radians(ext[2])))
        for name, poly in seg.items():
            ax.add_patch(Polygon(poly, fill=False, ec=style.INK, lw=1))
        ax.set_title(f"{t0:%d %b %Y} → {t1:%d %b %Y} ({sel.sum()} pairs)", fontsize=8.5, color=style.INK)
        ax.grid(False); ax.tick_params(labelsize=7)
        c0 = np.mean([p[0] for p in list(seg.values())[0]]); c1 = np.mean([p[1] for p in list(seg.values())[0]])
        ax.set_xlim(c0 - 0.04, c0 + 0.04); ax.set_ylim(c1 - 0.03, c1 + 0.03)
    cb = fig.colorbar(im, ax=axs, shrink=0.8, pad=0.02); cb.outline.set_visible(False)
    cb.set_label("summed LOS change vs control (mm)\n+ towards satellite; gaps rescaled", fontsize=8, color=style.INK)
    fig.suptitle(f"{site.capitalize()}: LiCSAR, same window in different years (outline = pre-registered segment; blank = incoherent)",
                 x=0.01, ha="left", fontsize=9.5, color=style.INK)
    fig.savefig(out, dpi=150, bbox_inches="tight"); plt.close(fig); print(out)


if __name__ == "__main__":
    main()
