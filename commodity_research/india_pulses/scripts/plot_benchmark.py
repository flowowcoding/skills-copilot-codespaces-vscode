"""Benchmark weakness figure: revision from the GoI first estimate to the final, by crop and season.

Usage: python plot_benchmark.py --results ../results --out ../figures/fig_ae_revisions.png
"""
import argparse
import numpy as np, pandas as pd
from plotstyle import setup, C, TEXT


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", default="../results"); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    plt = setup()
    o = pd.read_csv(f"{a.results}/ae_revisions.csv"); o = o[o.first_stage == 1]
    seasons = sorted(o.season.unique()); x = {s: i for i, s in enumerate(seasons)}
    fig, ax = plt.subplots(figsize=(8, 4.8))
    labs = {"gram": "gram (2nd AE → final)", "tur": "tur (1st AE → final)", "sugarcane": "sugarcane (1st AE → final)", "cotton": "cotton (1st AE → final)"}
    for k, crop in enumerate(["gram", "tur", "sugarcane", "cotton"]):
        d = o[o.crop == crop]
        ax.plot([x[s] + (k - 1.5) * 0.12 for s in d.season], d.rev_pct, "o", color=C[k], ms=6,
                label=f"{labs[crop]}: mean |rev| {d.rev_pct.abs().mean():.1f}%")
    ax.axhline(0, color=TEXT, lw=0.8)
    ax.set_xticks(range(len(seasons))); ax.set_xticklabels(seasons)
    ax.set_ylabel("final / first estimate − 1 (%)")
    ax.set_title("How far the Government of India's first estimate is from its final", color=TEXT)
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2)
    fig.tight_layout(); fig.savefig(a.out, dpi=130)


if __name__ == "__main__":
    main()
