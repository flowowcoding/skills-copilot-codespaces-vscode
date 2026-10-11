"""Point-in-time vintages of Government of India production estimates (tur, gram, sugarcane, cotton).

Source: Ministry of Agriculture & Farmers Welfare press releases on PIB (https://www.pib.gov.in/
PressReleasePage.aspx?PRID=<prid>), found with fetch_pib_index.py and downloaded with
fetch_pib_releases.py, plus the "Time Series" PDF tables attached to them (static.pib.gov.in).
Values were transcribed from the release text (headline list) and checked against the attached tables;
where a release is missing from PIB (2016-17 4th AE, 2019-20 4th AE) the value comes from the
"previous year" column of a later release's table and its date is the date that later release was
posted (conservative: it was public no later than that).

Units: tur, gram, sugarcane in million tonnes; cotton in million bales of 170 kg.
Stages: AE1..AE4 (advance estimates), FINAL. From 2022-23 the 4th AE was dropped and the final moved
to Sep-Nov after the season (no longer with the next February release).

Seasons before 2016-17: only FINAL values are available here (from the time-series tables). Their
public date is approximated as Feb 15 of (season end year + 1), the then-usual release with the next
2nd AE (flagged date_approx=1). Crop-level advance-estimate vintages before 2016-17 are not
reachable (desagri.gov.in and the pre-2017 PIB archive are blocked from this environment).

Seasons 1995-96 .. 2002-03 (added after the pre-registration, before any holdout evaluation, because the
walk-forward trend needs >= 6 earlier finals and the official time-series tables start in 2003-04):
FINAL = ICRISAT district-level production summed over its 311 districts, divided by the median ratio
(ICRISAT sum / official final) over the overlap seasons 2003-04 .. 2008-09 (gram 1.00, tur 0.97,
sugarcane 0.101 -- ICRISAT's cane production is in different units). date_approx = 2 (proxy).

Output: ../data/ae_vintages.csv (crop, season, stage, value, unit, release_date, date_approx, prid, url, note)
Usage:  python build_benchmark.py --out ../data
"""
import argparse
import pandas as pd

