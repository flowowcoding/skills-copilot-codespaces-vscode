# Copper smelter activity from free satellite data

**Question.** Mine earthmoving did not track copper output (`../../satellite_poc/chile_copper/`).
Do *processing* signals - furnace heat at smelters - track metal supply better, and can a free
index beat the official statistics or say anything about copper prices?

**Short answer.**
- **On/off: yes, often to the day.** The free Sentinel-2 hot-pixel index detected 9 of 15
  testable outages (two more were untestable because of cloud). The free night-time Sentinel-3
  signal detected 5 of 6. The closures were caught cleanly:
  - Ventanas: last hot pass 18 May 2023, closed 31 May.
  - Hernán Videla Lira: last hot pass 22 Feb 2024, last anodes 23 Feb.
  - Altonorte: dark from 16 Mar 2025, ten days before the first press report on 26 Mar. Its
    restart in early May 2025 is also visible, and no public restart announcement was found.
  - PASAR: last hot pass 11 Mar 2025 (partly cloudy) and first clear cold pass 16 Mar. SAVANT
    reports its last activity signal on 15 Mar.

  The six misses: Kennecott 2020 and 2023 and Hamburg 2023 (enclosed furnaces, or other hot
  units kept running); Manyar's acid-plant outage and its restart (the furnace stayed hot); and
  Sterlite (no signal at all, possibly a location problem).
- **How much: no.** Activity does not track reported throughput (Kennecott quarterly: Spearman
  +0.27 in development, -0.31 in the 6-quarter holdout). The China index does not track NBS refined
  output either (YoY Spearman +0.27 in development, below the pre-set 0.3; -0.52 in the holdout).
- **Markets: nothing tradeable.** The global index has no reliable relation with next-month COMEX
  copper (-0.13 dev, -0.02 holdout). The threshold rule made 33 trades in development (61% hits,
  +0.47% per trade net) and only 3 in the holdout, which is too few to judge.
- This matches the mining result: free imagery answers "is it running?" and not "how much?".
  The main reason here is that a big smelter is "hot" on nearly every clear pass whatever its
  throughput. The China index saturates at 1.0, so there is nothing to correlate.

Everything below the pre-registration was written after it. Nothing in the pre-registered
tests was changed after results were seen. Exploratory additions are labelled as such.

## Pre-registration (written 2026-10-11 02:49 UTC, before any smelter time series was looked at)

Only the location chips (`figures/locate/`, one year per smelter) and three test chips
(Kennecott, Altonorte, Gresik, year 2023) had been viewed when this was written. The hot-pixel
rule in `s2_hot.py` was fixed on those chips. The ground-truth series (NBS China refined copper,
Kennecott quarterly concentrate smelted) had been downloaded and parsed but not compared with
anything.

**Signal (primary): Sentinel-2 SWIR hot pixels** (`s2_hot.py`, rule in its docstring), 20 m,
every acquisition 2017-01 to 2026-10, box of +-1 km (+-1.2 to 1.5 km for spread-out plants)
around the furnace/slag area in `smelters.csv`.

**Index (frozen):**
1. Valid scene: cloud fraction in the box <= 0.2 and valid (non-nodata) fraction >= 0.95.
2. Furnace mask per smelter: pixels hot in >= 3 valid scenes **and** in <= 85% of valid scenes
   during the mask period 2017-01-01 to 2024-12-31 (never the holdout), dilated by one pixel.
   The 85% cap drops static materials that look "hot" on every pass (e.g. Gresik jetty sheds);
   the >= 3 rule drops one-off bush fires, glint and noise.
3. Per scene: `n_mask_hot` = hot pixels inside the mask; `active` = n_mask_hot >= 1.
4. Monthly per smelter: active share = mean(active) over valid scenes; intensity = mean
   n_mask_hot. Fewer than 2 valid scenes = missing month.
5. Aggregates: capacity-weighted mean of active shares (weights = `approx_capacity_kt_cu`);
   a smelter missing in a month is filled with its own 2017-2024 mean for that calendar month.

