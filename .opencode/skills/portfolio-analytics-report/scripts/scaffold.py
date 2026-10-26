#!/usr/bin/env python
"""Scaffold a new ex-post portfolio analytics project from a JSON spec.

The scaffold copies the skill's ``templates/`` directory into a target folder
and regenerates the marker-delimited UNIVERSE and ASSUMPTIONS blocks of
``src/config.py``. Everything else (data layer, simulation, metrics, report) is
generic and needs no editing.

Usage
-----
    python scripts/scaffold.py --spec spec.json --out C:\\path\\to\\project
    python scripts/scaffold.py --spec spec.json --out ./my-report --force

Spec fields
-----------
    title              report title (str, required)
    subtitle           optional override; omit to auto-generate
    market             e.g. "Hong Kong" (default "Hong Kong")
    currency           ISO code, e.g. "HKD" (default "HKD")
    currency_symbol    display symbol, e.g. "HK$" (default "HK$")
    tickers            list of {ticker, name, short} (required, >= 1)
    benchmark          {ticker, name, short} (required)
    weights            optional list aligned to tickers, or {ticker: weight}
    target_weight      optional scalar, used when weights is absent
    rebalance          "monthly" | "quarterly" | "weekly" (default "monthly")
    risk_free          decimal, e.g. 0.0 (default 0.0)
    cost_bps           list of ints, per side, must include 0 (default [0,5,10,25])
    primary_cost_bps   int, must be in cost_bps (default 10)
    initial_capital    float (default 1_000_000)

Note: the engine resets weights on the last trading day of each rebalance
period, so "monthly", "quarterly" and "weekly" produce different simulations
(and different turnover, cost drag and volatility), not just different wording.
Monthly returns are still the unit of analysis in every case.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATES = SKILL_DIR / "templates"

UNIVERSE_START = "# >>> UNIVERSE"
UNIVERSE_END = "# <<< UNIVERSE"
ASSUMPTIONS_START = "# >>> ASSUMPTIONS"
ASSUMPTIONS_END = "# <<< ASSUMPTIONS"


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

def _fail(msg: str) -> None:
    raise SystemExit(f"spec error: {msg}")


def _check_ticker(obj: Any, label: str) -> dict[str, str]:
    if not isinstance(obj, dict):
        _fail(f"{label} must be an object with ticker/name/short")
    ticker = str(obj.get("ticker", "")).strip()
    if not ticker:
        _fail(f"{label}.ticker is required")
    name = str(obj.get("name") or ticker).strip()
    short = str(obj.get("short") or name).strip()
    return {"ticker": ticker, "name": name, "short": short}


def normalise(spec: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(spec, dict):
        _fail("spec must be a JSON object")

    title = str(spec.get("title", "")).strip()
    if not title:
        _fail("title is required")

    raw_tickers = spec.get("tickers")
    if not isinstance(raw_tickers, list) or not raw_tickers:
        _fail("tickers must be a non-empty list")
    tickers = [_check_ticker(t, f"tickers[{i}]") for i, t in enumerate(raw_tickers)]

    codes = [t["ticker"] for t in tickers]
    if len(set(codes)) != len(codes):
        _fail("tickers contains duplicates")

    benchmark = _check_ticker(spec.get("benchmark"), "benchmark")
    if benchmark["ticker"] in codes:
        _fail("benchmark must not also be a holding")
    if any(t["ticker"] == benchmark["ticker"] for t in tickers):
        _fail("benchmark appears in tickers")

    weights_spec = spec.get("weights")
    if weights_spec is None:
        target = float(spec.get("target_weight", 1.0 / len(tickers)))
        weights = {t["ticker"]: target for t in tickers}
    elif isinstance(weights_spec, dict):
        missing = [c for c in codes if c not in weights_spec]
        if missing:
            _fail(f"weights is missing tickers: {missing}")
        weights = {c: float(weights_spec[c]) for c in codes}
    elif isinstance(weights_spec, list):
        if len(weights_spec) != len(tickers):
            _fail("weights list must align with tickers")
        weights = {c: float(w) for c, w in zip(codes, weights_spec)}
    else:
        _fail("weights must be a list, an object, or absent")

    total = sum(weights.values())
    if not math.isclose(total, 1.0, abs_tol=1e-6):
        _fail(f"weights must sum to 1.0 (got {total:.6f})")
    if any(w <= 0 for w in weights.values()):
        _fail("weights must be strictly positive")

    cost_bps = [int(x) for x in spec.get("cost_bps", [0, 5, 10, 25])]
    if 0 not in cost_bps:
        _fail("cost_bps must include 0 (the gross baseline)")
    if cost_bps != sorted(cost_bps):
        _fail("cost_bps must be ascending")
    primary = int(spec.get("primary_cost_bps", 10))
    if primary not in cost_bps:
        _fail("primary_cost_bps must appear in cost_bps")

    rebalance = str(spec.get("rebalance", "monthly")).lower()
    if rebalance not in {"monthly", "quarterly", "weekly"}:
        _fail("rebalance must be monthly, quarterly or weekly")

    return {
        "title": title,
        "subtitle": spec.get("subtitle") or None,
        "market": str(spec.get("market", "Hong Kong")),
        "currency": str(spec.get("currency", "HKD")),
        "currency_symbol": str(spec.get("currency_symbol", "HK$")),
        "tickers": tickers,
        "benchmark": benchmark,
        "weights": weights,
        "rebalance": rebalance,
        "risk_free": float(spec.get("risk_free", 0.0)),
        "cost_bps": cost_bps,
        "primary_cost_bps": primary,
        "initial_capital": float(spec.get("initial_capital", 1_000_000)),
    }


# --------------------------------------------------------------------------- #
# Code generation
# --------------------------------------------------------------------------- #

def _py(value: Any) -> str:
    """Stable Python literal for scalars, lists and dicts."""
    return repr(value)


def universe_block(s: dict[str, Any]) -> str:
    codes = [t["ticker"] for t in s["tickers"]]
    benchmark = s["benchmark"]

    names = {t["ticker"]: t["name"] for t in s["tickers"]}
    names[benchmark["ticker"]] = benchmark["name"]
    shorts = {t["ticker"]: t["short"] for t in s["tickers"]}
    shorts[benchmark["ticker"]] = benchmark["short"]

    weights = {c: s["weights"][c] for c in codes}
    equal = len({round(w, 10) for w in weights.values()}) == 1
    target = weights[codes[0]] if equal else None

    lines = [
        UNIVERSE_START,
        f"TICKERS: list[str] = {_py(codes)}",
        f"BENCHMARK: str = {_py(benchmark['ticker'])}",
        "",
        "NAMES: dict[str, str] = {",
    ]
    for code, name in names.items():
        lines.append(f"    {_py(code)}: {_py(name)},")
    lines += ["}", "", "SHORT_NAMES: dict[str, str] = {"]
    for code, short in shorts.items():
        lines.append(f"    {_py(code)}: {_py(short)},")
    lines += ["}", ""]

    if equal:
        lines += [
            f"WEIGHT_TARGET: float = {_py(round(target, 10))}",
            f"REBALANCE: str = {_py(s['rebalance'])}",
        ]
    else:
        lines += [
            "# Custom book: WEIGHTS below is authoritative; WEIGHT_TARGET is not used.",
            "WEIGHT_TARGET: float = 0.0",
            f"REBALANCE: str = {_py(s['rebalance'])}",
        ]

    lines += [
        "",
        f"TITLE: str = {_py(s['title'])}",
        f"SUBTITLE: str | None = {_py(s['subtitle'])}",
        f"MARKET: str = {_py(s['market'])}",
        f"CURRENCY: str = {_py(s['currency'])}",
        f"CURRENCY_SYMBOL: str = {_py(s['currency_symbol'])}",
    ]

    if not equal:
        lines += ["", "# Explicit target weights (must sum to 1).", "CUSTOM_WEIGHTS: dict[str, float] = {"]
        for code in codes:
            lines.append(f"    {_py(code)}: {_py(round(weights[code], 10))},")
        lines.append("}")

    lines.append(UNIVERSE_END)
    return "\n".join(lines)


def assumptions_block(s: dict[str, Any]) -> str:
    return "\n".join(
        [
            ASSUMPTIONS_START,
            f"RISK_FREE: float = {_py(s['risk_free'])}",
            f"COST_BPS: list[int] = {_py(s['cost_bps'])}",
            f"PRIMARY_COST_BPS: int = {_py(s['primary_cost_bps'])}",
            f"INITIAL_CAPITAL: float = {_py(s['initial_capital'])}",
            ASSUMPTIONS_END,
        ]
    )


def _replace_block(text: str, start: str, end: str, block: str) -> str:
    i = text.find(start)
    j = text.find(end)
    if i == -1 or j == -1 or j < i:
        raise SystemExit(f"config template is missing the {start} ... {end} markers")
    return text[:i] + block + text[j + len(end):]


def patch_config(path: Path, s: dict[str, Any]) -> None:
    text = path.read_text(encoding="utf-8")
    text = _replace_block(text, UNIVERSE_START, UNIVERSE_END, universe_block(s))
    text = _replace_block(text, ASSUMPTIONS_START, ASSUMPTIONS_END, assumptions_block(s))

    # A custom book needs WEIGHTS to come from CUSTOM_WEIGHTS.
    marker = "WEIGHTS: dict[str, float] = {t: WEIGHT_TARGET for t in TICKERS}"
    if "CUSTOM_WEIGHTS" in text:
        text = text.replace(
            marker,
            "WEIGHTS: dict[str, float] = dict(CUSTOM_WEIGHTS)",
        )
    path.write_text(text, encoding="utf-8")


def write_readme(out: Path, s: dict[str, Any]) -> None:
    tickers = ", ".join(f"{t['ticker']} ({t['name']})" for t in s["tickers"])
    out.joinpath("README.md").write_text(
        f"""# {s['title']}

