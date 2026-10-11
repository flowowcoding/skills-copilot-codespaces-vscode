# Weather forecasts as early warning: hurricane cones vs commodity futures

**Question.** Free NHC forecasts show a hurricane threatening a production region days before
landfall. Has the futures price already moved by then, and is anything left to capture?

**Short answer.** At the moment the forecast first threatens, the market has not moved in any
consistent direction. Between that first threat and landfall, prices do not drift in a tradable
way. All five pre-registered rules **failed on the 2018–2026 holdout**. The one regular pattern
comes **after** landfall. In orange juice, prices kept rising for about 20 trading days after a
hurricane actually reached the citrus belt: **8 of 8 events, about +9% net**. That pattern was
found after looking at the data, so it is exploratory. It is registered here as a forward test, not
claimed as an edge. There is no overreaction: storms that miss do not first push prices up, so
there is nothing to fade.

## Data (all free, all point-in-time unless marked)

| what | source | use |
|---|---|---|
| NHC official forecast track per advisory (ATCF `OFCL`), 2000–2026 | https://ftp.nhc.noaa.gov/atcf/archive/ (current season `aid_public/`) | cones, triggers (2000–04 only calibrate the 2005 cone) |
| NCEP GEFS ensemble member tracks (`AP01`–`AP30`) in the same a-decks | same | ensemble share passing within 100 km (descriptive) |
| NHC published GIS cones | https://www.nhc.noaa.gov/gis/forecast/archive/ | validating the rebuilt cones |
| HURDAT2 best track 1851–2025; 2026 operational b-decks | https://www.nhc.noaa.gov/data/hurdat/, https://ftp.nhc.noaa.gov/atcf/btk/ | **hindsight only**: hit/miss labels, landfall day used to split the timeline |
| Futures, continuous front month: OJ=F, NG=F, CL=F, RB=F, CT=F, ZR=F (SB=F context) | Yahoo chart API | returns |
| USDA NASS October Florida citrus forecasts 2004–2024 | nass.usda.gov `cit10YY.pdf` | damage confirmation (`data/usda_citrus_october.csv`) |
| BSEE Gulf shut-in peaks, EIA | press releases via OGJ/Offshore/EIA (URLs in `data/damage_reports.csv`) | damage confirmation |
| Census county/state boundaries 2022 | www2.census.gov GENZ2022 | regions |

**Cones.** For every advisory (7,961 Atlantic advisories, 2005–2026) the NHC cone is rebuilt the way
NHC builds it. The circle radius at each lead time is the 67th percentile of the previous five
seasons' official track errors. Those errors are computed here against HURDAT2, giving a 72 h radius
of 209 n mi in 2005 and 97 n mi in 2026 (`data/cone_radii_nm.csv`). The cone is the hull of the
circles along the official track. Against the published NHC 5-day cones, the overlap
(intersection-over-union) is **0.96–0.97** for Irma, Ian, Milton, Ida and Laura
(`data/cone_validation.csv`; maps in `figures/cone_*.png`). Timing: an advisory is public at
synoptic time + 3 h, and GEFS tracks at + 6 h.

**Regions** (`data/regions.geojson`, fixed before any returns were computed):

* `citrus`: 22 Florida citrus counties.
* `gulf_energy`: the offshore Gulf producing area (97.3–87.5°W, north of 26°N), plus 50 km discs
  around 8 refining/LNG hubs.
* `cotton`: GA, AL, SC, NC, MS, plus the Texas coastal cotton counties.
* `rice`: SW Louisiana and Texas coastal rice counties (exploratory).

**Event set.** The set is systematic, not hand-picked. It contains every Atlantic storm whose 3-day
cone touched a region while NHC forecast hurricane strength: **140 storm–region events from 60
storms** (`data/event_table.csv`). By region, citrus has 27 (8 hits), Gulf energy 34 (23 hits),
cotton 57 (26 hits) and rice 22 (10 hits). All the named storms in the brief are included: Katrina,
Rita, Wilma, Ike, Gustav, Harvey, Irma, Laura, Ida, Ian, Idalia, Helene, Milton and Francine. A
"hit" means an advisory placed the centre within 100 km of the region at ≥ 64 kt, which is known in
real time. The per-advisory threat series is in `data/forecast_overlap.csv`. It holds 18,294 rows:
share of the region inside the 3-day cone, 5-day cone flag, closest forecast distance, forecast
intensity, and the share of GEFS members passing within 100 km by 72/120 h. Isaias (Oct 2026) is
the only event without a full +20-day window, and it is excluded from returns.

