# Yield-curve evaluation — vectorised kernel + five methods — design

**Status:** approved design (brainstorming → spec). Implements GSP-116; ships as the launch curves feature.
**Date:** 2026-06-25
**Owner:** Matt Wright
**Ticket:** GSP-116 — *Curve.spot_rate/discount_factor silently fall back to map_elements on list columns*

> Supersedes the earlier 2-method draft (`2026-06-25-curve-eval-linear-svensson-design.md`).
> Scope expanded to a single, cohesive five-method curve feature for the OSS launch.

---

## 1. Problem

`Curve.spot_rate()` / `Curve.discount_factor()` fall back to `pl.Expr.map_elements(...)` on the
natural `curve.discount_factor(af.projection.t_years())` usage (`_curve.py:175-182`, `246-258`).
`map_elements` is the forbidden anti-pattern (~14x slower; the telemetry guardrail hard-fails it
in optimize mode), so the most discoverable curve usage is silently the slow path. Eager
(`scalar`/`list`/`ndarray`/`Series`) inputs are fine; only the `Expr`/list-column path degrades.

## 2. What we're building

A vectorised, streaming (`is_elementwise=True`) Rust kernel `curve_eval` that evaluates a yield
curve over a `List<f64>` of year-fractions `t` → `List<f64>` of **annually-compounded spot
rates**, dispatched on a `method` tag. It powers the `Expr`/list path of `spot_rate` and
`discount_factor`, deleting the `map_elements` branches (the GSP-116 fix). Shipping **five
methods** spanning the two families actuaries use:

| Bucket | Method tag | What | Tier |
|--------|-----------|------|------|
| A — knot interpolation | `linear` | linear-on-zero-rates, flat extrapolation (the existing behaviour) | trivial |
| A — knot interpolation | `log_linear` | linear in log(discount factor) ≡ piecewise-constant forwards; the production discounting workhorse | trivial |
| A — knot interpolation | `pchip` | Fritsch-Carlson monotone cubic Hermite (C¹) — smooth without spline oscillation/negative forwards | moderate |
| B — parametric fit | `svensson` | Nelson-Siegel-Svensson (6-param) — central-bank econ-curve standard (Fed/ECB/BIS) | harder |
| B — parametric fit | `smith_wilson` | classic Smith-Wilson — the Solvency II risk-free-rate method | harder |

**Why two buckets, dispatched.** NSS and Smith-Wilson are *parametric models*, not knot
interpolation — they have parameters, not `(xs, ys)` knots (QuantLib, RustQuant and the
`yield-curves` crate all draw this exact line: NSS/SW are `FittingMethod`s, categorically
separate from `Interpolation`). The two families share only an **output** contract (`t → rate`),
never an **input** contract. So the kernel dispatches on a `method` tag carrying a per-method
payload. Adding a future method = one branch + a payload; **no signature change.**

## 3. Architecture — three layers

```
Python Curve ──(eager: scalar/list/ndarray/Series)──> Python evaluators (parity reference)
   │                                                    _interpolation.* , _svensson.* , _smith_wilson.*
   └──(lazy: pl.Expr / list column)──> curve_eval() plugin ──> Rust kernel
Host-side setup (Phase 1, once per curve, numpy):
   knot coeffs (pchip slopes, log-DF), NSS fit, SW weight-solve + α-calibration
```

- **Rust kernel** = pure per-`t` evaluation. Returns spot rate. Knows nothing about fitting.
- **Python `Curve`** = representation + dispatch; eager paths evaluate in Python, the `Expr` path
  calls the kernel. **Cross-path parity is a correctness requirement.**
- **Host-side setup** = all the expensive work (cubic slopes, NLS fit, linear solve, α-calibration)
  happens once at construction, numpy-only. The kernel only ever evaluates closed forms.

## 4. The kernel `curve_eval`

**File:** `core/src/polars_functions/curve_eval.rs` (+ `mod.rs` wiring; PyO3 wrapper in
`bindings/python/src/vector.rs`).

