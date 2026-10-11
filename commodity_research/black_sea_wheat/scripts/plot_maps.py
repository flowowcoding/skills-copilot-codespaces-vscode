#!/usr/bin/env python3
"""Maps of the sampling frame and the winter/spring wheat masks.

  figures/map_frame.png      sample pixels by country, region labels, admin-1 outlines
  figures/map_masks_<Y>.png  pixel class in year Y (winter crop / spring crop / other) from
                             data/features/pixel_class.csv (if present)
  figures/map_worldcereal.png WorldCereal 2021 winter-cereal fraction at the pixels (if present)

Usage: python plot_maps.py --geo SCRATCH/raw/geo [--year 2021]
"""
import argparse
import os

import geopandas as gpd
import pandas as pd

import plotstyle

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "..", "data")
F = os.path.join(HERE, "..", "figures")


def base(plt, geo):
    g = gpd.read_file(os.path.join(geo, "ne_10m_admin_1_states_provinces.shp"))
    g = g[g.adm0_a3.isin(["RUS", "UKR", "KAZ", "BLR", "GEO", "MDA"])]
    fig, ax = plt.subplots(figsize=(11, 5.2))
    g.boundary.plot(ax=ax, color="#d9d8d4", linewidth=0.3)
    ax.set_xlim(22, 92)
    ax.set_ylim(43, 59)
    ax.set_aspect(1.6)
    ax.grid(False)
    ax.set_xlabel('longitude, °E')
    ax.set_ylabel('latitude, °N')
    return fig, ax


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--geo", required=True)
    ap.add_argument("--year", type=int, default=2021)
    a = ap.parse_args()
    plt = plotstyle.setup()
    px = pd.read_csv(os.path.join(D, "reference", "pixels.csv"))
    fig, ax = base(plt, a.geo)
    for c, col in zip(["Russia", "Ukraine", "Kazakhstan"], plotstyle.C):
        s = px[px.country == c]
        ax.scatter(s.lon, s.lat, s=0.6, color=col, label=c, rasterized=True)
    for r, s in px.groupby("region"):
        ax.text(s.lon.median(), s.lat.median(), r, fontsize=8, color=plotstyle.TEXT, ha="center",
                bbox=dict(facecolor=plotstyle.BG, edgecolor="none", alpha=0.7, pad=1))
    ax.axhline(50, color=plotstyle.MUTED, lw=0.8, ls="--")
    ax.text(23, 50.2, "50°N (CHIRPS limit)", fontsize=7, color=plotstyle.MUTED)
    ax.set_title(f"Sample: {len(px):,} MODIS 250 m cells with >=75% WorldCover-2021 cropland")
    ax.legend(loc="lower right", markerscale=12)
    fig.tight_layout()
    fig.savefig(os.path.join(F, "map_frame.png"), dpi=150)
    wc = os.path.join(D, "reference", "worldcereal_2021_at_pixels.csv")
    if os.path.exists(wc):
        w = px.merge(pd.read_csv(wc), on="pixel_id")
        fig, ax = base(plt, a.geo)
        s = w[w.wc_winter_frac.notna()]
        sc = ax.scatter(s.lon, s.lat, c=s.wc_winter_frac, s=0.8, cmap="Blues", vmin=0, vmax=1, rasterized=True)
        s2 = w[w.wc_spring_frac > 0.5]
        ax.scatter(s2.lon, s2.lat, s=0.8, color=plotstyle.C[1], label="spring cereals > 50%", rasterized=True)
        fig.colorbar(sc, ax=ax, shrink=0.6, label="winter-cereal share of cell")
        ax.set_title("ESA WorldCereal 2021 at the sample cells")
        ax.legend(loc="lower right", markerscale=12)
        fig.tight_layout()
        fig.savefig(os.path.join(F, "map_worldcereal.png"), dpi=150)
    pc = os.path.join(D, "features", "pixel_class.csv")
    if os.path.exists(pc):
        k = pd.read_csv(pc)
        k = px.merge(k[k.year == a.year], on="pixel_id")
        fig, ax = base(plt, a.geo)
        for lab, col in [("other", "#d9d8d4"), ("spring", plotstyle.C[1]), ("winter", plotstyle.C[0])]:
            s = k[k.cls == lab]
            ax.scatter(s.lon, s.lat, s=0.7, color=col, label=f"{lab} ({len(s):,})", rasterized=True)
        ax.set_title(f"Phenology mask {a.year}: winter crop / spring crop / other")
        ax.legend(loc="lower right", markerscale=12)
        fig.tight_layout()
        fig.savefig(os.path.join(F, f"map_masks_{a.year}.png"), dpi=150)


if __name__ == "__main__":
    main()
