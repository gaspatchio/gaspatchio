# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: T201
"""Measured runner for the unified aggregation surface on the real L4 model.

Compares three ways of producing portfolio reporting figures from the L4
(reconciled-lifelib) VA model, at a given policy count:

* **baseline**  -- pure full projection (materialise every column): the same number
  the dev/model-bench dashboard tracks (wall, data_mb). The aggregation needed to
  check the batched path runs *outside* the timed region.
* **aggregated** -- ``run_aggregated(..., batch_size="auto")``: batch policies,
  fold each batch to per-period vectors, never co-resident.
* **spill**     -- ``run_to_parquet(..., batch_size="auto")``: the full-output
  path, batched and streamed to parquet (for callers that need every column).

It records wall time and *peak* process RSS (sampled in a background thread, so
the full-materialise peak is actually captured), and asserts the batched
aggregates equal the baseline aggregates. Importable by the benchmark driver and
the integration test; also runnable as a script for a quick local table.
"""

from __future__ import annotations

import gc
import importlib.util
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import polars as pl
import psutil

from gaspatchio_core import ActuarialFrame, run_aggregated, run_to_parquet
from gaspatchio_core.scenarios import PeriodSum, Sum

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType
    from typing import Self

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
L4_DIR = REPO_ROOT / "tutorial" / "level-4-lifelib" / "base"
L4_MODEL_PY = L4_DIR / "model.py"
L4_BASE_POINTS = L4_DIR / "model_points.parquet"
_GENERATE_PY = Path(__file__).resolve().parent / "generate_model_points.py"

# Per-period portfolio cashflows + scalar present values — a realistic reporting
# output. PeriodSum yields per-period (length n_periods) vectors; Sum yields one
# portfolio scalar.
_PERIOD_COLUMNS = ("net_cf", "claims", "premiums", "expenses")
_SCALAR_COLUMNS = ("pv_net_cf", "pv_claims")
_PERIOD = "__period"

