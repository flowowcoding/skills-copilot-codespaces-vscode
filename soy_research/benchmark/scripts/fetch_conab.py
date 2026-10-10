#!/usr/bin/env python3
"""Download Conab "Acompanhamento da Safra Brasileira de Graos" per-levantamento
spreadsheets from gov.br and record each survey's release date.

Coverage: gov.br/conab hosts crop years 2019/20 onward (12 levantamentos each).
Older surveys (2005/06-2018/19) live only on the legacy portals
(www.conab.gov.br / antigo.conab.gov.br / portaldeinformacoes.conab.gov.br),
which were unreachable from this environment (connection reset / HTTP 503).

Release date logic (point-in-time critical):
  * Each folder page and its inner page carry "Publicado em <dd/mm/yyyy hhHmm>".
    For content migrated to gov.br these are sometimes the migration date
    (e.g. 17/09/2025) or carry a wrong year.
  * Levantamento k of crop year Y/Y+1 is published in month Oct+(k-1).
    We take the first candidate date that falls in that expected month; if a
    candidate has the right day/month but the wrong year we repair the year;
    otherwise date_quality='approx' and the date is the 10th of the expected
    month (Conab's usual release window is the 2nd week).

Output: <out>/conab_manifest.csv and the spreadsheets in <raw>/.

Usage:
    python fetch_conab.py --raw RAW_DIR --out OUT_DIR
"""
import argparse
import csv
import datetime as dt
import os
import re
import subprocess
import time

BASE = ("https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/"
        "safras/safra-de-graos/boletim-da-safra-de-graos")
INDEX = BASE + "/boletim-da-safra-de-graos"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")


def get(url, dest=None, tries=3):
    """Fetch url with curl (proxy-aware). Returns bytes or writes dest."""
    for i in range(tries):
        cmd = ["curl", "-sS", "-L", "-A", UA, "--max-time", "120", url]
        if dest:
            cmd += ["-o", dest]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode == 0:
            return r.stdout if not dest else dest
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"failed: {url}: {r.stderr[:200]}")


def list_folders():
    folders = set()
    for start in range(0, 600, 30):
        html = get(f"{INDEX}?b_start:int={start}").decode("utf8", "replace")
        new = set(re.findall(r"boletim-da-safra-de-graos/(\d+o-levantamento-safra-20\d\d-(?:20)?\d\d)", html))
        if not new - folders and start > 0:
            break
        folders |= new
    return sorted(folders)


def parse_folder(name):
    m = re.match(r"(\d+)o-levantamento-safra-(20\d\d)-(?:20)?(\d\d)", name)
    k, y = int(m.group(1)), int(m.group(2))
    return k, y


def expected_month(k, y):
    m = 10 + (k - 1)
    yy = y + (m - 1) // 12
    return yy, (m - 1) % 12 + 1


def pick_date(cands, k, y):
    ey, em = expected_month(k, y)
    for d in cands:
        if d.year == ey and d.month == em:
            return d, "page"
    for d in cands:
        if d.month == em and 1 <= d.day <= 28:
            return d.replace(year=ey), "page_year_repaired"
    return dt.datetime(ey, em, 10, 9, 0), "approx"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.raw, exist_ok=True)
    os.makedirs(a.out, exist_ok=True)
    rows = []
    for name in list_folders():
        k, y = parse_folder(name)
        crop = f"{y}/{str(y + 1)[2:]}"
        url = f"{BASE}/{name}"
        html = get(url).decode("utf8", "replace")
        inner = get(f"{url}/{name}").decode("utf8", "replace")
        cands = []
        for h in (inner, html):
            for s in re.findall(r'class="value">\s*(\d\d/\d\d/\d{4}) (\d\d)h(\d\d)', h):
                cands.append(dt.datetime.strptime(f"{s[0]} {s[1]}:{s[2]}", "%d/%m/%Y %H:%M"))
        rel, q = pick_date(cands, k, y)
        links = sorted(set(re.findall(r'href="(' + re.escape(url) + r'/[^"]+)"', html)))
        files = []
        for l in links:
            l = re.sub(r"/view$", "", l)
            tail = l.rsplit("/", 1)[-1].lower()
            if tail.endswith(".pdf") or tail == name or "apresentacao" in tail or "boletim" in tail or tail == "":
                continue
            if re.search(r"xls|tabela|previsao|planilha", tail):
                files.append(l)
        local = ""
        src = ""
        for f in files:
            dest = os.path.join(a.raw, f"conab_{y}-{y + 1}_L{k:02d}" + (".xlsx" if f.endswith("x") else ".xls"))
            get(f, dest)
            with open(dest, "rb") as fh:
                head = fh.read(8)
            if head.startswith(b"PK") or head.startswith(b"\xd0\xcf\x11\xe0"):
                if head.startswith(b"PK") and dest.endswith(".xls"):
                    os.rename(dest, dest + "x"); dest += "x"
                if head.startswith(b"\xd0\xcf") and dest.endswith(".xlsx"):
                    os.rename(dest, dest[:-1]); dest = dest[:-1]
                local, src = os.path.basename(dest), f
                break
            os.remove(dest)
        rows.append(dict(crop_year=crop, levantamento=k, release_datetime_brt=rel.strftime("%Y-%m-%d %H:%M"),
                         date_quality=q, page_url=url, file_url=src, local_file=local,
                         date_candidates=";".join(sorted({c.strftime('%Y-%m-%d %H:%M') for c in cands}))))
        print(crop, k, rel.date(), q, local or "NO FILE", flush=True)
    with open(os.path.join(a.out, "conab_manifest.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["crop_year"], r["levantamento"])))


if __name__ == "__main__":
    main()
