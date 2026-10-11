# US corn and soybean benchmark: USDA yield vintages, trade consensus and the CBOT report-day reaction

This folder is the benchmark and market side of the US satellite-yield test (the satellite signal itself is built in `soy_research/us/satellite/`). It follows the Brazil design in `soy_research/benchmark/`: every number carries the time it was published, and later revisions never overwrite earlier vintages. Nothing here uses satellite data. It sets the bar a satellite yield signal must clear: the surprise that moves prices is **USDA minus the pre-report trade consensus**, and public information barely predicts it.

## Headline results

| | Corn | Soybeans |
|---|---|---|
| Report-day variance / normal-day variance (Aug, Sep) | 3.8, 1.9 | 4.0, 4.0 |
| Aug: return per 1% yield surprise vs consensus | **−0.90%** (t −2.7, n 22, 2005–26, R² 0.26) | **−0.64%** (t −2.9, n 15, 2012–26, R² 0.44) |
| Sep: return per 1% surprise | −0.85% (t −1.8, n 15, 2012–26) | −0.83% (t −2.7, n 15) |
| Aug+Sep, per 1 bu/acre surprise | −0.58% (t −3.4) = **−2.5 ¢/bu** (t −3.1) | −1.50% (t −3.4) = **−17.7 ¢/bu** (t −3.6) |
| Aug: return per 1% revision vs previous USDA (July WASDE) | −0.05% (t −0.4, R² 0.005) | −0.21% (t −1.7) |
| Best free predictor of the surprise (leave-one-year-out R²) | ≤ 0.04 (G/E change) | ≤ 0.10 (G/E vs normal) |
| Knowing the surprise sign a day early, Aug+Sep, net of 0.6 ¢/bu costs | +2.8 ¢/bu per trade (+0.68%, t 1.8, hit 58%, n 36) | +7.2 ¢/bu (+0.57%, t 1.5, hit 53%, n 30) |
| Same, August only | +4.5 ¢/bu (+1.17%, t 2.1, n 22) | +11.1 ¢/bu (+1.05%, t 1.9, n 15) |
| Same, only surprises larger than the median | +6.8 ¢/bu (+1.72%, t 3.2, n 18) | +16.7 ¢/bu (+1.41%, t 2.4, n 15) |

Unlike Brazil (about −0.1% per Mt, not significant), the US reports move CBOT, and the move is driven by the part the trade did not expect. In August the change from USDA's July (trend) number explains nothing once you know the consensus.

## Contents

| Path | What it is |
|---|---|
| `data/pit/pit_us_corn_soy.parquet` | **The point-in-time dataset.** 63,712 rows: one row per (source, report, release timestamp, crop, marketing year, region, variable). NASS reports for all states, WASDE US lines for every market year shown, weekly crop condition. |
| `data/pit/pit_us_corn_soy_core.csv` | Same, limited to US + the 12 main states and to area/yield/production/stocks (16,912 rows, 2 MB, without the URL column). |
| `data/pit/MANIFEST.json` | Dataset version (`us-corn-soy-pit v1.0`), build time, row counts, sha256 of each file. |
| `data/consensus/consensus.csv` | **Consensus table**: one row per (report, crop, yield/production) with the chosen trade average, range, poll, source URL, how it was captured, and alternative values from other sources. 203 rows. |
| `data/consensus/consensus_raw.csv` | Every hand-collected consensus value, one source URL per value (182 rows). |
| `data/consensus/farmdoc_extracted.csv` | Values read from farmdoc webinar decks, including the 1996/97–2020 bar charts of "USDA August production minus average trade guess". |
| `data/prices/` | **Price tables**: `cbot_corn_zc_daily.csv`, `cbot_soy_zs_daily.csv` (Yahoo continuous, 2000–2026, with log return and roll flag); `contracts_daily.csv` (ZCZ26, ZCH27, ZSX25, ZSX26, ZSF27); `etf_daily.csv` (Teucrium CORN, SOYB); `intraday_60m.csv` (60-minute bars, last 730 days). |
| `data/interim/` | Per-source vintages: `nass_report_vintages.parquet` (parsed NASS text reports), `wasde_us_vintages.csv`, `crop_condition.csv` (weekly good/excellent, US + 12 states, with release date), `quickstats_corn_soy_extract.csv.gz`. |
| `data/reference/` | `esmis_manifest.csv` (URL and release date of every report file read), `other_release_dates.csv` (Crop Progress and Grain Stocks dates), `farmdoc_decks.csv`. |
| `results/` | `events.csv` (one row per report × crop: USDA, previous USDA, consensus, surprises, crop condition, returns), `summary_reaction.csv`, `regressions.csv`, `variance_ratio.csv`, `surprise_predictability.csv`, `sign_knowledge_edge.csv`, `intraday_check.csv`, `proxy_tracking_event_days.csv`, `analysis_stdout.txt`. |
| `figures/` | fig1–fig5 (below). |
| `scripts/` | Command-line scripts, each with a docstring (`python3 scripts/<name>.py -h`). `scripts/run_all.sh` rebuilds everything. |

