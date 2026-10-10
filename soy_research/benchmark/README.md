# Brazil soybean benchmark: official estimate vintages and the CBOT price reaction

This folder holds the benchmark and market side of the satellite-signal project. Everything is built point-in-time: each estimate carries the timestamp when it was published, and later revisions never overwrite earlier vintages. Nothing here uses satellite data. It sets the baseline a satellite yield signal has to beat.

## Contents

| Path | What it is |
|---|---|
| `data/pit/pit_soy_brazil.csv` / `.parquet` | **The point-in-time dataset.** One row per (source, vintage, crop_year, region, variable). 56,776 rows. |
| `data/pit/final_outturns.csv` | Final outturns by crop year, region and variable from several sources: Conab latest, Conab "série" sheet, IBGE LSPA latest, IBGE PAM, USDA latest. |
| `data/prices/cbot_soy_zs_daily.csv` | CBOT soybean front month (Yahoo `ZS=F`), 2000-09 to 2026-10, with daily log return `ret` and a roll flag `roll`. |
| `data/prices/usdbrl_daily.csv` | USD/BRL rate (Yahoo `BRL=X`), included for context. |
| `data/interim/` | Per-source intermediate files: Conab manifest (URLs and release dates), Conab, IBGE and WASDE vintages, IBGE release dates. |
| `data/reference/conab_release_date_overrides.csv` | Release dates for the 2022/23 Conab surveys, corrected by hand. Each row gives the URL of its evidence. |
| `data/raw/conab/` | The 84 Conab spreadsheets as downloaded (81 MB). Git-ignored. |
| `results/*.csv` | Analysis tables (described below). `results/events.csv` has one row per release, with its surprise and event day. |
| `figures/*.png` | Figures 0–5. |
| `scripts/` | Command-line scripts with docstrings. `scripts/run_all.sh` rebuilds everything. |

### PIT schema

`source` (conab, ibge_lspa, usda_wasde) · `vintage_id` · `release_date` (local date) · `release_ts_utc` · `date_quality` · `crop_year` · `region` · `variable` · `value` · `unit` · `is_current_crop` · `source_url`

- **Crop year.** `crop_year` uses the Brazilian convention: crop "2021/22" is planted Sep–Dec 2021 and harvested Jan–Jun 2022. The WASDE Brazil market year "2021/22" is the same crop. IBGE harvest year 2022 is mapped to 2021/22.
- **Units.** `planted_area` and `harvested_area` are in kha, `yield` in kg/ha, and `production` in kt. WASDE balance-sheet items are also in kt: beginning_stocks, imports, domestic_crush, domestic_total, exports and ending_stocks.
- **Regions.** Conab rows cover every state (UF) and macro-region plus BR. IBGE rows cover BR and every UF that grows soy. WASDE rows cover BR, plus US, AR and WORLD as context.
- **`is_current_crop`.** Each Conab spreadsheet also prints the previous crop. Those rows are kept with `is_current_crop=0` because they are genuine late revisions. For WASDE, `is_current_crop=1` marks the newest market year in the report.
- **Release times:**
  - Conab: 09:00 BRT.
  - WASDE: 12:00 ET.
  - IBGE: the time in IBGE's calendar, or 10:00 BRT when only the news-release date is known.

## Sources and coverage

