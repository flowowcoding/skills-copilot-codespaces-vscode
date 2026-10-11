"""Shared constants and helpers for the field-level corn/soy yield model (Iowa + Illinois)."""
import os, re, time
import numpy as np, requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
DATA, FEAT, SIG, FIG, RES = (os.path.join(ROOT, d) for d in ["data", "features", "signal", "figures", "results"])
PREV = os.path.abspath(os.path.join(ROOT, "..", "..", "soy_research", "us", "satellite"))  # previous MODIS model (data/ + signal/)
STATES = ["IA", "IL"]
STFIPS = {"IA": "19", "IL": "17", "IN": "18", "NE": "31"}
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
WIN = 48        # window side in 30 m CDL cells (1.44 km)
MARGIN = 2      # extra CDL cells read around each window (for the 5 x 5 interior test)
STEP = 2        # sample every 2nd cell -> 24 x 24 = 576 points per window (60 m spacing)
CORN, SOY = 1, 5  # CDL codes


def get(url, tries=6, timeout=900, stream_to=None):
    err = None
    for k in range(tries):
        try:
            r = requests.get(url, timeout=timeout); r.raise_for_status()
            if stream_to:
                with open(stream_to, "wb") as f:
                    f.write(r.content)
                return stream_to
            return r.content
        except Exception as e:  # noqa
            err = e; time.sleep(5 * (k + 1))
    raise RuntimeError(f"{url}: {err}")


def stac_items(tries=6, **kw):
    """pystac search with retries (the PC STAC API sometimes times out)"""
    import pystac_client
    err = None
    for k in range(tries):
        try:
            return list(pystac_client.Client.open(STAC).search(**kw).items())
        except Exception as e:  # noqa
            err = e; time.sleep(10 * (k + 1))
    raise RuntimeError(err)


def cdl_tiles(year, bbox=(-96.7, 36.9, -87.4, 43.6)):
    """PC usda-cdl cropland items (90 km COG tiles, EPSG:5070) for one year <= 2021"""
    its = stac_items(collections=["usda-cdl"], bbox=list(bbox), datetime=f"{year}-01-01/{year}-12-31",
                     query={"usda_cdl:type": {"eq": "cropland"}})
    return [it for it in its if it.id.startswith(f"cropland_{year}_")]


def cropscape_state(year, st, tmpdir):
    """download a NASS CropScape state CDL GeoTIFF (EPSG:5070, 30 m) and return its path"""
    xml = get(f"https://nassgeodata.gmu.edu/axis2/services/CDLService/GetCDLFile?year={year}&fips={STFIPS[st]}").decode()
    url = re.search(r"<returnURL>(.*?)</returnURL>", xml).group(1)
    fn = f"{tmpdir}/cdl_{year}_{st}.tif"
    get(url, stream_to=fn)
    return fn


def point_offsets():
    """(row, col) of the sample points inside a window, in CDL cells relative to the window's UL corner"""
    r = np.arange(1, WIN, STEP)  # 1, 3, ..., 47
    R, C = np.meshgrid(r, r, indexing="ij")
    return R.ravel(), C.ravel()


def doy(ts):
    return ts.dayofyear if hasattr(ts, "dayofyear") else ts.timetuple().tm_yday
