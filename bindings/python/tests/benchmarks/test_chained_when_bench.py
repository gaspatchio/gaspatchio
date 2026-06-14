# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Benchmark for chained scalar when() — unified reverse-fold vs native pl.when().

Two gate classes guard regressions at different scales:

- ``TestChainedWhenSlowdownGateAtScale`` is the **durable** regression
  guard: runs at ``N_LARGE = 1_000_000`` rows where Polars-engine work
  dominates Python construction overhead. The DSL/native ratio
  converges to ~0% at this scale (chain≥3 actually shows DSL slightly
  *faster* than native because reverse-fold produces a flatter plan than
  the chained ``pl.when().when()...`` builder). Any chain=10 ratio worse
  than +10% at n=1M signals a real per-row regression — not Python
  overhead, not CI noise.

- ``TestChainedWhenSlowdownGate`` is the **legacy** gate at n=100_000
  with a 45% ratio threshold. At n≤100K the test measures Python
  construction overhead as a percentage of native pl.when's
  sub-millisecond setup cost, so it's variance-dominated on CI runners.
  Kept for backward compat (it's useful as a smoke check on dev
  machines) but the at-scale gate is the canonical regression signal.

The literal fast-path in ``_shape_from_expr_dtype`` / ``_kind_from_dtype``
short-circuits ``pl.lit(...)`` operands before the
``select(expr).collect_schema()`` probe; what remains is fixed Python
proxy construction cost, which only matters when n is small.

