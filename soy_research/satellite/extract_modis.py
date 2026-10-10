"""Extract MODIS Terra MOD13A1 (v061, 500 m, 16-day) NDVI / EVI / pixel reliability at the sample pixels.

Reads from Microsoft Planetary Computer (collection modis-13A1-061, no auth). Each tile asset is
downloaded into memory, the sample pixels are pulled out, and the raster is discarded, so disk use
stays at ~3 bytes x pixels per composite. Resumable: existing outputs are skipped.

Season window: composites starting DOY >= 193 (mid-July) through DOY <= 145 (late May) of the next
year, for seasons 2000/01 .. --last-season.

Outputs: <work>/modis/<YYYYDDD>_<tile>.npz  (pixel_id, ndvi, evi, rel, composite start/end dates)
         <work>/modis_items.csv              (item id, start, end, tile)
Usage: python extract_modis.py --work <scratch>/soy_sat [--threads 32]
"""
import argparse, io, os, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np, pandas as pd, requests, rasterio
import planetary_computer as pc, pystac_client

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = {"ndvi": "500m_16_days_NDVI", "evi": "500m_16_days_EVI", "rel": "500m_16_days_pixel_reliability"}


def list_items(tiles, first, last):
    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
    rows = []
    for y in range(first, last + 1):
        for it in cat.search(collections=["modis-13A1-061"], datetime=f"{y}-01-01/{y}-12-31", bbox=[-62, -34, -38, -2]).items():
            if not it.id.startswith("MOD13A1"):
                continue
            h, v = int(it.properties["modis:horizontal-tile"]), int(it.properties["modis:vertical-tile"])
            t = f"h{h:02d}v{v:02d}"
            if t not in tiles:
                continue
            doy = int(it.id.split(".")[1][5:8])
            if 145 < doy < 193:
                continue
            rows.append(dict(item=it.id, tile=t, start=it.properties["start_datetime"][:10], end=it.properties["end_datetime"][:10],
                             key=it.id.split(".")[1][1:], **{k: it.assets[v].href for k, v in ASSETS.items()}))
        print("listed", y, len(rows), flush=True)
    return pd.DataFrame(rows)


def fetch(href, tries=5):
    for k in range(tries):
        try:
            r = requests.get(pc.sign(href), timeout=180); r.raise_for_status()
            with rasterio.MemoryFile(r.content) as m, m.open() as s:
                return s.read(1)
        except Exception as e:  # noqa
            time.sleep(3 * (k + 1)); err = e
    raise RuntimeError(f"{href}: {err}")


def task(row, px, outdir):
    fn = f"{outdir}/{row.key}_{row.tile}.npz"
    if os.path.exists(fn):
        return fn, 0
    a = {k: fetch(getattr(row, k)) for k in ASSETS}
    rr, cc = px.row.values, px.col.values
    np.savez(fn + ".tmp.npz", pixel_id=px.pixel_id.values.astype(np.int32), ndvi=a["ndvi"][rr, cc].astype(np.int16),
             evi=a["evi"][rr, cc].astype(np.int16), rel=a["rel"][rr, cc].astype(np.uint8), start=row.start, end=row.end)
    os.replace(fn + ".tmp.npz", fn)
    return fn, 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--data", default=os.path.join(HERE, "data"))
    ap.add_argument("--threads", type=int, default=32)
    ap.add_argument("--first-year", type=int, default=2000)
    ap.add_argument("--last-year", type=int, default=2026)
    a = ap.parse_args()
    px = pd.read_csv(f"{a.data}/pixels.csv")
    outdir = f"{a.work}/modis"; os.makedirs(outdir, exist_ok=True)
    lf = f"{a.work}/modis_items.csv"
    items = pd.read_csv(lf) if os.path.exists(lf) else list_items(set(px.tile), a.first_year, a.last_year)
    items = items[~((items.key.astype(str).str[:4] == "2000") & (items.key.astype(str).str[4:].astype(int) <= 145))]
    items.to_csv(lf, index=False)
    print("items", len(items), flush=True)
    groups = {t: g for t, g in px.groupby("tile")}
    t0 = time.time(); n = 0
    with ThreadPoolExecutor(a.threads) as ex:
        futs = [ex.submit(task, r, groups[r.tile], outdir) for r in items.itertuples()]
        for i, f in enumerate(as_completed(futs)):
            try:
                _, d = f.result(); n += d
            except Exception as e:  # noqa
                print("FAILED", e, flush=True)
            if i % 50 == 0:
                print(i, len(futs), f"{time.time() - t0:.0f}s new={n}", flush=True)


if __name__ == "__main__":
    main()
