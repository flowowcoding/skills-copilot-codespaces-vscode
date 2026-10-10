#!/usr/bin/env python3
"""Assemble the tidy, versioned point-in-time (PIT) dataset and the final
outturn table.

PIT dataset: one row per (source, release, crop_year, region, variable):
    source            conab | ibge_lspa | usda_wasde
    vintage_id        e.g. conab_2021-22_L05, ibge_lspa_202203, usda_wasde_2022-03-09
    release_date      local calendar date of publication
    release_ts_utc    publication timestamp (UTC)
    date_quality      page | page_year_repaired | ibge_calendar | ibge_news | approx | usda_official
    crop_year         Brazilian crop year 'YYYY/YY' (planting Sep-Dec YYYY, harvest Jan-Jun YYYY+1).
                      WASDE Brazil market year 'YYYY/YY' == same crop. IBGE harvest year Y -> (Y-1)/Y.
    region            BR, UF codes (MT, PR, ...), macro-regions (Conab), US/AR/WORLD (WASDE context)
    variable          planted_area (kha), harvested_area (kha), yield (kg/ha), production (kt),
                      WASDE balance items (kt): beginning_stocks, imports, domestic_crush,
                      domestic_total, exports, ending_stocks
    value, unit
    is_current_crop   1 if crop_year is the survey's own crop (Conab current column; WASDE:
                      the newest market year in the report; IBGE: always 1)
    source_url

Finals table (final_outturns.csv): latest Conab vintage, latest IBGE LSPA,
IBGE PAM (definitive municipal survey, SIDRA 1612), latest WASDE (== USDA PSD).

Usage:
    python build_dataset.py --interim DIR --out DIR
"""
import argparse
import json
import os
import subprocess

import pandas as pd

