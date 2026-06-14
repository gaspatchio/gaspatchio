# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
L5 Typed-vs-Untyped Benchmark Harness

Compares ``level-5-scenarios/base`` (untyped L5) against
``level-5-scenarios-typed/base`` (typed L5 — MortalityTable + Curve + Schedule)
across three model-point scales: 8, 1000, 10000 points.

Each (model, scale) pair runs 3 times.  Per-run measurements:

- Wall-clock time via ``time.perf_counter()``
- Peak process RSS via ``resource.getrusage(resource.RUSAGE_SELF).ru_maxrss``
  On macOS ``ru_maxrss`` is in bytes; divide by 1024**2 for MB.
  On Linux it is in kilobytes; divide by 1024 for MB.

Memory caveat: ``getrusage`` gives peak RSS since process start, not just for
a single run.  The reported "peak_rss_mb" is the running maximum, which
means later runs accumulate earlier allocations.  This is appropriate for a
"what is the memory envelope of this model" question.

Run with:
    uv run python tutorial/level-5-scenarios-typed/benchmark.py

Output:
    tutorial/level-5-scenarios-typed/report/benchmark.md
    tutorial/level-5-scenarios-typed/report/throughput.png
    tutorial/level-5-scenarios-typed/report/memory.png
"""

from __future__ import annotations

import gc
import importlib.util
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import altair as alt
import polars as pl
from loguru import logger

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.scenarios import with_scenarios

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# Path(__file__) may resolve through the tutorial symlink when run directly.
# Use Path(__file__).parent to get the directory of this file (without resolving
# the symlink), then compute paths relative to the containing tutorials directory.
# Specifically: this file is at <tutorials>/level-5-scenarios-typed/benchmark.py
# so parent.parent is the tutorials root (whether accessed via symlink or direct path).
_THIS_FILE = Path(__file__)
_TUTORIALS_ROOT = _THIS_FILE.parent.parent  # e.g. gaspatchio-core/tutorial/ (symlink) or the real path

UNTYPED_DIR = _TUTORIALS_ROOT / "level-5-scenarios" / "base"
TYPED_DIR = _TUTORIALS_ROOT / "level-5-scenarios-typed" / "base"
REPORT_DIR = _TUTORIALS_ROOT / "level-5-scenarios-typed" / "report"

SCALES: list[tuple[str, Path]] = [
    ("8", UNTYPED_DIR / "model_points.parquet"),
    ("1k", UNTYPED_DIR / "model_points_1k.parquet"),
    ("10k", UNTYPED_DIR / "model_points_10k.parquet"),
]

SCENARIOS = ["BASE", "UP", "DOWN"]
N_REPEATS = 3

# ---------------------------------------------------------------------------
# Memory helper
# ---------------------------------------------------------------------------

_IS_MACOS = platform.system() == "Darwin"


def _peak_rss_mb() -> float:
    """Return the process peak RSS in megabytes.

    Uses ``resource.getrusage(resource.RUSAGE_SELF).ru_maxrss``.
    On macOS the value is bytes; on Linux it is kilobytes.
    """
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if _IS_MACOS:
        return raw / (1024 * 1024)
    return raw / 1024


# ---------------------------------------------------------------------------
# Altair theme (reuse L5 style)
# ---------------------------------------------------------------------------

_FONT = "Segoe UI, Helvetica Neue, Arial, sans-serif"

_UNTYPED_COLOR = "#4682B4"  # steel blue
_TYPED_COLOR = "#CD853F"  # peru / amber


def _gaspatchio_theme() -> alt.theme.ThemeConfig:
    return {
        "config": {
            "background": "#FAFAFA",
            "title": {"font": _FONT, "fontSize": 16, "anchor": "start"},
            "axis": {
                "labelFont": _FONT,
                "labelFontSize": 11,
                "titleFont": _FONT,
                "titleFontSize": 12,
                "grid": True,
                "gridColor": "#E0E0E0",
            },
            "legend": {
                "labelFont": _FONT,
                "labelFontSize": 11,
                "titleFont": _FONT,
                "titleFontSize": 12,
            },
            "view": {"strokeWidth": 0},
        }
    }


@alt.theme.register("gaspatchio", enable=True)
def _enable_gaspatchio_theme() -> alt.theme.ThemeConfig:
    return _gaspatchio_theme()

# ---------------------------------------------------------------------------
# Module loader
# ---------------------------------------------------------------------------


def _load_module(model_py: Path, name: str) -> Any:
    """Load a model.py file as a module."""
    spec = importlib.util.spec_from_file_location(name, model_py)
    if spec is None or spec.loader is None:
        msg = f"Cannot load module from {model_py}"
        raise RuntimeError(msg)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# Single benchmark run
# ---------------------------------------------------------------------------


def _run_once(
    model_module: Any,
    points_path: Path,
    scenarios: list[str] = SCENARIOS,
) -> tuple[float, float, int]:
    """Execute one model run and return (elapsed_s, peak_rss_mb, n_output_rows).

    The pre-run ``gc.collect()`` flushes unreferenced objects so the
    allocation delta is less noisy.
    """
    gc.collect()
    rss_before = _peak_rss_mb()
    t0 = time.perf_counter()

    mp = pl.read_parquet(points_path)
    af = ActuarialFrame(mp)
    af = with_scenarios(af, scenarios)
    result_af = model_module.main(af)
    df = result_af.collect()

    elapsed = time.perf_counter() - t0
    rss_after = _peak_rss_mb()
    rss_delta = max(0.0, rss_after - rss_before)
    return elapsed, rss_delta, len(df)


# ---------------------------------------------------------------------------
# Benchmark (n_repeats per model/scale pair)
# ---------------------------------------------------------------------------


def _benchmark(
    model_module: Any,
    points_path: Path,
    label: str,
    scale_label: str,
    n_repeats: int = N_REPEATS,
) -> dict[str, Any]:
    n_points = pl.read_parquet(points_path).shape[0]
    logger.info(f"Benchmarking {label} @ {scale_label} ({n_points} points) x{n_repeats}")

    runs = [_run_once(model_module, points_path) for _ in range(n_repeats)]
    times = [r[0] for r in runs]
    mems = [r[1] for r in runs]
    n_rows_out = runs[0][2]
    time_mean = sum(times) / n_repeats
    time_std = (sum((t - time_mean) ** 2 for t in times) / n_repeats) ** 0.5

    return {
        "label": label,
        "scale_label": scale_label,
        "n_points": n_points,
        "n_rows_out": n_rows_out,
        "time_mean_s": time_mean,
        "time_std_s": time_std,
        "time_min_s": min(times),
        "time_max_s": max(times),
        "throughput_pts_per_s": n_points / time_mean,
        "peak_rss_mb": max(mems),
    }


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------


def _build_throughput_chart(results: list[dict[str, Any]]) -> alt.Chart:
    """Line chart: throughput (pts/s) vs n_points, one line per model."""
    rows = [
        {
            "Model": r["label"],
            "Points": r["n_points"],
            "Throughput (pts/s)": r["throughput_pts_per_s"],
        }
        for r in results
    ]
    df = pl.DataFrame(rows)

    color_scale = alt.Scale(
        domain=["Untyped L5", "Typed L5"],
        range=[_UNTYPED_COLOR, _TYPED_COLOR],
    )

    return (
        alt.Chart(df)
        .mark_line(point=True, strokeWidth=2)
        .encode(
            x=alt.X(
                "Points:Q",
                scale=alt.Scale(type="log"),
                axis=alt.Axis(title="Model Points (log scale)"),
            ),
            y=alt.Y(
                "Throughput (pts/s):Q",
                axis=alt.Axis(title="Throughput (model-points / sec)"),
            ),
            color=alt.Color("Model:N", scale=color_scale, title="Model"),
            shape=alt.Shape("Model:N", title="Model"),
        )
        .properties(
            width=600,
            height=400,
            title="Throughput vs Scale — Untyped vs Typed L5",
        )
    )


def _build_memory_chart(results: list[dict[str, Any]]) -> alt.Chart:
    """Line chart: peak RSS delta (MB) vs n_points, one line per model."""
    rows = [
        {
            "Model": r["label"],
            "Points": r["n_points"],
            "Peak RSS delta (MB)": r["peak_rss_mb"],
        }
        for r in results
    ]
    df = pl.DataFrame(rows)

    color_scale = alt.Scale(
        domain=["Untyped L5", "Typed L5"],
        range=[_UNTYPED_COLOR, _TYPED_COLOR],
    )

    return (
        alt.Chart(df)
        .mark_line(point=True, strokeWidth=2)
        .encode(
            x=alt.X(
                "Points:Q",
                scale=alt.Scale(type="log"),
                axis=alt.Axis(title="Model Points (log scale)"),
            ),
            y=alt.Y(
                "Peak RSS delta (MB):Q",
                axis=alt.Axis(title="Peak RSS delta (MB)"),
            ),
            color=alt.Color("Model:N", scale=color_scale, title="Model"),
            shape=alt.Shape("Model:N", title="Model"),
        )
        .properties(
            width=600,
            height=400,
            title="Peak Memory vs Scale — Untyped vs Typed L5",
        )
    )


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


def _write_report(
    results: list[dict[str, Any]],
    git_sha: str,
    python_version: str,
    arch: str,
    report_dir: Path,
) -> Path:
    """Write benchmark.md to report_dir."""
    import datetime

    today = datetime.date.today().isoformat()

    lines: list[str] = []
    lines.append("# L5 Typed-Inputs Benchmark")
    lines.append("")
    lines.append(f"Date: {today}")
    lines.append(f"Branch: gsp-92-rollforward-redesign @ {git_sha}")
    lines.append(f"Hardware: {arch} / Python {python_version}")
    lines.append("")
    lines.append("## Configuration")
    lines.append("")
    lines.append(f"- Scenarios per run: {', '.join(SCENARIOS)}")
    lines.append(f"- Repeats: {N_REPEATS} per (model, scale)")
    lines.append(
        "- Memory measurement: `resource.getrusage(RUSAGE_SELF).ru_maxrss` "
        "(peak RSS since process start; macOS reports bytes, divided by 1024^2 for MB)"
    )
    lines.append("")
    lines.append("## Results")
    lines.append("")

    header = "| Model | Points | Time (mean ± std) | Throughput (pts/s) | Peak RSS delta (MB) |"
    sep = "|-------|--------|-------------------|---------------------|----------------------|"
    lines.append(header)
    lines.append(sep)

    for r in results:
        time_str = f"{r['time_mean_s']:.3f} ± {r['time_std_s']:.3f}"
        throughput_str = f"{r['throughput_pts_per_s']:,.1f}"
        rss_str = f"{r['peak_rss_mb']:.1f}"
        lines.append(
            f"| {r['label']} | {r['n_points']:,} | {time_str} | {throughput_str} | {rss_str} |"
        )

    lines.append("")
    lines.append("## Charts")
    lines.append("")
    lines.append("![Throughput vs Scale](throughput.png)")
    lines.append("")
    lines.append("![Peak RSS vs Scale](memory.png)")
    lines.append("")
    lines.append("## Findings")
    lines.append("")

    # Auto-generate findings
    findings = _generate_findings(results)
    for f in findings:
        lines.append(f"- {f}")
    lines.append("")

    report_path = report_dir / "benchmark.md"
    report_path.write_text("\n".join(lines))
    return report_path


def _generate_findings(results: list[dict[str, Any]]) -> list[str]:
    """Generate comparison findings from results."""
    findings: list[str] = []

    # Group by scale
    scales_seen = sorted({r["n_points"] for r in results})
    for n_pts in scales_seen:
        scale_results = {r["label"]: r for r in results if r["n_points"] == n_pts}
        untyped = scale_results.get("Untyped L5")
        typed = scale_results.get("Typed L5")
        if untyped is None or typed is None:
            continue
        ratio = typed["throughput_pts_per_s"] / untyped["throughput_pts_per_s"]
        direction = "faster" if ratio > 1 else "slower"
        pct_diff = abs(ratio - 1) * 100
        findings.append(
            f"At {n_pts:,} points: typed L5 throughput is "
            f"{ratio:.2f}x ({pct_diff:.1f}% {direction}) vs untyped. "
            f"Typed: {typed['throughput_pts_per_s']:,.1f} pts/s, "
            f"Untyped: {untyped['throughput_pts_per_s']:,.1f} pts/s."
        )

        rss_ratio = (typed["peak_rss_mb"] + 1e-6) / (untyped["peak_rss_mb"] + 1e-6)
        findings.append(
            f"At {n_pts:,} points: typed L5 peak RSS delta is "
            f"{typed['peak_rss_mb']:.1f} MB vs {untyped['peak_rss_mb']:.1f} MB untyped "
            f"(ratio {rss_ratio:.2f}x)."
        )

    # Scaling shape
    typed_results = sorted(
        [r for r in results if r["label"] == "Typed L5"], key=lambda x: x["n_points"]
    )
    if len(typed_results) >= 2:
        small = typed_results[0]
        large = typed_results[-1]
        pts_ratio = large["n_points"] / small["n_points"]
        time_ratio = large["time_mean_s"] / small["time_mean_s"]
        findings.append(
            f"Typed L5 scaling: {pts_ratio:.0f}x more points → {time_ratio:.1f}x more time "
            f"(near-linear scaling is expected for this model)."
        )

    return findings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the full benchmark and write outputs to report_dir."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Loading modules...")
    untyped_mod = _load_module(UNTYPED_DIR / "model.py", "untyped_l5")
    typed_mod = _load_module(TYPED_DIR / "model.py", "typed_l5")

    # Get git SHA for report
    try:
        git_sha = (
            subprocess.check_output(
                ["git", "-C", str(_TUTORIALS_ROOT), "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except subprocess.CalledProcessError:
        git_sha = "unknown"

    python_version = platform.python_version()
    arch = platform.machine()

    results: list[dict[str, Any]] = []

    for scale_label, points_path in SCALES:
        if not points_path.exists():
            logger.warning(f"Skipping scale {scale_label}: {points_path} not found")
            continue

        results.append(
            _benchmark(untyped_mod, points_path, "Untyped L5", scale_label)
        )
        results.append(
            _benchmark(typed_mod, points_path, "Typed L5", scale_label)
        )

    # Print summary to stdout
    logger.info("=" * 70)
    logger.info("BENCHMARK RESULTS")
    logger.info("=" * 70)
    for r in results:
        logger.info(
            f"{r['label']:12s} | {r['n_points']:6,} pts | "
            f"{r['time_mean_s']:.3f}±{r['time_std_s']:.3f}s | "
            f"{r['throughput_pts_per_s']:8,.1f} pts/s | "
            f"{r['peak_rss_mb']:.1f} MB RSS delta"
        )

    # Charts
    logger.info("Writing charts...")
    throughput_chart = _build_throughput_chart(results)
    throughput_chart.save(str(REPORT_DIR / "throughput.png"), scale_factor=2)

    memory_chart = _build_memory_chart(results)
    memory_chart.save(str(REPORT_DIR / "memory.png"), scale_factor=2)

    # Markdown report
    logger.info("Writing benchmark.md...")
    report_path = _write_report(results, git_sha, python_version, arch, REPORT_DIR)
    logger.info(f"Report written to {report_path}")


if __name__ == "__main__":
    main()
