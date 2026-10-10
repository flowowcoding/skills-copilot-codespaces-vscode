"""Extract quarterly 'Ore mined' (tonnes, 100% basis) for Los Bronces and Collahuasi from
Anglo American's quarterly production reports (PDF).

Usage:
    python anglo_ore_mined.py PDF_DIR URLS.txt OUT.csv

PDF_DIR holds qN-YYYY.pdf (N = quarter covered); URLS.txt lists "YYYY QN URL" per line.
Reports show the last five quarters, newest first. English reports use "Ore mined" with comma
thousands separators; the Chile-site Spanish copies use "Mineral extraído" with dots.
A quarter seen in several reports takes the value from the latest report.
Note: this is ORE mined, not total material (ore + waste); Anglo does not publish waste.
"""
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

pdir, urlf, out = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
urls = {f"q{l.split()[1][1]}-{l.split()[0]}": l.split()[2] for l in open(urlf) if l.strip()}
ANCHOR = {"Los Bronces": r"(Los Bronces mine|Mina Los Bronces)", "Collahuasi": r"(Collahuasi 100\s?% basis|100\s?% base (?:en )?Collahuasi|Collahuasi[^\n]{0,25}100\s?%)"}
rows = []
for f in sorted(pdir.glob("q?-20??.pdf")):
    t = subprocess.run(["pdftotext", "-layout", str(f), "-"], capture_output=True, text=True).stdout
    q = pd.Period(f"{f.stem[3:]}Q{f.stem[1]}", "Q")
    for mine, anc in ANCHOR.items():
        m = re.search(anc, t)
        if not m:
            print("missing", mine, f.stem); continue
        r = re.search(r"(Ore mined|Mineral extra.do)\s+(.*)", t[m.end():m.end() + 600])
        if not r:
            print("no ore row", mine, f.stem); continue
        nums = re.findall(r"\d{1,3}(?:[.,]\d{3})+", r.group(2))[:5]
        for k, v in enumerate(nums):
            rows.append(dict(quarter=str(q - k), mine=mine, ore_mined_t=int(re.sub(r"[.,]", "", v)),
                             report=f.stem, source=urls.get(f.stem, "")))
df = pd.DataFrame(rows)
df["rq"] = df.report.map(lambda s: s[3:] + s[1])
df = df.sort_values(["mine", "quarter", "rq"]).groupby(["mine", "quarter"]).last().reset_index().drop(columns="rq")
df.to_csv(out, index=False)
print(df.pivot(index="quarter", columns="mine", values="ore_mined_t").to_string())
