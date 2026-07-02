# L3 Effectiveness Evals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `evals/` so skills are graded by *executing what the agent emits* (and by objective ground truth for non-code skills), comparing **with-skill vs without-skill** to report per-model **lift** — replacing the self-report grading entirely.

**Architecture:** Generic oracles (`evals/oracles/`) grade an agent's raw completion: `execute` runs emitted model code via `gspio run-model` against a fixture; `numeric` additionally reconciles to a reference; `ground_truth` scores text against planted defects / code-presence / expected routing. A one-shot Executor runs each task twice (with/without skill), a Comparator computes lift per model, and `run_evals.py` writes `capability-matrix.json` + `lift-matrix.json` for the existing dashboard. Each skill maps to an oracle + carries its ground truth in the dataset, so all 7 skills ride the same machinery.

**Tech Stack:** Python 3.12, `pydantic-ai` + `pydantic-evals` (the `evals` dep group), Polars, `gspio` CLI, pytest, subprocess. Repo: `gaspatchio-core`, branch `feat/l3-eval-refactor` (worktree at `.claude/worktrees/l3-eval-refactor`).

**Execution contract (verified — the oracles depend on this):**
- Run a model: `uv run gspio run-model <model.py> <data.parquet> --output-file <out.parquet> --mode debug`, invoked with `cwd=bindings/python`. Exit 0 = ran; 1 = error. Output parquet = input columns + computed columns.
- A model file must define `def main(af: ActuarialFrame) -> ActuarialFrame:`. Input parquet needs a `Policy number` (str) column + the numeric columns the model uses.

**Conventions for every task:**
- Work in the worktree on `feat/l3-eval-refactor`. Absolute paths; git via `git -C "~/projects/gaspatchio/gaspatchio-core/.claude/worktrees/l3-eval-refactor" …`.
- **Tests run from `bindings/python`** (the only uv project — the worktree root has no pyproject, so `uv run` from there resolves the wrong workspace). Canonical: `cd "<worktree>/bindings/python" && uv run pytest ../../evals/<path> -v`. pytest auto-adds the worktree root to `sys.path` (the `evals` package has `__init__.py`), so `import evals.*` resolves. Wherever a step shows `uv run pytest evals/X`, run it as `cd "<worktree>/bindings/python" && uv run pytest ../../evals/X`.
- **One-time per worktree:** `cd "<worktree>/bindings/python" && uv sync --group evals` — installs the eval deps (`pydantic-ai`, `pydantic-evals`) AND builds the `gaspatchio_core` extension (maturin), which is required for the execute/numeric oracle tests that invoke `gspio run-model`. Do this before Task 2.
- The oracles' `gspio` subprocess uses `cwd=bindings/python` (computed as `parents[2]/"bindings"/"python"` from `evals/oracles/*.py`).
- ruff `select=["ALL"]`: docstrings (D205/D209), type hints, import only what's used. Keep `# noqa: S603`/`S101` where shown (subprocess + test asserts). Commits: signed, conventional, **no** AI/Co-Authored-By trailer.
- **Oracle tests must not call an LLM** — they grade canned artifact strings. Only the final smoke run (Task 13) needs API keys.

**Scope:** All 7 skills. Phases: (1) oracle core, (2) executor + comparator, (3) fixtures + per-skill datasets, (4) wire-up + dashboard data + smoke run. The gh-pages `skills.html` *rendering* of lift is a follow-on (noted in Task 12), since that HTML is hand-maintained on the gh-pages branch; this plan produces the lift **data**.

---

## Phase 1 — Oracle core

### Task 1: Oracle result type + code extraction

**Files:**
- Create: `evals/oracles/__init__.py`
- Create: `evals/oracles/base.py`
- Create: `evals/oracles/test_base.py`

- [ ] **Step 1: Write the failing test** — `evals/oracles/test_base.py`:

```python
"""Tests for oracle base types + code extraction."""

from evals.oracles.base import OracleResult, extract_code


def test_oracle_result_holds_score_and_detail() -> None:
    """An OracleResult carries a [0,1] score and a human detail string."""
    r = OracleResult(score=0.5, detail="2/4 columns")
    assert r.score == 0.5
    assert "2/4" in r.detail


def test_extract_code_takes_largest_python_fence() -> None:
    """extract_code returns the largest ```python fenced block, dedented."""
    md = (
        "Intro.\n\n```python\nx = 1\n```\n\n"
        "More.\n\n```python\nfrom gaspatchio_core import ActuarialFrame\n\n"
        "def main(af):\n    af.y = af.x * 2\n    return af\n```\n"
    )
    code = extract_code(md)
    assert "def main(af)" in code
    assert "x = 1" not in code  # the larger block wins


def test_extract_code_returns_empty_when_no_fence() -> None:
    """No python fence yields an empty string."""
    assert extract_code("just prose, no code") == ""
```

- [ ] **Step 2: Run, expect FAIL** — `cd "<worktree>" && uv run pytest evals/oracles/test_base.py -v` → ModuleNotFoundError.

- [ ] **Step 3: Create the files.**

`evals/oracles/__init__.py`:
```python
"""Objective grading oracles for skill effectiveness evals."""
```

`evals/oracles/base.py`:
```python
"""Shared oracle types and the code-extraction helper."""

from __future__ import annotations

import re
from dataclasses import dataclass

_FENCE = re.compile(r"```python\n(.*?)```", re.DOTALL)


@dataclass(frozen=True, slots=True)
class OracleResult:
    """The outcome of grading one artifact: a [0,1] score and a reason."""

    score: float
    detail: str


def extract_code(artifact: str) -> str:
    """Return the largest ```python fenced block in the artifact, or ''.

    Agents wrap emitted model code in a python fence; the largest block is the
    model (smaller blocks are usually illustrative snippets).
    """
    blocks = _FENCE.findall(artifact)
    if not blocks:
        return ""
    return max(blocks, key=len).strip()
```

- [ ] **Step 4: Run, expect PASS** — `uv run pytest evals/oracles/test_base.py -v` → 3 passed. `uv run ruff check evals/oracles/` → clean.

- [ ] **Step 5: Commit**
```bash
git -C "<worktree>" add evals/oracles/__init__.py evals/oracles/base.py evals/oracles/test_base.py
git -C "<worktree>" commit -m "feat(evals): oracle result type + code extraction"
```

---

### Task 2: Execute oracle (run emitted model code)

**Files:**
- Create: `evals/oracles/execute.py`
- Create: `evals/oracles/test_execute.py`
- Create: `evals/oracles/_fixtures/min_points.parquet` (via a build step below)