## Pre-registration

`PREREGISTRATION.md` was written and hashed (`data/prereg_sha256.txt`, sha256 `8a85a390…`, 02:30 UTC
11 Oct 2026) before any event-window return was computed. It is reproduced at the end of this file.
It also discloses the one earlier look at prices, while checking contract rolls, which included the
Irma, Ian and Katrina windows.

## Results

### 1. When does the price move? (abnormal returns, %, t in brackets, all years)

Day 0 is the first trading day on which the trigger advisory could be traded at the close. L is the
best-track closest approach.

| market | event | n | pre [−10,−1] | day 0 | (0, L] | post (L, L+20] | mean \|CAR\| pre / d0 / 0–L / post |
|---|---|---|---|---|---|---|---|
| OJ | hit | 8 | +2.1 (1.0) | +0.9 (0.9) | −0.9 (−0.5) | **+6.9 (4.6)** | 5.4 / 2.7 / 4.0 / 6.9 |
| OJ | miss | 19 | +1.3 (0.8) | −1.1 (−1.4) | −0.0 (−0.1) | −3.2 (−1.3) | 5.3 / 2.5 / 2.2 / 8.5 |
| NG | hit | 22 | −1.2 (−0.5) | +0.7 (0.7) | +0.0 (0.0) | +1.0 (0.3) | 8.4 / 3.2 / 3.0 / 12.6 |
| NG | miss | 11 | +1.1 (0.4) | −0.5 (−0.5) | −0.0 (−0.0) | +8.0 (2.0) | 7.2 / 2.7 / 3.7 / 13.6 |
| CL | hit | 22 | −2.0 (−1.4) | +0.7 (1.3) | −0.8 (−1.4) | +0.6 (0.3) | 5.6 / 1.7 / 2.0 / 8.5 |
| CL | miss | 11 | +2.4 (2.3) | +0.3 (0.6) | **−2.6 (−3.5)** | +3.3 (1.4) | 3.6 / 1.3 / 2.6 / 7.1 |
| RB | hit | 22 | −2.3 (−1.3) | **+1.9 (2.5)** | −0.0 (−0.0) | +0.1 (0.0) | 5.3 / 2.7 / 1.9 / 11.3 |
| RB | miss | 11 | +0.3 (0.2) | +0.2 (0.4) | **−2.3 (−3.3)** | +2.2 (0.9) | 4.3 / 1.6 / 2.6 / 6.9 |
| CT | hit | 25 | −0.7 (−0.6) | +0.2 (0.7) | +0.1 (0.1) | +0.6 (0.3) | 4.6 / 1.3 / 1.7 / 6.9 |
| CT | miss | 31 | +0.9 (1.0) | −0.0 (−0.2) | −0.3 (−0.8) | −0.5 (−0.3) | 3.7 / 1.0 / 1.9 / 6.4 |
| ZR | hit | 10 | +2.6 (1.5) | −0.3 (−0.6) | +0.9 (1.1) | −1.8 (−0.8) | 4.1 / 0.8 / 1.5 / 5.1 |
| ZR | miss | 12 | −1.1 (−0.7) | −0.1 (−0.3) | −0.4 (−0.7) | +2.4 (2.1) | 4.1 / 0.9 / 1.5 / 3.6 |

The NHC trigger comes a median 2.7–3.4 days before closest approach. The 5-day cone touches the
region a further 1–2.6 days earlier. Over that window, no market moves in a consistent direction
before landfall:

* Hits show no systematic drift between trigger and landfall.
* Energy reacts on the trigger day itself, before an end-of-day entry is possible (RB +1.9%).
* For misses, energy gives back about 2.5% as the threat fades.

The one consistent signal is OJ after a hit (`figures/car_OJ.png`). It holds in both halves: design
+7.6% (n = 4, t 2.8), holdout +6.3% (n = 4, t 3.8).

Irma is the clearest case of pricing ahead of the 3-day trigger. OJ=F rose 9.8% in the ten days
before the trigger, while Irma was only inside the 5-day cone (`figures/overlap_irma2017_citrus.png`,
`event_irma2017_OJ.png`). That rise was in the expiring, illiquid September contract.

