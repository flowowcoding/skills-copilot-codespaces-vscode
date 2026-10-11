#!/usr/bin/env python3
"""Report-day price reaction to USDA US corn/soybean yield surprises.

Steps
  1. events: one row per (Crop Production Aug/Sep/Oct/Nov or January Annual Summary report, crop)
     with USDA yield/production, the previous USDA number (Aug: July WASDE; Sep-Nov: previous
     Crop Production; Jan: November Crop Production), the pre-report consensus, surprises and
     report-day returns.
  2. price series (all close-to-close log returns, %, on the release date; the release is at
     12:00 ET -- 08:30 ET before 2013 -- and the settlement comes after it):
       r_main  = Teucrium ETF (CORN from 2010-06, SOYB from 2011-09: new-crop-weighted, roll-free);
                 before that the Yahoo continuous future on days when it is liquid (volume >= 20% of
                 its 60-day median and not a roll day), else missing.
       r_cont  = continuous future (ZC=F / ZS=F), liquid days only.
       r_nc    = true new-crop contract (ZCZ26, ZSX26, ZSX25) where Yahoo still serves it.
     Cents/bushel = return x previous settlement of the continuous future.
  3. (a) variance ratio of report days vs "normal" days (no USDA WASDE / Crop Production / Acreage /
         Prospective Plantings / Grain Stocks release, no roll), same calendar month and years;
     (b) return on surprise vs consensus, (c) vs previous USDA, (d) predictability of the
     surprise from public information (leave-one-year-out), (e) value of knowing the sign.
  4. intraday check with Yahoo 60-minute bars (last 730 days only).

Usage:
    python -I analysis.py --data ../data --out ../results --figs ../figures
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plotstyle as ps  # noqa: E402

MONTHS = {8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 1: "Jan", 2: "Jan"}
COMMISSION_CBU = 0.10   # ~$5 round-turn commission+fees per 5,000 bu contract = 0.10 c/bu
TICK_CBU = 0.25         # one tick = 1/4 cent = $12.50 per contract
COST_CBU = COMMISSION_CBU + 2 * TICK_CBU  # one tick of slippage on entry and on exit


# ----------------------------------------------------------------------------- prices
def load_prices(d):
    p = {}
    for crop, f, etf in [("corn", "cbot_corn_zc_daily.csv", "CORN"), ("soybeans", "cbot_soy_zs_daily.csv", "SOYB")]:
        c = pd.read_csv(os.path.join(d, "prices", f), parse_dates=["date"]).set_index("date")
        c["vrel"] = c.volume / c.volume.rolling(60, min_periods=20).median().shift(1)
        c["liquid"] = (c.vrel >= 0.2) & (c.roll == 0)
        e = pd.read_csv(os.path.join(d, "prices", "etf_daily.csv"), parse_dates=["date"])
        e = e[e.symbol == etf].set_index("date")
        df = pd.DataFrame({"r_cont_raw": c.ret * 100, "liquid": c.liquid, "fut_close": c.close,
                           "roll": c.roll})
        df["fut_prev"] = df.fut_close.shift(1)
        df = df.join((e.ret * 100).rename("r_etf"), how="outer")
        df["r_cont"] = df.r_cont_raw.where(df.liquid.fillna(False).astype(bool))
        df["r_main"] = df.r_etf.where(df.r_etf.notna(), df.r_cont)
        df["src_main"] = np.where(df.r_etf.notna(), "etf", np.where(df.r_cont.notna(), "cont", ""))
        p[crop] = df
    k = pd.read_csv(os.path.join(d, "prices", "contracts_daily.csv"), parse_dates=["date"])
    k["ret"] = k.ret * 100
    return p, k


def newcrop_ret(k, crop, year, date):
    sym = {("corn", 2026): "ZCZ26.CBT", ("soybeans", 2026): "ZSX26.CBT", ("soybeans", 2025): "ZSX25.CBT"}.get(
        (crop, year))
    if sym is None:
        return np.nan, np.nan
    x = k[(k.symbol == sym) & (k.date == date)]
    if x.empty:
        return np.nan, np.nan
    prev = k[(k.symbol == sym) & (k.date < date)].sort_values("date").close
    return float(x.ret.iloc[0]), float(prev.iloc[-1]) if len(prev) else np.nan


# ----------------------------------------------------------------------------- events
def build_events(d, prices, k):
    nass = pd.read_parquet(os.path.join(d, "interim", "nass_report_vintages.parquet"))
    nass = nass[nass.region == "US"].copy()
    nass["value"] = np.where(nass.variable == "yield", nass.value, nass.value / 1000)
    w = pd.read_csv(os.path.join(d, "interim", "wasde_us_vintages.csv"))
    cons = pd.read_csv(os.path.join(d, "consensus", "consensus.csv"))
    cond = pd.read_csv(os.path.join(d, "interim", "crop_condition.csv"))
    cond = cond[cond.region == "US"]
    cp = nass[nass.report.isin(["crop_production", "crop_production_annual"])]
    piv = cp.pivot_table(index=["release_date", "report", "crop", "crop_year"], columns="variable",
                         values="value").reset_index()
    rows = []
    for crop in ["corn", "soybeans"]:
        g = piv[piv.crop == crop].sort_values("release_date").reset_index(drop=True)
        wc = w[(w.crop == crop)]
        for i, r in g.iterrows():
            rd = pd.Timestamp(r.release_date)
            m = MONTHS[rd.month]
            prev_yield = prev_prod = prev_date = prev2_yield = None
            same = g[(g.crop_year == r.crop_year) & (g.release_date < r.release_date)]
            ww = wc[(wc.crop_year == r.crop_year) & (wc.release_date < r.release_date)]
            if m == "Aug" or same.empty:
                # previous USDA = latest WASDE projection before the report (July)
                last = ww.release_date.max()
                x = ww[ww.release_date == last].set_index("variable").value
                prev_yield, prev_prod, prev_date = x.get("yield"), x.get("production"), last
                d2 = ww[ww.release_date < last].release_date.max()
                x2 = ww[ww.release_date == d2].set_index("variable").value
                prev2_yield = x2.get("yield")
            else:
                s = same.iloc[-1]
                prev_yield, prev_prod, prev_date = s["yield"], s["production"], s.release_date
                if len(same) >= 2:
                    prev2_yield = same.iloc[-2]["yield"]
                else:
                    x2 = ww[ww.release_date < prev_date]
                    x2 = x2[x2.release_date == x2.release_date.max()].set_index("variable").value
                    prev2_yield = x2.get("yield")
            c = cons[(cons.report_date == r.release_date) & (cons.crop == crop)].set_index("variable")
            cy = c.consensus.get("yield", np.nan)
            cpr = c.consensus.get("production", np.nan)
            # crop condition: latest rating released (16:00 ET) strictly before the release day
            cc = cond[(cond.crop == crop) & (cond.release_date < r.release_date)]
            cc_y = cc[cc.crop_year == r.crop_year]
            ge_now = cc_y.cond_ge_pct.iloc[-1] if len(cc_y) else np.nan
            ci_now = cc_y.cond_index.iloc[-1] if len(cc_y) else np.nan
            cc_prev = cc_y[cc_y.release_date < str(prev_date)]
            ge_prev = cc_prev.cond_ge_pct.iloc[-1] if len(cc_prev) else np.nan
            # same-week G/E in earlier years (PIT: only past crop years)
            wk = pd.Timestamp(cc_y.WEEK_ENDING.iloc[-1]).dayofyear if len(cc_y) else None
            hist = cond[(cond.crop == crop) & (cond.crop_year < r.crop_year) & (cond.crop_year >= r.crop_year - 10)]
            if wk is not None and len(hist):
                hd = pd.to_datetime(hist.WEEK_ENDING).dt.dayofyear
                hh = hist[(hd - wk).abs() <= 3]
                ge_norm = hh.cond_ge_pct.mean()
            else:
                ge_norm = np.nan
            p = prices[crop]
            ret_main = p.r_main.get(rd, np.nan)
            src = p.src_main.get(rd, "")
            nc, nc_prev = newcrop_ret(k, crop, rd.year if m != "Jan" else rd.year - 1, rd)
            rows.append(dict(
                release_date=r.release_date, month=m, report=r.report, crop=crop, crop_year=int(r.crop_year),
                release_time_et="08:30" if r.release_date < "2013-01-11" else "12:00",
                usda_yield=r["yield"], usda_prod=r["production"], usda_area=r["harvested_area"],
                prev_date=prev_date, prev_yield=prev_yield, prev_prod=prev_prod, prev2_yield=prev2_yield,
                cons_yield=cy, cons_prod=cpr,
                cons_source=c.source.get("yield", c.source.get("production", "")) if len(c) else "",
                ge_now=ge_now, ge_prev=ge_prev, ge_norm=ge_norm, cond_index=ci_now,
                r_main=ret_main, src_main=src, r_cont=p.r_cont.get(rd, np.nan), r_etf=p.r_etf.get(rd, np.nan),
                r_newcrop=nc, fut_prev=p.fut_prev.get(rd, np.nan), newcrop_prev=nc_prev))
    e = pd.DataFrame(rows)
    for c in ["prev_yield", "prev_prod", "prev2_yield", "ge_now", "ge_prev", "ge_norm", "cond_index"]:
        e[c] = pd.to_numeric(e[c].map(lambda v: v.iloc[0] if isinstance(v, pd.Series) else v), errors="coerce")
    e["cons_yield_eff"] = e.cons_yield.where(e.cons_yield.notna(), e.cons_prod / e.usda_area)
    e["cons_yield_implied"] = e.cons_yield.isna() & e.cons_prod.notna()
    e["surp_bu"] = e.usda_yield - e.cons_yield_eff
    e["surp_pct"] = 100 * (e.usda_yield / e.cons_yield_eff - 1)
    e["surp_prod_pct"] = 100 * (e.usda_prod / e.cons_prod - 1)
    e["rev_bu"] = e.usda_yield - e.prev_yield
    e["rev_pct"] = 100 * (e.usda_yield / e.prev_yield - 1)
    e["exp_rev_pct"] = 100 * (e.cons_yield_eff / e.prev_yield - 1)   # analysts' expected revision
    e["prior_rev_pct"] = 100 * (e.prev_yield / e.prev2_yield - 1)
    e["d_ge"] = e.ge_now - e.ge_prev
    e["ge_dev"] = e.ge_now - e.ge_norm
    e["price_cbu"] = e.fut_prev
    e["r_main_cbu"] = e.r_main / 100 * e.price_cbu
    # best available reaction: true new-crop contract when Yahoo has it, else r_main
    e["r_best"] = e.r_newcrop.where(e.r_newcrop.notna(), e.r_main)
    e["r_best_cbu"] = np.where(e.r_newcrop.notna(), e.r_newcrop / 100 * e.newcrop_prev, e.r_main_cbu)
    return e.sort_values(["crop", "release_date"]).reset_index(drop=True)


# ----------------------------------------------------------------------------- helpers
def ols(y, X, names):
    X = sm.add_constant(np.column_stack(X), has_constant="add") if len(X) else np.ones((len(y), 1))
    m = sm.OLS(y, X, missing="drop").fit(cov_type="HC1")
    out = {"n": int(m.nobs), "r2": m.rsquared}
    for j, nm in enumerate(["const"] + names):
        out[f"b_{nm}"] = m.params[j]
        out[f"t_{nm}"] = m.tvalues[j]
    return out


def report_days(d):
    """All USDA report dates that move grain prices (excluded from the normal-day sample)."""
    s = set()
    nass = pd.read_parquet(os.path.join(d, "interim", "nass_report_vintages.parquet"))
    s |= set(nass.release_date)
    w = pd.read_csv(os.path.join(d, "interim", "wasde_us_vintages.csv"))
    s |= set(w.release_date)
    o = pd.read_csv(os.path.join(d, "reference", "other_release_dates.csv"))
    s |= set(o[o.slug == "grain-stocks"].release_date)
    return {pd.Timestamp(x) for x in s}


# ----------------------------------------------------------------------------- analyses
def variance_ratio(e, prices, rdays):
    rows = []
    for crop in ["corn", "soybeans"]:
        p = prices[crop]
        for m, mm in [("Aug", [8]), ("Sep", [9]), ("Oct", [10]), ("Nov", [11]), ("Jan", [1, 2])]:
            ev = e[(e.crop == crop) & (e.month == m)].dropna(subset=["r_main"])
            for series in ["r_main", "r_cont"]:
                evr = ev[series].dropna() if series in ev else ev.r_main
                if len(evr) < 5:
                    continue
                yrs = set(pd.to_datetime(ev.loc[evr.index, "release_date"]).dt.year)
                nd = p[(p.index.month.isin(mm)) & (p.index.year.isin(yrs)) & (~p.index.isin(rdays))
                       & (p.roll.fillna(0) == 0)][series].dropna()
                lev = stats.levene(evr, nd, center="median")
                rows.append(dict(crop=crop, month=m, series=series, n_report=len(evr), n_normal=len(nd),
                                 sd_report=evr.std(), sd_normal=nd.std(), var_ratio=evr.var() / nd.var(),
                                 mean_abs_report=evr.abs().mean(), mean_abs_normal=nd.abs().mean(),
                                 levene_p=lev.pvalue, years=f"{min(yrs)}-{max(yrs)}"))
    return pd.DataFrame(rows)


def regressions(e):
    rows = []
    groups = [("Aug", ["Aug"]), ("Sep", ["Sep"]), ("Aug+Sep", ["Aug", "Sep"]), ("Oct", ["Oct"]), ("Nov", ["Nov"]),
              ("Jan", ["Jan"]), ("Aug-Nov", ["Aug", "Sep", "Oct", "Nov"]), ("All", ["Aug", "Sep", "Oct", "Nov", "Jan"])]
    for crop in ["corn", "soybeans"]:
        for gname, ms in groups:
            x = e[(e.crop == crop) & e.month.isin(ms)]
            for yv, ylab in [("r_main", "%"), ("r_main_cbu", "c/bu"), ("r_best", "% (new-crop where available)")]:
                specs = [
                    ("surprise vs consensus, % of consensus", ["surp_pct"]),
                    ("surprise vs consensus, bu/acre", ["surp_bu"]),
                    ("production surprise vs consensus, %", ["surp_prod_pct"]),
                    ("revision vs previous USDA, %", ["rev_pct"]),
                    ("revision vs previous USDA, bu/acre", ["rev_bu"]),
                    ("horse race: surprise % + expected revision %", ["surp_pct", "exp_rev_pct"]),
                ]
                for spec, xs in specs:
                    if yv != "r_main" and spec.startswith(("production", "horse", "revision vs previous USDA, %")):
                        continue
                    xx = x.dropna(subset=[yv] + xs)
                    if len(xx) < 6:
                        continue
                    o = ols(xx[yv].values, [xx[c].values for c in xs], xs)
                    o.update(crop=crop, months=gname, y=ylab, spec=spec,
                             years=f"{xx.crop_year.min()}-{xx.crop_year.max()}")
                    rows.append(o)
    cols = ["crop", "months", "y", "spec", "n", "years", "r2"]
    df = pd.DataFrame(rows)
    rest = [c for c in df.columns if c not in cols]
    return df[cols + rest]


def loyo_predict(df, target, feats):
    """Leave-one-crop-year-out OLS predictions."""
    pred = pd.Series(np.nan, index=df.index)
    for yr in df.crop_year.unique():
        tr, te = df[df.crop_year != yr], df[df.crop_year == yr]
        if len(tr) < len(feats) + 4:
            continue
        X = np.column_stack([np.ones(len(tr))] + [tr[f].values for f in feats])
        b = np.linalg.lstsq(X, tr[target].values, rcond=None)[0]
        pred[te.index] = np.column_stack([np.ones(len(te))] + [te[f].values for f in feats]) @ b
    return pred


def predictability(e):
    rows, preds = [], []
    feats_all = {"constant only (historical mean surprise)": [],
                 "expected revision (consensus - prev USDA)": ["exp_rev_pct"],
                 "prior USDA revision": ["prior_rev_pct"],
                 "G/E change since previous USDA": ["d_ge"],
                 "G/E vs 10-yr same-week mean": ["ge_dev"],
                 "G/E change + G/E dev + expected revision": ["d_ge", "ge_dev", "exp_rev_pct"]}
    for target, tlab in [("surp_pct", "surprise vs consensus (% of consensus)"),
                         ("rev_pct", "revision vs previous USDA (%)")]:
        for crop in ["corn", "soybeans"]:
            for gname, ms in [("Aug", ["Aug"]), ("Sep", ["Sep"]), ("Aug-Nov", ["Aug", "Sep", "Oct", "Nov"])]:
                x = e[(e.crop == crop) & e.month.isin(ms)]
                for fname, fs in feats_all.items():
                    if target == "rev_pct" and "expected revision" in fname and len(fs) == 1:
                        pass
                    xx = x.dropna(subset=[target] + fs).copy()
                    if len(xx) < 8:
                        continue
                    o = ols(xx[target].values, [xx[f].values for f in fs], fs)
                    pr = loyo_predict(xx, target, fs)
                    ok = pr.notna()
                    yv, pv = xx.loc[ok, target], pr[ok]
                    oos_r2 = 1 - ((yv - pv) ** 2).sum() / ((yv - yv.mean()) ** 2).sum()
                    hit = (np.sign(yv) == np.sign(pv))[yv != 0].mean()
                    cc = np.corrcoef(yv, pv)[0, 1] if fs and pv.std() > 0 else np.nan
                    rows.append(dict(target=tlab, crop=crop, months=gname, features=fname, n=o["n"],
                                     years=f"{xx.crop_year.min()}-{xx.crop_year.max()}", in_sample_r2=o["r2"],
                                     loyo_r2=oos_r2, loyo_sign_hit=hit, corr_pred_actual=cc,
                                     **{k: v for k, v in o.items() if k.startswith(("b_", "t_"))}))
                    if target == "surp_pct" and gname == "Aug-Nov" and len(fs) == 3:
                        preds.append(xx.assign(pred=pr)[["release_date", "crop", "month", "surp_pct", "pred"]])
    return pd.DataFrame(rows), (pd.concat(preds) if preds else pd.DataFrame())


def edge(e, preds):
    rows, trades = [], []
    x = e.dropna(subset=["r_main", "surp_pct"]).copy()
    x = x[x.surp_pct != 0]
    x["dir"] = -np.sign(x.surp_pct)              # smaller crop than expected -> long
    x["gross_cbu"] = x.dir * x.r_main_cbu
    x["cost_cbu"] = COST_CBU
    x["net_cbu"] = x.gross_cbu - x.cost_cbu
    x["net_pct"] = x.net_cbu / x.price_cbu * 100
    x["gross_pct"] = x.dir * x.r_main
    if len(preds):
        x = x.merge(preds[["release_date", "crop", "pred"]], on=["release_date", "crop"], how="left")
    for crop in ["corn", "soybeans"]:
        for gname, ms in [("Aug", ["Aug"]), ("Sep", ["Sep"]), ("Aug+Sep", ["Aug", "Sep"]),
                          ("Aug-Nov", ["Aug", "Sep", "Oct", "Nov"]), ("All incl. Jan", list(MONTHS.values()))]:
            g = x[(x.crop == crop) & x.month.isin(ms)]
            if len(g) < 5:
                continue
            for rule, gg, dcol in [("know sign of surprise (all reports)", g, "dir"),
                                   ("know sign, only |surprise| > median", g[g.surp_pct.abs() > g.surp_pct.abs().median()], "dir"),
                                   ("perfect foresight of return sign (upper bound)", g, "oracle"),
                                   ("sign from public-info model (LOYO)", g.dropna(subset=["pred"]) if "pred" in g else g.iloc[:0], "model")]:
                if len(gg) < 4:
                    continue
                if dcol == "oracle":
                    dirv = np.sign(gg.r_main)
                elif dcol == "model":
                    dirv = -np.sign(gg.pred)
                else:
                    dirv = gg.dir
                gross = dirv * gg.r_main_cbu
                net = gross - COST_CBU
                netp = net / gg.price_cbu * 100
                rows.append(dict(crop=crop, months=gname, rule=rule, n=len(gg),
                                 years=f"{gg.crop_year.min()}-{gg.crop_year.max()}",
                                 hit_rate=(gross > 0).mean(), mean_gross_cbu=gross.mean(), mean_net_cbu=net.mean(),
                                 mean_net_pct=netp.mean(), t_net=netp.mean() / (netp.std(ddof=1) / np.sqrt(len(netp))),
                                 mean_net_usd_per_contract=net.mean() * 50, cost_cbu=COST_CBU,
                                 total_net_cbu=net.sum()))
    return pd.DataFrame(rows), x


def intraday(d, e):
    x = pd.read_csv(os.path.join(d, "prices", "intraday_60m.csv"))
    x["ts"] = pd.to_datetime(x.ts_utc, utc=True).dt.tz_convert("America/New_York")
    x["date"] = x.ts.dt.date.astype(str)
    rows = []
    for r in e[e.release_date >= "2024-10-01"].itertuples():
        # Yahoo's intraday continuous series (ZC=F/ZS=F) appears to be re-mapped to the current
        # front contract, so only the individual contract is used here.
        for sym in (["ZCZ26.CBT"] if r.crop == "corn" else ["ZSX26.CBT"]):
            s = x[x.symbol == sym].sort_values("ts")
            day = s[s.date == r.release_date]
            prev = s[s.ts < pd.Timestamp(r.release_date + " 00:00", tz="America/New_York")]
            if day.empty or prev.empty:
                continue
            # previous settlement proxy: last bar of the previous session before 14:20 ET
            pv = prev[prev.ts.dt.hour < 15].close.iloc[-1] if (prev.ts.dt.hour < 15).any() else prev.close.iloc[-1]
            pre = day[day.ts.dt.hour < 12]          # bars that END by 12:00 ET (bar start < 11:xx)
            pre = pre[pre.ts + pd.Timedelta(hours=1) <= pd.Timestamp(r.release_date + " 12:00", tz="America/New_York")]
            post = day[(day.ts.dt.hour >= 12) & (day.ts.dt.hour < 15)]
            if pre.empty or post.empty:
                continue
            p_pre, p_close = pre.close.iloc[-1], post.close.iloc[-1]
            role = "new-crop" if (r.crop_year == 2026) else "deferred (next year's crop)"
            rows.append(dict(release_date=r.release_date, crop=r.crop, month=r.month, symbol=sym, contract_role=role,
                             surp_pct=r.surp_pct, ret_prevclose_to_1200=100 * np.log(p_pre / pv),
                             ret_1200_to_close=100 * np.log(p_close / p_pre), ret_total=100 * np.log(p_close / pv)))
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------- figures
def figures(e, vr, preds, trades, figdir):
    os.makedirs(figdir, exist_ok=True)
    for crop, fn, nm in [("corn", "fig1_corn_reaction_vs_surprise.png", "Corn"),
                         ("soybeans", "fig2_soy_reaction_vs_surprise.png", "Soybeans")]:
        fig, ax = ps.single(6.5, 4.0)
        for i, (m, lab) in enumerate([("Aug", "August"), ("Sep", "September"), ("Oct", "October/November"),
                                      ("Jan", "January final")]):
            ms = ["Oct", "Nov"] if m == "Oct" else [m]
            g = e[(e.crop == crop) & e.month.isin(ms)].dropna(subset=["surp_pct", "r_main"])
            ax.scatter(g.surp_pct, g.r_main, s=22, color=ps.C[i], label=f"{lab} (n={len(g)})", alpha=0.9,
                       edgecolor="none")
            if m in ("Aug", "Sep") and len(g) > 5:
                b = np.polyfit(g.surp_pct, g.r_main, 1)
                xs = np.linspace(g.surp_pct.min(), g.surp_pct.max(), 10)
                ax.plot(xs, np.polyval(b, xs), color=ps.C[i], lw=1.2)
        for r in e[(e.crop == crop)].dropna(subset=["surp_pct", "r_main"]).itertuples():
            if abs(r.r_main) > 4.5 or abs(r.surp_pct) > 3.0:
                ax.annotate(r.release_date[:7], (r.surp_pct, r.r_main), fontsize=6.5, color=ps.TEXT,
                            xytext=(3, 3), textcoords="offset points")
        ax.axhline(0, color=ps.GRID, lw=0.8)
        ax.axvline(0, color=ps.GRID, lw=0.8)
        ax.set_xlabel("USDA yield minus pre-report consensus, % of consensus")
        ax.set_ylabel("report-day return, % (close to close)")
        ax.set_title(f"{nm}: report-day return vs yield surprise against the trade consensus, 2005-2026",
                     loc="left")
        ax.legend(frameon=False, loc="upper right")
        ps.save(fig, os.path.join(figdir, fn))
    # variance ratio
    fig, ax = ps.single(6.5, 3.2)
    v = vr[vr.series == "r_main"]
    months = ["Aug", "Sep", "Oct", "Nov", "Jan"]
    for i, crop in enumerate(["corn", "soybeans"]):
        vv = v[v.crop == crop].set_index("month").reindex(months)
        ax.bar(np.arange(5) + (i - 0.5) * 0.38, vv.var_ratio, width=0.36, color=ps.C[i], label=crop)
        for j, val in enumerate(vv.var_ratio):
            if pd.notna(val):
                ax.text(j + (i - 0.5) * 0.38, val + 0.1, f"{val:.1f}", ha="center", fontsize=7, color=ps.TEXT)
    ax.axhline(1, color=ps.TEXT, lw=0.6, ls=":")
    ax.set_xticks(range(5), ["August", "September", "October", "November", "January"])
    ax.set_ylabel("variance of report-day return / normal days")
    ax.set_title("Report-day return variance relative to non-report days in the same month", loc="left")
    ax.legend(frameon=False)
    ps.save(fig, os.path.join(figdir, "fig3_variance_ratio.png"))
    # predictability
    if len(preds):
        fig, ax = ps.single(5.5, 4.0)
        for i, crop in enumerate(["corn", "soybeans"]):
            g = preds[preds.crop == crop].dropna()
            ax.scatter(g.pred, g.surp_pct, s=20, color=ps.C[i], label=f"{crop} (n={len(g)})", edgecolor="none")
        lim = max(abs(preds.surp_pct).max(), 1)
        ax.plot([-lim, lim], [-lim, lim], color=ps.GRID, lw=0.8)
        ax.axhline(0, color=ps.GRID, lw=0.6)
        ax.axvline(0, color=ps.GRID, lw=0.6)
        ax.set_xlabel("predicted surprise, % (leave-one-year-out; crop condition + expected revision)")
        ax.set_ylabel("actual surprise vs consensus, %")
        ax.set_title("Free public information barely predicts the surprise vs consensus (Aug-Nov)", loc="left")
        ax.legend(frameon=False)
        ps.save(fig, os.path.join(figdir, "fig4_surprise_predictability.png"))
    # cumulative P&L knowing the sign
    fig, ax = ps.single(6.5, 3.2)
    for i, crop in enumerate(["corn", "soybeans"]):
        t = trades[(trades.crop == crop) & trades.month.isin(["Aug", "Sep"])].sort_values("release_date")
        ax.plot(pd.to_datetime(t.release_date), t.net_cbu.cumsum(), color=ps.C[i], lw=1.5,
                label=f"{crop}: {len(t)} trades, mean {t.net_cbu.mean():.1f} c/bu net")
    ax.axhline(0, color=ps.GRID, lw=0.8)
    ax.set_ylabel("cumulative net cents/bushel")
    ax.set_title("Knowing the sign of the Aug/Sep yield surprise one day early: cumulative net P&L", loc="left")
    ax.legend(frameon=False, loc="upper left")
    ps.save(fig, os.path.join(figdir, "fig5_sign_knowledge_pnl.png"))


def summarise(r):
    """Compact table of the headline slopes (one row per crop x month group)."""
    out = []
    for crop in ["corn", "soybeans"]:
        for m in ["Aug", "Sep", "Aug+Sep", "Oct", "Nov", "Jan", "Aug-Nov"]:
            g = r[(r.crop == crop) & (r.months == m)]

            def get(y, spec, b):
                x = g[(g.y == y) & (g.spec == spec)]
                if not len(x):
                    return (np.nan,) * 5
                x = x.iloc[0]
                return x[f"b_{b}"], x[f"t_{b}"], x.n, x.r2, x.years
            a = get("%", "surprise vs consensus, % of consensus", "surp_pct")
            b = get("%", "surprise vs consensus, bu/acre", "surp_bu")
            c = get("c/bu", "surprise vs consensus, bu/acre", "surp_bu")
            d = get("%", "revision vs previous USDA, %", "rev_pct")
            p = get("%", "production surprise vs consensus, %", "surp_prod_pct")
            e = get("% (new-crop where available)", "surprise vs consensus, % of consensus", "surp_pct")
            h = g[(g.y == "%") & g.spec.str.startswith("horse")]
            out.append(dict(crop=crop, months=m, n=a[2], years=a[4], pct_per_1pct_surprise=a[0], t=a[1], r2=a[3],
                            pct_per_bu_acre=b[0], t_bu=b[1], cents_per_bu_acre=c[0], t_cents=c[1],
                            rev_pct_per_1pct=d[0], t_rev=d[1], n_rev=d[2], r2_rev=d[3],
                            horse_surprise=h.b_surp_pct.iloc[0] if len(h) else np.nan,
                            t_horse_surprise=h.t_surp_pct.iloc[0] if len(h) else np.nan,
                            horse_expected_rev=h.b_exp_rev_pct.iloc[0] if len(h) else np.nan,
                            t_horse_expected_rev=h.t_exp_rev_pct.iloc[0] if len(h) else np.nan,
                            prod_surprise_pct=p[0], t_prod=p[1], n_prod=p[2],
                            newcrop_override_pct=e[0], t_newcrop_override=e[1]))
    return pd.DataFrame(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--figs", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    prices, k = load_prices(a.data)
    e = build_events(a.data, prices, k)
    e.to_csv(os.path.join(a.out, "events.csv"), index=False, float_format="%.4f")
    rdays = report_days(a.data)
    vr = variance_ratio(e, prices, rdays)
    vr.to_csv(os.path.join(a.out, "variance_ratio.csv"), index=False, float_format="%.4f")
    rg = regressions(e)
    rg.to_csv(os.path.join(a.out, "regressions.csv"), index=False, float_format="%.4f")
    summarise(rg).to_csv(os.path.join(a.out, "summary_reaction.csv"), index=False, float_format="%.3f")
    pr, preds = predictability(e)
    pr.to_csv(os.path.join(a.out, "surprise_predictability.csv"), index=False, float_format="%.4f")
    ed, trades = edge(e, preds)
    ed.to_csv(os.path.join(a.out, "sign_knowledge_edge.csv"), index=False, float_format="%.4f")
    it = intraday(a.data, e)
    it.to_csv(os.path.join(a.out, "intraday_check.csv"), index=False, float_format="%.4f")
    # tracking of the price proxies on event days where the true new-crop contract exists
    tr = e.dropna(subset=["r_newcrop"])[["release_date", "crop", "month", "r_newcrop", "r_etf", "r_cont"]]
    tr.to_csv(os.path.join(a.out, "proxy_tracking_event_days.csv"), index=False, float_format="%.3f")
    figures(e, vr, preds, trades, a.figs)
    pd.set_option("display.width", 220, "display.max_columns", 30)
    print("events with consensus+return:", e.dropna(subset=["surp_pct", "r_main"]).groupby(["crop", "month"]).size())
    print(vr[vr.series == "r_main"].round(3).to_string())
    key = rg[(rg.y == "%") & rg.spec.isin(["surprise vs consensus, % of consensus", "surprise vs consensus, bu/acre",
                                             "revision vs previous USDA, %"])]
    print(key[["crop", "months", "spec", "n", "years", "r2"] + [c for c in key.columns if c.startswith(("b_s", "t_s", "b_r", "t_r"))]].round(3).to_string())
    print(pr.round(3).to_string())
    print(ed.round(3).to_string())
    print(it.round(2).to_string())
    print(tr.round(2).to_string())


if __name__ == "__main__":
    main()
