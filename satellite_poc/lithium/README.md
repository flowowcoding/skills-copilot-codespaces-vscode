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
