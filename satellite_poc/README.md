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

## Pit-wall and heap instability: a lead over geotechnical disclosures? (`pit_walls/`)

**Idea.** Halts are announced the same day. Geotechnical problems are not. Rio Tinto's first
word on the Bingham Canyon south wall came in the Q2 2024 review (16 Jul 2024), and it hit output
into 2026. Can free radar see the wall move first?

**Data actually reachable without a login:**
- Sentinel-1 amplitude (Planetary Computer).
- **NASA OPERA DISP-S1 InSAR displacement, per point, through ASF's open displacement-portal API.** The granules themselves need Earthdata. Coverage is North America only, the archive skips winters, and the Apr-Jun 2024 data were only produced in Sep 2025.
- COMET LiCSAR interferograms at 100 m, worldwide.
- Umbra sub-metre SAR of Bingham.
- Not reachable: HyP3, SLCs, EGMS (all need a login).

**Test.** Pre-registered in `pit_walls/prereg.json` before any series was computed:
- 60-day LOS change outside baseline ±3 SD and ≥ 15 mm, for 3 epochs;
- the run must start between D-12 months and D-4 weeks.

Four events: Bingham 2024 south wall, Bingham "Leo" SE-wall failure 31 May 2021, Çöpler heap
13 Feb 2024, Eagle heap 24 Jun 2024.

**Result: 0 of 20 tests detected anything ahead of time; Eagle couldn't be tested.**
- OPERA shows Bingham walls creeping steadily: SE wall −26 to −42 mm/yr since 2016; S wall slowly speeding up, −3 → −8 → −12 mm/yr. Nothing anomalous before July 2024 or before the Leo failure.
- LiCSAR does not reproduce the ~80 mm pre-failure heap motion a vendor reported at Çöpler; the heap is mostly incoherent at 100 m.
- Amplitude sees nothing before any event, as expected.

Details, caveats and figures are in `pit_walls/README.md`. Free, anonymous products give no usable
lead. A lead would need your own near-real-time InSAR, point-scale anomaly detection and many
more events.

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

## 5. Market side: what is it worth to know about a mine disruption early?

`event_study/` asks whether an early warning would pay before anyone spends more on imagery: how much
do miners fall when a disruption is disclosed, does the price move before the disclosure, and does
it keep drifting afterwards?

**Events.** `event_study/events.csv` lists 78 disclosed disruptions (77 from 2015-2026, plus Mount
Polley 2014 for reference). Each row has a source URL, the physical start date where one is known,
the disclosure date and timing, and the mine's rough share of the company. They come from two
places:

- 50 well-known cases from news searches, including all the examples in the brief. These were
  picked because they were big.
- 28 from a keyword scan of 12 years of ASX headlines for 60 miners (incident, fatality, flood,
  fire, wall, cyclone, strike, ...). These were picked by keyword, not by size.

**Data and method.** Daily adjusted closes come from Yahoo. Abnormal returns use a market model
against a sector benchmark:

- GDX or SIL for US gold and silver
- XGD.TO for TSX gold
- COPX for copper and base metals
- PICK for the diversified majors' ADRs
- XME for US coal
- ^AXGD or ^AXMJ for ASX
- local indices for London, Hong Kong and Johannesburg

Day 0 is the first session that could react to the disclosure. Trading halts, which are common on
the ASX, are folded into day 0.

**Data actually used.** 69 events have prices and 68 of those are in the 2015-2026 sample.
Survivorship is a real problem:

- Yahoo has no prices for 7 delisted companies: Trevali, SEMAFO, Turquoise Hill, Newcrest, Tahoe,
  Mandalay and Centamin. In the press these fell roughly 19-41% on the news, so dropping them
  understates the reaction.
- Victoria Gold is measured through its thin US OTC line.
- Two Russian events have no benchmark on Yahoo.

### Results (n = 68)

| window | all | single mine or large share (34) | small share (34) |
|---|---|---|---|
| physical start to day -1 (38 events with a dated start, buy-and-hold) | -0.6% (median +0.1%, t -0.45) | -0.8% (t -0.39) | -0.2% (t -0.26) |
| days -5 to -1 | +0.2% (t 0.28) | +0.4% (t 0.36) | 0.0% (t -0.04) |
| **reaction, days 0 to +1** | **-8.1%** (median -3.2%, t -4.09, BMP t -3.79, 75% negative) | **-14.1%** (median -7.5%, t -3.92) | -2.0% (t -2.73) |
| drift, days +1 to +5 | -2.6% (t -2.07) | -3.5% (t -1.44) | -1.8% (t -2.32) |
| drift, days +1 to +20 | -3.0% (t -1.23) | -5.7% (t -1.26) | -0.4% (t -0.18) |
| drift, days +1 to +60 | -3.7% (t -1.06) | -5.9% (t -0.95) | -1.6% (t -0.47) |

`event_study/figures/car_disclosure.png` plots these paths. Splits are in
`event_study/results/summary.csv`:

- Single-asset companies: -21% over days 0 to +1 (n=14).
- Small caps: -12% (n=18).
- Geotechnical failures: -17%.
- Accidents and fatalities: -4%.
- Weather: no reaction.
- By exchange: TSX -9%, US -12%, ASX -6%.

