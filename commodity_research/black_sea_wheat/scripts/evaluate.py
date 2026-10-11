#!/usr/bin/env python3
"""Pre-registered evaluation of the Black Sea wheat satellite signal (see README.md).

Periods: development 2008-2020, holdout 2021-2025, live 2026. Ukraine 2022+ is reported but
excluded from pooled metrics (war).

  accuracy      mean |error| vs the USDA final (% of final) of the satellite estimate, the trend,
                and USDA's latest estimate before T, by country and season month (WASDE dates)
  test (a)      Russia: next USDA revision (100 ln USDA_R / USDA_prev) on satellite-minus-USDA
                gap (100 ln S / USDA_prev) and the previous USDA revision (persistence); OLS with
                crop-year clustered t. Sign hit rate when |gap| > 3 %. Also pooled 3 countries.
                Secondary (Russia): adding the private-minus-USDA gap (IKAR/SovEcon/MinAg, latest
                per forecaster within 45 days before T) as a control.
  test (b)      lead weeks: in every country-year with |final - first USDA| >= 5 % of the first USDA
                (USDA's May number), the date each source first MOVES >= 5 % away from its own value
                at USDA's first report, in the direction of the final: weekly satellite vs WASDE vs
                (Russia) private estimates. False alarms reported (see test_b docstring).
  test (c)      prices: (i) WASDE day, Russia May-Dec reports with |gap| >= 2 %: long if satellite
                below USDA, short if above, close before -> release-day close; (ii) weekly dates
                Apr 1 .. Sep 23, same rule, hold 5/10/15/20 trading days from the close of the first
                trading day >= T; costs 0.6 c/bu round trip (ZW, KE) or 10 bp (WEAT). Slope of the
                forward return on the gap with Newey-West t.  Benchmark rule: persistence (sign of
                the previous USDA revision).

Usage: python evaluate.py --tag v1 [--holdout]   (without --holdout only development rows are scored)
Writes results/*_<tag>[_holdout].csv and figures.
"""
import argparse
import os

import numpy as np
import pandas as pd
import statsmodels.api as sm

import plotstyle

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "..", "data")
R = os.path.join(HERE, "..", "results")
F = os.path.join(HERE, "..", "figures")
DEV = range(2008, 2021)
HOLD = range(2021, 2026)
COST_CENTS = 0.6
COST_ETF = 0.10  # % round trip
SHOCK = [2010, 2012, 2018, 2021, 2024, 2025]


def period(y):
    return "dev" if y in DEV else ("holdout" if y in HOLD else ("live" if y == 2026 else "pre"))


def clustered(d, y, xs):
    d = d.dropna(subset=[y] + xs)
    if len(d) < 5 or d.year.nunique() < 3:
        return None
    m = sm.OLS(d[y], sm.add_constant(d[xs])).fit(cov_type="cluster", cov_kwds={"groups": d.year})
    return m


def load(tag, holdout):
    s = pd.read_csv(os.path.join(D, "signal", f"bsw_signal_{tag}.csv"), parse_dates=["forecast_date", "next_release"])
    s["period"] = s.year.map(period)
    keep = ["dev"] + (["holdout", "live"] if holdout else [])
    s = s[s.period.isin(keep)]
    rv = pd.read_csv(os.path.join(R, "usda_revisions.csv"), parse_dates=["release_date"])
    return s, rv


def usda_tables(rv):
    rv = rv.sort_values("release_date")
    rv["prev2"] = rv.groupby(["country", "crop_year"]).prev.shift(1)
    return rv


def accuracy(s):
    w = s[(s.kind == "wasde") & (s.ukraine_war_flag == 0)].copy()
    w["season_month"] = (w.next_release.dt.year - w.year) * 12 + w.next_release.dt.month - 4
    fin = w.final_usda_expost
    w["err_sat"] = 100 * (w.sat_estimate_mmt - fin) / fin
    w["err_trend"] = 100 * (w.trend_mmt - fin) / fin
    w["err_usda"] = 100 * (w.usda_latest_mmt - fin) / fin
    rows = []
    for (c, p, m), g in w.groupby(["country", "period", "season_month"]):
        rows.append(dict(country=c, period=p, season_month=m, n=len(g), sat=g.err_sat.abs().mean(),
                         trend=g.err_trend.abs().mean(), usda=g.err_usda.abs().mean()))
    for (c, p), g in w.groupby(["country", "period"]):
        rows.append(dict(country=c, period=p, season_month="all", n=len(g), sat=g.err_sat.abs().mean(),
                         trend=g.err_trend.abs().mean(), usda=g.err_usda.abs().mean()))
    return pd.DataFrame(rows), w


