# Satellite + weather yield signal for US corn and soybeans (point-in-time)

(The pre-registration below was written before the holdout was evaluated and is not edited afterwards.
Results sections follow it.)

## Pre-registration (written 2026-10-11 02:00 UTC, before any holdout evaluation)

Development years: forecasts for 2013–2021 (walk-forward, training from 2008). Holdout: 2022, 2023, 2024,
2025. Live out-of-sample: 2026 (scored against USDA's 2026 reports now, against the January 2027 final later).
In development mode `model.py` writes holdout rows only to `signal/.sealed_holdout_v1.csv`, which no
evaluation code reads.

**Disclosure (contamination).** At about 01:50 UTC a development run printed, by mistake, the national
*soybean* forecasts for 2022–2025 of an earlier version of the model (OLS trend, VI features only
de-meaned) next to the finals. Corn holdout numbers and all state numbers were not seen. After that two
changes were made, each motivated by development-period diagnostics: (1) the trend became a Theil–Sen line,
because the 2012 drought dragged the 20-year OLS trend 5–8 bu below the corn finals of 2014–2016; (2) the
EVI features are detrended rather than de-meaned, because canopy greenness rises over time with yields and a
de-meaned VI double-counts the trend. Both changes may have been nudged by what was seen. For transparency
the pre-fix version is scored on the holdout too (`v0_prefix`, below), and the soybean holdout results of
v1 should be read with that caveat.

Frozen spec (sha256 prefixes: `model.py` e9d5e1ff4d02e076, `build_features.py` 68477f7ccbb2d0d4,
`extract_hls.py` 3d672a282f02cb09, `build_sample.py` da1bb43bf31de7d4, `extract_cdl.py` 99b2bebabdb20d68,
`extract_modis.py` be1e3d4a714ef148, `extract_weather.py` 96d3fd0d871e3654, `evaluate.py` e29d45f8723cd046):

- **Unit.** State (IA IL NE MN IN OH SD ND KS MO WI MI) × crop (corn for grain, soybeans) × year × report
  (August, September). Forecast date = actual NASS Crop Production release date − 5 days.
- **Inputs at the forecast date T.** Aqua MYD13Q1 EVI composites starting DOY 169, 185, 201, 217 whose end
  date + 14 days ≤ T (Aug: 169 and 185; Sep: 169–217); gridMET days ≤ T − 3. Missing Aqua composites are
  filled with HLS EVI calibrated to MODIS (state intercepts + common slope, fitted on earlier years only).
- **Drift guard.** If, for the forecast year, mean(Aqua − calibrated HLS) EVI over the composites in use
  exceeds 0.02 in absolute value, the year's Aqua values are replaced by calibrated HLS.
- **Masks.** Previous two CDLs, rotation rule (corn after soy or after corn-corn; soy after corn or
  soy-soy), pixel in mask if ≥ 60 % of its 9 × 9 CDL cells are predicted for the crop. Equal pixel weights.
- **Features.** `evi_int` (mean detrended EVI anomaly over the composites in use), `evi_peak` (detrended max
  EVI over them), `prcp_ja` (Jul 1 – T−3 precipitation / training mean − 1), `hdd30` (Jul 1 – T−3 sum of
  max(Tmax − 30 °C, 0) minus training mean). VI trends: state intercepts + pooled slope, training years only.
- **Target.** ln(January final / trend), trend = Theil–Sen line through the January finals Y−20 … Y−1.
- **Model.** Pooled ridge over the 12 states, separate per crop × report, features z-scored on the training
  set, α = 3, unpenalised intercept, trained on 2008 … Y−1; weather-only ridge if a state has no VI.
- **Uncertainty.** Leave-one-year-out RMSE within training (state; and for the national aggregate).
- **US.** US trend × exp(Σ w_s dev_s), w_s = June-Acreage harvested area × trend yield share of the US
  (rest of the US at trend).

Pre-registered holdout metrics (reported whatever they show):

1. US yield mean |error| (%) vs the January final, per crop and report: satellite vs (a) trend, (b) USDA's
   forecast in that report, (c) the trade consensus for that report.
2. State yield mean |error| (%), pooled, vs trend and USDA.
3. Gap test: (final − USDA) regressed on (satellite − USDA) in log %, states pooled and US, year-clustered
   t; sign hit rate when |gap| > 3 %. Per year: the satellite-minus-USDA and satellite-minus-consensus gaps
   and whether the final moved toward the satellite.
4. Trading: hit rate of sign(satellite − consensus) against sign(USDA − consensus), and the report-day
   return of shorting (long) new-crop futures (benchmark ETF/contract series) when the satellite is above
   (below) the consensus, net of 0.6 ¢/bu.
5. Secondary, also pre-registered: the weather-only variant (`v1_wx`, features `prcp_ja,hdd30`), to show
   what the satellite adds to weather.

Success criteria fixed in advance: (a) the satellite US error is below the trend error at the September date
for both crops in the holdout; (b) the state gap slope in (3) is positive with t > 2; (c) the trading hit
rate in (4) is above the base rate (share of reports with USDA above consensus).

---
## What this is

A satellite-plus-weather estimate of corn and soybean yield for the 12 main US states and the US, issued
5 days before each August and September USDA Crop Production report, 2013–2026, using only data public at the
forecast date. It asks whether free imagery sees the US yield before USDA and the trade do. The benchmark
side (USDA vintages, consensus, report-day returns) is in `../benchmark/` and is used here, not duplicated.

## Data (all free; checked on Planetary Computer STAC, no auth)

| Input | Source | Use | Point-in-time rule |
|---|---|---|---|
| **Aqua** MYD13Q1 v061 EVI/NDVI, 250 m, 16-day, pixel reliability | PC `modis-13Q1-061` | Crop condition | composite end + 14 d |
| Terra MOD13Q1 (tile h11v04, DOY 193) | PC | Drift check only | — |
| HLS v2 L30/S30 (30 m, read at 240 m overviews) | PC `hls2-l30`, `hls2-s30` (2020+) | Fill for missing Aqua composites; drift guard | window end + 14 d |
| USDA CDL 30 m, 2008–2021 | PC `usda-cdl` (ends 2021) | Masks | CDL Y used from year Y+1 |
| USDA CDL 2022–2025 | NASS CropScape state files | Masks | same |
| gridMET daily pr, tmmx, 4 km | northwestknowledge.net (PC copy ends 2020) | Precipitation, heat degree days | day d usable on d + 3 |
| NASS Quick Stats bulk file | nass.usda.gov/datasets | County acres (sample), pre-2004 finals, fallbacks | — |
| Benchmark PIT dataset, consensus, events | `../benchmark/` (`prep_benchmark.py`) | Release dates, January finals (truth), USDA Aug/Sep state + US forecasts, June Acreage, consensus, report-day returns | release timestamps |

**Aqua vs Terra.** Aqua was chosen: (1) Terra's overpass drift since ~2022 broke the Brazil model (via LST);
(2) Aqua composites are phased 8 days later, so the latest *published* composite at an early-August
forecast date ends ~1 week later than Terra's. LST is not used at all (the Brazil no-LST variant did much
better). Drift was tested directly (`plot_drift.py`, `figures/fig_drift.png`, `results/drift_check.csv`):
Terra−Aqua EVI on tile h11v04 stays inside its 2003–21 ±2 sd band through 2026 (2020–26 mean +0.018 vs
+0.007 before: a mild rise, within noise). Aqua minus calibrated HLS is within ±0.015 in 2020–2025 but
**+0.026 in 2026** (+0.03 at the Aug composites), so in 2026 both MODIS sensors read greener than HLS — the
signature of the late-life orbit drift. The pre-registered drift guard therefore swapped Aqua for
calibrated HLS for the September 2026 forecast (it never triggered in 2022–2025).

