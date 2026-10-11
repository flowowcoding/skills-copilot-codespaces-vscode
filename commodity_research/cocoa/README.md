# West African cocoa: can free weather and satellite data beat a weak official benchmark?

Status: PRE-REGISTRATION written 2026-10-11, before any feature–outcome relationship was computed.
Results are appended below the pre-registration and do not change it.

## Pre-registration (fixed before evaluation)

**Hypothesis.** Markets with weaker official data are easier to beat. Côte d'Ivoire (CIV) and Ghana
(GHA) grow about 60% of world cocoa, and their official numbers are thin: no USDA-style crop report,
ICCO estimates that come quarterly and are revised a lot, and weekly CIV port arrivals that reach the
market only through exporter estimates relayed by news agencies.

**Holdout.** Every season from **2022/23 onward** (as-of dates ≥ 2022-10-01): 2022/23, 2023/24,
2024/25 and 2025/26. Training covers as-of dates 2003-10-01 to 2022-09-30. Cocoa years run Oct–Sep.
Anomaly climatologies use **2003–2021 only**.

**Data, point-in-time.** Each feature value carries the date it could have been known:
- CHIRPS v2 monthly (0.05°): the CHC server posting date (median 16 days after month end); for files
  bulk-reposted in 2015, month end + 15 days.
- NASA POWER daily (T2M_MAX, RH2M, GWETROOT …): month end + 7 days. Current vintage only; POWER
  back-fills recent days.
- MODIS Aqua MYD13A1 EVI (500 m, 16-day): production date in the item id + 2 days.
- Spatial weights: cocoa area by region/district from Kalischek et al. (2023) via Trase.
- Arrivals/purchases: market-known date = as-of date + 1 day (exporter estimates come out on Monday
  for the week ending Sunday).
- ICCO bulletin: the release date stated in the press release.

**Monthly features** (zone ALL = CIV + GHA, cocoa-area weighted; z-scores against 2003–2021 for the
same calendar end-month):
- `rain_3m_z`, `rain_6m_z`: CHIRPS rainfall summed over the last 3 / 6 published months.
- `soil_3m_z`: POWER GWETROOT mean over the last 3 complete months.
- `tmax_3m_z`: POWER mean Tmax over the last 3 months.
- `rh_3m_z`: POWER mean RH2M over the last 3 months. Low RH stands in for the Harmattan.
- `evi_3m_z`: MODIS EVI, the cocoa-pixel mean of good-quality pixels over the last 6 published composites,
  as a z-score against each pixel's day-of-year climatology.

**Two pre-specified composites** (no fitting of weights):
- `DRY = mean(rain_6m_z, soil_3m_z, rh_3m_z, −tmax_3m_z, evi_3m_z)`. Higher means wetter, cooler and
  greener. Expected effect: more supply.
- `WETX = max(0, rain_3m_z − 1)` captures excess rain (black-pod risk). Expected effect: less supply.

**Test (a1): season arrivals.** Target = CIV cumulative-arrivals y/y % as reported (same period last
season), taken from the report closest to the checkpoint:
- `MC_yoy`: main crop, checkpoint 31 Mar, window 10 Mar–30 Apr. Features as of 15 Oct at the start of
  the season.
- `SEAS_yoy`: whole season, checkpoint 30 Sep, window 15 Aug–10 Oct. Features as of 15 Oct.
- `MID_delta = SEAS_yoy − MC_yoy`: how the mid-crop changes the pace. Features as of 31 Mar.

Model: OLS `target ~ DRY + WETX` fitted on the training seasons and applied unchanged to the holdout.
Success means:
1. the holdout MAE beats the naive forecast (the training mean); and
2. the sign is right in at least 2/3 of the holdout seasons.

N is tiny (about 9 training and 2–3 holdout seasons), so a pass would count only as anecdotal.