def private_gap(w, priv):
    """100 ln(mean of each forecaster's latest Russia estimate published in the 45 days up to T /
    previous USDA). NaN when no private estimate."""
    out = []
    for r in w.itertuples():
        if priv is None or r.country != "Russia":
            out.append(np.nan)
            continue
        q = priv[(priv.crop_year == r.year) & (priv.pub_date <= r.forecast_date) &
                 (priv.pub_date > r.forecast_date - pd.Timedelta(days=45))]
        if q.empty:
            out.append(np.nan)
            continue
        v = q.sort_values("pub_date").groupby("forecaster").value_mmt.last().mean()
        out.append(100 * np.log(v / r.prev))
    return out


def test_a(s, rv, priv=None):
    w = s[(s.kind == "wasde") & (s.ukraine_war_flag == 0)].copy()
    r = rv[["country", "crop_year", "release_date", "value_mmt", "prev", "prev2"]].rename(
        columns={"crop_year": "year", "release_date": "next_release", "value_mmt": "usda_new"})
    w = w.merge(r, on=["country", "year", "next_release"], how="inner")
    w["rev_next"] = 100 * np.log(w.usda_new / w.prev)
    w["prev_rev"] = 100 * np.log(w.prev / w.prev2)
    w["gap"] = 100 * np.log(w.sat_estimate_mmt / w.prev)
    w = w.dropna(subset=["rev_next", "gap"])
    w["priv_gap"] = private_gap(w, priv)
    rows = []
    for scope, d0 in [("Russia", w[w.country == "Russia"]), ("pooled3", w)]:
        for p, d in d0.groupby("period"):
            specs = [("persistence", ["prev_rev"]), ("gap", ["gap"]), ("gap+persistence", ["gap", "prev_rev"])]
            if scope == "Russia":
                specs += [("private+persistence", ["priv_gap", "prev_rev"]),
                          ("gap+private+persistence", ["gap", "priv_gap", "prev_rev"])]
            for spec, xs in specs:
                m = clustered(d, "rev_next", xs)
                if m is None:
                    continue
                big = d[(d.gap.abs() > 3) & (d.rev_next != 0)]
                rows.append(dict(scope=scope, period=p, spec=spec, n=int(m.nobs), years=d.year.nunique(),
                                 b_gap=m.params.get("gap", np.nan), t_gap=m.tvalues.get("gap", np.nan),
                                 b_prev=m.params.get("prev_rev", np.nan), t_prev=m.tvalues.get("prev_rev", np.nan),
                                 b_priv=m.params.get("priv_gap", np.nan), t_priv=m.tvalues.get("priv_gap", np.nan),
                                 r2=m.rsquared, hit_gap3=(np.sign(big.gap) == np.sign(big.rev_next)).mean(),
                                 n_gap3=len(big)))
    return pd.DataFrame(rows), w


ALL = []


