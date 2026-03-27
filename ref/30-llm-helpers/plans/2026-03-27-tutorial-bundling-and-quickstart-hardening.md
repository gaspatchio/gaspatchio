# Tutorial Bundling & Quickstart Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bundle tutorial files inside the gaspatchio Python package, add a `gspio tutorial` CLI command, add expected output verification, and harden the quickstart skill so agents cannot improvise models.

**Architecture:** Move the canonical tutorial files from `tutorial/` (repo root) into `bindings/python/gaspatchio_core/tutorials/`. Add a `tutorial` subcommand group to the existing Typer CLI (`cli.py`). Add `expected_output.txt` to each tutorial's `base/` directory. Update the quickstart SKILL.md to use the CLI command and add anti-pattern guardrails.

**Tech Stack:** Python (Typer CLI), maturin (packaging), pytest (verification tests)

**Spec:** `ref/30-llm-helpers/specs/2026-03-27-tutorial-bundling-and-quickstart-hardening-design.md`

---

## File Structure

```
bindings/python/
├── gaspatchio_core/
│   ├── cli.py                          # MODIFY: add tutorial subcommand group
│   ├── tutorial_cli.py                 # CREATE: tutorial list/init/verify commands
│   └── tutorials/                      # CREATE: move tutorial content here
│       ├── __init__.py                 # CREATE: package marker + helper to get tutorials path
│       ├── level-1-hello-world/
│       │   └── base/
│       │       ├── model.py
│       │       └── expected_output.txt # CREATE
│       ├── level-2-assumptions/
│       │   ├── base/
│       │   │   ├── model.py
│       │   │   └── expected_output.txt # CREATE
│       │   └── steps/...
│       ├── level-3-mini-va/
│       │   ├── base/
│       │   │   ├── model.py
│       │   │   └── expected_output.txt # CREATE
│       │   └── steps/...
│       ├── level-4-lifelib/
│       │   ├── base/
│       │   │   ├── model.py
│       │   │   ├── assumptions/...
│       │   │   └── expected_output.txt # CREATE
│       │   └── ...
│       └── level-5-scenarios/
│           ├── base/
│           │   ├── model.py
│           │   ├── assumptions/...
│           │   └── expected_output.txt # CREATE
│           └── steps/...

tutorial/                               # REPLACE: symlink to bindings/python/gaspatchio_core/tutorials
tests/
├── skills/
│   └── test_tutorial_cli.py            # CREATE: tests for tutorial CLI commands
│   └── test_tutorial_outputs.py        # CREATE: CI test that verifies all tutorials match expected output
skills/
└── quickstart/
    └── SKILL.md                        # MODIFY: use gspio tutorial command, add anti-patterns
```

---

### Task 1: Move tutorials into the Python package

**Files:**
- Move: `tutorial/*` -> `bindings/python/gaspatchio_core/tutorials/`
- Create: `bindings/python/gaspatchio_core/tutorials/__init__.py`
- Replace: `tutorial/` with symlink

- [ ] **Step 1: Move the tutorial directory into the package**

```bash
cd ~/projects/gaspatchio/gaspatchio-core-skills-improvements
mv tutorial bindings/python/gaspatchio_core/tutorials
```

- [ ] **Step 2: Create `__init__.py` with helper function**

Create `bindings/python/gaspatchio_core/tutorials/__init__.py`:

```python
"""Bundled tutorial models for gaspatchio.

Provides tutorial files that ship with the package, so
`gspio tutorial init level-1` works regardless of install method.
"""

from pathlib import Path


def get_tutorials_dir() -> Path:
    """Return the path to the bundled tutorials directory."""
    return Path(__file__).parent
```

- [ ] **Step 3: Create symlink at repo root for developer convenience**

```bash
cd ~/projects/gaspatchio/gaspatchio-core-skills-improvements
ln -s bindings/python/gaspatchio_core/tutorials tutorial
```

- [ ] **Step 4: Verify the symlink works**

```bash
ls -la tutorial/
ls tutorial/level-1-hello-world/base/model.py
```

Expected: symlink resolves, model.py is accessible from both paths.

- [ ] **Step 5: Verify maturin still builds**

```bash
cd bindings/python && uv run maturin develop --uv 2>&1 | tail -5
```

Expected: build succeeds (maturin includes everything under `gaspatchio_core/` automatically).

- [ ] **Step 6: Verify tutorials are accessible from the installed package**

