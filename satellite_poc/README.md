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

## Takeaways

- Both free sensors resolve the sites, but neither picks out the business signal we
  wanted above the noise. This matches the Cushing result: at 10-100 m, the hard part is
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

Reproduce:

```bash
pip install -r requirements.txt
python s1stack.py -121.944 37.494 0.022 2022-01-01/2026-10-01 fremont_s1.npz   # ~300 MB
python fremont_radar.py fremont_s1.npz results/fremont_radar.csv
python lsheat.py -86.789 37.945 0.012 2015-01-01/2026-10-01 hawes_st.npz
python heat_ts.py hawes_st.npz 2022-01-01 hawesville
```

The image stacks aren't committed because of their size. `results/` holds the derived time series.
