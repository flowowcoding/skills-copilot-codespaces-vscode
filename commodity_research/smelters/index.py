"""Per-smelter activity index from the Sentinel-2 hot-pixel archive (frozen rules, see README).

For each smelter: furnace mask = pixels hot in >= 3 valid scenes and in <= 85% of valid scenes
during the mask period (default 2017-01-01..2024-12-31), dilated by one pixel. Per scene:
n_mask_hot and active (n_mask_hot >= 1). Valid scene: cloud_frac <= 0.2, valid_frac >= 0.95.

Usage:
    python index.py [--s2 data/s2] [--out data/index] [--mask-start 2017-01-01] [--mask-end 2024-12-31] [--tag ""]

Writes, per smelter, <out>/<id>_scenes.csv (scene-level) and one file <out>/monthly<tag>.csv
(smelter, month, n_valid, active_share, intensity) plus <out>/masks<tag>.npz.
"""
import argparse, glob, os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CLOUD_MAX, VALID_MIN = 0.2, 0.95
MIN_HITS, MAX_FREQ = 3, 0.85


def dilate(m):
    out = m.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            out |= np.roll(np.roll(m, dy, 0), dx, 1)
    return out


def smelter_index(csv_path, mask_start, mask_end):
    df = pd.read_csv(csv_path)
    z = np.load(csv_path.replace(".csv", "_hotpix.npz"))
    shp = tuple(z["shape"])
    df["valid"] = (df.cloud_frac <= CLOUD_MAX) & (df.valid_frac >= VALID_MIN)
    inper = df.valid & (df.date >= mask_start) & (df.date <= mask_end)
    nval = int(inper.sum())
    cnt = np.zeros(shp, np.int32)
    sel = inper.values[z["scene"]]
    np.add.at(cnt, (z["y"][sel], z["x"][sel]), 1)
    freq = cnt / max(nval, 1)
    core = (cnt >= MIN_HITS) & (freq <= MAX_FREQ)
    mask = dilate(core) if core.any() else core
    inmask = mask[z["y"], z["x"]]
    n = np.bincount(z["scene"][inmask], minlength=len(df))
    exc = np.bincount(z["scene"][inmask], weights=z["exc"][inmask], minlength=len(df))
    df["n_mask_hot"] = n
    df["exc_mask"] = exc.round(3)
    df["active"] = (n >= 1).astype(int)
    meta = dict(mask_px=int(mask.sum()), core_px=int(core.sum()), static_px=int(((cnt >= MIN_HITS) & (freq > MAX_FREQ)).sum()),
                n_valid_mask_period=nval)
    return df, mask, meta


def monthly(df):
    v = df[df.valid].copy()
    v["month"] = v.date.str[:7]
    g = v.groupby("month").agg(n_valid=("active", "size"), active_share=("active", "mean"), intensity=("n_mask_hot", "mean"))
    g = g[g.n_valid >= 2]
    return g.reset_index()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--s2", default=os.path.join(HERE, "data", "s2"))
    ap.add_argument("--out", default=os.path.join(HERE, "data", "index"))
    ap.add_argument("--mask-start", default="2017-01-01")
    ap.add_argument("--mask-end", default="2024-12-31")
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    allm, masks, metas = [], {}, []
    for f in sorted(glob.glob(os.path.join(a.s2, "*.csv"))):
        sid = os.path.basename(f)[:-4]
        df, mask, meta = smelter_index(f, a.mask_start, a.mask_end)
        cols = ["smelter", "date", "time", "orbit", "valid", "cloud_frac", "n_hot", "n_mask_hot", "exc_mask", "active"]
        if not a.tag:
            df[cols].to_csv(os.path.join(a.out, f"{sid}_scenes.csv"), index=False)
        m = monthly(df); m.insert(0, "smelter", sid); allm.append(m)
        masks[sid] = mask
        metas.append(dict(smelter=sid, **meta, n_scenes=len(df), n_valid=int(df.valid.sum())))
    pd.concat(allm).to_csv(os.path.join(a.out, f"monthly{a.tag}.csv"), index=False)
    np.savez_compressed(os.path.join(a.out, f"masks{a.tag}.npz"), **masks)
    meta = pd.DataFrame(metas)
    meta.to_csv(os.path.join(a.out, f"mask_summary{a.tag}.csv"), index=False)
    print(meta.to_string())


if __name__ == "__main__":
    main()