**Test 1 - known on/off events** (`events.csv`, 18 rows, dates and sources fixed above):
- Outage detected if, in the event window, active share <= 0.5 x the baseline share, one-sided
  Fisher exact p < 0.05, and the window has >= 3 valid scenes (else "not testable").
- Restart (Manyar 2025): share after restart >= 2 x share during the outage, Fisher p < 0.05.
- Reported: hit rate = detected / testable. Robustness: same test with a mask from the
  baseline year only.

**Test 2 - output tracking, Kennecott** (only smelter with free quarterly smelter-level output
found): quarterly concentrate smelted (Rio Tinto) vs quarterly active share and intensity,
Spearman. Development 2017Q1-2024Q4, **holdout 2025Q1-2026Q2 (6 quarters)**. "Tracks" only if
Spearman >= 0.5 in development and >= 0.3 with the same sign in the holdout.

**Test 3 - China aggregate vs NBS** (most tradeable target): China index = capacity-weighted
active share of the Chinese smelters covered; 3-month mean; YoY change (pts) vs NBS refined
copper YoY (published "comparable basis" where available). Development = NBS months through
2024-12, **holdout = 2025-01 to 2026-08** (the last 6 quarters plus Jul-Aug 2026). "Tracks" only
if Spearman >= 0.3 in development with circular-shift permutation p < 0.05 **and** >= 0.3 in the
holdout. Also same with MoM changes (secondary). Lead time = (NBS release ~16th of next month)
minus (index ready ~2 days after month end).

**Test 4 - markets** (secondary, run only once): monthly change of the global index vs the
next month's COMEX copper (HG=F, Yahoo) return; rule: long copper when the global index's
3-month change is below -1 SD of its development distribution (supply loss), short above +1 SD,
flat otherwise; 10 bp round-trip cost; development vs holdout as in Test 3. Annual TC/RC
benchmarks are compared descriptively only (10 points).

**Not done / descriptive only:** SO2 (NASA annual catalogue), commercial-index comparison
(SAVANT public monthly values), Sentinel-3 SLSTR night-time fire product (feasibility only).

**Addendum (2026-10-11 02:55 UTC, before any FRP series was computed):** a second, night-time
sensor turned out to be free and small: the Sentinel-3 SLSTR Fire Radiative Power product on
the Planetary Computer (1 km, Aug 2020 onward, ~1 night pass a day, ~0.5 MB per granule;
`s3_frp.py`). Feasibility checks seen so far: Altonorte 11 of 49 night granules with a
detection (Jan-Feb 2024), Ventanas 17 of 58 (Apr-May 2023, before closure), Kennecott 0 of 79
(Jun-Jul 2024, operating). The same event test is applied to it (granule "active" = >= 1
detection within 1.5 km; same window, baseline, 0.5x and Fisher rules; events after Aug 2020
only) and the same China and Kennecott tests as a secondary signal. A night granule without a
detection may simply be cloudy (the product does not say), which biases toward "off" in wet
climates.

## What is accessible for free (checked 2026-10-11)

