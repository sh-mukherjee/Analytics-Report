# Pitfalls

Hard-won failure modes, roughly in the order you will hit them.

## Environment

### `uv sync` reports a failure when it succeeded

`uv` writes progress to stderr. PowerShell turns stderr from a native command
into a `RemoteException` and reports exit code 1 even on success. Verify the
environment directly:

```powershell
.venv\Scripts\python.exe -c "import pandas, numpy, statsmodels; print(pandas.__version__)"
```

### The `python` alias is a Windows Store stub

`python --version` can open the Store or exit silently. Use `py -3.13`,
`uv run`, or `.venv\Scripts\python.exe`.

### pandas 3.x differences

- `pct_change()` now needs `fill_method=None` to avoid the deprecation path and
  to keep the first value as NaN instead of forward-filling.
- `DataFrame.assign(corr=...)` collides with the `DataFrame.corr` method. Do not
  use `assign` for a column named `corr`, `cov`, `mean`, `count`, `min`, `max`,
  `sum`, `var`, `std`, `skew`, `kurt`, `abs`, `mode`, `round`, `shift`, `diff`,
  `rank`, `clip`, `dot`, `T`, or `size` — access them as dict keys or rename.
- `resample("M")` is removed; use `"ME"` for month-end.

## Yahoo Finance

### Zero dividends on an ETF that does pay

Several HK ETFs return an empty `events.dividends` map even though the fund
distributes. 3032.HK and 3033.HK both show zero while 2800.HK and 3067.HK show
full histories for the same period.

This does not necessarily mean the series is wrong: the adjusted-close path can
still match peer ETFs tracking the same index (3032.HK −44.1% vs 3033.HK
−45.3% over Sep 2020 – Oct 2026). But if the fund did distribute and the vendor
did not adjust for it, the benchmark total return is **understated** and every
active-return figure is **overstated**. Disclose this; do not silently assume
the benchmark is a total-return series.

Practical check:

```python
peer_changes = {t: adj[t].iloc[-1] / adj[t].iloc[0] - 1
                for t in ["3032.HK", "3033.HK", "3067.HK"]}
```

A spread of a percentage point or two over six years is tracking difference; a
spread of ten points is a data problem.

### Wrong share class

Same index, different issuer: 3032.HK is Hang Seng Investment, 3067.HK is
iShares, 3033.HK is CSOP. Confirm `meta.longName` and use the one the user
means. Different issuers have different fee drags and distribution policies.

### Adjusted-close ratio jitter

`adjclose / close` changes only on ex-dividend or split dates. Compare the
**ratio** with a 10 bp threshold, not a 1e-6 threshold on `pct_change()` of a
rounded ratio: floating-point noise otherwise shows hundreds of spurious
"corporate actions". Also compare `adjclose / close` rather than returns, so
that ordinary price moves do not trigger it.

### Non-trading days and gaps

The Hong Kong market closes for Lunar New Year and typhoons; a 5–6 day gap is
normal. Do not forward-fill across gaps and then treat the filled days as zero
returns. Align on common dates and let the calendar be irregular.

### Listing-date mismatch

The benchmark ETF may list later than the stocks. The common window is set by
the **latest** first-valid date, which is often the ETF. Report the inception
you actually used, not the earliest stock date.

## Simulation

### `np.full(k, weight)` when weights are not equal

A scalar weight silently ignores a custom book. Carry a weight **vector**
(`config.WEIGHTS_VECTOR`) and copy it once as the rebalance target. Keep a
per-ticker dict for reporting.

### Cost drag measured against the wrong baseline

`drag = gross_cagr − net_cagr` requires the gross CAGR from the **same**
simulation engine (the 0 bps curve), not the CAGR of the return series. Mixing
the two produces a nonzero drag at 0 bps.

### Rebalance count versus rebalance dates

The loop must rebalance on every scheduled date, including the final one. If the
count is one short, the last period's weights were never reset and the final
monthly return is not comparable.

