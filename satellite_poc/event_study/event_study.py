"""Event study: how much is it worth to know about a mine disruption early?

Usage: event_study.py EVENTS.csv PRICE_DIR OUT_DIR [FIG_DIR]

For every event in EVENTS.csv with price data (see fetch_prices.py) this computes daily
abnormal returns around the first public disclosure and writes:

  OUT_DIR/event_results.csv   one row per event: windows, lead values, drift trades
  OUT_DIR/summary.csv         pooled and split statistics (n, mean, median, t, BMP t, ...)
  OUT_DIR/lead_value.csv      value of knowing 1/5/20 trading days before disclosure, net of costs
  OUT_DIR/drift_strategy.csv  post-disclosure drift trade (no satellite needed), net of costs
  OUT_DIR/robustness.csv      key numbers under alternative choices
  OUT_DIR/car_path.csv        mean CAR path by group (the figure's data)
  FIG_DIR/car_disclosure.png  mean CAR around disclosure, two groups

Definitions
-----------
Day 0 is the first session that can price the disclosure: the disclosure date for
pre-market, intraday or unknown timing, the next session for after-close releases.
If trading is halted (zero volume, which is how Yahoo shows ASX halts and suspensions),
day 0 runs until the first session that trades again, so the reaction includes the halt.
Post-event days are counted from the end of that reaction day.

Abnormal return (AR) uses a market model, r_i - (a + b r_m), fitted on trading days
[-280, -31]; the benchmark is a sector ETF or index (column `benchmark`), forward-filled
onto the stock's own calendar. With fewer than 100 estimation days, a = 0 and b = 1.
CAR is the sum of ARs. Trades use buy-and-hold returns hedged with b times the benchmark.

Costs: a round trip costs the full bid-ask spread (Corwin-Schultz estimate from daily
highs and lows over days [-120, -11], floored by size tier: 0.05% large, 0.15% mid,
0.50% small) plus 0.05% commission per side. Shorts also pay borrow: 0.5% a year for
large caps, 2% for mid caps, 10% for small caps. These are optimistic for small caps,
which retail brokers often cannot lend at all.
"""
import sys, os
import numpy as np
import pandas as pd
from scipy import stats

TIER_SPREAD_FLOOR = {"large": 0.0005, "mid": 0.0015, "small": 0.005}
TIER_BORROW = {"large": 0.005, "mid": 0.02, "small": 0.10}
COMMISSION = 0.0005  # per side
USABLE = {"ok", "primary_missing_otc_used"}
PRE, POST = 60, 61   # event-time range kept in memory


def load_px(price_dir, sym):
    f = os.path.join(price_dir, sym.replace("^", "_").replace("/", "_") + ".csv")
    if not os.path.exists(f):
        return None
    d = pd.read_csv(f, parse_dates=["date"]).set_index("date").sort_index()
    return d[~d.index.duplicated(keep="last")]


def exchange_of(t):
    for suf, ex in [(".AX", "ASX"), (".TO", "TSX"), (".V", "TSX"), (".L", "LSE"),
                    (".HK", "HKEX"), (".JO", "JSE"), (".ME", "MOEX")]:
        if t.endswith(suf):
            return ex
    return "US"


def corwin_schultz(h, l):
    """Mean Corwin-Schultz (2012) spread estimate from daily high/low series."""
    h, l = h.values.astype(float), l.values.astype(float)
    ok = (h > 0) & (l > 0) & (h >= l)
    h, l = np.where(ok, h, np.nan), np.where(ok, l, np.nan)
    beta = np.log(h[1:] / l[1:]) ** 2 + np.log(h[:-1] / l[:-1]) ** 2
    gamma = np.log(np.fmax(h[1:], h[:-1]) / np.fmin(l[1:], l[:-1])) ** 2
    k = 3 - 2 * np.sqrt(2)
    alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / k - np.sqrt(gamma / k)
    s = 2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha))
    s = np.where(s < 0, 0, s)
    return float(np.nanmean(s)) if np.isfinite(s).any() else np.nan


