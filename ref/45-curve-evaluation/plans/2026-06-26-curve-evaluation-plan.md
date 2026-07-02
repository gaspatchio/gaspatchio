# Yield-Curve Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a vectorised, streaming Rust Polars kernel `curve_eval` that evaluates a yield curve over a `List<f64>` of year-fractions → `List<f64>` of annually-compounded spot rates, dispatched on a `method` tag, powering five methods (`linear`, `log_linear`, `pchip`, `svensson`, `smith_wilson`) and deleting the `map_elements` footgun in `Curve.spot_rate`/`discount_factor` (GSP-116).

**Architecture:** One Rust kernel dispatches on a `method` string in its kwargs struct; knot methods binary-search a segment and evaluate a closed form, parametric methods evaluate a closed form from stored params. All heavy setup (pchip slopes, NSS fit, SW weight-solve + α-calibration) is host-side numpy, once per curve. Python `Curve` owns representation + dispatch; eager paths evaluate in Python (parity reference), the `Expr` path calls the kernel.

**Tech Stack:** Rust (`gaspatchio_core_lib`, Polars plugins via `pyo3-polars`), Python (PyO3 bindings, numpy, Polars), maturin.

**Spec:** `gaspatchio-core/ref/45-curve-evaluation/specs/2026-06-25-curve-evaluation-design.md` (copy alongside this plan).

---

## Conventions & environment (read first)

- **Repo root:** `~/projects/gaspatchio/gaspatchio-core`. Work on `develop`. Commits: signed, conventional, **no AI/Co-Authored-By trailer**, reference `GSP-116`.
- **Rust gate (works locally):** `cd core && cargo test` and `cargo test curve_eval`. This is the primary local gate.
- **Python build after Rust changes:** `cd bindings/python && maturin build -uv` (rebuilds the `_internal` extension so Python sees the new plugin).
- **Python tests:** `cd bindings/python && uv run pytest tests/curves -v`. **Local caveat:** `uv run`/`uv sync` is currently broken on this machine (`lancedb` has no macOS-x86_64 wheel → `uv sync` fails). Python test steps below are authoritative for CI / a clean env; locally, lean on `cargo test` and run Python tests where the env resolves. Do **not** treat a local `uv` failure as a code failure — confirm in CI.
- **Units:** Curve rates are **decimals** (`0.03` = 3%). Published Fed/ECB params are in **percent** — divide by 100 in tests.
- **Compounding:** every method returns **annually-compounded** spot rates. `svensson` computes the continuously-compounded GSW value then converts `r = exp(r_cc) − 1`. `smith_wilson`/`log_linear` produce a discount factor then `r = DF^(−1/t) − 1` (already annual).
- **Reference values used in tests** (vendored facts, attributed in Task 11):
  - lifelib SW example: inputs `r=[.01,.02,.03,.032,.035,.04]`, `M=[1,2,4,5,6,7]`, `UFR=0.04`, `α=0.15` → `r(3)=0.0264236322`, `r(10)=0.0485040138`, `r(20)=0.0506997613`.
  - Fed GSW 1987-12-01 (well-separated τ): `BETA0=7.2283, BETA1=−1.6739, BETA2=−0.8650, BETA3=6.9326, TAU1=0.19719, TAU2=8.3942` (percent).

---

## File structure (decomposition)

| File | Responsibility |
|------|----------------|
| `core/src/polars_functions/curve_eval.rs` | The kernel: `CurveEvalKwargs`, `curve_eval`, per-method closed forms, inline Rust tests |
| `core/src/polars_functions/mod.rs` | Module wiring (`pub mod` / `pub use`) |
| `core/benches/curve_eval.rs` | Criterion bench over 10K×120 lists |
| `bindings/python/src/vector.rs` | PyO3 `#[polars_expr]` wrapper + output-type helper |
| `bindings/python/gaspatchio_core/polars_backend/plugins.py` | `curve_eval(...)` Python plugin wrapper (`register_plugin_function`) |
| `bindings/python/gaspatchio_core/functions/vector.py` | Re-export `curve_eval` |
| `bindings/python/gaspatchio_core/curves/_interpolation.py` | Eager parity: `log_df`, `pchip_slopes`, `hermite_eval` |
| `bindings/python/gaspatchio_core/curves/_svensson.py` | `svensson_spot`, `fit_svensson` (numpy) |
| `bindings/python/gaspatchio_core/curves/_smith_wilson.py` | Wilson heart, `solve_zeta`, `sw_spot`, `calibrate_alpha` |
| `bindings/python/gaspatchio_core/curves/_curve.py` | interpolation enum, parametric payload, constructors, Expr-path dispatch (GSP-116 fix) |
| `bindings/python/tests/curves/test_curve_eval.py` etc. | Cross-path + per-method tests |
| `bindings/python/tests/curves/REFERENCES.md` | Third-party oracle attribution |

---

## Task 1: Rust kernel scaffold + `linear` method

**Files:**
- Create: `core/src/polars_functions/curve_eval.rs`
- Modify: `core/src/polars_functions/mod.rs`

- [ ] **Step 1: Write the failing test** (inline in `curve_eval.rs`)

```rust
// core/src/polars_functions/curve_eval.rs
use polars::prelude::*;
use serde::Deserialize;

#[derive(Deserialize)]
pub struct CurveEvalKwargs {
    pub method: String,
    pub xs: Option<Vec<f64>>,
    pub ys: Option<Vec<f64>>,
    pub slopes: Option<Vec<f64>>,
    pub extrapolation: Option<String>,
    pub b0: Option<f64>, pub b1: Option<f64>, pub b2: Option<f64>,
    pub b3: Option<f64>, pub tau1: Option<f64>, pub tau2: Option<f64>,
    pub u: Option<Vec<f64>>, pub zeta: Option<Vec<f64>>,
    pub omega: Option<f64>, pub alpha: Option<f64>,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lin_kwargs(xs: Vec<f64>, ys: Vec<f64>) -> CurveEvalKwargs {
        CurveEvalKwargs {
            method: "linear".into(), xs: Some(xs), ys: Some(ys),
            slopes: None, extrapolation: Some("flat".into()),
            b0: None, b1: None, b2: None, b3: None, tau1: None, tau2: None,
            u: None, zeta: None, omega: None, alpha: None,
        }
    }

    #[test]
    fn test_linear_interp_and_flat_extrap() {
        let t = ListChunked::from_iter([Some(Series::new(
            "".into(), vec![0.5_f64, 1.0, 3.0, 5.0, 11.0],
        ))]).into_series();
        let kw = lin_kwargs(vec![1.0, 5.0, 10.0], vec![0.03, 0.03, 0.05]);
        let out = curve_eval(&[t], &kw).unwrap();
        let inner = out.list().unwrap().get_as_series(0).unwrap();
        let v = inner.f64().unwrap();
        // t=0.5 below first knot -> flat 0.03; t=1 ->0.03; t=3 ->0.03 (flat 1..5);
        // t=5 ->0.03; t=11 above last -> flat 0.05
        assert!((v.get(0).unwrap() - 0.03).abs() < 1e-12);
        assert!((v.get(2).unwrap() - 0.03).abs() < 1e-12);
        assert!((v.get(4).unwrap() - 0.05).abs() < 1e-12);
    }

    #[test]
    fn test_linear_midpoint() {
        let t = ListChunked::from_iter([Some(Series::new("".into(), vec![7.5_f64]))]).into_series();
        let kw = lin_kwargs(vec![5.0, 10.0], vec![0.04, 0.05]);
        let out = curve_eval(&[t], &kw).unwrap();
        let v = out.list().unwrap().get_as_series(0).unwrap();
        assert!((v.f64().unwrap().get(0).unwrap() - 0.045).abs() < 1e-12);
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && cargo test curve_eval`
Expected: FAIL — `curve_eval` not found / module not declared.

- [ ] **Step 3: Implement the kernel + `linear` branch** (same file, above the tests)

