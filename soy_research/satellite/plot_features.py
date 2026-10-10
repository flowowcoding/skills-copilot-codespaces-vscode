"""Feature figures: (1) RS EVI anomaly through the season in drought years vs a normal year,
(2) Brazil-wide mean MODIS Terra LST anomaly by season (sensor-drift diagnostic).
Usage: python plot_features.py"""
import os
import numpy as np, pandas as pd
from plotstyle import setup, C, TEXT, MUTED
HERE = os.path.dirname(os.path.abspath(__file__))
plt = setup()
v = pd.read_csv(f"{HERE}/features/modis_vi_state.csv")
fig, ax = plt.subplots(figsize=(8, 4))
lab = {2012: "2011/12", 2020: "2019/20", 2022: "2021/22", 2023: "2022/23"}
ax.axhline(0, color=MUTED, lw=0.8)
for (Y, nm), col in zip(lab.items(), C):
    d = v[(v.state == "RS") & (v.season == Y)].sort_values("slot")
    days = (pd.to_datetime(d.start) - pd.to_datetime(f"{Y - 1}-07-01")).dt.days
    ax.plot(days, d.evi_anom, color=col, marker="o", ms=3, label=nm)
tk = [0, 31, 62, 92, 123, 153, 184, 215, 243, 274, 304, 335]
ax.set_xticks(tk); ax.set_xticklabels(["Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun"])
ax.set_ylabel("EVI anomaly vs prior seasons (mask-weighted)")
ax.set_title("Rio Grande do Sul: soybean-mask EVI anomaly by composite start date, drought seasons")
ax.legend(loc="lower left", fontsize=8)
fig.tight_layout(); fig.savefig(f"{HERE}/figures/fig_rs_evi_anomaly.png", dpi=130); plt.close(fig)

l = pd.read_csv(f"{HERE}/features/lst_state.csv")
m = l[(l.slot >= 12) & (l.slot <= 25)].groupby("season").lst_anom.mean()
fig, ax = plt.subplots(figsize=(8, 3.6))
cols = [C[1] if s >= 2023 else C[0] for s in m.index]
ax.bar(m.index, m.values, color=cols, width=0.7)
ax.axhline(0, color=MUTED, lw=0.8)
ax.set_ylabel("mean LST anomaly, deg C")
ax.set_title("MODIS Terra daytime LST anomaly, Dec-Mar, mean of 12 states (holdout seasons in orange)")
ax.text(0.01, 0.05, "Terra's overpass has drifted earlier since ~2022; cooler readings across all states look like sensor drift, not weather",
        transform=ax.transAxes, fontsize=7.5, color=TEXT)
fig.tight_layout(); fig.savefig(f"{HERE}/figures/fig_lst_drift.png", dpi=130); plt.close(fig)
