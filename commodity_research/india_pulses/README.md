# India pulses and monsoon crops: satellite + weather vs the Government of India's estimates

(The pre-registration below was written before the development run and before any holdout
evaluation. It has not been edited since. Results follow it.)

## Pre-registration (written 2026-10-11 02:45 UTC, before any model output was seen)

**Hypothesis under test.** Markets with weaker official data are easier to beat. The official data
here are the Ministry of Agriculture's advance estimates (AE) and final estimates for India.

**Targets** (why these: `FEASIBILITY.md`):

- gram (chickpea), priced with WPI Gram;
- tur (pigeon pea), priced with WPI Arhar;
- sugarcane, priced with ICE raw sugar SB=F, roll-adjusted.

**Held out.** Seasons 2022-23, 2023-24, 2024-25 and 2025-26 (season label Y ≥ 2023). In development
mode, `model.py` writes those rows only to `signal/.sealed_holdout_v1.csv`, and `evaluate.py --mode dev`
never reads that file.

- The revision test is scored on the last three seasons that have a final: 2022-23 to 2024-25.
  2025-26 has no final yet, so it is reported only as AE2 → AE3, provisionally.
- The price test is scored on the last three seasons: 2023-24 to 2025-26. 2022-23 is reported separately
  as an extra out-of-sample season.

**Disclosure.** Before writing this, I tabulated the benchmark itself, i.e. how much the official
estimates were revised from first estimate to final, for all seasons including the holdout
(`results/ae_revisions.csv`, needed for the "how weak is the benchmark" question). I also printed one
sanity check of pigeon-pea-weighted June–September CHIRPS rainfall for 2000–2026. No satellite index,
gap or price-model output had been computed for any season.

**Frozen spec.** sha256 prefixes:

| file | sha256 prefix |
|---|---|
| `model.py` | ad144985857b8f94 |
| `build_features.py` | bd2c7e18163dd358 |
| `evaluate.py` | ae7597f419eee4c8 |
| `build_evi.py` | 32786b8cfa050731 |
| `build_weather.py` | 188fcefe6562d217 |
| `build_benchmark.py` | f5c5db4d466cc32d |
| `build_districts.py` | 14a486ec41c68424 |
| `build_pixels.py` | 7e41417aa6ab6e4a |

Masks:

- Districts are the ICRISAT district-level database (311 districts on 1966 boundaries). The core
  districts for a crop are the smallest set covering 90% of its 2008–2017 area. Weights are each
  district's 2008–2017 mean area.
- Pixels are MODIS 500 m pixels on a 1.5 km grid within 25 km of each core district's centroid.
- A pixel counts as cropland if its EVI over Jul 2002 – Jun 2007 has p95 − p5 ≥ 0.20, p5 ≤ 0.25 and
  p95 ≥ 0.35.

Inputs, with the availability rule for each:

| input | source | available from |
|---|---|---|
| EVI | MODIS Aqua MYD13A1, pixel reliability 0–1 | composite end + 14 days |
| EVI anomaly | per pixel, against the same composite in the previous 8 seasons (at least 3) | same as EVI |
| rainfall | CHIRPS monthly | day 20 of the next month |
| soil moisture, heat | NASA POWER root-zone soil wetness and Tmax | day + 7 |

Windows and signs are fixed from the crop calendar. They are listed in `build_features.py` and
summarised here:

- **gram**: rain Aug–Mar; soil Oct 15 – Mar 31; EVI composites starting Nov 15 – Mar 15; heat is
  days with Tmax ≥ 35 °C in Feb–Mar.
- **tur**: rain Jun–Nov; soil Jul–Dec; EVI Aug–Dec.
- **cane**: rain Jun–Oct; soil Jun – Feb; EVI Aug – Jan.

Each component is z-scored against all earlier seasons at the same calendar offset (at least 5
needed). The index is the mean of the available z's, with signs +EVI, +rain, +soil, −heat.

Production model (`model.py`):