```bash
cd bindings/python && uv run python -c "
from gaspatchio_core.tutorials import get_tutorials_dir
d = get_tutorials_dir()
print(f'Tutorials dir: {d}')
print(f'Levels: {sorted([p.name for p in d.iterdir() if p.is_dir() and p.name.startswith(\"level\")])}}')
"
```

Expected: prints the tutorials directory and all 5 level names.

- [ ] **Step 7: Commit**

```bash
git add bindings/python/gaspatchio_core/tutorials/ tutorial
git commit -m "refactor: move tutorials into gaspatchio_core package for bundling"
```

---

### Task 2: Generate expected output files for all 5 tutorial levels

**Files:**
- Create: `bindings/python/gaspatchio_core/tutorials/level-1-hello-world/base/expected_output.txt`
- Create: `bindings/python/gaspatchio_core/tutorials/level-2-assumptions/base/expected_output.txt`
- Create: `bindings/python/gaspatchio_core/tutorials/level-3-mini-va/base/expected_output.txt`
- Create: `bindings/python/gaspatchio_core/tutorials/level-4-lifelib/base/expected_output.txt`
- Create: `bindings/python/gaspatchio_core/tutorials/level-5-scenarios/base/expected_output.txt`

- [ ] **Step 1: Run each tutorial model and capture its output**

Run each tutorial from `bindings/python/` (where the uv environment lives). Capture stdout only (not stderr/logging) to the expected output file.

For each level, run:

```bash
cd ~/projects/gaspatchio/gaspatchio-core-skills-improvements/bindings/python
uv run python -c "
import sys, os
os.chdir('gaspatchio_core/tutorials/level-1-hello-world/base')
exec(open('model.py').read())
" > gaspatchio_core/tutorials/level-1-hello-world/base/expected_output.txt
```

Repeat for levels 2-5, adjusting the path. For levels 4 and 5, the models may use `gspio run-model` or have different entry points -- check each model's `if __name__` block or run instructions.

**Important:** Some models may use relative paths to load assumption data. Run from the model's directory so relative paths resolve correctly. If `os.chdir` doesn't work cleanly, use:

```bash
cd gaspatchio_core/tutorials/level-1-hello-world/base && uv run python model.py > expected_output.txt 2>/dev/null
```

If a model requires `gspio run-model` rather than `python model.py`, use that instead and capture its stdout.

- [ ] **Step 2: Verify each expected_output.txt is non-empty and contains Polars table output**

```bash
for level in level-1-hello-world level-2-assumptions level-3-mini-va level-4-lifelib level-5-scenarios; do
    f="gaspatchio_core/tutorials/$level/base/expected_output.txt"
    if [ -s "$f" ]; then
        echo "OK: $f ($(wc -l < "$f") lines)"
    else
        echo "EMPTY: $f"
    fi
done
```

Expected: all 5 files exist and are non-empty.

- [ ] **Step 3: Commit**

```bash
git add gaspatchio_core/tutorials/*/base/expected_output.txt
git commit -m "feat: add expected output files for all 5 tutorial levels"
```

---

### Task 3: Write the tutorial CLI module

**Files:**
- Create: `bindings/python/gaspatchio_core/tutorial_cli.py`
- Test: `tests/skills/test_tutorial_cli.py`

- [ ] **Step 1: Write failing tests for the tutorial CLI**

Create `tests/skills/test_tutorial_cli.py`:

