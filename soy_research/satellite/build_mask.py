"""Build the candidate pixel sample (MODIS 500 m sinusoidal grid) inside soybean municipalities.

Step 1 of the mask. This only decides WHICH pixels we download. It uses a deliberately generous
superset (any municipality whose soybean share ever reached --min-share in PAM 2000-latest), so it
leaks nothing: the per-season mask that actually enters the signal is decided later
(build_features.py) from (a) the pixel's own phenology in PRIOR seasons and (b) municipal soy area
from PAM lagged by two years (the latest PAM published at the as-of date).

Within each state we draw up to --per-state pixels, with probability proportional to the
municipality's peak soy share (soy-dense areas oversampled). Weighting by municipality later undoes
the oversampling.

Outputs: <out>/pixels.csv (pixel_id, state, muni, tile, row, col, lon, lat)
         figures/mask_samples.png (visual check)
Usage: python build_mask.py [--per-state 40000] [--min-share 0.05]
"""
import argparse, json, os
import numpy as np, pandas as pd
from pyproj import Transformer
from rasterio.features import rasterize
from rasterio.transform import Affine
from shapely.geometry import shape, box
from shapely.ops import transform as stransform

HERE = os.path.dirname(os.path.abspath(__file__))
STATES = ["MT", "PR", "RS", "GO", "MS", "BA", "MG", "MA", "TO", "PI", "SP", "SC"]
R = 6371007.181
TILE = 1111950.5197665233
PX = TILE / 2400
X0, Y0 = -20015109.355798, 10007554.677899
SINU = "+proj=sinu +lon_0=0 +x_0=0 +y_0=0 +R=6371007.181 +units=m +no_defs"


def tile_transform(h, v):
    return Affine(PX, 0, X0 + h * TILE, 0, -PX, Y0 - v * TILE)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=os.path.join(HERE, "data"))
    ap.add_argument("--per-state", type=int, default=40000)
    ap.add_argument("--min-share", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    tr = Transformer.from_crs("EPSG:4326", SINU, always_xy=True)
    mu = pd.read_csv(f"{a.data}/pam_muni_area.csv")
    peak = mu.groupby("muni").area_ha.max()
    geoms = {}
    for st in STATES:
        fc = json.load(open(f"{a.data}/munis_{st}.geojson"))
        for f in fc["features"]:
            code = int(f["properties"]["codarea"])
            g = stransform(lambda x, y, z=None: tr.transform(x, y), shape(f["geometry"]))
            geoms[code] = (st, g)
    area_ha = pd.Series({k: g.area / 1e4 for k, (s, g) in geoms.items()})
    share = (peak.reindex(area_ha.index).fillna(0) / area_ha).clip(0, 1)
    cand = share[(share >= a.min_share) & (peak.reindex(share.index) >= 2000)]
    print("candidate municipalities", len(cand), "of", len(share))
    # tiles touched
    tiles = set()
    for code in cand.index:
        b = geoms[code][1].bounds
        for h in range(int((b[0] - X0) // TILE), int((b[2] - X0) // TILE) + 1):
            for v in range(int((Y0 - b[3]) // TILE), int((Y0 - b[1]) // TILE) + 1):
                tiles.add((h, v))
    print("tiles", sorted(tiles))
    recs = []
    for h, v in sorted(tiles):
        T = tile_transform(h, v)
        tb = box(X0 + h * TILE, Y0 - (v + 1) * TILE, X0 + (h + 1) * TILE, Y0 - v * TILE)
        shapes = [(geoms[c][1], int(c)) for c in cand.index if geoms[c][1].intersects(tb)]
        if not shapes:
            continue
        lab = rasterize(shapes, out_shape=(2400, 2400), transform=T, fill=0, dtype="int32")
        rr, cc = np.nonzero(lab)
        recs.append(pd.DataFrame({"tile": f"h{h:02d}v{v:02d}", "row": rr.astype(np.int16), "col": cc.astype(np.int16), "muni": lab[rr, cc]}))
        print(h, v, len(rr))
    px = pd.concat(recs, ignore_index=True)
    px["state"] = px.muni.map(lambda c: geoms[c][0])
    px["p"] = px.muni.map(cand)
    out = []
    for st, g in px.groupby("state"):
        n = min(a.per_state, len(g))
        idx = rng.choice(len(g), size=n, replace=False, p=(g.p / g.p.sum()).values)
        out.append(g.iloc[np.sort(idx)])
    s = pd.concat(out, ignore_index=True)
    # pixel centres -> lon/lat
    hh = s.tile.str[1:3].astype(int); vv = s.tile.str[4:6].astype(int)
    x = X0 + hh * TILE + (s.col + 0.5) * PX
    y = Y0 - vv * TILE - (s.row + 0.5) * PX
    inv = Transformer.from_crs(SINU, "EPSG:4326", always_xy=True)
    s["lon"], s["lat"] = inv.transform(x.values, y.values)
    s = s.sort_values(["tile", "row", "col"]).reset_index(drop=True)
    s["pixel_id"] = np.arange(len(s))
    os.makedirs(f"{a.data}/../work", exist_ok=True)
    s[["pixel_id", "state", "muni", "tile", "row", "col", "lon", "lat"]].to_csv(f"{a.data}/pixels.csv", index=False)
    print(s.groupby("state").size())
    cand.rename("peak_share").to_csv(f"{a.data}/candidate_munis.csv")


if __name__ == "__main__":
    main()