```rust
/// Linear interpolation of `ys` over sorted `xs` with flat extrapolation.
/// Mirrors bindings `_interpolation.linear_interpolate` exactly.
fn eval_linear(t: f64, xs: &[f64], ys: &[f64]) -> f64 {
    if t <= xs[0] { return ys[0]; }
    let n = xs.len();
    if t >= xs[n - 1] { return ys[n - 1]; }
    // bracket: first i with xs[i] > t  (xs strictly increasing, guaranteed by Curve)
    let i = xs.partition_point(|&x| x <= t); // index of first x > t
    let (x0, x1) = (xs[i - 1], xs[i]);
    let (y0, y1) = (ys[i - 1], ys[i]);
    y0 + (y1 - y0) * (t - x0) / (x1 - x0)
}

fn eval_one(t: f64, kw: &CurveEvalKwargs) -> PolarsResult<f64> {
    match kw.method.as_str() {
        "linear" => {
            let xs = kw.xs.as_ref().ok_or_else(|| polars_err!(ComputeError: "curve_eval linear: missing xs"))?;
            let ys = kw.ys.as_ref().ok_or_else(|| polars_err!(ComputeError: "curve_eval linear: missing ys"))?;
            Ok(eval_linear(t, xs, ys))
        }
        other => Err(polars_err!(ComputeError: "curve_eval: unknown method '{}'", other)),
    }
}

/// Evaluate a yield curve over a List<Float64> of year-fractions `t`.
/// Returns List<Float64> of annually-compounded spot rates, same per-row shape.
pub fn curve_eval(inputs: &[Series], kwargs: &CurveEvalKwargs) -> PolarsResult<Series> {
    let t_list = inputs[0].list()?;
    let out: ListChunked = t_list
        .amortized_iter()
        .map(|opt| match opt {
            None => Ok(None),
            Some(s) => {
                let ca = s.as_ref().f64()?;
                let vals: Vec<Option<f64>> = ca
                    .iter()
                    .map(|o| match o {
                        Some(t) => eval_one(t, kwargs).map(Some),
                        None => Ok(None),
                    })
                    .collect::<PolarsResult<Vec<_>>>()?;
                Ok(Some(Float64Chunked::from_iter(vals).into_series()))
            }
        })
        .collect::<PolarsResult<ListChunked>>()?;
    Ok(out.into_series())
}
```

Then wire the module — in `core/src/polars_functions/mod.rs` add (alongside the existing `list_pow` lines):

```rust
pub mod curve_eval;
pub use curve_eval::{curve_eval, CurveEvalKwargs};
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && cargo test curve_eval`
Expected: PASS (both tests). Also `cargo fmt && cargo clippy`.

- [ ] **Step 5: Commit**

```bash
git add core/src/polars_functions/curve_eval.rs core/src/polars_functions/mod.rs
git commit -m "feat(curves): curve_eval kernel scaffold + linear method (GSP-116)"
```

---

## Task 2: PyO3 wrapper + Python plugin glue

> **Review carry-overs (from the Task-1 double-check, 2026-06-26) — decide these while wiring Python here:**
> 1. **NaN-in-`t` contract (decide + document + parity-test).** `t` is user list-column data and is *not* gated by the constructor's knot validation. A non-finite `t` currently **panics** in the kernel (`eval_linear` usize underflow when `partition_point` returns 0); the Python reference `linear_interpolate` likewise raises. Pick a deliberate semantic — **recommended: non-finite `t` → null output** (a bad cell never silently poisons a spot rate, and never aborts a 100K run) — implement it in `eval_linear`, **mirror it in `linear_interpolate`**, and pin it with a cross-path NaN test (the §9 "one curve, one answer" guarantee must hold for NaN too). The kernel's `# Panics` note flags this as deferred-to-here.
> 2. **Non-Float64 inner dtype.** The kernel does `s.as_ref().f64()?`, so an `Int64`/`Float32` `t` list **errors** — stricter than the sibling `list_pow`, which casts. Decide deliberately: either the wrapper coerces `t` to `f64` before the plugin, or the kernel casts (like `list_pow`) and we document it. Keep `curve_eval` context in the error if kept strict.
> 3. *(Low)* `curve_eval` indexes `inputs[0]` with no arity check — an empty `inputs` slice panics. Same defensive class as the knot guard, consistent with `list_pow`; no action unless trivial.

**Files:**
- Modify: `bindings/python/src/vector.rs` (add wrapper next to `list_pow`)
- Modify: `bindings/python/gaspatchio_core/polars_backend/plugins.py`
- Modify: `bindings/python/gaspatchio_core/functions/vector.py`
- Test: `bindings/python/tests/curves/test_curve_eval.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/curves/test_curve_eval.py
import polars as pl
import pytest
from gaspatchio_core.functions.vector import curve_eval


def test_curve_eval_linear_plugin() -> None:
    df = pl.DataFrame({"t": [[0.5, 1.0, 7.5, 11.0]]})
    out = df.select(
        curve_eval(pl.col("t"), method="linear",
                   xs=[1.0, 5.0, 10.0], ys=[0.03, 0.04, 0.05]).alias("r")
    )
    r = out["r"].to_list()[0]
    assert r[0] == pytest.approx(0.03, abs=1e-12)   # flat below
    assert r[2] == pytest.approx(0.045, abs=1e-12)  # midpoint 5..10
    assert r[3] == pytest.approx(0.05, abs=1e-12)   # flat above
```

- [ ] **Step 2: Verify it fails**

Run: `cd bindings/python && uv run pytest tests/curves/test_curve_eval.py -v`
Expected: FAIL — `ImportError: cannot import name 'curve_eval'`.

- [ ] **Step 3: Implement the wrappers**

In `bindings/python/src/vector.rs` (mirror the `list_pow` wrapper; output type `List(Float64)`):

```rust
fn curve_eval_output(_: &[Field]) -> PolarsResult<Field> {
    Ok(Field::new(
        PlSmallStr::from_static("curve_eval"),
        DataType::List(Box::new(DataType::Float64)),
    ))
}

#[polars_expr(output_type_func = curve_eval_output)]
pub fn curve_eval(
    inputs: &[Series],
    kwargs: gaspatchio_core_lib::CurveEvalKwargs,
) -> PolarsResult<Series> {
    gaspatchio_core_lib::polars_functions::curve_eval::curve_eval(inputs, &kwargs)
}
```

In `bindings/python/gaspatchio_core/polars_backend/plugins.py` (mirror `list_pow`; pass kwargs dict, `is_elementwise=True`):

```python
def curve_eval(
    t: pl.Expr,
    *,
    method: str,
    xs: list[float] | None = None,
    ys: list[float] | None = None,
    slopes: list[float] | None = None,
    extrapolation: str = "flat",
    b0: float | None = None, b1: float | None = None, b2: float | None = None,
    b3: float | None = None, tau1: float | None = None, tau2: float | None = None,
    u: list[float] | None = None, zeta: list[float] | None = None,
    omega: float | None = None, alpha: float | None = None,
) -> pl.Expr:
    """Evaluate a yield curve over a list column of year-fractions.

    Returns a List[f64] of annually-compounded spot rates. Dispatch on ``method``;
    each method reads only its relevant kwargs.
    """
    return register_plugin_function(
        plugin_path=_get_lib(),
        function_name="curve_eval",
        args=[t],
        is_elementwise=True,
        kwargs={
            "method": method, "xs": xs, "ys": ys, "slopes": slopes,
            "extrapolation": extrapolation,
            "b0": b0, "b1": b1, "b2": b2, "b3": b3, "tau1": tau1, "tau2": tau2,
            "u": u, "zeta": zeta, "omega": omega, "alpha": alpha,
        },
    )
```

In `bindings/python/gaspatchio_core/functions/vector.py` add to the re-exports (single edit — import + `__all__` together):

```python
from gaspatchio_core.polars_backend.plugins import curve_eval  # noqa: F401
```
and append `"curve_eval"` to that module's `__all__`.

- [ ] **Step 4: Build + verify pass**

Run: `cd bindings/python && maturin build -uv && uv run pytest tests/curves/test_curve_eval.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/src/vector.rs bindings/python/gaspatchio_core/polars_backend/plugins.py \
        bindings/python/gaspatchio_core/functions/vector.py bindings/python/tests/curves/test_curve_eval.py
git commit -m "feat(curves): expose curve_eval plugin to Python (GSP-116)"
```

---

## Task 3: Wire `linear` into the Curve Expr path — the GSP-116 fix

**Files:**
- Modify: `bindings/python/gaspatchio_core/curves/_curve.py:175-182` (`spot_rate` Expr branch), `:246-258` (`discount_factor` Expr branch)
- Test: `bindings/python/tests/curves/test_curve_eval.py`

- [ ] **Step 1: Write the failing cross-path-equivalence test**

