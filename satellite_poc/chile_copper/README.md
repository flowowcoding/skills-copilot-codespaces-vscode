# Chilean copper: does pit activity across many mines track national supply?

Single-mine work (sections 3-4 of `../README.md`) showed the index sees **whether** a mine
operates, but not **how much** it produces. This section tests the remaining idea: add up pit
activity across most of Chile's big open pits and see whether the total tracks copper output.

## Pre-registration (written 2026-10-10, before any index was computed)

Everything below was fixed before computing a single index value or correlation. The ground
truth values had been downloaded and glanced at for parsing, but no comparison was made.

**Mines (15 operations, 17 Cochilco columns).** Escondida, Zaldívar, Radomiro Tomic,
Chuquicamata, Ministro Hales, Gabriela Mistral, Spence, Sierra Gorda, Centinela (sulphides +
oxides), Collahuasi, Quebrada Blanca, El Abra, Los Pelambres, Los Bronces, Caserones,
Candelaria, Mantos Blancos. Together 77-81% of Chilean mine output (2018-2025). Underground mines
(El Teniente, Andina) are excluded.

**Pit zones.** Hand-drawn polygons over the pits only (not dumps, pads, plants or tailings),
drawn on Sentinel-2 images from Nov 2025 - Mar 2026 (`chip.py`), stored in `mines.json`,
shown in `figures/pit_zones.png`.

**Index** (`activity_index.py`, frozen):
- Sentinel-2 L2A, 2018-01 to 2026-10, one tile + orbit per site, brightness = red (B04) + SWIR
  (B11) at 20 m (`s2bright.py`). Clouds and snow masked with a spectral rule (blue > 0.20 and
  blue > 0.9 x SWIR, dilated 40 m); images with > 10% of the box masked dropped.
  *Amendment made before any index was computed:* the first download used ESA's scene
  classification (SCL) for masking, as in `../s2stack.py`. Its pre-2022 processing labels bright
  dumps, leach pads and pit benches as cloud or snow (16% of the Escondida box masked on
  average in 2018-21, 3% from 2023; `figures/scl_mask_bias.png`), which would hide the mines
  and put a break into every series at the 2022 reprocessing. That download was discarded.
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

## Data

