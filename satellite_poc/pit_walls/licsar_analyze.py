"""Pre-registered precursor test on LiCSAR segment series (licsar_ts.py output) for heap-leach failures.

60-day change = sum of segment-minus-control LOS increments over pairs ending in the trailing
60 days (needs >= 50 % of those days covered by coherent pairs). Rule: detect.py / prereg.json,
reference date D = failure date (both failures were announced the same day).

Usage:
  python licsar_analyze.py SITE OUT_PREFIX FIG.png TRACK=CSV [TRACK=CSV ...]
e.g. python licsar_analyze.py copler results/copler_licsar figures/copler_licsar.png asc043=a.csv desc123=b.csv
"""
import sys, os, json
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from detect import detect, pseudo_dates
import style

HERE = os.path.dirname(os.path.abspath(__file__))


def ch60(df, seg):
    inc = df[f"{seg}|inc_mm"]; out = []
    for t in df.d2:
        w = df[(df.d2 > t - pd.Timedelta(days=60)) & (df.d2 <= t)]
        ok = w[f"{seg}|inc_mm"].notna()
        cover = w.dt[ok].sum() / 60.0
        out.append(w[f"{seg}|inc_mm"][ok].sum() if cover >= 0.5 else np.nan)
    return pd.Series(out, index=pd.DatetimeIndex(df.d2))


def main():
    site, prefix, fig_fn = sys.argv[1:4]
    tracks = dict(a.split("=", 1) for a in sys.argv[4:])
    cfg = json.load(open(os.path.join(HERE, "prereg.json")))["sites"][site]
    ev = cfg["events"][0]; seg = ev["segment"]; D = pd.Timestamp(ev["D"])
    det, fa, series = [], [], {}
    for name, fn in tracks.items():
        df = pd.read_csv(fn, parse_dates=["d1", "d2"])
        s = ch60(df, seg); series[name] = (df, s)
        r = detect(s, D, "insar"); r.update(site=site, track=name, segment=seg,
                                           coherent_pairs_window=int(df[(df.d2 >= D - pd.DateOffset(months=12)) & (df.d2 < D)][f"{seg}|inc_mm"].notna().sum()),
                                           pairs_window=int(((df.d2 >= D - pd.DateOffset(months=12)) & (df.d2 < D)).sum()))
        det.append(r)
        for P in pseudo_dates(s.dropna().index):
            if P >= D - pd.DateOffset(months=1):
                continue          # only windows that end before the real event
            q = detect(s, P, "insar")
            fa.append({"site": site, "track": name, "D": P.date(), "fired": q["first_alarm"] is not None,
                       "first_alarm": q["first_alarm"], "alarm_value": q["alarm_value"], "base_sd": q["base_sd"]})
        T = pd.DataFrame({"d1": df.d1.dt.date.values, "d2": df.d2.dt.date.values, "inc_mm": df[f"{seg}|inc_mm"].values,
                          "frac_coh": df[f"{seg}|frac_coh"].values, "cum_mm": df[f"{seg}|cum_mm"].values, "ch60_mm": s.values})
        T.round(2).to_csv(f"{prefix}_{name}_series.csv", index=False)
    det = pd.DataFrame(det); fa = pd.DataFrame(fa)
    det.to_csv(f"{prefix}_detections.csv", index=False); fa.to_csv(f"{prefix}_false_alarms.csv", index=False)
    print(det[["track", "n_base", "base_mean", "base_sd", "first_alarm", "lead_days", "alarm_value", "late_alarm", "coherent_pairs_window", "pairs_window"]].to_string())
    if len(fa):
        print(fa.groupby("track").fired.agg(["mean", "size"]))
        print(fa[fa.fired].to_string())

    style.apply()
    fig, ax = plt.subplots(figsize=(8.5, 3.6))
    lo = D - pd.DateOffset(months=30)
    for i, (name, (df, s)) in enumerate(series.items()):
        z = df[(df.d2 >= lo) & (df.d2 <= D + pd.DateOffset(months=3))]
        c = z[f"{seg}|cum_mm"] - z[f"{seg}|cum_mm"].iloc[0]
        col = style.PRIMARY if i == 0 else style.INK
        ax.plot(z.d2, c, color=col, lw=1.8 if i == 0 else 1.2, marker="." if i == 0 else None, ms=3)
        ax.text(z.d2.iloc[-1], c.iloc[-1], f"  {name}", color=style.INK, fontsize=8, va="center")
        r = det[det.track == name].iloc[0]
        if r.first_alarm is not None and not pd.isna(r.first_alarm):
            style.mark(ax, pd.Timestamp(r.first_alarm), f"rule fires ({name})", y=0.88 - 0.1 * i, ls=":")
    ax.axvspan(D - pd.DateOffset(months=24), D - pd.DateOffset(months=12), color="#efeee9", lw=0)
    ax.text(D - pd.DateOffset(months=24), 0.03, " baseline", transform=ax.get_xaxis_transform(), fontsize=7, color=style.INK)
    style.mark(ax, D, "failure (announced same day)")
    ax.set_ylabel("LOS vs control (mm, + towards satellite)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.set_title(f"{site.capitalize()} heap leach pad, LiCSAR 12-day interferogram chain (flat = incoherent pairs skipped)")
    fig.tight_layout(); fig.savefig(fig_fn, dpi=150); plt.close(fig); print(fig_fn)


if __name__ == "__main__":
    main()
