# L3 — Skill effectiveness evals (wholesale refactor)

**Status:** Draft for review
**Date:** 2026-06-24
**Topic:** `ref/43-skill-lifecycle/` (L3 of the skill-lifecycle program)
**Author:** Matt Wright

Refactor the existing `evals/` harness so it measures whether a skill actually
makes an agent **produce correct artifacts** — by *executing* what the agent
emits and comparing **with-skill vs without-skill** — instead of trusting the
agent's self-assessment. Breaking changes are expected and acceptable; the
current grading core is replaced, not extended.

This is L3 of the skill-lifecycle program (umbrella design:
`ref/43-skill-lifecycle/specs/2026-06-15-skill-lifecycle-design.md`; L0/L1 shipped
in core PR #136; L2 detector shipped in `gaspatchio-docs`). It supersedes that
umbrella's "L3 lives in private docs" note — the eval harness already exists and
runs in **core** CI with API keys, so L3 stays in core.

---

## 1. Problem

`evals/` runs 7 skills × 4 models and renders a capability matrix to
`skills.html` on gh-pages. Three flaws make the numbers untrustworthy:

1. **The agent grades itself.** Every `result_types.py` model is the agent
   *self-reporting* booleans about its own behaviour — `DiscoveryResult.code_written`,
   `ExtendingResult.uses_antipattern`, `BuildingResult.gspio_docs_consulted`,
   `ScenarioResult.model_py_modified`. The grader (`evaluators.py`) then scores
   those self-reports. A model good at *saying* the right thing scores well
   regardless of whether it could build a working model.
2. **The agents have no tools.** They are pure-prompt `pydantic_ai.Agent`s with an
   `output_type`. They *cannot* run `gspio docs`, write a file, or execute code —
   so `gspio_docs_consulted: True` is fiction. Nothing the agent claims is verified
   against reality.
3. **No lift, and unpopulated.** The harness only runs *with* the skill, so it
   reports an absolute pass rate, never **does the skill help** (with vs without).
   And the live dashboard shows "No capability data yet" — we have **zero** real
   numbers for any skill. (Minor: `compute_pass_rate`'s docstring says "≥0.7" but
   the code uses `0.5`.)

The research grounding (`ref/43-skill-lifecycle/research/2026-06-15-stream2-...`)
is unambiguous: for code-producing skills, **execution-based grading** must
dominate and **per-model paired lift** is the headline effectiveness metric;
LLM-judge/self-report "can't tell if code works."

## 2. Goals / Non-goals

**Goals**
- Replace self-report grading with **objective oracles**: execute what the agent
  emits; for non-code skills, grade against ground truth. LLM-judge only for
  subjective style.
- Measure **per-model paired lift** (with-skill − without-skill) as the headline,
  never pooled across models.
- Populate the dashboard with real numbers for all **7 skills**.
- Keep the harness in core, reuse the dataset format, dashboard, and CI wiring
  where they still fit.

**Non-goals (v1)**
- Full agentic execution (tools, multi-step recovery). v1 is **one-shot
  emit → oracle executes**; a clean seam allows adding the agentic tier later
  for selected skills.
- A CI pass/fail gate. v1 is informational (dashboard + lift); a lift-regression
  gate is a later add.
- Heavy statistical machinery (clustered SEM, large trial counts). v1 reports
  per-model lift with a low, configurable trial count; rigor is a documented seam.

## 3. What exists today (precise)

| File | Role | Fate |
|---|---|---|
| `evals/run_evals.py` | 7×4 loop, `compute_pass_rate`, writes `capability-matrix.json` + `benchmark-results.json` | **rewrite** the loop (add baseline arm + lift); keep the JSON outputs/shape the dashboard reads |
| `evals/agents.py` | `make_agent(skill, model)`; loads `SKILL.md`+refs as system prompt; pure-prompt + `output_type` | **rewrite**: emit free-form artifacts (code/text), no `output_type` self-report; with/without-skill variants |
| `evals/result_types.py` | per-skill self-report Pydantic models | **delete** (self-report is the bug) |
| `evals/evaluators.py` | self-report graders + some `LLMJudge` | **replace** with oracle-based graders |
| `evals/datasets/*.yaml` | per-skill test cases (`inputs` + evaluators) | **rewrite** cases to carry task + fixture + expected ground truth; keep the pydantic-evals `Dataset` format where it fits |
| `evals/serve_dashboard.py`, `skills.html` | renders the capability matrix | **keep**; extend to show lift |
| `.github/workflows/evals.yml` (`skill-evals`, `Update Capability Matrix`) | runs evals, renders to gh-pages | **keep**; the run now produces lift; still informational |

## 4. Architecture — Executor → Oracle → Comparator → Dashboard

```
For each (skill, task, model):
  EXECUTOR   run the task twice: arm A = system prompt WITH skill content,
             arm B = WITHOUT (baseline). One-shot completion each. Identical
             task + fixture. (Tiered seam: an arm could later be a tool-using
             agentic loop instead of one-shot.)
  ORACLE     grade each arm's artifact objectively (skill-type-specific, below)
             → score in [0,1]. No self-report.
  COMPARATOR lift = score(A) − score(B), per model. Headline.
  DASHBOARD  capability matrix (absolute A scores) + lift per skill×model.
```

### 4.1 Executor
- `make_agent(skill, model, *, with_skill: bool)` — system prompt = task framing
  (+ skill content iff `with_skill`). Returns the raw completion text (the
  artifact), not a structured self-report.
- **Paired in the same run** (research: don't run all with-skill then baselines
  later). Both arms see the identical task and fixture.
- **Tiered seam:** the executor is an interface (`run(task) -> artifact`). v1
  implements `OneShotExecutor`; a future `AgenticExecutor` (tools + steps) drops
  in without touching oracles or the comparator.

### 4.2 Oracle (the grading core) — three types
Each skill maps to the most objective oracle its output admits:

| Skill | Artifact | Oracle type | Concretely |
|---|---|---|---|
| **building** | model code | **execute** | extract code → run via `gspio run-model` against a fixture → 1.0 if it runs and emits the expected columns; partial for runs-but-missing-columns; 0.0 if it raises |
| **reconciliation** | model code | **execute + numeric** | run → compare output to a stored reference within tolerance (the 0.0000% discipline); score by how close |
| **scenarios** | run_scenarios.py | **execute** | run against a base model + fixture → scenarios produce expected output keys; model.py unchanged is checked by *diffing files*, not a self-report bool |
| **extending** | accessor code | **execute** | load the accessor, apply it to a scalar and a list column → 1.0 if both work; detect anti-patterns by **static scan of the emitted code** (regex for `map_elements`/`apply`/`iter_rows`/`for`-over-rows), not a self-report bool |
| **review** | findings text | **ground truth (seeded defect)** | feed model code with **planted** anti-patterns; score = fraction of planted defects the findings name (recall), penalise fabricated criticals (precision) |
| **discovery** | questions/spec text | **ground truth** | objective checks on the text: contains **no code block** (code-detector), asks ≥1 question, names the right tutorial level |
| **quickstart** | routing text | **ground truth** | the recommended tutorial level matches the expected one |

Oracles live in `evals/oracles/` — one module per type (`execute.py`,
`numeric.py`, `ground_truth.py`), each a pure function
`grade(artifact, case) -> float` so they're unit-testable without an LLM. The
execute/numeric oracles run emitted code in an **isolated subprocess + tmp cwd**
with the fixture copied in (mirrors the L2 harness's isolation), never in-process.

### 4.3 Comparator
`lift(skill, model) = mean(score_A) − mean(score_B)` over the skill's cases.
Reported **per model**. A skill that only helps the weakest model is a different
(and important) finding from uniform lift — pooling is forbidden.

### 4.4 Dashboard
`skills.html` keeps the capability matrix (absolute with-skill scores) and gains a
**lift view** (skill × model, signed). `run_evals.py` writes
`capability-matrix.json` (unchanged shape: with-skill scores) plus a new
`lift-matrix.json`; `serve_dashboard.py` renders both.

## 5. Fixtures & tasks
Execution grading needs (a) a task the agent answers and (b) a fixture + expected
ground truth the oracle checks against. Per skill, a `evals/fixtures/<skill>/`
holds the small synthetic parquet(s) the emitted code reads (model points,
assumptions) — built deterministically by a `_build.py` (the L2 `docs_fixtures`
pattern). Each dataset case carries: the prompt, the fixture name, and the
expected ground truth (expected columns / reference output / planted-defect list /
expected level). Fixtures are tiny; numbers realistic, schemas exact.

## 6. Design decisions

- **D1 — Objective oracles replace self-report; execution dominates for
  code-producing skills; LLM-judge only for subjective style.** *Why:* the
  research + the self-report flaw. Self-report `result_types.py` is deleted.
- **D2 — Per-model paired lift is the headline; with/without-skill run paired,
  never pooled across models.** *Why:* lift proves the skill *helps*; pooling
  hides capability-conditional effects.
- **D3 — Tiered executor: one-shot emit→execute in v1, agentic loop behind a
  stable interface for later.** *Why:* one-shot is cheap, deterministic-enough,
  and kills self-report; agentic realism can be added per-skill without reworking
  oracles.
- **D4 — Oracles are pure `grade(artifact, case) -> float` functions in
  `evals/oracles/`, unit-tested without an LLM; emitted code runs in an isolated
  subprocess.** *Why:* the grading core must itself be testable and safe.
- **D5 — Stays in core `evals/`; reuse dataset format, dashboard, CI wiring.**
  *Why:* it already runs there with keys; supersedes the umbrella "L3 in docs."
- **D6 — v1 informational (dashboard + lift), no CI gate.** *Why:* establish real
  baselines first; gating on lift-regression is a later add.
- **D7 — All 7 skills in v1.** *Why:* user decision; the three oracle types cover
  all seven, so no skill is left on the old self-report path.
- **D8 — Low, configurable trial count; report per-model lift; SEM/pass^k a
  documented seam.** *Why:* cost + "simple/robust over complex"; rigor when needed.

## 7. Cost & running
One-shot (not agentic) keeps cost modest: 7 skills × 4 models × 2 arms ×
`--trials N` completions, plus deterministic oracle execution. Trial count,
model list, and skill list are all CLI flags (`--model`, `--skill`, `--trials`)
so a cheap smoke run (1 model, 1 skill, 1 trial) is possible. Runs in core CI
with the existing API-key secrets; locally it's API-bound (no model build), so it
does not stress the machine. API keys provided at test time.

## 8. Testing the harness itself
- Oracles: unit-tested with fixture artifacts — a known-good emitted model scores
  1.0; a broken one (raises) scores 0.0; a model missing a column scores partial;
  the seeded-defect oracle scores a findings-text that catches N/M planted bugs.
- Executor: tested with a stub model (no real API) that returns a canned artifact,
  proving the with/without wiring + pairing.
- Comparator: pure function, unit-tested (lift = A − B per model).
- A `--dry-run`/stub-model path lets CI exercise the plumbing without spending.

## 9. Risks & mitigations
- **Emitted code reads un-fixtured data / needs setup → false 0.0.** *Mitigation:*
  tasks are scoped to the provided fixture; the prompt states the exact file +
  schema; partial-credit scoring distinguishes "didn't run" from "ran, wrong."
- **One-shot underestimates skills that assume iteration.** *Mitigation:* the
  agentic tier (D3) is the documented escalation; v1 reports one-shot lift
  honestly as such.
- **Executing model code in CI is slow/heavy.** *Mitigation:* tiny fixtures;
  subprocess isolation; configurable trial/model counts; it's the eval, run on a
  schedule, not per-PR.
- **LLM variance inflates/deflates lift.** *Mitigation:* paired same-task design
  cancels much task variance; low trial count averages the rest; report per
  model; treat single runs as data points.
- **Breaking the populated dashboard.** *Mitigation:* keep `capability-matrix.json`
  shape; add `lift-matrix.json` alongside; the dashboard is currently empty so
  there's nothing to regress.

## 10. Open questions
- Per-skill partial-credit rubric for the execute oracle (binary runs/doesn't vs
  graded column coverage) — pin per skill when built.
- Whether `discovery`/`quickstart` ground-truth needs an LLM-judge fallback for
  free-text routing, or pure string/level matching suffices.
- Reference outputs for `reconciliation` — reuse an L4-lifelib slice or a smaller
  synthetic reference.
- Trial count default for a meaningful-but-cheap lift signal.

## 11. Sources
`ref/43-skill-lifecycle/research/2026-06-15-stream2-effectiveness-eval-sota.md`
(Anthropic skill-creator executor/grader/comparator/analyzer + paired ablation;
SWE-bench execution grading; MT-Bench judge biases; statistical-evals). Current
implementation: `evals/run_evals.py`, `agents.py`, `evaluators.py`,
`result_types.py`, `datasets/*.yaml`, `serve_dashboard.py`,
`.github/workflows/evals.yml`.
