"""Extract MODIS Aqua MYD13A1 v061 (500 m, 16-day) EVI and pixel reliability at the sample pixels.

Aqua is used rather than Terra because Terra's overpass has drifted earlier since ~2022 (the failure mode
found in ../../soy_research/satellite) and Aqua composites are phased 8 days later.
Source: Microsoft Planetary Computer STAC collection modis-13A1-061 (no auth). Each tile asset is read in
memory, the sample pixels are pulled out, the raster is discarded. Reprocessed duplicates: the most
recently produced item wins. Point-in-time rule used downstream: a composite is usable from its end
date + 14 days (typical LP DAAC + PC latency; conservative).

Outputs: <work>/modis_MYD/<YYYYDDD>_<tile>.npz (evi int16 x1e4, rel int8, start, end)
         <work>/modis_MYD_items.csv
Usage:  python extract_modis.py --work <scratch>/india [--threads 12]
"""
import argparse, os, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np, pandas as pd, requests, rasterio
import planetary_computer as pc, pystac_client

ASSETS = {"evi": "500m_16_days_EVI", "rel": "500m_16_days_pixel_reliability"}
BBOX = [68, 8, 90, 34]


def list_items(tiles, first, last):
    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
    rows = []
    for y in range(first, last + 1):
        for q in range(4):
            m0 = 3 * q + 1
            dt = f"{y}-{m0:02d}-01/{y}-{m0 + 2:02d}-{30 if m0 + 2 in (4, 6, 9, 11) else 31}"
            for k in range(6):
                try:
                    its = list(cat.search(collections=["modis-13A1-061"], datetime=dt, bbox=BBOX).items()); break
                except Exception as e:  # noqa
                    print("retry list", dt, e); time.sleep(10 * (k + 1))
            for it in its:
                if not it.id.startswith("MYD13A1"):
                    continue
                t = f"h{int(it.properties['modis:horizontal-tile']):02d}v{int(it.properties['modis:vertical-tile']):02d}"
                if t in tiles:
                    rows.append(dict(item=it.id, tile=t, start=it.properties["start_datetime"][:10],
                                     end=it.properties["end_datetime"][:10], key=it.id.split(".")[1][1:],
                                     produced=it.id.split(".")[-1], **{k2: it.assets[v].href for k2, v in ASSETS.items()}))
        print("listed", y, len(rows), flush=True)
    d = pd.DataFrame(rows).sort_values("produced").drop_duplicates(["key", "tile"], keep="last")
    return d.sort_values(["key", "tile"])


def fetch(href, tries=6):
    err = None
    for k in range(tries):
        try:
            r = requests.get(pc.sign(href), timeout=300); r.raise_for_status()
            with rasterio.MemoryFile(r.content) as m, m.open() as s:
                return s.read(1)
        except Exception as e:  # noqa
            err = e; time.sleep(4 * (k + 1))
    raise RuntimeError(f"{href}: {err}")


def task(row, px, outdir):
    fn = f"{outdir}/{row.key}_{row.tile}.npz"
    if os.path.exists(fn):
        return 0
    out = {k: fetch(getattr(row, k))[px.row.values, px.col.values] for k in ASSETS}
    np.savez(fn + ".tmp.npz", evi=out["evi"].astype(np.int16), rel=out["rel"].astype(np.int8), start=row.start, end=row.end, item=row.item)
    os.replace(fn + ".tmp.npz", fn)
    return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--threads", type=int, default=12)
    ap.add_argument("--first-year", type=int, default=2002)
    ap.add_argument("--last-year", type=int, default=2026)
    ap.add_argument("--relist", action="store_true")
    a = ap.parse_args()
    px = pd.read_csv(f"{a.work}/pixels.csv")
    tiles = set(px.tile)
    outdir = f"{a.work}/modis_MYD"; os.makedirs(outdir, exist_ok=True)
    lf = f"{a.work}/modis_MYD_items.csv"
    if os.path.exists(lf) and not a.relist:
        items = pd.read_csv(lf, dtype={"key": str})
    else:
        items = list_items(tiles, a.first_year, a.last_year); items.to_csv(lf, index=False)
    print("items", len(items), flush=True)
    groups = {t: g for t, g in px.groupby("tile")}
    t0 = time.time(); n = 0
    with ThreadPoolExecutor(a.threads) as ex:
        futs = [ex.submit(task, r, groups[r.tile], outdir) for r in items.itertuples()]
        for i, f in enumerate(as_completed(futs)):
            try:
                n += f.result()
            except Exception as e:  # noqa
                print("FAILED", e, flush=True)
            if i % 50 == 0:
                print(i, len(futs), f"{time.time() - t0:.0f}s new={n}", flush=True)
    print("done", n, flush=True)


if __name__ == "__main__":
    main()
