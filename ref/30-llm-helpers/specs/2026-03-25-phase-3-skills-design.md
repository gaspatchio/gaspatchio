# Phase 3: Gaspatchio Skills — Design Spec

## Overview

Bring the Superpowers experience to actuaries building models on gaspatchio. Six skills forming a workflow chain from first install through production-quality reconciled models with scenario analysis, packaged as a Claude Code / Copilot plugin.

The skills adopt Superpowers' key patterns: hard gates between phases, Socratic discovery, anti-rationalization engineering, distrust-based review chains, and evidence-before-claims. Applied to the actuarial domain with ASOP 56 professional standards, gaspatchio-specific anti-patterns, and tutorial-level references throughout.

## Audience

- **Primary**: Actuaries who know Excel, learning Python-based modeling with gaspatchio
- **Secondary**: LLM agents (Claude Code, Copilot, Cursor) assisting those actuaries
- **Tertiary**: Experienced Python actuaries who want structured model development workflows

## Skill Relationships

### Full workflow (greenfield model)

When building a model from scratch, the skills chain naturally:

```
quickstart → model-discovery → model-building → model-review → model-reconciliation → model-scenarios
```

### Every skill is independently invocable

**Skills are NOT a mandatory chain.** Each skill can and should be used standalone whenever it applies. An actuary who already has a working model can jump straight to model-scenarios. An actuary reviewing a colleague's PR uses model-review without having done discovery or building. The chain above is the *maximum* workflow for a greenfield build — most real usage will be a single skill or a subset.

| Skill | Standalone use case | Chain position (if building from scratch) |
|---|---|---|
| **quickstart** | First-time user exploring gaspatchio | 1st |
| **model-discovery** | Scoping any new model or model change | 2nd |
| **model-building** | Writing or modifying any model code | 3rd |
| **model-review** | Reviewing ANY model change — yours or someone else's. **The most commonly used skill standalone.** | 4th |
| **model-reconciliation** | Matching a model against any reference (Excel, lifelib, prior version) | 5th |
| **model-scenarios** | Running scenarios on any validated model | 6th |

### Hard gates (within a skill, not between skills)

Each skill has its own completion gate — a condition that must be met before the skill's work is considered done. These gates apply within the skill, not as prerequisites for other skills.

| Skill | Completion gate |
|---|---|
| quickstart | Must run a tutorial model successfully |
| model-discovery | Must have approved model spec before writing code |
| model-building | Must pass post-build checklist |
| model-review | Must address all Critical/Important issues |
| model-reconciliation | Must show quantitative evidence of match |
| model-scenarios | Must produce report with charts and audit trail |

## Directory Structure

```
skills/
├── quickstart/
│   └── SKILL.md
├── model-discovery/
│   └── SKILL.md
├── model-building/
│   ├── SKILL.md
│   └── references/
│       ├── model-phases.md
│       ├── assumptions.md
│       ├── conditionals-and-lists.md
│       ├── timing-and-dates.md
│       ├── scenarios.md
│       └── common-mistakes.md
├── model-review/
│   ├── SKILL.md
│   └── references/
│       ├── gaspatchio-antipatterns.md
│       └── asop56-checklist.md
├── model-reconciliation/
│   ├── SKILL.md
│   └── references/
│       ├── technique-quick-checks.md
│       ├── technique-pattern-detection.md
│       ├── technique-linear-regression.md
│       ├── technique-cohort-analysis.md
│       ├── technique-timeseries-residual.md
│       ├── technique-waterfall.md
│       ├── technique-pca.md
│       └── technique-heatmap.md
└── model-scenarios/
    └── SKILL.md
```

---

## Skill 1: quickstart

**Frontmatter:**
```yaml
---
name: gaspatchio-quickstart
description: Use when user is new to gaspatchio, setting up for the first time, or wants to get started quickly with actuarial modeling
---
```

**Purpose**: Get an actuary from zero to running model in 10 minutes.

**Flow**:
1. Verify install: `uv run gspio --version`
2. If user has data: inspect it with `uv run gspio describe --json data.parquet` — agent reads JSON, explains what it sees (model points vs assumption table), suggests which tutorial level matches
3. Copy the appropriate tutorial level base model
4. Run it: `uv run python model.py`
5. Explain the output, walk through the code section by section
6. If user has their own data: swap it in, adjust the model
7. Guide to next step: model-discovery for new models, model-building for extending tutorials

