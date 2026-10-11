# Satellite-driven commodity supply research

**Question:** can free satellite data estimate changes in physical supply before the market has
priced them in? Imagery is one source of evidence. Official forecasts, company disclosures and
prices decide whether that evidence matters financially.

Every test below was fixed before looking at the outcome, used point-in-time data, and was scored
on data held back from tuning. Negative results are reported as they came out.

## Map of the repo

| folder | what it is |
|---|---|
| `cushing_backtest/` | Started here: Cushing oil-tank fill vs. "tank landlord" stocks (from the LosingLoonies video) |
| `satellite_poc/` | Mining track: activity indices, halts, production tests, sub-metre radar, pit walls, mine inventory, event study, Chile copper, lithium |
| `soy_research/benchmark/` | Point-in-time Conab / WASDE / IBGE vintages for Brazilian soy, CBOT prices, revision behaviour |
| `soy_research/satellite/` | MODIS + CHIRPS state-level soybean yield signal, versioned and timestamped |
| `forward_tests/` | Frozen post-hoc signals, scored only on data that arrives after registration |

## Results so far

| track | question | result |
|---|---|---|
| Cushing tanks | Does perfect knowledge of the weekly Cushing change make money? | The satellite timing never beats trading after the EIA release. The "public" edge is mostly 2020. |
| Mine halts (Cobre Panamá, Eagle, Çöpler, Karlawinda) | Can free radar/optical see a mine stop? | **Yes**, clearly, in the pit zones (12/12 months lower after the halt at Cobre and Çöpler). |
| Karlawinda, Greenbushes | Does the activity index track reported quarterly tonnes? | **No**. The tuned correlation collapsed on held-back quarters. |
| Chile copper (17 mines, ~80% of output) | Does summed pit activity track national output? | **No** (Spearman −0.70 in development). Copper output follows grade and throughput, not earthmoving. |
| Bingham, Umbra 33 cm radar | Did pit equipment drop after Rio's 2024 geotechnical disclosure? | **No**, once corrected for viewing angle. The raw −43% was an artefact. |
| Pit walls (Bingham, Çöpler, Eagle) | Does free InSAR/radar warn before geotechnical disclosures? | **No**: 0/20 pre-set tests fired, and free InSAR arrives 4–14 months late. |
| Thacker Pass | Does construction seen from space lead company disclosures? | It tracks construction well, but leads only already-scheduled milestones, and there's no stock signal. |
| Event study (68 disruptions) | What is an early warning worth? | About 12% per event for single-mine companies, but disclosure comes within 0–1 days. |
| Brazil soy, benchmark | Do official Brazil revisions move CBOT? | Barely (about −0.1% per Mt, not significant). Revisions are persistent (USDA next ≈ 0.5 × previous). |
| Brazil soy, satellite | Does a satellite yield estimate beat the official ones? | Brazil level: **failed** on held-back seasons (Terra overpass drift). State level: satellite-minus-official predicts the next official revision beyond persistence, with 1–6 week leads in southern droughts. |

## What we've learned

1. **Free imagery reliably answers "is it happening?" but not "how much?"** That holds for mine
   halts, construction and equipment, at 10 m and even at 33 cm.
2. **For metals, earthmoving is the wrong supply measure.** Output depends on ore grade and plant
   throughput, which imagery doesn't see.
3. **Company-level events can't be front-run with free data.** Disclosure is too fast and the
   archives are too slow.
4. **Crops are the better fit**, because what imagery sees (plant vigour) is close to output. The
   one surviving signal is the state-level soy revision lead. But Brazil revisions barely move
   CBOT, so predicting them may not pay.

## Open next steps

- **Forward test:** score the soy no-LST variant (chosen after the fact) on the 2026/27 season,
  rules frozen now. Also score the Greenbushes forward test against IGO's Jul–Sep 2026 report.
- **Go where reports move prices:** USDA's US crop reports move CBOT far more than Brazil's.
  Repeat the soy benchmark + satellite design for the US corn and soy yields in USDA's August
  and September reports, then test whether satellite-minus-USDA predicts the report-day return.
- **Metals via processing, not pits:** smelter thermal signatures, concentrate stockpiles and
  port shipping, as SAVANT-type services do. The edge has to be measured against those services.
