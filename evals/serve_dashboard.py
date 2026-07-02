#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: T201
"""Serve the gh-pages dashboard locally with eval/benchmark results.

Converts local results into the benchmark-action data.js format
and serves the dashboard with live-reload on file changes.

Usage:
    uv run python evals/serve_dashboard.py          # default port 8787
    uv run python evals/serve_dashboard.py --port 9000
"""

import http.server
import json
import re
import shutil
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "evals" / "results"
PREVIEW_DIR = RESULTS_DIR / "dev-preview"
GH_PAGES_INDEX = REPO_ROOT / "index.html"


def build_data_js(benchmark_json: Path, name: str) -> str:
    """Convert benchmark-results.json into benchmark-action data.js format."""
    if not benchmark_json.exists():
        return ""
    entries = json.loads(benchmark_json.read_text())
    data = {
        "entries": {
            name: [
                {
                    "commit": {
                        "id": "local",
                        "message": "local run",
                        "author": {"username": "local"},
                    },
                    "date": int(time.time()),
                    "benches": [
                        {
                            "name": e["name"],
                            "value": e["value"],
                            "unit": e.get("unit", ""),
                        }
                        for e in entries
                    ],
                }
            ]
        }
    }
    return f"window.BENCHMARK_DATA = {json.dumps(data, indent=2)};"


def build_data_js_from_entries(entries: list[dict], name: str) -> str:
    """Build data.js from a pre-built list of bench entries."""
    data = {
        "entries": {
            name: [
                {
                    "commit": {"id": "local", "message": "local run", "author": {"username": "local"}},
                    "date": int(time.time()),
                    "benches": entries,
                }
            ]
        }
    }
    return f"window.BENCHMARK_DATA = {json.dumps(data, indent=2)};"


def _parse_bencher_output(path: Path) -> list[dict]:
    """Parse Criterion --output-format bencher output into benchmark entries.

    Bencher format: `test <name> ... bench:    <ns> ns/iter (+/- <variance>)`
    """
    results = []
    for line in path.read_text().splitlines():
        m = re.match(r"^test\s+(.+?)\s+\.\.\.\s+bench:\s+([\d,]+)\s+ns/iter", line)
        if m:
            name = m.group(1).strip()
            ns = int(m.group(2).replace(",", ""))
            results.append({"name": name, "value": ns, "unit": "ns/iter"})
    return results


def prepare_preview() -> None:
    """Build the dev-preview directory from local results."""
    # Dashboard data artifacts: capability-matrix.json (with-skill scores) and
    # lift-matrix.json (per-model with-minus-without). skills.html on gh-pages
    # renders both; rendering changes live on the gh-pages branch, not here.
    # Ensure structure
    for sub in ["dev/bench", "dev/model-bench", "dev/evals", "dev/capability"]:
        (PREVIEW_DIR / sub).mkdir(parents=True, exist_ok=True)

    # Copy dashboard pages from gh-pages branch
    import subprocess

    for page in ["index.html", "skills.html"]:
        result = subprocess.run(
            ["git", "show", f"origin/gh-pages:{page}"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        if result.returncode == 0:
            (PREVIEW_DIR / page).write_text(result.stdout)
            print(f"  Dashboard: loaded {page} from gh-pages")
        else:
            print(f"  WARNING: {page} not found on gh-pages")

    # Eval results -> data.js
    eval_results = RESULTS_DIR / "benchmark-results.json"
    if eval_results.exists():
        js = build_data_js(eval_results, "Skill Evals")
        (PREVIEW_DIR / "dev" / "evals" / "data.js").write_text(js)
        print(f"  Skill Evals: loaded from {eval_results}")

    # Capability matrix
    cap_matrix = RESULTS_DIR / "capability-matrix.json"
    if cap_matrix.exists():
        shutil.copy2(cap_matrix, PREVIEW_DIR / "dev" / "capability" / "capability-matrix.json")
        print(f"  Capability Matrix: loaded from {cap_matrix}")

    # Lift matrix (with-skill minus without-skill, per model)
    lift_matrix = RESULTS_DIR / "lift-matrix.json"
    if lift_matrix.exists():
        shutil.copy2(lift_matrix, PREVIEW_DIR / "dev" / "capability" / "lift-matrix.json")  # noqa: E501
        print(f"  Lift Matrix: loaded from {lift_matrix}")

    # Model benchmark results
    model_bench = REPO_ROOT / "evals" / "benchmarks" / "model_points" / "benchmark-results.json"
    if model_bench.exists():
        js = build_data_js(model_bench, "Model Benchmarks")
        (PREVIEW_DIR / "dev" / "model-bench" / "data.js").write_text(js)
        print(f"  Model Benchmarks: loaded from {model_bench}")

    # Comparison benchmark results
    comp_bench = REPO_ROOT / "evals" / "benchmarks" / "comparison_results" / "benchmark-results.json"
    if comp_bench.exists():
        (PREVIEW_DIR / "dev" / "comparison").mkdir(parents=True, exist_ok=True)
        js = build_data_js(comp_bench, "Gaspatchio vs Lifelib")
        (PREVIEW_DIR / "dev" / "comparison" / "data.js").write_text(js)
        print(f"  Comparison: loaded from {comp_bench}")

    # Rust bench results (from local Criterion run or CI)
    rust_bench = Path("/tmp/rust-bench-output.txt")
    if rust_bench.exists():
        # Convert Criterion bencher format to benchmark-action data.js
        rust_results = _parse_bencher_output(rust_bench)
        if rust_results:
            js = build_data_js_from_entries(rust_results, "Rust Benchmarks")
            (PREVIEW_DIR / "dev" / "bench" / "data.js").write_text(js)
            print(f"  Rust Benchmarks: loaded from {rust_bench}")
        else:
            print(f"  Rust Benchmarks: no valid entries in {rust_bench}")
    else:
        data_js = PREVIEW_DIR / "dev" / "bench" / "data.js"
        if not data_js.exists():
            print(f"  Rust Benchmarks: no data (run cargo bench to populate)")


def main() -> None:
    """Serve the dashboard."""
    import argparse

    parser = argparse.ArgumentParser(description="Serve dashboard locally")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    print("Preparing dashboard preview...")
    prepare_preview()

    print(f"\nServing dashboard at http://localhost:{args.port}")
    print("Press Ctrl+C to stop\n")

    import os

    os.chdir(PREVIEW_DIR)

    class RefreshHandler(http.server.SimpleHTTPRequestHandler):
        """Re-reads results on every index.html request."""

        def __init__(self, *a: object, **kw: object) -> None:
            super().__init__(*a, directory=str(PREVIEW_DIR), **kw)  # type: ignore[arg-type]

        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                prepare_preview()
            super().do_GET()

        def log_message(self, format: str, *a: object) -> None:  # noqa: A002
            if "/dev/" not in str(a[0]):
                super().log_message(format, *a)

    with http.server.HTTPServer(("", args.port), RefreshHandler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
