# Field-level corn and soybean yield model (Iowa + Illinois, 30 m Landsat / Sentinel-2)

(The pre-registration below was written before the holdout was evaluated and is not edited afterwards.
Results sections follow it.)

## Pre-registration (written 2026-10-11 04:58 UTC, before any holdout evaluation)

**Question.** The previous US model (Aqua MODIS 250 m EVI in high-share counties + gridMET, state ridge;
`soy_research/us/satellite/`) failed its 2022-25 holdout against USDA. Hypothesis: the gap to commercial
providers is field-level resolution and crop-specific phenology. Test: a county model built from 30 m
field-interior pixels, classified in season as corn or soybeans, with per-pixel seasonal curves.

**What was seen before this was written.** Development walk-forward results for 2016-2021 only (six feature
sets were tried on them: a 12-feature set, sets A-E; set D was frozen). Holdout yields were not used by any
model or evaluation run. Pixel/county features for 2022-2026 were computed (they contain no yield
information), and the in-season classifier's accuracy against CDL 2022-2025 was printed (a crop-map metric,
not a yield metric). Two pipeline decisions were taken after looking at observation counts only: Landsat 7 is
dropped from 2022 on (it would make 2023 a three-satellite year), and the primary model uses Landsat only
(see "Why Landsat-only is primary").

Frozen spec (sha256 prefixes: `common.py` 921b7721aa0e60bf, `extract_imagery.py` b38355b164a04740,
`extract_cdl_windows.py` 5b6f63bae65f2a74, `build_windows.py` 695e0542a7319922, `extract_weather_county.py`
75f79e540ebb53c9, `fetch_nass_county.py` 1a86cdce9386450d, `prep_benchmark.py` 9421b332a61dcc46,
`build_features.py` a9a0a5931fbbe8b2, `model.py` 0efafc9c4d44326c, `evaluate.py` b5fd2a631e54995b;
`features/sensor_offsets.csv` 71c569ea99191b69):

- **Unit.** County × crop (corn for grain, soybeans) × year × report (aug, sep), 193 IA/IL counties.
  Forecast date T = NASS Crop Production release date − 5 days.
- **Inputs at T.** Landsat 7/8/9 C2 L2 acquisitions with date + 8 d ≤ T (L7 only to 2021); Sentinel-2 L2A
  (secondary model) with date + 3 d ≤ T; gridMET days ≤ T − 3; CDL Y−1 and Y−2 for masks; CDL labels of years
  < Y for the classifier; NASS county yields of years < Y (published each February).
