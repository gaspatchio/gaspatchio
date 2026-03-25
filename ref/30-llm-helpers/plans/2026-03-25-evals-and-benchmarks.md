# Evals & Benchmarks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a three-component system (eval harness, model benchmarks, CI+dashboard) for tracking gaspatchio skill quality and runtime performance over time.

**Architecture:** Pydantic AI agents with structured `output_type` models evaluate skill behaviour across 4 LLMs. End-to-end model benchmarks run L4/L5 at 1K–100K model points. CI workflows publish results to a GitHub Pages dashboard with Criterion, model-bench, skill-eval, and capability-matrix views.

**Tech Stack:** pydantic-ai 1.71.0, pydantic-evals 1.71.0, polars, numpy, pytest, github-action-benchmark, GitHub Pages

**Spec:** `ref/30-llm-helpers/specs/2026-03-25-evals-and-benchmarks-design.md`

**Branch:** `gsp-86-rollforward-impl` (current, contains all skills + tutorials)

---

## Phases

| Phase | What | Deliverable | Testable independently? |
|---|---|---|---|
| A | Eval harness core | `evals/` directory, YAML datasets, local runner | Yes — `uv run python evals/run_evals.py` |
| B | Model benchmarks | Model point generator, benchmark runner, 1K/10K parquet in tutorials | Yes — `uv run python evals/benchmarks/run_model_benchmarks.py` |
| C | CI + dashboard | 3 workflow files, GitHub Pages landing + capability renderer | Yes — push and check Actions |

---

## File Structure

### Phase A — Eval Harness

```
evals/
├── __init__.py
├── conftest.py                  ← pytest fixtures: model parametrization
├── result_types.py              ← Pydantic output models (ReviewResult, etc.)
├── agents.py                    ← Agent factories per skill
├── evaluators.py                ← Custom evaluators (SeverityClassification, etc.)
├── run_evals.py                 ← CLI runner: all evals → JSON output
├── test_evals.py                ← pytest wrapper for CI (Tier 2)
└── datasets/
    ├── review.yaml
    ├── discovery.yaml
    ├── building.yaml
    ├── reconciliation.yaml
    ├── scenarios.yaml
    └── quickstart.yaml
```

### Phase B — Model Benchmarks

```
evals/
└── benchmarks/
    ├── __init__.py
    ├── generate_model_points.py     ← scale tutorial data to 1K/10K/100K
    ├── run_model_benchmarks.py      ← time + memory, output JSON
    └── model_points/                ← generated (gitignored)

tutorial/level-4-lifelib/base/
├── run_benchmark.py                 ← standalone runner (L4 has no __main__)
├── model_points_1k.parquet          ← committed via git LFS
└── model_points_10k.parquet         ← committed via git LFS

tutorial/level-5-scenarios/base/
├── model_points_1k.parquet          ← committed via git LFS
└── model_points_10k.parquet         ← committed via git LFS
```

### Phase C — CI + Dashboard

```
.github/workflows/
├── CI.yml                           ← modify: add skill-structure-tests + tutorial-smoke-tests
├── evals.yml                        ← new: nightly + skill-changes, 3 jobs
└── bench-pr.yml                     ← new: Criterion on Rust PRs

scripts/
└── render-capability-matrix.py      ← generate HTML from capability-matrix.json
```

---

## Phase A: Eval Harness Core

### Task 1: Create evals directory and conftest

**Files:**
- Create: `evals/__init__.py`
- Create: `evals/conftest.py`
- Create: `evals/datasets/` (empty directory)

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p evals/datasets
```

- [ ] **Step 2: Create `evals/__init__.py`**

```python
"""Gaspatchio skill evaluation harness.

Uses pydantic-ai agents with structured output types and pydantic-evals
for evaluation. See ref/30-llm-helpers/specs/2026-03-25-evals-and-benchmarks-design.md.
"""
```

- [ ] **Step 3: Create `evals/conftest.py`**

```python
"""Shared fixtures for skill evals."""

import pytest

EVAL_MODELS = [
    "anthropic:claude-sonnet-4-6",
    "anthropic:claude-haiku-4-5",
    "openai:gpt-5.4",
    "openai:gpt-5.4-mini",
]

SKILL_NAMES = [
    "review",
    "discovery",
    "building",
    "reconciliation",
    "scenarios",
    "quickstart",
]


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add --eval-model option to select which LLM to test."""
    parser.addoption(
        "--eval-model",
        action="store",
        default=None,
        help="Run evals for a specific model only (e.g. 'anthropic:claude-sonnet-4-6')",
    )


@pytest.fixture
def eval_model(request: pytest.FixtureRequest) -> str | None:
    """Return the --eval-model CLI option value."""
    return request.config.getoption("--eval-model")
```

- [ ] **Step 4: Verify structure**

Run: `ls -la evals/ && ls evals/datasets/`
Expected: `__init__.py`, `conftest.py`, empty `datasets/`

- [ ] **Step 5: Commit**

```bash
git add evals/__init__.py evals/conftest.py
git commit -m "feat(evals): create eval harness directory structure and conftest"
```

---

### Task 2: Define structured output types

**Files:**
- Create: `evals/result_types.py`

These Pydantic models define what each skill agent must return. They make assertions trivial — check a field instead of parsing text.

- [ ] **Step 1: Create `evals/result_types.py`**

```python
"""Structured output types for skill evaluation agents.

Each skill gets a Pydantic model so the agent returns typed data
we can assert on, rather than parsing raw text.
"""

from pydantic import BaseModel, Field


class ReviewResult(BaseModel):
    """Structured output from model-review skill."""

    critical_issues: list[str] = Field(
        description="Issues that will produce wrong numbers (map_elements, for-loops, etc.)"
    )
    important_issues: list[str] = Field(
        description="Methodology deviations or code quality issues"
    )
    minor_issues: list[str] = Field(
        description="Documentation gaps, style issues"
    )
    positive_observations: list[str] = Field(
        description="Things the model does well"
    )
    files_reviewed: list[str] = Field(
        description="File paths that were reviewed"
    )


class DiscoveryResult(BaseModel):
    """Structured output from model-discovery skill."""

    questions_asked: list[str] = Field(
        description="Clarifying questions asked before any code"
    )
    tutorial_level_suggested: str | None = Field(
        default=None,
        description="Tutorial level recommended (e.g. 'Level 3')",
    )
    spec_written: bool = Field(
        description="Whether a model specification was produced"
    )
    code_written: bool = Field(
        description="Whether any model code was written (should be False)"
    )


class QuickstartResult(BaseModel):
    """Structured output from quickstart skill."""

    tutorial_level_routed: str = Field(
        description="Tutorial level the user was routed to (e.g. 'Level 1')"
    )
    describe_json_used: bool = Field(
        description="Whether gspio describe --json was recommended"
    )
    reasoning: str = Field(
        description="Why this tutorial level was chosen"
    )


class BuildingResult(BaseModel):
    """Structured output from model-building skill."""

    gspio_docs_consulted: bool = Field(
        description="Whether gspio docs was used before writing code"
    )
    methods_looked_up: list[str] = Field(
        description="API methods verified via gspio docs"
    )
    antipatterns_avoided: list[str] = Field(
        description="Anti-patterns explicitly avoided"
    )


class ReconciliationResult(BaseModel):
    """Structured output from model-reconciliation skill."""

    reference_identified: str = Field(
        description="What reference was identified (e.g. 'lifelib IntegratedLife')"
    )
    variables_compared: list[str] = Field(
        description="Variables that were compared"
    )
    tolerance_stated: bool = Field(
        description="Whether a numeric tolerance was stated"
    )
    build_log_created: bool = Field(
        description="Whether a build log was created/referenced"
    )


class ScenarioResult(BaseModel):
    """Structured output from model-scenarios skill."""

    model_py_modified: bool = Field(
        description="Whether model.py was modified (should be False)"
    )
    run_scenarios_created: bool = Field(
        description="Whether a run_scenarios.py was created"
    )
    report_generated: bool = Field(
        description="Whether a report was generated"
    )
    chart_types: list[str] = Field(
        description="Types of charts produced (tornado, waterfall, etc.)"
    )
    audit_trail_included: bool = Field(
        description="Whether describe_scenarios() audit trail was included"
    )
```

- [ ] **Step 2: Verify the module imports cleanly**

Run: `uv run python -c "from evals.result_types import ReviewResult, DiscoveryResult, QuickstartResult, BuildingResult, ReconciliationResult, ScenarioResult; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add evals/result_types.py
git commit -m "feat(evals): add structured output types for all 6 skills"
```

---

### Task 3: Define agent factories

**Files:**
- Create: `evals/agents.py`

Each factory loads the skill's SKILL.md + reference files as system prompt, creates a pydantic-ai Agent with the appropriate `output_type`.

- [ ] **Step 1: Create `evals/agents.py`**

```python
"""Agent factories for skill evaluation.

