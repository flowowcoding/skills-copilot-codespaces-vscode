#!/usr/bin/env bash
# Rebuild everything. Usage: bash run_all.sh <scratch_dir>
# Raw downloads (Trase CSVs, geoBoundaries) are expected in <scratch>/raw/{trase,geob}; see README for URLs.
set -euo pipefail
S=${1:?scratch dir}
cd "$(dirname "$0")"
python3 fetch_prices.py
python3 build_mask.py --raw "$S/raw"
python3 fetch_chirps.py --mask ../data/mask_grid.csv --out ../data
python3 fetch_power.py --points ../data/sample_points.csv --scratch "$S" --out ../data
python3 extract_modis.py --mask ../data/mask_grid.csv --work "$S"
python3 build_features.py --work "$S"
python3 evaluate.py | tee ../results/evaluate_stdout.txt
python3 make_signal.py --version v1
python3 plot.py
