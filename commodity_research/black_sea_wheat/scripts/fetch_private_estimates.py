#!/usr/bin/env python3
"""Collect dated Russian wheat crop estimates by IKAR, SovEcon and the Russian agriculture
ministry (plus other quoted analysts) from the IKAR "IKAR in Mass Media" English press
archive (https://ikar.ru/1/en/press/), which reposts Reuters / Interfax / S&P / Bloomberg
items about the Russian grain market with their publication date (2011-2026).

Steps
  1. List pages  /1/en/press/?theme=all&period=all&sort=date&ipg=N  -> id, date (DD.MM.YY),
     title, source agency.
  2. Items whose title mentions wheat or grain together with crop/harvest/forecast/outlook/
     estimate/output are downloaded (raw HTML kept outside the repo).
  3. Sentence-level extraction: a sentence mentioning wheat + a forecasting word + a number
     of "million (metric) tonnes/tons" (or "mln t"); the agency is the named forecaster in the
     sentence (IKAR, SovEcon, ministry, Rusagrotrans, ProZerno, Rosstat, USDA, ...); the value is
     the number after "to"/"at"/"of"/"pegged at" (or the only number). Crop year: an explicit
     20xx in the sentence, else the publication year (Jul-Dec items with "next year" -> +1).
  4. Rows are flagged `auto`; obvious non-production rows (exports, total grain, other
     countries) are dropped by keywords. The output is a candidate table; the README states
     how it was reviewed. Publication date = news date (the estimate itself is usually
     announced the same or previous day).

Usage: python fetch_private_estimates.py --raw SCRATCH/raw/ikar --out data/private
Writes OUT/ikar_press_index.csv, OUT/private_estimates_candidates.csv
"""
import argparse
import html
import os
import re
import subprocess
import time

import pandas as pd

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
BASE = "https://ikar.ru"
AGENCIES = [("IKAR", r"\bIKAR\b|Institute for Agricultural Market Studies"), ("SovEcon", r"Sovecon|SovEcon"),
            ("MinAg", r"[Aa]griculture [Mm]inist|[Aa]griculture [Mm]inister|[Mm]inistry of [Aa]griculture|Patrushev|Lut\b|Tkachev|Fyodorov|Skrynnik|Kremlin|Putin|government"),
            ("Rusagrotrans", r"Rusagrotrans"), ("ProZerno", r"ProZerno|Pro Zerno"), ("Rosstat", r"Rosstat|statistics service"),
            ("USDA", r"\bUSDA\b|U\.S\. Department of Agriculture"), ("Grain Union", r"Grain Union|RZS|Zlochevsky"),
            ("IGC", r"International Grains Council|\bIGC\b"), ("Strategy Partners", r"Strategie Grains|Strategy Partners")]


def get(url, tries=4):
    for k in range(tries):
        r = subprocess.run(["curl", "-sS", "-m", "60", "-A", UA, url], capture_output=True)
        if r.returncode == 0 and len(r.stdout) > 1000:
            return r.stdout.decode("utf-8", "ignore")
        time.sleep(3 * (k + 1))
    return ""


def text_of(h):
    h = re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h)))


def list_pages(raw):
    rows = []
    for pg in range(1, 120):
        fn = os.path.join(raw, f"list_{pg:03d}.html")
        if not os.path.exists(fn):
            t = get(f"{BASE}/1/en/press/?theme=all&period=all&sort=date&tag=&ipg={pg}")
            open(fn, "w").write(t)
        t = open(fn).read()
        m = re.findall(r'class=small>(\d\d\.\d\d\.\d\d)</div>.*?href="/1/en/press/(\d+)/" class=title><b>(.*?)</b>.*?'
                       r'<p class=small>(.*?)</p>.*?title="Source"><a[^>]*>(.*?)</a>', t, re.S)
        if not m:
            break
        for d, i, ti, sn, src in m:
            rows.append(dict(id=int(i), date=pd.to_datetime(d, format="%d.%m.%y").date(), title=html.unescape(ti).strip(),
                             snippet=text_of(sn).strip(), agency_src=html.unescape(src).strip()))
    return pd.DataFrame(rows).drop_duplicates("id")