- **Pixels.** 4 windows of 1.44 km per county (2,304 points on a 60 m grid), field interiors from CDL Y−1
  (≥ 23 of 25 cells in the 5 × 5 block share the centre's corn/soy class). In-season LightGBM classifier
  (CDL Y−1/Y−2 class + smoothed NDVI every 10 days to the cutoff), trained on years < Y; corn if p ≥ 0.7,
  soy if p ≤ 0.3; rotation rule in 2013-14.
- **Curves.** Gaussian-kernel smoothing (σ 8 d) with two upper-envelope passes, daily grid DOY 100..cutoff.
- **Features (primary, Landsat-only).** County medians of `nirv_auc` (NIRv integral DOY 120..cutoff),
  `nirv_last` (mean NIRv last 15 days), `gu_doy` (first DOY NDVI ≥ 0.5), plus gridMET `prcp_jul`, `hdd_jul`
  (Aug) and `prcp_jul`, `prcp_aug`, `hdd_jul`, `hdd_aug` (Sep), each as the county's deviation from its own
  training-year mean, z-scored.
- **Target.** ln(county yield / county trend); county trend = state Theil-Sen trend through January finals
  Y−20..Y−1 × the county's median ratio to the state final over Y−10..Y−1.
- **Model.** Pooled ridge per crop × report, α from leave-one-year-out CV in {1, 3, 10, 30, 100, 300},
  trained on all county-years 2013..Y−1.
- **Aggregation.** State dev = county predictions weighted by county harvested acres of Y−1; IA+IL = state
  forecasts weighted by state harvested acres of Y−1; US proxy = US trend × exp(β × IA+IL dev), β = slope
  through the origin of US on IA+IL log deviations of finals, Y−20..Y−1.
- **Uncertainty.** Leave-one-year-out RMSE of the region's log deviation inside the training years.
- **Secondary variants (also reported).** `gbm` (LightGBM, fixed hyper-parameters), `wx` (weather only), `vi`
  (imagery only), and `fused` (same spec on Landsat + Sentinel-2 features, plus S2 red-edge `ndre_jul`).

Pre-registered holdout metrics (2022-2025, January final = truth; reported whatever they show):

1. Mean |error| (%) for IA and IL pooled ("states"), IA+IL and the US proxy, per crop × report: field model
   vs (a) trend, (b) previous MODIS model `us_sat_v1`, (c) USDA in that report, (d) trade consensus (US only).
2. County skill: pooled and within-year R² of detrended county anomalies (and correlations), vs trend (zero
   anomaly) and "USDA uniform" (every county gets USDA's state anomaly in that report).
3. Share of region-years in which the final moved from USDA toward the model (|model − USDA| > 1 %).

Success criteria (September date, both crops unless stated):

- **S1a** within-year county R² > 0 (positive out-of-sample spatial skill).
- **S1b** pooled county R² above the USDA-uniform baseline (field data add county information beyond USDA's
  state number).
- **S2** state (IA, IL pooled) mean |error| below trend and below the MODIS model.
- **S3 (closes the gap)** IA+IL mean |error| ≤ USDA's IA+IL mean |error|. "Narrows the gap" if the field
  model's state-level excess error over USDA is smaller than the MODIS model's.
- **S4** US proxy mean |error| below trend.

Development results at freeze (2016-2021, walk-forward from 2013; mean |error| %, field / trend / MODIS /
USDA): states corn Aug 5.2 / 5.8 / 4.4 / 4.9, Sep 4.7 / 5.8 / 4.6 / 4.3; soy Aug 4.1 / 8.2 / 4.1 / 3.4, Sep
4.7 / 8.2 / 3.4 / 2.6. County pooled R² (Sep) corn 0.05, soy 0.25 (USDA uniform 0.15, 0.43); within-year R²
0.09 and 0.15.

---
## What was built

A county yield model for **Iowa and Illinois** (193 counties, ≈30 % of US corn + soy area) driven by 30 m
field pixels, issued 5 days before each August and September USDA Crop Production report, 2016-2026,
walk-forward from 2013. Everything is free and point-in-time; scripts are CLIs with docstrings in `scripts/`.

## Data

| Input | Source | Use | Point-in-time rule |
|---|---|---|---|
| Landsat 7/8/9 Collection 2 Level-2 SR (30 m), QA_PIXEL cloud mask | Planetary Computer `landsat-c2-l2` (T1, ≤ 80 % cloud, DOY 100-255) | Primary curves / features | acquisition + 8 d ≤ T; L7 only to 2021 |
| Sentinel-2 L2A (B04, B8A, B05 at 20 m), SCL mask | PC `sentinel-2-l2a` (2017+, ≤ 80 % cloud, DOY 145-255) | Secondary (fused) model, red edge, classifier check | acquisition + 3 d ≤ T |
| USDA CDL 30 m | PC `usda-cdl` (2011-2021), NASS CropScape state files (2022-2025) | Field interiors (Y−1), rotation prior (Y−1, Y−2), classifier labels (< Y) | CDL Y used from Y+1 |
| gridMET daily pr, tmmx, tmmn, vpd (4 km) | northwestknowledge.net yearly netCDF, averaged per county | Weather features | day d usable on d + 3 |
| NASS county yields, harvested acres | Quick Stats bulk file (`qs.crops_20261010`) | Target (truth), county weights | year Y published Feb Y+1 |
| January finals, USDA Aug/Sep state + US forecasts, release dates, consensus | `soy_research/us/benchmark` via `soy_research/us/satellite/data` (`prep_benchmark.py`) | Truth, benchmarks | release timestamps |
| MODIS model forecasts (`us_sat_v1`) | `soy_research/us/satellite/signal/us_sat_signal_v1.csv` | Benchmark (b) | as published |

**Why not HLS.** PC's `hls2-l30`/`hls2-s30` start in 2020 (checked: no items before 2020) and LP DAAC needs an
Earthdata login, which would leave two training years. The two HLS ingredients were read from their own Level-2
products instead (no BRDF/bandpass normalisation; sensor offsets are removed empirically:
`features/sensor_offsets.csv`, median NDVI difference vs L8/L9 on same-point pairs ≤ 1 day apart, years ≤ 2021:
L7 +0.020, S2A/B +0.010; S2C gets the S2A/B mean).

**Why Landsat-only is primary.** Adding Sentinel-2 raises the clear-observation count from ~10 to ~23 per pixel
by the August date, but only from 2018 (2013-16 have no S2 on PC, 2017 little). Denser series shift the curve
metrics (2018 test: fused − Landsat-only = +0.01 to +0.04 in NDVI-based features, the size of a typical annual
anomaly), so a model trained on sparse years and applied to dense ones would read the density change as yield.
Landsat has two satellites every year (L7+L8 2013-21, L8+L9 2022+) and median 9-13 clear observations at the
August date and 10-17 at the September date in every year.

**Sample.** 4 windows of 1.44 km per county drawn inside ≥ 50 % corn+soy land (CDL 2015), 772 windows
(`figures/sample_map.png`); 2,304 points per county on a 60 m grid; per year ~200 k field-interior points, after
classification a median of **~1,000 field pixels per county** (corn ~540, soy ~400; 10-90 %: 680-1,320). Only
small windows around the points are read (COG range requests); ~1.5 GB of per-point values are kept in scratch,
nothing raw (≈526 k window × scene reads). 40 scene items failed after retries (≈0.2 % of 20 k; 37 Sentinel-2, 3 Landsat, all 2022-25; their windows are missing for that date).

## Method (details in the pre-registration and the script docstrings)

1. `build_windows.py` → `extract_cdl_windows.py` → `extract_imagery.py` (per source and year) →
   `extract_weather_county.py`, `fetch_nass_county.py`, `prep_benchmark.py`.
2. `build_features.py offsets | pixels | classify | county | weather`: per-pixel smoothed NDVI/NIRv curves to
   the cutoff (`figures/curves_2019.png`, `curves_2023.png` show corn greening ~2 weeks before soy), in-season
   classification (`figures/window_example.png`), county medians, county weather.
3. **Crop identification.** Walk-forward LightGBM on CDL Y−1/Y−2 + the curve to the cutoff. Accuracy against the
   same-year CDL (`features/classifier_accuracy.csv`), Landsat-only: 0.88 (Aug) / 0.90 (Sep) in 2015-21 and
   0.91 / 0.92 in 2022-25, vs 0.85-0.88 for the rotation rule; pixels kept (p ≥ 0.7 or ≤ 0.3) are 0.92-0.95
   right. With Sentinel-2: 0.93 / 0.95 in 2022-25. (The previous MODIS mask was ~70 % right.)
4. `model.py` (county ridge, walk-forward) → `evaluate.py` → `make_signal.py` → `plot_figures.py`.

## Results: holdout 2022-2025 (errors vs the January final)

Mean |error|, %. Field model = pre-registered primary (Landsat-only ridge). "States" pools IA and IL (8
state-years); IA+IL = acre-weighted (4); US = proxy (4). `results/accuracy_holdout_v1.csv`,
`figures/accuracy_holdout.png`, `figures/paths_{corn,soy}.png`.

| Crop | Report | Level | **Field** | Trend | MODIS v1 | USDA | Consensus | Weather-only | Fused (L+S2) |
|---|---|---|---|---|---|---|---|---|---|
| corn | Aug | states | **1.9** | 2.9 | 2.8 | 3.1 | – | 1.7 | 1.6 |
| corn | Aug | IA+IL | **1.4** | 2.9 | 2.5 | 1.9 | – | 1.0 | 0.8 |
| corn | Aug | US proxy | **3.4** | 2.0 | 1.4 | 1.5 | 1.3 | 3.1 | 4.1 |
| corn | Sep | states | **2.1** | 2.9 | 3.8 | 2.3 | – | 2.2 | 2.5 |
| corn | Sep | IA+IL | **2.0** | 2.9 | 2.9 | 2.3 | – | 1.5 | 2.5 |
| corn | Sep | US proxy | **3.4** | 2.0 | 2.3 | 1.2 | 1.2 | 2.7 | 4.1 |
| soy | Aug | states | **5.8** | 3.3 | 5.8 | 2.1 | – | 4.7 | 6.8 |
| soy | Aug | IA+IL | **5.8** | 2.0 | 5.4 | 1.8 | – | 4.7 | 6.9 |
| soy | Aug | US proxy | **7.1** | 1.3 | 5.0 | 2.9 | 2.1 | 6.2 | 7.9 |
| soy | Sep | states | **4.6** | 3.3 | 6.1 | 2.3 | – | 3.7 | 5.6 |
| soy | Sep | IA+IL | **4.6** | 2.0 | 6.1 | 2.3 | – | 3.8 | 5.8 |
| soy | Sep | US proxy | **6.1** | 1.3 | 5.2 | 2.2 | 2.6 | 5.5 | 6.9 |

Development (2016-21) for comparison, states, field / trend / MODIS / USDA: corn Aug 5.2 / 5.8 / 4.4 / 4.9,
Sep 4.7 / 5.8 / 4.6 / 4.3; soy Aug 4.1 / 8.2 / 4.1 / 3.4, Sep 4.7 / 8.2 / 3.4 / 2.6 (`results/accuracy_dev_v1.csv`).

### County skill (the field-level test; `results/county_skill_holdout_v1.csv`, `figures/county_scatter_holdout.png`)

R² of detrended county anomalies, ln(NASS county yield / county trend), 2022-25 (≈620 county-years per cell).

| Crop | Report | Field pooled R² | Field within-year R² (corr) | Weather-only pooled / within | Fused pooled / within | USDA-uniform pooled / within |
|---|---|---|---|---|---|---|
| corn | Aug | 0.06 | 0.06 (0.33) | 0.17 / 0.15 | 0.07 / 0.06 | −0.17 / −0.08 |
| corn | Sep | −0.01 | 0.05 (0.33) | 0.16 / 0.17 | 0.06 / 0.19 | −0.07 / 0.01 |
| soy | Aug | −0.37 | 0.15 (0.40) | −0.13 / 0.20 | −0.36 / 0.28 | 0.08 / 0.13 |
| soy | Sep | −0.01 | **0.36 (0.60)** | −0.01 / 0.21 | −0.18 / 0.36 | 0.10 / 0.19 |

- **Spatial skill is real but modest**: within a year the field model ranks counties with correlation 0.33
  (corn) to 0.60 (soy, September). For soybeans in September it explains 36 % of the cross-county variance,
  well above USDA's state numbers spread uniformly (19 %). For corn, the county weather alone does better than
  imagery + weather (within-year R² 0.17 vs 0.05); adding Sentinel-2 density lifts corn September to 0.19.
- **Pooled R² is near zero or negative** because the year-level component is biased (soy +2 to +10 % every
  holdout year). The county RMSE is 7 % (corn) and 8.5-10 % (soy); county yields carry a lot of noise that four
  1.4 km windows (~1 % of a county) cannot see.

### Pre-registered criteria (September)

| | Corn | Soy | Verdict |
|---|---|---|---|
| S1a within-year county R² > 0 | 0.05 ✔ | 0.36 ✔ | **pass** |
| S1b pooled county R² > USDA uniform | −0.01 vs −0.07 ✔ | −0.01 vs 0.10 ✘ | **fail** |
| S2 states below trend and MODIS | 2.1 vs 2.9 / 3.8 ✔ | 4.6 vs 3.3 / 6.1 ✘ | **fail** |
| S3 IA+IL ≤ USDA (closes the gap) | 2.0 vs 2.3 ✔ | 4.6 vs 2.3 ✘ | **fail** (corn yes, soy no) |
| S3' narrows the gap (state excess over USDA smaller than MODIS's) | −0.2 vs +1.5 pts ✔ | +2.2 vs +3.8 pts ✔ | **pass** |
| S4 US proxy below trend | 3.4 vs 2.0 ✘ | 6.1 vs 1.3 ✘ | **fail** |

Direction (final moved from USDA toward the model when they differed by > 1 %, `results/direction_holdout_v1.csv`):
corn 10/14 Aug, 9/10 Sep; soy 5/14 Aug, 4/14 Sep.

### Reading the results

- **Corn, state level: the field model beat USDA in 2022-25** (states 1.9 vs 3.1 % in August, 2.1 vs 2.3 % in
  September; IA+IL 1.4 vs 1.9 and 2.0 vs 2.3), and beat trend and the MODIS model, and the final moved toward it
  in 19 of 24 cases. But (i) USDA's state corn numbers were unusually poor in these years (its US numbers were
  1.2-1.5 %), (ii) the weather-only county model did as well or better (1.7 / 2.2 states, 1.0 / 1.5 IA+IL), so
  the gain comes from county-level modelling with county weather, not from the 30 m imagery, and (iii) 4 years.
