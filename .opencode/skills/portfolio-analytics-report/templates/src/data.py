"""Data acquisition, caching, validation and alignment.

Source: Yahoo Finance public chart endpoint (no API key). Responses are cached
under ``data/raw`` so the report is reproducible offline and figures do not
drift between runs. The endpoint is called directly rather than through a
wrapper library so that the adjusted-close series and corporate-action events
are read without an extra dependency layer.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import requests

from src import config

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
}


# --------------------------------------------------------------------------- #
# Fetching
# --------------------------------------------------------------------------- #

def fetch_yahoo(ticker: str, retries: int = 4) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (daily OHLCV+adjclose, dividends) for ``ticker`` from Yahoo."""
    params = {
        "period1": 0,
        "period2": int(time.time()) + 86_400,
        "interval": "1d",
        "events": "div,splits",
    }
    last_err: Exception | None = None

    for attempt in range(retries):
        try:
            resp = requests.get(
                YAHOO_CHART.format(ticker=ticker),
                params=params,
                headers=HEADERS,
                timeout=30,
            )
            resp.raise_for_status()
            payload = resp.json()
            result = (payload.get("chart") or {}).get("result") or []
            if not result:
                err = (payload.get("chart") or {}).get("error")
                raise ValueError(f"empty chart result ({err})")
            res = result[0]

            quotes = res["indicators"]["quote"][0]
            adj_block = (res["indicators"].get("adjclose") or [{}])[0]
            adjclose = adj_block.get("adjclose")
            if adjclose is None:                      # fall back to raw close
                adjclose = quotes.get("close")

            df = pd.DataFrame(
                {
                    "date": pd.to_datetime(res["timestamp"], unit="s").normalize(),
                    "open": quotes.get("open"),
                    "high": quotes.get("high"),
                    "low": quotes.get("low"),
                    "close": quotes.get("close"),
                    "volume": quotes.get("volume"),
                    "adjclose": adjclose,
                }
            )
            df = (
                df.dropna(subset=["date", "close", "adjclose"])
                .drop_duplicates(subset="date", keep="last")
                .set_index("date")
                .sort_index()
            )

            events = (res.get("events") or {}).get("dividends") or {}
            divs = pd.DataFrame(
                [
                    {
                        "date": pd.to_datetime(int(ts), unit="s").normalize(),
                        "amount": float(ev["amount"]),
                    }
                    for ts, ev in events.items()
                ]
            )
            if divs.empty:
                divs = pd.DataFrame(columns=["date", "amount"])

            return df, divs.sort_values("date").reset_index(drop=True)

        except Exception as exc:  # noqa: BLE001 - retry any transport/parse error
            last_err = exc
            time.sleep(1.5 * (attempt + 1))

    raise RuntimeError(f"Failed to fetch {ticker}: {last_err}")


def load_raw(tickers: list[str] | None = None, refresh: bool = False) -> dict[str, dict[str, Any]]:
    """Load cached raw data, fetching only what is missing (or all if refresh)."""
    tickers = tickers or config.ALL_TICKERS
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    out: dict[str, dict[str, Any]] = {}

    for ticker in tickers:
        price_path = config.RAW_DIR / f"{ticker}.csv"
        div_path = config.RAW_DIR / f"{ticker}_dividends.csv"

        if price_path.exists() and not refresh:
            prices = pd.read_csv(price_path, parse_dates=["date"], index_col="date")
            divs = (
                pd.read_csv(div_path, parse_dates=["date"])
                if div_path.exists()
                else pd.DataFrame(columns=["date", "amount"])
            )
            source = "cache"
        else:
            print(f"  fetching {ticker} ...", flush=True)
            prices, divs = fetch_yahoo(ticker)
            prices.to_csv(price_path)
            divs.to_csv(div_path, index=False)
            source = "yahoo"

        out[ticker] = {"prices": prices, "dividends": divs, "source": source}

    return out


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

