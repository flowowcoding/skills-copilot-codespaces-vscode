"""Daily weather per state from gridMET (4 km, CONUS, 1979-present, updated daily), at the sample pixels.

gridMET's Planetary Computer copy ends in 2020 (as do Daymet and the PC ERA5 has no 2025+ items), so the
yearly netCDF files are read from the producer, https://www.northwestknowledge.net/metdata/data/
(pr_<Y>.nc precipitation mm, tmmx_<Y>.nc daily max temperature K). Each file is downloaded to scratch,
the May 1 .. Sep 30 slab is sampled at the unique gridMET cells under the candidate pixels, and the file is
deleted. Aggregated immediately to state x day (unweighted mean over the state's candidate pixels):
  prcp_mm   precipitation
  tmax_c    daily maximum temperature
  hdd30     mean over pixels of max(tmax - 30, 0)  (heat degree days above 30 C)
  gdd       mean over pixels of a Tmax-only growing-degree index, max(min(tmax, 30) - 10, 0) / 2
            (diagnostic only; not a model feature)
Point-in-time rule applied downstream: day d is available on d + 3 (gridMET posts with a 1-2 day lag).

Output: features/weather_state_daily.csv (state, date, prcp_mm, tmax_c, hdd30, gdd)
Usage: python extract_weather.py --work <scratch>/us_sat [--years 2003-2026]
"""
import argparse, os, time
import numpy as np, pandas as pd, requests
import netCDF4

HERE = os.path.dirname(os.path.abspath(__file__))
URL = "https://www.northwestknowledge.net/metdata/data/{v}_{y}.nc"
VARS = {"pr": "precipitation_amount", "tmmx": "air_temperature"}


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


def sample(fn, var, lat, lon):
    with netCDF4.Dataset(fn) as nc:
        la, lo = nc["lat"][:], nc["lon"][:]
        days = pd.Timestamp("1900-01-01") + pd.to_timedelta(nc["day"][:].astype(float), unit="D")
        sel = np.where((days.month >= 5) & (days.month <= 9))[0]
        ii = np.abs(la[:, None] - lat[None, :]).argmin(0); jj = np.abs(lo[:, None] - lon[None, :]).argmin(0)
        i0, i1, j0, j1 = ii.min(), ii.max() + 1, jj.min(), jj.max() + 1
        v = nc[VARS[var]]
        v.set_auto_maskandscale(True)
        if len(sel) == 0:
            return days[:0], np.zeros((0, len(lat)))
        slab = np.asarray(v[sel[0]:sel[-1] + 1, i0:i1, j0:j1].filled(np.nan), dtype=np.float32)
        return days[sel[0]:sel[-1] + 1], slab[:, ii - i0, jj - j0]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--data", default=os.path.join(HERE, "data"))
    ap.add_argument("--out", default=os.path.join(HERE, "features"))
    ap.add_argument("--years", default="2003-2026")
    a = ap.parse_args()
    px = pd.read_csv(f"{a.data}/pixels.csv")
    tmp = f"{a.work}/gridmet"; os.makedirs(tmp, exist_ok=True)
    y0, y1 = map(int, a.years.split("-"))
    states = px.state.values
    parts = []
    for y in range(y0, y1 + 1):
        pf = f"{tmp}/state_{y}.csv"
        if os.path.exists(pf) and y < y1:
            parts.append(pd.read_csv(pf)); continue
        res = {}
        for v in VARS:
            fn = f"{tmp}/{v}_{y}.nc"
            get(URL.format(v=v, y=y), fn)
            res[v] = sample(fn, v, px.lat.values, px.lon.values)
            os.remove(fn)
        days, pr = res["pr"]; days2, tx = res["tmmx"]
        n = min(len(days), len(days2)); days, pr, tx = days[:n], pr[:n], tx[:n] - 273.15
        hdd = np.maximum(tx - 30, 0); gdd = np.maximum(np.minimum(tx, 30) - 10, 0) / 2
        rows = []
        for s in sorted(set(states)):
            m = states == s
            rows.append(pd.DataFrame(dict(state=s, date=days.strftime("%Y-%m-%d"), prcp_mm=np.nanmean(pr[:, m], 1), tmax_c=np.nanmean(tx[:, m], 1),
                                          hdd30=np.nanmean(hdd[:, m], 1), gdd=np.nanmean(gdd[:, m], 1))))
        d = pd.concat(rows); d.to_csv(pf, index=False, float_format="%.3f"); parts.append(d)
        print(y, len(days), days.max().date(), flush=True)
    pd.concat(parts).sort_values(["state", "date"]).to_csv(f"{a.out}/weather_state_daily.csv", index=False, float_format="%.3f")


if __name__ == "__main__":
    main()