- [ ] **Step 1: Build a tiny fixture for the test.** Run from `<worktree>`:
```bash
uv run python - <<'PY'
from pathlib import Path
import polars as pl
d = Path("evals/oracles/_fixtures"); d.mkdir(parents=True, exist_ok=True)
pl.DataFrame({
    "Policy number": ["P1", "P2", "P3"],
    "sum_assured": [100000.0, 200000.0, 50000.0],
    "mortality_rate": [0.001, 0.004, 0.02],
    "annual_premium": [400.0, 1500.0, 900.0],
}).write_parquet(d / "min_points.parquet")
print("wrote", d / "min_points.parquet")
PY
```

- [ ] **Step 2: Write the failing test** — `evals/oracles/test_execute.py`:

```python
"""Tests for the execute oracle (runs emitted model code via gspio)."""

import shutil
from pathlib import Path

import pytest

from evals.oracles.execute import grade_execution

FIXTURE = Path(__file__).resolve().parent / "_fixtures" / "min_points.parquet"

GOOD = """Here is the model:

```python
from gaspatchio_core import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.expected_claims = af.sum_assured * af.mortality_rate
    return af
```
"""

BROKEN = """```python
from gaspatchio_core import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.x = af.nonexistent_column * 2
    return af
```
"""

NO_CODE = "I would compute expected claims as sum_assured times mortality_rate."


@pytest.fixture
def case(tmp_path: Path) -> dict:
    shutil.copy(FIXTURE, tmp_path / "data.parquet")
    return {"fixture_data": "data.parquet", "expected_columns": ["expected_claims"], "_workdir": tmp_path}


def test_good_model_scores_one(case: dict) -> None:
    """A model that runs and produces the expected column scores 1.0."""
    r = grade_execution(GOOD, case, case["_workdir"])
    assert r.score == 1.0, r.detail


def test_broken_model_scores_zero(case: dict) -> None:
    """A model that raises at run time scores 0.0."""
    r = grade_execution(BROKEN, case, case["_workdir"])
    assert r.score == 0.0, r.detail


def test_no_code_scores_zero(case: dict) -> None:
    """An artifact with no code block scores 0.0."""
    r = grade_execution(NO_CODE, case, case["_workdir"])
    assert r.score == 0.0
```

- [ ] **Step 3: Run, expect FAIL** — `uv run pytest evals/oracles/test_execute.py -v` → ModuleNotFoundError.

- [ ] **Step 4: Create `evals/oracles/execute.py`:**

```python
"""Execute oracle: run emitted model code via gspio and grade the output."""

from __future__ import annotations

import subprocess
from pathlib import Path

import polars as pl

from evals.oracles.base import OracleResult, extract_code

_BINDINGS = Path(__file__).resolve().parents[2] / "bindings" / "python"
_TIMEOUT = 300


def grade_execution(artifact: str, case: dict, workdir: Path) -> OracleResult:
    """Run the model code in `artifact` against the case fixture; grade columns.

    Score = fraction of `case["expected_columns"]` present in the output; 0.0 if
    no code, the run errors, or no output is written. The model runs in an
    isolated subprocess (`gspio run-model`) with the fixture in `workdir`.
    """
    code = extract_code(artifact)
    if not code:
        return OracleResult(0.0, "no python code block emitted")
    model_py = workdir / "model.py"
    model_py.write_text(code)
    data = workdir / case["fixture_data"]
    out = workdir / "out.parquet"
    proc = subprocess.run(  # noqa: S603
        ["uv", "run", "gspio", "run-model", str(model_py), str(data),
         "--output-file", str(out), "--mode", "debug"],
        cwd=_BINDINGS, capture_output=True, text=True, timeout=_TIMEOUT, check=False,
    )
    if proc.returncode != 0:
        return OracleResult(0.0, f"run-model failed: {proc.stderr.strip()[-300:]}")
    if not out.exists():
        return OracleResult(0.0, "no output parquet produced")
    cols = pl.read_parquet(out).columns
    expected = case["expected_columns"]
    present = [c for c in expected if c in cols]
    score = len(present) / len(expected) if expected else 1.0
    return OracleResult(score, f"{len(present)}/{len(expected)} expected columns present")
```

- [ ] **Step 5: Run, expect PASS** — `uv run pytest evals/oracles/test_execute.py -v` → 3 passed. (Needs the `gspio` CLI available via `uv` in `bindings/python` — it is; no API keys needed.) `uv run ruff check evals/oracles/execute.py` → clean.

- [ ] **Step 6: Commit**
```bash
git -C "<worktree>" add evals/oracles/execute.py evals/oracles/test_execute.py evals/oracles/_fixtures/min_points.parquet
git -C "<worktree>" commit -m "feat(evals): execute oracle (runs emitted model via gspio)"
```

---

### Task 3: Numeric oracle (reconcile to reference)

**Files:**
- Create: `evals/oracles/numeric.py`
- Create: `evals/oracles/test_numeric.py`

- [ ] **Step 1: Write the failing test** — `evals/oracles/test_numeric.py`:

```python
"""Tests for the numeric oracle (reconcile output to a reference)."""

import shutil
from pathlib import Path

import polars as pl
import pytest

from evals.oracles.numeric import grade_numeric

FIXTURE = Path(__file__).resolve().parent / "_fixtures" / "min_points.parquet"

MATCHES = """```python
from gaspatchio_core import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.expected_claims = af.sum_assured * af.mortality_rate
    return af
```
"""

WRONG = """```python
from gaspatchio_core import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.expected_claims = af.sum_assured * af.mortality_rate * 2.0
    return af
```
"""


@pytest.fixture
def case(tmp_path: Path) -> dict:
    shutil.copy(FIXTURE, tmp_path / "data.parquet")
    # Reference = the correct answer for this fixture.
    pts = pl.read_parquet(FIXTURE)
    ref = pts.select(
        (pl.col("sum_assured") * pl.col("mortality_rate")).alias("expected_claims")
    )
    ref.write_parquet(tmp_path / "reference.parquet")
    return {
        "fixture_data": "data.parquet",
        "reference": "reference.parquet",
        "reconcile_columns": ["expected_claims"],
        "tolerance": 1e-6,
        "_workdir": tmp_path,
    }


def test_matching_model_scores_one(case: dict) -> None:
    """A model whose numbers match the reference within tolerance scores 1.0."""
    r = grade_numeric(MATCHES, case, case["_workdir"])
    assert r.score == 1.0, r.detail


def test_wrong_model_scores_below_one(case: dict) -> None:
    """A model off by 2x scores below 1.0."""
    r = grade_numeric(WRONG, case, case["_workdir"])
    assert r.score < 1.0, r.detail
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest evals/oracles/test_numeric.py -v` → ModuleNotFoundError.

- [ ] **Step 3: Create `evals/oracles/numeric.py`:**