| source | status | used for |
|---|---|---|
| Sentinel-2 L2A (B8A/B11/B12/SCL), Planetary Computer, no account | works; 20 m, ~5-day revisit, daytime only, 2017 onward | primary hot-pixel index (`s2_hot.py`) |
| Sentinel-3 SLSTR FRP L2 (`sentinel-3-slstr-frp-l2-netcdf`), Planetary Computer | works; 1 km, about one night pass per day, Aug 2020 onward, ~0.5 MB per granule | night-time detections (`s3_frp.py`) |
| NASA FIRMS (VIIRS/MODIS active fire) | **archive and area API need a MAP_KEY** ("Invalid MAP_KEY" for DEMO_KEY). Only the global last-24h/7-day CSVs are open | not used (no history) |
| VIIRS Nightfire (Colorado School of Mines EOG) | **login required** (OpenID redirect) | not used |
| Landsat 8/9 at night | Planetary Computer has only Collection-2 L2 (daytime) and L1 MSS; night TIRS scenes are not there | not used (the daytime roof-heating problem from Hawesville applies) |
| Sentinel-5P TROPOMI SO2 (`sentinel-5p-l2-netcdf`) | works, but ~120 MB per 5-minute granule (1 GB per orbit file), too heavy for daily per-smelter series here | replaced by NASA's annual SO2 catalogue |
| NASA GSFC SO2 point-source catalogue v2 (`Catalogue_SO2_2025.xls`) | public, annual 2005-2025, kt SO2 | `so2_catalog.py` |
| NBS China refined copper, monthly | data.stats.gov.cn **blocked** (HTTP 403, WAF). The monthly press release lists only "ten non-ferrous metals" | rebuilt from reposts (gotohui to 2020-08, chinabaogao notes after); `nbs_copper.py` |
| Rio Tinto quarterly production (Kennecott concentrate smelted, anodes, refined) | SEC EDGAR 6-K, free | `rio_kennecott.py` |
| Cochilco smelter output by smelter | not found as a free monthly series (only mine output by company) | not used |
| COMEX copper HG=F | Yahoo chart API, works | `prices.py` |
| Spot treatment charges | paywalled (Fastmarkets/SMM). Only annual benchmarks are public | `data/market/tc_benchmarks.csv` (descriptive) |

## Smelters covered (`smelters.csv`)

34 smelters, roughly 10 Mt/yr of copper capacity by the rough weights in the file:
- **Chile:** all 7 smelters.
- **Zambia:** Kansanshi, Mufulira, Nchanga.
- **Africa, other:** Lualaba (DRC), Tsumeb (Namibia).
- **Indonesia:** PT Smelting Gresik, Freeport Manyar.
- **USA:** Kennecott, Miami.
- **Europe:** Huelva, Hamburg, Pirdop, Rönnskär, Harjavalta, Głogów, Legnica.
- **India:** Sterlite.
- **Japan and Philippines:** Saganoseki, PASAR.
- **China:** Guixi, Guangxi Jinchuan (Fangchenggang), Jinchuan (Jinchang), Zijin Qiqihar.
- **Australia:** Mount Isa, Olympic Dam.
- **Other:** Sarcheshmeh (Iran), Balkhash (Kazakhstan).

How each was located:
- Every location was checked on a Sentinel-2 SWIR chip, using hot-pixel frequency over one
  year (`figures/locate/`, `figures/locate_grid.jpg`). The box is centred on the furnace and slag
  cluster where one exists.
- Named OSM features were the starting point (Nominatim).

Dropped because they could not be located reliably: Ilo, Naoshima, Onsan, Dahej, Adani Kutch,
Amman, Chambishi, Tongling, Daye, Dongying and Xiangguang. In particular, China's other big
smelters are not covered. **China coverage is 4 smelters, about 2 Mt/yr, roughly 15% of Chinese
capacity.** That alone makes Test 3 weak.

**Which smelters are visible at all:**
- **Strong signal in both sensors:** plants with Peirce-Smith converters and open slag handling
  (Chile, Kansanshi, Pirdop, Sarcheshmeh, Olympic Dam).
- **Signal in daytime S2 only:** most others.
- **No signal in either sensor:** PT Smelting Gresik (Mitsubishi continuous process),
  Atlantic Copper Huelva and Sterlite (2017-18).
- **No night-time signal:** Kennecott, Hamburg, Manyar, Guixi and PASAR. The night product sees
  nothing at enclosed flash-smelting/flash-converting plants.

## Method (summary; frozen rules are in the pre-registration and the script docstrings)

- **Hot pixel** (`s2_hot.py`): TAI = (B12 - B11)/B8A >= 0.45, B12 - B11 >= 0.05, B12 >= 0.15
  and B8A <= 0.30, or both SWIR bands near saturation. Molten or freshly poured slag emits at
  2.2 µm and 1.6 µm, so B12 rises above B11, which sunlit natural surfaces almost never do.
