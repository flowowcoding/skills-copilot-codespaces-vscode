## Equipment counts in the Bingham Canyon pit (Umbra SAR, ~0.5 m)

**Question.** Free 10 m radar can't see single trucks. Umbra's open data has about 0.5 m
X-band SAR, sharp enough to show haul trucks and shovels. Can a count of bright,
vehicle-sized objects in the pit track mining activity?

**Test case (pre-registered before counting).** From Q2 2024, Rio Tinto reported
pit-wall (geotechnical) problems at Kennecott. It changed the mine plan, used more
low-grade stockpile ore in Q3 2024, and mined copper fell 44 % year on year in Q3 2024.
Hypothesis: the geometry-corrected count of mobile equipment in the pit core is **lower
in Apr–Dec 2024 than in Jul 2023–Mar 2024**.

**Data.** All 157 Umbra collects of "Bingham Copper Mine", Jul 2023 to Nov 2025, read
straight from the public S3 bucket. 110 have `_METADATA.json`. The other 47 (mostly
2025) take their viewing geometry from the STAC item, which matches the metadata
wherever both exist. Every GEC uses a rotated geotransform and 108 are in EPSG:4326.
The new windowed reader handles both, so all 157 load (the earlier version lost 43).

### Method

1. **Common grid** (`umbra_detect.py fetch`). Each GEC is read at full resolution over
   the pit core (lon −112.168…−112.132, lat 40.508…40.537) and warped onto one 1 m UTM 12N
   grid with max resampling, so bright points survive.
2. **Detection** (`umbra_detect.py detect`). This works on per-image brightness
   *ranks*, because Umbra changed the GEC amplitude scaling in early 2024 (metadata
   v1.0 → v1.1). A candidate is a blob in the brightest 1 % of the image: 7–400 m², at
   most 25 m across, with a peak in the brightest 0.1 %. It counts only when it stands
   alone on darker ground: few bright pixels in an 8–16 m ring, no bright line through
   it, and not a thin streak. Large saturated targets (shovels and their sidelobe
   crosses) get looser limits. Detections within 10 m are merged. The ring and line
   statistics are computed only at candidate centres, so an image takes 1–5 s (the old
   21×21 median filter took minutes).
3. **Tuning.** Thresholds were set **only by looking at detections**: galleries of chips
   from two images before and two after the product change, with my own hand labels
   (`figures/detection_chips.png`, `figures/detections_*_crop.png`). I did not look at
   counts or test results while tuning. About 55–70 % of detections look like vehicles
   or shovels in both eras. The rest are mostly short bench-crest segments and rubble.
4. **Quality rule.** I dropped collects steeper than 20° incidence (13 of 157). At those
   angles the pit walls lay over and almost every detection was a stretched crest
   segment. This was decided from the galleries before any counts were computed. The
   result without this rule is reported below.
5. **Analysis** (`umbra_analyze.py`). I count only detections inside the footprint
   covered by every image (78 % of the grid). The planned static mask (20 m cells hit in
   more than 25 % of images) removes **0 cells**: nothing sits in the same place often
   enough. The geometry correction is an OLS fit of count on sin/cos azimuth, incidence
   and look side (R² = 0.46). The corrected count is the residual plus the overall mean.

### Result: the pre-registered hypothesis is not supported

| comparison (one-sided, H: later period lower) | n | mean before | mean after | change | Welch p | permutation p | Mann-Whitney p |
|---|---|---|---|---|---|---|---|
| **Pre-registered:** geometry-corrected, Apr–Dec 2024 vs Jul 2023–Mar 2024 | 57 / 42 | 34.4 | 36.9 | **+7 %** | 0.80 | 0.79 | 0.92 |
| Raw count, no geometry correction | 57 / 42 | 42.8 | 24.5 | −43 % | <0.001 | <0.001 | <0.001 |
| Same incidence band only (20–30°), raw | 17 / 42 | 24.2 | 24.5 | +1 % | 0.52 | 0.52 | 0.58 |
| Geometry and period in one regression | 57 / 42 | | | +3.0 objects (+7 %), SE 4.0 | 0.77 | | |
| No 20° incidence filter, corrected | 62 / 47 | 33.1 | 33.7 | +2 % | 0.59 | 0.59 | 0.76 |
| 2025 vs Jul 2023–Mar 2024, corrected | 57 / 45 | 34.4 | 48.3 | +41 % | 1.00 | 1.00 | 1.00 |

Quarterly means (`results/quarterly_means.csv`, `figures/bingham_equipment_timeseries.png`):