```python
"""Numeric oracle: run emitted model code, reconcile to a stored reference."""

from __future__ import annotations

import subprocess
from pathlib import Path

import polars as pl

from evals.oracles.base import OracleResult, extract_code

_BINDINGS = Path(__file__).resolve().parents[2] / "bindings" / "python"
_TIMEOUT = 300


def grade_numeric(artifact: str, case: dict, workdir: Path) -> OracleResult:
    """Run the model, then reconcile `case["reconcile_columns"]` to the reference.

    Score = 1.0 if the worst relative difference across the reconcile columns is
    within `case["tolerance"]`, else `max(0, 1 - worst_rel)`. 0.0 if it does not
    run or a reconcile column is missing.
    """
    code = extract_code(artifact)
    if not code:
        return OracleResult(0.0, "no python code block emitted")
    (workdir / "model.py").write_text(code)
    out = workdir / "out.parquet"
    proc = subprocess.run(  # noqa: S603
        ["uv", "run", "gspio", "run-model", str(workdir / "model.py"),
         str(workdir / case["fixture_data"]), "--output-file", str(out), "--mode", "debug"],
        cwd=_BINDINGS, capture_output=True, text=True, timeout=_TIMEOUT, check=False,
    )
    if proc.returncode != 0 or not out.exists():
        return OracleResult(0.0, f"run-model failed: {proc.stderr.strip()[-300:]}")
    got = pl.read_parquet(out)
    ref = pl.read_parquet(workdir / case["reference"])
    tol = float(case.get("tolerance", 1e-6))
    worst = 0.0
    for col in case["reconcile_columns"]:
        if col not in got.columns:
            return OracleResult(0.0, f"missing reconcile column: {col}")
        denom = ref[col].abs().max() or 1.0
        rel = (got[col] - ref[col]).abs().max() / denom
        worst = max(worst, float(rel))
    score = 1.0 if worst <= tol else max(0.0, 1.0 - worst)
    return OracleResult(score, f"worst relative diff {worst:.2e} (tol {tol:.0e})")
```

- [ ] **Step 4: Run, expect PASS** — `uv run pytest evals/oracles/test_numeric.py -v` → 2 passed. `uv run ruff check evals/oracles/numeric.py` → clean.

- [ ] **Step 5: Commit**
```bash
git -C "<worktree>" add evals/oracles/numeric.py evals/oracles/test_numeric.py
git -C "<worktree>" commit -m "feat(evals): numeric oracle (reconcile to reference)"
```

---

### Task 4: Ground-truth oracles (seeded defects, no-code, routing)

**Files:**
- Create: `evals/oracles/ground_truth.py`
- Create: `evals/oracles/test_ground_truth.py`

- [ ] **Step 1: Write the failing test** — `evals/oracles/test_ground_truth.py`:

```python
"""Tests for the text ground-truth oracles."""

from evals.oracles.ground_truth import (
    grade_no_code,
    grade_routing,
    grade_seeded_defects,
)


def test_seeded_defects_scores_recall() -> None:
    """Score = fraction of planted defect terms named in the findings text."""
    findings = "Critical: this uses map_elements which defeats vectorisation."
    case = {"planted_defects": ["map_elements", "for-loop"]}
    r = grade_seeded_defects(findings, case)
    assert r.score == 0.5, r.detail


def test_seeded_defects_clean_case_rewards_no_false_alarm() -> None:
    """A clean case (no planted defects) scores 1.0 only if no critical raised."""
    case = {"planted_defects": [], "forbidden_terms": ["critical", "bug"]}
    assert grade_seeded_defects("Looks correct; no issues found.", case).score == 1.0
    assert grade_seeded_defects("Critical bug here!", case).score == 0.0


def test_no_code_detects_python_fence() -> None:
    """grade_no_code scores 1.0 only when the artifact contains no python code."""
    assert grade_no_code("What is your valuation date?", {}).score == 1.0
    assert grade_no_code("```python\nx=1\n```", {}).score == 0.0


def test_routing_matches_expected_level() -> None:
    """grade_routing scores 1.0 when the expected level string appears."""
    case = {"expected_level": "Level 3"}
    assert grade_routing("I'd route you to Level 3 (Mini VA).", case).score == 1.0
    assert grade_routing("Start at Level 1.", case).score == 0.0
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest evals/oracles/test_ground_truth.py -v` → ModuleNotFoundError.

- [ ] **Step 3: Create `evals/oracles/ground_truth.py`:**

```python
"""Ground-truth oracles for non-code skills: defects, code-presence, routing."""

from __future__ import annotations

import re

from evals.oracles.base import OracleResult, extract_code


def grade_seeded_defects(artifact: str, case: dict) -> OracleResult:
    """Score a review against planted defects.

    With planted defects: score = recall (fraction named, case-insensitive).
    Clean case (no planted defects): 1.0 only if no `forbidden_terms` appear —
    rewarding the agent for not inventing criticals.
    """
    text = artifact.lower()
    planted = case.get("planted_defects", [])
    if planted:
        found = sum(1 for d in planted if d.lower() in text)
        return OracleResult(found / len(planted), f"named {found}/{len(planted)} planted defects")
    forbidden = case.get("forbidden_terms", [])
    raised = [t for t in forbidden if t.lower() in text]
    return OracleResult(0.0 if raised else 1.0, f"false-alarm terms: {raised}" if raised else "clean, no false alarm")


def grade_no_code(artifact: str, case: dict) -> OracleResult:  # noqa: ARG001
    """Score 1.0 if the artifact contains no python code block (discovery gate)."""
    return OracleResult(0.0 if extract_code(artifact) else 1.0,
                        "code emitted (should not)" if extract_code(artifact) else "no code, as required")


def grade_routing(artifact: str, case: dict) -> OracleResult:
    """Score 1.0 if the expected tutorial level appears as a whole phrase."""
    level = case["expected_level"]
    hit = re.search(rf"\b{re.escape(level)}\b", artifact) is not None
    return OracleResult(1.0 if hit else 0.0, f"expected '{level}': {'found' if hit else 'absent'}")
```

- [ ] **Step 4: Run, expect PASS** — `uv run pytest evals/oracles/test_ground_truth.py -v` → 4 passed. `uv run ruff check evals/oracles/ground_truth.py` → clean.

- [ ] **Step 5: Commit**
```bash
git -C "<worktree>" add evals/oracles/ground_truth.py evals/oracles/test_ground_truth.py
git -C "<worktree>" commit -m "feat(evals): ground-truth oracles (defects, no-code, routing)"
```

---

### Task 5: Accessor oracle (extending skill)

**Files:**
- Create: `evals/oracles/accessor.py`
- Create: `evals/oracles/test_accessor.py`

- [ ] **Step 1: Write the failing test** — `evals/oracles/test_accessor.py`:

```python
"""Tests for the accessor oracle (extending skill): static anti-pattern scan."""

from evals.oracles.accessor import grade_accessor

CLEAN = """```python
from gaspatchio_core import ActuarialFrame

def hazard(af):
    return -(1 - af.qx).log()
```
"""

ANTIPATTERN = """```python
def hazard(af):
    return af.qx.map_elements(lambda q: -1)
