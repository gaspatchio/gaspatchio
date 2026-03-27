# Tutorial Bundling & Quickstart Hardening

**Date:** 2026-03-27
**Status:** Draft
**Branch:** skills-improvements

## Problem

The quickstart skill tells agents to copy tutorial files from the repo's `tutorial/` directory. When the user installs gaspatchio via `uv pip install` + `npx skills add` (no repo clone), the tutorial files don't exist. In a real test with Cursor, the agent:

1. Correctly identified the tutorials were missing
2. Improvised a model from scratch using raw Polars instead of the gaspatchio API
3. Produced code that violated every API pattern (no `main()`, no `when()`, internal `list_conditional()`, manual timeline construction)
4. Hit `map_elements` warnings and iterated through failures

The model "worked" but was unauditable, non-idiomatic, and taught the actuary nothing about gaspatchio.

**Transcript:** `ref/30-llm-helpers/transcripts/cursor_getting_started_with_gaspatchio.md`
**Broken model:** `ref/30-llm-helpers/transcripts/model.py`

## Design

### 1. Bundle tutorials in the Python package

Move the entire `tutorial/` tree into the Python package so it ships with every install method (PyPI, wheel, source).

**Location:** `gaspatchio_core/tutorials/`

**What gets bundled:**
- All 5 levels (level-1 through level-5)
- Both `base/` and `steps/` directories
- All data files (parquet, csv)
- Total size: ~3.5MB

**Maturin config:** Add `tutorial/` to the package data via `[tool.maturin]` include patterns or by placing the content inside the `gaspatchio_core` package directory.

**The repo `tutorial/` directory remains** as the development source. A symlink or copy step in the build ensures the package always has the latest tutorials. The simplest approach: move the canonical tutorial files into `gaspatchio_core/tutorials/` and symlink `tutorial/` at the repo root back to it for developer convenience.

### 2. Add expected output files

Each tutorial level's `base/` directory gets an `expected_output.txt` file containing the exact stdout produced by running the model.

**Format:** Plain text, the raw terminal output from `uv run python model.py`.

**Files to create:**
- `level-1-hello-world/base/expected_output.txt`
- `level-2-assumptions/base/expected_output.txt`
- `level-3-mini-va/base/expected_output.txt`
- `level-4-lifelib/base/expected_output.txt`
- `level-5-scenarios/base/expected_output.txt`

**CI integration:** A test that runs each tutorial model and diffs stdout against `expected_output.txt`. Fails if they diverge (catches API changes that silently break tutorials).

### 3. Add `gspio tutorial` CLI command

A new subcommand on the `gspio` CLI.

**Usage:**
```bash
# List available tutorials
gspio tutorial list

# Copy a tutorial to the current directory
gspio tutorial init level-1

# Copy to a specific destination
gspio tutorial init level-1 --dest ./my-first-model

# Run a tutorial's model and verify output matches expected
gspio tutorial verify level-1
```

**Subcommands:**

- **`list`** — Print a table of available levels with name and one-line description. Source: read from the tutorials directory, each level has a README or the model's module docstring.

- **`init <level>`** — Copy the tutorial's `base/` directory (model + data + expected output) into the destination. Refuses to overwrite if destination exists (use `--force` to override). Prints next-step instructions after copying.

- **`verify <level>`** — Run the tutorial model in a temp directory and diff stdout against `expected_output.txt`. Exit 0 if match, exit 1 with diff if mismatch. Useful for CI and for agents to confirm a model runs correctly.

**Level naming:** Accept `level-1`, `1`, `level-1-hello-world` — normalize to the directory name.

### 4. Update quickstart SKILL.md

Replace the current Step 4 ("Copy the selected tutorial base") with a call to the CLI command:

```markdown
## Step 4 — Initialize and Run

1. Initialize the tutorial:
   ```bash
   uv run gspio tutorial init <level> --dest ./my-first-model
   ```

2. Run the model:
   ```bash
   cd my-first-model
   uv run python model.py
   ```

3. Verify the output matches expected:
   ```bash
   uv run gspio tutorial verify <level>
   ```
```

**Add an anti-patterns section** to the skill:

```markdown
## NEVER Do This

This skill copies and runs existing tutorial code. It does NOT write model code.

- NEVER write a model from scratch if the tutorial files are available
- NEVER import `list_conditional`, `accumulate`, or other internal functions
- NEVER use `af.with_columns(pl.col(...))` — use `af.column_name = expression`
- NEVER build projection timelines manually — use `af.date.create_projection_timeline()`
- NEVER skip `gspio tutorial init` and improvise — the tutorials exist for a reason

If `gspio tutorial init` fails, diagnose why. Do NOT fall back to writing code.
```

**Add a verification gate** after running the model:

```markdown
## Completion Gate

This skill is complete when:
1. `gspio tutorial init` succeeded (tutorial files are in the user's directory)
2. `uv run python model.py` produced output
3. `gspio tutorial verify` confirms output matches expected (or user has modified the model intentionally)

If verification fails, investigate — do NOT claim success.
```

### 5. Package size consideration

The tutorial data files (mostly parquet) add ~3.5MB to the wheel. This is acceptable for an actuarial framework where users expect data files. For context, polars itself is ~30MB.

If size becomes a concern later, a `gaspatchio[tutorials]` optional extra could gate the data files, but this adds install friction. Recommend shipping them unconditionally for now.

## Out of Scope

- Rewriting tutorial content (tutorials are already validated)
- Bundling skills in the Python package (skills are distributed via `npx skills add`)
- Changes to other skills beyond quickstart
- MCP server or other Phase 4 work

## Success Criteria

1. `uv pip install gaspatchio && uv run gspio tutorial list` shows all 5 levels
2. `uv run gspio tutorial init level-1 --dest ./test && cd test && uv run python model.py` produces correct output
3. `uv run gspio tutorial verify level-1` exits 0
4. An agent with the quickstart skill can run through the full flow without improvising code
5. CI test validates all 5 tutorials produce expected output