The diagnostic ``benchmark`` fixtures (``TestChainedWhenBenchmarkSmall`` /
``TestChainedWhenBenchmarkLarge``) emit per-config numbers but do not
assert — the gate classes are the regression guards.
"""

from __future__ import annotations

import time

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame, when

pytestmark = pytest.mark.benchmark

PR1_SLOWDOWN_GATE = 0.45  # ≤ 45% slower than native — see module docstring for CI-variance rationale
AT_SCALE_GATE = 0.10  # ≤ 10% slower at n=1M — durable regression signal once Polars work dominates Python overhead


@pytest.fixture
def small_frame() -> tuple[ActuarialFrame, pl.LazyFrame]:
    """10K-row scalar frame for benchmark."""
    n = 10_000
    rows = list(range(n))
    af = ActuarialFrame({"x": rows})
    lf = pl.LazyFrame({"x": rows})
    return af, lf


@pytest.fixture
def large_frame() -> tuple[ActuarialFrame, pl.LazyFrame]:
    """100K-row scalar frame for benchmark."""
    n = 100_000
    rows = list(range(n))
    af = ActuarialFrame({"x": rows})
    lf = pl.LazyFrame({"x": rows})
    return af, lf


def _build_dsl_chain(af: ActuarialFrame, size: int) -> ActuarialFrame:
    builder = when(af.x < 0).then(0)
    for i in range(1, size):
        builder = builder.when(af.x < i * 100).then(i)
    af.bracket = builder.otherwise(size)
    return af


def _build_native_chain(lf: pl.LazyFrame, size: int) -> pl.LazyFrame:
    expr = pl.when(pl.col("x") < 0).then(0)
    for i in range(1, size):
        expr = expr.when(pl.col("x") < i * 100).then(i)
    return lf.select(expr.otherwise(size).alias("bracket"))


@pytest.mark.parametrize("size", [2, 3, 5, 10])
class TestChainedWhenBenchmarkSmall:
    def test_dsl_unified(self, benchmark, small_frame, size: int) -> None:
        af, _ = small_frame

        def run() -> pl.DataFrame:
            return _build_dsl_chain(af, size).collect()

        benchmark(run)

    def test_native_baseline(self, benchmark, small_frame, size: int) -> None:
        _, lf = small_frame

        def run() -> pl.DataFrame:
            return _build_native_chain(lf, size).collect()

        benchmark(run)


@pytest.mark.parametrize("size", [2, 3, 5, 10])
class TestChainedWhenBenchmarkLarge:
    def test_dsl_unified(self, benchmark, large_frame, size: int) -> None:
        af, _ = large_frame

        def run() -> pl.DataFrame:
            return _build_dsl_chain(af, size).collect()

        benchmark(run)

    def test_native_baseline(self, benchmark, large_frame, size: int) -> None:
        _, lf = large_frame

        def run() -> pl.DataFrame:
            return _build_native_chain(lf, size).collect()

        benchmark(run)


def _best_of(fn, runs: int) -> float:
    """Return min wall time over ``runs`` invocations."""
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        times.append(time.perf_counter() - start)
    return min(times)


@pytest.mark.parametrize("size", [2, 3, 5, 10])
class TestChainedWhenSlowdownGate:
    """Assert DSL chained ``when()`` slowdown vs native is within ``PR1_SLOWDOWN_GATE``.

    Uses ``time.perf_counter()`` best-of-N rather than the ``benchmark``
    fixture so we get a deterministic ratio inside a single test (the
    fixture-based benches are diagnostic-only).

    Warm-up: 5 runs to JIT/cache. Measurement: best of 30. Asserts on
    `(dsl - native) / native`; negative deltas (DSL faster) pass trivially.

    **Gate runs at n=100_000 only.** At n≤10_000 the native ``pl.when()`` is
    sub-millisecond, so fixed Python overhead in chain construction
    (proxy creation, ConditionExpression instantiation) dominates the
    ratio — chain=2 at 10K shows >100% slowdown but contributes <1ms of
    real wall-time, which is meaningless as a regression signal. The 10K
    runs stay as ``TestChainedWhenBenchmarkSmall`` diagnostics. Production
    actuarial models run at 100K+ rows where the percentage is meaningful.

    Rationale for the threshold: PR 2 deletes ``ColumnTypeDetector``,
    routes shape/kind through cached proxy properties, and short-circuits
    literal expressions (``pl.lit(...)``) before the plan probe. Measured
    local outcome at n=100_000 post-PR-3: chain=10 ~25%, chain=5 ~25%,
    chain=3 ~30%, chain=2 ~29%. The remaining gap is fixed Python
    construction cost (proxy/ConditionExpression instantiation) plus
    repeated probes of the same ``pl.col(name)`` operand across chain
    steps — neither addressed by the literal fast-path alone. Closing
    further (per-frame memoization or proxy-hot-path refactor) is
    queued as a follow-up perf task. The 45% gate gives ~15pp of CI
    margin over local; see module docstring for variance details.
    """

    N = 100_000

    WARMUP = 5
    RUNS = 30

    def test_dsl_within_slowdown_gate(self, size: int) -> None:
        rows = list(range(self.N))

        def run_dsl() -> pl.DataFrame:
            af = ActuarialFrame({"x": rows})
            return _build_dsl_chain(af, size).collect()

        def run_native() -> pl.DataFrame:
            lf = pl.LazyFrame({"x": rows})
            return _build_native_chain(lf, size).collect()

        for _ in range(self.WARMUP):
            run_dsl()
            run_native()

        dsl_t = _best_of(run_dsl, self.RUNS)
        native_t = _best_of(run_native, self.RUNS)
        slowdown = (dsl_t - native_t) / native_t

        assert slowdown <= PR1_SLOWDOWN_GATE, (
            f"DSL slowdown {slowdown * 100:.1f}% exceeds gate "
            f"{PR1_SLOWDOWN_GATE * 100:.0f}% at chain={size}, n={self.N} "
            f"(DSL {dsl_t * 1000:.2f}ms vs native {native_t * 1000:.2f}ms)"
        )


@pytest.mark.parametrize("size", [2, 3, 5, 10])
class TestChainedWhenSlowdownGateAtScale:
    """Durable regression gate at n=1M where Polars work dominates.

    At small n (≤100K), the DSL/native ratio is dominated by fixed
    Python construction cost — proxy/ConditionExpression creation,
    shape probes, dispatch routing — which is invariant in n. That
    overhead expressed as a percentage of native ``pl.when()``'s
    sub-millisecond setup cost is variance-prone on CI: a 0.5ms
    jitter on a 1ms baseline reads as 50pp swing in the gate.

    At n=1M, Polars-engine wall time is in the 15–25ms range, so
    that same Python overhead is one or two percent of total.
    Measured local outcome post-PR-101:

      chain=2  → +0.2%
      chain=3  → -5.0%   (DSL faster: reverse-fold flatter plan)
      chain=5  → -4.6%
      chain=10 → -17.7%

    A 10% gate at this scale catches real per-row regressions
    (anything that adds work inside the loop, e.g. an O(n) Python
    callback, a Polars planner cost regression in chained when, or
    an inadvertent eager collect) while staying robust to CI jitter.

    Wall time per parametrize case: ~150ms × (2 warmup + 5 measured) × 2
    expressions ≈ 2s, so the four chain sizes total under 10s.
    """

    N_LARGE = 1_000_000

    WARMUP = 2
    RUNS = 5

    def test_dsl_within_at_scale_gate(self, size: int) -> None:
        rows = list(range(self.N_LARGE))

        def run_dsl() -> pl.DataFrame:
            af = ActuarialFrame({"x": rows})
            return _build_dsl_chain(af, size).collect()

        def run_native() -> pl.DataFrame:
            lf = pl.LazyFrame({"x": rows})
            return _build_native_chain(lf, size).collect()

        for _ in range(self.WARMUP):
            run_dsl()
            run_native()

        dsl_t = _best_of(run_dsl, self.RUNS)
        native_t = _best_of(run_native, self.RUNS)
        slowdown = (dsl_t - native_t) / native_t

        assert slowdown <= AT_SCALE_GATE, (
            f"DSL slowdown {slowdown * 100:.1f}% exceeds at-scale gate "
            f"{AT_SCALE_GATE * 100:.0f}% at chain={size}, n={self.N_LARGE} "
            f"(DSL {dsl_t * 1000:.2f}ms vs native {native_t * 1000:.2f}ms)"
        )
