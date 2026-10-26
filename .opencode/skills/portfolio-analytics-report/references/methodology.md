# Methodology

What the report computes and why. Numbers below use the reference project
(four HK tech names vs 3032.HK, Sep 2020 – Sep 2026) as an illustration only.

## 1. Data

- **Source.** Yahoo Finance chart endpoint, called directly with `requests`
  (not `yfinance`) so that adjusted close and corporate actions are read without
  a wrapper layer.
- **Cache.** Every response is written to `data/raw/<ticker>.csv` and
  `<ticker>_dividends.csv`. Re-runs are offline and reproducible.
- **Alignment.** All series are joined on common trading dates. The window is
  the intersection of valid history: start = latest first-valid date, end =
  earliest last-valid date.
- **Inception.** The pipeline then trims to the **first month-end** in that
  window. This guarantees every monthly observation is a complete month. The
  earliest common daily bar is often a few weeks before the first month-end and
  is discarded.
- **Returns.** `adjclose.pct_change()` — total return, dividends reinvested.
  First bar is the base, not a return.
- **Monthly returns.** Compounded from daily returns within each month
  (`(1+r).prod()-1`), not sampled from month-end prices. This matters when a
  month contains a large intra-month swing.

## 2. Portfolio construction

- Target weights are applied at inception and reset on the last trading day of
  each rebalance period. `config.REBALANCE` selects `monthly`, `quarterly` or
  `weekly`; the inception date itself is not a rebalance because the book is
  already at target.
- Between rebalances weights **drift**: `w_t = w_{t-1}(1+r_t)/(1+r_p,t)`.
  Reported monthly returns are therefore true buy-and-hold returns within the
  month, regardless of rebalance frequency.
- The simulation is daily, so intra-month compounding is exact.
- **Turnover** at a rebalance is one-way: `0.5 · Σ|target − drifted|`. Cost is
  `turnover × bps / 10,000`, charged to equity on the rebalance date.
- **Cost variants** at 0/5/10/25 bps per side produce parallel equity curves.
  The 0 bps curve is the headline. Drag is measured against the 0 bps curve, not
  against the raw return series.
- **Buy-and-hold counterfactual** runs the same initial weights with no
  rebalancing, for the rebalancing-versus-drift comparison.

## 3. Return statistics

| Statistic | Definition |
|---|---|
| Total return | `equity_end / equity_start − 1` |
| CAGR | `(total)^(1/years) − 1`, years = calendar days / 365.25 |
| Annualised return | `mean(monthly) × 12` (arithmetic) |
| Volatility | `std(monthly, ddof=1) × √12` |
| Sharpe | `(annualised return − rf) / volatility` |
| Sortino | `(annualised return − rf) / downside deviation` |
| Downside deviation | `√(mean(min(r − rf/12, 0)²)) × √12` |
| Calmar | `CAGR / |max drawdown|` |
| Max drawdown | minimum of `equity / cummax(equity) − 1` |

Sharpe and Sortino deliberately use the **arithmetic** annualised mean, which
is the textbook definition and matches how most vendors report. State this in
the appendix; geometric-mean variants produce different numbers.

## 4. Drawdowns

- **Headline max drawdown** is peak-to-trough on the equity curve, full stop.
- **Drawdown table** uses a **10% zig-zag rule**: a drawdown starts when the
  curve falls 10% below a running high and ends at the low before a 10% rebound
  (or at the final observation). This splits a multi-year bear market into
  readable legs. Without it, a single peak-to-recovery episode swallows the
  whole sample because the curve never regains its high.
- Recovery is measured against the prior peak and may be absent ("not
  recovered"). Underwater days run from peak to recovery, or to the end of the
  sample.

## 5. Benchmark-relative

- **Active return** = portfolio − benchmark, monthly. Cumulative active is
  compounded: `(1+r_p)/(1+r_b) − 1`.
- **Tracking error** = `std(r_p − r_b, ddof=1) × √12`.
- **Information ratio** = `mean(r_p − r_b) × 12 / TE`.
- **Beta/alpha** from monthly OLS of portfolio on benchmark, with Newey–West
  HAC standard errors. Maxlag uses the usual
  `floor(4·(n/100)^(2/9))` rule. Alpha is annualised by ×12; the t-statistic and
  p-value come from the HAC fit.
- **Treynor** = `(annualised return − rf) / beta`.
- **M²** = `rf + Sharpe_p × vol_b`; M² versus benchmark =
  `(Sharpe_p − Sharpe_b) × vol_b`.
- **Up/down capture** = mean portfolio return in benchmark up (down) months,
  divided by the benchmark's mean in those months.
- **Batting average** = share of months with `r_p > r_b`.

## 6. Tail and distribution statistics

- **Historical VaR/CVaR**, not a normal approximation. `VaR(95%)` is the 5th
  percentile loss; `CVaR` is the mean loss beyond it. Both daily and monthly.
- **Skewness, excess kurtosis, Jarque–Bera** on monthly returns.
- **Omega** = sum of gains above 0 / sum of losses below 0.
- **Ulcer index** = `√mean(drawdown²)`; **pain index** = `−mean(drawdown)`.
- **Tail ratio** = `|p95| / |p5|`.

## 7. Attribution

Return contributions must satisfy, exactly:

```
Σ_i contribution_i = cumulative portfolio return
```

The identity holds because `Σ_i w_{i,t-1} r_{i,t} = r_{p,t}` each day. To get a
cumulative contribution, multiply each daily contribution by the portfolio's
growth factor **to the start of that day**, then sum:

```
contribution_i = Σ_t [ w_{i,t-1} r_{i,t} × Π_{s<t}(1 + r_{p,s}) ]
```

Do not sum raw monthly contributions and call it cumulative: that ignores
compounding and the total will not reconcile. `run.py` prints the delta; it
should be ~1e-15.

Risk contributions use the monthly covariance matrix:

```
port_var = w' Σ w
MCTR_i   = (Σ w)_i / √port_var
RC_i     = w_i · MCTR_i / √port_var      # sums to 1
```

Equal weights do not imply equal risk contribution; state the observed spread.

## 8. Annualisation choices

- Volatility: monthly × √12 (headline). Daily × √252 is reported as a
  robustness check because the two often differ by several points. With 72
  observations the relative standard error of annualised volatility is roughly
  `1/√(2n)`, i.e. ~8%, so a 4–5 pp gap is not evidence of a bug.
- Returns: arithmetic mean × 12 for Sharpe/Sortino/Treynor; CAGR for growth
  statements. Mixing them silently is a common error.

## 9. What the report intentionally does not do

- No optimisation, no forecasting, no backtest of a rule. It is a description
  of one realised path.
- No FX conversion. If holdings and benchmark are in different currencies the
  comparison is invalid; say so.
- No taxes, spreads, market impact, lot rounding or withholding. The cost table
  covers the rebalancing component only.
