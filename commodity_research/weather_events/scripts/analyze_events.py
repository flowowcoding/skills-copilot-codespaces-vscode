"""Event construction, event-study CARs, pre-registered trading rules, baselines and overreaction.

Implements PREREGISTRATION.md exactly (see README "Deviations" for anything that differs).

Inputs  (data/): forecast_overlap.csv, advisories.csv.gz, besttrack_verification.csv,
                 storm_names.csv, prices/<TICKER>.csv
Outputs (results/):
  events.csv              one row per (market, storm) trigger: dates, hit/miss, returns by window
  car_paths.csv           mean / median abnormal CAR by event day, per market x sample x hit/miss
  rule_grid.csv           6-cell grid, design and holdout, gross/net/2x-cost
  rule_results.csv        selected + prior cell, design vs holdout, t-test, seasonal excess
  seasonal_baseline.csv   season-long (15 Aug-31 Oct) long-only rule per market and sample
  overreaction.csv        misses: 0->A and A->A+10 returns, correlation, fade rule
  roll_check.csv          sanity check of roll-day detection

Usage: python analyze_events.py --data ../data --out ../results
"""
import argparse
import os

import numpy as np
import pandas as pd
from scipy import stats

MARKETS = {  # ticker: (region, round-trip cost %, primary?)
    "OJ": ("citrus", 0.50, True), "NG": ("gulf_energy", 0.10, True), "CL": ("gulf_energy", 0.05, True),
    "RB": ("gulf_energy", 0.08, True), "CT": ("cotton", 0.10, True), "ZR": ("rice", 0.30, False)}
AG = {"OJ", "CT", "ZR", "SB"}
CUTOFF_H = 17           # advisory must be available by 17:00 UTC to trade at that day's close
DESIGN_END = 2017
MAXHOLD = 15


# ----------------------------------------------------------------------------- prices / rolls
def roll_days(tk, px):
    d = px.index
    if tk in AG:
        v = px.volume.fillna(0)
        med = v.rolling(40, min_periods=10).median().shift(1)
        low = v < 0.10 * med
        out = []
        run = 0
        for i in range(len(d)):
            if low.iloc[i]:
                run += 1
            else:
                if run >= 2 and v.iloc[i] >= 0.25 * med.iloc[i]:
                    out.append(d[i])
                run = 0
        return pd.DatetimeIndex(out)
    s = pd.Series(d, index=d)
    months = pd.period_range(d[0], d[-1], freq="M")
    out = []
    for m in months:
        days = s[(s.dt.year == m.year) & (s.dt.month == m.month)]
        if len(days) < 5:
            continue
        if tk == "NG":        # last trade = 3rd-last business day of month; roll = next day
            nxt = s[s > days.iloc[-3]]
        elif tk == "CL":      # last trade = 3 business days before the 25th (or prior business day)
            ref = days[days.dt.day <= 25].iloc[-1]     # the 25th, or the business day before it
            last = days.iloc[list(days).index(ref) - 3]
            nxt = s[s > last]
        elif tk == "RB":      # last trade = last business day of month; roll = first day of next month
            nxt = s[s > days.iloc[-1]]
        else:
            continue
        if len(nxt):
            out.append(nxt.iloc[0])
    return pd.DatetimeIndex(out)


def load_prices(data):
    P, R, ROLL = {}, {}, {}
    for tk in MARKETS:
        px = pd.read_csv(os.path.join(data, "prices", f"{tk}.csv"), parse_dates=["date"]).set_index("date")
        px = px[px.close > 0]
        r = np.log(px.close).diff()
        rd = roll_days(tk, px)
        ROLL[tk] = rd
        r.loc[r.index.isin(rd)] = np.nan
        P[tk], R[tk] = px, r
    return P, R, ROLL


def day_on_or_after(dates, ts):
    """First trading date d with ts <= d + CUTOFF_H hours."""
    i = dates.searchsorted(ts - pd.Timedelta(hours=CUTOFF_H))
    return i if i < len(dates) else None


