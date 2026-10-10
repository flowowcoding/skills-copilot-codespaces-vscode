"""Wall-segment displacement series from OPERA DISP-S1 points (opera_disp.py output) and the
pre-registered detection test for the Bingham Canyon events.

Per track (direction + reference date): masked epochs are dropped; per-point increments
between consecutive epochs; segment increment = median over points with a valid increment
(needs >= 5 points and >= 20 % of the segment), minus the control-ring median; cumulated.
60-day change = cum(t) - cum(t - 60 d). Detection rule: detect.py / prereg.json.

Usage:
  python opera_analyze.py LONG.csv OUTDIR FIGDIR
Writes OUTDIR/bingham_opera_segments.csv, bingham_opera_detections.csv,
bingham_opera_false_alarms.csv and FIGDIR/bingham_opera_*.png
"""
import sys, json, os
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from detect import detect, pseudo_dates
import style

HERE = os.path.dirname(os.path.abspath(__file__))
SEGS = ["N", "NE", "SE", "S", "SW", "W"]


def segment_series(df):
    W = df.pivot_table(index="date", columns="pid", values="disp_mm")
    M = df.pivot_table(index="date", columns="pid", values="masked").astype(bool)
    W = W.where(~M)
    inc = W.diff()
    sec = df.drop_duplicates("pid").set_index("pid").sector
    out = {}
    for name in SEGS + ["control"]:
        cols = [c for c in inc.columns if sec.get(c) == name]
        if not cols:
            continue
        sub = inc[cols]; n = sub.notna().sum(axis=1)
        med = sub.median(axis=1).where(n >= max(5, 0.2 * len(cols)))
        out[name] = med; out[name + "|npts"] = n; out[name + "|valid_frac"] = W[cols].notna().mean(axis=1)
    S = pd.DataFrame(out)
    for name in SEGS:
        if name in S:
            rel = S[name] - S["control"]
            S[name + "|inc_rel"] = rel
            S[name + "|cum"] = rel.fillna(0).cumsum()
            S[name + "|ch60"] = change60(S[name + "|cum"], rel.notna())
    return S


def change60(cum, ok):
    vals = []
    for t in cum.index:
        t0 = t - pd.Timedelta(days=60)
        prev = cum[cum.index <= t0]
        win = ok[(ok.index > t0) & (ok.index <= t)]
        vals.append(cum[t] - prev.iloc[-1] if len(prev) and len(win) and win.mean() >= 0.5 else np.nan)
    return pd.Series(vals, index=cum.index)