**Tutorial level routing**:
- "I have policy data and want to project cashflows" → L1 base
- "I need to use assumption tables" → L2 base
- "I want a complete VA model" → L3 base
- "I'm porting from lifelib" → L4
- "I need scenario analysis" → L5

**Size**: ~100 lines. No reference files.

---

## Skill 2: model-discovery

**Frontmatter:**
```yaml
---
name: gaspatchio-model-discovery
description: Use when building an actuarial model from scratch, porting from Excel or lifelib, or when the model specification is unclear. Socratic discovery before any code is written.
---
```

**Purpose**: Socratic method to understand what the actuary needs before writing any code. Adapted from Superpowers' brainstorming skill.

**Hard gate**: Do NOT write model code until the spec is approved. Do NOT skip to model-building.

**Flow** (one question at a time):
1. **Inspect data first**: `uv run gspio describe --json` on all provided data files. Agent reads the JSON and understands the data structure before asking questions.
2. **Product understanding**: What type of insurance product? What cashflows? What guarantees?
3. **Decrement model**: Which decrements? (mortality, lapse, disability, etc.) What timing conventions?
4. **Assumptions**: What assumption tables exist? What dimensions? How are rates structured?
5. **Projection**: Monthly or annual? How many timesteps? What drives the projection length?
6. **Outputs**: What PV variables? What intermediate variables for reconciliation? What reporting format?
7. **Propose 2-3 model structures**: With trade-offs. Reference tutorial levels as starting points.
8. **Write model spec**: Section-by-section matching gaspatchio's 11-section structure.
9. **User approves spec** → transition to model-building.

**Actuarial knowledge lookup**: Use `uv run gspio knowledge "<concept>" -T <tag>` to research unfamiliar actuarial concepts before asking about them.

**Tutorial shortcuts**:
- If the model looks like L3 mini-VA → "This is very similar to the Level 3 tutorial. Want to start from that and modify?"
- If porting from lifelib → "Level 4 has a reconciled lifelib port. Want to start there?"

**Anti-rationalizations**:
- "I already know what I want" → "Even experienced actuaries benefit from structured discovery. Let me confirm the data structure first."
- "Just start coding" → "Models built without a spec take longer to debug. The spec takes 10 minutes and saves hours."

**Changes from existing gaspatchio-discovery.md**:
- Add `gspio describe --json` as mandatory first step
- Add tutorial level routing
- Add L5 scenario references
- Strengthen the Socratic one-question-at-a-time protocol (Superpowers pattern)
- Add explicit hard gate and anti-rationalization section

---

## Skill 3: model-building

**Frontmatter:**
```yaml
---
name: gaspatchio-model-building
description: Use when writing or editing gaspatchio model code (model.py files). Enforces ActuarialFrame idioms, mandatory API lookups, and section-by-section building.
---
```

**Purpose**: Code writing skill that enforces gaspatchio idioms and builds models section by section with incremental validation.

**Hard gate**: Must pass post-build checklist before transitioning to model-review.

**Core rules** (carried from existing skill):
- MANDATORY lookup gate: `uv run gspio docs "<method>"` before using any API method
- Build in model's section order (time setup → mortality → lapse → AV → claims → cashflows → PV)
- Validate incrementally: `uv run gspio run-single-policy model.py data.parquet 1 --output-file /tmp/result.parquet`

**New sections** (from pending observations):

