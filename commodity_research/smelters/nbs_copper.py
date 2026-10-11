"""China monthly refined copper (electrolytic copper) output, NBS figures, rebuilt from public reposts.

NBS's own database (data.stats.gov.cn) refuses requests from this environment (HTTP 403, WAF
"UrlACL"), and NBS's monthly industrial-production press release lists only "ten non-ferrous
metals" and primary aluminium, not copper. Two public reposts of the NBS number are used:

1. gotohui.com "全国精炼铜(电解铜)产量(当月值)" (source: NBS) - visible without login up to 2020-08.
2. chinabaogao.com (观研天下) monthly data notes "YYYY年M月我国精炼铜（电解铜）产量约为X万吨，同比增长Y%"
   (source: NBS), with the article's publication date. Crawled from the metallurgy data listing.
   Each note also gives the YoY change, so a missing month can be back-filled from the next year's note.

Usage:
    python nbs_copper.py OUT.csv [--pages 100]

Output columns: month, kt (thousand tonnes), yoy_pct (as published), published (repost date,
an upper bound on when the number was public; NBS itself releases ~15th-17th of the next month),
source_url, method (direct / backfill_from_yoy).
January is usually missing: NBS publishes January and February together.
"""
import argparse, re, html, time, concurrent.futures as cf
import requests
import pandas as pd

UA = {"User-Agent": "Mozilla/5.0"}


def get(url, tries=4):
    for k in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=40)
            if r.status_code == 200:
                return r.content.decode("utf-8", "ignore")
        except requests.RequestException:
            pass
        time.sleep(2 + 2 * k)
    return ""


def text(h):
    t = re.sub(r"<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", html.unescape(t))


def gotohui():
    t = text(get("https://www.gotohui.com/ndata/show-985090"))
    rows = re.findall(r"\d+ (\d{4}-\d{2}) (\d+\.\d+) (-?\d+\.\d+|--)", t)
    return [dict(month=m, kt=float(v) * 10, yoy_pct=None if y == "--" else float(y), published=None,
                 source_url="https://www.gotohui.com/ndata/show-985090", method="direct") for m, v, y in rows]


def crawl_listing(pages):
    urls = ["https://data.chinabaogao.com/yejin"] + [f"https://data.chinabaogao.com/yejin/list_{i}.html" for i in range(2, pages + 1)]
    found = {}
    with cf.ThreadPoolExecutor(8) as ex:
        for h in ex.map(get, urls):
            for u, title in re.findall(r'href="([^"]+\.html)"[^>]*>([^<]{4,120})<', h):
                if "精炼铜" in title and "产量" in title:
                    found["https:" + u if u.startswith("//") else u] = title
    return found


PAT = re.compile(r"(\d{4})年(\d{1,2})月(?:份)?我国精炼铜（电解铜）产量(?:约为|为|达|约)?\s*([\d.]+)\s*万吨[，,]\s*同比(增长|下降|减少|持平)\s*([\d.]*)\s*%?")


def parse_article(url):
    h = get(url)
    t = text(h)
    pub = re.search(r"(20\d{2}-\d{2}-\d{2}) \d{2}:\d{2} 分享", t)
    out = []
    for y, m, v, d, p in PAT.findall(t[:6000]):
        yoy = 0.0 if d == "持平" else float(p or 0) * (-1 if d in ("下降", "减少") else 1)
        out.append(dict(month=f"{int(y)}-{int(m):02d}", kt=float(v) * 10, yoy_pct=yoy,
                        published=pub.group(1) if pub else None, source_url=url, method="direct"))
    return out[:1]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--pages", type=int, default=100)
    a = ap.parse_args()
    arts = crawl_listing(a.pages)
    print(len(arts), "chinabaogao notes")
    rows = []
    with cf.ThreadPoolExecutor(8) as ex:
        for r in ex.map(parse_article, list(arts)):
            rows += r
    df = pd.DataFrame(rows + gotohui())
    df = df.sort_values(["month", "method", "published"]).drop_duplicates("month", keep="first")
    # back-fill a missing month from next year's YoY
    have = set(df.month)
    extra = []
    for r in df.itertuples():
        if r.yoy_pct is None or pd.isna(r.yoy_pct):
            continue
        prev = f"{int(r.month[:4]) - 1}{r.month[4:]}"
        if prev not in have:
            extra.append(dict(month=prev, kt=round(r.kt / (1 + r.yoy_pct / 100), 1), yoy_pct=None, published=None,
                              source_url=r.source_url, method="backfill_from_yoy"))
    df = pd.concat([df, pd.DataFrame(extra)]).sort_values("month")
    df.to_csv(a.out, index=False)
    print(df.month.min(), df.month.max(), len(df), "months;", (df.method == "backfill_from_yoy").sum(), "back-filled")


if __name__ == "__main__":
    main()
