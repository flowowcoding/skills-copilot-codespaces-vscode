# 5. Chilean copper: does pit activity across many mines track national supply?

Single-mine work (sections 3-4 of `../README.md`) showed the index sees **whether** a mine
operates, but not **how much** it produces. This section tests the remaining idea: add up pit
activity across most of Chile's big open pits and see whether the total tracks copper output.

## Pre-registration (written 2026-10-10, before any index was computed)

Everything below was fixed before computing a single index value or correlation. The ground
truth values had been downloaded and glanced at for parsing, but no comparison was made.

**Mines (15 operations, 17 Cochilco columns).** Escondida, Zaldívar, Radomiro Tomic,
Chuquicamata, Ministro Hales, Gabriela Mistral, Spence, Sierra Gorda, Centinela (sulphides +
oxides), Collahuasi, Quebrada Blanca, El Abra, Los Pelambres, Los Bronces, Caserones,
Candelaria, Mantos Blancos. Together about 70% of Chilean mine output. Underground mines
(El Teniente, Andina) are excluded.

**Pit zones.** Hand-drawn polygons over the pits only (not dumps, pads, plants or tailings),
drawn on Sentinel-2 images from Nov 2025 - Mar 2026 (`chip.py`), stored in `mines.json`,
shown in `figures/pit_zones.png`.

**Index** (`activity_index.py`, frozen):
- Sentinel-2 L2A, 2018-01 to 2026-10, one tile + orbit per site, brightness = red (B04) + SWIR
  (B11) at 20 m, cloud/shadow/snow masked by the scene classification, images with > 20% of
  the box masked dropped (`s2bright.py`).
- Pair consecutive clear images at most 12 days apart. A pixel changed if its normalised log
  brightness moved by more than 0.12. Pixels in deep shadow (< -0.3) are ignored.
- Control = quieter half of the ground more than 300 m from any pit. Busy pit pixels = above
  the 90th percentile of control change frequency.
- **Primary variant R:** busy pixels and control re-picked each calendar year from the previous
  year's data (mining fronts move over 8 years). Secondary: F (picked once on 2018), A (all pit
  pixels, no busy selection).
- Index per pair = busy pit share changed minus control share changed (pts). Quarterly index
  = mean over the quarter's pairs; monthly likewise.

**Ground truth.**
- Primary: Cochilco monthly payable copper production by operation (kt), 2014-01 to 2026-07,
  summed to quarters (`cochilco_monthly_by_operation.csv`).
- Secondary (closer to what a pit index can see): BHP quarterly **material mined** for
  Escondida and Spence (`bhp_material_mined_quarterly.csv`), Anglo American quarterly **ore
  mined** for Los Bronces and Collahuasi (`anglo_ore_mined_quarterly.csv`).

**Periods.** Index scored from 2019-01 (2018 is calibration only).
- Development: 2019Q1-2024Q4 (YoY changes 2020Q1-2024Q4, n = 20).
- **Holdout: 2025Q1-2026Q2 (6 quarters), not looked at until the development results are
  written down.** 2026Q3 has index but no Cochilco data yet (Cochilco ends July 2026).
- No parameter will be tuned on either period. The development period exists to report an
  in-sample number honestly, not to choose settings.

**Tests** (`evaluate.py`):
1. Per mine: Spearman rank correlation between the **year-on-year** change of the quarterly
   index (pts) and the year-on-year log change of quarterly copper production. Pearson
   reported alongside. Same for **quarter-on-quarter** changes (secondary, seasonal effects
   such as sun angle and Andean snow are not removed).
2. **Aggregate (primary):** each mine's YoY index change divided by its development-period
   standard deviation, weighted by the mine's 2018 share of the covered mines' production,
   summed. Correlated (Spearman) with the YoY log change of total production of the covered
   mines, and of total Chile. Significance: circular-shift permutation of the aggregate series.
3. Secondary ground truth: same YoY and QoQ correlations against material/ore mined for
   Escondida, Spence, Los Bronces, Collahuasi.
4. Monthly aggregate YoY (secondary).

**What counts as success.** The aggregate "tracks production" only if the YoY Spearman is
>= 0.5 in development with permutation p < 0.05 **and** >= 0.3 with the same sign in the
holdout. Anything weaker is reported as a failure.

**Known-event checks** (expected direction written before looking):
- Escondida, COVID crew cuts, 2020Q2 (material mined -25% YoY): index lower than 2019Q2.
- Escondida strike, 9 Feb - 24 Mar 2017 (separate 2016-17 stack, calibrated on 2016H2): pit
  index drops during the strike.
- Spence 2024Q1 (material mined -36% YoY): index lower than 2023Q1.
- Quebrada Blanca: QB2 mining ramps up 2022-2024: index rises.
- Chuquicamata: pit wound down after the move underground in 2019: index falls over time.
- Los Pelambres drought 2019-2022 limited the plant, not the pit: no clear pit signal expected.
