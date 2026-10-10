"""Turn Cochilco's monthly copper-mine production by operation (xlsx) into a tidy CSV.

Usage:
    python ground_truth.py COCHILCO.xlsx OUT.csv

Source: Cochilco, "Producción de cobre mina por empresa (mensual)", downloaded 2026-10-10 from
https://www.cochilco.cl/web/download/951/cobre/12683/produccion-de-cobre-mina-por-empresa-mensual.xlsx
(linked from https://www.cochilco.cl/web/historico-produccion-de-cobre-y-molibdeno/).
Units: thousand tonnes of payable (commercial) fine copper per month, by operation ("faena").
Annual subtotal rows and empty future months are dropped.
"""
import sys
import pandas as pd

SRC = "https://www.cochilco.cl/web/download/951/cobre/12683/produccion-de-cobre-mina-por-empresa-mensual.xlsx"
raw = pd.read_excel(sys.argv[1], header=None)
hdr = raw.index[raw[0].astype(str).str.strip().str.startswith("mes")][0]
df = raw.iloc[hdr + 1:].copy()
df.columns = [str(c).strip() for c in raw.iloc[hdr]]
df = df.rename(columns={df.columns[0]: "month"})
df = df[pd.to_datetime(df["month"], errors="coerce").notna() & df["month"].map(lambda v: not isinstance(v, (int, float)))]
df["month"] = pd.to_datetime(df["month"]).dt.to_period("M").astype(str)
df = df.set_index("month").apply(pd.to_numeric, errors="coerce")
df = df[df["TOTAL CHILE"] > 0]
long = df.reset_index().melt(id_vars="month", var_name="operation", value_name="kt_cu").dropna()
long["source"] = SRC
long.to_csv(sys.argv[2], index=False)
print(df.index.min(), df.index.max(), len(df), "months,", df.shape[1], "operations")
