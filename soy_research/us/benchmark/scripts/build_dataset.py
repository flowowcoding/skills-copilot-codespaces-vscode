#!/usr/bin/env python3
"""Assemble the versioned point-in-time (PIT) dataset for US corn and soybeans.

Inputs (from the other scripts)
  --nass       parse_nass.py output (Crop Production, Annual Summary, Acreage, Prospective Plantings)
  --wasde      parse_wasde_us.py output (WASDE US balance-sheet lines)
  --qs         extract_quickstats.py output (weekly crop condition)
  --dates      fetch_release_dates.py output (Crop Progress release dates)
  --consensus  data/consensus/consensus_raw.csv (hand-collected, URL per value)
  --farmdoc    extract_farmdoc_decks.py output

Outputs (--out = data/)
  pit/pit_us_corn_soy.parquet   full PIT table (all states, crop condition)
  pit/pit_us_corn_soy_core.csv  US + 12 main states, area/yield/production only (<5 MB)
  consensus/consensus.csv       one row per (report, crop, variable): chosen consensus + alternatives
  interim/crop_condition.csv    weekly good/excellent % (US + 12 states) with PIT release timestamp
  pit/MANIFEST.json             version, build date, row counts, sha256

PIT schema: source, report, release_date, release_time_et, release_ts_utc, crop, crop_year,
marketing_year, region, variable, value, unit, source_url, dataset_version
  * units harmonised: area million acres, production million bu, yield bu/acre, condition %.
  * release time: 08:30 ET before 11-Jan-2013, 12:00 ET from then (NASS/WAOB); Crop Progress 16:00 ET.
  * nothing is overwritten: each (source, report, release_date) is its own vintage.

Usage:
    python -I build_dataset.py --nass N.csv --wasde W.csv --qs Q.csv.gz --dates D.csv \
        --consensus C.csv --farmdoc F.csv --out ../data
"""
import argparse
import hashlib
import json
import os

import numpy as np
import pandas as pd

VERSION = "us-corn-soy-pit v1.0"
STATES12 = ["IA", "IL", "NE", "MN", "IN", "OH", "SD", "ND", "KS", "MO", "WI", "MI"]
# preference when several sources give a consensus for the same report/variable
POLL_RANK = [("Reuters", 0), ("WILL", 1), ("farmdoc", 2), ("Bloomberg", 3), ("Dow Jones", 4), ("World-Grain", 5),
             ("Food Business", 5), ("DTN", 6), ("Pro Farmer", 6)]


