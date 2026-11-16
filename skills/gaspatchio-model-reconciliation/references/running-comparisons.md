# Running Comparisons

```bash
# Run single policy — ALWAYS use --output-file for machine-readable output
uv run gspio run-single-policy model.py data.parquet POLICY_ID --output-file /tmp/result.parquet

# Run all policies
uv run gspio run-model model.py data.parquet --output-file /tmp/results.parquet

# Inspect structure of result
uv run gspio describe /tmp/result.parquet --json
```

## Inspecting model output

After running with `--output-file`, inspect the output structure:
```bash
uv run gspio describe --json /tmp/result.parquet
```
This shows schema, column types, detected dimensions, and sample rows. Use it to understand the output before writing comparison code.

**Always use `--output-file`**. Do NOT parse stdout for reconciliation — use parquet (typed, schema-preserved) for machine diffs.

Use Polars to compare the gaspatchio outputs to the source model outputs at the **column + time-step** level.

## What a fix moved, and whether two runs agree

Comparing gaspatchio with itself has its own commands; do not hand-roll them.

```bash
# Two versions of the model (before and after a fix): which lines' numbers moved
uv run gspio calc-graph model.py data.parquet -o after.audit.json --results after.parquet
uv run gspio diff before.audit.json after.audit.json

# Two runs of one version (a re-run, another machine): do they agree?
uv run gspio compare after.audit.json run1.parquet run2.parquet

# The ids repeat (two cohorts, a scenario axis): name every column a row is known by
uv run gspio compare after.audit.json run1.parquet run2.parquet \
    --policy-id-column policy_id --policy-id-column cohort
```

`gspio diff` on two audit files says what changed — formulas, tables, policy
data — and, reading the two results files the audit files record, which
lines' numbers moved, in how many policies, from which period and by how
much; `gspio compare` answers a different question, whether two runs of *one*
artifact agree. Put each fix's diff in its build-log entry: the line the fix
edited reads `(self)`, and every other line that moved reads `(inherited)`. A
line that moved and was not meant to is the next mismatch. When one column
does not name each row once, give `--policy-id-column` again for each further
column (`run-model`, `calc-graph`, `run-artifact`, `compare` and `diff` all
repeat it); the
results file records the identity it was written under, and `compare`/`diff`
pair rows on it.
