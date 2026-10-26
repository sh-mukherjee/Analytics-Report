#!/usr/bin/env python
"""Validate the CSV outputs of a portfolio analytics report.

Run from the project root after ``run.py``:

    .venv\\Scripts\\python.exe .opencode\\skills\\portfolio-analytics-report\\scripts\\check_outputs.py

Exit code 0 means the internal consistency gates passed. This does not judge
the investment conclusion, only the arithmetic and the shape of the outputs.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

OUT = Path("outputs")
# CSVs are rounded to 6 dp, so a 72-month compound carries ~3e-6 of rounding.
# The exact (1e-15) reconciliation is printed by run.py on the in-memory data.
TOL_COMPOUND = 1e-5
TOL_CONTRIB = 1e-5
TOL_SHARE = 1e-5


def load() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    required = ["metrics.csv", "monthly_returns.csv", "contributions.csv", "holdings.csv"]
    missing = [f for f in required if not (OUT / f).exists()]
    if missing:
        raise SystemExit(f"missing outputs in {OUT.resolve()}: {missing}")

    metrics = pd.read_csv(OUT / "metrics.csv").set_index("metric")["value"]
    monthly = pd.read_csv(OUT / "monthly_returns.csv", parse_dates=[0], index_col=0)
    contrib = pd.read_csv(OUT / "contributions.csv")
    holdings = pd.read_csv(OUT / "holdings.csv")
    return metrics, monthly, contrib, holdings


def main() -> int:
    metrics, monthly, contrib, holdings = load()
    checks: list[tuple[str, str, bool]] = []

    def add(name: str, detail: str, ok: bool) -> None:
        checks.append((name, detail, bool(ok)))

    total_p = float(metrics["total_p"])
    total_b = float(metrics["total_b"])
    n_months = int(float(metrics["n_months"]))

    # Shapes
    add("Monthly rows match n_months", f"{len(monthly)} vs {n_months}", len(monthly) == n_months)
    add(
        "Monthly returns are complete (no NaN)",
        f"{int(monthly.isna().sum().sum())} NaN",
        not monthly.isna().any().any(),
    )
    add(
        "Monthly file has portfolio and benchmark",
        ",".join(monthly.columns),
        {"portfolio", "benchmark"}.issubset(monthly.columns),
    )

    # Compounding
    comp_p = float((1 + monthly["portfolio"]).prod() - 1)
    comp_b = float((1 + monthly["benchmark"]).prod() - 1)
    add(
        "Monthly portfolio compounds to total_p",
        f"delta {abs(comp_p - total_p):.2e}",
        abs(comp_p - total_p) < TOL_COMPOUND,
    )
    add(
        "Monthly benchmark compounds to total_b",
        f"delta {abs(comp_b - total_b):.2e}",
        abs(comp_b - total_b) < TOL_COMPOUND,
    )

    # Contributions
    contrib_sum = float(contrib["contribution_total"].sum())
    add(
        "Return contributions reconcile to total_p",
        f"delta {abs(contrib_sum - total_p):.2e}",
        abs(contrib_sum - total_p) < TOL_CONTRIB,
    )
    if "risk_contribution" in contrib:
        risk_sum = float(contrib["risk_contribution"].sum())
        add("Risk contributions sum to 1", f"{risk_sum:.6f}", abs(risk_sum - 1) < TOL_SHARE)
    else:
        add("Risk contributions present", "column missing", False)

    # Weights
    weight_sum = float(holdings["weight"].sum())
    add("Holdings weights sum to 1", f"{weight_sum:.6f}", abs(weight_sum - 1) < TOL_SHARE)
    add(
        "Holdings match contribution rows",
        f"{len(holdings)} vs {len(contrib)}",
        len(holdings) == len(contrib),
    )

    # Dates
    start = pd.to_datetime(monthly.index[0])
    end = pd.to_datetime(monthly.index[-1])
    months = pd.PeriodIndex(monthly.index, freq="M")
    add(
        "Each month appears exactly once",
        f"{len(months)} months",
        months.is_unique,
    )
    add(
        "Months are strictly increasing",
        f"{months[0]} .. {months[-1]}",
        months.is_monotonic_increasing,
    )
    add(
        "Observations sit in the last week of the month",
        f"{int((monthly.index.day >= 25).sum())}/{len(monthly)}",
        bool((monthly.index.day >= 25).all()),
    )
    add("Inception precedes end", f"{start.date()} .. {end.date()}", start < end)

    # Key metrics present and finite
    for key in ("cagr_p", "vol_p", "vol_b", "sharpe_p", "maxdd_p", "beta", "te"):
        ok = key in metrics.index and math.isfinite(float(metrics[key]))
        add(f"Metric {key} finite", str(metrics.get(key, "missing")), ok)

    add(
        "Max drawdown is negative",
        f"{float(metrics['maxdd_p']):.4f}",
        float(metrics["maxdd_p"]) < 0,
    )
    add(
        "Volatility is positive",
        f"{float(metrics['vol_p']):.4f}",
        float(metrics["vol_p"]) > 0,
    )

    # Daily vs monthly volatility sanity
    daily_gap = abs(float(metrics["vol_daily_p"]) - float(metrics["vol_p"]))
    add(
        "Daily/monthly volatility within 10 pp",
        f"{daily_gap*100:.2f} pp",
        daily_gap < 0.10,
    )

    width = max(len(name) for name, _, _ in checks)
    failed = 0
    for name, detail, ok in checks:
        status = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"[{status}] {name:<{width}}  {detail}")

    print()
    if failed:
        print(f"{failed} check(s) failed")
        return 1
    print(f"all {len(checks)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
