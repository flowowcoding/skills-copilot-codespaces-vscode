"""Orbit-drift check for the MODIS vegetation index inputs (Terra vs Aqua, and Aqua vs HLS).

1. Terra minus Aqua: on the core tile h11v04 (IA / MN / WI / IL / northern MO), for every candidate pixel
   with good-quality values, Terra MOD13Q1 EVI of the composite starting DOY 193 (Jul 12-27) minus the mean
   of the two Aqua MYD13Q1 composites that bracket it (DOY 185 and 201). The mean over pixels, per year.
   Terra's equator crossing drifted earlier from ~2022 and Aqua's later, so a break after 2021 flags drift.
2. HLS minus Aqua: residual of the per-crop HLS->MODIS state calibration (features/hls_state.csv vs
   features/modis_state.csv), averaged per year. HLS platforms (Landsat 8/9, Sentinel-2) keep their orbits,
   so a trend in this residual would point to Aqua drift.
Outputs: results/drift_check.csv, figures/fig_drift.png
Usage: python plot_drift.py --work <scratch>/us_sat
"""
import argparse, glob, os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def load(work, plat, doy, tile="h11v04"):
    out = {}
    for fn in glob.glob(f"{work}/modis_{plat}/*{doy:03d}_{tile}.npz"):
        k = os.path.basename(fn).split("_")[0]
        if int(k[4:]) != doy:
            continue
        z = np.load(fn)
        good = (z["rel"] >= 0) & (z["rel"] <= 1)
        out[int(k[:4])] = pd.Series(np.where(good, z["evi"] / 1e4, np.nan), index=z["pixel_id"])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    a = ap.parse_args()
    t193 = load(a.work, "MOD", 193); a185 = load(a.work, "MYD", 185); a201 = load(a.work, "MYD", 201)
    rows = []
    for y in sorted(t193):
        if y in a185 and y in a201:
            aq = (a185[y] + a201[y]) / 2
            d = (t193[y] - aq).dropna()
            rows.append(dict(year=y, test="terra_minus_aqua_evi", value=d.mean(), n=len(d), terra=t193[y].mean(), aqua=aq.mean()))
    h = pd.read_csv(os.path.join(HERE, "features", "hls_state.csv"))
    m = pd.read_csv(os.path.join(HERE, "features", "modis_state.csv")); m = m[m.source == "MYD"]
    j = h.merge(m, on=["year", "doy", "crop", "state"]).dropna(subset=["evi", "hls_evi"])
    j = j[(j.hls_valid_frac >= 0.3) & (j.valid_frac >= 0.3)]
    for crop, g in j.groupby("crop"):
        b, c = np.polyfit(g.hls_evi, g.evi, 1)
        g = g.assign(res=g.evi - (c + b * g.hls_evi))
        for y, gg in g.groupby("year"):
            rows.append(dict(year=y, test=f"aqua_minus_hls_fit_{crop}", value=gg.res.mean(), n=len(gg)))
    d = pd.DataFrame(rows)
    d.to_csv(os.path.join(HERE, "results", "drift_check.csv"), index=False, float_format="%.4f")
    print(d.to_string())
    from plotstyle import setup, C, TEXT
    plt = setup()
    fig, ax = plt.subplots(figsize=(9, 4))
    t = d[d.test == "terra_minus_aqua_evi"]
    ax.plot(t.year, t.value, color=C[0], marker="o", ms=4, label="Terra (Jul 12-27) minus Aqua (bracketing composites), EVI, tile h11v04")
    for i, crop in enumerate(["corn", "soy"]):
        hh = d[d.test == f"aqua_minus_hls_fit_{crop}"]
        ax.plot(hh.year, hh.value, color=C[i + 1], marker="s", ms=4, label=f"Aqua minus HLS-calibrated, {crop} mask states (residual)")
    pre = t[t.year <= 2021].value
    ax.axhspan(pre.mean() - 2 * pre.std(), pre.mean() + 2 * pre.std(), color="#e6e5e1", alpha=0.6, lw=0)
    ax.axvline(2021.5, color=TEXT, lw=0.8, ls=":")
    ax.text(2021.6, ax.get_ylim()[1], "Terra drift begins ~2022", va="top", color=TEXT, fontsize=8)
    ax.set_ylabel("EVI difference"); ax.set_title("Orbit-drift check: Terra vs Aqua, and Aqua vs HLS (shaded: Terra-Aqua 2003-21 mean ± 2 sd)")
    ax.legend(loc="lower left", fontsize=7.5)
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "figures", "fig_drift.png"), dpi=130)


if __name__ == "__main__":
    main()
