"""Evaluate the satellite yield signal against finals and against the official vintage public at each date.

Reads signal/soy_sat_signal_v1.csv (with --holdout) or signal/dev_only_signal_v1.csv (development),
and the benchmark agent's point-in-time file ../benchmark/data/pit/pit_soy_brazil.csv.

Outputs in results/:
  accuracy_by_asof.csv     |error| of yield vs final by as-of date, sat vs trend vs official, dev vs holdout
  official_vs_sat_asof.csv every (season, region, as-of) with sat estimate, official vintage then public
                           (Conab for 2019/20+, IBGE LSPA otherwise), its later revisions and final
  revision_test.csv        does (sat - official) at a release predict the NEXT official revision,
                           beyond the official's own last revision (persistence baseline)?
  shock_seasons.csv        divergence vs official and lead time in shock seasons
and figures/fig_accuracy_by_asof.png, figures/fig_shock_paths.png
Usage: python evaluate.py [--holdout]
"""
import argparse, os
import numpy as np, pandas as pd
from plotstyle import setup, C, TEXT, MUTED

HERE = os.path.dirname(os.path.abspath(__file__))
PIT = f"{HERE}/../benchmark/data/pit/pit_soy_brazil.csv"
STATES = ["MT", "PR", "RS", "GO", "MS", "BA", "MG", "MA", "TO", "PI", "SP", "SC"]
HOLD = 2023
SHOCKS = {2012: ["BR", "RS", "PR", "MS"], 2016: ["BR", "BA", "MA", "TO", "PI", "MT"], 2019: ["BR", "PR", "MS", "GO"],
          2020: ["BR", "RS"], 2022: ["BR", "PR", "RS", "MS"], 2023: ["BR", "RS"], 2024: ["BR", "MT", "RS", "MS", "PR"],
          2025: ["BR", "RS"]}


def cy(Y):
    return f"{Y - 1}/{str(Y)[2:]}"


def ols_cluster(y, X, g):
    """OLS with intercept; returns coef, cluster-robust (by g) t-stats, n, R2."""
    X = np.column_stack([np.ones(len(y)), X])
    XtXi = np.linalg.pinv(X.T @ X); b = XtXi @ X.T @ y; e = y - X @ b
    meat = np.zeros((X.shape[1], X.shape[1]))
    for k in np.unique(g):
        m = g == k; s = X[m].T @ e[m]; meat += np.outer(s, s)
    G = len(np.unique(g)); n, p = X.shape
    V = XtXi @ meat @ XtXi * G / max(G - 1, 1) * (n - 1) / max(n - p, 1)
    r2 = 1 - (e @ e) / ((y - y.mean()) @ (y - y.mean()))
    return b, b / np.sqrt(np.diag(V)), n, r2