```
"""


def test_clean_accessor_scores_one() -> None:
    """Emitted code free of vectorisation anti-patterns scores 1.0."""
    assert grade_accessor(CLEAN, {}).score == 1.0


def test_antipattern_scores_zero() -> None:
    """map_elements / apply / iter_rows / row-loops score 0.0."""
    assert grade_accessor(ANTIPATTERN, {}).score == 0.0


def test_no_code_scores_zero() -> None:
    """No code block scores 0.0."""
    assert grade_accessor("I'd write an accessor.", {}).score == 0.0
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest evals/oracles/test_accessor.py -v` → ModuleNotFoundError.

- [ ] **Step 3: Create `evals/oracles/accessor.py`:**

```python
"""Accessor oracle (extending skill): static scan for vectorisation anti-patterns.

v1 grades the emitted code statically (the anti-patterns the skill forbids are
syntactic). A future tier can import + apply the accessor to scalar/list columns;
the seam is the same `grade(artifact, case)` signature.
"""

from __future__ import annotations

import re

from evals.oracles.base import OracleResult, extract_code

_ANTIPATTERNS = (
    re.compile(r"\.map_elements\b"),
    re.compile(r"\.apply\b"),
    re.compile(r"\.iter_rows\b"),
    re.compile(r"\bfor\s+\w+\s+in\s+.*\.(iter_rows|rows)\b"),
)


def grade_accessor(artifact: str, case: dict) -> OracleResult:  # noqa: ARG001
    """Score 1.0 if emitted code is anti-pattern-free, 0.0 if not (or no code)."""
    code = extract_code(artifact)
    if not code:
        return OracleResult(0.0, "no python code block emitted")
    hits = [p.pattern for p in _ANTIPATTERNS if p.search(code)]
    return OracleResult(0.0 if hits else 1.0, f"anti-patterns: {hits}" if hits else "vectorised, clean")
```

- [ ] **Step 4: Run, expect PASS** — `uv run pytest evals/oracles/test_accessor.py -v` → 3 passed. `uv run ruff check evals/oracles/accessor.py` → clean.

- [ ] **Step 5: Commit**
```bash
git -C "<worktree>" add evals/oracles/accessor.py evals/oracles/test_accessor.py
git -C "<worktree>" commit -m "feat(evals): accessor oracle (static anti-pattern scan)"
```

---

## Phase 2 — Executor + Comparator

### Task 6: Executor (with/without-skill arms)

**Files:**
- Modify (rewrite): `evals/agents.py`
- Create: `evals/test_agents.py`

- [ ] **Step 1: Write the failing test** — `evals/test_agents.py` (no LLM — checks prompt composition + the with/without seam):

```python
"""Tests for the executor's prompt composition (no LLM calls)."""

from evals.agents import build_system_prompt


def test_with_skill_includes_skill_content() -> None:
    """The with-skill prompt contains the skill's SKILL.md text."""
    p = build_system_prompt("model-building", with_skill=True)
    assert "Building Gaspatchio Models" in p  # SKILL.md H1


def test_without_skill_omits_skill_content() -> None:
    """The baseline prompt omits skill content but keeps the task framing."""
    p = build_system_prompt("model-building", with_skill=False)
    assert "Building Gaspatchio Models" not in p
    assert "gaspatchio" in p.lower()  # generic framing remains
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest evals/test_agents.py -v` → ImportError (`build_system_prompt` not defined).

- [ ] **Step 3: Rewrite `evals/agents.py`** (replaces the self-report `output_type` agents with free-form completion agents + the with/without seam):

```python
"""Executor: build with/without-skill agents that emit free-form artifacts.

The agent's completion (model code or analysis text) is graded by an oracle —
there is no structured self-report output type. Each task runs twice: with the
skill content in the system prompt, and without (baseline), for lift.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_ai import Agent

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

_BASELINE = (
    "You are helping build actuarial models with gaspatchio, a Python "
    "framework. Answer the user's request directly and completely. When you "
    "write model code, return it in a single ```python code block."
)

SKILL_DIRS = {
    "review": "model-review",
    "discovery": "model-discovery",
    "quickstart": "quickstart",
    "building": "model-building",
    "reconciliation": "model-reconciliation",
    "scenarios": "model-scenarios",
    "extending": "extending-gaspatchio",
}


def _load_skill_content(skill_dir: str) -> str:
    """Load SKILL.md + reference files for a skill directory."""
    d = SKILLS_DIR / skill_dir
    parts = [(d / "SKILL.md").read_text()]
    refs = d / "references"
    if refs.exists():
        for ref in sorted(refs.glob("*.md")):
            parts.append(f"\n\n--- Reference: {ref.name} ---\n\n{ref.read_text()}")
    return "\n".join(parts)


def build_system_prompt(skill: str, *, with_skill: bool) -> str:
    """Compose the system prompt: baseline framing, plus skill content iff with_skill."""
    if not with_skill:
        return _BASELINE
    return _load_skill_content(SKILL_DIRS[skill]) + "\n\n" + _BASELINE


def make_agent(skill: str, model: str, *, with_skill: bool) -> Agent[None, str]:
    """Create a plain-text agent for a skill/model, with or without the skill."""
    return Agent(model, system_prompt=build_system_prompt(skill, with_skill=with_skill))
```

- [ ] **Step 4: Run, expect PASS** — `uv run pytest evals/test_agents.py -v` → 2 passed. (`test_with_skill_includes_skill_content` asserts the `model-building` SKILL.md H1 "Building Gaspatchio Models" — confirm that heading exists; if the H1 differs, use the actual H1 text from `skills/model-building/SKILL.md`.) `uv run ruff check evals/agents.py` → clean.

- [ ] **Step 5: Commit**
```bash
git -C "<worktree>" add evals/agents.py evals/test_agents.py
git -C "<worktree>" commit -m "refactor(evals): executor emits free-form artifacts + with/without-skill seam"
```

---

### Task 7: Comparator (per-model lift)

**Files:**
- Create: `evals/comparator.py`
- Create: `evals/test_comparator.py`

- [ ] **Step 1: Write the failing test** — `evals/test_comparator.py`:

```python
"""Tests for lift computation."""

from evals.comparator import lift


def test_lift_is_with_minus_without_per_model() -> None:
    """Lift = mean(with) - mean(without), computed per model."""
    with_scores = {"sonnet": [1.0, 0.5], "haiku": [0.5, 0.5]}
    without_scores = {"sonnet": [0.5, 0.5], "haiku": [0.5, 0.5]}
    out = lift(with_scores, without_scores)
    assert out["sonnet"] == pytest_approx(0.25)
    assert out["haiku"] == 0.0


def pytest_approx(v: float) -> float:
    """Tiny shim so the test reads clearly without importing pytest.approx."""
    return round(v, 10)
```

(Note: replace the shim — use `pytest.approx`. Final test:)
```python
"""Tests for lift computation."""

