#!/usr/bin/env python3
"""Descriptive benchmark analysis (no satellite data):

  1. Forecast paths & revisions of Brazil soybean production per season and
     source (Conab, USDA WASDE, IBGE LSPA); big-revision seasons; state
     contributions.
  2. Market reaction: CBOT soybean (ZS=F) log returns on release days vs
     normal days; regression of release-day returns on the revision surprise.
  3. Predictability: autocorrelation of revisions within and across sources,
     forecast-efficiency (Nordhaus) tests.

All inputs are point-in-time: each estimate is used only from its release
timestamp. Event day = the CBOT session whose settlement (13:15 CT) follows
the release (Conab 09:00 BRT, IBGE ~09-12h BRT, WASDE 12:00 ET -> same day).

Usage:
    python analysis.py --data DIR --prices DIR --out RESULTS_DIR --figs FIG_DIR
"""
import argparse
import os

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

import plotstyle as ps

SRC_LABEL = {"conab": "Conab", "usda_wasde": "USDA WASDE", "ibge_lspa": "IBGE LSPA"}
SRC_COLOR = {"conab": ps.C[0], "usda_wasde": ps.C[1], "ibge_lspa": ps.C[2]}
STATES = ["MT", "PR", "RS", "GO", "MS", "BA", "MG", "MA", "PI", "TO"]
MATOPIBA = ["MA", "TO", "PI", "BA"]


def headline_crop(d):
    """Crop a release is 'about': month>=Oct -> Y/Y+1 else (Y-1)/Y."""
    d = pd.to_datetime(pd.Series(d))
    y = np.where(d.dt.month >= 10, d.dt.year, d.dt.year - 1)
    return pd.Series([f"{a}/{(a + 1) % 100:02d}" for a in y], index=d.index)


def season_month(d):
    """Release month index in the season: Oct=1 ... Sep=12; May-Sep of the planting year -> -4..0."""
    d = pd.to_datetime(pd.Series(d))
    return ((d.dt.month - 10) % 12) + 1


def br_paths(pit):
    """Headline-crop BR production paths, one row per (source, vintage)."""
    p = pit[(pit.region == "BR") & (pit.variable == "production")].copy()
    p["release_date"] = pd.to_datetime(p.release_date)
    p["hl"] = headline_crop(p.release_date).values
    keep = ((p.source == "conab") & (p.is_current_crop == 1)) | (p.source == "ibge_lspa") | \
           ((p.source == "usda_wasde") & (p.crop_year == p.hl))
    p = p[keep].sort_values(["source", "crop_year", "release_ts_utc"])
    p["mt"] = p.value / 1000.0
    p["rev"] = p.groupby(["source", "crop_year"]).mt.diff()
    p["k"] = p.groupby(["source", "crop_year"]).cumcount() + 1
    p["smonth"] = season_month(p.release_date).values
    return p


def usda_newcrop(pit):
    """All USDA vintages of each Brazil crop (from its May/June first projection)."""
    p = pit[(pit.source == "usda_wasde") & (pit.region == "BR") & (pit.variable == "production")].copy()
    p["release_date"] = pd.to_datetime(p.release_date)
    p["mt"] = p.value / 1000
    return p.sort_values(["crop_year", "release_date"])


