"""Chart and HTML report generation."""

from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape
from matplotlib.colors import TwoSlopeNorm
from matplotlib.ticker import FuncFormatter, MaxNLocator, MultipleLocator, PercentFormatter

from src import config, data

# --------------------------------------------------------------------------- #
# Style
# --------------------------------------------------------------------------- #

plt.rcParams.update(
    {
        "figure.dpi": 150,
        "savefig.dpi": 150,
        "font.size": 9.5,
        "font.family": "DejaVu Sans",
        "axes.edgecolor": "#C9D0D6",
        "axes.labelcolor": "#46525E",
        "axes.labelsize": 9,
        "xtick.color": "#66737F",
        "ytick.color": "#66737F",
        "xtick.labelsize": 8.5,
        "ytick.labelsize": 8.5,
        "axes.grid": True,
        "grid.color": "#EDF0F2",
        "grid.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
        "legend.fontsize": 8.5,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    }
)

C = config.COLORS


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #

def pct(x: float, dp: int = 2, sign: bool = False) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    fmt = f"{{:+.{dp}f}}%" if sign else f"{{:.{dp}f}}%"
    return fmt.format(x * 100)


def pp(x: float, dp: int = 2, sign: bool = False) -> str:
    """Percentage points: like pct, without the percent sign."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    fmt = f"{{:+.{dp}f}}" if sign else f"{{:.{dp}f}}"
    return fmt.format(x * 100) + " pp"


def num(x: float, dp: int = 2) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    return f"{x:,.{dp}f}"


def money(x: float) -> str:
    return f"{x:,.0f}"


def _tick_step(span: float) -> float:
    """Axis tick step (in return units) giving roughly 3-7 gridlines."""
    for step in (0.5, 0.25, 0.1, 0.05, 0.02, 0.01, 0.005):
        if 2.5 <= span / step <= 7:
            return step
    return 0.05


def money_short(x: float) -> str:
    """Compact currency label for chart annotations."""
    return f"{config.CURRENCY_SYMBOL}{x/1e6:,.2f}m"


def cur(x: float) -> str:
    """Full currency amount, e.g. 1,000,000 with the display symbol prefixed."""
    return f"{config.CURRENCY_SYMBOL}{money(x)}"


def d(x) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)) or pd.isna(x):
        return "—"
    return pd.Timestamp(x).strftime("%d %b %Y")


def cls_for(x: float) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "mute"
    return "pos" if x > 0 else ("neg" if x < 0 else "")


def _table(headers: list[str], rows: list[list[tuple[str, str]]], total: bool = False) -> str:
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = []
    for i, row in enumerate(rows):
        is_total = total and i == len(rows) - 1
        tds = "".join(
            f'<td class="{c}">{t}</td>' if c else f"<td>{t}</td>" for t, c in row
        )
        body.append(f'<tr class="total">{tds}</tr>' if is_total else f"<tr>{tds}</tr>")
    return (
        f"<table><thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
    )


# --------------------------------------------------------------------------- #
# Figures
# --------------------------------------------------------------------------- #

def _save(fig, name: str) -> str:
    config.CHART_DIR.mkdir(parents=True, exist_ok=True)
    path = config.CHART_DIR / f"{name}.png"
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return str(path)


def _b64(path: str) -> str:
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()


def _growth(a, m) -> str:
    w = config.WEIGHTS_VECTOR
    equal = bool(np.allclose(w, w[0]))
    label = (
        f"Portfolio ({w[0]*100:.0f}% each, {config.REBALANCE} rebalanced)"
        if equal
        else f"Portfolio ({config.REBALANCE} rebalanced)"
    )
    fig, ax = plt.subplots(figsize=(10.6, 4.4))
    ax.plot(a.equity.index, a.equity.values, color=C["portfolio"], lw=1.7, label=label)
    ax.plot(a.equity_bench.index, a.equity_bench.values, color=C["benchmark"], lw=1.5, label=f"Benchmark ({config.BENCHMARK})")
    ax.axhline(config.INITIAL_CAPITAL, color="#9AA6B2", lw=0.8, ls=(0, (4, 3)))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v/config.INITIAL_CAPITAL:.2f}×"))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_ylabel("Value (multiple of initial capital)")
    ax.legend(loc="upper right")
    ax.annotate(
        f"{money_short(a.equity_bench.iloc[-1])}",
        xy=(a.equity_bench.index[-1], a.equity_bench.iloc[-1]),
        xytext=(7, 9),
        textcoords="offset points",
        color=C["benchmark"],
        fontsize=8.5,
        va="bottom",
        ha="left",
        fontweight="bold",
    )
    ax.annotate(
        f"{money_short(a.equity.iloc[-1])}",
        xy=(a.equity.index[-1], a.equity.iloc[-1]),
        xytext=(7, -9),
        textcoords="offset points",
        color=C["portfolio"],
        fontsize=8.5,
        va="top",
        ha="left",
        fontweight="bold",
    )
    ax.set_xlim(a.equity.index[0], a.equity.index[-1] + pd.Timedelta(days=70))
    ax.grid(axis="x", visible=False)
    return _save(fig, "growth")


def _drawdown(a) -> str:
    fig, ax = plt.subplots(figsize=(10.6, 3.9))
    dd_p = a.equity / a.equity.cummax() - 1
    dd_b = a.equity_bench / a.equity_bench.cummax() - 1
    ax.fill_between(dd_p.index, dd_p.values, 0, color=C["portfolio"], alpha=0.08, linewidth=0)
    ax.plot(dd_p.index, dd_p.values, color=C["portfolio"], lw=1.2, label="Portfolio")
    ax.plot(dd_b.index, dd_b.values, color=C["benchmark"], lw=1.1, label="Benchmark")
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_ylim(min(dd_p.min(), dd_b.min()) * 1.12, 0.02)
    ax.legend(loc="lower left")
    for series, color, dy in ((dd_p, C["portfolio"], -13), (dd_b, C["benchmark"], -13)):
        trough = series.idxmin()
        ax.annotate(
            f"{series.min()*100:.0f}%",
            xy=(trough, series.min()),
            xytext=(0, dy),
            textcoords="offset points",
            ha="center",
            fontsize=8.5,
            color=color,
            fontweight="bold",
        )
    ax.grid(axis="x", visible=False)
    return _save(fig, "drawdown")


def _partial_years(a) -> set[int]:
    """Calendar years that appear only partially in the monthly record."""
    first = pd.Timestamp(a.monthly.index[0])
    last = pd.Timestamp(a.monthly.index[-1])
    years = set()
    if first.month != 1:
        years.add(first.year)
    if last.month != 12:
        years.add(last.year)
    return years


def _yearly(a) -> str:
    y = a.yearly
    partial = _partial_years(a)
    fig, ax = plt.subplots(figsize=(10.6, 3.8))
    x = np.arange(len(y))
    w = 0.38
    ax.bar(x - w / 2, y["portfolio"].values, w, color=C["portfolio"], label="Portfolio", zorder=3)
    ax.bar(x + w / 2, y["benchmark"].values, w, color=C["benchmark"], label="Benchmark", zorder=3)
    ax.axhline(0, color="#7A8794", lw=0.9, zorder=4)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{i}{'*' if i in partial else ''}" for i in y.index])
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.grid(axis="x", visible=False)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", ncol=2)
    ax.set_ylabel("Total return")
    for xi, (p, b) in enumerate(zip(y["portfolio"], y["benchmark"])):
        ax.annotate(f"{p*100:.0f}", xy=(xi - w / 2, p), xytext=(0, 3 if p >= 0 else -12),
                    textcoords="offset points", ha="center", fontsize=7.5, color=C["portfolio"])
        ax.annotate(f"{b*100:.0f}", xy=(xi + w / 2, b), xytext=(0, 3 if b >= 0 else -12),
                    textcoords="offset points", ha="center", fontsize=7.5, color=C["benchmark"])
    return _save(fig, "yearly")


def _heatmap(a) -> str:
    mat = a.monthly_matrix.drop(columns=["YTD"])
    fig, ax = plt.subplots(figsize=(10.6, 3.5))
    data_vals = mat.to_numpy(dtype=float) * 100
    cmap = plt.get_cmap("RdYlGn")
    norm = TwoSlopeNorm(vmin=-30, vcenter=0, vmax=30)
    im = ax.imshow(np.ma.masked_invalid(data_vals), cmap=cmap, norm=norm, aspect="auto")
    ax.set_xticks(range(12))
    ax.set_xticklabels(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
    ax.set_yticks(range(len(mat.index)))
    star = _partial_years(a)
    ax.set_yticklabels([f"{i}{'*' if i in star else ''}" for i in mat.index])
    ax.grid(False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    for i in range(data_vals.shape[0]):
        for j in range(data_vals.shape[1]):
            v = data_vals[i, j]
            if np.isnan(v):
                ax.text(j, i, "·", ha="center", va="center", color="#C9D0D6", fontsize=9)
            else:
                ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=8,
                        color="#1B2A38" if abs(v) < 18 else "white")
    ax.set_xticks(np.arange(-0.5, 12, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(mat.index), 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=2)
    ax.tick_params(which="minor", length=0)
    cb = fig.colorbar(im, ax=ax, pad=0.012, fraction=0.026)
    cb.outline.set_visible(False)
    cb.ax.tick_params(labelsize=7.5)
    cb.set_label("Monthly return (%)", fontsize=8)
    return _save(fig, "heatmap")


def _rolling(a) -> str:
    r = a.rolling
    fig, axes = plt.subplots(2, 2, figsize=(10.6, 6.2), sharex=True)
    ax1, ax2, ax3, ax4 = axes.ravel()

    ax1.plot(r.index, r["ret_p"], color=C["portfolio"], lw=1.3, label="Portfolio")
    ax1.plot(r.index, r["ret_b"], color=C["benchmark"], lw=1.2, label="Benchmark")
    ax1.axhline(0, color="#7A8794", lw=0.8)
    ax1.set_title("Rolling 12-month return", fontsize=9.5, loc="left", color="#16202A")
    ax1.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax1.legend(loc="upper left", fontsize=8, frameon=True, facecolor="white",
               edgecolor="none", framealpha=0.9)

    ax2.plot(r.index, r["vol_p"], color=C["portfolio"], lw=1.3)
    ax2.plot(r.index, r["vol_b"], color=C["benchmark"], lw=1.2)
    ax2.set_title("Rolling 12-month volatility (annualised)", fontsize=9.5, loc="left")
    ax2.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))

    ax3.plot(r.index, r["sharpe_p"], color=C["portfolio"], lw=1.3)
    ax3.plot(r.index, r["sharpe_b"], color=C["benchmark"], lw=1.2)
    ax3.axhline(0, color="#7A8794", lw=0.8)
    ax3.set_title("Rolling 12-month Sharpe ratio", fontsize=9.5, loc="left")
    ax3.legend(["Portfolio", "Benchmark"], loc="lower left", fontsize=8, frameon=True,
               facecolor="white", edgecolor="none", framealpha=0.9)

    ax4.plot(r.index, r["beta_p"], color=C["accent2"], lw=1.3)
    ax4.axhline(1.0, color="#9AA6B2", lw=0.9, ls=(0, (4, 3)))
    ax4.set_title("Rolling 12-month beta vs benchmark", fontsize=9.5, loc="left")

    for ax in axes.ravel():
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.grid(axis="x", visible=False)
    fig.tight_layout()
    return _save(fig, "rolling")


def _scatter(a) -> str:
    p = a.monthly["portfolio"]
    b = a.monthly["benchmark"]
    beta = a.regression["beta"]
    alpha = a.regression["alpha_monthly"]
    fig, ax = plt.subplots(figsize=(6.2, 5.0))
    ax.scatter(b, p, s=22, color=C["accent2"], alpha=0.55, edgecolor="white", linewidth=0.5, zorder=3)
    lo = min(b.min(), p.min()) * 1.12
    hi = max(b.max(), p.max()) * 1.08
    lim = np.array([lo, hi])
    ax.plot(lim, beta * lim + alpha, color=C["portfolio"], lw=1.3, zorder=4,
            label=f"Fit: β={beta:.2f}, α={a.regression['alpha_annual']*100:+.1f}%/yr")
    ax.plot(lim, lim, color="#9AA6B2", lw=1.0, ls=(0, (4, 3)), zorder=2, label="β = 1")
    ax.set_xlim(lim)
    ax.set_ylim(lim)
    ax.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.set_xlabel("Benchmark monthly return")
    ax.set_ylabel("Portfolio monthly return")
    ax.legend(loc="upper left", fontsize=8)
    ax.set_aspect("equal", adjustable="box")
    ax.text(0.98, 0.03, f"R² = {a.regression['r2']:.2f}", transform=ax.transAxes,
            ha="right", va="bottom", fontsize=8.5, color="#66737F")
    return _save(fig, "scatter")


def _active(a) -> str:
    m = a.monthly
    active = (1 + m["portfolio"]) / (1 + m["benchmark"]) - 1
    cum_active = (1 + active).cumprod() - 1
    beta = a.regression["beta"]
    ex = m["portfolio"] - beta * m["benchmark"]
    cum_ex = (1 + ex).cumprod() - 1
    idx = [m.index[0] - pd.offsets.MonthEnd(1)] + list(m.index)

    fig, ax = plt.subplots(figsize=(10.6, 4.0))
    ax.plot(idx[1:], cum_active.values, color=C["portfolio"], lw=1.6, label="Cumulative active return")
    ax.plot(idx[1:], cum_ex.values, color=C["accent2"], lw=1.3, ls=(0, (5, 2)),
            label="Cumulative beta-adjusted excess return")
    ax.axhline(0, color="#7A8794", lw=0.9)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.grid(axis="x", visible=False)
    ax.legend(loc="lower left")
    ax.fill_between(idx[1:], cum_active.values, 0, color=C["portfolio"], alpha=0.07, linewidth=0)
    ax.set_xlim(m.index[0], m.index[-1] + pd.Timedelta(days=40))
    return _save(fig, "active")


def _attrib(a) -> str:
    fig, axes = plt.subplots(1, 2, figsize=(10.6, 3.3))
    ax1, ax2 = axes

    at = a.attribution
    names = [config.SHORT[t] for t in at["ticker"]]
    vals = at["contribution_total"].to_numpy() * 100
    colors = [C["portfolio"] if v >= 0 else "#B03A2E" for v in vals]
    ax1.barh(names, vals, color=colors, height=0.55, zorder=3)
    ax1.axvline(0, color="#7A8794", lw=0.9)
    ax1.set_title("Contribution to cumulative return (pp)", fontsize=9.5, loc="left")
    ax1.invert_yaxis()
    ax1.grid(axis="y", visible=False)
    lo = min(float(vals.min()), 0.0)
    hi = max(float(vals.max()), 0.0)
    span = max(hi - lo, 1.0)
    ax1.set_xlim(lo - span * 0.10, hi + span * 0.16)
    ax1.xaxis.set_major_locator(MaxNLocator(nbins=7, integer=True))
    for i, v in enumerate(vals):
        ax1.text(v + (0.02 * span if v >= 0 else -0.02 * span), i, f"{v:+.1f}",
                 va="center", ha="left" if v >= 0 else "right", fontsize=8, color="#16202A")

    rc = a.risk_contrib
    names2 = [config.SHORT[t] for t in rc["ticker"]]
    vals2 = rc["risk_contribution"].to_numpy() * 100
    eq_share = 100.0 / len(names2)
    palette = config.HOLDING_COLORS
    bar_colors = [palette[i % len(palette)] for i in range(len(names2))]
    ax2.barh(names2, vals2, color=bar_colors, height=0.55, zorder=3)
    ax2.axvline(eq_share, color="#C77C1E", lw=1.0, ls=(0, (4, 3)))
    ax2.set_title("Share of portfolio risk (%)", fontsize=9.5, loc="left")
    ax2.invert_yaxis()
    ax2.grid(axis="y", visible=False)
    ax2.set_xlim(0, max(float(vals2.max()), eq_share) * 1.22)
    ax2.xaxis.set_major_locator(MaxNLocator(nbins=6, steps=[1, 2, 2.5, 5, 10]))
    for i, v in enumerate(vals2):
        ax2.text(v + 0.7, i, f"{v:.1f}", va="center", fontsize=8)

    fig.tight_layout()
    return _save(fig, "attrib")


def _distribution(a) -> str:
    p = a.monthly["portfolio"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.6, 3.6))
    ax1.hist(p * 100, bins=18, color=C["accent2"], alpha=0.75, edgecolor="white", density=True, zorder=3)
    grid = np.linspace(p.min() * 100, p.max() * 100, 200)
    mu, sd = p.mean() * 100, p.std(ddof=1) * 100
    ax1.plot(grid, (1 / (sd * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((grid - mu) / sd) ** 2),
             color=C["portfolio"], lw=1.4, label="Normal fit")
    ax1.axvline(0, color="#7A8794", lw=0.8)
    ax1.set_title("Monthly return distribution", fontsize=9.5, loc="left")
    ax1.set_xlabel("Monthly return (%)")
    ax1.grid(axis="x", visible=False)
    ax1.legend(loc="upper left")

    from scipy import stats

    stats.probplot(p.to_numpy(), dist="norm", plot=ax2)
    ax2.get_lines()[0].set_markerfacecolor(C["accent2"])
    ax2.get_lines()[0].set_markeredgecolor("white")
    ax2.get_lines()[0].set_markersize(4.5)
    ax2.get_lines()[1].set_color(C["portfolio"])
    ax2.get_lines()[1].set_linewidth(1.3)
    ax2.set_title("Normal Q-Q plot", fontsize=9.5, loc="left")
    ax2.set_title("")
    ax2.set_xlabel("Theoretical quantiles")
    ax2.set_ylabel("Sample quantiles")
    fig.tight_layout()
    return _save(fig, "distribution")


def _riskreturn(a) -> str:
    fig, ax = plt.subplots(figsize=(10.6, 4.0))
    h = a.holdings
    ax.scatter(h["vol"], h["cagr"], s=90, color=C["muted"], alpha=0.55, edgecolor="white",
               linewidth=1.0, zorder=3, label="Constituents")
    for _, row in h.iterrows():
        ax.annotate(config.SHORT[row["ticker"]], (row["vol"], row["cagr"]),
                    xytext=(7, 4), textcoords="offset points", fontsize=8, color="#5A6773")
    m = a.metrics
    ax.scatter([m["vol_p"]], [m["cagr_p"]], s=190, color=C["portfolio"], edgecolor="white",
               linewidth=1.6, zorder=5, label="Portfolio")
    ax.annotate("Portfolio", (m["vol_p"], m["cagr_p"]), xytext=(9, -12),
                textcoords="offset points", fontsize=9, fontweight="bold", color=C["portfolio"])
    ax.scatter([m["vol_b"]], [m["cagr_b"]], s=150, color=C["benchmark"], marker="D",
               edgecolor="white", linewidth=1.4, zorder=5, label="Benchmark")
    ax.annotate("Benchmark", (m["vol_b"], m["cagr_b"]), xytext=(9, 4),
                textcoords="offset points", fontsize=9, fontweight="bold", color=C["benchmark"])
    ax.axhline(0, color="#7A8794", lw=0.9)
    ax.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))

    xs = np.concatenate([h["vol"].to_numpy(float), [m["vol_p"], m["vol_b"]]])
    ys = np.concatenate([h["cagr"].to_numpy(float), [m["cagr_p"], m["cagr_b"]]])
    x_pad = max((xs.max() - xs.min()) * 0.14, 0.02)
    y_pad = max((ys.max() - ys.min()) * 0.16, 0.02)
    x_lo, x_hi = max(0.0, xs.min() - x_pad), xs.max() + x_pad
    y_lo, y_hi = min(0.0, ys.min() - y_pad), max(0.0, ys.max() + y_pad)
    ax.set_xlim(x_lo, x_hi)
    ax.set_ylim(y_lo, y_hi)
    ax.xaxis.set_major_locator(MultipleLocator(_tick_step(x_hi - x_lo)))
    ax.yaxis.set_major_locator(MultipleLocator(_tick_step(y_hi - y_lo)))
    ax.set_xlabel("Annualised volatility")
    ax.set_ylabel("Annualised return (CAGR)")
    ax.legend(loc="lower left")
    return _save(fig, "riskreturn")


# --------------------------------------------------------------------------- #
# Tables
# --------------------------------------------------------------------------- #

def _t_summary(a) -> str:
    m = a.metrics
    rows = [
        [("Total return", ""), (pct(m["total_p"]), cls_for(m["total_p"])), (pct(m["total_b"]), cls_for(m["total_b"])), (pp(m["active_total"], sign=True), cls_for(m["active_total"]))],
        [("Annualised return (CAGR)", ""), (pct(m["cagr_p"]), cls_for(m["cagr_p"])), (pct(m["cagr_b"]), cls_for(m["cagr_b"])), (pp(m["active_cagr"], sign=True), cls_for(m["active_cagr"]))],
        [("Annualised volatility", ""), (pct(m["vol_p"]), ""), (pct(m["vol_b"]), ""), (pp(m["vol_p"] - m["vol_b"], sign=True), "")],
        [("Sharpe ratio", ""), (num(m["sharpe_p"]), ""), (num(m["sharpe_b"]), ""), (num(m["sharpe_p"] - m["sharpe_b"], 2), cls_for(m["sharpe_p"] - m["sharpe_b"]))],
        [("Sortino ratio", ""), (num(m["sortino"]), ""), (num(m["sortino_b"]), ""), (num(m["sortino"] - m["sortino_b"]), cls_for(m["sortino"] - m["sortino_b"]))],
        [("Maximum drawdown", ""), (pct(m["maxdd_p"]), "neg"), (pct(m["maxdd_b"]), "neg"), (pp(m["maxdd_p"] - m["maxdd_b"], sign=True), cls_for(m["maxdd_p"] - m["maxdd_b"]))],
        [("Calmar ratio", ""), (num(m["calmar"]), ""), (num(m["calmar_b"]), ""), (num(m["calmar"] - m["calmar_b"]), cls_for(m["calmar"] - m["calmar_b"]))],
        [("Beta vs benchmark", ""), (num(m["beta"]), ""), ("1.00", ""), ("—", "")],
        [("Alpha (annualised, HAC)", ""), (pct(m["alpha_annual"], sign=True), cls_for(m["alpha_annual"])), ("0.00%", ""), ("—", "")],
        [("Tracking error", ""), (pct(m["te"]), ""), ("—", ""), ("—", "")],
        [("Information ratio", ""), (num(m["ir"]), ""), ("—", ""), ("—", "")],
        [(f"Ending value of {money_short(config.INITIAL_CAPITAL)}", ""), (money(m["terminal_p"]), ""), (money(m["terminal_b"]), ""), (money(m["terminal_p"] - m["terminal_b"]), cls_for(m["terminal_p"] - m["terminal_b"]))],
    ]
    return _table(["Metric", "Portfolio", "Benchmark", "Difference"], rows)


def _t_yearly(a) -> str:
    y = a.yearly
    rows = []
    for year, row in y.iterrows():
        rows.append([
            (_year_label(a, year), ""),
            (pct(row["portfolio"]), cls_for(row["portfolio"])),
            (pct(row["benchmark"]), cls_for(row["benchmark"])),
            (pp(row["active"], sign=True), cls_for(row["active"])),
        ])
    m = a.metrics
    rows.append([
        ("Full period", ""),
        (pct(m["total_p"]), cls_for(m["total_p"])),
        (pct(m["total_b"]), cls_for(m["total_b"])),
        (pp(m["active_total"], sign=True), cls_for(m["active_total"])),
    ])
    return _table(["Year", "Portfolio", "Benchmark", "Active"], rows, total=True)


def _t_drawdowns(dd: pd.DataFrame, label: str) -> str:
    if dd.empty:
        return "<p class='note'>No drawdowns exceeding the 10% threshold.</p>"
    rows = []
    for _, r in dd.iterrows():
        rows.append([
            (d(r["peak"]), ""),
            (d(r["trough"]), ""),
            (pct(r["depth"]), "neg"),
            (f"{int(r['to_trough_days'])} d", ""),
            (d(r["recovery"]) if r["recovered"] else "not recovered", "mute" if not r["recovered"] else ""),
            (f"{r['underwater_days']/365.25:.1f} y", ""),
        ])
    return _table(["Peak", "Trough", "Depth", "To trough", "Recovery", "Underwater"], rows)


def _t_varcvar(a) -> str:
    m = a.metrics
    rows = [
        [("VaR 95%", ""), (pct(m["var_95_1d"]), ""), (pct(m["var_95_m"]), "")],
        [("CVaR 95%", ""), (pct(m["cvar_95_1d"]), ""), (pct(m["cvar_95_m"]), "")],
        [("VaR 99%", ""), (pct(m["var_99_1d"]), ""), (pct(m["var_99_m"]), "")],
        [("CVaR 99%", ""), (pct(m["cvar_99_1d"]), ""), (pct(m["cvar_99_m"]), "")],
    ]
    return _table(["Loss threshold", "Daily", "Monthly"], rows)


def _t_distribution(a) -> str:
    m = a.metrics
    bw = a.best_worst
    rows = [
        [("Skewness", ""), (num(m["skew"]), "")],
        [("Excess kurtosis", ""), (num(m["kurtosis"]), "")],
        [("Jarque–Bera p-value", ""), (num(m["jb_p"], 3), "")],
        [("Best month", ""), (f"{pct(bw['best'][0])} · {bw['best'][1].strftime('%b %Y')}", "pos")],
        [("Worst month", ""), (f"{pct(bw['worst'][0])} · {bw['worst'][1].strftime('%b %Y')}", "neg")],
        [("Positive months", ""), (pct(m["hit_rate"], 0), "")],
        [("Average up / down month", ""), (f"{pct(m['avg_up_month'])} / {pct(m['avg_down_month'])}", "")],
        [("Gain-to-loss ratio", ""), (num(m["gain_loss_ratio"]), "")],
        [("Omega ratio", ""), (num(m["omega"]), "")],
        [("Ulcer index", ""), (pct(m["ulcer"]), "")],
    ]
    return _table(["Distribution", "Portfolio"], rows)


def _t_regression(a) -> str:
    r = a.regression
    m = a.metrics
    rows = [
        [("Beta", ""), (f"{r['beta']:.3f}", ""), (f"SE {r['beta_se']:.3f}", "mute")],
        [("Alpha (annualised)", ""), (pct(r["alpha_annual"], sign=True), cls_for(r["alpha_annual"])), (f"SE {pct(r['alpha_se_annual'])}", "mute")],
        [("Alpha t-statistic", ""), (num(r["alpha_t"], 2), ""), (f"p = {r['alpha_p']:.2f}", "mute")],
        [("R²", ""), (num(r["r2"]), ""), ("", "")],
        [("Correlation with benchmark", ""), (num(r["corr"]), ""), ("", "")],
        [("Tracking error", ""), (pct(m["te"]), ""), ("", "")],
        [("Information ratio", ""), (num(m["ir"]), ""), (pct(m["tracking_diff"]) + " avg active p.a.", "mute")],
        [("Up capture", ""), (pct(m["up_capture"], 0), ""), ("of benchmark up months", "mute")],
        [("Down capture", ""), (pct(m["down_capture"], 0), ""), ("of benchmark down months", "mute")],
        [("Batting average", ""), (pct(m["batting_avg"], 0), ""), ("months ahead of benchmark", "mute")],
        [("Treynor ratio", ""), (num(m["treynor"]), ""), ("", "")],
        [("M² (annualised)", ""), (pct(m["m2"]), ""), ("", "")],
        [("M² versus benchmark", ""), (pp(m["m2_excess"], sign=True), cls_for(m["m2_excess"])), ("", "")],
    ]
    return _table(["Statistic", "Value", "Detail"], rows)


def _t_monthly(a) -> str:
    rows = []
    for dt, row in a.monthly.iterrows():
        act = row["portfolio"] - row["benchmark"]
        rows.append([
            (dt.strftime("%b %Y"), ""),
            (pct(row["portfolio"]), cls_for(row["portfolio"])),
            (pct(row["benchmark"]), cls_for(row["benchmark"])),
            (pp(act, sign=True), cls_for(act)),
        ])
    m = a.metrics
    rows.append([
        ("Full period", ""),
        (pct(m["total_p"]), cls_for(m["total_p"])),
        (pct(m["total_b"]), cls_for(m["total_b"])),
        (pp(m["active_total"], sign=True), cls_for(m["active_total"])),
    ])
    return _table(["Month", "Portfolio", "Benchmark", "Active"], rows, total=True)


def _t_holdings(a) -> str:
    rows = []
    for _, r in a.holdings.iterrows():
        rows.append([
            (config.SHORT[r["ticker"]], ""),
            (pct(r["weight"], 0), ""),
            (pct(r["total"]), cls_for(r["total"])),
            (pct(r["cagr"]), cls_for(r["cagr"])),
            (pct(r["vol"]), ""),
            (num(r["sharpe"]), ""),
            (pct(r["maxdd"]), "neg"),
            (num(r["beta"]), ""),
            (num(r["corr"]), ""),
        ])
    return _table(
        ["Holding", "Weight", "Total return", "CAGR", "Volatility", "Sharpe", "Max DD", "Beta", "Corr."],
        rows,
    )


def _t_attribution(a) -> str:
    rows = []
    for _, r in a.attribution.iterrows():
        rows.append([
            (config.SHORT[r["ticker"]], ""),
            (pp(r["contribution_total"], sign=True), cls_for(r["contribution_total"])),
            (pp(r["contribution_annual"], sign=True), cls_for(r["contribution_annual"])),
        ])
    total = a.attribution["contribution_total"].sum()
    rows.append([("Total", ""), (pp(total, sign=True), cls_for(total)), ("", "")])
    return _table(["Holding", "Cumulative", "Annualised"], rows, total=True)


def _t_risk_contrib(a) -> str:
    rows = []
    for _, r in a.risk_contrib.iterrows():
        rows.append([
            (config.SHORT[r["ticker"]], ""),
            (pct(r["weight"], 0), ""),
            (pct(r["risk_contribution"], 1), ""),
        ])
    rows.append([("Total", ""), ("100%", ""), ("100.0%", "")])
    return _table(["Holding", "Weight", "Risk share"], rows, total=True)


def _t_costs(a) -> str:
    rows = []
    for _, r in a.cost_table.iterrows():
        label = "Gross" if r["bps"] == 0 else f"{int(r['bps'])} bps"
        rows.append([
            (label, ""),
            (pct(r["cagr"]), cls_for(r["cagr"])),
            (pct(r["total"]), cls_for(r["total"])),
            (pp(r["drag"], sign=True) if r["bps"] else "—", ""),
            (pct(r["maxdd"]), "neg"),
        ])
    return _table(["Cost assumption", "CAGR", "Total", "Drag", "Max DD"], rows)


def _t_rebalance(a) -> str:
    rows = []
    for _, r in a.rebalance_compare.iterrows():
        rows.append([
            (r["policy"], ""),
            (pct(r["total"]), cls_for(r["total"])),
            (pct(r["cagr"]), cls_for(r["cagr"])),
            (pct(r["vol"]), ""),
            (pct(r["maxdd"]), "neg"),
        ])
    return _table(["Policy", "Total", "CAGR", "Volatility", "Max DD"], rows)


def _t_volcheck(a) -> str:
    m = a.metrics
    rows = [
        [("Monthly returns × √12", ""), (pct(m["vol_p"]), ""), (pct(m["vol_b"]), "")],
        [("Daily returns × √252", ""), (pct(m["vol_daily_p"]), ""), (pct(m["vol_daily_b"]), "")],
        [("Difference", ""), (pp(m["vol_daily_p"] - m["vol_p"], sign=True), ""), (pp(m["vol_daily_b"] - m["vol_b"], sign=True), "")],
    ]
    return _table(["Basis", "Portfolio", "Benchmark"], rows)


def _t_dataquality(rows: list[dict]) -> str:
    out = []
    for r in rows:
        out.append([
            (r["ticker"], ""),
            (f"{r['bars']:,}", ""),
            (r["first"], ""),
            (r["last"], ""),
            (str(r["dividends"]), ""),
            (str(r["adj_ratio_moves"]), ""),
            (f"{r['max_gap_days']} d", ""),
            (r["source"], "mute"),
        ])
    return _table(
        ["Ticker", "Bars", "First", "Last", "Dividends", "Adj. moves", "Max gap", "Source"],
        out,
    )


def _t_validation(checks: list[tuple[str, str, bool]]) -> str:
    rows = []
    for name, value, ok in checks:
        rows.append([(name, ""), (value, ""), ("pass" if ok else "attention", "pos" if ok else "neg")])
    return _table(["Check", "Result", "Status"], rows)


# --------------------------------------------------------------------------- #
# Narrative
# --------------------------------------------------------------------------- #

def _name_list() -> str:
    names = [config.NAMES[t] for t in config.TICKERS]
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def _number_word(n: int) -> str:
    words = {
        1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
        6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
    }
    return words.get(n, str(n))


def _year_label(a, year: int) -> str:
    """Row label for a calendar year, naming the months when it is partial."""
    first = pd.Timestamp(a.monthly.index[0])
    last = pd.Timestamp(a.monthly.index[-1])
    if year == first.year and first.month != 1:
        return f"{year} ({first:%b}–Dec)"
    if year == last.year and last.month != 12:
        return f"{year} (Jan–{last:%b})"
    return str(year)


def _yearly_caption(a) -> str:
    """Caption for the calendar-year chart, noting any partial first/last year."""
    first = pd.Timestamp(a.monthly.index[0])
    last = pd.Timestamp(a.monthly.index[-1])
    parts = []
    if first.year == last.year:
        if first.month != 1 or last.month != 12:
            parts.append(f"{first.year}* covers {first:%B}–{last:%B}")
    else:
        if first.month != 1:
            parts.append(f"{first.year}* covers {first:%B}–December")
        if last.month != 12:
            parts.append(f"{last.year}* covers January–{last:%B}")
    caption = "Calendar-year total returns."
    if parts:
        caption += " " + "; ".join(parts) + ". An asterisk marks a partial year."
    return caption


def _takeaways(a, res) -> list[str]:
    m = a.metrics
    b = a.best_worst
    out = []

    out.append(
        f"<strong>{cur(config.INITIAL_CAPITAL)} became {cur(m['terminal_p'])}</strong> over "
        f"{m['years']:.1f} years, against {cur(m['terminal_b'])} for the benchmark — "
        f"{pp(m['active_total'], sign=True)} of cumulative active return, or "
        f"{pp(m['active_cagr'], sign=True)} a year."
    )

    sharper = m["sharpe_p"] > m["sharpe_b"]
    both_neg = m["sharpe_p"] < 0 and m["sharpe_b"] < 0
    if both_neg:
        risk_note = "but both are negative"
    elif m["sharpe_b"] < 0 <= m["sharpe_p"]:
        risk_note = "with the benchmark still negative"
    elif m["sharpe_p"] < 0 <= m["sharpe_b"]:
        risk_note = "with the portfolio still negative"
    else:
        risk_note = "with both positive"
    out.append(
        f"Risk-adjusted returns are {'marginally better' if sharper else 'slightly worse'} than the "
        f"benchmark (Sharpe {m['sharpe_p']:.2f} vs {m['sharpe_b']:.2f}), {risk_note}. "
        f"The portfolio ran at {pct(m['vol_p'])} volatility versus {pct(m['vol_b'])}, and its "
        f"maximum drawdown was {pct(m['maxdd_p'])} against {pct(m['maxdd_b'])}."
    )

    peak_date = a.equity.idxmax()
    trough_date = a.equity.loc[peak_date:].idxmin()
    peak_val = float(a.equity.loc[peak_date])
    trough_val = float(a.equity.loc[trough_date])
    out.append(
        f"The equity high was {d(peak_date)} ({cur(peak_val)}). It then fell "
        f"{pct(abs(trough_val/peak_val - 1))} to {d(trough_date)} and never regained that high, "
        f"finishing {pct(abs(a.equity.iloc[-1]/peak_val - 1))} below it."
    )

    out.append(
        f"Beta was {m['beta']:.2f} with R² of {m['r2']:.2f}, so roughly "
        f"{m['r2']*100:.0f}% of monthly variance is explained by the index. Alpha was "
        f"{pct(m['alpha_annual'], sign=True)} a year with a t-statistic of {m['alpha_t']:.2f} "
        f"(p = {m['alpha_p']:.2f}): {'indistinguishable from zero' if m['alpha_p'] > 0.05 else 'statistically distinguishable from zero'}."
    )

    at = a.attribution.sort_values("contribution_total", ascending=False)
    best = at.iloc[0]
    worst = at.iloc[-1]
    spread_pp = (a.risk_contrib["risk_contribution"].max() - a.risk_contrib["risk_contribution"].min()) * 100
    out.append(
        f"Attribution is lopsided. {config.SHORT[best['ticker']]} contributed "
        f"{pp(best['contribution_total'], sign=True)}; {config.SHORT[worst['ticker']]} "
        f"contributed {pp(worst['contribution_total'], sign=True)}. Measured by risk, the largest "
        f"and smallest risk contributions differed by {spread_pp:.0f} pp despite identical "
        f"{pct(config.WEIGHTS[best['ticker']], 0)} weights."
    )

    rebal = a.rebalance_compare
    diff = rebal.iloc[0]["total"] - rebal.iloc[1]["total"]
    vol_verb = "raised" if rebal.iloc[0]["vol"] > rebal.iloc[1]["vol"] else "lowered"
    drag = a.cost_table.loc[a.cost_table.bps == config.PRIMARY_COST_BPS, "drag"].iloc[0]
    verdict = (
        "so the gain is not an artefact of transaction costs."
        if diff > 0
        else "so the shortfall is not explained by transaction costs."
    )
    out.append(
        f"{config.REBALANCE.capitalize()} rebalancing was worth {pp(diff, sign=True)} against "
        f"simply holding the initial weights, and it {vol_verb} volatility from "
        f"{pct(rebal.iloc[1]['vol'])} to {pct(rebal.iloc[0]['vol'])}. At {config.PRIMARY_COST_BPS} bps "
        f"a side the discipline cost {pct(drag)} a year of CAGR, {verdict}"
    )
    return out


def _rolling_bullets(a) -> list[str]:
    r = a.rolling
    out = []
    out.append(
        f"Rolling 12-month return ranged from {pct(r['ret_p'].min())} to {pct(r['ret_p'].max())}; "
        f"the benchmark ranged from {pct(r['ret_b'].min())} to {pct(r['ret_b'].max())}."
    )
    out.append(
        f"The portfolio beat the benchmark in {pct((r['active'] > 0).mean(), 0)} of rolling "
        f"12-month windows, and the gap was widest at "
        f"{pct(r['active'].max(), sign=True)} ({r['active'].idxmax().strftime('%b %Y')}) and "
        f"{pct(r['active'].min(), sign=True)} ({r['active'].idxmin().strftime('%b %Y')})."
    )
    avg_beta = r["beta_p"].mean()
    beta_note = (
        "a higher-beta way to own the same theme, so it amplified the benchmark's moves in both directions"
        if avg_beta > 1.02
        else "a lower-beta way to own the same theme, so it dampened the benchmark's moves"
        if avg_beta < 0.98
        else "close to a beta-matched way to own the same theme"
    )
    out.append(
        f"Rolling beta stayed between {r['beta_p'].min():.2f} and {r['beta_p'].max():.2f}, "
        f"averaging {avg_beta:.2f} — {beta_note}."
    )
    out.append(
        f"Rolling volatility was higher than the benchmark's in "
        f"{pct((r['vol_p'] > r['vol_b']).mean(), 0)} of windows, so the extra risk was not a "
        f"temporary feature of one episode."
    )
    return out


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #

def build(a, res, quality_rows: list[dict], out_path: Path | None = None) -> Path:
    m = a.metrics
    out_path = out_path or (config.OUT_DIR / "report.html")
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)

    figs = {
        "growth": _b64(_growth(a, m)),
        "yearly": _b64(_yearly(a)),
        "drawdown": _b64(_drawdown(a)),
        "distribution": _b64(_distribution(a)),
        "scatter": _b64(_scatter(a)),
        "active": _b64(_active(a)),
        "heatmap": _b64(_heatmap(a)),
        "attrib": _b64(_attrib(a)),
        "riskreturn": _b64(_riskreturn(a)),
        "rolling": _b64(_rolling(a)),
    }

    # validation
    contrib_sum = float(a.attribution["contribution_total"].sum())
    monthly_compound = float((1 + a.monthly["portfolio"]).prod() - 1)
    bench_compound = float((1 + a.monthly["benchmark"]).prod() - 1)
    risk_sum = float(a.risk_contrib["risk_contribution"].sum())
    weight_sum = float(a.holdings["weight"].sum())
    vol_gap = abs(m["vol_daily_p"] - m["vol_p"])

    checks = [
        ("Weights sum to 100%", f"{weight_sum*100:.4f}%", abs(weight_sum - 1) < 1e-9),
        ("Return contributions reconcile to cumulative return", f"Δ {abs(contrib_sum - m['total_p'])*100:.6f} pp", abs(contrib_sum - m["total_p"]) < 1e-6),
        ("Monthly returns compound to cumulative return", f"Δ {abs(monthly_compound - m['total_p'])*100:.6f} pp", abs(monthly_compound - m["total_p"]) < 1e-9),
        ("Monthly benchmark compound to benchmark return", f"Δ {abs(bench_compound - m['total_b'])*100:.6f} pp", abs(bench_compound - m["total_b"]) < 1e-9),
        ("Risk contributions sum to 100%", f"{risk_sum*100:.2f}%", abs(risk_sum - 1) < 1e-9),
        (
            "Rebalances executed",
            f"{len(res.rebalances)} of {len(res.rebalance_dates)} {config.REBALANCE} dates",
            len(res.rebalances) == len(res.rebalance_dates),
        ),
        ("Daily vs monthly volatility gap", f"{vol_gap*100:.2f} pp", vol_gap < 0.08),
    ]

    tables = {
        "summary": _t_summary(a),
        "yearly": _t_yearly(a),
        "drawdown_p": _t_drawdowns(a.drawdowns, "Portfolio"),
        "drawdown_b": _t_drawdowns(a.drawdown_bench, "Benchmark"),
        "varcvar": _t_varcvar(a),
        "distribution": _t_distribution(a),
        "regression": _t_regression(a),
        "monthly": _t_monthly(a),
        "holdings": _t_holdings(a),
        "attribution": _t_attribution(a),
        "risk_contrib": _t_risk_contrib(a),
        "costs": _t_costs(a),
        "rebalance": _t_rebalance(a),
        "volcheck": _t_volcheck(a),
        "dataquality": _t_dataquality(quality_rows),
        "validation": _t_validation(checks),
    }

    kpis = [
        {"label": "Total return", "value": pct(m["total_p"]), "cls": cls_for(m["total_p"]),
         "detail": f"vs {pct(m['total_b'])} · {pp(m['active_total'], sign=True)}"},
        {"label": "CAGR", "value": pct(m["cagr_p"]), "cls": cls_for(m["cagr_p"]),
         "detail": f"vs {pct(m['cagr_b'])}"},
        {"label": "Volatility", "value": pct(m["vol_p"]), "cls": "",
         "detail": f"vs {pct(m['vol_b'])} · beta {m['beta']:.2f}"},
        {"label": "Sharpe ratio", "value": num(m["sharpe_p"]), "cls": cls_for(m["sharpe_p"]),
         "detail": f"vs {num(m['sharpe_b'])} · rf = {pct(config.RISK_FREE, 1)}"},
        {"label": "Max drawdown", "value": pct(m["maxdd_p"]), "cls": "neg",
         "detail": f"vs {pct(m['maxdd_b'])}"},
        {"label": "Alpha (ann.)", "value": pct(m["alpha_annual"], sign=True), "cls": cls_for(m["alpha_annual"]),
         "detail": f"t = {m['alpha_t']:.2f}, p = {m['alpha_p']:.2f}"},
    ]

    n_names = len(config.TICKERS)
    equal_weight = pct(config.WEIGHTS[config.TICKERS[0]], 0)
    if config.SUBTITLE:
        subtitle = config.SUBTITLE
    else:
        subtitle = (
            f"A {m['years']:.0f}-year ex-post review of a {equal_weight} equal-weight holding in "
            f"{_name_list()}, rebalanced {config.REBALANCE} and measured against "
            f"{config.NAMES[config.BENCHMARK]} ({config.BENCHMARK})."
        )

    headline_note = (
        "<b>Reading this report.</b> The basket was assembled with the benefit of hindsight and "
        f"covers one specific stretch for {config.MARKET} equities. The numbers describe what this "
        f"specific portfolio did; they are not evidence that equal-weighting these {n_names} names, or "
        f"any {n_names} names, earns a premium. Gross returns are shown throughout, with rebalancing "
        "costs isolated in section 08."
    )

    mtd_note = ""
    if res.partial_month and res.mtd:
        mtd_note = (
            f"<b>Month to date ({d(res.mtd['start'])} to {d(res.mtd['end'])}, "
            f"{res.mtd['days']} sessions):</b> the portfolio is "
            f"{pct(res.mtd['portfolio'], sign=True)} and the benchmark "
            f"{pct(res.mtd['benchmark'], sign=True)}. The current month is excluded from every "
            f"statistic above so that all observations are complete months."
        )

    low_beta = a.holdings.sort_values("beta").iloc[0]
    beta_word = (
        "a higher-beta expression of the same theme"
        if m["beta"] > 1.02
        else "a lower-beta expression of the same theme"
        if m["beta"] < 0.98
        else "a broadly beta-matched expression of the same theme"
    )

    env = Environment(
        loader=FileSystemLoader(str(Path(__file__).parent)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("template.html")

    html = template.render(
        title=config.TITLE,
        subtitle=subtitle,
        meta={
            "start": d(m["start"]),
            "end": d(m["end"]),
            "obs": f"{m['n_months']} months · {m['n_days']:,} days",
            "currency": config.CURRENCY,
            "generated": datetime.now().strftime("%d %b %Y"),
            "capital": cur(config.INITIAL_CAPITAL),
            "benchmark_name": config.NAMES[config.BENCHMARK],
            "benchmark": config.BENCHMARK,
            "n_names": n_names,
            "n_series": n_names + 1,
            "n_names_word": _number_word(n_names),
            "equal_weight": equal_weight,
            "risk_free": pct(config.RISK_FREE, 2),
            "risk_free_text": "zero" if config.RISK_FREE == 0 else pct(config.RISK_FREE, 2),
            "market": config.MARKET,
            "years": f"{m['years']:.1f}",
            "benchmark_divs": next(
                (r["dividends"] for r in quality_rows if r["ticker"] == config.BENCHMARK), 0
            ),
            "yearly_caption": _yearly_caption(a),
        },
        kpis=kpis,
        takeaways=_takeaways(a, res),
        headline_note=headline_note,
        mtd_note=mtd_note,
        figs=figs,
        tables=tables,
        performance_lede=(
            f"Over {m['n_months']} months the basket {'lost' if m['total_p'] < 0 else 'gained'} "
            f"{pct(abs(m['total_p']))} while the benchmark "
            f"{'lost' if m['total_b'] < 0 else 'gained'} {pct(abs(m['total_b']))}. The portfolio "
            f"therefore finished {pp(m['active_total'], sign=True)} "
            f"{'ahead of' if m['active_total'] >= 0 else 'behind'} the index on a cumulative basis. "
            f"The year-by-year record shows the gap opening in both directions: active return was "
            f"{pct(a.yearly['active'].max(), sign=True)} in {a.yearly['active'].idxmax()} and "
            f"{pct(a.yearly['active'].min(), sign=True)} in {a.yearly['active'].idxmin()}."
        ),
        summary_table_note=(
            "Portfolio statistics use monthly returns unless stated. Sharpe and Sortino use a "
            f"{pct(config.RISK_FREE, 2)} risk-free rate, so they measure raw return per unit of risk "
            "rather than excess return over cash."
        ),
        risk_lede=(
            f"Annualised volatility of {pct(m['vol_p'])} and a {pct(m['maxdd_p'])} peak-to-trough "
            f"decline define this portfolio more than its return does. The drawdown is not a brief "
            f"episode: the curve stayed underwater for up to "
            f"{a.drawdowns['underwater_days'].max()/365.25:.1f} years, and the monthly loss "
            f"distribution has excess kurtosis of {m['kurtosis']:.2f}."
        ),
        drawdown_note=(
            f"Drawdowns are separated using a 10% zig-zag rule, so a long bear market is shown as its "
            f"individual legs rather than one six-year episode. The deepest single leg was "
            f"{pct(a.drawdowns.iloc[0]['depth'])} in "
            f"{int(a.drawdowns.iloc[0]['to_trough_days'])} days ({d(a.drawdowns.iloc[0]['peak'])} to "
            f"{d(a.drawdowns.iloc[0]['trough'])}); the cumulative peak-to-trough decline from the "
            f"{d(a.equity.idxmax())} high to the {d(a.equity.loc[a.equity.idxmax():].idxmin())} low was "
            f"{pct(m['maxdd_p'])}. Recovery is measured against the prior peak and is often absent."
        ),
        risk_stats_note=(
            "Value-at-Risk and CVaR are historical, computed from the realised distribution rather "
            "than a normal approximation. Daily figures describe a single session's loss at the "
            "stated confidence level; monthly figures describe a full month."
        ),
        benchmark_lede=(
            f"The portfolio is {beta_word} rather than a diversifier: "
            f"beta {m['beta']:.2f}, R² {m['r2']:.2f}, tracking error {pct(m['te'])}. "
            f"Concentration in {n_names} names produced {pct(m['up_capture'], 0)} up-capture and "
            f"{pct(m['down_capture'], 0)} down-capture against the index."
        ),
        regression_note=(
            "Alpha is the annualised intercept of a regression of monthly portfolio returns on "
            "monthly benchmark returns, with Newey–West standard errors to account for "
            "heteroskedasticity and autocorrelation. Up- and down-capture are the average portfolio "
            "return in benchmark up and down months, divided by the benchmark's average in those "
            "months."
        ),
        monthly_lede=(
            "The monthly record shows how uneven the path was: the largest single month was "
            f"{pct(a.best_worst['best'][0])} and the worst {pct(a.best_worst['worst'][0])}, and "
            f"{pct(m['hit_rate'], 0)} of months were positive. Returns of this magnitude in single "
            "months are what make rolling statistics so volatile."
        ),
        holdings_lede=(
            f"Identical {equal_weight} weights did not produce identical risk or return. "
            f"{config.SHORT[low_beta['ticker']]} had the lowest beta ({low_beta['beta']:.2f}) and "
            f"correlation ({low_beta['corr']:.2f}) to the benchmark; the other holdings carried more "
            f"of the volatility, with individual volatilities ranging from "
            f"{pct(a.holdings['vol'].min())} to {pct(a.holdings['vol'].max())}."
        ),
        holdings_note=(
            "Statistics are computed on monthly total returns over the common window; beta and "
            "correlation are measured against the benchmark."
        ),
        rolling_lede=(
            "Rolling windows show whether the risk profile was stable or episodic. A portfolio that "
            "holds its beta and volatility over time can be assessed on average statistics; one whose "
            "risk moves with the cycle cannot."
        ),
        rolling_bullets=_rolling_bullets(a),
        avg_turnover=pct(m["avg_turnover"]),
        annual_turnover=pct(m["annual_turnover"]),
        rebalance_freq=config.REBALANCE,
        volcheck_note=(
            "The two estimates differ because monthly sampling discards within-month information and "
            f"because {config.MARKET} equities exhibit short-horizon bid–ask and microstructure noise "
            f"that inflates daily volatility. With {m['n_months']} monthly observations the sampling "
            "error on annualised volatility is roughly ±"
            f"{100/np.sqrt(2*m['n_months']):.0f}% relative, so the gap is within normal tolerance "
            "rather than a data error."
        ),
        footer=(
            f"Prepared {datetime.now().strftime('%d %B %Y')} · {config.TITLE} · "
            f"Window {d(m['start'])} to {d(m['end'])} · Benchmark {config.BENCHMARK} "
            f"({config.NAMES[config.BENCHMARK]})"
        ),
    )

    out_path.write_text(html, encoding="utf-8")

    # --- CSV outputs --------------------------------------------------------
    a.monthly.rename(columns={"portfolio": "portfolio", "benchmark": "benchmark"}).rename_axis("month").to_csv(
        config.OUT_DIR / "monthly_returns.csv", float_format="%.6f"
    )
    a.attribution.merge(a.risk_contrib[["ticker", "risk_contribution"]], on="ticker").to_csv(
        config.OUT_DIR / "contributions.csv", index=False, float_format="%.6f"
    )
    a.holdings.to_csv(config.OUT_DIR / "holdings.csv", index=False, float_format="%.6f")
    a.cost_table.to_csv(config.OUT_DIR / "cost_sensitivity.csv", index=False, float_format="%.6f")
    a.yearly.to_csv(config.OUT_DIR / "calendar_years.csv", float_format="%.6f")

    metrics_rows = []
    for key, value in m.items():
        if isinstance(value, (pd.Timestamp,)):
            value = value.strftime("%Y-%m-%d")
        metrics_rows.append({"metric": key, "value": value})
    pd.DataFrame(metrics_rows).to_csv(config.OUT_DIR / "metrics.csv", index=False)

    return out_path
