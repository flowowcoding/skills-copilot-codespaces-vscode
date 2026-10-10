"""Greenbushes quarterly production from IGO's ASX quarterly activities reports.

Lists IGO announcements on asx.com.au for each year, downloads every quarterly activities
report PDF (after the ASX terms page), converts it with `pdftotext -layout` and parses the
Greenbushes rows of the TLEA operations table:

    Total Material Mined (Ore + Waste)  BCM
    Ore Mined                           t
    Spodumene Concentrate Production    t

Each table carries several quarters; a quarter takes its value from the LATEST report that
shows it (so restatements win), and the source URL of that report is kept. IGO's fiscal year
ends 30 June, so "1Q25" = Jul-Sep 2024. Values are 100% basis.

Usage:
    python igo_greenbushes.py WORKDIR OUT.csv [--years 2021-2026]

WORKDIR holds the downloaded PDFs/text (use a scratch dir).
"""
import argparse
import json
import os
import re
import subprocess

import pandas as pd

LIST = "https://www.asx.com.au/asx/v2/statistics/announcements.do?by=asxCode&asxCode=IGO&timeframe=Y&year={y}"
SHOW = "https://www.asx.com.au/asx/v2/statistics/displayAnnouncement.do?display=pdf&idsId={i}"
ROWS = {"total_material_bcm": r"Total Material Mined(?: \(Ore \+ Waste\))?\s+(?:BCM|‘000 bcm)",
        "ore_mined_t": r"Ore Mined\s+(?:\d\s+)?t\b",
        "spodumene_t": r"(?:Total )?Spodumene (?:Concentrate )?Production\s+(?:\d+\s+)?t\b"}


def curl(url, out=None):
    cmd = ["curl", "-sSL", "--retry", "3", url] + (["-o", out] if out else [])
    return subprocess.run(cmd, capture_output=True, text=out is None, check=True).stdout


def fiscal_to_end(q):
    """'2Q25' -> Timestamp('2024-12-31') (IGO fiscal year ends June)."""
    n, fy = int(q[0]), 2000 + int(q[2:])
    month = {1: 9, 2: 12, 3: 3, 4: 6}[n]
    year = fy - 1 if n <= 2 else fy
    return pd.Period(f"{year}-{month:02d}", "M").to_timestamp("M").normalize()


def parse(txt):
    """Return {quarter: {metric: value}} from one report's text.

    Finds a header line with 'Units' and quarter labels whose next ~15 lines contain the
    Greenbushes 'Total Material Mined' row. Header tokens include FY/YTD columns so values
    line up with the right quarter."""
    out = {}
    lines = txt.splitlines()
    for i, ln in enumerate(lines):
        hdr = re.findall(r"\b([1-4]Q\d\d|FY\d\d|YTD)\b", ln)
        if not (re.search(r"\bUnits?\b", ln) and any(re.match(r"[1-4]Q", h) for h in hdr)):
            continue
        block = "\n".join(lines[i + 1:i + 16])
        if not re.search(ROWS["total_material_bcm"], block, re.I):
            continue
        for key, pat in ROWS.items():
            m = re.search(pat + r"(.*)", block, re.I)
            if not m:
                continue
            nums = re.findall(r"-?\d[\d,]*(?:\.\d+)?|\*", m.group(1))
            for q, v in zip(hdr, nums):
                # IGO bought into Greenbushes in Jun 2021; earlier columns are prior-year comparatives
                if re.match(r"[1-4]Q", q) and v != "*" and int(q[2:]) >= 22:
                    out.setdefault(q, {})[key] = float(v.replace(",", ""))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workdir")
    ap.add_argument("out")
    ap.add_argument("--years", default="2021-2026")
    a = ap.parse_args()
    y0, y1 = map(int, a.years.split("-"))
    os.makedirs(a.workdir, exist_ok=True)
    reports = []
    for y in range(y0, y1 + 1):
        page = curl(LIST.format(y=y))
        for row in re.findall(r"(?s)<tr>(.*?)</tr>", page):
            title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", row)).strip()
            if not re.search(r"Quarterly (Activities )?Report", title) or re.search("Webcast|Presentation", title):
                continue
            d = re.search(r"(\d\d)/(\d\d)/(\d{4})", row)
            ids = re.search(r"idsId=(\d+)", row).group(1)
            reports.append((f"{d.group(3)}-{d.group(2)}-{d.group(1)}", ids, title))
    rows = {}
    for date, ids, title in sorted(reports):
        pdf = os.path.join(a.workdir, f"{date}_{ids}.pdf")
        meta = pdf[:-4] + ".json"
        if not os.path.exists(meta):
            url = re.search(r'name="pdfURL" value="([^"]+)"', curl(SHOW.format(i=ids))).group(1)
            curl(url, pdf)
            subprocess.run(["pdftotext", "-layout", pdf, pdf[:-4] + ".txt"], check=True)
            json.dump({"url": url, "title": title}, open(meta, "w"))
        url = json.load(open(meta))["url"]
        for q, vals in parse(open(pdf[:-4] + ".txt", errors="ignore").read()).items():
            rows.setdefault(q, {}).update(vals)
            rows[q].update(source_url=url, report_date=date)
    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index.name = "fiscal_quarter"
    df.insert(0, "quarter_end", [fiscal_to_end(q).date() for q in df.index])
    df = df.sort_values("quarter_end")
    df.to_csv(a.out)
    print(df.drop(columns=["source_url"]).to_string())


if __name__ == "__main__":
    main()