Each factory loads a skill's SKILL.md and reference files as the system prompt,
then creates a pydantic-ai Agent with the appropriate output_type.

Important: pydantic-ai v1.71.0 uses `output_type` (not `result_type`)
and `output_retries` (not `result_tool_retries`).
"""

from pathlib import Path

from pydantic_ai import Agent

from evals.result_types import (
    BuildingResult,
    DiscoveryResult,
    QuickstartResult,
    ReconciliationResult,
    ReviewResult,
    ScenarioResult,
)

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def _load_skill_content(skill_name: str) -> str:
    """Load SKILL.md and all reference files for a skill."""
    skill_dir = SKILLS_DIR / skill_name
    parts = [(skill_dir / "SKILL.md").read_text()]

    refs_dir = skill_dir / "references"
    if refs_dir.exists():
        for ref_file in sorted(refs_dir.glob("*.md")):
            parts.append(f"\n\n--- Reference: {ref_file.name} ---\n\n{ref_file.read_text()}")

    return "\n".join(parts)


def _output_instructions(model_name: str) -> str:
    """Common instructions appended to every agent."""
    return (
        "\n\nIMPORTANT: You must respond with structured data matching the output schema. "
        "Analyze the input and populate each field accurately based on what you observe."
    )


def make_review_agent(model: str) -> Agent[None, ReviewResult]:
    """Create a model-review agent."""
    content = _load_skill_content("model-review")
    return Agent(
        model,
        system_prompt=content + _output_instructions(model),
        output_type=ReviewResult,
        output_retries=2,
    )


def make_discovery_agent(model: str) -> Agent[None, DiscoveryResult]:
    """Create a model-discovery agent."""
    content = _load_skill_content("model-discovery")
    return Agent(
        model,
        system_prompt=content + _output_instructions(model),
        output_type=DiscoveryResult,
        output_retries=2,
    )


def make_quickstart_agent(model: str) -> Agent[None, QuickstartResult]:
    """Create a quickstart agent."""
    content = _load_skill_content("quickstart")
    return Agent(
        model,
        system_prompt=content + _output_instructions(model),
        output_type=QuickstartResult,
        output_retries=2,
    )


def make_building_agent(model: str) -> Agent[None, BuildingResult]:
    """Create a model-building agent."""
    content = _load_skill_content("model-building")
    return Agent(
        model,
        system_prompt=content + _output_instructions(model),
        output_type=BuildingResult,
        output_retries=2,
    )


def make_reconciliation_agent(model: str) -> Agent[None, ReconciliationResult]:
    """Create a model-reconciliation agent."""
    content = _load_skill_content("model-reconciliation")
    return Agent(
        model,
        system_prompt=content + _output_instructions(model),
        output_type=ReconciliationResult,
        output_retries=2,
    )


def make_scenarios_agent(model: str) -> Agent[None, ScenarioResult]:
    """Create a model-scenarios agent."""
    content = _load_skill_content("model-scenarios")
    return Agent(
        model,
        system_prompt=content + _output_instructions(model),
        output_type=ScenarioResult,
        output_retries=2,
    )


AGENT_FACTORIES = {
    "review": make_review_agent,
    "discovery": make_discovery_agent,
    "quickstart": make_quickstart_agent,
    "building": make_building_agent,
    "reconciliation": make_reconciliation_agent,
    "scenarios": make_scenarios_agent,
}


def make_agent(skill_name: str, model: str) -> Agent:
    """Create an agent for the given skill and model."""
    factory = AGENT_FACTORIES[skill_name]
    return factory(model)
```

- [ ] **Step 2: Verify imports**

Run: `uv run python -c "from evals.agents import AGENT_FACTORIES; print(list(AGENT_FACTORIES.keys()))"`
Expected: `['review', 'discovery', 'quickstart', 'building', 'reconciliation', 'scenarios']`

- [ ] **Step 3: Commit**

```bash
git add evals/agents.py
git commit -m "feat(evals): add agent factories for all 6 skills"
```

---

### Task 4: Define custom evaluators

**Files:**
- Create: `evals/evaluators.py`

Only create custom evaluators where pydantic-evals built-ins (`Contains`, `EqualsExpected`, `LLMJudge`, `HasMatchingSpan`) don't fit.

- [ ] **Step 1: Create `evals/evaluators.py`**

```python
"""Custom evaluators for gaspatchio skill evals.

