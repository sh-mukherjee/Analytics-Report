"""Entry point: build the ex-post portfolio analytics report.

Usage:
    python run.py              # use cached data if present
    python run.py --refresh    # re-download prices from Yahoo Finance
"""

from __future__ import annotations

import argparse
import sys

from src import config, data, metrics, portfolio, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ex-post portfolio analytics")
    parser.add_argument("--refresh", action="store_true", help="re-download data from Yahoo Finance")
    args = parser.parse_args(argv)

    print("[1/5] Loading price data")
    raw = data.load_raw(refresh=args.refresh)

    print("[2/5] Aligning series")
    panel = data.build_panel(raw)
    quality = data.validate_raw(raw, panel.start, panel.end)
    print(
        f"      common window {panel.start.date()} -> {panel.end.date()} "
        f"({len(panel.dates):,} bars, {len(panel.dropped_dates)} dropped)"
    )

    # Start at the first month-end so every observation is a complete month.
    first_month_end = data.month_end_dates(panel.dates)[0]
    panel = data.trim(panel, first_month_end)
    print(f"      inception set to first month-end: {panel.start.date()}")

    print(f"[3/5] Simulating {config.REBALANCE} rebalancing")
    daily = data.daily_returns(panel)
    result = portfolio.build(panel, daily)
    print(
        f"      {len(result.monthly)} complete months, "
        f"{len(result.rebalances)} {config.REBALANCE} rebalances"
    )
    if result.partial_month:
        print(
            f"      month-to-date {result.mtd['start'].date()} -> "
            f"{result.mtd['end'].date()}: portfolio "
            f"{result.mtd['portfolio']*100:+.2f}%, benchmark "
            f"{result.mtd['benchmark']*100:+.2f}% (excluded from statistics)"
        )

    print("[4/5] Computing analytics")
    a = metrics.compute(result)
    m = a.metrics
    print(
        f"      total {m['total_p']*100:+.2f}% vs {m['total_b']*100:+.2f}% | "
        f"CAGR {m['cagr_p']*100:+.2f}% | vol {m['vol_p']*100:.2f}% | "
        f"max DD {m['maxdd_p']*100:.2f}% | Sharpe {m['sharpe_p']:.2f}"
    )

    print("[5/5] Writing report")
    path = report.build(a, result, quality)
    print(f"      {path}")
    print(f"      {config.OUT_DIR / 'metrics.csv'}")
    print(f"      {config.CHART_DIR}")

    # quick reconciliation echo
    contrib = float(a.attribution["contribution_total"].sum())
    print(
        f"      reconciliation: contributions {contrib:.8f} vs total {m['total_p']:.8f} "
        f"(delta {abs(contrib - m['total_p']):.2e})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