def revision_tables(paths, newcrop, out, pit):
    allv = pit[(pit.region == "BR") & (pit.variable == "production")].sort_values("release_ts_utc")
    latest = allv.groupby(["source", "crop_year"]).value.last() / 1e3
    rows = []
    for (s, c), g in paths.groupby(["source", "crop_year"]):
        g = g.sort_values("release_ts_utc")
        first_any = g.mt.iloc[0]
        if s == "usda_wasde":
            nc = newcrop[newcrop.crop_year == c]
            first_any = nc.mt.iloc[0] if len(nc) else first_any
        fin = g.mt.iloc[-1]
        rows.append(dict(source=s, crop_year=c, n_vintages=len(g), first_release=g.release_date.iloc[0].date(),
                         first_mt=round(first_any, 2), oct_or_first_inseason_mt=round(g.mt.iloc[0], 2),
                         end_of_season_mt=round(fin, 2), first_to_end_of_season_pct=round(100 * (fin / first_any - 1), 2),
                         peak_mt=round(g.mt.max(), 2), trough_mt=round(g.mt.min(), 2),
                         sum_abs_rev_mt=round(g.rev.abs().sum(), 2),
                         largest_cut_mt=round(g.rev.min(), 2), largest_cut_date=(
                             g.loc[g.rev.idxmin(), "release_date"].date() if g.rev.notna().any() else None),
                         n_nonzero_rev=int((g.rev.abs() > 1e-9).sum()),
                         latest_any_vintage_mt=round(latest.get((s, c), np.nan), 2),
                         first_to_latest_pct=round(100 * (latest.get((s, c), np.nan) / first_any - 1), 2)))
    t = pd.DataFrame(rows)
    t.to_csv(os.path.join(out, "revision_summary_by_season.csv"), index=False)
    # by season month
    m = paths.dropna(subset=["rev"]).groupby(["source", "smonth"]).agg(
        n=("rev", "size"), mean_rev_mt=("rev", "mean"), mean_abs_rev_mt=("rev", lambda x: x.abs().mean()),
        share_nonzero=("rev", lambda x: (x.abs() > 1e-9).mean())).reset_index()
    m.to_csv(os.path.join(out, "revision_by_season_month.csv"), index=False)
    return t, m


def state_contrib(pit, out):
    """First in-season -> latest change by state for Conab and IBGE."""
    rows = []
    for s in ["conab", "ibge_lspa"]:
        q = pit[(pit.source == s) & (pit.variable == "production") & (pit.is_current_crop == 1)].copy()
        q = q.sort_values("release_ts_utc")
        for (c, r), g in q.groupby(["crop_year", "region"]):
            rows.append(dict(source=s, crop_year=c, region=r, first_kt=g.value.iloc[0], final_kt=g.value.iloc[-1],
                             first_release=g.release_date.iloc[0], change_kt=g.value.iloc[-1] - g.value.iloc[0]))
    t = pd.DataFrame(rows)
    mat = t[t.region.isin(MATOPIBA)].groupby(["source", "crop_year"])[["first_kt", "final_kt", "change_kt"]].sum()
    mat = mat.reset_index().assign(region="MATOPIBA")
    t = pd.concat([t, mat], ignore_index=True)
    t.to_csv(os.path.join(out, "state_first_to_final.csv"), index=False)
    return t


# ---------------------------------------------------------------- events
def event_day(ts_utc, tdays):
    """Map release timestamps to the first CBOT session whose settlement is after release."""
    ts = pd.to_datetime(ts_utc, utc=True)
    ct = ts.dt.tz_convert("America/Chicago")
    # settlement 13:15 CT; release after that -> next session
    d = ct.dt.normalize().dt.tz_localize(None)
    after = (ct.dt.hour * 60 + ct.dt.minute) > (13 * 60 + 15)
    d = d + pd.to_timedelta(after.astype(int), unit="D")
    idx = np.searchsorted(tdays.values, d.values)
    idx = np.clip(idx, 0, len(tdays) - 1)
    return pd.Series(tdays.values[idx], index=ts_utc.index)


