# 5. Lithium: Thacker Pass construction and Greenbushes mining

## Pre-registration (written 2026-10-10, before any index was computed)

Production figures and company milestones were collected first. The Thacker Pass Sentinel-2
stack had been downloaded but not analysed. No Greenbushes satellite index had been computed.

### A. Thacker Pass (Lithium Americas, NYSE: LAC)

- **A1. Footprint.** Monthly disturbed area from Sentinel-2. A pixel counts as disturbed when
  its spectral change against the pre-construction baseline (Jun-Sep 2019-2021 median) is above
  the 99.5th percentile of the same change in undisturbed control ground. The pre-construction
  months should read close to zero. Construction began in March 2023, and the series should rise
  from there.
- **A2. Progress vs disclosures.** Quarterly change in disturbed area and in Sentinel-1
  bright-structure count (plant zone) against the construction capex reported each quarter.
  - Statistic: Spearman rank correlation at lags −1, 0 and +1 quarter.
  - "Satellite leads" only if the lag where satellite comes first is clearly the strongest.
  - A footprint turning point dated before the filing or release that disclosed it also counts
    as leading.
- **A3. Stock.** For each LAC quarterly report since Oct 2023: the 3-day return in excess of LIT
  (lithium ETF) against the satellite progress "surprise" (this quarter's growth in footprint or
  structure minus the previous quarter's).
  - Exploratory only: n ≈ 11.
  - Pass if the sign agreement is at least 8 of 11.
- **A4. Umbra 2025.** Share of plant-zone pixels in the top 5% of brightness, in rank space,
  per collect. It should increase over 2025 as steel goes up. Statistic: Spearman ρ against time.

### B. Greenbushes (Talison; IGO reports it each quarter)

- **Data.** Total material mined (BCM, 100% basis) per quarter, 1Q22-4Q26 (20 quarters, IGO
  fiscal year ending June), parsed from IGO quarterly activities reports.
- **B1. Primary test, frozen method.** The Karlawinda optical index (`../optical_zones.py`) is used
  unchanged: THRESH 0.12, SHADOW −0.3, busy pixels picked before 2021-07-01, scored afterwards.
  - Zones are drawn from imagery only.
  - Statistic: Pearson r between the quarterly mean pit-zone index and material mined, over all
    20 quarters. No settings were tuned, so every quarter is out of sample.
  - **Pass:** r ≥ 0.5 with one-sided p < 0.05, **and** quarter-on-quarter changes also correlate
    positively (r > 0.3), which guards against two trends correlating by accident.
- **B2. Tuned variant with holdout.**
  - Tuned on 1Q22-4Q24 (12 quarters). The only knobs are the zone (pit, pit+dumps) and
    THRESH ∈ {0.08, 0.12, 0.16}.
  - Scored once on the holdout 1Q25-4Q26 (8 quarters).
- **B3. Level changes at plan changes.**
  - (i) 29 Jan 2024, FY24 guidance cut for price reasons: mean pit index over 2 quarters before
    vs 2 quarters after. The reported mining figures predict an *increase*, because material
    mined doubled while processing was cut.
  - (ii) Mid-2025 fleet cut (38 to 23 trucks; material mined fell from 5.1 to 3.4 Mm³ BCM):
    Jan-Jun 2025 vs Jul-Dec 2025. Predicted: a decrease.
  - Statistic: Welch t-test on per-image-pair values.
- **B4. Umbra 2025.** Pit-zone change between consecutive collects with matching geometry, in rank
  space. Predicted: Jul-Dec 2025 below Jan-Jun 2025 (material mined −33%).

## Data

| what | source | file |
|---|---|---|
| Sentinel-2 L2A, 6 bands at 20 m, clouds and snow masked | Planetary Computer | `s2bands.py`. Thacker Pass: 305 clear images, Jun 2018-Oct 2026. Greenbushes: 263 images, 2019-Oct 2026. |
| Sentinel-1 RTC VV, 10 m, orbit 64 ascending | Planetary Computer | `../s1stack.py`. Thacker Pass: 334 passes, 2019-Oct 2026. Australia has a 2022-early 2025 gap, so it was not used for Greenbushes. |
| Umbra spotlight SAR, about 0.5 m, warped to 4 m | Umbra open data (S3) | `umbra.py`. Thacker Pass: 57 collects. Greenbushes: 47 collects. All Jan-Nov 2025. |
| LAC milestones and quarterly capex | SEC EDGAR (6-K, 8-K, 10-Q, 10-K), one source URL per row | `thacker_milestones.csv`, `thacker_capex.csv` |
| Greenbushes material mined, ore mined, spodumene (100% basis) | IGO ASX quarterly reports, 1Q22-4Q26 | `igo_greenbushes.py` → `greenbushes_production.csv` |
| Greenbushes plan changes | IGO ASX releases | `greenbushes_events.csv` |
| LAC and LIT daily prices | Yahoo Finance chart API | cached by `thacker_eval.py` |

## Results: Thacker Pass

Zones are in `figures/thacker_zones.png`.

**A1. Footprint: pass.**
- The pre-registered version uses a Jun-Sep baseline and is scored on Jun-Sep months
  (`results/thacker_footprint_prereg.csv`).
- Before construction (2018-2022) it reads −0.09 to +0.16 km². The worst single month was
  0.24 km² (Apr 2020).
- Summer means: 0.9 km² in 2023 (1.4 by September), 2.2 in 2024, 2.8 in 2025 and 4.7 in 2026.

Deviation from the pre-registration:
- With the Jun-Sep baseline, Oct-Feb collapsed to zero: snow and low sun flood the per-month
  control threshold.
- `footprint.py --seasonal` compares each month with the same calendar months of 2018-21. Months
  whose control threshold is above 0.45 are dropped (`figures/thacker_footprint.png`).
- Dec-Feb are still unusable, and October reads 10-20% low (visible as a dip at the end of each
  season).

| zone (snow-free months) | Sep 2023 | Aug 2024 | Aug 2025 | Jul 2026 |
|---|---|---|---|---|
| plant site | 1.30 | 1.78 | 1.92 | 2.28 |
| east (ponds, laydown, camp) | 0.25 | 0.48 | 0.86 | 1.67 |
| west (haul road, pit area) | 0.00 | 0.09 | 0.22 | 1.13 |

**Plant structures (Sentinel-1).** `figures/thacker_structures.png`.
- The bright-structure area in the plant zone sat at zero until autumn 2025 (noise about ±0.3 ha).
- From there it climbed: 1.2 ha (Q4-25), 2.2 (Q1-26), 9.0 (Q2-26), 15.2 (Q3-26) and 16 ha
  (early Oct 2026).
- This is the steel going up. The optical footprint can't see it, because the ground had already
  been cleared.

**A2. Progress vs disclosed capex: contemporaneous only, no lead.**

Spearman ρ, 13 quarters (2023Q2-2026Q2). Lag +1 means the satellite change comes one quarter
before the capex:

| satellite series | lag −1 | lag 0 | lag +1 |
|---|---|---|---|
| Δ disturbed area | −0.03 | +0.16 | +0.38 (p 0.20) |
| Δ radar structures | +0.59 (p 0.03) | +0.59 (p 0.03) | +0.37 |

- Under the pre-registered rule, "leads" needs the lead lag to be clearly strongest. It isn't.
- The structure correlation comes from the 2025Q4-2026Q2 ramp, when both series rose together.
- Disturbed area did not track spending:
  - 2023 cost $0.19B and added 1.4 km².
  - 2025 cost $0.61B and added only 0.7 km², because the money went into concrete and steel inside
    ground already cleared.

**Timing against disclosures.** The satellite confirmed each guided step about a month before the
company did. None was a surprise:

| event | first seen from orbit | company disclosure | already guided? |
|---|---|---|---|
| major earthworks start | Jul 2023 composite (0.2 → 0.9 km²) | 9 Aug 2023 (Q2 results) | yes, "H2 2023" since 2 Mar 2023 |
| 2024 stall | plant zone flat at 1.78 km², Apr-Sep 2024 | 15 Mar 2024: capex cut until DOE loan | yes, disclosed first |
| restart | Mar 2025 (east zone 0.24 → 0.64 km²) | limited notice to proceed (10-K, 28 Mar 2025); FID 1 Apr 2025 | same time |
| first steel | radar structures above noise 6-18 Oct 2025 | 13 Nov 2025 (Q3 results) | yes, "Sep 2025" since May 2025 |
| Q3 2026 steel | +6 ha in Q3 2026 | Q3 report due about Nov 2026 | peak construction guided for late 2026 |

**A3. Stock: fail.**
- Across 12 LAC quarterly reports, the 3-day return in excess of LIT agreed in sign with the
  footprint surprise 7 times out of 10 (binomial p 0.17, ρ −0.22). It agreed with the structure
  surprise 5 times out of 12 (ρ +0.08).
- The pre-registered bar was 8 of 11.
- LAC's large moves all came from financing and policy news (excess over LIT):

| date | news | excess move |
|---|---|---|
| 14 Mar 2024 | DOE conditional commitment | +15% |
| 16 Oct 2024 | GM joint venture | +23% |
| 28 Oct 2024 | DOE loan closes | +22% |
| 24 Sep 2025 | Reuters reports government wants an equity stake | +96% raw |
| 30 Sep 2025 | DOE/GM agreement | +21% |

- None of those is visible from orbit.

**A4. Umbra 2025: fail.**
- The plant-zone bright excess *fell* through 2025 (ρ −0.46, p 0.0003, n 57; ascending
  right-looking only: ρ −0.47, n 26) (`figures/umbra_thacker_bright.png`).
- The high values are in Jan-Feb, which points to snow darkening the control ground rather than
  less plant.
- The look geometry varies from collect to collect (16-45° incidence, both sides), and Sentinel-1
  shows little steel before October 2025.
- Ad hoc sub-metre collects with mixed geometry did not beat the regular Sentinel-1 orbit.

## Results: Greenbushes

Zones are in `figures/greenbushes_zones.png`. Quarterly series are in
`results/greenbushes_quarterly.csv`. `figures/greenbushes_index_vs_material.png` shows material
mined against the frozen pit index.

Material mined moved far more than at Karlawinda. It held at 1.2-1.6 Mbcm through FY22-FY24,
rose to 5.3 Mbcm in the Mar-2025 quarter, then fell to 3.0-3.5 Mbcm after the fleet cut.

| test | result | verdict |
|---|---|---|
| **B1** frozen pit index vs material mined (20 q) | r = +0.34 (p 0.07); quarter-on-quarter r = −0.25. Dumps r = +0.42 but QoQ −0.10; plant +0.04; tailings −0.10 | **fail** |
| **B2** tuned on 12 q, scored on 8 holdout q | selected pit+dumps, THRESH 0.08 (tune r = 0.41) → **holdout r = −0.13** | **fail** |
| **B3 (i)** 29 Jan 2024 guidance cut | pit index 19.0 → 24.7 (t 1.4, p 0.17). Points the way the mining data predict (stripping up), but not significant | inconclusive |
| **B3 (ii)** 2025 fleet cut (−33% material) | pit index 21.1 → 28.4 (t 1.2, p 0.24), the wrong way | **fail** |
| **B4** Umbra pit change, H1 vs H2 2025 (29 matched pairs) | 3.9% → 4.4% excess (t 0.45, p 0.66), no drop | **fail** |

The 2024 "curtailment" at Greenbushes cut processing and sales, not mining. Material mined doubled
in the same quarter because of deferred stripping for the CGP3 expansion. Reading a production cut
from pit activity would have got the sign wrong.

**Exploratory, found after the tests failed; not a result.**
- The pit and plant indices move together (quarterly r = 0.90). Something mine-wide (moisture,
  dust, residual haze over bright surfaces) dominates the index, and the natural-ground control
  doesn't remove it.
- Pit minus plant correlates with material mined at r = 0.68 (detrended 0.71; first 12 q 0.77;
  last 8 q 0.75; QoQ 0.39, p 0.10). It also catches the Sep-2025 drop.
- I chose it after seeing all 20 quarters, so these numbers are in-sample.
- **Forward test (registered 2026-10-10).**
  - The Jul-Sep 2026 quarter (IGO 1Q27) has only 3 clear image pairs (winter). Pit minus plant
    = −1.3.
  - The 20-quarter fit predicts **2.4 Mbcm (±1.0) total material mined**, against 3.44 Mbcm in
    the June quarter.
  - Check it against IGO's September 2026 quarterly (due late Oct 2026) before trusting the
    variant at all.

## Caveats

- **Thacker Pass.**
  - One project, 13 capex quarters, 12 earnings events: low power throughout.
  - Capex for 2023Q4, 2024Q4, 2025Q4 and 2026 is derived from cumulative or balance-sheet
    figures (see `thacker_capex.csv`), and the bases mix cash and capitalised costs.
  - The bright-structure count will saturate once the plant zone is built out.
- **Greenbushes.**
  - Winter cloud leaves 5-13 image pairs per quarter.
  - The frozen method picks busy pixels from 2019-21, but the pit has since grown west and south
    into ground that was forest then.
  - The 1Q22 material figure is from a table with a units typo ("'000 bcm").
- **Umbra.**
  - Only 2025.
  - Geometry and timing are chosen by Umbra, not by the question.
  - The south-up GECs needed warping, not windowed reads.

## Trading relevance

- **Construction tracking works** at no cost:
  - Sentinel-2 maps the earthworks.
  - Sentinel-1 measures steel going up.
  - Both are dated within weeks, at a site disclosed only quarterly.
- **But for LAC it added no tradeable information.**
  - Every physical milestone was guided in advance and confirmed about a month later. The
    satellite only shortened the confirmation lag.
  - The stock moved on financing, government and partner news, none of which is visible from
    orbit.
  - Where satellites would matter is the case they haven't tested: a project that slips silently
    against guidance (earthworks or steel stalling while the company says "on schedule"). The
    footprint and structure series are the monitoring tools for that.
- **Mine output at 10-20 m is still not measurable.**
  - Greenbushes failed with quarter-to-quarter swings of ±30-60%, three times Karlawinda's.
  - Its 2024 price-driven change hit processing, not the pit.
- **What would be needed:**
  - a processing-side signal (stockpile or concentrate shed volumes, tailings deposition), or
  - an index that removes the mine-wide common mode, if the forward test above holds.

## Reproduce

```bash
S=/path/to/scratch            # large stacks (~2 GB) live here, not in git
python s2bands.py -- -118.12,41.675,-117.98,41.74 2018-06-01/2026-10-10 $S/tp_s2.npz
python footprint.py $S/tp_s2.npz '{"plant":[310,410,155,250],"east":[411,490,165,255],"west_pit_road":[100,309,100,250]}' results/thacker_footprint_prereg.csv
python footprint.py $S/tp_s2.npz '{"plant":[310,410,155,250],"east":[411,490,165,255],"west_pit_road":[100,309,100,250]}' results/thacker_footprint_seasonal.csv --seasonal
python ../s1stack.py --bbox -118.12,41.675,-117.98,41.74 2019-01-01/2026-10-10 $S/tp_s1.npz
python radar_structures.py $S/tp_s1.npz -118.046,41.6959,-118.0222,41.7126 2023-01-01 results/thacker_s1_structures.csv
python thacker_eval.py results/thacker_footprint_seasonal.csv results/thacker_s1_structures.csv thacker_capex.csv $S/prices $S/thacker   # → results/thacker_*.csv/json
python umbra.py index "Thacker Pass Lithium Mine, Nevada, United States" results/umbra_thacker_collects.csv
python umbra.py stack results/umbra_thacker_collects.csv -118.095,41.68,-117.995,41.735 4 $S/umbra_tp.npz
python umbra_metrics.py bright $S/umbra_tp.npz -118.046,41.6959,-118.0222,41.7126 results/umbra_thacker_plant_bright.csv

python igo_greenbushes.py $S/asx greenbushes_production.csv
python s2bands.py --maxcloud 70 --maxbad 0.3 -- 116.02,-33.91,116.11,-33.82 2019-01-01/2026-10-10 $S/gb_s2.npz
python -c "import numpy as np; d=np.load('$S/gb_s2.npz'); np.savez_compressed('$S/gb_rs.npz', dates=d['dates'], refl=d['refl'][:,[2,4]])"
python greenbushes_eval.py $S/gb_rs.npz '{"pit":[195,268,160,300],"dumps":[262,312,140,330],"plant":[150,194,190,250],"tailings":[130,235,251,400]}' greenbushes_production.csv $S/gb   # → results/greenbushes_*
python umbra.py index "Greenbushes Mine, Australia" results/umbra_greenbushes_collects.csv
python umbra.py stack results/umbra_greenbushes_collects.csv 116.045,-33.885,116.08,-33.84 4 $S/umbra_gb.npz
python umbra_metrics.py change $S/umbra_gb.npz 116.0617,-33.8737,116.0773,-33.8486 results/umbra_greenbushes_pit_change.csv
python make_figures.py results figures $S/tp_s2.npz $S/gb_s2.npz
```

| script | does |
|---|---|
| `s2bands.py` | multi-band Sentinel-2 stack, clouds and snow masked |
| `footprint.py` | monthly disturbed area per zone vs a pre-construction baseline |
| `radar_structures.py` | Sentinel-1 bright-structure hectares in a zone |
| `thacker_eval.py` | A2/A3: quarterly satellite change vs capex and LAC excess returns |
| `umbra.py` | Umbra open-data catalogue and warped 4 m stack |
| `umbra_metrics.py` | A4 bright-pixel excess; B4 matched-geometry rank change |
| `igo_greenbushes.py` | parse Greenbushes production from IGO ASX quarterlies |
| `greenbushes_eval.py` | B1-B3: frozen and tuned optical index vs material mined |
| `make_figures.py` | figures |
