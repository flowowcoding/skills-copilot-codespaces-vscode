#!/usr/bin/env bash
# Rebuild the US corn/soy benchmark end to end.
# Usage: scripts/run_all.sh [RAW_DIR]   (raw downloads are untrusted data and stay outside the repo)
# Hand-collected inputs kept in the repo: data/consensus/consensus_raw.csv (one URL per value) and
# data/reference/farmdoc_decks.csv (which farmdoc decks were read).
set -euo pipefail
cd "$(dirname "$0")/.."
R=${1:-/tmp/us_bench_raw}
mkdir -p "$R"/{esmis,qs,wasde_csv/csv,farmdoc} data/{pit,interim,prices,consensus,reference} results figures
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
# 1. NASS / WASDE text reports from ESMIS (Cornell/NAL archive)
python3 -I scripts/fetch_nass_reports.py --out "$R/esmis" --from-year 2005 --months 1 5 6 7 8 9 10 11
python3 -I scripts/fetch_release_dates.py --out data/reference/other_release_dates.csv
python3 -I -c "import pandas as pd; m=pd.read_csv('$R/esmis/manifest.csv'); m.drop(columns=['local_path']).to_csv('data/reference/esmis_manifest.csv', index=False)"
# 2. Quick Stats bulk file (no API key needed) -> corn/soy national+state extract
QS=$(curl -sS -A "$UA" https://www.nass.usda.gov/datasets/ | grep -oE 'qs\.crops_[0-9]+\.txt\.gz' | head -1)
[ -s "$R/qs/$QS" ] || curl -sS -A "$UA" -o "$R/qs/$QS" "https://www.nass.usda.gov/datasets/$QS"
python3 -I scripts/extract_quickstats.py --bulk "$R/qs/$QS" --out data/interim/quickstats_corn_soy_extract.csv.gz
# 3. OCE historical WASDE CSVs (Apr-2010+)
curl -sS -L -A "$UA" https://usda.azureedge.us/historical-wasde-report-data-3 -o "$R/wasde_csv/index.html"
grep -oE 'href="[^"]+\.(csv|zip)"' "$R/wasde_csv/index.html" | sed 's/href="//;s/"$//;s#^https://www.usda.gov##' | sort -u |
  while read -r p; do f=$(basename "$p"); [ -s "$R/wasde_csv/csv/$f" ] || curl -sS -L -A "$UA" "https://usda.azureedge.us$p" -o "$R/wasde_csv/csv/$f"; done
for z in "$R"/wasde_csv/csv/*.zip; do unzip -o -q "$z" -d "${z%.zip}"; done
# 4. parse
python3 -I scripts/parse_nass.py --manifest "$R/esmis/manifest.csv" --out "$R/nass_parsed.csv"
python3 -I -c "import pandas as pd; pd.read_csv('$R/nass_parsed.csv').to_parquet('data/interim/nass_report_vintages.parquet', index=False)"
python3 -I scripts/parse_wasde_us.py --csv-dir "$R/wasde_csv/csv" --manifest "$R/esmis/manifest.csv" --out data/interim/wasde_us_vintages.csv
# 5. consensus: farmdoc decks (other consensus values are hand-collected in consensus_raw.csv)
tail -n +2 data/reference/farmdoc_decks.csv | while IFS=, read -r f d u b; do
  [ -s "$R/farmdoc/$f" ] || curl -sS -A "$UA" -o "$R/farmdoc/$f" "$u"; done
python3 -I scripts/extract_farmdoc_decks.py --decks "$R/farmdoc" --map data/reference/farmdoc_decks.csv --out data/consensus/farmdoc_extracted.csv
# 6. prices
python3 -I scripts/fetch_prices.py --out data/prices
# 7. PIT dataset, consensus table, analysis + figures
python3 -I scripts/build_dataset.py --nass "$R/nass_parsed.csv" --wasde data/interim/wasde_us_vintages.csv \
  --qs data/interim/quickstats_corn_soy_extract.csv.gz --dates data/reference/other_release_dates.csv \
  --consensus data/consensus/consensus_raw.csv --farmdoc data/consensus/farmdoc_extracted.csv --out data
(cd scripts && python3 -I analysis.py --data ../data --out ../results --figs ../figures > ../results/analysis_stdout.txt)
