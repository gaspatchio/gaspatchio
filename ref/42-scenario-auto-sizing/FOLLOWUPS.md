# Follow-ups — scenario benchmarks & showcase

## 1. `explode`-to-long-format for the per-month cross-scenario fan — find the gaspatchio-native way

**Where:** `evals/benchmarks/run_scenario_showcase.py::_fan_series`.

**What it does now:** to build the percentile fan (per projection month, the 5/25/50/75/95
percentiles of *portfolio* net cashflow across scenarios), it drops the per-policy list
columns to long format:

```python
df.select("scenario_id", "month", "net_cf")
  .explode(["month", "net_cf"])                       # scenarios × policies × months → rows
  .group_by("scenario_id", "month").agg(pl.col("net_cf").sum())   # portfolio per (scenario, month)
  .group_by("month").agg([... quantile(q) ...])       # cross-scenario percentile per month
```

**Why flagged (Matt's observation):** `explode` materialises the
`scenarios × policies × months` grid into a long frame — which is *exactly* the blow-up the
bounded-memory `for_each_scenario(batch_size="auto")` loop is designed to avoid. Using it
inside the scenario showcase feels like reaching outside the framework's model.

**The nuance (why it's not a clear-cut bug):** `explode` + `group_by` is *explicitly
documented* as the correct Phase-4 fund-aggregation pattern in
`skills/model-building/references/aggregate-patterns.md` (lines 43–59), and `explode` is **not**
in the `extending-gaspatchio` anti-patterns list (which targets Python loops, `map_elements`,
per-row dict lookups, `.iter_rows()`). So for one-shot per-entity→portfolio period aggregation
it is sanctioned. It is bounded here by `N_FAN` (a 100-scenario subset), so it is safe at the
current scale.

**To investigate — is there a more "gaspatchio" route for cross-scenario per-period stats?**
1. **Aggregator framework, per-period:** can `Quantile(...).over(...)` (the scenario
   Aggregator protocol) compute per-projection-period percentiles across scenarios directly,
   so the fan comes out of the same bounded-memory loop as the distribution — no explode, no
   second full-grid re-run? (The distribution already uses `Sum(...).alias().over("scenario_id")`
   — the idiomatic path. The fan is the part that fell back to raw Polars.)
2. **List-native portfolio sum:** sum the per-policy `net_cf` *lists* element-wise across
   policies within each scenario (→ one portfolio `net_cf` list per scenario, length = horizon),
   then take per-month percentiles across the per-scenario lists — staying in the list-column
   world rather than exploding. Does an accessor exist for element-wise list sum across rows, or
   is that a framework gap worth raising?
3. If neither is ergonomic, that is itself a **framework-gap finding** (per the
   `aggregate-patterns.md` ethos: "raise it as a framework gap rather than reaching for a loop"
   — here, rather than reaching for `explode` in the scenario context).

**General principle to confirm with Matt:** treat `explode`-on-list-columns inside the scenario
loop as a smell to be justified, even though it is fine in plain Phase-4 fund aggregation.

---

## 2. Live-streaming scenario aggregation — real-time convergence demo

**Idea (Matt, "for later"):** stream the *running* aggregations to disk as the scenario loop
progresses so a chart updates in real time — watch CTE70 / the loss distribution converge as the
scenario count grows. Visualises the Monte-Carlo convergence question actuaries actually argue
about ("how many scenarios until the tail is stable?").

**Why it's natural (not a hack):** the Beam-style mergeable Aggregator protocol
(`create_accumulator` → `add_input` → `merge_accumulators` → `extract_output`) means the merged
accumulator after *K* batches **is the exact aggregate over the first K batches' scenarios**. So
partial-after-each-batch snapshots are correct, not approximations.

**Mechanism:**
1. Add an optional `on_batch=` / `stream_path=` to `for_each_scenario` (sits beside the existing
   `progress` flag). After each `merge_accumulators`, call `extract_output` on the running state
   and append one JSONL line: `{"scenarios_done": K, "cte70": ..., "cte95": ..., "p05".."p95": ...}`.
2. Append-only JSONL (atomic line appends) so the reader never sees a half-written record. Use a
   small `batch_size` for many frames.
3. Live viewer reuses the gh-pages dashboard pattern but local + live: an HTML page that
   `fetch`-polls the JSONL every ~250 ms and redraws Vega-Lite/Chart.js (or a polling Altair cell
   in a notebook, or a `rich` terminal plot).

**Money-shot chart:** running CTE70/CTE95 vs scenarios-completed (the convergence line) + a loss
histogram filling in beside it.

**Two effort levels:** (a) quick demo with no framework change — drive scenarios in explicit
chunks (`itertools.batched`), `extract`/write a snapshot per chunk (bypasses `auto`); (b) proper —
the `on_batch` hook, which works with `batch_size="auto"` and is reusable. (b) is small and the
better one.

**Gotchas:** atomic snapshot writes; deterministic scenario ordering means "1..K done" is
well-defined; keep the per-batch `extract_output` cheap (it runs every batch).