```python
# append to tests/curves/test_curve_eval.py
import numpy as np
from gaspatchio_core import ActuarialFrame
from gaspatchio_core.curves import Curve


def _linear_curve() -> Curve:
    return Curve.from_zero_rates(tenors=[1.0, 5.0, 10.0], rates=[0.03, 0.04, 0.05])


def test_linear_cross_path_equivalence() -> None:
    c = _linear_curve()
    ts = [0.5, 1.0, 3.0, 7.5, 11.0]
    scalar = [c.spot_rate(t) for t in ts]
    listout = c.spot_rate(ts)
    series = c.spot_rate(pl.Series("t", ts)).to_list()
    # Expr path through an ActuarialFrame list column
    af = ActuarialFrame(pl.DataFrame({"t": [ts]}))
    af.r = c.spot_rate(af["t"])
    expr_out = af.collect()["r"].to_list()[0]
    for a, b, s, e in zip(scalar, listout, series, expr_out, strict=True):
        assert a == pytest.approx(b, abs=1e-12)
        assert a == pytest.approx(s, abs=1e-12)
        assert a == pytest.approx(e, abs=1e-12)


def test_discount_factor_expr_no_map_elements() -> None:
    c = _linear_curve()
    af = ActuarialFrame(pl.DataFrame({"t": [[1.0, 2.0, 5.0]]}))
    af.df = c.discount_factor(af["t"])
    out = af.collect()["df"].to_list()[0]
    # DF = (1+r)^(-t); r(1)=0.03, r(2)=0.0325, r(5)=0.04
    assert out[0] == pytest.approx((1.03) ** -1, abs=1e-9)
    assert out[2] == pytest.approx((1.04) ** -5, abs=1e-9)
```

- [ ] **Step 2: Verify it fails**

Run: `cd bindings/python && uv run pytest tests/curves/test_curve_eval.py -k cross_path -v`
Expected: FAIL (Expr path still uses `map_elements`, or numeric mismatch / perf warning).

- [ ] **Step 3: Replace the `map_elements` Expr branches**

In `_curve.py` `spot_rate`, replace the `if isinstance(t, pl.Expr):` block (currently lines 175-182) with a dispatch to the kernel:

```python
        if isinstance(t, pl.Expr):
            from gaspatchio_core.functions.vector import curve_eval
            return curve_eval(
                t, method="linear",
                xs=list(self.tenors), ys=list(self.rates), extrapolation="flat",
            )
```

In `discount_factor`, replace the `if isinstance(t, pl.Expr):` block (lines 246-258) with: derive the rate via `curve_eval`, then `(1+r)^(-t)` via the existing `list_pow`:

```python
        if isinstance(t, pl.Expr):
            from gaspatchio_core.functions.vector import curve_eval, list_pow
            r = curve_eval(
                t, method="linear",
                xs=list(self.tenors), ys=list(self.rates), extrapolation="flat",
            )
            return list_pow(r + 1.0, t * -1.0)
```

> Tasks 4-9 generalise these two branches to dispatch on the curve's method (see Task 4 Step 3); for now they hard-wire `"linear"` so Task 3 is self-contained and GSP-116 is closed for the shipped method.

- [ ] **Step 4: Build + verify pass**

Run: `cd bindings/python && maturin build -uv && uv run pytest tests/curves/test_curve_eval.py -v`
Expected: PASS. Confirm no `map_elements` remains: `grep -n map_elements gaspatchio_core/curves/_curve.py` → no matches.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/curves/_curve.py bindings/python/tests/curves/test_curve_eval.py
git commit -m "fix(curves): vectorise spot_rate/discount_factor Expr path via curve_eval (GSP-116)"
```

---

## Task 4: `log_linear` method

**Files:**
- Modify: `bindings/python/gaspatchio_core/curves/_interpolation.py` (add `log_df_knots`)
- Modify: `core/src/polars_functions/curve_eval.rs` (add branch + tests)
- Modify: `bindings/python/gaspatchio_core/curves/_curve.py` (interpolation enum + method-dispatch helper + eager parity)
- Test: `tests/curves/test_curve_eval.py`

- [ ] **Step 1: Rust failing test + branch** (in `curve_eval.rs` tests)

```rust
    #[test]
    fn test_log_linear() {
        // ys carry log-DF: ys_i = -u_i * ln(1+r_i). Use r=3% flat -> DF, logDF.
        let xs = vec![1.0_f64, 5.0];
        let r = [0.03_f64, 0.03];
        let ys: Vec<f64> = xs.iter().zip(r).map(|(u, ri)| -u * (1.0 + ri).ln()).collect();
        let t = ListChunked::from_iter([Some(Series::new("".into(), vec![3.0_f64]))]).into_series();
        let kw = CurveEvalKwargs { method: "log_linear".into(), xs: Some(xs), ys: Some(ys),
            extrapolation: Some("flat".into()), slopes: None,
            b0:None,b1:None,b2:None,b3:None,tau1:None,tau2:None,u:None,zeta:None,omega:None,alpha:None };
        let out = curve_eval(&[t], &kw).unwrap();
        let v = out.list().unwrap().get_as_series(0).unwrap();
        // flat 3% curve -> r(3) == 0.03
        assert!((v.f64().unwrap().get(0).unwrap() - 0.03).abs() < 1e-12);
    }
```

Add to `eval_one`'s match:

```rust
        "log_linear" => {
            let xs = kw.xs.as_ref().ok_or_else(|| polars_err!(ComputeError: "curve_eval log_linear: missing xs"))?;
            let ys = kw.ys.as_ref().ok_or_else(|| polars_err!(ComputeError: "curve_eval log_linear: missing ys"))?;
            let log_df = eval_linear(t, xs, ys);   // ys are log-DF; flat-extrapolate log-DF
            let df = log_df.exp();
            Ok(df.powf(-1.0 / t) - 1.0)            // annually-compounded spot
        }
```

Run `cd core && cargo test curve_eval` → PASS.

- [ ] **Step 2: Python host-side helper + eager parity**

In `_interpolation.py` add (numpy-free, mirrors existing style):

```python
def log_df_knots(tenors: Sequence[float], rates: Sequence[float]) -> list[float]:
    """log discount factor at each knot: -u * ln(1 + r)."""
    import math
    return [-u * math.log(1.0 + r) for u, r in zip(tenors, rates, strict=True)]


def log_linear_spot(t: float, tenors: Sequence[float], log_df: Sequence[float]) -> float:
    """Spot rate at t from log-DF knots (linear in log-DF, flat extrapolation)."""
    import math
    ld = linear_interpolate(t, tenors, log_df)
    return math.exp(ld) ** (-1.0 / t) - 1.0
```

- [ ] **Step 3: Curve method-dispatch (generalise the Expr branch for all knot methods)**

In `_curve.py`: broaden the `interpolation` field/validation to accept `"linear" | "log_linear" | "pchip"`; precompute and store per-method knot `ys` (and `slopes` for pchip in Task 5) at construction. **Also add the optional field `parametric: ParametricPayload | None = None` to the frozen dataclass now** (default `None`), so the dispatch helper below is valid before Task 6 populates it (`ParametricPayload` is defined in Task 6 — for this task, type it as `object | None = None` and tighten in Task 6). Introduce one private helper used by both `spot_rate` and `discount_factor` so later tasks add a method in one place:

```python
    def _kernel_kwargs(self) -> dict[str, object]:
        """Kwargs for curve_eval matching this curve's method."""
        if self.parametric is None:  # bucket A (knot)
            if self.interpolation == "linear":
                return {"method": "linear", "xs": list(self.tenors), "ys": list(self.rates),
                        "extrapolation": "flat"}
            if self.interpolation == "log_linear":
                from gaspatchio_core.curves._interpolation import log_df_knots
                return {"method": "log_linear", "xs": list(self.tenors),
                        "ys": log_df_knots(self.tenors, self.rates), "extrapolation": "flat"}
            # pchip filled in Task 5
        # parametric filled in Tasks 6-9
        raise ValueError(f"unsupported curve method for kernel: {self.interpolation}")
```

Replace the two hard-wired `"linear"` Expr blocks from Task 3 with `curve_eval(t, **self._kernel_kwargs())` (and for `discount_factor`, `list_pow(curve_eval(t, **self._kernel_kwargs()) + 1.0, t * -1.0)`). Add the eager `log_linear` branch in the scalar/list/ndarray/Series paths via `log_linear_spot`.

- [ ] **Step 4: Python test + verify**

```python
def test_log_linear_cross_path_and_flat_curve() -> None:
    c = Curve.from_zero_rates(tenors=[1.0, 5.0, 10.0], rates=[0.03, 0.03, 0.03],
                              interpolation="log_linear")
    # flat input -> flat 3% everywhere
    assert c.spot_rate(3.0) == pytest.approx(0.03, abs=1e-12)
    af = ActuarialFrame(pl.DataFrame({"t": [[2.0, 3.0, 7.0]]}))
    af.r = c.spot_rate(af["t"])
    for v in af.collect()["r"].to_list()[0]:
        assert v == pytest.approx(0.03, abs=1e-9)
