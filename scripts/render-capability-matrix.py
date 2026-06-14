#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: T201
"""Render capability matrix HTML from JSON.

Reads dev/capability/capability-matrix.json and generates
dev/capability/index.html with a colour-coded grid.

Run by CI on gh-pages branch after skill evals complete.
"""

import json
from pathlib import Path

MATRIX_PATH = Path("dev/capability/capability-matrix.json")
OUTPUT_PATH = Path("dev/capability/index.html")
INDEX_PATH = Path("index.html")


def score_class(score: float) -> str:
    """Map a score to a CSS class."""
    if score >= 0.8:
        return "pass"
    if score >= 0.5:
        return "partial"
    return "fail"


def score_label(score: float) -> str:
    """Map a score to a display label."""
    if score >= 0.8:
        return "PASS"
    if score >= 0.5:
        return "PARTIAL"
    return "FAIL"


def render_matrix(data: dict) -> str:
    """Generate HTML table from capability matrix data."""
    models = list(data.keys())
    skills = list(next(iter(data.values())).keys()) if data else []

    short_names = [m.split(":")[-1] if ":" in m else m for m in models]

    rows = []
    for skill in skills:
        cells = []
        for model in models:
            score = data[model].get(skill, 0)
            cls = score_class(score)
            label = score_label(score)
            cells.append(f'<td class="{cls}">{label} ({score:.0%})</td>')
        rows.append(f"<tr><td>{skill}</td>{''.join(cells)}</tr>")

    return f"""<!DOCTYPE html>
<html>
<head>
<title>Gaspatchio Capability Matrix</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 2rem; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: center; }}
th {{ background: #f5f5f5; }}
td:first-child {{ text-align: left; font-weight: bold; }}
.pass {{ background: #d4edda; color: #155724; }}
.partial {{ background: #fff3cd; color: #856404; }}
.fail {{ background: #f8d7da; color: #721c24; }}
a {{ color: #0366d6; }}
</style>
</head>
<body>
<h1>Gaspatchio Capability Matrix</h1>
<p><a href="../">← Back to dashboard</a></p>
<p>LLM model × skill test pass rates. Updated nightly.</p>
<table>
<tr><th>Skill</th>{''.join(f'<th>{n}</th>' for n in short_names)}</tr>
{''.join(rows)}
</table>
</body>
</html>"""