- **Trend.** An OLS line through the log of the last 10 finals that were public at the as-of date.
  Seasons before 2016-17 count as public from Feb 15 of the year after the season ended.
- **Fit.** log(final) − trend regressed on the index, at the same calendar offset, for seasons 2006 … Y−1
  that have a public final (at least 5 needed).
- **Prediction.** sat_pred = exp(trend + a + b·index).
- **Signal.** gap = log(sat_pred / latest official estimate).

**(a) Revision test.**

- Every AE with a public final. y = log(final / AE). gap is computed the day before that AE's release.
- Primary sample: each crop's first estimate (tur AE1, sugarcane AE1, gram AE2).
- Statistic: pooled OLS of y on gap with crop intercepts and season-clustered standard errors.
- Success needs all three of:
  1. in development, b > 0 with t ≥ 1.65;
  2. in the holdout, with b frozen from development, MAE(log AE + b·gap) < MAE(log AE) against the
     final;
  3. in the holdout, sign(gap) = sign(y) in more than half the crop-seasons.
- Secondary: all AE stages pooled.

**(b) Price test.**

- As-of dates are month-ends: gram Nov–Apr, tur Aug–Jan, sugarcane Jul–Jan.
- Target: the log change over the next h = 1, 2, 3 months.
  - WPI: month M → M+h.
  - SB=F: 21·h trading days.
- Baseline: y ~ official anomaly (log latest AE − trend, 0 if there is no AE yet) + momentum. Momentum is
  WPI M−4 → M−1, or 63 trading days for SB=F.
- Full model: baseline + the satellite anomaly (a + b·index).
- Fitting: walk-forward by season, with at least 5 training seasons.
- Trade: on the incremental forecast (full − baseline).
  - SB=F: long or short, 0.15% round-trip cost.
  - WPI: long-only, 2% + 1%/month carry, because physical pulses cannot be shorted.
- A target "works" in the holdout if ΔR²_oos > 0 at ≥ 2 of the 3 horizons **and** mean net P&L per
  trade > 0 at ≥ 2 of the 3 horizons.

All results are reported whatever they show.

---
## Changes after the pre-registration, made before the holdout run (written 2026-10-11 03:02 UTC)

Four changes were made after the pre-registration. Each was either a bug fix or a data or format
fix. None changes a window, threshold, regressor or success criterion.

1. **`evaluate.py`.** `sig.asof` / `r.asof` resolved to pandas' `DataFrame.asof` method rather than
   the column. I changed the code to `sig["asof"]`. Hash now `80be3e6f3e553ed0`.
2. **`build_benchmark.py`.** The pre-registered fit uses seasons 2006 … Y−1, and the trend needs ≥ 6
   earlier finals. The official time-series tables only start in 2003-04, so with them alone the fit
   could not start until 2010 and the first walk-forward price forecast would come in 2020. I added
   proxy finals for 1995-96 to 2002-03: ICRISAT district production sums, scaled by their median ratio
   to the official finals for 2003-04 to 2008-09. These rows are flagged `date_approx = 2`. Hash now
   `6d43ee04805215f4`.
3. **`build_evi.py` and `build_features.py`.** Output formatting only: the `end` column was dropped and
   values are written with 4 significant digits, so the committed CSV stays under 5 MB. Hashes now
   `078c6dd1efcd651d` and `97c24e5223248eec`.
4. **Disclosure.** While debugging change 1, a development run on *partial* MODIS data (composites to
   about 2019) printed development-period price metrics. It was the development period only, but it
   was seen before change 2.

## Development results (seasons ≤ 2021-22, walk-forward), frozen before the holdout run

Copied from `results/results_dev.json` at 03:01 UTC.

**(a) Revision test, first estimates.**

- n = 16, slope b = +0.068, season-clustered t = 0.65, Spearman +0.13, sign hit rate 50%.
- All stages: n = 62, b = −0.019 (t −0.31), hit rate 45%.
- **The development criterion (t ≥ 1.65) fails.**

**(b) Price tests.**