```

Run: `cd bindings/python && maturin build -uv && uv run pytest tests/curves -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add core/src/polars_functions/curve_eval.rs bindings/python/gaspatchio_core/curves/_interpolation.py \
        bindings/python/gaspatchio_core/curves/_curve.py bindings/python/tests/curves/test_curve_eval.py
git commit -m "feat(curves): add log_linear interpolation method"
```

---

## Task 5: `pchip` method (Fritsch-Carlson monotone cubic)

**Files:**
- Modify: `bindings/python/gaspatchio_core/curves/_interpolation.py` (`pchip_slopes`, `hermite_eval`)
- Modify: `core/src/polars_functions/curve_eval.rs` (pchip branch + tests)
- Modify: `bindings/python/gaspatchio_core/curves/_curve.py` (store slopes; `_kernel_kwargs` pchip; eager parity)
- Test: `tests/curves/test_curve_eval.py`

- [ ] **Step 1: Python `pchip_slopes` + `hermite_eval` with failing test**

```python
# _interpolation.py
def pchip_slopes(xs: Sequence[float], ys: Sequence[float]) -> list[float]:
    """Fritsch-Carlson monotonicity-preserving Hermite tangents."""
    n = len(xs)
    if n < 2:  # noqa: PLR2004
        return [0.0] * n
    delta = [(ys[k + 1] - ys[k]) / (xs[k + 1] - xs[k]) for k in range(n - 1)]
    m = [0.0] * n
    m[0], m[-1] = delta[0], delta[-1]
    for k in range(1, n - 1):
        if delta[k - 1] * delta[k] <= 0:   # extremum or flat -> zero slope
            m[k] = 0.0
        else:
            m[k] = (delta[k - 1] + delta[k]) / 2.0
    # Fritsch-Carlson limiter (circle rule)
    for k in range(n - 1):
        if delta[k] == 0.0:
            m[k] = 0.0
            m[k + 1] = 0.0
            continue
        a = m[k] / delta[k]
        b = m[k + 1] / delta[k]
        s = a * a + b * b
        if s > 9.0:  # noqa: PLR2004
            tau = 3.0 / (s ** 0.5)
            m[k] = tau * a * delta[k]
            m[k + 1] = tau * b * delta[k]
    return m


def hermite_eval(t: float, xs: Sequence[float], ys: Sequence[float],
                 slopes: Sequence[float]) -> float:
    """C1 cubic Hermite eval with flat extrapolation."""
    if t <= xs[0]:
        return ys[0]
    n = len(xs)
    if t >= xs[-1]:
        return ys[-1]
    from bisect import bisect_right
    k = bisect_right(xs, t) - 1
    h = xs[k + 1] - xs[k]
    s = (t - xs[k]) / h
    h00 = 2 * s**3 - 3 * s**2 + 1
    h10 = s**3 - 2 * s**2 + s
    h01 = -2 * s**3 + 3 * s**2
    h11 = s**3 - s**2
    return ys[k] * h00 + h * slopes[k] * h10 + ys[k + 1] * h01 + h * slopes[k + 1] * h11
```

```python
# test
def test_pchip_monotone_no_overshoot() -> None:
    xs = [1.0, 2.0, 3.0, 10.0, 15.0]
    ys = [0.01, 0.02, 0.025, 0.05, 0.05]   # monotone non-decreasing
    from gaspatchio_core.curves._interpolation import pchip_slopes, hermite_eval
    m = pchip_slopes(xs, ys)
    # dense sample stays within [min,max] of bracketing knots (no overshoot)
    prev = -1.0
    for i in range(0, 1400):
        t = 1.0 + i * 0.01
        v = hermite_eval(t, xs, ys, m)
        assert 0.01 - 1e-9 <= v <= 0.05 + 1e-9
        assert v >= prev - 1e-9   # monotone non-decreasing preserved
        prev = v
```

Run: `cd bindings/python && uv run pytest tests/curves/test_curve_eval.py -k pchip -v` → PASS (pure-Python helpers; no build needed).

- [ ] **Step 2: Rust pchip branch + test**

```rust
    #[test]
    fn test_pchip_matches_hermite() {
        // single segment, slopes given: linear-ish check at midpoint
        let xs = vec![1.0_f64, 2.0];
        let ys = vec![0.0_f64, 1.0];
        let slopes = vec![1.0_f64, 1.0]; // matches secant -> straight line
        let t = ListChunked::from_iter([Some(Series::new("".into(), vec![1.5_f64]))]).into_series();
        let kw = CurveEvalKwargs { method: "pchip".into(), xs: Some(xs), ys: Some(ys),
            slopes: Some(slopes), extrapolation: Some("flat".into()),
            b0:None,b1:None,b2:None,b3:None,tau1:None,tau2:None,u:None,zeta:None,omega:None,alpha:None };
        let out = curve_eval(&[t], &kw).unwrap();
        let v = out.list().unwrap().get_as_series(0).unwrap();
        assert!((v.f64().unwrap().get(0).unwrap() - 0.5).abs() < 1e-12);
    }
```

Add branch (shared Hermite eval):

```rust
fn eval_hermite(t: f64, xs: &[f64], ys: &[f64], m: &[f64]) -> f64 {
    if t <= xs[0] { return ys[0]; }
    let n = xs.len();
    if t >= xs[n - 1] { return ys[n - 1]; }
    let k = xs.partition_point(|&x| x <= t) - 1;
    let h = xs[k + 1] - xs[k];
    let s = (t - xs[k]) / h;
    let (s2, s3) = (s * s, s * s * s);
    let h00 = 2.0 * s3 - 3.0 * s2 + 1.0;
    let h10 = s3 - 2.0 * s2 + s;
    let h01 = -2.0 * s3 + 3.0 * s2;
    let h11 = s3 - s2;
    ys[k] * h00 + h * m[k] * h10 + ys[k + 1] * h01 + h * m[k + 1] * h11
}
```
```rust
        "pchip" => {
            let xs = kw.xs.as_ref().ok_or_else(|| polars_err!(ComputeError: "curve_eval pchip: missing xs"))?;
            let ys = kw.ys.as_ref().ok_or_else(|| polars_err!(ComputeError: "curve_eval pchip: missing ys"))?;
            let m = kw.slopes.as_ref().ok_or_else(|| polars_err!(ComputeError: "curve_eval pchip: missing slopes"))?;
            Ok(eval_hermite(t, xs, ys, m))
        }
```

Run `cd core && cargo test curve_eval` → PASS.

- [ ] **Step 3: Curve wiring** — store `slopes = pchip_slopes(tenors, rates)` at construction when `interpolation=="pchip"`; `_kernel_kwargs` returns `{"method":"pchip","xs":...,"ys":list(rates),"slopes":...}`; eager paths call `hermite_eval`.

- [ ] **Step 4: Build + Python cross-path test**

```python
def test_pchip_cross_path() -> None:
    c = Curve.from_zero_rates(tenors=[1.0, 2.0, 5.0, 10.0],
                              rates=[0.01, 0.02, 0.03, 0.035], interpolation="pchip")
    ts = [1.0, 1.5, 3.0, 7.0, 12.0]
    af = ActuarialFrame(pl.DataFrame({"t": [ts]}))
    af.r = c.spot_rate(af["t"])
    expr_out = af.collect()["r"].to_list()[0]
    for t, e in zip(ts, expr_out, strict=True):
        assert c.spot_rate(t) == pytest.approx(e, abs=1e-12)
```

Run: `cd bindings/python && maturin build -uv && uv run pytest tests/curves -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add core/src/polars_functions/curve_eval.rs bindings/python/gaspatchio_core/curves/_interpolation.py \
        bindings/python/gaspatchio_core/curves/_curve.py bindings/python/tests/curves/test_curve_eval.py