GEFS reaches 50% of members within 100 km a median **9–18 h after** the NHC trigger for hits. On
this test, the raw free ensemble does not give an earlier warning than the official cone.

### 2. Pre-registered rules (net of costs; `results/rule_results.csv`, grid in `rule_grid.csv`)

| market | cell | sample | n | gross % | net % | net 2× cost % | win | t | p (1-sided) | excess vs seasonal % | holdout success |
|---|---|---|---|---|---|---|---|---|---|---|---|
| OJ | selected (short, E1) | design | 15 | +0.95 | +0.45 | −0.05 | 53% | 0.71 | 0.25 | +1.11 | |
| OJ | selected (short, E1) | holdout | 9 | +0.24 | −0.26 | −0.76 | 22% | −0.17 | 0.56 | +0.21 | no |
| OJ | prior (long, E1) | design | 15 | −0.95 | −1.45 | −1.95 | 27% | −2.28 | 0.98 | −1.11 | |
| OJ | prior (long, E1) | holdout | 9 | −0.24 | −0.74 | −1.24 | 56% | −0.48 | 0.68 | −0.21 | no |
| NG | selected (long, D5) | design | 15 | +1.94 | +1.84 | +1.74 | 67% | 1.17 | 0.13 | +3.23 | |
| NG | selected (long, D5) | holdout | 14 | +1.59 | +1.49 | +1.39 | 57% | 0.51 | 0.31 | +2.19 | no |
| NG | prior (long, E1) | design | 15 | −0.68 | −0.78 | −0.88 | 47% | −0.62 | 0.73 | −0.67 | |
| NG | prior (long, E1) | holdout | 14 | +2.44 | +2.34 | +2.24 | 64% | 2.92 | 0.01 | +2.86 | yes* |
| CL | selected (short, E1) | design | 15 | +1.42 | +1.37 | +1.32 | 73% | 3.06 | 0.00 | +1.73 | |
| CL | selected (short, E1) | holdout | 14 | +0.43 | +0.38 | +0.33 | 57% | 0.50 | 0.31 | +0.57 | no |
| CL | prior (long, E1) | design | 15 | −1.42 | −1.47 | −1.52 | 27% | −3.29 | 1.00 | −1.73 | |
| CL | prior (long, E1) | holdout | 14 | −0.43 | −0.48 | −0.53 | 43% | −0.63 | 0.73 | −0.57 | no |
| RB | selected (long, D5) | design | 15 | +3.66 | +3.58 | +3.50 | 53% | 1.18 | 0.13 | +3.81 | |
| RB | selected (long, D5) | holdout | 14 | −1.59 | −1.67 | −1.75 | 36% | −1.47 | 0.92 | −1.56 | no |
| RB | prior (long, E1) | design | 15 | −0.99 | −1.07 | −1.15 | 20% | −1.41 | 0.91 | −1.29 | |
| RB | prior (long, E1) | holdout | 14 | −0.19 | −0.27 | −0.35 | 36% | −0.35 | 0.63 | −0.28 | no |
| CT | selected (short, E1) | design | 25 | +0.55 | +0.45 | +0.35 | 48% | 0.93 | 0.18 | +0.48 | |
| CT | selected (short, E1) | holdout | 20 | −0.45 | −0.55 | −0.65 | 55% | −1.18 | 0.87 | −0.61 | no |
| CT | prior (long, E1) | design | 25 | −0.55 | −0.65 | −0.75 | 52% | −1.34 | 0.90 | −0.48 | |
| CT | prior (long, E1) | holdout | 20 | +0.45 | +0.35 | +0.25 | 40% | 0.75 | 0.23 | +0.61 | no |

**0 of 5 design-selected rules pass the holdout.** The two that were strong in design both fail:
the CL short (t 3.1) and the RB long (+3.6%).

\* The NG economic-prior cell (long until arrival or all-clear) passes all three holdout criteria
(+2.3% net, p 0.01). It does not count as a finding, for two reasons:

1. It was negative in design (−0.8%), so the result is not stable.
2. Ten holdout tests at p < 0.10 should produce about one pass by chance alone.

For context, Gulf offshore output now matters far less to Henry Hub than LNG export terminals do,
and a storm can shut those terminals, which cuts demand. The sign of NG's reaction to a storm is
therefore unclear.

The "go long OJ when the 3-day cone first overlaps the citrus belt" rule loses money in both
samples. Costs make little difference, except in OJ (0.5% round trip, `rules.png`).