- **Pulses (WPI).** ΔR²_oos is negative at every horizon:
  - gram −0.76 / −1.08 / −1.43;
  - tur −0.06 / −0.07 / −0.07.
  - Long-only P&L net of costs is negative at every horizon.
  - The gram baseline itself is unstable (R²_oos ≈ −3). The official-anomaly regressor is zero for every
    season before 2016-17 (no AE vintages exist before then), so its coefficient rests on a handful
    of seasons.
- **SB=F.**
  - ΔR²_oos: +0.002 / −0.003 / −0.004.
  - Hit rate: 52% / 55% / 48%.
  - Mean net P&L per trade: +0.2% / −0.3% / −1.5%.

---
## Holdout results (run 2026-10-11 03:03 UTC with `model.py --mode final` and `evaluate.py --mode final`)

**Verdict: every pre-registered test failed. Nothing is tradeable after costs.**

### How weak is the benchmark?

GoI first estimate vs final, 2016-17 to 2024-25. Data: `results/ae_revisions.csv`; figure:
`figures/fig_ae_revisions.png`.

| crop (first estimate) | n | mean revision | mean \|revision\| | range |
|---|---|---|---|---|
| gram (AE2, Feb) | 9 | −1.9% | **4.3%** | −10.0% … +3.2% |
| tur (AE1, Sep–Nov) | 8 | −1.3% | **8.3%** | −18.8% … +9.9% |
| sugarcane (AE1) | 8 | **+4.4%** (first estimate is low 7 times in 8) | 4.9% | −1.9% … +12.5% |
| cotton (AE1) | 8 | −2.4% | 6.4% | −14.1% … +11.8% |

How the mean |revision| shrinks by stage:

| crop | AE1 | AE2 | AE3 | AE4 |
|---|---|---|---|---|
| tur | 8.3% | 7.7% | 3.4% | 2.8% |
| gram | – | 4.3% | 3.7% | 1.6% |
| sugarcane | 4.9% | 4.3% | 2.3% | 1.6% |

The official numbers really are noisy. The two large gram cuts both fell in holdout seasons:
2022-23 was cut 10.0% after the March 2023 rain, and 2023-24 was cut 9.2% after the El Niño
drought. Tur had a −18.8% revision in 2018-19 and −14.9% in 2022-23.

### Satellite estimate vs the official one

Mean |log error| against the final, at each crop's first estimate:

| period | satellite | GoI first estimate |
|---|---|---|
| development | 13.9% | 5.6% |
| holdout | 17.9% | 6.3% |

Holdout by crop:

| crop | satellite | GoI |
|---|---|---|
| gram | 18.5% | 8.0% |
| tur | 23.6% | 6.5% |
| sugarcane | 11.6% | 4.2% |

The free-data estimate is 2–3× *worse* than the "weak" official estimate.

### (a) Revision test (`results/revision_test_rows_final.csv`, `figures/fig_revision_gap.png`)

| sample | n dev | b (t, season-clustered) | dev hit | n holdout | holdout hit | MAE log AE → adjusted | holdout Spearman |
|---|---|---|---|---|---|---|---|
| first estimates (primary) | 16 | +0.068 (0.65) | 50% | 9 | 44% | 6.26% → 6.63% (worse) | −0.42 |
| all stages | 62 | −0.019 (−0.31) | 45% | 24 | 54% | 4.56% → 4.52% | −0.34 |

All three success criteria fail.

The worst miss was gram 2023-24. The day before AE2, the satellite was 10.8% *above* the official
number. The final came in 9.7% *below* it.

**2025-26 (provisional; no final yet).** The day before AE3, the satellite was above AE2:

| crop | satellite vs AE2 | AE3 revision |
|---|---|---|
| gram | +14.8% | +6.1% |
| tur | +12.6% | +4.0% |
| cane | +6.4% | −0.0% |

The direction matches in 2 of 3. That isn't evidence: the satellite estimate has been above the
official one in 7 of the 9 holdout first-estimate rows, which is bias, not skill.

### (b) Price tests (`results/price_test_rows_final.csv`, `figures/fig_sugar_pnl.png`)