def span_ret(r, i0, i1):
    """Simple return from close i0 to close i1 (roll days dropped)."""
    if i1 <= i0:
        return 0.0
    return float(np.expm1(np.nansum(r.values[i0 + 1:i1 + 1])))


# ----------------------------------------------------------------------------- events
def build_events(data, P, R):
    ov = pd.read_csv(os.path.join(data, "forecast_overlap.csv"), parse_dates=["init", "avail_utc"])
    adv = pd.read_csv(os.path.join(data, "advisories.csv.gz"), parse_dates=["init_t", "avail_utc"])
    ver = pd.read_csv(os.path.join(data, "besttrack_verification.csv"),
                      parse_dates=["bt_t_closest", "landfall_utc", "bt_first_within100_ts"])
    advs = {k: g.sort_values("init_t") for k, g in adv.groupby("storm_id")}
    rows = []
    for tk, (region, cost, primary) in MARKETS.items():
        dates = R[tk].index
        o = ov[ov.region == region]
        for sid, g in o.groupby("storm_id"):
            g = g.sort_values("init")
            trig = g[g.cone72 & (g.vmax72 >= 64)]
            if trig.empty:
                continue
            t = trig.iloc[0]
            i0 = day_on_or_after(dates, t.avail_utc)
            if i0 is None:
                continue
            # walk the storm's later advisories (rows absent from overlap = >2000 km away = all-clear)
            later = advs[sid][advs[sid].init_t > t.init]
            gi = g.set_index("init")
            arrival = allclear = None
            hit = False
            for _, a in later.iterrows():
                row = gi.loc[a.init_t] if a.init_t in gi.index else None
                if row is not None and row.dist0_km <= 100:
                    if arrival is None:
                        arrival = a.avail_utc
                    hit |= row.vmax0 >= 64
                if row is None or not row.cone120:
                    allclear = a.avail_utc
                    break
            if allclear is None:   # advisories ended
                allclear = later.avail_utc.iloc[-1] + pd.Timedelta(hours=6) if len(later) else t.avail_utc
            if t.dist0_km <= 100:
                arrival = arrival or t.avail_utc
                hit |= t.vmax0 >= 64
            e1_t = min(x for x in [arrival, allclear] if x is not None)
            iE1 = day_on_or_after(dates, e1_t)
            iE1 = min(iE1 if iE1 is not None else len(dates) - 1, i0 + MAXHOLD, len(dates) - 1)
            iE1 = max(iE1, i0 + 1)
            iA = day_on_or_after(dates, allclear)
            iA = min(iA if iA is not None else len(dates) - 1, len(dates) - 1)
            v = ver[(ver.storm_id == sid) & (ver.region == region)]
            v = v.iloc[0] if len(v) else None
            iL = i0
            if v is not None:
                iL = day_on_or_after(dates, v.bt_t_closest)
                iL = max(i0, iL if iL is not None else i0)
            rows.append(dict(
                market=tk, region=region, storm_id=sid, name=t["name"], year=t.init.year,
                sample="design" if t.init.year <= DESIGN_END else "holdout",
                trigger_adv_utc=t.init, trigger_avail_utc=t.avail_utc, trig_vmax72=t.vmax72,
                trig_dist0_km=t.dist0_km, trig_cone72_frac=t.cone72_frac, trig_gefs_p72=t.gefs_p72,
                first_cone120_utc=g[g.cone120].init.min(), max_cone72_frac=g.cone72_frac.max(),
                max_gefs_p72=g.gefs_p72.max(),
                day0=dates[i0].date(), exitE1=dates[iE1].date(), allclear_day=dates[iA].date(),
                closest_day=dates[min(iL, len(dates) - 1)].date(),
                arrival_utc=arrival, allclear_utc=allclear, hit_pit=bool(hit),
                bt_hit_hu=bool(v.bt_hit_hu) if v is not None else False,
                bt_hit_ts=bool(v.bt_hit_ts) if v is not None else False,
                bt_dmin_km=v.bt_dmin_km if v is not None else np.nan,
                bt_t_closest=v.bt_t_closest if v is not None else pd.NaT,
                bt_vmax_within100=v.bt_vmax_within100 if v is not None else 0,
                landfall_utc=v.landfall_utc if v is not None else pd.NaT,
                landfall_vmax=v.landfall_vmax if v is not None else np.nan,
                complete=bool(max(iL, iA, i0) + 20 < len(dates)),
                i0=i0, iE1=iE1, iA=iA, iL=min(iL, len(dates) - 1)))
    ev = pd.DataFrame(rows).sort_values(["market", "trigger_avail_utc"]).reset_index(drop=True)
    return ev


