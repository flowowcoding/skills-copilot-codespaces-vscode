"""Build the price panels used as targets.

Daily (Yahoo Finance chart API, continuous front-month futures, no auth):
  SB=F ICE raw sugar No.11 (c/lb), CT=F ICE cotton No.2 (c/lb), ZM=F CBOT soymeal, INR=X USD/INR.
  Yahoo's "=F" series splices contracts at expiry without adjustment. Returns on the first trading day
  after each expiry month switch are replaced by 0 (roll gap removed) to build a roll-adjusted
  total-return-like index `<sym>_tr`. Sugar No.11 expires on the last trading day of the month before
  delivery (Mar/May/Jul/Oct), so switches occur at the start of Mar, May, Jul, Oct; cotton No.2 contracts
  (Mar/May/Jul/Oct/Dec) switch around the start of those months as well (approximate rule).
Monthly:
  WPI (Office of the Economic Adviser, https://eaindustry.nic.in): Gram, Arhar (tur), Masur, Sugar,
  Sugarcane. 2004-05 base (Jan 2005 - Mar 2017) spliced into 2011-12 base (Apr 2012 - latest) by
  chaining log changes; values are the final revised indices (provisional prints differ slightly).
  WPI for month M is published around the 14th of M+1 -> available_date.
  Statistics Canada table 32-10-0077-01: Saskatchewan farm prices of lentils and dry peas (CAD/t).

Outputs: ../data/prices_daily.csv, ../data/prices_monthly.csv
Usage:   python build_prices.py --raw <scratch>/india/raw --out ../data
"""
import argparse, json
import numpy as np, pandas as pd

SYMS = {"SB=F": "sugar", "CT=F": "cotton", "ZM=F": "soymeal", "INR=X": "usdinr"}
ROLL_MONTHS = {"sugar": [3, 5, 7, 10], "cotton": [3, 5, 7, 10, 12], "soymeal": [1, 3, 5, 7, 8, 9, 10, 12]}
WPI_ITEMS = {"Gram": "wpi_gram", "Arhar": "wpi_arhar", "Masur": "wpi_masur", "Sugar": "wpi_sugar", "Sugarcane": "wpi_sugarcane"}


def yahoo(fn):
    r = json.load(open(fn))["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    s = pd.Series(q["close"], index=pd.to_datetime(r["timestamp"], unit="s").normalize()).dropna()
    return s[~s.index.duplicated(keep="last")]


def wpi(fn, items):
    d = pd.read_excel(fn)
    d = d[d.COMM_NAME.astype(str).str.strip().isin(items)].drop_duplicates("COMM_NAME")
    cols = [c for c in d.columns if str(c).startswith("INDX")]
    out = d.set_index(d.COMM_NAME.str.strip())[cols].T
    out.index = pd.to_datetime([c[4:6] + "-" + c[6:] for c in cols], format="%m-%Y")
    return out.apply(pd.to_numeric, errors="coerce")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    D = pd.DataFrame({v: yahoo(f"{a.raw}/prices/{k}.json") for k, v in SYMS.items()})
    D = D[D.index >= "2003-01-01"]
    for c, months in ROLL_MONTHS.items():
        s = D[c].dropna(); r = np.log(s).diff()
        first_of_month = s.index.to_series().groupby([s.index.year, s.index.month]).transform("min") == s.index.to_series()
        roll = first_of_month & s.index.month.isin(months)
        r[roll] = 0.0
        D[f"{c}_tr"] = np.exp(r.fillna(0).cumsum()) * 100
        D[f"{c}_rollday"] = roll.astype(int).reindex(D.index)
    D.rename_axis("date").to_csv(f"{a.out}/prices_daily.csv", float_format="%.4f")
    # WPI splice
    old = pd.concat([wpi(f"{a.raw}/wpi/w0405_month2till2012.xls", WPI_ITEMS), wpi(f"{a.raw}/wpi/w0405_month2.xls", WPI_ITEMS)])
    old = old[~old.index.duplicated(keep="first")].sort_index()
    new = wpi(f"{a.raw}/wpi/monthly_index_1112.xls", WPI_ITEMS).sort_index()
    M = pd.DataFrame(index=pd.date_range("2005-01-01", new.index.max(), freq="MS"))
    for k, v in WPI_ITEMS.items():
        lo = np.log(old[k]).diff()[old.index < "2012-04-01"]
        ln = np.log(new[k]).diff()[new.index >= "2012-05-01"]
        r = pd.concat([lo, ln]).reindex(M.index).fillna(0)
        r.iloc[0] = 0
        lvl = np.exp(r.cumsum())
        M[v] = lvl / lvl[lvl.index == "2012-04-01"].iloc[0] * new.loc["2012-04-01", k]
        M.loc[M.index > new[k].last_valid_index(), v] = np.nan
    M["wpi_available_date"] = (M.index + pd.offsets.MonthBegin(1) + pd.Timedelta(days=13)).date
    sc = pd.read_csv(f"{a.raw}/statcan/32100077.csv", low_memory=False)
    sc = sc[(sc.GEO == "Saskatchewan") & sc["Farm products"].str.contains("Lentils|Dry peas")]
    sc = sc.pivot_table(index="REF_DATE", columns="Farm products", values="VALUE")
    sc.index = pd.to_datetime(sc.index + "-01"); sc.columns = ["sk_dry_peas_cad_t" if "peas" in c else "sk_lentils_cad_t" for c in sc.columns]
    M = M.join(sc, how="left")
    M.rename_axis("month").to_csv(f"{a.out}/prices_monthly.csv", float_format="%.2f")
    print(D.tail(2).T, M.tail(8))


if __name__ == "__main__":
    main()