def build_events(pit, paths, z):
    tdays = pd.Series(pd.to_datetime(z.index))
    ev = {}
    for s in ["conab", "usda_wasde", "ibge_lspa"]:
        g = paths[paths.source == s].copy()
        g["event_day"] = event_day(g.release_ts_utc, tdays).values
        ev[s] = g
    # US control for WASDE: change in US ending stocks & production, newest market year common to both reports
    w = pit[(pit.source == "usda_wasde") & (pit.region == "US") & pit.variable.isin(["ending_stocks", "production"])]
    w = w.pivot_table(index=["release_date", "crop_year"], columns="variable", values="value").reset_index()
    w["release_date"] = pd.to_datetime(w.release_date)
    rel = sorted(w.release_date.unique())
    us = []
    for a, b in zip(rel[:-1], rel[1:]):
        A, B = w[w.release_date == a].set_index("crop_year"), w[w.release_date == b].set_index("crop_year")
        common = sorted(set(A.index) & set(B.index))
        if not common:
            continue
        y = common[-1]
        us.append(dict(release_date=b, us_es_chg_mt=(B.loc[y, "ending_stocks"] - A.loc[y, "ending_stocks"]) / 1e3,
                       us_prod_chg_mt=(B.loc[y, "production"] - A.loc[y, "production"]) / 1e3))
    us = pd.DataFrame(us)
    ev["usda_wasde"] = ev["usda_wasde"].merge(us, on="release_date", how="left")
    # Conab surprise vs latest USDA (strictly before Conab release)
    # all USDA vintages of a crop (incl. May-Sep new-crop projections), not only headline ones
    u = pit[(pit.source == "usda_wasde") & (pit.region == "BR") & (pit.variable == "production")]
    u = u.assign(mt=u.value / 1e3)[["release_ts_utc", "crop_year", "mt"]].rename(columns={"mt": "usda_mt"})
    u = u.assign(t=pd.to_datetime(u.release_ts_utc, utc=True)).sort_values("t")
    for s in ["conab", "ibge_lspa"]:
        g = ev[s].assign(t=pd.to_datetime(ev[s].release_ts_utc, utc=True)).sort_values("t")
        g = pd.merge_asof(g, u[["t", "crop_year", "usda_mt"]], on="t", by="crop_year", allow_exact_matches=False)
        g["vs_usda"] = g.mt - g.usda_mt
        ev[s] = g
    # Conab-implied surprise for USDA: USDA estimate minus latest Conab
    cpath = paths[paths.source == "conab"][["release_ts_utc", "crop_year", "mt"]].rename(columns={"mt": "conab_mt"})
    cpath = cpath.assign(t=pd.to_datetime(cpath.release_ts_utc, utc=True)).sort_values("t")
    g = ev["usda_wasde"].assign(t=pd.to_datetime(ev["usda_wasde"].release_ts_utc, utc=True)).sort_values("t")
    g = pd.merge_asof(g, cpath[["t", "crop_year", "conab_mt"]], on="t", by="crop_year", allow_exact_matches=False)
    g["vs_conab"] = g.mt - g.conab_mt
    ev["usda_wasde"] = g
    return ev


def ols(y, X, names):
    X = sm.add_constant(np.column_stack(X))
    m = sm.OLS(y, X, missing="drop").fit(cov_type="HC1")
    r = {"n": int(m.nobs), "r2": round(m.rsquared, 3)}
    for i, nm in enumerate(["const"] + names):
        r[f"b_{nm}"] = round(m.params[i], 4)
        r[f"t_{nm}"] = round(m.tvalues[i], 2)
    return r