git commit -m "feat(curves): add pchip (Fritsch-Carlson monotone cubic) method"
```

---

## Task 6: `svensson` evaluation (NSS closed form)

**Files:**
- Create: `bindings/python/gaspatchio_core/curves/_svensson.py`
- Modify: `core/src/polars_functions/curve_eval.rs` (svensson branch + tests)
- Modify: `bindings/python/gaspatchio_core/curves/_curve.py` (`from_svensson`, parametric payload, dispatch, eager parity)
- Test: `tests/curves/test_svensson.py` (create)

- [ ] **Step 1: Python `svensson_spot` (cc) + failing test against Fed GSW**

```python
# _svensson.py
from __future__ import annotations
import math

_EPS = 1e-8

def svensson_spot_cc(t: float, b0: float, b1: float, b2: float, b3: float,
                     tau1: float, tau2: float) -> float:
    """Continuously-compounded NSS spot rate (GSW eq. 22). t>=0."""
    def loadings(x: float) -> tuple[float, float]:
        if x < _EPS:
            return 1.0, 0.0  # limits: (1-e^-x)/x -> 1 ; ((1-e^-x)/x - e^-x) -> 0
        e = math.exp(-x)
        l = (1.0 - e) / x
        return l, l - e
    l1, c1 = loadings(t / tau1)
    _, c2 = loadings(t / tau2)
    return b0 + b1 * l1 + b2 * c1 + b3 * c2

def svensson_spot(t: float, b0: float, b1: float, b2: float, b3: float,
                  tau1: float, tau2: float) -> float:
    """Annually-compounded NSS spot rate."""
    return math.exp(svensson_spot_cc(t, b0, b1, b2, b3, tau1, tau2)) - 1.0
```

```python
# tests/curves/test_svensson.py
import math
import pytest
from gaspatchio_core.curves._svensson import svensson_spot_cc

# Fed GSW 1987-12-01 params (percent), well-separated taus
GSW = dict(b0=7.2283, b1=-1.6739, b2=-0.8650, b3=6.9326, tau1=0.19719, tau2=8.3942)

def test_svensson_cc_matches_self_consistent() -> None:
    # sanity: t->0 limit gives b0+b1; long t -> b0
    assert svensson_spot_cc(1e-9, **GSW) == pytest.approx(GSW["b0"] + GSW["b1"], abs=1e-6)
    assert svensson_spot_cc(1e6, **GSW) == pytest.approx(GSW["b0"], abs=1e-6)
```

> Oracle note: a stronger test (Task 11 / optional) evaluates `svensson_spot_cc` at the GSW params for t=1,2,5,10,20,30 and asserts agreement with that date's published `SVENYxx` (percent) to ≤1e-3. Vendored values + attribution land in `REFERENCES.md`.

Run: `cd bindings/python && uv run pytest tests/curves/test_svensson.py -v` → PASS.

- [ ] **Step 2: Rust svensson branch + test**

```rust
    #[test]
    fn test_svensson_limits() {
        let kw = CurveEvalKwargs { method: "svensson".into(),
            b0: Some(0.04), b1: Some(-0.01), b2: Some(0.0), b3: Some(0.0),
            tau1: Some(1.5), tau2: Some(10.0),
            xs:None, ys:None, slopes:None, extrapolation:None, u:None, zeta:None, omega:None, alpha:None };
        // t->0 (annual): exp(b0+b1)-1 ; here b2=b3=0 so spot_cc(small)=b0+b1=0.03
        let t = ListChunked::from_iter([Some(Series::new("".into(), vec![1e-9_f64]))]).into_series();
        let v = curve_eval(&[t], &kw).unwrap().list().unwrap().get_as_series(0).unwrap();
        let got = v.f64().unwrap().get(0).unwrap();
        assert!((got - ((0.03_f64).exp() - 1.0)).abs() < 1e-6);
    }
```

Add branch (closed form, cc→annual; mirror Python `_EPS`):

```rust
fn svensson_load(x: f64) -> (f64, f64) {
    if x < 1e-8 { return (1.0, 0.0); }
    let e = (-x).exp();
    let l = (1.0 - e) / x;
    (l, l - e)
}
```
```rust
        "svensson" => {
            let (b0,b1,b2,b3) = (kw.b0.unwrap(), kw.b1.unwrap(), kw.b2.unwrap(), kw.b3.unwrap());
            let (t1,t2) = (kw.tau1.unwrap(), kw.tau2.unwrap());
            let (l1, c1) = svensson_load(t / t1);
            let (_, c2) = svensson_load(t / t2);
            let cc = b0 + b1 * l1 + b2 * c1 + b3 * c2;
            Ok(cc.exp() - 1.0)
        }
```
(Use the `xs/ys` `ok_or_else` pattern for missing svensson fields too — replace `.unwrap()` with explicit `polars_err!` to honour the "no unwrap in production" rule.)

Run `cd core && cargo test curve_eval` → PASS.

- [ ] **Step 3: `Curve.from_svensson` + parametric payload + dispatch**

Define `ParametricPayload` (frozen dataclass: `kind: Literal["svensson","smith_wilson"]` + the params dict/fields) and tighten the `parametric` field's type (added in Task 4). Add constructor `from_svensson(*, b0,b1,b2,b3,tau1,tau2, day_count=None)` storing decimal params. Extend `_kernel_kwargs` for `parametric.kind == "svensson"` → `{"method":"svensson", b0..tau2}`. Eager paths call `svensson_spot`. Validate `tau1>0, tau2>0`; warn (not raise) if `b0<=0` or `b0+b1<=0`. **Extend `canonical_form()`** to include `parametric` (kind + params) when present, so `source_sha()` distinguishes parametric curves; knot curves (no `parametric`) keep their existing canonical form → **existing linear-curve shas unchanged.**

- [ ] **Step 4: Build + cross-path test**

```python
def test_svensson_cross_path() -> None:
    from gaspatchio_core.curves import Curve
    from gaspatchio_core import ActuarialFrame
    import polars as pl
    # decimal params
    c = Curve.from_svensson(b0=0.04, b1=-0.01, b2=0.005, b3=0.002, tau1=1.5, tau2=10.0)
    ts = [0.5, 1.0, 5.0, 10.0, 30.0]
    af = ActuarialFrame(pl.DataFrame({"t": [ts]}))
    af.r = c.spot_rate(af["t"])
    expr_out = af.collect()["r"].to_list()[0]
    for t, e in zip(ts, expr_out, strict=True):
        assert c.spot_rate(t) == pytest.approx(e, abs=1e-12)
```

Run: `cd bindings/python && maturin build -uv && uv run pytest tests/curves -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add core/src/polars_functions/curve_eval.rs bindings/python/gaspatchio_core/curves/_svensson.py \
        bindings/python/gaspatchio_core/curves/_curve.py bindings/python/tests/curves/test_svensson.py
git commit -m "feat(curves): add svensson (NSS) closed-form evaluation"
```

---

## Task 7: `svensson` fitting (numpy separable-NLS)

**Files:**
- Modify: `bindings/python/gaspatchio_core/curves/_svensson.py` (`fit_svensson`)
- Modify: `bindings/python/gaspatchio_core/curves/_curve.py` (`fit_svensson` constructor)
- Test: `tests/curves/test_svensson.py`

- [ ] **Step 1: Failing curve-value-recovery test** (NOT parameter recovery)

```python
import numpy as np
from gaspatchio_core.curves._svensson import svensson_spot_cc, fit_svensson

def test_fit_recovers_curve_values_not_params() -> None:
    # well-separated taus -> generate synthetic cc rates, fit, check CURVE values
    true = dict(b0=0.045, b1=-0.02, b2=0.01, b3=0.008, tau1=0.5, tau2=7.0)
    tenors = [0.5, 1, 2, 3, 5, 7, 10, 20, 30]
    rates = [svensson_spot_cc(t, **true) for t in tenors]   # cc rates as observations
    fit = fit_svensson(tenors, rates)
    for t in [0.75, 4.0, 15.0, 25.0]:
        got = svensson_spot_cc(t, **fit)
        want = svensson_spot_cc(t, **true)
        assert got == pytest.approx(want, abs=1e-6)   # curve values, tight