def official_table(pit):
    o = pit[(pit.variable == "yield") & (pit.source.isin(["conab", "ibge_lspa"]))].copy()
    o = o[(o.is_current_crop == 1) | (o.source == "ibge_lspa")]
    o["season"] = o.crop_year.str[:4].astype(int) + 1
    o["release_date"] = pd.to_datetime(o.release_date)
    o = o[o.region.isin(STATES + ["BR"])].sort_values(["source", "region", "season", "release_date"])
    o = o.drop_duplicates(["source", "region", "season", "release_date"], keep="last")
    return o[["source", "region", "season", "release_date", "value"]]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--holdout", action="store_true", help="evaluate the full file including holdout seasons")
    ap.add_argument("--tag", default="v1", help="signal version to evaluate; results get a suffix unless v1")
    a = ap.parse_args()
    S = pd.read_csv(f"{HERE}/signal/soy_sat_signal_{a.tag}.csv" if a.holdout else f"{HERE}/signal/dev_only_signal_{a.tag}.csv")
    sfx = "" if a.tag == "v1" else f"_{a.tag}"
    S = S.rename(columns={"final_yield_expost": "final_yield"})
    S["as_of_date"] = pd.to_datetime(S.as_of_date)
    S["period"] = np.where(S.season >= HOLD, "holdout", "dev")
    os.makedirs(f"{HERE}/results", exist_ok=True)
    pit = pd.read_csv(PIT); O = official_table(pit)
    # official's own final = its latest vintage
    ofin = O.groupby(["source", "region", "season"]).value.last().rename("official_final")
    # which source is "the official" for a season: Conab when available (2019/20+), else LSPA
    def src_for(Y):
        return "conab" if Y >= 2020 else "ibge_lspa"

    # trend for BR: area-weighted trend not stored -> use states' trend aggregated with the same areas
    st = S[S.state != "BR"].copy()
    brt = st.groupby(["season", "as_of_date"]).apply(lambda d: (d.trend_yield * d.area_ha_used).sum() / d.area_ha_used.sum()).rename("trend_br")
    S = S.merge(brt.reset_index(), on=["season", "as_of_date"], how="left")
    S.loc[S.state != "BR", "trend_br"] = S.trend_yield
    S["trend_use"] = np.where(S.state == "BR", S.trend_br, S.trend_yield)

    # attach official vintage public at each as-of (strictly before as-of date)
    rows = []
    for r in S.itertuples():
        src = src_for(r.season)
        q = O[(O.source == src) & (O.region == r.state) & (O.season == r.season)]
        prev = q[q.release_date < r.as_of_date]
        fin = ofin.get((src, r.state, r.season), np.nan)
        rows.append(dict(official_source=src, official_at_asof=prev.value.iloc[-1] if len(prev) else np.nan,
                         official_release=prev.release_date.iloc[-1] if len(prev) else pd.NaT, official_final=fin))
    S = pd.concat([S.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
    S["sat_err"] = S.predicted_yield / S.final_yield - 1
    S["trend_err"] = S.trend_use / S.final_yield - 1
    S["off_err"] = S.official_at_asof / S.official_final - 1
    S["gap_sat_vs_official"] = np.log(S.predicted_yield / S.official_at_asof)
    S["official_rev_to_final"] = np.log(S.official_final / S.official_at_asof)
    keep = ["season", "crop_year", "period", "as_of_date", "asof_slot", "state", "predicted_yield", "uncertainty_yield_1sd", "trend_use",
            "final_yield", "official_source", "official_release", "official_at_asof", "official_final", "sat_err", "trend_err", "off_err",
            "gap_sat_vs_official", "official_rev_to_final"]
    S[keep].to_csv(f"{HERE}/results/official_vs_sat_asof{sfx}.csv", index=False, float_format="%.4f")

    # ---------- accuracy by as-of ----------
    acc = []
    for (per, lvl), d in S.assign(level=np.where(S.state == "BR", "BR", "state")).groupby(["period", "level"]):
        for slot, g in d.groupby("asof_slot", sort=False):
            ok = g.dropna(subset=["off_err"])
            acc.append(dict(period=per, level=lvl, as_of_slot=slot, n=len(g), seasons=g.season.nunique(),
                            sat_mape=g.sat_err.abs().mean(), trend_mape=g.trend_err.abs().mean(),
                            n_with_official=len(ok), sat_mape_same=ok.sat_err.abs().mean() if len(ok) else np.nan,
                            official_mape_same=ok.off_err.abs().mean() if len(ok) else np.nan,
                            sat_within_1sd=(g.sat_err.abs() * g.predicted_yield <= g.uncertainty_yield_1sd).mean()))
    A = pd.DataFrame(acc)
    order = {s: i for i, s in enumerate(["11-01", "11-16", "12-01", "12-16", "01-01", "01-16", "02-01", "02-16", "03-01", "03-16", "04-01", "04-16", "05-01", "05-16", "06-01"])}
    A["o"] = A["as_of_slot"].map(order); A = A.sort_values(["level", "period", "o"]).drop(columns="o")
    A.to_csv(f"{HERE}/results/accuracy_by_asof{sfx}.csv", index=False, float_format="%.4f")

    # ---------- revision test ----------
    rt = []
    for (src, reg, Y), q in O[O.season >= S.season.min()].groupby(["source", "region", "season"]):
        q = q.reset_index(drop=True)
        sat = S[(S.state == reg) & (S.season == Y)].sort_values("as_of_date")
        for i in range(1, len(q) - 1):
            rd = q.release_date[i]
            if not (rd.month in (12, 1, 2, 3, 4, 5)):
                continue
            s_ = sat[sat.as_of_date <= rd]
            if len(s_) == 0:
                continue
            rt.append(dict(source=src, region=reg, season=Y, release_date=rd, official=q.value[i],
                           prev_rev=np.log(q.value[i] / q.value[i - 1]), next_rev=np.log(q.value[i + 1] / q.value[i]),
                           rev_to_final=np.log(q.value.iloc[-1] / q.value[i]),
                           sat=s_.predicted_yield.iloc[-1], sat_asof=s_.as_of_date.iloc[-1]))
    R = pd.DataFrame(rt)
    R["gap"] = np.log(R.sat / R.official)
    # remove the systematic level difference between sat (IBGE-PAM based) and each source, using only PRIOR seasons
    R = R.sort_values(["source", "region", "season", "release_date"])
    R["gap_adj"] = np.nan
    for (src, reg), g in R.groupby(["source", "region"]):
        for Y in g.season.unique():
            past = g[g.season < Y].gap
            R.loc[g.index[g.season == Y], "gap_adj"] = g[g.season == Y].gap - (past.mean() if len(past) >= 2 else 0.0)
    R["period"] = np.where(R.season >= HOLD, "holdout", "dev")
    R.to_csv(f"{HERE}/results/revision_test_rows{sfx}.csv", index=False, float_format="%.5f")
    res = []
    for (src, per), g in list(R.groupby(["source", "period"])) + [((s, "all"), R[R.source == s]) for s in R.source.unique()]:
        for lvl, gg in (("state", g[g.region != "BR"]), ("BR", g[g.region == "BR"])):
            if len(gg) < 12:
                continue
            for target in ("next_rev", "rev_to_final"):
                y = gg[target].values
                b0, t0, n, r20 = ols_cluster(y, gg[["prev_rev"]].values, gg.season.values)
                b, t, n, r2 = ols_cluster(y, gg[["prev_rev", "gap_adj"]].values, gg.season.values)
                big = gg[(gg.gap_adj.abs() > 0.03) & (gg[target].abs() > 0.005)]
                res.append(dict(source=src, period=per, level=lvl, target=target, n=n, seasons=gg.season.nunique(),
                                b_prev_only=b0[1], t_prev_only=t0[1], r2_prev_only=r20,
                                b_prev=b[1], t_prev=t[1], b_gap=b[2], t_gap=t[2], r2=r2,
                                n_gap_gt3pct_and_revised=len(big), sign_hit=(np.sign(big.gap_adj) == np.sign(big[target])).mean() if len(big) else np.nan))
    pd.DataFrame(res).to_csv(f"{HERE}/results/revision_test{sfx}.csv", index=False, float_format="%.4f")

    # ---------- divergence events and lead time ----------
    # bias between sat (IBGE-PAM definition) and each official source, from PRIOR seasons only
    S["gap_adj"] = np.nan
    for (src, reg), g in S.dropna(subset=["gap_sat_vs_official"]).groupby(["official_source", "state"]):
        for Y in g.season.unique():
            past = g[(g.season < Y) & (g.asof_slot == "03-01")].gap_sat_vs_official
            S.loc[g.index[g.season == Y], "gap_adj"] = g[g.season == Y].gap_sat_vs_official - (past.mean() if len(past) >= 2 else 0.0)
    ev = []
    S["sat_dev"] = S.predicted_yield / S.trend_use - 1
    base = []
    for (Y, reg), d in S[S.asof_slot.isin(["01-01", "01-16", "02-01", "02-16", "03-01", "03-16", "04-01"])].groupby(["season", "state"]):
        d = d.sort_values("as_of_date").dropna(subset=["gap_adj"])
        if len(d):  # unconditional base rate: official later moves >=3% (from its Jan/first in-window vintage)
            r0 = d.iloc[0]; tt = np.log(r0.official_final / r0.official_at_asof)
            base.append(dict(period="holdout" if Y >= HOLD else "dev", down=tt <= -0.03, up=tt >= 0.03))
        src = src_for(Y)
        q = O[(O.source == src) & (O.region == reg) & (O.season == Y)].sort_values("release_date")
        for sign in (-1, 1):
            # satellite-driven divergence: sat >= 5% beyond the official AND the satellite itself moved off trend that way
            hit = d[(sign * d.gap_adj >= 0.05) & (sign * d.sat_dev >= 0.02)]
            if not len(hit):
                continue
            r = hit.iloc[0]; o0 = r.official_at_asof
            later = q[q.release_date >= r.as_of_date]
            tot = np.log(r.official_final / o0)
            moved = sign * tot >= 0.03
            half = later[sign * np.log(later.value / o0) >= sign * tot / 2] if moved else later.iloc[0:0]
            hd = half.release_date.iloc[0] if len(half) else pd.NaT
            ev.append(dict(season=Y, crop_year=cy(Y), period="holdout" if Y >= HOLD else "dev", region=reg, direction="sat below official" if sign < 0 else "sat above official",
                           signal_asof=r.as_of_date.date(), gap_adj=r.gap_adj, official_then=o0, official_source=src,
                           official_later_revision=tot, official_followed=moved, official_half_revision_date=hd.date() if pd.notna(hd) else None,
                           lead_weeks=(hd - r.as_of_date).days / 7 if pd.notna(hd) else np.nan))
    E = pd.DataFrame(ev)
    B = pd.DataFrame(base).groupby("period")[["down", "up"]].mean()
    B.to_csv(f"{HERE}/results/official_revision_base_rate{sfx}.csv")
    E.to_csv(f"{HERE}/results/divergence_events{sfx}.csv", index=False, float_format="%.4f")

    # ---------- shock seasons ----------
    sh = []
    for Y, regs in SHOCKS.items():
        for reg in regs:
            d = S[(S.season == Y) & (S.state == reg)].sort_values("as_of_date")
            if not len(d):
                continue
            src = src_for(Y)
            q = O[(O.source == src) & (O.region == reg) & (O.season == Y)].sort_values("release_date")
            fin_o = ofin.get((src, reg, Y), np.nan); thr = 0.03 if reg == "BR" else 0.06

            def first_settled(dates, errs):
                ok = np.abs(np.asarray(errs)) <= thr
                for i in range(len(ok)):
                    if ok[i:].all():
                        return dates[i]
                return pd.NaT
            sat_d = first_settled(list(d.as_of_date), d.sat_err.values)
            qq = q[q.release_date <= pd.Timestamp(Y, 7, 1)]
            off_d = first_settled(list(qq.release_date), (qq.value / fin_o - 1).values) if len(qq) else pd.NaT
            # divergence at selected dates
            for slot in ("12-01", "01-01", "02-01", "03-01", "04-01"):
                r = d[d.asof_slot == slot]
                if not len(r):
                    continue
                r = r.iloc[0]
                sh.append(dict(season=Y, crop_year=cy(Y), region=reg, as_of_slot=slot, sat_yield=r.predicted_yield, sat_err_vs_final=r.sat_err,
                               official_source=src, official_yield=r.official_at_asof, official_err_vs_own_final=r.off_err,
                               gap_sat_minus_official=r.gap_sat_vs_official, official_later_revision=r.official_rev_to_final,
                               official_moved_toward_sat=(np.sign(r.gap_sat_vs_official) == np.sign(r.official_rev_to_final)) if np.isfinite(r.gap_sat_vs_official) and abs(r.official_rev_to_final) > 0.005 else np.nan,
                               sat_settled_date=sat_d, official_settled_date=off_d,
                               sat_lead_weeks=(off_d - sat_d).days / 7 if pd.notna(sat_d) and pd.notna(off_d) else np.nan,
                               settle_threshold=thr))
    pd.DataFrame(sh).to_csv(f"{HERE}/results/shock_seasons{sfx}.csv", index=False, float_format="%.4f")

    # ---------- figures ----------
    plt = setup()
    br = A[A.level == "BR"]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    labs = list(order); x = np.arange(len(labs))
    dv = br[br.period == "dev"].set_index("as_of_slot").reindex(labs)
    ho = br[br.period == "holdout"].set_index("as_of_slot").reindex(labs)
    ax.plot(x, dv.sat_mape * 100, color=C[0], marker="o", ms=4, label="satellite, 2010/11-2021/22 (walk-forward)")
    if ho.sat_mape.notna().any():
        ax.plot(x, ho.sat_mape * 100, color=C[1], marker="o", ms=4, label="satellite, holdout 2022/23-2025/26")
    allp = br.groupby("as_of_slot")[["trend_mape", "official_mape_same", "n_with_official"]].apply(
        lambda g: pd.Series({"trend": np.average(g.trend_mape, weights=br.loc[g.index, "n"]),
                             "off": np.average(g.official_mape_same.fillna(0), weights=g.n_with_official) if g.n_with_official.sum() else np.nan})).reindex(labs)
    ax.plot(x, allp.trend * 100, color=C[2], ls="--", label="trend only, all seasons")
    ax.plot(x, allp.off * 100, color=C[3], marker="s", ms=4, label="official vintage public at date (Conab / IBGE LSPA)")
    ax.set_xticks(x); ax.set_xticklabels(labs, fontsize=7.5)
    ax.set_ylabel("mean |error| vs final, %"); ax.set_ylim(bottom=0)
    ax.set_title("Brazil soybean yield: forecast error by as-of date")
    ax.text(0, -0.17, "Official before Feb 16 = Conab only (2019/20+); from mid-Feb IBGE LSPA covers earlier seasons. Each source vs its own final.",
            transform=ax.transAxes, fontsize=7, color=TEXT)
    ax.legend(loc="lower left", fontsize=8)
    fig.tight_layout(); fig.savefig(f"{HERE}/figures/fig_accuracy_by_asof{sfx}.png", dpi=130); plt.close(fig)

    seas = [Y for Y in SHOCKS if Y in set(S.season)]
    nc = 4; nr = int(np.ceil(len(seas) / nc))
    fig, axs = plt.subplots(nr, nc, figsize=(13, 3.2 * nr), sharey=True)
    for ax, Y in zip(np.ravel(axs), seas):
        d = S[(S.season == Y) & (S.state == "BR")].sort_values("as_of_date")
        src = src_for(Y)
        q = O[(O.source == src) & (O.region == "BR") & (O.season == Y)].sort_values("release_date")
        q = q[(q.release_date >= pd.Timestamp(Y - 1, 10, 1)) & (q.release_date <= pd.Timestamp(Y, 7, 1))]
        ax.axhline(0, color=MUTED, lw=0.8)
        ax.fill_between(d.as_of_date, (d.predicted_yield - d.uncertainty_yield_1sd) / d.final_yield * 100 - 100,
                        (d.predicted_yield + d.uncertainty_yield_1sd) / d.final_yield * 100 - 100, color=C[0], alpha=0.12, lw=0)
        ax.plot(d.as_of_date, d.sat_err * 100, color=C[0], marker="o", ms=3, label="satellite")
        ax.plot(q.release_date, (q.value / ofin.get((src, "BR", Y)) - 1) * 100, color=C[1], marker="s", ms=4, drawstyle="steps-post",
                label="Conab" if src == "conab" else "IBGE LSPA")
        ax.set_title(f"{cy(Y)}{'  (holdout)' if Y >= HOLD else ''}", fontsize=10)
        ax.tick_params(axis="x", labelsize=7); ax.xaxis.set_major_formatter(__import__("matplotlib").dates.DateFormatter("%b"))
        ax.legend(fontsize=7, loc="upper right")
    for ax in np.ravel(axs)[len(seas):]:
        ax.axis("off")
    np.ravel(axs)[0].set_ylabel("% vs own final"); np.ravel(axs)[nc if nr > 1 else 0].set_ylabel("% vs own final")
    fig.suptitle("Brazil yield estimate vs final, shock seasons: satellite (as-of dates, ±1 sd) vs official vintages", x=0.01, ha="left", color=TEXT)
    fig.tight_layout(); fig.savefig(f"{HERE}/figures/fig_shock_paths{sfx}.png", dpi=120); plt.close(fig)
    print(A[A.level == "BR"].round(3).to_string())
    print(pd.DataFrame(res).round(3).to_string())


if __name__ == "__main__":
    main()