def test_b(s, rv, priv):
    """Lead weeks, measured on each source's OWN move after USDA's first (May) report.
    Base date = USDA's first WASDE for the crop. Big-change country-years: |USDA final / USDA first - 1|
    >= 5 %. USDA crossing = first WASDE >= 5 % away from its first number in the direction of the final.
    Satellite crossing = first weekly estimate (dated after the base date) >= 5 % away from the satellite's
    own estimate the day before the base date, same direction. Private (Russia) = first private estimate
    >= 5 % away from the latest private estimate published before the base date (else from USDA first).
    False alarms: in every country-year, the direction of the satellite's first +-5 % move after the base
    date vs the direction of USDA's eventual change."""
    wk = s[s.kind == "weekly"]
    wa = s[s.kind == "wasde"]
    rows = []
    for (c, y), g in wk.groupby(["country", "year"]):
        u = rv[(rv.country == c) & (rv.crop_year == y)].sort_values("release_date")
        if u.empty or (c == "Ukraine" and y >= 2022):
            continue
        base, d0 = u.value_mmt.iloc[0], u.release_date.iloc[0]
        fin = u.final.iloc[0]
        chg = (fin - base) / base
        s0 = wa[(wa.country == c) & (wa.year == y) & (wa.next_release == d0)]
        if s0.empty:
            continue
        sbase = s0.sat_estimate_mmt.iloc[0]
        g = g[g.forecast_date >= d0].sort_values("forecast_date")
        dev = g.sat_estimate_mmt / sbase - 1
        x0 = g[dev.abs() >= 0.05]
        ALL.append(dict(country=c, year=y, period=period(y), change_pct=100 * chg,
                        sat_first_move=x0.forecast_date.iloc[0].date() if len(x0) else None,
                        sat_move_sign=float(np.sign(dev[x0.index[0]])) if len(x0) else 0.0))
        if abs(chg) < 0.05:
            continue
        sg = np.sign(chg)
        sd = g[dev * sg >= 0.05].forecast_date
        ud = u[(u.value_mmt / base - 1) * sg >= 0.05].release_date
        row = dict(country=c, year=y, period=period(y), usda_first=base, usda_first_date=d0.date(), final=fin,
                   change_pct=100 * chg, sat_at_base=sbase,
                   sat_cross=sd.iloc[0].date() if len(sd) else None,
                   usda_cross=ud.iloc[0].date() if len(ud) else None)
        if len(sd) and len(ud):
            row["lead_weeks"] = (ud.iloc[0] - sd.iloc[0]).days / 7
            at = g[g.forecast_date <= ud.iloc[0]]
            row["sat_on_side_at_usda_cross"] = bool(((at.sat_estimate_mmt.iloc[-1] / sbase - 1) * sg) >= 0.05) if len(at) else None
        if priv is not None and c == "Russia":
            q = priv[priv.crop_year == y].sort_values("pub_date")
            pre = q[q.pub_date < d0]
            pbase = pre.value_mmt.iloc[-1] if len(pre) else base
            post = q[q.pub_date >= d0]
            pd_ = post[(post.value_mmt / pbase - 1) * sg >= 0.05].pub_date
            row["private_base"] = pbase
            row["private_cross"] = pd_.iloc[0].date() if len(pd_) else None
            if len(pd_) and len(ud):
                row["private_lead_weeks"] = (ud.iloc[0] - pd_.iloc[0]).days / 7
            if len(pd_) and len(sd):
                row["sat_minus_private_lead_weeks"] = (pd_.iloc[0] - sd.iloc[0]).days / 7
        rows.append(row)
    return pd.DataFrame(rows)


def prices():
    out = {}
    for n, k in [("cbot_wheat_zw", "ZW"), ("kc_wheat_ke", "KE"), ("teucrium_weat", "WEAT")]:
        p = pd.read_csv(os.path.join(D, "prices", f"{n}_daily.csv"), parse_dates=["date"]).set_index("date")
        out[k] = p
    return out


def cost_pct(k, price):
    return COST_ETF if k == "WEAT" else 100 * COST_CENTS / price