import pytest

from evals.comparator import lift


def test_lift_is_with_minus_without_per_model() -> None:
    """Lift = mean(with) - mean(without), computed per model, never pooled."""
    out = lift(
        {"sonnet": [1.0, 0.5], "haiku": [0.5, 0.5]},
        {"sonnet": [0.5, 0.5], "haiku": [0.5, 0.5]},
    )
    assert out["sonnet"] == pytest.approx(0.25)
    assert out["haiku"] == pytest.approx(0.0)
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest evals/test_comparator.py -v` → ImportError.

- [ ] **Step 3: Create `evals/comparator.py`:**

```python
"""Comparator: per-model lift = mean(with-skill) - mean(without-skill)."""

from __future__ import annotations


def lift(
    with_scores: dict[str, list[float]],
    without_scores: dict[str, list[float]],
) -> dict[str, float]:
    """Return per-model lift. Never pools across models (effects are model-conditional)."""
    out: dict[str, float] = {}
    for model, ws in with_scores.items():
        bs = without_scores.get(model, [])
        w = sum(ws) / len(ws) if ws else 0.0
        b = sum(bs) / len(bs) if bs else 0.0
        out[model] = w - b
    return out
```

- [ ] **Step 4: Run, expect PASS** — `uv run pytest evals/test_comparator.py -v` → 1 passed (use the second, `pytest.approx` version of the test). `uv run ruff check evals/comparator.py` → clean.

- [ ] **Step 5: Commit**
```bash
git -C "<worktree>" add evals/comparator.py evals/test_comparator.py
git -C "<worktree>" commit -m "feat(evals): per-model lift comparator"
```

---

## Phase 3 — Fixtures, registry, per-skill datasets

### Task 8: Skill→oracle registry + fixtures builder

**Files:**
- Create: `evals/oracles/registry.py`
- Create: `evals/oracles/test_registry.py`
- Create: `evals/fixtures/_build.py`

- [ ] **Step 1: Write the failing test** — `evals/oracles/test_registry.py`:

```python
"""Tests for the skill->oracle registry."""

from evals.oracles.registry import ORACLES, oracle_for


def test_every_skill_maps_to_a_callable_oracle() -> None:
    """All 7 skills resolve to a callable grader."""
    skills = ["review", "discovery", "quickstart", "building",
              "reconciliation", "scenarios", "extending"]
    for s in skills:
        assert callable(oracle_for(s)), s


def test_oracle_signature_is_uniform() -> None:
    """Every oracle is registered under a name in ORACLES."""
    assert set(ORACLES) >= {"execute", "numeric", "ground_truth_defects",
                            "ground_truth_no_code", "ground_truth_routing", "accessor"}
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest evals/oracles/test_registry.py -v` → ModuleNotFoundError.

- [ ] **Step 3: Create `evals/oracles/registry.py`:**

```python
"""Map each skill to the oracle that grades its artifact.

Oracles share the signature ``grade(artifact: str, case: dict, workdir: Path) -> OracleResult``.
Text oracles ignore `workdir`; execution oracles use it. The dataset case carries
the ground truth (expected_columns / reference / planted_defects / expected_level).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from evals.oracles.accessor import grade_accessor
from evals.oracles.base import OracleResult
from evals.oracles.execute import grade_execution
from evals.oracles.ground_truth import grade_no_code, grade_routing, grade_seeded_defects
from evals.oracles.numeric import grade_numeric


def _text(fn: Callable[[str, dict], OracleResult]) -> Callable[[str, dict, Path], OracleResult]:
    """Adapt a text oracle (artifact, case) to the uniform (artifact, case, workdir)."""
    def wrapped(artifact: str, case: dict, workdir: Path) -> OracleResult:  # noqa: ARG001
        return fn(artifact, case)
    return wrapped


ORACLES: dict[str, Callable[[str, dict, Path], OracleResult]] = {
    "execute": grade_execution,
    "numeric": grade_numeric,
    "ground_truth_defects": _text(grade_seeded_defects),
    "ground_truth_no_code": _text(grade_no_code),
    "ground_truth_routing": _text(grade_routing),
    "accessor": _text(grade_accessor),
}

SKILL_ORACLE: dict[str, str] = {
    "building": "execute",
    "reconciliation": "numeric",
    "scenarios": "execute",
    "extending": "accessor",
    "review": "ground_truth_defects",
    "discovery": "ground_truth_no_code",
    "quickstart": "ground_truth_routing",
}


def oracle_for(skill: str) -> Callable[[str, dict, Path], OracleResult]:
    """Return the oracle callable for a skill."""
    return ORACLES[SKILL_ORACLE[skill]]
```

- [ ] **Step 4: Create `evals/fixtures/_build.py`** (deterministic fixture generator):

```python
"""Build deterministic eval fixtures (tiny synthetic parquets). Run:

    uv run python evals/fixtures/_build.py
