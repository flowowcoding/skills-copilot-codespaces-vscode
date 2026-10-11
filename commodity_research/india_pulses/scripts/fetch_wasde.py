"""USDA WASDE vintages of India cotton (production, as published each month), Apr 2010 onward.

Source: USDA OCE "Historical WASDE Report Data" CSVs, links listed on
https://usda.azureedge.us/historical-wasde-report-data-3 (www.usda.gov returns 403 here, the azureedge
mirror serves the same files). WASDE has no India sugar or pulse lines; India cotton is the only India
crop of interest it covers. Release: 12:00 ET on ReleaseDate.

Output: ../data/wasde_india_cotton_vintages.csv (release_date, market_year, attribute, value, unit, proj_flag)
Usage:  python fetch_wasde.py --work <scratch>/india/raw/wasde --out ../data
"""
import argparse, glob, io, os, re, subprocess, zipfile
import pandas as pd

PAGE = "https://usda.azureedge.us/historical-wasde-report-data-3"


def curl(url, fn):
    subprocess.run(["curl", "-s", "-L", "-m", "300", "-A", "Mozilla/5.0", "-o", fn, url], check=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    curl(PAGE, f"{a.work}/page.html")
    links = re.findall(r'href="([^"]+\.(?:csv|zip))"', open(f"{a.work}/page.html").read())
    for u in links:
        path = u.split("/sites/", 1)[1]
        fn = f"{a.work}/{os.path.basename(path)}"
        if not os.path.exists(fn) or os.path.getsize(fn) < 5000:
            curl("https://usda.azureedge.us/sites/" + path, fn)
    frames = []
    for fn in sorted(glob.glob(f"{a.work}/*.csv")) + sorted(glob.glob(f"{a.work}/*.zip")):
        srcs = []
        if fn.endswith(".zip"):
            z = zipfile.ZipFile(fn); srcs = [io.BytesIO(z.read(n)) for n in z.namelist() if n.endswith(".csv")]
        else:
            srcs = [fn]
        for s in srcs:
            x = pd.read_csv(s, dtype=str, encoding="latin1")
            x = x[(x.Region == "India") & (x.Commodity == "Cotton") & (x.Attribute.isin(["Production", "Exports", "Imports", "Ending Stocks"]))]
            frames.append(x)
    d = pd.concat(frames).drop_duplicates()
    d = d.rename(columns={"ReleaseDate": "release_date", "MarketYear": "market_year", "Attribute": "attribute", "Value": "value",
                          "Unit": "unit", "ProjEstFlag": "proj_flag"})[["release_date", "market_year", "attribute", "value", "unit", "proj_flag"]]
    d["value"] = pd.to_numeric(d.value, errors="coerce")
    d["release_date"] = pd.to_datetime(d.release_date, format="mixed").dt.date
    d = d.sort_values(["release_date", "market_year", "attribute"]).drop_duplicates(["release_date", "market_year", "attribute"], keep="last")
    d.to_csv(f"{a.out}/wasde_india_cotton_vintages.csv", index=False)
    print(d.release_date.min(), d.release_date.max(), len(d))


if __name__ == "__main__":
    main()