**Test (a2): ICCO revisions.** Unit = ICCO bulletin `b` that has a current-season world production
number and a later bulletin for the same season. Target = next revision `(P_{b+1} − P_b)/P_b` in %.
Model: `rev_next ~ rev_prev + DRY_b + WETX_b`, with features as of the release date of `b`. The
benchmark is the persistence model `rev_next ~ rev_prev`. Success means:
1. holdout MAE below persistence; and
2. the DRY coefficient is positive and WETX negative, each with |t| > 2 in training.

Country-level (CIV, GHA) revisions are available only from 2018 and are reported descriptively.

**Test (b): futures returns.** Monthly, as of the last trading day `t`; ICE NY cocoa front-month
continuous (Yahoo CC=F). Target: the log return over the next h = 1, 2, 3 months.
- **B1 (published information):** `r_3m`, `r_12m` (momentum) and `arr_yoy`, the latest CIV arrivals
  y/y known by `t` (carried forward up to 60 days within a season, else 0, with a missing flag).
- **B2:** B1 plus `DRY_t` and `WETX_t`. Expected signs: DRY negative, WETX positive (good weather means
  lower prices).

Coefficients are fitted on training months 2003-10 to 2022-09. The primary evaluation applies the
frozen coefficients; an expanding-window refit is a secondary check. Metrics: holdout OOS R² of B2
against B1, and a trading rule `position = sign(pred_B2, h=1)` rebalanced monthly. Costs are 15 bps
per unit of turnover (one-way), plus the roll embedded in CC=F. The rule is compared with the same
rule on B1 and with buy-and-hold. Success means:
1. OOS R²(B2 vs B1) > 0 at h = 1; and
2. the B2 rule's net mean monthly return exceeds the B1 rule's, with t > 1.5.

**2023–24 regime.** All holdout metrics are also reported without season 2023/24 (Oct 2023–Sep 2024).

**Not tested (descriptive only):** zone-level (CIV_W, CIV_E, GHA) features, ENSO, and Ghana purchases.

**Implementation details fixed before evaluation, after inspecting data coverage only:**
1. A window whose last observation ends more than 75 days before the as-of date counts as missing.
   Planetary Computer has no MODIS composites for July–November 2025, and without this rule a stale
   EVI value would carry forward.
2. The composites average whatever components are available (skip-NaN mean).
3. For first forecasts, `rev_prev` = 0.
4. `yoy` is the reported y/y % when given, otherwise `100·(cum/prev − 1)` from the same report.

---

## Results (computed after the pre-registration above)

**Bottom line: no.** A weaker official benchmark did not make free weather and satellite data
useful here. None of the three pre-registered tests passed in a way that counts. The one formal pass
(season arrivals, N = 2) is anecdotal and rests on insignificant training coefficients. The
weather-augmented trading rule lost money net of costs, in the holdout both with and without 2023/24.

### How weak is the official benchmark?

It is weak, but in a particular way: it is late and noisy, not wrong on average.
- **ICCO arrives late.** The first ICCO forecast for a season comes out at the end of February,
  five months into the season, when most of the main crop has already reached the ports.
- **World numbers are revised moderately.** The first forecast differed from the latest estimate by
  **2.8%** on average (18 seasons, 2006/07–2024/25).
- **Country numbers are noisy:**
  - CIV: **3.3%** (6 seasons).
  - Ghana: **17%** (6 seasons). Its 2023/24 estimate went 580 → 501 → 450 → 480 → 530 → 449 kt.
    See `figures/fig2_icco_vintages_2023_24.png` and `results/benchmark_first_vs_latest.csv`.
- **ICCO has stopped forecasting.** It withheld current-season production and grindings from May 2025
  ("ongoing review of its estimation … methodologies"). It published no 2025/26 forecast in Feb, May
  or Aug 2026.
