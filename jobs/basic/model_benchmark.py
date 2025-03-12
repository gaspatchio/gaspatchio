import sys
import time
from pathlib import Path

import pandas as pd
import typer
from typing_extensions import Annotated

# Add the project root to the path so we can import from jobs
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from jobs.basic.model import (
    run_model,
    run_model_with_dsl,
    run_model_with_pythonic_dsl,
)
from model_core_exp.core import read_model_points


def benchmark(
    size: Annotated[str, typer.Option("--size", help="Size of dataset")] = "smol",
    runs: Annotated[int, typer.Option("--runs", help="Number of runs")] = 5,
):
    """Benchmark the different model approaches."""
    results = []
    file_path = f"jobs/basic/model-points-{size}.parquet"

    print(f"Benchmarking with {size} dataset, {runs} runs each")
    print("-" * 50)

    # Get the data
    df = read_model_points(file_path)

    # Standard approach
    times_standard = []
    for i in range(runs):
        start = time.time()
        result = run_model(df).collect()
        end = time.time()
        times_standard.append(end - start)

    avg_standard = sum(times_standard) / len(times_standard)
    results.append(
        {
            "Method": "Standard Polars",
            "Average Time (s)": avg_standard,
            "Records": len(result),
            "Time per Record (μs)": (avg_standard * 1e6) / len(result),
        }
    )

    # Original DSL approach
    times_dsl = []
    for i in range(runs):
        start = time.time()
        result = run_model_with_dsl(df).collect()
        end = time.time()
        times_dsl.append(end - start)

    avg_dsl = sum(times_dsl) / len(times_dsl)
    results.append(
        {
            "Method": "Original DSL",
            "Average Time (s)": avg_dsl,
            "Records": len(result),
            "Time per Record (μs)": (avg_dsl * 1e6) / len(result),
        }
    )

    # Pythonic DSL approach
    times_pythonic = []
    for i in range(runs):
        start = time.time()
        result = run_model_with_pythonic_dsl(df).collect()
        end = time.time()
        times_pythonic.append(end - start)

    avg_pythonic = sum(times_pythonic) / len(times_pythonic)
    results.append(
        {
            "Method": "Pythonic DSL",
            "Average Time (s)": avg_pythonic,
            "Records": len(result),
            "Time per Record (μs)": (avg_pythonic * 1e6) / len(result),
        }
    )

    # Convert to DataFrame for nice display
    df_results = pd.DataFrame(results)

    # Display the results
    print("\nPerformance Results:")
    print(df_results.to_string(index=False))

    # Display relative performance
    baseline = avg_standard
    print("\nRelative Performance (compared to Standard Polars):")
    print("Standard Polars: 1.00x")
    print(f"Original DSL: {avg_dsl/baseline:.2f}x")
    print(f"Pythonic DSL: {avg_pythonic/baseline:.2f}x")


if __name__ == "__main__":
    app = typer.Typer()
    app.command()(benchmark)
    app()