def market_reaction(ev, z, out):
    z = z.copy()
    z["r"] = 100 * z.ret
    clean = z[z.roll == 0]
    alld = set()
    for s, g in ev.items():
        alld |= set(pd.to_datetime(g.event_day))
    normal = clean[~clean.index.isin(alld)]
    normal = normal[normal.index >= "2005-01-01"]
    rows = []
    for s, g in ev.items():
        days = pd.to_datetime(g.event_day.unique())
        r = clean.reindex(days).r.dropna()
        # same-period comparison: normal days between this source's first and last event
        nr = normal[(normal.index >= r.index.min()) & (normal.index <= r.index.max())].r
        for lab, rr, nn in [(SRC_LABEL[s], r, nr),
                            (SRC_LABEL[s] + " (Dec-Apr)", r[r.index.month.isin([12, 1, 2, 3, 4])],
                             nr[nr.index.month.isin([12, 1, 2, 3, 4])])]:
            rows.append(dict(sample=lab, period=f"{r.index.min().date()}..{r.index.max().date()}", n=len(rr),
                             n_normal=len(nn), mean_abs_ret_pct=round(rr.abs().mean(), 3),
                             mean_abs_normal_pct=round(nn.abs().mean(), 3), sd_pct=round(rr.std(), 3),
                             sd_normal_pct=round(nn.std(), 3), var_ratio=round(rr.var() / nn.var(), 2),
                             levene_p=round(stats.levene(rr, nn, center="median").pvalue, 4)))
    rows.append(dict(sample="Normal days (no release, no roll), 2005-2026", n=len(normal),
                     mean_abs_ret_pct=round(normal.r.abs().mean(), 3), sd_pct=round(normal.r.std(), 3)))
    vol = pd.DataFrame(rows)
    vol.to_csv(os.path.join(out, "release_day_volatility.csv"), index=False)

    # regressions
    reg = []

    def add(label, g, ycol, xcols, sub=None):
        g = g.copy()
        g = g[g.event_day.isin(clean.index)]
        g["y"] = clean.reindex(pd.to_datetime(g.event_day)).r.values
        if sub is not None:
            g = g[sub(g)]
        g = g.dropna(subset=["y"] + xcols)
        if len(g) < 8:
            return
        r = ols(g.y.values, [g[c].values for c in xcols], xcols)
        r.update(model=label)
        reg.append(r)
        return g

    inseason = lambda g: pd.to_datetime(g.event_day).dt.month.isin([12, 1, 2, 3, 4, 5])
    c = ev["conab"]
    add("Conab: ret ~ revision vs prev Conab (Mt)", c, "y", ["rev"])
    add("Conab: ret ~ revision, Dec-May releases", c, "y", ["rev"], inseason)
    add("Conab: ret ~ Conab minus latest USDA (Mt)", c, "y", ["vs_usda"])
    add("Conab: ret ~ revision + vs_usda", c, "y", ["rev", "vs_usda"])
    add("Conab: ret ~ revision, excl. |rev|>10 Mt (Feb-2022 outlier)", c, "y", ["rev"], lambda g: g.rev.abs() <= 10)
    add("Conab: ret ~ revision, excl. days with a WASDE release", c, "y", ["rev"],
        lambda g: ~g.event_day.isin(set(ev["usda_wasde"].event_day)))
    w = ev["usda_wasde"]
    add("WASDE: ret ~ Brazil revision (Mt)", w, "y", ["rev"])
    add("WASDE: ret ~ Brazil revision + US ending-stocks chg + US prod chg (Mt)", w, "y",
        ["rev", "us_es_chg_mt", "us_prod_chg_mt"])
    add("WASDE: ret ~ Brazil revision + US controls, Dec-May", w, "y", ["rev", "us_es_chg_mt", "us_prod_chg_mt"],
        inseason)
    add("WASDE: ret ~ Brazil revision, post-2019/20 (Conab overlap)", w, "y", ["rev"],
        lambda g: g.crop_year >= "2019/20")
    add("WASDE: ret ~ USDA minus latest Conab + US controls", w, "y", ["vs_conab", "us_es_chg_mt", "us_prod_chg_mt"])
    i = ev["ibge_lspa"]
    add("IBGE: ret ~ revision vs prev LSPA (Mt)", i, "y", ["rev"])
    add("IBGE: ret ~ revision, Jan-May releases", i, "y", ["rev"], inseason)
    add("IBGE: ret ~ IBGE minus latest USDA (Mt)", i, "y", ["vs_usda"])
    # pooled Brazil-news days: one regression with all three surprises (0 when no release that day)
    days = sorted(set().union(*[set(pd.to_datetime(g.event_day)) for g in ev.values()]))
    P = pd.DataFrame(index=pd.DatetimeIndex(days))
    for s, col in [("conab", "rev"), ("usda_wasde", "rev"), ("ibge_lspa", "rev")]:
        g = ev[s].dropna(subset=[col]).groupby(pd.to_datetime(ev[s].dropna(subset=[col]).event_day))[col].sum()
        P[s] = g.reindex(P.index).fillna(0.0)
    us = ev["usda_wasde"].groupby(pd.to_datetime(ev["usda_wasde"].event_day))[["us_es_chg_mt", "us_prod_chg_mt"]].sum()
    P = P.join(us).fillna(0.0)
    P["y"] = clean.r.reindex(P.index)
    P = P.dropna(subset=["y"])
    P = P[P.index >= "2019-10-01"]
    r = ols(P.y.values, [P[c].values for c in ["conab", "usda_wasde", "ibge_lspa", "us_es_chg_mt", "us_prod_chg_mt"]],
            ["conab_rev", "wasde_br_rev", "ibge_rev", "us_es_chg", "us_prod_chg"])
    r.update(model="All Brazil-release days since 2019/20: joint")
    reg.append(r)
    reg = pd.DataFrame(reg)
    cols = ["model", "n", "r2"] + [c for c in reg.columns if c.startswith(("b_", "t_"))]
    reg = reg[cols]
    reg.to_csv(os.path.join(out, "release_day_regressions.csv"), index=False)
    # 2-day window robustness for Conab & WASDE
    z2 = clean.r.rolling(2).sum().shift(-1)  # r_t + r_{t+1}
    rob = []
    for s, xs in [("conab", ["rev"]), ("usda_wasde", ["rev", "us_es_chg_mt", "us_prod_chg_mt"]), ("ibge_lspa", ["rev"])]:
        g = ev[s].copy()
        g["y"] = z2.reindex(pd.to_datetime(g.event_day)).values
        g = g.dropna(subset=["y"] + xs)
        rr = ols(g.y.values, [g[c].values for c in xs], xs)
        rr.update(model=f"{SRC_LABEL[s]}: 2-day [t,t+1] return ~ " + " + ".join(xs))
        rob.append(rr)
    # including roll days
    for s, xs in [("conab", ["rev"]), ("usda_wasde", ["rev"])]:
        g = ev[s].copy()
        g["y"] = z.r.reindex(pd.to_datetime(g.event_day)).values
        g = g.dropna(subset=["y"] + xs)
        rr = ols(g.y.values, [g[c].values for c in xs], xs)
        rr.update(model=f"{SRC_LABEL[s]}: incl. roll days")
        rob.append(rr)
    pd.DataFrame(rob).to_csv(os.path.join(out, "release_day_regressions_robustness.csv"), index=False)
    return vol, reg, clean