**Seasonal baseline** (`results/seasonal_baseline.csv`): the unconditional long from 15 Aug to
31 Oct earned OJ +6.2% in design (t 1.3) and +1.3% in holdout. NG: −4.7% / +5.9%. All t < 1.4.
Storm triggers add nothing over the calendar.

### 3. Overreaction (`results/overreaction.csv`)

Misses do not show a pre-registered run-up to revert. From trigger to all-clear, OJ moved −0.1%;
NG +1.7%, CL −1.4% and CT −0.7% (n = 11–31). Over the next 10 days, returns are near zero, and the
correlation between the two periods is not negative. The fade rule loses money in every market
(OJ −2.1% per trade, n = 6; CT −1.7%, n = 13). Two weak patterns exist in the event study but are
not significant: OJ misses −3.2% over 20 days (t −1.3), and the energy give-back for misses noted
above. The conclusion is **no exploitable overreaction**.

### 4. Exploratory, not pre-registered: drift after a hurricane reaches the citrus belt

`scripts/explore_postlandfall.py` tests a real-time version of the OJ post-landfall pattern. It goes
long OJ at the close after the first advisory that puts a ≥ 64 kt centre within 100 km of the
citrus counties, and holds for 20 trading days.

* All 8 events are positive: Katrina 05, Wilma 05, Matthew 16, Irma 17, Elsa 21, Ian 22, Nicole 22,
  Milton 24.
* Mean **+9.2% net** of a 0.5% round trip, median +10.0%, t 5.0.
* The placebo (same calendar dates in non-storm years) averages +0.4%. Resampling gives p = 0.009.
* Subtracting each year's trailing 120-day trend still leaves 7 of 8 positive.
* 5- and 10-day holds are weaker (+1.2% and +4.1% respectively).

USDA's own damage estimates arrive slowly, which is consistent with this drift. In hurricane
seasons, the final crop came in far below the October forecast: Wilma −17%, Irma −17%, Ian −44%,
Milton cut a further 20% by December. In other seasons the median gap was about −5%
(`data/usda_citrus_october.csv`). The same after-arrival test shows nothing for NG, CL, RB, CT or ZR.

**Status: hypothesis only.** With n = 8, found after seeing all years, in a thin market, this should
be logged as a forward test (proposed entry below), not traded.

## Caveats

* **Small samples.** The citrus belt has 8 hurricane hits in 21 years. Energy and cotton events
  overlap in time (2005, 2008 and 2020 clusters), so they are not independent.
