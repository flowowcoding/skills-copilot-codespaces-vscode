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