def first_pos(index, date, strict=False):
    i = index.searchsorted(pd.Timestamp(date), side="right" if strict else "left")
    return int(i) if i < len(index) else None


def analyse_event(ev, s, b, beta1=False):
    """Return (row dict, AR series indexed by event time) for one event."""
    idx = s.index
    px = s["adjclose"]
    vol = s["volume"].fillna(0).values
    blev = b["adjclose"].reindex(idx.union(b.index)).ffill().reindex(idx)
    rs, rb = px.pct_change(), blev.pct_change()

    i0 = first_pos(idx, ev.disclosure_date, strict=(ev.disclosure_timing == "post"))
    if i0 is None or i0 < 40:
        return None, None
    # reaction end: extend through trading halts (zero volume days)
    e = i0
    if vol[e] > 0 and e + 1 < len(idx) and vol[e + 1] == 0:
        e += 1                                     # intraday halt starting on day 0
    while e < len(idx) - 1 and vol[e] == 0 and e - i0 < 15:
        e += 1
    halt = e - i0

    est = pd.DataFrame({"rs": rs.iloc[max(0, i0 - 280): i0 - 30],
                        "rb": rb.iloc[max(0, i0 - 280): i0 - 30]}).dropna()
    if len(est) >= 100 and not beta1:
        bta, alp = np.polyfit(est.rb, est.rs, 1)
        resid = est.rs - (alp + bta * est.rb)
        model = "market_model"
    else:
        bta, alp = 1.0, 0.0
        resid = est.rs - est.rb if len(est) > 20 else pd.Series(rs.iloc[:i0].dropna() - rb.iloc[:i0].dropna())
        model = "market_adjusted"
        if beta1 and len(est) > 20:
            resid = est.rs - est.rb
    sigma = float(resid.std())

    ar_raw = rs - (alp + bta * rb)
    # event time: pre days relative to i0, post days relative to reaction end e
    t_of = {}
    for p in range(max(1, i0 - PRE), min(len(idx), e + POST)):
        if p < i0:
            t_of[p] = p - i0
        elif p <= e:
            t_of[p] = 0
        else:
            t_of[p] = p - e
    ar = pd.Series({p: ar_raw.iloc[p] for p in t_of}).groupby(pd.Series(t_of)).sum(min_count=1)

    def car(a, z):
        w = ar.loc[a:z]
        need = z - a + 1
        return float(w.sum()) if w.notna().sum() == need else np.nan

    def bhar(p1, p2):
        """Hedged buy-and-hold return from close of position p1 to close of p2."""
        if p1 < 0 or p2 >= len(idx) or p2 <= p1:
            return np.nan
        r_s = px.iloc[p2] / px.iloc[p1] - 1
        r_b = blev.iloc[p2] / blev.iloc[p1] - 1
        return float(r_s - bta * r_b)

    def scar(c, L):
        return c / (sigma * np.sqrt(L)) if sigma > 0 and np.isfinite(c) else np.nan

    tier = ev.size_tier
    cs = corwin_schultz(s["high"].iloc[max(0, i0 - 120): i0 - 10], s["low"].iloc[max(0, i0 - 120): i0 - 10])
    spread = max(cs if np.isfinite(cs) else 0, TIER_SPREAD_FLOOR[tier])
    rt_cost = spread + 2 * COMMISSION
    borrow = TIER_BORROW[tier]

    row = dict(event_id=ev.event_id, ticker=ev.ticker_used, benchmark=ev.benchmark,
               exchange=exchange_of(ev.ticker_used), day0=idx[i0].date(), reaction_end=idx[e].date(),
               halt_days=halt, model=model, beta=round(bta, 3), sigma_daily=sigma,
               spread_est=cs, round_trip_cost=rt_cost, borrow_annual=borrow)

    # (a) pre-disclosure drift from physical start
    if isinstance(ev.phys_start_date, str) and ev.phys_start_date:
        ps = first_pos(idx, ev.phys_start_date)
        if ps is not None and ps < i0:
            L = i0 - ps
            row.update(pre_phys_days=L, car_pre_phys=car(-L, -1), bhar_pre_phys=bhar(ps - 1, i0 - 1))
            row["scar_pre_phys"] = scar(row["car_pre_phys"], L)
        else:
            row.update(pre_phys_days=0)
    for a, z in [(-20, -1), (-5, -1), (-1, -1), (0, 0), (1, 1), (0, 1), (1, 5), (1, 20), (1, 60), (2, 5), (2, 20), (2, 60)]:
        c = car(a, z)
        row[f"car_{a}_{z}"] = c
        L = (z - a + 1) + (halt if a <= 0 <= z else 0)
        row[f"scar_{a}_{z}"] = scar(c, L)

    # multi-stage events: reaction at the later "material" date
    if isinstance(ev.material_date, str) and ev.material_date:
        im = first_pos(idx, ev.material_date)
        if im is not None and im > e:
            row["car_material_0_1"] = float(ar_raw.iloc[im: im + 2].sum())
            row["car_day0_to_material_end"] = float(ar_raw.iloc[i0: im + 2].sum())

    # value of a k-day lead: short at close of day -k, cover at end of reaction (or +1)
    for k in (1, 5, 20):
        for xo, tag in [(0, "d0"), (1, "d1")]:
            g = -bhar(i0 - k, e + xo)  # close of day -k is position i0-k
            days = k + halt + xo
            row[f"lead{k}_{tag}_gross"] = g
            row[f"lead{k}_{tag}_net"] = g - rt_cost - borrow * days / 252 if np.isfinite(g) else np.nan
    # post-disclosure drift: short at close of reaction day, cover after N days
    for N in (5, 20, 60):
        g = -bhar(e, e + N)
        row[f"bhar_1_{N}"] = -g
        row[f"drift{N}_short_gross"] = g
        row[f"drift{N}_short_net"] = g - rt_cost - borrow * N / 252 if np.isfinite(g) else np.nan
        row[f"drift{N}_long_net"] = -g - rt_cost if np.isfinite(g) else np.nan
        # entering one day later (after the next-day reaction)
        g1 = -bhar(e + 1, e + 1 + N)
        row[f"drift{N}_short_lag1_net"] = g1 - rt_cost - borrow * N / 252 if np.isfinite(g1) else np.nan
    return row, ar