```

- [ ] **Step 2: Verify it fails**

Run: `cd bindings/python && uv run pytest tests/curves/test_svensson.py -k recovers -v`
Expected: FAIL — `fit_svensson` not defined.

- [ ] **Step 3: Implement `fit_svensson`** (numpy; separable / variable-projection)

```python
def _design(tenors: "np.ndarray", tau1: float, tau2: float) -> "np.ndarray":
    import numpy as np
    def cols(tau: float) -> tuple["np.ndarray", "np.ndarray"]:
        x = tenors / tau
        small = x < _EPS
        e = np.exp(-np.where(small, 1.0, x))
        l = np.where(small, 1.0, (1.0 - e) / np.where(small, 1.0, x))
        c = np.where(small, 0.0, l - e)
        return l, c
    l1, c1 = cols(tau1)
    _, c2 = cols(tau2)
    return np.column_stack([np.ones_like(tenors), l1, c1, c2])

def fit_svensson(tenors: "Sequence[float]", rates: "Sequence[float]", *,
                 tau_lo: float = 0.05, tau_hi: float = 30.0, n_grid: int = 50,
                 min_ratio: float = 1.5) -> dict[str, float]:
    """Fit NSS to observed (continuously-compounded) zero rates. Returns the 6 params.

    Separable NLS: 2-D grid over (tau1<tau2) with inner OLS for the betas.
    Scores by residual SSE (params are non-unique near tau1=tau2; we do not
    constrain betas hard). t->0 limits handled in the design matrix.
    """
    import numpy as np
    from loguru import logger
    t = np.asarray(tenors, dtype=float)
    y = np.asarray(rates, dtype=float)
    if t.size < 6:  # noqa: PLR2004
        msg = f"fit_svensson needs >=6 observations; got {t.size}"
        raise ValueError(msg)
    grid = np.geomspace(tau_lo, tau_hi, n_grid)
    best: tuple[float, tuple[float, float], "np.ndarray"] | None = None
    for tau1 in grid:
        for tau2 in grid[grid > tau1 * min_ratio]:   # tau1<tau2, skip near-diagonal
            phi = _design(t, tau1, tau2)
            beta, *_ = np.linalg.lstsq(phi, y, rcond=1e-12)
            sse = float(np.sum((y - phi @ beta) ** 2))
            if best is None or sse < best[0]:
                best = (sse, (tau1, tau2), beta)
    assert best is not None
    _, (tau1, tau2), beta = best
    # local refine on log(tau) via Nelder-Mead (small helper, pure numpy)
    tau1, tau2 = _refine_taus(t, y, tau1, tau2)
    phi = _design(t, tau1, tau2)
    beta, *_ = np.linalg.lstsq(phi, y, rcond=1e-12)
    b0, b1, b2, b3 = (float(x) for x in beta)
    if b0 <= 0 or b0 + b1 <= 0:
        logger.warning("svensson fit: b0={} b0+b1={} <= 0 (negative-rate regime?)", b0, b0 + b1)
    return {"b0": b0, "b1": b1, "b2": b2, "b3": b3, "tau1": float(tau1), "tau2": float(tau2)}
```

Add the deterministic local refine (successive log-space grid zoom — simpler and more robust than Nelder-Mead, fully specified, no optimizer dependency):

```python
def _sse(t: "np.ndarray", y: "np.ndarray", tau1: float, tau2: float) -> float:
    import numpy as np
    phi = _design(t, tau1, tau2)
    beta, *_ = np.linalg.lstsq(phi, y, rcond=1e-12)
    return float(np.sum((y - phi @ beta) ** 2))

def _refine_taus(t: "np.ndarray", y: "np.ndarray", tau1: float, tau2: float, *,
                 rounds: int = 5, span: float = 0.5, n: int = 9) -> tuple[float, float]:
    """Successive local-grid refinement around (tau1,tau2) in log space.

    Deterministic: each round samples an n x n log-spaced window of half-width
    `span` around the current best (enforcing tau1<tau2), keeps the lowest-SSE
    cell, then halves `span`. Converges curve values to ~1e-7 for sane inputs.
    """
    import numpy as np
    best = (_sse(t, y, tau1, tau2), tau1, tau2)
    for _ in range(rounds):
        g1 = np.exp(np.linspace(np.log(best[1]) - span, np.log(best[1]) + span, n))
        g2 = np.exp(np.linspace(np.log(best[2]) - span, np.log(best[2]) + span, n))
        for a in g1:
            for b in g2:
                if b <= a:                       # enforce tau1 < tau2
                    continue
                s = _sse(t, y, float(a), float(b))
                if s < best[0]:
                    best = (s, float(a), float(b))
        span *= 0.5
    return best[1], best[2]
```

- [ ] **Step 4: Verify pass + `Curve.fit_svensson`**

Add `Curve.fit_svensson(*, tenors, rates, day_count=None)` → calls `fit_svensson`, stores source knots (provenance) + params, `parametric.kind="svensson"`.

Run: `cd bindings/python && uv run pytest tests/curves/test_svensson.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/curves/_svensson.py bindings/python/gaspatchio_core/curves/_curve.py \
        bindings/python/tests/curves/test_svensson.py
git commit -m "feat(curves): fit_svensson — numpy separable-NLS NSS fitter"
```

---

## Task 8: `smith_wilson` evaluation + ζ-solve

**Files:**
- Create: `bindings/python/gaspatchio_core/curves/_smith_wilson.py`
- Modify: `core/src/polars_functions/curve_eval.rs` (smith_wilson branch + tests)
- Modify: `bindings/python/gaspatchio_core/curves/_curve.py` (`fit_smith_wilson`, dispatch, eager parity)
- Test: `tests/curves/test_smith_wilson.py` (create)

- [ ] **Step 1: Python heart/solve/eval + failing test vs lifelib worked example**

```python
# _smith_wilson.py
from __future__ import annotations
import numpy as np

def sw_heart(u: "np.ndarray", v: "np.ndarray", alpha: float) -> "np.ndarray":
    """Wilson 'heart' H(u,v) (min/max-free form, matches lifelib)."""
    u = u[:, None]; v = v[None, :]
    return 0.5 * (alpha * (u + v) + np.exp(-alpha * (u + v))
                  - alpha * np.abs(u - v) - np.exp(-alpha * np.abs(u - v)))

def solve_zeta(u: "np.ndarray", r: "np.ndarray", ufr: float, alpha: float) -> "np.ndarray":
    omega = np.log(1.0 + ufr)
    mu = np.exp(-omega * u)
    m = (1.0 + r) ** (-u)
    h = sw_heart(u, u, alpha)
    w = mu[:, None] * h * mu[None, :]
    return np.linalg.solve(w, m - mu)

def sw_price(t: "np.ndarray", u: "np.ndarray", zeta: "np.ndarray",
             omega: float, alpha: float) -> "np.ndarray":
    # W(t,u_j) = e^{-omega(t+u)} H(t,u)
    t = np.atleast_1d(np.asarray(t, dtype=float))
    h = sw_heart(t, u, alpha)                      # (len(t), len(u))
    w = np.exp(-omega * (t[:, None] + u[None, :])) * h
    return np.exp(-omega * t) + w @ zeta

def sw_spot(t: float, u: "np.ndarray", zeta: "np.ndarray",
            omega: float, alpha: float) -> float:
    p = float(sw_price(np.array([t]), u, zeta, omega, alpha)[0])
    return p ** (-1.0 / t) - 1.0                   # annually compounded; t>0
```

```python
# tests/curves/test_smith_wilson.py
import numpy as np
import pytest
from gaspatchio_core.curves._smith_wilson import solve_zeta, sw_spot

# lifelib worked example (MIT, (c) 2022 lifelib Developers) — see REFERENCES.md
U = np.array([1.0, 2.0, 4.0, 5.0, 6.0, 7.0])
R = np.array([0.01, 0.02, 0.03, 0.032, 0.035, 0.04])
UFR, ALPHA = 0.04, 0.15

def test_sw_matches_lifelib_example() -> None:
    omega = np.log(1.0 + UFR)
    zeta = solve_zeta(U, R, UFR, ALPHA)
    assert sw_spot(3.0, U, zeta, omega, ALPHA) == pytest.approx(0.0264236322, abs=1e-9)
    assert sw_spot(10.0, U, zeta, omega, ALPHA) == pytest.approx(0.0485040138, abs=1e-9)
    assert sw_spot(20.0, U, zeta, omega, ALPHA) == pytest.approx(0.0506997613, abs=1e-9)

def test_sw_reproduces_inputs_at_knots() -> None:
    omega = np.log(1.0 + UFR)
    zeta = solve_zeta(U, R, UFR, ALPHA)
    for u, r in zip(U, R, strict=True):
        assert sw_spot(float(u), U, zeta, omega, ALPHA) == pytest.approx(float(r), abs=1e-9)