"""

from pathlib import Path

import polars as pl

OUT = Path(__file__).resolve().parent


def build() -> None:
    """Write the model-points fixture used by the execute/numeric oracles."""
    (OUT / "building").mkdir(exist_ok=True)
    pts = pl.DataFrame({
        "Policy number": ["P1", "P2", "P3", "P4"],
        "sum_assured": [100000.0, 250000.0, 50000.0, 175000.0],
        "mortality_rate": [0.001, 0.004, 0.02, 0.008],
        "annual_premium": [400.0, 1500.0, 900.0, 1100.0],
    })
    pts.write_parquet(OUT / "building" / "model_points.parquet")

    (OUT / "reconciliation").mkdir(exist_ok=True)
    pts.write_parquet(OUT / "reconciliation" / "model_points.parquet")
    pts.select(
        (pl.col("sum_assured") * pl.col("mortality_rate")).alias("expected_claims")
    ).write_parquet(OUT / "reconciliation" / "reference.parquet")


if __name__ == "__main__":
    build()
    print("fixtures built")  # noqa: T201
```

- [ ] **Step 5: Build fixtures + run tests** — `uv run python evals/fixtures/_build.py` then `uv run pytest evals/oracles/test_registry.py -v` → 2 passed. `uv run ruff check evals/oracles/registry.py evals/fixtures/_build.py` → clean.

- [ ] **Step 6: Commit**
```bash
git -C "<worktree>" add evals/oracles/registry.py evals/oracles/test_registry.py evals/fixtures/
git -C "<worktree>" commit -m "feat(evals): skill->oracle registry + deterministic fixtures"
```

---

### Task 9: Rewrite datasets — execute & numeric skills (building, reconciliation, scenarios, extending)

Datasets move from "input + self-report evaluator" to "task prompt + ground truth the oracle reads." The new dataset format is a plain YAML the rewritten `run_evals.py` reads directly (not via pydantic-evals' evaluator wiring — that coupled to self-report). Each case: `name`, `prompt`, and oracle ground-truth keys.

**Files:**
- Rewrite: `evals/datasets/building.yaml`, `reconciliation.yaml`, `scenarios.yaml`, `extending.yaml`
- Create: `evals/test_datasets.py`

- [ ] **Step 1: Write the failing test** — `evals/test_datasets.py`:

```python
"""Every dataset is well-formed for the new oracle-driven runner."""

from pathlib import Path

import yaml

DATASETS = Path(__file__).resolve().parent / "datasets"
SKILLS = ["review", "discovery", "quickstart", "building",
          "reconciliation", "scenarios", "extending"]


def test_every_skill_has_a_dataset_with_cases() -> None:
    """Each skill has a YAML dataset with at least one case carrying a prompt."""
    for skill in SKILLS:
        data = yaml.safe_load((DATASETS / f"{skill}.yaml").read_text())
        assert data["cases"], skill
        for case in data["cases"]:
            assert case["name"] and case["prompt"], (skill, case.get("name"))
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest evals/test_datasets.py -v` → FAIL (existing datasets use `inputs`/`evaluators`, not `prompt`).

- [ ] **Step 3: Rewrite `evals/datasets/building.yaml`:**

```yaml
# Building skill: emit a model; oracle runs it and checks expected columns.
cases:
  - name: expected_claims
    prompt: |
      Write a complete gaspatchio model. The input parquet model_points.parquet
      has columns: "Policy number" (str), sum_assured (f64), mortality_rate (f64),
      annual_premium (f64). Define `def main(af): ...` that adds a column
      `expected_claims` = sum_assured * mortality_rate. Return a single ```python
      block.
    fixture_data: building/model_points.parquet
    expected_columns: ["expected_claims"]
  - name: net_premium_and_claims
    prompt: |
      Write a complete gaspatchio model over model_points.parquet (columns:
      "Policy number", sum_assured, mortality_rate, annual_premium). Add
      `expected_claims` = sum_assured * mortality_rate and `net_premium` =
      annual_premium - expected_claims. Return one ```python block defining
      `def main(af): ...`.
    fixture_data: building/model_points.parquet
    expected_columns: ["expected_claims", "net_premium"]
```

- [ ] **Step 4: Rewrite `evals/datasets/reconciliation.yaml`:**

```yaml
# Reconciliation skill: emit a model whose numbers match the reference.
cases:
  - name: claims_match_reference
    prompt: |
      Write a gaspatchio model over model_points.parquet (columns: "Policy
      number", sum_assured, mortality_rate, annual_premium). It must produce a
      column `expected_claims` that reconciles to the reference. The intended
      calculation is expected_claims = sum_assured * mortality_rate. Return one
      ```python block defining `def main(af): ...`.
    fixture_data: reconciliation/model_points.parquet
    reference: reconciliation/reference.parquet
    reconcile_columns: ["expected_claims"]
    tolerance: 1.0e-6
```

- [ ] **Step 5: Rewrite `evals/datasets/scenarios.yaml`** (executes; reuses the building fixture; the oracle checks the emitted code runs and adds a shocked column):

```yaml
# Scenarios skill: emit a model applying a mortality shock; oracle runs it.
cases:
  - name: mortality_shock_column
    prompt: |
      Write a complete gaspatchio model over model_points.parquet (columns:
      "Policy number", sum_assured, mortality_rate, annual_premium). Apply a
      +20% mortality stress: add a column `claims_stressed` =
      sum_assured * mortality_rate * 1.2. Return one ```python block defining
      `def main(af): ...`.
    fixture_data: building/model_points.parquet
    expected_columns: ["claims_stressed"]
```

- [ ] **Step 6: Rewrite `evals/datasets/extending.yaml`** (accessor oracle — static scan, no fixture):

```yaml
# Extending skill: emit accessor/helper code; oracle scans for anti-patterns.
cases:
  - name: hazard_rate_vectorised
    prompt: |
      Write a gaspatchio helper that computes a hazard rate from a mortality
      rate column qx as -ln(1 - qx), vectorised (no per-row Python). Return one
      ```python block.
  - name: cumulative_growth_vectorised
    prompt: |
      Write a gaspatchio helper that computes cumulative account-value growth
      from a per-period return column, vectorised across the projection (no
      map_elements, no row loops). Return one ```python block.
```

- [ ] **Step 7: Run, expect PASS** — `uv run pytest evals/test_datasets.py -v` → it now checks all 7, but discovery/quickstart/review are still the OLD format → it will FAIL on those until Task 10. So run only the rewritten ones for now: `uv run pytest evals/test_datasets.py -v` is expected to FAIL on review/discovery/quickstart — that's fine; proceed to Task 10 which fixes them, then this test passes. (Do not commit a passing claim yet.)

- [ ] **Step 8: Commit**
```bash
git -C "<worktree>" add evals/datasets/building.yaml evals/datasets/reconciliation.yaml evals/datasets/scenarios.yaml evals/datasets/extending.yaml evals/test_datasets.py
git -C "<worktree>" commit -m "refactor(evals): oracle-driven datasets for building/reconciliation/scenarios/extending"
```

---

### Task 10: Rewrite datasets — ground-truth skills (review, discovery, quickstart)

**Files:**
- Rewrite: `evals/datasets/review.yaml`, `discovery.yaml`, `quickstart.yaml`

- [ ] **Step 1: Rewrite `evals/datasets/review.yaml`** (seeded-defect cases; oracle scores recall over the planted defects, and no-false-alarm for the clean case):

```yaml
# Review skill: feed code with planted defects; oracle scores recall.
cases:
  - name: catches_map_elements
    prompt: |
      Review this gaspatchio model for issues:
      ```python
      def main(af):
          af.age_category = af.age.map_elements(lambda x: "young" if x < 40 else "old")
          return af
      ```
    planted_defects: ["map_elements"]
  - name: catches_for_loop
    prompt: |
      Review this gaspatchio model for issues:
      ```python
      def main(af):
          out = []
          for row in af.collect().iter_rows(named=True):
              out.append(row["premium"] * 2)
          return af
      ```
    planted_defects: ["iter_rows", "loop"]
  - name: catches_hardcoded_assumption
    prompt: |
      Review this gaspatchio model for issues:
      ```python
      def main(af):
          af.mortality_rate = 0.015
          af.claims = af.sum_assured * af.mortality_rate
          return af
      ```
    planted_defects: ["hardcoded", "Table"]
  - name: passes_clean_model
    prompt: |
      Review this gaspatchio model section; report only real issues:
      ```python
      af.mort_rate_ann = mortality_table.lookup(af.attained_age, af.sex)
      af.pols_death = af.pols_if * af.mort_rate_ann
      ```
    planted_defects: []
    forbidden_terms: ["critical", "map_elements", "for-loop"]
```

- [ ] **Step 2: Rewrite `evals/datasets/discovery.yaml`** (no-code oracle):

```yaml
# Discovery skill: must scope before coding; oracle scores "no code emitted".
cases:
  - name: asks_before_coding_term_product
    prompt: |
      I want to build a term insurance model in gaspatchio. Help me get started.
  - name: asks_before_coding_va
    prompt: |
      Port my Excel variable-annuity model to gaspatchio.
```

- [ ] **Step 3: Rewrite `evals/datasets/quickstart.yaml`** (routing oracle):

```yaml
# Quickstart skill: routes to the right tutorial level.
cases:
  - name: routes_va_to_level_3
    prompt: |
      I'm new to gaspatchio and want to build a mini variable-annuity model with
      mortality, lapse, account value, and discounting. Where should I start?
    expected_level: "Level 3"
  - name: routes_beginner_to_level_1
    prompt: |
      I've never used gaspatchio. What's the very first tutorial I should do?
    expected_level: "Level 1"
```

- [ ] **Step 4: Run, expect PASS** — `uv run pytest evals/test_datasets.py -v` → 1 passed (all 7 datasets now well-formed). `uv run python -c "import yaml; [yaml.safe_load(open(f'evals/datasets/{s}.yaml')) for s in ['review','discovery','quickstart','building','reconciliation','scenarios','extending']]"` → no error.

- [ ] **Step 5: Commit**
```bash
git -C "<worktree>" add evals/datasets/review.yaml evals/datasets/discovery.yaml evals/datasets/quickstart.yaml
git -C "<worktree>" commit -m "refactor(evals): oracle-driven datasets for review/discovery/quickstart"
```

---

## Phase 4 — Wire-up, dashboard data, smoke run

### Task 11: Rewrite `run_evals.py` (loop → oracle → lift); delete self-report code

**Files:**
- Rewrite: `evals/run_evals.py`
- Delete: `evals/result_types.py`, `evals/evaluators.py`
- Rewrite: `evals/test_evals.py` (the old slow tests reference deleted symbols)

- [ ] **Step 1: Delete the self-report modules + update conftest if it imports them.**
```bash
git -C "<worktree>" rm evals/result_types.py evals/evaluators.py
grep -rn "result_types\|evaluators import\|from evals.evaluators" "<worktree>/evals" || echo "no remaining refs"
```
If `evals/conftest.py` or others import the deleted modules, remove those imports in this task.

- [ ] **Step 2: Rewrite `evals/run_evals.py`:**

```python
#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: T201
"""Run skill effectiveness evals: with/without-skill, per-model lift.

    uv run python evals/run_evals.py                          # all skills, all models
    uv run python evals/run_evals.py --skill building          # one skill
    uv run python evals/run_evals.py --model anthropic:claude-haiku-4-5 --trials 1
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from evals.agents import SKILL_DIRS, make_agent
from evals.comparator import lift
from evals.oracles.registry import oracle_for