def _load_module(path: Path, name: str) -> ModuleType:
    """Load a module from a file path (evals is not an importable package here)."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        msg = f"could not load module from {path}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_l4_cache: ModuleType | None = None
_gen_cache: ModuleType | None = None


def load_l4_model() -> ModuleType:
    """Load the L4 model module once (real ``__file__`` so its paths resolve)."""
    global _l4_cache  # noqa: PLW0603
    if _l4_cache is None:
        _l4_cache = _load_module(L4_MODEL_PY, "l4_aggbench_model")
    return _l4_cache


def l4_model_points(n: int, *, seed: int = 42) -> pl.DataFrame:
    """Return ``n`` L4 model points (8 base rows, or scaled-with-variation)."""
    base = pl.read_parquet(L4_BASE_POINTS)
    if n <= base.height:
        return base.head(n)
    global _gen_cache  # noqa: PLW0603
    if _gen_cache is None:
        _gen_cache = _load_module(_GENERATE_PY, "l4_aggbench_genmp")
    return _gen_cache.generate_model_points(base, n, seed=seed)


def make_model_fn(
    model: ModuleType,
) -> Callable[[ActuarialFrame], ActuarialFrame]:
    """Bind the L4 model's assumptions once so every batch reuses them.

    Loading assumptions per batch would unfairly penalise the batched path (and is
    not how a real caller would drive it); the global table registry treats the
    re-use as idempotent.
    """
    assumptions = model.load_assumptions()

    def model_fn(af: ActuarialFrame) -> ActuarialFrame:
        return model.main(af, assumptions_override=assumptions)

    return model_fn


def aggregations() -> list[object]:
    """Fresh list of aliased aggregators (accumulator state lives per-run, not here)."""
    aggs: list[object] = [PeriodSum(c).alias(c) for c in _PERIOD_COLUMNS]
    aggs += [Sum(c).alias(c) for c in _SCALAR_COLUMNS]
    return aggs


class _PeakRss:
    """Sample process RSS in a background thread; report peak over a region."""

    def __init__(self, interval_s: float = 0.015) -> None:
        self.interval_s = interval_s
        self._proc = psutil.Process()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.baseline = 0
        self.peak = 0

    def __enter__(self) -> Self:
        gc.collect()
        self.baseline = self._proc.memory_info().rss
        self.peak = self.baseline
        self._stop.clear()
        self._thread = threading.Thread(target=self._sample, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self.peak = max(self.peak, self._proc.memory_info().rss)

    def _sample(self) -> None:
        while not self._stop.is_set():
            self.peak = max(self.peak, self._proc.memory_info().rss)
            self._stop.wait(self.interval_s)

    @property
    def peak_mb(self) -> float:
        return round(max(0, self.peak - self.baseline) / (1024 * 1024), 1)


@dataclass(frozen=True)
class PathResult:
    """One measured path (baseline / aggregated / spill)."""

    label: str
    time_s: float
    peak_mb: float
    batch_size: int
    outputs: dict[str, object] = field(default_factory=dict)
    extra: dict[str, float] = field(default_factory=dict)


def _baseline_outputs(proj: pl.DataFrame) -> dict[str, object]:
    """Aggregate the full materialised projection the way the batched path does."""
    out: dict[str, object] = {}
    for col in _PERIOD_COLUMNS:
        series = (
            proj.lazy()
            .select(pl.col(col))
            .with_columns(pl.int_ranges(pl.col(col).list.len()).alias(_PERIOD))
            .explode([col, _PERIOD])
            .group_by(_PERIOD)
            .agg(pl.col(col).sum())
            .sort(_PERIOD)
            .collect()[col]
        )
        out[col] = series.to_numpy().astype(np.float64)
    for col in _SCALAR_COLUMNS:
        out[col] = float(proj[col].sum())
    return out


def _data_mb(df: pl.DataFrame) -> float:
    """List-column data footprint in MB (model-bench's deterministic data_mb)."""
    list_types = (
        pl.List(pl.Float64),
        pl.List(pl.Int64),
        pl.List(pl.Date),
        pl.List(pl.Datetime),
    )
    elements = 0
    for col in df.columns:
        if df[col].dtype in list_types:
            elements += int(df[col].list.len().sum() or 0)
    return round(elements * 8 / 1024 / 1024, 1)


def run_baseline(
    model_fn: Callable[[ActuarialFrame], ActuarialFrame], mp: pl.DataFrame
) -> PathResult:
    """Full projection, with the per-period fold timed separately.

    ``time_s`` is ONLY ``main`` + ``collect`` — the pure projection that
    ``dev/model-bench`` charts (wall / throughput / ``data_mb``). The aggregation
    (the explode + group_by every reporting figure needs) is timed on its own and
    exposed as ``extra['agg_wall_s'] = projection + fold`` — i.e. *materialise then
    aggregate*, the **fair** baseline for ``run_aggregated`` (which does the same
    work, batched). Peak stays on the projection to match model-bench.
    """
    with _PeakRss() as rss:
        t0 = time.perf_counter()
        proj = model_fn(ActuarialFrame(mp)).collect()
        proj_s = time.perf_counter() - t0
    t1 = time.perf_counter()
    outputs = _baseline_outputs(proj)  # the fold every reporting figure pays for
    fold_s = time.perf_counter() - t1
    extra = {
        "data_mb": _data_mb(proj),
        "fold_s": round(fold_s, 3),
        "agg_wall_s": round(proj_s + fold_s, 3),  # materialise-then-aggregate
    }
    del proj
    return PathResult(
        "baseline", round(proj_s, 3), rss.peak_mb, mp.height, outputs, extra
    )


def run_batched(
    model_fn: Callable[[ActuarialFrame], ActuarialFrame],
    mp: pl.DataFrame,
    *,
    batch_size: int | str = "auto",
) -> PathResult:
    """``run_aggregated`` — batch policies, fold each to per-period vectors."""
    with _PeakRss() as rss:
        t0 = time.perf_counter()
        res = run_aggregated(model_fn, mp, aggregations(), batch_size=batch_size)
        elapsed = time.perf_counter() - t0
    outputs: dict[str, object] = {
        c: np.asarray(getattr(res, c), dtype=np.float64) for c in _PERIOD_COLUMNS
    }
    for c in _SCALAR_COLUMNS:
        outputs[c] = float(getattr(res, c))
    extra = {
        "driver_peak_mb": res.peak_rss_mb or 0.0,
        "n_periods": float(res.n_periods),
    }
    return PathResult(
        "aggregated", round(elapsed, 3), rss.peak_mb, res.batch_size, outputs, extra
    )


def run_spill(
    model_fn: Callable[[ActuarialFrame], ActuarialFrame],
    mp: pl.DataFrame,
    out_dir: Path,
    *,
    batch_size: int | str = "auto",
) -> PathResult:
    """``run_to_parquet`` — full per-policy output, batched and streamed to disk."""
    with _PeakRss() as rss:
        t0 = time.perf_counter()
        res = run_to_parquet(model_fn, mp, out_dir, batch_size=batch_size)
        elapsed = time.perf_counter() - t0
    return PathResult(
        "spill",
        round(elapsed, 3),
        rss.peak_mb,
        mp.height // max(1, res.n_batches),
        extra={"n_batches": float(res.n_batches)},
    )


def outputs_match(
    a: dict[str, object], b: dict[str, object], *, rtol: float = 1e-9
) -> bool:
    """Return True if two output dicts agree (vectors close; scalars close)."""
    if set(a) != set(b):
        return False
    for key, av in a.items():
        bv = b[key]
        if isinstance(av, np.ndarray):
            if not np.allclose(av, np.asarray(bv), rtol=rtol):
                return False
        elif abs(float(av) - float(bv)) > rtol * max(1.0, abs(float(av))):  # type: ignore[arg-type]
            return False
    return True


@dataclass(frozen=True)
class ScaleComparison:
    """All three paths plus derived ratios + correctness for one policy count."""

    n_policies: int
    baseline: PathResult
    aggregated: PathResult
    spill: PathResult | None
    correct: bool

    @property
    def baseline_agg_wall(self) -> float:
        """Fair baseline wall: materialise-then-aggregate (projection + fold)."""
        return float(self.baseline.extra.get("agg_wall_s", self.baseline.time_s))

    @property
    def speedup(self) -> float:
        """FAIR speedup: materialise-then-aggregate / aggregated (>1 = batched wins).

        Compares like-for-like (both produce the aggregate figures), not against the
        pure projection that never does the fold.
        """
        if not self.aggregated.time_s:
            return 0.0
        return round(self.baseline_agg_wall / self.aggregated.time_s, 2)

    @property
    def memory_ratio(self) -> float:
        """Baseline peak / aggregated peak (>1 = aggregated lighter)."""
        if not self.aggregated.peak_mb:
            return 0.0
        return round(self.baseline.peak_mb / self.aggregated.peak_mb, 2)


def compare(n: int, *, include_spill: bool = True) -> ScaleComparison:
    """Run all three paths at ``n`` policies and check batched == baseline."""
    model = load_l4_model()
    model_fn = make_model_fn(model)
    mp = l4_model_points(n)

    baseline = run_baseline(model_fn, mp)
    aggregated = run_batched(model_fn, mp)
    correct = outputs_match(baseline.outputs, aggregated.outputs)

    spill: PathResult | None = None
    if include_spill:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="l4_spill_") as tmp:
            spill = run_spill(model_fn, mp, Path(tmp))

    return ScaleComparison(mp.height, baseline, aggregated, spill, correct)