# ---------------------------------------------------------------- predictability
def autocorr(paths, pit, out):
    rows = []
    for s, g in paths.groupby("source"):
        g = g.sort_values(["crop_year", "release_ts_utc"]).copy()
        g["rev_lag"] = g.groupby("crop_year").rev.shift(1)
        h = g.dropna(subset=["rev", "rev_lag"])
        h = h[h.crop_year >= "2005/06"]
        r = ols(h.rev.values, [h.rev_lag.values], ["rev_lag"])
        nz = h[(h.rev_lag.abs() > 1e-9) & (h.rev.abs() > 1e-9)]
        same = (np.sign(nz.rev) == np.sign(nz.rev_lag)).mean()
        cut = h[h.rev_lag < -1e-9]
        r.update(test=f"{SRC_LABEL[s]}: rev_k ~ rev_k-1 (BR production, Mt)",
                 corr=round(h[["rev", "rev_lag"]].corr().iloc[0, 1], 3),
                 spearman=round(stats.spearmanr(h.rev, h.rev_lag)[0], 3),
                 p_same_sign_given_both_nonzero=round(same, 3), n_both_nonzero=len(nz),
                 p_cut_after_cut=round((cut.rev < -1e-9).mean(), 3),
                 p_cut_unconditional=round((h.rev < -1e-9).mean(), 3))
        rows.append(r)
        # Nordhaus efficiency: (final - est_k) on rev_k
        g["final"] = g.groupby("crop_year").mt.transform("last")
        g["fe"] = g.final - g.mt
        e = g.dropna(subset=["rev"])
        e = e[e.groupby("crop_year").release_ts_utc.transform("max") != e.release_ts_utc]
        rr = ols(e.fe.values, [e.rev.values], ["rev"])
        rr.update(test=f"{SRC_LABEL[s]}: (final - est_k) ~ rev_k  [efficiency]")
        rows.append(rr)
    # state-level (IBGE long history, Conab short)
    for s in ["ibge_lspa", "conab"]:
        q = pit[(pit.source == s) & (pit.variable == "production") & (pit.is_current_crop == 1)
                & pit.region.isin(STATES)].sort_values("release_ts_utc").copy()
        q["mt"] = q.value / 1e3
        q["rev"] = q.groupby(["region", "crop_year"]).mt.diff()
        q["rev_lag"] = q.groupby(["region", "crop_year"]).rev.shift(1)
        h = q.dropna(subset=["rev", "rev_lag"])
        r = ols(h.rev.values, [h.rev_lag.values], ["rev_lag"])
        nz = h[(h.rev_lag.abs() > 1e-9) & (h.rev.abs() > 1e-9)]
        r.update(test=f"{SRC_LABEL[s]}: state rev_k ~ rev_k-1 (pooled {', '.join(STATES)})",
                 corr=round(h[["rev", "rev_lag"]].corr().iloc[0, 1], 3),
                 p_same_sign_given_both_nonzero=round((np.sign(nz.rev) == np.sign(nz.rev_lag)).mean(), 3),
                 n_both_nonzero=len(nz))
        rows.append(r)
    # cross-source lead-lag: revisions of A released since B's previous release predict B's next revision
    rel = {s: g.sort_values("release_ts_utc") for s, g in paths.groupby("source")}
    for a, b in [("conab", "usda_wasde"), ("usda_wasde", "conab"), ("ibge_lspa", "usda_wasde"),
                 ("usda_wasde", "ibge_lspa"), ("ibge_lspa", "conab"), ("conab", "ibge_lspa")]:
        A, B = rel[a].copy(), rel[b].copy()
        A["t"] = pd.to_datetime(A.release_ts_utc, utc=True)
        B["t"] = pd.to_datetime(B.release_ts_utc, utc=True)
        recs = []
        for c, gb in B.groupby("crop_year"):
            gb = gb.sort_values("t")
            ga = A[A.crop_year == c]
            for i in range(1, len(gb)):
                t0, t1 = gb.t.iloc[i - 1], gb.t.iloc[i]
                x = ga[(ga.t > t0) & (ga.t < t1)].rev.sum(min_count=1)
                # gap: A's latest level minus B's previous level (information not yet in B)
                la = ga[ga.t < t1]
                gap = (la.mt.iloc[-1] - gb.mt.iloc[i - 1]) if len(la) else np.nan
                recs.append(dict(crop_year=c, y=gb.rev.iloc[i], x=x, gap=gap))
        h = pd.DataFrame(recs).dropna()
        if len(h) < 10:
            continue
        r = ols(h.y.values, [h.x.values], ["A_rev_since_prev_B"])
        r.update(test=f"{SRC_LABEL[b]} next rev ~ {SRC_LABEL[a]} revisions since previous {SRC_LABEL[b]}",
                 corr=round(h[["y", "x"]].corr().iloc[0, 1], 3))
        rows.append(r)
        r = ols(h.y.values, [h.gap.values], ["gap"])
        r.update(test=f"{SRC_LABEL[b]} next rev ~ ({SRC_LABEL[a]} latest - {SRC_LABEL[b]} previous) level gap",
                 corr=round(h[["y", "gap"]].corr().iloc[0, 1], 3))
        rows.append(r)
    t = pd.DataFrame(rows)
    first = ["test", "n", "r2"]
    t = t[first + [c for c in t.columns if c not in first]]
    t.to_csv(os.path.join(out, "revision_predictability.csv"), index=False)
    return t