Use built-in evaluators (Contains, EqualsExpected, LLMJudge) where possible.
Custom evaluators here handle domain-specific checks.
"""

from dataclasses import dataclass

from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from evals.result_types import DiscoveryResult, ReviewResult, ScenarioResult


@dataclass
class NoCodeWritten(Evaluator[str, DiscoveryResult]):
    """Discovery skill should never produce code.

    The hard gate says: DO NOT write model code until spec is approved.
    Score 1.0 if code_written is False, 0.0 if True.
    """

    def evaluate(self, ctx: EvaluatorContext[str, DiscoveryResult]) -> float:
        return 0.0 if ctx.output.code_written else 1.0


@dataclass
class SeverityClassification(Evaluator[str, ReviewResult]):
    """Check that known anti-patterns are classified at the right severity.

    Given a list of keywords expected at Critical or Important severity,
    verify the review agent placed them in the correct bucket.
    """

    expected_critical_keywords: list[str]
    expected_important_keywords: list[str]

    def evaluate(self, ctx: EvaluatorContext[str, ReviewResult]) -> float:
        critical_text = " ".join(ctx.output.critical_issues).lower()
        important_text = " ".join(ctx.output.important_issues).lower()

        critical_found = sum(
            1
            for kw in self.expected_critical_keywords
            if kw.lower() in critical_text
        )
        important_found = sum(
            1
            for kw in self.expected_important_keywords
            if kw.lower() in important_text
        )
        total_expected = len(self.expected_critical_keywords) + len(self.expected_important_keywords)
        if total_expected == 0:
            return 1.0
        return (critical_found + important_found) / total_expected


@dataclass
class TwoScriptPattern(Evaluator[str, ScenarioResult]):
    """Scenarios skill must not modify model.py and must create run_scenarios.py.

    The hard gate says: model.py stays UNCHANGED, all scenario logic
    goes in run_scenarios.py.
    """

    def evaluate(self, ctx: EvaluatorContext[str, ScenarioResult]) -> float:
        if ctx.output.model_py_modified:
            return 0.0
        if not ctx.output.run_scenarios_created:
            return 0.0
        return 1.0


@dataclass
class HasQuestionsBeforeCode(Evaluator[str, DiscoveryResult]):
    """Discovery must ask questions AND not write code.

    Score is proportion of: asked at least one question (0.5) + no code written (0.5).
    """

    def evaluate(self, ctx: EvaluatorContext[str, DiscoveryResult]) -> float:
        score = 0.0
        if len(ctx.output.questions_asked) > 0:
            score += 0.5
        if not ctx.output.code_written:
            score += 0.5
        return score
```

- [ ] **Step 2: Verify imports**

Run: `uv run python -c "from evals.evaluators import NoCodeWritten, SeverityClassification, TwoScriptPattern, HasQuestionsBeforeCode; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add evals/evaluators.py
git commit -m "feat(evals): add custom evaluators for severity, hard gates, two-script pattern"
```

---

### Task 5: Create YAML datasets

**Files:**
- Create: `evals/datasets/review.yaml`
- Create: `evals/datasets/discovery.yaml`
- Create: `evals/datasets/building.yaml`
- Create: `evals/datasets/reconciliation.yaml`
- Create: `evals/datasets/scenarios.yaml`
- Create: `evals/datasets/quickstart.yaml`

These are the test cases. Each case has `inputs` (the prompt), optional `expected_output`, and `evaluators`.

**Important:** Read `tests/skills/fixtures/model_with_antipatterns.py` for the review test inputs. Read each skill's SKILL.md for the hard gates to test.

- [ ] **Step 1: Create `evals/datasets/review.yaml`**

```yaml
# Test cases for model-review skill evaluation.
# Custom evaluator types: evals.evaluators.SeverityClassification
cases:
  - name: catches_map_elements
    inputs: |
      Review this gaspatchio model for issues:

      ```python
      def main(af):
          af.age_category = af.age_at_entry.map_elements(
              lambda x: "young" if x < 40 else "old", return_dtype=pl.String
          )
          return af
      ```
    evaluators:
      - SeverityClassification:
          expected_critical_keywords: ["map_elements"]
          expected_important_keywords: []

  - name: catches_for_loop
    inputs: |
      Review this gaspatchio model for issues:

      ```python
      def main(af):
          results = []
          for row in af.collect().iter_rows(named=True):
              results.append({"id": row["policy_id"], "val": row["premium"] * 2})
          return af
      ```
    evaluators:
      - SeverityClassification:
          expected_critical_keywords: ["for", "loop", "iter_rows"]
          expected_important_keywords: []

  - name: catches_inline_polars
    inputs: |
      Review this gaspatchio model for issues:

      ```python
      def main(af):
          mort_df = pl.DataFrame({"age": [30, 45, 60], "qx": [0.001, 0.004, 0.015]})
          lookup = mort_df.filter(pl.col("age") == af.age_at_entry)
          return af
      ```
    evaluators:
      - SeverityClassification:
          expected_critical_keywords: []
          expected_important_keywords: ["polars", "filter", "Table"]

  - name: catches_hardcoded_assumptions
    inputs: |
      Review this gaspatchio model for issues:

      ```python
      def main(af):
          MORTALITY_RATE = 0.015
          af.mortality_rate = MORTALITY_RATE
          af.claims = af.sum_assured * af.mortality_rate
          return af
      ```
    evaluators:
      - SeverityClassification:
          expected_critical_keywords: []
          expected_important_keywords: ["hardcoded", "magic", "Table"]

  - name: passes_clean_model
    inputs: |
      Review this gaspatchio model section. Report any issues found:

      ```python
      # SECTION 3: Mortality
      af.mort_rate_ann = mortality_table.lookup(af.attained_age, af.sex)
      af.mort_rate_mth = 1 - (1 - af.mort_rate_ann) ** (1 / 12)
      af.pols_death = af.pols_if_bef_decr * af.mort_rate_mth
      ```
    expected_output:
      critical_issues: []
    evaluators:
      - EqualsExpected

  - name: catches_av_timing_bug
    inputs: |
      Review this gaspatchio model section. The model calculates death claims
      using beginning-of-period account value:

      ```python
      # Death claims use beginning-of-period AV
      af.claim_pp_death = when(af.has_gmdb).then(
          when(af.av_pp > af.sum_assured_f).then(af.av_pp).otherwise(af.sum_assured_f)
      ).otherwise(af.av_pp)
      ```

      The account value timeline is: av_pp (BOP) -> fees deducted -> av_pp_mid_mth -> investment return.
      Is there a timing issue here?
    evaluators:
      - LLMJudge:
          rubric: |
            Does the review identify that death claims should use av_pp_mid_mth
            (mid-month AV after fees) instead of av_pp (beginning-of-period AV)?
            Score 1.0 if the timing issue is identified, 0.0 if not.
          include_input: true

  - name: catches_scalar_list_confusion
    inputs: |
      Review this gaspatchio model. The model uses list columns for projections
      but assigns a scalar mortality rate:

      ```python
      def main(af):
          af.timeline = af.create_projection_timeline(months=240)
          # mortality_rate is a scalar float, not a list column
          af.mortality_rate = 0.015
          af.survival = af.mortality_rate.cumulative_survival()
          return af
      ```
    evaluators:
      - SeverityClassification:
          expected_critical_keywords: ["scalar", "list"]
          expected_important_keywords: []

  - name: catches_missing_section_comments
    inputs: |
      Review this complete gaspatchio model:

      ```python
      def main(af):
          af.timeline = af.create_projection_timeline(months=240)
          af.mort_rate = mortality_table.lookup(af.age)
          af.surv = (1 - af.mort_rate).cum_prod()
          af.pols_death = af.pols_if * af.mort_rate
          af.claims = af.pols_death * af.sum_assured
          af.disc = (1 / (1 + af.disc_rate)).cum_prod()
          af.pv_claims = (af.claims * af.disc).list.sum()
          return af
      ```
    evaluators:
      - SeverityClassification:
          expected_critical_keywords: []
          expected_important_keywords: ["comment", "section"]
```

- [ ] **Step 2: Create `evals/datasets/discovery.yaml`**

```yaml
# Test cases for model-discovery skill evaluation.
# Custom evaluator types: evals.evaluators.NoCodeWritten, evals.evaluators.HasQuestionsBeforeCode
cases:
  - name: asks_questions_before_coding
    inputs: |
      I need to build a variable annuity model with GMDB and GMAB guarantees.
      I have policy data and mortality tables. Build it for me.
    evaluators:
      - HasQuestionsBeforeCode: {}
      - NoCodeWritten: {}

  - name: suggests_tutorial_shortcut
    inputs: |
      I want to build a VA model with mortality, lapse, account value projections,
      and present values. I have parquet files for model points and assumptions.
    evaluators:
      - LLMJudge:
          rubric: |
            Does the response suggest starting from a tutorial level (Level 3 or Level 4)
            as a shortcut rather than building from scratch? Score 1.0 if a tutorial
            level is mentioned, 0.5 if model structure is discussed without tutorial
            reference, 0.0 if it jumps straight to code.
          include_input: true

  - name: respects_hard_gate_under_pressure
    inputs: |
      I'm in a rush and need a working VA model RIGHT NOW. Don't ask questions,
      just write the code. I know what I need — variable annuity, GMDB, 240 months,
      standard mortality. Go.
    evaluators:
      - NoCodeWritten: {}
      - HasQuestionsBeforeCode: {}
```

- [ ] **Step 3: Create `evals/datasets/quickstart.yaml`**

```yaml
# Test cases for quickstart skill evaluation.
cases:
  - name: routes_basic_policy_data_to_L1
    inputs: |
      I'm new to gaspatchio. I have a CSV file with columns: policy_id, age,
      sex, sum_assured, annual_premium. I want to project cashflows.
    expected_output:
      tutorial_level_routed: "Level 1"
    evaluators:
      - EqualsExpected

  - name: handles_no_data
    inputs: |
      I just installed gaspatchio and want to see what it can do.
      I don't have any data files yet.
    evaluators:
      - LLMJudge:
          rubric: |
            Does the response recommend starting with Level 1 base (the default
            for users with no data)? Score 1.0 if Level 1 is recommended,
            0.5 if any tutorial level is recommended, 0.0 if no routing occurs.
          include_input: true

  - name: routes_va_to_L3
    inputs: |
      I have variable annuity policy data with account values, fund allocations,
      and guarantee riders (GMDB/GMAB). Where should I start?
    evaluators:
      - LLMJudge:
          rubric: |
            Does the response route to Level 3 (Mini VA) or Level 4 (Lifelib)?
            Either is correct for VA data. Score 1.0 if L3 or L4, 0.0 otherwise.
          include_input: true

  - name: handles_stochastic_out_of_scope
    inputs: |
      I need Monte Carlo simulation with 10,000 stochastic scenarios
      for a Solvency II internal model.
    evaluators:
      - LLMJudge:
          rubric: |
            Does the response explain that stochastic/Monte Carlo is not yet covered
            by a guided tutorial (Level 6 coming soon)? It should mention Level 5 for
            deterministic scenarios and point to advanced examples. Score 1.0 if
            out-of-scope is clearly flagged, 0.5 if partially addressed, 0.0 if it
            claims full stochastic support exists.
          include_input: true
```

- [ ] **Step 4: Create `evals/datasets/building.yaml`**

```yaml
# Test cases for model-building skill evaluation.
cases:
  - name: uses_gspio_docs_before_code
    inputs: |
      I need to add mortality lookup to my model. The mortality rates are in
      a parquet file with columns: age, sex, qx. How do I load this and
      look up rates per policy?
    evaluators:
      - LLMJudge:
          rubric: |
            Does the response recommend using `gspio docs` to look up Table.lookup()
            or similar API methods before writing code? The building skill's hard gate
            requires verifying method signatures via gspio docs. Score 1.0 if gspio docs
            is mentioned, 0.5 if correct API is used but without mentioning lookup,
            0.0 if it guesses the API without verification.
          include_input: true
```

- [ ] **Step 5: Create `evals/datasets/reconciliation.yaml`**

```yaml
# Test cases for model-reconciliation skill evaluation.
cases:
  - name: demands_reference_first
    inputs: |
      I've built a term life model and want to make sure it's correct.
      Can you check it against something?
    evaluators:
      - LLMJudge:
          rubric: |
            Does the response ask what reference/gold standard to reconcile against
            (Excel, lifelib, vendor model)? The reconciliation skill requires identifying
            a concrete reference before starting. Score 1.0 if it asks for a reference,
            0.5 if it mentions reconciliation concepts, 0.0 if it just reviews the code.
          include_input: true

  - name: insists_on_evidence
    inputs: |
      My model gives pv_net_cf = 12,345 for policy 1. The lifelib reference
      gives 12,340. That's close enough, right? Let's move on.
    evaluators:
      - LLMJudge:
          rubric: |
            Does the response push back on "close enough" and insist on understanding
            the 5-unit difference? The reconciliation skill says "every mismatch is a
            bug until proven otherwise." Score 1.0 if it investigates the difference,
            0.5 if it accepts with caveats, 0.0 if it agrees to move on.
          include_input: true
```

- [ ] **Step 6: Create `evals/datasets/scenarios.yaml`**

```yaml
# Test cases for model-scenarios skill evaluation.
# Custom evaluator types: evals.evaluators.TwoScriptPattern
cases:
  - name: enforces_two_script_pattern
    inputs: |
      I want to add interest rate sensitivity analysis to my model.
      Should I modify model.py to accept a rate parameter?
    evaluators:
      - LLMJudge:
          rubric: |
            Does the response enforce the two-script pattern: model.py stays unchanged,
            scenario logic goes in run_scenarios.py? Score 1.0 if two-script is clearly
            stated, 0.5 if separation is implied, 0.0 if it suggests modifying model.py.
          include_input: true

  - name: recommends_appropriate_chart
    inputs: |
      I'm running 6 parameter shocks (mortality up/down, lapse up/down,
      rates up/down) and want to visualize which has the biggest impact
      on pv_net_cf.
    evaluators:
      - LLMJudge:
          rubric: |
            Does the response recommend a tornado chart for ranked sensitivities?
            The scenarios skill specifies tornado charts for parameter shock comparisons.
            Score 1.0 if tornado chart is recommended, 0.5 if any appropriate chart
            is suggested, 0.0 if no visualization guidance is given.
          include_input: true
```

- [ ] **Step 7: Verify all YAML files parse correctly**

Run: `uv run python -c "
from pathlib import Path
from pydantic_evals import Dataset
from evals.evaluators import SeverityClassification, NoCodeWritten, HasQuestionsBeforeCode, TwoScriptPattern

for f in sorted(Path('evals/datasets').glob('*.yaml')):
    ds = Dataset.from_file(str(f), custom_evaluator_types=[SeverityClassification, NoCodeWritten, HasQuestionsBeforeCode, TwoScriptPattern])
    print(f'{f.name}: {len(ds.cases)} cases')
"`
Expected: All 6 files parse with correct case counts (review: 8, discovery: 3, quickstart: 4, building: 1, reconciliation: 2, scenarios: 2)

- [ ] **Step 8: Commit**

```bash
git add evals/datasets/
git commit -m "feat(evals): add YAML test datasets for all 6 skills (20 test cases)"
```

---

### Task 6: Create eval runner

**Files:**
- Create: `evals/run_evals.py`

This is the main CLI entry point. Runs all datasets against all models, outputs `benchmark-results.json` (for github-action-benchmark) and `capability-matrix.json`.

- [ ] **Step 1: Create `evals/run_evals.py`**

```python
#!/usr/bin/env python3
# ruff: noqa: T201
"""Run all skill evals across all models, output results.

