#!/usr/bin/env python3
"""Parse the soybean table ("Soja" sheet) of every Conab levantamento
spreadsheet listed in conab_manifest.csv into long point-in-time rows.

Each spreadsheet holds two crop years: the previous one (column a/c/e) and
the current one (b/d/f). Both are recorded as vintages released on that date;
``is_current_crop`` distinguishes them (the previous-crop column is a late
revision of an already-harvested crop).

Also extracts the "Soja (serie)" sheet when present (Conab's long history of
final estimates, as published at that release), used only for the final
outturn table of pre-2019/20 crops.

Units: planted_area kha, yield kg/ha, production kt.

Usage:
    python parse_conab.py --manifest conab_manifest.csv --raw RAW_DIR --out OUT_DIR
"""
import argparse
import os
import re

import pandas as pd

REGIONS = {"NORTE", "NORDESTE", "CENTRO-OESTE", "SUDESTE", "SUL", "NORTE/NORDESTE", "CENTRO-SUL", "BRASIL",
           "RR", "RO", "AC", "AM", "AP", "PA", "TO", "MA", "PI", "CE", "RN", "PB", "PE", "AL", "SE", "BA",
           "MT", "MS", "GO", "DF", "MG", "ES", "RJ", "SP", "PR", "SC", "RS"}


def crop_from_label(lbl):
    m = re.search(r"(\d{2})/(\d{2})", str(lbl))
    return f"20{m.group(1)}/{m.group(2)}" if m else None


def parse_soja(path):
    x = pd.ExcelFile(path)
    sh = [s for s in x.sheet_names if s.strip().lower() == "soja"]
    if not sh:
        raise ValueError(f"no Soja sheet in {path}: {x.sheet_names}")
    d = x.parse(sh[0], header=None)
    hdr = d.index[d.iloc[:, 0].astype(str).str.contains("REGI", na=False)][0]
    labels = d.iloc[hdr + 1].tolist()
    prev, cur = crop_from_label(labels[1]), crop_from_label(labels[2])
    nota = " ".join(d.iloc[:, 0].dropna().astype(str).tolist())
    m = re.search(r"Estimativa em ([a-zç]+)/(\d{4})", nota, re.I)
    est = f"{m.group(1).lower()}/{m.group(2)}" if m else ""
    rows = []
    for _, r in d.iloc[hdr + 3:].iterrows():
        reg = str(r.iloc[0]).strip().upper()
        if reg not in REGIONS:
            continue
        reg = "BR" if reg == "BRASIL" else reg
        for var, (ip, ic) in {"planted_area": (1, 2), "yield": (4, 5), "production": (7, 8)}.items():
            for crop, col, curflag in ((prev, ip, 0), (cur, ic, 1)):
                v = pd.to_numeric(r.iloc[col], errors="coerce")
                if pd.notna(v):
                    rows.append(dict(crop_year=crop, region=reg, variable=var, value=float(v),
                                     is_current_crop=curflag, nota_estimativa=est))
    return pd.DataFrame(rows)


def parse_serie(path):
    x = pd.ExcelFile(path)
    sh = [s for s in x.sheet_names if s.strip().lower().startswith("soja (s")]
    if not sh:
        return None
    d = x.parse(sh[0], header=None)
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    man = pd.read_csv(a.manifest)
    out = []
    last_serie = None
    for _, m in man.iterrows():
        if not isinstance(m.local_file, str):
            print("missing file", m.crop_year, m.levantamento)
            continue
        p = os.path.join(a.raw, m.local_file)
        df = parse_soja(p)
        df["levantamento"] = m.levantamento
        df["release_datetime_brt"] = m.release_datetime_brt
        df["date_quality"] = m.date_quality
        df["survey_crop_year"] = m.crop_year
        df["file_url"] = m.file_url
        assert (df[df.is_current_crop == 1].crop_year == m.crop_year).all(), (p, df.crop_year.unique())
        out.append(df)
        s = parse_serie(p)
        if s is not None:
            last_serie = (m.release_datetime_brt, s)
    out = pd.concat(out, ignore_index=True)
    os.makedirs(a.out, exist_ok=True)
    out.to_csv(os.path.join(a.out, "conab_soy_vintages.csv"), index=False)
    print(len(out), "rows;", out.survey_crop_year.nunique(), "crop years;",
          out.groupby("survey_crop_year").levantamento.nunique().to_dict())
    if last_serie is not None:
        rel, s = last_serie
        s.to_csv(os.path.join(a.out, "conab_soja_serie_sheet_raw.csv"), index=False, header=False)
        print("serie sheet from release", rel)


if __name__ == "__main__":
    main()
