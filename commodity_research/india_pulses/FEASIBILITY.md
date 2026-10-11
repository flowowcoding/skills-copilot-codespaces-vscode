# India pulses / monsoon crops: which prices can we test against?

Survey done 2026-10-11 from this sandbox (egress through the agent proxy). "Reachable" means a
script here could download it with no login. That's the bar a reproducible backtest needs.

## What exists and what we could reach

| Candidate target | Free daily history? | Reachable here? | Verdict |
|---|---|---|---|
| **NCDEX chana (chickpea) futures** | Yes on ncdex.com (2004 to the SEBI suspension, Dec 2021; relaunch not traded with depth) | **No**: `ncdex.com/markets/historical-data` sits behind a JavaScript fingerprint bot-check | Not usable. The only real pulse futures market is also suspended for the last 4+ seasons |
| NCDEX tur/urad/moong futures | Delisted in 2007 | n/a | Not tradeable |
| **Agmarknet daily mandi prices** (min/max/modal by APMC) | Yes (agmarknet.gov.in, data.gov.in API) | **No**: agmarknet.gov.in returns HTTP 403, data.gov.in and api.agmarknet.gov.in drop the connection, eNAM trade-data pages render no data without a browser | Would have been the best pulse "market". Not reachable |
| DoCA Price Monitoring Cell daily wholesale/retail (gram dal, tur dal, masoor dal, sugar; ~550 centres) | Yes (fcainfoweb.nic.in) | Page loads but every report sits behind a **captcha** | Not used (we don't automate captchas) |
| UPAg (Unified Portal for Agricultural Statistics) API | Prices + estimates | Swagger at `data.upag.gov.in/docs` is public, but every data endpoint needs an OAuth login | Not used |
| **WPI item indices: Gram, Arhar (tur), Masur, Sugar** (Office of the Economic Adviser) | Monthly, Jan 2005 to Apr 2026 (two bases spliced) | **Yes**: eaindustry.nic.in xls | **Used** as the pulse "market". Wholesale, national, published around the 14th of the next month |
| WFP/HDX retail prices from DoCA (chickpea to 2020, masur, "lentils", moong, urad; ~50 centres) | Monthly | Yes (HDX CSV) | Kept as a cross-check only. Commodity mapping is inconsistent (the Delhi "Lentils" and "Chickpeas" series are identical in 2014–19) |
| **ICE raw sugar No.11 (SB=F)** | Daily since 2000 | Yes (Yahoo chart API) | **Used**: tradeable, liquid, India is the #2 producer and swings world exports through export quotas |
| ICE cotton No.2 (CT=F) | Daily | Yes | Feasible, but not chosen (see below) |
| MCX cotton (candy) | Daily | No (mcxindia.com 403) | Not used |
| CBOT soymeal (ZM=F), soybeans (ZS=F) | Daily | Yes | Not chosen: Indian soymeal is a small share of world trade, and CBOT is driven by the US and Brazil |
| Canadian lentils / dry peas (Saskatchewan farm price, StatCan 32-10-0077) | Monthly, 1987+ | Yes | Context only. Monthly farm-gate prices aren't tradeable, and India's import demand is policy-driven (duties, MSP) |
| Australian chickpeas | No free series found | n/a | n/a |

## Targets chosen

1. **Chickpea (chana / gram), with the WPI Gram index as the price.** It's the largest Indian pulse
   (about half of output), and India grows about 70% of the world's chickpeas. It's a rabi crop grown on
   stored soil moisture, so EVI, soil moisture and February–March heat all bear directly on yield. And the
   official estimates are known to be weak: the 2nd AE is the first gram number, it comes out while the
   crop is still in the field, and trade estimates often differ from it by 10–20%. The price isn't
   tradeable, because NCDEX chana has been suspended since Dec 2021 and holding physical stock costs about
   1%/month plus mandi fees. So the price test is a "would a long-only stockist have gained" test, with
   costs.
2. **Sugar, with ICE raw sugar SB=F as the price.** This is the one liquid, tradeable market where the
   Indian monsoon shows up. Cane in Maharashtra and Karnataka depends on the monsoon. The catch is that
   ISMA's own estimates have used satellite cane-area surveys since about 2018, so the benchmark here
   is *not* weak.

Pigeon pea (tur, with WPI Arhar as the price) goes through the same pipeline as a secondary pulse
target. It's kharif and monsoon-driven, and it was the centre of the 2015–16 price spike. It costs
almost nothing extra, because the advance-estimate releases and the satellite extraction are shared.

Cotton was not chosen. India is the largest producer, but CT=F follows US weather, China, and
fund flows. The USDA already publishes monthly WASDE numbers for India cotton, so the benchmark
there is comparatively strong.
