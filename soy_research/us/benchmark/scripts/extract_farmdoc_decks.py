#!/usr/bin/env python3
"""Extract pre-report average trade guesses from farmdoc (University of Illinois)
USDA-report webinar decks, e.g.
  https://farmdoc.illinois.edu/wp-content/uploads/2020/02/2020-08-12-FarmDoc-Webinar.pdf
Decks were found through the WordPress media API
  https://farmdoc.illinois.edu/wp-json/wp/v2/media?search=webinar&per_page=100

Two kinds of information are read (pdftotext, PDFs treated as untrusted data):
  1. "USDA = X / Avg. (Trade) Guess = Y" annotations on the yield and production
     charts of the report being discussed (corn/soy, yield/production).
  2. The bar charts "USDA August Corn Production Minus Average Trade Guess" and
     "USDA August Soybean Production Forecast Minus Average Trade Guess": bar labels are
     ordered by x position; the last bar is the deck's year. Implied consensus
     production = USDA August production - bar value (million bu).

Usage:
    python -I extract_farmdoc_decks.py --decks DIR --map deck_dates.csv --out OUT.csv
deck_dates.csv: file,report_date,url
"""
import argparse
import os
import re
import subprocess

import pandas as pd


def text(path, first=None, last=None, bbox=False):
    cmd = ["pdftotext"] + (["-f", str(first), "-l", str(last)] if first else []) + (
        ["-bbox"] if bbox else ["-layout"]) + [path, "-"]
    return subprocess.run(cmd, capture_output=True).stdout.decode("utf-8", "replace")


def annotations(path):
    """Pairs (crop, variable, usda, guess) from figure annotations."""
    out = []
    lines = text(path).splitlines()
    for i, ln in enumerate(lines):
        m = re.search(r"Figure\s*\d+\s*[:.]?\s*(U\.S\.\s+(Average\s+)?(Corn|Soybean)\s+(Average\s+)?(Yield|Production))", ln)
        if not m:
            continue
        crop = "corn" if m.group(3) == "Corn" else "soybeans"
        var = m.group(5).lower()
        col = m.start()
        # window: following lines until the next figure title in the same column
        win_lines = []
        for ln2 in lines[i + 1: i + 40]:
            f = [mm.start() for mm in re.finditer(r"Figure\s*\d", ln2)]
            if any(abs(p - col) < 20 for p in f):
                break
            win_lines.append(ln2[max(0, col - 5):] if col > 40 else ln2[: 140])
        win = " ".join(win_lines)
        u = re.search(r"USDA\s*=\s*([\d,]+\.?\d*)", win)
        g = re.search(r"Avg\.\s*(?:Trade\s*)?Guess\s*=\s*([\d,]+\.?\d*)", win)
        if u and g and abs(float(g.group(1).replace(",", "")) / float(u.group(1).replace(",", "")) - 1) < 0.15:
            out.append((crop, var, float(u.group(1).replace(",", "")), float(g.group(1).replace(",", ""))))
    return out


def bar_series(path):
    """August production minus average trade guess, by year (last bar = deck year)."""
    res = {}
    full = text(path)
    pages = full.split("\f")
    for pi, pg in enumerate(pages, start=1):
        for crop, rx in [("corn", r"USDA August Corn Production Minus Average Trade Guess"),
                         ("soybeans", r"USDA August Soybean Production Forecast Minus")]:
            if not re.search(rx, pg):
                continue
            bb = text(path, pi, pi, bbox=True)
            toks = re.findall(r'xMin="([\d.]+)" yMin="([\d.]+)" xMax="[\d.]+" yMax="[\d.]+">([^<]+)<', bb)
            toks = [(float(x), float(y), t) for x, y, t in toks if re.fullmatch(r"-?\d+", t)]
            if not toks:
                continue
            # axis tick labels sit at the far left; bars are to the right of the axis
            xs = sorted(x for x, _, _ in toks)
            axis_x = max(x for x, _, t in toks if x < xs[0] + 35)
            vals = [int(t) for x, _, t in sorted(toks) if x > axis_x + 15]
            res[crop] = vals
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--decks", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    m = pd.read_csv(a.map)
    rows = []
    for r in m.itertuples():
        p = os.path.join(a.decks, r.file)
        for crop, var, usda, guess in annotations(p):
            rows.append(dict(report_date=r.report_date, crop=crop, variable=var, avg=guess, usda_in_deck=usda,
                             poll="farmdoc average trade guess", source="farmdoc webinar deck", source_url=r.url,
                             note=""))
        if getattr(r, "bars", 0) == 1:
            yr = int(str(r.report_date)[:4])
            for crop, vals in bar_series(p).items():
                for k, v in enumerate(reversed(vals)):
                    rows.append(dict(report_date=f"{yr - k}-08", crop=crop, variable="production_surprise",
                                     avg=float(v), usda_in_deck=None, poll="farmdoc average trade guess",
                                     source="farmdoc webinar deck (bar chart)", source_url=r.url,
                                     note="USDA August production minus average trade guess, million bu"))
    df = pd.DataFrame(rows).drop_duplicates(["report_date", "crop", "variable", "source_url"])
    df.to_csv(a.out, index=False)
    print(df.groupby(["variable", "crop"]).size())


if __name__ == "__main__":
    main()