* **Price data.** Yahoo `=F` series are unadjusted front-month prices. Roll days are removed by
  rule. The check works for energy: absolute return on roll days is 5.0% vs 2.5% on other days for
  NG. It is weaker for OJ (2.0 vs 1.7) and fails for rice. OJ=F carries the expiring, illiquid
  contract for about two weeks before each roll (Irma's run-up was in the September contract), so a
  real trader holding the next contract would have seen different numbers.
* **OJ is thin.** A 0.5% round trip is optimistic in 2023–24, when spreads of 1–3 ¢ on 400–500 ¢
  were common and limit moves occurred.
* **Settlement timing.** Day 0 needs the advisory by 17:00 UTC. Energy settles at 14:30 ET
  (18:30 UTC), but OJ and cotton settle earlier, so the cutoff is tight for the 11 am EDT
  advisory (15 UTC).
* **Rebuilt cones** match the published cones closely (IoU ≈ 0.97) but not exactly. Pre-2008 cones
  cannot be checked, because no GIS archive exists for them.
* **Regions are coarse.** The cotton region is five whole states, the energy region ignores
  pipeline and LNG detail, and the citrus county list is fixed at its 2020s footprint even though the
  belt has shrunk over time.
* **Intraday reaction is invisible.** With daily closes, a reaction within hours of an advisory can
  only be seen on day 0, not traded at that day's close.

## How this plugs into the crop tracks

The same pipeline carries over to slower hazards:

1. Take a public forecast archived with its issue time.
2. Turn it into a "threat to region" series.
3. Mark the day it first crosses a threshold.
4. Test prices over pre-registered windows, design vs holdout.

Two examples:

* **NOAA CPC 1–3 month outlooks** are tercile probability maps archived as GIS since the 1990s.
  Applied to US wheat and corn, or to the soy states in `soy_research/`, the threat would be the
  share of a crop area under "below-normal precipitation ≥ 40%".
* **ENSO** probability forecasts (CPC/IRI, monthly since 2002) can be tested against cocoa (West
  Africa dry season), Australian wheat and palm oil.

Results here suggest where to look. Markets absorb a widely watched forecast immediately. The
leftover edge is in **how slowly confirmed damage is quantified**, as with the OJ drift and the
USDA revisions. The useful crop-track work is therefore pairing a forecast trigger with fast damage
measurement after the event. Examples: Sentinel-1/2 grove or field damage mapping right after
landfall, or the satellite yield signal in `soy_research/satellite/`, aimed at the regions the
forecast flagged.

## Proposed forward test (not yet added to `forward_tests/REGISTRY.md`)

**OJ post-landfall drift.** Go long OJ at the close of the first trading day after an NHC advisory
puts a ≥ 64 kt centre within 100 km of the 22 citrus counties. Exit after 20 trading days, with a
0.75% round trip. Score each event against the same-date placebo. Judge after 4 new events.
Success means mean net > 0 and at least 3 of 4 events beating placebo.

## Reproduce

```bash
S=<scratch>
python scripts/fetch_forecasts.py --scratch $S                       # a-decks, HURDAT2, b-decks (~50 MB, scratch)
python scripts/build_regions.py  --geo $S/geo --out data/regions.geojson   # needs Census cb_2022 zips in $S/geo
python scripts/fetch_prices.py   --out data/prices
python scripts/compute_overlap.py --scratch $S --regions data/regions.geojson --out data
python scripts/parse_usda_citrus.py --pdfdir $S/usda --out data/usda_citrus_october.csv
python scripts/analyze_events.py --data data --out results
python scripts/explore_postlandfall.py --data data --out results
python scripts/build_event_table.py --scratch $S --data data --results results
python scripts/plot_cone_maps.py --scratch $S --data data --out figures --events AL112017:citrus AL092022:citrus AL142024:citrus AL092021:gulf_energy AL132020:gulf_energy AL122005:gulf_energy
python scripts/plot_results.py --data data --results results --out figures --events Irma:2017:OJ Ian:2022:OJ Milton:2024:OJ Katrina:2005:NG Ida:2021:NG Laura:2020:CL Harvey:2017:RB
```

Files:

* `data/`: event_table.csv, forecast_overlap.csv, advisories.csv.gz, besttrack_verification.csv,
  cone_radii_nm.csv, cone_validation.csv, regions.geojson, usda_citrus_october.csv,
  damage_reports.csv, prices/.
* `results/`: events.csv (per market × storm: dates, windows, returns), car_summary.csv,
  car_paths.csv, rule_grid.csv, rule_results.csv, seasonal_baseline.csv, overreaction.csv,
  explore_postlandfall*.csv, roll_check.csv.
* `figures/`: cone maps, CAR paths, event price paths, threat series, rules.

## Deviations from the pre-registration

1. Events without a complete +20-day window (Isaias, Oct 2026) are excluded from returns. The
   pre-registration did not cover this case.
2. The seasonal baseline excludes years with a trigger within ±14 calendar days (≈ ±10 trading
   days). The season-long rule drops 2026, which is incomplete.
3. Trading-rule overlap: a new trigger is skipped if it arrives before max(E1 exit, day 0 + 10) of
   the previous trade in that market. The same skip set is used for every cell, so cells stay
   comparable.
4. The rice roll-day rule does not isolate rolls (see caveats). Rice is exploratory only.

---

# Appendix: pre-registration (verbatim copy of PREREGISTRATION.md)


Written 2026-10-11 02:30 UTC, after the forecast and price data were downloaded and **before any
event-window return was computed**. This text is copied unchanged into README.md. If anything
changes after this point, it is listed under "Deviations" in the README.

Disclosure: while checking how Yahoo rolls OJ=F between contracts, I printed raw OJ=F closes for
28 Aug–22 Sep 2017, 1 Sep–14 Oct 2022 and 20 Aug–20 Sep 2005. Those windows include Irma, Ian and
Katrina/Rita, so I saw that OJ=F rose about 11% from 1 to 8 Sep 2017 (in the expiring September
contract). No other event windows were looked at.

## Markets and regions

| market (Yahoo) | region (data/regions.geojson) | role |
|---|---|---|
| OJ=F orange juice | `citrus`: 22 Florida citrus counties | primary |
| NG=F natural gas, CL=F WTI crude, RB=F RBOB gasoline | `gulf_energy`: offshore Gulf OCS area plus 50 km discs around 8 refining/LNG hubs | primary |
| CT=F cotton | `cotton`: GA, AL, SC, NC, MS plus Texas coastal cotton counties | primary |
| ZR=F rough rice | `rice`: SW Louisiana and Texas coastal rice counties | exploratory: event study only, no rule |

## Event (trigger) definition, all point-in-time

* Forecasts: the NHC official track (ATCF `OFCL`) of every Atlantic storm, 2005–2026. Each one gets an
  NHC-style cone whose radii are the 67th percentile of the previous five seasons' official errors.
* **Trigger advisory** for storm *s* and region *R*: the first advisory whose **3-day cone intersects
  R** and whose **maximum forecast intensity over 0–72 h is at least 64 kt** (a forecast hurricane).
  Each storm–region pair triggers at most once.
* Available at advisory synoptic time + 3 h. **Day 0** is the first trading day *d* with
  availability ≤ *d* 17:00 UTC (13:00 EDT). Entry is at the day-0 close.
* **Point-in-time exit E1**: the first later advisory where either (a) the advisory position is within
  100 km of R ("arrival"), or (b) the 5-day cone no longer intersects R ("all-clear"), or (c) the
  storm's advisories end. Exit at the close of the first trading day on or after that availability,
  using the same 17:00 UTC cutoff, and no later than day 0 + 15 trading days.
* **Miss** (point-in-time): no advisory during the episode has its position within 100 km of R at
  ≥ 64 kt. **Hit** otherwise. HURDAT2 best-track hit/miss labels are reported only for comparison.
* If a market already has an open position from an earlier trigger, a new trigger is skipped for
  the trading rule. The event study keeps every event and flags overlaps.

## Samples

* **Design:** triggers in 2005–2017. **Holdout:** triggers in 2018–2026, used once, after freezing.

## Trading rule family and selection (per primary market)

* Grid: direction ∈ {long, short} × exit ∈ {E1, day 0 + 5 trading days, day 0 + 10 trading days}.
* Pick the single cell with the highest mean net return on design events. Freeze it. Score it on
  the holdout.
* Always report the economic-prior cell (**long, E1**) as well, whatever the selection picks.
* Round-trip costs (commission + half-spread × 2 + slippage), as a % of price: OJ 0.50, CT 0.10,
  NG 0.10, CL 0.05, RB 0.08 (ZR 0.30 is reported only). Sensitivity: 2× costs.
* **Holdout success** requires all three: mean net return > 0; one-sided t-test p < 0.10 across
  holdout events; and mean excess over the seasonal baseline > 0.

## Seasonal (naive) baseline

* For every trade: the same calendar entry day and the same number of trading days held, in every
  other year 2005–2025 with no trigger for that market within ±10 trading days. The baseline is the
  average of those trades, and the event excess is event return − baseline.
* Also an unconditional season-long rule: long from 15 Aug to 31 Oct every year.

## Event study (descriptive)

* Daily log returns, with roll days removed (below). Abnormal return = return − that market's mean
  daily return in the same calendar month, 2005–2026.
* CAR windows: pre-trigger [−10, −1]; trigger to landfall [0, L]; post-landfall [L+1, L+20]; and
  [0, +20]. Here L is the trading day of the best-track closest approach (hindsight, used only to
  split the timeline).
* Expected if markets price forecasts efficiently: most of the move by L, and no drift after L.

## Overreaction test

* On **misses**: r(day 0 → all-clear day A) and r(A → A + 10 trading days).
* Hypothesis: A→A+10 averages negative (reversion) and is negatively correlated with 0→A.
* **Fade rule:** on misses where r(0→A) > 0, short at the A close for 10 trading days, net of costs.
  Scored on design and holdout separately.

## Roll handling (Yahoo continuous series are unadjusted)

* OJ, CT, ZR, SB: a roll day is the first day volume recovers to ≥ 25% of its 40-day median after at
  least two days below 10%. Its return (which contains the calendar spread) is dropped.
* NG, CL, RB: the roll day is the first trading day after the approximate exchange last-trade date
  (NG: 3 business days before the delivery month; CL: 3 business days before the 25th of the prior
  month; RB: last business day of the prior month). Its return is dropped.
