"""Extract MODIS Aqua MYD13A1 v061 (500 m, 16-day) EVI + pixel reliability at cocoa-weighted sample pixels.

Source: Microsoft Planetary Computer STAC, collection modis-13A1-061 (no auth), tiles h17v08 + h18v08.
Pixels: N locations drawn from data/mask_grid.csv with probability ∝ cocoa ha (uniform jitter inside
the 0.05° cell), so every pixel carries equal weight in a zone mean. The mask is district-level
(Kalischek et al. 2023 via Trase), so pixels are cocoa-*region* pixels (cocoa + forest + fallow mix),
not confirmed cocoa farms.

Point-in-time: availability = production date in the item id (A<start>…061.<YYYYDDDhhmmss>) + 2 days.
Caveat: Aqua stopped orbit maintenance in 2022 and its equator crossing has drifted later since
(the Terra-drift issue found in the Brazil soy track); EVI after 2022 may carry a drift artefact.

Outputs: <work>/modis/<key>_<tile>.npz (pixel_id, evi, rel), <work>/modis_items.csv,
         data/modis_pixels.csv (pixel_id, lat, lon, zone, tile, row, col)
Usage: python extract_modis.py --mask ../data/mask_grid.csv --work <scratch> [--n 20000] [--threads 10]
"""
import argparse, os, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np, pandas as pd, requests, rasterio
import planetary_computer as pc, pystac_client
from pyproj import Transformer

HERE = os.path.dirname(os.path.abspath(__file__))
T = 1111950.5197665233
PX = T / 2400
SIN = "+proj=sinu +R=6371007.181 +nadgrids=@null +wktext +units=m +no_defs"
ASSETS = {"evi": "500m_16_days_EVI", "rel": "500m_16_days_pixel_reliability"}


def sample_pixels(mask, n, seed=0):
    rng = np.random.default_rng(seed)
    i = rng.choice(len(mask), n, p=mask.w_ha / mask.w_ha.sum())
    m = mask.iloc[i].reset_index(drop=True)
    lat = m.lat.values + rng.uniform(-0.025, 0.025, n); lon = m.lon.values + rng.uniform(-0.025, 0.025, n)
    x, y = Transformer.from_crs("EPSG:4326", SIN, always_xy=True).transform(lon, lat)
    h = np.floor((x + 20015109.354) / T).astype(int); v = np.floor((10007554.677 - y) / T).astype(int)
    col = np.floor((x - (-20015109.354 + h * T)) / PX).astype(int); row = np.floor(((10007554.677 - v * T) - y) / PX).astype(int)
    return pd.DataFrame(dict(pixel_id=np.arange(n), lat=lat.round(5), lon=lon.round(5), zone=m.zone, tile=[f"h{a:02d}v{b:02d}" for a, b in zip(h, v)], row=row, col=col))


def list_items(tiles, first, last):
    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
    rows = []
    for y in range(first, last + 1):
        for it in cat.search(collections=["modis-13A1-061"], datetime=f"{y}-01-01/{y}-12-31", bbox=[-8.5, 5, 1, 8.5]).items():
            if not it.id.startswith("MYD13A1"):
                continue
            t = f"h{int(it.properties['modis:horizontal-tile']):02d}v{int(it.properties['modis:vertical-tile']):02d}"
            if t not in tiles:
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
    p = px[px.tile == row.tile]
    out = {k: fetch(getattr(row, k))[p.row.values, p.col.values] for k in ASSETS}
    np.savez(fn + ".tmp.npz", pixel_id=p.pixel_id.values.astype(np.int32), evi=out["evi"].astype(np.int16), rel=out["rel"].astype(np.int8))
    os.replace(fn + ".tmp.npz", fn)
    return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mask", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--threads", type=int, default=10)
    ap.add_argument("--first-year", type=int, default=2002)
    ap.add_argument("--last-year", type=int, default=pd.Timestamp.today().year)
    a = ap.parse_args()
    pxf = os.path.join(HERE, "..", "data", "modis_pixels.csv")
    if os.path.exists(pxf):
        px = pd.read_csv(pxf)
    else:
        px = sample_pixels(pd.read_csv(a.mask), a.n); px.to_csv(pxf, index=False)
    tiles = sorted(px.tile.unique()); print("tiles", tiles, px.tile.value_counts().to_dict())
    itf = f"{a.work}/modis_items.csv"
    if os.path.exists(itf):
        items = pd.read_csv(itf, dtype={"key": str, "produced": str})
    else:
        items = list_items(tiles, a.first_year, a.last_year); items.to_csv(itf, index=False)
    os.makedirs(f"{a.work}/modis", exist_ok=True)
    n = 0
    with ThreadPoolExecutor(a.threads) as ex:
        futs = [ex.submit(task, r, px, f"{a.work}/modis") for r in items.itertuples()]
        for i, f in enumerate(as_completed(futs)):
            n += f.result()
            if i % 50 == 0:
                print(i, "/", len(futs), flush=True)
    print("done, new files", n)


if __name__ == "__main__":
    main()