**Signature & contract:**
```rust
pub fn curve_eval(inputs: &[Series], kwargs: &CurveEvalKwargs) -> PolarsResult<Series>
// inputs[0] = List<Float64> of t (year-fractions), jagged per row allowed
// output    = List<Float64> of annually-compounded spot rates, same per-row lengths
```
- `amortized_iter()` over the t-list (per-row independent → jagged lists free, like `list_pow`);
  per element dispatch once on `method`. Null element → null; empty inner list → empty.
- `is_elementwise=True` (each row depends only on its own `t` + immutable kwargs).
- Output-type helper returns `List(Float64)`.

**Kwargs** — a flat `#[derive(Deserialize)]` struct with a `method` discriminator + optional
per-method fields (mirrors the existing `rollforward` kwargs pattern; avoids serde-enum-over-pickle
edge cases):
```rust
#[derive(Deserialize)]
pub struct CurveEvalKwargs {
    pub method: String,                  // linear | log_linear | pchip | svensson | smith_wilson
    // Bucket A (knot) — coefficients precomputed host-side:
    pub xs: Option<Vec<f64>>,            // knot tenors (sorted)
    pub ys: Option<Vec<f64>>,            // knot values: zero rate (linear), log-DF (log_linear), zero rate (pchip)
    pub slopes: Option<Vec<f64>>,        // pchip per-knot Hermite tangents
    pub extrapolation: Option<String>,   // "flat" (only value now); applies to knot methods
    // Bucket B (svensson):
    pub b0: Option<f64>, pub b1: Option<f64>, pub b2: Option<f64>,
    pub b3: Option<f64>, pub tau1: Option<f64>, pub tau2: Option<f64>,
    // Bucket B (smith_wilson):
    pub u: Option<Vec<f64>>,             // knot tenors u_j
    pub zeta: Option<Vec<f64>>,          // fitted weights ζ_j
    pub omega: Option<f64>,              // ω = ln(1+UFR)
    pub alpha: Option<f64>,              // α convergence parameter
}
```
**Shared evaluation paths inside the kernel:**
- **Knot methods** binary-search the bracketing segment for `t`, then:
  - `linear` → linear interp of `ys` (zero rate); flat extrapolation (`t≤xs[0]→ys[0]`, `t≥xs[-1]→ys[-1]`), bit-mirroring `linear_interpolate`.
  - `log_linear` → linear interp of `ys` (= log-DF) → `DF=exp(that)` → `r = DF^(-1/t) − 1`.
  - `pchip` → one shared **Hermite cubic** eval from `(ys, slopes)` (see §6c).
- **Parametric methods** ignore segments:
  - `svensson` → closed-form continuously-compounded rate (§6d), converted to annual.
  - `smith_wilson` → `P(t)=e^{-ωt}+Σ_j ζ_j W(t,u_j)` then `r = P(t)^(-1/t) − 1` (§6e).

## 5. Compounding convention (uniform — a deliberate, documented choice)

**All methods return annually-compounded zero rates**, and `discount_factor` is uniformly
`(1+r)^(-t)` (via the existing `list_pow`), so the formula stays visible in Python.
- `linear`/`log_linear`/`pchip`: operate on the user's zero rates (annually compounded by the
  existing `(1+r)^(-t)` convention). `log_linear` round-trips through DF and back — exact.
- `svensson`: the GSW form is **continuously compounded**; the evaluator computes it then converts
  internally `r_annual = exp(r_cc) − 1`. The Fed/ECB test oracle compares against the
  *pre-conversion* continuous value (§11).
- `smith_wilson`: `r = P(t)^(-1/t) − 1` is **already annually compounded** — no conversion.
- For `log_linear`/`smith_wilson`, `discount_factor`'s `(1+r)^(-t)` exactly recovers the underlying
  `DF` (since `r ≡ DF^(-1/t)−1`).

## 6. Per-method specifications

### 6a. `linear` (knot, trivial)
Linear interpolation of zero rates between knots; flat extrapolation. Host-side: none (sorted
knots). Numerically identical to the current `linear_interpolate` — the parity baseline.

