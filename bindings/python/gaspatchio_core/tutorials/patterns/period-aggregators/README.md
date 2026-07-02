# Period Aggregators

Three runnable scripts that exercise the **per-period (vector) aggregators** —
`PeriodSum`, `PeriodMean`, `PeriodCTE`, `PeriodQuantile`, `PeriodMedian` — and
double as a reference vocabulary for LLMs writing tail-risk and term-structure
jobs against this API.

A *scalar* aggregator (`Sum`, `Mean`) collapses a portfolio to one number. A
`Period*` aggregator keeps the **time axis**: it folds the portfolio at *each*
projection period and returns a **vector** — the term structure. That is the
shape an ALM / hedging desk needs (cashflow profile, tail-by-period), not a
single grand total. `Period*` aggregators are imported from
`gaspatchio_core.scenarios` and folded by `run_aggregated`.

Each script is self-contained — a small inline synthetic `pl.DataFrame` of model
points, a tiny `model_fn` that projects a monthly net-cashflow term structure,
then the pattern, then an `assert` that the aggregator output equals an
independent NumPy oracle built from the same `net_cf` matrix. The `net_cf` column
ramps with the month index, so every term structure is genuinely non-flat — a
flat vector would make the per-period assertion vacuous. A clean run is the
success signal.

| File | Pattern | Asserts |
|------|---------|---------|
| `01_period_sum_mean.py` | `Sum` (scalar) vs `PeriodSum` / `PeriodMean` (vector) via `run_aggregated` | `PeriodSum`/`PeriodMean` == NumPy `matrix.sum(axis=0)` / `mean(axis=0)` exactly; scalar `Sum` == `sum()` of the `PeriodSum` vector; term structure is non-flat |
| `02_period_tail_metrics.py` | `PeriodCTE(level=0.05, direction="upper")` (TVaR) + `PeriodQuantile(levels=(0.05, 0.95))` (VaR) | `PeriodCTE` per period == hand 10-probe-quantile CTE (within DDSketch bucket tolerance); upper-tail CTE > median; `PeriodQuantile` returns `dict{level -> ndarray}`, a known quantile at period 0 matches hand order-stat interp, q95 > q05 |
| `03_period_over_and_limits.py` | `PeriodMedian(...).over("g")` + `PeriodCTE(...).over("g")` partitioned; `PeriodQuantile(...).over("g")` guardrail | Each group's tidy `{g, period, value}` median vector == that group's NumPy median; CTE > median per group; `PeriodQuantile.over()` raises `NotImplementedError` (caught, asserted, no crash) |

## Running

```bash
uv run python \
    bindings/python/gaspatchio_core/tutorials/patterns/period-aggregators/01_period_sum_mean.py
```

Swap in `02_period_tail_metrics.py` or `03_period_over_and_limits.py`. Each
script asserts internally; a clean run with the printed reconciliation is the
success signal.

## API surface used

- `run_aggregated(model_fn, model_points, aggregations, *, batch_size=...)` — fold a portfolio to aggregates without holding it whole
- `Sum(col).alias(name)` — scalar fold across the portfolio (`AggregatedResult.<name>` → `float`); needs a **scalar** column, not a `list[f64]`
- `PeriodSum(col).alias(name)` — per-period total vector (`AggregatedResult.<name>` → `np.ndarray`)
- `PeriodMean(col).alias(name)` — per-period mean vector (`np.ndarray`)
- `PeriodMedian(col).alias(name)` — per-period median vector (DDSketch-backed)
- `PeriodCTE(col, level=..., direction="upper"|"lower").alias(name)` — per-period Conditional Tail Expectation / TVaR (`np.ndarray`); `level` is the **tail probability**
- `PeriodQuantile(col, levels=(...)).alias(name)` — per-period quantiles; un-partitioned output is `dict{level -> np.ndarray}`
- `Period*(...).alias(name).over(by)` — partition a vector fold; returns a tidy `{*by, period, alias}` `pl.DataFrame` (`PeriodMedian`, `PeriodCTE`, `PeriodSum`, … support `.over()`; `PeriodQuantile.over()` is rejected)
- `AggregatedResult` — frozen dataclass; read by attribute, never `.collect()`
- `af.projection.set(...)` / `af.projection.period_dates()` — declare the projection grid inside `model_fn`

## Conventions these scripts encode (grounded from source)

- **`PeriodCTE` `level` is a tail probability, not a confidence level.** The
  regulatory **CTE(95)** — mean of the worst 5% — is
  `PeriodCTE(level=0.05, direction="upper")` (large values = bad losses), **not**
  `PeriodCTE(level=0.95)`. `level=0.95` averages the *upper 95%* of the
  distribution (≈ the overall mean). Confirmed in
  `gaspatchio_core/scenarios/_sketch.py` `SignedSketch.cte` — it samples
  `qs = [1 - level*(i+0.5)/10 for i in range(10)]` and averages them.
- **`PeriodCTE`/`PeriodQuantile`/`PeriodMedian` are DDSketch-backed
  approximations**, not exact order statistics. The CTE is the mean of 10 probe
  quantiles; residual vs an exact hand reconstruction is bucket-discretisation
  error (~tens of bp on these ranges — see the `_sketch` module docstring). The
  asserts use a relative tolerance, never an exact-equality check on the tail.
- **`PeriodQuantile` (un-partitioned) returns `dict{level -> np.ndarray}`**, one
  per-period vector per level — see `PeriodQuantile.extract_output` in
  `_period_sketch.py`. (The running-at-scale prose describes a tidy
  `{period, level, value}` frame; the implemented un-partitioned shape is this
  dict, which is what `02` asserts against.)
- **`PeriodQuantile.over()` is rejected with `NotImplementedError`** — its
  multi-level dict has no tidy single-column form, so the driver
  (`_reject_multi_level_over` in `_aggregated.py`) raises *early*, before any
  compute. Use `PeriodMedian`/`PeriodCTE` with `.over()`, or `PeriodQuantile`
  without `.over()`.
- **Every aggregator needs `.alias(name)`** — the alias is the attribute you read
  off `AggregatedResult`.

## Provenance

These are the real regulatory risk measures the `Period*` term structures
compute:

- **CTE / TVaR** (`PeriodCTE`): Hardy, M. R. (2003), *Investment Guarantees:
  Modeling and Risk Management for Equity-Linked Life Insurance*, Wiley — §9 on
  the Conditional Tail Expectation as the coherent tail risk measure underpinning
  segregated-fund / variable-annuity capital.
- **VaR / quantiles** (`PeriodQuantile`, `PeriodMedian`): Klugman, S. A.,
  Panjer, H. H. & Willmot, G. E., *Loss Models: From Data to Decisions*, Wiley —
  Value-at-Risk and quantile risk measures.

The DDSketch-backed per-period aggregators are part of the batched
aggregate-and-stream work (repo `ref/41-backend-portability`, GSP-89/GSP-101):
mergeable, bounded-memory quantile/CTE sketches folded one batch at a time, with
the aggregate held to bucket-accuracy regardless of total portfolio scale.

## When to reach for which

- **Cashflow profile / term structure** (BEL by period, projected net CF):
  `PeriodSum`, `PeriodMean`. See `01_period_sum_mean.py`.
- **Tail capital** (CTE/TVaR reserve, VaR limit, by period): `PeriodCTE`,
  `PeriodQuantile`. See `02_period_tail_metrics.py`.
- **Reported by segment** (product line, fund, rating band): add `.over(by)` —
  but `PeriodQuantile.over()` is not supported. See `03_period_over_and_limits.py`.
