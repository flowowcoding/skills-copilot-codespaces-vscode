"""Monthly disturbed-ground footprint from a Sentinel-2 stack (output of s2bands.py).

Method (pre-registered, see README):
  1. Each image is put in log space and normalised per band by the median of undisturbed
     control pixels (everything outside the buffered site box). This removes sun angle,
     haze and season-wide moisture/greenness shifts.
  2. Baseline = per-pixel median of the normalised images from Jun-Sep of the baseline years
     (default 2018-2021, before construction started in March 2023).
  3. Change d = RMS over bands of (image - baseline).
  4. Monthly composite = per-pixel median of d over that month's clear images.
  5. A pixel is disturbed in a month when d is above the 99.5th percentile of d over the
     control pixels in the same month (false-positive rate 0.5% by construction). The expected
     false positives (0.5% of zone pixels) are subtracted from each zone's area.
Months where under 70% of the site box is cloud/snow free are left blank.

Usage:
    python footprint.py STACK.npz ZONES_JSON OUT.csv [--base-years 2018-2021] [--site x0,x1,y0,y1]
                        [--maps OUT_maps.npz]

ZONES_JSON maps zone name -> [x0, x1, y0, y1] in stack pixel coordinates (inclusive).
Zones are assigned in the order given (earlier zones win overlaps). --site defaults to the
bounding box of all zones; control is everything more than 15 px outside it.
"""
import argparse
import json

import numpy as np
import pandas as pd

PCT, BUF, MINVALID = 99.5, 15, 0.7


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stack")
    ap.add_argument("zones")
    ap.add_argument("out")
    ap.add_argument("--base-years", default="2018-2021")
    ap.add_argument("--site", default=None)
    ap.add_argument("--maps", default=None, help="save monthly disturbed masks here")
    a = ap.parse_args()

    d = np.load(a.stack)
    refl = d["refl"].astype(np.float32)
    dates = pd.to_datetime(d["dates"])
    T, B, H, W = refl.shape
    valid = (refl > 0).all(1)
    L = np.log(np.where(valid[:, None], refl, np.nan))

    zones = json.loads(a.zones)
    yy, xx = np.mgrid[:H, :W]
    inbox = lambda b, pad=0: (xx >= b[0] - pad) & (xx <= b[1] + pad) & (yy >= b[2] - pad) & (yy <= b[3] + pad)
    site = [int(v) for v in a.site.split(",")] if a.site else [
        min(z[0] for z in zones.values()), max(z[1] for z in zones.values()),
        min(z[2] for z in zones.values()), max(z[3] for z in zones.values())]
    site_m, ctrl = inbox(site), ~inbox(site, BUF)
    masks, taken = {}, np.zeros((H, W), bool)
    for name, b in zones.items():
        masks[name] = inbox(b) & ~taken
        taken |= masks[name]

    # 1. per-image, per-band control normalisation
    L -= np.nanmedian(L[:, :, ctrl], axis=2)[:, :, None, None]
    # 2. baseline
    y0, y1 = map(int, a.base_years.split("-"))
    bsel = (dates.year >= y0) & (dates.year <= y1) & dates.month.isin([6, 7, 8, 9])
    base = np.nanmedian(L[bsel], axis=0)
    print(f"baseline from {bsel.sum()} images")
    # 3. change magnitude
    dmag = np.sqrt(np.nanmean((L - base[None]) ** 2, axis=1))       # T, H, W
    # 4./5. monthly composites and threshold
    month = dates.to_period("M")
    rows, maps = [], {}
    for m in sorted(set(month)):
        sel = month == m
        with np.errstate(all="ignore"):
            comp = np.nanmedian(dmag[sel], axis=0)
        ok = np.isfinite(comp)
        vsite = ok[site_m].mean()
        row = {"month": str(m), "n_images": int(sel.sum()), "site_valid": round(float(vsite), 3)}
        if vsite < MINVALID or ok[ctrl].mean() < MINVALID:
            rows.append(row)
            continue
        thr = np.nanpercentile(comp[ctrl], PCT)
        dist = ok & (comp > thr)
        row["threshold"] = round(float(thr), 4)
        px_km2 = (20 / 1000) ** 2 * (1 if "res" not in d else 1)
        for name, mk in masks.items():
            n_ok = (ok & mk).sum()
            frac = dist[mk].sum() / max(n_ok, 1)
            row[f"{name}_km2"] = round(float((frac - (100 - PCT) / 100) * mk.sum() * px_km2), 4)
        row["control_check_km2"] = round(float((dist[ctrl].mean() - (100 - PCT) / 100) * site_m.sum() * px_km2), 4)
        rows.append(row)
        maps[str(m)] = dist & site_m
    df = pd.DataFrame(rows).set_index("month")
    zc = [c for c in df.columns if c.endswith("_km2") and c != "control_check_km2"]
    df["total_km2"] = df[zc].sum(1, min_count=1)
    df.to_csv(a.out)
    if a.maps:
        np.savez_compressed(a.maps, months=np.array(list(maps)), masks=np.stack(list(maps.values())),
                            site=np.array(site))
    print(df[["n_images", "site_valid", "total_km2"] + zc].to_string())


if __name__ == "__main__":
    main()
