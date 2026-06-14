# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Performance benchmark tests for scenario functionality.
# ABOUTME: Measures scenario expansion and full model execution at various scales.

"""Performance benchmark tests for scenario functionality."""

import importlib.util
import sys
import types
from itertools import batched
from pathlib import Path

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.scenarios import with_scenarios

# Path to test data
SCRATCH_DIR = Path(__file__).parent.parent / "scratch" / "scenarios"
ASSUMPTIONS_DIR = SCRATCH_DIR / "assumptions"


def load_scratch_module(name: str) -> types.ModuleType:
    """Dynamically load a module from the scratch directory."""
    # Ensure scratch dir is in path
    scratch_str = str(SCRATCH_DIR)
    if scratch_str not in sys.path:
        sys.path.insert(0, scratch_str)

    spec = importlib.util.spec_from_file_location(name, SCRATCH_DIR / f"{name}.py")
    if spec is None or spec.loader is None:
        msg = f"Could not load {name}"
        raise ImportError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def model_points_small() -> pl.DataFrame:
    """Load small model points (8 policies)."""
    return pl.read_parquet(SCRATCH_DIR / "model_points.parquet")


@pytest.fixture
def model_points_1k() -> pl.DataFrame:
    """Load 1k model points."""
    return pl.read_parquet(SCRATCH_DIR / "model_points_1k.parquet")


@pytest.fixture
def model_points_10k() -> pl.DataFrame:
    """Load 10k model points."""
    return pl.read_parquet(SCRATCH_DIR / "model_points_10k.parquet")


@pytest.fixture
def model_points_100k() -> pl.DataFrame:
    """Load 100k model points."""
    return pl.read_parquet(SCRATCH_DIR / "model_points_100k.parquet")


class TestScenarioExpansionBenchmarks:
    """Benchmark tests for scenario expansion performance."""

    @pytest.mark.benchmark(group="scenario-expansion")
    def test_expand_small_x_100_scenarios(
        self, benchmark, model_points_small: pl.DataFrame
    ) -> None:
        """Benchmark: 8 policies x 100 scenarios = 800 rows."""
        scenarios = list(range(1, 101))

        def run_expansion() -> pl.DataFrame:
            af = ActuarialFrame(model_points_small)
            af = with_scenarios(af, scenarios)
            return af.collect()

        result = benchmark(run_expansion)
        assert len(result) == 8 * 100

    @pytest.mark.benchmark(group="scenario-expansion")
    def test_expand_1k_x_100_scenarios(
        self, benchmark, model_points_1k: pl.DataFrame
    ) -> None:
        """Benchmark: 1k policies x 100 scenarios = 100k rows."""
        scenarios = list(range(1, 101))

        def run_expansion() -> pl.DataFrame:
            af = ActuarialFrame(model_points_1k)
            af = with_scenarios(af, scenarios)
            return af.collect()

        result = benchmark(run_expansion)
        assert len(result) == 1000 * 100

    @pytest.mark.benchmark(group="scenario-expansion")
    def test_expand_10k_x_100_scenarios(
        self, benchmark, model_points_10k: pl.DataFrame
    ) -> None:
        """Benchmark: 10k policies x 100 scenarios = 1M rows."""
        scenarios = list(range(1, 101))

        def run_expansion() -> pl.DataFrame:
            af = ActuarialFrame(model_points_10k)
            af = with_scenarios(af, scenarios)
            return af.collect()

        result = benchmark(run_expansion)
        assert len(result) == 10000 * 100


class TestFullModelBenchmarks:
    """Benchmark tests for full model execution with scenarios."""

    @pytest.mark.benchmark(group="full-model")
    def test_full_model_small_x_100_scenarios(
        self, benchmark, model_points_small: pl.DataFrame
    ) -> None:
        """Benchmark: Full GMXB model with 8 policies x 100 scenarios."""
        model_module = load_scratch_module("model_applied_life")
        stochastic_module = load_scratch_module("stochastic_scenarios")

        run_model = model_module.main
        generate_stochastic_returns = stochastic_module.generate_stochastic_returns

        stochastic_returns = generate_stochastic_returns(
            n_scenarios=100, n_months=180, seed=12345
        )

        scenarios = list(range(1, 101))

        def run_full_model() -> pl.DataFrame:
            af = ActuarialFrame(model_points_small)
            af = with_scenarios(af, scenarios)
            result_af = run_model(af, scenario_returns_override=stochastic_returns)
            return result_af.collect()

        result = benchmark(run_full_model)
        assert len(result) == 8 * 100
        assert "pv_net_cf" in result.columns


