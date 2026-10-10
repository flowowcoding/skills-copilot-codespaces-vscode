"""Does knowing the weekly Cushing inventory change make money, and does it matter *when* you know it?

Rule from the video: when Cushing tanks fill, buy the tank "landlords"; when they drain, sell.
We run that rule on three information schedules so the value of the head start is isolated:

  oracle     - you know the week's change while it is happening (hold the same Fri->Fri week).
               This is pure look-ahead and is only an upper bound.
  satellite  - you know the change at the Friday the week ends (a perfect satellite), and hold
               until the next Friday. Includes the following Wednesday's EIA release.
  public     - you trade at the close on EIA release day (normally Wednesday 10:30 ET), using
               the number everyone already has. Needs no satellite at all.

Returns use dividend-adjusted closes and a per-side cost on every position change.
Every strategy is also compared with coin-flip strategies on the same schedule.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

import numpy as np
import pandas as pd

from data import cushing_stocks, prices

LANDLORDS = ["PAA", "EPD", "ET", "ENB"]
CONTROL = ["USO"]
SCHEDULES = ["oracle", "satellite", "public"]
TRADING_DAYS = 252


@dataclass
class Config:
    start: str = "2015-01-01"
    cost_bps: float = 5.0      # per side, applied to |change in position|
    long_short: bool = False   # False: long when filling, flat when draining
    n_random: int = 2000
    seed: int = 0


def release_dates(week_ending: pd.DatetimeIndex, trading_days: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """EIA publishes on the Wednesday after the week ends, or Thursday when Mon-Wed holds a holiday."""
    tset = set(trading_days)
    out = []
    for fri in week_ending:
        mon, wed = fri + pd.Timedelta(days=3), fri + pd.Timedelta(days=5)
        holiday = any(d not in tset for d in pd.bdate_range(mon, wed))
        out.append(wed + pd.Timedelta(days=1 if holiday else 0))
    return pd.DatetimeIndex(out)


def entry_signals(stocks: pd.Series, trading_days: pd.DatetimeIndex, schedule: str,
                  long_short: bool) -> pd.Series:
    """Signal (+1 / 0 or -1) indexed by the trading day whose close it is entered at."""
    change = stocks.diff().dropna()
    sig = pd.Series(np.where(change > 0, 1.0, -1.0 if long_short else 0.0), index=change.index)
    if schedule == "oracle":
        when, side = sig.index - pd.Timedelta(days=7), "left"     # previous Friday close
    elif schedule == "satellite":
        when, side = sig.index, "left"                            # this Friday close
    elif schedule == "public":
        when, side = release_dates(sig.index, trading_days), "right"  # release-day close
    else:
        raise ValueError(schedule)
    # Snap to a trading day: on-or-before for Friday entries, on-or-after for release days.
    pos = trading_days.searchsorted(when, side="right") - 1 if side == "left" else trading_days.searchsorted(when)
    ok = (pos >= 0) & (pos < len(trading_days))
    out = pd.Series(sig.values[ok], index=trading_days[pos[ok]])
    return out[~out.index.duplicated(keep="last")]


def positions(entries: pd.Series, trading_days: pd.DatetimeIndex) -> pd.Series:
    """Position held over each day's close-to-close return (entered at a prior close)."""
    held = entries.reindex(trading_days).ffill()
    return held.shift(1).fillna(0.0)


def strategy_returns(pos: pd.Series | np.ndarray, asset_ret: pd.Series, cost_bps: float) -> np.ndarray:
    p = np.asarray(pos, dtype=float)
    turnover = np.abs(np.diff(p, axis=0, prepend=0.0 if p.ndim == 1 else np.zeros((1, p.shape[1]))))
    r = asset_ret.to_numpy()
    if p.ndim == 2:
        r = r[:, None]
    return p * r - turnover * cost_bps / 1e4


def stats(daily: np.ndarray) -> dict:
    eq = np.cumprod(1 + daily)
    years = len(daily) / TRADING_DAYS
    vol = daily.std() * np.sqrt(TRADING_DAYS)
    return {
        "total_ret": eq[-1] - 1,
        "cagr": eq[-1] ** (1 / years) - 1,
        "sharpe": daily.mean() * TRADING_DAYS / vol if vol > 0 else np.nan,
        "max_dd": (eq / np.maximum.accumulate(eq) - 1).min(),
    }


