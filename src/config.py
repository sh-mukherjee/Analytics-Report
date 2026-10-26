"""Project-wide constants and assumptions.

Everything universe-specific lives between the ``UNIVERSE`` markers so that the
skill's scaffold script can regenerate it from a spec. The ``ASSUMPTIONS`` block
holds the choices a reader might reasonably disagree with; they are surfaced in
the report appendix rather than buried.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

# >>> UNIVERSE
TICKERS: list[str] = ["0700.HK", "9988.HK", "9618.HK", "3690.HK"]
BENCHMARK: str = "3032.HK"

NAMES: dict[str, str] = {
    "0700.HK": "Tencent Holdings",
    "9988.HK": "Alibaba Group",
    "9618.HK": "JD.com",
    "3690.HK": "Meituan",
    "3032.HK": "Hang Seng Tech Index ETF",
}

SHORT_NAMES: dict[str, str] = {
    "0700.HK": "Tencent",
    "9988.HK": "Alibaba",
    "9618.HK": "JD.com",
    "3690.HK": "Meituan",
    "3032.HK": "HS Tech ETF",
}

WEIGHT_TARGET: float = 0.25
REBALANCE: str = "monthly"

TITLE: str = "HK Technology Equal-Weight Portfolio"
SUBTITLE: str | None = None
MARKET: str = "Hong Kong"
CURRENCY: str = "HKD"
CURRENCY_SYMBOL: str = "HK$"
# <<< UNIVERSE

# >>> ASSUMPTIONS
RISK_FREE: float = 0.0
COST_BPS: list[int] = [0, 5, 10, 25]
PRIMARY_COST_BPS: int = 10
INITIAL_CAPITAL: float = 1_000_000.0
# <<< ASSUMPTIONS

ALL_TICKERS: list[str] = TICKERS + [BENCHMARK]

TRADING_DAYS: int = 252
MONTHS_PER_YEAR: int = 12

# Equal weights by default; replace with an explicit dict for a custom book.
WEIGHTS: dict[str, float] = {t: WEIGHT_TARGET for t in TICKERS}
WEIGHTS_VECTOR: np.ndarray = np.array([WEIGHTS[t] for t in TICKERS], dtype=float)

SHORT: dict[str, str] = {t: SHORT_NAMES.get(t, NAMES[t]) for t in ALL_TICKERS}

# --- Paths --------------------------------------------------------------------

ROOT: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = ROOT / "data"
RAW_DIR: Path = DATA_DIR / "raw"
OUT_DIR: Path = ROOT / "outputs"
CHART_DIR: Path = OUT_DIR / "charts"

# --- Presentation -------------------------------------------------------------

COLORS: dict[str, str] = {
    "portfolio": "#0B5563",
    "benchmark": "#C77C1E",
    "equity": "#0B5563",
    "drawdown_p": "#B03A2E",
    "drawdown_b": "#C77C1E",
    "accent": "#2E86AB",
    "accent2": "#4E9BC0",
    "muted": "#7A8794",
    "grid": "#E4E7EB",
}

_PALETTE: list[str] = [
    "#0B5563",
    "#2E86AB",
    "#C77C1E",
    "#8C5A9E",
    "#5C8A3A",
    "#A0522D",
    "#7A8794",
    "#B03A2E",
]
HOLDING_COLORS: list[str] = [_PALETTE[i % len(_PALETTE)] for i in range(len(TICKERS))]