class TestMemoryBenchmarks:
    """Memory profiling tests for scenario functionality.

    Run with: uv run pytest -m benchmark --memray
    """

    @pytest.mark.benchmark(group="memory-expansion")
    def test_memory_expansion_small_x_10(
        self, model_points_small: pl.DataFrame
    ) -> None:
        """Memory: 8 policies x 10 scenarios = 80 rows."""
        scenarios = list(range(1, 11))
        af = ActuarialFrame(model_points_small)
        af = with_scenarios(af, scenarios)
        result = af.collect()
        assert len(result) == 8 * 10

    @pytest.mark.benchmark(group="memory-expansion")
    def test_memory_expansion_small_x_100(
        self, model_points_small: pl.DataFrame
    ) -> None:
        """Memory: 8 policies x 100 scenarios = 800 rows."""
        scenarios = list(range(1, 101))
        af = ActuarialFrame(model_points_small)
        af = with_scenarios(af, scenarios)
        result = af.collect()
        assert len(result) == 8 * 100

    @pytest.mark.benchmark(group="memory-expansion")
    def test_memory_expansion_1k_x_10(self, model_points_1k: pl.DataFrame) -> None:
        """Memory: 1k policies x 10 scenarios = 10k rows."""
        scenarios = list(range(1, 11))
        af = ActuarialFrame(model_points_1k)
        af = with_scenarios(af, scenarios)
        result = af.collect()
        assert len(result) == 1000 * 10

    @pytest.mark.benchmark(group="memory-expansion")
    def test_memory_expansion_1k_x_100(self, model_points_1k: pl.DataFrame) -> None:
        """Memory: 1k policies x 100 scenarios = 100k rows."""
        scenarios = list(range(1, 101))
        af = ActuarialFrame(model_points_1k)
        af = with_scenarios(af, scenarios)
        result = af.collect()
        assert len(result) == 1000 * 100

    @pytest.mark.benchmark(group="memory-expansion")
    def test_memory_expansion_10k_x_10(self, model_points_10k: pl.DataFrame) -> None:
        """Memory: 10k policies x 10 scenarios = 100k rows."""
        scenarios = list(range(1, 11))
        af = ActuarialFrame(model_points_10k)
        af = with_scenarios(af, scenarios)
        result = af.collect()
        assert len(result) == 10000 * 10

    @pytest.mark.benchmark(group="memory-expansion")
    def test_memory_expansion_10k_x_100(self, model_points_10k: pl.DataFrame) -> None:
        """Memory: 10k policies x 100 scenarios = 1M rows."""
        scenarios = list(range(1, 101))
        af = ActuarialFrame(model_points_10k)
        af = with_scenarios(af, scenarios)
        result = af.collect()
        assert len(result) == 10000 * 100


