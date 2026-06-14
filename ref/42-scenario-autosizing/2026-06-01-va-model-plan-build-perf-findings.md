# VA-model throughput investigation — can we 2× the dashboard numbers?

Date: 2026-06-01 · Branch: `stage1/jagged-rollforward` · Scope: framework-level (not model)
changes to the L4 "VA Model (GMDB/GMAB)" benchmark that feeds the landing-page chart.

Method: one read-only analysis workflow (4 parallel lanes → synthesis) plus inline
profiling and spike code, all measured on the existing **release** extension.

## Headline

The benchmarked wall-time at the scales the dashboard emphasises (8 / 1K / 10K policies)
is **dominated by Python plan-build, not computation**. A single framework change to how
the schema is resolved during plan construction yields:

| scale | baseline | fixed | speedup |
|------:|---------:|------:|:-------:|
| 1K    | 4,930 pts/s | **12,949** | **2.63×** |
| 10K   | 30,263 pts/s | **49,424** | **1.63×** |
| 100K  | 23,464 pts/s | 24,559 | 1.05× |

Output is **byte-identical** across all 126 columns at every scale; 1,343 tests pass.

## What the experiments killed (both were the "obvious" big levers)

1. **"Build the extension in release" (synthesis ranked #1, est. 2–5×).** FALSE. The
   `[tool.uv] config-settings = "--profile=dev"` pin in `pyproject.toml:190` is **dead
   config** — captured `uv sync` (the CI path) invoking `cargo rustc --profile release`
   directly. The dashboard already measures a release build. (The dev pin is still worth
   fixing as a correctness/clarity issue, but it is not a perf win.)

2. **"Flat long-form Phase-3 representation" (synthesis ranked #3, est. 1.5–3×).** FALSE —
   it is **6.7× *slower*** end-to-end. The list-per-policy representation is well-chosen:
   each policy's list is a contiguous group, so `list.shift` / `list.eval(cum_prod)` are
   14–25× faster than the equivalent `.shift().over(pol)` / `.cum_prod().over(pol)` windows
   on a flat frame. Period-shift and cumulative-product dominate real projections, so
   long-form loses badly. (Proof: `/tmp/gsp_perf/longform_e2e.py`.)

Both top-ranked findings came from agents reading code; both fell to a measurement. The
real lever was the synthesis's **lowest**-ranked item (#6, est. 1.05–1.2×) — found only by
profiling the plan-build/collect split.

## The real lever: schema resolution during plan-build

`af.main()` builds an ~89-node `with_columns` LazyFrame. Splitting wall-time:

```
L4/1K : plan-build=169ms (83%)  collect=34ms   | 187 collect_schema() calls = 122ms
L4/10K: plan-build=187ms (54%)  collect=161ms  | (plan-build is fixed, data-independent)
```

Two sources, both attacked:

- **Shape probes (91× `column/shape.py`).** `_shape_from_expr_dtype` did
  `df.select(expr).collect_schema()` — re-resolving the whole growing plan just to learn
  one expr's scalar-vs-list shape (~400µs late in the build). Fix: resolve the expr against
  a **minimal frame built from only `expr.meta.root_names()`** (cached by root-set):
  400µs → ~20µs.
- **The `_df` setter (87× `frame/base.py`).** Resolved the full plan schema on *every*
  assignment — **783µs/call on the real plan** (plugin/list output-type resolution is
  expensive). Fix: **lazy `_schema`** (defer in the setter) + **incremental update** in
  `__setitem__` — resolve only the new column's dtype via the cheap minimal probe and
  append it. 783µs → ~20µs/assignment.

Net: `collect_schema` cost 122ms → **4.5ms**; plan-build 169ms → 45ms.

Files: `bindings/python/gaspatchio_core/frame/base.py`,
`bindings/python/gaspatchio_core/column/shape.py` (committed on
`perf/plan-build-schema-resolution`).

## Honest caveats

- **Scale.** This is a *fixed* ~130ms plan-build saving — huge at 8/1K/10K, ~1.05× at 100K
  (where collect is ~4s). To move the **100K** number you need collect-side Rust kernel
  work, not this.
- **Micro-regression (resolved).** The minimal-frame probe is cheaper on deep plans but
  ~10–113µs *dearer* on trivial shallow frames (it grew with chain length). Fixed by
  gating both fast paths behind a column-count threshold (`_MINIMAL_PROBE_MIN_COLS` /
  `_INCREMENTAL_SCHEMA_MIN_COLS = 16`): shallow plans keep the original cheap deep probe.
  Chained-`when` construction is now within ±20µs of baseline (noise); the legacy
  `TestChainedWhenSlowdownGate` (n=100K, documented-noisy) trips on baseline too under
  load, and the canonical at-scale gate (n=1M) passes for both.

## Remaining levers for the collect-side / 100K (analysed, not yet built/measured)

Each needs a Rust rebuild; expectations are the lanes' estimates, unverified:
- List kernels (`list_conditional`/`list_pow`/`list_clip`/`accumulate`) skip the redundant
  per-row `cast(Float64)` + `Vec<Option<f64>>` allocation → ~1.1–1.3×.
- Lookup kernel: drop eager `rechunk` on contiguous explode + reuse shared age/duration key
  encodings across the ~10 lookups → ~1.1–1.3×.
- `[profile.release]` tuning (`lto="thin"`, `codegen-units=1`) — none exists today → ~1.1×.

These stack toward maybe ~1.5× at 100K, not a clean 2×.

## Reproduce

`/tmp/gsp_perf/` — `split.py` (plan-build/collect split + schema-call count),
`baseline.py` (throughput + checksum), `longform_e2e.py` (representation disproof),
`resolve_cost.py` (resolution-primitive costs), `fullcheck.py` (full-output equality).
Workflow: `ref/42-scenario-autosizing/perf-map-workflow.js`.
