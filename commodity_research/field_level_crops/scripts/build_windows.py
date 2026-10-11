"""Choose the sampling windows: 4 windows of 1.44 x 1.44 km per county, inside high-cropland parts of it.

Design (fixed before any imagery or yield modelling):
  * counties: Iowa and Illinois counties whose 2013-15 mean corn+soy planted area (NASS) is >= 15 % of the
    county's land area and which report a corn yield in >= 5 of 2013-2021
  * the 2015 CDL (Planetary Computer `usda-cdl`, read at its 120 m overview) is mosaicked; every county is cut
    into 1.44 km blocks (12 x 12 overview cells, 48 x 48 CDL cells) lying fully inside the county
  * a block is a candidate if >= 50 % of it is corn or soybeans in 2015 (if a county has < 4 such blocks the
    threshold drops to its 4 best blocks); 4 blocks are drawn at random (seed = county FIPS), each >= 5 km
    from those already drawn
  * 2015 is used only as a cropland screen (no yields, no imagery); masks for each forecast year come
    later from that year's prior CDLs

Output: data/windows.csv (win_id, fips, state, x0, y0 = upper-left corner in EPSG:5070 metres, frac_cs_2015,
        lon, lat of the window centre)
Usage:  python build_windows.py --geo <dir with cb_2020_us_county_500k.zip> [--per-county 4]
"""
import argparse
import numpy as np, pandas as pd, geopandas as gpd, rasterio
from rasterio.features import rasterize
from pyproj import Transformer
import planetary_computer as pc
from common import DATA, STATES, STFIPS, WIN, cdl_tiles, CORN, SOY

OV = 4  # 120 m overview
B = WIN // OV  # block side in overview cells


def mosaic_2015(bounds):
    its = cdl_tiles(2015)
    x0, y0, x1, y1 = bounds
    # align to the tile grid (all tiles share a 90 km grid; 120 m divides it)
    t = its[0].properties["proj:transform"]
    gx, gy = t[2], t[5]
    X0 = gx + np.floor((x0 - gx) / 120) * 120; Y1 = gy + np.ceil((y1 - gy) / 120) * 120
    W = int(np.ceil((x1 - X0) / 120)); H = int(np.ceil((Y1 - y0) / 120))
    mos = np.zeros((H, W), np.uint8)
    for it in its:
        t = it.properties["proj:transform"]; tx, ty = t[2], t[5]
        if tx > x1 or tx + 90000 < x0 or ty < y0 or ty - 90000 > y1:
            continue
        with rasterio.open(pc.sign(it.assets["cropland"].href)) as s:
            a = s.read(1, out_shape=(s.height // OV, s.width // OV))
        c0 = int(round((tx - X0) / 120)); r0 = int(round((Y1 - ty) / 120))
        rs, cs = max(r0, 0), max(c0, 0); re_, ce = min(r0 + a.shape[0], H), min(c0 + a.shape[1], W)
        if re_ > rs and ce > cs:
            blk = a[rs - r0:re_ - r0, cs - c0:ce - c0]
            mos[rs:re_, cs:ce] = np.where(blk > 0, blk, mos[rs:re_, cs:ce])
    return mos, rasterio.transform.from_origin(X0, Y1, 120, 120)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--geo", required=True)
    ap.add_argument("--per-county", type=int, default=4)
    ap.add_argument("--states", default=",".join(STATES))
    a = ap.parse_args()
    states = a.states.split(",")
    c = gpd.read_file(f"zip://{a.geo}/cb_2020_us_county_500k.zip")
    c = c[c.STATEFP.isin([STFIPS[s] for s in states])].to_crs(5070)
    c["fips"] = c.STATEFP + c.COUNTYFP
    c["state"] = c.STATEFP.map({v: k for k, v in STFIPS.items()})
    cy = pd.read_csv(f"{DATA}/county_yield.csv", dtype={"fips": str})
    pl = cy[cy.year.between(2013, 2015)].groupby(["fips", "year"]).planted_ac.sum().groupby("fips").mean()
    ny = cy[(cy.crop == "corn") & cy.year.between(2013, 2021) & cy.yield_bu_ac.notna()].groupby("fips").size()
    c["cs_share"] = c.fips.map(pl) / (c.ALAND * 0.000247105)
    c["n_yield"] = c.fips.map(ny).fillna(0)
    keep = c[(c.cs_share >= 0.15) & (c.n_yield >= 5)].copy()
    print("counties", len(c), "kept", len(keep))
    mos, T = mosaic_2015(keep.total_bounds)
    cs = np.isin(mos, [CORN, SOY]).astype(np.float32)
    tr = Transformer.from_crs(5070, 4326, always_xy=True)
    rows = []
    for _, k in keep.sort_values("fips").iterrows():
        m = rasterize([(k.geometry, 1)], out_shape=mos.shape, transform=T, fill=0, dtype=np.uint8)
        rr, cc = np.where(m)
        r0, c0 = (rr.min() // B) * B, (cc.min() // B) * B
        cand = []
        for r in range(r0, rr.max() + 1, B):
            for q in range(c0, cc.max() + 1, B):
                if r + B > m.shape[0] or q + B > m.shape[1] or m[r:r + B, q:q + B].min() == 0:
                    continue
                cand.append((r, q, cs[r:r + B, q:q + B].mean()))
        cand = pd.DataFrame(cand, columns=["r", "q", "f"])
        pool = cand[cand.f >= 0.5]
        if len(pool) < a.per_county:
            pool = cand.nlargest(a.per_county, "f")
        rng = np.random.default_rng(int(k.fips))
        order = rng.permutation(len(pool))
        chosen = []
        for i in order:
            p = pool.iloc[i]
            if all(np.hypot((p.r - o.r) * 120, (p.q - o.q) * 120) >= 5000 for o in chosen):
                chosen.append(p)
            if len(chosen) == a.per_county:
                break
        for j, p in enumerate(chosen):
            x0, y0 = T.c + p.q * 120, T.f - p.r * 120
            lon, lat = tr.transform(x0 + WIN * 15, y0 - WIN * 15)
            rows.append(dict(fips=k.fips, state=k.state, x0=x0, y0=y0, frac_cs_2015=round(p.f, 3), lon=round(lon, 5), lat=round(lat, 5),
                             cs_share=round(k.cs_share, 3)))
    w = pd.DataFrame(rows)
    w.insert(0, "win_id", np.arange(len(w)))
    w.to_csv(f"{DATA}/windows.csv", index=False)
    print(w.groupby("state").agg(n=("win_id", "size"), counties=("fips", "nunique"), frac=("frac_cs_2015", "mean")))


if __name__ == "__main__":
    main()
