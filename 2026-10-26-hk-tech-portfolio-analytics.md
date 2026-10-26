# Plan: Equal-Weight HK Tech Portfolio — Ex-Post Analytics Report

**Created:** 2026-10-26
**Status:** Approved, awaiting build mode
**Project:** `C:\Users\shm\Projects\Analytics-Report`

---

## 1. Objective

Produce an ex-post analytics report for a 25%-equal-weight portfolio of four HK-listed
stocks, rebalanced monthly, benchmarked against a HK tech index ETF.

### Inputs (from `Tickers.md`)

| Ticker | Name | Role |
|---|---|---|
| 0700.HK | Tencent Holdings | Holding |
| 9988.HK | Alibaba Group | Holding |
| 9618.HK | JD.com | Holding |
| 3690.HK | Meituan | Holding |
| 3032.HK | iShares Hang Seng TECH ETF | Benchmark |

---

## 2. Confirmed Decisions

| Item | Decision |
|---|---|
| Language | Python |
| Environment | `uv venv --python 3.13` + `pyproject.toml` + `uv.lock` (not `python -m venv`) |
| Window | 2020-09-02 → last complete month-end; Oct 2026 shown as MTD only |
| Prices | Adjusted close — total return, dividends reinvested |
| Currency | HKD throughout, no FX conversion |
| Portfolio | 25% each at each month-end close; drift intra-month; reset at next month-end |
| Benchmark | 3032.HK buy-and-hold, no rebalancing |
| Risk-free rate | 0%, disclosed as an explicit assumption |
| Transaction costs | Gross headline; separate sensitivity table at 5 / 10 / 25 bps per side |
| Deliverable | Self-contained `report.html` + CSV outputs |

---

## 3. Data Feasibility (verified during planning)

Yahoo Finance intraday-of-record confirmed via API before planning:

| Ticker | First bar | Last bar | Bars |
|---|---|---|---|
| 0700.HK | 2004-06-16 | 2026-10-26 | 5,523 |
| 9988.HK | 2019-11-26 | 2026-10-26 | 1,700 |
| 9618.HK | 2020-06-18 | 2026-10-26 | 1,562 |
| 3690.HK | 2018-09-20 | 2026-10-26 | 1,990 |
| 3032.HK | **2020-09-02** | 2026-10-26 | 1,510 |

**Earliest common date = 2020-09-02**, driven by the benchmark ETF, not by the stocks.
Result: ~6.15 years, ~1,440 trading days, ~74 monthly periods. All five quote in HKD.

**Open data risk:** Yahoo reports zero distributions for 3032.HK. If the ETF paid
distributions, a price-only benchmark would bias every relative metric. Must be verified
against the issuer's distribution record in Phase 1; if Yahoo is missing them, either
rebuild the benchmark as a total-return series or state the limitation prominently.

---

## 4. Environment

- Python 3.14.6 is present but the `python` alias points at the Windows Store stub;
  `py` and `uv` both work. `uv 0.11.26` installed; Python 3.13.12 already available.
- Pin to 3.13 rather than 3.14 for wheel maturity (pandas / matplotlib / statsmodels).
- Dependencies: `pandas`, `numpy`, `scipy`, `statsmodels`, `matplotlib`, `yfinance`,
  `jinja2`, `openpyxl`.
- `.gitignore`: `.venv/`, `data/`, `outputs/`, `__pycache__/`.

---

## 5. Build Order

### Phase 0 — Project + environment
`uv venv --python 3.13`, `pyproject.toml`, `uv.lock`, `.gitignore`.

### Phase 1 — Data layer (`src/data.py`)
- Fetch daily OHLC, adjusted close, dividends, splits; **cache raw to CSV** so the report
  rebuilds offline and numbers do not drift between runs.
- Validate: currency, duplicate/missing dates, non-positive prices, split consistency,
  stale prices, suspension gaps.