**Archive gaps.** PC has no MODIS 13Q1/13A1 (Terra or Aqua, nor 09A1/15A2H/11A2/43A4) from 2025-06-26
onward until 2026, and Aqua 2026 lacks the composites starting DOY 137–169 and 233. Those composites
(2025: 185, 201, 217; 2026: 169) are HLS-calibrated fills: MODIS = a_state + b·HLS, fitted on earlier
years (R² 0.91–0.96, residual sd 0.025 EVI at state level — about the size of a typical inter-annual
anomaly, so 2025 state features are noisy; nationally the noise averages down). ERA5 (PC ends 2024),
Daymet/gridMET on PC (end 2020) and TerraClimate were not used.

**Years.** Aqua pixel series 2002–2026 (composites DOY 137–249); CDL 2008–2025; gridMET 2003–2026;
training from 2008; walk-forward forecasts 2013–2026 (9 development years, 4 holdout, 2026 live).

## Sample and masks

- **Candidate sample** (`build_sample.py`, `figures/sample_map.png`): counties with 2006–10 NASS corn+soy
  planted share ≥ 30 % of land (or each state's top 25 counties with share ≥ 10 %) — 557 counties holding
  85 % of 12-state corn+soy acres; 5,000 MODIS 250 m cells per state, drawn in proportion to county acres.
  The map shows the Red River Valley, eastern SD/NE, southern MN, IA, IL, IN, western OH, northern MO and the
  bootheel, NE Kansas plus irrigated pockets, southern WI and southern MI/the Thumb.
- **Year-Y masks** (`build_features.py`, `figures/mask_map_2024.png`, `features/mask_summary.csv`): predicted
  crop per 30 m CDL cell from CDL Y−1 and Y−2 (corn after soy or corn-corn; soy after corn or soy-soy);
  a pixel enters if ≥ 60 % of its 9×9 cells are predicted for the crop. 12.0–14.5k corn and 10.8–13.6k soy
  pixels a year (~500–1,450 per state per crop). Ex-post check against CDL Y: 65–71 % of masked cells are
  the predicted crop (cell rotation accuracy 68–77 %), i.e. the "corn mask" is ~70 % corn, ~25 % soy.
  2008 (same-year CDL) and 2009 (Y−1 only) are training-only exceptions.

## Signal dataset

`signal/us_sat_signal_v1.csv` (pre-registered model; 728 rows = 14 years × 2 reports × 2 crops × 13
regions). Columns: `forecast_date`, `data_cutoff_date` (latest VI composite end or weather day used),
`vi_cutoff_date`, `weather_cutoff_date`, `release_date`, `report` (aug/sep), `crop`, `year`, `region`
(state or US), `predicted_yield` (bu/ac), `uncertainty` (1 sd, bu/ac), `trend_yield`, `pred_dev_log`,
`model` (full / weather_only / aggregate), `vi_source` (MYD, HLS-cal, HLS-cal-driftguard), features and
coefficients, `model_version` (`us_sat_v1`), `usda_yield_at_release` and `gap_sat_usda_pct` (USDA's number
in that report, public only at release), `consensus_yield` and `gap_sat_cons_pct` (US rows; trade average
before the release), `final_yield_expost` (evaluation only). Variants: `_v1_wx` (weather only),
`_v1_noguard` (no drift guard; differs only in 2026), `_v0_prefix` (pre-fix spec, see disclosure).

Feature files: `features/modis_state.csv` (crop × state × composite EVI/NDVI with `available_date` and
source), `features/weather_state_daily.csv`, `features/asof_features.csv` (the model features at each
forecast date), `features/hls_*.csv`, `features/mask_summary.csv`.

## Results (holdout 2022–2025; errors vs the January final)

Mean |error|, %. Cells: **satellite / trend / USDA (that report) / consensus**. Dev = 2013–2021.

| Level | Report | Dev | **Holdout** |
|---|---|---|---|
| US corn | Aug | 3.8 / 2.8 / 2.1 / 2.1 | **1.4** / 1.9 / 1.5 / 1.3 |
| US corn | Sep | 3.0 / 2.8 / 1.6 / 1.8 | **2.3** / 1.9 / 1.2 / 1.2 |
| US soy | Aug | 5.1 / 4.9 / 3.0 / 3.6 | **5.0** / 3.1 / 2.9 / 2.1 |
| US soy | Sep | 3.5 / 4.9 / 2.5 / 2.8 | **5.2** / 3.1 / 2.2 / 2.6 |
| States corn | Aug | 6.3 / 6.8 / 4.1 | **4.8** / 5.1 / 3.7 |
| States corn | Sep | 5.7 / 6.8 / 3.7 | **4.2** / 5.1 / 3.3 |
| States soy | Aug | 7.0 / 7.6 / 5.2 | **9.5** / 8.1 / 6.7 |
| States soy | Sep | 5.7 / 7.6 / 4.0 | **8.8** / 8.1 / 4.9 |

(`results/accuracy_v1.csv`, `figures/fig_accuracy_v1.png`, `figures/fig_us_paths_{corn,soy}_v1.png`.)

**Pre-registered success criteria: FAILED.**
(a) US Sep error below trend for both crops: no (corn 2.3 vs 1.9, soy 5.2 vs 3.1).
(b) State gap slope > 0 with t > 2: no (Aug +0.08, t 0.6; Sep −0.01, t −0.1).
(c) Trading hit rate above base rate: no (44 % vs 56 %).

- **Corn**: the satellite beats trend at state level in both reports (4.8 vs 5.1, 4.2 vs 5.1) and is
  the best of the four at the US August date (1.4 %, vs USDA 1.5), but four years cannot separate 1.4 from
  1.3–1.5. USDA is always better at state level, and by September USDA's objective-yield survey wins clearly.
- **Soybeans**: worse than trend everywhere in the holdout; the satellite sat 2–6 % above final in 2022,
  2023 and 2025. Soy yield is set by August–September pod fill, which a forecast made in early August (or
  with composites ending Aug 20) cannot see.
- **What the satellite adds to weather** (`v1_wx`): corn states Sep 4.2 vs 4.3 holdout (5.7 vs 6.9 dev);
  nationally the weather-only model is as good or better. The VI adds a little at state level for corn only.
- The pre-fix spec (`v0_prefix`) is worse in the holdout (US corn Sep 3.6 %, soy 6.6 %), so the fixes did
  not buy the result.

### Satellite minus USDA / consensus, and did the final move toward the satellite? (US, `results/gaps_us_v1.csv`)

| Year | Crop | Aug: sat − USDA / sat − cons (%) | Sep: sat − USDA / sat − cons (%) | Final vs USDA Aug / Sep (%) | Final moved toward sat (Aug / Sep) |
|---|---|---|---|---|---|
| 2022 | corn | +2.1 / +1.9 | +4.1 / +4.1 | −1.2 / +0.5 | no / yes |
| 2023 | corn | +2.4 / +2.2 | −0.2 / −0.0 | +1.2 / +2.0 | yes / no |
| 2024 | corn | −1.9 / −1.4 | −1.4 / −1.0 | −2.1 / −2.4 | yes / yes |
| 2025 | corn | −0.6 / +1.8 | +2.1 / +2.5 | −1.2 / −0.1 | yes / no |
| 2022 | soy | +0.3 / +1.9 | +3.6 / +1.6 | −4.7 / −2.0 | no / no |
| 2023 | soy | +5.8 / +5.0 | +6.1 / +5.9 | −0.6 / +1.0 | no / yes |
| 2024 | soy | −0.1 / +1.2 | −0.0 / −0.4 | −4.8 / −4.8 | yes / yes |
| 2025 | soy | +2.1 / +3.3 | +4.0 / +4.6 | −1.1 / −0.9 | no / no |

- The final moved toward the satellite in 8 of 16 cases (corn 5/8, soy 3/8; 5 of 11 when |gap| > 1 %);
  the satellite was closer to the final than USDA in 6/16. Development: 39 % and 17 %.
- 2024 corn is the one clean hit: the satellite was 1.4–1.9 % below USDA and the final came in 2.1–2.4 %
  below USDA's August/September numbers.
- Gap regression (`results/gap_test_v1.csv`): states pooled, holdout slope +0.08 (t 0.6) Aug, −0.01 Sep; in
  development +0.13 (t 1.6) and +0.17 (t 2.6). The US Aug slope (+0.43, t 3.9) rests on 8 points / 4
  clusters and is not a finding.

### Trading on sign(satellite − consensus) (`results/trading_v1.csv`, `trading_rows_v1.csv`)

Short new-crop futures (benchmark `r_main`: Teucrium ETF in these years) at the prior close when the
satellite is above the consensus, long when below, exit at the report-day close, net of 0.6 ¢/bu.

| Period | n | Hit vs sign(USDA − cons) | Base rate (USDA > cons) | Net ¢/bu (t) | Always-short |
|---|---|---|---|---|---|
| Dev 2013–21 | 36 | 86 % | 83 % | +3.8 (1.3) | +1.2 |
| **Holdout** corn | 8 | 25 % | 63 % | −1.9 (−0.7) | −1.5 |
| **Holdout** soy | 8 | 63 % | 50 % | −4.7 (−0.5) | −7.6 |
| **Holdout** both | 16 | **44 %** | 56 % | **−3.3 (−0.7)** | −4.6 |

The satellite was above the consensus in 12 of 16 holdout reports, so it mostly reproduces the "USDA beats the
trade" bias that the benchmark found and that stopped paying in 2022–25. It does not clear the benchmark's
bar (sign hit above the 64 % / 50 % August base rates).

## 2026 live forecasts (frozen spec; US, bu/ac)

| Crop | Report | Forecast date | Satellite (±1 sd) | Trend | USDA in the report | Consensus | Sat − USDA | Sat − cons |
|---|---|---|---|---|---|---|---|---|
| Corn | Aug | 2026-08-07 | **187.1 ± 6.7** | 185.0 | 180.7 | 182.4 | +3.5 % | +2.5 % |
| Corn | Sep | 2026-09-06 | **185.7 ± 5.4** | 185.0 | 178.5 | 178.1 | +3.9 % | +4.2 % |
| Soy | Aug | 2026-08-07 | **55.6 ± 2.7** | 53.6 | 52.7 | 52.9 | +5.4 % | +5.0 % |
| Soy | Sep | 2026-09-06 | **55.1 ± 2.7** | 53.6 | 52.8 | 52.4 | +4.2 % | +5.0 % |

- The drift guard fired for September (Aqua − HLS +0.026); without it the Sep forecasts would be 192.2 corn
  and 56.4 soy (`signal/us_sat_signal_v1_noguard.csv`). The weather-only model says 182.0 / 53.7.
- USDA's October 2026 report (Oct 9) moved to 181.2 corn and 53.1 soy, i.e. toward the satellite, but by
  far less than the gap. Given the soybean bias in the holdout and the residual 2026 greening, treat 2026 as
  a test of the drift guard rather than a call. The January 2027 final will score it.
- State-level 2026 numbers are in the signal file.

## Caveats

- **Small samples.** 4 holdout years (8 US numbers per crop); every holdout t-statistic rests on 4 clusters.
- **Contamination**: see the disclosure in the pre-registration (soybean US holdout numbers of an earlier
  version were seen before two spec changes).
- **Reprocessed archive.** MODIS collection 6.1 and gridMET are reprocessed products, not the real-time
  versions (gridMET's real-time days are provisional); latency rules are applied but values are final.
- **Mask.** The rotation mask is ~70 % right at the cell level, so corn and soy signals contaminate each other;
  equal pixel weights inside high-share counties under-represent fringe areas (W Kansas, N Minnesota).
- **HLS fills** for 2025 and 2026 come from 48 MGRS tiles (4 per state) and carry ~0.025 EVI state-level noise.
- **Drift.** The guard threshold (0.02) was set after the 2026 residual was visible (it uses no yields).
  The 2024 residual (+0.012) suggests drift may already have nudged 2024 features upward.
- **Truth and trend.** Truth = January Annual Summary vintage; trends use January vintages 2004+ and revised
  Quick Stats values before 2004. Forecast dates use actual release dates (release − 5 days).
- `evaluate.py` gained a fix after the pre-registration hash (next-report regressions now skip the cancelled
  Oct-2013/Oct-2025 reports); `model.py` gained the `--no-drift-guard`/`--trend`/`--vi-demean-only` options and
  an empty-log guard; the v1 computation is unchanged.

## Reproduce

All scripts are CLIs with docstrings. Scratch use: ~0.5 GB kept (pixel series, CDL windows); ~120 GB streamed.

```
S=<scratch>/us_sat
python fetch_nass.py                                   # Quick Stats bulk -> data/nass_*.csv, county acres
python prep_benchmark.py                               # benchmark PIT -> release dates, Jan finals, USDA, consensus
python build_sample.py --geo $S/geo                    # data/pixels.csv (Census county shapefile in $S/geo)
python plot_sample.py --geo $S/geo                     # figures/sample_map.png
python extract_modis.py --work $S                      # Aqua MYD13Q1 at pixels (~35 min)
python extract_modis.py --work $S --platform MOD --tiles h11v04 --doys 193   # drift check
python extract_cdl.py --work $S                        # CDL windows 2008-2025
python extract_weather.py --work $S                    # gridMET -> features/weather_state_daily.csv
python extract_hls.py --work $S                        # HLS overview reads (~30 min)
python build_features.py --work $S                     # masks + MODIS state series (needed before calibration)
python extract_hls.py --work $S --calibrate            # HLS -> MODIS calibration, fills
python build_features.py --work $S --hls               # final features/modis_state.csv
python plot_sample.py --geo $S/geo --mask-year 2024 --work $S
python plot_drift.py --work $S
python model.py [--evaluate-holdout]                   # signal/us_sat_signal_v1.csv
python model.py --evaluate-holdout --feats prcp_ja,hdd30 --tag v1_wx
python model.py --evaluate-holdout --no-drift-guard --tag v1_noguard
python model.py --evaluate-holdout --trend ols --vi-demean-only --tag v0_prefix
python evaluate.py --tag v1                            # results/, figures/ (also v1_wx, v0_prefix)
```