**1. The market does not know before the announcement.** Prices don't move between the physical
event and the disclosure. That includes cases where the information was clearly private:

- Mosaic's sinkhole was public 12 trading days after regulators were told: drift +2.3%, then no
  reaction.
- St Barbara's Simberi stoppage was disclosed 4 days late.
- Coronado's Mammoth fatality happened during trading on a Friday and was disclosed on the Monday.

The large pre-drifts are all at events where the cause was already public, for example the Panama
protests at First Quantum (-47% before the first halt notice).

**2. Disclosure is almost always immediate.** 64 events have a dated physical start. For 53 of
them, the gap to disclosure was 0 or 1 trading day, and the 1-day cases are nearly all events after
the close or at weekends. Only 8 had a gap of 5 days or more.

### Value of a lead

The trade: short at the close of day -k, cover at the close of the reaction day, hedged with
beta times the benchmark. Costs:

- the full spread (Corwin-Schultz estimate from daily highs and lows; median round trip 0.9%,
  1.3% for small caps)
- 0.05% commission per side
- borrow at 0.5%, 2% or 10% a year for large, mid and small caps

These assume perfect foresight. See `event_study/results/lead_value.csv`.

| lead | all, net (median, t) | single or large share, net | small share, net |
|---|---|---|---|
| 1 day | +6.3% (median +0.9%, t 3.47) | +11.9% (median +4.6%, t 3.64) | +0.6% (t 0.79) |
| 5 days | +5.9% (median +1.7%, t 3.02) | +11.5% (median +5.1%) | +0.3% |
| 20 days | +6.5% (median +4.4%, t 2.73) | +12.3% (median +9.6%) | +0.7% |

- Because nothing happens before disclosure, a 1-day lead is worth almost as much as a 20-day one.
- The mean is driven by a handful of collapses (Victoria Gold, Çöpler, Kingston, Boss).
- Only single-asset or large-share companies are worth watching. When the mine is a small share
  of the company, the lead is worth about the trading cost.
- Retail can rarely take the short side at the small caps where the value is:
  - ASX and TSX-V small caps usually can't be borrowed and have no listed options.
  - Puts exist only for the large US-listed names.
  - The realistic use is a holder selling early, which avoids the same loss without borrowing.
- False alarms cost roughly the round trip, because abnormal returns average zero. A signal on
  single-asset names would break even at roughly 10-20% precision. **The binding constraint is
  timing, not accuracy**: the signal has to arrive before a disclosure that usually comes within a
  day. A 5-12 day revisit cannot do that.

### Drift trade without a satellite

Short at the close of the reaction day (`event_study/results/drift_strategy.csv`). Net returns:

- 5 days: +1.5% (t 1.21)
- 20 days: +1.3% (t 0.54)
- 60 days: +1.0% (t 0.27)

Only 53-57% of trades win. **This is not tradeable as a general rule.** Buying the drop isn't
either.

One subgroup stands out: geotechnical failures (n=16) netted +12.1% over 20 days (t 2.70). Treat
it as a hypothesis, not a rule:

- It was found after the fact among about 15 splits.
- Much of it comes from staged bad news: Freeport's force majeure 15 days after the mud rush,
  Ivanhoe's guidance withdrawal 4 days after the seismic halt, and Victoria Gold's receivership.
- It shrinks to -8.3% (t -1.70) when the later "material" announcement is used as day 0.

### Caveats

- **Selection bias.** Events chosen from news react far more than events chosen by keyword:
  -12.1% against -2.3% (t -1.20) over days 0 to +1. The pooled means overstate what a systematic
  scan would find.
- **Survivorship.** The 7 delisted companies are missing, and they include some of the worst drops.
- **Overlap.**
  - Samarco appears twice (BHP and Vale on the same day).
  - Coronado (5 events), St Barbara, Barrick and Anglo repeat.
  - Two Coronado windows overlap.
  - Results hold when one event per company or cluster is kept, and when overlaps are dropped
    (`results/robustness.csv`).
- **Dates.** Several physical start dates are approximate (Kennecott, Salares Norte, 29Metals
  2024). Release timing within the day is unknown for 18 events. The two-day reaction window
  covers a release that came after the close.
- **Benchmarks.** These are imperfect. FM and IVN are large weights in copper ETFs. The London
  names use the FTSE All-Share. Yahoo's ASX indices were not checked against S&P's own series.
  Market-adjusted returns (beta = 1) give the same answers.

**Bottom line for the satellite programme:**

- An early warning on a single-asset miner would be worth about 5-12% per event. That value is
  real and doesn't depend on how many days early it comes.
- But listed miners disclose halts within a day.
- No free sensor revisits fast enough to get in first.

Satellite work only makes sense where there is no disclosure obligation:

- unlisted mines whose output moves a listed buyer, royalty holder or the commodity price
- slow partial slowdowns that never trigger an announcement

```bash
cd event_study
python fetch_prices.py events.csv PRICE_DIR            # Yahoo daily bars, ~20 MB, not committed
python event_study.py events.csv PRICE_DIR results figures
```