Ex-post performance and risk review generated with the `portfolio-analytics-report` skill.

- Universe: {tickers}
- Benchmark: {s['benchmark']['ticker']} ({s['benchmark']['name']})
- Rebalance: {s['rebalance']}
- Currency: {s['currency']} (no FX conversion)
- Risk-free rate: {s['risk_free']:.2%}

## Run

```powershell
uv sync --python 3.13
.venv\\Scripts\\python.exe run.py
```

Re-download prices instead of using the cache:

```powershell
.venv\\Scripts\\python.exe run.py --refresh
```

## Outputs

`outputs/report.html` is a self-contained report. `outputs/*.csv` hold every
metric, monthly return, contribution and cost table. `data/raw/` caches the
Yahoo Finance responses.

## Caveats

Prices come from Yahoo Finance. Read `references/pitfalls.md` in the skill for
the vendor quirks worth checking (empty dividend histories, adjusted-close
revisions, non-trading-day alignment). The report appendix discloses the
assumptions; review it before circulating the report.
""",
        encoding="utf-8",
    )


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def scaffold(spec_path: Path, out: Path, force: bool = False) -> Path:
    if not TEMPLATES.is_dir():
        raise SystemExit(f"templates not found at {TEMPLATES}")

    try:
        raw = json.loads(spec_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise SystemExit(f"spec not found: {spec_path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"spec is not valid JSON: {exc}")

    spec = normalise(raw)

    if out.exists() and any(out.iterdir()):
        if not force:
            raise SystemExit(f"target {out} is not empty (use --force to overwrite)")
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    for item in TEMPLATES.iterdir():
        target = out / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)

    patch_config(out / "src" / "config.py", spec)
    write_readme(out, spec)
    out.joinpath("spec.json").write_text(
        json.dumps(raw, indent=2) + "\n", encoding="utf-8"
    )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scaffold a portfolio analytics project")
    parser.add_argument("--spec", required=True, type=Path, help="JSON spec path")
    parser.add_argument("--out", required=True, type=Path, help="target project directory")
    parser.add_argument("--force", action="store_true", help="overwrite a non-empty target")
    args = parser.parse_args(argv)

    out = scaffold(args.spec, args.out, args.force)
    print(f"scaffolded -> {out.resolve()}")
    print("next:")
    print(f"  cd {out}")
    print("  uv sync --python 3.13")
    print("  .venv\\Scripts\\python.exe run.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