```

Run: `cd bindings/python && uv run pytest tests/curves/test_smith_wilson.py -v` → PASS (pure numpy, no build).

- [ ] **Step 2: Rust smith_wilson branch + test**

```rust
fn sw_heart_scalar(u: f64, v: f64, alpha: f64) -> f64 {
    0.5 * (alpha * (u + v) + (-alpha * (u + v)).exp()
           - alpha * (u - v).abs() - (-alpha * (u - v).abs()).exp())
}
```
```rust
        "smith_wilson" => {
            let u = kw.u.as_ref().ok_or_else(|| polars_err!(ComputeError: "curve_eval smith_wilson: missing u"))?;
            let zeta = kw.zeta.as_ref().ok_or_else(|| polars_err!(ComputeError: "curve_eval smith_wilson: missing zeta"))?;
            let omega = kw.omega.ok_or_else(|| polars_err!(ComputeError: "curve_eval smith_wilson: missing omega"))?;
            let alpha = kw.alpha.ok_or_else(|| polars_err!(ComputeError: "curve_eval smith_wilson: missing alpha"))?;
            let mut p = (-omega * t).exp();
            for (uj, zj) in u.iter().zip(zeta.iter()) {
                p += (-omega * (t + uj)).exp() * sw_heart_scalar(t, *uj, alpha) * zj;
            }
            Ok(p.powf(-1.0 / t) - 1.0)
        }
```
Rust test: solve ζ in Python is not available in the Rust test, so pin the kernel against precomputed `(u, zeta, omega, alpha)` from the lifelib example (vendor the solved ζ vector as a constant in the test) and assert `r(3)=0.0264236322`.

Run `cd core && cargo test curve_eval` → PASS.

- [ ] **Step 3: `Curve.fit_smith_wilson`** — `fit_smith_wilson(*, tenors, rates, ufr=0.033, llp=None, alpha=None)`; for this task require an explicit `alpha` (calibration is Task 9). De-dup tenors closer than 1/12. Solve ζ, store `parametric.kind="smith_wilson"` with `(u, zeta, omega, alpha)`. `_kernel_kwargs` → `{"method":"smith_wilson", u, zeta, omega, alpha}`. Eager paths call `sw_spot`.

- [ ] **Step 4: Build + cross-path test**

```python
def test_sw_cross_path() -> None:
    from gaspatchio_core.curves import Curve
    from gaspatchio_core import ActuarialFrame
    import polars as pl
    c = Curve.fit_smith_wilson(tenors=list(U), rates=list(R), ufr=UFR, alpha=ALPHA)
    ts = [1.0, 3.0, 7.0, 20.0]
    af = ActuarialFrame(pl.DataFrame({"t": [ts]}))
    af.r = c.spot_rate(af["t"])
    out = af.collect()["r"].to_list()[0]
    for t, e in zip(ts, out, strict=True):
        assert c.spot_rate(t) == pytest.approx(e, abs=1e-9)
```

Run: `cd bindings/python && maturin build -uv && uv run pytest tests/curves -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add core/src/polars_functions/curve_eval.rs bindings/python/gaspatchio_core/curves/_smith_wilson.py \
        bindings/python/gaspatchio_core/curves/_curve.py bindings/python/tests/curves/test_smith_wilson.py
git commit -m "feat(curves): add classic Smith-Wilson evaluation + zeta-solve"
```

---

## Task 9: Smith-Wilson α-calibration

**Files:**
- Modify: `bindings/python/gaspatchio_core/curves/_smith_wilson.py` (`calibrate_alpha`)
- Modify: `bindings/python/gaspatchio_core/curves/_curve.py` (`fit_smith_wilson` optional α + UFR/LLP defaults)
- Test: `tests/curves/test_smith_wilson.py`

- [ ] **Step 1: Failing test — α calibration converges to ≥0.05, gap ≤1bp at CP**

```python
from gaspatchio_core.curves._smith_wilson import calibrate_alpha, sw_price

def test_calibrate_alpha_meets_gap_and_floor() -> None:
    llp = float(U.max())
    cp = max(llp + 40.0, 60.0)
    alpha = calibrate_alpha(U, R, ufr=UFR, llp=llp)
    assert alpha >= 0.05 - 1e-12
    # forward intensity gap at CP within ~1bp of omega
    omega = np.log(1.0 + UFR)
    zeta = solve_zeta(U, R, UFR, alpha)
    eps = 1e-4
    p1 = float(sw_price(np.array([cp]), U, zeta, omega, alpha)[0])
    p2 = float(sw_price(np.array([cp + eps]), U, zeta, omega, alpha)[0])
    fwd = -(np.log(p2) - np.log(p1)) / eps      # forward intensity at CP
    assert abs(fwd - omega) <= 1e-4 + 1e-6
```

- [ ] **Step 2: Verify it fails**

Run: `cd bindings/python && uv run pytest tests/curves/test_smith_wilson.py -k calibrate -v`
Expected: FAIL — `calibrate_alpha` not defined.

- [ ] **Step 3: Implement `calibrate_alpha`** (scan-then-bisect, P(CP)>0 guard)

```python
def _gap(u, r, ufr, alpha, cp) -> float | None:
    omega = np.log(1.0 + ufr)
    zeta = solve_zeta(u, r, ufr, alpha)
    p_cp = float(sw_price(np.array([cp]), u, zeta, omega, alpha)[0])
    if p_cp <= 0:
        return None                                  # singularity / negative DF -> reject
    eps = 1e-4
    p2 = float(sw_price(np.array([cp + eps]), u, zeta, omega, alpha)[0])
    fwd = -(np.log(p2) - np.log(p_cp)) / eps
    return fwd - omega                               # signed gap vs omega

def calibrate_alpha(u, r, *, ufr: float, llp: float, tol: float = 1e-4,
                    lo: float = 0.05, hi: float = 1.0, steps: int = 96) -> float:
    """Smallest alpha>=0.05 with |forward(CP)-omega|<=1bp (EIOPA rule). CP=max(LLP+40,60)."""
    import numpy as np
    cp = max(llp + 40.0, 60.0)
    grid = np.linspace(lo, hi, steps)
    for a in grid:                                   # smallest-first scan
        g = _gap(u, r, ufr, float(a), cp)
        if g is not None and abs(g) <= tol:
            return float(a)
    # if no grid point meets tol, return the alpha with the smallest |gap| (skipping poles)
    cand = [(abs(g), float(a)) for a in grid if (g := _gap(u, r, ufr, float(a), cp)) is not None]
    if not cand:
        msg = "smith_wilson: alpha calibration failed (all candidates singular)"
        raise ValueError(msg)
    return min(cand)[1]
```

- [ ] **Step 4: Verify pass + wire optional α into the constructor**

In `Curve.fit_smith_wilson`: `ufr` default `0.033` (EUR 2026), `llp` defaults to `max(tenors)` if `None`; if `alpha is None`, call `calibrate_alpha(...)`; else use the supplied α. Validate `alpha >= 0.05` when supplied.

Run: `cd bindings/python && uv run pytest tests/curves/test_smith_wilson.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/curves/_smith_wilson.py bindings/python/gaspatchio_core/curves/_curve.py \
        bindings/python/tests/curves/test_smith_wilson.py
git commit -m "feat(curves): Smith-Wilson alpha calibration (optional) with singularity guard"
```

---

## Task 10: Benchmark

**Files:**
- Create: `core/benches/curve_eval.rs`
- Modify: `core/Cargo.toml` (`[[bench]]`)

- [ ] **Step 1: Write the bench** (mirror `core/benches/list_pow.rs`)

```rust
use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};
use gaspatchio_core_lib::polars_functions::curve_eval::{curve_eval, CurveEvalKwargs};
use polars::prelude::*;

fn make_t(rows: usize) -> Series {
    let data: Vec<Option<Series>> = (0..rows)
        .map(|_| {
            let v: Vec<f64> = (0..120).map(|i| (i as f64 + 1.0) / 12.0).collect();
            Some(Series::new("".into(), v))
        })
        .collect();
    ListChunked::from_iter(data).into_series()
}

