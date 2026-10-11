"""Annual SO2 emissions of each smelter from NASA's satellite point-source catalogue.

Source: NASA GSFC MEaSUREs "Global catalogue of large SO2 sources", version 2 (Fioletov et al.
2023, ESSD 15, 75), file https://so2.gsfc.nasa.gov/kml/Catalogue_SO2_2025.xls (public, no login).
Annual emissions in kt SO2/yr, 2005-2025, merged from OMI, OMPS and TROPOMI. Columns y2005..
are the emission estimates, s.... their uncertainties.

Each smelter in smelters.csv is matched to the nearest catalogue source of type "Smelter" within
--max-km (the catalogue's position is the fitted plume centre, so a few km offset is normal).

Usage:
    python so2_catalog.py CATALOGUE.xls smelters.csv OUT.csv [--max-km 20]
"""
import argparse, math
import pandas as pd


def km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = 0.5 - math.cos((lat2 - lat1) * p) / 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2
    return 12742 * math.asin(math.sqrt(a))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("xls"); ap.add_argument("smelters"); ap.add_argument("out")
    ap.add_argument("--max-km", type=float, default=20)
    a = ap.parse_args()
    cat = pd.read_excel(a.xls, "Catalogue")
    sm = pd.read_csv(a.smelters)
    rows = []
    for s in sm.itertuples():
        d = cat.apply(lambda r: km(s.lat, s.lon, r.LATITUDE, r.LONGITUDE), axis=1)
        c = cat.assign(dist=d)
        c = c[(c.dist <= a.max_km) & (c.TYPE.str.strip() == "Smelter")].sort_values("dist")
        if c.empty:
            continue
        r = c.iloc[0]
        for y in range(2005, 2026):
            rows.append(dict(smelter=s.id, source_number=int(r.NUMBER), source_name=r.NAME, comment=r.COMMENT,
                             dist_km=round(r.dist, 1), year=y, so2_kt=r[f"y{y}"], so2_sd=r[f"s{y}"]))
    out = pd.DataFrame(rows)
    out.to_csv(a.out, index=False)
    print(out.groupby("smelter").agg(src=("source_name", "first"), dist=("dist_km", "first")).to_string())


if __name__ == "__main__":
    main()