def random_percentile(entries: pd.Series, trading_days, asset_ret, cfg: Config, rng) -> float:
    """Share of coin-flip strategies (same entry dates, same cost) whose total return we beat."""
    lo = -1.0 if cfg.long_short else 0.0
    flips = rng.choice([lo, 1.0], size=(len(entries), cfg.n_random))
    rand_entries = pd.DataFrame(flips, index=entries.index)
    rand_pos = rand_entries.reindex(trading_days).ffill().shift(1).fillna(0.0)
    rand_daily = strategy_returns(rand_pos.to_numpy(), asset_ret, cfg.cost_bps)
    rand_total = np.prod(1 + rand_daily, axis=0) - 1
    ours = np.prod(1 + strategy_returns(positions(entries, trading_days), asset_ret, cfg.cost_bps)) - 1
    return float((rand_total < ours).mean())


def run(cfg: Config, tickers: list[str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    tickers = tickers or LANDLORDS + CONTROL
    stocks = cushing_stocks()
    px = prices(tickers)
    px = px[px.index >= pd.Timestamp(cfg.start) - pd.Timedelta(days=10)].dropna(how="all")
    rets = px.pct_change()
    rets = rets[rets.index >= cfg.start].fillna(0.0)
    days = rets.index
    rng = np.random.default_rng(cfg.seed)

    rows, daily_by = [], {}
    for t in tickers:
        bh = stats(rets[t].to_numpy())
        rows.append({"ticker": t, "schedule": "buy&hold", **bh, "trades": 1, "beats_random": np.nan})
        for sched in SCHEDULES:
            ent = entry_signals(stocks, days, sched, cfg.long_short)
            ent = ent[(ent.index >= days[0]) & (ent.index <= days[-1])]
            pos = positions(ent, days)
            daily = strategy_returns(pos, rets[t], cfg.cost_bps)
            daily_by[(t, sched)] = daily
            rows.append({
                "ticker": t, "schedule": sched, **stats(daily),
                "trades": int((pos.diff().abs() > 0).sum()),
                "beats_random": random_percentile(ent, days, rets[t], cfg, rng),
            })
    table = pd.DataFrame(rows)
    # How independent are the "five tests"? Correlation of satellite-schedule strategy returns.
    corr = pd.DataFrame({t: daily_by[(t, "satellite")] for t in tickers}, index=days).corr()
    return table, corr


def equity_curves(cfg: Config, ticker: str) -> pd.DataFrame:
    """Growth of $1 for buy&hold and each schedule, for one ticker."""
    stocks = cushing_stocks()
    px = prices(LANDLORDS + CONTROL)[ticker]
    ret = px.pct_change()
    ret = ret[ret.index >= cfg.start].fillna(0.0)
    days = ret.index
    curves = {"buy&hold": (1 + ret).cumprod().to_numpy()}
    for sched in SCHEDULES:
        ent = entry_signals(stocks, days, sched, cfg.long_short)
        curves[sched] = np.cumprod(1 + strategy_returns(positions(ent, days), ret, cfg.cost_bps))
    return pd.DataFrame(curves, index=days)


def fmt(table: pd.DataFrame) -> str:
    t = table.copy()
    for c in ["total_ret", "cagr", "max_dd", "beats_random"]:
        t[c] = t[c].map(lambda v: "" if pd.isna(v) else f"{v:+.0%}" if c != "beats_random" else f"{v:.0%}")
    t["sharpe"] = t["sharpe"].map(lambda v: f"{v:.2f}")
    return t.to_string(index=False)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default=Config.start)
    ap.add_argument("--cost-bps", type=float, default=Config.cost_bps)
    ap.add_argument("--long-short", action="store_true")
    ap.add_argument("--n-random", type=int, default=Config.n_random)
    a = ap.parse_args()
    cfg = Config(start=a.start, cost_bps=a.cost_bps, long_short=a.long_short, n_random=a.n_random)
    table, corr = run(cfg)
    print(f"start={cfg.start} cost={cfg.cost_bps}bps/side long_short={cfg.long_short}\n")
    print(fmt(table))
    print("\nCorrelation of daily strategy returns (satellite schedule):")
    print(corr.round(2).to_string())


if __name__ == "__main__":
    main()