fn kw(method: &str) -> CurveEvalKwargs {
    CurveEvalKwargs {
        method: method.into(),
        xs: Some(vec![1.0, 2.0, 5.0, 10.0, 20.0, 30.0]),
        ys: Some(vec![0.02, 0.022, 0.025, 0.028, 0.03, 0.031]),
        slopes: Some(vec![0.002, 0.0015, 0.001, 0.0006, 0.0002, 0.0001]),
        extrapolation: Some("flat".into()),
        b0: Some(0.04), b1: Some(-0.01), b2: Some(0.005), b3: Some(0.002),
        tau1: Some(1.5), tau2: Some(10.0),
        u: Some(vec![1.0, 5.0, 10.0, 20.0, 30.0]),
        zeta: Some(vec![0.01, -0.02, 0.015, -0.005, 0.002]),
        omega: Some((1.033_f64).ln()), alpha: Some(0.15),
    }
}

fn bench(c: &mut Criterion) {
    let mut g = c.benchmark_group("curve_eval");
    for method in ["linear", "log_linear", "pchip", "svensson", "smith_wilson"] {
        for rows in [1_000usize, 10_000, 100_000] {
            let t = make_t(rows);
            let k = kw(method);
            g.bench_with_input(BenchmarkId::new(method, rows), &rows, |b, _| {
                b.iter(|| curve_eval(std::slice::from_ref(&t), &k).unwrap());
            });
        }
    }
    g.finish();
}
criterion_group!(benches, bench);
criterion_main!(benches);
```

Add to `core/Cargo.toml`:
```toml
[[bench]]
name = "curve_eval"
harness = false
```

- [ ] **Step 2-4: Run & sanity-check scaling**

Run: `cd core && cargo bench --bench curve_eval`
Expected: completes; per-method time scales ~linearly 1K→10K→100K (correct elementwise handling).

- [ ] **Step 5: Commit**

```bash
git add core/benches/curve_eval.rs core/Cargo.toml
git commit -m "bench(curves): curve_eval over 10K x 120 lists, all methods"
```

---

## Task 11: Attribution, exports, docstrings

**Files:**
- Create: `bindings/python/tests/curves/REFERENCES.md`
- Modify: `bindings/python/gaspatchio_core/curves/__init__.py` / `__init__.pyi`
- Modify: doctest-validated docstrings on `from_zero_rates` (extended `interpolation`), `from_svensson`, `fit_svensson`, `fit_smith_wilson`, and the `spot_rate`/`discount_factor` projection examples — per `ref/12-docstring-and-examples/12-docstring-README.md`

- [ ] **Step 1: Write `tests/curves/REFERENCES.md`**

```markdown
# Third-party reference oracles (test-only)

These sources provide numeric oracles used by the curve tests. All are permissive-licensed;
none are bundled in the shipped wheel. Values are facts (published numeric outputs); test code
is original.

| Source | Licence | © | URL | Used for |
|--------|---------|---|-----|----------|
| lifelib | MIT | 2022 lifelib Developers | https://lifelib.io/libraries/economic_curves/smith_wilson.html | Smith-Wilson worked-example values (test_smith_wilson.py) |
| Federal Reserve GSW | US-Gov public domain | — | https://www.federalreserve.gov/data/nominal-yield-curve.htm | NSS published params + SVENYxx (test_svensson.py) |
```

- [ ] **Step 2: Export the new constructors**

Ensure `Curve.from_svensson`, `Curve.fit_svensson`, `Curve.fit_smith_wilson` are public on `Curve`; update `curves/__init__.pyi` stub to list them with signatures. Add an `interpolation` Literal update (`"linear" | "log_linear" | "pchip"`) to the stub.

- [ ] **Step 3: Docstrings — really great, doctest-validated**

Every public curve method gets a full docstring following the project standard
(`gaspatchio-core/ref/12-docstring-and-examples/12-docstring-README.md`) and matching the existing
`_curve.py` style: one-line summary, `Args:`/`Returns:`/`Raises:`, a **"When to use"** note for the
actuary, and an `Examples:` block with **runnable, doctest-validated** code (floats use
`# doctest: +ELLIPSIS`). Author the example, then lock its exact output with
`cd bindings/python && uv run pytest --doctest-modules gaspatchio_core/curves/_curve.py --accept`
(the `--accept` flag captures real outputs — the `0.0...` placeholders below become locked values).
Prefer authoring each docstring *with* its method (Tasks 4-9); this step is the final
standard/consistency pass + full doctest run. Include at minimum:

`from_zero_rates` (extended `interpolation`):

```python
        Examples:
            >>> from gaspatchio_core.curves import Curve
            >>> c = Curve.from_zero_rates(
            ...     tenors=[1, 2, 5, 10], rates=[0.01, 0.02, 0.03, 0.035],
            ...     interpolation="pchip",   # or "linear" | "log_linear"
            ... )
            >>> c.spot_rate(3.5)  # doctest: +ELLIPSIS
            0.0...
            >>> c.discount_factor([1.0, 5.0])  # doctest: +ELLIPSIS
            [0.99..., 0.86...]
```

`from_svensson` (decimals in, annually-compounded out — NSS converts internally):

```python
        Examples:
            >>> from gaspatchio_core.curves import Curve
            >>> nss = Curve.from_svensson(
            ...     b0=0.040, b1=-0.010, b2=0.005, b3=0.002, tau1=1.5, tau2=10.0
            ... )
            >>> nss.spot_rate(7.5)  # doctest: +ELLIPSIS
            0.03...
            >>> nss.spot_rate(50)   # smooth closed-form extrapolation  # doctest: +ELLIPSIS
            0.04...
```

`fit_svensson` (fits 6 params to observed zero rates; separable NLS, numpy):

```python
        Examples:
            >>> from gaspatchio_core.curves import Curve
            >>> nss = Curve.fit_svensson(
            ...     tenors=[1, 2, 5, 10, 20, 30],
            ...     rates=[0.030, 0.032, 0.035, 0.038, 0.040, 0.041],
            ... )
            >>> nss.spot_rate(10.0)  # doctest: +ELLIPSIS
            0.0...
```

`fit_smith_wilson` (classic SW; EIOPA EUR defaults UFR 3.30%/LLP 20y; α auto-calibrates; the 2026
EIOPA FSP/LLFR alternative extrapolation is a planned future method):

```python
        Examples:
            >>> from gaspatchio_core.curves import Curve
            >>> sw = Curve.fit_smith_wilson(
            ...     tenors=[1, 2, 3, 5, 7, 10, 15, 20],
            ...     rates=[0.031, 0.033, 0.034, 0.036, 0.038, 0.040, 0.041, 0.042],
            ... )
            >>> sw.spot_rate(20.0)  # reproduces the liquid input at the LLP  # doctest: +ELLIPSIS
            0.042...
            >>> sw.spot_rate(60.0)  # extrapolates toward the UFR  # doctest: +ELLIPSIS
            0.0...
```

Extend the existing `spot_rate`/`discount_factor` docstrings to show the **projection** usage (the
GSP-116 fast path), which reads identically for every method:

```python
            >>> import polars as pl
            >>> from gaspatchio_core import ActuarialFrame
            >>> af = ActuarialFrame(pl.DataFrame({"t": [[1.0, 5.0, 10.0]]}))
            >>> af.df = c.discount_factor(af["t"])     # vectorised in Rust, no map_elements
            >>> af.collect()["df"].to_list()[0]  # doctest: +ELLIPSIS
            [0.99..., 0.86..., 0.7...]
```

- [ ] **Step 4: Full suite**

Run: `cd core && cargo test && cd ../bindings/python && maturin build -uv && uv run pytest tests/curves -v && uv run pytest --doctest-modules --doctest-glob="*.pyi" gaspatchio_core/curves`
Expected: all PASS (every docstring example included).

- [ ] **Step 5: Commit**

```bash
git add bindings/python/tests/curves/REFERENCES.md bindings/python/gaspatchio_core/curves/__init__.py \
        bindings/python/gaspatchio_core/curves/__init__.pyi bindings/python/gaspatchio_core/curves/_curve.py
git commit -m "docs(curves): attribution, exports, and docstrings for curve methods"
```

---

## Final verification (whole feature)

- [ ] `cd core && cargo test && cargo clippy && cargo fmt --check`
- [ ] `cd bindings/python && maturin build -uv && uv run pytest tests/curves -v`
- [ ] `grep -rn map_elements gaspatchio_core/curves/` → no matches (GSP-116 closed)
- [ ] Cross-path equivalence green for all five methods
- [ ] SW matches lifelib example to 1e-9; NSS curve-values match GSW to ≤1e-3pp
- [ ] Bench scales linearly 1K→100K for every method
- [ ] Then: superpowers:finishing-a-development-branch (push `develop`; squash-merge to `main` before launch)