- Align on the **intersection** of trading days across all five; log every dropped date.
- Daily total returns from adjusted close; monthly returns from the last common trading
  day of each month.
- Exclude the partial October 2026 month from statistics; report separately as MTD.

### Phase 2 — Portfolio construction (`src/portfolio.py`)
- Equal weight at each month-end close; weights drift intra-month; full reset monthly.
- Benchmark: 3032.HK buy-and-hold.
- Two return streams: daily (drawdown, VaR, rolling risk) and monthly (performance and
  benchmark-relative tables).
- Turnover per rebalance; net-of-cost sensitivity at 5 / 10 / 25 bps per side.

### Phase 3 — Analytics (`src/metrics.py`)

**Return**
Cumulative return; annualized geometric (CAGR); growth of HK$1m; monthly and calendar-year
return tables; best/worst months; hit rate.

**Risk**
Annualized volatility (daily × √252, cross-checked against monthly × √12); downside
deviation; max drawdown plus top-5 drawdowns with depth/peak/recovery dates; underwater
curve; historical VaR/CVaR at 95/99 on daily and monthly; skewness; excess kurtosis;
Jarque-Bera.

**Risk-adjusted**
Sharpe; Sortino; Calmar; Omega; Ulcer/Pain index; tail ratio.

**Benchmark-relative**
Beta; annualized Jensen alpha with Newey-West HAC standard errors; correlation/R²;
tracking error; information ratio; active return; up/down capture; monthly batting average;
Treynor; M².

**Attribution**
Per-stock return contribution; risk contribution (marginal contribution to portfolio
variance, % of total — genuinely informative with only four names); diversification ratio.

**Rolling**
12-month rolling return, volatility, Sharpe, beta, tracking error vs benchmark; cumulative
alpha.

**Visuals**
Growth of HK$1m; drawdown/underwater; monthly heatmap; calendar-year bars; rolling charts;
risk-return scatter; monthly return scatter vs benchmark with regression line and alpha;
contribution bars; return distribution with normal overlay; QQ plot.

### Phase 4 — Deliverable (`src/report.py`)
- Single self-contained `report.html`: executive summary → data & methodology →
  performance → risk → benchmark comparison → attribution → rolling → appendix
  (assumptions, data-quality log, limitations).
- Machine-readable outputs: `metrics.csv`, `monthly_returns.csv`, `contributions.csv`,
  PNG charts under `outputs/charts/`.

### Phase 5 — Validation
- Weights sum to 1; monthly returns compound exactly to cumulative return.
- Benchmark equity curve reproduces the raw ETF price series.
- Contribution sums reconcile to portfolio return.
- Daily-vs-monthly volatility agree within tolerance.
- Two months hand-checked against raw prices.

---

## 6. Assumptions & Limitations (to appear in report appendix)

- Fixed ~6-year window (2020-09 to present); single regime spanning the 2021 tech
  crackdown, the 2022 selloff, and the 2024–25 recovery.
- Ex-post selected four-name basket: in-sample by construction, carries selection bias.
  Nothing here is evidence of a repeatable edge.
- Monthly rebalancing ignores lot sizes, bid-ask spread, and HK stamp duty.
- Yahoo is a secondary data source; ETF distribution coverage requires the Phase 1 check.
- Zero risk-free rate flatters Sharpe/Sortino relative to a HIBOR-based calculation; the
  assumption is disclosed rather than buried.

---

## 7. Final Layout

```
Analytics-Report/
├── Tickers.md
├── pyproject.toml
├── uv.lock
├── .gitignore
├── src/
│   ├── data.py
│   ├── portfolio.py
│   ├── metrics.py
│   └── report.py
├── data/            (cached raw + processed CSV)
├── outputs/
│   ├── report.html
│   ├── metrics.csv
│   ├── monthly_returns.csv
│   ├── contributions.csv
│   └── charts/
└── .venv/
```
