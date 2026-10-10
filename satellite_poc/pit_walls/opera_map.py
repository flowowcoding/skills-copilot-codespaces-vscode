"""Exploratory (NOT pre-registered) point maps of OPERA DISP-S1 LOS change over Bingham Canyon:
the same calendar window in several years, drawn over a Sentinel-2 chip, so a localised wall
movement that a sector median would dilute can be seen.

Usage:
  python opera_map.py LONG.csv BASEMAP.png BBOX OUT.png DIRECTION MMDD_START MMDD_END YEAR [YEAR ...]
  e.g. python opera_map.py long.csv bingham_s2.png -112.19,40.49,-112.11,40.56 out.png DESCENDING 0401 0710 2022 2023 2024
Also writes OUT.csv (in results/ when OUT is in figures/) with the per-point change (mm, control-ring median removed) per year.
"""
import sys, os
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
from PIL import Image
import style


def change(df, t0, t1):
    W = df.pivot_table(index="date", columns="pid", values="disp_mm").where(
        ~df.pivot_table(index="date", columns="pid", values="masked").astype(bool))
    a = W[(W.index >= t0) & (W.index <= t0 + pd.Timedelta(days=24))].iloc[:1]
    b = W[(W.index <= t1) & (W.index >= t1 - pd.Timedelta(days=24))].iloc[-1:]
    if a.empty or b.empty:
        return None, None, None
    ch = b.iloc[0] - a.iloc[0]
    return ch, a.index[0].date(), b.index[0].date()


def main():
    long_csv, basemap, bbox, out, direction, m0, m1 = sys.argv[1:8]; years = [int(y) for y in sys.argv[8:]]
    bbox = [float(v) for v in bbox.split(",")]
    df = pd.read_csv(long_csv, parse_dates=["date"]); df = df[df.direction == direction]
    if direction == "ASCENDING":
        df = df[df.frame.notna()]
    pts = df.drop_duplicates("pid").set_index("pid")
    img = np.asarray(Image.open(basemap).convert("L"))
    style.apply()
    fig, axs = plt.subplots(1, len(years), figsize=(3.3 * len(years), 3.6))
    axs = np.atleast_1d(axs); rows = []
    for ax, y in zip(axs, years):
        t0 = pd.Timestamp(f"{y}-{m0[:2]}-{m0[2:]}"); t1 = pd.Timestamp(f"{y}-{m1[:2]}-{m1[2:]}")
        if t1 < t0:
            t0 = t0 - pd.DateOffset(years=1)
        ch, a, b = change(df, t0, t1)
        ax.imshow(img, cmap="gray", extent=[bbox[0], bbox[2], bbox[1], bbox[3]], alpha=0.55, aspect=1 / np.cos(np.radians(40.5)))
        ax.grid(False); ax.set_xticks([]); ax.set_yticks([])
        if ch is None:
            ax.set_title(f"{y}: no data"); continue
        ch = ch - ch[pts.sector[ch.index] == "control"].median()
        p = pts.loc[ch.index]; inpit = p.sector != "control"
        sc = ax.scatter(p.lon[inpit], p.lat[inpit], c=ch[inpit], cmap="RdBu", vmin=-40, vmax=40, s=9, edgecolors="none")
        ax.set_title(f"{a} → {b}", color=style.INK, fontsize=8.5)
        ax.set_xlim(bbox[0], bbox[2]); ax.set_ylim(bbox[1], bbox[3])
        for pid, v in ch.items():
            rows.append({"pid": pid, "year": y, "from": a, "to": b, "sector": pts.sector[pid], "lon": pts.lon[pid], "lat": pts.lat[pid], "los_change_mm": round(v, 1)})
    cb = fig.colorbar(sc, ax=axs, shrink=0.75, pad=0.02)
    cb.set_label("LOS change vs control (mm)\nnegative = away from satellite", color=style.INK, fontsize=8)
    cb.outline.set_visible(False)
    fig.suptitle(f"OPERA DISP-S1 {direction.lower()}, Bingham Canyon: same window, different years (blank = masked / no data)",
                 color=style.INK, fontsize=9.5, x=0.01, ha="left")
    fig.savefig(out, dpi=150, bbox_inches="tight"); plt.close(fig)
    csv = out.rsplit(".", 1)[0] + ".csv"
    alt = csv.replace("figures/", "results/")
    if alt != csv and os.path.isdir(os.path.dirname(alt) or "."):
        csv = alt                     # keep tables in results/ next to figures/
    pd.DataFrame(rows).to_csv(csv, index=False)
    r = pd.DataFrame(rows)
    print(r[r.sector != "control"].groupby(["year", "sector"]).los_change_mm.agg(["median", lambda s: (s < -20).mean(), "count"]).round(2).unstack(0))


if __name__ == "__main__":
    main()