### 6b. `log_linear` (knot, trivial)
Linear interpolation in `log(DF)`. Host-side: precompute `ys_i = log(DF(u_i)) = −u_i·ln(1+r_i)`.
Kernel: linear-interp `log(DF)` at `t`, `DF=exp(...)`, `r = DF^(-1/t) − 1`. Equivalent to
piecewise-constant instantaneous forwards. Flat extrapolation in log-DF slope.

### 6c. `pchip` (knot, moderate — Fritsch-Carlson monotone cubic Hermite, C¹)
**Host-side (numpy, once):** compute monotonicity-preserving Hermite tangents `m_i`:
1. Secant slopes `δ_k = (y_{k+1}−y_k)/(x_{k+1}−x_k)`.
2. Interior init `m_k=(δ_{k−1}+δ_k)/2`; endpoints `m_1=δ_1`, `m_n=δ_{n−1}`.
3. Where `δ_k=0` set `m_k=m_{k+1}=0`; at sign-change of adjacent secants set interior `m_k=0`.
4. **Limiter:** with `α_k=m_k/δ_k`, `β_k=m_{k+1}/δ_k`, if `α_k²+β_k²>9` scale
   `τ=3/√(α_k²+β_k²)`, `m_k←τα_kδ_k`, `m_{k+1}←τβ_kδ_k`.
**Kernel:** with `h=x_{k+1}−x_k`, `s=(t−x_k)/h`,
`y = y_k·h00(s) + h·m_k·h10(s) + y_{k+1}·h01(s) + h·m_{k+1}·h11(s)`,
`h00=2s³−3s²+1, h10=s³−2s²+s, h01=−2s³+3s², h11=s³−s²`. Flat extrapolation outside the knots.
Reference: `yield-curves` Rust crate `PchipCurve` (same split). C¹ — no spline oscillation, no
negative forwards; the "smooth but safe" actuarial choice.

### 6d. `svensson` (parametric — NSS, harder)
**Closed form** (GSW eq. 22), `x1=t/τ1`, `x2=t/τ2`, continuously compounded:
```
y(t) = b0 + b1·L1 + b2·(L1 − e^{−x1}) + b3·(L2 − e^{−x2}),   L1=(1−e^{−x1})/x1,  L2=(1−e^{−x2})/x2
```
**t→0 limits:** `L1→1`, `(L1−e^{−x1})→0`, `(L2−e^{−x2})→0` ⇒ `y(0)=b0+b1`. Guard `t/τ` below ε.
Convert to annual: `r=exp(y)−1`. `t<0` invalid.

