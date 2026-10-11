# Forward-test registry

Every signal here was chosen after looking at data, so its historical numbers are optimistic. They
are frozen now, and get scored only on data that didn't exist when they were frozen. Nothing in
this file may be edited after registration except the **Outcome** fields.

Frozen at commit `b4f0a0a` (2026-10-11). Code fingerprints (sha256, first 16 hex characters):
`soy_research/satellite/model.py` c26001312fe0c231 · `soy_research/satellite/build_features.py` ceb08de5f6fa93a5 ·
`satellite_poc/lithium/greenbushes_eval.py` 761132f79c3e5a8c.

---

## FT-1: Greenbushes "pit minus plant" activity index (registered 2026-10-10)

- **Signal:** pit-zone minus plant-zone optical activity index, from `satellite_poc/lithium/`.
  Fitted on 20 quarters (in-sample r = 0.68).
- **Prediction:** IGO's report for the September 2026 quarter (IGO's 1Q FY27, due late Oct 2026)
  shows Greenbushes **total material mined of 2.4 Mbcm, with an interval of 1.4–3.4 Mbcm**, down
  from 3.44 Mbcm in the June 2026 quarter. This rests on only 3 clear image pairs.
- **Pass:** the reported figure is within 1.4–3.4 Mbcm **and** below the June quarter.
  **Fail:** anything else.
- **Outcome:** _pending_

## FT-2: Brazil soybean yield signal v2 (= v1b, no land-surface temperature)

- **Spec:** the v1 pipeline in `soy_research/satellite/` run with
  `--feats evi_cum,ndvi_recent,precip_cum` (v1 without `lst_cum`). Trained walk-forward on all
  seasons up to 2025/26, with no further changes.
- **Season scored:** 2026/27, then every later season with the spec unchanged.
- **Forecast dates:** 1 Jan, 1 Feb, 1 Mar, 1 Apr 2027. Data cutoffs and product delays are
  handled as in v1.
- **Truth:** IBGE PAM final yield. Use the provisional figure if the final isn't out, and mark
  the result provisional.
- **Scores:**
  1. Brazil absolute % yield error on 1 Feb and 1 Mar, against (a) the trend line and (b) the
     Conab estimate public on the same date.
  2. State level: the gap test in `soy_research/satellite/results/revision_test.csv`
     (next revision ~ previous revision + gap), with the 2026/27 releases added.
- **Pass criterion:** judged only once 3 forward seasons exist (2026/27–2028/29). The mean of
  score 1 must be below trend **and** within 1 percentage point of Conab, and the state-level gap
  coefficient must be positive with t > 2 on forward seasons alone. A single season is reported
  but not judged.
- **Outcome 2026/27:** _pending_

## FT-3: US corn and soybean yield signal v1, 2026 crop (registered 2026-10-11)

- **Spec:** `soy_research/us/satellite/` v1: Aqua MYD13Q1 EVI, prior-years CDL mask, gridMET,
  Theil–Sen trend, no land-surface temperature. Signal file `signal/us_sat_signal_v1.csv`.
  The pre-registered 2022–25 holdout **failed**, so this entry only records a live check. It is
  not a second chance for the same spec.
- **Disclosed problems:**
  - Before the spec was frozen, the holdout numbers of an earlier version were seen by accident.
  - The 0.02-EVI drift guard was set after the 2026 residual was visible (no yields were used).
    The no-guard variant is recorded too.
- **Forecasts made before USDA's January 2027 final (US, bu/acre):**

| crop | satellite, Aug | satellite, Sep | no-guard, Sep | USDA Aug | USDA Sep |
|---|---|---|---|---|---|
| corn | 187.1 | 185.7 | 192.2 | 180.7 | 178.5 |
| soy | 55.6 | 55.1 | – | 52.7 | 52.8 |

- **Score:** is USDA's January 2027 final closer to the satellite's September forecast than to
  USDA's September forecast, for each crop? USDA's October report (181.2 corn, 53.1 soy) moved
  toward the satellite, but October is not the truth.
- **Outcome:** _pending (USDA January 2027 Crop Production Annual Summary)_

## FT-4: Orange-juice drift after a hurricane hits the Florida citrus belt (registered 2026-10-11)

- **Found after looking at the data** in `commodity_research/weather_events/`: 8 of 8 past events
  positive, +9.2% net over 20 days, p 0.009 against the same dates in other years. All five
  pre-registered hurricane rules failed; this one was not among them.
- **Rule:** go long OJ (ICE, front month) at the close of the first trading day after an NHC
  advisory puts a hurricane-strength centre (≥ 64 kt) within 100 km of the 22 citrus counties
  defined in `data/regions.geojson`. Exit after 20 trading days. Cost: 0.75% round trip.
  Code: `scripts/explore_postlandfall.py` (sha256 55d4af1ffef67f92).
- **Score:** each event's net return against the same-date return in other years.
- **Pass:** after 4 new events (from the 2027 season on; Isaias 2026 excluded), mean net return > 0
  **and** at least 3 of 4 events beat the comparison. **Fail:** anything else.
- **Outcome:** _pending (0 of 4 events)_

## FT-5: Field-level corn and soy model, Iowa + Illinois (registered 2026-10-11)

- **Spec:** `commodity_research/field_level_crops/` v1: Landsat 30 m field interiors, in-season
  crop classifier, county gridMET, ridge model (`scripts/model.py`, sha256 e2bd61bf608a6b2b). Pre-registered
  2022–25 holdout: corn passed at state level (2.1% vs USDA 2.3%), soy failed (4.6% vs 2.3%).
- **Also tracked:** the `--no-intercept` soy variant, chosen after seeing the holdout bias. It is
  tracked separately and is not the main spec.
- **Frozen 2026 forecasts (IA+IL, September):**

| crop | field model | USDA Sep (weighted) |
|---|---|---|
| corn | 219.8 ± 8.9 bu/ac | 214.5 |
| soy | 68.7 ± 3.0 bu/ac | 65.0 |

- **Score:** each year from 2026, state-level |error| against USDA's January final, compared
  with USDA's September forecast and with trend.
- **Pass:** judged after 3 forward years (2026–2028). The corn model must beat USDA's September
  state forecasts on average, and the soy no-intercept variant must beat trend.
- **Outcome 2026:** _pending (USDA January 2027 final)_