```python
# ruff: noqa: S101, ANN201, PLR2004, INP001
"""Tests for the gspio tutorial CLI commands."""

import subprocess
from pathlib import Path

import pytest

TUTORIALS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "bindings"
    / "python"
    / "gaspatchio_core"
    / "tutorials"
)


def run_gspio(*args: str) -> subprocess.CompletedProcess[str]:
    """Run gspio command and return result."""
    return subprocess.run(  # noqa: S603, S607
        ["uv", "run", "gspio", *args],
        capture_output=True,
        text=True,
        cwd=TUTORIALS_DIR.parent.parent,  # bindings/python/
    )


class TestTutorialList:
    """Tests for gspio tutorial list."""

    def test_list_shows_all_levels(self):
        result = run_gspio("tutorial", "list")
        assert result.returncode == 0
        for level in range(1, 6):
            assert f"level-{level}" in result.stdout

    def test_list_shows_descriptions(self):
        result = run_gspio("tutorial", "list")
        assert result.returncode == 0
        assert "Hello World" in result.stdout


class TestTutorialInit:
    """Tests for gspio tutorial init."""

    def test_init_copies_model_file(self, tmp_path: Path):
        result = run_gspio("tutorial", "init", "level-1", "--dest", str(tmp_path / "test-model"))
        assert result.returncode == 0
        assert (tmp_path / "test-model" / "model.py").exists()

    def test_init_copies_expected_output(self, tmp_path: Path):
        run_gspio("tutorial", "init", "level-1", "--dest", str(tmp_path / "test-model"))
        assert (tmp_path / "test-model" / "expected_output.txt").exists()

    def test_init_refuses_overwrite(self, tmp_path: Path):
        dest = tmp_path / "test-model"
        dest.mkdir()
        (dest / "model.py").write_text("existing")
        result = run_gspio("tutorial", "init", "level-1", "--dest", str(dest))
        assert result.returncode != 0
        assert "already exists" in result.stderr or "already exists" in result.stdout

    def test_init_accepts_short_name(self, tmp_path: Path):
        result = run_gspio("tutorial", "init", "1", "--dest", str(tmp_path / "test-model"))
        assert result.returncode == 0
        assert (tmp_path / "test-model" / "model.py").exists()

    def test_init_rejects_unknown_level(self, tmp_path: Path):
        result = run_gspio("tutorial", "init", "level-99", "--dest", str(tmp_path / "test-model"))
        assert result.returncode != 0


class TestTutorialVerify:
    """Tests for gspio tutorial verify."""

    def test_verify_level_1_passes(self):
        result = run_gspio("tutorial", "verify", "level-1")
        assert result.returncode == 0

    def test_verify_rejects_unknown_level(self):
        result = run_gspio("tutorial", "verify", "level-99")
        assert result.returncode != 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/projects/gaspatchio/gaspatchio-core-skills-improvements/bindings/python
uv run pytest ../../tests/skills/test_tutorial_cli.py -v 2>&1 | tail -20
```