def _print_table(cmp: ScaleComparison) -> None:
    verdict = "PASS" if cmp.correct else "FAIL"
    print(f"\n=== L4 @ {cmp.n_policies} policies — correctness: {verdict} ===")
    print(f"{'path':<18}{'wall_s':>10}{'peak_MB':>10}{'batch':>9}")
    print(
        f"{'baseline (proj)':<18}{cmp.baseline.time_s:>10}"
        f"{cmp.baseline.peak_mb:>10}{cmp.baseline.batch_size:>9}"
    )
    print(f"{'baseline+aggregate':<18}{cmp.baseline_agg_wall:>10}{'—':>10}{'—':>9}")
    print(
        f"{'aggregated':<18}{cmp.aggregated.time_s:>10}"
        f"{cmp.aggregated.peak_mb:>10}{cmp.aggregated.batch_size:>9}"
    )
    if cmp.spill is not None:
        print(
            f"{'spill':<18}{cmp.spill.time_s:>10}"
            f"{cmp.spill.peak_mb:>10}{cmp.spill.batch_size:>9}"
        )
    print(
        f"aggregated vs materialise-then-aggregate: "
        f"{cmp.speedup}x faster, {cmp.memory_ratio}x lighter"
    )


if __name__ == "__main__":
    import sys

    size = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000
    _print_table(compare(size))