- **Soybeans: failed**, for a diagnosable reason. The ridge intercept learns the mean anomaly of the training
  years, and 2014-2021 IA/IL soybean finals ran on average ~8 % above the 20-year Theil-Sen trend (−7 to +18 %);
  in 2022-25 the gap shrank to ~2 %, so every holdout forecast sits 2-10 % high. The spatial (within-year) skill is the best of all cells.
  A **post-hoc** diagnostic, not pre-registered and chosen after seeing this bias (`--no-intercept`,
  `signal/field_signal_v1_noint.csv`, `results/*_v1_noint.csv`), removes it: soy September states 2.0 %
  (USDA 2.3), IA+IL 1.9 % (USDA 2.3), county pooled R² 0.32. It can only be judged on future years.
- **US proxy: failed.** Scaling the IA+IL anomaly to the US (β ≈ 0.6-0.8) is a poor national estimate: in 2022-24
  the US finals came in below trend while IA/IL were near it. Two states are not the US.
- **Sentinel-2 (fused) variant**: better county ranking (corn Sep within-year 0.19, soy Aug 0.28) and the best
  August corn numbers (IA+IL 0.8 %), but worse September and soybean numbers; training on 2013-17 without S2
  makes it a moving target.

**Does field-level close the gap?** Partly. For corn it closed the state-level gap to USDA in 2022-25 and
roughly halved the MODIS model's error, but most of that comes from county weather; the imagery adds county
ranking skill (soy especially) rather than better state totals. For soybeans it narrowed the MODIS gap but did not
close it, because of a trend-level bias rather than a lack of signal. Nationally (US proxy), no. The free 30 m
stack is a better crop-ID and county-ranking tool than 250 m MODIS (classification 0.92 vs ~0.70; county
correlation 0.33-0.60), but it does not, on this evidence, beat USDA or the trade on the US numbers that move
prices.