- **CIV arrivals reach the public only through exporter estimates relayed by news agencies.** Prior-year
  comparisons get revised, e.g. 2,327 → 2,320 kt. In 2024/25–2025/26 the Reuters exporters series and the
  "government data" quoted by Barchart differed by about 5 percentage points. Example: 29 Jun 2025 is
  +1.1% (Reuters) against 22 Jun 2025 at +6.9% (government data). CIV also moved its marketing year to
  start on 1 Sep in 2025/26.
- **The market still has a dense benchmark:** the weekly arrivals. Price moved with them, not with
  ICCO.

### Test (a1): season arrivals (`results/test_a1_season_arrivals.csv`)

The model is OLS `target ~ DRY + WETX`, fitted on the training seasons.

| target | n train | train R² | t(DRY) | t(WETX) | holdout MAE: model vs naive | sign hits | holdout detail |
|---|---|---|---|---|---|---|---|
| MC_yoy | 9 | 0.29 | 0.5 | −1.5 | 20.3 vs 14.7 pp | 0/3 | 22/23: −4.8 vs +5.9 · 23/24: −28.0 vs +6.0 · 24/25: +11.0 vs −5.1 |
| SEAS_yoy | 11 | 0.08 | −0.4 | 0.8 | 18.2 vs 22.6 pp | 2/2 | 23/24: −25.3 vs −1.1 · 25/26: +19.8 vs +7.6 |
| MID_delta | 8 | 0.34 | 1.3 | 1.3 | 1.9 vs 2.6 pp | 1/1 | 23/24 only |

- **Without 2023/24:** MC MAE 13.4 vs 7.9 (0/2 signs). SEAS has 1/1 sign hits (2025/26).
- **MC fails outright.** Start-of-season weather pointed the wrong way in all three holdout seasons,
  including the 2023/24 collapse.
- **SEAS formally passes** but is not a finding: N = 2, coefficients indistinguishable from zero, and
  the 2023/24 prediction (−1%) missed a −25% season.

### Test (a2): ICCO world production revisions (`results/test_a2_icco_revisions.csv`)

53 training and 15 holdout revisions.
- **Training fit:** `rev_next = 0.12 + 0.18·rev_prev + 0.22·DRY + 1.73·WETX`.
  - DRY: t = 0.8.
  - WETX: t = +2.4, the *opposite* of the expected black-pod sign.
- **Holdout MAE:** full model **2.12 pp** vs persistence **1.27 pp** vs zero **1.08 pp**.
- **Without 2023/24:** 2.30 vs 0.87 vs 0.75.
- **Fail.** Even persistence is worse than predicting no revision.
- **Country-level (descriptive, n = 27):** corr(DRY, next CIV revision) = +0.22; Ghana −0.21.

### Test (b): ICE cocoa returns (`results/test_b_returns.csv`, `figures/fig5_holdout_strategy.png`)

Holdout Oct 2022–Sep 2026, 48 months.

| h | train t(DRY) | train t(WETX) | OOS R² B2 vs B1 (frozen / expanding) | without 2023/24 (frozen) |
|---|---|---|---|---|
| 1 | −0.6 | −2.3 | **−9.4% / −7.6%** | −14.2% |
| 2 | −0.2 | −1.8 | −13.2% / −9.4% | −22.6% |
| 3 | −0.7 | −1.6 | −12.6% / −10.9% | −21.8% |

**Monthly sign rule, h = 1, net of 15 bp per unit traded:**

| rule | holdout mean %/month | Sharpe | hit rate | without 2023/24 |
|---|---|---|---|---|
| B1 (momentum + arrivals) | −2.78 | −0.60 | 48% | −1.89 |
| **B2 (+ weather), pre-registered** | **−4.28** | −0.95 | 44% | −5.12 |
| B2 − B1 | −1.50 (t −0.97) | | | −3.23 (t −1.87) |
| buy and hold | +1.85 | | | +0.65 |

- **In-sample,** weather added 2.4 pp of R² (0.067 → 0.091). This came almost entirely from WETX,
  again with the opposite sign: wet spells were followed by *lower* prices in 2003–2022.
