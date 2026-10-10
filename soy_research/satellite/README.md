# Satellite + weather soybean yield signal for Brazil (point-in-time)

(Results sections below are filled in after the holdout run. This pre-registration section was written
first and has not been edited since.)

## Pre-registration (written 2026-10-10 15:20 UTC, before any holdout evaluation)

Development used seasons up to 2021/22 only. The holdout is the last four seasons, 2022/23, 2023/24,
2024/25 and 2025/26. Nothing about the model was chosen by looking at them. The development run wrote
holdout rows only to `signal/.sealed_holdout_v1.csv`. No evaluation code read that file.

Frozen spec (`model.py`, sha256 prefix `c51301377322455e`; `build_features.py` `ceb08de5f6fa93a5`; `build_mask.py` `6378d653b8c8aed2`):

- **Unit.** One state and season (12 states: MT PR RS GO MS BA MG MA TO PI SP SC), at as-of dates on the 1st and 16th of each month from Nov 1 to Jun 1.
- **Target.** final yield / trend − 1. The trend is an OLS line through the last 15 yields that were known at the as-of date, evaluated at the target year:
  - a year counts as known through PAM once PAM was out (Sep 30 of the following year);
  - otherwise it uses the latest IBGE LSPA vintage released before the as-of date.
- **Features**, using only inputs whose `available_date` ≤ as-of:
  - `evi_cum`: mean EVI anomaly over the crop window to date;
  - `ndvi_recent`: NDVI anomaly of the last two composites in the window;
  - `precip_cum`: CHIRPS Oct-to-date precipitation / climatology − 1;
  - `lst_cum`: mean MODIS daytime LST anomaly from Dec 1 to Mar 22.
  - The crop windows for PR, RS and SC are shifted later by 16, 32 and 32 days.
  - All anomalies are per-pixel against prior seasons only.
- **Model.** A pooled ridge across states, fitted separately for each as-of date. Features are z-scored on the training set. α = 3, with an unpenalised intercept. Training is walk-forward on seasons 2003/04 … Y−1, and the first forecast season is 2010/11.
- **Uncertainty.** The leave-one-season-out RMSE on the training seasons.
- **Brazil.** The sum of the 12 states plus the rest of Brazil at trend yield, using point-in-time areas.

Pre-registered holdout metrics, reported whatever they show:

1. Mean |error| of the Brazil yield against the IBGE final, at each as-of date (Feb 1, Mar 1 and Apr 1 are the headline dates). It is compared with:
   - (a) the trend-only forecast;
   - (b) the official vintage public at that date: Conab for 2019/20 onward, IBGE LSPA otherwise, each against its own final.
2. Mean |error| of state yields against the IBGE final, pooled, compared with trend-only.
3. Revision test: regress the official's next revision on its previous revision and on (satellite − official) at the release. The gap is de-meaned by source and state using prior seasons only, and standard errors are clustered by season. We report the gap coefficient and its t-statistic.
4. Shock seasons: the sign of (satellite − official) against the official's later revision, and the lead time. Lead time is the first date after which the estimate stays within 3% of final for Brazil and within 6% for a state, satellite versus official.

Success criteria fixed in advance: the satellite beats trend at Feb 1 and Mar 1 for Brazil in the holdout, and the gap coefficient for the revision test is positive.

---

## What this is

This is a satellite-plus-weather estimate of soybean yield for each of the 12 main Brazilian states and for Brazil, issued on the 1st and 16th of every month from November to June. It runs from 2010/11 to 2025/26.

Every number in it uses only data that was public on the as-of date. The 12 states made up 95% of Brazil's production in 2025.

The point is to test whether free satellite data sees supply shocks before the official agencies (Conab, IBGE) price them in.

## Data sources (all free and all reachable from this environment)