The inception date is the exception: the book starts at target, so it should not
appear in the rebalance log. Compare `len(result.rebalances)` with the number of
rebalance dates **after** inception, not with the raw date list or the month
count. At monthly frequency over six years that is 72 rebalances from 73 dates;
quarterly gives 24, weekly about 312. A "72 of 73" mismatch means inception was
counted; a mismatch of one at the end means the last date was dropped.

### Rebalance frequency assumed to be cosmetic

`monthly`, `quarterly` and `weekly` reset different weights at different dates.
Totals, turnover, cost drag, volatility and the rebalancing-versus-buy-and-hold
comparison all change. Test at least two frequencies when you touch the
simulation: a working engine should produce visibly different results, and the
report wording must follow `config.REBALANCE` rather than hard-coding "monthly".

### Partial current month

If the data ends mid-month, the last "month" is a stub. Detect it, report it as
month-to-date, and exclude it from every annualised statistic. Including it
distorts the final calendar year and the last monthly return.

### Buy-and-hold counterfactual volatility

Use the **daily** return series of the buy-and-hold curve with √252 to compare
against the rebalanced portfolio's monthly √12 figure only if you also report
the rebalanced daily figure. Otherwise label the basis; mixing bases creates a
fake difference.

## Attribution

### Contributions that do not sum to the return

Summing raw monthly contributions ignores compounding. Link each contribution
by cumulative growth to the start of the period before summing (see
`references/methodology.md` §7). Verify: the delta must be ~1e-15, not 1e-4.

### Covariance matrix built from the wrong columns

`result.monthly_stock_returns.cov()` may include the benchmark if the frame was
built from the full panel. Select `config.TICKERS` explicitly and reindex both
axes before computing marginal contributions, or the risk shares will not sum
to 1.

### Risk contributions that do not sum to 100%

`RC = w·(Σw)/port_var` sums to 1 only when `w` sums to 1 and `Σ` is aligned.
Check `Σ RC = 1` in the appendix; a value like 98.7% means a misalignment.

## Charts

### Duplicate Q-Q title

`scipy.stats.probplot` sets a centred "Probability Plot" title that survives
`ax.set_title(..., loc="left")`. Call `ax.set_title("")` after `probplot` and
then set your own title.

### Label collisions

At 1300px wide, axis-end annotations collide with each other and with the
legend. Offset in points (`xytext=(7, -9)`), set `va`/`ha`, and move the legend
to a corner where the series are not. With a concentrated book two lines can be
within a few pixels of each other at the right edge.

### Colour scale clipping

Heatmap cells outside ±30% should keep their numeric label even though the
colour is clipped; otherwise the reader cannot tell −45% from −30%.

### Y-axis in millions

`f"{v/1e6:.2f}m"` is fine for a 1m portfolio but meaningless for a 100k one.
Prefer a multiple of initial capital ("1.20×") or a currency-aware helper.

## HTML / Jinja

### Escaped HTML in the narrative

`autoescape` is on. `<strong>` in a takeaway renders literally as
`&lt;strong&gt;` unless the value is marked `|safe`. Mark the narrative and
tables `|safe`; never mark user-supplied strings.

### Stale hand-written prose

Every narrative line that quotes a number must be generated from `a.metrics`,
not typed. After a rebuild, grep the HTML for old values (e.g. a previous total
return) before delivery.

### Giant base64 images

Embedding ten PNGs at 150 dpi produces a ~1 MB HTML file. That is intended
(self-contained). Do not switch to external images unless the user asks; the
file must open offline.

## Review

### Chrome headless needs a file URL

Use `file:///C:/...` with forward slashes. `--print-to-pdf` works but the PDF is
not readable by every model; screenshots are more reliable for visual checks.

### Section anchors in headless screenshots

`--screenshot` with `#benchmark` often captures a blank viewport. For a full
review, take one tall screenshot with `--window-size=1300,16000` and slice it
locally with Pillow.
