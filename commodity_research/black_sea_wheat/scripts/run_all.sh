#!/usr/bin/env bash
# Rebuild the Black Sea wheat study end to end.  Usage: scripts/run_all.sh SCRATCH
# Raw downloads (WASDE files, IKAR pages, WorldCover/WorldCereal reads, MODIS pixel extracts, POWER
# CSVs) are untrusted data: they stay in SCRATCH, outside the repo, and every script that reads them runs
# with python -I (scripts that import a sibling module and read only repo files run without -I).
# Wall time ~3 h, dominated by the MODIS extraction (~3,300 tile-composites streamed from Planetary Computer).
set -euo pipefail
cd "$(dirname "$0")"
S=${1:?scratch dir}
mkdir -p "$S"/raw/{wasde/csv,wasde/txt,geo,ikar,power,finals,worldcereal}
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
# 1. USDA WASDE: OCE CSVs (Apr-2010+) and ESMIS text reports (2004-2010)
curl -sS -L -A "$UA" https://usda.azureedge.us/historical-wasde-report-data-3 -o "$S/raw/wasde/index.html"
grep -oE 'href="[^"]+\.(csv|zip)"' "$S/raw/wasde/index.html" | sed 's/href="//;s/"$//;s#^https://www.usda.gov##' | sort -u |
  while read -r p; do f=$(basename "$p"); [ -s "$S/raw/wasde/csv/$f" ] || curl -sS -L -A "$UA" "https://usda.azureedge.us$p" -o "$S/raw/wasde/csv/$f"; done
for z in "$S"/raw/wasde/csv/*.zip; do unzip -o -q "$z" -d "${z%.zip}"; done
for pg in 18 19 20 21 22 23 24 25 26 27; do
  curl -sS -L -A "$UA" "https://esmis.nal.usda.gov/publication/world-agricultural-supply-and-demand-estimates?page=$pg"
done | grep -oE 'href="/sites/default/release-files/[^"]+\.txt"' | sed 's/href="//;s/"$//' | grep -vi special | sort -u |
  while read -r p; do f=$(basename "$p"); [ -s "$S/raw/wasde/txt/$f" ] || curl -sS -L -A "$UA" "https://esmis.nal.usda.gov$p" -o "$S/raw/wasde/txt/$f"; done
python3 -I parse_wasde_wheat.py --csv-dir "$S/raw/wasde/csv" --txt-dir "$S/raw/wasde/txt" --out ../data/benchmark
python3 -I fetch_finals.py --raw "$S/raw/finals" --wasde ../data/benchmark/wasde_wheat_vintages.csv --out ../data/benchmark/final_outturns.csv
# 2. prices, private estimates
python3 -I fetch_prices.py --out ../data/prices
python3 -I fetch_private_estimates.py --raw "$S/raw/ikar" --out ../data/private
python3 -I clean_private_estimates.py      # uses data/private/manual_overrides.csv and manual_additions.csv
python3 benchmark_analysis.py > ../results/benchmark_stdout.txt
# 3. frame, masks, satellite, weather
curl -sS -o "$S/raw/geo/ne_admin1.zip" https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_1_states_provinces.zip
(cd "$S/raw/geo" && unzip -o -q ne_admin1.zip)
python3 -I build_frame.py --work "$S" --geo "$S/raw/geo" --out ../data/reference
curl -sS -L -o "$S/raw/worldcereal/aez.geojson" "https://zenodo.org/records/7875105/files/WorldCereal_AEZ.geojson?download=1"
python3 -I sample_worldcereal.py --pixels ../data/reference/pixels.csv --aez "$S/raw/worldcereal/aez.geojson" \
        --tmp "$S/raw/worldcereal" --out ../data/reference/worldcereal_2021_at_pixels.csv
python3 -I extract_modis.py --work "$S" --threads 6
python3 -I fetch_weather.py --pixels ../data/reference/pixels.csv --raw "$S/raw/power" --out ../data/features
python3 -I build_features.py --work "$S"
python3 plot_maps.py --geo "$S/raw/geo" --year 2021
# 4. models (pre-registered v1, weather-only v1_wx, first-coded v0_first), region indicators, evaluation
python3 -I model.py --tag v1 --years 2008-2026
python3 -I model.py --tag v1_wx --feats prcp_w,hdd_w,frost_w,prcp_s,hdd_s --years 2008-2026
python3 -I model.py --tag v0_first --spec v0 --years 2008-2026
python3 export_region_signal.py
for t in v1_wx v0_first v1; do python3 evaluate.py --tag $t --holdout > ../results/evaluate_stdout_${t}_holdout.txt; done
python3 build_manifest.py