def test_c(s, rv, px):
    rows, trades = [], []
    # (i) WASDE day
    w = s[(s.kind == "wasde") & (s.country == "Russia")].copy()
    w["season_month"] = (w.next_release.dt.year - w.year) * 12 + w.next_release.dt.month - 4
    w = w[w.season_month <= 8]
    rr = rv[rv.country == "Russia"][["crop_year", "release_date", "prev", "prev2"]].rename(
        columns={"crop_year": "year", "release_date": "next_release"})
    w = w.merge(rr, on=["year", "next_release"], how="left")
    w["gap"] = 100 * np.log(w.sat_estimate_mmt / w.prev)
    w["prev_rev"] = 100 * np.log(w.prev / w.prev2)
    for k, p in px.items():
        r = p.ret.where(p.roll == 0) * 100
        for rule in ["satellite", "persistence"]:
            for per, d in w.groupby("period"):
                res = []
                for x in d.itertuples():
                    if x.next_release not in r.index or not np.isfinite(r.loc[x.next_release]):
                        continue
                    if rule == "satellite":
                        if not np.isfinite(x.gap) or abs(x.gap) < 2:
                            continue
                        pos = -np.sign(x.gap)
                    else:
                        if not np.isfinite(x.prev_rev) or x.prev_rev == 0:
                            continue
                        pos = -np.sign(x.prev_rev)
                    prc = p.close.shift(1).loc[x.next_release]
                    g = pos * r.loc[x.next_release]
                    res.append(dict(year=x.year, date=x.next_release, pos=pos, gross=g, net=g - cost_pct(k, prc)))
                    trades.append(dict(test="wasde_day", series=k, rule=rule, period=per, **res[-1]))
                if res:
                    q = pd.DataFrame(res)
                    rows.append(dict(test="wasde_day", series=k, rule=rule, period=per, horizon_d=1, n=len(q),
                                     hit=(q.gross > 0).mean(), mean_gross_pct=q.gross.mean(), mean_net_pct=q.net.mean(),
                                     t_net=q.net.mean() / (q.net.std(ddof=1) / np.sqrt(len(q))) if len(q) > 2 else np.nan))
    # (ii) weekly signals, 1-4 week holds
    wk = s[(s.kind == "weekly") & (s.country == "Russia")].copy()
    wk = wk[wk.forecast_date.dt.month.between(4, 9)]
    wk["gap"] = wk.gap_sat_usda_pct
    for k, p in px.items():
        r = (p.ret.where(p.roll == 0).fillna(0) * 100)
        idx = r.index
        cs = r.cumsum()
        for h in [5, 10, 15, 20]:
            for per, d in wk.groupby("period"):
                res = []
                for x in d.itertuples():
                    i0 = idx.searchsorted(x.forecast_date)
                    if i0 + h >= len(idx) or not np.isfinite(x.gap):
                        continue
                    fwd = cs.iloc[i0 + h] - cs.iloc[i0]
                    res.append(dict(year=x.year, date=idx[i0], gap=x.gap, fwd=fwd, price=p.close.iloc[i0]))
                if not res:
                    continue
                q = pd.DataFrame(res)
                lags = max(1, h // 5)
                m = sm.OLS(q.fwd, sm.add_constant(q.gap)).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
                t = q[q.gap.abs() >= 2].copy()
                t["pos"] = -np.sign(t.gap)
                t["gross"] = t.pos * t.fwd
                t["net"] = t.gross - [cost_pct(k, pr) for pr in t.price]
                # non-overlapping subsample: every (h/5)-th week within each year
                t["wk"] = t.groupby("year").cumcount()
                tn = t[t.wk % lags == 0]
                rows.append(dict(test=f"weekly_{h}d", series=k, rule="satellite", period=per, horizon_d=h, n=len(tn),
                                 hit=(tn.gross > 0).mean() if len(tn) else np.nan,
                                 mean_gross_pct=tn.gross.mean(), mean_net_pct=tn.net.mean(),
                                 t_net=tn.net.mean() / (tn.net.std(ddof=1) / np.sqrt(len(tn))) if len(tn) > 2 else np.nan,
                                 slope_fwd_on_gap=m.params["gap"], t_slope_hac=m.tvalues["gap"], n_slope=len(q)))
    return pd.DataFrame(rows), pd.DataFrame(trades)


def fig_paths(s, rv, priv, years, suffix):
    plt = plotstyle.setup()
    for y in years:
        g = s[(s.kind == "weekly") & (s.country == "Russia") & (s.year == y)].sort_values("forecast_date")
        if g.empty:
            continue
        u = rv[(rv.country == "Russia") & (rv.crop_year == y)].sort_values("release_date")
        fig, ax = plt.subplots(figsize=(8, 4.2))
        sd = g.uncertainty_log
        ax.fill_between(g.forecast_date, g.sat_estimate_mmt * np.exp(-sd), g.sat_estimate_mmt * np.exp(sd),
                        color=plotstyle.C[0], alpha=0.12, lw=0)
        ax.plot(g.forecast_date, g.sat_estimate_mmt, color=plotstyle.C[0], label="satellite + weather (weekly)")
        ax.step(u.release_date, u.value_mmt, where="post", color=plotstyle.C[1], label="USDA WASDE")
        if priv is not None:
            q = priv[(priv.crop_year == y) & (priv.pub_date.dt.year == y)]
            for f_, col, mk in [("IKAR", plotstyle.C[2], "o"), ("SovEcon", plotstyle.C[3], "s")]:
                qq = q[q.forecaster == f_]
                if len(qq):
                    ax.scatter(qq.pub_date, qq.value_mmt, color=col, s=14, marker=mk, label=f_, zorder=3)
        ax.axhline(u.final.iloc[0], color=plotstyle.MUTED, lw=0.8, ls="--")
        ax.text(g.forecast_date.iloc[0], u.final.iloc[0], " USDA final", color=plotstyle.MUTED, fontsize=8, va="bottom")
        ax.set_xlim(pd.Timestamp(y, 3, 25), pd.Timestamp(y, 12, 31))
        ax.set_ylabel("Russia wheat production, Mt")
        ax.set_title(f"Russia {y}: satellite estimate vs USDA and private forecasts")
        ax.legend(loc="best", fontsize=8)
        fig.tight_layout()
        fig.savefig(os.path.join(F, f"fig_russia_{y}{suffix}.png"), dpi=150)
        plt.close(fig)


def fig_gap(aw, suffix):
    plt = plotstyle.setup()
    d = aw[aw.country == "Russia"]
    fig, ax = plt.subplots(figsize=(6, 4.5))
    for (p, col) in [("dev", plotstyle.C[0]), ("holdout", plotstyle.C[1])]:
        q = d[d.period == p]
        if len(q):
            ax.scatter(q.gap, q.rev_next, s=12, color=col, label=f"{p} (n={len(q)})")
    ax.axhline(0, color=plotstyle.MUTED, lw=0.8)
    ax.axvline(0, color=plotstyle.MUTED, lw=0.8)
    ax.set_xlabel("satellite − previous USDA, % (day before WASDE)")
    ax.set_ylabel("USDA revision at that WASDE, %")
    ax.set_title("Russia: does the satellite gap predict USDA's next revision?")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(F, f"fig_gap_test{suffix}.png"), dpi=150)
    plt.close(fig)


