# Free-satellite proofs of concept

These follow the Cushing backtest (`../cushing_backtest`). Each one asks a single question
first: **can free imagery even see the thing we care about?** We check that against a
known event before spending any effort on trading.

All imagery comes from Microsoft Planetary Computer (free, no account needed).

## 1. Radar car lots: Tesla Fremont (Sentinel-1, 10 m)

**Idea.** Metal reflects radar strongly, so a lot packed with cars should look bright even
though single cars are smaller than a pixel. Radar also sees through cloud. Tesla
historically pushed deliveries at quarter end, so if radar sees inventory, the factory and
its rail yard should look emptier in the last two weeks of each quarter.

**Data.** 179 passes from the same orbit (descending, about 06:00 local), Jan 2022 to Sep 2026.

**Method.** First keep pixels that are bright and change a lot from pass to pass
(`figures/fremont_var.png`). They cluster on the factory and on the rail spur where cars
are loaded onto railcars. Then compare the factory and rail boxes with the same kind of
pixels elsewhere in the scene. Each pixel is measured against its own median, so sensor
and weather drift cancel.

**Result: no quarter-end signal.**

| area | last 2 weeks of quarter | rest of quarter | p |
|---|---|---|---|
| factory | +0.32 dB | +0.48 dB | 0.70 |
| rail yard | +0.73 dB | +0.89 dB | 0.60 |

The difference points the right way but is far smaller than the noise between passes. One
unexplained finding stands out: factory brightness relative to the control fell
steadily, from +2.0 dB (2022) to -0.6 dB (2026). That could be fewer cars stored on site,
or construction and layout changes. It is not validated, so don't trade on it.

## 2. Smelter heat: Century Aluminum Hawesville, KY (Landsat 8/9 thermal, 100 m)

**Idea.** Aluminium potlines run hot around the clock, so a shutdown should show up as a
cooler plant. Hawesville is a clean test: it has been idle since July 2022.

**Data.** 90 cloud-free scenes, 2015 to 2026, all taken around 11:00 local.

**Method.** Find the plant's hottest pixels before 2022 (`figures/hawes_map.png`, which sits
on the potlines in `figures/hawes_zoom.png`). Track their temperature minus the scene median.

**Result: weak and ambiguous.**

| summer (May-Sep), plant minus surroundings | |
|---|---|
| 2016-2018 (only 2 of 5 potlines running) | about +13.7 K |
| 2019-2021 (restarted) | about +13.4 K |
| 2023-2026 (idle) | about +12.1 K |

The plant is still about 12 K hotter than the fields while fully idle, so daytime Landsat
mostly sees sun-heated roofs. There is a drop of roughly 1.5 K after the shutdown, but the
2019 restart caused no rise, so I can't attribute the drop to the potlines. It also takes
months of scenes to see, which is useless for trading. Better candidates would be night
thermal (ECOSTRESS, VIIRS Nightfire) or a plant whose process heat is far higher than its
roof heat (steel blast furnaces, flares).

## 3. Mine activity index: three halted mines (Sentinel-1 radar, 10 m)

**Idea.** An active open-pit mine changes constantly: blasting, haul trucks, stockpiles
growing and shrinking. A radar pass should therefore look very different from the previous
one over the mine, and much less so once the mine goes quiet. Radar sees through cloud and
snow, which matters for tropical and northern mines.

**Index.** For each pass: the share of active mine pixels whose backscatter moved more than
3 dB since the last pass, minus the same share over the surroundings (rain, snow and
moisture move both). Water is dropped, since wind on ponds also changes the radar. Active
pixels are picked on **2021 data only** (busier than 90% of surrounding pixels), and the
index is scored on **2022 onward**, so picking the pixels doesn't bias the test.

**Test cases.** Three single-mine halts with known dates:

| mine | halted | operating | after halt | separation* | same-month gap |
|---|---|---|---|---|---|
| Cobre Panamá (First Quantum) | 24 Nov 2023, protests and court ruling | +7.1 | -2.7 | **4.2** | +9.6 pts, 12/12 months |
| Eagle, Yukon (Victoria Gold) | 24 Jun 2024, heap-leach failure | +5.1 | +0.7 | 1.0 | +3.2 pts, 10/11 months |
| Çöpler, Turkey (SSR Mining) | 13 Feb 2024, heap-leach failure | +0.5 | +0.1 | 0.1 | +0.7 pts, 9/12 months |

\*difference in means divided by the pooled standard deviation of single passes.
`figures/mines_activity.png`

**What this shows.**

- **Cobre Panamá:** unmistakable, and caught within one pass (19 Nov +, 1 Dec -). Not
  seasonal: every calendar month was busier before the halt than after.
