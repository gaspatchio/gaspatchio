# Evals & Benchmarks: Design Spec

## Overview

Three-component system for tracking gaspatchio quality over time:

1. **Pydantic AI eval harness** — test skill behaviour across 4 LLM models using structured output, span-based evaluation, and built-in + custom evaluators
2. **CI workflows** — Tier 1 (every PR, free), Tier 2 (nightly + skill changes, ~$3-6/run), Criterion benchmarks
3. **GitHub Pages dashboard** — auto-generated performance charts, skill eval time-series, and capability matrix

## LLM Models Tested

| Role | Model ID | Provider |
|---|---|---|
| Anthropic flagship | `claude-sonnet-4-6` | Anthropic |
| Anthropic fast | `claude-haiku-4-5` | Anthropic |
| OpenAI flagship | `gpt-5.4` | OpenAI |
| OpenAI fast | `gpt-5.4-mini` | OpenAI |

---

## Component 1: Pydantic AI Eval Harness

### Architecture

Uses `pydantic-ai` for agent execution and `pydantic-evals` for evaluation. Follows the framework's SOTA patterns:

- **Structured output** via Pydantic `result_type` — agents return typed models, not raw text
- **Built-in evaluators** (`Contains`, `EqualsExpected`, `HasMatchingSpan`, `LLMJudge`) — don't reinvent what exists
- **Span-based evaluation** via OpenTelemetry — verify tool calls by checking spans, not grepping output
- **Dataset serialization** via `.from_file()` / `.to_file()` — YAML test cases, version-controlled

### Directory structure

```
evals/
├── __init__.py
├── conftest.py              ← pytest fixtures: model parametrization, skill loaders, logfire config
├── agents.py                ← Pydantic AI agent definitions with result_type models
├── evaluators.py            ← Custom evaluators (only where built-ins don't fit)
├── run_evals.py             ← CLI: run all evals, output results JSON + capability matrix
├── test_evals.py            ← pytest wrapper for CI
├── datasets/
│   ├── review.yaml          ← model-review test cases
│   ├── discovery.yaml       ← model-discovery test cases
│   ├── building.yaml        ← model-building test cases
│   ├── reconciliation.yaml  ← model-reconciliation test cases
│   ├── scenarios.yaml       ← model-scenarios test cases
│   └── quickstart.yaml      ← quickstart test cases
└── results/                 ← generated (gitignored except capability-matrix.json)
    ├── benchmark-results.json    ← customBiggerIsBetter for github-action-benchmark
    └── capability-matrix.json    ← model × skill × test pass rates
```

### Structured output types

Each skill gets a Pydantic result model so the agent returns typed data we can assert on:

```python
from pydantic import BaseModel

class ReviewResult(BaseModel):
    """Structured output from model-review skill."""
    critical_issues: list[str]
    important_issues: list[str]
    minor_issues: list[str]
    positive_observations: list[str]
    files_reviewed: list[str]

class DiscoveryResult(BaseModel):
    """Structured output from model-discovery skill."""
    questions_asked: list[str]
    tutorial_level_suggested: str | None
    spec_written: bool
    code_written: bool  # should always be False

class QuickstartResult(BaseModel):
    """Structured output from quickstart skill."""
    tutorial_level_routed: str
    describe_json_used: bool
    reasoning: str

class ScenarioResult(BaseModel):
    """Structured output from model-scenarios skill."""
    model_py_modified: bool  # should always be False
    run_scenarios_created: bool
    report_generated: bool
    chart_types: list[str]
    audit_trail_included: bool
```

### Agent definitions

```python
from pydantic_ai import Agent

def make_review_agent(model: str) -> Agent[None, ReviewResult]:
    skill_content = Path("skills/model-review/SKILL.md").read_text()
    antipatterns = Path("skills/model-review/references/gaspatchio-antipatterns.md").read_text()
    asop56 = Path("skills/model-review/references/asop56-checklist.md").read_text()

    return Agent(
        model,
        system_prompt=f"{skill_content}\n\n{antipatterns}\n\n{asop56}",
        result_type=ReviewResult,
        result_tool_retries=2,  # let model retry on validation failure
    )
```

### Evaluators

**Built-in (use directly):**

| Evaluator | What it checks | Used for |
|---|---|---|
| `Contains` | Output contains expected substring | "did it mention map_elements?" |
| `EqualsExpected` | Exact match | "did it route to Level 1?" |
| `HasMatchingSpan` | OTEL span exists | "did it call gspio docs?" |
| `LLMJudge` | Semantic quality via rubric | Hard tests (timing bugs, assumption staleness) |

