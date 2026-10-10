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

## 3. Mine activity index: Cobre Panamá (Sentinel-1 radar, 10 m) — works

**Idea.** An active open-pit mine changes constantly: blasting, haul trucks, stockpiles
growing and shrinking. A radar pass every 12 days should therefore change a lot from the
previous one over the mine, and very little once it goes idle. Radar sees through clouds,
which matters in the tropics. Cobre Panamá is a clean test: production halted around
24 Nov 2023, just before Panama's Supreme Court struck down the mining contract on 28 Nov.

**Data.** 156 passes from one orbit, Jan 2021 to Sep 2026.

**Method.** The mine mask is bare ground from a Sentinel-2 image (NDVI < 0.25), with water
removed (wind on the tailings pond also changes the radar). For each pass, the index is the
share of mine pixels whose backscatter moved more than 3 dB since the last pass, minus the
same share over forest (rain and moisture move both). `figures/cobre_activity.png`

**Result: the halt is unmistakable and caught within one pass.**

| | mean index | sd | passes |
|---|---|---|---|
| operating (to mid-Oct 2023) | +2.1 pts | 1.7 | 82 |
| halted (mid-Dec 2023 on) | -2.9 pts | 1.9 | 69 |

The step falls between the 19 Nov (+1.2) and 1 Dec (-0.8) passes. Only 9% of halted passes
score above the operating period's 10th percentile. It isn't seasonal: dry-season quarters
before the halt were positive (2021Q1 +3.4, 2022Q1 +1.5, 2023Q1 +1.9).

**What it does not show yet.** This halt was public news the same day, so here the satellite
gave no head start. The value would be at small single-mine companies, where a slowdown, a
ramp-up that runs late, or a quiet restart only shows up in the next quarterly report.
The next test is whether the index tracks *reported quarterly production* (ore mined or
tonnes moved) at a few such miners, and whether it moves before the report does.

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
| `activity.py STACK.npz NDVI.npy OUT.csv` | mine activity index |

Reproduce:

```bash
pip install -r requirements.txt
python s1stack.py -121.944 37.494 0.022 2022-01-01/2026-10-01 fremont_s1.npz   # ~300 MB
python fremont_radar.py fremont_s1.npz results/fremont_radar.csv
python lsheat.py -86.789 37.945 0.012 2015-01-01/2026-10-01 hawes_st.npz
python heat_ts.py hawes_st.npz 2022-01-01 hawesville
python s1stack.py --bbox -80.69,8.81,-80.62,8.89 2021-01-01/2026-10-01 cobre_s1.npz
python s2ndvi.py -80.69,8.81,-80.62,8.89 2023-01-01/2023-10-31 885 771 cobre_ndvi.npy
python activity.py cobre_s1.npz cobre_ndvi.npy results/cobre_activity.csv
```

The image stacks aren't committed because of their size. `results/` holds the derived time series.
