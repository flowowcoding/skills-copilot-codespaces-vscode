"""Thacker Pass: satellite construction progress vs disclosed capex and LAC share price (A2, A3).

Inputs (all produced by the other scripts in this folder):
  FOOTPRINT.csv   footprint.py --seasonal output (monthly disturbed km2 per zone)
  STRUCT.csv      radar_structures.py output (Sentinel-1 bright-structure hectares per pass)
  CAPEX.csv       thacker_capex.csv (quarterly capex disclosed by LAC, with sources)
  PRICES_DIR      folder for cached Yahoo Finance daily prices (LAC, LIT); fetched if missing

Quarterly satellite levels:
  footprint  median over the quarter's usable months. Months whose control threshold is
             above 0.45 are dropped: snow or low sun makes the whole scene look changed, and
             the per-month percentile threshold then hides real disturbance.
  structures median of the Sentinel-1 bright-structure area over the quarter's passes.
Quarters with no usable month are filled by linear interpolation (flagged in the CSV).

A2: Spearman rho between the quarterly change in each satellite level and the capex reported
    for the same quarter, and for one quarter later/earlier. Positive k means the satellite
    change comes k quarters before the capex quarter.
A3: for each LAC quarterly report since the Oct 2023 separation, the LAC return minus the LIT
    (lithium ETF) return from the close before the report to the close one trading day after
    it, compared with the satellite "surprise" (this quarter's change minus last quarter's).

Usage:
    python thacker_eval.py FOOTPRINT.csv STRUCT.csv CAPEX.csv PRICES_DIR OUT_PREFIX
writes OUT_PREFIX_quarterly.csv, OUT_PREFIX_reports.csv and OUT_PREFIX_results.json
"""
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd
from scipy import stats

MAXTHR = 0.45
REPORTS = {  # LAC quarterly results release date -> quarter reported (new LAC, NYSE: LAC since 2023-10-03)
    "2023-11-09": "2023Q3", "2024-03-15": "2023Q4", "2024-05-13": "2024Q1", "2024-08-14": "2024Q2",
    "2024-11-07": "2024Q3", "2025-03-28": "2024Q4", "2025-05-15": "2025Q1", "2025-08-14": "2025Q2",
    "2025-11-13": "2025Q3", "2026-03-19": "2025Q4", "2026-05-14": "2026Q1", "2026-08-13": "2026Q2"}


def prices(sym, folder):
    os.makedirs(folder, exist_ok=True)
    fn = os.path.join(folder, f"{sym}.json")
    if not os.path.exists(fn):
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1=1546300800&period2=1798761600&interval=1d"
        subprocess.run(["curl", "-sS", "-A", "Mozilla/5.0", url, "-o", fn], check=True)
    r = json.load(open(fn))["chart"]["result"][0]
    s = pd.Series(r["indicators"]["adjclose"][0]["adjclose"],
                  index=pd.to_datetime(r["timestamp"], unit="s").normalize(), name=sym)
    return s.dropna()


def main():
    fp_csv, st_csv, capex_csv, pdir, out = sys.argv[1:6]
    fp = pd.read_csv(fp_csv, index_col=0)
    fp.index = pd.PeriodIndex(fp.index, freq="M")
    ok = fp["threshold"] <= MAXTHR
    fpq = fp.loc[ok, "total_km2"].groupby(fp.index[ok].asfreq("Q")).median()
    st = pd.read_csv(st_csv, index_col=0, parse_dates=True)["zone_bright_ha"]
    stq = st.groupby(st.index.to_period("Q")).median()
    capex = pd.read_csv(capex_csv)
    capex.index = pd.PeriodIndex(capex["quarter"], freq="Q")
    qs = pd.period_range("2022Q1", max(fpq.index.max(), stq.index.max()), freq="Q")
    q = pd.DataFrame(index=qs)
    q["footprint_km2"] = fpq.reindex(qs)
    q["footprint_interpolated"] = q["footprint_km2"].isna()
    q["footprint_km2"] = q["footprint_km2"].interpolate(limit_area="inside")
    q["structures_ha"] = stq.reindex(qs)
    q["d_footprint"] = q["footprint_km2"].diff()
    q["d_structures"] = q["structures_ha"].diff()
    q["capex_musd"] = capex["capex_musd"].reindex(qs)
    q.index = q.index.astype(str)
    q.round(3).to_csv(f"{out}_quarterly.csv")
    print(q.round(2).to_string())

    res = {"A2": {}}
    for col in ("d_footprint", "d_structures"):
        res["A2"][col] = {}
        for k in (-1, 0, 1):
            x = q[col].values
            y = q["capex_musd"].shift(-k).values      # capex k quarters after the satellite quarter
            m = np.isfinite(x) & np.isfinite(y)
            rho, p = stats.spearmanr(x[m], y[m])
            res["A2"][col][f"lag{k:+d}"] = dict(rho=float(rho), p=float(p), n=int(m.sum()))
    # level vs cumulative capex (descriptive)
    cum = q["capex_musd"].cumsum()
    for col in ("footprint_km2", "structures_ha"):
        m = q[col].notna() & q["capex_musd"].notna()
        res[f"level_{col}_vs_cumulative_capex_rho"] = float(stats.spearmanr(q[col][m], cum[m])[0])

    lac, lit = prices("LAC", pdir), prices("LIT", pdir)
    rows = []
    for d, quarter in REPORTS.items():
        t = pd.Timestamp(d)
        i0 = lac.index.searchsorted(t) - 1            # close before the report
        i1 = min(lac.index.searchsorted(t) + 1, len(lac) - 1)
        d0, d1 = lac.index[i0], lac.index[i1]
        ex = (lac[d1] / lac[d0] - 1) - (lit.asof(d1) / lit.asof(d0) - 1)
        prev = str(pd.Period(quarter, "Q") - 1)
        rows.append(dict(report_date=d, quarter=quarter, excess_return_pct=round(ex * 100, 2),
                         surprise_footprint=q.loc[quarter, "d_footprint"] - q.loc[prev, "d_footprint"],
                         surprise_structures=q.loc[quarter, "d_structures"] - q.loc[prev, "d_structures"]))
    r = pd.DataFrame(rows)
    r.round(3).to_csv(f"{out}_reports.csv", index=False)
    print(r.round(2).to_string())
    for col in ("surprise_footprint", "surprise_structures"):
        m = r[col].notna() & (r[col].abs() > 1e-9)
        agree = int((np.sign(r.loc[m, col]) == np.sign(r.loc[m, "excess_return_pct"])).sum())
        rho, p = stats.spearmanr(r.loc[m, col], r.loc[m, "excess_return_pct"])
        res[f"A3_{col}"] = dict(sign_agree=agree, n=int(m.sum()), rho=float(rho), p=float(p),
                                binom_p=float(stats.binomtest(agree, int(m.sum()), 0.5, alternative="greater").pvalue))
    json.dump(res, open(f"{out}_results.json", "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
