#!/usr/bin/env python3
"""Parse NASS report text files (downloaded by fetch_nass_reports.py) into
point-in-time US corn and soybean area / yield / production vintages, national
and by state.

Reports and the value taken from each (crop year Y = the season being reported):
  Prospective Plantings (end-March, Y)    planted area, intentions for Y
  Acreage (end-June, Y)                   planted area and harvested-for-grain area for Y
  Crop Production (Aug, Sep, Oct, Nov, Y) harvested area, yield, production forecasts for Y
  Crop Production Annual Summary (Jan Y+1) "final" planted, harvested, yield, production for Y
                                          (later revised by NASS; the January vintage is kept)

Table detection is generic: a table whose title starts with "Corn"/"Corn for
Grain"/"Soybeans"/"Soybean"/"Soybeans for Beans" followed by "Area" or "Yield"
(excluding silage). Column groups are read from the header (planted / harvested
/ yield / production / percent) and the LAST column of each group is the
current-year value. Rows: full state names (2009+) or postal codes (2005-2010);
the "United States"/"US" row is region US.

Release time: 08:30 ET until 2012, 12:00 ET from 11-Jan-2013 (USDA notice of
19-Sep-2012, https://www.usda.gov/sites/default/files/documents/USDA_Release_time_change_9_19_12.pdf).

Usage:
    python -I parse_nass.py --manifest RAW/manifest.csv --out OUT.csv
Output columns: source, report, release_date, release_time_et, release_ts_utc,
crop, crop_year, marketing_year, region, variable, value, unit, file, source_url
"""
import argparse
import re

import numpy as np
import pandas as pd

STATES = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA", "Colorado": "CO",
    "Connecticut": "CT", "Delaware": "DE", "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA",
    "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY", "North Carolina": "NC",
    "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA",
    "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX",
    "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY", "United States": "US", "US": "US", "U.S.": "US",
}
CODES = set(STATES.values())
TITLE = {
    "corn": re.compile(r"^\s*Corn(?: for Grain)?\s*:?\s+(Area|Yield)", re.I),
    "soybeans": re.compile(r"^\s*Soybeans?(?: for Beans)?\s*:?\s+(Area|Yield)", re.I),
}
SLUG_REPORT = {
    "prospective-plantings": "prospective_plantings",
    "acreage": "acreage",
    "crop-production": "crop_production",
    "crop-production-annual-summary": "crop_production_annual",
}
NUM = re.compile(r"^-?[\d,]+(?:\.\d+)?$")
UNITS = {"planted_area": "1000 acres", "harvested_area": "1000 acres", "yield": "bu/acre",
         "production": "1000 bu"}


def tok2num(t):
    if NUM.match(t):
        return float(t.replace(",", ""))
    if re.match(r"^\((NA|D|X|Z|S)\)$", t) or t in ("-", "(NA)"):
        return np.nan
    return None


def parse_row(line):
    m = re.match(r"^\s*([A-Za-z][A-Za-z .']*?)\s*(\d/)?\s*\.*\s*:(.*)$", line)
    if not m:
        return None, None
    name = m.group(1).strip().rstrip(".").strip()
    if name in STATES:
        code = STATES[name]
    elif name.upper() in CODES and len(name) == 2:
        code = name.upper()
    else:
        return None, None
    vals = []
    for t in m.group(3).split():
        v = tok2num(t)
        if v is None:
            return None, None
        vals.append(v)
    return code, vals


def header_groups(header):
    """Ordered measure groups as they appear in the column-header text."""
    h = header.lower()
    keys = {"planted": "planted_area", "harvested": "harvested_area", "yield": "yield", "production": "production",
            "percent": "percent", "previous year": "percent"}
    pos = []
    for k, v in keys.items():
        i = h.find(k)
        if i >= 0 and v not in [p[1] for p in pos]:
            pos.append((i, v))
    return [v for _, v in sorted(pos)]


def column_map(groups, n, header=""):
    if not groups:
        return {}
    if groups == ["harvested_area", "yield", "production"] and n == 7:
        # old layout: either production shows 3 years (Aug) or yield shows prev year,
        # previous-month forecast and current forecast (Sep-Nov: "Aug 1 : Sep 1")
        if re.search(r"\b(Aug|Sep|Oct|Nov)\w*\.?\s+1\b", header):
            return {"harvested_area": 1, "yield": 4, "production": 6}
        return {"harvested_area": 1, "yield": 3, "production": 6}
    g = len(groups)
    if "percent" in groups:  # percent-of-previous-year column is a single trailing column
        core = [x for x in groups if x != "percent"]
        k = (n - 1) // max(len(core), 1)
        return {x: (i + 1) * k - 1 for i, x in enumerate(core)}
    if n % g:
        return {}
    k = n // g
    return {x: (i + 1) * k - 1 for i, x in enumerate(groups)}


