"""Extract the USDA NASS October Florida all-orange forecast and implied prior-season final.

Source PDFs (one per season, released ~10-12 October):
  https://www.nass.usda.gov/Statistics_by_State/Florida/Publications/Citrus/Citrus_Forecast/<YYYY-YY>/cit10<YY>.pdf
The October report is the first official crop estimate of the season, so a hurricane in Aug-Sep
shows up as a lower October number versus the previous season's final; storms after the October
report (Wilma 2005, Milton 2024) show up as the gap between October and the season's final.

Output: data/usda_citrus_october.csv with season, oct_forecast_mbox, pct_vs_prior_final,
prior_final_mbox (implied), final_mbox (from the next season's report), final_vs_oct_pct.

Usage: python parse_usda_citrus.py --pdfdir DIR --out ../data/usda_citrus_october.csv
"""
import argparse
import glob
import os
import re
import subprocess

import pandas as pd

WORD = {"less": -1, "below": -1, "down": -1, "lower": -1, "more": 1, "above": 1, "up": 1, "higher": 1}


def parse(txt):
    t = re.sub(r"\s+", " ", txt)
    m = re.search(r"all oranges?\s+([\d.]+)\s+million boxes", t, re.I) or \
        re.search(r"all orange forecast released today .{0,80}? is ([\d.]+) million boxes", t, re.I)
    fc = float(m.group(1)) if m else None
    p = None
    for pat in [r"All Orange Production (Down|Up) ([\d.]+) Percent",
                r"all orange forecast released today .{0,120}? million boxes, ([\d.]+) percent (less|more|below|above|lower|higher)",
                r"all orange forecast released today .{0,120}? million boxes, (down|up) ([\d.]+) percent",
                r"([\d.]+) percent (less|more|below|above|lower|higher) than (?:the )?last season",
                r"(down|up) ([\d.]+) percent from (?:the )?last season",
                r"(\d+) million boxes or ([\d.]+) percent (less|more) than last season",
                r"([\d.]+) percent (less|more) than (?:the )?(?:\d{4}-\d{2,4} )?(?:season|last)"]:
        m = re.search(pat, t, re.I)
        if m:
            g = m.groups()
            if g[0].lower() in WORD:
                p = WORD[g[0].lower()] * float(g[1])
            elif len(g) == 3:
                p = WORD[g[2].lower()] * float(g[1])
            else:
                p = WORD[g[1].lower()] * float(g[0])
            break
    return fc, p


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdfdir", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = []
    for f in sorted(glob.glob(os.path.join(a.pdfdir, "cit10*.pdf"))):
        yy = int(os.path.basename(f)[5:7])
        txt = subprocess.run(["pdftotext", "-layout", f, "-"], capture_output=True, text=True).stdout
        fc, p = parse(txt)
        rows.append(dict(season=f"{2000 + yy}-{(yy + 1) % 100:02d}", oct_forecast_mbox=fc, pct_vs_prior_final=p,
                         source=f"https://www.nass.usda.gov/Statistics_by_State/Florida/Publications/Citrus/"
                                f"Citrus_Forecast/{2000 + yy}-{(yy + 1) % 100:02d}/cit10{yy:02d}.pdf"))
    d = pd.DataFrame(rows)
    d["prior_final_mbox"] = (d.oct_forecast_mbox / (1 + d.pct_vs_prior_final / 100)).round(1)
    nxt = dict(zip(d.season.str[:4].astype(int) - 1, d.prior_final_mbox))
    d["final_mbox"] = d.season.str[:4].astype(int).map(nxt)
    d["final_vs_oct_pct"] = (100 * (d.final_mbox / d.oct_forecast_mbox - 1)).round(1)
    d.to_csv(a.out, index=False)
    print(d.drop(columns="source").to_string())


if __name__ == "__main__":
    main()