Holdout = seasons 2023-24 to 2025-26. Values are at h = 1 / 2 / 3 months.

| target | ΔR²_oos | trades | hit rate | mean net P&L per trade | verdict |
|---|---|---|---|---|---|
| gram (WPI Gram, long-only) | −0.009 / −0.013 / −0.017 | 14 / 13 / 13 | 43 / 31 / 31% | −3.8 / −5.2 / −5.9% | fails |
| tur (WPI Arhar, long-only) | −0.051 / −0.037 / −0.040 | 9 / 13 / 13 | 33 / 54 / 54% | −5.4 / −4.4 / −7.9% | fails |
| sugar (SB=F, long/short) | +0.0003 / −0.0003 / −0.0042 | 21 each | 57 / 62 / 48% | +0.40 / −0.43 / +0.38% | fails: ΔR² > 0 at only 1 of 3; P&L ≈ 0 |

Development results at the same horizons:

- SB=F: ΔR² +0.002 / −0.003 / −0.004; P&L +0.2 / −0.3 / −1.5%.
- Pulses: negative throughout.

The extra out-of-sample season 2022-23 for SB=F: ΔR² +0.023 / +0.011 / +0.008 and P&L +1.4 / +0.4 / −1.0%,
from only 7 trades. The h = 2 and 3 trades overlap (one opens every month), so the cumulative curves
in the figure overstate the effective number of bets.

### Known shocks (`figures/fig_shocks_gram.png`, `figures/fig_shocks_tur.png`; signal file, month-end rows)

**The weather and EVI components see the shocks. The production model throws them away.**

| season | what happened | index (z) | satellite estimate vs final |
|---|---|---|---|
| 2014-15 gram | unseasonal March 2015 rain and hail | −0.9 in Dec, then +0.3 by Mar–Apr. The cool, wet March counts as low heat stress (heat z −1.9), and the index has no term for harvest-time rain damage | +36 to +47% |
| 2015-16 gram | drought | −1.5 (EVI z −2.4) | +17 to +64%, ending +29% (final 7.06) |
| 2015-16 tur | drought | −1.8 (EVI z −2.5) | +8 to +14% |
| 2018-19 tur | final 18.8% below AE1 | −1.3 by November | at AE1 the gap was −0.4%, i.e. no warning |
| 2021-22 gram | March 2022 heat wave | index +0.8 to +1.1. The heat term was −1.0 in Feb (cool) and −0.1 by Mar 31, so the heat wave barely shows in counts of Tmax ≥ 35 °C days over chickpea districts | −5 to −10%; the final was a record 13.5 Mt |
| 2022-23 gram | unseasonal rain in March 2023; final 10% below AE2 | +1.0 to +2.0 (wet soil reads as good) | +11 to +14%; gap at AE2 −1.2%, so no warning |
| 2023-24 tur | El Niño monsoon deficit | −1.0 to −1.3 (EVI z −2.1 in Sep 2023) | +14 to +45% |
| 2023-24 gram | El Niño monsoon deficit | rain z −1.1; EVI near 0 | +23 to +27% |

The fitted index slope b is only 0.01–0.09 log points per unit z. Production deviations from a
10-year log-linear trend are dominated by area. Gram area roughly doubled between 2015 and 2018
and has fallen since, and cane expanded with the ethanol push. So the regression shrinks the weather
signal towards zero, and the trend extrapolation sets the estimate.

A post-hoc check, not pre-registered, using the last in-season index against the year-on-year change
in the final:

| crop | Spearman | n |
|---|---|---|
| tur | +0.51 | 20 |
| sugarcane | +0.29 | 20 |
| gram | +0.22 | 20 |

So the index carries direction, especially for kharif tur. But its Spearman with the official
revision is 0.03 (n = 25) and −0.58 in the holdout.

## What this means for the hypothesis

