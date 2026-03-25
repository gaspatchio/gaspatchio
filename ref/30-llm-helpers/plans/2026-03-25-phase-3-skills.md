# Phase 3: Gaspatchio Skills — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build 6 gaspatchio skills (quickstart, model-discovery, model-building, model-review, model-reconciliation, model-scenarios) with test fixtures and a Pydantic AI test harness.

**Architecture:** Migrate 3 existing skills from `ref/30-llm-helpers/skills/` to `skills/` at repo root, refresh with pending observations and tutorial references. Create 3 new skills (quickstart, model-review, model-scenarios). Build test fixtures and a Tier 1 deterministic test suite using Pydantic AI `TestModel`.

**Tech Stack:** Markdown (SKILL.md with YAML frontmatter), Python, Pydantic AI, Pydantic Evals, pytest

**Spec:** `ref/30-llm-helpers/specs/2026-03-25-phase-3-skills-design.md`

**Source skills:** `ref/30-llm-helpers/skills/gaspatchio-{discovery,building,reconciliation}.md`

---

## Task 1: Create skills/ directory and migrate existing skills

**Files:**
- Create: `skills/model-discovery/SKILL.md` (from `ref/30-llm-helpers/skills/gaspatchio-discovery.md`)
- Create: `skills/model-building/SKILL.md` (from `ref/30-llm-helpers/skills/gaspatchio-building.md`)
- Create: `skills/model-building/references/` (from `ref/30-llm-helpers/skills/gaspatchio-building-references/`)
- Create: `skills/model-reconciliation/SKILL.md` (from `ref/30-llm-helpers/skills/gaspatchio-reconciliation.md`)
- Create: `skills/model-reconciliation/references/` (from `ref/30-llm-helpers/skills/gaspatchio-reconciliation-references/`)

