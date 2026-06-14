# Level 3 (typed): Mini Variable Annuity with Typed Inputs

This level mirrors `level-3-mini-va/` but rebuilds every assumption surface using gaspatchio's three typed inputs: **`Schedule`**, **`Curve`**, and **`MortalityTable`**.

## Why a parallel level instead of a fork

`level-3-mini-va/` keeps using the lower-level `Table` + manual constants; both styles work and both ship. This typed variant exists to:

1. **Demonstrate the typed-input composition story** — `Schedule` produces year fractions, `Curve` consumes them to produce discount factors, `MortalityTable` provides convention-aware mortality lookup
2. **Provide regression coverage** — every step has an `expected_output.txt`; `06-reconcile/` asserts the typed model matches the untyped model at base + select-mort to ~1e-9 relative precision
3. **Surface real-world API gaps** discovered while building the steps (recorded in this README and in the per-step READMEs)

## What each step exercises

| Step | Typed-input feature | Parity gate |
|------|---------------------|-------------|
| `base` | `Curve.from_zero_rates` (flat 4%) + `Schedule.from_calendar_grid(OneTwelfth)` + `MortalityTable(structure="aggregate")` | matches level-3 base exactly |
| `01-from-files` | All four data inputs loaded from parquet, including `curve.parquet` | matches level-3 step 01 exactly |
| `02-select-mort` | `MortalityTable(structure="select_ultimate", select_period=24)` with sex-based `table_id` dispatch | matches level-3 step 02 exactly |
| `05-rate-curves` | Non-flat zero-rate curve + `shift_parallel(bps=100)` + `key_rate_shift(tenor=5.0, bps=50)` | feature exploration; no parity (different curve construction) |
| `06-reconcile` | Reconcile script — runs both implementations and asserts numerical agreement | the gate itself |
| `07-anniversary-aware` | `Schedule.from_inception` + `anniversary_mask_expr()` for per-policy anniversary commissions | new pedagogy; no parity |

Steps `03-guarantees` and `04-dynamic-lapse` from the original tutorial are not mirrored — they don't exercise typed inputs.

## How to run

```bash
uv run python tutorial/level-3-mini-va-typed/base/model.py
uv run python tutorial/level-3-mini-va-typed/steps/01-from-files/model.py
uv run python tutorial/level-3-mini-va-typed/steps/02-select-mort/model.py
uv run python tutorial/level-3-mini-va-typed/steps/05-rate-curves/model.py
uv run python tutorial/level-3-mini-va-typed/steps/06-reconcile/reconcile.py
uv run python tutorial/level-3-mini-va-typed/steps/07-anniversary-aware/model.py
```

## Findings worth reading the docs about

These are real surface-area gaps and ergonomic friction points discovered while building the steps. They inform what future iterations and the docs site need to address.

**Broadcasting a Python list to a Polars list-column** uses an awkward `pl.lit(pl.Series([list])).first()` idiom. Worth documenting; better idiom needed.

**`Curve.discount_factor(pl.Expr)` does not work on list-column expressions** — `map_elements` is scalar-only. Currently you must convert to a list and broadcast (per above) rather than feeding `af.projection.t_years()` directly.

**`MortalityTable.at(structure="select_ultimate", duration=...)` originally crashed on ActuarialFrame columns** because `pl.Expr.clip()` doesn't work on list dtypes and `ColumnProxy.__gt__` returns a `ConditionExpression` not a `pl.Expr`. Fixed during step 02 build; the `_to_expr()` bridge + `list_clip` plugin path is now wired in.

**`Table` dimension shorthand `{"age": "attained_age"}`** does not rename the underlying column — `Table.lookup(age=...)` then fails because the actual column is `attained_age`. Use `DataDimension(column="attained_age", rename_to="age")` instead.

**Telemetry emits a `MAP_ELEMENTS_PERFORMANCE_ISSUE` warning** every time a Schedule expression method runs. Documented as future work.

**`key_rate_shift(tenor=...)` requires an exact knot tenor** — non-knot values raise `ValueError`. Current limitation, documented.

## Prerequisites

- `level-3-mini-va/base/model.py` lines 1-55 (the original docstring) for ActuarialFrame, `.projection`, `when/then/otherwise`, `.collect()`
- `level-2-assumptions/` for the underlying `Table` mechanics that `MortalityTable` wraps

## See also

- `ref/36-rollforward-redesign/` — the design and plans behind the typed inputs
- `gaspatchio_core.schedule`, `gaspatchio_core.curves`, `gaspatchio_core.mortality` — the typed-input source modules