NUM = r"(\d{1,3}(?:[.,]\d{1,2})?)\s*(?:million|mln|mn|m)\.?\s*(?:metric\s+)?(?:tonnes|tons|t\b|mt\b)"
FORE = r"forecast|estimat|outlook|expect|harvest|crop|output|production|pegged|see[sn]?\b|predict|project"
BAD = r"export|grain crop|grain harvest|total grain|grains? (?:production|output|forecast)|barley|corn|maize|sunflower|ukrain|kazakh|world|global|stocks|carryover|import|sugar|soy|rapeseed|EU\b|European|Australia|India|China|U\.S\.|Argentin|Canada|Turkey|Egypt"


MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def dateline(body, posted):
    """Article date from the dateline ('MOSCOW, June 17 (Reuters)', 'July 7 (Bloomberg)', a leading
    ISO date); the archive posting date can lag the article by weeks for older items."""
    head = body[:400]
    m = re.search(r"\b(20\d\d)-(\d\d)-(\d\d)\b", head)
    if m:
        d = pd.Timestamp(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
        return (d, "dateline") if d <= posted else (posted, "posted")
    m = re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})\s*\((?:Bloomberg|Reuters|Interfax|Dow Jones|AFP|RIA|TASS|Platts)", head)
    if m:
        mo, dd = MONTHS[m.group(1)[:3].lower()], int(m.group(2))
        y = posted.year if mo <= posted.month else posted.year - 1
        try:
            d = pd.Timestamp(y, mo, dd).date()
        except ValueError:
            return posted, "posted"
        if (posted - d).days <= 120:
            return d, "dateline"
    return posted, "posted"


def extract(row, body):
    out = []
    pub, dsrc = dateline(body, row.date)
    for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\"'])", body):
        if not re.search(r"wheat", s, re.I) or not re.search(FORE, s, re.I):
            continue
        nums = list(re.finditer(NUM, s))
        if not nums:
            continue
        ag = [n for n, p in AGENCIES if re.search(p, s)]
        val = None
        for n in nums:
            pre = s[max(0, n.start() - 14):n.start()].lower()
            if re.search(r"\b(to|at|of|pegged at|be|reach|total|around|about|seen at|see|sees)\s*$", pre):
                val = n
        if val is None and len(nums) == 1 and not re.search(r"\bby\s*$", s[max(0, nums[0].start() - 5):nums[0].start()]):
            val = nums[0]
        if val is None:
            continue
        v = float(val.group(1).replace(",", "."))
        if not (20 <= v <= 110):
            continue
        yrs = re.findall(r"\b(20[0-3]\d)\b", s)
        cy = int(yrs[0]) if yrs else pub.year
        if not yrs and re.search(r"next year|next season|coming year", s):
            cy += 1
        out.append(dict(pub_date=pub, posted_date=row.date, date_source=dsrc, ikar_id=row.id, source_agency=row.agency_src, title=row.title,
                        forecaster=";".join(ag) if ag else "", crop_year=cy, value_mmt=v,
                        bad_keyword=bool(re.search(BAD, s)), sentence=s[:600],
                        url=f"{BASE}/1/en/press/{row.id}/"))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.raw, exist_ok=True); os.makedirs(a.out, exist_ok=True)
    idx = list_pages(a.raw)
    idx.to_csv(os.path.join(a.out, "ikar_press_index.csv"), index=False)
    print("index", len(idx), idx.date.min(), idx.date.max())
    sel = idx[idx.title.str.contains(r"wheat|grain|crop|harvest", case=False)
              & idx.title.str.contains(r"crop|harvest|forecast|outlook|estimat|output|production|frost|drought|weather|yield|cut|rais|lower", case=False)
              & ~idx.title.str.contains(r"[^\x00-\x7f]{3}", regex=True)]
    print("selected", len(sel))
    rows = []
    for r in sel.itertuples():
        fn = os.path.join(a.raw, f"item_{r.id}.html")
        if not os.path.exists(fn):
            open(fn, "w").write(get(f"{BASE}/1/en/press/{r.id}/"))
            time.sleep(0.3)
        t = text_of(open(fn).read())
        i = t.find(f"#{r.id} IKAR in Mass Media")
        body = t[i + len(f"#{r.id} IKAR in Mass Media"):] if i >= 0 else t
        j = body.find(" Source: ")
        body = body[:j] if j > 0 else body
        rows += extract(r, body)
    c = pd.DataFrame(rows).drop_duplicates(["pub_date", "forecaster", "value_mmt", "sentence"])
    c.to_csv(os.path.join(a.out, "private_estimates_candidates.csv"), index=False)
    print("candidates", len(c), "clean", (~c.bad_keyword).sum())


if __name__ == "__main__":
    main()
