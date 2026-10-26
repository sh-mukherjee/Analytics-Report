"""Portfolio construction: rebalanced target weights vs the benchmark.

The engine compounds daily returns while letting weights drift between
rebalances, so intra-month compounding is exact and the reset happens on the
last trading day of each rebalance period (``config.REBALANCE``). Reported
monthly returns are therefore true buy-and-hold-within-month returns, not
approximations.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src import config, data


@dataclass
class Simulation:
    equity: pd.Series
    weights_start: pd.DataFrame          # weight of each stock at the start of each day
    contribution: pd.DataFrame           # additive daily contribution, w_{t-1} * r_t
    rebalances: pd.DataFrame             # date, one-way turnover, cost


@dataclass
class PortfolioResult:
    dates: pd.DatetimeIndex
    daily: pd.DataFrame                  # r_portfolio, r_benchmark
    monthly: pd.DataFrame                # complete months only
    equity: pd.Series
    equity_bench: pd.Series
    weights_start: pd.DataFrame
    contribution: pd.DataFrame
    rebalances: pd.DataFrame
    net_equity: dict[int, pd.Series] = field(default_factory=dict)
    monthly_stock_returns: pd.DataFrame | None = None
    monthly_weights: pd.DataFrame | None = None
    monthly_contribution: pd.DataFrame | None = None
    analysis_end: pd.Timestamp | None = None
    month_ends: pd.DatetimeIndex | None = None
    partial_month: bool = False
    mtd: dict[str, float] = field(default_factory=dict)
    buy_and_hold_equity: pd.Series | None = None
    rebalance_dates: pd.DatetimeIndex | None = None


def _simulate(
    price_index: pd.DatetimeIndex,
    stock_returns: pd.DataFrame,
    weights_vec: np.ndarray,
    cost_bps: float,
    rebalance_set: set[pd.Timestamp],
) -> Simulation:
    cols = list(stock_returns.columns)
    R = stock_returns.to_numpy(dtype=float)
    target = np.asarray(weights_vec, dtype=float)
    k = R.shape[1]
    n = len(price_index)

    equity = np.ones(n)
    weights = target.copy()
    weights_start = np.zeros((n, k))
    contribution = np.zeros((n, k))
    rebalances: list[dict] = []

    for i in range(n):
        weights_start[i] = weights
        if i == 0:
            continue

        r = R[i - 1]
        rp = float(weights @ r)
        contribution[i] = weights * r
        equity[i] = equity[i - 1] * (1.0 + rp)
        weights = weights * (1.0 + r) / (1.0 + rp)

        if price_index[i] in rebalance_set:
            one_way = float(0.5 * np.abs(target - weights).sum())
            cost = one_way * cost_bps / 10_000.0
            if cost:
                equity[i] *= 1.0 - cost
            rebalances.append(
                {"date": price_index[i], "turnover": one_way, "cost": cost}
            )
            weights = target

    return Simulation(
        equity=pd.Series(equity, index=price_index, name="equity"),
        weights_start=pd.DataFrame(weights_start, index=price_index, columns=cols),
        contribution=pd.DataFrame(contribution, index=price_index, columns=cols),
        rebalances=pd.DataFrame(rebalances),
    )


def build(panel: data.Panel, daily_ret: pd.DataFrame) -> PortfolioResult:
    """Run the gross simulation plus net-of-cost variants and derive monthlies."""
    dates = panel.dates
    month_ends = data.month_end_dates(dates)

    # A month that has not finished is reported as MTD, never as a full month.
    today = pd.Timestamp.today().normalize()
    partial = (
        len(month_ends) > 0
        and month_ends[-1].to_period("M") == dates[-1].to_period("M")
        and dates[-1].to_period("M") == today.to_period("M")
    )
    used_ends = month_ends[:-1] if partial else month_ends
    analysis_end = used_ends[-1]
    if analysis_end > dates[-1]:
        analysis_end = dates[-1]

    stock_ret = daily_ret[config.TICKERS]
    bench_ret = daily_ret[config.BENCHMARK]

    # Rebalances happen on the last trading day of each rebalance period.
    # The inception date is already at target, so it is not a rebalance.
    reb_all = data.rebalance_dates(dates, config.REBALANCE)
    reb_used = reb_all[(reb_all > dates[0]) & (reb_all <= analysis_end)]
    reb_set = set(reb_used)

    gross = _simulate(dates, stock_ret, config.WEIGHTS_VECTOR, 0.0, reb_set)
    net_curves = {
        bps: _simulate(dates, stock_ret, config.WEIGHTS_VECTOR, float(bps), reb_set).equity
        for bps in config.COST_BPS
    }

    bench_eq = pd.concat(
        [
            pd.Series([1.0], index=[dates[0]]),
            (1.0 + bench_ret).cumprod(),
        ]
    )
    bench_eq = bench_eq[~bench_eq.index.duplicated(keep="first")]

    daily = pd.DataFrame(
        {
            "portfolio": gross.equity.pct_change(fill_method=None),
            "benchmark": bench_eq.pct_change(fill_method=None),
        }
    ).iloc[1:]

    # Complete months only.
    eq = gross.equity.loc[:analysis_end]
    eq_b = bench_eq.loc[:analysis_end]
    ends_in_window = pd.DatetimeIndex([d for d in used_ends if d <= analysis_end])
    monthly = pd.DataFrame(
        {
            "portfolio": eq.loc[ends_in_window].pct_change(fill_method=None),
            "benchmark": eq_b.loc[ends_in_window].pct_change(fill_method=None),
        }
    ).dropna()

    # Monthly stock returns / weights / contributions on the same calendar.
    month_start_dates = pd.DatetimeIndex([dates[0]]).append(ends_in_window[:-1])
    px = panel.adj_close.loc[ends_in_window]
    monthly_stock = px.pct_change(fill_method=None).dropna()

    w_start_month = gross.weights_start.loc[month_start_dates]
    w_start_month.index = ends_in_window

    # Exact additive decomposition: r_p,m = sum_i w_i,start * r_i,m, so
    # multiplying by the growth factor to the start of each month and summing
    # over months reproduces the cumulative return exactly.
    monthly_contrib = w_start_month[config.TICKERS].mul(
        monthly_stock[config.TICKERS]
    )
    monthly_contrib.index = ends_in_window

    # Counterfactual: equal weight bought once and never rebalanced.
    buy_and_hold = _simulate(dates, stock_ret, config.WEIGHTS_VECTOR, 0.0, set())

    # Month-to-date stub (excluded from all statistics).
    mtd = {}
    if partial:
        mtd = {
            "start": analysis_end,
            "end": dates[-1],
            "portfolio": float(gross.equity.iloc[-1] / gross.equity.loc[analysis_end] - 1.0),
            "benchmark": float(bench_eq.iloc[-1] / bench_eq.loc[analysis_end] - 1.0),
            "days": int((dates > analysis_end).sum()),
        }

    return PortfolioResult(
        dates=dates,
        daily=daily,
        monthly=monthly,
        equity=gross.equity,
        equity_bench=bench_eq,
        weights_start=gross.weights_start,
        contribution=gross.contribution,
        rebalances=gross.rebalances,
        net_equity=net_curves,
        monthly_stock_returns=monthly_stock,
        monthly_weights=w_start_month,
        monthly_contribution=monthly_contrib,
        analysis_end=analysis_end,
        month_ends=ends_in_window,
        partial_month=partial,
        mtd=mtd,
        buy_and_hold_equity=buy_and_hold.equity,
        rebalance_dates=reb_used,
    )
