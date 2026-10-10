"""Pre-registered detection rule (see prereg.json), shared by the OPERA, LiCSAR and amplitude tests.

detect(series, D, kind) -> dict with baseline stats, the first qualifying run in the search
window [D-12mo, D-4wk] (the lead), and the first run after it (late detection).
series: pandas Series indexed by date (the 60-day change for InSAR, the change index for amplitude).
"""
import numpy as np
import pandas as pd

RULES = {"insar": dict(k=3.0, absmin=15.0, run=3, two_sided=True),
         "amplitude": dict(k=3.0, absmin=0.0, run=2, two_sided=False)}


def runs(flags):
    """Start indices of runs of True, with their lengths."""
    out, start = [], None
    for i, f in enumerate(list(flags) + [False]):
        if f and start is None:
            start = i
        if not f and start is not None:
            out.append((start, i - start)); start = None
    return out


def detect(s, D, kind="insar"):
    r = RULES[kind]; D = pd.Timestamp(D); s = s.dropna()
    base = s[(s.index >= D - pd.DateOffset(months=24)) & (s.index < D - pd.DateOffset(months=12))]
    res = {"D": D.date(), "n_base": len(base), "base_mean": np.nan, "base_sd": np.nan,
           "first_alarm": None, "lead_days": None, "alarm_sign": None, "alarm_value": None, "late_alarm": None}
    if len(base) < 8:
        res["note"] = "baseline too short"; return res
    mu, sd = base.mean(), base.std(); res.update(base_mean=round(mu, 2), base_sd=round(sd, 2))
    dev = s - mu
    exc = (dev.abs() > r["k"] * sd) if r["two_sided"] else (dev > r["k"] * sd)
    exc &= s.abs() >= r["absmin"]
    lo, hi = D - pd.DateOffset(months=12), D - pd.Timedelta(weeks=4)
    for i, n in runs(exc.values):
        t = s.index[i]
        if n < r["run"] or t < lo:
            continue
        if t <= hi and res["first_alarm"] is None:
            res.update(first_alarm=t.date(), lead_days=(D - t).days, alarm_sign=int(np.sign(dev.iloc[i])),
                       alarm_value=round(float(s.iloc[i]), 2))
        elif t > hi and res["late_alarm"] is None and t <= D + pd.DateOffset(months=3):
            res["late_alarm"] = t.date()
    return res


def pseudo_dates(index, start_offset_months=24):
    """1 Jan / 1 Jul dates with a full 24-month history and data up to D."""
    t0 = index.min() + pd.DateOffset(months=start_offset_months); t1 = index.max()
    return [d for d in pd.date_range("2000-01-01", t1, freq="6MS") if d >= t0 and d.month in (1, 7)]