Expected: all tests FAIL (tutorial subcommand doesn't exist yet).

- [ ] **Step 3: Write the tutorial CLI module**

Create `bindings/python/gaspatchio_core/tutorial_cli.py`:

```python
# ruff: noqa: T201, E501
"""CLI subcommands for managing gaspatchio tutorials.

Provides list, init, and verify commands so users can get started
with tutorials regardless of how gaspatchio was installed.
"""

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from .tutorials import get_tutorials_dir

console = Console()

tutorial_app = typer.Typer(
    name="tutorial",
    help="List, initialize, and verify gaspatchio tutorials.",
)

# Level metadata: (directory_name, short_description)
LEVELS: list[tuple[str, str]] = [
    ("level-1-hello-world", "Hello World — term life portfolio, column arithmetic, when/then"),
    ("level-2-assumptions", "Assumptions — mortality/lapse table lookups, multi-dimension tables"),
    ("level-3-mini-va", "Mini Variable Annuity — account values, guarantees, dynamic lapse"),
    ("level-4-lifelib", "Reconciled Lifelib — production model reconciled to 0.0000% vs lifelib"),
    ("level-5-scenarios", "Scenarios — parameter shocks, sensitivity analysis, stress testing"),
]


def _resolve_level(name: str) -> str:
    """Normalize a level name to its directory name.

    Accepts 'level-1', '1', 'level-1-hello-world', etc.

    Parameters
    ----------
    name : str
        User-provided level identifier.

    Returns
    -------
    str
        The canonical directory name (e.g. 'level-1-hello-world').

    Raises
    ------
    typer.BadParameter
        If the level name cannot be resolved to a known tutorial.

    """
    # Exact match
    for dir_name, _ in LEVELS:
        if name == dir_name:
            return dir_name

    # Short forms: 'level-1' or '1'
    stripped = name.removeprefix("level-")
    for dir_name, _ in LEVELS:
        if dir_name.startswith(f"level-{stripped}-"):
            return dir_name

    available = ", ".join(f"level-{i + 1}" for i in range(len(LEVELS)))
    msg = f"Unknown tutorial level: '{name}'. Available: {available}"
    raise typer.BadParameter(msg)


@tutorial_app.command()
def list() -> None:  # noqa: A001
    """List available tutorial levels."""
    tutorials_dir = get_tutorials_dir()
    table = Table(title="Gaspatchio Tutorials")
    table.add_column("Level", style="cyan")
    table.add_column("Description")
    table.add_column("Status")

    for dir_name, description in LEVELS:
        level_dir = tutorials_dir / dir_name / "base"
        status = "[green]ready[/green]" if level_dir.exists() else "[red]missing[/red]"
        short_name = dir_name.split("-")[0] + "-" + dir_name.split("-")[1]
        table.add_row(short_name, description, status)

    console.print(table)
    console.print("\n[bold]Get started:[/bold] gspio tutorial init level-1\n")


@tutorial_app.command()
def init(
    level: Annotated[str, typer.Argument(help="Tutorial level (e.g. 'level-1', '1', 'level-1-hello-world')")],
    dest: Annotated[
        Path,
        typer.Option("--dest", "-d", help="Destination directory"),
    ] = Path("my-first-model"),
    force: Annotated[bool, typer.Option("--force", "-f", help="Overwrite destination if it exists")] = False,
) -> None:
    """Copy a tutorial into your working directory."""
    dir_name = _resolve_level(level)
    tutorials_dir = get_tutorials_dir()
    source = tutorials_dir / dir_name / "base"

    if not source.exists():
        console.print(f"[red]Tutorial source not found: {source}[/red]")
        raise typer.Exit(code=1)

    dest_resolved = dest.resolve()

    if dest_resolved.exists() and not force:
        console.print(f"[red]Destination already exists: {dest_resolved}[/red]")
        console.print("Use --force to overwrite.")
        raise typer.Exit(code=1)

    if dest_resolved.exists() and force:
        shutil.rmtree(dest_resolved)

    shutil.copytree(source, dest_resolved)
    console.print(f"[green]Tutorial copied to: {dest_resolved}[/green]\n")
    console.print("[bold]Next steps:[/bold]")
    console.print(f"  cd {dest}")
    console.print("  uv run python model.py\n")


@tutorial_app.command()
def verify(
    level: Annotated[str, typer.Argument(help="Tutorial level to verify")],
) -> None:
    """Run a tutorial model and verify its output matches expected."""
    dir_name = _resolve_level(level)
    tutorials_dir = get_tutorials_dir()
    base_dir = tutorials_dir / dir_name / "base"

    expected_file = base_dir / "expected_output.txt"
    if not expected_file.exists():
        console.print(f"[red]No expected_output.txt found for {dir_name}[/red]")
        raise typer.Exit(code=1)

    model_file = base_dir / "model.py"
    if not model_file.exists():
        console.print(f"[red]No model.py found for {dir_name}[/red]")
        raise typer.Exit(code=1)

    expected = expected_file.read_text().strip()

    result = subprocess.run(  # noqa: S603
        [sys.executable, str(model_file)],
        capture_output=True,
        text=True,
        cwd=str(base_dir),
    )

    if result.returncode != 0:
        console.print(f"[red]Model failed to run:[/red]\n{result.stderr}")
        raise typer.Exit(code=1)

    actual = result.stdout.strip()

    if actual == expected:
        console.print(f"[green]PASS: {dir_name} output matches expected[/green]")
        raise typer.Exit(code=0)

    console.print(f"[red]FAIL: {dir_name} output does not match expected[/red]\n")
    console.print("[bold]Expected:[/bold]")
    console.print(expected)
    console.print("\n[bold]Actual:[/bold]")
    console.print(actual)
    raise typer.Exit(code=1)
```

- [ ] **Step 4: Register the tutorial subcommand in cli.py**

In `bindings/python/gaspatchio_core/cli.py`, add the import and registration. Add near the other imports at the top of the file:

```python
from .tutorial_cli import tutorial_app
```

Add after the `app = typer.Typer(...)` definition (after line ~74):

```python
app.add_typer(tutorial_app, name="tutorial")
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd ~/projects/gaspatchio/gaspatchio-core-skills-improvements/bindings/python
uv run pytest ../../tests/skills/test_tutorial_cli.py -v 2>&1
```

Expected: all tests PASS.

- [ ] **Step 6: Manual smoke test**

```bash
cd ~/projects/gaspatchio/gaspatchio-core-skills-improvements/bindings/python
uv run gspio tutorial list
uv run gspio tutorial init level-1 --dest /tmp/test-tutorial-init
cd /tmp/test-tutorial-init && uv run python model.py
cd ~/projects/gaspatchio/gaspatchio-core-skills-improvements/bindings/python
uv run gspio tutorial verify level-1
rm -rf /tmp/test-tutorial-init
```

Expected: list shows 5 levels, init copies files, model runs, verify passes.

- [ ] **Step 7: Commit**

```bash
git add bindings/python/gaspatchio_core/tutorial_cli.py tests/skills/test_tutorial_cli.py
git add bindings/python/gaspatchio_core/cli.py
git commit -m "feat: add gspio tutorial list/init/verify CLI commands"
```

---

### Task 4: Add CI test for tutorial output verification

**Files:**
- Create: `tests/skills/test_tutorial_outputs.py`

- [ ] **Step 1: Write the CI test**

Create `tests/skills/test_tutorial_outputs.py`:

```python
# ruff: noqa: S101, ANN201, S603, S607, INP001
"""CI test: verify all tutorial models produce expected output.

Catches API changes that silently break tutorial examples.
Runs each tutorial's model.py and diffs stdout against expected_output.txt.
"""

import subprocess
import sys
from pathlib import Path

import pytest

TUTORIALS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "bindings"
    / "python"
    / "gaspatchio_core"
    / "tutorials"
)

LEVELS = [
    "level-1-hello-world",
    "level-2-assumptions",
    "level-3-mini-va",
    "level-4-lifelib",
    "level-5-scenarios",
]


@pytest.mark.parametrize("level", LEVELS)
def test_tutorial_output_matches_expected(level: str):
    """Tutorial model output matches expected_output.txt."""
    base_dir = TUTORIALS_DIR / level / "base"
    model_file = base_dir / "model.py"
    expected_file = base_dir / "expected_output.txt"

    if not model_file.exists():
        pytest.skip(f"No model.py for {level}")
    if not expected_file.exists():
        pytest.skip(f"No expected_output.txt for {level}")

    result = subprocess.run(
        [sys.executable, str(model_file)],
        capture_output=True,
        text=True,
        cwd=str(base_dir),
    )

    assert result.returncode == 0, f"{level} model failed:\n{result.stderr}"

    expected = expected_file.read_text().strip()
    actual = result.stdout.strip()

    assert actual == expected, (
        f"{level} output mismatch.\n\n"
        f"--- Expected ---\n{expected}\n\n"
        f"--- Actual ---\n{actual}"
    )
```

- [ ] **Step 2: Run the test**

```bash
cd ~/projects/gaspatchio/gaspatchio-core-skills-improvements/bindings/python
uv run pytest ../../tests/skills/test_tutorial_outputs.py -v 2>&1
```

Expected: all 5 levels PASS (assuming expected_output.txt files were created correctly in Task 2).

- [ ] **Step 3: Commit**

```bash
git add tests/skills/test_tutorial_outputs.py
git commit -m "test: add CI verification that tutorial outputs match expected"
```

---

### Task 5: Harden the quickstart SKILL.md

**Files:**
- Modify: `skills/quickstart/SKILL.md`

- [ ] **Step 1: Update Step 4 to use the CLI command**

Replace the current Step 4 in `skills/quickstart/SKILL.md`. The current Step 4 (lines ~91-111) says "Copy the selected tutorial base" using `cp -r tutorial/...`.

Replace with:

```markdown
## Step 4 — Initialize and Run

1. Initialize the tutorial into the user's working directory:

```bash
uv run gspio tutorial init <level> --dest ./my-first-model
```

Replace `<level>` with the level chosen in Step 3 (e.g. `level-1`, `level-2`).

If `gspio tutorial init` fails:
- Run `uv run gspio tutorial list` to verify tutorials are available.
- If tutorials are missing, the package may be installed from source without tutorial data. Ask the user to reinstall from a wheel or PyPI.
- Do NOT fall back to writing model code. This skill does not write code.

2. Run the model:

```bash
cd my-first-model
uv run python model.py
```

3. Verify the output matches expected:

```bash
uv run gspio tutorial verify <level>
```

If verification passes, explain the output to the user (proceed to Step 5).
If verification fails, investigate the diff — do NOT claim success.
```

- [ ] **Step 2: Add the anti-patterns section**

Add this new section after "Step 2 — Inspect User Data" and before "Step 3 — Route to Tutorial Level":

```markdown
## NEVER Do This

This skill initializes and runs existing tutorials. It does NOT write model code.

If you catch yourself doing any of the following, STOP and re-read this skill:

- **NEVER write a model from scratch.** Use `gspio tutorial init` to get a working model. The tutorials exist and are tested.
- **NEVER import internal functions** like `list_conditional`, `accumulate`, or anything from `gaspatchio_core.functions.vector`. These are internal implementation details.
- **NEVER use raw Polars patterns** like `af.with_columns(pl.col(...))`. The gaspatchio API uses `af.column_name = expression`.
- **NEVER build projection timelines manually** with `[[i for i in range(n)]] * rows`. Use `af.date.create_projection_timeline()`.
- **NEVER skip `gspio tutorial init`** and improvise. If the command fails, diagnose why — do not fall back to writing code.
- **NEVER claim "tutorial files aren't shipped with the package."** They are. If they're missing, the installation is broken.
```

- [ ] **Step 3: Update the Completion Gate**

Replace the current Completion Gate at the end of the skill with:

```markdown
## Completion Gate

This skill is complete when ALL of the following are true:

1. `gspio tutorial init` succeeded — tutorial files are in the user's directory
2. `uv run python model.py` produced output without errors
3. `gspio tutorial verify <level>` confirms output matches expected
4. The user has been walked through what each output section means

If verification fails, investigate the mismatch. Do NOT claim success without a passing verify.
```

- [ ] **Step 4: Run the skill structure tests to ensure SKILL.md is still valid**

```bash
cd ~/projects/gaspatchio/gaspatchio-core-skills-improvements/bindings/python
uv run pytest ../../tests/skills/test_skill_structure.py -v -k quickstart 2>&1
```

Expected: all quickstart-related structural tests PASS (frontmatter, standalone mention, completion gate).

- [ ] **Step 5: Commit**

```bash
git add skills/quickstart/SKILL.md
git commit -m "fix(skill): harden quickstart to use gspio tutorial, add anti-patterns"
```

---

### Task 6: Update ruff per-file-ignores for tutorials

**Files:**
- Modify: `bindings/python/pyproject.toml`

Tutorial model files use `print()` and have standalone scripts — they need relaxed linting.

- [ ] **Step 1: Add tutorial ignore rules**

In `bindings/python/pyproject.toml`, add to the `[tool.ruff.lint.per-file-ignores]` section:

```toml
"gaspatchio_core/tutorials/**/*.py" = [
    "INP001",  # tutorials are standalone scripts, not part of a namespace package
    "T201",    # print() is expected in tutorial output
    "S101",    # asserts OK in tutorial code
    "ANN201",  # tutorial functions don't need return annotations
    "PLR2004", # magic values OK in tutorials
    "D100",    # module docstrings optional for tutorial steps
    "D103",    # function docstrings optional for tutorial steps
]
```

- [ ] **Step 2: Verify ruff passes on tutorials**

```bash
cd ~/projects/gaspatchio/gaspatchio-core-skills-improvements/bindings/python
uv run ruff check gaspatchio_core/tutorials/ 2>&1 | tail -10
```

Expected: no errors (or only pre-existing issues unrelated to this change).

- [ ] **Step 3: Commit**

```bash
git add bindings/python/pyproject.toml
git commit -m "chore: add ruff per-file-ignores for bundled tutorial scripts"
```

---

### Task 7: Final integration test

- [ ] **Step 1: Run all tests together**

```bash
cd ~/projects/gaspatchio/gaspatchio-core-skills-improvements/bindings/python
uv run pytest ../../tests/skills/ -v 2>&1
```

Expected: all tests pass — skill structure tests, tutorial CLI tests, tutorial output verification tests.

- [ ] **Step 2: End-to-end smoke test of the full quickstart flow**

```bash
cd ~/projects/gaspatchio/gaspatchio-core-skills-improvements/bindings/python
uv run gspio tutorial list
uv run gspio tutorial init level-1 --dest /tmp/e2e-quickstart-test
cd /tmp/e2e-quickstart-test && uv run python model.py
cd ~/projects/gaspatchio/gaspatchio-core-skills-improvements/bindings/python
uv run gspio tutorial verify level-1
rm -rf /tmp/e2e-quickstart-test
```

Expected: full flow works end-to-end.

- [ ] **Step 3: Verify tutorials are still accessible via the repo-root symlink**

```bash
cd ~/projects/gaspatchio/gaspatchio-core-skills-improvements
ls tutorial/level-1-hello-world/base/model.py
ls tutorial/README.md
```

Expected: symlink works, existing developer paths still resolve.