India's official pulse estimates are weaker than the US and Brazil benchmarks studied elsewhere in
this repo (tur first-estimate errors of 8%, with misses up to 19%). Even so, free 500 m imagery plus
district centroids is not enough to beat them. The binding constraint is **area**: crop type and
sown area move pulse output more than yield weather does, and free MODIS without a crop map can't
measure them.

The price side is also unpromising:

- Pulse prices are set largely by policy: import duties and quotas, stock limits, MSP procurement.
- There is no liquid pulse futures market. NCDEX chana has been suspended since 2021.
- Sugar has a liquid market, but there the benchmark (ISMA) already uses satellite cane surveys.

A weaker benchmark is necessary for a free-data edge here, but it isn't sufficient.

## Caveats

- **Small n.** Crop-level advance-estimate vintages exist only from 2016-17, because pre-2017 PIB and
  desagri.gov.in are unreachable. That leaves 16 development and 9 holdout rows for the primary test.
  The pre-2016 finals have assumed public dates, and the 1995–2002 finals are ICRISAT-based proxies.
- **Masks.**
  - Districts are ICRISAT 1966-boundary centroids with a 25 km radius. Some centroids are wrong:
    Mayurbhanj sits in the sea and contributes 0.2% of pigeon-pea weight.
  - There is no crop-type map. Rabi EVI mixes chickpea with wheat and mustard, and kharif EVI mixes tur
    with soybean, cotton and others.
  - The cropland filter is EVI-based.
- **Weather inputs.** NASA POWER's near-real-time values are later replaced by MERRA-2, so recent-day
  inputs are slightly cleaner than what was visible live. CHIRPS final is used with a day-20 lag.
- **Prices.**
  - WPI uses final revised indices (provisional prints differ slightly). WPI is a monthly average,
    so the "entry" is not an executable price.
  - SB=F is Yahoo's spliced front month, with first-day-of-roll-month returns zeroed. The roll dates
    are approximate.
  - Cotton, soymeal, Saskatchewan lentils and WFP retail prices were surveyed but not tested.
- **Context-only data.**
  - Weekly sowing reports are parsed (`data/sowing_progress.csv`) but too patchy to model.
  - ISMA estimates are partial (`data/isma_estimates_partial.csv`).
  - USDA WASDE India cotton (`data/wasde_india_cotton_vintages.csv`) is unused, since cotton was not
    chosen.
- **Disclosures.** The benchmark revisions, including the holdout seasons, were tabulated before the
  pre-registration. A partial-data development run was seen before two fixes. Both are described in
  the changes section above.

## Sources

All sources are free. Each one was reached from this environment unless the table says otherwise.

| Data | Source | Used for | Point-in-time rule |
|---|---|---|---|
| GoI advance and final estimates, 2016-17 to 2025-26 (tur, gram, sugarcane, cotton) | PIB press releases of the Ministry of Agriculture & FW (`https://www.pib.gov.in/PressReleasePage.aspx?PRID=…`, PRIDs in `data/ae_vintages.csv`); attached time-series PDFs on static.pib.gov.in | Benchmark; revision test; official anomaly in the price model | PIB "Posted On" date. Two missing releases (2016-17 AE4, 2019-20 AE4) are dated to the first later release that shows them |
| Finals 2003-04 to 2015-16 | History columns of those time-series tables | Trend and model training | Assumed public on Feb 15, two calendar years after the season started |
| Finals 1995-96 to 2002-03 (proxy) | ICRISAT district sums scaled to the official level | Trend only | Same rule as above |
| Weekly kharif/rabi sowing (area coverage) | PIB releases (`data/sowing_progress.csv`, 245 crop-rows) | Context only. Too patchy to model: PIB has 0–3 releases a year in 2019, 2021 and 2022 | PIB posting date |
| ISMA sugar estimates | News reports (`data/isma_estimates_partial.csv`, 7 rows) | Context only | Reported date (month precision) |
| USDA WASDE India cotton, Apr 2010 onward (2,352 rows) | USDA OCE historical WASDE CSVs (usda.azureedge.us mirror) | Context only. India cotton is the only India crop in WASDE | Release date, 12:00 ET |
| District crop area 1966–2017 (311 districts, centroids) | ICRISAT District Level Database API (`data.icrisat.org/dldAPI/apportioned/area-production-yield`) | Masks and weights | Static (2008–17 mean area) |
| MODIS Aqua MYD13A1 v061 EVI + pixel reliability, 500 m, 16-day, Jul 2002 to Sep 2026 (4,296 tile-composites, 8 tiles) | Microsoft Planetary Computer STAC `modis-13A1-061` | Crop vigour | Composite end + 14 days |
| CHIRPS v2.0 monthly precipitation, 0.05°, Jan 2000 to Aug 2026 | data.chc.ucsb.edu | Rainfall | Day 20 of the next month |
| NASA POWER daily Tmax, root-zone soil wetness, 2001 to Oct 2026, 162 district centroids | power.larc.nasa.gov | Heat and soil moisture | Day + 7 |
| WPI Gram, Arhar, Masur, Sugar (2004-05 base spliced into 2011-12 base) | eaindustry.nic.in | Pulse price targets | About the 14th of the next month |
| ICE SB=F, CT=F, CBOT ZM=F, USD/INR daily | Yahoo Finance chart API | Sugar target; context | Close |
| Saskatchewan lentil and pea farm prices | Statistics Canada 32-10-0077-01 | Context | Monthly |
| WFP/DoCA retail prices | HDX `wfp-food-prices-for-india` | Feasibility check only | Monthly |

