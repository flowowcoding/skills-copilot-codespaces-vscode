#!/usr/bin/env python3
"""USDA benchmark for Black Sea wheat: how good (or weak) are USDA's Russia / Ukraine /
Kazakhstan production forecasts, compared with its US wheat forecasts, and do the revisions
move wheat futures?

Inputs: data/benchmark/wasde_wheat_vintages.csv, data/prices/*.csv,
        data/private/private_estimates.csv (reviewed IKAR/SovEcon/ministry quotes, optional)
Outputs (results/):
  usda_revisions.csv        one row per (country, crop year, report): estimate, previous,
                            revision (Mt and % of final), error vs final
  revision_stats.csv        by country and month-of-season: mean |revision| %, mean |error| %,
                            share of the first-to-final change still to come, persistence
                            slope (rev_t on rev_t-1, crop-year clustered t)
  wasde_day_reaction.csv    WASDE-day log return of ZW, KE, WEAT on the Russia revision (%),
                            controlling for the US revision; HC1 t-stats
  private_vs_usda.csv       for each USDA report: latest private (IKAR / SovEcon / MinAg)
                            Russia estimate published before it, private minus USDA, and the
                            next USDA revision (does USDA move toward the private estimates?)
  figures/fig_revisions.png, figures/fig_paths_russia.png

Final = last WASDE vintage for the crop year (USDA definition, excludes Crimea).
Season months: report month counted from May of the harvest year (May = 1 ... next Apr = 12).

Usage: python benchmark_analysis.py
"""
import os

import numpy as np
import pandas as pd
import statsmodels.api as sm

import plotstyle

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "..", "data")
R = os.path.join(HERE, "..", "results")
F = os.path.join(HERE, "..", "figures")
COUNTRIES = ["Russia", "Ukraine", "Kazakhstan", "United States"]


def load_vintages():
    w = pd.read_csv(os.path.join(D, "benchmark", "wasde_wheat_vintages.csv"), parse_dates=["release_date"])
    w = w[(w.attribute == "Production") & w.region.isin(COUNTRIES)].rename(columns={"region": "country"})
    w = w.sort_values("release_date")
    fin = w.groupby(["country", "crop_year"]).tail(1).set_index(["country", "crop_year"]).value_mmt.rename("final")
    w = w.join(fin, on=["country", "crop_year"])
    last = w.groupby(["country", "crop_year"]).release_date.transform("max")
    w["final_settled"] = last >= pd.to_datetime(w.crop_year.astype(str) + "-11-01") + pd.DateOffset(months=12)
    w["season_month"] = (w.release_date.dt.year - w.crop_year) * 12 + w.release_date.dt.month - 4
    w = w[(w.season_month >= 1) & (w.season_month <= 12)]
    w["prev"] = w.groupby(["country", "crop_year"]).value_mmt.shift(1)
    w["rev_mt"] = w.value_mmt - w.prev
    w["rev_pct"] = 100 * w.rev_mt / w.final
    w["err_pct"] = 100 * (w.value_mmt - w.final) / w.final
    w["prev_rev_pct"] = w.groupby(["country", "crop_year"]).rev_pct.shift(1)
    w["next_rev_pct"] = w.groupby(["country", "crop_year"]).rev_pct.shift(-1)
    return w


def clustered(y, X, g):
    X = sm.add_constant(X)
    m = sm.OLS(y, X, missing="drop").fit(cov_type="cluster", cov_kwds={"groups": g})
    return m


def revision_stats(w):
    rows = []
    s = w[w.final_settled & (w.crop_year >= 2005) & (w.crop_year <= 2024)]
    for c, g in s.groupby("country"):
        first = g.groupby("crop_year").head(1)
        for mth, gm in g.groupby("season_month"):
            rows.append(dict(country=c, season_month=mth, n=len(gm), mean_abs_rev_pct=gm.rev_pct.abs().mean(),
                             mean_abs_err_pct=gm.err_pct.abs().mean(), rmse_pct=np.sqrt((gm.err_pct ** 2).mean())))
        d = g.dropna(subset=["rev_pct", "prev_rev_pct"])
        m = clustered(d.rev_pct, d[["prev_rev_pct"]], d.crop_year)
        rows.append(dict(country=c, season_month="all", n=len(g), mean_abs_rev_pct=g.rev_pct.abs().mean(),
                         mean_abs_err_pct=g.err_pct.abs().mean(), rmse_pct=np.sqrt((g.err_pct ** 2).mean()),
                         first_abs_err_pct=first.err_pct.abs().mean(),
                         sd_rev_pct=g.rev_pct.std(), persistence_slope=m.params["prev_rev_pct"],
                         persistence_t=m.tvalues["prev_rev_pct"], persistence_n=len(d),
                         share_rev_same_sign_as_prev=(np.sign(d.rev_pct) == np.sign(d.prev_rev_pct))[d.rev_pct != 0].mean()))
    return pd.DataFrame(rows)


def prices():
    out = {}
    for n in ["cbot_wheat_zw", "kc_wheat_ke", "teucrium_weat"]:
        p = pd.read_csv(os.path.join(D, "prices", f"{n}_daily.csv"), parse_dates=["date"]).set_index("date")
        p.loc[p.roll == 1, "ret"] = np.nan
        out[n] = 100 * p.ret
    return pd.DataFrame(out)