- **Out of sample** it hurt.
- **Not tradeable.** The rule is negative before and after costs.
- **Even B1** has negative OOS R² against a zero forecast (−27%).
- **Post-hoc sensitivity: DRY without EVI** (Aqua drift and the 2025 gap). B2 − B1 = +0.16 %/month
  (t 0.07) in the full holdout and −1.02 (t −0.35) without 2023/24. Still nothing.

### Known events (descriptive, post-hoc)

**2023/24:**
- Aug–Nov 2023 had the wettest root-zone soils of the 2003–2026 record for the cocoa belt (POWER
  GWETROOT z ≈ +2.6 to +3.2; CIV_E and GHA ≈ +3.7).
- The MODIS EVI anomaly reached about −2.5 at the same time (fig4).
- So the black-pod setup *was* visible as an extreme in free data. But the pre-registered composite
  treats wet as good. In training, excess rain went with *more* supply and lower prices, so no
  linear model fitted before 2022 could have used it.
- A dry Harmattan is *not* visible in POWER RH: `rh_3m_z` stayed positive through Feb 2024.
- Arrivals were already −23% y/y by the end of October 2023 and −35% by early December. That is
  public weekly data that led the price spike, and ICCO's first forecast (29 Feb 2024).

**2015/16 El Niño:**
- A dry season shows up clearly: rain_6m_z −1.5 to −2.2 from Oct 2015 to Mar 2016, and
  tmax/RH anomalies in spring 2016.
- Main-crop arrivals were only −3%. The whole season ended −16%, with a weak mid-crop.
- In-sample (training), so this is not evidence.

**2025/26:** an extreme wet Mar–Jun 2026 (rain_3m_z up to +4.4) followed a dry late 2025.
Season arrivals were +19.8% (government series).

### Disclosure of a bug fixed after the first evaluation run

The first run treated MODIS composites as available only from their Collection 6.1 *reprocessing*
date (2020–21). As a result EVI was missing throughout training and DRY in training excluded EVI.

The fix: if a composite was produced more than 30 days after its end, availability = composite end +
20 days, the original release latency.

First-run output is kept in `results/evaluate_stdout_run1_evi_avail_bug.txt`. Every pre-registered
test also failed in that run, including SEAS: 0/2 signs, MAE 23.5 vs 22.6. The fix turned SEAS into
a formal 2/2 pass. Read that pass with this in mind.

## Data obtained

| item | coverage | file | source |
|---|---|---|---|
| ICE NY cocoa CC=F daily | 2000-01 → 2026-10-09 | `data/prices_cc.csv` | Yahoo chart API; London C=F returned "delisted" |
| ICCO world production / grindings / surplus vintages | 2007 → 2026-08, 94 rows | `data/icco_world_vintages.csv` | ICCO QBCS press releases via `https://www.icco.org/wp-json/wp/v2/posts?search=Quarterly%20Bulletin` |
| ICCO CIV and Ghana production vintages | Aug 2018 → May 2025, 37 rows | `data/icco_country_vintages.csv` | free `Production_QBCS-*.pdf` tables on icco.org; image PDFs read visually |
| CIV port arrivals as reported (cumulative, same period last year) | 2009 → 2026-09, 117 obs (dense 2016–2023) | `data/civ_arrivals_reported.csv` | ICCO Monthly Cocoa Market Reviews/Reports (162 PDFs, 2008–2025) quoting Reuters, CCC and exporters; plus news snippets found by web search (brecorder/Reuters, fin24, Barchart reposts, cropgpt aggregator, flagged) |
| Ghana COCOBOD purchases as reported | 2009 → 2024, 42 obs | `data/gha_purchases_reported.csv` | ICCO monthly reports |
| Cocoa area by region/district | 33 CIV regions, 260 GHA districts | `data/mask_units.csv`, `data/mask_grid.csv` | Trase spatial metrics derived from Kalischek et al. 2023 (`resources.trase.earth/20261008/data/spatial-metrics/...`) + geoBoundaries gbOpen ADM2 |
| CHIRPS v2 monthly rainfall, cocoa-weighted | 1981-01 → 2026-08, with posting dates | `data/chirps_monthly_zone.csv` | `data.chc.ucsb.edu/products/CHIRPS-2.0/africa_monthly/tifs/` |
| NASA POWER daily at 30 cocoa points → monthly | 1984 → 2026-09 | `data/power_monthly_zone.csv` | `power.larc.nasa.gov/api/temporal/daily/point` |
| MODIS Aqua MYD13A1 EVI at 20,000 cocoa-weighted pixels | 2002-07 → 2026-09 (gap Jul–Nov 2025) | `data/modis_evi_composites.csv`, `data/modis_pixels.csv` | Planetary Computer `modis-13A1-061` |
| Feature windows and monthly features | 2003-10 → 2026-09 | `data/feature_windows.csv`, `data/features_monthly.csv` | `scripts/build_features.py` |
| **Point-in-time signal dataset** | 9,429 rows | `signal/cocoa_pit_signal_v1.csv` | columns: version, as_of, data_cutoff, region, feature, value, source |

