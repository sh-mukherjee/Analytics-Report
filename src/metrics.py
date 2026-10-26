"""Ex-post performance, risk, benchmark-relative and attribution analytics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

from src import config


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _years(index: pd.Index) -> float:
    return max((index[-1] - index[0]).days / 365.25, 1e-9)


def equity_from_returns(
    r: pd.Series, base: float = 1.0, base_date: pd.Timestamp | None = None
) -> pd.Series:
    """Equity curve with a base point one bar before the first return."""
    eq = (1.0 + r).cumprod() * base
    if base_date is None:
        base_date = r.index[0] - pd.Timedelta(days=1)
    return pd.concat([pd.Series([base], index=[base_date]), eq])


def total_return(eq: pd.Series) -> float:
    return float(eq.iloc[-1] / eq.iloc[0] - 1.0)


def cagr(eq: pd.Series) -> float:
    yrs = _years(eq.index)
    return float((eq.iloc[-1] / eq.iloc[0]) ** (1.0 / yrs) - 1.0)


def ann_return(r: pd.Series, periods: int) -> float:
    return float(r.mean() * periods)


def ann_vol(r: pd.Series, periods: int) -> float:
    return float(r.std(ddof=1) * np.sqrt(periods))


def downside_dev(r: pd.Series, periods: int, mar: float = 0.0) -> float:
    threshold = mar / periods
    downside = np.minimum(r - threshold, 0.0)
    return float(np.sqrt((downside**2).mean()) * np.sqrt(periods))


def sharpe(r: pd.Series, periods: int, rf: float = config.RISK_FREE) -> float:
    vol = ann_vol(r, periods)
    return float("nan") if vol == 0 else (ann_return(r, periods) - rf) / vol


def sortino(r: pd.Series, periods: int, rf: float = config.RISK_FREE) -> float:
    dd = downside_dev(r, periods, rf)
    return float("nan") if dd == 0 else (ann_return(r, periods) - rf) / dd


def drawdown_series(eq: pd.Series) -> pd.Series:
    return eq / eq.cummax() - 1.0


def max_drawdown(eq: pd.Series) -> float:
    return float(drawdown_series(eq).min())


def drawdown_episodes(eq: pd.Series, top: int = 5, threshold: float = 0.10) -> pd.DataFrame:
    """Top drawdown legs, identified by a 10% zig-zag rule.

    A drawdown starts when the curve falls ``threshold`` below a running high
    and ends at the low that precedes a ``threshold`` rebound (or at the final
    observation). This separates the legs of a long bear market instead of
    collapsing six years into a single peak-to-recovery episode.
    """
    v = eq.to_numpy(dtype=float)
    dates = eq.index
    if len(v) < 2:
        return pd.DataFrame()

    episodes: list[dict[str, Any]] = []

    def _record(peak_i: int, trough_i: int) -> None:
        peak_val = v[peak_i]
        after = eq.iloc[trough_i + 1 :]
        rec = after[after >= peak_val]
        recovery = rec.index[0] if len(rec) else None
        episodes.append(
            {
                "peak": dates[peak_i],
                "trough": dates[trough_i],
                "recovery": recovery,
                "depth": float(v[trough_i] / peak_val - 1.0),
                "to_trough_days": int((dates[trough_i] - dates[peak_i]).days),
                "recovery_days": (
                    int((recovery - dates[trough_i]).days) if recovery is not None else np.nan
                ),
                "underwater_days": (
                    int((recovery - dates[peak_i]).days)
                    if recovery is not None
                    else int((dates[-1] - dates[peak_i]).days)
                ),
                "recovered": recovery is not None,
            }
        )

    peak_i, trough_i = 0, 0
    state = "up"
    for i in range(1, len(v)):
        if state == "up":
            if v[i] > v[peak_i]:
                peak_i = i
            elif v[i] <= v[peak_i] * (1.0 - threshold):
                state, trough_i = "down", i
        else:
            if v[i] < v[trough_i]:
                trough_i = i
            elif v[i] >= v[trough_i] * (1.0 + threshold):
                _record(peak_i, trough_i)
                state, peak_i = "up", i

    if state == "down" and trough_i > peak_i:
        _record(peak_i, trough_i)

    out = pd.DataFrame(episodes)
    if out.empty:
        return out
    return out.sort_values("depth").head(top).reset_index(drop=True)


def var_cvar(r: pd.Series, level: float) -> tuple[float, float]:
    q = float(np.quantile(r, 1.0 - level))
    tail = r[r <= q]
    cvar = float(-tail.mean()) if len(tail) else float("nan")
    return -q, cvar


def omega(r: pd.Series, threshold: float = 0.0) -> float:
    gains = np.clip(r - threshold, 0, None).sum()
    losses = -np.clip(r - threshold, None, 0).sum()
    return float("nan") if losses == 0 else float(gains / losses)


def ulcer_index(eq: pd.Series) -> float:
    dd = drawdown_series(eq)
    return float(np.sqrt((dd**2).mean()))


def pain_index(eq: pd.Series) -> float:
    return float(-drawdown_series(eq).mean())


def tail_ratio(r: pd.Series) -> float:
    p95, p5 = np.percentile(r, 95), np.percentile(r, 5)
    return float(abs(p95) / abs(p5)) if p5 != 0 else float("nan")


def capture_ratios(r: pd.Series, b: pd.Series) -> tuple[float, float]:
    up, down = b > 0, b < 0
    up_cap = r[up].mean() / b[up].mean() if up.any() else np.nan
    down_cap = r[down].mean() / b[down].mean() if down.any() else np.nan
    return float(up_cap), float(down_cap)


def capm(r: pd.Series, b: pd.Series, periods: int = 12) -> dict[str, float]:
    """OLS with Newey-West HAC errors on monthly returns."""
    X = sm.add_constant(b.to_numpy(dtype=float))
    model = sm.OLS(r.to_numpy(dtype=float), X)
    maxlags = max(1, int(np.floor(4 * (len(r) / 100.0) ** (2.0 / 9.0))))
    fit = model.fit(cov_type="HAC", cov_kwds={"maxlags": maxlags})

    alpha_m, beta = fit.params
    se_alpha, se_beta = fit.bse
    t_alpha = fit.tvalues[0]
    p_alpha = fit.pvalues[0]
    r2 = fit.rsquared
    corr = float(np.corrcoef(r, b)[0, 1])

    return {
        "alpha_monthly": float(alpha_m),
        "alpha_annual": float(alpha_m * periods),
        "alpha_se_annual": float(se_alpha * periods),
        "alpha_t": float(t_alpha),
        "alpha_p": float(p_alpha),
        "beta": float(beta),
        "beta_se": float(se_beta),
        "r2": float(r2),
        "corr": corr,
        "n": int(len(r)),
        "maxlags": int(maxlags),
    }


def calendar_year_table(monthly: pd.DataFrame) -> pd.DataFrame:
    out = {}
    for col in monthly.columns:
        g = monthly[col].groupby(monthly.index.year).apply(lambda s: float((1 + s).prod() - 1))
        out[col] = g
    table = pd.DataFrame(out)
    table["active"] = table["portfolio"] - table["benchmark"]
    table.index.name = "year"
    return table


def monthly_table(monthly: pd.Series) -> pd.DataFrame:
    """Year x month matrix of returns (percent), plus a YTD column."""
    df = monthly.copy()
    table = pd.DataFrame(
        {
            "year": df.index.year,
            "month": df.index.month,
            "ret": df.to_numpy(),
        }
    )
    pivot = table.pivot(index="year", columns="month", values="ret")
    pivot = pivot.reindex(columns=range(1, 13))
    pivot["YTD"] = pivot.apply(lambda row: (1 + row.dropna()).prod() - 1, axis=1)
    return pivot


def rolling_metrics(monthly: pd.DataFrame, window: int = 12) -> pd.DataFrame:
    p, b = monthly["portfolio"], monthly["benchmark"]
    out = pd.DataFrame(index=monthly.index)
    out["ret_p"] = (1 + p).rolling(window).apply(np.prod, raw=True) - 1
    out["ret_b"] = (1 + b).rolling(window).apply(np.prod, raw=True) - 1
    out["vol_p"] = p.rolling(window).std(ddof=1) * np.sqrt(12)
    out["vol_b"] = b.rolling(window).std(ddof=1) * np.sqrt(12)
    out["sharpe_p"] = (
        p.rolling(window).mean() * 12 / (p.rolling(window).std(ddof=1) * np.sqrt(12))
    )
    out["sharpe_b"] = (
        b.rolling(window).mean() * 12 / (b.rolling(window).std(ddof=1) * np.sqrt(12))
    )
    out["beta_p"] = p.rolling(window).cov(b) / b.rolling(window).var()
    out["te"] = (p - b).rolling(window).std(ddof=1) * np.sqrt(12)
    out["active"] = out["ret_p"] - out["ret_b"]
    return out.dropna()


# --------------------------------------------------------------------------- #
# Main computation
# --------------------------------------------------------------------------- #

@dataclass
class Analytics:
    daily: pd.DataFrame
    monthly: pd.DataFrame
    equity: pd.Series
    equity_bench: pd.Series
    metrics: dict[str, Any]
    holdings: pd.DataFrame
    monthly_cal: pd.DataFrame
    yearly: pd.DataFrame
    drawdowns: pd.DataFrame
    drawdown_bench: pd.DataFrame
    rolling: pd.DataFrame
    attribution: pd.DataFrame
    risk_contrib: pd.DataFrame
    cost_table: pd.DataFrame
    rebalance_compare: pd.DataFrame
    distribution: dict[str, float]
    regression: dict[str, float]
    capture: dict[str, float]
    best_worst: dict[str, Any]
    monthly_matrix: pd.DataFrame
    yearly_matrix: pd.DataFrame


def compute(result) -> Analytics:  # result: portfolio.PortfolioResult
    daily_all = result.daily
    monthly = result.monthly

    # Restrict daily stats to the complete-month window.
    daily = daily_all.loc[: result.analysis_end].dropna()
    p, b = monthly["portfolio"], monthly["benchmark"]

    eq = result.equity.loc[: result.analysis_end] * config.INITIAL_CAPITAL
    eq_b = result.equity_bench.loc[: result.analysis_end] * config.INITIAL_CAPITAL

    # --- headline metrics ---------------------------------------------------
    m: dict[str, Any] = {}
    m["start"] = eq.index[0]
    m["end"] = monthly.index[-1]
    m["n_months"] = len(monthly)
    m["n_days"] = len(daily)
    m["years"] = _years(eq.index)

    for label, series, curve in (("p", p, eq), ("b", b, eq_b)):
        m[f"total_{label}"] = total_return(curve)
        m[f"cagr_{label}"] = cagr(curve)
        m[f"vol_{label}"] = ann_vol(series, 12)
        m[f"vol_daily_{label}"] = ann_vol(daily["portfolio" if label == "p" else "benchmark"], 252)
        m[f"sharpe_{label}"] = sharpe(series, 12)
        m[f"maxdd_{label}"] = max_drawdown(curve)
        m[f"terminal_{label}"] = float(curve.iloc[-1])

    m["active_total"] = m["total_p"] - m["total_b"]
    m["active_cagr"] = m["cagr_p"] - m["cagr_b"]
    m["active_vol"] = float((p - b).std(ddof=1) * np.sqrt(12))
    m["te"] = m["active_vol"]
    m["ir"] = (
        float((p - b).mean() * 12 / m["te"]) if m["te"] else float("nan")
    )
    m["tracking_diff"] = float((p - b).mean() * 12)

    m["sortino"] = sortino(p, 12)
    m["sortino_b"] = sortino(b, 12)
    m["downside_dev"] = downside_dev(p, 12)
    m["downside_dev_b"] = downside_dev(b, 12)
    m["calmar"] = m["cagr_p"] / abs(m["maxdd_p"]) if m["maxdd_p"] else float("nan")
    m["calmar_b"] = m["cagr_b"] / abs(m["maxdd_b"]) if m["maxdd_b"] else float("nan")

    m["var_95_1d"], m["cvar_95_1d"] = var_cvar(daily["portfolio"], 0.95)
    m["var_99_1d"], m["cvar_99_1d"] = var_cvar(daily["portfolio"], 0.99)
    m["var_95_m"], m["cvar_95_m"] = var_cvar(p, 0.95)
    m["var_99_m"], m["cvar_99_m"] = var_cvar(p, 0.99)

    m["omega"] = omega(p)
    m["omega_b"] = omega(b)
    m["ulcer"] = ulcer_index(eq)
    m["ulcer_b"] = ulcer_index(eq_b)
    m["pain"] = pain_index(eq)
    m["tail_ratio"] = tail_ratio(p)

    m["skew"] = float(stats.skew(p, bias=False))
    m["kurtosis"] = float(stats.kurtosis(p, fisher=True, bias=False))
    jb_stat, jb_p = stats.jarque_bera(p)
    m["jb_stat"], m["jb_p"] = float(jb_stat), float(jb_p)
    m["skew_b"] = float(stats.skew(b, bias=False))
    m["kurtosis_b"] = float(stats.kurtosis(b, fisher=True, bias=False))

    # --- regression / benchmark-relative -----------------------------------
    reg = capm(p, b)
    m["beta"] = reg["beta"]
    m["alpha_annual"] = reg["alpha_annual"]
    m["alpha_t"] = reg["alpha_t"]
    m["alpha_p"] = reg["alpha_p"]
    m["r2"] = reg["r2"]
    m["corr"] = reg["corr"]

    m["treynor"] = (ann_return(p, 12) - config.RISK_FREE) / reg["beta"] if reg["beta"] else np.nan
    m["m2"] = config.RISK_FREE + m["sharpe_p"] * m["vol_b"]
    m["m2_excess"] = (m["sharpe_p"] - m["sharpe_b"]) * m["vol_b"]

    up_cap, down_cap = capture_ratios(p, b)
    m["up_capture"], m["down_capture"] = up_cap, down_cap
    m["batting_avg"] = float((p > b).mean())
    m["hit_rate"] = float((p > 0).mean())
    m["best_month"] = float(p.max())
    m["worst_month"] = float(p.min())
    m["best_month_b"] = float(b.max())
    m["worst_month_b"] = float(b.min())
    m["best_month_date"] = p.idxmax()
    m["worst_month_date"] = p.idxmin()

    m["avg_up_month"] = float(p[p > 0].mean())
    m["avg_down_month"] = float(p[p < 0].mean())
    m["gain_loss_ratio"] = abs(m["avg_up_month"] / m["avg_down_month"]) if m["avg_down_month"] else np.nan

    # concentration / diversification
    w = pd.Series(config.WEIGHTS)
    cov = result.monthly_stock_returns.loc[:, config.TICKERS].cov() * 12
    cov = cov.loc[config.TICKERS, config.TICKERS]
    port_var = float(w @ cov @ w)
    mctr = (cov @ w) / np.sqrt(port_var)
    rc = w * mctr / np.sqrt(port_var)
    port_vol = float(np.sqrt(port_var))
    m["diversification_ratio"] = (
        float((w * np.sqrt(np.diag(cov))).sum() / port_vol) if port_vol else np.nan
    )

    # --- tables -------------------------------------------------------------
    holdings = pd.DataFrame(
        {
            "ticker": config.TICKERS,
            "name": [config.NAMES[t] for t in config.TICKERS],
            "weight": [config.WEIGHTS[t] for t in config.TICKERS],
        }
    )
    rows = []
    for t in config.TICKERS:
        s = result.monthly_stock_returns[t]
        tot = float((1 + s).prod() - 1)
        yrs = _years(s.index)
        rows.append(
            {
                "cagr": (1 + tot) ** (1 / yrs) - 1,
                "vol": s.std(ddof=1) * np.sqrt(12),
                "sharpe": (s.mean() * 12) / (s.std(ddof=1) * np.sqrt(12)) if s.std(ddof=1) else np.nan,
                "maxdd": max_drawdown(equity_from_returns(s)),
                "beta": s.cov(b) / b.var(),
                "corr": s.corr(b),
                "total": tot,
            }
        )
    holdings = pd.concat([holdings, pd.DataFrame(rows)], axis=1)

    monthly_contrib = result.monthly_contribution
    # Exact decomposition: sum of daily w_{i,t-1} r_{i,t} equals the daily
    # portfolio return, so linking each day by cumulative growth reproduces the
    # cumulative return exactly.
    daily_contrib = result.contribution.loc[: result.analysis_end]
    growth = (result.equity.loc[: result.analysis_end] / result.equity.iloc[0]).shift(
        1, fill_value=1.0
    )
    contribution = daily_contrib.mul(growth, axis=0).sum()
    attribution = pd.DataFrame(
        {
            "ticker": config.TICKERS,
            "name": [config.NAMES[t] for t in config.TICKERS],
            "contribution_total": [contribution[t] for t in config.TICKERS],
            "contribution_annual": [contribution[t] / m["years"] for t in config.TICKERS],
        }
    )

    risk_contrib = pd.DataFrame(
        {
            "ticker": config.TICKERS,
            "name": [config.NAMES[t] for t in config.TICKERS],
            "weight": [config.WEIGHTS[t] for t in config.TICKERS],
            "risk_contribution": rc.to_numpy(),
        }
    )

    # cost sensitivity
    base_curve = result.net_equity[0].loc[: result.analysis_end]
    base_cagr = cagr(base_curve)
    cost_rows = []
    for bps in config.COST_BPS:
        curve = result.net_equity[bps].loc[: result.analysis_end]
        cost_rows.append(
            {
                "bps": bps,
                "cagr": cagr(curve),
                "total": total_return(curve),
                "drag": base_cagr - cagr(curve),
                "maxdd": max_drawdown(curve),
            }
        )
    cost_table = pd.DataFrame(cost_rows)
    m["avg_turnover"] = float(result.rebalances["turnover"].mean())
    m["annual_turnover"] = float(result.rebalances["turnover"].sum() / m["years"])

    # Rebalancing vs a one-off purchase of the target weights, same universe.
    bh = result.buy_and_hold_equity.loc[: result.analysis_end]
    bh_ret = bh.pct_change(fill_method=None).dropna()
    rebalance_compare = pd.DataFrame(
        [
            {
                "policy": f"{config.REBALANCE.capitalize()} rebalance to target",
                "total": m["total_p"],
                "cagr": m["cagr_p"],
                "vol": m["vol_p"],
                "maxdd": m["maxdd_p"],
            },
            {
                "policy": "Buy and hold (no rebalancing)",
                "total": total_return(bh),
                "cagr": cagr(bh),
                "vol": ann_vol(bh_ret, 252),
                "maxdd": max_drawdown(bh),
            },
        ]
    )

    dd = drawdown_episodes(eq, top=5)
    dd_b = drawdown_episodes(eq_b, top=5)

    yearly = calendar_year_table(monthly)
    rolling = rolling_metrics(monthly)
    mm = monthly_table(p)
    ymb = monthly_table(b)

    # distribution / scatter helpers
    distribution = {"p": p, "b": b}

    return Analytics(
        daily=daily,
        monthly=monthly,
        equity=eq,
        equity_bench=eq_b,
        metrics=m,
        holdings=holdings,
        monthly_cal=monthly.rename(columns={"portfolio": "Portfolio", "benchmark": "Benchmark"}),
        yearly=yearly,
        drawdowns=dd,
        drawdown_bench=dd_b,
        rolling=rolling,
        attribution=attribution,
        risk_contrib=risk_contrib,
        cost_table=cost_table,
        rebalance_compare=rebalance_compare,
        distribution=distribution,
        regression=reg,
        capture={"up": up_cap, "down": down_cap},
        best_worst={
            "best": (float(p.max()), p.idxmax()),
            "worst": (float(p.min()), p.idxmin()),
            "best_b": (float(b.max()), b.idxmax()),
            "worst_b": (float(b.min()), b.idxmin()),
        },
        monthly_matrix=mm,
        yearly_matrix=ymb,
    )
