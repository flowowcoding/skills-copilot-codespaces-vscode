#!/usr/bin/env bash
# Rebuild the benchmark end to end. Usage: scripts/run_all.sh [RAW_WASDE_DIR]
# Downloads are untrusted data: they go to data/raw (Conab) or RAW_WASDE_DIR, and
# every reader runs with python -I.
set -euo pipefail
cd "$(dirname "$0")/.."
W=${1:-/tmp/soy_wasde_raw}
mkdir -p "$W/csv" "$W/txt" data/raw/conab data/interim data/pit data/prices results figures
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
# 1. Conab per-levantamento spreadsheets (gov.br, 2019/20+)
python3 -I scripts/fetch_conab.py --raw data/raw/conab --out data/interim
python3 -I scripts/parse_conab.py --manifest data/interim/conab_manifest.csv --raw data/raw/conab \
        --out data/interim --overrides data/reference/conab_release_date_overrides.csv
# 2. USDA WASDE: OCE historical CSVs (Apr-2010+) and ESMIS text reports (2005-2010)
curl -sS -L -A "$UA" https://usda.azureedge.us/historical-wasde-report-data-3 -o "$W/index.html"
grep -oE 'href="[^"]+\.(csv|zip)"' "$W/index.html" | sed 's/href="//;s/"$//;s#^https://www.usda.gov##' | sort -u |
  while read -r p; do f=$(basename "$p"); [ -s "$W/csv/$f" ] || curl -sS -L -A "$UA" "https://usda.azureedge.us$p" -o "$W/csv/$f"; done
for z in "$W"/csv/*.zip; do unzip -o -q "$z" -d "${z%.zip}"; done
for pg in 19 20 21 22 23 24 25 26; do
  curl -sS -L -A "$UA" "https://esmis.nal.usda.gov/publication/world-agricultural-supply-and-demand-estimates?page=$pg"
done | grep -oE 'href="/sites/default/release-files/[^"]+\.txt"' | sed 's/href="//;s/"$//' | grep -vi special | sort -u |
  while read -r p; do f=$(basename "$p"); [ -s "$W/txt/$f" ] || curl -sS -L -A "$UA" "https://esmis.nal.usda.gov$p" -o "$W/txt/$f"; done
python3 -I scripts/parse_wasde.py --csv-dir "$W/csv" --txt-dir "$W/txt" --out data/interim
# 3. IBGE LSPA vintages
python3 -I scripts/fetch_ibge_lspa.py --out data/interim
# 4. Prices
python3 -I scripts/fetch_prices.py --out data/prices
# 5. Tidy PIT dataset + finals, analysis, figures
python3 -I scripts/build_dataset.py --interim data/interim --out data/pit
(cd scripts && python3 analysis.py --data ../data/pit --prices ../data/prices --out ../results --figs ../figures)