U = "https://www.pib.gov.in/PressReleasePage.aspx?PRID={}"
# (season, stage, release_date, prid, tur, gram, sugarcane, cotton, note)
V = [
    ("2016-17", "AE2", "2017-02-15", 1482805, 4.23, 9.12, 309.98, 32.51, ""),
    ("2016-17", "AE3", "2017-05-09", 1489532, 4.60, 9.08, 306.03, 32.58, ""),
    ("2016-17", "AE4", "2017-09-25", 1503909, None, None, 306.72, 33.09, "4th AE release not on PIB; cane/cotton from 'last year' figures in 2017-18 AE1 text"),
    ("2016-17", "FINAL", "2018-05-16", 1532333, 4.87, 9.38, 306.069, 32.577, "first seen as 'Final' in 2017-18 AE3 table"),
    ("2017-18", "AE1", "2017-09-25", 1503909, 3.99, None, 337.69, 32.27, ""),
    ("2017-18", "AE2", "2018-02-27", 1521936, 4.02, 11.10, 353.23, 33.92, ""),
    ("2017-18", "AE3", "2018-05-16", 1532333, 4.18, 11.16, 355.10, 34.86, ""),
    ("2017-18", "AE4", "2018-08-29", 1544375, 4.25, 11.23, 376.91, 34.89, ""),
    ("2017-18", "FINAL", "2019-06-03", 1573283, 4.29, 11.38, 379.905, 32.805, "first seen as 'Final' in 2018-19 AE3 table"),
    ("2018-19", "AE1", "2018-09-26", 1547282, 4.08, None, 383.89, 32.48, ""),
    ("2018-19", "AE2", "2019-02-28", 1566589, 3.68, 10.32, 380.83, 30.09, ""),
    ("2018-19", "AE3", "2019-06-03", 1573283, 3.50, 10.09, 400.37, 27.59, ""),
    ("2018-19", "AE4", "2019-08-19", 1582362, 3.59, 10.13, 400.16, 28.71, ""),
    ("2018-19", "FINAL", "2020-02-18", 1603539, 3.315, 9.938, 405.416, 28.042, "history column of 2019-20 AE2 table (LMT precision from 2023 tables)"),
    ("2019-20", "AE1", "2019-09-23", 1585878, 3.54, None, 377.77, 32.27, ""),
    ("2019-20", "AE2", "2020-02-18", 1603539, 3.69, 11.22, 353.85, 34.89, ""),
    ("2019-20", "AE3", "2020-05-15", 1624044, 3.75, 10.90, 358.14, 36.05, ""),
    ("2019-20", "AE4", "2020-09-22", 1657839, 3.83, 11.35, 355.70, 35.491, "4th AE release not on PIB; from '4th Adv.Est.' column of 2020-21 AE1 table"),
    ("2019-20", "FINAL", "2021-02-24", 1700545, 3.892, 11.078, 370.50, 36.065, ""),
    ("2020-21", "AE1", "2020-09-22", 1657839, 4.04, None, 399.83, 37.12, ""),
    ("2020-21", "AE2", "2021-02-24", 1700545, 3.88, 11.62, 397.66, 36.54, ""),
    ("2020-21", "AE3", "2021-05-25", 1721692, 4.14, 12.61, 392.80, 36.49, ""),
    ("2020-21", "AE4", "2021-08-11", 1744934, 4.28, 11.99, 399.25, 35.38, ""),
    ("2020-21", "FINAL", "2022-02-16", 1798835, 4.316, 11.911, 405.399, 35.248, ""),
    ("2021-22", "AE1", "2021-09-21", 1756743, 4.43, None, 419.25, 36.22, ""),
    ("2021-22", "AE2", "2022-02-16", 1798835, 4.00, 13.12, 414.04, 34.06, ""),
    ("2021-22", "AE3", "2022-05-19", 1826742, 4.35, 13.98, 430.499, 31.54, ""),
    ("2021-22", "AE4", "2022-08-17", 1852470, 4.34, 13.75, 431.812, 31.20, ""),
    ("2021-22", "FINAL", "2023-02-14", 1899193, 4.220, 13.544, 439.425, 31.118, ""),
    ("2022-23", "AE1", "2022-09-21", 1861223, 3.89, None, 465.05, 34.19, ""),
    ("2022-23", "AE2", "2023-02-14", 1899193, 3.666, 13.632, 468.789, 33.723, ""),
    ("2022-23", "AE3", "2023-05-25", 1927272, 3.430, 13.543, 494.228, 34.347, ""),
    ("2022-23", "FINAL", "2023-10-18", 1968931, 3.312, 12.267, 490.533, 33.660, ""),
    ("2023-24", "AE1", "2023-10-27", 1972233, 3.421, None, 434.793, 31.657, ""),
    ("2023-24", "AE2", "2024-02-29", 2010380, 3.339, 12.161, 446.430, 32.311, ""),
    ("2023-24", "AE3", "2024-06-04", 2022740, 3.385, 11.576, 442.522, 32.522, ""),
    ("2023-24", "FINAL", "2024-09-25", 2058534, 3.417, 11.039, 453.158, 32.522, ""),
    ("2024-25", "AE1", "2024-11-05", 2070834, 3.502, None, 439.930, 29.926, ""),
    ("2024-25", "AE2", "2025-03-10", 2109884, 3.511, 11.535, 435.079, 29.425, ""),
    ("2024-25", "AE3", "2025-05-28", 2132263, 3.561, 11.337, 450.116, 30.692, ""),
    ("2024-25", "FINAL", "2025-11-20", 2192315, 3.624, 11.114, 454.611, 29.724, ""),
    ("2025-26", "AE1", "2025-11-26", 2194726, 3.597, None, 475.614, 29.215, ""),
    ("2025-26", "AE2", "2026-03-10", 2237560, 3.455, 11.792, 500.197, 29.091, ""),
    ("2025-26", "AE3", "2026-05-27", 2265965, 3.592, 12.514, 500.063, 29.024, ""),
]
# finals before 2016-17 (time-series tables in PRID 1532333 / 1899193); cane, cotton from lakh units
HIST = {
    "tur": [2.36, 2.35, 2.74, 2.31, 3.08, 2.27, 2.46, 2.86, 2.65, 3.020, 3.174, 2.807, 2.561],
    "gram": [5.72, 5.47, 5.60, 6.33, 5.75, 7.06, 7.48, 8.22, 7.70, 8.830, 9.526, 7.332, 7.058],
    "sugarcane": [233.862, 237.088, 281.172, 355.520, 348.188, 285.029, 292.302, 342.382, 361.037, 341.200, 352.142, 362.333, 348.448],
    "cotton": [13.729, 16.429, 18.499, 22.632, 25.884, 22.276, 24.022, 33.000, 35.200, 34.220, 35.902, 34.805, 30.005],
}
UNIT = {"tur": "Mt", "gram": "Mt", "sugarcane": "Mt", "cotton": "M bales (170 kg)"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--icrisat", default=None, help="district_apy_icrisat.csv (default: <out>/district_apy_icrisat.csv)")
    a = ap.parse_args()
    rows = []
    for s, st, dt, prid, *vals, note in V:
        for crop, v in zip(["tur", "gram", "sugarcane", "cotton"], vals):
            if v is not None:
                rows.append(dict(crop=crop, season=s, stage=st, value=v, unit=UNIT[crop], release_date=dt, date_approx=0,
                                 prid=prid, url=U.format(prid), note=note))
    for crop, vals in HIST.items():
        for i, v in enumerate(vals):
            y0 = 2003 + i
            rows.append(dict(crop=crop, season=f"{y0}-{str(y0 + 1)[2:]}", stage="FINAL", value=v, unit=UNIT[crop],
                             release_date=f"{y0 + 2}-02-15", date_approx=1, prid=1532333 if i < 9 else 1899193,
                             url=U.format(1532333 if i < 9 else 1899193), note="history column of a later time-series table"))
    icr = pd.read_csv(a.icrisat or f"{a.out}/district_apy_icrisat.csv")
    tot = icr.groupby(["crop", "year"]).prod_kt.sum().unstack(0) / 1000
    for crop, k in [("gram", "chickpea"), ("tur", "pigeonpea"), ("sugarcane", "sugarcane")]:
        off = pd.Series(HIST[crop][:6], index=range(2003, 2009))
        ratio = float((tot[k].loc[2003:2008] / off).median())
        for y0 in range(1995, 2003):
            rows.append(dict(crop=crop, season=f"{y0}-{str(y0 + 1)[2:]}", stage="FINAL", value=round(tot[k].loc[y0] / ratio, 3),
                             unit=UNIT[crop], release_date=f"{y0 + 2}-02-15", date_approx=2, prid=None, url="http://data.icrisat.org/dld/",
                             note=f"proxy: ICRISAT district sum / {ratio:.4f} (median ratio to official finals 2003-04..2008-09)"))
    d = pd.DataFrame(rows).sort_values(["crop", "season", "release_date"])
    d.to_csv(f"{a.out}/ae_vintages.csv", index=False)
    # revision summary: first estimate -> final
    first = {"tur": "AE1", "sugarcane": "AE1", "cotton": "AE1", "gram": "AE2"}
    p = d[d.date_approx == 0].pivot_table(index=["crop", "season"], columns="stage", values="value")
    out = []
    for (crop, s), r in p.iterrows():
        for st in ["AE1", "AE2", "AE3", "AE4"]:
            if pd.notna(r.get(st)) and pd.notna(r.get("FINAL")):
                out.append(dict(crop=crop, season=s, stage=st, first_stage=int(st == first[crop]), ae=r[st], final=r["FINAL"],
                                rev_pct=100 * (r["FINAL"] / r[st] - 1)))
    o = pd.DataFrame(out)
    o.to_csv(f"{a.out}/../results/ae_revisions.csv", index=False, float_format="%.3f")
    f = o[o.first_stage == 1]
    print(f.groupby("crop").rev_pct.agg(["count", "mean", lambda x: x.abs().mean(), "min", "max"]).round(1))
    print(o.groupby(["crop", "stage"]).rev_pct.apply(lambda x: x.abs().mean()).unstack().round(1))


if __name__ == "__main__":
    main()