| Source | URL | Coverage obtained |
|---|---|---|
| Conab, *Acompanhamento da Safra Brasileira de Grãos*: one spreadsheet per survey ("levantamento"), sheet `Soja` | https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/safras/safra-de-graos/boletim-da-safra-de-graos | **2019/20–2025/26: 84 of 84 vintages (12 per crop).** Brazil, all 27 UFs and the macro-regions. Variables: planted area, yield, production. Each file's URL is in `conab_manifest.csv`. |
| USDA WASDE, World Soybean Supply and Use table | OCE "Historical WASDE report data" CSVs, Apr-2010 onward ([usda.gov page](https://www.usda.gov/about-usda/general-information/staff-offices/office-chief-economist/commodity-markets/wasde-report), fetched via the mirror https://usda.azureedge.us/historical-wasde-report-data-3). Text reports for 2005–2010 from the Cornell/NAL archive, https://esmis.nal.usda.gov/publication/world-agricultural-supply-and-demand-estimates | **260 reports, Jan-2005 to Oct-2026.** Brazil, US, Argentina and World balance sheets for every market year shown. The text parser matches the CSV on all 504 overlapping cells (Apr-2010). |
| IBGE LSPA, SIDRA table 6588 (monthly vintages of the current-year estimate) | https://sidra.ibge.gov.br/tabela/6588 (API: servicodados.ibge.gov.br/api/v3/agregados/6588) | **240 monthly vintages, Sep-2006 to Aug-2026** (harvests 2006–2026). Brazil and every UF. Variables: planted area, harvested area, production, yield. Release dates come from the IBGE calendar API for 2017 onward (117) and from IBGE news releases before that (110). The remaining 13 are approximated as the 10th of the following month. |
| IBGE PAM, SIDRA 1612 (definitive municipal survey) | https://sidra.ibge.gov.br/tabela/1612 | Finals for 2003/04–2024/25, Brazil and UFs. |
| CBOT soybean prices: Yahoo `ZS=F` continuous | https://query1.finance.yahoo.com/v8/finance/chart/ZS=F | Daily, 2000-09-15 to 2026-10-09. |

### Coverage gaps (be explicit about these)

1. **Conab vintages before 2019/20 are missing.** The 2005/06–2018/19 surveys exist only on the old Conab portals: www.conab.gov.br, antigo.conab.gov.br and portaldeinformacoes.conab.gov.br. Every connection to them from this environment failed, either with a TCP reset at the egress proxy or with HTTP 503 through WebFetch. The Wayback Machine (web.archive.org) was blocked too.
   - Big Conab seasons we therefore cannot cover: **2011/12, 2015/16 (MATOPIBA) and 2017/18**.
   - IBGE LSPA, which has state-level vintages from 2006, and USDA WASDE, which has Brazil totals from 2005, fill that window.
   - `fetch_conab.py` can be pointed at those portals from a machine that can reach them. The spreadsheet layout is the same and `parse_conab.py` reads both `.xls` and `.xlsx`.
2. **Conab release dates.** For 2019/20–2021/22 and 2023/24–2025/26 they come from the gov.br "Publicado em" field. On gov.br, the 2022/23 dates are placeholders written when the content was migrated (all on the 10th, including Saturdays). They were replaced with dates confirmed in the press; see `data/reference/`.
3. **IBGE first estimate.** In table 6588, IBGE's first estimate for a harvest year is the January survey (published around mid-February). The Oct–Dec forecasts for the next harvest are not archived as vintages. The IBGE 2005/06 vintages (Sep–Dec 2006) are all after harvest.
4. **When USDA first projects a crop.** In the 2005–2008 text archive the new Brazil crop first appears in the June WASDE; from 2009 it appears in May. The October WASDEs of 2013 and 2025 were not published because of US government shutdowns.
5. **Prices: no individual contracts.** Yahoo serves only live contracts (`ZSK27.CBT` works; `ZSK24.CBT` returns "No data found"). Stooq was unreachable and CME/Barchart history is paywalled. So the May and July contracts could not be rolled from individual settlements.
   - Mitigation: Yahoo's continuous series switches contract at expiry. Volume moves one session before the price jump, so for each of the seven expiry months (F H K N Q U X) the script flags both the volume-jump session and the session after it.
   - That flags 366 days. Mean |return| is 1.86% on flagged days versus 1.05% on other days, and it catches the large old-crop/new-crop jumps (for example 2014-08-15 at −10.5% and 2022-07-15 at −9.4%).
   - Every regression drops flagged days. Results with them kept are in the robustness file.
6. **Not obtained (optional items):**
   - Brazilian basis.
   - B3 soybean futures (SJC).
   - Pre-2006 IBGE vintages.
   - Major non-WASDE USDA reports (Acreage, Grain Stocks, Prospective Plantings). These are not removed from the "normal day" sample.

## Method

- **Headline crop.** A release in month ≥ October is about crop Y/Y+1; otherwise it is about crop (Y−1)/Y. Revision paths use, for each source, the BR production of its headline crop: the Conab current column, the IBGE harvest year, or the WASDE market year equal to the headline crop. Figure 1 also shows the USDA new-crop projections made from May/June.
- **Revision.** The revision is the change from the same source's previous estimate of the same crop, in Mt.
- **Cross-source surprise.** This is the level minus the other agency's latest estimate published strictly earlier. Examples: Conab − latest USDA, and USDA − latest Conab.
- **Event day.** The event day is the first CBOT session whose settlement (13:15 CT) comes after the release. For Conab (09:00 BRT), IBGE and WASDE (12:00 ET) this is always the release day itself.
  - The return is the close-to-close log return, in %.
  - "Normal" days are sessions with no Conab, IBGE or WASDE release and no roll flag, compared over the same years as each source.
- **Estimation.** OLS with HC1 standard errors. The WASDE regressions control for the change in US ending stocks and US production, both in Mt.
- **Predictability.**
  - Autocorrelation: regress revision k on revision k−1 within the same source and crop.
  - Nordhaus/efficiency test: regress (final − estimate_k) on revision_k.
  - Cross-source lead-lag: does agency A's revision since agency B's last release predict B's next revision?

## Findings

### 1. How the estimates evolve

The tables are `results/revision_summary_by_season.csv`, `results/revision_by_season_month.csv` and `results/state_first_to_final.csv`. The figures are fig1, fig2 and fig5.

- **When revisions happen.** Most of the revision happens between January and April. Mean absolute monthly revision:
  - Conab: 1.6 Mt in January, 3.5 Mt in February (driven by 2022), 1.5 Mt in March.
  - USDA: about 1.2 Mt per month from January to April.
  - IBGE: 1.6–1.7 Mt in March–April.
  - October–December and July–August revisions are small, under 0.7 Mt.
  - Conab's September survey (L12) sometimes adds a late jump; 2019/20 rose by 3.9 Mt.
- **Big-revision seasons.** The first in-season estimate to the latest vintage:

| Season | Conab | USDA | IBGE | What happened |
|---|---|---|---|---|
| 2021/22 | 140.8 → 125.6 Mt (−10.8%) | 144 → 130.5 Mt | 131.8 → 119.5 Mt | Southern drought. Conab's state breakdown: RS −12.0 Mt, PR −8.5 Mt, MS −3.6 Mt, partly offset by MT +3.6 and GO +3.3. Single largest revision: Conab L5 on 2022-02-10, −15.0 Mt. |
| 2023/24 | 162.0 → 147.4 Mt at L12 (151.3 Mt later) | 163 → 153 Mt | 150.4 → 145.0 Mt | Losses spread across states: MT −5.0, PR −3.6, MS −3.0, RS −2.2 Mt. Almost all of the cut came Dec–Mar (MT and central-west dryness). In Conab's numbers the late-April/May RS floods were small: L8 in May was +1.2 Mt and L9 −0.3 Mt. |
| 2011/12 | not available | 75 (peak) → 66.5 Mt | 70.1 → 65.7 Mt | Southern drought. In IBGE's figures RS fell 2.3 Mt. |
| 2015/16 | not available | 100 → 96.5 Mt | 102.7 → 95.8 Mt | IBGE: MATOPIBA −4.5 Mt, MT −2.2 Mt. |
| 2008/09 | not available | 64 → 57.8 Mt (−9.7%) | 57.8 → 57.0 Mt | Southern drought. IBGE's first estimate is from January, by which point it already included most of the loss. |

  - Other large USDA misses were upward: 2009/10 (+15%), 2010/11 (+16%), 2016/17 (+11%) and 2017/18 (+14%). USDA tends to start conservative and move in steps.
- **Final levels differ by agency.** Since 2019/20, USDA's latest figure sits 0–7 Mt above Conab's final, and Conab sits 2.6–6.4 Mt above IBGE (`final_outturns.csv`). Each agency is therefore benchmarked against its own final.

### 2. Market reaction on release days

The tables are `results/release_day_volatility.csv`, `results/release_day_regressions*.csv` and fig3. Roll days are excluded.

**Volatility.**

| Release | SD of daily return | SD on normal days, same years | Variance ratio | Levene p |
|---|---|---|---|---|
| WASDE (n=240) | 1.85% | 1.37% | 1.83 | <0.001 |
| Conab (n=74) | 0.90% | 1.23% | 0.54 | 0.017 (*quieter* than normal) |
| IBGE (n=230) | 1.34% | 1.38% | 0.94 | 0.18 (no different) |

The extra WASDE volatility comes from the US numbers. Conab days often fall one or two days before WASDE.

**Release-day return regressed on the Brazil revision** (% return per Mt, with t-statistics):

| Specification | Slope (%/Mt) | t | R² | n |
|---|---|---|---|---|
| WASDE, Brazil revision | −0.101 | −1.31 | 0.005 | 219 |
| WASDE, Brazil revision with US controls | −0.079 | −1.01 | — | — |
| ↳ US ending-stocks change (control) | −0.25 | −2.11 | — | — |
| IBGE, revision | −0.097 | −1.65 | — | 209 |
| IBGE, Jan–May releases | −0.121 | −2.00 | — | — |
| IBGE − latest USDA | −0.066 | −2.53 | — | — |
| Conab, revision | +0.084 | 2.74 | — | 67 |
| Conab, excluding the Feb-2022 −15 Mt cut | +0.043 | 0.66 | — | 66 |
| Conab − latest USDA | +0.037 | 0.82 | — | — |

- The Conab slope has the "wrong" sign, and the whole effect comes from one release. On 2022-02-10 Conab cut 15 Mt and CBOT fell 1.3%, because USDA had already cut the day before.
- For scale: −0.1%/Mt is about **1.2 US¢/bu per Mt** at the post-2019 average price of $12.20/bu. A 10 Mt cut would be worth roughly +1% on the day.
- **Conclusion:** Brazil revisions from the official agencies barely move CBOT on the day they are published. Signs are right for USDA and IBGE but rarely significant, and R² is below 3%. The market seems to price Brazil supply before the official numbers appear, through private estimates, weather and USDA's earlier cuts. That is the window a satellite signal would need to exploit.

### 3. Are revisions predictable? The free baseline

The table is `results/revision_predictability.csv` and the figure is fig4. Revision k regressed on revision k−1 (Mt), within each source:

| Source | Slope | t | Pearson ρ | Spearman | Notes |
|---|---|---|---|---|---|
| USDA (n=208) | 0.50 | 4.9 | 0.51 | 0.47 | P(cut \| previous cut) = 0.54 vs 0.16 unconditionally; 88% of consecutive non-zero revisions share a sign. |
| Conab (n=70) | 0.37 | 2.25 | 0.36 | 0.21 | Influenced by 2022. |
| IBGE (n=198) | 0.26 | 1.4 | 0.34 | 0.29 | — |
| Conab, state level (pooled, n=700) | 0.42 | 6.35 | — | — | 75% sign persistence. |
| IBGE, state level (n=1,980) | 0.20 | 2.5 | — | — | — |

- **USDA smooths its revisions.** Regressing (final − estimate) on the latest revision gives b = 1.06 (t = 4.5). Each 1 Mt USDA cut predicts about another 1 Mt in the same direction before the final. IBGE: b = 0.36 (t = 2.0). Conab: b = 0.22 (t = 1.0, not significant).
- **Conab leads USDA.** USDA's next Brazil revision equals 0.41 × Conab's revisions since the previous WASDE (t = 7.3, R² = 0.50, n = 62). The same holds against IBGE's revisions: b = 0.25, t = 3.4.
- **Baseline any satellite signal must beat:**
  - The persistence of the agencies' own revisions.
  - A "Conab gap" rule for USDA revisions: R² ≈ 0.5 on USDA's next revision.
  - Neither rule predicts prices, because release-day price reactions are close to zero.

## Reproduce

```bash
cd soy_research/benchmark
scripts/run_all.sh /path/for/raw/wasde      # full rebuild (≈30 min, the gov.br pages are slow)
# or step by step: see the docstring of each script (python3 scripts/<name>.py -h)
```

Dependencies: pandas, numpy, scipy, statsmodels, matplotlib, openpyxl, xlrd, python-calamine (one Conab xlsx has a broken stylesheet) and pyarrow. Every downloaded file is read with `python -I`.
