#!/usr/bin/env bash
# Full pipeline, in order. WORK = scratch directory for raw downloads (not committed).
set -euo pipefail
WORK=${WORK:-/tmp/india}
cd "$(dirname "$0")"
# --- raw downloads (scratch) ---
python3 fetch_pib_index.py --out "$WORK/raw/pib"
python3 fetch_pib_releases.py --index "$WORK/raw/pib/pib_agri_index.csv" --out "$WORK/raw/pib"
curl -s "http://data.icrisat.org/dldAPI/apportioned/area-production-yield" -o "$WORK/raw/icrisat/apy_apportioned.json"
python3 fetch_chirps.py --work "$WORK"
# prices: Yahoo chart JSON for SB=F CT=F ZM=F ZS=F INR=X into $WORK/raw/prices/<sym>.json,
# WPI xls (eaindustry.nic.in) into $WORK/raw/wpi, StatCan 32100077 into $WORK/raw/statcan
# --- committed data ---
python3 build_districts.py --json "$WORK/raw/icrisat/apy_apportioned.json" --out ../data
python3 build_pixels.py --districts ../data/district_weights.csv --out "$WORK"
python3 fetch_power.py --districts ../data/district_weights.csv --work "$WORK"
python3 extract_modis.py --work "$WORK"
python3 build_weather.py --work "$WORK" --out ../data
python3 build_evi.py --work "$WORK" --out ../data
python3 build_benchmark.py --out ../data
python3 parse_sowing.py --pib "$WORK/raw/pib" --out ../data
python3 fetch_wasde.py --work "$WORK/raw/wasde" --out ../data
python3 build_prices.py --raw "$WORK/raw" --out ../data
# --- model + evaluation ---
python3 model.py --mode dev && python3 evaluate.py --mode dev
python3 model.py --mode final && python3 evaluate.py --mode final
python3 plot_mask.py --pixels "$WORK/pixels_crop.csv" --out ../figures/fig_mask_districts.png
python3 plot_benchmark.py --out ../figures/fig_ae_revisions.png
python3 plot_results.py