# ----------------------------------------------------------------------------- abnormal returns
def abnormal(R):
    A = {}
    for tk, r in R.items():
        mu = r.groupby(r.index.month).transform("mean")
        A[tk] = r - mu
    return A


def car(a, i, j):
    """Sum of abnormal log returns on days i..j inclusive (event days are absolute indices)."""
    i, j = max(i, 1), min(j, len(a) - 1)
    return float(np.nansum(a.values[i:j + 1])) if j >= i else 0.0


def add_windows(ev, R, A):
    out = []
    for _, e in ev.iterrows():
        a, r = A[e.market], R[e.market]
        i0, iL, iA = e.i0, e.iL, e.iA
        out.append(dict(
            car_pre=car(a, i0 - 10, i0 - 1), car_day0=car(a, i0, i0),
            car_0_L=car(a, i0 + 1, iL), car_post20=car(a, iL + 1, iL + 20),
            car_0_20=car(a, i0 + 1, i0 + 20), car_m10_L=car(a, i0 - 10, iL),
            ret_E1=span_ret(r, i0, e.iE1), ret_5=span_ret(r, i0, i0 + 5), ret_10=span_ret(r, i0, i0 + 10),
            ret_0_A=span_ret(r, i0, iA), ret_A_10=span_ret(r, iA, iA + 10)))
    return pd.concat([ev, pd.DataFrame(out)], axis=1)


def car_paths(ev, A):
    rows = []
    for (tk, smp, hit), g in ev.groupby(["market", "sample", "hit_pit"]):
        for anchor in ["day0", "closest"]:
            M = []
            for _, e in g.iterrows():
                c = e.i0 if anchor == "day0" else e.iL
                a = A[tk].values
                seg = [a[k] if 0 < k < len(a) else np.nan for k in range(c - 10, c + 21)]
                M.append(np.nancumsum(np.nan_to_num(seg)))
            M = np.array(M)
            M = M - M[:, [9]]       # rebase to 0 at event day -1 close
            for k in range(-10, 21):
                rows.append(dict(market=tk, sample=smp, hit=hit, anchor=anchor, k=k, n=len(M),
                                 mean=M[:, k + 10].mean(), median=np.median(M[:, k + 10])))
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------- trading rules
def tradeable(ev):
    """Drop triggers that arrive while an earlier position in the same market is still open."""
    keep = []
    for tk, g in ev.groupby("market"):
        busy = -1
        for idx, e in g.iterrows():
            if e.i0 > busy:
                keep.append(idx)
                busy = max(e.iE1, e.i0 + 10)
    return ev.loc[sorted(keep)]


def seasonal_baseline_ret(tk, R, ev_all, day0, nhold):
    """Same calendar entry & holding in every other year without a trigger within +-10 days."""
    r = R[tk]
    dates = r.index
    trig = pd.to_datetime(ev_all[ev_all.market == tk].day0)
    vals = []
    for y in range(2005, 2026):
        if y == day0.year:
            continue
        try:
            d = pd.Timestamp(year=y, month=day0.month, day=day0.day)
        except ValueError:
            continue
        i = dates.searchsorted(d)
        if i + nhold >= len(dates):
            continue
        if (abs((trig - dates[i]).dt.days) <= 14).any():
            continue
        vals.append(span_ret(r, i, i + nhold))
    return np.mean(vals) if vals else np.nan