This is a pure file move — no content changes yet. Content refresh happens in Tasks 3-5.

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p skills/quickstart
mkdir -p skills/model-discovery
mkdir -p skills/model-building/references
mkdir -p skills/model-review/references
mkdir -p skills/model-reconciliation/references
mkdir -p skills/model-scenarios
```

- [ ] **Step 2: Copy and rename existing skills**

```bash
cp ref/30-llm-helpers/skills/gaspatchio-discovery.md skills/model-discovery/SKILL.md
cp ref/30-llm-helpers/skills/gaspatchio-building.md skills/model-building/SKILL.md
cp ref/30-llm-helpers/skills/gaspatchio-building-references/* skills/model-building/references/
cp ref/30-llm-helpers/skills/gaspatchio-reconciliation.md skills/model-reconciliation/SKILL.md
cp ref/30-llm-helpers/skills/gaspatchio-reconciliation-references/* skills/model-reconciliation/references/
```

- [ ] **Step 3: Update frontmatter names in copied skills**

In each SKILL.md, update the `name:` field:
- `gaspatchio-discovery` → `gaspatchio-model-discovery`
- `gaspatchio-building` → `gaspatchio-model-building`
- `gaspatchio-reconciliation` → `gaspatchio-model-reconciliation`

- [ ] **Step 4: Commit**

```
feat(skills): migrate existing skills to skills/ directory
```

---

## Task 2: Create quickstart skill (NEW)

**Files:**
- Create: `skills/quickstart/SKILL.md`

~100 lines. No reference files.

- [ ] **Step 1: Create SKILL.md**

Read the spec section "Skill 1: quickstart" for full requirements. The skill must:

Frontmatter:
```yaml
---
name: gaspatchio-quickstart
description: Use when user is new to gaspatchio, setting up for the first time, or wants to get started quickly with actuarial modeling
---
```

Body structure:
1. **Announce**: "I'm using the gaspatchio quickstart skill."
2. **Verify install**: `uv run gspio --version`
3. **Inspect data** (if provided): `uv run gspio describe --json data.parquet` — explain what the JSON tells you (model points vs assumption table, column types, dimensions)
4. **Route to tutorial level**:
   - Policy data, simple cashflows → L1 base
   - Need assumption tables → L2 base
   - Complete VA model → L3 base
   - Porting from lifelib → L4
   - Scenario analysis → L5
5. **Copy and run**: Copy the selected tutorial base, run it, explain output
6. **Swap user data**: If they have their own data, guide swapping it in
7. **Next steps**: model-discovery for new models, model-building for extending

Key rules:
- Do NOT write model code in this skill — guide the user to the right starting point
- The tutorial IS the quickstart — don't reinvent it
- Use `gspio describe --json` to understand data before recommending a level

- [ ] **Step 2: Verify by reading it**

Read the file back and check: is it under 150 lines? Does it have frontmatter? Does it reference `gspio describe --json`? Does it route to all 5 tutorial levels?

- [ ] **Step 3: Commit**

```
feat(skills): add quickstart skill
```

---

## Task 3: Refresh model-discovery skill

**Files:**
- Modify: `skills/model-discovery/SKILL.md`

Read `ref/30-llm-helpers/skills/gaspatchio-discovery.md` (the source) and the spec section "Skill 2: model-discovery" for what to add.

- [ ] **Step 1: Add gspio describe --json as mandatory first step**

Before any questions, the agent must inspect all provided data files:
```markdown
## Step 1: Inspect the data

Before asking questions, run `uv run gspio describe --json <file>` on every data file the user has provided. Read the JSON output to understand:
- Is this model points or an assumption table? (check `table_shape`)
- What columns exist? What are their types?
- What dimensions are detected?
- What does the suggested code look like?

This informs all subsequent questions.
```

- [ ] **Step 2: Add tutorial level routing**

Add a section after the discovery questions:
```markdown
## Tutorial shortcuts

Before designing from scratch, check if the model matches an existing tutorial level:
- Term life with scalar rates → Start from L1 Step 03
- Term life with assumption tables → Start from L2 base
- Variable annuity with guarantees → Start from L3 base
- Porting from lifelib → Start from L4
- Scenario analysis on an existing model → Start from L5

If a match exists, propose: "This is very similar to Level N. Want to start from that and modify?"
```

- [ ] **Step 3: Add anti-rationalization section**

```markdown
## Anti-rationalizations

The agent must NOT skip discovery even when pressured:
- "I already know what I want" → "Even experienced actuaries benefit from structured discovery. Let me confirm the data structure first."
- "Just start coding" → "Models built without a spec take longer to debug. The spec takes 10 minutes and saves hours."
- "We don't have time for this" → "Discovery IS the fastest path. Skipping it means debugging blind."
```

- [ ] **Step 4: Add hard gate**

Add near the top:
```markdown
## Hard gate

Do NOT write model code until the model spec is approved by the user.
Do NOT skip to model-building. The spec must exist before implementation begins.
```

- [ ] **Step 5: Add standalone invocation note**

```markdown
## When to use this skill

This skill can be used standalone — it does NOT require quickstart to have been run first.
Use it whenever you need to scope a new model, plan a model change, or understand what a model should do before writing code.
```

- [ ] **Step 6: Commit**

```
feat(skills): refresh model-discovery with describe --json, tutorial routing, hard gates
```

---

## Task 4: Refresh model-building skill

**Files:**
- Modify: `skills/model-building/SKILL.md`
- Modify: `skills/model-building/references/common-mistakes.md`
- Modify: `skills/model-building/references/model-phases.md`
- Modify: `skills/model-building/references/timing-and-dates.md`

Read `ref/30-llm-helpers/skills/gaspatchio-building.md` (the source) and the spec section "Skill 3: model-building" for what to add.

- [ ] **Step 1: Add post-build checklist**

Add a new section at the end of SKILL.md:
```markdown
## Post-build checklist

Before claiming the model is complete, verify ALL of these:
- [ ] No `map_elements` or `apply` calls anywhere in model code
- [ ] No Python for-loops over rows (no `for row in df.iter_rows()`)
- [ ] All sections have header comments (SECTION 1, SECTION 2, etc.)
- [ ] All `Table.lookup()` calls verified with `uv run gspio docs "Table.lookup"`
- [ ] Model runs with `--output-file` without errors
- [ ] Key outputs have expected signs (claims positive, net_cf can be negative)
- [ ] All assumption Tables created with correct dimensions
- [ ] No hardcoded magic numbers — all rates come from Table lookups or named constants

This checklist is the completion gate for this skill.
```

- [ ] **Step 2: Add data enrichment section**

Add to SKILL.md (observation #16):
```markdown
## Data enrichment patterns

When model points need parameters from assumption files, join them BEFORE creating the ActuarialFrame:

### Product parameter join
```python
mp = mp.join(product_params.select([...]), on=["product_id", "plan_id"], how="left")
```

### Space parameter cross-join
```python
gmxb = space_params.filter(pl.col("space") == "GMXB").select(["expense_acq", "expense_maint"])
mp = mp.with_columns([pl.lit(gmxb["expense_acq"].item()).alias("expense_acq")])
```

### Wide-to-long unpivot
```python
long = wide_df.unpivot(index="t", on=["FUND1", "FUND2"], variable_name="fund_index", value_name="return")
```

See Level 4 model.py lines 204-277 for the canonical example.
```

- [ ] **Step 3: Add product-specific formula section**

Add to SKILL.md (observation #13):
```markdown
## Product-specific formulas

Different products may use different formulas for the same calculation. Use parameter-driven selection, not hardcoded logic:

```python
# BAD: hardcoded formula
af.dyn_lapse_factor = (1.0 - af.M * (1.0 / af.itm - af.D)).clip(af.L, af.U)

# GOOD: parameter-driven selection
af.dl001_factor = (1.0 - af.M * (1.0 / af.itm - af.D)).clip(af.L, af.U)
af.dl002_factor = (af.Y * af.itm ** af.Power).clip(af.FactorFloor, af.FactorCap)
af.dyn_lapse_factor = when(af.formula_id == "DL001").then(af.dl001_factor).otherwise(af.dl002_factor)
```

See Level 3 Step 06 (Gap 3) and Level 4 for examples.
```

- [ ] **Step 4: Add Table.lookup() exact-match warning to common-mistakes.md**

Add entry to `references/common-mistakes.md` (observation #17):
```markdown
## N. Table.lookup() is exact-match

**Wrong**: Creating a Table with breakpoint ages [25, 30, 35, 40, ...] and expecting interpolation.
**Right**: Table.lookup() requires exact key matches. Generate full-range tables (every integer age) or use appropriate dimension types.

```python
# BAD: sparse table with gaps
mort_data = pl.DataFrame({"age": [25, 30, 35], "qx": [0.001, 0.002, 0.004]})
# lookup(age=27) will FAIL — no exact match for age 27

# GOOD: full integer-age table
mort_data = pl.DataFrame({"age": list(range(20, 100)), "qx": [gompertz(a) for a in range(20, 100)]})
```
```

- [ ] **Step 5: Add BEF_DECR to model-phases.md**

Add to `references/model-phases.md` (observation #18):
```markdown
## Decrement ordering: BEF_DECR pattern

For production models with multiple decrements and new business:

1. `pols_if_bef_mat` = survival × policy_count × (duration ≤ maturity) × (duration > 0)
2. `pols_maturity` = pols_if_bef_mat × (duration == maturity_month)
3. `pols_if_bef_nb` = pols_if_bef_mat - pols_maturity
4. `pols_new_biz` = policy_count × (duration == 0)
5. `pols_if_bef_decr` = pols_if_bef_nb + pols_new_biz
6. `pols_death` = pols_if_bef_decr × mort_rate_mth
7. `pols_lapse` = (pols_if_bef_decr - pols_death) × lapse_rate_mth

The `duration > 0` guard prevents double-counting NB policies. For IF-only business, the simple ordering gives identical results. See Level 4 model.py SECTION 8.
```

- [ ] **Step 6: Add discount factor conventions to timing-and-dates.md**

Add to `references/timing-and-dates.md` (observation #15):
```markdown
## Discount factor conventions

Two approaches exist:

**Cumulative product** (actuarially intuitive):
```python
af.per_period_disc = 1.0 / (1.0 + af.disc_rate_mth)
af.disc_factors = af.per_period_disc.cum_prod()
```

**Closed-form** (matches lifelib):
```python
af.disc_factors = (af.month.cast(pl.Float64) * -1.0 * (1.0 + af.disc_rate_mth).log()).exp()
```

These give different results when rates change between years. When reconciling, match the reference model's formula. See Level 3 Step 06 (Gap 4).
```

- [ ] **Step 7: Add standalone invocation note and tutorial references**

Add near the top of SKILL.md:
```markdown
## When to use this skill

This skill can be used standalone. You do NOT need to have run model-discovery first.
Use it whenever you are writing or modifying gaspatchio model code.

## Tutorial reference

Every concept in this skill has a worked example in the tutorial:
- Column arithmetic, when/then → L1
- Table.lookup(), dimensions → L2
- Full VA model with all sections → L3 base
- Data enrichment, BEF_DECR, accumulate → L4
- Scenarios → L5
```

- [ ] **Step 8: Commit**

```
feat(skills): refresh model-building with 5 new sections and tutorial references
```

---

## Task 5: Refresh model-reconciliation skill

**Files:**
- Modify: `skills/model-reconciliation/SKILL.md`

Read the spec section "Skill 5: model-reconciliation" for what to add.

- [ ] **Step 1: Add learning reconciliation section**

Add (observation #12):
```markdown
## Learning reconciliation

If you're new to reconciliation, start with the 4-gap exercise in `tutorial/level-3-mini-va/steps/06-reconcile/`:
- Run `model_with_gaps.py` → see 0/8 points pass (2.5%-51.7% differences)
- Fix each gap one at a time → see improvement
- Run `model.py` (reference answer) → see 8/8 pass at 0.0000%

This teaches reconciliation through experience, not theory.
```

- [ ] **Step 2: Add matching intermediates section**

Add (observation #14):
```markdown
## Matching intermediates, not just aggregates

Passing PVs is necessary but not sufficient. A model can give the right PVs for the wrong reasons.

Always compare intermediate variables (mort_rate, pols_if, av_pp, claims_death) per timestep, not just aggregate PVs. Use `gspio run-single-policy --output-file` to capture all variables, then compare per-timestep.

The Level 4 full reconciliation (`reconcile_full.py`) compares 25 intermediate variables per point per timestep — this is the gold standard.
```

- [ ] **Step 3: Add gspio describe --json for output inspection**

Add to the diagnostic workflow:
```markdown
After running the model with `--output-file`, inspect the output:
```bash
uv run gspio describe --json /tmp/result.parquet
```
This shows you the schema, column types, and sample rows of the model output before you start comparing.
```

- [ ] **Step 4: Add standalone invocation note and strengthen L4 reference**

- [ ] **Step 5: Commit**

```
feat(skills): refresh model-reconciliation with intermediates guidance and Step 06 reference
```

---

## Task 6: Create model-review skill (NEW)

**Files:**
- Create: `skills/model-review/SKILL.md`
- Create: `skills/model-review/references/gaspatchio-antipatterns.md`
- Create: `skills/model-review/references/asop56-checklist.md`

The most complex new skill. Read the spec section "Skill 4: model-review" for full requirements.

- [ ] **Step 1: Create SKILL.md**

Frontmatter:
```yaml
---
name: gaspatchio-model-review
description: Use when reviewing changes to a gaspatchio model, validating model quality, or preparing a model for production use. Covers both gaspatchio code quality and actuarial professional standards (ASOP 56).
---
```

Structure:
1. **Announce + when to use** (standalone — the most commonly used skill independently)
2. **Hard gate**: All Critical and Important issues must be addressed
3. **How to review**: Read the git diff, inspect each change, run the model
4. **Layer 1: Gaspatchio code quality** — reference gaspatchio-antipatterns.md (10 anti-patterns with severity)
5. **Layer 2: Actuarial methodology** — reference asop56-checklist.md (correctness, assumptions, change impact, documentation)
6. **Issue classification**: Critical / Important / Minor with definitions
7. **Distrust-based review**: DO NOT trust "results look reasonable", "close enough", "we already checked"
8. **Review output format**: Markdown template with sections per severity
9. **Standalone note**: Can be invoked on ANY model change, not just after building

- [ ] **Step 2: Create gaspatchio-antipatterns.md**

Reference file listing the 10 anti-patterns from the spec with wrong/right code examples:
1. `map_elements` / `apply` (Critical)
2. Python for-loops over data (Critical)
3. Scalar/list confusion (Critical)
4. Inline Polars instead of Table.lookup (Important)
5. Guessed API signatures (Important)
6. Missing `--output-file` validation (Important)
7. Wrong projection accessor (Important)
8. Hardcoded assumptions (Important)
9. Missing `when/then/otherwise` (Minor)
10. No section comments (Minor)

Each with a "Wrong" code block, a "Right" code block, and a "Why it matters" explanation.

- [ ] **Step 3: Create asop56-checklist.md**

Reference file with the ASOP 56-informed checklist from the spec:
- Correctness checks (5 items)
- Assumption integrity checks (4 items)
- Change impact checks (4 items)
- Documentation checks (3 items)

Each with a brief explanation of what to look for and why.

- [ ] **Step 4: Commit**

```
feat(skills): add model-review skill with gaspatchio antipatterns and ASOP 56 checklist
```

---

## Task 7: Create model-scenarios skill (NEW)

**Files:**
- Create: `skills/model-scenarios/SKILL.md`

Read the spec section "Skill 6: model-scenarios" for full requirements.

- [ ] **Step 1: Create SKILL.md**

Frontmatter:
```yaml
---
name: gaspatchio-model-scenarios
description: Use when running scenario analysis, applying parameter shocks, performing sensitivity sweeps, or producing scenario comparison reports on a gaspatchio model.
---
```

Structure:
1. **Announce + when to use** (standalone — works on any validated model)
2. **Hard gate**: Must produce report with charts and audit trail
3. **Two-script pattern**: model.py unchanged, run_scenarios.py for orchestration
4. **Scenario types** (progressive, 5 levels from the spec):
   - Interest rate scenarios (`with_scenarios`)
   - Parameter shocks (JSON config, `Table.with_shock`)
   - Conditional shocks (`where`, `when`, `pipeline`)
   - Sensitivity sweeps (`sensitivity_analysis`)
   - Regulatory comparison (`describe_scenarios` for audit trail)
5. **JSON shock schema** — exact format with examples
6. **Report requirements** — metadata, config, results table, charts, audit trail
7. **CLI commands** — both `gspio run-model` (standalone) and `python run_scenarios.py` (scenarios)
8. **Tutorial reference** — L5 base and Steps 01-04 as worked examples
9. **Anti-rationalizations** — "modify the model", "don't need a report", "tornado chart is enough"

Key: include the actual JSON shock schema examples from the spec so the agent can write valid configs.

- [ ] **Step 2: Commit**

```
feat(skills): add model-scenarios skill
```

---

## Task 8: Create test fixtures

**Files:**
- Create: `tests/skills/fixtures/model_with_antipatterns.py`
- Create: `tests/skills/fixtures/model_clean.py`
- Create: `tests/skills/__init__.py`
- Create: `tests/skills/fixtures/__init__.py`

- [ ] **Step 1: Create model_with_antipatterns.py**

A deliberately broken model (~100 lines) that contains ALL the anti-patterns the model-review skill should catch:

1. `map_elements` call (line ~30)
2. Python for-loop over rows (line ~40)
3. Scalar/list confusion (line ~50)
4. Inline `df.filter(pl.col(...))` instead of Table.lookup (line ~60)
5. Hardcoded magic number for mortality rate (line ~70)
6. Missing section comments
7. Wrong decrement ordering (simple, not BEF_DECR)

The model should be structurally valid Python (imports work, functions defined) but obviously wrong to a reviewer. Include comments like `# ANTI-PATTERN: map_elements` so we can grep for them in tests.

Base it loosely on the L1 tutorial structure so it's recognisable as a gaspatchio model.

- [ ] **Step 2: Create model_clean.py**

Copy `tutorial/level-4-lifelib/base/model.py` — this is the gold standard that should pass review with no Critical or Important issues.

Actually, just symlink or reference it in tests:
```python
MODEL_CLEAN_PATH = Path("tutorial/level-4-lifelib/base/model.py")
```

- [ ] **Step 3: Create __init__.py files**

Empty `__init__.py` in `tests/skills/` and `tests/skills/fixtures/`.

- [ ] **Step 4: Commit**

```
feat(skills): add test fixtures for skill testing
```

---

## Task 9: Create Tier 1 test suite (Pydantic AI TestModel)

**Files:**
- Create: `tests/skills/test_skill_structure.py`
- Create: `tests/skills/test_review_fixtures.py`

- [ ] **Step 1: Create test_skill_structure.py**

Verify all 6 skills have valid structure:

```python
"""Tier 1: Verify skill files exist and have valid frontmatter."""
import pytest
import yaml
from pathlib import Path

SKILLS_DIR = Path("skills")
EXPECTED_SKILLS = [
    "quickstart",
    "model-discovery",
    "model-building",
    "model-review",
    "model-reconciliation",
    "model-scenarios",
]

@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_exists(skill_name):
    skill_path = SKILLS_DIR / skill_name / "SKILL.md"
    assert skill_path.exists(), f"Missing: {skill_path}"

@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_has_frontmatter(skill_name):
    content = (SKILLS_DIR / skill_name / "SKILL.md").read_text()
    assert content.startswith("---"), f"{skill_name} missing YAML frontmatter"
    # Extract frontmatter
    parts = content.split("---", 2)
    assert len(parts) >= 3, f"{skill_name} frontmatter not properly closed"
    fm = yaml.safe_load(parts[1])
    assert "name" in fm, f"{skill_name} missing 'name' in frontmatter"
    assert "description" in fm, f"{skill_name} missing 'description' in frontmatter"
    assert fm["description"].startswith("Use when"), f"{skill_name} description should start with 'Use when'"

@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_has_standalone_note(skill_name):
    """Every skill must document that it can be used independently."""
    content = (SKILLS_DIR / skill_name / "SKILL.md").read_text()
    assert "standalone" in content.lower() or "independent" in content.lower(), \
        f"{skill_name} must mention standalone/independent invocation"

def test_model_building_has_references():
    refs = list((SKILLS_DIR / "model-building" / "references").iterdir())
    assert len(refs) >= 6, f"Expected 6+ reference files, got {len(refs)}"

def test_model_reconciliation_has_techniques():
    refs = list((SKILLS_DIR / "model-reconciliation" / "references").iterdir())
    assert len(refs) >= 8, f"Expected 8+ technique files, got {len(refs)}"

def test_model_review_has_references():
    refs = list((SKILLS_DIR / "model-review" / "references").iterdir())
    assert len(refs) >= 2, f"Expected gaspatchio-antipatterns.md and asop56-checklist.md"
```

- [ ] **Step 2: Create test_review_fixtures.py**

Verify the test fixtures contain the expected anti-patterns:

```python
"""Tier 1: Verify test fixtures contain expected anti-patterns."""
from pathlib import Path

FIXTURES_DIR = Path("tests/skills/fixtures")

def test_antipattern_fixture_has_map_elements():
    content = (FIXTURES_DIR / "model_with_antipatterns.py").read_text()
    assert "map_elements" in content

def test_antipattern_fixture_has_for_loop():
    content = (FIXTURES_DIR / "model_with_antipatterns.py").read_text()
    assert "for row in" in content or "iter_rows" in content

def test_antipattern_fixture_has_inline_polars():
    content = (FIXTURES_DIR / "model_with_antipatterns.py").read_text()
    assert "df.filter" in content or "pl.col" in content

def test_antipattern_fixture_has_magic_numbers():
    content = (FIXTURES_DIR / "model_with_antipatterns.py").read_text()
    assert "0.015" in content or "ANTI-PATTERN: hardcoded" in content

def test_clean_model_exists():
    """L4 base model should exist as the clean reference."""
    assert Path("tutorial/level-4-lifelib/base/model.py").exists()
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/skills/ -v
```

Expected: All tests pass (once skills are created in Tasks 1-8).

- [ ] **Step 4: Commit**

```
feat(skills): add Tier 1 deterministic test suite for skills
```

---

## Task 10: Update skill-development-notes.md

**Files:**
- Modify: `ref/30-llm-helpers/skill-development-notes.md`

- [ ] **Step 1: Mark all pending observations as APPLIED**

Update observations #7, #12-19 from PENDING to APPLIED with references to where they were applied:

- #7 (model-review skill) → APPLIED — skills/model-review/SKILL.md
- #12 (deliberate-gap reconciliation) → APPLIED — skills/model-reconciliation/SKILL.md
- #13 (product-specific formulas) → APPLIED — skills/model-building/SKILL.md
- #14 (accumulate vs cum_prod) → APPLIED — skills/model-reconciliation/SKILL.md
- #15 (discount factor conventions) → APPLIED — skills/model-building/references/timing-and-dates.md
- #16 (data pipeline patterns) → APPLIED — skills/model-building/SKILL.md
- #17 (Table.lookup exact-match) → APPLIED — skills/model-building/references/common-mistakes.md
- #18 (BEF_DECR ordering) → APPLIED — skills/model-building/references/model-phases.md
- #19 (tutorial as skill reference) → APPLIED — all 6 skills reference tutorial levels

- [ ] **Step 2: Commit**

```
docs(skills): mark all pending observations as APPLIED
```

---

## Task 11: Update top-level tutorial README

**Files:**
- Modify: `tutorial/README.md`

- [ ] **Step 1: Add skills reference section**

Add a section after "On-ramps":
```markdown
## AI-assisted model building

gaspatchio includes skills for AI coding assistants (Claude Code, Copilot, Cursor):

| Skill | What it does |
|---|---|
| quickstart | Get from zero to running model in 10 minutes |
| model-discovery | Socratic method to understand what to build |
| model-building | Write model code with gaspatchio best practices |
| model-review | Review model changes (code quality + actuarial methodology) |
| model-reconciliation | Match a model against a reference implementation |
| model-scenarios | Run scenarios, shocks, sensitivity analysis with reports |

Skills are in the `skills/` directory. See `gspio setup-ai` for installation.
```

- [ ] **Step 2: Commit**

```
docs(tutorial): add skills reference section to tutorial README
```

---

## Parallelization Notes

- **Task 1** (migration) must be first
- **Tasks 2-7** (individual skills) can all run in parallel after Task 1
- **Task 8** (test fixtures) can run in parallel with Tasks 2-7
- **Task 9** (test suite) depends on Tasks 1-8 being complete
- **Tasks 10-11** (docs updates) depend on Tasks 2-7

**Recommended sequence**: Task 1 → [Tasks 2-8 in parallel] → Task 9 → [Tasks 10-11]