| Input | Source | Use | Point-in-time availability rule |
|---|---|---|---|
| MODIS Terra MOD13A1 v061 NDVI/EVI, 500 m, 16-day, plus pixel reliability | Microsoft Planetary Computer `modis-13A1-061` | Crop condition (the backbone) | Composite end date + 14 days |
| Gap fill: MOD13Q1 (250 m, same dates) and MYD13A1 (Aqua, ±8 days) | Planetary Computer | 70 tile-dates missing from MOD13A1 on PC (2022/23, Feb 2023, 2026) | The substitute product's own end date + 14 days |
| MODIS Terra MOD11A2 v061 daytime LST, 1 km, 8-day | Planetary Computer `modis-11A2-061` | Heat and drought stress | End date + 10 days |
| CHIRPS v2.0 monthly precipitation, 0.05° | data.chc.ucsb.edu | Rainfall | Month M available on day 20 of M+1 |
| IBGE PAM, SIDRA 1612: state yields 1985–2025 and municipal soy area 2000–2025 | apisidra.ibge.gov.br | Targets, trends, mask weights | PAM year X available from Sep 30 of X+1 |
| IBGE LSPA, SIDRA 6588: monthly state vintages 2006–2026 | apisidra / benchmark | Latest-year yield before PAM, current-year area, comparison | Benchmark release dates (`../benchmark/data/interim/ibge_lspa_release_dates.csv`) |
| Conab survey vintages 2019/20–2025/26, USDA, LSPA | `../benchmark/data/pit/pit_soy_brazil.csv` | Comparison and revision tests | Its `release_date` |
| IBGE municipal boundaries | servicodados.ibge.gov.br malhas v3 | Mask | Static (current mesh) |

Checked but not used:

- **ERA5 on Planetary Computer** (`era5-pds`): no items after 2024, so it cannot be used in real time.
- **TerraClimate**: ends in 2021.
- **MapBiomas**: the bucket is reachable, but the yearly 30 m Brazil mosaics are several GB each.
- **Sentinel-2 / HLS**: not needed, because MODIS covers 26 seasons.

**Archive gap.** Planetary Computer has no MODIS 13A1/13Q1/09A1/43A4 for 2025-07-12 → 2025-11-16, on Terra or on Aqua. The 2025/26 as-of dates for Nov 1, Nov 16 and Dec 1 therefore contain no VI information: the features are set to climatology and the forecast collapses to trend.

Seasons covered:

- Pixel series: 2000/01–2025/26, 538 composites × 7 MODIS tiles, h12–13 / v09–12.
- Mask and anomalies: from 2003/04.
- Walk-forward forecasts: 2010/11–2025/26, with 12 development seasons and 4 holdout seasons.

## Mask method (point-in-time)

1. **Candidate pixels** (`build_mask.py`).
   - Start from the 1,448 municipalities whose PAM soy share ever reached 5% (and at least 2,000 ha).
   - Rasterise them on the MODIS 500 m sinusoidal grid.
   - Draw 40,000 pixels per state, with probability proportional to the municipality's peak soy share.
   - This step only decides which pixels to download. It is a superset, so it leaks nothing.
   - Map: `figures/mask_samples.png`.
2. **Season-Y mask** (`build_features.py`). A pixel is in the mask for season Y if it showed summer-crop phenology in at least 2 of seasons Y−1, Y−2 and Y−3.
   - Summer-crop phenology means a quality-screened NDVI peak of at least 0.78 between Nov 16 and Mar 21, and a rise of at least 0.35 from the pre-season minimum (Aug 12 – Dec 2).
   - Nothing from season Y enters its own mask.
   - Map for 2023/24: `figures/mask_season_2024.png`. The mask sits on the Mato Grosso plateau, the MATOPIBA chapadões, Goiás and the Triângulo, western Paraná and the RS planalto, and excludes the Xingu forest and the Pantanal.
3. **Weights.** Each mask pixel is weighted by its municipality's PAM soy area in year Y−2 (the latest PAM published when season Y starts), divided by the number of mask pixels in that municipality.
4. **Check against PAM** (`features/mask_validation_2024.csv`). Correlation across municipalities between mask share and PAM soy share:
   - PR 0.88, MS 0.93, RS 0.69, MT 0.64, GO 0.63; 0.51 pooled over all 1,302 municipalities.
   - The mask over-includes in GO, MG and SP, where maize and sugarcane share the phenology, and is weak in MA and PI. Weighting by municipal PAM area limits the damage.
5. **Anomalies.** Each pixel's value is compared with that pixel's own mean at the same composite slot over all prior seasons (at least 3). The anomalies are then aggregated with the mask weights. This removes changes in mask composition.

## Features (one row per state × composite, plus as-of feature snapshots)