def ttest_1s(x):
    x = np.asarray(x, float)
    x = x[~np.isnan(x)]
    if len(x) < 2 or x.std(ddof=1) == 0:
        return np.nan, np.nan
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    return t, 1 - stats.t.cdf(t, len(x) - 1)


def rules(ev, R, ev_all):
    grid, res = [], []
    exits = {"E1": "ret_E1", "D5": "ret_5", "D10": "ret_10"}
    for tk, (region, cost, primary) in MARKETS.items():
        g = tradeable(ev[ev.market == tk])
        cells = {}
        for smp in ["design", "holdout"]:
            s = g[g["sample"] == smp]
            for dr, sign in [("long", 1), ("short", -1)]:
                for ex, col in exits.items():
                    gross = sign * s[col] * 100
                    net = gross - cost
                    t, p = ttest_1s(net)
                    cells[(smp, dr, ex)] = net
                    grid.append(dict(market=tk, sample=smp, direction=dr, exit=ex, n=len(s),
                                     gross_mean=gross.mean(), net_mean=net.mean(),
                                     net_2x_mean=(gross - 2 * cost).mean(), net_median=net.median(),
                                     hit_rate=(net > 0).mean() if len(s) else np.nan, t=t, p_1s=p))
        if not primary:
            continue
        dg = pd.DataFrame([x for x in grid if x["market"] == tk and x["sample"] == "design"])
        best = dg.loc[dg.net_mean.idxmax()]
        for label, dr, ex in [("selected", best.direction, best.exit), ("prior", "long", "E1")]:
            sign = 1 if dr == "long" else -1
            for smp in ["design", "holdout"]:
                s = g[g["sample"] == smp]
                gross = sign * s[exits[ex]] * 100
                net = gross - cost
                hold = {"E1": (s.iE1 - s.i0).values, "D5": np.full(len(s), 5), "D10": np.full(len(s), 10)}[ex]
                base = np.array([sign * seasonal_baseline_ret(tk, R, ev_all, pd.Timestamp(d), int(h)) * 100
                                 for d, h in zip(s.day0, hold)])
                exc = gross.values - base
                t, p = ttest_1s(net)
                te, pe = ttest_1s(exc)
                ok = (len(s) > 0 and net.mean() > 0 and p < 0.10 and np.nanmean(exc) > 0)
                res.append(dict(market=tk, cell=label, direction=dr, exit=ex, sample=smp, n=len(s),
                                gross_mean=gross.mean(), net_mean=net.mean(), net_2x=(gross - 2 * cost).mean(),
                                net_median=net.median(), hit_rate=(net > 0).mean() if len(s) else np.nan,
                                t=t, p_1s=p, seasonal_base_mean=np.nanmean(base), excess_mean=np.nanmean(exc),
                                excess_t=te, success=bool(ok) if smp == "holdout" else np.nan,
                                events=";".join(f"{n}{str(y)[2:]}" for n, y in zip(s.name, s.year))))
    return pd.DataFrame(grid), pd.DataFrame(res)


def season_long(R):
    rows = []
    for tk, (region, cost, _) in MARKETS.items():
        r = R[tk]
        for y in range(2005, 2027):
            i0 = r.index.searchsorted(pd.Timestamp(y, 8, 15))
            i1 = r.index.searchsorted(pd.Timestamp(y, 10, 31), side="right") - 1
            if i1 <= i0 or r.index[-1] < pd.Timestamp(y, 10, 31):
                continue
            rows.append(dict(market=tk, year=y, sample="design" if y <= DESIGN_END else "holdout",
                             net=span_ret(r, i0, i1) * 100 - cost))
    d = pd.DataFrame(rows)
    s = d.groupby(["market", "sample"]).net.agg(["count", "mean", "median"]).reset_index()
    s["t"] = d.groupby(["market", "sample"]).net.apply(lambda x: ttest_1s(x)[0]).values
    return s