### PIT schema

`source` (usda_nass, usda_wasde) · `report` (prospective_plantings, acreage, crop_production, crop_production_annual, wasde, crop_progress) · `release_date` · `release_time_et` · `release_ts_utc` · `crop` · `crop_year` · `marketing_year` · `region` (US or state code) · `variable` · `value` · `unit` · `source_url` · `dataset_version`

- **Variables and units**:
  - `planted_area`, `harvested_area`: million acres.
  - `yield`: bu/acre.
  - `production`, `ending_stocks` (WASDE): million bu.
  - `cond_ge_pct`, `cond_pvp_pct`: % of the crop rated good+excellent, and poor+very poor.
- **Which value each report contributes for crop year Y**:
  - Prospective Plantings (end-March, Y): planted area.
  - Acreage (end-June): planted area and harvested-for-grain area.
  - Crop Production (Aug–Nov): harvested area, yield, production. These are forecasts.
  - Annual Summary (January of Y+1): the January "final" for planted area, harvested area, yield and production. NASS revises these later; the January vintage is the one kept.
- **Release times** come from the USDA notice of 19-Sep-2012 (https://www.usda.gov/sites/default/files/documents/USDA_Release_time_change_9_19_12.pdf):
  - NASS and WASDE were released at **08:30 ET until 2012** and at **12:00 ET from 11-Jan-2013**. The report texts carry no clock time; Quick Stats load times (about 12:00–12:27 on report days since 2013) agree with the notice.
  - Crop Progress: 16:00 ET. The date is the ESMIS release date (a Tuesday after Monday holidays). It is assumed to be the Monday after the week-ending date for 14% of rows, which are not in the calendar.
- **No look-ahead.** For each report, the "previous USDA" and the crop-condition features use only releases stamped strictly before it.

## Sources and coverage

| Source | URL | Coverage obtained |
|---|---|---|
| NASS Crop Production and Crop Production Annual Summary, text reports from the ESMIS archive (usda.library.cornell.edu now redirects to esmis.nal.usda.gov) | https://esmis.nal.usda.gov/publication/crop-production , …/crop-production-annual-summary | **Aug, Sep, Oct, Nov 2005–2026: 85 of 88 reports.** Oct-2013 and Oct-2025 were cancelled by government shutdowns; Nov-2026 has not been released yet. **January finals 2005–2026: 22**, for crop years 2004–2025 (the 2019 one came out on 8-Feb-2019). National values and **every state**: all 12 requested states (IA IL NE MN IN OH SD ND KS MO WI MI) appear in all 85 forecast reports. Variables: harvested area, yield, production. |
| NASS Acreage and Prospective Plantings (ESMIS) | …/publication/acreage , …/publication/prospective-plantings | 2005–2026: 22 + 22 reports, national and state. |
| NASS Quick Stats | API https://quickstats.nass.usda.gov/api returns `401 unauthorized` without a key, so the **free bulk file** https://www.nass.usda.gov/datasets/qs.crops_20261010.txt.gz (1.1 GB) was used instead | Weekly crop condition, 2000–2026. Also a cross-check: on all **12,619** state × report cells that overlap, the forecasts from the parsed text reports equal Quick Stats' "YEAR – AUG/SEP/OCT/NOV FORECAST" records. Quick Stats "YEAR" values are revised later, so they are *not* used as vintages. |
| WASDE US corn and soybean balance sheets | OCE historical CSVs, Apr-2010 to Sep-2026 (https://usda.azureedge.us/historical-wasde-report-data-3 , mirror of the usda.gov WASDE page); ESMIS text reports for 2005 to Mar-2010 and Oct-2026 | **237 reports, Jan-2005 to Oct-2026.** Before 2010 only the months Jan and May–Nov were downloaded. Used for the previous-USDA number in August (the July projection) and for ending stocks. |
| Trade consensus (average analyst estimate) | Listed per value in `consensus_raw.csv`. Main sources: WILL Agri-Newsline PDFs (https://will.illinois.edu/nfs/WANLyymmdd.pdf, 2013–2015), farmdoc webinar decks (2017–2020, plus the August bar charts back to 1996/97), Reuters polls (TradingView, Producer.com, Grainews and Pro Farmer copies), Bloomberg (BNN Bloomberg, Pro Farmer), and World-Grain / Food Business News, DTN, Farm Progress, MarketsFarm, ADMIS, AgOptimus | See the next table. |
| CBOT prices | Yahoo chart API, `https://query1.finance.yahoo.com/v8/finance/chart/<sym>` | ZC=F and ZS=F, daily 2000–2026. ZCZ26, ZSX26, ZSX25, ZCH27 and ZSF27 individual contracts. Teucrium CORN (from 2010-06) and SOYB (from 2011-09). 60-minute bars, Oct-2024 to Oct-2026. |

**Consensus coverage.** These are reports with a consensus, counted per crop. The yield-or-production column is what the regressions use.

| Report | Yield consensus | Production consensus | Yield or production (regressions) |
|---|---|---|---|
| August | 2013–2026 (14 corn, 13 soy) | 2005–2026 (18 / 18) | **2005–2026: 22 corn, 22 soy** |
| September | 2013–2026 (14 / 14) | 2012–2026 (10 / 9) | **2012–2026: 15 / 15** |
| October | 2014–2024 (11 / 10) | 2014–2026 (9 / 10) | 12 / 11 |
| November | 2013–2025 (9 / 10) | 2013–2023 (7 / 6) | 9 / 10 |
| January | 2014–2026 (6 / 6) | 2014–2023 (5 / 4) | 6 / 6 |

- **Implied yield consensus.** Where only a production consensus exists, the yield consensus is taken as production consensus ÷ USDA harvested area. This is valid when the report leaves area unchanged, which is the normal case in August. It covers 8 August corn and 9 August soy events, mostly 2005–2012.
- **Implied production consensus, 2005–2011.** These August values are USDA production minus farmdoc's published "USDA minus average trade guess" bar.

## Coverage gaps and caveats

1. **How the consensus values were captured.**
   - 87 of the 203 chosen values were read directly from the PDF or page: WILL newsletters, farmdoc decks, the Reuters table on TradingView, Pro Farmer and AgOptimus.
   - 116 come from web-search snippets quoting the cited article. Reuters, World-Grain and the like block scripted access with a 403 or a paywall.
   - The snippet values agree with the directly read ones wherever both exist: 27 pairs, median absolute difference 0.0%, maximum 0.64%, for example 2012-08 corn production 10,971 in both.
   - Polls differ (Reuters, Bloomberg, Dow Jones/WSJ, farmdoc's average). Where several exist the order of preference is Reuters > WILL > farmdoc > Bloomberg > Dow Jones > World-Grain/FBN > other. The alternatives are kept in `consensus.csv`.
   - Two values are approximate: Jan-2026 was described only as "a cut of about 2 bu (corn) / 0.3 bu (soy) expected".
2. **Consensus not found:**
   - yield consensus for August/September before 2013. 2012 has production only, and 2005–2011 has August production only, from the farmdoc bars.
   - September before 2012.
   - Oct-2020 production; Nov-2018, Nov-2020 and Nov-2024; Jan-2016, Jan-2018 (corn), Jan-2019, Jan-2021, Jan-2022, Jan-2024 and Jan-2025.
   - Most October/November/January reports before 2013.
3. **Prices: no historical individual contracts.**
   - Yahoo serves only live and very recently expired contracts. ZCZ24, ZCZ25 and ZSX24 return "No data found"; ZSX25 still works.
   - CME settlement pages block scripts, Stooq resets the connection, and Nasdaq Data Link (CHRIS), MarketWatch and Investing.com refuse access.
   - **The continuous series is the wrong contract on most report days.** In early August ZS=F is the expiring August contract. On September report days ZC=F and ZS=F are the September contracts in delivery. Both trade under 20% of normal volume, so their returns are stale; ZC=F shows 0.00% on 12-Sep-2025, for example.
   - **The main return series is therefore the Teucrium ETF** (CORN from 2010, SOYB from 2011). It holds the second and third contracts plus the next December (corn) or November (soy), so it is roll-free and weighted toward new crop.
     - It closes at 16:00 ET, after the 14:15 ET settlement.
     - On the 9 event days where the true new-crop contract exists, ETF returns are 0.7–1.0× the contract's and have the same sign every time (`proxy_tracking_event_days.csv`). In-season daily correlation is 0.95. So ETF-based slopes are, if anything, slightly attenuated.
   - **Before the ETFs existed**, the continuous future is used only on days when it is liquid: volume at least 20% of its 60-day median, and not a roll day. That keeps August corn (Sep contract) and October soybeans and corn for 2005–2011. It drops August and September soybeans and September corn for those years.
   - For 2025–26 the regressions are rerun with the true new-crop contract (`newcrop_override_pct` in `summary_reaction.csv`). Results are unchanged.
4. **Intraday.**
   - Free 60-minute bars exist only for the last 730 days. Yahoo's intraday ZC=F and ZS=F appear to be remapped to the current front month, so only the individual contracts are used.
   - On the 6 reports where the contract was new crop (Aug, Sep and Oct 2026), about half of the absolute close-to-close move happened before 12:00 ET (`intraday_check.csv`). Close-to-close returns therefore include pre-report noise.
   - No free 1-minute data around 12:00 ET was found.
5. **Other report days are not separated out:**
   - The Crop Production days also carry the WASDE: US demand changes and world numbers.
   - The January and October reports coincide with Grain Stocks (Jan) or follow end-September stocks (Oct). This is why January and October variance ratios are so high and why the January revision slope is large.
6. **Normal days** exclude every WASDE, Crop Production, Acreage, Prospective Plantings and Grain Stocks day, and the roll days. Crop Progress days are kept as normal days.

## Method

- **Event day.** This is the release date. Since 2013 the release comes at noon during the CBOT session; before 2013 it came at 08:30 ET, before the 09:30 ET open. Either way the day's settlement is the first one after the report.
  - The return is the close-to-close log return in %.
  - Cents/bu = return × the previous settlement of the continuous future. For 2025–26 events the new-crop contract's settlement is used.
- **Surprises:**
  - Surprise vs consensus = USDA − consensus, in bu/acre and in % of consensus. The production surprise is in % of the consensus.
  - Revision = USDA − previous USDA. For August the previous USDA is the latest WASDE (the July trend or weather-adjusted yield); for Sep–Nov it is the previous Crop Production; for January it is the November forecast.
  - Expected revision = consensus − previous USDA.
- **(a) Variance.** Variance of report-day returns ÷ variance on normal days in the same calendar month and the same years, with a Brown–Forsythe/Levene test.
- **(b, c) Regressions.** OLS with HC1 standard errors, return on the surprise, run per crop and per report month, plus pooled Aug+Sep, Aug–Nov and all reports. Revision and production specifications are included, and a "horse race" regresses the return on the surprise plus the expected revision.
- **(d) Predictability.** The targets are the surprise vs consensus, and for comparison the revision vs previous USDA. Features are all public before the release:
  - the historical mean, in a constant-only model;
  - the analysts' expected revision;
  - the previous USDA revision;
  - the change in national good/excellent rating since the previous USDA report;
  - good/excellent minus its same-week mean over the previous 10 years.

  Fit is OLS, scored with leave-one-crop-year-out out-of-sample R², sign hit rate and correlation.
- **(e) Value of the sign.**
  - Enter at the close before the report: long if USDA comes in below consensus, short if above. Exit at the report-day close.
  - Costs are 0.6 ¢/bu round trip ($30 per 5,000-bu contract): $5 commission and fees plus one tick (¼ ¢) of slippage on entry and on exit.
  - The comparison rules are: trade only surprises larger than the median, perfect foresight of the return sign (upper bound), and the sign predicted by the public-information model (leave-one-year-out).

## Findings

### (a) US reports move CBOT

`results/variance_ratio.csv`, fig3. Main return series, normal days in the same month and years:

| Report | Corn VR | Soy VR | sd report / normal (corn) | sd report / normal (soy) |
|---|---|---|---|---|
| August | 3.8 (n 22) | 4.0 (n 15) | 2.89% / 1.49% | 2.37% / 1.18% |
| September | 1.9 (n 18) | 4.0 (n 16) | 1.61% / 1.17% | 1.88% / 0.94% |
| October | 5.9 | 4.6 | 4.08% / 1.67% | 2.93% / 1.37% |
| November | 1.7 | 2.5 | 1.73% / 1.33% | 1.59% / 1.01% |
| January | 8.9 | 3.0 | 3.76% / 1.26% | 1.82% / 1.06% |

All Levene p-values are below 0.05. For comparison, Brazil-only revision days had a variance ratio of 0.5–0.9 in the Brazil study.

### (b) The surprise vs consensus drives the reaction

From `results/summary_reaction.csv`; figs 1–2:

| Crop | Reports | n | %/1% surprise (t) | %/bu-acre (t) | ¢/bu per bu-acre (t) | R² |
|---|---|---|---|---|---|---|
| Corn | Aug | 22 | −0.90 (−2.7) | −0.57 (−3.0) | −2.4 (−2.7) | 0.26 |
| Corn | Sep | 15 | −0.85 (−1.8) | −0.73 (−2.4) | −3.4 (−3.3) | 0.18 |
| Corn | Aug+Sep | 37 | −0.88 (−3.1) | −0.58 (−3.4) | −2.5 (−3.1) | 0.24 |
| Corn | Aug–Nov | 58 | −0.88 (−3.5) | −0.57 (−4.0) | −2.5 (−3.7) | 0.22 |
| Soy | Aug | 15 | −0.64 (−2.9) | −1.35 (−2.6) | −14.8 (−2.8) | 0.44 |
| Soy | Sep | 15 | −0.83 (−2.7) | −1.70 (−2.9) | −25.0 (−2.9) | 0.25 |
| Soy | Aug+Sep | 30 | −0.71 (−3.4) | −1.50 (−3.4) | −17.7 (−3.6) | 0.37 |
| Soy | Oct / Nov | 11 / 10 | −0.2 (−0.2) / −0.1 (−0.2) | — | — | ≈0 |

- **The elasticity is close to −1.** A yield surprise of 1% moves the new-crop price by roughly −0.7% to −0.9% on the day.
- **A 1 bu/acre surprise** is worth about 2.5 ¢/bu in corn, roughly $125 a contract. In soybeans it is about 18 ¢/bu.
- **Typical surprise sizes.** The standard deviation of the August surprise is 1.6% for corn (about 3 bu) and 2.6% for soybeans (about 1.3 bu).
- **Largest moves:**
  - corn 2006-08 (+1.4% surprise, −6.0%);
  - corn 2019-08 (+2.8% surprise, −5.7%);
  - soy 2015-08 (+4.7% surprise, −5.4%);
  - soy 2018-08 (+4.0% surprise, −4.3%).
- **Robustness:**
  - Using the production surprise gives the same picture: corn Aug+Sep −0.75%/1%, t −3.5; soy −0.56, t −2.4.
  - So does replacing the ETF with the true new-crop contract for 2025–26.
- **October and November soybeans show no reaction.** Those surprises are small (sd 0.7–0.9%) and the harvest is mostly known by then.

### (c) Surprise vs previous USDA

- **August.** The revision from July is unrelated to the report-day return: corn −0.05%/1%, t −0.4, R² 0.005; soy −0.21, t −1.7. The consensus already anticipates most of the revision. The analysts' expected revision explains 85% (corn) and 57% (soy) of the actual August revision out of sample.
- **Horse race.** Holding the expected revision fixed, the surprise keeps its slope: corn Aug −1.10, t −3.3; soy Aug −0.88, t −4.8.
- **September, October (corn) and January.** Revisions vs the previous USDA do correlate with returns: corn Sep −0.68, t −3.6; Oct −2.4, t −3.9; Jan −2.3, t −4.1. These reports also carry stocks and area changes that the yield consensus does not capture, so the residual surprise is still what matters for a trader.

### (d) Free public information barely predicts the surprise

`results/surprise_predictability.csv`, fig4.

- **Out of sample (leave-one-year-out) R²** for the surprise vs consensus:
  - Corn: −0.15 to +0.04 in August, negative in September, about 0 for Aug–Nov pooled.
  - Soybeans: best is +0.10 in August (good/excellent vs normal) and +0.08 in September (all features combined). Aug–Nov pooled is +0.01 to +0.06.
- **Sign hit rates do not beat the base rates.**
- **The one free regularity is a bias: USDA tends to come in above the trade.**

  | Report | Mean surprise | Share of reports where USDA beat the consensus |
  |---|---|---|
  | Corn, August | +0.6% | 64% |
  | Corn, September | +0.8% | 93% (14 of 15) |
  | Soybeans, September | +0.7% | 73% |

  A constant-sign rule gets these hit rates. Trading on it does not pay: September corn net −0.06 ¢/bu. In September the return is unrelated to the sign, even though it moves with the size.
- **Crop condition** strongly predicts the *revision* vs the previous USDA:
  - good/excellent vs normal: LOYO R² 0.51 for corn in August;
  - good/excellent change: LOYO R² 0.33 for soybeans in September.

  The consensus has already absorbed this.
- **The baseline a satellite signal must beat:** out-of-sample R² of about 0 (corn) and up to about 0.1 (soybeans) for the surprise vs consensus, and a sign hit rate above the base rate (about 64% for August corn and about 50% for August soybeans).

### (e) What knowing the sign one day early is worth

`results/sign_knowledge_edge.csv`, fig5. All figures are net of 0.6 ¢/bu:

| Crop | Rule | n | Hit rate | Net ¢/bu | Net % | t | $/contract |
|---|---|---|---|---|---|---|---|
| Corn | Aug, know sign | 22 | 59% | +4.5 | +1.17 | 2.1 | +227 |
| Corn | Aug+Sep, know sign | 36 | 58% | +2.8 | +0.68 | 1.8 | +138 |
| Corn | Aug+Sep, surprise above the median | 18 | 78% | +6.8 | +1.72 | 3.2 | +342 |
| Corn | Aug+Sep, perfect foresight of the return | 36 | 100% | +7.5 | +1.82 | 7.6 | +377 |
| Corn | Aug+Sep, public-info model | 36 | 47% | −1.0 | +0.01 | 0.0 | −51 |
| Soy | Aug, know sign | 15 | 60% | +11.1 | +1.05 | 1.9 | +554 |
| Soy | Aug+Sep, know sign | 30 | 53% | +7.2 | +0.57 | 1.5 | +359 |
| Soy | Aug+Sep, surprise above the median | 15 | 73% | +16.7 | +1.41 | 2.4 | +837 |
| Soy | Aug+Sep, perfect foresight of the return | 30 | 97% | +19.4 | +1.69 | 7.0 | +971 |
| Soy | Aug+Sep, public-info model | 30 | 47% | −3.9 | −0.29 | −0.7 | −193 |

- **Knowing the sign alone captures about a third of the perfect-foresight value.** The hit rate is only 53–59% because small surprises are swamped by other news in the report and by pre-report noise.
- **Knowing the sign of a large surprise is worth about 7 ¢/bu (corn) and 17 ¢/bu (soy) per report.**
- **Costs are small next to that.** At 0.6 ¢/bu they are about 0.15% of the corn price and 0.06% of the soy price. The real hurdle is accuracy, not costs.
- **What this means for the satellite signal.** It has to call the sign of USDA minus consensus correctly, especially when the surprise is large, more often than the 64% (corn) and 50% (soy) base rates in August.

## Reproduce

```bash
cd soy_research/us/benchmark
scripts/run_all.sh /path/for/raw/downloads   # ~10 min plus the 1.1 GB Quick Stats download
```

- **Hand-collected inputs** stay in the repo: `data/consensus/consensus_raw.csv` and `data/reference/farmdoc_decks.csv`. Fetching the farmdoc decks needs a plain HTTPS client. The WILL newsletters were fetched with a browser-like client, because curl hits a redirect loop there, and are cited by URL.
- **Dependencies**: pandas, numpy, scipy, statsmodels, matplotlib, pyarrow, and pdftotext (poppler).
- **Untrusted data.** Every downloaded file is treated as untrusted and read with `python -I`. Raw files stay outside the repo.
