# Step 06: Reconcile — Typed vs Untyped Parity

## What this step verifies

This step confirms that replacing raw `Table.lookup()` calls and scalar constants
with typed input primitives (`MortalityTable`, `Curve`, `Schedule`) does not change
any present-value output.

Two checks are performed:

| Check | Typed model | Untyped model |
|---|---|---|
| base | `level-3-mini-va-typed/base/model.py` | `level-3-mini-va/base/model.py` |
| 02-select-mort | `level-3-mini-va-typed/steps/02-select-mort/model.py` | `level-3-mini-va/steps/02-select-mort/model.py` |

For each check, the script compares seven PV columns across all 4 model points:

- `pv_net_cf`, `pv_claims`, `pv_premiums`, `pv_expenses`
- `pv_commissions`, `pv_inv_income`, `pv_av_change`

**Tolerance:** 1e-9 relative — set above f64 machine epsilon (~2.2e-16) to absorb
benign floating-point path differences (e.g., `exp(log(...))` vs `(1+r)^t`), while
catching any semantically meaningful divergence.

## Why step 05 (rate-curves) is not included

Step 05 (`05-rate-curves`) loads a multi-tenor yield curve from a parquet file and
interpolates discount factors — a fundamentally different curve construction from the
flat 4% constant in the untyped base. There is no corresponding untyped step that
constructs discount factors from the same yield curve, so there is no meaningful
parity comparison to make.

## Why step 07 (anniversary-aware) is not included

Step 07 applies anniversary-aware mortality — rates are updated at policy anniversary
dates rather than at fixed calendar months. This changes mortality semantics, not just
the lookup mechanism, so the outputs will differ from the untyped base by design. A
parity gate would always fail and would provide no signal.

## What it means if a check fails

A failure means the typed-input layer introduced a numerical difference that exceeds
1e-9 relative. Candidates to investigate:

- **`MortalityTable.at()` clamp behaviour**: verify `select_period` clamping in
  step 02 matches the untyped `.clip(upper_bound=SELECT_PERIOD_LEN - 1)` call.
- **`Curve.discount_factor()` precision**: verify the `(1 + r)^(-t)` path in `Curve`
  agrees with the `exp(t * log(1 + r_mth))` path in the untyped model to within
  floating-point rounding.
- **`Schedule.year_fractions()` accumulation**: verify the cumulative year-fraction
  grid matches `month / 12` at every period.

## How to run

From the repo root:

```bash
uv run python tutorial/level-3-mini-va-typed/steps/06-reconcile/reconcile.py
```

Expected output:

```
====================================================================
L3-TYPED STEP 06: Parity check — typed inputs vs untyped inputs
====================================================================

Running: typed/base  vs  untyped/base
  ...
  PASS

Running: typed/02-select-mort  vs  untyped/02-select-mort
  ...
  PASS

====================================================================
Check                                        Tolerance    Result
--------------------------------------------------------------------
typed/base  vs  untyped/base                 1e-9 rel     PASS
typed/02-select-mort  vs  untyped/02         1e-9 rel     PASS
--------------------------------------------------------------------
RESULT: ALL CHECKS PASS
====================================================================
```

Exit code is `0` on full pass, `1` if any check fails.