Not reachable from here, so they are gaps:

- **Daily mandi prices.** agmarknet.gov.in returns 403, data.gov.in drops the connection, eNAM needs a
  browser, and fcainfoweb.nic.in (DoCA) is behind a captcha.
- **NCDEX historical data.** Behind a bot-check.
- **MCX.** Returns 403.
- **Pre-2017 releases.** desagri.gov.in, the pre-2017 PIB archive and web.archive.org all drop the
  connection, so crop-level advance estimates before 2016-17 are missing.
- **IMD gridded rainfall.** Not tried; CHIRPS is used instead.
- **UPAg API.** Needs a login.

## Files

| path | contents |
|---|---|
| `FEASIBILITY.md` | survey of the tradeable and observable price targets, and why two were chosen |
| `scripts/` | CLI scripts with docstrings. `run_all.sh` gives the order |
| `data/ae_vintages.csv` | point-in-time GoI estimates (crop, season, stage, value, release date, PRID/URL) |
| `data/district_weights.csv`, `data/district_apy_icrisat.csv` | masks and weights; ICRISAT district APY |
| `data/evi_district_composite.csv` | district EVI and EVI anomaly per Aqua composite, with available_date |
| `data/chirps_district_monthly.csv`, `data/weather_crop_daily.csv` | rainfall and crop-weighted POWER weather |
| `data/prices_daily.csv`, `data/prices_monthly.csv` | SB=F/CT=F/ZM=F/INR (+ roll-adjusted); WPI pulses and sugar; Saskatchewan lentils and peas |
| `data/sowing_progress.csv`, `data/isma_estimates_partial.csv`, `data/wasde_india_cotton_vintages.csv` | context benchmarks |
| `signal/india_signal_v1.csv` | **the versioned point-in-time signal dataset**, 520 rows (described below) |
| `signal/india_signal_v1_dev.csv`, `signal/.sealed_holdout_v1.csv` | the development-run split, kept for audit |
| `results/` | `ae_revisions.csv`, revision and price test rows, `results_dev.json`, `results_final.json` |
| `figures/` | masks, benchmark revisions, revision-gap scatter, shock paths, SB=F P&L |

What each row of `signal/india_signal_v1.csv` holds:

- **Keys:** crop × season × as-of date (month-ends, plus the day before each GoI release).
- **Satellite side:** the z components, the index, the trend, the fit, and sat_pred with its 90% band.
- **Official side:** the latest official stage, value and date at the as-of date, and the gap.
- **Provenance:** model_version, code hashes and a created_utc timestamp.