- **Two false-positive classes, found on the test chips:**
  - Bright static materials: Gresik jetty sheds, Chinese painted roofs, the wet edge of the
    Kennecott tailings dam. Handled with the NIR cap, and by the mask's 85% persistence cap.
  - One-off bush fires, glint and ship wakes. Handled by the mask's "hot in >= 3 scenes" rule.
- **Index** (`index.py`): share of clear passes (cloud <= 20% of the box) with at least one hot
  pixel on the smelter's furnace mask (mask built from 2017-2024 only), averaged by month.
- **Night** (`s3_frp.py`): share of night granules (local solar time 20:00-05:00) with an SLSTR
  FRP detection within 1.5 km.
- **Every scene is archived** (`data/s2/*.csv`, plus every hot pixel in `*_hotpix.npz`), so other
  masks or thresholds can be re-run without downloading again.

## Test 1 results: known events (`results/events_results.csv`, `figures/events_scenes.png`)

| event | S2 baseline -> window share | S2 | S3 night baseline -> window | S3 | last hot pass before / first after |
|---|---|---|---|---|---|
| Ventanas closure, 31 May 2023 | 0.46 -> 0.00 (33 passes) | **detected** | 0.135 -> 0.002 | **detected** | 18 May 2023 / (one false hit, Jan 2026) |
| Hernán Videla Lira halt, 23 Feb 2024 | 0.35 -> 0.00 (51) | **detected** | 0.23 -> 0.00 | **detected** | 22 Feb 2024 / none |
| Sterlite closure, Mar-May 2018 | 0.00 -> 0.00 | missed (no baseline signal) | n/a (pre-2020) | - | - |
| Kennecott 27-day shutdown, May 2017 | 2 baseline passes | not testable | n/a | - | - |
| Kennecott shutdown, Jun-Sep 2020 | 0.54 -> 0.29 (34) | missed (p = 0.014 but ratio 0.54 > 0.5) | n/a | - | - |
| Kennecott rebuild, May-Aug 2023 | 0.51 -> 0.38 (29) | missed | no night signal | - | - |
| Kennecott shutdown, Sep-Oct 2025 | 0.58 -> 0.13 (15) | **detected** | no night signal | - | 22 Aug / 8 Sep 2025 |
| Manyar acid-plant fire, Oct 2024 | 1.00 -> 0.86 (7) | missed | no night signal | - | furnace still hot in Nov-Dec 2024 and Apr-May 2025 |
| Manyar restart, mid-2025 | outage 0.86 -> 0.89 | missed (outage was not dark) | none | missed | - |
| Altonorte halt, Mar 2025 | 1.00 -> 0.00 (7) | **detected** | 0.195 -> 0.00 | **detected** | 13 Mar / 5 May 2025 |
| PASAR care and maintenance, 2025 | 0.79 -> 0.00 (15) | **detected** | no night signal | - | 11 Mar 2025 (partly cloudy pass) / none |
| Fangchenggang (SAVANT-reported), Mar 2025 | 1 window pass | not testable | no night signal | - | the one pass on 20 Mar is hot |
| Pirdop maintenance 2023 | 1.00 -> 0.17 | **detected** | 0.25 -> 0.00 | **detected** | 13 May / 2 Jun 2023 |
| Pirdop maintenance 2025 | 1.00 -> 0.24 | **detected** | 0.23 -> 0.00 | **detected** | 9 May / 8 Jun 2025 |
| Hamburg maintenance, May-Jul 2023 | 0.69 -> 1.00 | missed | no night signal | - | - |
| Olympic Dam SCM17, Aug-Nov 2017 | 1.00 -> 0.40 | **detected** | n/a | - | - |
| Olympic Dam SCM21, Aug-Dec 2021 | 0.86 -> 0.23 | **detected** | (0.18 -> 0.06, exploratory: baseline starts before the S3 archive) | - | - |

