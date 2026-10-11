"""List every Ministry of Agriculture & Farmers Welfare press release on PIB (2017 onward).

PIB's "All releases" page (https://www.pib.gov.in/allRel.aspx) is an ASP.NET form; this script posts
ministry=27 (Agriculture & FW), day=all, for each month, and records (PRID, title, year, month).
PIB's searchable archive starts in 2017; earlier releases are not reachable from this form.

Output: <out>/pib_agri_index.csv  (prid, title, year, month)
Usage:  python fetch_pib_index.py --out ../data/raw_index [--first 2017 --last 2026]
"""
import argparse, os, re, time
import pandas as pd, requests

U = "https://www.pib.gov.in/allRel.aspx?reg=3&lang=1"


def form(h):
    return {m.group(1): m.group(2) for m in re.finditer(r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"', h)}


def month_list(S, base, y, m, tries=5):
    for k in range(tries):
        try:
            f = dict(base)
            f.update({"ctl00$ContentPlaceHolder1$ddlMinistry": "27", "ctl00$ContentPlaceHolder1$ddlday": "0",
                      "ctl00$ContentPlaceHolder1$ddlMonth": str(m), "ctl00$ContentPlaceHolder1$ddlYear": str(y),
                      "__EVENTTARGET": "ctl00$ContentPlaceHolder1$ddlYear", "ctl00$Bar1$ddlregion": "3", "ctl00$Bar1$ddlLang": "1"})
            r = S.post(U, data=f, timeout=90).text
            return [(int(a), re.sub(r"\s+", " ", b).strip()) for a, b in re.findall(r"PRID=(\d+)[^>]*>\s*([^<]+)<", r)]
        except Exception as e:  # noqa
            print("retry", y, m, e); time.sleep(5 * (k + 1))
    return []


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--first", type=int, default=2017)
    ap.add_argument("--last", type=int, default=2026)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0"
    base = form(S.get(U, timeout=90).text)
    rows = []
    for y in range(a.first, a.last + 1):
        for m in range(1, 13):
            if (y, m) > (2026, 10):
                break
            L = month_list(S, base, y, m)
            rows += [dict(prid=p, title=t, year=y, month=m) for p, t in L]
            print(y, m, len(L), flush=True)
    pd.DataFrame(rows).drop_duplicates("prid").to_csv(f"{a.out}/pib_agri_index.csv", index=False)


if __name__ == "__main__":
    main()
