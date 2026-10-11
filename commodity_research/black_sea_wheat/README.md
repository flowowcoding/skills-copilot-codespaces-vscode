# Black Sea wheat: can free satellite + weather data front-run USDA on Russia, Ukraine and Kazakhstan?

Hypothesis tested: markets with **weaker official data** are easier to beat with free imagery than the US
(where `soy_research/us/` failed) or Brazil. Russia is the world's largest wheat exporter and USDA's Russia
numbers are revised far more than its US numbers, so if free data can lead anyone, it should be here.

## Pre-registration (written 2026-10-11 04:25 UTC, before any holdout evaluation; not edited afterwards)

**Periods.** Development: crop years 2008–2020 (walk-forward; training years from 2003, always
< the forecast year). **Holdout: 2021–2025.** Live: 2026 (USDA's 2026 numbers exist up to the
9-Oct-2026 WASDE; the final arrives in 2027–28). `evaluate.py` scores only development rows unless it is
run with `--holdout`.

**Frozen spec** (sha256 prefixes): `model.py` be3a05a3d89be725, `build_features.py` 797862d2a66acaa4, `evaluate.py` 6079a11438992cb9, `extract_modis.py` 9d487ff6b84733c2, `build_frame.py` e40e24542419005f, `sample_worldcereal.py` 9099dcad95697e92, `fetch_weather.py` 2edf77fb85fbc418, `clean_private_estimates.py` ed7ce6f5861f575a, `parse_wasde_wheat.py` 8046d9535a5470da; signal `bsw_signal_v1.csv` a431befd63d4d617. In words (full detail in the `model.py` docstring):

- **Unit**: country (Russia, Ukraine, Kazakhstan) × crop year × forecast date. Forecast dates: the day
  before every WASDE from May(Y) to Jan(Y+1), plus weekly dates Apr 1 + 7k (to Dec 30).
- **Inputs at T**: Aqua MYD13Q1 composites with end + 14 d ≤ T; NASA POWER days ≤ T − 5; winter mask
  w121 once its composites are usable, else w89 (thresholds calibrated once on WorldCereal 2021);
  truth = latest USDA estimate published before T.
- **Features** (country = cropland-weighted mean over regions): `evi_w` (detrended winter-mask EVI anomaly
  over usable composites, autumn Y−1 to mid-July), `prcp_w`, `hdd_w`, `frost_w` (winter zones), `evi_s`,
  `prcp_s`, `hdd_s` (spring-wheat regions only).
- **Target**: ln(truth / trend), trend = Theil–Sen over the 15 previous crop years.
- **Model**: pooled ridge (α = 3) over the three countries, features z-scored within country on the
  training years, unpenalised country intercepts; Ukraine 2022+ excluded from training (war).
- **Estimate** S = trend × exp(prediction); uncertainty = training leave-one-year-out RMSE.

**Tests, fixed in advance** (holdout 2021–2025 is the test; development numbers are reported alongside):

- **(a) Revision test, Russia.** At the day before each WASDE (May–Jan), regress USDA's revision at that
  WASDE, 100·ln(USDA_new / USDA_prev), on the gap 100·ln(S / USDA_prev) and on the previous USDA
  revision (persistence). OLS, crop-year clustered t. **Success: gap slope > 0 with t > 2 AND sign hit
  rate > 60 % when |gap| > 3 %.** Also reported: the pooled three-country version (Ukraine 2022+ excluded)
  and the version adding the private (IKAR/SovEcon/ministry) gap as a control.
- **(b) Lead weeks.** In every country-year with |USDA final − USDA's first (May) estimate| ≥ 5 %
  (Ukraine 2022+ excluded), the first weekly date at which S is ≥ 5 % away from USDA's first estimate in
  the direction of the final, vs the first WASDE that is, vs (Russia) the first private estimate that is.
  **Success: median lead over USDA ≥ 2 weeks in the holdout, with S on the correct side at USDA's crossing
  date in most cases.** False alarms (crossings in the wrong direction / in years without a big change)
  reported.
- **(c) Prices.** (i) WASDE day, Russia May–Dec reports with |gap| ≥ 2 %: long ZW when S is below USDA,
  short when above, from the close before the report to the report-day close, net of 0.6 ¢/bu.
  (ii) Weekly Russia signals Apr–Sep, same rule, hold 10 trading days (5, 15, 20 also reported),
  non-overlapping, net of costs. KE and the roll-free WEAT ETF (10 bp) reported too. **Success: ZW net
  mean > 0 with t > 2 for (i) and for (ii) at 10 days.**
