# Rollforward Patterns

Three runnable scripts that exercise the rollforward kernel and double
as a reference vocabulary for LLMs writing actuarial models against this
API.

Each script is self-contained — declare the projection grid via
`af.projection.set(...)`, declare states + ops on the builder returned by
`af.projection.rollforward(...)`, compile, collect, and assert against a
closed-form or hand-computed expectation.

| File | Pattern | Reference |
|------|---------|-----------|
| `01_single_state_fund.py` | grow → charge → floor on one state | Hardy (2003) §6.3 |
| `02_multistate_ratchet.py` | fund + GMDB ratchet via `pl.col("fund@eop")` cross-state read | Bauer/Kling/Russ (2008) |
| `03_lapse_stop.py` | withdrawal-driven termination via `lapse_when_all_non_positive` | Milevsky/Salisbury (2006) |

## Running

```bash
uv run python \
    bindings/python/gaspatchio_core/tutorials/patterns/rollforward-patterns/01_single_state_fund.py
```

Each script asserts internally; a clean run with the printed terminal
values is the success signal.

## API surface used

- `af.projection.set(start_date=..., n_periods=..., frequency=...)` — declare the projection grid on the frame
- `af.projection.rollforward(states=..., lapse_when_all_non_positive=...)` — builder for the kernel
- `b["state"].grow(rate)` — multiplicative growth
- `b["state"].charge(rate)` — proportional fee deduction
- `b["state"].subtract(expr)` — additive withdrawal
- `b["state"].ratchet(to=expr, when=mask)` — high-water-mark step-up
- `b["state"].floor(value=0.0)` — non-negativity clamp
- `pl.col("state@point")` — cross-state read at a named point
- `compile_rollforward(builder)` → `CompiledRollforward`
- `compiled.expr_for(state, point="eop")` → `pl.Expr` (all extractions share ONE kernel call on an `ActuarialFrame`)

## When to use which pattern

- **One state, mostly arithmetic:** start with `01_single_state_fund.py`.
  Most life-insurance accumulation patterns (UL account values, term
  reserves, deferred annuities pre-conversion) are this shape.
- **Two or more states with derived dependencies:** `02_multistate_ratchet.py`.
  GMxB riders, two-leg reinsurance, retro-fund mechanics — anything
  where one state's transition reads another's same-period value.
- **Projection that should terminate when a balance hits zero:**
  `03_lapse_stop.py`. GMWB withdrawal contracts, term-life lapse
  scenarios, defaulted-loan run-off.
