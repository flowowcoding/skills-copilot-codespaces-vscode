"""Build the production-region polygons that forecast cones are tested against.

Regions (all fixed before any price data was examined; see README "Regions"):

* citrus   : 22 Florida counties that hold >95% of commercial citrus acreage (USDA NASS
             Florida Citrus Statistics county tables): the Central Ridge, Indian River,
             Southwest and northern fringe counties listed in CITRUS below.
* gulf_energy : the offshore Gulf of Mexico (Gulf of America) OCS producing area --
             water between 87.5W and 97.3W, north of 26.0N (Perdido, Green Canyon, Mississippi
             Canyon, shelf) -- unioned with 50 km discs around the eight Texas/Louisiana/
             Mississippi refining and LNG hubs in HUBS.
* cotton   : Southeast cotton belt states (GA, AL, SC, NC, MS) plus the Texas Coastal Bend /
             Upper Coast / Lower Rio Grande counties in TX_COTTON. (The Texas High Plains, the
             largest US cotton area, sits far inland and is not reached by hurricane cones.)
* rice     : SW Louisiana rice parishes + Texas Gulf coast rice counties (exploratory only).

Inputs : Census cartographic boundary files cb_2022_us_county_5m / cb_2022_us_state_5m (zip).
Output : data/regions.geojson (EPSG:4326), small.

Usage  : python build_regions.py --geo DIR --out ../data/regions.geojson
"""
import argparse

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, box
from shapely.ops import unary_union

CITRUS = ["Polk", "Highlands", "DeSoto", "Hendry", "Hardee", "Collier", "St. Lucie", "Indian River",
          "Lake", "Osceola", "Charlotte", "Manatee", "Okeechobee", "Martin", "Hillsborough",
          "Glades", "Pasco", "Orange", "Brevard", "Palm Beach", "Lee", "Sarasota"]
HUBS = {  # lat, lon of refining / LNG export clusters
    "Corpus Christi": (27.81, -97.40), "Freeport": (28.95, -95.33), "Houston-Texas City": (29.70, -95.05),
    "Beaumont-Port Arthur-Sabine Pass": (29.85, -93.95), "Lake Charles-Cameron": (30.05, -93.30),
    "Baton Rouge": (30.50, -91.18), "New Orleans corridor (Garyville-Chalmette-Plaquemines)": (29.95, -90.30),
    "Pascagoula": (30.35, -88.50)}
TX_COTTON = ["Nueces", "San Patricio", "Refugio", "Calhoun", "Victoria", "Jackson", "Wharton",
             "Matagorda", "Kleberg", "Willacy", "Cameron", "Hidalgo", "Fort Bend", "Bee", "Goliad",
             "Brazoria", "Live Oak"]
RICE_LA = ["Acadia", "Jefferson Davis", "Vermilion", "Evangeline", "St. Landry", "Allen",
           "Calcasieu", "Cameron", "Avoyelles", "Rapides"]
RICE_TX = ["Wharton", "Colorado", "Matagorda", "Jackson", "Brazoria", "Jefferson", "Chambers",
           "Liberty", "Waller", "Fort Bend"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--geo", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    cty = gpd.read_file(f"zip://{a.geo}/cb_2022_us_county_5m.zip").to_crs(4326)
    st = gpd.read_file(f"zip://{a.geo}/cb_2022_us_state_5m.zip").to_crs(4326)

    def counties(state, names):
        sel = cty[(cty.STUSPS == state) & cty.NAME.isin(names)]
        missing = set(names) - set(sel.NAME)
        assert not missing, (state, missing)
        return unary_union(sel.geometry.values)

    land = unary_union(st[st.STUSPS.isin(["TX", "LA", "MS", "AL", "FL"])].geometry.values)
    offshore = box(-97.3, 26.0, -87.5, 30.4).difference(land)
    utm = "EPSG:3857"
    hubs = gpd.GeoSeries([Point(lon, lat) for lat, lon in HUBS.values()], crs=4326).to_crs(utm)
    hubs = hubs.buffer(50_000 / 0.87).to_crs(4326)  # ~50 km at 29N in web-mercator metres
    regions = {
        "citrus": counties("FL", CITRUS),
        "gulf_energy": unary_union([offshore] + list(hubs.values)),
        "cotton": unary_union([unary_union(st[st.STUSPS.isin(["GA", "AL", "SC", "NC", "MS"])].geometry.values),
                               counties("TX", TX_COTTON)]),
        "rice": unary_union([counties("LA", RICE_LA), counties("TX", RICE_TX)]),
    }
    g = gpd.GeoDataFrame({"region": list(regions)}, geometry=list(regions.values()), crs=4326)
    g["geometry"] = g.geometry.simplify(0.01)
    g["area_km2"] = g.to_crs(6933).area / 1e6
    g.to_file(a.out, driver="GeoJSON")
    print(g[["region", "area_km2"]])


if __name__ == "__main__":
    main()