# ---------------------------------------------------------------- figures
def fig_paths(paths, newcrop, figs):
    crops = sorted(set(paths.crop_year) | set(newcrop.crop_year))
    crops = [c for c in crops if "2005/06" <= c <= "2025/26"]
    fig, axes = ps.grid(len(crops), ncols=6, w=2.5, h=1.9)
    for ax, c in zip(axes, crops):
        for s in ["usda_wasde", "ibge_lspa", "conab"]:
            g = newcrop[newcrop.crop_year == c] if s == "usda_wasde" else paths[(paths.source == s) & (paths.crop_year == c)]
            if len(g):
                ax.step(g.release_date, g.mt, where="post", color=SRC_COLOR[s], lw=1.6, label=SRC_LABEL[s])
        ax.set_title(c, loc="left")
        ax.tick_params(axis="x", labelsize=6.5)
        ax.xaxis.set_major_formatter(ps.mdates.DateFormatter("%b\n%y"))
        ax.xaxis.set_major_locator(ps.mdates.MonthLocator(bymonth=[1, 7]))
    for ax in axes[len(crops):]:
        ax.set_visible(False)
    ps.legend_top(fig, [SRC_LABEL[s] for s in ["conab", "usda_wasde", "ibge_lspa"]],
                  [SRC_COLOR[s] for s in ["conab", "usda_wasde", "ibge_lspa"]])
    fig.suptitle("Brazil soybean production estimates by release date (Mt), each panel = one crop year",
                 x=0.01, ha="left", y=1.0, fontsize=10, color=ps.TEXT)
    ps.save(fig, os.path.join(figs, "fig1_forecast_paths_small_multiples.png"))


