# HK Technology Equal-Weight Portfolio — Ex-Post Analytics

An ex-post performance and risk review of a 25% equal-weight holding in Tencent (0700.HK),
Alibaba (9988.HK), JD.com (9618.HK) and Meituan (3690.HK), rebalanced monthly and measured
against the Hang Seng Tech Index ETF (3032.HK).

The output is a single self-contained HTML report plus machine-readable CSV files.

The repository also contains a **coding agent skill** at
`.opencode/skills/portfolio-analytics-report/` that builds the same HTML
portfolio analytics report for any basket of tickers and any benchmark.

## Quick start

```powershell
uv sync                      # create .venv and install dependencies (Python 3.13)
.venv\Scripts\python.exe run.py
```

Re-download prices instead of using the local cache:

```powershell
.venv\Scripts\python.exe run.py --refresh
```

## Outputs

| File | Contents |
|---|---|
| `outputs/report.html` | Full report: summary, performance, risk, benchmark comparison, monthly detail, attribution, rolling analytics, robustness, appendix |
| `outputs/metrics.csv` | Every scalar metric computed (tidy `metric,value` format) |
| `outputs/monthly_returns.csv` | Monthly portfolio and benchmark total returns |
| `outputs/contributions.csv` | Return and risk contribution by holding |
| `outputs/holdings.csv` | Per-stock return, volatility, beta, correlation, drawdown |
| `outputs/calendar_years.csv` | Calendar-year returns and active return |
| `outputs/cost_sensitivity.csv` | CAGR and drag at 0 / 5 / 10 / 25 bps per side |
| `outputs/charts/*.png` | Individual figures (also embedded in the HTML) |
| `data/raw/*.csv` | Cached Yahoo Finance price history and corporate actions |

## Method

- **Window.** Starts at the first month-end on which all five series trade (30 Sep 2020), so
  every monthly observation is complete. Earliest common daily bar is 2 Sep 2020, set by the
  benchmark ETF's listing date. The current, incomplete month is shown as month-to-date and
  excluded from statistics.
- **Returns.** Adjusted close (total return, dividends reinvested), HKD, no FX conversion.
- **Portfolio.** 25% per name at each month-end close; weights drift with prices between
  rebalances; monthly returns are compounded from daily returns.
- **Benchmark.** 3032.HK buy-and-hold.
- **Risk-free rate.** 0% (disclosed assumption), so Sharpe/Sortino measure raw return per unit
  of risk.
- **Costs.** Gross headline; rebalancing cost sensitivity at 5 / 10 / 25 bps per side.

## Layout

```
config.py      constants and assumptions
data.py        fetch, cache, validate, align, returns
portfolio.py   monthly-rebalanced simulation, turnover, cost variants
metrics.py     performance, risk, benchmark-relative, attribution
report.py      figures, tables, HTML/CSV output
template.html  Jinja2 report template
run.py         pipeline entry point
```

## Reconciliation

`run.py` prints a check on each run: return contributions sum to the cumulative return to
within 1e-15, monthly returns compound exactly to the cumulative return, and risk contributions
sum to 100%. The same checks appear in the report appendix.

## Coding agent skill

The **coding agent skill** lives at `.opencode/skills/portfolio-analytics-report/`.
Give it a JSON spec — holdings, benchmark, weights, rebalance frequency — and it
scaffolds, runs and validates a complete HTML portfolio analytics report. The
skill keeps the generic pipeline in `templates/`, a `scaffold.py` that
regenerates `src/config.py` from the spec, an output validator, and reference
notes on methodology, pitfalls and validation. To start a new portfolio, point
the scaffold at a spec:

```powershell
.venv\Scripts\python.exe .opencode\skills\portfolio-analytics-report\scripts\scaffold.py `
  --spec my-spec.json --out ..\my-portfolio-report
```

The spec sets the universe, benchmark, weights, rebalance frequency
(`monthly` / `quarterly` / `weekly`), risk-free rate, cost grid and initial
capital. `spec.example.json` in the skill directory reproduces this exact report.

## Caveats

The universe was chosen with hindsight, covers a single six-year regime, ignores execution
frictions beyond the rebalancing cost table, and relies on a vendor price history that records
no distributions for the benchmark ETF. See the report appendix for the full list.