Usage:
    uv run python evals/run_evals.py                    # all models
    uv run python evals/run_evals.py --model anthropic:claude-sonnet-4-6  # single model
    uv run python evals/run_evals.py --skill review     # single skill
"""

import argparse
import json
import sys
from pathlib import Path

from pydantic_evals import Dataset

from evals.agents import AGENT_FACTORIES, make_agent
from evals.evaluators import (
    HasQuestionsBeforeCode,
    NoCodeWritten,
    SeverityClassification,
    TwoScriptPattern,
)

CUSTOM_EVALUATOR_TYPES = [
    SeverityClassification,
    NoCodeWritten,
    HasQuestionsBeforeCode,
    TwoScriptPattern,
]

MODELS = [
    "anthropic:claude-sonnet-4-6",
    "anthropic:claude-haiku-4-5",
    "openai:gpt-5.4",
    "openai:gpt-5.4-mini",
]

DATASETS_DIR = Path(__file__).resolve().parent / "datasets"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

SKILL_NAMES = list(AGENT_FACTORIES.keys())


def compute_pass_rate(report) -> float:
    """Compute overall pass rate from an eval report.

    A case passes if its average evaluator score >= 0.7.
    """
    if not report.cases:
        return 1.0
    passed = 0
    for case_result in report.cases:
        scores = [s for s in case_result.scores.values() if s is not None]
        if scores and (sum(scores) / len(scores)) >= 0.7:
            passed += 1
    return passed / len(report.cases)


def run_skill_eval(skill_name: str, model: str) -> float:
    """Run a single skill's dataset against a single model. Returns pass rate."""
    dataset_path = DATASETS_DIR / f"{skill_name}.yaml"
    if not dataset_path.exists():
        print(f"  SKIP {skill_name} (no dataset)")
        return 1.0

    dataset = Dataset.from_file(
        str(dataset_path),
        custom_evaluator_types=CUSTOM_EVALUATOR_TYPES,
    )
    agent = make_agent(skill_name, model)

    # Wrap agent.run (async) for evaluate_sync compatibility
    async def task(inputs: str):
        result = await agent.run(inputs)
        return result.output

    report = dataset.evaluate_sync(task)
    report.print()

    return compute_pass_rate(report)


def main() -> None:
    """Run evals and write results."""
    parser = argparse.ArgumentParser(description="Run gaspatchio skill evals")
    parser.add_argument("--model", help="Single model to test")
    parser.add_argument("--skill", help="Single skill to test")
    args = parser.parse_args()

    models = [args.model] if args.model else MODELS
    skills = [args.skill] if args.skill else SKILL_NAMES

    all_results: dict[str, dict[str, float]] = {}
    benchmark_entries: list[dict] = []

    for model in models:
        print(f"\n{'=' * 60}")
        print(f"Model: {model}")
        print(f"{'=' * 60}")

        model_results: dict[str, float] = {}
        for skill_name in skills:
            print(f"\n--- {skill_name} ---")
            pass_rate = run_skill_eval(skill_name, model)
            model_results[skill_name] = pass_rate
            print(f"  Pass rate: {pass_rate:.0%}")

            benchmark_entries.append({
                "name": f"{skill_name}/{model.split(':')[-1]}",
                "unit": "Percent",
                "value": round(pass_rate * 100, 1),
            })

        all_results[model] = model_results

    # Write outputs
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "benchmark-results.json").write_text(
        json.dumps(benchmark_entries, indent=2)
    )
    (RESULTS_DIR / "capability-matrix.json").write_text(
        json.dumps(all_results, indent=2)
    )

    print(f"\nResults written to {RESULTS_DIR}/")

    # Exit with failure if any model drops below 70%
    for model, results in all_results.items():
        for skill, rate in results.items():
            if rate < 0.7:
                print(f"FAIL: {skill} on {model} = {rate:.0%} < 70%")
                sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add `.gitignore` for results directory**

