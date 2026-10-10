"""Karlawinda (Capricorn Metals): optical zone index vs reported quarterly material mined.
Quarters 2023Q4-2026Q2 were looked at while choosing settings; 2022Q1-2023Q3 and 2026Q3 were not.
Usage: karlawinda_eval.py results/karlawinda_optical_zones.csv"""
import sys, pandas as pd
from scipy import stats

# Material mined, BCM '000 (ore + waste), from Capricorn's ASX quarterly reports
BCM = pd.Series({"2022Q1": 3255, "2022Q2": 3903, "2022Q3": 3832, "2022Q4": 1827, "2023Q1": 3275, "2023Q2": 3638,
                 "2023Q3": 3613, "2023Q4": 3204, "2024Q1": 2602, "2024Q2": 3149, "2024Q3": 3697, "2024Q4": 3123,
                 "2025Q1": 3822, "2025Q2": 4499, "2025Q3": 4512, "2025Q4": 4366, "2026Q1": 3695, "2026Q2": 4152,
                 "2026Q3": 4439})
TUNED = ["2023Q4", "2024Q1", "2024Q2", "2024Q3", "2024Q4", "2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2"]
SUSPENSION = ("2022-10-14", "2022-11-03")   # mining suspended 13 Oct - 3 Nov 2022 after a fatal incident

df = pd.read_csv(sys.argv[1], index_col=0, parse_dates=True)
df = df[df.days_since_prev <= 12]
zones = [c for c in df.columns if c != "days_since_prev"]
q = df.groupby(df.index.to_period("Q"))[zones].mean()
q.index = q.index.astype(str); q["BCM"] = BCM
oos = [i for i in q.index if i not in TUNED]
for z in zones:
    cells = []
    for name, idx in [("tuned", TUNED), ("unseen", oos), ("all", list(q.index))]:
        r, p = stats.pearsonr(q.loc[idx, z], q.loc[idx, "BCM"])
        cells.append(f"{name} r={r:+.2f} p={p:.2f}")
    print(f"{z:12s}  " + "   ".join(cells))
w, b = df[SUSPENSION[0]:SUSPENSION[1]], df["2022-01-01":"2022-09-30"]
print(f"suspension passes (n={len(w)}) vs Jan-Sep 2022:")
for z in zones:
    print(f"  {z:12s} {w[z].mean():5.1f} vs {b[z].mean():5.1f}")