def render_index() -> str:
    """Generate landing page HTML."""
    return """<!DOCTYPE html>
<html>
<head>
<title>Gaspatchio Dev Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 2rem; max-width: 1000px; }
a { color: #0366d6; text-decoration: none; }
a:hover { text-decoration: underline; }
.card { border: 1px solid #ddd; border-radius: 8px; padding: 1rem; margin: 1rem 0; }
.card h2 { margin-top: 0; }
.chart-container { position: relative; height: 300px; margin: 1rem 0; }
.chart-row { display: flex; gap: 1rem; }
.chart-row .chart-container { flex: 1; }
.muted { color: #666; font-size: 0.85em; }
</style>
</head>
<body>
<h1>Gaspatchio Dev Dashboard</h1>

<div class="card">
<h2>VA Model Performance (100K policies)</h2>
<p class="muted">Throughput and data memory over time. Higher throughput = faster. Lower data MB = more efficient.</p>
<div class="chart-row">
  <div class="chart-container"><canvas id="throughputChart"></canvas></div>
  <div class="chart-container"><canvas id="memoryChart"></canvas></div>
</div>
<p class="muted">See <a href="dev/model-bench/">all model benchmarks</a> for full detail.</p>
</div>

<script src="dev/model-bench/data.js"></script>
<script>
(function() {
  if (typeof window.BENCHMARK_DATA === 'undefined') return;
  const entries = window.BENCHMARK_DATA.entries['Model Benchmarks'] || [];

  function extract(entries, nameFilter) {
    return entries.map(entry => {
      const bench = entry.benches.find(b => b.name === nameFilter);
      if (!bench) return null;
      const date = new Date(entry.date);
      return { x: date, y: bench.value, commit: entry.commit.id.substring(0, 7) };
    }).filter(Boolean);
  }

  const throughputVA = extract(entries, 'VA Model (GMDB/GMAB)/100K-throughput');
  const throughputL5 = extract(entries, 'VA + Scenarios (3x)/100K-throughput');
  const dataMbVA = extract(entries, 'VA Model (GMDB/GMAB)/100K-data-mb');
  const dataMbL5 = extract(entries, 'VA + Scenarios (3x)/100K-data-mb');
  const memoryVA = extract(entries, 'VA Model (GMDB/GMAB)/100K-memory');
  const memoryL5 = extract(entries, 'VA + Scenarios (3x)/100K-memory');

  const chartOpts = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: { legend: { position: 'bottom' } },
    scales: {
      x: { type: 'time', time: { unit: 'day' } },
    }
  };

  new Chart(document.getElementById('throughputChart'), {
    type: 'line',
    data: {
      datasets: [
        { label: 'VA Model (pts/s)', data: throughputVA, borderColor: '#2563eb', backgroundColor: '#2563eb22', fill: false, tension: 0.2, pointRadius: 3 },
        { label: 'VA + Scenarios (pts/s)', data: throughputL5, borderColor: '#7c3aed', backgroundColor: '#7c3aed22', fill: false, tension: 0.2, pointRadius: 3 },
      ]
    },
    options: { ...chartOpts, plugins: { ...chartOpts.plugins, title: { display: true, text: 'Throughput (100K policies)' } }, scales: { ...chartOpts.scales, y: { title: { display: true, text: 'points/sec' }, beginAtZero: true } } }
  });

  // Memory chart: prefer data-mb if available, fall back to RSS delta
  const memVA = dataMbVA.length > 0 ? dataMbVA : memoryVA;
  const memL5 = dataMbL5.length > 0 ? dataMbL5 : memoryL5;
  const memLabel = dataMbVA.length > 0 ? 'Data Memory' : 'RSS Delta';

  new Chart(document.getElementById('memoryChart'), {
    type: 'line',
    data: {
      datasets: [
        { label: 'VA Model (' + memLabel + ')', data: memVA, borderColor: '#dc2626', backgroundColor: '#dc262622', fill: false, tension: 0.2, pointRadius: 3 },
        { label: 'VA + Scenarios (' + memLabel + ')', data: memL5, borderColor: '#ea580c', backgroundColor: '#ea580c22', fill: false, tension: 0.2, pointRadius: 3 },
      ]
    },
    options: { ...chartOpts, plugins: { ...chartOpts.plugins, title: { display: true, text: 'Memory (100K policies)' } }, scales: { ...chartOpts.scales, y: { title: { display: true, text: 'MB' }, beginAtZero: true } } }
  });
})();
</script>

<div class="card">
<h2><a href="dev/bench/">Rust Micro-Benchmarks</a></h2>
<p>Criterion time-series: assumption lookup speed, vector operations, accumulate plugin.</p>
<p class="muted">Windows: <a href="dev/bench-windows/">Rust micro-benchmarks on windows-large</a></p>
</div>

<div class="card">
<h2><a href="dev/model-bench/">Model Benchmarks</a></h2>
<p>End-to-end model execution at 8 / 1K / 10K / 100K model points (L4, L5).</p>
<p class="muted">Windows: <a href="dev/model-bench-windows/">model benchmarks on windows-large</a></p>
</div>

<div class="card">
<h2><a href="dev/scenario-bench/">Scenario Performance</a></h2>
<p>Scenario throughput and memory for the bounded-memory default path.</p>
<p class="muted">Windows: <a href="dev/scenario-bench-windows/">scenario benchmarks on windows-large</a></p>
</div>

<div class="card">
<h2><a href="dev/comparison/">Gaspatchio vs Lifelib</a></h2>
<p>Matched-scale comparison against the lifelib IntegratedLife reference model.</p>
<p class="muted">Windows: <a href="dev/comparison-windows/">comparison benchmarks on windows-large</a></p>
</div>

<div class="card">
<h2><a href="dev/evals/">Skill Quality</a></h2>
<p>Pass-rate time-series by LLM model across all 6 skills.</p>
</div>

<div class="card">
<h2><a href="dev/capability/">Capability Matrix</a></h2>
<p>LLM model x skill test grid. Which models pass which skill tests?</p>
</div>

</body>
</html>"""


def main() -> None:
    """Render all dashboard pages."""
    # Capability matrix
    if MATRIX_PATH.exists():
        data = json.loads(MATRIX_PATH.read_text())
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(render_matrix(data))
        print(f"Wrote {OUTPUT_PATH}")
    else:
        print(f"SKIP capability matrix — {MATRIX_PATH} not found")

    # Landing page
    INDEX_PATH.write_text(render_index())
    print(f"Wrote {INDEX_PATH}")


if __name__ == "__main__":
    main()