def describe(x, sx=None):
    """Cross-sectional statistics; sx are standardized values for the BMP test."""
    x = pd.Series(x, dtype=float).dropna()
    n = len(x)
    out = dict(n=n, mean=np.nan, median=np.nan, sd=np.nan, t=np.nan, p=np.nan,
               bmp_t=np.nan, wilcoxon_p=np.nan, pct_negative=np.nan)
    if n == 0:
        return out
    out.update(mean=x.mean(), median=x.median(), pct_negative=(x < 0).mean())
    if n >= 2:
        sd = x.std(ddof=1)
        out.update(sd=sd, t=x.mean() / (sd / np.sqrt(n)) if sd > 0 else np.nan)
        out["p"] = 2 * stats.t.sf(abs(out["t"]), n - 1) if np.isfinite(out["t"]) else np.nan
        if n >= 6:
            try:
                out["wilcoxon_p"] = stats.wilcoxon(x).pvalue
            except ValueError:
                pass
    if sx is not None:
        z = pd.Series(sx, dtype=float).dropna()
        if len(z) >= 2 and z.std(ddof=1) > 0:
            out["bmp_t"] = z.mean() / (z.std(ddof=1) / np.sqrt(len(z)))
    return out


GROUPS = {
    "all": lambda d: d.index == d.index,
    "single_or_large_share": lambda d: d.share_class.isin(["single", "large"]),
    "single_asset": lambda d: d.share_class == "single",
    "large_share": lambda d: d.share_class == "large",
    "small_share": lambda d: d.share_class == "small",
    "size_small_cap": lambda d: d.size_tier == "small",
    "size_mid_cap": lambda d: d.size_tier == "mid",
    "size_large_cap": lambda d: d.size_tier == "large",
    "type_geotech": lambda d: d.type_group == "geotech",
    "type_accident": lambda d: d.type_group == "accident",
    "type_weather": lambda d: d.type_group == "weather",
    "type_labour_community": lambda d: d.type_group == "labour_community",
    "type_state_security": lambda d: d.type_group == "state_security",
    "type_guidance": lambda d: d.type_group == "guidance",
    "exch_ASX": lambda d: d.exchange == "ASX",
    "exch_TSX": lambda d: d.exchange == "TSX",
    "exch_US": lambda d: d.exchange == "US",
    "exch_other": lambda d: d.exchange.isin(["LSE", "HKEX", "JSE"]),
    "physical_start_1plus_days_before": lambda d: d.pre_phys_days.fillna(0) >= 1,
    "physical_start_5plus_days_before": lambda d: d.pre_phys_days.fillna(0) >= 5,
    "selected_from_prompt_or_news": lambda d: d.selection == "prompt",
    "selected_by_asx_keyword_scan": lambda d: d.selection == "asx_keyword",
}

