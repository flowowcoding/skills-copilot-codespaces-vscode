"""Extract MODIS 13Q1 v061 (250 m, 16-day) NDVI / EVI / pixel reliability / composite day at the sample pixels.

Default platform is Aqua (MYD13Q1). Reasons: (1) Terra's overpass has drifted earlier since ~2022 (the
Brazil holdout failure); (2) Aqua's 16-day composites are phased 8 days after Terra's, so for an early
August forecast date the latest *published* Aqua composite ends ~1 week later than the latest Terra one.
Terra (MOD13Q1) can be extracted for a drift check (--platform MOD), normally on the core tile only.

Source: Microsoft Planetary Computer STAC collection modis-13Q1-061 (no auth). Each tile asset is read in
memory, the sample pixels are pulled out, the raster is discarded. Resumable (existing outputs skipped).
Reprocessed duplicates: the most recently produced item id wins.

Composite window: start day-of-year in --doys (Aqua default 137..249 = mid-May .. early Sep).
Outputs: <work>/modis_<PLAT>/<YYYYDDD>_<tile>.npz  (pixel_id, ndvi, evi, rel, cdoy, start, end, item)
         <work>/modis_<PLAT>_items.csv
Usage: python extract_modis.py --work <scratch>/us_sat [--platform MYD] [--tiles h11v04,...] [--threads 12]
"""
import argparse, os, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np, pandas as pd, requests, rasterio
import planetary_computer as pc, pystac_client

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = {"ndvi": "250m_16_days_NDVI", "evi": "250m_16_days_EVI", "rel": "250m_16_days_pixel_reliability",
          "cdoy": "250m_16_days_composite_day_of_the_year"}
DOYS = {"MYD": [137, 153, 169, 185, 201, 217, 233, 249], "MOD": [145, 161, 177, 193, 209, 225, 241]}
BBOX = [-104.1, 36.9, -80.5, 49.1]


def list_items(plat, tiles, first, last, doys):
    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
    rows = []
    for y in range(first, last + 1):
        for it in cat.search(collections=["modis-13Q1-061"], datetime=f"{y}-05-01/{y}-09-30", bbox=BBOX).items():
            if not it.id.startswith(plat + "13Q1"):
                continue
            t = f"h{int(it.properties['modis:horizontal-tile']):02d}v{int(it.properties['modis:vertical-tile']):02d}"
            doy = int(it.id.split(".")[1][5:8])
            if t not in tiles or doy not in doys:
                continue
            rows.append(dict(item=it.id, tile=t, start=it.properties["start_datetime"][:10], end=it.properties["end_datetime"][:10],
                             key=it.id.split(".")[1][1:], produced=it.id.split(".")[-1], **{k: it.assets[v].href for k, v in ASSETS.items()}))
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
    rr, cc = px.row.values, px.col.values
    out = {}
    for k in ASSETS:
        a = fetch(getattr(row, k)); out[k] = a[rr, cc]; del a
    np.savez(fn + ".tmp.npz", pixel_id=px.pixel_id.values.astype(np.int32), ndvi=out["ndvi"].astype(np.int16), evi=out["evi"].astype(np.int16),
             rel=out["rel"].astype(np.int8), cdoy=out["cdoy"].astype(np.int16), start=row.start, end=row.end, item=row.item)
    os.replace(fn + ".tmp.npz", fn)
    return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--platform", default="MYD", choices=["MYD", "MOD"])
    ap.add_argument("--tiles", default=None, help="comma list; default = all tiles with sample pixels")
    ap.add_argument("--data", default=os.path.join(HERE, "data"))
    ap.add_argument("--threads", type=int, default=12)
    ap.add_argument("--first-year", type=int, default=2002)
    ap.add_argument("--last-year", type=int, default=2026)
    ap.add_argument("--relist", action="store_true")
    ap.add_argument("--doys", default=None, help="comma list of composite start days (default: platform list)")
    a = ap.parse_args()
    px = pd.read_csv(f"{a.data}/pixels.csv")
    tiles = set(a.tiles.split(",")) if a.tiles else set(px.tile)
    outdir = f"{a.work}/modis_{a.platform}"; os.makedirs(outdir, exist_ok=True)
    lf = f"{a.work}/modis_{a.platform}_items.csv"
    if os.path.exists(lf) and not a.relist:
        items = pd.read_csv(lf, dtype={"key": str})
    else:
        items = list_items(a.platform, tiles, a.first_year, a.last_year, DOYS[a.platform]); items.to_csv(lf, index=False)
    if a.doys:
        items = items[items.key.astype(str).str[4:].astype(int).isin([int(x) for x in a.doys.split(",")])]
    items = items[items.tile.isin(tiles)]
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
            if i % 25 == 0:
                print(i, len(futs), f"{time.time() - t0:.0f}s new={n}", flush=True)
    print("done", n, flush=True)


if __name__ == "__main__":
    main()