def overreaction(ev):
    rows = []
    for tk, (region, cost, primary) in MARKETS.items():
        for smp in ["design", "holdout", "all"]:
            m = ev[(ev.market == tk) & (~ev.hit_pit)]
            if smp != "all":
                m = m[m["sample"] == smp]
            if len(m) == 0:
                continue
            fade = m[m.ret_0_A > 0]
            fnet = -fade.ret_A_10 * 100 - cost
            rho = stats.spearmanr(m.ret_0_A, m.ret_A_10)[0] if len(m) > 3 else np.nan
            t_rev, _ = ttest_1s(m.ret_A_10)
            rows.append(dict(market=tk, sample=smp, n_miss=len(m), mean_0_A=m.ret_0_A.mean() * 100,
                             mean_A_10=m.ret_A_10.mean() * 100, t_A_10=t_rev, spearman_0A_A10=rho,
                             n_fade=len(fade), fade_net_mean=fnet.mean(), fade_t=ttest_1s(fnet)[0],
                             fade_hit=(fnet > 0).mean() if len(fade) else np.nan))
    return pd.DataFrame(rows)


def car_summary(ev):
    """Mean abnormal CAR (%) by window, with t-stats, per market x sample x hit/miss."""
    rows = []
    wins = ["car_pre", "car_day0", "car_0_L", "car_post20", "car_0_20"]
    ev = ev.assign(lead_trig_days=(pd.to_datetime(ev.bt_t_closest) - pd.to_datetime(ev.trigger_avail_utc)).dt.total_seconds() / 86400,
                   lead_c120_days=(pd.to_datetime(ev.bt_t_closest) - pd.to_datetime(ev.first_cone120_utc)).dt.total_seconds() / 86400)
    for smp in ["design", "holdout", "all"]:
        for (tk, hit), g in ev.groupby(["market", "hit_pit"]):
            if smp != "all":
                g = g[g["sample"] == smp]
            if g.empty:
                continue
            r = dict(market=tk, sample=smp, hit=hit, n=len(g),
                     lead_trigger_to_closest_d=g.lead_trig_days.median(),
                     lead_5day_cone_to_closest_d=g.lead_c120_days.median())
            for w in wins:
                r[w] = g[w].mean() * 100
                r[w + "_t"] = ttest_1s(g[w])[0]
                r[w + "_abs"] = g[w].abs().mean() * 100
            rows.append(r)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    P, R, ROLL = load_prices(a.data)
    chk = []
    for tk in MARKETS:
        r = np.log(P[tk].close).diff()
        isr = r.index.isin(ROLL[tk])
        chk.append(dict(market=tk, n_roll=int(isr.sum()), mean_abs_roll=r[isr].abs().mean() * 100,
                        mean_abs_other=r[~isr].abs().mean() * 100))
    pd.DataFrame(chk).to_csv(os.path.join(a.out, "roll_check.csv"), index=False)
    A = abnormal(R)
    ev = build_events(a.data, P, R)
    ev = add_windows(ev, R, A)
    cols = [c for c in ev.columns if c not in ("i0", "iE1", "iA", "iL")]
    ev[cols].round(5).to_csv(os.path.join(a.out, "events.csv"), index=False)
    car_summary(ev[ev.complete]).round(3).to_csv(os.path.join(a.out, "car_summary.csv"), index=False)
    car_paths(ev[ev.complete], A).round(5).to_csv(os.path.join(a.out, "car_paths.csv"), index=False)
    evc = ev[ev.complete]          # events whose +20-day window has not happened yet are excluded
    grid, res = rules(evc, R, ev)
    grid.round(4).to_csv(os.path.join(a.out, "rule_grid.csv"), index=False)
    res.round(4).to_csv(os.path.join(a.out, "rule_results.csv"), index=False)
    season_long(R).round(3).to_csv(os.path.join(a.out, "seasonal_baseline.csv"), index=False)
    overreaction(ev[ev.complete]).round(4).to_csv(os.path.join(a.out, "overreaction.csv"), index=False)
    print(pd.DataFrame(chk))
    print(ev.groupby(["market", "sample", "hit_pit"]).size())


if __name__ == "__main__":
    main()
