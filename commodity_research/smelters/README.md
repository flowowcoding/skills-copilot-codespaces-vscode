# Copper smelter activity from free satellite data

(Results sections are filled in below the pre-registration, after it was written.)

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