class TestFullModelMemory:
    """Memory tests for full model at incremental scales.

    Run with: uv run pytest -m benchmark --memray -k "TestFullModelMemory"
    """

    @pytest.mark.benchmark(group="memory-model")
    def test_memory_model_small_x_10(self, model_points_small: pl.DataFrame) -> None:
        """Memory: Full model 8 policies x 10 scenarios = 80 rows."""
        model_module = load_scratch_module("model_applied_life")
        stochastic_module = load_scratch_module("stochastic_scenarios")

        run_model = model_module.main
        generate_returns = stochastic_module.generate_stochastic_returns

        stochastic_returns = generate_returns(n_scenarios=10, n_months=180, seed=12345)
        scenarios = list(range(1, 11))

        af = ActuarialFrame(model_points_small)
        af = with_scenarios(af, scenarios)
        result_af = run_model(af, scenario_returns_override=stochastic_returns)
        result = result_af.collect()

        assert len(result) == 8 * 10
        assert "pv_net_cf" in result.columns

    @pytest.mark.benchmark(group="memory-model")
    def test_memory_model_small_x_100(self, model_points_small: pl.DataFrame) -> None:
        """Memory: Full model 8 policies x 100 scenarios = 800 rows."""
        model_module = load_scratch_module("model_applied_life")
        stochastic_module = load_scratch_module("stochastic_scenarios")

        run_model = model_module.main
        generate_returns = stochastic_module.generate_stochastic_returns

        stochastic_returns = generate_returns(n_scenarios=100, n_months=180, seed=12345)
        scenarios = list(range(1, 101))

        af = ActuarialFrame(model_points_small)
        af = with_scenarios(af, scenarios)
        result_af = run_model(af, scenario_returns_override=stochastic_returns)
        result = result_af.collect()

        assert len(result) == 8 * 100
        assert "pv_net_cf" in result.columns

    @pytest.mark.benchmark(group="memory-model")
    def test_memory_model_1k_x_10(self, model_points_1k: pl.DataFrame) -> None:
        """Memory: Full model 1k policies x 10 scenarios = 10k rows."""
        model_module = load_scratch_module("model_applied_life")
        stochastic_module = load_scratch_module("stochastic_scenarios")

        run_model = model_module.main
        generate_returns = stochastic_module.generate_stochastic_returns

        stochastic_returns = generate_returns(n_scenarios=10, n_months=180, seed=12345)
        scenarios = list(range(1, 11))

        af = ActuarialFrame(model_points_1k)
        af = with_scenarios(af, scenarios)
        result_af = run_model(af, scenario_returns_override=stochastic_returns)
        result = result_af.collect()

        assert len(result) == 1000 * 10
        assert "pv_net_cf" in result.columns

    @pytest.mark.benchmark(group="memory-model")
    def test_memory_model_1k_x_50(self, model_points_1k: pl.DataFrame) -> None:
        """Memory: Full model 1k policies x 50 scenarios = 50k rows."""
        model_module = load_scratch_module("model_applied_life")
        stochastic_module = load_scratch_module("stochastic_scenarios")

        run_model = model_module.main
        generate_returns = stochastic_module.generate_stochastic_returns

        stochastic_returns = generate_returns(n_scenarios=50, n_months=180, seed=12345)
        scenarios = list(range(1, 51))

        af = ActuarialFrame(model_points_1k)
        af = with_scenarios(af, scenarios)
        result_af = run_model(af, scenario_returns_override=stochastic_returns)
        result = result_af.collect()

        assert len(result) == 1000 * 50
        assert "pv_net_cf" in result.columns

    @pytest.mark.benchmark(group="memory-model")
    def test_memory_model_1k_x_100(self, model_points_1k: pl.DataFrame) -> None:
        """Memory: Full model 1k policies x 100 scenarios = 100k rows."""
        model_module = load_scratch_module("model_applied_life")
        stochastic_module = load_scratch_module("stochastic_scenarios")

        run_model = model_module.main
        generate_returns = stochastic_module.generate_stochastic_returns

        stochastic_returns = generate_returns(n_scenarios=100, n_months=180, seed=12345)
        scenarios = list(range(1, 101))

        af = ActuarialFrame(model_points_1k)
        af = with_scenarios(af, scenarios)
        result_af = run_model(af, scenario_returns_override=stochastic_returns)
        result = result_af.collect()

        assert len(result) == 1000 * 100
        assert "pv_net_cf" in result.columns


class TestStreamingComparison:
    """Compare streaming vs non-streaming for expansion only.

    Note: Full model can't stream due to cumulative operations (cum_prod, etc).
    """

    @pytest.mark.benchmark(group="memory-streaming")
    def test_streaming_expansion_10k_x_100(
        self, model_points_10k: pl.DataFrame
    ) -> None:
        """Memory: Streaming expansion 10k x 100 = 1M rows."""
        scenarios = list(range(1, 101))

        # Use ActuarialFrame with streaming via engine parameter
        lf = model_points_10k.lazy()
        af = ActuarialFrame(lf)
        af = with_scenarios(af, scenarios)

        # Collect with streaming engine
        result = af.collect(engine="streaming")

        assert len(result) == 10000 * 100

    @pytest.mark.benchmark(group="memory-streaming")
    def test_non_streaming_expansion_10k_x_100(
        self, model_points_10k: pl.DataFrame
    ) -> None:
        """Memory: Non-streaming expansion 10k x 100 = 1M rows (baseline)."""
        scenarios = list(range(1, 101))

        lf = model_points_10k.lazy()
        af = ActuarialFrame(lf)
        af = with_scenarios(af, scenarios)

        # Collect without streaming (default)
        result = af.collect()

        assert len(result) == 10000 * 100


