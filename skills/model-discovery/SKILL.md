---
name: gaspatchio-model-discovery
description: Use when starting a new gaspatchio model, porting from Excel or another system, or restructuring an existing model – forces a one-question-at-a-time discovery workflow for specification, data, assumptions, projection parameters, and outputs before any code is written.
allowed-tools: Bash(uv:*,gspio:*) Read Grep Glob
---

# Gaspatchio Model Discovery

## When to use this skill

This skill can be used standalone — it does NOT require quickstart to have been run first. Use it whenever you need to scope a new model, plan a model change, or understand what a model should do before writing code.

## Hard gate

Do NOT write model code until the model spec is approved by the user. Do NOT skip to model-building. The spec must exist before implementation begins.

## Overview

**Understand before you build.** This skill drives a strict discovery workflow so you fully specify the model before touching `model_*.py`.

The **ultimate output** of this skill is a single **Gaspatchio Model Specification document** that you can hand directly to `gaspatchio-building`

You use it to pin down, in that spec document:
- Source specification (Excel, lifelib, other systems, docs)
- Model points / data shape
- Assumption tables
- Projection settings
- Output and reconciliation requirements

## When to Use

Use this skill **before any gaspatchio code** when:

- The user says "build a model", "create a model", or "help me with a gaspatchio model".
- **You are porting from Excel, lifelib, or another system.** This is a critical trigger — do NOT skip discovery for Excel ports. The Excel model structure, formula dependencies, and assumption tables must be mapped and specified before any gaspatchio code is written.
- The user says "create an implementation plan" or "plan the conversion."
- Model inputs, assumptions, or outputs are not yet fully specified.
- You are tempted to "just start coding" to see what happens.

**Do not write model code until discovery is complete. No exceptions.**

## Discovery Workflow

Copy this checklist and keep it visible:

```text
Gaspatchio Discovery
- [ ] 1. Check existing project context
- [ ] 2. Research actuarial concepts from spec
- [ ] 3. Identify source specification
- [ ] 4. Lock down data/model points
- [ ] 5. Enumerate assumptions
- [ ] 6. Define projection parameters
- [ ] 7. Define outputs and aggregations
- [ ] 8. Confirm scope and approach before coding
```

### 0. Inspect the data

Before asking questions, run `uv run gspio describe --json <file>` on every data file the user has provided. Read the JSON output to understand:
- Is this model points or an assumption table? (check `table_shape` field)
- What columns exist? What are their types? (check `column_types`)
- What dimensions are detected? (check `detected_dimensions`)
- What does the suggested code look like? (check `suggested_code`)

This informs all subsequent questions. Don't ask the user about data structure — you already know it from describe.

### 1. Check project context first

Before asking **any** questions:

- Look for:
  - Existing gaspatchio models (`model_*.py`, `appliedlife/`, etc.)
  - Spec docs and README/`project.md`
  - Excel / lifelib / other system models referenced in the repo
- Answer for yourself:
  - What already exists?
  - What is clearly missing?
  - Are we building new, refactoring, or porting?
  - Does the model need custom calculations that don't exist in Gaspatchio yet? If so, note them — they will need the `gaspatchio-extending` skill before or during model building.

You MUST also obtain **at least one concrete piece of source-model documentation** before proceeding:

- Acceptable forms:
  - A URL to official docs (e.g. `[lifelib appliedlife IntegratedLife docs](https://lifelib.io/libraries/appliedlife/IntegratedLife.html)`)
  - A path to a spec document in the repo (`docs/model_spec.md`, internal wiki page, etc.)
  - A named Excel / lifelib model that functions as the spec (plus how to open it)
- If the user cannot provide any existing documentation, require them to confirm this explicitly and capture their verbal description as a short written spec in this conversation before you proceed.

Do **not** treat "we'll figure it out as we go" as acceptable. You either have:

- A concrete doc/URL/file you can reference, **or**
- An agreed minimal written spec you just created together.

Only then start discovery with the user.

### 2. Research actuarial concepts with the knowledge base

When the specification mentions actuarial concepts, regulatory frameworks, or domain terms you need to understand:

**Use `uv run gspio knowledge` to look up:**
- Regulatory requirements (IFRS 17, Solvency II, US GAAP)
- Calculation methodologies (CSM, risk adjustment, technical provisions)
- Assumption types (mortality, lapse, discount rates)
- Jurisdiction-specific requirements

**When to search:**
- Spec mentions a regulatory framework → search for requirements
- Spec references a calculation you're unsure about → search for methodology
- User mentions jurisdiction (EU, US, UK) → search with jurisdiction filter
- Assumption table mentioned → search for standard approaches

**Quick reference:**
```bash
# Regulatory requirements
uv run gspio knowledge "CSM calculation" -T IFRS17 -d standard

# Implementation guidance
uv run gspio knowledge "risk adjustment" -T IFRS17 -d guidance

# Jurisdiction-specific
uv run gspio knowledge "technical provisions" -j EU -T SolvencyII

# Mortality/assumptions
uv run gspio knowledge "mortality improvement" -T mortality
```

For full command reference, see: `docs/cli-knowledge-command.md` in gaspatchio-core.

**Do NOT:**
- Ask the user to explain standard actuarial concepts you can look up
- Proceed with vague understanding of regulatory requirements
- Guess at calculation methodologies

### 3. One-question-at-a-time protocol

You MUST:

- Ask **exactly one** question per message.
- Prefer multiple choice when possible.
- Wait for the answer before proceeding.
- Use follow-ups to refine, not to branch off.