**Host-side fit (`_svensson.py`, numpy-only, separable / variable-projection NLS):**
NSS is **linear in (b0,b1,b2,b3)** given (τ1,τ2), so fit = 2-D search over (τ1,τ2) with inner
`np.linalg.lstsq` for the betas:
- Design columns at observed tenors: `[1, L1, L1−e^{−x1}, L2−e^{−x2}]` with the t→0 limits above.
- **Grid** log-spaced over τ∈[0.05, 30], enforce **τ1<τ2** and **exclude a near-diagonal band**
  (`τ2/τ1 ≥ min_ratio`, default ~1.5) — the β2/β3 loadings go collinear at τ1≈τ2 (condition
  number → ~1750; the Fed's own published betas are unstable there).
- Inner solve with explicit `rcond` (~1e-12); **score by residual SSE, not β magnitude.**
- Local refine (2-D Nelder-Mead or alternating golden-section, pure numpy) after the grid.
- Constraints: τ>0 structural (grid); `b0>0`, `b0+b1>0` are **soft validators (warn, not reject)**
  — negative-rate regimes legitimately violate them. Equal-weighted SSE on rates (duration
  weighting is only for price-fitting).
- Constructors: `Curve.from_svensson(b0,b1,b2,b3,tau1,tau2)` (direct — Fed/ECB publish these) and
  `Curve.fit_svensson(tenors, rates)` (fit).

### 6e. `smith_wilson` (parametric — classic SW, harder)
**Wilson kernel** (`ω=ln(1+UFR)`), using lifelib's min/max-free heart for vectorisation:
```
H(u,v) = 0.5·( α(u+v) + e^{−α(u+v)} − α|u−v| − e^{−α|u−v|} )
W(u,v) = e^{−ω(u+v)}·H(u,v)
P(t)   = e^{−ωt} + Σ_j ζ_j·W(t,u_j)
r(t)   = P(t)^{−1/t} − 1            # annually compounded; guard t>0, P(0)=1
```
**Host-side solve (zero-coupon inputs, numpy, once):** with `μ_i=e^{−ω u_i}`, `m_i=(1+r_i)^{−u_i}`,
`W=diag(μ)·H·diag(μ)`, solve `np.linalg.solve(W, m − μ)` for ζ (not `inv`). De-duplicate/merge
knots closer than ~1 month (the only real conditioning risk).
**α calibration (optional):** if α not supplied, find the smallest α≥0.05 such that the forward
intensity at the **Convergence Point `CP = max(LLP+40, 60)`** is within 1bp of ω — via a
**scan-then-bisect that rejects α where `P(CP)≤0`** (the `g(α)` poles; this also rejects the
negative-DF pathology). If α is supplied, skip calibration.
**Parameters:** `UFR` and `LLP` are inputs with EIOPA defaults (**EUR UFR=0.033 (2026), LLP=20**) —
UFR is a *dated, per-currency* regulatory value, **not** a hard-coded constant.
**v1 = classic SW** (interpolate liquid + extrapolate to UFR). The 2026 EIOPA **FSP/LLFR
alternative extrapolation** (Reg (EU) 2026/269, OJ 18-Feb-2026; transitional to 2032) is **out of
scope** — its blend-weight form isn't yet pinned to primary text — and is **flagged in docs** as
the regulatory successor + planned future method. Constructor: `Curve.fit_smith_wilson(tenors,
rates, *, ufr=0.033, llp=None, alpha=None)`.

## 7. Curve API changes (`_curve.py`) — where GSP-116 is fixed

- **Knot curves (bucket A):** extend the existing `interpolation` field to
  `Literal["linear","log_linear","pchip"]` (default `"linear"` → **backward compatible**).
  `from_zero_rates` / `from_par_rates` accept the new `interpolation` values. Per-method
  coefficients (pchip slopes, log-DF) are precomputed at construction and stored.
- **Parametric curves (bucket B):** add one optional field `parametric: ParametricPayload | None`
  — a small tagged record (`kind ∈ {"svensson","smith_wilson"}` + its params). Constructors:
  `from_svensson`, `fit_svensson`, `fit_smith_wilson`.
- **Dispatch (derived, no redundant discriminator):** a curve is parametric when `parametric is
  not None` (use `parametric.kind`), else a knot curve using `interpolation`. The kernel's `method`
  kwarg is **computed at the call site** from this.
- **`canonical_form()`/`source_sha()`:** existing linear curves are **unchanged** (no `parametric`,
  `interpolation="linear"`); new methods add their bits. Backward-compatible shas.
- **The fix:** `spot_rate`/`discount_factor` `pl.Expr` branch → `curve_eval(...)` for **all**
  methods; the `map_elements` lines are deleted. Eager paths gain `log_linear`/`pchip`/`svensson`/
  `smith_wilson` branches via the Python evaluators (parity). `discount_factor` stays `(1+r)^(-t)`
  via `list_pow`. `forward_rate` unchanged (scalar).
- **Python glue:** `curve_eval(t, *, method, **payload)` in `polars_backend/plugins.py`
  (`register_plugin_function(..., is_elementwise=True, kwargs={...})`), re-exported in
  `functions/vector.py`.

## 8. Error handling

- Constructors validate: knot tenors strictly increasing, ≥2 knots (existing); `fit_svensson`
  needs `len(tenors)==len(rates)` and ≥6 observations; `fit_smith_wilson` validates `ufr>−1`,
  `llp>0`, supplied `alpha≥0.05`, and de-duplicates near tenors; `τ>0`.
- Soft validators (warn, not raise): NSS `b0>0`, `b0+b1>0`; SW `cond(W)` above ~1e10.
- Kernel: unknown `method` or a payload field missing for the chosen method → explicit
  `PolarsError` (no silent default). Nulls/empty lists as in §4; `svensson`/SW require `t>0`.

## 9. Testing

- **Cross-path equivalence (headline):** for every method, `scalar == list == ndarray == Series ==
  Expr` within tolerance — one curve, one answer regardless of input shape.
- **Rust inline `#[cfg(test)]`** in `curve_eval.rs`: `linear` matches `linear_interpolate`;
  `log_linear`/`pchip` against hand/reference values (pchip monotonicity on a monotone series);
  `svensson` against hand-computed values incl. `t→0`; `smith_wilson` against the **lifelib worked
  example** (`r=[.01,.02,.03,.032,.035,.04]`, `M=[1,2,4,5,6,7]`, UFR=0.04, α=0.15 → `r(3)=0.0264236322`,
  `r(10)=0.0485040138`, `r(20)=0.0506997613`; reproduces inputs at knots); jagged lists; nulls.
- **NSS oracle — curve values, NOT parameters** (params are non-unique near τ1≈τ2): evaluate the
  closed form at published Fed GSW params (a *well-separated-τ* date, e.g. 1987-12-01) → match
  `SVENYxx` to ≤1e-3pp; synthetic round-trip recovers **curve values** to ~1e-6 (assert on the
  curve, not β2/β3).
- **SW oracle:** lifelib hand example bit-for-bit; cross-check `solve(W,·)` vs `inv@`; (optional)
  reproduce one EIOPA monthly EUR curve from its published inputs+(UFR,α) to ~1e-4.
- **`discount_factor`** equals `(1+r)^(-t)` and the eager list path; **no `map_elements`** on the
  curve path (no `PerformanceViolationError` in optimize mode; plan stays streaming).
- **Bench:** `core/benches/curve_eval.rs` — each method over 10K×120 lists, scaling 100→100K,
  mirroring `list_pow.rs`; confirms linear scaling.

### 9b. Reference oracles & test-data licensing (verified 2026-06-26)

Tests may verify against third-party curve libraries' outputs/cases, restricted to **permissive
licences with attribution** (all verified compatible with our Apache-2.0 distribution):

| Source | Licence | Use |
|--------|---------|-----|
| lifelib | MIT (© 2022 lifelib Developers) | Smith-Wilson worked-example oracle |
| nelson_siegel_svensson (luphord) | MIT (© 2019 luphord) | optional NSS fitter cross-check |
| yield-curves (Rust crate) | MIT OR Apache-2.0 | optional pchip/linear cross-check |
| RustQuant | MIT OR Apache-2.0 | optional NSS/curve cross-check |
| QuantLib / QuantLib-Python | BSD-style (permissive) | optional broad method cross-check |
| Fed GSW (`feds200628.csv`) | US-Government work — public domain | NSS curve-value oracle |
| EIOPA published RFR curves | EU reuse policy (attribution; confirm terms before bundling) | optional SW integration oracle |

**Two mechanisms, preferred order:**
1. **Vendored published values (preferred):** copy specific numeric outputs (facts — not
   copyrightable) into test fixtures with a source citation. No dependency, **no SBOM/runtime
   impact**, not shipped in the wheel. Covers the concrete oracles (lifelib SW example; Fed GSW
   params + `SVENYxx`; EIOPA curve points).
2. **Dev/test-only library dependency** (only where live cross-checking adds real coverage, e.g.
   property-based checks over many random curves): add to a **dev/test dependency group** (never a
   runtime dep), attributed. Note these *can* surface in the SBOM (syft reads lockfile dev groups),
   so prefer (1) to keep the SBOM lean.

**Attribution:** a new `tests/curves/REFERENCES.md` lists each source actually used — licence,
copyright holder, URL, and what we use it for. The user-facing `NOTICE` is unchanged (these are
test-only, not bundled in the wheel). Prefer reusing **values/cases** (facts) over copying
third-party **test code**; if any test code is copied, carry its licence text + attribution per its
terms.

## 10. File touch list

- `core/src/polars_functions/curve_eval.rs` *(new — kernel + inline tests)*; `mod.rs` wiring.
- `core/benches/curve_eval.rs` *(new)* + `core/Cargo.toml` `[[bench]]`.
- `bindings/python/src/vector.rs` *(PyO3 wrapper + output-type helper)*.
- `bindings/python/gaspatchio_core/curves/_svensson.py` *(new — eval + numpy fit)*.
- `bindings/python/gaspatchio_core/curves/_smith_wilson.py` *(new — kernel heart, eval, ζ-solve, α-calibration)*.
- `bindings/python/gaspatchio_core/curves/_interpolation.py` *(add log-linear + pchip eval/slopes for eager parity)*.
- `bindings/python/gaspatchio_core/curves/_curve.py` *(interpolation enum, parametric payload, constructors, dispatch; delete `map_elements`)*.
- `bindings/python/gaspatchio_core/polars_backend/plugins.py` + `functions/vector.py` *(Python plugin wrapper + re-export)*.
- `bindings/python/gaspatchio_core/curves/__init__.py` / `__init__.pyi` *(export new constructors)*.
- Tests: `core` inline + `bindings/python/tests/curves/test_curve_eval.py`,
  `test_svensson_fit.py`, `test_smith_wilson.py` *(new)*; `tests/curves/REFERENCES.md`
  *(new — third-party oracle attribution, §9b)*.

## 11. Build / verification notes

- Rust changes → `maturin build -uv` (in `bindings/python/`) before Python sees the plugin;
  `cargo test`/`cargo bench` in `core/`.
- **Local env caveat:** `uv run`/`uv sync` is broken on this machine (`lancedb` has no
  macOS-x86_64 wheel → `uv sync` fails). Python tests run in CI / a clean env; `cargo test` is the
  primary local gate. Use `uvx`-isolated tooling locally where possible.
- Lands on `develop`; squash-merged to `main` before the OSS launch (keeps `main`'s clean lineage).

## 12. Out of scope (future variants — no rewrite needed)

- Interpolation: natural cubic spline (oscillation/negative-forward footgun), Hagan-West monotone
  convex (gold-plating), Nelson-Siegel (4-param), piecewise-flat forward, log-cubic.
- Parametric: exponential splines; **EIOPA FSP/LLFR alternative extrapolation** (Reg (EU) 2026/269)
  — the named regulatory successor to classic SW; needs OJ-text confirmation of the blend weight.
- Fitting NSS/SW to **bond prices** (vs observed zero rates); a frame accessor
  `af.<col>.curve.discount_factor(curve)`; continuous-compounding public API; per-row curves.

## 13. References

- GSW, FEDS 2006-28 / *JME* 2007 — NSS forms (eq. 22); data file `feds200628.csv` (cols
  `BETA0..3, TAU1, TAU2, SVENYxx` = continuously-compounded spot in %).
- BIS Papers No. 25 — central-bank NS/Svensson practice; yield- vs price-error weighting.
- Golub & Pereyra (1973), *SIAM J. Numer. Anal.* 10:413-432 — variable projection (separable NLS).
- arXiv:1602.02011 (Lagerås & Lindholm, "Issues with the Smith-Wilson method") — SW eqs. (1)-(6),
  α-calibration, singularity guard.
- EIOPA RFR Technical Documentation; EIOPA UFR-2026 (UFR EUR=3.30%, 31-Mar-2025); Reg (EU) 2026/269
  (OJ 18-Feb-2026, FSP/LLFR).
- lifelib `economic_curves/smith_wilson` — reference impl + worked numeric oracle.
- `yield-curves` Rust crate (Linear/CubicSpline/Pchip/NelsonSiegel/Svensson behind one eval trait).
- Repo reference impls: `core/src/polars_functions/list_pow.rs`; `accessors/finance.py`
  (`discount_factor` via `list_pow`); `curves/_interpolation.py`, `_bootstrap.py`.