## 2026 live forecasts (frozen spec, `field_v1_ridge`; bu/ac, ±1 sd)

| Crop | Report (forecast date) | IA | IL | IA+IL | US proxy | USDA IA / IL / US in that report | Consensus (US) |
|---|---|---|---|---|---|---|---|
| Corn | Aug (2026-08-07) | 212.8 ± 10.0 | 215.3 ± 11.9 | **214.0 ± 8.6** | 188.4 ± 4.7 | 216 / 212 / 180.7 | 182.4 |
| Corn | Sep (2026-09-06) | 218.5 ± 9.8 | 221.3 ± 12.2 | **219.8 ± 8.9** | 191.6 ± 4.8 | 219 / 209 / 178.5 | 178.1 |
| Soy | Aug (2026-08-07) | 64.3 ± 3.8 | 69.5 ± 4.4 | **67.0 ± 3.5** | 56.3 ± 2.2 | 62 / 67 / 52.7 | 52.9 |
| Soy | Sep (2026-09-06) | 65.9 ± 2.8 | 71.3 ± 4.5 | **68.7 ± 3.0** | 57.3 ± 1.9 | 64 / 66 / 52.8 | 52.4 |

- The model is above USDA for Illinois corn (+5.9 % in September) and both states' soybeans (+3 to +8 %). Given the
  holdout soybean bias (+2 to +10 %), the soybean numbers should be discounted; the post-hoc zero-intercept
  version says IA+IL soy 66.5 (Sep), corn 219.3. Weather-only says corn 215.4, soy 67.8 (Sep). The US proxy is not
  a usable national number (holdout 3-7 % errors).