**Custom (where built-ins don't fit):**

```python
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

class NoCodeWritten(Evaluator[str, DiscoveryResult]):
    """Discovery skill should never produce code."""
    def evaluate(self, ctx: EvaluatorContext[str, DiscoveryResult]) -> float:
        return 0.0 if ctx.output.code_written else 1.0

class SeverityClassification(Evaluator[str, ReviewResult]):
    """Check that known anti-patterns are classified at the right severity."""
    expected_critical_keywords: list[str]
    expected_important_keywords: list[str]

    def evaluate(self, ctx: EvaluatorContext[str, ReviewResult]) -> float:
        critical_found = sum(
            1 for kw in self.expected_critical_keywords
            if any(kw.lower() in issue.lower() for issue in ctx.output.critical_issues)
        )
        important_found = sum(
            1 for kw in self.expected_important_keywords
            if any(kw.lower() in issue.lower() for issue in ctx.output.important_issues)
        )
        total_expected = len(self.expected_critical_keywords) + len(self.expected_important_keywords)
        return (critical_found + important_found) / total_expected if total_expected > 0 else 1.0

class TwoScriptPattern(Evaluator[str, ScenarioResult]):
    """Scenarios skill must not modify model.py."""
    def evaluate(self, ctx: EvaluatorContext[str, ScenarioResult]) -> float:
        if ctx.output.model_py_modified:
            return 0.0
        if not ctx.output.run_scenarios_created:
            return 0.0
        return 1.0
```

### Span-based evaluation

With Logfire configured, verify tool calls via OTEL traces:

```python
from pydantic_evals.evaluators import HasMatchingSpan

# Verify the building skill called gspio docs before writing code
HasMatchingSpan(name_contains="gspio docs")

# Verify reconciliation demanded --output-file
HasMatchingSpan(name_contains="run-single-policy")
```

Note: span-based evaluation requires Logfire configuration. For CI without Logfire, fall back to output-based evaluation. Span evals are a bonus layer, not a requirement.

### Dataset format (YAML)

```yaml
# datasets/review.yaml
cases:
  - name: catches_map_elements
    inputs: |
      Review this gaspatchio model:

      ```python
      def main(af):
          af.age_category = af.age_at_entry.map_elements(
              lambda x: "young" if x < 40 else "old", return_dtype=pl.String
          )
          return af
      ```
    expected_output:
      critical_issues: ["map_elements"]
    evaluators:
      - type: SeverityClassification
        expected_critical_keywords: ["map_elements"]
        expected_important_keywords: []

  - name: catches_av_timing
    inputs: |
      Review this gaspatchio model section:

      ```python
      af.claim_pp_death = when(af.has_gmdb).then(
          when(af.av_pp > af.sum_assured_f).then(af.av_pp).otherwise(af.sum_assured_f)
      ).otherwise(af.av_pp)
      ```
    evaluators:
      - type: LLMJudge
        rubric: |
          Does the review identify that death claims should use av_pp_mid_mth
          (mid-month AV after fees) instead of av_pp (beginning-of-period AV)?
          Score 1.0 if the timing issue is identified, 0.0 if not.
        model: gpt-5.4-mini

  - name: passes_clean_model
    inputs: "[contents of tutorial/level-4-lifelib/base/model.py]"
    expected_output:
      critical_issues: []
      important_issues: []
    evaluators:
      - type: EqualsExpected
```

### Test runner

```python
# evals/run_evals.py
"""Run all skill evals across all models, output results."""

import json
from pathlib import Path
from pydantic_evals import Dataset

MODELS = [
    "claude-sonnet-4-6",
    "claude-haiku-4-5",
    "openai:gpt-5.4",
    "openai:gpt-5.4-mini",
]

DATASETS = {
    "review": "datasets/review.yaml",
    "discovery": "datasets/discovery.yaml",
    "building": "datasets/building.yaml",
    "reconciliation": "datasets/reconciliation.yaml",
    "scenarios": "datasets/scenarios.yaml",
    "quickstart": "datasets/quickstart.yaml",
}

def run_all():
    all_results = {}
    benchmark_entries = []

    for model in MODELS:
        model_results = {}
        for skill_name, dataset_path in DATASETS.items():
            dataset = Dataset.from_file(dataset_path)
            agent = make_agent(skill_name, model)

            report = dataset.evaluate_sync(agent.run_sync)
            report.print()

            # Compute pass rate
            pass_rate = compute_pass_rate(report)
            model_results[skill_name] = pass_rate

            # Add to benchmark format
            benchmark_entries.append({
                "name": f"{skill_name}/{model}",
                "unit": "Percent",
                "value": pass_rate * 100,
            })

        all_results[model] = model_results

    # Write outputs
    Path("results").mkdir(exist_ok=True)
    Path("results/benchmark-results.json").write_text(
        json.dumps(benchmark_entries, indent=2)
    )
    Path("results/capability-matrix.json").write_text(
        json.dumps(all_results, indent=2)
    )
```

### pytest integration

```python
# evals/test_evals.py
"""Tier 2: Run evals as pytest tests (nightly CI)."""

import pytest
from pydantic_evals import Dataset

MODELS = [...]

@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("dataset_name", ["review", "discovery", "building", ...])
@pytest.mark.slow  # marker for nightly-only tests
def test_skill_eval(model, dataset_name):
    dataset = Dataset.from_file(f"datasets/{dataset_name}.yaml")
    agent = make_agent(dataset_name, model)
    report = dataset.evaluate_sync(agent.run_sync)

    pass_rate = compute_pass_rate(report)
    assert pass_rate >= 0.7, f"{dataset_name} on {model}: {pass_rate:.0%} < 70% threshold"
```

---

## Component 1b: End-to-End Model Benchmarks

### Purpose

Track gaspatchio's end-to-end performance running real actuarial models at different scales. This tests the full stack (Rust core + Python bindings + Polars + assumptions + projections) with realistic workloads, not just isolated Criterion micro-benchmarks.

### Model benchmark matrix

Run tutorial models across 3 model point sizes:

| Model | 8 points (tutorial) | 1K points | 10K points | 100K points |
|---|---|---|---|---|
| L1 base (scalar) | baseline | | | |
| L3 base (mini VA) | baseline | | | |
| L4 base (full appliedlife) | baseline | | | |
| L5 base (3 scenarios) | baseline | | | |

Each cell records: **wall-clock time** (seconds) and **peak memory** (MB).

### Model point generation

Tutorial models ship with 3-8 model points. For benchmarking we need larger sets. Add a script that generates synthetic model points by scaling up the tutorial data:

```
evals/
├── benchmarks/
│   ├── generate_model_points.py   ← generate 1K/10K/100K model points from tutorial data
│   ├── run_model_benchmarks.py    ← run models at each scale, output results
│   └── model_points/              ← generated (gitignored)
│       ├── l3_1k.parquet
│       ├── l3_10k.parquet
│       ├── l3_100k.parquet
│       ├── l4_1k.parquet
│       ├── l4_10k.parquet
│       └── l4_100k.parquet
```

**`generate_model_points.py`**: Takes the tutorial's 8 model points, varies key fields (age, sex, entry_date, sum_assured, premium_pp, av_pp_init, fund_index) to create diverse synthetic populations. Keeps the same column schema so the model code runs unchanged.

```python
def generate_model_points(source_mp: pl.DataFrame, n: int, seed: int = 42) -> pl.DataFrame:
    """Scale tutorial model points to N rows with realistic variation."""
    rng = np.random.default_rng(seed)
    # Sample from source rows with replacement
    # Add random variation to numeric fields
    # Ensure realistic ranges (age 20-80, term 5-30, etc.)
    return scaled_mp
```

**`run_model_benchmarks.py`**: Runs each model × scale combination, measures time and memory, outputs `customSmallerIsBetter` JSON:

```json
[
  {"name": "L3-base/8-points",    "unit": "seconds", "value": 0.42},
  {"name": "L3-base/1K-points",   "unit": "seconds", "value": 1.23},
  {"name": "L3-base/10K-points",  "unit": "seconds", "value": 8.45},
  {"name": "L3-base/100K-points", "unit": "seconds", "value": 72.1},
  {"name": "L4-base/8-points",    "unit": "seconds", "value": 0.51},
  ...
]
```

### What this catches

- **Performance regressions** in the Rust core that don't show up in micro-benchmarks (e.g., a change to Table lookup that's fast on 100 rows but slow on 100K)
- **Memory scaling issues** (e.g., a change that works at 1K but OOMs at 100K)
- **Python binding overhead** at scale (e.g., serialization costs that dominate at large model point counts)
- **Scenario overhead** (L5 with 3 scenarios × 100K points = 300K effective rows)

