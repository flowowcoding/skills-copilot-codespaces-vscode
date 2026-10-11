"""Kennecott smelter quarterly output from Rio Tinto quarterly operations reviews (SEC EDGAR 6-K).

Parses the "Kennecott smelter & refinery" block of the production statistics appendix:
copper concentrates smelted ('000 t), copper anodes produced ('000 t) and refined copper ('000 t),
five quarters per report. The newest report carrying a quarter wins (restatements).

Usage:
    python rio_kennecott.py OUT.csv
"""
import re, sys, html, time
import requests
import pandas as pd

UA = {"User-Agent": "research contact@example.com"}
REPORT_Q = ['2017Q1', '2017Q2', '2017Q3', '2017Q4', '2018Q1', '2018Q2', '2018Q3', '2018Q4', '2019Q1', '2019Q2', '2019Q3', '2019Q4', '2020Q1', '2020Q3', '2020Q4', '2021Q1', '2021Q2', '2021Q3', '2021Q4', '2022Q1', '2022Q2', '2022Q3', '2022Q4', '2023Q1', '2023Q2', '2023Q3', '2023Q4', '2024Q1', '2024Q2', '2024Q3', '2024Q4', '2025Q3', '2025Q4', '2026Q1', '2026Q2']  # quarter each report covers (last column)
REPORTS = [  # quarterly operations reviews, EDGAR path, same order
    "0001003297-17-000088/exhibit99-1.htm", "0001003297-17-000254/e99-1.htm", "0001003297-17-000318/e99110-17.htm",
    "0001564590-18-000493/rio-ex991_9.htm", "0001564590-18-008388/rio-ex991_6.htm", "0001564590-18-016912/rio-ex991_6.htm",
    "0001564590-18-024330/rio-ex991_6.htm", "0001564590-19-000763/rio-ex991_7.htm", "0001564590-19-011673/rio-ex991_6.htm",
    "0001628280-19-008764/exh991_2qresults.htm", "0001628280-19-012307/a3qpr2019.htm", "0001628280-20-000383/a4qor2019_final.htm",
    "0001628280-20-005101/ex01qor20201.htm", "0001628280-20-014525/ex991_3qresults.htm", "0001628280-21-000532/a4q2020prodresults.htm",
    "0001628280-21-007200/ex01d20firstquarterresul.htm", "0001628280-21-013938/ex01secondquarterresults.htm",
    "0001628280-21-020079/ex1prodresults3q2021.htm", "0001628280-22-001004/ex1_4qorxresults.htm",
    "0001628280-22-009605/ex1form6k1qresults.htm", "0001628280-22-018966/ex1_2qpr2022.htm", "0001628280-22-026538/a3qor2022_final.htm",
    "0001628280-23-001086/ex1_4q22xresults.htm", "0001628280-23-012235/ex01q12023results.htm", "0001628280-23-025112/ex01q22023results.htm",
    "0001628280-23-034501/ex01rt3qor.htm", "0001628280-24-001327/ex01_4qresults.htm", "0001628280-24-016513/ex1_24q1results.htm",
    "0001628280-24-031937/ex1_2qresults16jul24.htm", "0001628280-24-042902/ex01_2024-3qor.htm",
    "0001628280-25-001683/ex1_4q2024resultsrelease.htm", "0000863064-25-000018/ex1results3q2025.htm",
    "0000863064-26-000006/ex1_2025-q4results.htm", "0000863064-26-000022/ex1d21rt1q26results.htm", "0000863064-26-000035/ex991results.htm",
]
ROWS = {"conc_smelted_kt": r"Copper concentrates smelted \(.000 tonnes\)", "anodes_kt": r"Copper anodes produced \(.000 tonnes\)(?: \([a-z]\))?",
        "refined_kt": r"(?:Production of refined metal: )?Copper \(.000 tonnes\)(?: \([a-z]\))?"}


def fetch(path):
    acc, fn = path.split("/")
    url = f"https://www.sec.gov/Archives/edgar/data/863064/{acc.replace('-', '')}/{fn}"
    for k in range(4):
        r = requests.get(url, headers=UA, timeout=60)
        if r.ok:
            t = re.sub(r"<[^>]+>", " ", r.content.decode("utf-8", "ignore"))
            return url, re.sub(r"\s+", " ", html.unescape(t))
        time.sleep(3)
    return url, ""


def parse(url, t, last_q):
    """The appendix shows five consecutive quarters ending with the report's own quarter."""
    out = []
    i = t.find("Kennecott smelter")
    if i < 0:
        return out
    p = pd.Period(last_q, freq="Q")
    quarters = [str(p - k) for k in range(4, -1, -1)]
    blk = t[i:i + 1500]
    rec = {}
    for k, pat in ROWS.items():
        m = re.search(pat + r"\s+((?:[\d,.]+\s+){5})", blk)
        if m:
            rec[k] = [float(v.replace(",", "")) for v in m.group(1).split()[:5]]
    for j, q in enumerate(quarters):
        out.append(dict(quarter=q, **{k: v[j] for k, v in rec.items()}, source_url=url))
    return out


def main():
    rows = []
    for q, p in zip(REPORT_Q, REPORTS):
        url, t = fetch(p)
        got = parse(url, t, q)
        print(p, len(got), got[-1] if got else "", file=sys.stderr)
        rows += got
        time.sleep(0.3)
    df = pd.DataFrame(rows)
    df = df.dropna(subset=["conc_smelted_kt"]).drop_duplicates("quarter", keep="last").sort_values("quarter")
    df.to_csv(sys.argv[1], index=False)
    print(df.to_string())


if __name__ == "__main__":
    main()
