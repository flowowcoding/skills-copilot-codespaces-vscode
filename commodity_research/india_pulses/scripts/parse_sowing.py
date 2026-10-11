"""Parse weekly kharif/rabi area-coverage (sowing progress) releases from PIB into a dated table.

Input: <pib>/releases.csv and <pib>/html/<prid>.html (fetch_pib_releases.py).
For each release, rows for Total Pulses, Tur/Arhar, Gram, Sugarcane, Cotton are located in the HTML
tables/text and the (current season, same date last year) areas in lakh ha are extracted. Column layouts
changed over time (2 to 5 numeric columns: normal area, current, last year, difference or %); the pair is
chosen by a consistency check (the next number equals current-last or the % change), else the first two.
"As on" date is read from the text when present; the public date is the PIB posting date.

Coverage is patchy (PIB carried few sowing releases in 2018-2022), so these numbers are published in
the signal dataset as context and are NOT used by the pre-registered model.

Output: ../data/sowing_progress.csv (prid, posted, season_type, as_on, crop, area_cur_lha, area_prev_lha)
Usage:  python parse_sowing.py --pib <scratch>/india/raw/pib --out ../data
"""
import argparse, re
import pandas as pd

LABELS = {"pulses": r"(?:Total\s+)?Pulses", "tur": r"(?:Tur|Arhar)(?:\s*\(Arhar\))?", "gram": r"Gram",
          "sugarcane": r"Sugarcane", "cotton": r"Cotton"}


def clean(h):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", h, flags=re.S)
    j = t.find("Posted On"); k = t.find("Release ID", j); t = t[j:k]
    t = re.sub(r"</t[dh]>", " | ", t); t = re.sub(r"</tr>|<br\s*/?>|</p>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t); t = re.sub(r"&nbsp;|&ndash;", " ", t); t = re.sub(r"&amp;", "&", t)
    return re.sub(r"[ \t\r]+", " ", t)


def pick(nums):
    for i in range(len(nums) - 1):
        c, l = nums[i], nums[i + 1]
        if l <= 0:
            continue
        if i + 2 < len(nums) and (abs(nums[i + 2] - (c - l)) < 0.06 or abs(abs(nums[i + 2]) - abs(100 * (c - l) / l)) < 0.06):
            return c, l
    return (nums[0], nums[1]) if len(nums) >= 2 else (None, None)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pib", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rel = pd.read_csv(f"{a.pib}/releases.csv")
    rel = rel[rel.kind == "sowing"]
    rows = []
    for r in rel.itertuples():
        try:
            t = clean(open(f"{a.pib}/html/{r.prid}.html", encoding="utf8", errors="ignore").read())
        except FileNotFoundError:
            continue
        season = "rabi" if re.search(r"\brabi\b", (r.title + t[:600]), re.I) else "kharif"
        m = re.search(r"as on\s*(\d{1,2})[\.\-/ ](\d{1,2}|[A-Za-z]+)[\.\-/ ,]*(\d{4})", t, re.I)
        as_on = None
        if m:
            try:
                as_on = pd.to_datetime(" ".join(m.groups()), dayfirst=True).date()
            except Exception:  # noqa
                as_on = None
        tab = t[t.find("|"):] if "|" in t else t
        for crop, lab in LABELS.items():
            mm = re.search(r"\|\s*" + lab + r"\s*\|((?:\s*-?[\d,]+\.?\d*\s*\|){2,6})", tab, re.I)
            if not mm:
                continue
            nums = [float(x.replace(",", "")) for x in re.findall(r"-?[\d,]+\.?\d*", mm.group(1))]
            c, l = pick(nums)
            if c is not None:
                rows.append(dict(prid=r.prid, posted=r.posted, season_type=season, as_on=as_on, crop=crop,
                                 area_cur_lha=c, area_prev_lha=l))
    d = pd.DataFrame(rows).sort_values(["posted", "crop"])
    d.to_csv(f"{a.out}/sowing_progress.csv", index=False)
    print(d.groupby(["season_type", "crop"]).size(), d.tail(10))


if __name__ == "__main__":
    main()