DATASETS = _REPO_ROOT / "evals" / "datasets"
FIXTURES = _REPO_ROOT / "evals" / "fixtures"
RESULTS = _REPO_ROOT / "evals" / "results"

MODELS = [
    "anthropic:claude-sonnet-4-6",
    "anthropic:claude-haiku-4-5",
    "openai:gpt-5.4",
    "openai:gpt-5.4-mini",
]


def _score_arm(skill: str, model: str, *, with_skill: bool, trials: int) -> float:
    """Mean oracle score for one skill/model/arm over its dataset cases × trials."""
    cases = yaml.safe_load((DATASETS / f"{skill}.yaml").read_text())["cases"]
    agent = make_agent(skill, model, with_skill=with_skill)
    grade = oracle_for(skill)
    scores: list[float] = []
    for case in cases:
        for _ in range(trials):
            with tempfile.TemporaryDirectory() as td:
                workdir = Path(td)
                # Build a fresh per-trial case from the original (never mutate
                # `case` in place — trial 2 would then see a basename path).
                run_case = dict(case)
                if case.get("fixture_data"):
                    name = Path(case["fixture_data"]).name
                    shutil.copy(FIXTURES / case["fixture_data"], workdir / name)
                    run_case["fixture_data"] = name
                if case.get("reference"):
                    name = Path(case["reference"]).name
                    shutil.copy(FIXTURES / case["reference"], workdir / name)
                    run_case["reference"] = name
                artifact = agent.run_sync(run_case["prompt"]).output
                scores.append(grade(artifact, run_case, workdir).score)
    return sum(scores) / len(scores) if scores else 0.0


def main() -> None:
    """Run evals, write capability + lift matrices."""
    ap = argparse.ArgumentParser(description="Skill effectiveness evals")
    ap.add_argument("--model")
    ap.add_argument("--skill")
    ap.add_argument("--trials", type=int, default=1)
    args = ap.parse_args()

    models = [args.model] if args.model else MODELS
    skills = [args.skill] if args.skill else list(SKILL_DIRS)

    capability: dict[str, dict[str, float]] = {}
    with_by_model: dict[str, dict[str, list[float]]] = {}
    without_by_model: dict[str, dict[str, list[float]]] = {}

    for model in models:
        capability[model] = {}
        for skill in skills:
            w = _score_arm(skill, model, with_skill=True, trials=args.trials)
            b = _score_arm(skill, model, with_skill=False, trials=args.trials)
            capability[model][skill] = w
            with_by_model.setdefault(skill, {})[model] = [w]
            without_by_model.setdefault(skill, {})[model] = [b]
            print(f"{model} / {skill}: with={w:.2f} without={b:.2f} lift={w - b:+.2f}")

    lift_matrix = {skill: lift(with_by_model[skill], without_by_model[skill]) for skill in skills}

    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "capability-matrix.json").write_text(json.dumps(capability, indent=2))
    (RESULTS / "lift-matrix.json").write_text(json.dumps(lift_matrix, indent=2))
    print(f"\nWrote capability-matrix.json + lift-matrix.json to {RESULTS}/")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Rewrite `evals/test_evals.py`** (a cheap, no-LLM structural test of the wiring + the slow opt-in test):

```python
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Eval wiring tests. The structural test is free; the slow test calls LLM APIs.

    uv run pytest evals/test_evals.py            # structural (free)
    uv run pytest evals/test_evals.py -m slow    # real eval (costs API $)
"""

from pathlib import Path

import pytest
import yaml

from evals.agents import SKILL_DIRS
from evals.oracles.registry import oracle_for

DATASETS = Path(__file__).resolve().parent / "datasets"


def test_every_skill_wires_to_an_oracle_and_dataset() -> None:
    """Each skill has a dataset and a resolvable oracle (no LLM call)."""
    for skill in SKILL_DIRS:
        assert callable(oracle_for(skill)), skill
        cases = yaml.safe_load((DATASETS / f"{skill}.yaml").read_text())["cases"]
        assert cases, skill


@pytest.mark.slow
def test_building_lift_is_nonnegative() -> None:
    """With-skill should not underperform baseline on building (costs API $)."""
    from evals.run_evals import _score_arm

    model = "anthropic:claude-haiku-4-5"
    w = _score_arm("building", model, with_skill=True, trials=1)
    b = _score_arm("building", model, with_skill=False, trials=1)
    assert w >= b - 0.01, f"with={w} < without={b}"
```

