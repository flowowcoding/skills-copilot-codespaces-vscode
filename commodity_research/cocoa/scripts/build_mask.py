"""Build the cocoa-area weighting mask for Côte d'Ivoire + Ghana on the CHIRPS 0.05° grid.

Cocoa area per admin unit comes from Trase's spatial metrics, which aggregate the 10 m cocoa map of
Kalischek et al. (2023, Nature Food, Sentinel-2 2019-2021):
  https://resources.trase.earth/20261008/data/spatial-metrics/spatial-metrics-cote-d-ivoire-cocoa-cocoa_area_region.csv
  https://resources.trase.earth/20261008/data/spatial-metrics/spatial-metrics-ghana-cocoa-cocoa_area_district.csv
Admin geometries: geoBoundaries gbOpen CIV ADM2 (33 regions) and GHA ADM2 (260 districts).
The raw 10 m raster is only published on Earth Engine (no free bulk download), so cocoa area is spread
uniformly within each unit: weight(cell) = sum_units area(cell ∩ unit) * cocoa_ha(unit) / area(unit).

Zones: CIV_W (west of -5.5°E: Soubré/San Pédro/Daloa/Duékoué, the core of the "new" cocoa belt),
CIV_E (rest of CIV), GHA. Outputs (to --out):
  mask_grid.csv     lat, lon, country, zone, w_ha  (cells with w_ha > 0)
  mask_units.csv    unit, country, zone, cocoa_ha, area_km2, density
  sample_points.csv 30 representative points (weighted k-means of cells) for point APIs (Open-Meteo)
Usage: python build_mask.py --raw <scratch>/raw --out ../data
"""
import argparse, difflib, os, re
import numpy as np, pandas as pd, geopandas as gpd
from shapely.geometry import box

RES = 0.05
BBOX = (-8.7, 4.3, 1.3, 9.1)  # lon0, lat0, lon1, lat1


def norm(s):
    s = s.upper().replace("DISTRICT AUTONOME", "AUTONOME")
    s = re.sub(r"\b(MUNICIPAL|METROPOLITAN|METROPOLIS)\b", "", s)
    s = re.sub(r"[-/]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def join(geo, tr):
    tr = tr.assign(k=tr.region.map(norm)).groupby("k", as_index=False).cocoa_area_hectares.sum()
    keys = list(tr.k)
    out = []
    for _, r in geo.iterrows():
        k = norm(r.shapeName)
        m = k if k in keys else (difflib.get_close_matches(k, keys, n=1, cutoff=0.75) or [None])[0]
        out.append(m)
    geo = geo.assign(k=out).merge(tr, on="k", how="left")
    return geo


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"))
    a = ap.parse_args()
    parts = []
    for iso, geo_f, tr_f in [("CIV", "geoBoundaries-CIV-ADM2_simplified.geojson", "spatial-metrics-cote-d-ivoire-cocoa-cocoa_area_region.csv"),
                             ("GHA", "geoBoundaries-GHA-ADM2_simplified.geojson", "spatial-metrics-ghana-cocoa-cocoa_area_district.csv")]:
        g = gpd.read_file(f"{a.raw}/geob/{geo_f}")
        t = pd.read_csv(f"{a.raw}/trase/{tr_f}")
        j = join(g, t)
        miss = j.cocoa_area_hectares.isna().sum()
        tot_t, tot_j = t.cocoa_area_hectares.sum(), j.cocoa_area_hectares.sum()
        print(iso, "units", len(j), "unmatched", miss, f"cocoa ha matched {tot_j/1e6:.2f}M of {tot_t/1e6:.2f}M")
        j["country"] = iso
        parts.append(j[["shapeName", "country", "cocoa_area_hectares", "geometry"]])
    u = pd.concat(parts, ignore_index=True).fillna({"cocoa_area_hectares": 0})
    u = gpd.GeoDataFrame(u, geometry="geometry", crs="EPSG:4326")
    ue = u.to_crs("EPSG:32630")
    u["area_km2"] = ue.area / 1e6
    u["density"] = u.cocoa_area_hectares / u.area_km2  # ha per km2
    cx = u.geometry.representative_point().x
    u["zone"] = np.where(u.country == "GHA", "GHA", np.where(cx < -5.5, "CIV_W", "CIV_E"))
    # grid
    lons = np.round(np.arange(BBOX[0] + RES / 2, BBOX[2], RES), 3)
    lats = np.round(np.arange(BBOX[1] + RES / 2, BBOX[3], RES), 3)
    cells = gpd.GeoDataFrame({"lon": np.repeat(lons, len(lats)), "lat": np.tile(lats, len(lons))},
                             geometry=[box(x - RES / 2, y - RES / 2, x + RES / 2, y + RES / 2) for x in lons for y in lats], crs="EPSG:4326")
    inter = gpd.overlay(cells, u[u.cocoa_area_hectares > 0], how="intersection", keep_geom_type=True)
    inter["a_km2"] = inter.to_crs("EPSG:32630").area / 1e6
    inter["w_ha"] = inter.a_km2 * inter.density
    grid = inter.groupby(["lat", "lon"]).agg(w_ha=("w_ha", "sum")).reset_index()
    lab = inter.sort_values("w_ha").groupby(["lat", "lon"]).last()[["country", "zone"]].reset_index()
    grid = grid.merge(lab, on=["lat", "lon"])
    grid = grid[grid.w_ha > 1].sort_values(["lat", "lon"])
    os.makedirs(a.out, exist_ok=True)
    grid[["lat", "lon", "country", "zone", "w_ha"]].to_csv(f"{a.out}/mask_grid.csv", index=False, float_format="%.3f")
    u.drop(columns="geometry").rename(columns={"shapeName": "unit", "cocoa_area_hectares": "cocoa_ha"}).to_csv(
        f"{a.out}/mask_units.csv", index=False, float_format="%.2f")
    print(grid.groupby("zone").w_ha.agg(["count", "sum"]))
    # representative points: weighted k-means per zone (10 each)
    rng = np.random.default_rng(0)
    pts = []
    for z, gz in grid.groupby("zone"):
        X = gz[["lon", "lat"]].values; w = gz.w_ha.values
        C = X[rng.choice(len(X), 10, replace=False, p=w / w.sum())]
        for _ in range(50):
            lab_ = ((X[:, None, :] - C[None]) ** 2).sum(-1).argmin(1)
            C = np.array([np.average(X[lab_ == k], axis=0, weights=w[lab_ == k]) if (lab_ == k).any() else C[k] for k in range(10)])
        lab_ = ((X[:, None, :] - C[None]) ** 2).sum(-1).argmin(1)
        for k in range(10):
            pts.append(dict(point=f"{z}_{k:02d}", zone=z, lon=round(C[k, 0], 3), lat=round(C[k, 1], 3), w_ha=w[lab_ == k].sum()))
    pd.DataFrame(pts).to_csv(f"{a.out}/sample_points.csv", index=False, float_format="%.3f")


if __name__ == "__main__":
    main()
