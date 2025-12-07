# Review of Recursive Accumulation Strategy

**Status:** Review Complete
**Date:** December 2025
**Reviewer:** Gaspatchio Core Team

## 1. Executive Summary

The analysis in `26-background.md` accurately identifies the "intra-seriatim" dependency problem as the primary bottleneck in actuarial modeling with Python/Polars. The proposed architectural solution—**offloading the sequential loop to a Rust Polars plugin operating on List columns**—is sound and aligns with best practices seen in high-performance systems like JuliaActuary and specialized C++ actuarial engines.

However, the proposed API design (`accumulate` with hardcoded `inflows`, `outflows`, `interest`) is **insufficiently generic**. It risks becoming "compiled gymnastics"—fast but brittle logic that requires recompilation for every new product feature.

**Recommendation:** Adopt a **layered approach**. Implement a generic **Linear Recurrence Scanner** (`scan_linear`) in Rust as the primary primitive. This handles 90% of use cases (standard AV rollforward, reserve accumulation) without baking accounting rules into the compiled binary. Use Python to compose these primitives.

---

## 2. Validation of Core Thesis

The document correctly establishes:
1.  **The Parallelism Constraint:** Intra-policy calculations are inherently serial ($t$ depends on $t-1$), but inter-policy calculations are embarrassingly parallel.
2.  **The Data Layout:** Polars `List` columns (one row per policy, list of values over time) perfectly match this constraint. They allow `rayon` to parallelize *across* rows while a single thread processes the serial list *within* a row.
3.  **The Performance Gap:** Python loops are too slow (~2,300ns/op). Rust loops (~7ns/op) are required to meet run-time targets.

**Confirmed:** This architecture is the correct "Gaspatchio Way"—leveraging Python for graph management and Rust for heavy computation.

---

## 3. Critique of Proposed API (`accumulate`)

The proposed function signature is:
```python
def accumulate(inflows, outflows, interest, timing_points, initial)
```

### Risks & Weaknesses
1.  **Rigid Accounting Identity:** This assumes the formula is always $AV_t = (AV_{t-1} + In - Out) \times (1 + i)$.
    *   *Failure Mode:* Variable Annuities where M&E fees are deducted *daily* or *after* interest.
    *   *Failure Mode:* Products where COI is deducted mid-month but expenses are beginning-of-month.
    *   *Failure Mode:* "Ratchet" death benefits that track the maximum historical AV (requires `max` logic, not just add/mult).
2.  **Signature Churn:** If a new product adds a "Maintenance Fee" distinct from "Administration Fee", the Rust signature must change to accept it, or the user must pre-aggregate in Python (which defeats the purpose of the "timing points" argument).
3.  **Opaque Logic:** The recursion logic is hidden inside the Rust binary. Actuaries cannot inspect the formula without reading Rust source code.

---

## 4. The Improved Solution: Generalized Linear Recurrence

Instead of hardcoding "Account Value Logic", we should implement **Linear Recurrence** as a generic mathematical primitive.

Most actuarial accumulations (AV, Reserves, tracking accounts) fit the form:

$$ State_t = (State_{t-1} \times M_t) + A_t $$

Where:
*   $M_t$ (Multiplicative Factor): The "growth" component (e.g., $1 + interest\_rate$, or survival probability $1 - q_x$).
*   $A_t$ (Additive Term): The "flow" component (e.g., $Premium - Charges$).

### Layer 1: The Rust Primitive (`scan_linear`)

Implement this generic plugin in `gaspatchio-core`.

```rust
/// Computes: out[t] = (out[t-1] * mult[t]) + add[t]
pub fn scan_linear(
    initial: &Series,  // Scalar initial state per policy
    multiply: &Series, // List column of multiplicative factors
    add: &Series       // List column of additive terms
) -> PolarsResult<Series>
```

**Why this wins:**
*   **Generic:** Handles AV rollforward, Reserve accumulation, Expense tracking, and Survival probabilities with one kernel.
*   **Fast:** The loop body is trivial and essentially free of branches.
*   **Composable:** Python manages the complexity.

In practice this should be exposed as a **Polars expression plugin** (taking
`&[Series]` and returning a single `Series`), not as a per-policy scalar
function. A few details that matter for correctness and composability:

- **Outer shape**
    - `initial` is a length‑N scalar series (one value per policy), with the
      usual Polars broadcasting behaviour when `len == 1`.
    - `multiply` and `add` are typically `List` series (one list per policy),
      and the scan runs independently within each row’s list.
- **Broadcasting**
    - For flexibility, `multiply` and `add` should also accept scalar‑per‑row
      series (or a single scalar for all rows) and broadcast those scalars
      across the inner lists, mirroring how `list_pow` broadcasts exponents
      today.
- **Null semantics**
    - You must choose and document explicit semantics. A reasonable default is:
        - `initial`: null → error or propagate a null output list for that row.
        - `multiply`: null → treat as multiplicative identity (`M_t = 1.0`), or
          hard‑error for strictness.
        - `add`: null → treat as additive identity (`A_t = 0.0`), or hard‑error.
    - Whatever you pick should be consistent with other `polars_functions`
      kernels and surfaced clearly in the Python docstrings.
