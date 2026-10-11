#!/usr/bin/env python3
"""Final wheat outturns (area, yield, production) for Russia, Ukraine, Kazakhstan (+ US).

Sources
  * FAOSTAT QCL bulk file (national statistics: Rosstat, Ukrstat, Kazakh Bureau of National
    Statistics as reported to FAO), https://bulks-faostat.fao.org/production/
    Production_Crops_Livestock_E_All_Data_(Normalized).zip
  * USDA FAS PSD current snapshot, https://apps.fas.usda.gov/psdonline/downloads/psd_grains_pulses_csv.zip
    (area harvested, yield, production as USDA carries them today; NOT a vintage).
  * USDA WASDE last vintage per market year (from data/benchmark/wasde_wheat_vintages.csv):
    the "USDA final" used as truth for the revision and model tests, so that truth and
    the USDA forecasts share one definition (USDA excludes Crimea from both Russia and Ukraine).

Usage: python fetch_finals.py --raw SCRATCH/raw/finals --wasde data/benchmark/wasde_wheat_vintages.csv \
          --out data/benchmark/final_outturns.csv
"""
import argparse
import os
import subprocess
import zipfile

import pandas as pd

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
FAO = "https://bulks-faostat.fao.org/production/Production_Crops_Livestock_E_All_Data_(Normalized).zip"
PSD = "https://apps.fas.usda.gov/psdonline/downloads/psd_grains_pulses_csv.zip"
FAO_AREAS = {"Russian Federation": "Russia", "Ukraine": "Ukraine", "Kazakhstan": "Kazakhstan",
             "United States of America": "United States"}
PSD_AREAS = {"Russia": "Russia", "Ukraine": "Ukraine", "Kazakhstan": "Kazakhstan", "United States": "United States"}


def dl(url, fn):
    if not os.path.exists(fn):
        subprocess.run(["curl", "-sS", "-L", "-A", UA, "-o", fn, url], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--wasde", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.raw, exist_ok=True)
    rows = []
    f1 = os.path.join(a.raw, "faostat_qcl.zip")
    dl(FAO, f1)
    z = zipfile.ZipFile(f1)
    name = [n for n in z.namelist() if n.endswith(".csv") and "All_Data" in n][0]
    it = pd.read_csv(z.open(name), encoding="latin1", usecols=["Area", "Item", "Element", "Year", "Unit", "Value"],
                     chunksize=500000)
    for ch in it:
        ch = ch[(ch.Item == "Wheat") & ch.Area.isin(FAO_AREAS)]
        rows.append(ch)
    f = pd.concat(rows)
    var = {"Area harvested": ("harvested_area", 1e-3), "Yield": ("yield", None), "Production": ("production", 1e-6)}
    out = []
    for r in f.itertuples():
        if r.Element not in var:
            continue
        v, sc = var[r.Element]
        val = r.Value
        if v == "yield":
            val = val / 1000 if r.Unit in ("kg/ha",) else val / 10000  # hg/ha -> t/ha
            unit = "t/ha"
        else:
            val = val * sc
            unit = "kha" if v == "harvested_area" else "mmt"
        out.append(dict(source="faostat", country=FAO_AREAS[r.Area], crop_year=int(r.Year), variable=v,
                        value=round(val, 4), unit=unit))
    f2 = os.path.join(a.raw, "psd_grains.zip")
    dl(PSD, f2)
    z = zipfile.ZipFile(f2)
    p = pd.read_csv(z.open(z.namelist()[0]))
    p = p[(p.Commodity_Description == "Wheat") & p.Country_Name.isin(PSD_AREAS)]
    pv = {"Area Harvested": ("harvested_area", "kha"), "Yield": ("yield", "t/ha"), "Production": ("production", "mmt")}
    for r in p.itertuples():
        if r.Attribute_Description not in pv:
            continue
        v, u = pv[r.Attribute_Description]
        val = r.Value / 1000 if v == "production" else r.Value
        out.append(dict(source="usda_psd_current", country=PSD_AREAS[r.Country_Name], crop_year=int(r.Market_Year),
                        variable=v, value=val, unit=u))
    w = pd.read_csv(a.wasde)
    w = w[(w.attribute == "Production") & w.region.isin(PSD_AREAS)]
    last = w.sort_values("release_date").groupby(["region", "crop_year"]).tail(1)
    for r in last.itertuples():
        out.append(dict(source="usda_wasde_last", country=r.region, crop_year=r.crop_year, variable="production",
                        value=r.value_mmt, unit="mmt", note=f"last WASDE {r.release_date} ({r.proj_flag})"))
    o = pd.DataFrame(out).sort_values(["country", "variable", "source", "crop_year"])
    o = o[o.crop_year >= 1995]
    o.to_csv(a.out, index=False)
    q = o[(o.variable == "production") & (o.crop_year >= 2005)].pivot_table(index=["country", "crop_year"], columns="source", values="value")
    print(q.loc["Russia"].round(1).to_string())


if __name__ == "__main__":
    main()
