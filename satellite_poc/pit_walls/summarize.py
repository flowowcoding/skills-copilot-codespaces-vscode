"""Collect the pre-registered detection results of every method/site into one table.

Usage:  python summarize.py RESULTS_DIR   (writes RESULTS_DIR/summary.csv)
"""
import sys, os
import pandas as pd

R = sys.argv[1]
rows = []
def add(fn, method, site, track_col=None, fixed_track=None):
    p = os.path.join(R, fn)
    if not os.path.exists(p):
        return
    d = pd.read_csv(p)
    for _, r in d.iterrows():
        rows.append({"site": site, "event": r.get("event", {"copler": "heap leach pad slip", "eagle": "heap leach pad failure"}.get(site)),
                     "method": method, "track": r[track_col] if track_col else fixed_track,
                     "segment": r["segment"], "D": r["D"], "n_baseline": r["n_base"], "baseline_sd": r["base_sd"],
                     "detected_before_D_minus_4wk": pd.notna(r["first_alarm"]) and r["first_alarm"] not in ("None", ""),
                     "first_alarm": r["first_alarm"], "lead_days": r["lead_days"], "late_alarm": r["late_alarm"],
                     "note": r.get("note", "")})
add("bingham_opera_detections.csv", "OPERA DISP-S1 (InSAR, 30 m)", "bingham", track_col="direction")
add("copler_licsar_detections.csv", "LiCSAR (InSAR, 100 m)", "copler", track_col="track")
add("eagle_licsar_detections.csv", "LiCSAR (InSAR, 100 m)", "eagle", track_col="track")
for s in ["bingham", "copler", "eagle"]:
    add(f"{s}_amplitude_detections.csv", "Sentinel-1 RTC amplitude (10 m)", s, fixed_track="S1 RTC")
out = pd.DataFrame(rows)
out.to_csv(os.path.join(R, "summary.csv"), index=False)
print(out[["site", "event", "method", "track", "segment", "baseline_sd", "detected_before_D_minus_4wk", "late_alarm", "note"]].to_string())