class TestBatchAPIBenchmarks:
    """Benchmark tests verifying batched scenario execution bounds memory.

    Note: The pre-GSP-100 ``batch_scenarios`` helper has been retired in favour
    of ``for_each_scenario(batch_size=N)``. These benchmarks still chunk a
    scenario-id list explicitly via ``itertools.batched`` to drive the
    classic batch-and-aggregate pattern.
    """

    @pytest.mark.benchmark(group="batch-api")
    def test_batched_model_1k_x_100_in_batches_of_10(
        self, model_points_1k: pl.DataFrame
    ) -> None:
        """Memory: Batched model 1k x 100 scenarios in 10 batches of 10.

        This should use significantly less peak memory than processing
        all 100 scenarios at once, since we aggregate per-batch.
        """
        model_module = load_scratch_module("model_applied_life")
        stochastic_module = load_scratch_module("stochastic_scenarios")

        run_model = model_module.main
        generate_returns = stochastic_module.generate_stochastic_returns

        all_scenarios = list(range(1, 101))
        batch_aggregates = []

        for batch_tuple in batched(all_scenarios, 10):
            batch_ids = list(batch_tuple)
            # Generate returns only for this batch
            stochastic_returns = generate_returns(
                n_scenarios=len(batch_ids), n_months=180, seed=12345 + batch_ids[0]
            )

            af = ActuarialFrame(model_points_1k)
            af = with_scenarios(af, batch_ids)
            result_af = run_model(af, scenario_returns_override=stochastic_returns)
            result = result_af.collect()

            # Aggregate this batch (reduces memory before next batch)
            batch_agg = result.group_by("scenario_id").agg(
                pl.col("pv_net_cf").sum().alias("total_pv_net_cf")
            )
            batch_aggregates.append(batch_agg)

        # Combine all batch aggregates
        all_results = pl.concat(batch_aggregates)
        assert len(all_results) == 100  # One row per scenario

    @pytest.mark.benchmark(group="batch-api")
    def test_batched_model_1k_x_100_in_batches_of_50(
        self, model_points_1k: pl.DataFrame
    ) -> None:
        """Memory: Batched model 1k x 100 scenarios in 2 batches of 50.

        Larger batches = fewer iterations, but more memory per batch.
        """
        model_module = load_scratch_module("model_applied_life")
        stochastic_module = load_scratch_module("stochastic_scenarios")

        run_model = model_module.main
        generate_returns = stochastic_module.generate_stochastic_returns

        all_scenarios = list(range(1, 101))
        batch_aggregates = []

        for batch_tuple in batched(all_scenarios, 50):
            batch_ids = list(batch_tuple)
            stochastic_returns = generate_returns(
                n_scenarios=len(batch_ids), n_months=180, seed=12345 + batch_ids[0]
            )

            af = ActuarialFrame(model_points_1k)
            af = with_scenarios(af, batch_ids)
            result_af = run_model(af, scenario_returns_override=stochastic_returns)
            result = result_af.collect()

            batch_agg = result.group_by("scenario_id").agg(
                pl.col("pv_net_cf").sum().alias("total_pv_net_cf")
            )
            batch_aggregates.append(batch_agg)

        all_results = pl.concat(batch_aggregates)
        assert len(all_results) == 100


class TestBatchedVsUnbatched:
    """Compare memory usage between batched and unbatched approaches.

    The key insight: batched processing with intermediate aggregation
    keeps peak memory bounded to batch_size * policies, not total scenarios.
    """

    @pytest.mark.benchmark(group="batch-comparison")
    def test_unbatched_baseline_1k_x_100(self, model_points_1k: pl.DataFrame) -> None:
        """Memory baseline: 1k x 100 scenarios without batching = 5.7 GiB peak."""
        model_module = load_scratch_module("model_applied_life")
        stochastic_module = load_scratch_module("stochastic_scenarios")

        run_model = model_module.main
        generate_returns = stochastic_module.generate_stochastic_returns

        stochastic_returns = generate_returns(n_scenarios=100, n_months=180, seed=12345)
        scenarios = list(range(1, 101))

        af = ActuarialFrame(model_points_1k)
        af = with_scenarios(af, scenarios)
        result_af = run_model(af, scenario_returns_override=stochastic_returns)
        result = result_af.collect()

        # Aggregate after all computation
        aggregated = result.group_by("scenario_id").agg(
            pl.col("pv_net_cf").sum().alias("total_pv_net_cf")
        )
        assert len(aggregated) == 100

    @pytest.mark.benchmark(group="batch-comparison")
    def test_batched_1k_x_100_batch_size_10(
        self, model_points_1k: pl.DataFrame
    ) -> None:
        """Memory: Batched 1k x 100 with batch_size=10.

        Expected peak memory: ~570 MiB (10x less than unbatched).
        """
        model_module = load_scratch_module("model_applied_life")
        stochastic_module = load_scratch_module("stochastic_scenarios")

        run_model = model_module.main
        generate_returns = stochastic_module.generate_stochastic_returns

        all_scenarios = list(range(1, 101))
        batch_aggregates = []

        for batch_tuple in batched(all_scenarios, 10):
            batch_ids = list(batch_tuple)
            stochastic_returns = generate_returns(
                n_scenarios=len(batch_ids), n_months=180, seed=12345 + batch_ids[0]
            )

            af = ActuarialFrame(model_points_1k)
            af = with_scenarios(af, batch_ids)
            result_af = run_model(af, scenario_returns_override=stochastic_returns)
            result = result_af.collect()

            batch_agg = result.group_by("scenario_id").agg(
                pl.col("pv_net_cf").sum().alias("total_pv_net_cf")
            )
            batch_aggregates.append(batch_agg)
            # Explicitly clear large intermediate (Python GC)
            del result, result_af

        all_results = pl.concat(batch_aggregates)
        assert len(all_results) == 100