def reaction(w, px):
    ru = w[w.country == "Russia"][["release_date", "crop_year", "season_month", "rev_pct", "rev_mt"]]
    us = w[w.country == "United States"][["release_date", "crop_year", "rev_pct"]].rename(columns={"rev_pct": "us_rev_pct"})
    ua = w[w.country == "Ukraine"][["release_date", "crop_year", "rev_pct"]].rename(columns={"rev_pct": "ua_rev_pct"})
    kz = w[w.country == "Kazakhstan"][["release_date", "crop_year", "rev_pct"]].rename(columns={"rev_pct": "kz_rev_pct"})
    e = ru.merge(us, on=["release_date", "crop_year"], how="left").merge(ua, on=["release_date", "crop_year"], how="left") \
        .merge(kz, on=["release_date", "crop_year"], how="left")
    e = e[e.season_month <= 8].dropna(subset=["rev_pct"])  # May..Dec of the harvest year: current crop in play
    e = e.join(px, on="release_date")
    rows = []
    for col in px.columns:
        for spec, xs in [("russia_only", ["rev_pct"]), ("russia+us", ["rev_pct", "us_rev_pct"]),
                         ("blacksea3", ["rev_pct", "ua_rev_pct", "kz_rev_pct", "us_rev_pct"])]:
            d = e.dropna(subset=[col] + xs)
            m = sm.OLS(d[col], sm.add_constant(d[xs])).fit(cov_type="HC1")
            rows.append(dict(series=col, spec=spec, n=len(d), slope_russia_pct_per_1pct=m.params["rev_pct"],
                             t_russia=m.tvalues["rev_pct"], r2=m.rsquared,
                             slope_us=m.params.get("us_rev_pct", np.nan), t_us=m.tvalues.get("us_rev_pct", np.nan)))
    return pd.DataFrame(rows), e


def private_vs_usda(w):
    fn = os.path.join(D, "private", "private_estimates.csv")
    if not os.path.exists(fn):
        return None
    p = pd.read_csv(fn, parse_dates=["pub_date"])
    p = p[p.include == 1]
    ru = w[w.country == "Russia"].copy()
    rows = []
    for r in ru.itertuples():
        q = p[(p.crop_year == r.crop_year) & (p.pub_date < r.release_date)]
        q = q[q.pub_date >= r.release_date - pd.Timedelta(days=45)]
        if q.empty:
            continue
        last = q.sort_values("pub_date").groupby("forecaster").tail(1)
        rows.append(dict(release_date=r.release_date, crop_year=r.crop_year, season_month=r.season_month,
                         usda=r.value_mmt, usda_prev=r.prev, final=r.final, rev_pct=r.rev_pct,
                         next_rev_pct=r.next_rev_pct,
                         private_mean=last.value_mmt.mean(), n_forecasters=len(last),
                         forecasters=";".join(last.forecaster), private_lastdate=last.pub_date.max().date()))
    d = pd.DataFrame(rows)
    d["priv_minus_usda_prev_pct"] = 100 * (d.private_mean - d.usda_prev) / d.final
    d["priv_minus_usda_pct"] = 100 * (d.private_mean - d.usda) / d.final
    d["priv_err_pct"] = 100 * (d.private_mean - d.final) / d.final
    d["usda_err_pct"] = 100 * (d.usda - d.final) / d.final
    return d


def figs(w, st):
    plt = plotstyle.setup()
    s = st[st.season_month != "all"].copy()
    s["season_month"] = s.season_month.astype(int)
    fig, ax = plt.subplots(figsize=(7.5, 4))
    for c, col in zip(COUNTRIES, plotstyle.C):
        g = s[s.country == c].sort_values("season_month")
        ax.plot(g.season_month, g.mean_abs_err_pct, color=col, label=c, marker="o", ms=3)
    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(["May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr"])
    ax.set_ylabel("mean |USDA estimate − final|, % of final")
    ax.set_title("USDA wheat production error by report month, crop years 2005–2024")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(F, "fig_revisions.png"), dpi=150)
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ru = w[w.country == "Russia"]
    for y, col in zip([2010, 2012, 2024, 2021], plotstyle.C):
        g = ru[ru.crop_year == y]
        ax.plot(g.season_month, g.value_mmt / g.final.iloc[-1] * 100 - 100, color=col, label=str(y), marker="o", ms=3)
    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(["May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr"])
    ax.axhline(0, color=plotstyle.MUTED, lw=0.8)
    ax.set_ylabel("USDA Russia estimate vs final, %")
    ax.set_title("USDA Russia wheat path in shock years")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(F, "fig_paths_russia.png"), dpi=150)


def main():
    os.makedirs(R, exist_ok=True)
    w = load_vintages()
    w.to_csv(os.path.join(R, "usda_revisions.csv"), index=False, float_format="%.4f")
    st = revision_stats(w)
    st.to_csv(os.path.join(R, "revision_stats.csv"), index=False, float_format="%.4f")
    print(st[st.season_month == "all"].round(3).to_string())
    px = prices()
    rx, e = reaction(w, px)
    rx.to_csv(os.path.join(R, "wasde_day_reaction.csv"), index=False, float_format="%.4f")
    print(rx.round(3).to_string())
    pv = private_vs_usda(w)
    if pv is not None:
        pv.to_csv(os.path.join(R, "private_vs_usda.csv"), index=False, float_format="%.4f")
        d = pv.dropna(subset=["next_rev_pct"])
        m = clustered(d.rev_pct, d[["priv_minus_usda_prev_pct"]], d.crop_year)
        print("USDA revision on (private - previous USDA):", m.params.round(3).to_dict(), m.tvalues.round(2).to_dict(), len(d))
        m2 = clustered(d.next_rev_pct, d[["priv_minus_usda_pct"]], d.crop_year)
        print("next USDA revision on (private - current USDA):", m2.params.round(3).to_dict(), m2.tvalues.round(2).to_dict())
        print("mean |err| private vs usda (same dates):", d.priv_err_pct.abs().mean().round(2), d.usda_err_pct.abs().mean().round(2))
    figs(w, st)


if __name__ == "__main__":
    main()