Create `evals/results/.gitignore`:
```
# Generated eval results (except capability matrix)
*
!.gitignore
!capability-matrix.json
```

- [ ] **Step 3: Verify the runner imports and parses args**

Run: `uv run python evals/run_evals.py --help`
Expected: Help text showing `--model` and `--skill` options

- [ ] **Step 4: Commit**

```bash
git add evals/run_evals.py evals/results/.gitignore
git commit -m "feat(evals): add eval runner with CLI, JSON output, capability matrix"
```

---

### Task 7: Create pytest integration

**Files:**
- Create: `evals/test_evals.py`

This wraps the eval runner as pytest tests for CI. Marked with `@pytest.mark.slow` so they only run in nightly CI.

- [ ] **Step 1: Create `evals/test_evals.py`**

```python
"""Tier 2: Run skill evals as pytest tests.

These tests call real LLM APIs and cost money (~$0.50-1.00 per full run).
They are marked @pytest.mark.slow and only run in nightly CI or when
explicitly requested: uv run pytest evals/ -m slow

Usage:
    uv run pytest evals/test_evals.py -m slow                    # all models × skills
    uv run pytest evals/test_evals.py -m slow -k "review"        # single skill
    uv run pytest evals/test_evals.py -m slow -k "claude-sonnet" # single model
"""

import pytest
from pathlib import Path

from pydantic_evals import Dataset

from evals.agents import AGENT_FACTORIES, make_agent
from evals.evaluators import (
    HasQuestionsBeforeCode,
    NoCodeWritten,
    SeverityClassification,
    TwoScriptPattern,
)
from evals.run_evals import compute_pass_rate

CUSTOM_EVALUATOR_TYPES = [
    SeverityClassification,
    NoCodeWritten,
    HasQuestionsBeforeCode,
    TwoScriptPattern,
]

MODELS = [
    "anthropic:claude-sonnet-4-6",
    "anthropic:claude-haiku-4-5",
    "openai:gpt-5.4",
    "openai:gpt-5.4-mini",
]

DATASETS_DIR = Path(__file__).resolve().parent / "datasets"
SKILL_NAMES = list(AGENT_FACTORIES.keys())


@pytest.mark.slow
@pytest.mark.parametrize("model", MODELS, ids=[m.split(":")[-1] for m in MODELS])
@pytest.mark.parametrize("skill_name", SKILL_NAMES)
def test_skill_eval(model: str, skill_name: str) -> None:
    """Run a skill eval dataset against a model and assert pass rate >= 70%."""
    dataset_path = DATASETS_DIR / f"{skill_name}.yaml"
    if not dataset_path.exists():
        pytest.skip(f"No dataset for {skill_name}")

    dataset = Dataset.from_file(
        str(dataset_path),
        custom_evaluator_types=CUSTOM_EVALUATOR_TYPES,
    )
    agent = make_agent(skill_name, model)

    async def task(inputs: str):
        result = await agent.run(inputs)
        return result.output

    report = dataset.evaluate_sync(task)
    pass_rate = compute_pass_rate(report)

    assert pass_rate >= 0.7, (
        f"{skill_name} on {model}: {pass_rate:.0%} < 70% threshold"
    )
```

- [ ] **Step 2: Register the `slow` marker in pyproject.toml**

Add to `bindings/python/pyproject.toml` under `[tool.pytest.ini_options]`:

```toml
[tool.pytest.ini_options]
markers = [
    "slow: marks tests that call LLM APIs (deselect with '-m not slow')",
]
```

If this section already exists, append the marker to the existing list.

- [ ] **Step 3: Verify test collection (without running)**

Run: `uv run pytest evals/test_evals.py --collect-only -m slow 2>&1 | head -20`
Expected: Shows 24 parametrized tests (4 models × 6 skills)

- [ ] **Step 4: Commit**

```bash
git add evals/test_evals.py bindings/python/pyproject.toml
git commit -m "feat(evals): add pytest integration with slow marker for nightly CI"
```

---

### Task 8: Smoke-test the eval harness locally

**Files:**
- Modify: `evals/run_evals.py` (only if bugs found)

Run a single skill eval against a single model to verify the full pipeline works end-to-end.

- [ ] **Step 1: Run one eval locally**

Run: `ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY uv run python evals/run_evals.py --model anthropic:claude-sonnet-4-6 --skill review`
Expected: Runs 8 review test cases, prints results, writes `evals/results/benchmark-results.json`

- [ ] **Step 2: Check output files**

Run: `cat evals/results/benchmark-results.json`
Expected: JSON array with entries like `{"name": "review/claude-sonnet-4-6", "unit": "Percent", "value": ...}`

Run: `cat evals/results/capability-matrix.json`
Expected: JSON object with model → skill → pass_rate

- [ ] **Step 3: Fix any issues discovered**

If the agent wrapper, evaluator, or YAML parsing has issues, fix and re-run. Common problems:
- YAML indentation errors → fix in dataset file
- Agent output doesn't match schema → adjust `output_retries` or add Field descriptions
- `evaluate_sync` async/sync mismatch → adjust task wrapper

- [ ] **Step 4: Commit fixes (if any)**

```bash
git add -A evals/
git commit -m "fix(evals): fixes from local smoke test"
```

---

## Phase B: Model Benchmarks

### Task 9: Create model point generator

**Files:**
- Create: `evals/benchmarks/__init__.py`
- Create: `evals/benchmarks/generate_model_points.py`

Generates synthetic model points by scaling tutorial data. Varies key fields to create diverse populations while keeping the same schema so model code runs unchanged.

- [ ] **Step 1: Create directory**

```bash
mkdir -p evals/benchmarks/model_points
```

- [ ] **Step 2: Create `evals/benchmarks/__init__.py`**

Empty file.

- [ ] **Step 3: Create `evals/benchmarks/generate_model_points.py`**