### Dashboard integration

Results appear on the same GitHub Pages dashboard under `/dev/model-bench/` alongside Criterion and skill evals. Time-series charts show how each model × scale combination tracks over time.

### Tutorial enhancement

Add model point files to the tutorial levels so users can also test at scale:

```
tutorial/level-3-mini-va/base/
├── model_points.parquet           ← existing (4 points)
├── model_points_1k.parquet        ← new (1,000 points)
└── model_points_10k.parquet       ← new (10,000 points)

tutorial/level-4-lifelib/base/
├── model_points.parquet           ← existing (8 points)
├── model_points_1k.parquet        ← new (1,000 points)
└── model_points_10k.parquet       ← new (10,000 points)
```

100K files are too large for the repo — generated on-the-fly by `generate_model_points.py` during CI benchmarks.

---

## Component 2: CI Workflows

### Existing CI (`CI.yml`) — add Tier 1

Add to existing workflow:

```yaml
skill-structure-tests:
  name: Skill Structure Tests (Tier 1)
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
      with:
        lfs: true
    - uses: astral-sh/setup-uv@v6
    - run: uv run pytest tests/skills/ -v

tutorial-smoke-tests:
  name: Tutorial Smoke Tests
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
      with:
        lfs: true
    - uses: astral-sh/setup-uv@v6
    - run: |
        for model in tutorial/level-*/base/model.py; do
          uv run python "$model" || exit 1
        done
```