| File | Content |
|---|---|
| `features/modis_vi_state.csv` | Per state × 16-day composite: NDVI, EVI, NDVI/EVI anomaly, valid fraction, `available_date` |
| `features/lst_state.csv` | Per state × 8-day composite: LST (°C), LST anomaly, `available_date` |
| `features/precip_state.csv` | Per state × month: CHIRPS precipitation, climatology, `available_date` |
| `features/asof_features.csv` | Per (season, as-of, state): the four model features and the cut-off dates of each input |
| `features/mask_summary.csv` | Mask pixels per state and season (80k in 2003/04 → 237k in 2025/26) |

## Signal dataset

- `signal/soy_sat_signal_v1.csv` is the pre-registered model.
- `signal/soy_sat_signal_v1b_nolst.csv` is an exploratory variant (see below).

There are 3,120 rows in each file, covering 16 seasons × 15 as-of dates × (12 states + BR). Columns:

| Column | Meaning |
|---|---|
| `as_of_date` | Forecast date |
| `data_cutoff_date` | End date of the latest input composite or month actually used |
| `crop_year`, `state` | Season and region |
| `predicted_yield` | Yield forecast, kg/ha |
| `predicted_production` | Production forecast, t |
| `uncertainty_yield_1sd`, `uncertainty_production_1sd` | One-standard-deviation uncertainty |
| `trend_yield` | Point-in-time trend yield |
| `area_ha_used`, `area_source` | Area used: `lspa` = latest released IBGE area for the season, `trend` = last known area × its 3-year growth |
| `coef_*`, feature values | Model coefficients and feature values |
| `final_yield_expost` | Evaluation only; it is not point-in-time information |

The yield is the satellite signal. **Production uses official (LSPA) area once it is public, from mid-February.**

Note on uncertainty: the 1-sd band covered the realised error in 83–100% of development cases, so it is conservative. In the holdout, coverage fell to 75%.

## Results

Errors are mean |error| in %. Each cell reads **satellite / trend-only / official vintage public at that date**. The satellite is scored against the IBGE PAM final. The official is Conab from 2019/20 and IBGE LSPA otherwise, each scored against its own final. Before mid-February only Conab seasons have an official figure.

### Pre-registered model v1: development 2010/11–2021/22 (walk-forward) vs holdout 2022/23–2025/26

| Level | Period | Dec 1 | Jan 1 | Feb 1 | Mar 1 | Apr 1 | May 1 |
|---|---|---|---|---|---|---|---|
| Brazil | dev | 6.6 / 5.9 / 6.3 | 6.8 / 5.9 / 6.5 | **3.6** / 6.0 / 5.8 | **3.4** / 6.0 / 4.3 | 3.9 / 6.0 / 3.0 | 3.9 / 6.0 / 1.8 |
| Brazil | **holdout** | 4.5 / 4.6 / 4.7 | 2.6 / 4.6 / 4.2 | **6.0** / 4.6 / 3.2 | **4.5** / 4.7 / 2.1 | 6.2 / 4.7 / 1.5 | 5.3 / 4.7 / 1.1 |
| States (pooled) | dev | 14.0 / 13.2 / 14.5 | 13.4 / 13.2 / 14.7 | 10.8 / 13.2 / 13.9 | 9.8 / 13.2 / 10.2 | 9.0 / 13.2 / 8.5 | 9.1 / 13.2 / 5.1 |
| States (pooled) | **holdout** | 8.6 / 8.6 / 8.6 | 9.0 / 8.6 / 8.4 | 10.7 / 8.6 / 7.5 | 10.7 / 8.6 / 5.8 | 11.1 / 8.6 / 3.7 | 10.8 / 8.6 / 2.4 |

**Pre-registered success criterion: FAILED.**

- In the holdout, the Brazil forecast is worse than trend at Feb 1 (6.0 vs 4.6) and about equal at Mar 1 (4.5 vs 4.7). States are worse than trend.
- In development the satellite beat both trend and the official vintage at Feb 1–Mar 1.
- From mid-March the official agencies are always better, because they collect harvest information.

**Why the holdout failed: the MODIS Terra orbit drift** (`figures/fig_lst_drift.png`).

- Terra's overpass has been drifting earlier since about 2022. The 12-state mean Dec–Mar LST anomaly is −1.6, −0.4, −2.1 and −3.6 °C in 2023–2026, against −1.0 to +0.7 °C in every earlier season.
- The model reads "cool canopy" as a good crop, so it pushed every state up by 5–25%. Brazil was biased high by 3–7% in each holdout season.
- The VI anomalies drift much less.

