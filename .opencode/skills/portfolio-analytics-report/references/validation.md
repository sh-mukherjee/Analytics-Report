# Validation

Run this before you show the report to anyone.

## Automated

From the project root, after `run.py`:

```powershell
.venv\Scripts\python.exe .opencode\skills\portfolio-analytics-report\scripts\check_outputs.py
```

It reads `outputs/*.csv` and checks the arithmetic and shape:

| Check | Threshold |
|---|---|
| Monthly rows equal `n_months` | exact |
| No NaN in monthly returns | exact |
| Monthly portfolio compounds to `total_p` | < 1e-5 (CSV rounded to 6 dp) |
| Monthly benchmark compounds to `total_b` | < 1e-5 |
| Return contributions reconcile to `total_p` | < 1e-5 |
| Risk contributions sum to 1 | < 1e-5 |
| Holding weights sum to 1 | < 1e-5 |
| Each calendar month appears once, in order | exact |
| Observations in the last week of the month | day ≥ 25 |
| Core metrics finite, max drawdown < 0, volatility > 0 | exact |
| Daily vs monthly volatility gap | < 10 pp |

Exit code 0 and `all N checks passed` is the bar.

## Manual, in the console

`run.py` prints its own reconciliation:

```
reconciliation: contributions -0.47074794 vs total -0.47074794 (delta 1.89e-15)
```

A delta near 1e-15 is exact. Anything above 1e-6 means contributions were summed
without linking (see `references/pitfalls.md`).

Also confirm from the log:

- `inception set to first month-end` is the date in the report header
- `N complete months` equals the number of rebalances
- the partial month is printed as MTD and says "excluded from statistics"

## Manual, in the HTML

Open `outputs/report.html` in a browser, or render headlessly:

```powershell
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
& $chrome --headless=new --disable-gpu --hide-scrollbars `
  --window-size=1300,16000 --screenshot="$PWD\outputs\full.png" `
  "file:///$($PWD.Path.Replace('\','/'))/outputs/report.html"
```

Then slice and read:

```powershell
@'
from PIL import Image
im = Image.open("outputs/full.png")
step = 1450
for i, y in enumerate(range(0, im.size[1], step)):
    im.crop((0, y, im.size[0], min(y + step, im.size[1]))).save(f"outputs/slice_{i:02d}.png")
print(im.size, i + 1)
'@ | Set-Content -Encoding utf8 slice.py
.venv\Scripts\python.exe slice.py
```

Check, in order:

1. **Header** — title, subtitle, inception, last complete month, base currency.
2. **KPI cards** — six cards on one row at 1300px; no wrapped numbers; details
   readable.
3. **Takeaways** — real `<strong>` formatting, not escaped tags; numbers match
   the KPI cards.
4. **Growth chart** — legend does not cover the lines; end labels do not
   overlap; y-axis is labelled.
5. **Summary table** — all 12+ rows; "Ending value" uses the right currency.
6. **Drawdown chart** — trough annotations legible; no label sitting on the
   axis.
7. **Q-Q plot** — exactly one title ("Normal Q-Q plot"), not a second centred
   "Probability Plot".
8. **Scatter** — square aspect, beta = 1 line visible, fit annotation readable.
9. **Heatmap** — every populated cell labelled; clipped colours still show the
   signed number.
10. **Attribution** — bars sum to the total shown in the table; risk shares sum
    to 100%.
11. **Rolling panel** — four subplots, legends only where needed, beta = 1 line
    dashed and labelled in the caption.
12. **Robustness** — cost table starts at Gross with drag "—"; rebalance table
    has the right policy names; volatility basis table labels both bases.
13. **Appendix** — data-quality table, assumptions list, reconciliation table
    all visible and consistent with the current run.
14. **Footer** — generated date, window, benchmark.

Grep for leftovers:

```powershell
Select-String -Path outputs\report.html -Pattern "nan|None|undefined|\{\{|\{%|HIBOR|four bars"
```

Base64 image lines will match incidental strings; filter to the line numbers
outside the `<img>` tags.

## Cross-checks against reality

These catch vendor errors that arithmetic checks cannot:

- **Benchmark identity.** Does `NAMES[benchmark]` match the fund you meant?
  Different issuers tracking the same index have different tickers.
- **Peer ETFs.** Compare total change over the window against another ETF on the
  same index. A 1–2 pp difference over six years is tracking difference; 10 pp is
  a data problem.
- **Known price levels.** Spot-check the first and last adjusted close against a
  public chart. Corporate actions that the vendor mis-applied show up as absurd
  levels.
- **Best/worst months.** A −24% month in a 40%-vol portfolio is plausible; a
  −60% month is usually a split or a bad adjustment.
- **Dividend count.** If an income ETF shows zero distributions, investigate
  before trusting the total return.

## Sign-off

- [ ] `check_outputs.py` passes
- [ ] `run.py` reconciliation delta < 1e-6
- [ ] no `nan`/`None`/escaped HTML in the rendered page
- [ ] benchmark ticker verified against its long name
- [ ] appendix discloses risk-free rate, costs, dividends, ex-post selection
- [ ] narrative numbers match the tables after the final rebuild
- [ ] user has been told the main caveat that could overturn the conclusion
