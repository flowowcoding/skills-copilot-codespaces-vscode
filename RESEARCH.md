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
| `commodity_research/` | Weak-benchmark markets (cocoa, Black Sea wheat, India), field-level crops, copper smelters, hurricanes |
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
| US corn/soy, benchmark | Do USDA surprises move CBOT? | **Yes**: surprise vs analyst consensus moves new-crop prices (Aug corn −0.90% per 1% surprise, t −2.7; soy −0.64%, t −2.9). Revisions vs prior USDA don't. Public crop-condition data barely predicts the surprise. |
| US corn/soy, satellite (Aqua EVI + gridMET) | Does satellite − consensus predict the USDA surprise? | **No**: the pre-registered 2022–25 holdout failed. Worse than USDA in September, soy worse than trend, trading hit rate 44% vs a 56% base rate (−3.3 ¢/bu net). 2024 corn was the one clean hit. |
| West African cocoa | Does weather/satellite beat weak ICCO data and port arrivals? | **No**: arrivals, ICCO revisions and returns not predicted on 2022/23–2025/26; the trading rule lost 4.3% a month. 2023's disease shock had no precedent in the history. |
| Black Sea wheat | Does satellite beat USDA's weak Russia numbers? | **No**: worse than trend on 2021–25. USDA follows IKAR/SovEcon, and the satellite adds nothing beyond them. |
| India pulses and monsoon | Does satellite beat India's advance estimates? | **No**: 2–3× worse than the first official estimate. Area swings dominate, and there's no crop map. |
| Field-level crops (Landsat 30 m, IA+IL) | Does field-level resolution close the gap to USDA? | **Corn yes, soy no**: state corn 2.1% vs USDA 2.3% (mostly from county weather); soy runs high; US-level worse than consensus. |
| Copper smelters (S2 SWIR, S3 night fire) | Do processing signals track metal supply? | **On/off yes, output no**: 9/15 and 5/6 shutdowns caught (Altonorte 10 days before the press); output and the China index fail; no price signal. |
| Hurricanes vs futures | Do free storm forecasts get ahead of prices? | **No**: markets react on the threat day; all 5 pre-registered rules fail on 2018–26. OJ after landfall (8/8, found after looking) is now a forward test. |

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

- **Forward tests** (`forward_tests/REGISTRY.md`): FT-1 Greenbushes (late Oct 2026), FT-2 Brazil
  soy v2 (from 2026/27), FT-3 US corn/soy 2026 and FT-5 field-level IA+IL (both against USDA's
  January 2027 final), FT-4 OJ after hurricane landfall (from the 2027 season).
- **Honest status:** no free-satellite signal tested so far beats the official forecasts or the
  analyst consensus out of sample. The public crop and mine data are hard to beat with free
  250 m–10 m imagery and simple models.
- **What's left after 16 tracks:**
  1. **Operating-status alerts, not supply forecasts.** Free imagery reliably flags shutdowns and
     restarts at specific plants, sometimes before the press (Altonorte). That's useful for risk
     monitoring or for non-listed assets, but not as a supply forecast.
  2. **Field-level corn.** The 30 m model edged USDA's state corn forecasts. It needs forward
     years (FT-5) before anyone should trust it, and then a national version.
  3. **Physically large, slow-to-report shocks** (citrus after hurricanes). Watch FT-4.