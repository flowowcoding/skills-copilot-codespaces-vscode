# Pre-registration: hurricane forecast threats and commodity futures

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