def fig_rev_month(m, figs):
    names = {1: "Oct", 2: "Nov", 3: "Dec", 4: "Jan", 5: "Feb", 6: "Mar", 7: "Apr", 8: "May", 9: "Jun", 10: "Jul",
             11: "Aug", 12: "Sep"}
    fig, ax = ps.single(7.5, 3.2)
    srcs = ["conab", "usda_wasde", "ibge_lspa"]
    w = 0.26
    for j, s in enumerate(srcs):
        g = m[m.source == s].set_index("smonth").reindex(range(1, 13))
        ax.bar(np.arange(1, 13) + (j - 1) * w, g.mean_abs_rev_mt, width=w - 0.03, color=SRC_COLOR[s],
               label=SRC_LABEL[s])
    ax.set_xticks(range(1, 13), [names[i] for i in range(1, 13)])
    ax.set_ylabel("Mean |revision| of Brazil production (Mt)")
    ax.set_title("When do Brazil soybean estimates move? Mean absolute monthly revision by release month",
                 loc="left")
    ax.legend(frameon=False, ncol=3, loc="upper right")
    ps.save(fig, os.path.join(figs, "fig2_revision_by_month.png"))


def fig_reaction(ev, clean, figs):
    fig, axes = ps.grid(3, ncols=3, w=3.3, h=3.0, sharey=True)
    for ax, s in zip(axes, ["conab", "usda_wasde", "ibge_lspa"]):
        g = ev[s].dropna(subset=["rev"]).copy()
        g["y"] = clean.r.reindex(pd.to_datetime(g.event_day)).values
        g = g.dropna(subset=["y"])
        ax.scatter(g.rev, g.y, s=14, color=SRC_COLOR[s], alpha=0.75, edgecolor=ps.BG, linewidth=0.6)
        if len(g) > 5:
            b = np.polyfit(g.rev, g.y, 1)
            xx = np.linspace(g.rev.min(), g.rev.max(), 10)
            ax.plot(xx, np.polyval(b, xx), color=ps.TEXT, lw=1, ls="--")
            ax.text(0.02, 0.04, f"slope {b[0]:+.3f} %/Mt, n={len(g)}", transform=ax.transAxes, fontsize=7.5,
                    color=ps.TEXT)
        ax.axhline(0, color=ps.GRID, lw=0.8)
        ax.axvline(0, color=ps.GRID, lw=0.8)
        ax.set_title(SRC_LABEL[s], loc="left")
        ax.set_xlabel("Revision vs previous estimate (Mt)")
    axes[0].set_ylabel("CBOT soybean return on release day (%)")
    fig.suptitle("Release-day CBOT return vs Brazil production revision (roll days excluded)", x=0.01, ha="left",
                 fontsize=10, color=ps.TEXT)
    ps.save(fig, os.path.join(figs, "fig3_release_day_reaction.png"))


def fig_autocorr(paths, figs):
    fig, axes = ps.grid(3, ncols=3, w=3.3, h=3.0)
    for ax, s in zip(axes, ["conab", "usda_wasde", "ibge_lspa"]):
        g = paths[paths.source == s].sort_values(["crop_year", "release_ts_utc"]).copy()
        g["lag"] = g.groupby("crop_year").rev.shift(1)
        g = g.dropna(subset=["rev", "lag"])
        ax.scatter(g.lag, g.rev, s=14, color=SRC_COLOR[s], alpha=0.75, edgecolor=ps.BG, linewidth=0.6)
        ax.axhline(0, color=ps.GRID, lw=0.8)
        ax.axvline(0, color=ps.GRID, lw=0.8)
        rho = g[["rev", "lag"]].corr().iloc[0, 1]
        ax.text(0.02, 0.92, f"corr {rho:+.2f}, n={len(g)}", transform=ax.transAxes, fontsize=7.5, color=ps.TEXT)
        ax.set_title(SRC_LABEL[s], loc="left")
        ax.set_xlabel("Previous revision (Mt)")
    axes[0].set_ylabel("Next revision (Mt)")
    fig.suptitle("Do revisions persist? Brazil production revision k vs k-1, same source and crop", x=0.01,
                 ha="left", fontsize=10, color=ps.TEXT)
    ps.save(fig, os.path.join(figs, "fig4_revision_autocorrelation.png"))


