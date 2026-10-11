#!/usr/bin/env python3
"""Turn the auto-extracted IKAR-archive candidates into a reviewed table of dated private /
ministry Russian wheat production estimates.

Rules (all point-in-time; no use of the final outturn):
  1. Russia only: the sentence or the item title mentions Russia/Russian, or the forecaster is
     IKAR / SovEcon / the Russian agriculture ministry; sentences about other countries
     (Ukraine, Kazakhstan, France, US, EU ...) are dropped.
  2. Not a harvest-progress or past figure: drop sentences with "harvested", "threshed",
     "reaped", "so far", "as of", "by <weekday>", "last year", "in <past year> when",
     "versus/compared with ... in <past year>", "record of", "averag".
  3. Not a partial crop: drop "winter wheat" / "spring wheat" only figures, and export,
     total-grain, stocks figures (keyword filter from the extractor).
  4. Exactly one named forecaster in the sentence; if none, the forecaster named in the item
     title is used ("The consultancy cut ..."). USDA and IGC rows are dropped (not private).
     Forecasters kept: IKAR, SovEcon, MinAg (Russian agriculture ministry / minister),
     ProZerno, Rusagrotrans, Grain Union.
  5. Plausibility vs information available then: value within +-35 % of the latest USDA WASDE
     Russia estimate for that crop year published before the item (before May: USDA's
     estimate of the previous crop).
  6. Same forecaster, same value, reposted within 10 days -> first date kept.
  7. Manual overrides: data/private/manual_overrides.csv (id, value, include, note) fixes rows
     checked by reading the item (ranges -> midpoint, "from" values, scenarios, mis-assigned years).
  8. Manual additions: data/private/manual_additions.csv, dated estimates for 2010, 2018 and May
     2024 found by web search (Moscow Times / S&P / Miller Magazine / IKAR items), with URL.
Ranges "X-Y million" keep the upper bound in the extractor; ranges are flagged in the README.

Usage: python clean_private_estimates.py
Writes data/private/private_estimates.csv
"""
import os
import re

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "..", "data")
KEEP_F = {"IKAR", "SovEcon", "MinAg", "ProZerno", "Rusagrotrans", "Grain Union"}
PAST = (r"harvested|threshed|reaped|so far|as of|by (monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
        r"last year|last season|previous year|when (the country|russia) harvested|record of|averag|in 20\d\d when|"
        r"compared (with|to) .{0,40}(20\d\d|last)|versus .{0,30}(20\d\d|last)|from last|down from \d|up from \d")
OTHER = r"Ukrain|Kazakh|France|French|Germany|German|U\.S\.|United States|Canad|Australia|Argentin|India|China|EU\b|European|Turkey|Egypt|Romania|Bulgaria"


def title_forecaster(t):
    for f, p in [("IKAR", r"IKAR|Ikar"), ("SovEcon", r"Sovecon|SovEcon"), ("MinAg", r"[Mm]inistry|[Mm]inister"),
                 ("ProZerno", r"ProZerno"), ("Rusagrotrans", r"Rusagrotrans")]:
        if re.search(p, str(t)):
            return f
    return ""


def main():
    c = pd.read_csv(os.path.join(D, "private", "private_estimates_candidates.csv"), parse_dates=["pub_date"])
    w = pd.read_csv(os.path.join(D, "benchmark", "wasde_wheat_vintages.csv"), parse_dates=["release_date"])
    w = w[(w.region == "Russia") & (w.attribute == "Production")].sort_values("release_date")
    c["reason"] = ""
    s = c.sentence.fillna("")
    russia = s.str.contains(r"Russia", case=False) | c.title.str.contains(r"Russia", case=False) | c.forecaster.fillna("").str.contains("IKAR|SovEcon|MinAg")
    c.loc[~russia, "reason"] += "not_russia;"
    c.loc[s.str.contains(OTHER), "reason"] += "other_country;"
    c.loc[s.str.contains(PAST, case=False, regex=True), "reason"] += "past_or_progress;"
    c.loc[s.str.contains(r"winter wheat|spring wheat", case=False), "reason"] += "partial_crop;"
    c.loc[c.bad_keyword, "reason"] += "keyword;"
    f = c.forecaster.fillna("")
    nf = f.str.split(";").map(lambda x: len([y for y in x if y]))
    c.loc[nf > 1, "reason"] += "multi_forecaster;"
    c["forecaster_final"] = np.where(nf == 1, f, c.title.map(title_forecaster))
    c.loc[~c.forecaster_final.isin(KEEP_F), "reason"] += "no_private_forecaster;"
    # plausibility vs the USDA estimate available at the time
    ref = []
    for r in c.itertuples():
        q = w[(w.crop_year == r.crop_year) & (w.release_date < r.pub_date)]
        if q.empty:
            q = w[(w.crop_year == r.crop_year - 1) & (w.release_date < r.pub_date)]
        ref.append(q.value_mmt.iloc[-1] if len(q) else np.nan)
    c["usda_ref"] = ref
    bad = (c.value_mmt / c.usda_ref - 1).abs() > 0.35
    c.loc[bad | c.usda_ref.isna(), "reason"] += "implausible;"
    mo = os.path.join(D, "private", "manual_overrides.csv")
    c["note"] = ""
    if os.path.exists(mo):
        m = pd.read_csv(mo)
        for r in m.itertuples():
            i = c.index[(c.ikar_id == r.ikar_id) & ((c.value_mmt - r.old_value).abs() < 1e-6)]
            for j in i:
                if not pd.isna(r.new_value):
                    c.loc[j, "value_mmt"] = r.new_value
                if not pd.isna(r.crop_year):
                    c.loc[j, "crop_year"] = int(r.crop_year)
                if not pd.isna(r.forecaster):
                    c.loc[j, "forecaster_final"] = r.forecaster
                c.loc[j, "reason"] = "" if r.include == 1 else "manual_exclude;"
                c.loc[j, "note"] = r.note
    c["include"] = (c.reason == "").astype(int)
    ma = os.path.join(D, "private", "manual_additions.csv")
    if os.path.exists(ma):
        m = pd.read_csv(ma, parse_dates=["pub_date"])
        m = m.rename(columns={"forecaster": "forecaster_final"}).assign(include=1, reason="", ikar_id=np.nan,
                                                                      source_agency="manual", title="", sentence="")
        c = pd.concat([c, m], ignore_index=True)
    k = c[c.include == 1].sort_values("pub_date")
    keep = []
    last = {}
    for i, r in k.iterrows():
        key = (r.forecaster_final, r.crop_year, r.value_mmt)
        if key in last and (r.pub_date - last[key]).days <= 10:
            c.loc[i, "include"] = 0
            c.loc[i, "reason"] = "repost;"
            continue
        last[key] = r.pub_date
    out = c.rename(columns={"forecaster": "forecaster_raw", "forecaster_final": "forecaster"})
    out = out[["pub_date", "forecaster", "crop_year", "value_mmt", "include", "reason", "usda_ref", "ikar_id",
               "source_agency", "title", "sentence", "url", "note"]].sort_values(["pub_date", "forecaster"])
    out.to_csv(os.path.join(D, "private", "private_estimates.csv"), index=False)
    inc = out[out.include == 1]
    print("included", len(inc), inc.groupby("forecaster").size().to_dict())
    print(inc.groupby("crop_year").size().to_dict())


if __name__ == "__main__":
    main()