### Exploratory, NOT pre-registered: v1b without LST

This variant is the same spec without `lst_cum`. **The idea came from looking at the holdout, so these numbers are optimistic.**

| Level | Period | Jan 1 | Feb 1 | Mar 1 | Apr 1 |
|---|---|---|---|---|---|
| Brazil | dev | 6.9 | 4.8 | 3.7 | 4.4 |
| Brazil | holdout | 4.0 | **2.1** | **1.6** | 2.5 |

- At Feb 1 and Mar 1 this beats both trend (4.6) and the official vintage then public (3.2 and 2.1).
- It should be pre-registered as v2 and judged on 2026/27 onward, ideally with an Aqua/Terra drift correction rather than simply dropping LST.

### Does satellite − official predict the next official revision?

(`results/revision_test.csv`)

The regression is: next revision (log yield) ~ previous revision + gap. The gap is log(satellite / official) at the release, de-meaned by source and state using prior seasons only. Releases are Dec–May, standard errors are clustered by season, and v1 is the model.

| Official | Period | n (seasons) | Persistence b (t) | Gap b (t) | R², persistence only → with gap | Sign hit when \|gap\| > 3% |
|---|---|---|---|---|---|---|
| Conab, states | dev | 216 (3) | 0.41 (7.9) | 0.03 (0.5) | 0.170 → 0.174 | 57% |
| Conab, states | holdout | 288 (4) | 0.39 (9.5) | 0.06 (3.4) | 0.148 → 0.195 | 66% |
| LSPA, states | dev | 576 (12) | 0.11 (1.8) | 0.12 (2.1) | 0.012 → 0.071 | 58% |
| LSPA, states | holdout | 180 (4) | 0.27 (4.0) | 0.13 (7.3) | 0.078 → 0.206 | 78% |
| Conab / LSPA, Brazil | all | 42 / 63 | 0.34 / 0.36 | 0.05 / 0.03 (t ≈ 1) | — | 56% |

- **At state level the satellite gap adds information beyond persistence.** A 10% gap predicts about a 1% further official move in the same direction, and sign accuracy is 58–78%.
- At Brazil level it adds nothing significant.
- The holdout t-statistics rest on only 4 clusters, so treat them as indicative.
- The persistence baseline (Conab state 0.41, t 7.9) matches the benchmark agent's 0.42.

### Divergence events and lead time

(`results/divergence_events.csv`, `results/shock_seasons.csv`, `figures/fig_shock_paths.png`)

**Event definition.** An event fires on the first as-of date from Jan 1 to Apr 1 when the satellite is at least 5% away from the official AND has itself moved at least 2% off trend in the same direction. It is "followed" if the official later moved at least 3% that way. The lead is the time from the signal to the official release that completes half of that later revision.

- **Satellite below official (cuts):**
  - Development: followed 56% of the time against a 35% base rate; median lead 7.4 weeks.
  - Holdout: followed 30% against a 23% base rate; median lead 5 weeks.
- **Satellite above official:**
  - Development: followed 49% against 33%.
  - Holdout: followed 45% against 44%, so no edge.

**Shock seasons (v1).**

| Season | What the satellite saw vs the official | Lead |
|---|---|---|
| 2011/12 (south drought) | At Mar 1, below LSPA in RS (−12%), PR (−7%), MS (−15%) and SC; LSPA later cut 32%, 8%, 17% and 27% | 1–6 weeks (RS 5.7). The satellite then overshot: Brazil −9% at Apr 1 |
| 2015/16 (MATOPIBA) | From mid-Feb, below LSPA in MA (−22%), PI (−35%), BA (−14% at Mar 1) and TO; LSPA later cut 47–93% (log) | 10–16 weeks (Brazil 7.9). The direction was right but the size far too small: the satellite was still 33–50% above final in BA, MA and PI at Mar 1 |
| 2018/19 | PR and GO settled within 6% of final 1.6 weeks before LSPA | 1.6 weeks |
| 2019/20 (RS) | **Miss.** RS EVI anomaly was *positive* in Jan–Feb, and the satellite was 75% above final. Conab also missed (+63%) | — |
| 2021/22 (south drought) | Below Conab in PR (−9%) and MS (−15%) on Jan 1; in Brazil (−9%) and RS (−45%) on Feb 1. Conab's −15 Mt cut came on Feb 10 | 1.3 weeks (Brazil, RS, SC); 5.7 weeks (PR, MS) |
| 2022/23 (RS, holdout) | RS 24% below Conab on Feb 1; Conab cut by Mar 9. Brazil was biased high (LST drift) | 5.1 weeks |
| 2023/24 (holdout) | PR 15% below Conab on Feb 1; Conab cut a week later. RS 18% below Conab from Jan 1, but Conab completed half of its cut only on Jun 13 (floods), so the 23-week lead is not meaningful. **MT was the main loss and the satellite did not lead it**: Conab was within 6% by Jan 10, the satellite only by Feb 16 (−5 weeks), and MS was a miss | +1 week (PR); −5 weeks (MT) |
| 2024/25 (holdout) | RS ~17% below Conab in Jan–Feb, and Conab cut 24% later. In v1 this is not counted as an event because the prediction stayed near trend; v1b flags it on Feb 1 | 5.7 weeks (v1b) |

