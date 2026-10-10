"""Extract quarterly 'Material mined' (kt, 100% basis) for Escondida and Spence from BHP's
quarterly Operational Review filings (SEC Form 6-K).

Usage:
    python bhp_material_mined.py FILINGS_DIR IDS.txt OUT.csv

FILINGS_DIR holds the 6-K HTML files named YYYY-MM-DD.htm (filing date); IDS.txt lists
"YYYY-MM-DD ACCESSION:FILENAME" per line so the source URL can be written next to each value.
Each filing shows the last five quarters; a quarter seen in several filings takes the value
from the latest filing (restatements win).
"""
import html
import re
import sys
from pathlib import Path

import pandas as pd

fdir, ids, out = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
urls = {}
for line in open(ids):
    d, acc = line.split()
    a, f = acc.split(":")
    urls[d] = f"https://www.sec.gov/Archives/edgar/data/811809/{a.replace('-', '')}/{f}"
PAT = {"Escondida": r"Escondida, Chile.{0,80}?Material mined \(?kt\)?", "Spence": r"Spence\)?(?:, Chile)?.{0,60}?Material mined \(?kt\)?"}
rows = []
for f in sorted(fdir.glob("*.htm")):
    t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", f.read_text(errors="ignore"))))
    fq = pd.Period(f.stem, "Q") - 1                    # last quarter covered by this filing
    for mine, pat in PAT.items():
        m = re.search(pat, t)
        if not m:
            print("missing", mine, f.stem); continue
        nums = re.findall(r"\d{1,3}(?:,\d{3})+|\d+", t[m.end():m.end() + 200])[:5]
        for k, v in enumerate(nums):
            rows.append(dict(quarter=str(fq - 4 + k), mine=mine, material_mined_kt=int(v.replace(",", "")),
                             filing=f.stem, source=urls[f.stem]))
df = pd.DataFrame(rows).sort_values(["mine", "quarter", "filing"]).groupby(["mine", "quarter"]).last().reset_index()
df.to_csv(out, index=False)
print(df.pivot(index="quarter", columns="mine", values="material_mined_kt").to_string())