### New workflow: `evals.yml`

```yaml
name: Evals & Benchmarks

on:
  schedule:
    - cron: '0 3 * * *'
  push:
    branches: [main]
    paths: ['skills/**']
  workflow_dispatch:

permissions:
  contents: write  # for gh-pages push

jobs:
  rust-benchmarks:
    name: Criterion Benchmarks
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
      - name: Run benchmarks
        run: cargo bench --bench assumption_table_lookup_benchmark -- --output-format bencher | tee bench-output.txt
        working-directory: core
      - name: Store benchmark results
        uses: benchmark-action/github-action-benchmark@v1
        with:
          name: Rust Benchmarks
          tool: cargo
          output-file-path: core/bench-output.txt
          github-token: ${{ secrets.GITHUB_TOKEN }}
          auto-push: true
          benchmark-data-dir-path: dev/bench
          alert-threshold: '130%'
          fail-on-alert: true

  model-benchmarks:
    name: End-to-End Model Benchmarks
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          lfs: true
      - uses: astral-sh/setup-uv@v6
      - name: Run model benchmarks
        run: uv run python evals/run_model_benchmarks.py | tee model-bench-output.json
      - name: Store model benchmark results
        uses: benchmark-action/github-action-benchmark@v1
        with:
          name: Model Benchmarks
          tool: customSmallerIsBetter
          output-file-path: model-bench-output.json
          github-token: ${{ secrets.GITHUB_TOKEN }}
          auto-push: true
          benchmark-data-dir-path: dev/model-bench
          alert-threshold: '150%'
          fail-on-alert: true

  skill-evals:
    name: Skill Evals (4 models)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          lfs: true
      - uses: astral-sh/setup-uv@v6
      - name: Run evals
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: uv run python evals/run_evals.py
      - name: Store eval results
        uses: benchmark-action/github-action-benchmark@v1
        with:
          name: Skill Evals
          tool: customBiggerIsBetter
          output-file-path: evals/results/benchmark-results.json
          github-token: ${{ secrets.GITHUB_TOKEN }}
          auto-push: true
          benchmark-data-dir-path: dev/evals
          alert-threshold: '80%'
          comment-on-alert: true

  capability-matrix:
    name: Update Capability Matrix
    needs: skill-evals
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: gh-pages
      - name: Download eval results
        uses: actions/download-artifact@v4
      - name: Update matrix page
        run: python scripts/render-capability-matrix.py
      - name: Push to gh-pages
        run: |
          git add .
          git commit -m "Update capability matrix" || true
          git push
```

### New workflow: `bench-pr.yml`

```yaml
name: Benchmark PR

on:
  pull_request:
    paths: ['core/**']

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
      - name: Run benchmarks
        run: cargo bench --bench assumption_table_lookup_benchmark -- --output-format bencher | tee bench-output.txt
        working-directory: core
      - name: Compare to baseline
        uses: benchmark-action/github-action-benchmark@v1
        with:
          tool: cargo
          output-file-path: core/bench-output.txt
          github-token: ${{ secrets.GITHUB_TOKEN }}
          alert-threshold: '130%'
          comment-on-alert: true
          fail-on-alert: true
          # Don't push — just compare and comment
          auto-push: false
```

---

## Component 3: GitHub Pages Dashboard

### Structure on `gh-pages` branch

