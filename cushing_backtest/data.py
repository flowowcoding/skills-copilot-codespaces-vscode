"""Download and cache the two public inputs: EIA weekly Cushing stocks and daily prices."""

from __future__ import annotations

import io
import time
from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(__file__).parent / "data"
EIA_URL = "https://www.eia.gov/dnav/pet/hist_xls/W_EPC0_SAX_YCUOK_MBBLw.xls"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"


def cushing_stocks(refresh: bool = False) -> pd.Series:
    """Weekly Cushing, OK crude stocks excluding SPR (thousand barrels), indexed by week-ending Friday."""
    path = DATA_DIR / "cushing_weekly.csv"
    if refresh or not path.exists():
        resp = requests.get(EIA_URL, timeout=60)
        resp.raise_for_status()
        raw = pd.read_excel(io.BytesIO(resp.content), sheet_name="Data 1", skiprows=2)
        raw.columns = ["week_ending", "stocks_kbbl"]
        raw["week_ending"] = pd.to_datetime(raw["week_ending"])
        DATA_DIR.mkdir(exist_ok=True)
        raw.dropna().to_csv(path, index=False)
    df = pd.read_csv(path, parse_dates=["week_ending"])
    return df.set_index("week_ending")["stocks_kbbl"].astype(float)


def prices(tickers: list[str], start: str = "2014-06-01", refresh: bool = False) -> pd.DataFrame:
    """Daily dividend-adjusted closes. Adjustment matters: MLPs pay most of their return as distributions."""
    path = DATA_DIR / "prices_daily.csv"
    if not refresh and path.exists():
        cached = pd.read_csv(path, index_col=0, parse_dates=True)
        if set(tickers) <= set(cached.columns):
            return cached[tickers]
    frames = {}
    for ticker in tickers:
        params = {
            "period1": int(pd.Timestamp(start).timestamp()),
            "period2": int(time.time()),
            "interval": "1d",
            "events": "div,splits",
        }
        resp = requests.get(YAHOO_URL.format(ticker=ticker), params=params,
                            headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        resp.raise_for_status()
        result = resp.json()["chart"]["result"][0]
        idx = pd.to_datetime(result["timestamp"], unit="s").normalize()
        adj = result["indicators"]["adjclose"][0]["adjclose"]
        frames[ticker] = pd.Series(adj, index=idx, dtype=float)
    out = pd.DataFrame(frames).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    DATA_DIR.mkdir(exist_ok=True)
    out.to_csv(path)
    return out