def parse_file(path, slug):
    lines = open(path, encoding="latin1").read().splitlines()
    out = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        crop = next((c for c, rx in TITLE.items() if rx.match(ln)), None)
        if crop is None or "....." in ln or "silage" in ln.lower() or "objective" in ln.lower():
            i += 1
            continue
        title = ln + " " + (lines[i + 1] if i + 1 < len(lines) else "")
        if "....." in title or re.search(r"(irrigat|non-?irrig|biotech|genetically|type|percent of|condition|"
                                          r"harvest(ed)? progress|stocks|price|value)", title, re.I):
            i += 1
            continue
        # header: after first dashed line until first data row
        j, header, started = i + 1, [], False
        rows, years = [], []
        while j < len(lines) and j < i + 120:
            s = lines[j]
            if re.match(r"^\s*-{20,}", s):
                started = True
                j += 1
                continue
            code, vals = parse_row(s) if started else (None, None)
            if code is None:
                if started and not rows:
                    header.append(s)
                    years += re.findall(r"\b(20\d\d|19\d\d)\b", s)
                if rows and TITLE["corn"].match(s) or rows and TITLE["soybeans"].match(s):
                    break
                j += 1
                continue
            rows.append((code, vals))
            j += 1
            if code == "US":
                break
        if not rows or rows[-1][0] != "US":
            i += 1
            continue
        groups = header_groups(" ".join(header))
        n = max(len(v) for _, v in rows)
        cmap = column_map(groups, n, " ".join(header))
        year = int(max(years)) if years else None
        for code, vals in rows:
            if len(vals) != n:
                continue
            for var, idx in cmap.items():
                out.append({"crop": crop, "region": code, "variable": var, "value": vals[idx], "crop_year": year,
                            "table_title": title.strip()[:120], "groups": "|".join(groups), "ncols": n})
        i = j
    return out


def release_time(d):
    return "08:30" if pd.Timestamp(d) < pd.Timestamp("2013-01-11") else "12:00"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    man = pd.read_csv(a.manifest)
    man = man[man.slug.isin(SLUG_REPORT)]
    recs = []
    for r in man.itertuples():
        d = pd.Timestamp(r.release_date)
        rep = SLUG_REPORT[r.slug]
        if rep == "crop_production" and d.month not in (8, 9, 10, 11):
            continue
        if "Notice" in r.file:
            continue
        for x in parse_file(r.local_path, r.slug):
            x.update(report=rep, release_date=r.release_date, file=r.file, source_url=r.url)
            recs.append(x)
    df = pd.DataFrame(recs)
    d = pd.to_datetime(df.release_date)
    # expected crop year for each report; drop tables about other years (e.g. previous-year tables)
    exp = np.where(df.report == "crop_production_annual", d.dt.year - 1, d.dt.year)
    bad = df.crop_year != exp
    print("dropped rows whose table year != expected crop year:", int(bad.sum()))
    df = df[~bad].copy()
    # keep table measures relevant to each report
    keep = {"prospective_plantings": {"planted_area"}, "acreage": {"planted_area", "harvested_area"},
            "crop_production": {"harvested_area", "yield", "production"},
            "crop_production_annual": {"planted_area", "harvested_area", "yield", "production"}}
    df = df[[v in keep[r] for r, v in zip(df.report, df.variable)]]
    # a revised file (…_revision.txt) supersedes the original of the same date
    df["is_rev"] = df.file.str.contains("revision")
    df = (df.sort_values(["is_rev"]).drop_duplicates(["report", "release_date", "crop", "region", "variable"],
                                                      keep="last"))
    df["release_time_et"] = df.release_date.map(release_time)
    ts = pd.to_datetime(df.release_date + " " + df.release_time_et).dt.tz_localize("America/New_York")
    df["release_ts_utc"] = ts.dt.tz_convert("UTC").dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    df["marketing_year"] = df.crop_year.astype(int).astype(str) + "/" + ((df.crop_year.astype(int) + 1) % 100).map(
        "{:02d}".format)
    df["unit"] = df.variable.map(UNITS)
    df["source"] = "usda_nass"
    cols = ["source", "report", "release_date", "release_time_et", "release_ts_utc", "crop", "crop_year",
            "marketing_year", "region", "variable", "value", "unit", "file", "source_url", "table_title"]
    df = df[cols].sort_values(["release_date", "crop", "variable", "region"])
    df.to_csv(a.out, index=False)
    us = df[df.region == "US"]
    print(len(df), "rows;", us.groupby(["report", "crop", "variable"]).release_date.nunique().to_string())


if __name__ == "__main__":
    main()
