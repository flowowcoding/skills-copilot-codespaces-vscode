"""Build district crop-area weights from the ICRISAT District Level Database (apportioned, 1966 boundaries).

Source: ICRISAT DLD API, http://data.icrisat.org/dldAPI/apportioned/area-production-yield (free, no login;
the JSON is what the http://data.icrisat.org/dld/src/crops.html table viewer loads). 311 districts in
20 states with centroid lat/lon, crop area/production/yield 1966-2017.

The mask weight for a district/crop is its mean area over 2008-2017 (the last 10 ICRISAT years). Districts
are kept for a crop if they are among the smallest set that covers 90% of national area of that crop
(ICRISAT total) -- the "core" districts.

Outputs (in --out):
  district_weights.csv : dist_code, state, district, lat, lon, area_<crop>_kha, share_<crop>, core_<crop>
  district_apy_icrisat.csv : dist_code, year, crop, area_kha, prod_kt (chickpea, pigeonpea, sugarcane, cotton)
Usage:  python build_districts.py --json <scratch>/raw/icrisat/apy_apportioned.json --out ../data
"""
import argparse, json, os
import pandas as pd

CROPS = {"chickpea": "CHICKPEA", "pigeonpea": "PIGEONPEA", "sugarcane": "SUGARCANE", "cotton": "COTTON"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cover", type=float, default=0.90)
    a = ap.parse_args()
    d = json.load(open(a.json))
    hdr = [h["header"] + (" (" + h["unit"] + ")" if h["unit"] else "") for h in d["headers"]]
    df = pd.DataFrame(d["data"], columns=hdr)
    num = lambda s: pd.to_numeric(s, errors="coerce").where(lambda x: x >= 0)
    base = pd.DataFrame({"dist_code": df["Dist Code"].astype(int), "year": df["Year"].astype(int),
                         "state": df["State Name"], "district": df["Dist Name"],
                         "lat": num(df["LATITUDE"]), "lon": num(df["LONGITUDE"])})
    long = []
    for c, C in CROPS.items():
        long.append(base[["dist_code", "year"]].assign(crop=c, area_kha=num(df[f"{C} AREA (1000 ha)"]),
                                                       prod_kt=num(df[f"{C} PRODUCTION (1000 tons)"])))
    apy = pd.concat(long)
    apy.to_csv(f"{a.out}/district_apy_icrisat.csv", index=False, float_format="%.2f")
    meta = base.drop_duplicates("dist_code").drop(columns="year").set_index("dist_code")
    rec = apy[apy.year.between(2008, 2017)].groupby(["dist_code", "crop"]).area_kha.mean().unstack()
    for c in CROPS:
        s = rec[c].fillna(0).sort_values(ascending=False)
        meta[f"area_{c}_kha"] = rec[c]
        meta[f"share_{c}"] = s / s.sum()
        cum = (s / s.sum()).cumsum()
        core = cum.index[(cum.shift(fill_value=0) < a.cover)]
        meta[f"core_{c}"] = meta.index.isin(core).astype(int)
        print(c, "national ICRISAT area kha", round(s.sum()), "core districts", len(core))
    meta.reset_index().to_csv(f"{a.out}/district_weights.csv", index=False, float_format="%.5f")


if __name__ == "__main__":
    main()
