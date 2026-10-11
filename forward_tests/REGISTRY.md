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

## FT-3: US corn and soybean yield signal (to be registered)

Registered by the US satellite track before its holdout is opened. The spec, holdout years and
pass criteria go in `soy_research/us/satellite/README.md`, with a copy here. Live check: the
Aug/Sep 2026 forecasts against USDA's 2026 reports and the January 2027 final.