**Bottom line.**

- In southern drought seasons the satellite repeatedly sat well below the official figure, and the agencies then revised toward it, typically 1–6 weeks later at state level.
- For Brazil, the lead before Conab's big February 2022 cut was only about 1–2 weeks.
- Elsewhere the signal is noisy:
  - false "cut" alarms in GO, MG and SP, where the mask catches maize and sugarcane;
  - a total miss for RS in 2019/20;
  - no lead on Mato Grosso in 2023/24;
  - systematic sensor-drift bias in v1 since 2022/23.

## Caveats

- **Reprocessed archive.** The MODIS data are collection 6.1, reprocessed in 2020–2021, not the near-real-time products that existed at each date. Latency rules are applied, but the values themselves are revised products. CHIRPS final is used with the final's latency (day 20 of the following month), which is conservative compared with CHIRPS-prelim.
- **Sensor drift and the end of the platforms.** Terra drift since ~2022 biases LST and probably VI. Terra and Aqua are near end-of-life, so a production version needs VIIRS (VNP13A1) or HLS/Sentinel-2, with a cross-calibration period.
- **The mask is a summer-crop mask, not a soybean mask.** First-season maize, rice in RS and sugarcane leak in, especially in GO, MG and SP.
- **Targets.** The targets are IBGE PAM yields (production / harvested area). Conab uses planted area and different levels, so each source is scored against its own final, and the revision test removes the level difference using prior seasons only. 2025/26 has no PAM yet, so its target is the latest LSPA vintage (Aug 2026), which is provisional.
- **Small samples.** The trend is a 15-year OLS line, with pre-2007 years taken from PAM even where the LSPA vintage is unknown; this only affects training-target construction before 2007. There are 16 forecast seasons, and the holdout has 4 seasons and 4 clusters, so the t-statistics are fragile. The Conab vintages begin only in 2019/20, so for 2011/12 and 2015/16 the comparison is against IBGE LSPA, whose first estimate comes out in mid-February.
- **Code changes after pre-registration.** After the pre-registration timestamp, `model.py` gained the `--feats`/`--tag` options and the output column was renamed `final_yield_expost`. The default v1 computation is unchanged and the outputs were regenerated identically. The sha256 prefix in the pre-registration refers to the file before those edits.

## Reproduce

All steps are CLI scripts with docstrings. The scratch directory holds about 3.3 GB of pixel series; no rasters are kept.

```
python fetch_ibge.py                                   # PAM, LSPA, municipal meshes -> data/
python build_mask.py                                   # candidate pixels -> data/pixels.csv
python plot_mask.py                                    # figures/mask_samples.png
python extract_modis.py --work $SCR --threads 40       # MOD13A1 at pixels (~20 min, ~95 GB streamed)
python extract_modis.py --work $SCR --fill-gaps        # MOD13Q1 / MYD13A1 substitutes for PC gaps
python extract_weather.py --work $SCR --what chirps
python extract_weather.py --work $SCR --what lst --threads 32
python build_features.py --work $SCR                   # features/*.csv
python model.py --evaluate-holdout                     # signal/soy_sat_signal_v1.csv (dev mode without the flag)
python evaluate.py --holdout                           # results/, figures/
python model.py --evaluate-holdout --feats evi_cum,ndvi_recent,precip_cum --tag v1b_nolst   # exploratory
python evaluate.py --holdout --tag v1b_nolst
python plot_features.py
```
