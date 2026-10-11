"""Download the PIB releases that carry crop production estimates or sowing (area coverage) progress.

Reads pib_agri_index.csv (fetch_pib_index.py), selects titles that look like advance/final estimates of
major crops or kharif/rabi area-coverage progress, and saves each release page plus every attached
static.pib.gov.in PDF. The release timestamp ("Posted On: 16 FEB 2022 6:39PM") is the public date used
downstream.

Outputs: <out>/html/<prid>.html, <out>/pdf/<prid>_<n>.pdf, <out>/releases.csv (prid, kind, title, posted, pdfs)
Usage:  python fetch_pib_releases.py --index <scratch>/raw/pib/pib_agri_index.csv --out <scratch>/raw/pib
"""
import argparse, os, re, subprocess, time
from concurrent.futures import ThreadPoolExecutor
import pandas as pd

EST = r"advance estimate|advanced estimate|final estimate|foodgrain production|foodgrains production|record production of food|fourth estimates|production of kharif foodgrains|foodgrain output"
SOW = r"sowing|area coverage|area sown|crops sown|sown on|kharif area|rabi area|crop area sown|covered\s*under"
EXCL = r"horticult|livestock|milk|lok sabha|rajya sabha|msp|procure|insurance|pmfby"


def curl(url, fn):
    for k in range(5):
        r = subprocess.run(["curl", "-s", "-L", "-m", "120", "-A", "Mozilla/5.0", "-o", fn, "-w", "%{http_code}", url], capture_output=True, text=True)
        if r.stdout == "200" and os.path.getsize(fn) > 1000:
            return True
        time.sleep(3 * (k + 1))
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    d = pd.read_csv(a.index)
    t = d.title.str.lower()
    d["kind"] = None
    d.loc[t.str.contains(SOW) & ~t.str.contains(EXCL), "kind"] = "sowing"
    d.loc[t.str.contains(EST) & ~t.str.contains(EXCL), "kind"] = "estimate"
    d = d[d.kind.notna()].sort_values("prid")
    os.makedirs(f"{a.out}/html", exist_ok=True); os.makedirs(f"{a.out}/pdf", exist_ok=True)
    def one(r):
        fn = f"{a.out}/html/{r.prid}.html"
        if not os.path.exists(fn):
            curl(f"https://www.pib.gov.in/PressReleasePage.aspx?PRID={r.prid}", fn)
        h = open(fn, encoding="utf8", errors="ignore").read() if os.path.exists(fn) else ""
        m = re.search(r"Posted On:\s*([0-9]{1,2} [A-Z]{3} [0-9]{4})\s*([0-9:]+\s*[AP]M)?", h)
        posted = pd.to_datetime(m.group(1), format="%d %b %Y").date() if m else None
        pdfs = sorted(set(re.findall(r'(https?://static\.pib\.gov\.in/[^"\']+\.pdf)', h, flags=re.I)))
        got = []
        for i, u in enumerate(pdfs):
            pf = f"{a.out}/pdf/{r.prid}_{i}.pdf"
            if os.path.exists(pf) or curl(u.replace(" ", "%20"), pf):
                got.append(os.path.basename(pf))
        print(r.prid, r.kind, posted, len(pdfs), flush=True)
        return dict(prid=r.prid, kind=r.kind, title=r.title, posted=posted, posted_time=(m.group(2) if m else None),
                    pdf_urls=" | ".join(pdfs), pdf_files=" ".join(got))

    with ThreadPoolExecutor(6) as ex:
        rows = list(ex.map(one, d.itertuples()))
    pd.DataFrame(rows).to_csv(f"{a.out}/releases.csv", index=False)


if __name__ == "__main__":
    main()