**Data enrichment** (observation #16): How to join product params, dynamic lapse params, space params from assumption files. Cross-join pattern for shared parameters. Unpivot for wide-format data.

**Product-specific formulas** (observation #13): `when(af.formula_id == "DL001").then(dl001).otherwise(dl002)` — parameter-driven formula selection, not hardcoded logic.

**Decrement ordering — BEF_DECR** (observation #18): Maturities first → remove → add NB → deaths from BEF_DECR → lapses from survivors. Why it matters for NB business.

**Discount factor conventions** (observation #15): cum_prod vs closed-form `exp(-t * ln(1+r))`. Both approaches documented with note: match the reference formula when reconciling.

**Table.lookup() is exact-match** (observation #17): Added to common-mistakes. Table does not interpolate — generate full-range tables.

**Post-build checklist** (observation #7, folded from model-review idea):
- [ ] No `map_elements` or `apply` calls
- [ ] No Python for-loops over rows
- [ ] All sections have header comments
- [ ] All `Table.lookup()` calls verified with `gspio docs`
- [ ] Model runs with `--output-file` without errors
- [ ] Key outputs have expected signs (claims positive, net_cf can be negative)
- [ ] All assumption Tables created with correct dimensions

**Tutorial references throughout**: Each concept links to the tutorial step where it's demonstrated.

**Changes from existing gaspatchio-building.md**:
- Add 5 new reference sections listed above
- Add post-build checklist
- Strengthen `--output-file` guidance throughout
- Add tutorial cross-references
- Add scenario-aware building patterns (L5)
- Update gotcha table with new entries (#15-19)

---

## Skill 4: model-review

**Frontmatter:**
```yaml
---
name: gaspatchio-model-review
description: Use when reviewing changes to a gaspatchio model, validating model quality, or preparing a model for production use. Covers both gaspatchio code quality and actuarial professional standards (ASOP 56).
---
```

**Purpose**: Two-layer review of model changes — gaspatchio code quality AND actuarial methodology. Adapted from Superpowers' code-review pattern with actuarial-specific checks.

**Hard gate**: All Critical and Important issues must be addressed before transitioning to model-reconciliation.

**When to trigger**:
- After model-building completes (automatic in the chain)
- When reviewing changes to an existing model
- Before merging model changes to production
- When preparing for regulatory review

### Layer 1: Gaspatchio Code Quality

**Anti-patterns to catch** (reference: `gaspatchio-antipatterns.md`):

| Anti-pattern | What to look for | Severity |
|---|---|---|
| `map_elements` / `apply` | Any use of these in model code | Critical |
| Python for-loops over data | `for row in df.iter_rows()` etc. | Critical |
| Inline Polars instead of Table | `df.filter(pl.col("age") == af.age)` instead of `Table.lookup()` | Important |
| Guessed API signatures | Method calls not verified via `gspio docs` | Important |
| Missing `--output-file` validation | Model not tested with actual data | Important |
| Wrong projection accessor | `.list.sum()` where `.projection.cumulative_survival()` needed | Important |
| Scalar/list confusion | Scalar operation where list is needed or vice versa | Critical |
| Missing `when/then/otherwise` | Boolean masking where conditional is clearer | Minor |
| No section comments | Model sections not labeled | Minor |
| Hardcoded assumptions | Magic numbers instead of Table lookups | Important |

**How to review**: Run `git diff` on changed files, read each change, classify issues with file:line references.

### Layer 2: Actuarial Methodology (ASOP 56-informed)

**Checks** (reference: `asop56-checklist.md`):

**Correctness** (Critical):
- Are formulas mathematically correct?
- Are lookup table references pointing at the right data?
- Is the calculation order correct (no missing or extra steps)?
- Are multiplicative vs additive operations applied correctly?
- Is decrement timing consistent (BOP vs mid-month vs EOP)?

**Assumption integrity** (Important):
- Are changed assumptions consistent with unchanged assumptions?
- Are assumption sources documented in comments?
- Is the aggregate of assumptions reasonable?
- Are stale assumptions flagged?

**Change impact** (Important):
- Does the change propagate to all dependent locations?
- Are there unintended side effects on unchanged outputs?
- Is the analysis of change plausible? (Run before/after, compare)
- Do outputs still reconcile to prior runs?

**Documentation** (Minor):
- Is the change rationale documented?
- Are material limitations disclosed?
- Is there evidence of testing?

### Issue classification

| Severity | Definition | Action |
|---|---|---|
| **Critical** | Will produce wrong numbers or crash | Must fix before proceeding |
| **Important** | Methodology deviation or significant code quality issue | Must fix before production |
| **Minor** | Documentation, style, or minor improvement | Fix when convenient |

### Distrust-based review (Superpowers pattern)

The reviewer should NOT trust:
- "Results look reasonable" — run the model and check quantitatively
- "This assumption is close enough" — compare against the source data
- "We already checked this" — verify the evidence exists
- "The change is small" — small changes can have large downstream effects

### Review output format

```markdown
## Model Review: [model name]

### Summary
[1-2 sentences: overall assessment]

### Critical Issues
- [file:line] [description] [why it matters]

### Important Issues
- [file:line] [description] [recommendation]

### Minor Issues
- [file:line] [description]

### Positive Observations
- [what the model does well]
```

**Transition**: Once all Critical and Important issues are addressed → model-reconciliation (if a reference exists) or done.

---

## Skill 5: model-reconciliation

**Frontmatter:**
```yaml
---
name: gaspatchio-model-reconciliation
description: Use when reconciling a gaspatchio model against a reference implementation (Excel, lifelib, another model), matching specific numeric targets, or validating model correctness through comparison.
---
```

**Purpose**: Variable-by-variable reconciliation against a gold standard. The most technically detailed skill.

**Hard gate**: Must show quantitative evidence of match (specific tolerance, specific metrics) before claiming the model is correct. No hand-waving.

**Evidence-before-claims** (Superpowers pattern):
- Run `gspio run-single-policy model.py data.parquet 1 --output-file /tmp/result.parquet`
- Compare quantitatively: `uv run gspio describe --json /tmp/result.parquet`
- Report specific metrics: "mort_rate matches at 0.0000% across all 82 timesteps"
- THEN claim the variable matches

**New sections** (from pending observations):

**Learning reconciliation** (observation #12): Point to L3 Step 06 as a teaching exercise. "If you're new to reconciliation, start with the 4-gap exercise in `tutorial/level-3-mini-va/steps/06-reconcile/`."

**Matching intermediates, not just aggregates** (observation #14): "Passing PVs is necessary but not sufficient. A model can give the right PVs for the wrong reasons. Compare intermediate variables (mort_rate, pols_if, av_pp) per timestep, not just aggregate PVs."

**Canonical example**: L4 lifelib reconciliation — 0.0000% across 1,016 points, 35 variables, ~9M data points. Reference `tutorial/level-4-lifelib/reconciliation_report.md`.

**Changes from existing gaspatchio-reconciliation.md**:
- Add learning reconciliation section (Step 06)
- Add intermediates guidance
- Add `gspio describe --json` for output inspection
- Strengthen L4 as canonical example
- Add tutorial references throughout
- All 8 technique reference files carried over unchanged

---

## Skill 6: model-scenarios

**Frontmatter:**
```yaml
---
name: gaspatchio-model-scenarios
description: Use when running scenario analysis, applying parameter shocks, performing sensitivity sweeps, or producing scenario comparison reports on a gaspatchio model.
---
```

**Purpose**: Guide an agent through deterministic scenario analysis on a validated model. Covers the full workflow from simple interest rate scenarios through regulatory stress tests with professional reports.

**Hard gate**: Must produce a report with charts and audit trail before claiming scenarios are complete.

**When to trigger**:
- After model-reconciliation (the model is validated, now run scenarios)
- When user asks about "what-if", "sensitivity", "stress test", "scenario"
- When user needs to compare model results under different assumptions

### Two-script pattern

The skill enforces gaspatchio's scenario architecture: model.py is unchanged, all scenario logic lives in run_scenarios.py.

- `model.py` — The projection model. Accepts `assumptions_override` for shocked tables. Not modified for scenarios.
- `run_scenarios.py` — Orchestration. Loads data, configures scenarios, calls model, generates charts and report.

### Scenario types (progressive)

**Level 1 — Interest rate scenarios**:
- `with_scenarios(af, ["BASE", "UP", "DOWN"])` — cross-join with scenario IDs
- Model's discount rate lookup uses `scenario_id` column automatically
- Chart: grouped bar comparing PV by scenario

**Level 2 — Parameter shocks**:
- Declarative JSON config: `{"table": "mortality_select", "multiply": 1.2}`
- `parse_scenario_config()` to load, `Table.with_shock()` to apply
- Loop: fresh assumptions per scenario, apply shocks, run model
- Chart: tornado chart (the classic actuarial sensitivity visualization)

**Level 3 — Conditional shocks**:
- `where` clause: `{"table": "mortality_select", "multiply": 1.5, "where": {"attained_age": {"gte": 65}}}`
- `when` clause: time-conditional shocks
- `pipeline`: chain operations (multiply then clip)
- Chart: cashflow trajectory comparison over time

**Level 4 — Sensitivity sweeps**:
- `sensitivity_analysis()` for 1D parameter sweeps
- Manual cross-product for 2D interaction grids
- Charts: sensitivity curve + 2D heatmap

**Level 5 — Regulatory scenario comparison**:
- Named scenarios as economic narratives ("PANDEMIC", "RATE_SHOCK", "MASS_LAPSE")
- Multi-shock combinations
- `describe_scenarios()` for audit trail / governance
- Chart: grouped bar + full regulatory-style report

### Report requirements

Every scenario run must produce `report/report.md` with:
- Model metadata (points, scenarios, runtime)
- Scenario configuration (JSON config inline)
- Results summary table with % change from base
- Embedded Altair chart PNGs
- Key findings (auto-generated)
- Audit trail from `describe_scenarios()`

### CLI commands

```bash
# Standard model run (no scenarios)
uv run gspio run-model model.py model_points.parquet

# Scenario analysis with report
uv run python run_scenarios.py
```

### Tutorial reference

L5 is the worked example for every concept in this skill:
- Base: `tutorial/level-5-scenarios/base/` (interest rate scenarios)
- Step 01: parameter shocks with tornado chart
- Step 02: conditional shocks with cashflow lines
- Step 03: sensitivity analysis with heatmap
- Step 04: scenario comparison with regulatory report

### Anti-rationalizations

- "I'll just modify the model for each scenario" → "Model.py stays unchanged. Use assumptions_override."
- "I don't need a report" → "Reports with audit trails are required for governance. describe_scenarios() generates them."
- "The tornado chart is enough" → "Different scenario types need different visualizations. Match the chart to the analysis."

---

## Testing Strategy

Three tiers, using Pydantic AI (`TestModel` for deterministic CI, real models for nightly evals) and Pydantic Evals for scoring.

### Tier 1: Every PR — Deterministic, Free, Fast

**Pydantic AI `TestModel`** tests that skills wire up correctly without calling any LLM. `TestModel` is a fake model that automatically invokes all tools and generates structurally valid output by walking the Pydantic schema. Zero API cost, millisecond execution, fully deterministic.

```python
from pydantic_ai.models.test import TestModel
from pydantic_ai import capture_run_messages

async def test_review_skill_produces_structured_output():
    """Verify the review agent produces correctly typed output."""
    with capture_run_messages() as messages:
        with review_agent.override(model=TestModel()):
            result = await review_agent.run("Review this model")
    # Structural assertions — deterministic
    assert isinstance(result.data.critical_issues, list)
    assert isinstance(result.data.important_issues, list)
    assert isinstance(result.data.files_reviewed, list)
```

**What Tier 1 catches**: broken imports, schema violations, wrong tool definitions, missing required fields, tool orchestration errors. Does NOT test prompt quality or reasoning.

**Plus tutorial smoke tests** — all 25+ tutorial models still run:

```python
import pytest
from pathlib import Path

TUTORIAL_MODELS = sorted(Path("tutorial").rglob("model.py"))

@pytest.mark.parametrize("model_path", TUTORIAL_MODELS, ids=lambda p: str(p))
def test_tutorial_model_runs(model_path):
    """Every tutorial model must execute without errors."""
    result = subprocess.run(["uv", "run", "python", str(model_path)], capture_output=True)
    assert result.returncode == 0, f"FAIL: {model_path}\n{result.stderr.decode()}"
```

### Tier 2: Nightly — Probabilistic, Costs Tokens, High Value

**Pydantic Evals** (`pydantic-evals` package) for scoring skill behaviour against a curated test dataset. Code-first, version-controlled, with code-based grading for most checks and LLM-as-judge only for semantic quality.

```python
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

class ContainsKeyword(Evaluator[str, str]):
    """Code-based grading: deterministic check for expected content."""
    keyword: str

    def evaluate(self, ctx: EvaluatorContext[str, str]) -> float:
        return 1.0 if self.keyword.lower() in ctx.output.lower() else 0.0

class SeverityClassification(Evaluator[str, ReviewResult]):
    """Check that known anti-patterns are classified at the right severity."""
    expected_critical: list[str]  # keywords that must appear in critical issues

    def evaluate(self, ctx: EvaluatorContext[str, ReviewResult]) -> float:
        found = sum(
            1 for kw in self.expected_critical
            if any(kw in issue for issue in ctx.output.critical_issues)
        )
        return found / len(self.expected_critical) if self.expected_critical else 1.0

# Test dataset
review_dataset = Dataset(
    cases=[
        Case(
            name="catches_map_elements",
            inputs=Path("tests/skills/fixtures/model_with_antipatterns.py").read_text(),
            expected_output="critical issue mentioning map_elements",
            evaluators=[ContainsKeyword(keyword="map_elements")],
        ),
        Case(
            name="catches_wrong_decrement_ordering",
            inputs=Path("tests/skills/fixtures/model_with_antipatterns.py").read_text(),
            expected_output="important issue about decrement ordering",
            evaluators=[ContainsKeyword(keyword="decrement")],
        ),
        Case(
            name="passes_clean_model",
            inputs=Path("tutorial/level-4-lifelib/base/model.py").read_text(),
            expected_output="no critical issues",
            evaluators=[SeverityClassification(expected_critical=[])],
        ),
    ],
)

report = review_dataset.evaluate_sync(run_review_agent)
report.print(include_input=False, include_output=True)
# Track scores over time — alert on regression, not individual failures
```

**Grading strategy**: Use **code-based evaluators** (contains, regex, count) for 80% of checks. Use **LLM-as-judge** only for semantic quality ("is this a good model spec?" or "does this review identify the right root cause?"). This minimises non-determinism and cost.

**Test cases per skill:**

| Skill | Test | Fixture | Grading method |
|---|---|---|---|
| **quickstart** | Routes to correct tutorial level | "I have a VA model" | Code: contains "L3" or "L5" |
| **model-discovery** | Asks questions before coding | "build me a model" | Code: contains "?" and NOT "def main" |
| **model-building** | References gspio docs | "Add mortality lookup" | Code: contains "gspio docs" |
| **model-review** | Catches `map_elements` | model_with_antipatterns.py | Code: "map_elements" in critical_issues |
| **model-review** | Catches wrong ordering | model_with_antipatterns.py | Code: "decrement" in important_issues |
| **model-review** | Catches inline Polars | model_with_antipatterns.py | Code: "Table.lookup" in important_issues |
| **model-review** | Passes clean model | L4 base model.py | Code: critical_issues is empty |
| **model-reconciliation** | Demands evidence | "My model matches" (no data) | Code: contains "output-file" or "run-single-policy" |
| **model-scenarios** | Enforces two-script pattern | "Run scenarios" | Code: contains "run_scenarios.py" and NOT "modify model.py" |

**Test fixtures** (`tests/skills/fixtures/`):
- `model_with_antipatterns.py` — model with `map_elements`, wrong ordering, inline Polars, magic numbers
- `model_clean.py` — L4 base model (should pass review)
- `model_close_but_wrong.py` — model producing PVs close to but not matching reference

### Tier 3: On Skill Changes — A/B Comparison

When a SKILL.md changes, run the Tier 2 eval suite against BOTH the old and new skill content. Compare scores per test case. If any score drops, flag for human review before merging.

This catches skill regressions: "We updated the review skill's anti-pattern list, but accidentally broke the decrement ordering check."

### Skill Triggering Tests (deferred to Phase 4)

Testing whether Claude Code auto-invokes the right skill from natural language requires the plugin manifest (`.claude-plugin/plugin.json`). Deferred to Phase 4.

| User prompt | Expected skill |
|---|---|
| "I'm new to gaspatchio, help me get started" | quickstart |
| "I need to build a term life model" | model-discovery |
| "Help me add lapse rates to this model" | model-building |
| "Review the changes I made to model.py" | model-review |
| "My model doesn't match the Excel output" | model-reconciliation |
| "Run a sensitivity analysis on mortality" | model-scenarios |

### Cost and CI/CD Impact

| Tier | When | Deterministic? | API cost | Runtime |
|---|---|---|---|---|
| **Tier 1** | Every PR | Yes | $0 | Seconds |
| **Tier 2** | Nightly | Mostly (code grading) | $1-5/run | Minutes |
| **Tier 3** | On SKILL.md changes | Same as Tier 2 | $2-10/run | Minutes |
| **Triggering** | Phase 4 | No | $1-3/run | Minutes |

---

## Migration Plan

1. Create `skills/` directory at repo root
2. Copy and refresh discovery, building, reconciliation skills (apply pending observations)
3. Move reference files into `skills/<skill-name>/references/`
4. Create new quickstart skill from scratch
5. Create new model-review skill from scratch
6. Create new model-scenarios skill from scratch
7. Leave originals in `ref/30-llm-helpers/skills/` until Phase 4 plugin packaging is done
8. Mark all pending observations as APPLIED

---

## What Phase 4 adds (not in scope here)

- `.claude-plugin/plugin.json` manifest pointing at `skills/`
- `plugin.json` for Copilot
- `gspio setup-ai` command
- First-run nudge
- Marketplace submissions
- Session hooks (Superpowers pattern)

---

## Success Criteria

1. All 6 skills work as Claude Code skills (agent invokes them, follows the workflow)
2. Every skill works standalone — no mandatory prerequisites from other skills
3. Each skill enforces its own completion gate (hard gate within the skill)
4. Model-review catches both gaspatchio anti-patterns and actuarial methodology issues
5. Skills reference tutorial levels as worked examples throughout
6. `gspio describe --json` is used for data inspection in quickstart and discovery
7. `--output-file` is the standard agent workflow in building and reconciliation
8. Skill triggering tests pass (natural language → correct skill)
9. Subagent review tests pass (review catches known issues)