METRICS = [("car_pre_phys", "scar_pre_phys"), ("car_-20_-1", "scar_-20_-1"), ("car_-5_-1", "scar_-5_-1"),
           ("car_-1_-1", "scar_-1_-1"), ("car_0_0", "scar_0_0"), ("car_1_1", "scar_1_1"),
           ("car_0_1", "scar_0_1"), ("car_1_5", "scar_1_5"), ("car_1_20", "scar_1_20"),
           ("car_1_60", "scar_1_60"), ("car_2_20", "scar_2_20"), ("car_2_60", "scar_2_60"),
           ("car_material_0_1", None), ("bhar_pre_phys", None), ("bhar_1_5", None), ("bhar_1_20", None),
           ("bhar_1_60", None)]


def plot(path_df, fig_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ink, bg, grid = "#52514e", "#fcfcfb", "#e6e5e1"
    cols = {"single_or_large_share": "#2a78d6", "small_share": "#eb6834"}
    labels = {"single_or_large_share": "Single mine or large share of company",
              "small_share": "Small share of company"}
    fig, ax = plt.subplots(figsize=(8, 4.6), dpi=150)
    fig.patch.set_facecolor(bg); ax.set_facecolor(bg)
    for g, c in cols.items():
        d = path_df[path_df.group == g]
        n = int(d.n.max())
        ax.fill_between(d.t, 100 * (d.mean_car - d.se), 100 * (d.mean_car + d.se), color=c, alpha=0.12, lw=0)
        ax.plot(d.t, 100 * d.mean_car, color=c, lw=2, label=f"{labels[g]} (n={n})")
        ax.annotate(f"{100 * d.mean_car.iloc[-1]:.1f}%", (d.t.iloc[-1], 100 * d.mean_car.iloc[-1]),
                    xytext=(4, 0), textcoords="offset points", va="center", color=ink, fontsize=8)
    ax.axvline(0, color=ink, ls="--", lw=1)
    ax.axhline(0, color=grid, lw=1)
    ax.text(0.5, ax.get_ylim()[1], " disclosure", color=ink, fontsize=8, va="top")
    ax.grid(axis="y", color=grid, lw=0.6)
    ax.set_axisbelow(True)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(colors=ink, labelsize=8, length=0)
    ax.set_xlabel("Trading days relative to first disclosure (halt days folded into day 0)", color=ink, fontsize=9)
    ax.set_ylabel("Mean cumulative abnormal return from day -20 (%)", color=ink, fontsize=9)
    ax.set_title("Mine disruptions: the market moves on the announcement, not before", color=ink,
                 fontsize=11, loc="left")
    ax.legend(frameon=False, fontsize=8, labelcolor=ink, loc="lower left")
    ax.set_xlim(-20, 66)
    fig.text(0.01, 0.01, "Shaded band = ±1 standard error. Market-model abnormal returns vs sector benchmark.",
             color=ink, fontsize=7)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(fig_path, facecolor=bg)


def summarise(res, out_dir, tag=""):
    rows = []
    for gname, f in GROUPS.items():
        d = res[f(res)]
        for m, sm in METRICS:
            if m not in d:
                continue
            st = describe(d[m], d[sm] if sm and sm in d else None)
            rows.append(dict(group=gname, metric=m, **st))
    return pd.DataFrame(rows)


def run_all(ev, price_dir, beta1=False, use_material=False):
    """Analyse every usable event; returns (list of row dicts, {event_id: AR series})."""
    rows, ars = [], {}
    for _, e in ev.iterrows():
        status = e.data_status
        if status not in USABLE or e.benchmark == "":
            rows.append(dict(event_id=e.event_id, ticker=e.ticker_used, status=status or "no_benchmark"))
            continue
        s, b = load_px(price_dir, e.ticker_used), load_px(price_dir, e.benchmark)
        if s is None or b is None:
            rows.append(dict(event_id=e.event_id, ticker=e.ticker_used, status="missing"))
            continue
        if use_material and e.material_date:
            e = e.copy(); e["disclosure_date"], e["disclosure_timing"] = e.material_date, "unknown"
        r, ar = analyse_event(e, s, b, beta1=beta1)
        if r is None:
            rows.append(dict(event_id=e.event_id, ticker=e.ticker_used, status="insufficient_history"))
            continue
        r["status"] = "analysed"
        rows.append(r); ars[e.event_id] = ar
    return rows, ars


def main(ev_path, price_dir, out_dir, fig_dir=None):
    os.makedirs(out_dir, exist_ok=True)
    ev = pd.read_csv(ev_path, dtype=str).fillna("")
    rows, ars = run_all(ev, price_dir)
    res = pd.DataFrame(rows).merge(
        ev[["event_id", "company", "mine", "share_class", "size_tier", "type_group", "event_type",
            "disclosure_date", "disclosure_timing", "phys_start_date", "material_date", "cluster",
            "in_sample", "selection"]], on="event_id", how="left")

    # overlapping windows of the same stock ([-60, +60] trading days)
    res["overlap_with"] = ""
    a = res[res.status == "analysed"]
    for t, g in a.groupby("ticker"):
        g = g.sort_values("day0")
        d0 = pd.to_datetime(g.day0).tolist(); ids = g.event_id.tolist()
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                if (d0[j] - d0[i]).days < 170:  # ~120 trading days
                    res.loc[res.event_id == ids[i], "overlap_with"] += ids[j] + " "
                    res.loc[res.event_id == ids[j], "overlap_with"] += ids[i] + " "
    res.to_csv(os.path.join(out_dir, "event_results.csv"), index=False)

    main_s = res[(res.status == "analysed") & (res.in_sample == "1")].copy()
    summ = summarise(main_s, out_dir)
    summ.to_csv(os.path.join(out_dir, "summary.csv"), index=False)

    # value of lead
    lead_rows = []
    for gname in ["all", "single_or_large_share", "single_asset", "small_share", "size_small_cap", "size_mid_cap",
                  "size_large_cap", "type_geotech", "exch_ASX", "exch_TSX", "exch_US",
                  "physical_start_1plus_days_before", "physical_start_5plus_days_before"]:
        d = main_s[GROUPS[gname](main_s)]
        for k in (1, 5, 20):
            for tag in ("d0", "d1"):
                gcol, ncol = f"lead{k}_{tag}_gross", f"lead{k}_{tag}_net"
                gs, ns = describe(d[gcol]), describe(d[ncol])
                cost = (d[gcol] - d[ncol]).mean()
                lead_rows.append(dict(group=gname, lead_days=k, exit="reaction day" if tag == "d0" else "reaction day +1",
                                      n=gs["n"], gross_mean=gs["mean"], gross_median=gs["median"], gross_t=gs["t"],
                                      cost_mean=cost, net_mean=ns["mean"], net_median=ns["median"], net_t=ns["t"],
                                      net_p=ns["p"], pct_profitable=(d[ncol] > 0).mean() if len(d) else np.nan))
    pd.DataFrame(lead_rows).to_csv(os.path.join(out_dir, "lead_value.csv"), index=False)

    drift_rows = []
    for gname in ["all", "single_or_large_share", "single_asset", "small_share", "size_small_cap", "size_mid_cap",
                  "size_large_cap", "type_geotech", "exch_ASX", "exch_TSX", "exch_US"]:
        d = main_s[GROUPS[gname](main_s)]
        for N in (5, 20, 60):
            for side, col in [("short at reaction close", f"drift{N}_short_net"),
                              ("short one day later", f"drift{N}_short_lag1_net"),
                              ("long (buy the drop)", f"drift{N}_long_net")]:
                st = describe(d[col])
                drift_rows.append(dict(group=gname, hold_days=N, side=side, n=st["n"],
                                       gross_mean=describe(d[f"drift{N}_short_gross"])["mean"] * (1 if "short" in side else -1),
                                       net_mean=st["mean"], net_median=st["median"], net_t=st["t"], net_p=st["p"],
                                       pct_profitable=(d[col] > 0).mean() if len(d) else np.nan))
    pd.DataFrame(drift_rows).to_csv(os.path.join(out_dir, "drift_strategy.csv"), index=False)

    # robustness
    rob = []
    def add(label, d, cols=("car_-5_-1", "car_0_1", "car_1_20", "car_1_60")):
        for c in cols:
            st = describe(d[c]); rob.append(dict(variant=label, metric=c, **st))
    add("baseline", main_s)
    w = main_s.copy()
    for c in ("car_-5_-1", "car_0_1", "car_1_20", "car_1_60"):
        lo, hi = w[c].quantile([0.05, 0.95]); w[c] = w[c].clip(lo, hi)
    add("winsorised 5/95", w)
    add("excluding state/security events", main_s[main_s.type_group != "state_security"])
    add("excluding overlapping same-stock windows", main_s[main_s.overlap_with == ""])
    add("one event per cluster (drop VALE_2015 and later CRN/SBM/ABX repeats)",
        main_s[(main_s.cluster == "") | ~main_s.duplicated("cluster", keep="first")])
    insample = set(main_s.event_id)
    geo = set(main_s[main_s.type_group == "geotech"].event_id)
    add("baseline | geotech events only", main_s[main_s.event_id.isin(geo)])
    for label, kw in [("market-adjusted returns (beta = 1)", dict(beta1=True)),
                      ("day 0 = later 'material' date where one exists (8 events)", dict(use_material=True))]:
        alt = pd.DataFrame(run_all(ev, price_dir, **kw)[0])
        add(label, alt[alt.event_id.isin(insample)])
        add(label + " | geotech events only", alt[alt.event_id.isin(geo)])
    oos = res[(res.status == "analysed") & (res.in_sample == "0")]
    if len(oos):
        add("out-of-range events only (Mount Polley 2014)", oos)
    pd.DataFrame(rob).to_csv(os.path.join(out_dir, "robustness.csv"), index=False)

    # CAR path for figure
    path_rows = []
    for gname in ["all", "single_or_large_share", "small_share"]:
        ids = main_s[GROUPS[gname](main_s)].event_id
        M = pd.DataFrame({i: ars[i].reindex(range(-20, 61)) for i in ids if i in ars})
        C = M.cumsum()
        C = C.loc[:, C.notna().all()]
        for t in C.index:
            v = C.loc[t]
            path_rows.append(dict(group=gname, t=t, n=v.size, mean_car=v.mean(), median_car=v.median(),
                                  se=v.std(ddof=1) / np.sqrt(v.size)))
    path = pd.DataFrame(path_rows)
    path.to_csv(os.path.join(out_dir, "car_path.csv"), index=False)
    if fig_dir:
        os.makedirs(fig_dir, exist_ok=True)
        plot(path, os.path.join(fig_dir, "car_disclosure.png"))

    print(res.status.value_counts().to_string())
    key = summ[(summ.group == "all")][["metric", "n", "mean", "median", "t", "bmp_t", "pct_negative"]]
    print(key.to_string(index=False, float_format=lambda v: f"{v:.4f}"))


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    main(*sys.argv[1:5])