def ts_utc(dates, times):
    t = pd.to_datetime(pd.Series(dates).astype(str) + " " + pd.Series(times).astype(str))
    return t.dt.tz_localize("America/New_York").dt.tz_convert("UTC").dt.strftime("%Y-%m-%dT%H:%M:%SZ").values


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def rank(row):
    s = f"{row.poll} {row.source}"
    if "approx" in s:
        return 50
    if "implied" in s:
        return 40
    return min([r for k, r in POLL_RANK if k in s] or [20])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for k in ["nass", "wasde", "qs", "dates", "consensus", "farmdoc", "out"]:
        ap.add_argument(f"--{k}", required=True)
    a = ap.parse_args()
    for d in ["pit", "consensus", "interim"]:
        os.makedirs(os.path.join(a.out, d), exist_ok=True)

    # ---- NASS report vintages
    n = pd.read_csv(a.nass)
    n["value"] = np.where(n.variable == "yield", n.value, n.value / 1000.0)
    n["unit"] = n.variable.map({"yield": "bu/acre", "production": "million bu", "planted_area": "million acres",
                                "harvested_area": "million acres"})
    n = n.drop(columns=["file", "table_title"])

    # ---- WASDE US lines (every market year shown in each report)
    w = pd.read_csv(a.wasde)
    w["report"] = "wasde"
    w["unit"] = w.variable.map({"yield": "bu/acre", "production": "million bu", "planted_area": "million acres",
                                "harvested_area": "million acres", "ending_stocks": "million bu"})
    w["wasde_flag"] = w.proj_flag
    w = w[["source", "report", "release_date", "release_time_et", "release_ts_utc", "crop", "crop_year",
           "marketing_year", "region", "variable", "value", "unit", "source_url"]]

    # ---- crop condition (weekly), timestamped at the Crop Progress release following week end
    q = pd.read_csv(a.qs, dtype=str)
    q = q[q.SHORT_DESC.str.contains("CONDITION")].copy()
    q["region"] = np.where(q.AGG_LEVEL_DESC == "NATIONAL", "US", q.STATE_ALPHA)
    q["crop"] = q.COMMODITY_DESC.str.lower()
    q["cat"] = q.SHORT_DESC.str.extract(r"PCT (.*)$")[0]
    q["v"] = pd.to_numeric(q.VALUE.str.replace(",", ""), errors="coerce")
    p = q.pivot_table(index=["crop", "region", "YEAR", "WEEK_ENDING"], columns="cat", values="v", aggfunc="first")
    p = p.reset_index()
    p["cond_ge_pct"] = p.GOOD + p.EXCELLENT
    p["cond_pvp_pct"] = p.POOR + p["VERY POOR"]
    p["cond_index"] = (5 * p.EXCELLENT + 4 * p.GOOD + 3 * p.FAIR + 2 * p.POOR + 1 * p["VERY POOR"]) / 100
    rd = pd.read_csv(a.dates)
    cp = pd.to_datetime(rd[rd.slug == "crop-progress"].release_date).sort_values().values
    we = pd.to_datetime(p.WEEK_ENDING).values
    idx = np.searchsorted(cp, we, side="right")  # first release strictly after the week-ending Sunday
    rel = np.where(idx < len(cp), cp[np.minimum(idx, len(cp) - 1)], np.datetime64("NaT", "ns"))
    # guard: release must be within 3 days of week end, else assume the Monday
    gap = (rel - we) / np.timedelta64(1, "D")
    rel = np.where((gap >= 1) & (gap <= 3), rel, we + np.timedelta64(1, "D"))
    p["release_date"] = pd.to_datetime(rel).strftime("%Y-%m-%d")
    p["date_quality"] = np.where((gap >= 1) & (gap <= 3), "esmis_calendar", "assumed_monday")
    p = p[p.region.isin(["US"] + STATES12)]
    cond = p[["crop", "region", "YEAR", "WEEK_ENDING", "release_date", "date_quality", "EXCELLENT", "GOOD", "FAIR",
              "POOR", "VERY POOR", "cond_ge_pct", "cond_pvp_pct", "cond_index"]].rename(columns={"YEAR": "crop_year"})
    cond.to_csv(os.path.join(a.out, "interim", "crop_condition.csv"), index=False)
    c_long = cond.melt(id_vars=["crop", "region", "crop_year", "release_date"],
                       value_vars=["cond_ge_pct", "cond_pvp_pct"], var_name="variable", value_name="value")
    c_long = c_long.dropna(subset=["value"])
    c_long["source"] = "usda_nass"
    c_long["report"] = "crop_progress"
    c_long["release_time_et"] = "16:00"
    c_long["release_ts_utc"] = ts_utc(c_long.release_date, c_long.release_time_et)
    c_long["crop_year"] = c_long.crop_year.astype(int)
    c_long["marketing_year"] = c_long.crop_year.astype(str) + "/" + ((c_long.crop_year + 1) % 100).map("{:02d}".format)
    c_long["unit"] = "percent of crop"
    c_long["source_url"] = "https://www.nass.usda.gov/datasets/ (Quick Stats bulk qs.crops); dates: https://esmis.nal.usda.gov/publication/crop-progress"

    pit = pd.concat([n, w, c_long[n.columns]], ignore_index=True)
    pit["dataset_version"] = VERSION
    pit = pit.sort_values(["release_ts_utc", "source", "report", "crop", "region", "marketing_year", "variable"])
    full = os.path.join(a.out, "pit", "pit_us_corn_soy.parquet")
    pit.to_parquet(full, index=False)
    core = pit[pit.region.isin(["US"] + STATES12) & (pit.report != "crop_progress")].copy()
    # keep the CSV small: short source-url keys, full URLs stay in the parquet
    core = core.drop(columns=["source_url", "dataset_version"])
    core_p = os.path.join(a.out, "pit", "pit_us_corn_soy_core.csv")
    core.to_csv(core_p, index=False, float_format="%.4f")

    # ---- consensus table
    c = pd.read_csv(a.consensus)
    f = pd.read_csv(a.farmdoc)
    f_ann = f[f.variable != "production_surprise"].drop(columns=["usda_in_deck"])
    # farmdoc bar charts: implied consensus production = USDA August production - surprise
    us = n[(n.region == "US") & (n.report == "crop_production") & (n.variable == "production")].copy()
    us["ym"] = us.release_date.str[:7]
    bars = f[f.variable == "production_surprise"].merge(us[["ym", "crop", "value", "release_date"]],
                                                       left_on=["report_date", "crop"], right_on=["ym", "crop"])
    bars = bars.assign(report_date=bars.release_date, variable="production", avg=bars.value - bars.avg,
                       poll="farmdoc average trade guess (implied)",
                       note="USDA August production minus farmdoc bar-chart surprise")
    bars = bars[[x for x in c.columns if x in bars.columns]]
    f_ann = f_ann.assign(capture="direct (page/PDF read)")
    bars = bars.assign(capture="direct (page/PDF read)")
    allc = pd.concat([c, f_ann, bars], ignore_index=True)
    allc["rank"] = allc.apply(rank, axis=1)
    allc = allc.sort_values(["report_date", "crop", "variable", "rank"])
    best = allc.groupby(["report_date", "crop", "variable"], as_index=False).first()
    alts = allc.groupby(["report_date", "crop", "variable"]).apply(
        lambda g: "; ".join(f"{r.avg:g} ({r.source})" for r in g.iloc[1:].itertuples()), include_groups=False)
    best = best.merge(alts.rename("alternatives").reset_index(), on=["report_date", "crop", "variable"])
    best["n_sources"] = allc.groupby(["report_date", "crop", "variable"]).size().values
    best = best.rename(columns={"avg": "consensus"})
    best["release_time_et"] = np.where(best.report_date < "2013-01-11", "08:30", "12:00")
    best = best[["report_date", "release_time_et", "crop", "variable", "consensus", "low", "high", "poll", "source",
                 "source_url", "capture", "n_sources", "alternatives", "note"]]
    best.to_csv(os.path.join(a.out, "consensus", "consensus.csv"), index=False)

    man = {"version": VERSION, "built": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
           "files": {}}
    for pth in [full, core_p, os.path.join(a.out, "consensus", "consensus.csv"),
                os.path.join(a.out, "interim", "crop_condition.csv")]:
        man["files"][os.path.relpath(pth, a.out)] = {"rows": int(len(pd.read_parquet(pth)) if pth.endswith(
            ".parquet") else len(pd.read_csv(pth))), "bytes": os.path.getsize(pth), "sha256": sha(pth)}
    json.dump(man, open(os.path.join(a.out, "pit", "MANIFEST.json"), "w"), indent=1)
    print(json.dumps(man, indent=1))
    print(best.groupby(["variable", "crop"]).size())


if __name__ == "__main__":
    main()