class TestSinkThenStream:
    """Test the sink-then-stream pattern for flexible post-hoc aggregation.

    Pattern:
    1. Run model in batches, sink full results to parquet files
    2. Later, scan all files and aggregate with streaming engine
       (streaming works because aggregation has no cum_prod/previous_period)
    """

    @pytest.mark.benchmark(group="sink-stream")
    def test_sink_then_stream_1k_x_100(
        self, model_points_1k: pl.DataFrame, tmp_path: Path
    ) -> None:
        """Memory: Sink full results then stream-aggregate.

        This pattern is more flexible than batch-aggregate because
        you can do any aggregation later, not locked in upfront.
        """
        model_module = load_scratch_module("model_applied_life")
        stochastic_module = load_scratch_module("stochastic_scenarios")

        run_model = model_module.main
        generate_returns = stochastic_module.generate_stochastic_returns

        all_scenarios = list(range(1, 101))
        output_dir = tmp_path / "scenario_results"
        output_dir.mkdir()

        # Phase 1: Run model in batches, sink full results to parquet
        for batch_num, batch_tuple in enumerate(batched(all_scenarios, 10)):
            batch_ids = list(batch_tuple)
            stochastic_returns = generate_returns(
                n_scenarios=len(batch_ids), n_months=180, seed=12345 + batch_ids[0]
            )

            af = ActuarialFrame(model_points_1k)
            af = with_scenarios(af, batch_ids)
            result_af = run_model(af, scenario_returns_override=stochastic_returns)

            # Sink full projection to parquet (not just aggregates)
            result_df = result_af.collect()
            result_df.write_parquet(output_dir / f"batch_{batch_num:04d}.parquet")

            # Clear memory before next batch
            del result_df, result_af

        # Phase 2: Stream-aggregate from files
        # This works because group_by/sum has no cumulative operations!
        aggregated = (
            pl.scan_parquet(output_dir / "*.parquet")
            .group_by("scenario_id")
            .agg(pl.col("pv_net_cf").sum().alias("total_pv_net_cf"))
            .collect(engine="streaming")
        )

        assert len(aggregated) == 100

    @pytest.mark.benchmark(group="sink-stream")
    def test_sink_then_multiple_aggregations(
        self, model_points_1k: pl.DataFrame, tmp_path: Path
    ) -> None:
        """Demonstrate flexibility: multiple different aggregations from same sink.

        Once data is on disk, you can run any aggregation you want
        without re-running the model.
        """
        model_module = load_scratch_module("model_applied_life")
        stochastic_module = load_scratch_module("stochastic_scenarios")

        run_model = model_module.main
        generate_returns = stochastic_module.generate_stochastic_returns

        # Use fewer scenarios for this test (faster)
        all_scenarios = list(range(1, 21))  # 20 scenarios
        output_dir = tmp_path / "scenario_results_multi"
        output_dir.mkdir()

        # Phase 1: Sink results
        for batch_num, batch_tuple in enumerate(batched(all_scenarios, 10)):
            batch_ids = list(batch_tuple)
            stochastic_returns = generate_returns(
                n_scenarios=len(batch_ids), n_months=180, seed=12345 + batch_ids[0]
            )

            af = ActuarialFrame(model_points_1k)
            af = with_scenarios(af, batch_ids)
            result_af = run_model(af, scenario_returns_override=stochastic_returns)
            result_df = result_af.collect()
            result_df.write_parquet(output_dir / f"batch_{batch_num:04d}.parquet")
            del result_df, result_af

        # Phase 2: Multiple different aggregations from same data
        base_scan = pl.scan_parquet(output_dir / "*.parquet")

        # Aggregation 1: Sum by scenario
        by_scenario = (
            base_scan.group_by("scenario_id")
            .agg(pl.col("pv_net_cf").sum().alias("total_pv"))
            .collect(engine="streaming")
        )
        assert len(by_scenario) == 20

        # Aggregation 2: Mean by scenario
        means = (
            base_scan.group_by("scenario_id")
            .agg(pl.col("pv_net_cf").mean().alias("mean_pv"))
            .collect(engine="streaming")
        )
        assert len(means) == 20

        # Aggregation 3: Percentiles across all scenarios
        percentiles = base_scan.select(
            pl.col("pv_net_cf").quantile(0.95).alias("p95")
        ).collect(engine="streaming")
        assert len(percentiles) == 1

    @pytest.mark.benchmark(group="sink-stream-scale")
    def test_sink_then_stream_10k_x_100(
        self, model_points_10k: pl.DataFrame, tmp_path: Path
    ) -> None:
        """Memory: Sink-then-stream at scale: 10k x 100 = 1M rows.

        Expected disk usage: ~19 GB
        Expected peak memory: ~1-2 GiB per batch (batch_size=10)
        """
        model_module = load_scratch_module("model_applied_life")
        stochastic_module = load_scratch_module("stochastic_scenarios")

        run_model = model_module.main
        generate_returns = stochastic_module.generate_stochastic_returns

        all_scenarios = list(range(1, 101))
        output_dir = tmp_path / "scenario_results_10k"
        output_dir.mkdir()

        # Phase 1: Run model in batches, sink full results to parquet
        for batch_num, batch_tuple in enumerate(batched(all_scenarios, 10)):
            batch_ids = list(batch_tuple)
            stochastic_returns = generate_returns(
                n_scenarios=len(batch_ids), n_months=180, seed=12345 + batch_ids[0]
            )

            af = ActuarialFrame(model_points_10k)
            af = with_scenarios(af, batch_ids)
            result_af = run_model(af, scenario_returns_override=stochastic_returns)

            result_df = result_af.collect()
            result_df.write_parquet(output_dir / f"batch_{batch_num:04d}.parquet")

            del result_df, result_af

        # Phase 2: Stream-aggregate from files
        aggregated = (
            pl.scan_parquet(output_dir / "*.parquet")
            .group_by("scenario_id")
            .agg(pl.col("pv_net_cf").sum().alias("total_pv_net_cf"))
            .collect(engine="streaming")
        )

        assert len(aggregated) == 100