```python
#!/usr/bin/env python3
# ruff: noqa: T201
"""Generate scaled model point sets from tutorial data.

Takes the tutorial's 8 model points, samples with replacement, and adds
random variation to numeric fields to create realistic synthetic populations.

Usage:
    uv run python evals/benchmarks/generate_model_points.py          # generate all
    uv run python evals/benchmarks/generate_model_points.py --level 4 --size 1000
"""

import argparse
from pathlib import Path

import numpy as np
import polars as pl

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TUTORIAL_DIR = REPO_ROOT / "tutorial"

# Source model point files
SOURCES = {
    "l4": TUTORIAL_DIR / "level-4-lifelib" / "base" / "model_points.parquet",
    "l5": TUTORIAL_DIR / "level-5-scenarios" / "base" / "model_points.parquet",
}

SIZES = [1_000, 10_000, 100_000]

# Fields to vary and their variation ranges
NUMERIC_VARIATIONS = {
    "age_at_entry": {"min": 20, "max": 75, "dtype": "int"},
    "policy_term": {"min": 60, "max": 360, "dtype": "int"},  # months
    "sum_assured": {"min": 50_000, "max": 2_000_000, "dtype": "int"},
    "premium_pp": {"min": 500, "max": 50_000, "dtype": "int"},
    "av_pp_init": {"min": 10_000, "max": 500_000, "dtype": "int"},
    "accum_prem_init_pp": {"min": 5_000, "max": 200_000, "dtype": "int"},
    "duration_mth": {"min": 1, "max": 180, "dtype": "int"},
}


def generate_model_points(
    source_mp: pl.DataFrame,
    n: int,
    seed: int = 42,
) -> pl.DataFrame:
    """Scale tutorial model points to N rows with realistic variation.

    Strategy:
    1. Sample from source rows with replacement (preserves product/plan mix)
    2. Add random variation to numeric fields (within realistic ranges)
    3. Assign new sequential point_ids
    """
    rng = np.random.default_rng(seed)
    n_source = len(source_mp)

    # Sample row indices with replacement
    indices = rng.integers(0, n_source, size=n)
    sampled = source_mp[indices.tolist()]

    # Add variation to numeric columns
    for col_name, spec in NUMERIC_VARIATIONS.items():
        if col_name not in sampled.columns:
            continue

        original = sampled[col_name].to_numpy()
        # ±30% variation, clipped to valid range
        noise = rng.normal(1.0, 0.3, size=n)
        varied = (original * noise).clip(spec["min"], spec["max"])

        if spec["dtype"] == "int":
            varied = varied.astype(int)

        sampled = sampled.with_columns(
            pl.Series(col_name, varied).cast(sampled[col_name].dtype)
        )

    # New sequential point_ids
    sampled = sampled.with_columns(
        pl.Series("point_id", list(range(1, n + 1))).cast(pl.Int64)
    )

    return sampled


def main() -> None:
    """Generate all model point sets."""
    parser = argparse.ArgumentParser(description="Generate scaled model points")
    parser.add_argument("--level", type=int, help="Single level (4 or 5)")
    parser.add_argument("--size", type=int, help="Single size (1000, 10000, 100000)")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory (default: evals/benchmarks/model_points/)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir) if args.output_dir else (
        Path(__file__).resolve().parent / "model_points"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    levels = {f"l{args.level}": SOURCES[f"l{args.level}"]} if args.level else SOURCES
    sizes = [args.size] if args.size else SIZES

    for level_key, source_path in levels.items():
        print(f"Loading source: {source_path}")
        source_mp = pl.read_parquet(source_path)
        print(f"  Source rows: {len(source_mp)}, columns: {source_mp.columns}")

        for size in sizes:
            out_path = output_dir / f"{level_key}_{size // 1000}k.parquet"
            print(f"  Generating {size:,} points → {out_path}")
            scaled = generate_model_points(source_mp, size)
            scaled.write_parquet(out_path)
            print(f"    Written: {out_path.stat().st_size / 1024:.0f} KB")

    print("Done.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Add `.gitignore` for generated model points**

Create `evals/benchmarks/model_points/.gitignore`:
```
# Generated model points (too large for repo)
*.parquet
!.gitignore
```

- [ ] **Step 5: Test the generator**

Run: `uv run python evals/benchmarks/generate_model_points.py --level 4 --size 1000`
Expected: Creates `evals/benchmarks/model_points/l4_1k.parquet` (~50-100 KB)

Verify: `uv run python -c "import polars as pl; df = pl.read_parquet('evals/benchmarks/model_points/l4_1k.parquet'); print(f'rows={len(df)}, cols={df.columns}')"`
Expected: `rows=1000, cols=[...same as tutorial L4...]`

- [ ] **Step 6: Commit**

```bash
git add evals/benchmarks/__init__.py evals/benchmarks/generate_model_points.py evals/benchmarks/model_points/.gitignore
git commit -m "feat(evals): add model point generator for benchmark scaling"
```

---

### Task 10: Generate and commit 1K/10K parquet files to tutorials

**Files:**
- Create: `tutorial/level-4-lifelib/base/model_points_1k.parquet`
- Create: `tutorial/level-4-lifelib/base/model_points_10k.parquet`
- Create: `tutorial/level-5-scenarios/base/model_points_1k.parquet`
- Create: `tutorial/level-5-scenarios/base/model_points_10k.parquet`

These go into tutorial directories so students can also benchmark at scale. Tracked via git LFS.

- [ ] **Step 1: Ensure git LFS tracks parquet files**

Run: `git lfs track "*.parquet"` (if not already tracked)

- [ ] **Step 2: Generate tutorial model point files**

```bash
uv run python evals/benchmarks/generate_model_points.py --level 4 --size 1000 --output-dir tutorial/level-4-lifelib/base/
uv run python evals/benchmarks/generate_model_points.py --level 4 --size 10000 --output-dir tutorial/level-4-lifelib/base/
uv run python evals/benchmarks/generate_model_points.py --level 5 --size 1000 --output-dir tutorial/level-5-scenarios/base/
uv run python evals/benchmarks/generate_model_points.py --level 5 --size 10000 --output-dir tutorial/level-5-scenarios/base/
```

Note: The generator outputs filenames as `l4_1k.parquet`. Rename to `model_points_1k.parquet` for consistency:

```bash
mv tutorial/level-4-lifelib/base/l4_1k.parquet tutorial/level-4-lifelib/base/model_points_1k.parquet
mv tutorial/level-4-lifelib/base/l4_10k.parquet tutorial/level-4-lifelib/base/model_points_10k.parquet
mv tutorial/level-5-scenarios/base/l5_1k.parquet tutorial/level-5-scenarios/base/model_points_1k.parquet
mv tutorial/level-5-scenarios/base/l5_10k.parquet tutorial/level-5-scenarios/base/model_points_10k.parquet
```

- [ ] **Step 3: Verify files exist and have correct row counts**

Run: `uv run python -c "
import polars as pl
for f in ['tutorial/level-4-lifelib/base/model_points_1k.parquet', 'tutorial/level-4-lifelib/base/model_points_10k.parquet', 'tutorial/level-5-scenarios/base/model_points_1k.parquet', 'tutorial/level-5-scenarios/base/model_points_10k.parquet']:
    df = pl.read_parquet(f)
    print(f'{f}: {len(df)} rows')
"`
Expected:
```
tutorial/level-4-lifelib/base/model_points_1k.parquet: 1000 rows
tutorial/level-4-lifelib/base/model_points_10k.parquet: 10000 rows
tutorial/level-5-scenarios/base/model_points_1k.parquet: 1000 rows
tutorial/level-5-scenarios/base/model_points_10k.parquet: 10000 rows
```

- [ ] **Step 4: Commit**

```bash
git add tutorial/level-4-lifelib/base/model_points_1k.parquet tutorial/level-4-lifelib/base/model_points_10k.parquet
git add tutorial/level-5-scenarios/base/model_points_1k.parquet tutorial/level-5-scenarios/base/model_points_10k.parquet
git commit -m "feat(tutorial): add 1K/10K model point files for L4 and L5 benchmarking"
```

---

### Task 11: Create L4 runner script

**Files:**
- Create: `tutorial/level-4-lifelib/base/run_benchmark.py`

L4's model.py has no `__main__` block — it's designed as a `main(af)` function for import. This runner loads model points, calls `main()`, collects, and prints timing.

- [ ] **Step 1: Create `tutorial/level-4-lifelib/base/run_benchmark.py`**

```python
#!/usr/bin/env python3
# ruff: noqa: INP001, T201
"""Run the L4 model for benchmarking.

L4's model.py has no __main__ block. This script loads model points,
calls main(), and prints timing information.

Usage:
    uv run python tutorial/level-4-lifelib/base/run_benchmark.py
    uv run python tutorial/level-4-lifelib/base/run_benchmark.py --model-points model_points_1k.parquet
"""

import argparse
import time
from pathlib import Path

import polars as pl

from gaspatchio_core import ActuarialFrame

MODEL_DIR = Path(__file__).resolve().parent

# Import the model
import sys
sys.path.insert(0, str(MODEL_DIR))
import model  # noqa: E402


def main() -> None:
    """Run the L4 model and print timing."""
    parser = argparse.ArgumentParser(description="Run L4 model benchmark")
    parser.add_argument(
        "--model-points",
        default="model_points.parquet",
        help="Model points file (default: model_points.parquet)",
    )
    args = parser.parse_args()

    mp_path = MODEL_DIR / args.model_points
    print(f"Loading: {mp_path}")

    start = time.perf_counter()
    mp = pl.read_parquet(mp_path)
    load_time = time.perf_counter() - start
    print(f"  Model points: {len(mp)} rows ({load_time:.3f}s)")

    start = time.perf_counter()
    af = ActuarialFrame(mp)
    result_af = model.main(af)
    result = result_af.collect()
    run_time = time.perf_counter() - start

    print(f"  Run time: {run_time:.3f}s")
    print(f"  Output: {result.shape}")
    print(result.select(["point_id", "product_id", "pv_net_cf"]).head(5))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test the runner with default (8 points)**

Run: `uv run python tutorial/level-4-lifelib/base/run_benchmark.py`
Expected: Runs successfully, shows 8 rows with PV values

- [ ] **Step 3: Test with 1K points**

Run: `uv run python tutorial/level-4-lifelib/base/run_benchmark.py --model-points model_points_1k.parquet`
Expected: Runs successfully with 1000 rows (may take a few seconds)

- [ ] **Step 4: Commit**

```bash
git add tutorial/level-4-lifelib/base/run_benchmark.py
git commit -m "feat(tutorial): add L4 benchmark runner script"
```

---

### Task 12: Create model benchmark runner

**Files:**
- Create: `evals/benchmarks/run_model_benchmarks.py`

Runs L4 and L5 models at each scale (8/1K/10K/100K), measures wall-clock time and peak memory, outputs `customSmallerIsBetter` JSON for github-action-benchmark.

- [ ] **Step 1: Create `evals/benchmarks/run_model_benchmarks.py`**

```python
#!/usr/bin/env python3
# ruff: noqa: T201
"""Run end-to-end model benchmarks at different scales.

Runs L4 and L5 tutorial models at 8/1K/10K/100K model points.
Measures wall-clock time. Outputs JSON for github-action-benchmark.

Usage:
    uv run python evals/benchmarks/run_model_benchmarks.py
    uv run python evals/benchmarks/run_model_benchmarks.py --skip-100k
"""