**Hit rate:**
- S2: **9 of 15 testable** with either mask (primary 2017-2024 mask, or a mask built from the
  baseline year only).
- S3 night: **5 of 6 testable**. The only miss is the Manyar restart; every other S3 test with a
  baseline signal was detected.

**How fast:**
- Detection is to the pass (5-day revisit, so 3-10 days with cloud) at open-converter plants.
- The night product sees a halt within a few nights.

Where the signal exists, an outage is unmistakable. The misses are physical, not statistical:
- Enclosed flash smelting plus flash converting (Kennecott) shows little hot material either
  way. Kennecott was "hot" on 24% of passes in 2020Q3, when it smelted only 1 kt of concentrate.
- A furnace on hot standby looks the same as a running one (Manyar).
- At Hamburg the hot pixels probably come from units that kept running through the flash-smelter
  overhaul (anode furnaces, recycling).

**Signals no event was registered for (post hoc, not validated):**
- **Potrerillos:** dark in both sensors from June 2025 onward. Codelco announced a 50% capacity
  cut in Dec 2024 (Chamber of Deputies note); no full-stop announcement was found.
- **Tsumeb:** S2 activity fades through 2025 to zero in 2026.
- **Mount Isa:** S2 dark in early 2026 (Glencore had put the smelter under review in 2025).
- **Głogów:** a dip in late 2025.
- **Chuquicamata:** low 2019 (smelter modernisation).

These would need checking against company statements before anyone relies on them.

## Test 2: does activity track output? Kennecott (`results/kennecott_quarterly_vs_index.csv`, `figures/kennecott_quarterly.png`)

| measure vs concentrate smelted (kt/quarter) | development 2017Q2-2024Q4 | holdout 2025Q1-2026Q2 |
|---|---|---|
| active share, Spearman | +0.27 (n 31, circular-shift p 0.05) | **-0.31** (n 6) |
| intensity (hot pixels per pass), Spearman | +0.29 (p 0.05) | -0.71 |
| S3 night share | no detections at Kennecott at all | - |

Pre-registered criterion (>= 0.5 in development, >= 0.3 in the holdout): **failed.** The very
low quarters (2020Q2-Q3, 2023Q2-Q3) sit at the low end of the index, but so do ordinary quarters.

## Test 3: China index vs NBS (`results/china_index_vs_nbs.csv`, `figures/china_vs_nbs.png`)

The NBS series (`data/china_nbs_refined_copper_monthly.csv`) was rebuilt from reposts. It runs
2014-2026 with gaps; YoY is NBS's own "comparable basis" figure where published.

| test | development (to 2024-12) | holdout (2025-01 to 2026-08) |
|---|---|---|
| **YoY, 3-month active share vs NBS YoY (primary)** | +0.27 (n 65, perm p 0.02) | **-0.52** (n 16) |
| MoM vs NBS MoM | -0.20 | -0.68 |
| S3 night index YoY vs NBS YoY (secondary) | +0.16 (n 30, p 0.16) | +0.61 (n 16) |
| exploratory: intensity YoY | -0.08 | -0.02 |
| exploratory: index leads NBS by 1 / 2 / 3 months | +0.24 / +0.30 / +0.16 | -0.44 / -0.52 / -0.59 |

**Failed.** The primary development correlation is below the pre-set 0.3, and the holdout has the
wrong sign. The S3 holdout of +0.61 follows a failed development test, so it does not count.
Why it fails:
1. **Coverage:** 4 of China's ~30 large smelters. Only 58% of the covered capacity has a valid
   observation in a typical month (south China is cloudy; Fangchenggang has 135 clear passes in
   ten years).
2. **Saturation:** the big Chinese plants are hot on essentially every clear pass, so the active
   share sits at 1.0. Intensity varies, but with viewing geometry and slag-pour timing, not with
   output. Guixi, China's biggest smelter, has zero night-time detections.
3. **The target barely moves:** NBS output grew 0-20% YoY with a strong trend and capacity
   additions. A binary on/off signal at four plants cannot resolve that.