def fig_acc(acc, suffix):
    plt = plotstyle.setup()
    a = acc[(acc.country == "Russia") & (acc.season_month != "all")].copy()
    a["season_month"] = a.season_month.astype(int)
    for p in a.period.unique():
        q = a[a.period == p].sort_values("season_month")
        fig, ax = plt.subplots(figsize=(7, 4))
        for col, lab, c in [("sat", "satellite + weather", plotstyle.C[0]), ("usda", "USDA (latest before date)", plotstyle.C[1]),
                            ("trend", "trend", plotstyle.C[2])]:
            ax.plot(q.season_month, q[col], marker="o", ms=3, color=c, label=lab)
        ax.set_xticks(range(1, 10))
        ax.set_xticklabels(["May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan"])
        ax.set_ylabel("mean |error| vs USDA final, %")
        ax.set_title(f"Russia, {p}: error the day before each WASDE")
        ax.legend()
        fig.tight_layout()
        fig.savefig(os.path.join(F, f"fig_accuracy_{p}{suffix}.png"), dpi=150)
        plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", default="v1")
    ap.add_argument("--holdout", action="store_true")
    a = ap.parse_args()
    suf = f"_{a.tag}" + ("_holdout" if a.holdout else "_dev")
    s, rv = load(a.tag, a.holdout)
    rv = usda_tables(rv)
    pf = os.path.join(D, "private", "private_estimates.csv")
    priv = None
    if os.path.exists(pf):
        priv = pd.read_csv(pf, parse_dates=["pub_date"])
        priv = priv[priv.include == 1]
    acc, _ = accuracy(s)
    acc.to_csv(os.path.join(R, f"accuracy{suf}.csv"), index=False, float_format="%.3f")
    print(acc[acc.season_month == "all"].round(2).to_string())
    ta, aw = test_a(s, rv, priv)
    ta.to_csv(os.path.join(R, f"test_a_revision{suf}.csv"), index=False, float_format="%.4f")
    aw.to_csv(os.path.join(R, f"test_a_rows{suf}.csv"), index=False, float_format="%.4f")
    print(ta.round(3).to_string())
    tb = test_b(s, rv, priv)
    tb.to_csv(os.path.join(R, f"test_b_lead{suf}.csv"), index=False, float_format="%.2f")
    print(tb.to_string())
    fa = pd.DataFrame(ALL)
    fa["big_change"] = fa.change_pct.abs() >= 5
    fa["correct_sign"] = np.where(fa.sat_move_sign == 0, np.nan, np.sign(fa.change_pct) == fa.sat_move_sign)
    fa.to_csv(os.path.join(R, f"test_b_alarms{suf}.csv"), index=False, float_format="%.2f")
    print(fa.groupby(["period", "big_change"]).agg(n=("year", "size"), moved=("sat_move_sign", lambda v: (v != 0).mean()),
                                                   correct=("correct_sign", "mean")).round(2))
    tc, trades = test_c(s, rv, prices())
    tc.to_csv(os.path.join(R, f"test_c_prices{suf}.csv"), index=False, float_format="%.4f")
    trades.to_csv(os.path.join(R, f"test_c_trades{suf}.csv"), index=False, float_format="%.4f")
    print(tc.round(3).to_string())
    fig_paths(s, rv, priv, [y for y in SHOCK + [2026] if (y in DEV) or a.holdout], "")
    fig_gap(aw, suf)
    fig_acc(acc, suf)


if __name__ == "__main__":
    main()