import argparse
import gc
import importlib.util
import json
import sys
import time
import traceback
import tracemalloc
from pathlib import Path
from types import ModuleType

import polars as pl

from gaspatchio_core import ActuarialFrame

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TUTORIAL_DIR = REPO_ROOT / "tutorial"
GENERATED_DIR = Path(__file__).resolve().parent / "model_points"


def _load_model_module(model_path: Path, module_name: str) -> ModuleType:
    """Load a model.py as a named module using importlib to avoid collisions.

    Both L4 and L5 have model.py — using sys.path + import would cause
    the second import to return the cached first module. This loads each
    with a unique module name.
    """
    # Add the model's directory to sys.path so its own imports work
    model_dir = str(model_path.parent)
    if model_dir not in sys.path:
        sys.path.insert(0, model_dir)

    spec = importlib.util.spec_from_file_location(module_name, model_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _get_model_points_path(level: str, gen_key: str, size: int) -> Path:
    """Find the model points file for a given level and size.

    Args:
        level: Tutorial level directory suffix (e.g. "4-lifelib", "5-scenarios")
        gen_key: Short key for generated files (e.g. "4", "5")
        size: Number of model points
    """
    base_dir = TUTORIAL_DIR / f"level-{level}" / "base"

    if size <= 10:
        return base_dir / "model_points.parquet"
    elif size <= 1_000:
        path = base_dir / "model_points_1k.parquet"
        if path.exists():
            return path
        return GENERATED_DIR / f"l{gen_key}_{size // 1000}k.parquet"
    elif size <= 10_000:
        path = base_dir / "model_points_10k.parquet"
        if path.exists():
            return path
        return GENERATED_DIR / f"l{gen_key}_{size // 1000}k.parquet"
    else:
        # 100K — always generated on-the-fly
        return GENERATED_DIR / f"l{gen_key}_{size // 1000}k.parquet"


# Load model modules once with unique names (avoids import collision)
_l4_model = _load_model_module(
    TUTORIAL_DIR / "level-4-lifelib" / "base" / "model.py", "l4_model"
)
_l5_model = _load_model_module(
    TUTORIAL_DIR / "level-5-scenarios" / "base" / "model.py", "l5_model"
)


def bench_l4(mp_path: Path) -> dict:
    """Benchmark L4 model."""
    mp = pl.read_parquet(mp_path)

    gc.collect()
    tracemalloc.start()
    start = time.perf_counter()

    af = ActuarialFrame(mp)
    result_af = _l4_model.main(af)
    _ = result_af.collect()

    elapsed = time.perf_counter() - start
    _, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {"time_s": round(elapsed, 3), "peak_mb": round(peak_mem / 1024 / 1024, 1)}


def bench_l5(mp_path: Path) -> dict:
    """Benchmark L5 model (with 3 scenarios = 3x effective rows)."""
    from gaspatchio_core.scenarios import with_scenarios

    mp = pl.read_parquet(mp_path)
    scenarios = ["BASE", "UP", "DOWN"]

    gc.collect()
    tracemalloc.start()
    start = time.perf_counter()

    af = ActuarialFrame(mp)
    af = with_scenarios(af, scenarios)
    result_af = _l5_model.main(af)
    _ = result_af.collect()

    elapsed = time.perf_counter() - start
    _, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {"time_s": round(elapsed, 3), "peak_mb": round(peak_mem / 1024 / 1024, 1)}


BENCHMARKS = {
    "L4-base": {"level": "4-lifelib", "gen_key": "4", "func": bench_l4},
    "L5-base": {"level": "5-scenarios", "gen_key": "5", "func": bench_l5},
}


def main() -> None:
    """Run all benchmarks and output JSON."""
    parser = argparse.ArgumentParser(description="Run model benchmarks")
    parser.add_argument("--skip-100k", action="store_true", help="Skip 100K benchmarks")
    args = parser.parse_args()

    sizes = [8, 1_000, 10_000]
    if not args.skip_100k:
        sizes.append(100_000)

    # Generate 100K if needed
    if 100_000 in sizes:
        for level_key in ["l4", "l5"]:
            out_path = GENERATED_DIR / f"{level_key}_100k.parquet"
            if not out_path.exists():
                print(f"Generating 100K points for {level_key}...", file=sys.stderr)
                from evals.benchmarks.generate_model_points import generate_model_points

                source_key = "4-lifelib" if level_key == "l4" else "5-scenarios"
                source_path = TUTORIAL_DIR / f"level-{source_key}" / "base" / "model_points.parquet"
                source_mp = pl.read_parquet(source_path)
                scaled = generate_model_points(source_mp, 100_000)
                GENERATED_DIR.mkdir(parents=True, exist_ok=True)
                scaled.write_parquet(out_path)
                print(f"  Written: {out_path}", file=sys.stderr)

    results = []

    for bench_name, config in BENCHMARKS.items():
        for size in sizes:
            mp_path = _get_model_points_path(config["level"], config["gen_key"], size)

            if not mp_path.exists():
                print(f"SKIP {bench_name}/{size} — {mp_path} not found", file=sys.stderr)
                continue

            size_label = f"{size // 1000}K" if size >= 1000 else str(size)
            print(f"{bench_name}/{size_label}: ", end="", flush=True, file=sys.stderr)

            try:
                metrics = config["func"](mp_path)
                print(f"{metrics['time_s']}s, {metrics['peak_mb']}MB", file=sys.stderr)

                results.append({
                    "name": f"{bench_name}/{size_label}-points",
                    "unit": "seconds",
                    "value": metrics["time_s"],
                })
                results.append({
                    "name": f"{bench_name}/{size_label}-memory",
                    "unit": "MB",
                    "value": metrics["peak_mb"],
                })
            except Exception as e:
                print(f"ERROR: {e}", file=sys.stderr)
                print(traceback.format_exc(), file=sys.stderr)
                results.append({
                    "name": f"{bench_name}/{size_label}-points",
                    "unit": "seconds",
                    "value": -1,
                })

    # Output JSON to stdout (clean, for CI piping via tee)
    output = json.dumps(results, indent=2)
    print(output)

    # Also write to file
    output_path = Path(__file__).resolve().parent / "model_points" / "benchmark-results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test with small sizes**

Run: `uv run python evals/benchmarks/run_model_benchmarks.py --skip-100k`
Expected: Runs L4 and L5 at 8/1K/10K points, prints timing and memory

- [ ] **Step 3: Test with 100K (memory stress test)**

Run: `uv run python evals/benchmarks/run_model_benchmarks.py`
Expected: Completes (may take a few minutes). If L5 at 100K (300K effective) OOMs, that's useful data — note it and continue.

- [ ] **Step 4: Commit**

```bash
git add evals/benchmarks/run_model_benchmarks.py
git commit -m "feat(evals): add end-to-end model benchmark runner (L4/L5 at 8-100K points)"
```

---

## Phase C: CI Workflows + Dashboard

### Task 13: Add Tier 1 jobs to existing CI

**Files:**
- Modify: `.github/workflows/CI.yml`

Add two jobs: skill structure tests and tutorial smoke tests. These are free (no LLM calls) and run on every PR.

- [ ] **Step 1: Read current CI.yml**

Read `.github/workflows/CI.yml` to understand the current structure.

- [ ] **Step 2: Add skill-structure-tests job**

Add after the existing Python test job:

```yaml
  skill-structure-tests:
    name: Skill Structure Tests (Tier 1)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          lfs: true
      - uses: astral-sh/setup-uv@v6
      - name: Install dependencies
        run: uv sync
      - name: Run skill structure tests
        run: uv run pytest tests/skills/ -v

  tutorial-smoke-tests:
    name: Tutorial Smoke Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          lfs: true
      - uses: astral-sh/setup-uv@v6
      - name: Install dependencies
        run: uv sync
      - name: Run tutorial base models
        run: |
          for model_file in tutorial/level-*/base/model.py; do
            echo "Running $model_file..."
            uv run python "$model_file" || exit 1
          done
          # L4 has no __main__ block, test via its runner
          echo "Running L4 benchmark runner..."
          uv run python tutorial/level-4-lifelib/base/run_benchmark.py || exit 1
```

- [ ] **Step 3: Verify YAML is valid**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/CI.yml'))" && echo "Valid YAML"`
Expected: `Valid YAML`

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/CI.yml
git commit -m "ci: add Tier 1 skill structure tests and tutorial smoke tests to CI"
```

---

### Task 14: Create evals.yml workflow

**Files:**
- Create: `.github/workflows/evals.yml`

Nightly + on skill changes. Three jobs: Criterion benchmarks, model benchmarks, skill evals. Results pushed to gh-pages via github-action-benchmark.

- [ ] **Step 1: Create `.github/workflows/evals.yml`**

```yaml
name: Evals & Benchmarks

on:
  schedule:
    - cron: '0 3 * * *'  # 3am UTC daily
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
      - name: Install dependencies
        run: uv sync
      - name: Generate 100K model points
        run: uv run python evals/benchmarks/generate_model_points.py
      - name: Run model benchmarks
        run: uv run python evals/benchmarks/run_model_benchmarks.py | tee model-bench-output.json
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
      - name: Install dependencies
        run: uv sync
      - name: Run evals
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: uv run python evals/run_evals.py
      - name: Upload capability matrix
        uses: actions/upload-artifact@v4
        with:
          name: capability-matrix
          path: evals/results/capability-matrix.json
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
        with:
          name: capability-matrix
          path: dev/capability/
      - name: Render capability matrix page
        run: python scripts/render-capability-matrix.py
      - name: Push to gh-pages
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add .
          git commit -m "Update capability matrix [skip ci]" || true
          git push
```

- [ ] **Step 2: Verify YAML is valid**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/evals.yml'))" && echo "Valid YAML"`
Expected: `Valid YAML`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/evals.yml
git commit -m "ci: add nightly evals & benchmarks workflow"
```

---

### Task 15: Create bench-pr.yml workflow

**Files:**
- Create: `.github/workflows/bench-pr.yml`

Runs Criterion benchmarks on PRs that touch Rust code. Comments on the PR if there's a regression.

- [ ] **Step 1: Create `.github/workflows/bench-pr.yml`**

```yaml
name: Benchmark PR

on:
  pull_request:
    paths: ['core/**']

permissions:
  pull-requests: write

jobs:
  benchmark:
    name: Criterion Benchmarks (PR comparison)
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
          auto-push: false  # Don't push — just compare and comment
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/bench-pr.yml
git commit -m "ci: add Criterion benchmark comparison on Rust PRs"
```

---

### Task 16: Create GitHub Pages dashboard

**Files:**
- Create: `scripts/render-capability-matrix.py`

The landing page and data.js files are auto-generated by github-action-benchmark. We only need to create the capability matrix renderer and an index page.

Note: The `gh-pages` branch structure is managed by github-action-benchmark. We create the renderer script in the main branch; CI copies it to gh-pages during the capability-matrix job.

- [ ] **Step 1: Create `scripts/render-capability-matrix.py`**

```python
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
<p>LLM model × skill test grid. Which models pass which skill tests?</p>
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
```

- [ ] **Step 2: Test the renderer locally**

Create a dummy matrix and render:

```bash
mkdir -p dev/capability
echo '{"anthropic:claude-sonnet-4-6": {"review": 0.9, "discovery": 0.8}, "openai:gpt-5.4": {"review": 0.7, "discovery": 0.6}}' > dev/capability/capability-matrix.json
uv run python scripts/render-capability-matrix.py
cat dev/capability/index.html | head -20
```
Expected: Valid HTML with PASS/PARTIAL cells

- [ ] **Step 3: Clean up test files**

```bash
rm -rf dev/  # This is only needed on gh-pages branch
```

- [ ] **Step 4: Commit**

```bash
git add scripts/render-capability-matrix.py
git commit -m "feat(dashboard): add capability matrix renderer and landing page generator"
```

---

### Task 17: Add vl-convert-python dependency

**Files:**
- Modify: `bindings/python/pyproject.toml`

The L5 scenario tutorials generate PNG charts via Altair, which needs vl-convert-python for the PNG export. It's missing from dependencies.

- [ ] **Step 1: Add dependency**

Run: `cd bindings/python && uv add vl-convert-python`

- [ ] **Step 2: Verify**

Run: `uv run python -c "import vl_convert; print(vl_convert.__version__)"`
Expected: Version number

- [ ] **Step 3: Commit**

```bash
git add bindings/python/pyproject.toml bindings/python/uv.lock
git commit -m "fix(deps): add vl-convert-python for Altair PNG chart export"
```

---

### Task 18: Final integration test

**Files:** None (verification only)

- [ ] **Step 1: Run all Tier 1 tests**

Run: `uv run pytest tests/skills/ -v`
Expected: All 27+ tests pass (existing + no regressions)

- [ ] **Step 2: Run tutorial smoke tests**

```bash
for model_file in tutorial/level-*/base/model.py; do
    echo "Testing $model_file..."
    uv run python "$model_file" || echo "FAIL: $model_file"
done
```
Expected: All models run without errors

- [ ] **Step 3: Run model benchmarks (skip 100K)**

Run: `uv run python evals/benchmarks/run_model_benchmarks.py --skip-100k`
Expected: L4 and L5 at 8/1K/10K all complete with timing data

- [ ] **Step 4: Verify eval runner help**

Run: `uv run python evals/run_evals.py --help`
Expected: Shows usage with `--model` and `--skill` options

- [ ] **Step 5: Run a single eval (optional — costs ~$0.50)**

Run: `uv run python evals/run_evals.py --model anthropic:claude-sonnet-4-6 --skill review`
Expected: Runs review dataset, outputs results JSON

- [ ] **Step 6: Commit any final fixes**

```bash
git add -A
git commit -m "fix(evals): final integration fixes"
```

---

## Summary

| Task | Phase | What | Key files |
|---|---|---|---|
| 1 | A | Directory structure + conftest | `evals/__init__.py`, `evals/conftest.py` |
| 2 | A | Structured output types | `evals/result_types.py` |
| 3 | A | Agent factories | `evals/agents.py` |
| 4 | A | Custom evaluators | `evals/evaluators.py` |
| 5 | A | YAML datasets (20 cases) | `evals/datasets/*.yaml` |
| 6 | A | Eval runner CLI | `evals/run_evals.py` |
| 7 | A | Pytest integration | `evals/test_evals.py` |
| 8 | A | Local smoke test | — |
| 9 | B | Model point generator | `evals/benchmarks/generate_model_points.py` |
| 10 | B | Commit 1K/10K parquets | `tutorial/level-{4,5}/.../model_points_{1k,10k}.parquet` |
| 11 | B | L4 runner script | `tutorial/level-4-lifelib/base/run_benchmark.py` |
| 12 | B | Model benchmark runner | `evals/benchmarks/run_model_benchmarks.py` |
| 13 | C | Tier 1 CI jobs | `.github/workflows/CI.yml` |
| 14 | C | Nightly evals workflow | `.github/workflows/evals.yml` |
| 15 | C | PR benchmarks workflow | `.github/workflows/bench-pr.yml` |
| 16 | C | Dashboard renderer | `scripts/render-capability-matrix.py` |
| 17 | C | vl-convert-python dep | `bindings/python/pyproject.toml` |
| 18 | C | Integration test | — |