- All rows, variants and the per-row USDA / consensus values are in `signal/field_level_signal.csv`. The January
  2027 Annual Summary and the February 2027 county estimates will score them.

## Commercial reference points (public claims, not independently verified)

| Provider | Claim | Source |
|---|---|---|
| Descartes Labs (now EarthDaily) | 2015 US corn yield forecast of Aug 6 within 1.9 % of the final; 2.5 % average error in historical back-tests; 2016 model error 2.37 % on Aug 4 (3.09 % for the 2015 model), "lower than USDA at every point in the season" in an 11-year back-test | [VentureBeat 2016](https://venturebeat.com/technology/descartes-labs-raises-5m-to-make-agricultural-predictions-with-deep-learning), [EarthDaily blog](https://earthdaily.com/blog/advancing-the-science-of-corn-forecasting) |
| Gro Intelligence (has since ceased operations) | August US corn estimate "usually within 4.5 bushels" of the final (~2.5 %), 2.5 bu (~1.4 %) in September; soybeans 1.7 bu (~3.3 %) Aug, 1.3 bu (~2.5 %) Sep | [DTN 2021](https://www.dtnpf.com/agriculture/web/ag/crops/article/2021/09/14/dtn-digital-yield-tour-corn-soybean) |
| EOSDA | Field-level "accuracy" 0.91 for maize and 0.86 for soy (WOFOST + Sentinel-2 LAI); metric undefined, no US county figures | [EOSDA product page](https://eos.com/products/crop-monitoring/custom-solutions/yield-prediction/) |
| Academic SCYM (Landsat, Lobell group) | 30 m maize yields explain 75 % of county yield variation in IL/IN/IA 2001-15 and 41-83 % in nine Midwest states (levels, not detrended anomalies, so not comparable with the anomaly R² above) | [Jin, Azzari & Lobell 2017](https://fse.fsi.stanford.edu/node/28600) |

For scale: the US-level USDA errors in the same holdout are 1.2-1.5 % (corn) and 2.2-2.9 % (soy); the
commercial claims for corn (1.4-2.5 %) are about USDA-level, not better. No provider publishes a pre-registered,
out-of-sample record. This free field-level model's US proxy (3.4 % corn) is worse than all of them; its IA+IL
corn numbers (1.4-2.0 %) are in their range, but over 4 years only.

## Caveats

- **Four holdout years** (8 state-years, 4 IA+IL and US points per cell). The corn "beats USDA" result is within
  the noise of 4 years; treat it as consistent with, not proof of, an edge.
- **Developer degrees of freedom.** Six feature sets were compared on 2016-21 before the freeze; the pre-2004
  trend history and two pipeline choices (Landsat-only primary; L7 dropped from 2022) were set from observation
  counts and development results, never from holdout yields.
- **County truth** is NASS's county estimates, which thin out in recent years (IA corn 73-79 counties in 2024-25
  vs 95-99 before); the county skill is measured on the counties NASS still publishes.
- **Spatial sample**: four 1.44 km windows per county (~1 % of the area, ~1,000 field pixels) — the main limit on
  county skill; a full-county read is ~25× the I/O.
- **Archive products**: Landsat C2 and S2 L2A on PC are reprocessed archives; the 8-day / 3-day latency rules are
  conservative for PC (2026 Landsat items appeared ~2 days after acquisition) but the values are final versions.
  gridMET is the reprocessed product. No BRDF normalisation; sensor offsets are additive NDVI shifts.
- **Classifier** uses the NDVI curve to the cutoff, so a badly stressed field could be mis-assigned between crops.
- **Post-pre-registration changes**: `model.py` gained the `--no-intercept` option (post-hoc diagnostic) and
  `make_signal.py`, `plot_figures.py` were added (presentation only); the v1 computation is unchanged.
  `features/classifier_accuracy.csv` was rebuilt from the pixel files (same numbers, all years).

## Files

- `scripts/` — `common.py`, `build_windows.py`, `extract_cdl_windows.py`, `extract_imagery.py`,
  `extract_weather_county.py`, `fetch_nass_county.py`, `prep_benchmark.py`, `build_features.py`, `model.py`,
  `evaluate.py`, `make_signal.py`, `plot_figures.py`, `plotstyle.py`.
- `signal/field_level_signal.csv` — deliverable (all regions, years 2016-2026, primary + variants, status column);
  `signal/field_signal_v1*.csv` raw model outputs; `signal/field_signal_dev.csv` the frozen spec on dev years.
- `features/` — `county_vi.csv` (Landsat-only county phenology metrics), `county_vi_fused.csv`,
  `county_weather.csv`, `county_predictions_v1*.csv` (county predicted vs actual anomalies),
  `classifier_accuracy.csv`, `sensor_offsets.csv`.
- `data/` — `windows.csv`, `county_yield.csv`, benchmark copies (`finals_jan.csv`, `usda_forecasts.csv`,
  `consensus.csv`, `release_dates.csv`, `state_harvested.csv`, `modis_v1.csv`).
- `results/` — accuracy, county skill, direction and per-region rows for dev and holdout (`_v1`, `_v1_fused`,
  `_v1_noint`).
- `figures/` — `sample_map.png`, `window_example.png`, `curves_2019.png`, `curves_2023.png`,
  `accuracy_{dev,holdout}.png`, `county_scatter_{dev,holdout}.png`, `paths_{corn,soy}.png`.

## Reproduce

```
S=<scratch>/field; G=<dir with cb_2020_us_county_500k.zip>
cd scripts
python fetch_nass_county.py [--raw <prefiltered Quick Stats tsv>]
python prep_benchmark.py
python build_windows.py --geo $G
python extract_cdl_windows.py --work $S
python extract_weather_county.py --work $S --geo $G
for y in $(seq 2013 2026); do python extract_imagery.py --work $S --source landsat --year $y; done   # ~15 min/yr
for y in $(seq 2017 2026); do python extract_imagery.py --work $S --source s2 --year $y --doy0 145; done  # ~30-60 min/yr
python build_features.py offsets --work $S
python build_features.py pixels --work $S --sources landsat --pixdir pix
python build_features.py classify --work $S && python build_features.py county --work $S
python build_features.py pixels --work $S --sources landsat,s2 --pixdir pix_fused
python build_features.py classify --work $S --pixdir pix_fused --tag _fused && python build_features.py county --work $S --pixdir pix_fused --tag _fused
python build_features.py weather --work $S
python model.py --years 2016-2026 --tag v1
python model.py --years 2016-2026 --tag v1_fused --models ridge,vi --vi-file county_vi_fused.csv --extra-vi ndre_jul
python model.py --years 2016-2026 --tag v1_noint --models ridge,wx,vi --no-intercept   # post-hoc
for t in v1 v1_fused v1_noint; do python evaluate.py --period dev --tag $t; python evaluate.py --period holdout --tag $t; done
python make_signal.py
python plot_figures.py sample --work $S --geo $G; python plot_figures.py curves --work $S --year 2019
python plot_figures.py results --period holdout; python plot_figures.py results --period dev
```