This prevents shotgun-question dumps that users ignore.

### 4. Key areas to explore

Work through these five areas explicitly:

| Area | What you MUST understand |
|------|--------------------------|
| **Specification** | Is there an Excel, lifelib, other system, or written spec? Which file, which sheet/model, which tab holds "truth"? What are the core formulas? |
| **Data (model points)** | Where are model points stored (Parquet/CSV)? Policy ID column name? Which columns define policy, coverage, riders, and dates? |
| **Assumptions** | Which assumption tables exist? Where are they located? What are their dimensions (age, duration, calendar year, policy year, scenario)? How are they keyed? |
| **Projection** | Projection frequency (monthly, annual, other)? Projection length driver (term, attained age, maturity date, contract boundary)? Valuation date and alignment rules? |
| **Within-period mechanics** | **Do any within-period charges or credits depend on the running balance?** (COI on net amount at risk, IUL floor/cap on the in-period index credit, AV-banded fees, GMDB ratchet to the post-growth AV, multi-state with cross-account reads.) This is the load-bearing question for linear-recurrence vs state-machine classification — answer it explicitly before handing off to model-building. |
| **Outputs** | Required cashflows, reserves, PV metrics, roll-forwards, and aggregations (per-policy, portfolio, cohort)? Any regulatory or accounting views that must match existing reports? |
| **Scenarios** | Will the model run under stress scenarios, sensitivity sweeps, or stochastic Monte Carlo? If yes, the model entry point should accept `assumptions_override` so a `ScenarioRun.run()` wrapper can hand shocked tables back in. Hand off to `gaspatchio-model-scenarios` after building. |

### 5. Explore alternative model structures

If there are multiple ways to structure the model:

- Propose **2–3 concrete options** with trade-offs:
  - **Single large model vs multiple modular models**
  - **Policy-centric vs coverage-centric frame**
  - **Projection-first vs valuation-view-first**
- Lead with your recommendation and briefly justify it.
- Let the user choose **before** you commit.

Example prompt:

```text
I see two viable structures:
A) Single model with per-coverage projection and all cashflows
B) Core projection + separate valuation/post-processing model

Pick A or B (or tell me what's wrong with both).
```

### 6. Confirm before building

Summarize in your own words:

- Source of truth:
  - Spec location (Excel/lifelib/other/docs)
  - "How to run" the source, if it exists
- Data:
  - Model points file(s), key columns, and row granularity
- Assumptions:
  - Table list, their dimensions, and file paths
- Projection:
  - Frequency, horizon driver, valuation date, any special timing rules
- Outputs:
  - Variables to produce, views to aggregate, and reconciliation targets

Then explicitly ask:

```text
Here's what I'll build in gaspatchio: [short structured summary].
Does this look right before I start coding? Anything missing or wrong?
```

**Do not write model code until the user confirms this summary.**

## Tutorial shortcuts

Before designing from scratch, check if the model matches an existing tutorial level:
- Term life with scalar rates → Start from Level 1 Step 03
- Term life with assumption tables → Start from Level 2 base
- Variable annuity with guarantees → Start from Level 3 base
- Porting from lifelib → Start from Level 4
- Scenario analysis on an existing model → Start from Level 5

If a match exists, propose: "This is very similar to Level N. Want to start from that and modify?"

## When Discovery is Complete

Consider discovery complete when:

- You can describe the model in 3–5 bullet points covering:
  - Spec source
  - Data shape
  - Assumptions
  - Projection rules
  - Outputs / reconciliation targets
- You know **exactly** which variables you will calculate in the first MVP.
- You could hand your notes to another engineer and they could build the same model.

At that point, switch to `gaspatchio-building` for actual implementation.

**Tutorial shortcut**: If the model is similar to a standard VA projection, start from the closest tutorial level rather than building from scratch:
- `tutorial/level-3-mini-va/base/` — inline data, 11-section model, good for learning
- `tutorial/level-3-mini-va/steps/05-rate-curves/` — full feature set with rate curves
- `tutorial/level-4-lifelib/base/` — 860-line production model, reconciled to 0.0000% against lifelib

## If Reconciling Against Existing Model

If the user mentions:

- "Reconcile", "match Excel", "match lifelib", "replicate", "compare to existing model"

then:

- Finish high-level discovery here, but
- Immediately hand off to `gaspatchio-reconciliation` for the strict reconciliation workflow.

Treat reconciliation as a separate, **hard-mode** process layered on top of discovery.

## Red Flags — You Are Skipping Discovery

| Thought | Reality |
|---------|---------|
| "I already know what I want" | Even experienced actuaries benefit from structured discovery. Confirm the data structure first. |
| "Just start coding" | Models built without a spec take longer to debug. The spec takes 10 minutes and saves hours. |
| "We don't have time for this" | Discovery IS the fastest path. Skipping it means debugging blind. |
| "I have the Excel model, I can see what it does" | Excel models have hidden dependencies, stale caches, and undocumented formulas. Map them first. |
| "The user already described the model" | A description is not a spec. Pin down data shape, assumptions, projection parameters, and outputs. |

---

## Integration

**Called after:**
- `gaspatchio-quickstart` — for new users getting oriented

**REQUIRED next step:**
- `gaspatchio-model-building` — **only after** the spec is approved by the user. The hard gate is absolute.

**REQUIRED when applicable:**
- `gaspatchio-model-reconciliation` — when a reference model exists. Hand off immediately after high-level discovery.

**Called by:**
- `gaspatchio-quickstart` routes here for new models
- `gaspatchio-model-building` routes here if no spec exists