class TestLargeModelPointsBenchmarks:
    """Benchmark tests for large model point counts with few scenarios.

    This tests the opposite scaling dimension: many policies, few scenarios.
    Closer to deterministic valuation workloads (many policies, few stress scenarios).
    """

    @pytest.mark.benchmark(group="large-mp")
    def test_full_model_100k_x_3(self, model_points_100k: pl.DataFrame) -> None:
        """Memory: Full model 100k policies x 3 scenarios = 300k rows.

        Tests scaling on the model point dimension rather than scenario dimension.
        """
        model_module = load_scratch_module("model_applied_life")
        stochastic_module = load_scratch_module("stochastic_scenarios")

        run_model = model_module.main
        generate_returns = stochastic_module.generate_stochastic_returns

        # Only 3 scenarios (like BASE, UP, DOWN stress scenarios)
        stochastic_returns = generate_returns(n_scenarios=3, n_months=180, seed=12345)
        scenarios = list(range(1, 4))

        af = ActuarialFrame(model_points_100k)
        af = with_scenarios(af, scenarios)
        result_af = run_model(af, scenario_returns_override=stochastic_returns)
        result = result_af.collect()

        assert len(result) == 100000 * 3
        assert "pv_net_cf" in result.columns

        # Aggregate by scenario
        aggregated = result.group_by("scenario_id").agg(
            pl.col("pv_net_cf").sum().alias("total_pv_net_cf")
        )
        assert len(aggregated) == 3
