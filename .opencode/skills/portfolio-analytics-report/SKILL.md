---
name: Portfolio Analytics Report
description: Build an ex-post portfolio analytics report (self-contained HTML + CSVs) for a basket of stocks or ETFs versus a benchmark. Use when the user asks for a performance and risk review of a portfolio — total return, CAGR, volatility, Sharpe/Sortino, drawdowns, beta/alpha, tracking error, capture ratios, attribution, or "how did this basket do" — especially with monthly rebalancing, equal weights, or a specific holding period. Also use when updating or re-running an existing analytics report built with this skill.
---

# Portfolio Analytics Report

Produces a single self-contained `report.html` plus CSV outputs from daily price
history. The pipeline is:

```
Yahoo Finance daily history → cached CSVs → aligned panel → daily simulation
  → monthly returns → metrics/attribution → charts → HTML + CSV
```

Everything downstream of `src/config.py` is generic. The only file that must be
regenerated for a new portfolio is `src/config.py`, and `scripts/scaffold.py`
does that from a JSON spec.

Read these before you start:

- `references/methodology.md` — what each statistic means and how it is computed
- `references/pitfalls.md` — data and modelling traps found in practice
- `references/validation.md` — the checks a finished report must pass

## Workflow

### 1. Collect the specification

Ask for anything not already given. Do not invent a universe.

| Field | Notes |
|---|---|
| Holdings | Yahoo tickers **with exchange suffix** (`0700.HK`, `AAPL`, `VOD.L`) |
| Benchmark | One ticker, typically an index ETF tracking the same theme |
| Weights | Equal weight unless stated; must sum to 100% |
| Rebalance | `monthly` (default), `quarterly` or `weekly`; weights reset at the last trading day of the period |
| Start | Omit to let the data decide the earliest common month-end |
| Currency | Report currency. No FX conversion is performed |
| Risk-free rate | Default 0%; disclose it in the appendix |
| Costs | Default 0/5/10/25 bps per side, gross headline |

Two things to confirm explicitly, because they change the story:

1. **Is the benchmark the right share class?** 3032.HK and 3067.HK both track
   the Hang Seng Tech Index but are different issuers with different dividend
   histories. Verify the ticker's long name before use.
2. **Does the user want a fixed start date or the earliest common date?** The
   template uses the first month-end on which every series trades, so every
   monthly observation is complete. A user-specified inception that falls
   mid-month silently produces a stub month unless trimmed to month-end.

### 2. Scaffold

Write a spec (see `spec.example.json` in this skill directory) and run:

```powershell
python .opencode/skills/portfolio-analytics-report/scripts/scaffold.py `
  --spec spec.json --out C:\path\to\project
```

The scaffold copies `templates/`, regenerates the `UNIVERSE` and `ASSUMPTIONS`
blocks in `src/config.py`, and writes `spec.json` plus `README.md` into the
project. Use `--force` only when the target is a previous scaffold you intend
to replace.

If the target directory already contains user work, stop and ask before
overwriting.

### 3. Install and run

```powershell
uv sync --python 3.13
.venv\Scripts\python.exe run.py
```

`uv sync` writes progress to **stderr**; PowerShell can report exit code 1 on a
successful sync. Verify with `.venv\Scripts\python.exe -c "import pandas; print(pandas.__version__)"`
instead of trusting the exit code.

On Windows the `python` alias is sometimes a Store stub. Use `py`, `uv run`, or
the venv interpreter explicitly.

### 4. Verify the numbers before reviewing the design

`run.py` prints a reconciliation line. It must show contributions summing to the
cumulative return (delta around 1e-15). Then check the run log:

- inception is the first month-end, not the first trading day
- the rebalance count equals the number of rebalance dates after inception
  (`monthly` ≈ months − 1, `quarterly` ≈ months / 3, `weekly` ≈ weeks − 1)
- the current partial month appears as MTD and is excluded from statistics
- daily and monthly volatility are within a few percentage points

Run through `references/validation.md` before opening the HTML.

### 5. Review the report visually

Charts are embedded as base64, so the file is large and self-contained. Render
it headlessly and inspect screenshots:

```powershell
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
& $chrome --headless=new --disable-gpu --hide-scrollbars `
  --window-size=1300,16000 --screenshot="$PWD\outputs\full.png" `
  "file:///$($PWD.Path.Replace('\','/'))/outputs/report.html"
```

Slice the tall screenshot into ~1400px panels and read them. Look for:
overlapping annotations, clipped axis labels, a duplicate Q-Q title, `nan`/`None`
in text, escaped HTML in the narrative (`&lt;strong&gt;`), and tables that
overflow their column.

### 6. Deliver

Report the headline table, the two or three findings that are not obvious from
the headline, the exact output paths, and the caveats that could change the
conclusion. Do not present the report as evidence of skill: the universe was
chosen ex post.

## Quality gates

A report is not finished until all of these hold:

- [ ] `run.py` reconciliation delta < 1e-6 for contributions and risk shares
- [ ] monthly returns compound exactly to the cumulative return
- [ ] inception is a month-end; no partial month in the statistics
- [ ] rebalance count matches the configured frequency (72 monthly dates over
      six years, 24 quarterly, ~312 weekly)
- [ ] benchmark metadata (name, issuer, currency) matches the intended index
- [ ] every chart has readable labels and no collisions at 1300px wide
- [ ] no `nan`, `None`, `&lt;`, or unresolved `{{ }}` in the rendered HTML
- [ ] appendix discloses risk-free rate, cost assumptions, benchmark dividend
      treatment, and ex-post selection
- [ ] CSVs open and have the expected columns
- [ ] the narrative matches the tables after a rebuild (no stale hand-written
      numbers)

## Project layout

```
config.py      universe, assumptions, paths, palette
data.py        fetch, cache, validate, align, returns
portfolio.py   simulation, turnover, cost variants, buy-and-hold counterfactual
metrics.py     performance, risk, benchmark-relative, attribution
report.py      charts, tables, narrative, HTML/CSV output
template.html  Jinja2 template (tables and narrative use |safe)
run.py         pipeline entry point
```

## Conventions that keep the report honest

- **Gross returns are the headline.** Costs are a sensitivity table, not a
  silent deduction.
- **Adjusted close = total return.** If the vendor shows no distributions for an
  ETF, disclose that the benchmark total return may be understated.
- **Contributions must reconcile.** Link daily `w_{i,t-1} · r_{i,t}` forward at
  the cumulative growth rate; do not sum raw monthly contributions.
- **Drawdown table uses a 10% zig-zag rule.** A single peak-to-recovery episode
  swallows a multi-year bear market. Headline max drawdown stays peak-to-trough.
- **Sharpe/Sortino use arithmetic annualised excess return.** State the
  risk-free rate.
- **Alpha/beta use monthly OLS with Newey–West HAC errors.**
- **Partial months are MTD only.** Never mix a stub into annualised statistics.
- **Rebalance frequency changes the simulation.** Monthly, quarterly and weekly
  reset different weights at different dates, so totals, turnover and cost drag
  all move. Do not assume a wording-only change.