- [ ] **Step 4: Run the free tests, expect PASS** — `uv run pytest evals/ -v -m "not slow"` → all pass (oracles, agents, comparator, datasets, registry, wiring), no collection errors, no refs to deleted modules. `uv run ruff check evals/` → clean (fix any import-order/unused from the deletions).

- [ ] **Step 5: Commit**
```bash
git -C "<worktree>" add evals/run_evals.py evals/test_evals.py
git -C "<worktree>" commit -m "refactor(evals): oracle-driven runner with per-model lift; drop self-report modules"
```

---

### Task 12: Write the lift matrix into the dashboard data + CI note

**Files:**
- Modify: `evals/serve_dashboard.py`
- Modify: `.github/workflows/evals.yml`

- [ ] **Step 1: Make the dashboard preview load `lift-matrix.json`.** In `evals/serve_dashboard.py`, the `prepare_preview()` function copies `capability-matrix.json` into `dev/capability/`. Add, immediately after that block (the `if cap_matrix.exists():` block):

```python
    # Lift matrix (with-skill minus without-skill, per model)
    lift_matrix = RESULTS_DIR / "lift-matrix.json"
    if lift_matrix.exists():
        shutil.copy2(lift_matrix, PREVIEW_DIR / "dev" / "capability" / "lift-matrix.json")
        print(f"  Lift Matrix: loaded from {lift_matrix}")
```

- [ ] **Step 2: Note the data contract for the gh-pages page.** Add a comment at the top of `prepare_preview()` (below its docstring) so the gh-pages `skills.html` maintainer knows the new artifact exists:

```python
    # Dashboard data artifacts: capability-matrix.json (with-skill scores) and
    # lift-matrix.json (per-model with-minus-without). skills.html on gh-pages
    # renders both; rendering changes live on the gh-pages branch, not here.
```

- [ ] **Step 3: Ensure CI uploads the lift matrix.** In `.github/workflows/evals.yml`, the `skill-evals` job uploads eval results. Find the upload/store step for `capability-matrix.json` and confirm `lift-matrix.json` is included in the uploaded path (add it to the path list if the upload enumerates files). If the step uploads the whole `evals/results/` dir, no change is needed — add a one-line comment noting `lift-matrix.json` is now produced.

- [ ] **Step 4: Validate.** `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/evals.yml')); print('YAML OK')"` → `YAML OK`. `uv run ruff check evals/serve_dashboard.py` → clean.

- [ ] **Step 5: Commit**
```bash
git -C "<worktree>" add evals/serve_dashboard.py .github/workflows/evals.yml
git -C "<worktree>" commit -m "feat(evals): publish lift-matrix.json alongside the capability matrix"
```

---

### Task 13: Smoke run + final verification (needs an API key)

**Files:** none (verification).

- [ ] **Step 1: Free full-suite check.** `cd "<worktree>" && uv run pytest evals/ -v -m "not slow"` → all pass; `uv run ruff check evals/` → clean. Confirms the whole harness wires up with no LLM calls.

- [ ] **Step 2: Cheapest real run (requires `ANTHROPIC_API_KEY` in env).** Run one skill, one model, one trial:
```bash
cd "<worktree>" && uv run python evals/run_evals.py --skill building --model anthropic:claude-haiku-4-5 --trials 1
```
Expected: prints `... building: with=<x> without=<y> lift=<±z>` and writes `evals/results/capability-matrix.json` + `lift-matrix.json`. Confirm both files exist and parse.

- [ ] **Step 3: Sanity the result.** With-skill score should be ≥ baseline for `building` (the skill teaches the right API). If lift is strongly negative, capture the emitted artifacts/oracle details and report — that's a real finding (either the skill or the task needs work), not a reason to weaken the oracle.

- [ ] **Step 4: Commit any results artifacts intended to seed the dashboard** (only if the repo tracks `evals/results/` — check `git status`; if results are git-ignored, skip). Otherwise no commit; the populated numbers come from CI.

---

## Self-review

**Spec coverage:**
- Executor (one-shot, with/without arms) → Task 6. ✓
- Oracle grading core (execute / numeric / ground-truth / accessor) → Tasks 2–5. ✓
- Comparator (per-model lift, never pooled) → Task 7. ✓
- Per-skill grading map for all 7 → Task 8 registry (`SKILL_ORACLE`) + datasets Tasks 9–10. ✓
- Fixtures → Task 8 `_build.py`. ✓
- Delete self-report (`result_types.py`, self-report `evaluators.py`) → Task 11. ✓
- Dashboard shows lift → Task 12 produces `lift-matrix.json` + loads it into the preview; the gh-pages `skills.html` render is explicitly a follow-on (the page is hand-maintained on gh-pages). ✓ (with the documented caveat)
- Lives in core, reuse CI wiring → Tasks 11–12. ✓
- Harness self-tested without an LLM → Tasks 1–10 all use canned artifacts; Task 11 structural test is free; only Task 13 needs a key. ✓
- Tiered seam (agentic later) → Executor returns text via a single `make_agent`; oracles take `(artifact, case, workdir)` so an agentic executor drops in unchanged. Noted in `accessor.py` docstring + executor. ✓
- v1 informational, no gate → no CI pass/fail added; evals stay informational. ✓

**Placeholder scan:** none — every step has concrete code/commands. The one intentional flag: Task 6 Step 4 says "if the SKILL.md H1 differs, use the actual heading" (a verification instruction, the H1 `# Building Gaspatchio Models` is from the current file). Task 9 Step 7 honestly states the test fails until Task 10 completes the other datasets (sequenced, not a placeholder).

**Type/name consistency:** `OracleResult(score, detail)` is used uniformly across all oracles and the registry. Oracle signature `(artifact: str, case: dict, workdir: Path) -> OracleResult` matches the registry adapter and `run_evals._score_arm`'s `grade(artifact, case, workdir)` call. `make_agent(skill, model, *, with_skill)` (Task 6) matches its call in `run_evals._score_arm` (Task 11). `build_system_prompt(skill, *, with_skill)` consistent. `lift(with_scores, without_scores)` (Task 7) matches its call in `run_evals.main`. `SKILL_DIRS` (Task 6) reused as the skill list in `run_evals` + `test_evals`. `oracle_for(skill)` (Task 8) used in `run_evals` + `test_evals`. Datasets use `prompt` + ground-truth keys (`fixture_data`/`expected_columns`/`reference`/`reconcile_columns`/`tolerance`/`planted_defects`/`forbidden_terms`/`expected_level`) consumed exactly by the matching oracle.
