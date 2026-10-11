"""Daily county weather from gridMET (4 km, CONUS, updated daily) for the field-level yield model.

Source: the producer's yearly netCDF files, https://www.northwestknowledge.net/metdata/data/<var>_<Y>.nc
(Planetary Computer's gridMET copy ends in 2020). Each file is downloaded to scratch, the Apr 1 .. Sep 30
slab is averaged over the gridMET cells whose centres fall inside each county polygon (Census 2020
cartographic boundary file), and the file is deleted.

Variables: pr (precipitation, mm), tmmx / tmmn (daily max / min temperature, K -> C), vpd (mean vapour
pressure deficit, kPa).
Point-in-time rule (applied in build_features.py): day d is usable from d + 3.

Output: <work>/weather/county_<Y>.csv.gz  (fips, date, prcp_mm, tmax_c, tmin_c, vpd_kpa)
Usage:  python extract_weather_county.py --work <scratch>/field --geo <dir with cb_2020_us_county_500k.zip>
            [--states IA,IL,IN,NE] [--years 2005-2026]
"""
import argparse, os, time
import numpy as np, pandas as pd, requests, netCDF4
import geopandas as gpd
from shapely.geometry import Point  # noqa: F401  (geopandas dependency check)

URL = "https://www.northwestknowledge.net/metdata/data/{v}_{y}.nc"
VARS = {"pr": ("precipitation_amount", "prcp_mm", 0.0), "tmmx": ("air_temperature", "tmax_c", -273.15),
        "tmmn": ("air_temperature", "tmin_c", -273.15), "vpd": ("mean_vapor_pressure_deficit", "vpd_kpa", 0.0)}
STFIPS = {"IA": "19", "IL": "17", "IN": "18", "NE": "31"}


def get(url, fn, tries=6):
    err = None
    for k in range(tries):
        try:
            with requests.get(url, timeout=900, stream=True) as r:
                r.raise_for_status()
                with open(fn, "wb") as f:
                    for ch in r.iter_content(1 << 22):
                        f.write(ch)
            return fn
        except Exception as e:  # noqa
            err = e; time.sleep(5 * (k + 1))
    raise RuntimeError(f"{url}: {err}")


def county_cells(geo, states, lat, lon):
    """map every county to the (i, j) gridMET cells whose centre lies inside it"""
    c = gpd.read_file(f"zip://{geo}/cb_2020_us_county_500k.zip")
    c = c[c.STATEFP.isin([STFIPS[s] for s in states])].to_crs(4326)
    c["fips"] = c.STATEFP + c.COUNTYFP
    b = c.total_bounds
    ii = np.where((lat >= b[1] - 0.05) & (lat <= b[3] + 0.05))[0]
    jj = np.where((lon >= b[0] - 0.05) & (lon <= b[2] + 0.05))[0]
    I, J = np.meshgrid(ii, jj, indexing="ij")
    pts = gpd.GeoDataFrame({"i": I.ravel(), "j": J.ravel()}, geometry=gpd.points_from_xy(lon[J.ravel()], lat[I.ravel()]), crs=4326)
    jn = gpd.sjoin(pts, c[["fips", "geometry"]], predicate="within")
    return jn[["fips", "i", "j"]].reset_index(drop=True), (ii.min(), ii.max() + 1, jj.min(), jj.max() + 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--geo", required=True)
    ap.add_argument("--states", default="IA,IL,IN,NE")
    ap.add_argument("--years", default="2005-2026")
    a = ap.parse_args()
    out = f"{a.work}/weather"; os.makedirs(out, exist_ok=True)
    y0, y1 = map(int, a.years.split("-"))
    cells = box = None
    for y in range(y0, y1 + 1):
        fo = f"{out}/county_{y}.csv.gz"
        if os.path.exists(fo):
            continue
        frames = []
        for v, (name, col, off) in VARS.items():
            fn = f"{out}/{v}_{y}.nc"
            t0 = time.time(); get(URL.format(v=v, y=y), fn)
            with netCDF4.Dataset(fn) as nc:
                lat, lon = np.asarray(nc["lat"][:]), np.asarray(nc["lon"][:])
                if cells is None:
                    cells, box = county_cells(a.geo, a.states.split(","), lat, lon)
                days = pd.Timestamp("1900-01-01") + pd.to_timedelta(np.asarray(nc["day"][:], float), unit="D")
                sel = np.where((days.month >= 4) & (days.month <= 9))[0]
                if len(sel) == 0:
                    os.remove(fn); continue
                var = nc[name]; var.set_auto_maskandscale(True)
                slab = np.asarray(var[sel[0]:sel[-1] + 1, box[0]:box[1], box[2]:box[3]].filled(np.nan), np.float32) + off
            os.remove(fn)
            vals = slab[:, cells.i.values - box[0], cells.j.values - box[2]]  # day x cell
            df = pd.DataFrame(vals.T); df["fips"] = cells.fips.values
            m = df.groupby("fips").mean()
            m.columns = days[sel[0]:sel[-1] + 1].strftime("%Y-%m-%d")
            frames.append(m.stack().rename(col))
            print(y, v, f"{time.time() - t0:.0f}s", flush=True)
        d = pd.concat(frames, axis=1).reset_index().rename(columns={"level_1": "date"})
        d.to_csv(fo, index=False, float_format="%.3f", compression="gzip")
        print(y, "rows", len(d), flush=True)


if __name__ == "__main__":
    main()
