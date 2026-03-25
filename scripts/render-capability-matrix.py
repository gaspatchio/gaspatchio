#!/usr/bin/env python3
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
<tr><th>Skill</th>{''.join(f'<th>{{n}}</th>' for n in short_names)}</tr>
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
<style>
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 2rem; max-width: 800px; }
a { color: #0366d6; text-decoration: none; }
a:hover { text-decoration: underline; }
.card { border: 1px solid #ddd; border-radius: 8px; padding: 1rem; margin: 1rem 0; }
.card h2 { margin-top: 0; }
</style>
</head>
<body>
<h1>Gaspatchio Dev Dashboard</h1>

<div class="card">
<h2><a href="dev/bench/">Rust Micro-Benchmarks</a></h2>
<p>Criterion time-series: assumption lookup speed, vector operations, accumulate plugin.</p>
</div>

<div class="card">
<h2><a href="dev/model-bench/">Model Benchmarks</a></h2>
<p>End-to-end model execution at 8 / 1K / 10K / 100K model points (L4, L5).</p>
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