| file | what | source |
|---|---|---|
| `cochilco_monthly_by_operation.csv` | monthly payable copper by operation, kt, 2014-01 to 2026-07, 42 operations + total | [Cochilco xlsx](https://www.cochilco.cl/web/download/951/cobre/12683/produccion-de-cobre-mina-por-empresa-mensual.xlsx), linked from [this page](https://www.cochilco.cl/web/historico-produccion-de-cobre-y-molibdeno/) |
| `bhp_material_mined_quarterly.csv` | Escondida and Spence material mined, kt per quarter, 2017Q4-2026Q2 | 31 BHP Operational Review 6-K filings on SEC EDGAR (URL per row) |
| `anglo_ore_mined_quarterly.csv` | Los Bronces and Collahuasi ore mined, t per quarter, 2018Q3-2026Q2 | 26 Anglo American quarterly production reports (URL per row) |
| `mines.json` | pit polygons and stack boxes | drawn here |
| `results/<mine>_pairs.csv` | index per image pair, variants R/F/A, pixel counts | `activity_index.py` |

Codelco, Antofagasta and the other operators publish only copper output or plant throughput,
not material moved, so the secondary ground truth covers four mines (BHP, Anglo American).

**Sentinel-1 over Chile.** Radar coverage did not stop when Sentinel-1B failed (Dec 2021):
every site checked (Escondida, Collahuasi, Los Bronces, Caserones) kept at least one orbit at
12-day revisit through 2022-24 (about 25-60 scenes a year per site, back to 6-day in 2025-26).
It was not needed here because the Atacama is clear on most Sentinel-2 passes.

## Development results (2019Q1-2024Q4), written down before the holdout was run

Run on 2026-10-10 15:10 UTC (`python evaluate.py results --variant R --period dev`).

**Aggregate, YoY (primary): r = -0.70 (Spearman), wrong sign.** Covered production vs
aggregate activity, n = 20 YoY quarters; Pearson -0.72; signs agree in 8 of 20 quarters.
Against total Chile -0.63. The circular-shift p is 0.07, but with 20 points only 13 shifts
exist, so 0.07 is the smallest p this test can give. Variants F and A give the same picture
(-0.68, -0.73). QoQ -0.30, monthly YoY -0.39. **Pre-registered criterion: failed.**

**Per mine vs copper produced, YoY Spearman:** median about +0.1; only Gabriela Mistral
(+0.48) clears +0.3; Los Pelambres is -0.56 (n = 14, many snow-masked quarters). QoQ is near
zero or negative almost everywhere.

**Per mine vs material / ore mined (secondary), YoY Spearman:** Spence +0.48 (Pearson +0.57),
Escondida +0.23, Collahuasi +0.16, Los Bronces +0.16 (n = 10). All positive, all weak.

The development period already says the index does not track output, either per mine or in
aggregate. The holdout is run anyway, unchanged, so the result is on record.

## Holdout (2025Q1-2026Q2), run once after the section above

| aggregate test | development 2020Q1-2024Q4 | holdout 2025Q1-2026Q2 | all 2020Q1-2026Q2 |
|---|---|---|---|
| **YoY vs covered output (primary), Spearman** | **-0.70** (n 20) | +0.43 (n 6) | -0.47 (n 26) |
| YoY vs covered output, Pearson | -0.72 | +0.54 | -0.58 |
| YoY signs agree | 8 / 20 | 6 / 6 | 14 / 26 |
| YoY vs total Chile, Spearman | -0.63 | +0.43 | -0.36 |
| QoQ vs covered output | -0.30 (n 23) | +0.26 (n 6) | -0.22 |
| monthly YoY vs covered output | -0.39 (n 60) | +0.03 (n 19) | -0.27 |

The holdout turns positive, but with 6 points a Spearman of 0.43 is far from significant (the
5% critical value is about 0.89), and it flips the sign of the development result rather than
confirming it. Variants F and A give +0.31 in the holdout. **Verdict: the aggregate index does
not track Chilean copper output.** `figures/chile_aggregate_yoy.png`

**Per mine, YoY Spearman vs copper produced** (variant R unless stated;
`figures/chile_mines_index_vs_production.png`):

| mine | YoY dev (n) | YoY holdout (n) | QoQ dev | YoY dev, F | YoY dev, A |
|---|---|---|---|---|---|
| escondida | -0.16 (20) | -0.54 (6) | -0.01 | -0.28 | -0.20 |
| zaldivar | -0.01 (20) | +0.37 (6) | -0.20 | -0.12 | +0.04 |
| radomiro tomic | +0.19 (20) | -0.14 (6) | -0.20 | +0.14 | +0.05 |
| chuquicamata | +0.18 (20) | +0.14 (6) | -0.11 | +0.19 | +0.19 |
| ministro hales | -0.00 (20) | +0.77 (6) | -0.05 | +0.10 | -0.09 |
| gabriela mistral | +0.48 (20) | +0.89 (6) | -0.25 | +0.35 | +0.40 |
| spence | +0.17 (20) | -0.31 (6) | -0.02 | +0.36 | +0.25 |
| sierra gorda | -0.17 (20) | +0.77 (6) | +0.22 | -0.25 | -0.13 |
| centinela | +0.01 (20) | -0.31 (6) | -0.44 | +0.02 | +0.01 |
| collahuasi | +0.13 (20) | -0.66 (6) | +0.13 | +0.06 | +0.15 |
| quebrada blanca | +0.00 (20) | +0.09 (6) | +0.06 | +0.03 | +0.01 |
| el abra | +0.09 (20) | +0.60 (6) | -0.26 | +0.14 | +0.17 |
| los pelambres | -0.56 (14) | +0.80 (4) | -0.27 | -0.52 | -0.62 |
| los bronces | +0.12 (10) | n/a (2) | -0.05 | -0.09 | +0.16 |
| caserones | -0.07 (15) | -0.90 (5) | -0.08 | -0.14 | -0.09 |
| candelaria | +0.29 (20) | -0.26 (6) | +0.27 | +0.37 | +0.39 |
| mantos blancos | +0.23 (20) | +0.03 (6) | +0.05 | +0.28 | +0.27 |

Median +0.09 (development) and +0.06 (holdout). Only Gabriela Mistral is positive in both
periods (+0.48, +0.89), which is about what chance gives among 17 mines.

**Per mine vs material / ore mined (secondary):**

| mine | measure | YoY dev (n) | YoY holdout (n) | QoQ dev | QoQ holdout |
|---|---|---|---|---|---|
| escondida | material mined | +0.23 (20) | -0.14 (6) | -0.07 | +0.54 |
| spence | material mined | +0.48 (20) | +0.20 (6) | +0.21 | +0.49 |
| los bronces | ore mined | +0.16 (10) | n/a (2) | +0.10 | n/a |
| collahuasi | ore mined | +0.16 (20) | -0.89 (6) | +0.26 | -0.43 |

Spence is the one mildly encouraging case (positive in all four cells). The rest is noise.

## Known events

| event | expected | index | seen? |
|---|---|---|---|
| Escondida COVID crew cuts, 2020Q2 vs 2019Q2 | lower | 13.1 vs 22.0 pts (-40%) | yes, but the median other mine fell 23% too (Escondida ranks 4th of 17) |
| Spence 2024Q1 vs 2023Q1 (material mined -36%) | lower | 3.2 vs 10.0 (-68%) | yes, but it falls in the 2024 drop that hit every mine (median -42%; rank 5 of 17) |
| Escondida strike, 9 Feb - 24 Mar 2017 | lower | 20.0 (3 pairs) vs 17.1 rest of 2017 | **no**; the pair fully inside the strike (28 Feb-20 Mar) is one of the year's highest |
| Quebrada Blanca, QB2 ramp-up 2022-24 | rising | 20 (2021) → 12, 15, 7 (2022-24) | **no**; output went from 2-3 kt to 50-60 kt a quarter while the index fell |
| Chuquicamata pit winding down | falling | flat 18-22 in 2019-23, then 14, 10, 11 | late and partly the common 2024 drop |
| Los Pelambres drought 2019-22 (plant-limited) | no pit signal | noisy, many snow-masked quarters | n/a |
| Escondida July 2026 storms (*not pre-registered*) | lower | 18.4 vs 10.0 in July 2025 | **no**: higher; storms change surface brightness, which reads as activity |

`figures/chile_events.png`. Sources for the events: BHP 6-K filings (material mined), Cochilco
(July 2026: Chile -9.4% YoY, Escondida 89 kt vs 115 kt), press coverage of the 2017 strike.

## Why it fails (exploratory, after the pre-registered tests)

1. **Copper output does not follow earthmoving, even in the companies' own numbers.** Over
   2020-26, YoY material mined vs YoY copper produced has Spearman **+0.01 at Escondida**,
   +0.38 at Spence; ore mined vs copper is +0.26 at Los Bronces and -0.12 at Collahuasi.
   Output is set by plant throughput, head grade and recovery. Escondida's 2021-23 dip (250-300 kt a quarter) and 2024-25 recovery (310-350 kt) were
   grade-driven, while tonnes moved stayed between 87 and 122 Mt a quarter throughout. A
   perfect pit-activity sensor would still not track copper.
2. **Aggregation amplifies the common error, not the signal.** Summing mines averages away
   mine-specific noise but keeps anything every mine shares. The shared component here is
   imaging, not mining: in 2023 all 17 mines sat above their own 2019-26 mean, in 2024 only 1
   did (median index 14.6 → 8.2), while covered output rose 6%. At the switch from ESA
   processing baseline 03.00 to 04.00/05.10 (25 Jan 2022) the median index jumped from 5.5 to
   13.5 within 60 days, and it rose at 16 of 17 mines. The 2024 drop happens within one baseline (05.10)
   and is unexplained. These two shared moves (2022 up, 2024 down) alone produce the negative
   development correlation: dropping 2022 and 2024 leaves -0.16 (n 12).
3. **The index sees bright-surface change, which weather also makes.** Rare Atacama storms
   (July 2026) and winter shadows in deep pits raise the index (mid-year peaks are visible at
   Chuquicamata). The Andes sites (Los Bronces, Los Pelambres, Caserones) lose most winter
   images to snow: Los Bronces keeps 147 images in 8.7 years and 10 usable YoY quarters.

## Trading relevance and lead time

- **Timeliness is real.** Sentinel-2 images reach Planetary Computer within a day or two, and the
  Atacama is clear on most 5-day passes. A monthly index is ready a few days after month end.
  Chile's official numbers come later. INE publishes national copper output about 30 days
  after month end (July 2026 on 31 August). Cochilco's by-company table comes about 40 days
  after (July 2026 data was reported by 11 September). Company quarterlies arrive 2-5
  weeks after quarter end (BHP's June-quarter review on 17 July). So the head start is about
  4 weeks against INE, 5-6 weeks against Cochilco, and up to ~3 months for an early-quarter
  month against the company reports.
- **But a fast signal that does not track the target is worth nothing.** On this test it
  points the wrong way in development, and the holdout is too short to rescue it. Monthly YoY
  correlation is -0.39 (development) and +0.03 (holdout). There is no evidence it would beat
  simply waiting for INE.
- **What might work instead** (untested): measure what sets output rather than earthmoving.
  Concentrator and SX-EW plant activity, thermal or night lights at smelters and ports,
  concentrate shipments at Coloso, Patache and Antofagasta (ship counts from Sentinel-1/2),
  and reservoir and tailings-water levels for drought-limited plants. And use a consistently
  reprocessed archive (ESA Collection-1) before trusting any multi-year change index.

## Caveats

- Pit polygons are hand-drawn on 2025-26 imagery. Pits grow, so in 2019 some of each polygon
  was undisturbed ground. The rolling busy-pixel selection (variant R) is meant to absorb
  this. Variant A (all pit pixels) gives the same answer.
- The Planetary Computer archive mixes processing baselines: Microsoft-processed 02.12 for
  2018-21, then ESA 03.00-05.13. Breaks between them are the largest error in this test.
- Cochilco reports payable copper by operation. Some columns combine pits with underground
  mines (Chuquicamata since 2019, Candelaria) or with leach pads fed from stockpiles. Plant
  feed from stockpiles separates output from mining in time.
- Small samples: 20 development and 6 holdout YoY quarters. Correlations of ±0.4 are noise
  at these sizes, and the circular-shift p-value cannot go below 0.07 with 20 points.
- The 2017 strike test uses the sparse 2016-17 archive (33 images, gaps of up to 21 days).

## Reproduce

```bash
# ground truth
python ground_truth.py cochilco_mensual.xlsx cochilco_monthly_by_operation.csv
python bhp_material_mined.py BHP_6K_DIR ids.txt bhp_material_mined_quarterly.csv
python anglo_ore_mined.py ANGLO_PDF_DIR urls.txt anglo_ore_mined_quarterly.csv
# zones (check by eye)
python zones_figure.py CHIP_DIR figures/pit_zones.png
# imagery: 15 stacks, 150-400 MB each, ~6-12 min each
for s in escondida chuqui mh gaby spence sierra_gorda centinela collahuasi qb el_abra \
         los_pelambres los_bronces caserones candelaria mantos_blancos; do
  python s2bright.py $s 2018-01-01/2026-10-10 STACKS/${s}_s2.npz
  python activity_index.py STACKS/${s}_s2.npz $s results
done
python s2bright.py escondida 2016-07-01/2017-12-31 STACKS/escondida_2016_s2.npz
python activity_index.py STACKS/escondida_2016_s2.npz escondida results --calib-end 2017-01-01 --maxgap 21
# evaluation, events, figures
python evaluate.py results --variant R --period dev --out results/eval_R_dev
python evaluate.py results --variant R --period holdout --out results/eval_R_holdout
python evaluate.py results --variant R --period all --out results/eval_R_all
python events.py results figures/chile_events.png
python plots.py results figures
```

| script | does |
|---|---|
| `chip.py` | Sentinel-2 true-colour chip with lon/lat grid, optional pit-polygon overlay |
| `zones_figure.py` | overlays every stack's pit polygons and tiles them (`figures/pit_zones.png`) |
| `s2bright.py` | Sentinel-2 red+SWIR brightness stack, spectral cloud/snow mask |
| `activity_index.py` | pit activity index per image pair, variants R/F/A, event mode |
| `ground_truth.py` | Cochilco monthly xlsx → tidy CSV |
| `bhp_material_mined.py` | BHP 6-K → Escondida/Spence material mined |
| `anglo_ore_mined.py` | Anglo American reports → Los Bronces/Collahuasi ore mined |
| `evaluate.py` | pre-registered tests; writes `results/eval_*`, `index_quarterly_*.csv`, `index_monthly_*.csv` |
| `events.py` | known-event checks and figure |
| `plots.py` | small multiples and aggregate figure |
