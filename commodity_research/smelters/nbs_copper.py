"""China monthly refined copper (electrolytic copper) output, NBS figures, rebuilt from public reposts.

NBS's own database (data.stats.gov.cn) refuses requests from this environment (HTTP 403, WAF
"UrlACL"), and NBS's monthly industrial-production press release lists only "ten non-ferrous
metals" and primary aluminium, not copper. Two public reposts of the NBS number are used:

1. gotohui.com "全国精炼铜(电解铜)产量(当月值)" (source: NBS) - visible without login up to 2020-08.
2. chinabaogao.com (观研天下) monthly data notes on refined copper output (source: NBS), crawled
   from its metallurgy data listing. A note gives some of: the month's value, its YoY change, the
   Jan-to-month cumulative value, and the same month one or two years earlier. Every one of these
   is kept, and the series is assembled in this order of preference:
     direct (month's value) > cum_diff (difference of two cumulative values) >
     ref (prior-year value quoted in a later note) > yoy_backfill (value / (1 + YoY)).

Usage:
    python nbs_copper.py OUT.csv [--pages 100] [--raw RAW.csv]

OUT columns: month, kt (thousand tonnes), method, published (date of the repost carrying the
figure; NBS itself publishes ~15th-17th of the following month, which is the date used in the
lead-time tests), source_url.
January and February are missing by construction: NBS publishes them only as a Jan-Feb total.
yoy_published_pct is NBS's own YoY ("comparable basis", which differs from the ratio of
published levels because the above-designated-size sample changes each year); yoy_level_pct is
the ratio of levels; yoy_pct = published where available, else level-based.
"""
import argparse, re, html, time, concurrent.futures as cf
import requests
import pandas as pd

UA = {"User-Agent": "Mozilla/5.0"}
GOTOHUI = "https://www.gotohui.com/ndata/show-985090"


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
    t = text(get(GOTOHUI))
    rows = re.findall(r"\d+ (\d{4}-\d{2}) (\d+\.\d+) (-?\d+\.\d+|--)", t)
    return [dict(month=m, kt=float(v) * 10, kind="direct", published=None, source_url=GOTOHUI) for m, v, y in rows]


def crawl_listing(pages):
    urls = ["https://data.chinabaogao.com/yejin"] + [f"https://data.chinabaogao.com/yejin/list_{i}.html" for i in range(2, pages + 1)]
    found = {}
    with cf.ThreadPoolExecutor(8) as ex:
        for h in ex.map(get, urls):
            for u, title in re.findall(r'href="([^"]+\.html)"[^>]*>([^<]{4,120})<', h):
                if "精炼铜" in title and "产量" in title and "年" in title and "全球" not in title and "-20" not in title:
                    found["https:" + u if u.startswith("//") else u] = title
    return found


NUM = r"(?:当期值|累计值|累计)?\s*(?:约为|为|约|达到|达|增至|降至)?\s*([\d.]+)\s*万吨"
P_MONTH = re.compile(r"(\d{4})年(\d{1,2})月(?:份)?(?:我国|全国|中国)?精炼铜(?:（电解铜）)?(?:行业规模以上企业)?产量" + NUM)
P_CUM = re.compile(r"(\d{4})年1-(\d{1,2})月(?:份)?(?:我国|全国|中国)?精炼铜(?:（电解铜）)?(?:行业规模以上企业)?产量" + NUM)
P_REF = re.compile(r"较(\d{4})年(\d{1,2})月(?:份)?的([\d.]+)万吨")
P_REF_PREV = re.compile(r"(\d{4})年(\d{1,2})月(?:份)?[^。]{0,60}?较上一年同期的([\d.]+)万吨")