- **Shape errors**
    - Within a row, the inner lengths of `multiply` and `add` need to agree, or
      you need an explicit truncation rule. The safest behaviour (and what
      `list_pow` does) is to **error on mismatched inner list lengths** rather
      than silently dropping values.

Implementation-wise, `scan_linear` will:

1. Take `initial`, `multiply`, `add` as `Series` and resolve scalar vs list
   representations plus any row/broadcast semantics.
2. Use `ListChunked::amortized_iter()` to iterate over policies.
3. For each policy, pull out the inner lists / scalars, then run a tight
   `for t in 0..len` loop with `state = state * M_t + A_t`, building a
   `Float64Chunked` for that row.
4. Collect the per‑row chunks into a `ListChunked` and return it as a `Series`.

### Layer 2: Python Composition

The Python `ProjectionAccessor` constructs the `M` and `A` vectors. This keeps the business logic in Python (where it is readable/auditable) and leaves only the raw crunching to Rust.

```python
# Python Side - "Rollforward" Implementation
def rollforward(self, initial, premiums, fees, interest_rate):
    # 1. Prepare the vectors in Python (vectorized, fast)
    #    We pre-calculate the 'net flow' and 'growth factor'
    #    This handles the 'timing' logic explicitly.
    
    # Example: Fees and Premiums happen BOP, Interest happens EOP
    # AV_t = (AV_{t-1} + Prem_t - Fee_t) * (1 + i_t)
    #      = AV_{t-1} * (1+i_t) + (Prem_t - Fee_t) * (1+i_t)
    
    growth_factor = 1 + interest_rate
    net_flow_grown = (premiums - fees) * growth_factor
    
    # 2. Call the generic Rust kernel
    return self._df.scan_linear(
        initial=initial,
        multiply=growth_factor,
        add=net_flow_grown
    )
```

### Layer 3: Handling "Complex" Dependencies

For logic that *cannot* be linearized (e.g., `COI = rate * max(0, SumAssured - AV_t)`), `scan_linear` is insufficient because $A_t$ depends on $State_t$.

We can group the non-linear cases into three buckets:

1.  **Piecewise-linear with simple branches.**
    * Example: `COI_t = rate_t * max(0, SumAssured - AV_t)` is linear on each
      side of the `AV_t < SA` threshold, with a simple boolean switch.
    * Future work here is a `scan_linear_with_branches` primitive that chooses
      between a small number of fixed linear update matrices per period based
      on cheap predicates on the current state.
2.  **Mildly implicit but well-behaved.**
    * Picard-style iteration is reasonable: run `scan_linear`, compute COI,
      re‑run with updated flows, and iterate to convergence.
    * The implementation must spell out convergence criteria (max iterations,
      tolerance) and stability assumptions; some highly leveraged UL/VA designs
      will not converge nicely.
3.  **Genuinely non-linear or path-dependent.**
    * For these, write a dedicated kernel (e.g., `scan_universal_life`) tailored
      to the product.
    * Longer‑term, a small bytecode / mini‑AST evaluated inside the loop is a
      way to keep flexibility without recompilation, but that should be treated
      as future work, not a requirement for v1.

---

## 5. Implementation Plan Updates

The implementation plan in `26-background.md` (Section 12) needs revision:

1.  **Revised Step 1:** Implement `scan_linear` in Rust instead of `account_value_scan`.
    *   Use `amortized_iter` for list traversal (crucial for performance).
    *   Design `scan_linear` so each row is independent and *can* be processed in
        parallel, but be cautious about adding rayon inside the plugin: Polars
        already manages thread‑level parallelism, so naive nested parallelism
        can oversubscribe threads. Start single‑threaded, profile, and add rayon
        only if it plays nicely with Polars’ plugin guidelines.
    *   **Strict, documented null handling:** The kernel should either error
        eagerly on unexpected nulls, or use explicit identity defaults
        ($M=1, A=0$) for `multiply`/`add`. The chosen behaviour must be
        documented and mirrored in the Python API.

2.  **Revised Step 2:** Update `ProjectionAccessor` in Python.
    *   Implement `rollforward` using `scan_linear` as the backend.
    *   Keep the `accumulate` method but implement it as a wrapper around `scan_linear` (or multiple passes of it) rather than a monolithic Rust call.

3.  **Verification:**
    *   Benchmark `scan_linear` vs the Python loop.
    *   Verify it can replicate the "Lifelib" results exactly.

## 6. Comparison with Peers

*   **JuliaActuary:** Uses Julia's ability to compile arbitrary loops on the fly. This allows "perfect" flexibility but requires the user to write Julia code.
*   **Gaspatchio:** Uses **Pre-compiled Kernels**. We trade "arbitrary logic" for "structured speed". By providing a powerful enough set of primitives (`scan_linear`, `scan_sum`, `scan_product`), we cover the actuarial domain space without forcing users to write Rust.

## Conclusion

The "Accumulator" approach is correct. The "Black Box" API is the danger. By shifting to **Linear Recurrence Primitives**, Gaspatchio remains generic, future-proof, and blazing fast.

