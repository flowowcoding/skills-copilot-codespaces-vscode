# Black Sea wheat: can free satellite + weather data front-run USDA on Russia, Ukraine and Kazakhstan?

Hypothesis tested: markets with **weaker official data** are easier to beat with free imagery than the US
(where `soy_research/us/` failed) or Brazil. Russia is the world's largest wheat exporter and USDA's Russia
numbers are revised far more than its US numbers, so if free data can lead anyone, it should be here.

<!-- PREREG -->

<!-- RESULTS -->

## Data obtained (all free, all point-in-time)

| Item | Source | Coverage | Point-in-time rule |
|---|---|---|---|
| USDA WASDE wheat balance sheets (Russia, Ukraine, Kazakhstan, US, EU, World, …) | OCE historical CSVs Apr-2010+ (https://usda.azureedge.us/historical-wasde-report-data-3, mirror of the usda.gov WASDE page); ESMIS (Cornell/NAL) text reports 2004–Mar-2010 (https://esmis.nal.usda.gov/publication/world-agricultural-supply-and-demand-estimates) | **270 reports, Mar-2004 → Oct-2026** (Oct-2013, Jan-2019, Oct-2025 not published). Text and CSV parsers agree on all 1,260 overlapping cells. | release date, 08:30 ET until 2013-01-10, 12:00 ET after |
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
- **Rosstat regional statistics** (fedstat.ru, rosstat.gov.ru) and **Ukrstat** refused connections from
  this environment (HTTP 403 / reset), so there is **no regional yield truth**. Regions enter only as
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

<!-- MASKRESULTS -->

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

<!-- REST -->