def parse_article(url):
    t = text(get(url))
    pub = re.search(r"(20\d{2}-\d{2}-\d{2}) \d{2}:\d{2} 分享", t)
    i = t.find(" 分享")
    j = t.find("猜你喜欢")
    body = t[i:j] if i > 0 and j > i else ""
    pub = pub.group(1) if pub else None
    out = []
    for y, m, v in P_MONTH.findall(body):
        out.append(dict(month=f"{y}-{int(m):02d}", kt=float(v) * 10, kind="direct", published=pub, source_url=url))
    for y, m, v in P_CUM.findall(body):
        out.append(dict(month=f"{y}-{int(m):02d}", kt=float(v) * 10, kind="cum", published=pub, source_url=url))
    for y, m, v in P_REF.findall(body):
        out.append(dict(month=f"{y}-{int(m):02d}", kt=float(v) * 10, kind="ref", published=pub, source_url=url))
    for y, m, v in P_REF_PREV.findall(body):
        out.append(dict(month=f"{int(y) - 1}-{int(m):02d}", kt=float(v) * 10, kind="ref", published=pub, source_url=url))
    for y, m, d, p in re.findall(r"(\d{4})年(\d{1,2})月(?:份)?(?:我国|全国|中国)?精炼铜(?:（电解铜）)?产量[^。]{0,40}?同比(增长|下降|增速为)(?:约为|约)?\s*([\d.]+)%", body):
        out.append(dict(month=f"{y}-{int(m):02d}", kt=float(p) * (-1 if d == "下降" else 1), kind="yoy", published=pub, source_url=url))
    return out


def assemble(raw):
    raw = raw.copy()
    raw["pub_sort"] = raw.published.fillna("9999")
    pick = lambda k: raw[raw.kind == k].sort_values("pub_sort").drop_duplicates("month").set_index("month")
    direct, cum, ref, yoy = pick("direct"), pick("cum"), pick("ref"), pick("yoy")
    rows = {m: dict(kt=r.kt, method="direct", published=r.published, source_url=r.source_url) for m, r in direct.iterrows()}
    for m, r in cum.iterrows():
        y, mm = int(m[:4]), int(m[5:])
        if mm == 2 and m not in rows:
            rows[m] = dict(kt=r.kt / 2, method="janfeb_half", published=r.published, source_url=r.source_url)
        prev = f"{y}-{mm - 1:02d}"
        if mm > 2 and m not in rows and prev in cum.index:
            rows[m] = dict(kt=round(r.kt - cum.loc[prev, "kt"], 1), method="cum_diff", published=r.published, source_url=r.source_url)
    for m, r in ref.iterrows():
        if m not in rows:
            rows[m] = dict(kt=r.kt, method="ref", published=None, source_url=r.source_url)
    for _ in range(3):   # yoy back-fill, both directions
        for m, r in yoy.iterrows():
            prev = f"{int(m[:4]) - 1}{m[4:]}"
            if m in rows and prev not in rows:
                rows[prev] = dict(kt=round(rows[m]["kt"] / (1 + r.kt / 100), 1), method="yoy_backfill", published=None, source_url=r.source_url)
            if prev in rows and m not in rows:
                rows[m] = dict(kt=round(rows[prev]["kt"] * (1 + r.kt / 100), 1), method="yoy_forward", published=r.published, source_url=r.source_url)
    out = pd.DataFrame.from_dict(rows, orient="index").rename_axis("month").reset_index().sort_values("month")
    out = out[out.method != "janfeb_half"]          # Jan-Feb combined: not a monthly value
    lv = out.set_index("month").kt
    out["yoy_level_pct"] = [round(100 * (lv[m] / lv[f"{int(m[:4]) - 1}{m[4:]}"] - 1), 2) if f"{int(m[:4]) - 1}{m[4:]}" in lv.index else None for m in out.month]
    out["yoy_published_pct"] = out.month.map(yoy.kt)   # NBS 'comparable basis' YoY as reposted
    out["yoy_pct"] = out.yoy_published_pct.fillna(out.yoy_level_pct)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--pages", type=int, default=100)
    ap.add_argument("--raw", default=None, help="also save every parsed figure here")
    a = ap.parse_args()
    arts = crawl_listing(a.pages)
    print(len(arts), "chinabaogao notes")
    rows = []
    with cf.ThreadPoolExecutor(8) as ex:
        for r in ex.map(parse_article, list(arts)):
            rows += r
    raw = pd.DataFrame(rows + gotohui())
    if a.raw:
        raw.to_csv(a.raw, index=False)
    out = assemble(raw)
    out.to_csv(a.out, index=False)
    print(out.month.min(), out.month.max(), len(out), "months")
    print(out.method.value_counts().to_string())


if __name__ == "__main__":
    main()
