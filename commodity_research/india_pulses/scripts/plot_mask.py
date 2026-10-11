"""Map of the crop masks: core districts per crop (ICRISAT centroids, size ~ area share) and the sampled
MODIS cropland pixels. State outlines: Natural Earth 1:50m admin-1 (public domain).

Usage: python plot_mask.py --data ../data --pixels <scratch>/india/pixels_crop.csv --out ../figures/fig_mask_districts.png
"""
import argparse
import geopandas as gpd, pandas as pd
from plotstyle import setup, C, TEXT, MUTED


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="../data"); ap.add_argument("--pixels", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    plt = setup()
    st = gpd.read_file(f"{a.data}/india_states_ne50m.geojson")
    dw = pd.read_csv(f"{a.data}/district_weights.csv")
    px = pd.read_csv(a.pixels)
    fig, ax = plt.subplots(figsize=(7.2, 7.6))
    st.boundary.plot(ax=ax, color="#d6d5d0", linewidth=0.5)
    p = px[px.crop].sample(min(25000, int(px.crop.sum())), random_state=0)
    ax.scatter(p.lon, p.lat, s=0.15, color=MUTED, alpha=0.5, lw=0, label="cropland pixels sampled (500 m)")
    for k, (crop, lab) in enumerate([("chickpea", "chickpea core districts"), ("pigeonpea", "pigeon pea core districts"), ("sugarcane", "sugarcane core districts")]):
        d = dw[dw[f"core_{crop}"] == 1]
        ax.scatter(d.lon + (k - 1) * 0.12, d.lat, s=900 * d[f"share_{crop}"], facecolor="none", edgecolor=C[k], lw=1.1, label=lab)
    ax.set_xlim(68, 90); ax.set_ylim(8, 32); ax.set_aspect("equal")
    ax.set_xlabel("longitude"); ax.set_ylabel("latitude")
    ax.set_title("Crop masks: core districts (circle area ~ share of national crop area) and sampled pixels", color=TEXT)
    ax.legend(loc="lower left", markerscale=1, fontsize=8)
    fig.tight_layout(); fig.savefig(a.out, dpi=130)


if __name__ == "__main__":
    main()