**Lead time, if it had worked:** the index for month m is ready about 2 days after month end. NBS
publishes around the 15th-17th of month m+1, so the lead is about two weeks. It is worth nothing
without tracking.

## Test 4: markets (`results/global_index_vs_copper.csv`, `results/output_tests.json`)

- **Global index, 3-month change vs next-month HG=F return:** Spearman -0.13 in development
  (the expected sign, since less smelting would be bullish, but not significant) and -0.02 in
  the holdout.
- **Threshold rule (long below -1 SD, short above +1 SD, 10 bp cost):**
  - Development: 33 trades, 61% hits, +0.47% net per trade (about 0.5 SD of a monthly copper
    return; no t-stat worth quoting).
  - Holdout: 3 trades (2 hits, +0.11%).

  No evidence of return predictability after costs.
- **Treatment charges:** annual benchmarks fell from $92.5 (2017) to $0 (2026). The global index
  stayed between 0.72 and 0.76 throughout (descriptive, 10 points). A fall in TCs is a margin
  story; smelters kept running, so a heat signal would not be expected to show it.

## SO2 (NASA catalogue, annual; `data/so2_nasa_catalogue_annual.csv`)

Only 11 of the smelters appear as catalogue sources (Ilo matched to the catalogue's "Ilo" source
8 km away). The rest emit too little SO2 to be fitted, Ventanas and HVL included.

The series is policy-dominated. Every Chilean smelter drops in 2019:
- Chuquicamata: 42 -> 2 kt
- Caletones: 38 -> 3 kt
- Potrerillos: 16 -> 2 kt
- Altonorte: 9 -> 2 kt

That is the Chilean DS 28 capture standard, not activity. One notable number: **Ilo fell from
about 230 kt (2024) to 11 kt (2025)**. That points to a 2025 stoppage or a capture upgrade; it
was not verified, and Ilo shows no S2 signal. The SO2 catalogue is annual and published with a
lag of about a year, so it has no trading use.

## Comparison with SAVANT (Earth-i / Marex)

What is public about SAVANT:
- **Launch and backing:** launched Oct 2019 by Earth-i with Marex Spectron, part-funded by the
  ESA/UKSA business applications programme.
- **Coverage claims:** about 75 smelters in the index, over 15 Mt/yr and about 80% of world
  capacity, plus about 30 more monitored. Marketing quotes "up to 90%".
- **Method:** each smelter is classed active or inactive daily from "more than twenty
  high-resolution satellites" and proprietary machine learning. No sensor or method detail is
  published.
- **Indices:** the "Global Copper Smelting Index" (capacity-weighted active share, 0-1); the
  "Activity Dispersion Index" (50 = average, weekly rolling, history from Mar 2016); an
  "Inactive Capacity Index".
- **Free publication:** a free monthly global index was promised from 18 Oct 2019. Press releases
  quoting monthly regional values ran until at least Sep 2023. No validation statistics against
  official output were ever published; Marex called it "a significant improvement over existing
  sources".

32 published monthly values were collected (`data/reference/savant_public_values.csv`) and
compared with this index (`results/savant_comparison.csv`):
- **North America (Kennecott + Miami):** Spearman +0.71 (n 6). Both indices put the mid-2020
  and 2023 Kennecott outages at the low end.
- **Global:** +0.17 (n 8).
- **China:** +0.06 (n 8; ours sits at 0.9-1.0).
- **South America:** -0.10 (n 5).

SAVANT's own public event calls match this index where both see the plant:
- Altonorte inactive for 3+ weeks: ours is dark 16 Mar - 30 Apr 2025.
- PASAR's last activity on 15 Mar 2025: ours has its last hot pixels on 11 Mar and its first
  clear cold pass on 16 Mar.

Its Fangchenggang "inactive from 20 Mar 2025" call could not be checked: the one clear pass, on
20 Mar, is hot.

