# Cushing tank signal backtest

Follow-up to *"Using Satellite Photos to Trade Stocks"* (LosingLoonies). The video's
"perfect knowledge" test traded tank landlords (PAA, EPD, ET, ENB, ...) on the weekly
change in Cushing crude stocks. This asks the question it skipped: **does it work just as
well with the EIA number after it's published?** If so, you don't need a satellite.

## Schedules

The rule is the same each time: own the ticker the week after a Cushing build. After a draw,
go flat (or short with `--long-short`). Only the timing of the information changes:

| schedule | when you know the weekly change | trades at |
|---|---|---|
| `oracle` | while it is happening (look-ahead) | previous Friday close |
| `satellite` | Friday the week ends (perfect satellite) | Friday close, about 5 days before EIA |
| `public` | EIA release (Wed 10:30 ET, Thu in holiday weeks) | release-day close |

Prices are dividend-adjusted, which matters for MLPs that pay out most of their return as
distributions. Cost is 5 bps per side by default. `beats_random` is the share of 2,000
coin-flip strategies, on the same dates and with the same costs, that the strategy beats.
USO is the crude control.

## Results (2015-01 to 2026-10, long/flat, 5 bps)

| ticker | buy&hold | oracle | satellite | public | public beats random |
|---|---|---|---|---|---|
| PAA | +16% | -46% | +13% | +211% | 92% |
| EPD | +124% | -26% | +9% | +205% | 97% |
| ET  | +83% | -63% | +55% | +169% | 85% |
| ENB | +72% | -43% | +32% | +187% | 99% |
| USO | -9% | -90% | -46% | +84% | 88% |

What this shows:

1. **The head start is worth nothing, or less.** Satellite never beats public. Oracle,
   which knows the change while it happens, loses money on every ticker. Builds come in the
   same weeks that oil and midstream stocks fall, so the "landlord" logic runs the wrong way
   on contemporaneous data.
2. **Public data looks better, but mostly because of 2020.** Long-after-builds sat out much
   of the 2020 crash (PAA 2020: -6% vs -51% buy&hold). Without 2020, public Sharpe is
   0.42-0.69 vs 0.40-0.56 for buy&hold. In 2015-2019 it was roughly zero. Over the full
   period it is exposed only half the time and still has drawdowns of 32-82%. In practice
   it is a mean-reversion/regime effect: buying the week after a build means buying after a
   selloff.
3. **The tickers are not independent tests.** Strategy returns correlate 0.5-0.8 across the
   landlords, so "5 of 5 beat random" is closer to one result.

So for retail: building a satellite pipeline for Cushing doesn't pay, because the free EIA
number does at least as well. The public-data effect is real enough to look at, but it
depends on a single regime, so it shouldn't be traded without out-of-sample checks.

## Run

```bash
pip install -r requirements.txt
python backtest.py                  # table, default settings
python backtest.py --long-short --cost-bps 10
marimo edit notebook.py             # interactive: ticker, cost, long/short
```

Data is cached in `data/`. Delete the CSVs to re-download from EIA (series
`W_EPC0_SAX_YCUOK_MBBL`) and Yahoo Finance.