```
gh-pages branch:
├── index.html                    ← landing page with links to all four views
├── dev/
│   ├── bench/
│   │   ├── index.html            ← auto-generated (Criterion micro-benchmarks)
│   │   └── data.js               ← historical Criterion data
│   ├── model-bench/
│   │   ├── index.html            ← auto-generated (end-to-end model benchmarks)
│   │   └── data.js               ← historical model benchmark data
│   ├── evals/
│   │   ├── index.html            ← auto-generated (skill eval pass rates)
│   │   └── data.js               ← historical eval data
│   └── capability/
│       ├── index.html            ← rendered from capability-matrix.json
│       └── capability-matrix.json
└── scripts/
    └── render-capability-matrix.py  ← generates capability/index.html
```

### Capability matrix page

Generated by `render-capability-matrix.py` from `capability-matrix.json`:

```html
<table>
  <tr>
    <th>Test</th>
    <th>claude-sonnet</th><th>claude-haiku</th>
    <th>gpt-5.4</th><th>gpt-5.4-mini</th>
  </tr>
  <tr>
    <td>review: catches map_elements</td>
    <td class="pass">PASS</td><td class="pass">PASS</td>
    <td class="pass">PASS</td><td class="pass">PASS</td>
  </tr>
  <tr>
    <td>review: catches AV timing bug</td>
    <td class="pass">PASS</td><td class="fail">FAIL</td>
    <td class="pass">PASS</td><td class="fail">FAIL</td>
  </tr>
</table>
```

Colour-coded: green (PASS / >80%), amber (PARTIAL / 50-80%), red (FAIL / <50%).

### Landing page

Simple HTML linking to:
- `/dev/bench/` — "Rust Micro-Benchmarks" (Criterion time-series: lookup speed, vector ops)
- `/dev/model-bench/` — "Model Benchmarks" (end-to-end model execution at 8/1K/10K/100K points)
- `/dev/evals/` — "Skill Quality" (pass-rate time-series by LLM model)
- `/dev/capability/` — "Capability Matrix" (LLM model × skill test grid)

---

## Regression Detection

| Metric | Threshold | Action |
|---|---|---|
| Criterion benchmark | >130% of previous | Fail CI, comment on commit |
| Skill eval pass rate | Drop below 70% | Fail CI, alert |
| Individual test regression | Pass → Fail for any model | Comment on commit |
| Tutorial smoke test | Any failure | Fail CI (every PR) |

---

## Cost

| Tier | When | Models | Cost |
|---|---|---|---|
| Tier 1 (structural + smoke) | Every PR | None | $0 |
| Criterion micro-benchmarks | PRs touching Rust + nightly | None | $0 |
| End-to-end model benchmarks | Nightly | None | $0 (compute only) |
| Tier 2 skill evals | Nightly + skill changes | 4 LLMs | ~$3-6/run |

---

## Test Cases (from our 20 agent tests)

The 20 tests we already ran become the seed dataset:

### review.yaml (~10 cases)
- catches_map_elements (easy)
- catches_for_loop (easy)
- catches_inline_polars (easy)
- catches_hardcoded_assumptions (easy)
- passes_clean_model (negative test)
- catches_av_timing_bug (hard — LLMJudge)
- catches_additive_decrement (hard — LLMJudge)
- catches_missing_previous_period (hard — LLMJudge)
- catches_stale_assumptions (ASOP 56)
- holds_hard_gate_under_pressure (pressure test)

### discovery.yaml (~3 cases)
- asks_questions_before_coding (hard gate)
- suggests_tutorial_shortcut (L3 for VA)
- respects_hard_gate_under_pressure

### quickstart.yaml (~4 cases)
- routes_basic_policy_data_to_L1
- handles_no_data (edge case)
- routes_va_with_recon_to_L3 (ambiguous)
- handles_stochastic_out_of_scope

### scenarios.yaml (~2 cases)
- enforces_two_script_pattern
- uses_sensitivity_analysis

### building.yaml (~1 case)
- uses_gspio_docs_before_code

---

## Success Criteria

1. `evals/` directory with YAML datasets covering all 6 skills
2. Structured output types for each skill (Pydantic models)
3. Built-in evaluators used where possible; custom only where needed
4. `run_evals.py` runs against 4 models and outputs `benchmark-results.json` + `capability-matrix.json`
5. `evals.yml` GitHub Actions workflow runs nightly + on skill changes
6. `bench-pr.yml` compares Criterion benchmarks on Rust PRs
7. GitHub Pages dashboard live with three views (bench, evals, capability)
8. Regression detection alerts on benchmark or eval quality drops
9. All existing Tier 1 tests (34) continue to pass