def fig_states(st, figs):
    cases = [("ibge_lspa", "2008/09"), ("ibge_lspa", "2011/12"), ("ibge_lspa", "2015/16"), ("ibge_lspa", "2017/18"),
             ("conab", "2019/20"), ("conab", "2021/22"), ("conab", "2022/23"), ("conab", "2023/24"),
             ("conab", "2024/25")]
    regs = ["MT", "PR", "RS", "GO", "MS", "MATOPIBA", "MG", "SC", "SP"]
    fig, axes = ps.grid(len(cases), ncols=3, w=3.3, h=2.4, sharey=False)
    for ax, (s, c) in zip(axes, cases):
        g = st[(st.source == s) & (st.crop_year == c)].set_index("region").reindex(regs)
        vals = g.change_kt / 1e3
        ax.bar(range(len(regs)), vals, color=SRC_COLOR[s], width=0.7)
        ax.axhline(0, color=ps.TEXT, lw=0.6)
        ax.set_xticks(range(len(regs)), [r if r != "MATOPIBA" else "MATO-\nPIBA" for r in regs], fontsize=6.5)
        br = st[(st.source == s) & (st.crop_year == c) & (st.region == "BR")].change_kt
        ax.set_title(f"{c} {SRC_LABEL[s]}  (BR {br.iloc[0] / 1e3:+.1f} Mt)" if len(br) else c, loc="left",
                     fontsize=8)
    axes[0].set_ylabel("First in-season to final (Mt)")
    fig.suptitle("Where the revisions came from: change by state, first estimate to latest", x=0.01, ha="left",
                 fontsize=10, color=ps.TEXT)
    ps.save(fig, os.path.join(figs, "fig5_state_revisions_big_seasons.png"))


def fig_prices(z, figs):
    fig, ax = ps.single(7.5, 2.8)
    zz = z[z.index >= "2005-01-01"]
    ax.plot(zz.index, zz.close / 100, color=ps.C[0], lw=1.0)
    ax.set_ylabel("USD/bu")
    ax.set_title("CBOT soybean front month (Yahoo ZS=F, continuous, unadjusted)", loc="left")
    ps.save(fig, os.path.join(figs, "fig0_cbot_soy_price.png"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--prices", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--figs", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    os.makedirs(a.figs, exist_ok=True)
    pit = pd.read_csv(os.path.join(a.data, "pit_soy_brazil.csv"))
    z = pd.read_csv(os.path.join(a.prices, "cbot_soy_zs_daily.csv"), parse_dates=["date"]).set_index("date")
    paths = br_paths(pit)
    paths = paths[paths.crop_year >= "2005/06"]
    newcrop = usda_newcrop(pit)
    t, m = revision_tables(paths, newcrop, a.out, pit)
    st = state_contrib(pit, a.out)
    ev = build_events(pit, paths, z)
    pd.concat([g.assign(source=s) for s, g in ev.items()], ignore_index=True).drop(columns=["t"], errors="ignore") \
        .to_csv(os.path.join(a.out, "events.csv"), index=False)
    vol, reg, clean = market_reaction(ev, z, a.out)
    ac = autocorr(paths, pit, a.out)
    fig_paths(paths, newcrop, a.figs)
    fig_rev_month(m, a.figs)
    fig_reaction(ev, clean, a.figs)
    fig_autocorr(paths, a.figs)
    fig_states(st, a.figs)
    fig_prices(z, a.figs)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print(vol.to_string(index=False))
    print(reg.to_string(index=False))
    print(ac.to_string(index=False))


if __name__ == "__main__":
    main()