- **Eagle and Çöpler: the index measures earthmoving, not production.** Both sites stayed
  busy after the halt.
  - At Çöpler, the slide material was dug out and moved to storage, and containment was
    built through 2024 ([SSR](https://ssrmining.com/2024-copler-incident/)).
  - At Eagle, the receiver recontoured the heap with bulldozers and built ponds, berms and
    an interception fence ([Yukon government](https://yukon.ca/en/node/28133)).
  - Eagle's index only settles near zero in 2025.
- **The tradeable question is still open.** These halts were all public the same day. The
  value would be at small single-mine companies, where a slowdown or a late ramp-up only
  shows in the next quarterly report. The next test is whether the index tracks reported
  quarterly tonnes mined, and whether it moves before the report.
- **A refinement to try:** split the index by zone (pit, waste dumps, process plant). Cleanup
  earthworks sit on pads and in valleys, while production happens in the pit.

## 4. Zones and the production test

### 4a. Split by zone: pits stop, plants and tailings don't

`zones.py` scores each mine zone separately (pit, dumps, heap-leach pad, plant, tailings).
The zones are pixel boxes drawn from before/after Sentinel-2 images (`gridchip.py`), not from
the radar results. Same rules as before: busy pixels are picked on 2021 data and scored
from 2022 on.

| mine | mining zone | same-month drop after halt | months lower |
|---|---|---|---|
| Cobre Panamá | Botija pit | 14.5 pts (was 9.6 for the whole mine) | 12/12 |
| Eagle | pit, Jun-Sep only | +4.4 → -2.2 (separation 1.8) | 10/11 |
| Çöpler | pits / north benches | 3.0 / 5.4 pts | 12/12 |

The plants and tailings kept changing after every halt (water handling, cleanup). Once the
mining zones are isolated, the halt shows at all three mines.

### 4b. Does activity track reported tonnes? Karlawinda (Capricorn Metals)

Karlawinda is a single open-pit gold mine in Western Australia. Capricorn reports material
mined every quarter, and I took 19 quarters (2022Q1-2026Q3) from its ASX reports.

Radar has no passes here from 2022 to early 2025 (the gap Sentinel-1B left), so this test
uses an optical version (`s2stack.py`, `optical_zones.py`). WA is nearly cloud-free, giving
368 clear images. For each image pair: the share of busy pixels whose red+SWIR brightness
changed by more than 12%, after normalising for sun angle against the surrounding desert.
Pixels in deep shadow are dropped. Zones are drawn in `figures/karlawinda_zones_grid.png`.

**I looked at 11 quarters (2023Q4-2026Q2) while choosing settings.** On those, the
waste-dump index reached r = +0.56. Then I froze the settings and scored the 8 quarters I
hadn't looked at:

| zone | tuned (11 q) | unseen (8 q) | all (19 q) |
|---|---|---|---|
| north pit | -0.13 | +0.39 | +0.04 |
| south pit | +0.04 | -0.11 | +0.05 |
| waste dumps | +0.56 | **-0.19** | +0.19 |
| tailings | +0.85 | +0.29 | +0.62* |

\*Both series trend upward with the 2025-26 expansion, so this is not a production signal.

**Quarterly tonnes: no.** The dump correlation was overfit and fell apart on the unseen quarters.
Normal quarter-to-quarter swings of about ±20% are too small for this index.

**Stoppages: yes.** Mining was suspended from 13 Oct to 3 Nov 2022 after a fatal accident.
The north-pit index sat near zero for all four image pairs in that window (1.4 against
12.5 over Jan-Sep 2022). It stayed low through the November ramp-up before recovering
(`figures/karlawinda_suspension.png`).

**But no head start.** Capricorn announced the incident at 5:22 pm on 13 Oct and the restart
on 3 Nov, each on the day it happened. Under ASX continuous disclosure, a stoppage like this
is public before the next satellite pass.

### Where this leaves the trading idea

- Free imagery reliably answers **"is this mine operating?"** but not **"how much did it
  produce?"**
- Major halts at listed miners are disclosed the same day, at least on the ASX, TSX and NYSE.
  So the on/off signal only has value where disclosure is slow or loose:
  - private or state-owned mines that feed a listed buyer, smelter or royalty holder
  - partial slowdowns that a company isn't required to announce
  - commodity-level aggregates across many mines
- These need many sites and a different kind of backtest. The single-mine stock-picking
  idea doesn't survive at 10-20 m.

## Takeaways

- Tests 1 and 2: both free sensors resolve the sites, but neither picks out the business
  signal we wanted above the noise. This matches the Cushing result: at 10-100 m, the hard part is
  never finding the object. It is measuring the small change that matters.
- The cheapest next tests are the ones with a big, slow change:
  - pit and stockpile growth at a single-mine company (Sentinel-2, Sentinel-1)
  - lithium pond area
  - the Fremont long-run decline, checked against Tesla's published Fremont output

## Scripts

| script | does |
|---|---|
| `s2chip.py LON LAT HALF DATES OUT.png ZOOM` | least-cloudy Sentinel-2 true-colour chip |
| `s1stack.py LON LAT HALF DATES OUT.npz` | Sentinel-1 RTC VV/VH stack, most common orbit |
| `fremont_radar.py STACK.npz [OUT.csv]` | quarter-end test and yearly trend |
| `lsheat.py LON LAT HALF DATES OUT.npz` | Landsat 8/9 surface temperature, clouds masked |
| `heat_ts.py STACK.npz REF_END OUT` | hottest-pixel series and map |
| `s2ndvi.py BBOX DATES H W OUT.npy` | Sentinel-2 NDVI on the radar grid (for the mine mask) |
| `activity.py STACK.npz MASK OUT.csv [CALIB_END]` | mine activity index (MASK = NDVI.npy or box:lon0,lat0,lon1,lat1) |
| `halt_stats.py RESULTS_DIR` | before/after statistics for the three mines |
| `plot_mines.py` | `figures/mines_activity.png` |
| `gridchip.py BBOX DATES OUT.png` | Sentinel-2 chip with a pixel grid, for drawing zones |
| `zones.py STACK_DIR OUT_DIR` | radar activity index per zone for the three halted mines |
| `s2stack.py BBOX DATES OUT.npz` | Sentinel-2 red + SWIR stack at 20 m, clouds masked |
| `optical_zones.py STACK.npz ZONES_JSON CALIB_END OUT.csv [SHADOW]` | optical activity index per zone |
| `karlawinda_eval.py ZONES.csv` | index vs reported material mined, tuned vs unseen quarters |

Reproduce:

```bash
pip install -r requirements.txt
python s1stack.py -121.944 37.494 0.022 2022-01-01/2026-10-01 fremont_s1.npz   # ~300 MB
python fremont_radar.py fremont_s1.npz results/fremont_radar.csv
python lsheat.py -86.789 37.945 0.012 2015-01-01/2026-10-01 hawes_st.npz
python heat_ts.py hawes_st.npz 2022-01-01 hawesville
python s1stack.py --bbox -80.69,8.81,-80.62,8.89 2021-01-01/2026-10-01 cobre_s1.npz
python s2ndvi.py -80.69,8.81,-80.62,8.89 2023-01-01/2023-10-31 885 771 cobre_ndvi.npy
python activity.py cobre_s1.npz cobre_ndvi.npy results/cobre_activity.csv 2022-01-01
python s1stack.py --bbox -135.88,63.99,-135.78,64.07 2021-01-01/2026-10-01 eagle_s1.npz
python activity.py eagle_s1.npz box:-135.858,64.013,-135.80,64.048 results/eagle_activity.csv 2022-01-01
python s1stack.py --bbox 38.48,39.39,38.58,39.47 2021-01-01/2026-10-01 copler_s1.npz
python activity.py copler_s1.npz box:38.507,39.411,38.563,39.445 results/copler_activity.csv 2022-01-01
python halt_stats.py results && python plot_mines.py
python zones.py . results
python s2stack.py 120.055,-23.81,120.135,-23.735 2021-01-01/2026-10-01 karla_s2.npz
python optical_zones.py karla_s2.npz '{"north pit":[190,240,145,197],"south pit":[222,282,197,242],"plant":[250,300,165,200],"waste dumps":[160,300,127,250],"tailings":[220,295,240,310]}' 2022-01-01 results/karlawinda_optical_zones.csv -0.3
python karlawinda_eval.py results/karlawinda_optical_zones.csv
```

## Is there sharper free imagery?

Not that is both sharp and frequent everywhere. What exists:

| source | resolution | revisit | catch |
|---|---|---|---|
| Sentinel-2 (used here) | 10 m | 5 days | clouds |
| Sentinel-1 radar (used here) | 10 m | 6 days again since 2026 with S1C + S1D | speckle |
| NISAR radar (NASA/ISRO, launched Jul 2025) | a few metres (sources differ) | 12 days | L-band public since Jul 2026, archive filling in during 2026 |
| Harmonized Landsat-Sentinel | 30 m | 2-3 days | coarser |
| Planet tropical mosaics (ex-NICFI) | ~5 m | monthly | free access ended Jan 2025; successor is non-commercial only |
| NAIP aerial (US) | 0.6-1 m | every 2-3 years | far too infrequent |
| Umbra / Capella open data | under 1 m | ad hoc | only sites they chose |

For mines, 10 m is not the bottleneck: pits and dumps span kilometres. Telling earthmoving
apart from production is the hard part.

The image stacks aren't committed because of their size. `results/` holds the derived time series.

## Mine inventory (named mines with footprint polygons)

`mine_inventory/` joins the ICMM Global Mining Dataset (names, commodities) to the Maus et al.
v2 mining polygons and the Zenodo ML-ready polygons. Of 8,017 ICMM mines, 55% match a
footprint. The output is a GeoPackage and CSV, plus lists of Chile/Peru open-pit copper mines
and lithium sites. See `mine_inventory/README.md` for sources, licences (CC BY-SA from Maus),
method, match rates and caveats. A polygon does not prove a mine is active or surface-worked.
