#!/usr/bin/env python3
"""Fetch IBGE LSPA (Levantamento Sistematico da Producao Agricola) monthly
soybean estimate vintages, Brazil + all states, with release dates.

Source: SIDRA table 6588 "Serie historica da estimativa anual ..." via
https://servicodados.ibge.gov.br/api/v3/agregados/6588 (monthly vintages
from Sep-2006; each monthly period is the estimate, as published that month,
of the CURRENT calendar-year harvest; harvest year Y == crop year (Y-1)/Y).

Release dates:
  * 2017+ : IBGE release calendar API (produto 9201).
  * 2006-2016 : IBGE news API - the LSPA press release ("Em <mes>, IBGE preve
    safra...") published in the month after the reference month.
  * fallback: 10th of the following month (date_quality='approx').

Usage:
    python fetch_ibge_lspa.py --out OUT_DIR
Writes OUT_DIR/ibge_lspa_raw.csv (long) and OUT_DIR/ibge_lspa_release_dates.csv
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import time
import urllib.parse

import pandas as pd

API = "https://servicodados.ibge.gov.br/api/v3"
VARS = {109: "planted_area", 216: "harvested_area", 35: "production", 36: "yield"}
UNIT_CONV = {"planted_area": 1e-3, "harvested_area": 1e-3, "production": 1e-3, "yield": 1.0}  # -> kha, kt, kg/ha
UF = {11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO", 21: "MA", 22: "PI", 23: "CE",
      24: "RN", 25: "PB", 26: "PE", 27: "AL", 28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP",
      41: "PR", 42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF"}
PT_MONTH = {m: i + 1 for i, m in enumerate(["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
                                             "agosto", "setembro", "outubro", "novembro", "dezembro"])}


def getjson(url, tries=4):
    for i in range(tries):
        r = subprocess.run(["curl", "-g", "-sS", "--max-time", "180", url], capture_output=True)
        if r.returncode == 0:
            try:
                return json.loads(r.stdout)
            except json.JSONDecodeError:
                pass
        time.sleep(3 * (i + 1))
    raise RuntimeError(url)


def fetch_values():
    per = [p["id"] for p in getjson(f"{API}/agregados/6588/periodos")]
    rows = []
    for i in range(0, len(per), 24):
        chunk = per[i:i + 24]
        url = (f"{API}/agregados/6588/periodos/{'|'.join(chunk)}/variaveis/{'|'.join(map(str, VARS))}"
               f"?localidades=N1[all]|N3[all]&classificacao=48[39443]")
        for v in getjson(url):
            var = VARS[int(v["id"])]
            for res in v["resultados"]:
                for s in res["series"]:
                    loc = s["localidade"]
                    reg = "BR" if loc["nivel"]["id"] == "N1" else UF.get(int(loc["id"]), loc["id"])
                    for p, val in s["serie"].items():
                        try:
                            x = float(val) * UNIT_CONV[var]
                        except (TypeError, ValueError):
                            continue
                        rows.append(dict(ref_month=p, region=reg, variable=var, value=x))
        print("periods", chunk[0], "-", chunk[-1], flush=True)
    return pd.DataFrame(rows)


def release_dates(ref_months):
    cal = getjson(f"{API}/calendario/9201?qtd=1000")["items"]
    d = {}
    for x in cal:
        ref = f"{x['ano_referencia_inicio']}{x['mes_referencia_inicio']:02d}"
        d[ref] = (dt.datetime.strptime(x["data_divulgacao"], "%d/%m/%Y %H:%M:%S"), "ibge_calendar")
    news = []
    for y in range(2006, 2018):
        for q in ["safra", "safra de grãos"]:
            url = f"{API}/noticias/?busca={urllib.parse.quote(q)}&de=01-01-{y}&ate=12-31-{y}&qtd=500"
            news += getjson(url).get("items", [])
    seen = set()
    cand = []
    for n in news:
        if n["id"] in seen:
            continue
        seen.add(n["id"])
        t = n["titulo"].lower()
        if "safra" not in t or re.search(r"municipal|\bpam\b|censo|pib|ipca|estoques|abate", t):
            continue
        cand.append((dt.datetime.strptime(n["data_publicacao"], "%d/%m/%Y %H:%M:%S"), n["titulo"]))
    for ref in ref_months:
        if ref in d:
            continue
        y, m = int(ref[:4]), int(ref[4:])
        ny, nm = (y + (m == 12), m % 12 + 1)
        best = None
        for pub, title in cand:
            if pub.year == ny and pub.month == nm and pub.day <= 25:
                tl = title.lower()
                named = [k for k in PT_MONTH if re.search(r"\b" + k + r"\b", tl)]
                score = 2 if PT_MONTH.get(named[0] if named else "", 0) == m else (1 if not named else 0)
                if score and (best is None or score > best[0] or (score == best[0] and pub < best[1])):
                    best = (score, pub, title)
        if best:
            d[ref] = (best[1].replace(hour=10, minute=0), "ibge_news:" + best[2][:80])
        else:
            d[ref] = (dt.datetime(ny, nm, 10, 10, 0), "approx")
    return pd.DataFrame([dict(ref_month=k, release_datetime_brt=v[0].strftime("%Y-%m-%d %H:%M"), date_source=v[1])
                         for k, v in sorted(d.items()) if k in set(ref_months)])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    v = fetch_values()
    v.to_csv(os.path.join(a.out, "ibge_lspa_raw.csv"), index=False)
    r = release_dates(sorted(v.ref_month.unique()))
    r.to_csv(os.path.join(a.out, "ibge_lspa_release_dates.csv"), index=False)
    print(len(v), "values;", r.date_source.str.split(":").str[0].value_counts().to_dict())


if __name__ == "__main__":
    main()
