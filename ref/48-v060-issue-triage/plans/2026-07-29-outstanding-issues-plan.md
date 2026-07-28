# v0.6.0 Outstanding-Issue Batch — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the eight outstanding issues triaged in
`ref/48-v060-issue-triage/specs/2026-07-27-outstanding-issues-design.md` and ship them as
v0.6.0 alongside the already-merged #21–#30.

**Architecture:** Five independent pull requests, ordered so that PRs 1–2 correct the
foundations (documented examples, the lookup error path) that PRs 3–5 build on. No shared
state between PRs; each is independently reviewable, testable, and mergeable. Every fix ships
a regression test pinning the *exact* reported symptom string, not a paraphrase.

**Tech Stack:** Python 3.12+ (PyO3 bindings, Polars 1.42.1), Rust (`gaspatchio_core_lib`,
maturin), pytest, uv.

## Global Constraints

- **Working directory for every Python command is `bindings/python`.** There is no Python
  project at the repository root.
- **Install with `uv sync --locked`.** `bindings/python/uv.lock` is tracked. To move a
  dependency, run `uv lock` and commit the result in the same PR.
- **Rust changes require a rebuild before Python tests see them:** `maturin build -uv` from
  `bindings/python`, or `uv run --reinstall`.
- **`AGENTS.md` is generated into `.github/copilot-instructions.md`.** After *any* AGENTS.md
  edit run `uv run --no-project --python 3.13 python ../../scripts/gen_skill_manifests.py`.
  CI enforces this via `--check`; `tests/skills/` (125 tests) guards it.
- **Commits are signed** (`commit.gpgsign=true`, SSH). Conventional commit format. Reference
  the issue number. **Never** add an AI-assistant signature or `Co-Authored-By` trailer.
- **Ruff runs `select = ["ALL"]`** and the on-save hook strips unused imports — add an import
  and its first use in the same edit.
- **Baseline suite:** 2,644 passed, 8 skipped, 5 xfailed, 1 xpassed. Must stay green.
- **Every new test file** starts with the SPDX header used across `bindings/python/tests/`:
  ```python
  # SPDX-FileCopyrightText: 2026 Opio Inc.
  #
  # SPDX-License-Identifier: Apache-2.0
  ```

---

# PR 1 — Papercuts (#38, #35, #40, #42)

Four unrelated small fixes. Grouped because none needs design discussion and all four are
reviewable at a glance. Land first: Task 2 corrects examples that Tasks 6–7 depend on.

---

### Task 1: Unary negation on list columns (#38)

`-af.some_list_column` raises `InvalidOperationError: neg operation not supported for dtype
list[f64]`, while `0.0 - col` and `col * -1.0` both work. Both proxies define the full
arithmetic dunder set but omit `__neg__`, so Python falls through to Polars' native `neg`,
which has no list kernel. The fix routes negation through the same dispatch method the other
operators use, which already handles list shimming.

**Files:**
- Modify: `bindings/python/gaspatchio_core/column/expression_proxy.py` (after `__pow__`, ~line 140)
- Modify: `bindings/python/gaspatchio_core/column/column_proxy.py` (after `__pow__`, ~line 162)
- Test: `bindings/python/tests/column/test_unary_negation.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `ExpressionProxy.__neg__(self) -> ExpressionProxy` and
  `ColumnProxy.__neg__(self) -> ExpressionProxy`.

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/column/test_unary_negation.py`:

```python
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Unary negation on scalar and list columns.

Regression test for the missing ``__neg__`` overload: ``-col`` raised
``InvalidOperationError: neg operation not supported for dtype list[f64]``
while the equivalent ``0.0 - col`` and ``col * -1.0`` both worked.
"""

import polars as pl

from gaspatchio_core import ActuarialFrame, when


def _frame() -> ActuarialFrame:
    return ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "scalar_col": [1.5, -2.5],
                "list_col": [[1.0, -2.0, 3.0], [4.0, 5.0, -6.0]],
            }
        )
    )


def test_negation_on_list_column_matches_zero_minus():
    af = _frame()
    af.negated = -af.list_col
    af.reference = 0.0 - af.list_col
    out = af.collect()
    assert out["negated"].to_list() == out["reference"].to_list()
    assert out["negated"].to_list() == [[-1.0, 2.0, -3.0], [-4.0, -5.0, 6.0]]


def test_negation_on_scalar_column_matches_zero_minus():
    af = _frame()
    af.negated = -af.scalar_col
    out = af.collect()
    assert out["negated"].to_list() == [-1.5, 2.5]


def test_negation_inside_when_then_otherwise():
    af = _frame()
    af.result = when(af.list_col > 0.0).then(-af.list_col).otherwise(0.0)
    out = af.collect()
    assert out["result"].to_list() == [[-1.0, 0.0, -3.0], [-4.0, -5.0, 0.0]]
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd bindings/python && uv run --frozen pytest tests/column/test_unary_negation.py -v
```

Expected: FAIL with `InvalidOperationError: neg operation not supported for dtype list[f64]`.

- [ ] **Step 3: Add `__neg__` to `ExpressionProxy`**

In `bindings/python/gaspatchio_core/column/expression_proxy.py`, immediately after
`__pow__`:

```python
    def __neg__(self) -> ExpressionProxy:
        """Unary negation operator."""
        # Multiply by -1 rather than delegating to Polars' `neg`, which has no
        # list kernel; `mul` goes through the dispatch system that handles list
        # column shimming.
        return self.mul(-1.0)
```

- [ ] **Step 4: Add `__neg__` to `ColumnProxy`**

In `bindings/python/gaspatchio_core/column/column_proxy.py`, immediately after `__pow__`:

```python
    def __neg__(self) -> ExpressionProxy:
        """Unary negation operator."""
        # Multiply by -1 rather than delegating to Polars' `neg`, which has no
        # list kernel; `mul` goes through the dispatch system that handles list
        # column shimming.
        return self.mul(-1.0)
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
cd bindings/python && uv run --frozen pytest tests/column/test_unary_negation.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Update the type stubs**

Add to both `bindings/python/gaspatchio_core/column/expression_proxy.pyi` and
`column_proxy.pyi` if those stub files exist (check with `ls
gaspatchio_core/column/*.pyi`); if they do, add `def __neg__(self) -> ExpressionProxy: ...`
alongside the other dunders. Then verify:

```bash
cd bindings/python && uv run --frozen python -m mypy.stubtest gaspatchio_core \
  --ignore-missing-stub --ignore-unused-allowlist \
  --mypy-config-file mypy-stubtest.ini --allowlist stubtest-allowlist.txt
```

Expected: no new errors.

- [ ] **Step 7: Commit**

```bash
git add bindings/python/gaspatchio_core/column/ bindings/python/tests/column/test_unary_negation.py
git commit -m "fix(column): support unary negation on list columns (#38)"
```

---

### Task 2: Correct the stale projection API in the docs (#35)

`af.date.create_projection_timeline(...)` no longer exists — zero hits in
`gaspatchio_core/`. The current API is `af.projection.set(...)` and **the parameter names
differ too**, so there are two stale places in AGENTS.md, not one. Because AGENTS.md is
auto-loaded by every agent session, a rotted example makes every downstream session start
from a false premise.

Correcting the prose fixes today and drifts again next release, so this task also makes the
quickstart example executable.

**Files:**
- Modify: `AGENTS.md` (the "Model Structure: Three Phases" code block; the Gotcha #2 row)
- Modify: `.github/copilot-instructions.md` (generated — do not hand-edit)
- Test: `bindings/python/tests/examples/test_agents_md_quickstart.py` (create)

**Interfaces:**
- Consumes: `ActuarialFrame.projection.set(...)` — verified signature:
  `set(*, schedule=None, valuation_date=None, until=None, until_value=None,
  issue_age_column="issue_age", inception_column="policy_inception", start_date=None,
  n_periods=None, frequency=None, per_policy=None) -> ActuarialFrame`
  (`bindings/python/gaspatchio_core/accessors/projection_frame.py:86`).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/examples/test_agents_md_quickstart.py`:

```python
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The AGENTS.md quickstart must actually run.

AGENTS.md is auto-loaded by every agent session, so a rotted example makes
every downstream session start from a false premise. #35 was exactly that:
the quickstart called ``af.date.create_projection_timeline(...)``, removed
some releases ago. This test executes the documented shape end to end so the
example cannot silently rot again.
"""

import datetime

import polars as pl

from gaspatchio_core import ActuarialFrame


def test_quickstart_projection_setup_runs():
    mp = pl.DataFrame(
        {
            "policy_id": [1, 2],
            "issue_age": [40, 55],
            "policy_inception": [
                datetime.date(2020, 1, 1),
                datetime.date(2021, 6, 1),
            ],
        }
    )
    af = ActuarialFrame(mp)

    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="maximum_age",
        until_value=100,
        frequency="monthly",
    )

    out = af.collect()
    assert out.height == 2
```

- [ ] **Step 2: Run the test to verify it passes or fails**

```bash
cd bindings/python && uv run --frozen pytest tests/examples/test_agents_md_quickstart.py -v
```

If it FAILS, the corrected signature in this plan is wrong — stop and read
`gaspatchio_core/accessors/projection_frame.py:86` before continuing. If it PASSES, the
signature is confirmed and the docs below are the only thing broken.

- [ ] **Step 3: Fix the "Model Structure: Three Phases" block in AGENTS.md**

Replace:

```python
    af = af.date.create_projection_timeline(
        valuation_date=datetime.date(2025, 1, 1),
        projection_end_type="maximum_age",
        projection_end_value=100,   # NOT 99
        projection_frequency="monthly",
    )
```

with:

```python
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="maximum_age",
        until_value=100,   # NOT 99
        frequency="monthly",
    )
```

- [ ] **Step 4: Fix Gotcha #2 in AGENTS.md**

In the "Top Gotchas" table, change the row reading `` `projection_end_value=99` `` to
`` `until_value=99` ``. The advice (use 100, off-by-one is catastrophic, ~3% BEL gap) is
unchanged — only the parameter name was stale.

- [ ] **Step 5: Sweep the skills directory for the same stale call**

```bash
grep -rn "create_projection_timeline\|projection_end_type\|projection_end_value\|projection_frequency" \
  skills/ tutorial/ bindings/python/gaspatchio_core/tutorials/ 2>/dev/null
```

Fix every hit using the same mapping: `projection_end_type` → `until`,
`projection_end_value` → `until_value`, `projection_frequency` → `frequency`,
`af.date.create_projection_timeline` → `af.projection.set`.

- [ ] **Step 6: Regenerate the Copilot instructions**

```bash
cd /path/to/repo && uv run --no-project --python 3.13 python scripts/gen_skill_manifests.py
uv run --no-project --python 3.13 python scripts/gen_skill_manifests.py --check
```

Expected: `--check` exits 0.

- [ ] **Step 7: Run the skill guard tests**

```bash
cd bindings/python && uv run --frozen pytest ../../tests/skills/ -q
```

Expected: 125 passed.

- [ ] **Step 8: Commit**

```bash
git add AGENTS.md .github/copilot-instructions.md skills/ \
  bindings/python/tests/examples/test_agents_md_quickstart.py
git commit -m "docs: correct the removed projection API in the quickstart (#35)"
```

---

### Task 3: `gspio describe` on parquet files with list columns (#40)

`gspio describe` on a file containing a `list<f64>` column fails with `Unsupported key type
for array storage: List(Float64)` — it treats every file as a candidate assumption table.
Describing a model's own run output is the reflex the CLI's own agent workflow instructs
("always use `--output-file`, then read the parquet"), so the documented happy path is what
breaks.

**Files:**
- Modify: `bindings/python/gaspatchio_core/cli.py:708` (the `describe` command)
- Test: `bindings/python/tests/api/test_cli_describe_list_columns.py` (create)

**Interfaces:**
- Consumes: `_analyze_table_shape(df)` and `_detect_table_structure(df)` in `cli.py`.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/api/test_cli_describe_list_columns.py`:

```python
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""`gspio describe` must handle a model's own output.

Regression test for #40: describing a parquet containing a ``list<f64>``
column failed with "Unsupported key type for array storage: List(Float64)"
because describe tried to register every file as an assumption table.
Reading back a run's own output is the documented agent workflow, so this is
the path that mattered most.
"""

import json

import polars as pl
from typer.testing import CliRunner

from gaspatchio_core.cli import app

runner = CliRunner()


def _write_projection_output(tmp_path):
    path = tmp_path / "results.parquet"
    pl.DataFrame(
        {
            "policy_id": [1, 2],
            "sum_assured": [100_000.0, 250_000.0],
            "net_cf": [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
        }
    ).write_parquet(path)
    return path


def test_describe_survives_list_columns(tmp_path):
    path = _write_projection_output(tmp_path)
    result = runner.invoke(app, ["describe", str(path)])
    assert result.exit_code == 0, result.output
    assert "net_cf" in result.output
    assert "Unsupported key type" not in result.output


def test_describe_json_survives_list_columns(tmp_path):
    path = _write_projection_output(tmp_path)
    result = runner.invoke(app, ["describe", str(path), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)
```

- [ ] **Step 2: Run the test to locate the exact failure**

```bash
cd bindings/python && uv run --frozen pytest tests/api/test_cli_describe_list_columns.py -v
```

Expected: FAIL. **Read the traceback and record which call raises** — it is one of
`_analyze_table_shape`, `_detect_table_structure`, or `analyze_table`. The fix goes at that
call site. Do not guess; the traceback names it.

- [ ] **Step 3: Guard the assumption-table analysis behind a list-column check**

In `cli.py`'s `describe`, immediately after the dataframe is read and before
`_analyze_table_shape(df)` is called, partition the columns:

```python
        # A file containing list columns is a projection output, not an
        # assumption table: assumption-table storage cannot key on List dtypes.
        # Summarise those columns directly instead of routing them through
        # table-structure detection (#40).
        list_columns = [
            name for name, dtype in df.schema.items() if isinstance(dtype, pl.List)
        ]
        scalar_df = df.drop(list_columns) if list_columns else df
```

Then pass `scalar_df` — not `df` — into `_analyze_table_shape` and
`_detect_table_structure`, and render the list columns separately with name, dtype, inner
dtype, min/max list length, and a first-row preview. Include them in the `--json` payload
under a `list_columns` key so the agent workflow can read them.

- [ ] **Step 4: Handle the all-list-columns edge case**

If `scalar_df` has no columns left, skip value-column detection entirely rather than letting
it raise, and report that the file contains only list columns.

- [ ] **Step 5: Run the test to verify it passes**

```bash
cd bindings/python && uv run --frozen pytest tests/api/test_cli_describe_list_columns.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Verify no regression on ordinary assumption tables**

```bash
cd bindings/python && uv run --frozen pytest tests/api/ -q
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add bindings/python/gaspatchio_core/cli.py \
  bindings/python/tests/api/test_cli_describe_list_columns.py
git commit -m "fix(cli): describe parquet files containing list columns (#40)"
```

---

### Task 4: Signpost timing conventions in AGENTS.md (#42)

`prospective_value`'s beginning/end-of-period semantics are documented in its docstring, but
AGENTS.md never mentions timing conventions at all, so the read-AGENTS-first path can miss
that it is a choice. #28 additionally fixed the discount-factor input contract: factors are
timing-anchored. A signpost, not a treatise — the detail belongs where it already lives.

**Files:**
- Modify: `AGENTS.md` (new section after "Assumption Tables")
- Modify: `.github/copilot-instructions.md` (generated)

**Interfaces:**
- Consumes: nothing. Produces: nothing.

- [ ] **Step 1: Read the authoritative docstring first**

```bash
cd bindings/python && uv run --frozen gspio docs "prospective_value" -n 40
```

Record the exact default (`beginning_of_period` vs `end_of_period`) — the section must match
the code, not this plan's assumption.

- [ ] **Step 2: Add the signpost section to AGENTS.md**

After the "Assumption Tables" section, insert:

```markdown
---

## Timing Conventions

Present-value and discounting methods take a **timing convention**, and it is a choice you
make, not a default you can ignore. Getting it wrong is a silent valuation error, not a
crash.

- `prospective_value(..., timing=...)` — whether a period's cashflow lands at the
  **beginning** or the **end** of that period. Run `uv run gspio docs "prospective_value"`
  for the full contract and the current default.
- **Discount factors are timing-anchored.** `end_of_period` factors start one period in;
  beginning-of-period factors start at 1.0. Passing factors built on the other convention
  shifts every cashflow by one period.
- Under varying (per-period) rates the two conventions are **not** related by a single
  multiplication — each cashflow carries its own compounded factor. See issue #28.

When reconciling against a reference model, confirm its timing convention before assuming a
difference is a bug in your assumptions.
```

- [ ] **Step 3: Regenerate the Copilot instructions**

```bash
uv run --no-project --python 3.13 python scripts/gen_skill_manifests.py
uv run --no-project --python 3.13 python scripts/gen_skill_manifests.py --check
```

Expected: exits 0.

- [ ] **Step 4: Run the skill guard tests**

```bash
cd bindings/python && uv run --frozen pytest ../../tests/skills/ -q
```

Expected: 125 passed.

- [ ] **Step 5: Commit**

```bash
git add AGENTS.md .github/copilot-instructions.md
git commit -m "docs: signpost timing conventions in the top-level guide (#42)"
```

- [ ] **Step 6: Open PR 1**

```bash
git push -u origin HEAD
gh pr create --title "Papercuts: negation, stale quickstart, describe, timing signpost" \
  --body "Closes #38, #35, #40, #42. See ref/48-v060-issue-triage/specs/2026-07-27-outstanding-issues-design.md §4."
```

---

# PR 2 — Lookup boundary (#37)

### Task 5: Targeted error for a bare-string lookup key (#37)

`tbl.lookup(product="annuity", age=af.age)` routes the string to `pl.col(...)`, so it reads
as a column name and fails with `ColumnNotFoundError: Column 'annuity' not found. Did you
mean...` — pointing away from the actual mistake.

**We deliberately do *not* auto-wrap bare strings as literals.** That would infer a meaning
from a shape, which *Sharp knives, no magic* forbids, and would silently change behaviour for
anyone legitimately passing a column name. Instead the error names both remedies.

Note the existing asymmetry at `_api.py:993`: only `str` routes to `pl.col`; every other
literal already falls through to `pl.lit(value)`.

**Files:**
- Modify: `bindings/python/gaspatchio_core/assumptions/_api.py:993`
- Test: `bindings/python/tests/assumptions/test_lookup_bare_string_key.py` (create)

**Interfaces:**
- Consumes: `Table.lookup(**dimensions)`.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/assumptions/test_lookup_bare_string_key.py`:

```python
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A bare-string lookup key must name both remedies.

Regression test for #37. ``lookup(product="annuity")`` reads the string as a
column name (Polars convention) and failed with a ColumnNotFoundError that
pointed away from the real mistake. The framework does NOT guess that a bare
string means a literal — inferring a meaning from a shape is what "Sharp
knives, no magic" forbids — so the contract is a clear error naming both fixes.
"""

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.assumptions import Table


def _table() -> Table:
    return Table(
        name="bare_string_key_rates",
        source=pl.DataFrame(
            {
                "product": ["annuity", "annuity", "term", "term"],
                "age": [40, 41, 40, 41],
                "rate": [0.001, 0.002, 0.003, 0.004],
            }
        ),
        dimensions={"product": "product", "age": "age"},
        value="rate",
    )


def test_bare_string_key_error_names_both_remedies():
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "age": [40]}))
    table = _table()

    with pytest.raises(Exception) as excinfo:
        af.rate = table.lookup(product="annuity", age=af.age)
        af.collect()

    message = str(excinfo.value)
    assert 'pl.lit("annuity")' in message
    assert 'af["annuity"]' in message
    assert "product" in message


def test_pl_lit_key_still_works():
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "age": [40]}))
    table = _table()
    af.rate = table.lookup(product=pl.lit("annuity"), age=af.age)
    out = af.collect()
    assert out["rate"].to_list() == [0.001]


def test_genuine_column_key_still_works():
    af = ActuarialFrame(
        pl.DataFrame({"policy_id": [1], "age": [40], "product": ["annuity"]})
    )
    table = _table()
    af.rate = table.lookup(product="product", age=af.age)
    out = af.collect()
    assert out["rate"].to_list() == [0.001]
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd bindings/python && uv run --frozen pytest tests/assumptions/test_lookup_bare_string_key.py -v
```

Expected: `test_bare_string_key_error_names_both_remedies` FAILS (the message contains
neither remedy). The other two must already PASS — if they don't, the fix must not break
them.

- [ ] **Step 3: Record the dimension name alongside each string key expression**

At `_api.py:993`, the `isinstance(value, str)` branch currently discards which dimension the
string came from. Capture it so the error can name it:

```python
                if isinstance(value, str):
                    # A bare string is read as a COLUMN NAME (Polars convention),
                    # not a literal value. We deliberately do not guess the other
                    # way — see #37 and PRINCIPLES.md "Sharp knives, no magic".
                    # Record the origin so a missing column produces an error
                    # naming both remedies rather than a bare ColumnNotFoundError.
                    string_key_origins[value] = dim_key
                    expr = pl.col(value)
```

Initialise `string_key_origins: dict[str, str] = {}` alongside `key_exprs = []`.

- [ ] **Step 4: Wrap the lookup so a missing string key raises the targeted error**

Wrap the evaluation boundary where `ColumnNotFoundError` currently escapes, and re-raise:

```python
        except pl.exceptions.ColumnNotFoundError as exc:
            missing = _extract_missing_column(str(exc))
            dim = string_key_origins.get(missing)
            if dim is None:
                raise
            msg = (
                f"Table {self._name!r}, dimension {dim!r}: {missing!r} was read as a "
                f"column name and no such column exists.\n"
                f'  • for a literal value:  {dim}=pl.lit("{missing}")\n'
                f'  • for a column:         {dim}=af["{missing}"]'
            )
            raise ValueError(msg) from exc
```

`errors/formatter.py` already enriches `ColumnNotFoundError`; check whether the enrichment
happens before or after this point and place the wrap so the targeted message survives.

- [ ] **Step 5: Run the test to verify it passes**

```bash
cd bindings/python && uv run --frozen pytest tests/assumptions/test_lookup_bare_string_key.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Run the full assumptions suite for regressions**

```bash
cd bindings/python && uv run --frozen pytest tests/assumptions/ -q
```

Expected: all pass — especially `test_dimension_rename.py` and `test_lookup_boundary.py`,
which cover the same code path from #17 and #32.

- [ ] **Step 7: Commit and open PR 2**

```bash
git add bindings/python/gaspatchio_core/assumptions/_api.py \
  bindings/python/tests/assumptions/test_lookup_bare_string_key.py
git commit -m "fix(assumptions): name both remedies for a bare-string lookup key (#37)"
git push -u origin HEAD
gh pr create --title "Lookup boundary: targeted error for bare-string dimension keys" \
  --body "Closes #37. Deliberately does not auto-wrap — see spec §4."
```

---

# PR 3 — Period index (#36)

### Task 6: Materialise `month` and `proj_year` at `projection.set()`

`projection.set()` materialises no period-index column, yet shipped examples use `af.month`.
Users derive it themselves from `t_years()`, which returns length `n_periods + 1` while
`year_fractions()` returns `n_periods` — an off-by-one waiting to happen.

**Naming is settled and `year` was rejected:** `ref/05-dsl-polars-wrapper` uses `af["year"]`
for *calendar* year, AGENTS.md Gotcha #7 names `proj_year` vs `year` as causing
silently-wrong stress scenarios. A framework-owned `year` column would collide with
model-point data and make a documented trap fire more often.

**Definitions (must be implemented exactly):**

| column | definition |
|---|---|
| `month` | elapsed **whole months** from projection start: `0,1,2,…` monthly; `0,3,6,…` quarterly; `0,12,24,…` annual |
| `proj_year` | `month // 12` |
| length | `n_periods + 1`, aligned with `t_years()` |

Defining `month` as *elapsed months* rather than a period counter keeps the name honest at
every frequency — a column called `month` that counted years would be its own trap.

**Files:**
- Modify: `bindings/python/gaspatchio_core/accessors/projection_frame.py` (in `set`, after the schedule is built)
- Test: `bindings/python/tests/accessors/test_projection_period_index.py` (create)

**Interfaces:**
- Consumes: `Schedule.year_fractions_expr()`, `Schedule.per_policy_period_dates_expr()`,
  and `self._require_projection()` — all in `projection_frame.py`.
- Produces: two materialised columns, `month` (`List<Int64>`) and `proj_year`
  (`List<Int64>`), on every frame returned by `projection.set()`. Task 7 depends on these
  names.

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/accessors/test_projection_period_index.py`:

```python
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""`projection.set()` materialises the period index.

Regression test for #36. Examples used ``af.month`` as though it existed;
it did not, and hand-rolling it from ``t_years()`` (length n_periods + 1) vs
``year_fractions()`` (length n_periods) invited an off-by-one. ``month`` is
ELAPSED WHOLE MONTHS so the name stays honest at every frequency, and the
annual index is ``proj_year`` — never ``year``, which collides with the
calendar year model points routinely carry (AGENTS.md Gotcha #7).
"""

import datetime

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame


def _frame() -> ActuarialFrame:
    return ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1],
                "issue_age": [40],
                "policy_inception": [datetime.date(2020, 1, 1)],
            }
        )
    )


def _set(frequency: str, n_periods: int = 24) -> pl.DataFrame:
    af = _frame().projection.set(
        start_date=datetime.date(2025, 1, 1),
        n_periods=n_periods,
        frequency=frequency,
    )
    return af.collect()


def test_monthly_month_is_consecutive_from_zero():
    out = _set("monthly", n_periods=24)
    assert out["month"].to_list()[0] == list(range(25))


def test_quarterly_month_steps_by_three():
    out = _set("quarterly", n_periods=4)
    assert out["month"].to_list()[0] == [0, 3, 6, 9, 12]


def test_annual_month_steps_by_twelve():
    out = _set("annual", n_periods=3)
    assert out["month"].to_list()[0] == [0, 12, 24, 36]


def test_proj_year_is_month_floor_div_twelve():
    out = _set("monthly", n_periods=24)
    months = out["month"].to_list()[0]
    assert out["proj_year"].to_list()[0] == [m // 12 for m in months]


def test_length_matches_t_years():
    af = _frame().projection.set(
        start_date=datetime.date(2025, 1, 1), n_periods=12, frequency="monthly"
    )
    af.ty = af.projection.t_years()
    out = af.collect()
    assert len(out["month"].to_list()[0]) == len(out["ty"].to_list()[0])


def test_existing_column_collision_raises():
    mp = pl.DataFrame(
        {
            "policy_id": [1],
            "issue_age": [40],
            "policy_inception": [datetime.date(2020, 1, 1)],
            "month": [7],
        }
    )
    with pytest.raises(ValueError, match="month"):
        ActuarialFrame(mp).projection.set(
            start_date=datetime.date(2025, 1, 1), n_periods=12, frequency="monthly"
        )
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd bindings/python && uv run --frozen pytest tests/accessors/test_projection_period_index.py -v
```

Expected: all FAIL with `month` not found (except the collision test, which fails because no
error is raised).

- [ ] **Step 3: Raise on collision before materialising**

In `set`, immediately before the columns are added:

```python
        # Refuse rather than overwrite: model points routinely carry a calendar
        # `year`, and silently replacing a user's column is the exact failure
        # class this release exists to eliminate (#36).
        for reserved in ("month", "proj_year"):
            if reserved in frame.columns:
                msg = (
                    f"projection.set() materialises a {reserved!r} column, but the "
                    f"frame already has one. Rename the existing column first — "
                    f"e.g. mp.rename({{{reserved!r}: 'source_{reserved}'}})."
                )
                raise ValueError(msg)
```

- [ ] **Step 4: Materialise the two columns**

Build `month` as the cumulative elapsed months, matching `t_years()`'s `n_periods + 1`
length and leading zero:

```python
        # `month` is ELAPSED WHOLE MONTHS from projection start, not a period
        # counter — so the name stays honest at quarterly and annual frequency.
        # Length is n_periods + 1, aligned with t_years(), so a maturity test
        # `when(af.month == af.policy_term * 12)` can fire on the final boundary.
        months_per_period = {"monthly": 1, "quarterly": 3, "annual": 12}[frequency]
        month_expr = (
            pl.int_ranges(0, (n_periods + 1) * months_per_period, months_per_period)
        )
```

For jagged (`per_policy`) timelines the length varies per policy — derive it from the same
per-policy period count the schedule already computes rather than from a scalar
`n_periods`, so `month` is jagged too. Then `proj_year` is
`month_expr.list.eval(pl.element() // 12)`.

- [ ] **Step 5: Run the test to verify it passes**

```bash
cd bindings/python && uv run --frozen pytest tests/accessors/test_projection_period_index.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Add a jagged-timeline test**

Append to the same file:

```python
def test_jagged_timeline_month_lengths_differ_per_policy():
    mp = pl.DataFrame(
        {
            "policy_id": [1, 2],
            "issue_age": [40, 60],
            "policy_inception": [
                datetime.date(2020, 1, 1),
                datetime.date(2020, 1, 1),
            ],
            "policy_term": [5, 10],
        }
    )
    af = ActuarialFrame(mp).projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_years",
        until_value=pl.col("policy_term"),
        frequency="monthly",
        per_policy=True,
    )
    out = af.collect()
    lengths = [len(m) for m in out["month"].to_list()]
    assert lengths[0] != lengths[1]
```

- [ ] **Step 7: Run the full projection suite**

```bash
cd bindings/python && uv run --frozen pytest tests/accessors/ tests/rollforward/ -q
```

Expected: all pass. `tests/accessors/test_projection.py` changed substantially in #19 — a
failure there means the new columns disturbed an existing shape assumption.

- [ ] **Step 8: Commit**

```bash
git add bindings/python/gaspatchio_core/accessors/projection_frame.py \
  bindings/python/tests/accessors/test_projection_period_index.py
git commit -m "feat(projection): materialise month and proj_year period index (#36)"
```

---

### Task 7: Document the period index and close the `year` question

**Files:**
- Modify: `AGENTS.md` (the `projection.set` example; Gotcha #7)
- Modify: `.github/copilot-instructions.md` (generated)

**Interfaces:**
- Consumes: `month` and `proj_year` from Task 6.

- [ ] **Step 1: Document the materialised columns in AGENTS.md**

In the "Model Structure: Three Phases" section, after the `projection.set(...)` call, add:

```markdown
`projection.set()` materialises two period-index columns you can use directly:

- `af.month` — elapsed whole months from projection start (`0,1,2,…` monthly;
  `0,3,6,…` quarterly). Length `n_periods + 1`, aligned with `projection.t_years()`.
- `af.proj_year` — `month // 12`.

There is deliberately **no** `year` column: model points routinely carry a calendar `year`,
and a framework-owned one would collide with it. See Gotcha #7.
```

- [ ] **Step 2: Strengthen Gotcha #7**

Change the "What Goes Wrong" cell for Gotcha #7 to note that `proj_year` is now materialised
by `projection.set()` and that `year`, if present, is the user's own calendar column — the
framework never creates one.

- [ ] **Step 3: Regenerate and verify**

```bash
uv run --no-project --python 3.13 python scripts/gen_skill_manifests.py --check || \
  uv run --no-project --python 3.13 python scripts/gen_skill_manifests.py
cd bindings/python && uv run --frozen pytest ../../tests/skills/ -q
```

Expected: 125 passed.

- [ ] **Step 4: Commit and open PR 3**

```bash
git add AGENTS.md .github/copilot-instructions.md
git commit -m "docs: document the materialised period index (#36)"
git push -u origin HEAD
gh pr create --title "Projection: materialise month and proj_year" \
  --body "Closes #36. \`year\` deliberately rejected — see spec §4."
```

---

# PR 4 — Curve extrapolation (#31)

### Task 8: Make the `extrapolation` parameter live in Rust

`log_linear` interpolates in log-discount-factor space via `eval_linear`, which flat-clamps
`ys` outside the knot range. For `log_linear`, `ys` are log-DFs, so clamping holds the
**discount factor** constant — it stops decaying. A flat 5% curve with a last knot at 10y
returns ≈1.64% at 30y, and `DF(30) = 0.607` against a correct `0.223`: the cashflow is
carried at ~2.7× its true value.

**The root cause is narrower than "wrong convention":** for `linear`/`pchip`, `ys` are rates,
so flat-clamping gives constant spot, which is correct. Only `log_linear` clamps in the wrong
space.

**`extrapolation` already exists and is dead** — declared at `curve_eval.rs:27`, defaulted at
`plugins.py:300`, serialised at line 360, and read by nothing.

**Files:**
- Modify: `core/src/polars_functions/curve_eval.rs` (the `"log_linear"` arm, ~line 169; the
  `extrapolation` doc comment at line 25)
- Test: `core/src/polars_functions/curve_eval.rs` (`#[cfg(test)]` module, existing)

**Interfaces:**
- Produces: `extrapolation` accepts `"flat"` (default) and `"forward"` for `log_linear`;
  every other value is a `ComputeError`. Tasks 9–10 depend on these exact strings.

- [ ] **Step 1: Write the failing Rust tests**

Add to the existing `#[cfg(test)]` module in `curve_eval.rs`:

```rust
    /// Flat 5% curve, last knot 10y: the spot at 30y must stay 5% under BOTH
    /// conventions. Before #31 it collapsed to ~1.64% because the log-DF LEVEL
    /// was clamped instead of the rate.
    #[test]
    fn log_linear_flat_curve_holds_rate_beyond_last_knot() {
        let xs = vec![5.0, 10.0];
        // y_i = -u_i * ln(1 + r_i) with r = 5%
        let ys = vec![-5.0 * 1.05_f64.ln(), -10.0 * 1.05_f64.ln()];
        for mode in ["flat", "forward"] {
            let kw = CurveEvalKwargs {
                method: "log_linear".into(),
                xs: Some(xs.clone()),
                ys: Some(ys.clone()),
                slopes: None,
                extrapolation: Some(mode.into()),
                b0: None, b1: None, b2: None, b3: None,
                tau1: None, tau2: None,
                u: None, zeta: None, omega: None, alpha: None,
            };
            let spot = eval_one(30.0, &kw).unwrap();
            assert!(
                (spot - 0.05).abs() < 1e-9,
                "mode {mode}: expected 5%, got {spot}"
            );
        }
    }

    /// Upward-sloping curve: "flat" holds the last SPOT, "forward" extends the
    /// last segment's forward. They must differ, and neither may collapse.
    #[test]
    fn log_linear_flat_and_forward_differ_on_a_sloped_curve() {
        let xs = vec![5.0, 10.0];
        let ys = vec![-5.0 * 1.04_f64.ln(), -10.0 * 1.05_f64.ln()];
        let mk = |mode: &str| CurveEvalKwargs {
            method: "log_linear".into(),
            xs: Some(xs.clone()),
            ys: Some(ys.clone()),
            slopes: None,
            extrapolation: Some(mode.into()),
            b0: None, b1: None, b2: None, b3: None,
            tau1: None, tau2: None,
            u: None, zeta: None, omega: None, alpha: None,
        };
        let flat = eval_one(30.0, &mk("flat")).unwrap();
        let forward = eval_one(30.0, &mk("forward")).unwrap();

        // "flat" holds the last knot's spot exactly.
        assert!((flat - 0.05).abs() < 1e-9, "flat should hold 5%, got {flat}");
        // "forward" extends the steeper last-segment forward, so it sits higher.
        assert!(forward > flat, "forward {forward} should exceed flat {flat}");
        // Neither may reproduce the pre-fix collapse.
        assert!(flat > 0.03 && forward > 0.03, "collapse regression");
    }

    #[test]
    fn log_linear_rejects_unknown_extrapolation() {
        let kw = CurveEvalKwargs {
            method: "log_linear".into(),
            xs: Some(vec![5.0, 10.0]),
            ys: Some(vec![-0.2, -0.5]),
            slopes: None,
            extrapolation: Some("parabolic".into()),
            b0: None, b1: None, b2: None, b3: None,
            tau1: None, tau2: None,
            u: None, zeta: None, omega: None, alpha: None,
        };
        let err = eval_one(30.0, &kw).unwrap_err().to_string();
        assert!(err.contains("parabolic"), "error must name the bad value: {err}");
        assert!(err.contains("flat"), "error must list valid options: {err}");
        assert!(err.contains("forward"), "error must list valid options: {err}");
    }
```

If the single-point evaluator is not named `eval_one`, use whatever the existing tests in
that module call — read them first and match.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd core && cargo test curve_eval
```

Expected: the flat-curve test FAILS (returns ≈0.0164 instead of 0.05); the unknown-mode test
FAILS (no error raised).

- [ ] **Step 3: Branch the `log_linear` arm on `extrapolation`**

Replace the body of the `"log_linear"` arm (currently `let log_df = eval_linear(t, xs, ys);`
then convert) with an implementation that, **before** falling back to interpolation, handles
`t` outside `[xs[0], xs[n-1]]`:

```rust
            let mode = kw.extrapolation.as_deref().unwrap_or("flat");
            let n = xs.len();
            let log_df = if n >= 2 && t > xs[n - 1] {
                match mode {
                    // Hold the SPOT rate, not the log-DF level: this is what
                    // "flat" already means for linear/pchip, whose ys are rates.
                    "flat" => ys[n - 1] * (t / xs[n - 1]),
                    // Extend the last segment's log-DF slope = constant forward.
                    "forward" => {
                        let s = (ys[n - 1] - ys[n - 2]) / (xs[n - 1] - xs[n - 2]);
                        ys[n - 1] + s * (t - xs[n - 1])
                    }
                    other => {
                        return Err(polars_err!(ComputeError:
                            "curve_eval log_linear: unknown extrapolation {:?}; \
                             expected \"flat\" or \"forward\"", other))
                    }
                }
            } else if n >= 2 && t < xs[0] {
                match mode {
                    "flat" => ys[0] * (t / xs[0]),
                    "forward" => {
                        let s = (ys[1] - ys[0]) / (xs[1] - xs[0]);
                        ys[0] - s * (xs[0] - t)
                    }
                    other => {
                        return Err(polars_err!(ComputeError:
                            "curve_eval log_linear: unknown extrapolation {:?}; \
                             expected \"flat\" or \"forward\"", other))
                    }
                }
            } else {
                eval_linear(t, xs, ys)
            };
            let df = log_df.exp();
            Ok(df.powf(-1.0 / t) - 1.0)
```

`ys[n-1] * (t / xs[n-1])` holds the spot constant because `ys` are log-DFs: scaling the
log-DF linearly in `t` keeps `-ln(DF)/t` fixed.

- [ ] **Step 4: Reject `"forward"` for `linear` and `pchip`**

In those two arms, before evaluating:

```rust
            if let Some(mode) = kw.extrapolation.as_deref() {
                if mode != "flat" {
                    return Err(polars_err!(ComputeError:
                        "curve_eval {}: extrapolation {:?} is not supported; \
                         only \"flat\" applies to rate-space knots",
                        kw.method, mode));
                }
            }
```

No silently-ignored parameters — that is the defect class this release exists to remove.

- [ ] **Step 5: Correct the now-false doc comment**

At `curve_eval.rs:25`, replace *"Currently always flat (the only supported value); reserved
for future methods"* with:

```rust
    /// Extrapolation mode outside the knot range. `"flat"` (default) holds the
    /// spot rate; `"forward"` holds the last segment's forward rate and applies
    /// to `log_linear` only. Unknown values are an error — never ignored.
```

- [ ] **Step 6: Run the Rust tests**

```bash
cd core && cargo test curve_eval && cargo clippy -- -D warnings && cargo fmt --check
```

Expected: all pass, clean.

- [ ] **Step 7: Commit**

```bash
git add core/src/polars_functions/curve_eval.rs
git commit -m "fix(curves): hold the rate, not the log-DF, past the last knot (#31)"
```

---

### Task 9: Thread `extrapolation` through the Python surface

**Files:**
- Modify: `bindings/python/gaspatchio_core/polars_backend/plugins.py:300` (docstring only —
  the kwarg already passes through)
- Modify: `bindings/python/gaspatchio_core/curves/_curve.py` (accept and forward
  `extrapolation`)
- Modify: the corresponding `.pyi` stub
- Test: `bindings/python/tests/curves/test_curve_extrapolation.py` (create)

**Interfaces:**
- Consumes: Task 8's `"flat"` / `"forward"` contract.
- Produces: `Curve.from_knots(..., extrapolation="flat"|"forward")`.

- [ ] **Step 1: Rebuild the extension so Python sees Task 8**

```bash
cd bindings/python && maturin build -uv && uv sync --locked
```

- [ ] **Step 2: Write the failing test**

Create `bindings/python/tests/curves/test_curve_extrapolation.py`:

```python
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Curve extrapolation beyond the last knot.

Regression test for #31. `log_linear` clamped the log-discount-factor LEVEL,
so the discount factor stopped decaying and long-end spot rates collapsed —
a flat 5% curve returned ~1.64% at 30y. `extrapolation` was declared,
defaulted and serialised across the plugin boundary but read by nothing.
"""

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.curves import Curve

TENORS = [5.0, 10.0]
FLAT_RATES = [0.05, 0.05]
SLOPED_RATES = [0.04, 0.05]


def _spot_at(rates, mode, t=30.0):
    curve = Curve.from_knots(
        TENORS, rates, method="log_linear", extrapolation=mode
    )
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "t": [t]}))
    af.spot = curve.spot_rate(af.t)
    return af.collect()["spot"].to_list()[0]


@pytest.mark.parametrize("mode", ["flat", "forward"])
def test_flat_curve_holds_its_rate_at_30y(mode):
    assert _spot_at(FLAT_RATES, mode) == pytest.approx(0.05, abs=1e-9)


def test_pre_fix_collapse_never_returns():
    # The reported symptom was ~1.64% on a flat 5% curve.
    for mode in ("flat", "forward"):
        assert _spot_at(FLAT_RATES, mode) > 0.03


def test_forward_exceeds_flat_on_an_upward_sloping_curve():
    flat = _spot_at(SLOPED_RATES, "flat")
    forward = _spot_at(SLOPED_RATES, "forward")
    assert flat == pytest.approx(0.05, abs=1e-9)
    assert forward > flat


def test_unknown_extrapolation_raises_naming_the_options():
    with pytest.raises(Exception) as excinfo:
        _spot_at(FLAT_RATES, "parabolic")
    message = str(excinfo.value)
    assert "parabolic" in message
    assert "flat" in message
    assert "forward" in message


def test_default_is_flat():
    curve = Curve.from_knots(TENORS, FLAT_RATES, method="log_linear")
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "t": [30.0]}))
    af.spot = curve.spot_rate(af.t)
    assert af.collect()["spot"].to_list()[0] == pytest.approx(0.05, abs=1e-9)
```

If `Curve.from_knots` is not the constructor name, read `curves/_curve.py` and use the real
one — the test must exercise the public API, not an internal.

- [ ] **Step 3: Run to verify it fails**

```bash
cd bindings/python && uv run --frozen pytest tests/curves/test_curve_extrapolation.py -v
```

Expected: FAIL — `from_knots` rejects `extrapolation`, or the values collapse.

- [ ] **Step 4: Accept and forward `extrapolation` in `_curve.py`**

Add `extrapolation: str = "flat"` to the knot-curve constructor, store it on the curve, and
pass it into the `curve_eval` call. Validate at construction so the error arrives at the call
site rather than at `collect()`:

```python
        if extrapolation not in ("flat", "forward"):
            msg = (
                f"extrapolation {extrapolation!r} is not supported; "
                f'expected "flat" or "forward"'
            )
            raise ValueError(msg)
```

`extrapolation` must join `canonical_form()` so `source_sha()` distinguishes two curves that
differ only by extrapolation mode — *Audit by default* requires the identity stamp to change
when behaviour changes.

- [ ] **Step 5: Correct the `plugins.py` docstring**

Replace *"``\"flat\"`` (the only supported value) clamps to the nearest knot"* with a
description of both modes and the fact that unknown values raise.

- [ ] **Step 6: Run the tests**

```bash
cd bindings/python && uv run --frozen pytest tests/curves/ -q
```

Expected: all pass, including the pre-existing `test_curve_eval.py` and
`test_curve_interpolation.py`.

- [ ] **Step 7: Verify stubs**

```bash
cd bindings/python && uv run --frozen python -m mypy.stubtest gaspatchio_core \
  --ignore-missing-stub --ignore-unused-allowlist \
  --mypy-config-file mypy-stubtest.ini --allowlist stubtest-allowlist.txt
```

- [ ] **Step 8: Commit**

```bash
git add bindings/python/gaspatchio_core/curves/ \
  bindings/python/gaspatchio_core/polars_backend/plugins.py \
  bindings/python/tests/curves/test_curve_extrapolation.py
git commit -m "feat(curves): expose flat/forward extrapolation on knot curves (#31)"
```

---

### Task 10: Document the breaking change

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add the migration entry**

Under the v0.6.0 heading, in a **Breaking changes** section:

```markdown
- **`log_linear` curves: long-end rates change past the last knot.** Extrapolation previously
  clamped the log-discount-factor level, so discount factors stopped decaying and spot rates
  collapsed toward zero — a flat 5% curve returned ≈1.64% at 30y, carrying a 30-year cashflow
  at ~2.7× its true value. `extrapolation="flat"` (the default) now holds the **spot rate**,
  matching what `"flat"` has always meant for `linear`/`pchip`. `extrapolation="forward"`
  holds the last segment's forward rate — the market-consistent choice for long-tail
  discounting. Unknown values now raise instead of being silently ignored.

  **Action:** if you evaluate a `log_linear` curve beyond its last knot, your long-end
  discount rates will change. Re-run any reconciliation that touches 20y+ cashflows.
```

- [ ] **Step 2: Commit and open PR 4**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): record the log_linear extrapolation change (#31)"
git push -u origin HEAD
gh pr create --title "Curves: make extrapolation live; fix the log_linear long-end collapse" \
  --body "Closes #31. BREAKING: long-end numbers change. See spec §4."
```

---

# PR 5 — Collect-time error attribution (#39)

### Task 11: Attribute collect-time errors to the assigned column

A lazy chain failing at `collect()` with `ShapeError: list lengths differed at index 0:
6 != 3` never says which assigned column produced it. This is a **principle violation**, not
an ergonomic wish: *Audit by default* promises expression lineage on every output column. The
lineage exists — #18 made the computation graph record-only metadata and error-boundary
diagnosis already replays against a pristine frame — the error path simply does not use it.

**This is the one task whose cost cannot be estimated before starting.** It is scheduled last
so that uncertainty sits off the critical path.

**Files:**
- Modify: `bindings/python/gaspatchio_core/frame/base.py` (the `collect()` error boundary)
- Modify: `bindings/python/gaspatchio_core/errors/boundary.py`
- Test: `bindings/python/tests/frame/test_collect_error_attribution.py` (create)

**Interfaces:**
- Consumes: the record-only computation graph from #18.
- Produces: enriched exception messages; no new public API.

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/frame/test_collect_error_attribution.py`:

```python
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Collect-time errors must name the offending column.

Regression test for #39. A lazy chain failing at collect() surfaced a raw
Polars error ("list lengths differed at index 0: 6 != 3") that never said
WHICH assigned column produced it — a long hunt in a 50-column model.
Assign-time errors were already attributed; collect-time ones were not.

The fallback contract matters as much as the feature: if attribution is
ambiguous the ORIGINAL error must pass through untouched. A wrong column name
costs more than no column name.
"""

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame


def _ragged_frame() -> ActuarialFrame:
    return ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1],
                "six": [[1.0, 2.0, 3.0, 4.0, 5.0, 6.0]],
                "three": [[1.0, 2.0, 3.0]],
            }
        )
    )


def test_shape_error_names_the_offending_column():
    af = _ragged_frame()
    af.mismatched = af.six * af.three
    with pytest.raises(Exception) as excinfo:
        af.collect()
    assert "mismatched" in str(excinfo.value)


def test_attribution_picks_the_right_column_in_a_chain():
    af = _ragged_frame()
    af.fine_one = af.six * 2.0
    af.fine_two = af.three + 1.0
    af.broken = af.six - af.three
    with pytest.raises(Exception) as excinfo:
        af.collect()
    message = str(excinfo.value)
    assert "broken" in message
    assert "fine_one" not in message
    assert "fine_two" not in message


def test_unattributable_error_passes_through_unchanged():
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "a": [1.0]}))
    original = None
    try:
        af.collect_with_forced_error()  # type: ignore[attr-defined]
    except AttributeError as exc:
        original = exc
    assert original is not None
```

The third test is a placeholder shape for the fallback contract — replace its body with
whatever unattributable failure the implementation can actually produce once Step 3 reveals
the attribution mechanism. **Do not delete it**; the fallback is the safety property.

- [ ] **Step 2: Run to verify it fails**

```bash
cd bindings/python && uv run --frozen pytest tests/frame/test_collect_error_attribution.py -v
```

Expected: the first two FAIL — the message contains only Polars' text.

- [ ] **Step 3: Read the existing replay machinery before writing anything**

```bash
cd bindings/python && sed -n '1,80p' gaspatchio_core/errors/boundary.py
grep -n "replay\|pristine\|computation_graph\|_graph" gaspatchio_core/frame/base.py | head -30
```

Record: how the graph stores each assignment, whether it retains the source expression, and
where `collect()` currently catches. The implementation below must match what is actually
there.

- [ ] **Step 4: Attribute by bisecting the recorded assignments**

At the `collect()` boundary, catch `pl.exceptions.ShapeError`,
`pl.exceptions.InvalidOperationError` and `pl.exceptions.SchemaError`, then re-apply the
recorded assignments one at a time against a pristine frame until one reproduces the same
error class and message. Attribute to that column and re-raise:

```python
        except (
            pl.exceptions.ShapeError,
            pl.exceptions.InvalidOperationError,
            pl.exceptions.SchemaError,
        ) as exc:
            column = self._attribute_failure(exc)
            if column is None:
                raise  # Never make the error worse than we found it.
            msg = (
                f"{exc}\n\n"
                f"  Failing column: {column!r}\n"
                f"  Defined as:     {self._graph_source_for(column)}"
            )
            raise type(exc)(msg) from exc
```

- [ ] **Step 5: Guarantee the fallback**

`_attribute_failure` returns `None` on any ambiguity — no reproducing assignment, more than
one candidate, or an exception raised during replay. Replay must never mutate the live frame.

- [ ] **Step 6: Run the tests**

```bash
cd bindings/python && uv run --frozen pytest tests/frame/ -q
```

Expected: all pass, including `test_base_error_handling.py`,
`test_compilation_errors.py` and `test_error_handling_fixed.py`, which #16/#18 changed.

- [ ] **Step 7: Run the full suite**

```bash
cd bindings/python && uv run --frozen pytest -q
```

Expected: ≥2,644 passed, 0 failed.

- [ ] **Step 8: Commit and open PR 5**

```bash
git add bindings/python/gaspatchio_core/frame/base.py \
  bindings/python/gaspatchio_core/errors/boundary.py \
  bindings/python/tests/frame/test_collect_error_attribution.py
git commit -m "feat(errors): name the offending column in collect-time failures (#39)"
git push -u origin HEAD
gh pr create --title "Errors: attribute collect-time failures to the assigned column" \
  --body "Closes #39. Falls back to the unmodified error on any ambiguity. See spec §4."
```

---

# Release

### Task 12: Cut v0.6.0

- [ ] **Step 1: Confirm every issue is closed**

```bash
gh issue list --state open --limit 20
```

Expected: only #41 (Excel port path, deferred) remains.

- [ ] **Step 2: Write the release notes, migration first**

Lead with the three breaking changes in this order — most likely to bite first:

1. **#24** — lookup misses now raise. Opt out with `on_missing="nan"` or a constant, per
   table or per lookup.
2. **#28** — `prospective_value` varying-rate `end_of_period` values change; NaN cashflows
   are no longer silently zeroed.
3. **#31** — `log_linear` long-end rates change past the last knot.

- [ ] **Step 3: Tag and release**

```bash
git checkout main && git pull
git tag -s v0.6.0 -m "v0.6.0"
git push origin v0.6.0
```

The tag push triggers the wheel matrix in `.github/workflows/CI.yml`.

- [ ] **Step 4: Version-stamp the issues**

Comment on #21–#30 and every issue closed above with the version carrying the fix, and remove
the `pending-release` label.

- [ ] **Step 5: Reply to the field reporter**

Confirm all 13 findings are resolved or tracked (#41 deferred with a tracking issue), and
call out **#24 specifically**: a `when()` guard wrapped around a lookup that relies on misses
will now raise unless `on_missing="nan"` is declared. That is the change most likely to break
the model already built against v0.5.x.

---

## Self-Review

**Spec coverage.** Every §4 issue maps to a task: #38→1, #35→2, #40→3, #42→4, #37→5, #36→6–7,
#31→8–10, #39→11. §5 sequencing → the five PR groupings. §7 release/comms → Task 12. §3's
#41 deferral is correctly absent (no task, tracked issue remains open). #33 is already done
on this branch and correctly has no task.

**Placeholder scan.** No TBD/TODO. Two steps deliberately require reading real code before
implementing — Task 3 Step 2 (locate the raise from the traceback) and Task 11 Step 3 (read
the replay machinery). These are not placeholders: both specify the exact command to run and
what to record, because inventing a call site the implementer cannot verify would be worse
than directing them to the evidence. Task 11's third test is explicitly marked as a shape to
be completed once Step 3 reveals the mechanism, with an instruction not to delete it.

**Type consistency.** `__neg__` returns `ExpressionProxy` on both proxies (Task 1). The
`"flat"`/`"forward"` strings are identical across Rust (Task 8), Python (Task 9), tests, and
the changelog (Task 10). `month` and `proj_year` are named identically in Task 6's
implementation, Task 6's tests, and Task 7's docs. `_attribute_failure` and
`_graph_source_for` are introduced and used only within Task 11.

**Known risk.** Task 6 Step 4's `month` construction for jagged timelines is described rather
than given as literal code, because the per-policy period count comes from schedule internals
this plan has not read. The implementer must read `Schedule` in `projection_frame.py` first.
This is flagged rather than guessed.