def validate_raw(raw: dict[str, dict[str, Any]], start: pd.Timestamp, end: pd.Timestamp) -> list[dict[str, Any]]:
    """Per-ticker data quality checks for the report appendix."""
    rows: list[dict[str, Any]] = []

    for ticker in config.ALL_TICKERS:
        px = raw[ticker]["prices"]
        divs = raw[ticker]["dividends"]
        win = px.loc[(px.index >= start) & (px.index <= end)]

        gaps = win.index.to_series().diff().dt.days
        max_gap = int(gaps.max()) if len(gaps.dropna()) else 0
        max_gap_date = gaps.idxmax().date().isoformat() if max_gap else ""

        # adjusted/raw ratio should only move on ex-dividend or split dates;
        # a 10bp threshold ignores floating-point jitter in the ratio itself
        ratio = win["adjclose"] / win["close"]
        ratio_moves = int((ratio.pct_change().abs() > 1e-3).sum())

        rows.append(
            {
                "ticker": ticker,
                "bars": int(len(win)),
                "first": win.index.min().date().isoformat() if len(win) else "",
                "last": win.index.max().date().isoformat() if len(win) else "",
                "dupes": int(px.index.duplicated().sum()),
                "non_positive": int((win["close"] <= 0).sum() + (win["adjclose"] <= 0).sum()),
                "max_gap_days": max_gap,
                "max_gap_end": max_gap_date,
                "adj_ratio_moves": ratio_moves,
                "dividends": int(len(divs)),
                "source": raw[ticker]["source"],
            }
        )

    return rows


# --------------------------------------------------------------------------- #
# Panel
# --------------------------------------------------------------------------- #

@dataclass
class Panel:
    adj_close: pd.DataFrame
    close: pd.DataFrame
    dates: pd.DatetimeIndex
    dropped_dates: list[pd.Timestamp] = field(default_factory=list)
    start: pd.Timestamp | None = None
    end: pd.Timestamp | None = None


def build_panel(raw: dict[str, dict[str, Any]]) -> Panel:
    """Align all series on common trading dates over the earliest common window."""
    adj = pd.concat(
        {t: raw[t]["prices"]["adjclose"] for t in config.ALL_TICKERS}, axis=1
    ).sort_index()
    raw_close = pd.concat(
        {t: raw[t]["prices"]["close"] for t in config.ALL_TICKERS}, axis=1
    ).sort_index()

    first_valid = {t: adj[t].first_valid_index() for t in config.ALL_TICKERS}
    start = max(d for d in first_valid.values() if d is not None)
    end = min(adj[t].last_valid_index() for t in config.ALL_TICKERS)

    window = adj.loc[(adj.index >= start) & (adj.index <= end)]
    bad = window.isna().any(axis=1)
    clean = window.loc[~bad].copy()
    clean.index.name = "date"

    clean_close = raw_close.reindex(clean.index)
    clean_close.index.name = "date"

    return Panel(
        adj_close=clean,
        close=clean_close,
        dates=clean.index,
        dropped_dates=list(window.index[bad]),
        start=clean.index.min(),
        end=clean.index.max(),
    )


def daily_returns(panel: Panel) -> pd.DataFrame:
    """Simple daily total returns; the first bar is the base, not a return."""
    ret = panel.adj_close.pct_change(fill_method=None).iloc[1:]
    ret.index.name = "date"
    return ret


def monthly_returns(daily: pd.DataFrame) -> pd.DataFrame:
    """Month-end compounded returns from a daily return frame."""
    def compound(s: pd.Series) -> float:
        return float((1.0 + s).prod() - 1.0)

    monthly = daily.resample("ME").apply(compound)
    return monthly.dropna(how="all")


def month_end_dates(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Last trading day of each calendar month present in ``index``."""
    s = pd.Series(index, index=index)
    return pd.DatetimeIndex(s.groupby([index.year, index.month]).max().values)


def rebalance_dates(index: pd.DatetimeIndex, freq: str = "monthly") -> pd.DatetimeIndex:
    """Last trading day of each rebalance period present in ``index``.

    ``freq`` is ``monthly``, ``quarterly`` or ``weekly``. Weekly uses the ISO
    week, so a holiday-shortened week still produces one rebalance.
    """
    s = pd.Series(index, index=index)

    if freq == "monthly":
        keys = [index.year, index.month]
    elif freq == "quarterly":
        keys = [index.year, index.quarter]
    elif freq == "weekly":
        iso = index.isocalendar()
        keys = [iso.year.to_numpy(), iso.week.to_numpy()]
    else:
        raise ValueError(f"unknown rebalance frequency: {freq}")

    return pd.DatetimeIndex(s.groupby(keys).max().values)


def trim(panel: Panel, start: pd.Timestamp) -> Panel:
    """Restrict the panel to dates on/after ``start`` (inclusive)."""
    mask = panel.dates >= start
    return Panel(
        adj_close=panel.adj_close.loc[mask],
        close=panel.close.loc[mask],
        dates=panel.dates[mask],
        dropped_dates=panel.dropped_dates,
        start=panel.dates[mask].min(),
        end=panel.dates[mask].max(),
    )