def main():
    long_csv, outdir, figdir = sys.argv[1:4]
    pre = json.load(open(os.path.join(HERE, "prereg.json")))["sites"]["bingham"]
    df = pd.read_csv(long_csv, parse_dates=["date"])
    df = df[~((df.direction == "ASCENDING") & (df.frame.isna()))]      # 27 points from a second, partial ascending frame
    tracks = {}
    for d, g in df.groupby("direction"):
        tracks[d] = segment_series(g)
    seg_rows = []
    for d, S in tracks.items():
        T = S.copy(); T.insert(0, "direction", d); seg_rows.append(T)
    pd.concat(seg_rows).round(2).to_csv(os.path.join(outdir, "bingham_opera_segments.csv"))

    det, fa = [], []
    for ev in pre["events"]:
        for d, S in tracks.items():
            if S.index.max() < pd.Timestamp(ev["D"]) - pd.Timedelta(weeks=4):
                continue
            for seg in [ev["segment"]] + ev["also_check"]:
                r = detect(S[seg + "|ch60"], ev["D"], "insar")
                r.update(event=ev["name"], direction=d, segment=seg, primary=seg == ev["segment"],
                         valid_frac_window=round(float(S[seg + "|valid_frac"][(S.index >= pd.Timestamp(ev["D"]) - pd.DateOffset(months=12)) & (S.index <= pd.Timestamp(ev["D"]))].mean()), 2))
                det.append(r)
    for d, S in tracks.items():
        for D in pseudo_dates(S.index):
            for seg in SEGS:
                r = detect(S[seg + "|ch60"], D, "insar")
                fa.append({"direction": d, "segment": seg, "D": D.date(), "fired": r["first_alarm"] is not None,
                           "first_alarm": r["first_alarm"], "alarm_value": r["alarm_value"], "base_sd": r["base_sd"]})
    det = pd.DataFrame(det); fa = pd.DataFrame(fa)
    det.to_csv(os.path.join(outdir, "bingham_opera_detections.csv"), index=False)
    fa.to_csv(os.path.join(outdir, "bingham_opera_false_alarms.csv"), index=False)
    print(det[["event", "direction", "segment", "n_base", "base_sd", "first_alarm", "lead_days", "alarm_value", "late_alarm", "valid_frac_window"]].to_string())
    print("\npseudo-date windows firing (fraction):")
    print(fa.groupby(["direction", "segment"]).fired.mean().round(2).unstack(0))

    overview(tracks["DESCENDING"], os.path.join(figdir, "bingham_opera_overview_des.png"))
    style.apply()
    for ev, d, seg in [(pre["events"][0], "DESCENDING", "S"), (pre["events"][1], "ASCENDING", "SE"), (pre["events"][1], "DESCENDING", "SE")]:
        S = tracks[d]; D = pd.Timestamp(ev["D"])
        fig, ax = plt.subplots(figsize=(8, 3.6))
        lo, hi = D - pd.DateOffset(months=30), min(D + pd.DateOffset(months=6), S.index.max())
        Z = S[(S.index >= lo) & (S.index <= hi)]
        for other in SEGS:
            if other != seg:
                c = Z[other + "|cum"] - Z[other + "|cum"].iloc[0]
                ax.plot(c.index, c, color=style.MUTED, lw=1)
                ax.text(c.index[-1], c.iloc[-1], " " + other, color=style.MUTED, fontsize=7, va="center")
        c = Z[seg + "|cum"] - Z[seg + "|cum"].iloc[0]
        ax.plot(c.index, c, color=style.PRIMARY, lw=2)
        ax.text(c.index[-1], c.iloc[-1], f" {seg} wall", color=style.INK, fontsize=8, va="center")
        ax.axvspan(D - pd.DateOffset(months=24), D - pd.DateOffset(months=12), color="#efeee9", lw=0)
        ax.text(D - pd.DateOffset(months=24), 0.02, " baseline", transform=ax.get_xaxis_transform(), fontsize=7, color=style.INK)
        r = det[(det.event == ev["name"]) & (det.direction == d) & (det.segment == seg)].iloc[0]
        if r.first_alarm is not None and not pd.isna(r.first_alarm):
            style.mark(ax, pd.Timestamp(r.first_alarm), "rule fires", y=0.9, ls=":")
        style.mark(ax, D, "event / disclosure" if ev["D"] == "2024-07-16" else "failure 31 May")
        ax.set_ylabel("LOS displacement vs control (mm)")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        ax.set_title(f"Bingham Canyon, OPERA DISP-S1 {d.lower()}: {ev['name']}", color=style.INK)
        ax.set_xlim(lo, hi + pd.Timedelta(days=60))
        fig.tight_layout()
        fn = os.path.join(figdir, f"bingham_opera_{'2024' if ev['D'].startswith('2024') else '2021'}_{d[:3].lower()}.png")
        fig.savefig(fn, dpi=150); plt.close(fig); print(fn)


def overview(S, fn):
    """All six wall sectors, descending track, whole archive."""
    style.apply()
    fig, ax = plt.subplots(figsize=(8.5, 3.6))
    for seg in SEGS:
        c = S[seg + "|cum"]
        hl = seg in ("S", "SE")
        ax.plot(c.index, c, color=style.PRIMARY if seg == "S" else (style.INK if seg == "SE" else style.MUTED), lw=1.8 if hl else 1)
        ax.text(c.index[-1], c.iloc[-1], f" {seg}", color=style.INK if hl else style.MUTED, fontsize=8, va="center")
    style.mark(ax, pd.Timestamp("2021-05-31"), "Leo failure (SE)", y=0.98, ls=":")
    style.mark(ax, pd.Timestamp("2024-07-16"), "Q2 2024 disclosure", y=0.98)
    ax.set_ylabel("LOS displacement vs control (mm)")
    ax.set_title("Bingham Canyon wall sectors, OPERA DISP-S1 descending (flat stretches = winter gaps)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.tight_layout(); fig.savefig(fn, dpi=150); plt.close(fig); print(fn)


if __name__ == "__main__":
    main()