**Not obtained or not used:**
- The 10 m Kalischek raster (Earth Engine only); we used district aggregates instead.
- ESA CCI and SMAP soil moisture (bulk downloads); POWER GWETROOT was used instead.
- ERA5 on Planetary Computer, which ended in 2024.
- Open-Meteo, which works but whose daily request weighting would exceed the free quota for 30
  points × 40 years.
- Sentinel-1/2.
- Reuters' own weekly arrivals archive, which sits behind Cloudflare (brecorder); web.archive.org is
  blocked from this environment.
- Weekly arrivals for 2011/12–2014/15 and much of 2023/24–2025/26 are sparse.
- Ghana COCOBOD mid-crop forecasts were not systematically collected.
- Individual (expired) cocoa contracts, which Yahoo does not serve.

## Caveats

- **Tiny N.** Season tests have 2–3 holdout seasons. The returns test has 48 holdout months
  (36 without 2023/24). Absence of evidence is weak too, but every point estimate goes the wrong way.
- **Mask.** District-level, uniform within district. The pixels are cocoa-*region* pixels (cocoa,
  forest and fallow), not confirmed farms.
- **MODIS Aqua** stopped orbit maintenance in 2022. The post-2024 EVI decline (fig4, z down to −5 in
  mid-2026, with 60–80% cloud) may be partly a drift or cloud artefact. Planetary Computer has no
  composites for Jul–Nov 2025.
- **POWER vintages** are not archived, so recent months may since have been back-filled
  (look-ahead risk, probably small at monthly scale). CHIRPS final values do not get revised.
- **Arrivals series** mix sources (CCC official, Reuters exporters, government data via Barchart),
  and prior-year comparisons get revised. A few observations come from an AI-written aggregator
  (cropgpt.ai) via search snippets and are flagged in `note`.
- **CC=F** is a rolled front-month series. Roll gaps contaminate monthly returns, which matters in
  the steep 2024 backwardation. The 15 bp cost does not include the bid-ask during the 2024 squeeze,
  when margins and liquidity were extreme.
- **Release dates.** ICCO's monthly reports are dated by their upload date. Older ones (before
  2019) were bulk-uploaded, so their `as_of` is the data date and the market-known date is
  data date + 1 day (news release), not the ICCO upload.

## Scripts (`scripts/`, each with `--help`)

`fetch_prices.py`, `build_mask.py`, `fetch_chirps.py`, `fetch_power.py`, `extract_modis.py`,
`build_features.py`, `evaluate.py`, `make_signal.py`, `plot.py`, `plotstyle.py`, `run_all.sh`.
Hand-curated benchmark CSVs (ICCO vintages, arrivals, purchases) carry a source URL on every row.