UF_IBGE = {11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO", 21: "MA", 22: "PI", 23: "CE",
           24: "RN", 25: "PB", 26: "PE", 27: "AL", 28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP",
           41: "PR", 42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF"}
UNITS = {"planted_area": "kha", "harvested_area": "kha", "yield": "kg/ha"}
WREG = {"Brazil": "BR", "United States": "US", "Argentina": "AR", "World": "WORLD"}


def to_utc(local, tz):
    return pd.to_datetime(local).dt.tz_localize(tz, ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")


def conab(interim):
    c = pd.read_csv(os.path.join(interim, "conab_soy_vintages.csv"))
    out = pd.DataFrame({
        "source": "conab",
        "vintage_id": "conab_" + c.survey_crop_year.str.replace("/", "-") + "_L" + c.levantamento.map("{:02d}".format),
        "release_date": pd.to_datetime(c.release_datetime_brt).dt.date,
        "release_ts_utc": to_utc(c.release_datetime_brt, "America/Sao_Paulo"),
        "date_quality": c.date_quality, "crop_year": c.crop_year, "region": c.region, "variable": c.variable,
        "value": c.value, "unit": c.variable.map(UNITS).fillna("kt"), "is_current_crop": c.is_current_crop,
        "source_url": c.file_url})
    return out


def ibge(interim):
    v = pd.read_csv(os.path.join(interim, "ibge_lspa_raw.csv"), dtype={"ref_month": str})
    r = pd.read_csv(os.path.join(interim, "ibge_lspa_release_dates.csv"), dtype={"ref_month": str})
    v = v.merge(r, on="ref_month", how="left")
    y = v.ref_month.str[:4].astype(int)
    q = v.date_source.str.split(":").str[0]
    return pd.DataFrame({
        "source": "ibge_lspa", "vintage_id": "ibge_lspa_" + v.ref_month,
        "release_date": pd.to_datetime(v.release_datetime_brt).dt.date,
        "release_ts_utc": to_utc(v.release_datetime_brt, "America/Sao_Paulo"),
        "date_quality": q, "crop_year": (y - 1).astype(str) + "/" + (y % 100).map("{:02d}".format),
        "region": v.region, "variable": v.variable, "value": v.value,
        "unit": v.variable.map(UNITS).fillna("kt"), "is_current_crop": 1,
        "source_url": "https://sidra.ibge.gov.br/tabela/6588 (ref " + v.ref_month + ")"})


def wasde(interim):
    w = pd.read_csv(os.path.join(interim, "wasde_soy_vintages.csv"))
    newest = w.groupby("release_date").market_year.transform("max")
    var = w.attribute.str.lower().str.replace(" ", "_")
    return pd.DataFrame({
        "source": "usda_wasde", "vintage_id": "usda_wasde_" + w.release_date,
        "release_date": pd.to_datetime(w.release_date).dt.date,
        "release_ts_utc": to_utc(w.release_date + " 12:00", "America/New_York"),
        "date_quality": "usda_official", "crop_year": w.market_year, "region": w.region.map(WREG),
        "variable": var, "value": w.value_mt * 1000.0, "unit": "kt",
        "is_current_crop": (w.market_year == newest).astype(int),
        "source_url": ("https://esmis.nal.usda.gov/publication/world-agricultural-supply-and-demand-estimates ("
                       + w.src + ")")})


def pam():
    url = ("https://servicodados.ibge.gov.br/api/v3/agregados/1612/periodos/2004-2030/variaveis/109|216|214|112"
           "?localidades=N1[all]|N3[all]&classificacao=81[2713]")
    r = subprocess.run(["curl", "-g", "-sS", "--max-time", "300", url], capture_output=True)
    rows = []
    vmap = {"109": ("planted_area", 1e-3), "216": ("harvested_area", 1e-3), "214": ("production", 1e-3),
            "112": ("yield", 1.0)}
    for v in json.loads(r.stdout):
        name, k = vmap[str(v["id"])]
        for res in v["resultados"]:
            for s in res["series"]:
                loc = s["localidade"]
                reg = "BR" if loc["nivel"]["id"] == "N1" else UF_IBGE[int(loc["id"])]
                for p, val in s["serie"].items():
                    try:
                        rows.append(dict(crop_year=f"{int(p) - 1}/{int(p) % 100:02d}", region=reg, variable=name,
                                         value=float(val) * k))
                    except (TypeError, ValueError):
                        pass
    return pd.DataFrame(rows)


def conab_serie(interim):
    """Conab's 'Soja (serie)' sheet (latest file that still carried it): finals
    for older crops (2013/14-2017/18) by state. Stale snapshot, not a vintage."""
    f = os.path.join(interim, "conab_soja_serie_sheet_raw.csv")
    if not os.path.exists(f):
        return pd.DataFrame()
    d = pd.read_csv(f, header=None)
    hdr = d.index[d.iloc[:, 0].astype(str).str.contains("REGI", na=False)][0]
    starts = [j for j in range(d.shape[1]) if "REGI" in str(d.iloc[hdr, j])]
    labels = d.iloc[hdr + 1]
    rows = []
    for var, j0 in zip(["planted_area", "yield", "production"], starts):
        cols = [j for j in range(j0 + 1, j0 + 12) if str(labels.iloc[j]).startswith("Safra")]
        # Column labels in this sheet are stale beyond 17/18 (e.g. the column
        # labelled 'Safra 18/19' holds 138.2 Mt = the 2020/21 crop), so only the
        # crops 2013/14-2017/18, whose labels check out against known finals, are kept.
        for _, r in d.iloc[hdr + 3:].iterrows():
            reg = str(r.iloc[j0]).strip().upper()
            if not (len(reg) == 2 or reg == "BRASIL"):
                continue
            for j in cols:
                lab = str(labels.iloc[j])
                crop = "20" + lab[-5:-3] + "/" + lab[-2:]
                if crop >= "2018/19":
                    continue
                v = pd.to_numeric(r.iloc[j], errors="coerce")
                if pd.notna(v):
                    rows.append(dict(crop_year=crop, region="BR" if reg == "BRASIL" else reg, variable=var,
                                     value=float(v)))
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interim", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    d = pd.concat([conab(a.interim), ibge(a.interim), wasde(a.interim)], ignore_index=True)
    d = d.sort_values(["source", "release_ts_utc", "crop_year", "region", "variable"]).reset_index(drop=True)
    d["release_ts_utc"] = d.release_ts_utc.dt.strftime("%Y-%m-%dT%H:%MZ")
    d.to_csv(os.path.join(a.out, "pit_soy_brazil.csv"), index=False)
    d.to_parquet(os.path.join(a.out, "pit_soy_brazil.parquet"), index=False)
    print("PIT rows", len(d), d.groupby("source").vintage_id.nunique().to_dict())

    # finals
    fin = []
    for src, g in d[d.source.isin(["conab", "ibge_lspa", "usda_wasde"])].groupby("source"):
        g = g.sort_values("release_ts_utc")
        last = g.groupby(["crop_year", "region", "variable"]).tail(1)
        fin.append(last.assign(final_source=src + "_latest")[["final_source", "crop_year", "region", "variable",
                                                              "value", "unit", "release_date", "vintage_id"]])
    p = pam()
    p["unit"] = p.variable.map(UNITS).fillna("kt")
    fin.append(p.assign(final_source="ibge_pam", release_date=None, vintage_id="SIDRA 1612"))
    cs = conab_serie(a.interim)
    if len(cs):
        cs["unit"] = cs.variable.map(UNITS).fillna("kt")
        fin.append(cs.assign(final_source="conab_serie_sheet", release_date=None,
                             vintage_id="Soja (serie) sheet in a 2019/20-2021/22 levantamento file"))
    fin = pd.concat(fin, ignore_index=True)
    fin.to_csv(os.path.join(a.out, "final_outturns.csv"), index=False)
    print("finals", fin.groupby("final_source").crop_year.nunique().to_dict())


if __name__ == "__main__":
    main()