- **Secondary**: weather-only variant (`v1_wx`: prcp/hdd/frost features only) to show what the
  satellite adds; error vs the final by report month against trend and USDA.

Any test that cannot be computed (too few cases) is reported as such, not replaced.

**Disclosure (what was seen before this was written).**
1. A first coded spec (`v0_first`: no target scaling, no winsorising) was run on all years and
   evaluated on **development rows only**. While debugging it, the Russia September-WASDE rows were
   printed for **every year including 2021–2026** (estimate, trend, USDA, final), i.e. 6 Russian
   holdout/live numbers of that version were seen. No Ukraine/Kazakhstan holdout numbers, no holdout
   test statistics and no holdout prices were looked at.
2. Two changes were then made, both motivated by development diagnostics: (i) the target is scaled
   by its within-country training sd before the pooled fit (the volatile Kazakh/Ukrainian targets were
   setting the coefficients applied to Russia), and (ii) z-scored features are winsorised at ±3 (a
   2.95-sd May-2009 frost reading and an 11-sd 2010 heat reading produced −46 % / −27 % swings with only
   6–7 training years). The `v1` development run was then evaluated (dev only) and the lead test (b)
   was redefined from "level crossing vs USDA's first number" to "each source's own move after USDA's
   first report", because the level version credited the satellite with leads from 1 April in nearly
   every year (the pre-season trend differs from USDA's May number), which measures nothing.
3. Development results of `v1` that were seen: Russia mean |error| vs final 15.1 % (trend 16.6 %,
   USDA latest 6.8 %); Ukraine 36 % (trend 15 %); test (a) Russia gap slope +0.03 (t 1.2), +0.11
   (t 2.1) with the private control; WASDE-day ZW net −0.03 %/trade; weekly ZW 10-day net −0.15 %.
   These were not good, and the spec was frozen anyway rather than tuned further.
4. For transparency `v0_first` is also scored on the holdout.


## Results (holdout 2021–2025, scored after the pre-registration above)

**Headline: the weak-benchmark premise is true, but it does not translate into a usable free-satellite
edge.** USDA's Russia numbers are 2–2.5× noisier than its US numbers, yet USDA simply follows IKAR/SovEcon
with about a one-month lag, those analysts are what the market prices, and the satellite + weather
model is less accurate than a plain trend in the holdout. Three of the four pre-registered criteria pass
on paper, but each pass has a simpler explanation (below), so this is **not** a signal to trade.

### Pre-registered criteria

| Test | Criterion | Development 2008–20 | **Holdout 2021–25** | Verdict |
|---|---|---|---|---|
| (a) Russia: USDA's next revision on satellite − USDA, controlling for persistence | slope > 0, t > 2, sign hit > 60 % | +0.029 (t 1.2), hit 62 % (n 53) | **+0.111 (t 3.1)**, hit 69 % (n 16) | pass on paper: 34 reports, 5 crop-year clusters |
| (a′) same, adding private (IKAR/SovEcon/ministry) − USDA | (reported) | +0.110 (t 2.1), private +0.51 (t 3.2) | **+0.019 (t 0.2)**, private +0.59 (t 1.7) | **satellite adds nothing beyond the analysts** |
| (b) lead over USDA in big-change country-years | median ≥ 2 weeks, on the right side at USDA's move | 8.6 weeks (30 of 34), right side 57 % | **12.0 weeks** (9 of 11), right side 89 % | pass on paper; the weather-only model gets the same 12 weeks |
| (c-i) WASDE day, ZW, net of 0.6 ¢/bu | mean > 0, t > 2 | −0.03 %/trade (t −0.1, n 78) | **+1.01 %** (t 2.8, n 28, hit 75 %) | pass on paper: 22 of 28 trades were shorts in the 2022–25 bear market |
| (c-ii) weekly signal, hold 10 trading days, ZW net | mean > 0, t > 2 | −0.15 % (t −0.3, n 122) | **+1.17 %** (t 1.2, n 44) | **fail** |

### Accuracy vs the USDA final (Russia, mean |error|, % of final, day before each WASDE)

| Report month | May | Jun | Jul | Aug | Sep | Oct | Nov–Jan |
|---|---|---|---|---|---|---|---|
| Satellite, dev / **holdout** | 23.7 / **8.1** | 19.0 / **12.4** | 18.6 / **9.9** | 12.7 / **11.6** | 12.4 / **11.9** | 10.5 / **12.3** | 12.5–13.4 / **12.2** |
| Trend, dev / holdout | 16.5 / 9.2 | 16.5 / 9.2 | 16.5 / 9.2 | 16.5 / 9.2 | 16.5 / 9.2 | 16.6 / 9.8 | 16.5–17.8 / 9.2 |
| USDA (latest), dev / holdout | — | 15.4 / 10.6 | 13.8 / 8.7 | 11.2 / 8.2 | 5.6 / 4.8 | 3.1 / 3.4 | 1.2–2.3 / 1.3–3.6 |

All reports: Russia satellite 15.1 % dev / **11.4 %** holdout vs trend 16.6 / **9.2** and USDA 6.8 / **5.3**.
Kazakhstan 18.6 / **15.3** vs trend 22.2 / 22.2 and USDA 12.6 / 14.0 (the one place the satellite beats
trend in both periods). Ukraine 36 / 45 (holdout = 2021 only; war years excluded) vs trend 15 / 8: the
Ukrainian model is broken by a poor 15-year trend through the 1990s–2000s collapse and winter-mask noise.
`results/accuracy_v1_holdout.csv`, `figures/fig_accuracy_{dev,holdout}_v1_holdout.png`.

### Why each "pass" is weaker than it looks

- **(a)** The satellite's revision signal disappears once IKAR/SovEcon are in the regression
  (`results/test_a_revision_v1_holdout.csv`, `figures/fig_gap_test_v1_holdout.png`). USDA's Russia
  revisions are predicted by the analysts (benchmark: slope 0.69, t 6.0); a satellite estimate that
  partly agrees with them inherits that, nothing more. Five clusters make any t-stat fragile.
- **(b)** The weekly satellite series is noisy: it moves ≥ 5 % away from its own May value in *every*
  country-year, in the eventual direction in 62 % of development years and 90 % of holdout years
  (`results/test_b_alarms_v1_holdout.csv`). The weather-only variant reaches the same 12-week median.
  Against the analysts (Russia, where both moved): satellite earlier by 17 weeks (2021) and 11 weeks
  (2025), later by 1 week (2022) and 3 weeks (2024); in 2023 the satellite never registered the upside.
- **(c-i)** On the same holdout WASDE days an always-short rule earned +0.32 %/report (t 0.8), the
  persistence rule (sign of USDA's previous Russia revision) +1.24 % (t 2.1, n 15), the weather-only
  model +0.79 % (t 2.4) and the first-coded spec +1.17 % (t 3.6), while in development every variant was
  ≤ 0. The satellite sat above USDA in most 2022–25 reports (a positive bias from a high trend), and
  wheat fell on report days. A regime, not a signal. Dev + holdout combined: +0.25 %/trade (t 1.1, n 106).
- Slopes of 5–20-day forward returns on the gap are insignificant and change sign between periods
  (dev +0.02 %/pt, holdout −0.05 %/pt for 10 days on ZW).

### Lead weeks in the named shock seasons (Russia; each source's own ≥ 5 % move after USDA's May number)

| Season | USDA first → final | Satellite moved | USDA moved | Analysts moved | Satellite lead over USDA | Notes |
|---|---|---|---|---|---|---|
| 2010 drought + export ban | 58 → 41.5 (−28 %) | 27 May (a June dip to 37 Mt, then 11–21 % *above* USDA in July; down to 46.5 on 5 Aug) | 9 Jul | 7 Jul (IKAR) | 6 wk on paper; 1 wk for the move that stuck (46.5 on 5 Aug vs USDA 45 on 12 Aug) | SovEcon 50 on ~20 Jul, 43.5 on 9 Aug |
| 2012 drought | 56 → 37.7 (−33 %) | 13 May | 12 Jun | 28 Jun (IKAR) | 4 wk | the satellite's clearest hit (south + Volga EVI −0.04) |
| 2018 | 72 → 71.7 (−0.4 %) | — | — | — | not a big-change year for USDA | cold wet Siberia/Urals; USDA cut to 68.5 in June then went back up |
| 2021 (export tax year) | 85 → 75.2 (−12 %) | 20 May | 12 Aug | 16 Sep | 12 wk | satellite 12–24 % below USDA from 20 May to 5 Aug (overshooting: 67.5 Mt in July); the clearest holdout hit |
| 2024 May frosts + southern drought | 88 → 81.6 (−7 %) | 3 Jun | 12 Jun | 13 May (IKAR) | 1 wk, and back above USDA a week later | **analysts led the satellite by 3 weeks**; the satellite then sat 2–12 % above USDA from mid-June to the end of the season (frosts were local; MERRA-2 0.5° Tmin barely shows them) |
| 2025 | 83 → 90.3 (+9 %) | 20 May | 9 Dec | 8 Aug (ministry 89–90) | 29 wk | right direction; Aqua archive ends 26 Jun 2025, so June–Sep 2025 used weather only |

Figures: `figures/fig_russia_{2010,2012,2018,2021,2024,2025,2026}.png` (weekly estimate with ±1 LOYO-RMSE
band, USDA steps, IKAR and SovEcon points).

**Ukraine 2022+.** Excluded from training and from every pooled metric (occupied territory and area loss;
USDA excludes Crimea and its post-2022 definition of controlled area changes). Signal rows are kept with
`ukraine_war_flag = 1` for reference only.

**2026 (live).** Not a usable call: the Planetary Computer Aqua archive lacks composites DOY 121–169 and 233
of 2026 and the autumn-2025 composites, so the winter mask falls back to the early-April definition and
the EVI anomaly uses 1–3 composites; the model says 118–121 Mt for Russia vs USDA 88 Mt (weather-only
variant: 103 Mt). It will be scored against USDA's 2027–28 final but should be read as a data-gap failure.

### What the satellite adds to weather (secondary, `v1_wx`)

Russia mean |error|: weather-only 20.8 % dev / 11.8 % holdout vs satellite + weather 15.1 / 11.4. The
satellite helps in development (and in Kazakhstan: 18.5 → 15.3 % holdout) but not materially in the
Russian holdout. Weather-only test (a) slope: −0.016 (t −2.2) dev, +0.077 (t 1.0) holdout.


## Data obtained (all free, all point-in-time)

| Item | Source | Coverage | Point-in-time rule |
|---|---|---|---|
| USDA WASDE wheat balance sheets (Russia, Ukraine, Kazakhstan, US, EU, World, …) | OCE historical CSVs Apr-2010+ (https://usda.azureedge.us/historical-wasde-report-data-3, mirror of the usda.gov WASDE page); ESMIS (Cornell/NAL) text reports 2004–Mar-2010 (https://esmis.nal.usda.gov/publication/world-agricultural-supply-and-demand-estimates) | **269 reports, Mar-2004 → Oct-2026** (Oct-2013, Jan-2019, Oct-2025 not published; re-posted duplicates and the "Revised" Oct-2008 report dropped in favour of the original). Text and CSV parsers agree on all 1,260 overlapping cells. | release date, 08:30 ET until 2013-01-10, 12:00 ET after |
| Final outturns | USDA last WASDE vintage (truth, excludes Crimea); FAOSTAT QCL bulk (Rosstat/Ukrstat/KZ stat); USDA PSD current | 1995–2026 | truth used only ex post |
| Private / ministry Russian estimates | IKAR "in Mass Media" archive (https://ikar.ru/1/en/press/, Reuters/Interfax/Bloomberg/S&P reposts) scraped (3,906 items, 807 crop-related read); dateline parsed; reviewed; plus 10 web-search additions for 2010, 2018, May-2024 | **123 dated estimates** (IKAR 85, SovEcon 32, ministry 5, Rusagrotrans 1), crop years 2010–2026; densest 2019–2025 | article date (dateline when the repost lags) |
| Prices | Yahoo chart API (browser UA): ZW=F, KE=F (2000–2026), Teucrium WEAT ETF (2011-09–2026, roll-free), USD/RUB | daily | roll days flagged and dropped |
| Euronext/Matif milling wheat | Yahoo `EBM=F` returns only the latest session; Euronext/Barchart history needs a login | **not obtained** | — |
| Cropland frame | ESA WorldCover 2021 v200 (Planetary Computer `esa-worldcover`), 80 m overview binned to MODIS 250 m cells | 26.3 M cells ≥ 75 % cropland in 8 regions; 24,000 sampled (3,000 per region) | static map, no yield information |
| Winter / spring cereals | ESA WorldCereal 2021 v100 (Zenodo 7875105), 10 m winter-cereals and spring-cereals classifications, streamed per agro-ecological zone out of the 7–19 GB zips with HTTP range requests | sampled at the pixels in the winter-wheat AEZs (6136, 22095, 22096, 22190, 22194) and spring AEZs (17135, 22194, 22095) | used once, to calibrate a spectral threshold |
| Vegetation | **Aqua** MODIS MYD13Q1 v061 EVI + pixel reliability (Planetary Computer `modis-13Q1-061`), 10 tiles h19–h23 v03–v04 | 2002–2026, composites DOY 73–249 + autumn DOY 281/297 | composite end + 14 days |
| Weather | NASA POWER daily point API (MERRA-2 / IMERG blend): Tmax, Tmin, bias-corrected precipitation, snow depth | 393 one-degree cells, 2001-01-01 → 2026-10-07 | day d used from d + 5 |

Why not the alternatives:
- **CHIRPS** stops at 50°N. 66 % of the sample (all of RU_Volga, RU_UralsSiberia, KZ_North, 98 % of
  RU_Central, 38 % of UA_CentralNorth) lies north of 50°N (`figures/map_frame.png`), so it cannot be used.
- **ERA5** on Planetary Computer ends in 2024.
- **Open-Meteo**'s free tier counts a 26-year multi-point pull as thousands of calls.
- **Terra** MODIS: orbit drift (the Brazil failure). Aqua only.
- **Rosstat regional statistics** and **Ukrstat**: rosstat.gov.ru and ukrstat.gov.ua are blocked by this
  environment's egress proxy and fedstat.ru answers HTTP 403, so there is **no regional yield truth**. Regions enter only as
  feature aggregates; the model is fitted at country level.

## Regions and masks

`scripts/build_frame.py` groups Natural Earth admin-1 units:

| Region | Oblasts | Wheat type |
|---|---|---|
| RU_South | Krasnodar, Rostov, Stavropol, Volgograd, Kalmykia, Astrakhan, Adygea, N. Caucasus republics | winter |
| RU_Central | Central Federal District (Belgorod, Voronezh, Kursk, Lipetsk, Tambov, Oryol, Tula, …) | winter |
| RU_Volga | Volga FD (Saratov, Samara, Orenburg, Bashkortostan, Tatarstan, Ulyanovsk, Penza, …) | winter + spring |
| RU_UralsSiberia | Kurgan, Chelyabinsk, Tyumen, Omsk, Novosibirsk, Altai Krai, Kemerovo, Krasnoyarsk, … | spring |
| UA_South | Odesa, Mykolaiv, Kherson, Zaporizhzhia, Dnipropetrovsk, Donetsk, Luhansk | winter |
| UA_CentralNorth | the rest of Ukraine (Crimea excluded everywhere) | winter |
| KZ_North | Kostanay, North Kazakhstan, Akmola, Pavlodar | spring |
| KZ_Other | Aktobe, West Kazakhstan, Karaganda, East Kazakhstan | spring |

Masks (there is no CDL equivalent):
1. **Frame**: MODIS 250 m cells with ≥ 75 % WorldCover-2021 cropland (`figures/map_frame.png`).
2. **Winter crop in year Y**: EVI in spring before spring-sown crops emerge — DOY 89 composite (Mar 30–Apr 14,
   usable ~Apr 28) or max of DOY 105/121 (Apr 15–May 16, usable ~May 30) — above a threshold calibrated on
   WorldCereal 2021 winter cereals (`results/mask_calibration.csv`, `figures/map_worldcereal.png`,
   `figures/map_masks_2021.png`). The mask changes every year, so crop rotation is followed.
3. **Spring crop** = frame cell not in the winter mask. In the spring-wheat regions (RU_Volga, RU_UralsSiberia,
   KZ) this is mostly spring cereals; elsewhere it is sunflower/maize, so spring features are only built for
   those four regions.

Mask diagnostics (`results/mask_calibration.csv`): against WorldCereal 2021 (cells ≥ 60 % vs ≤ 20 %
winter cereals) the spring-EVI threshold separates winter crops with balanced accuracy **0.88** in the
south (threshold EVI 0.365 on max(DOY 105, 121); 0.75 with the early DOY-89 composite, threshold 0.15) and
**0.86** in the north (0.26; 0.79 early, 0.11). Average winter share of the frame: RU_South 44 %,
RU_Central 39 %, UA 32–37 %, RU_Volga 20 %, Siberia/Kazakhstan 2–10 %. The spring masks are diluted: in
2021 WorldCereal puts only 22 % (KZ_North) to 42 % (RU_UralsSiberia) of a spring-mask cell in spring
cereals (WorldCover cropland includes fallow, pasture-like and abandoned land, and WorldCereal itself
under-detects Kazakh spring wheat), so spring EVI anomalies are attenuated.


## Benchmark: how weak is USDA on the Black Sea? (`scripts/benchmark_analysis.py`)

Crop years 2005–2024, WASDE vintages, final = last WASDE vintage. Season months run from May of the
harvest year (1) to April of the next (12).

| | Russia | Ukraine | Kazakhstan | **United States** |
|---|---|---|---|---|
| mean \|USDA estimate − final\|, all reports | **4.1 %** | 4.3 % | 8.8 % | 1.5 % |
| mean \|first (May) estimate − final\| | **12.9 %** | 13.5 % | 19.6 % | 5.1 % |
| RMSE, all reports | 8.1 % | 7.6 % | 14.3 % | 2.9 % |
| mean \|monthly revision\| | **1.53 %** | 1.79 % | 2.43 % | 0.72 % |
| August revision (mean \|rev\|) | **5.7 %** | 6.6 % | 7.1 % | 1.4 % |
| persistence: rev_t on rev_t−1 (t) | **0.43 (3.4)** | 0.19 (4.3) | 0.29 (4.2) | 0.16 (2.1) |
| non-zero revisions with the sign of the previous one | **80 %** | 79 % | 74 % | 64 % |

- USDA's Russia numbers are **2–2.5× noisier** than its US numbers and are revised in the same direction
  80 % of the time. The weak-benchmark premise holds.
- **USDA follows the Russian private analysts.** At each WASDE, USDA's revision = 0.69 × (latest
  IKAR/SovEcon/ministry figure − previous USDA), t = 6.0, n = 67 reports, crop-year clustered. After that
  revision the private-minus-USDA gap no longer predicts the next one (slope −0.00). On the same dates
  the private figures are only slightly closer to the final than USDA (mean |error| 5.7 % vs 6.1 %).
  **So the real bar is IKAR/SovEcon, not USDA**: USDA's Russia number lags them by about a month.
- **Do USDA's Russia revisions move wheat futures?** Barely. On WASDE days (May–Dec, 2005–2026) a 1 %
  cut in USDA's Russia crop moves ZW by +0.10 % (t −2.0 on the revision, n 154), KE by +0.10 % (t −2.1)
  and WEAT by +0.08 % (t −1.8), R² ≈ 0.03 (`results/wasde_day_reaction.csv`). That is a tenth of the US
  corn/soy elasticity, because the trade has already priced the IKAR/SovEcon numbers USDA catches up to.

Figures: `figures/fig_revisions.png` (error by report month), `figures/fig_paths_russia.png`
(USDA's path in 2010, 2012, 2021, 2024).

## Point-in-time signal dataset (`data/signal/`, version `bsw-signal-v1.0`)

| File | Rows | What it is |
|---|---|---|
| `bsw_signal_v1.csv` | 2,739 | **Primary, pre-registered.** Country × crop year (2008–2026) × forecast date (day before each WASDE May–Jan, `kind=wasde`; weekly Apr 1–Dec 30, `kind=weekly`). |
| `bsw_region_indicators_v1.csv` | 7,304 | Region-level anomalies (EVI winter/spring, precipitation, heat, frost, winter share) at the same dates, against the same region's earlier years only. Indicators, not yield forecasts (no regional truth). |
| `bsw_signal_v1_wx.csv` | 2,739 | Weather-only variant (secondary). |
| `bsw_signal_v0_first.csv` | 2,739 | First-coded spec (see disclosure), for transparency. |
| `MANIFEST.json`, `MANIFEST_<tag>.json` | — | Version, build time, sha256 and row count of every data file, script hashes. |

Columns of `bsw_signal_v1.csv`: `country`, `year` (harvest year = first year of the USDA market year),
`forecast_date`, `kind`, `next_release` (the WASDE the row precedes), `data_cutoff_vi` (= forecast date − 14 d;
composites ending later are excluded), `data_cutoff_weather` (= − 5 d), `pred_dev_log`, `trend_mmt`,
`sat_estimate_mmt`, `uncertainty_log` (training LOYO RMSE, log units), `n_train`, `n_train_years`,
`n_evi_w_comps` / `n_evi_s_comps` (composites used), `x_<feature>` (z-scored inputs), `b_<feature>`
(coefficients), `usda_latest_mmt` (latest WASDE published on or before the forecast date),
`gap_sat_usda_pct` (100·ln(sat / USDA latest)), `final_usda_expost` (**evaluation only, not point-in-time**),
`model_version`, `ukraine_war_flag`.

Other data: `data/benchmark/wasde_wheat_vintages.csv` (every WASDE world-wheat cell for Russia, Ukraine,
Kazakhstan, US, EU, World, FSU-12, Canada, Australia, Argentina, with release date and time),
`final_outturns.csv`; `data/private/private_estimates.csv` (123 included + all rejected candidates with
the rejection reason, URL and sentence), `ikar_press_index.csv`, `manual_overrides.csv`,
`manual_additions.csv`; `data/prices/*_daily.csv`; `data/reference/pixels.csv` (24,000 sample cells),
`region_cropland_cells.csv`, `regions.csv`, `worldcereal_2021_at_pixels.csv`; `data/features/`
(`modis_region.csv`, `pixel_class.csv.gz`, `weather_region_daily.csv`, `weather_points.csv`).
Results tables in `results/` (`*_v1_holdout.csv` are the pre-registered ones; `*_dev.csv` are the
development-only runs that preceded the pre-registration).

## Caveats

1. **Small samples.** 5 holdout crop years; every holdout t-statistic for Russia rests on 5 clusters
   (34 revision observations, 28 WASDE-day trades). The development period disagrees with the holdout on
   every price test.
2. **Contamination.** See the disclosure in the pre-registration: 6 Russian September numbers of the
   first-coded version were seen for 2021–2026, and two spec changes plus one test redefinition followed
   development diagnostics. The first-coded version scores similarly on the holdout (WASDE-day +1.17 %,
   test (a) +0.07, t 2.7; accuracy worse, 14.7 %), so the changes did not buy the result.
3. **No regional truth, no consensus poll.** Rosstat/Ukrstat regional statistics could not be reached;
   there is no free Reuters-style poll for Russia, so "the analysts" means the latest IKAR/SovEcon/ministry
   numbers quoted in the IKAR press archive (dense from 2019, thin for 2011–2018, 2010 and May-2024
   partly from web-search summaries of dated articles). Ranges were converted to midpoints; scenario
   figures dropped.
4. **Truth = USDA's last vintage**, which excludes Crimea and differs from Rosstat in some years (2022:
   USDA 92.0 vs Rosstat 104.2 Mt). Using Rosstat would change the 2022 picture.
5. **Trend.** A 15-year Theil–Sen trend is a poor baseline for Ukraine (1990s collapse) and runs high for
   Russia after 2022 (96.9 Mt for 2026), which pushes the satellite above USDA in most holdout reports.
6. **Masks.** WorldCover 2021 cropland applied to 2003–2026 (abandonment/reclamation ignored); one 2021
   WorldCereal calibration; spring masks diluted (22–42 % spring cereals). Equal pixel weights within
   regions over-weight fringe northern areas of RU_Central/RU_Volga.
7. **Archive gaps.** Aqua on Planetary Computer: nothing after 26-Jun-2025 until 2026; 2026 lacks DOY
   121–169 and 233; 2023 lacks DOY 297. 2025 spring-wheat EVI is therefore missing (weather only after
   June), and 2026 is a data-gap failure. MODIS collection 6.1 and POWER are reprocessed archives; the
   latency rules (composite end + 14 d, weather + 5 d) are applied, but the values are not the real-time
   ones.
8. **Weather resolution.** POWER/MERRA-2 at 0.5° misses local extremes (the May-2024 frosts register as
   ~1 cell-day in RU_Central); CHIRPS could not be used north of 50°N.
9. **Prices.** Continuous ZW/KE (roll days dropped) and WEAT; no Matif history; no intraday data, so
   report-day returns include the whole session. Costs 0.6 ¢/bu round trip (10 bp for WEAT).

## Reproduce

`scripts/run_all.sh <scratch>` rebuilds everything (~3 h, roughly 100 GB of MODIS tiles streamed, ~1.5 GB kept in scratch).
Every script is a CLI with a docstring (`python3 scripts/<name>.py -h`). Dependencies: pandas, numpy,
statsmodels, matplotlib, geopandas, rasterio, pystac-client, planetary-computer, requests, pyarrow.
Downloaded files are untrusted data and are read with `python -I` from outside the scripts directory.

