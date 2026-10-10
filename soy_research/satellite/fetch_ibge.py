"""Fetch IBGE soybean statistics and boundaries used by the satellite signal.

Outputs (in --out, default ./data):
  pam_state.csv      PAM final soybean area planted/harvested, production, yield by state, 2000-latest
  pam_muni_area.csv  PAM municipal soybean planted area (ha), 2000-latest (used ONLY lagged, for the mask)
  lspa_state.csv     IBGE LSPA monthly forecast vintages by state (table 6588, Sep 2006 - latest)
  munis_<UF>.geojson municipal boundaries for the soy states (IBGE malhas API, current mesh)

PAM year Y = calendar-year harvest Y, i.e. crop year (Y-1)/Y for soybean. PAM year Y is published
around September of Y+1, so at any as-of date in crop year (Y-1)/Y the latest PAM available is Y-2.

Usage: python fetch_ibge.py [--out data]
"""
import argparse, json, os, time
import pandas as pd, requests

UF = {"MT": 51, "PR": 41, "RS": 43, "GO": 52, "MS": 50, "BA": 29, "MG": 31, "MA": 21,
      "TO": 17, "PI": 22, "SP": 35, "SC": 42, "PA": 15, "RO": 11, "DF": 53}
SIDRA = "https://apisidra.ibge.gov.br/values"


def sidra(path, tries=4):
    for k in range(tries):
        try:
            r = requests.get(f"{SIDRA}/{path}", timeout=180)
            r.raise_for_status()
            d = r.json()
            return pd.DataFrame(d[1:]).rename(columns={c: v for c, v in d[0].items()})
        except Exception as e:  # noqa
            print("retry", path, e); time.sleep(5 * (k + 1))
    raise RuntimeError(path)


def num(s):
    return pd.to_numeric(s.replace({"-": "0", "...": None, "..": None, "X": None}), errors="coerce")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "data"))
    ap.add_argument("--first", type=int, default=2000, help="first year for municipal PAM")
    ap.add_argument("--first-state", type=int, default=1985, help="first year for state PAM (trend history)")
    ap.add_argument("--last", type=int, default=2025)
    ap.add_argument("--skip-muni", action="store_true", help="do not refetch municipal PAM")
    ap.add_argument("--skip-pam", action="store_true", help="only refresh LSPA vintages and meshes")
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    yrs = ",".join(str(y) for y in range(a.first, a.last + 1))

    inv = {str(v): k for k, v in UF.items()}
    # state PAM: 109 planted, 216 harvested, 214 production, 112 yield
    if not a.skip_pam:
        pam(a, ",".join(str(y) for y in range(a.first_state, a.last + 1)), inv)
    lspa(a, inv)
    meshes(a)


def pam(a, yrs, inv):
    df = sidra(f"t/1612/n3/all/v/109,216,214,112/p/{yrs}/c81/2713")
    br = sidra(f"t/1612/n1/all/v/109,216,214,112/p/{yrs}/c81/2713")
    br["Unidade da Federação (Código)"] = "BR"
    df = pd.concat([df, br])
    df = df.rename(columns={"Unidade da Federação (Código)": "uf_code", "Variável (Código)": "var", "Ano": "year", "Valor": "value"})
    df["value"] = num(df["value"])
    w = df.pivot_table(index=["uf_code", "year"], columns="var", values="value").reset_index()
    w.columns = ["uf_code", "year", "area_planted_ha", "yield_kg_ha", "production_t", "area_harvested_ha"]
    w["state"] = w.uf_code.map(lambda c: c if c == "BR" else inv.get(str(c), "UF" + str(c)))
    w["year"] = w.year.astype(int)
    w["yield_kg_ha"] = w.production_t / w.area_harvested_ha * 1000
    w[["state", "year", "area_planted_ha", "area_harvested_ha", "production_t", "yield_kg_ha"]].sort_values(["state", "year"]).to_csv(f"{a.out}/pam_state.csv", index=False)
    print("pam_state", len(w))

    if a.skip_muni:
        return
    # municipal planted area, one call per year (SIDRA cell limit)
    rows = []
    for y in range(a.first, a.last + 1):
        m = sidra(f"t/1612/n6/all/v/109/p/{y}/c81/2713")
        m = m.rename(columns={"Município (Código)": "muni", "Valor": "area_ha"})
        m["area_ha"] = num(m["area_ha"]).fillna(0); m["year"] = y
        rows.append(m[["muni", "year", "area_ha"]]); print("muni", y, len(m))
    mu = pd.concat(rows); mu = mu[mu.area_ha > 0]
    mu.to_csv(f"{a.out}/pam_muni_area.csv", index=False)



def lspa(a, inv):
    """LSPA vintages (table 6588): period YYYYMM = survey month; v109 planted, 216 harvested, 35 production, 36 yield"""
    r = requests.get("https://servicodados.ibge.gov.br/api/v3/agregados/6588/periodos", timeout=60).json()
    pers = [p["id"] for p in r]
    out = []
    for i in range(0, len(pers), 24):
        chunk = ",".join(pers[i:i + 24])
        l = sidra(f"t/6588/n1/all/n3/all/v/109,216,35,36/p/{chunk}/c48/39443")
        out.append(l); print("lspa", pers[i], len(l))
    l = pd.concat(out)
    l = l.rename(columns={"Brasil e Unidade da Federação (Código)": "region", "Variável (Código)": "var",
                          "Mês (Código)": "survey_month", "Valor": "value"})
    l["value"] = num(l["value"])
    l["state"] = l["region"].map(lambda c: "BR" if str(c) == "1" else inv.get(str(c)))
    l = l.dropna(subset=["state"])
    lw = l.pivot_table(index=["state", "survey_month"], columns="var", values="value").reset_index()
    lw = lw.rename(columns={"109": "area_planted_ha", "216": "area_harvested_ha", "35": "production_t", "36": "yield_kg_ha"})
    lw.to_csv(f"{a.out}/lspa_state.csv", index=False); print("lspa rows", len(lw))



def meshes(a):
    """municipal boundaries per state"""
    for uf, code in UF.items():
        fn = f"{a.out}/munis_{uf}.geojson"
        if os.path.exists(fn):
            continue
        u = f"https://servicodados.ibge.gov.br/api/v3/malhas/estados/{code}?intrarregiao=municipio&formato=application/vnd.geo+json&qualidade=intermediaria"
        g = requests.get(u, timeout=180); g.raise_for_status()
        open(fn, "w").write(g.text); print("mesh", uf, len(json.loads(g.text)["features"]))


if __name__ == "__main__":
    main()