**Bottom line:** a free S2 + S3 index reproduces SAVANT's kind of output (on/off by smelter,
capacity-weighted) at open-converter plants. The list covers ~10 Mt/yr, about a third of world capacity, and the visible subset is smaller. It does not
reach enclosed flash plants or most of China, and nobody, SAVANT included, has published
evidence that on/off status tracks monthly output.

## Caveats

- **Sentinel-2 is daytime-only, 5-day revisit, and blind under cloud.** Tropical and Chinese
  plants have 100-300 clear passes in ten years.
- **Validity screening relies on ESA's scene classification.** Its pre-2022 processing calls
  bright Atacama terrain cloud (see `../../satellite_poc/chile_copper/`), so Potrerillos and
  Chuquicamata have almost no valid passes before 2020-22.
- **Mask period:** the furnace mask uses 2017-2024 data. That includes the post-event years for
  2023-24 events, which is a spatial look-ahead. The baseline-year mask gives the same 9 of 15.
- **S3 night "no detection" can mean cloud.** The FRP product does not flag cloud at the site.
- **Event dates:**
  - Exact dates are from press releases. Two event "truths" are SAVANT claims (PASAR,
    Fangchenggang), not company data.
  - Kennecott 2020/2023 windows were set from quarterly throughput, not daily dates.
  - Sterlite may be mis-located: its mask is empty and there were only 14 valid baseline passes.
- **NBS series:** rebuilt from third-party reposts (gotohui, chinabaogao). About 15% of months
  are back-filled from YoY or quoted prior-year values, and some months are missing. The
  published YoY ("comparable basis") differs from level ratios by 1-3 points.
- **Weights:** capacities in `smelters.csv` are rough public figures, used only as weights.
- **Location chips:** 11 candidates could not be placed with confidence and were dropped rather
  than guessed.

## Files

| file | what |
|---|---|
| `smelters.csv` | 34 smelters: coordinates, box size, rough capacity, process, coordinate source |
| `events.csv` | 18 pre-registered events with windows, baselines and sources |
| `s2_hot.py` | Sentinel-2 hot-pixel locate chips and per-scene series (`locate`, `series`) |
| `run_series.py`, `index.py` | run all series; furnace mask and monthly index |
| `s3_frp.py`, `run_frp.py` | Sentinel-3 SLSTR night FRP detections per smelter |
| `evaluate_events.py`, `evaluate_output.py` | Tests 1-4 |
| `nbs_copper.py`, `rio_kennecott.py`, `prices.py`, `so2_catalog.py` | ground truth, prices and SO2 |
| `plots.py` | figures |
| `data/s2/<id>.csv`, `<id>_hotpix.npz` | per-smelter Sentinel-2 scene table and hot-pixel archive |
| `data/s3frp/<id>.csv` | per-smelter night granules with detections |
| `data/index/` | per-scene index (`<id>_scenes.csv`), `monthly.csv`, masks |
| `data/china_nbs_refined_copper_monthly.csv` (+ `_raw.csv`) | NBS refined copper, kt/month, YoY, repost dates |
| `data/reported/kennecott_quarterly.csv` | Kennecott concentrate smelted / anodes / refined, quarterly |
| `data/market/` | HG=F daily, annual TC/RC benchmarks |
| `data/so2_nasa_catalogue_annual.csv` | NASA annual SO2 per matched smelter |
| `data/reference/savant_public_values.csv` | SAVANT values quoted in Earth-i press releases |
| `results/` | event results, output tests (`output_tests.json`), comparison tables |
| `figures/` | small multiples, event scenes, Kennecott, China, location chips |

Reproduce: `python run_series.py && python run_frp.py && python index.py && python evaluate_events.py && python evaluate_output.py && python plots.py`
(ground truth: `python nbs_copper.py data/china_nbs_refined_copper_monthly.csv --raw data/china_nbs_refined_copper_raw.csv`,
`python rio_kennecott.py data/reported/kennecott_quarterly.csv`, `python prices.py data/market/hg_f_daily.csv`).