| quarter | images | mean incidence | raw count | geometry-corrected |
|---|---|---|---|---|
| 2023Q3 | 22 | 40.7° | 46.6 | 33.3 |
| 2023Q4 | 18 | 43.9° | 54.9 | 37.9 |
| 2024Q1 | 17 | 29.8° | 25.1 | 32.0 |
| 2024Q2 | 19 | 26.8° | 25.5 | 36.5 |
| 2024Q3 | 16 | 26.6° | 22.2 | 36.0 |
| 2024Q4 | 7 | 26.8° | 26.7 | 39.8 |
| 2025Q1 | 12 | 33.8° | 32.7 | 34.3 |
| 2025Q2 | 13 | 35.5° | 49.2 | 46.8 |
| 2025Q3 | 10 | 38.1° | 62.5 | 54.3 |
| 2025Q4 | 10 | 30.5° | 55.8 | 61.1 |

**Reading it.**

- The raw count does fall 43 % after April 2024, but that drop is an artefact. Umbra
  tasked this site at about 41–44° incidence in 2023 and at 16–30° in every collect from
  mid-January to December 2024, and the detector finds about 1.9 more objects per degree of
  incidence. The drop already appears in 2024Q1, before the event.
- Within the same incidence band, Apr–Dec 2024 matches Jul 2023–Mar 2024 almost exactly
  (24.5 vs 24.2).
- The regression's standard error means a fall of about 20 % or more would probably
  have been caught. A small fall cannot be ruled out.
- A flat truck count is also not proof that the geotechnical problem had no effect.
  Rio's statements describe re-sequencing and stockpile feed, which can cut copper
  output without parking the fleet.
- 2025 is clearly higher: +41 % after correction, and +60 % within the 20–30° band
  (38.9 vs 24.2, p = 0.009). I have not checked this against Rio's 2025 Kennecott
  disclosures. It could be real activity (for example a pushback), or a change in
  Umbra's 2025 processing (every 2025 product carries only STAC metadata from a newer
  processor). Treat it as unexplained.

**Exploratory, done after the test: did activity move off the south wall?** The share of
mobile detections in the southern third of the pit core was 40 % before, 47 % in
Apr–Dec 2024 (p = 0.03, two-sided) and 34 % in 2025 (`figures/bingham_spatial_shift.png`).
That points the opposite way to "activity left the south wall", but I don't trust it.
The images are not terrain-corrected (next section), so positions in a 1 km deep pit
shift by hundreds of metres with viewing geometry, and viewing geometry changed
between the periods.

### Caveats

- **No terrain correction.** Umbra GECs are projected onto a reference surface (scene
  height about 1,750 m), not a DEM. In a pit about 1.2 km deep, this moves features by
  hundreds of metres to kilometres depending on incidence and look direction, so the
  fixed box covers somewhat different ground in each image. I tried orthorectifying
  with the Copernicus 30 m DEM, and it made images from different geometries align
  *worse*, so I didn't use it.
- **Static mask.** For the same reason, the planned static mask finds no static cells.
- **Viewing geometry.** Geometry dominates the counts and is confounded with time
  (high incidence in 2023, low in 2024). Only the incidence-matched comparison and the
  regression separate the two, and the matched comparison has just 17 "before" images.
- **Detector precision.** It is roughly 55–70 %, judged by eye on 64 chips rather than
  against labelled ground truth. Rank thresholds also make sensitivity depend on how
  much of the scene is bright layover.
- **Sampling.** One snapshot every 5–10 days says little about a 24/7 fleet. 2024Q4 has
  only 7 usable images.

**Bottom line for trading.** Umbra's free data shows individual haul trucks and shovels,
but with this archive the counts mostly track viewing geometry, not the mine. They
showed no fall during Kennecott's disclosed 2024 trouble. Making this usable would take
fixed-geometry repeat tasking (same incidence and look direction every pass) and proper
terrain correction. A paying customer can order that from Umbra; the open archive
doesn't provide it.

### Files

| file | what |
|---|---|
| `umbra_index.py` | builds the collect index (GEC url plus geometry from metadata or STAC) |
| `umbra_detect.py` | `fetch` (warp to shared 1 m grid, cached in scratch), `detect`, `render` |
| `umbra_analyze.py` | footprint, static mask, geometry regression, pre-registered test, robustness, figures |
| `results/bingham_index.csv` | 157 collects with geometry |
| `results/per_image_counts.csv` | per-image raw, mobile and corrected counts |
| `results/quarterly_means.csv`, `results/test_results.csv` | tables above |
| `results/spatial_south_share.csv` | exploratory south-third share |
| `figures/bingham_equipment_timeseries.png` | corrected count per image and quarterly mean |
| `figures/detection_chips.png`, `figures/detections_*_crop.png` | visual detector checks |
| `figures/bingham_spatial_shift.png` | detection density by period (exploratory) |

Reproduce (the cache needs about 1.5 GB):

```
python umbra_index.py "Bingham Copper Mine" index.csv
python umbra_detect.py fetch index.csv CACHE --workers 6
python umbra_detect.py detect index.csv CACHE dets.json
python umbra_analyze.py index.csv dets.json CACHE OUT
```
