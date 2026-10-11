"""Map of the candidate sample pixels (and optionally one year's corn / soybean masks) over the CDL.

Background: CDL (Planetary Computer usda-cdl, cropland) read at 900 m from the COG overviews, classed as
corn, soybeans, other. Points: candidate pixels (data/pixels.csv); with --mask-year Y, the pixels in the
year-Y corn and soybean masks (<work>/mask_<Y>.csv from build_features.py).
Output: figures/sample_map.png (or figures/mask_map_<Y>.png)
Usage: python plot_sample.py --geo <scratch>/geo [--cdl-year 2021] [--mask-year 2024 --work <scratch>/us_sat]
"""
import argparse, os, sys
import numpy as np, pandas as pd, geopandas as gpd, rasterio
from rasterio.enums import Resampling
import planetary_computer as pc, pystac_client
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from plotstyle import setup, C, TEXT, BG, GRID  # noqa
STFIPS = ["19", "17", "31", "27", "18", "39", "46", "38", "20", "29", "55", "26"]
RES = 900.0


def cdl_mosaic(year, bounds):
    x0, y0, x1, y1 = bounds
    W, H = int((x1 - x0) / RES), int((y1 - y0) / RES)
    mos = np.zeros((H, W), np.uint8)
    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
    its = [it for it in cat.search(collections=["usda-cdl"], bbox=[-104.1, 35.9, -80.5, 49.1], query={"usda_cdl:type": {"eq": "cropland"}}).items()
           if it.id.startswith(f"cropland_{year}_")]

    def one(it):
        with rasterio.open(pc.sign(it.assets["cropland"].href)) as s:
            a = s.read(1, out_shape=(int(s.height * 30 / RES), int(s.width * 30 / RES)), resampling=Resampling.mode)
            return a, s.bounds
    with ThreadPoolExecutor(8) as ex:
        for a, b in ex.map(one, its):
            c0, r0 = int(round((b.left - x0) / RES)), int(round((y1 - b.top) / RES))
            h, w = a.shape
            rs, cs = max(r0, 0), max(c0, 0); re_, ce = min(r0 + h, H), min(c0 + w, W)
            if re_ <= rs or ce <= cs:
                continue
            blk = a[rs - r0:re_ - r0, cs - c0:ce - c0]
            mos[rs:re_, cs:ce] = np.where(blk > 0, blk, mos[rs:re_, cs:ce])
    return mos


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--geo", required=True)
    ap.add_argument("--cdl-year", type=int, default=2021)
    ap.add_argument("--mask-year", type=int, default=None)
    ap.add_argument("--work", default=None)
    a = ap.parse_args()
    plt = setup()
    stt = gpd.read_file(f"zip://{a.geo}/cb_2020_us_state_500k.zip")
    stt = stt[stt.STATEFP.isin(STFIPS)].to_crs("EPSG:5070")
    x0, y0, x1, y1 = stt.total_bounds
    x0, y0, x1, y1 = x0 - 20000, y0 - 20000, x1 + 20000, y1 + 20000
    mos = cdl_mosaic(a.cdl_year, (x0, y0, x1, y1))
    img = np.empty(mos.shape + (3,))
    bg = np.array([0xfc, 0xfc, 0xfb]) / 255
    img[:] = bg
    img[(mos > 0)] = np.array([0xe6, 0xe5, 0xe1]) / 255
    img[mos == 1] = np.array([0xf3, 0xd9, 0x99]) / 255   # corn: light tint of #eda100
    img[np.isin(mos, [5, 26, 254])] = np.array([0xa9, 0xdf, 0xc8]) / 255  # soy: light tint of #1baf7a
    fig, ax = plt.subplots(figsize=(11, 7.2))
    ax.imshow(img, extent=(x0, x1, y0, y1), interpolation="nearest")
    stt.boundary.plot(ax=ax, color=TEXT, linewidth=0.5)
    px = pd.read_csv(os.path.join(HERE, "data", "pixels.csv"))
    if a.mask_year:
        m = pd.read_csv(f"{a.work}/mask_{a.mask_year}.csv").merge(px, on="pixel_id")
        rest = m[(m.corn == 0) & (m.soy == 0)]
        ax.scatter(rest.x_5070, rest.y_5070, s=0.15, color="#a3a29d", label=f"candidate, not in {a.mask_year} masks ({len(rest):,})", rasterized=True)
        ax.scatter(m[m.corn == 1].x_5070, m[m.corn == 1].y_5070, s=0.3, color=C[3], label=f"corn mask {a.mask_year} ({int(m.corn.sum()):,})", rasterized=True)
        ax.scatter(m[m.soy == 1].x_5070, m[m.soy == 1].y_5070, s=0.3, color=C[2], label=f"soybean mask {a.mask_year} ({int(m.soy.sum()):,})", rasterized=True)
        title = f"{a.mask_year} corn and soybean masks (from CDL {a.mask_year - 2} and {a.mask_year - 1}) over CDL {a.cdl_year}"
        fn = f"mask_map_{a.mask_year}.png"
    else:
        ax.scatter(px.x_5070, px.y_5070, s=0.06, color=C[0], alpha=0.8, label=f"candidate MODIS 250 m pixels ({len(px):,}; 5,000 per state)", rasterized=True)
        title = f"Stratified sample over CDL {a.cdl_year} (corn = amber tint, soybeans = green tint)"
        fn = "sample_map.png"
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_xticks([]); ax.set_yticks([]); ax.grid(False); ax.set_xlabel(""); ax.set_ylabel("")
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.set_title(title)
    lg = ax.legend(loc="lower left", markerscale=25)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "figures", fn), dpi=130)
    print("wrote", fn)


if __name__ == "__main__":
    main()
