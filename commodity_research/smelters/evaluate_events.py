"""Test 1: do known smelter outages/restarts show in the Sentinel-2 hot-pixel index? (pre-registered)

For each row of events.csv: share of valid scenes with >= 1 furnace-mask hot pixel in the event
window vs the baseline window. Outage detected if window share <= 0.5 x baseline share, one-sided
Fisher exact p < 0.05 and >= 3 valid scenes in the window; restart detected if share >= 2 x the
baseline (= outage) share with p < 0.05. Done twice: primary mask (2017-2024) and a mask built
from the baseline window only (robustness).

Usage:
    python evaluate_events.py [--events events.csv] [--s2 data/s2] [--out results/events_results.csv]
"""
import argparse, os
import pandas as pd
from scipy.stats import fisher_exact
import index as idx

HERE = os.path.dirname(os.path.abspath(__file__))


def share(df, a, b):
    w = df[df.valid & (df.date >= a) & (df.date <= b)]
    return len(w), int(w.active.sum())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--events", default=os.path.join(HERE, "events.csv"))
    ap.add_argument("--s2", default=os.path.join(HERE, "data", "s2"))
    ap.add_argument("--out", default=os.path.join(HERE, "results", "events_results.csv"))
    a = ap.parse_args()
    ev = pd.read_csv(a.events)
    rows = []
    for e in ev.itertuples():
        f = os.path.join(a.s2, f"{e.smelter}.csv")
        if not os.path.exists(f):
            rows.append(dict(event_id=e.event_id, status="no data")); continue
        for variant, (ms, me) in {"primary": ("2017-01-01", "2024-12-31"), "baseline_mask": (e.baseline_start, e.baseline_end)}.items():
            df, mask, meta = idx.smelter_index(f, ms, me)
            nb, ab = share(df, e.baseline_start, e.baseline_end)
            nw, aw = share(df, e.start, e.end)
            sb = ab / nb if nb else float("nan"); sw = aw / nw if nw else float("nan")
            if nw < 3 or nb < 3:
                status, p = "not testable", float("nan")
            elif e.expected == "off":
                p = fisher_exact([[aw, nw - aw], [ab, nb - ab]], alternative="less")[1]
                status = "detected" if (sw <= 0.5 * sb and p < 0.05) else "missed"
            else:
                p = fisher_exact([[aw, nw - aw], [ab, nb - ab]], alternative="greater")[1]
                status = "detected" if (sw >= 2 * sb and p < 0.05) else "missed"
            act = df[df.valid & (df.active == 1)]
            last_before = act[act.date < e.start].date.max()
            first_after = act[act.date >= e.start].date.min()
            rows.append(dict(event_id=e.event_id, smelter=e.smelter, variant=variant, expected=e.expected,
                             baseline_valid=nb, baseline_active=ab, baseline_share=round(sb, 3),
                             window_valid=nw, window_active=aw, window_share=round(sw, 3), fisher_p=round(p, 4) if p == p else None,
                             status=status, mask_px=meta["mask_px"], last_active_before=last_before, first_active_from_start=first_after))
        # night-time Sentinel-3 SLSTR FRP (granule active = >= 1 detection within 1.5 km)
        ff = os.path.join(HERE, "data", "s3frp", f"{e.smelter}.csv")
        if os.path.exists(ff) and e.baseline_start >= "2020-08-08":
            fr = pd.read_csv(ff)
            fr["date"] = fr.datetime.str[:10]; fr["valid"] = True; fr["active"] = (fr.n_fire > 0).astype(int)
            nb, ab = share(fr, e.baseline_start, e.baseline_end); nw, aw = share(fr, e.start, e.end)
            sb = ab / nb if nb else float("nan"); sw = aw / nw if nw else float("nan")
            if nw < 3 or nb < 3 or (ab == 0 and e.expected == "off"):
                status, p = ("not testable" if ab else "no baseline signal"), float("nan")
            elif e.expected == "off":
                p = fisher_exact([[aw, nw - aw], [ab, nb - ab]], alternative="less")[1]
                status = "detected" if (sw <= 0.5 * sb and p < 0.05) else "missed"
            else:
                p = fisher_exact([[aw, nw - aw], [ab, nb - ab]], alternative="greater")[1]
                status = "detected" if (sw >= 2 * sb and p < 0.05) else "missed"
            rows.append(dict(event_id=e.event_id, smelter=e.smelter, variant="s3_frp_night", expected=e.expected,
                             baseline_valid=nb, baseline_active=ab, baseline_share=round(sb, 3), window_valid=nw, window_active=aw,
                             window_share=round(sw, 3), fisher_p=round(p, 4) if p == p else None, status=status))
    out = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    out.to_csv(a.out, index=False)
    print(out.to_string())
    for v in ["primary", "baseline_mask", "s3_frp_night"]:
        s = out[out.variant == v]
        t = s[s.status.isin(["detected", "missed"])]
        print(v, "detected", (t.status == "detected").sum(), "of", len(t), "testable;", (s.status == "not testable").sum(), "not testable")


if __name__ == "__main__":
    main()
