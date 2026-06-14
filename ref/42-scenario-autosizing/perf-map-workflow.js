// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

export const meta = {
  name: 'gsp-perf-map',
  description: 'Deep read-only analysis of the gaspatchio VA-model hot path → ranked, ready-to-run framework-level perf spike specs',
  whenToUse: 'Investigating how to 2x+ the L4 VA-model benchmark via framework (not model) changes',
  phases: [
    { title: 'Map', detail: '4 parallel read-only lanes: lookup kernel, list arithmetic representation, projection accessors, plan/build config' },
    { title: 'Synthesize', detail: 'rank theories by realistic multiple × confidence × independence; emit top spike specs' },
  ],
}

const ROOT = '~/projects/gaspatchio/gaspatchio-core'

const COMMON = `
You are analysing the gaspatchio-core actuarial framework to find FRAMEWORK-LEVEL (not model-level)
performance improvements that could 2x+ the throughput of the L4 "VA Model (GMDB/GMAB)" benchmark.

The benchmark: evals/benchmarks/run_model_benchmarks.py runs tutorial/level-4-lifelib/base/model.py
over 1K/10K/100K policies. Each policy is a monthly projection to age 100 (~120-480 periods). Columns
are Polars List(Float64) — one list per policy. Throughput = policies / wall_seconds.

HARD CONSTRAINTS for this task:
- READ-ONLY. Do NOT edit any file. Do NOT run cargo, maturin, uv sync, or any benchmark — the machine
  is busy compiling and timing would be invalid. Use Read / Grep / Bash(grep,ls,sed -n) on source only.
- Repo root: ${ROOT}
- Focus on GENERAL framework changes (kernels, query plan, representation, build config), NOT changes
  to the model.py itself.
- Ground every claim in specific files + line ranges you actually read. No hand-waving.
- "expected_multiple" = your honest estimate of the throughput multiple THIS change alone yields on the
  L4 hot path (e.g. "1.2x", "1.5-2x", "2-4x"). Be skeptical; most micro-opts are <1.2x. Reserve >=2x for
  changes that remove a dominant cost (a per-op explode/implode, a debug build, a repeated full-column copy).
`

const FINDINGS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['lane', 'findings', 'summary'],
  properties: {
    lane: { type: 'string' },
    summary: { type: 'string', description: 'what the hot path does in this lane + the single biggest waste found' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['id', 'title', 'current_behavior', 'evidence', 'proposed_change', 'scope', 'expected_multiple', 'confidence', 'risk', 'needs_rust_build'],
        properties: {
          id: { type: 'string', description: 'short slug e.g. lookup-zerocopy-offsets' },
          title: { type: 'string' },
          current_behavior: { type: 'string', description: 'exactly what the code does today + why it costs' },
          evidence: { type: 'string', description: 'file paths + line ranges read to support this' },
          proposed_change: { type: 'string', description: 'concrete minimal change; name files/functions to touch' },
          scope: { type: 'string', enum: ['rust-kernel', 'python-frame', 'query-plan', 'build-config', 'representation'] },
          expected_multiple: { type: 'string' },
          confidence: { type: 'string', enum: ['low', 'medium', 'high'] },
          risk: { type: 'string', description: 'correctness/compat risk + what could break (jagged per-policy timelines, streaming engine, reconciliation)' },
          needs_rust_build: { type: 'boolean' },
        },
      },
    },
  },
}

phase('Map')

const lanes = [
  {
    id: 'lookup-kernel',
    prompt: `${COMMON}
LANE: Assumption-table lookup kernel (the L4 model does many list-column multi-key lookups:
mortality_select 3 keys, lapse 2, surrender_charge 2, risk_free 3).

Read and trace the FULL data flow for a List-column lookup:
  Python: bindings/python/gaspatchio_core/assumptions/_api.py, _strategies.py, _dimensions.py, _builder.py, _utils.py
  Find where the lookup plugin is invoked (grep for 'register_plugin', 'lookup_series', 'plugin_path', 'is_elementwise' under bindings/python).
  Rust:  core/src/assumptions/key_encoder.rs, array_storage.rs, hash_storage.rs, table.rs, registry.rs
         and any lookup entrypoint under core/src/polars_functions/ (grep for 'lookup' across core/src).
Document precisely: for a List(Float64/Int64) key column of N policies × ~P periods, how many full-buffer
allocations/copies happen per lookup per table? Specifically check: does it explode() the list to a flat
Series, encode keys into a new buffer, gather into a new values buffer, then REBUILD a ListChunked with new
offsets? The AGENTS.md documents this path as "explode → encode → linear index → gather → rebuild ListChunked".
Key hypotheses to evaluate (state expected_multiple for each you find real):
  (a) Zero-copy on inner values: a lookup is elementwise & length-preserving, so you can gather on the list's
      INNER primitive array and REUSE the original arrow offsets — skipping explode and offset rebuild entirely.
  (b) Fused multi-key encode: encode all key dims in one pass over the flat buffer rather than per-dim temporaries.
  (c) Is the plugin marked is_elementwise=True? If not, it forces in-memory execution for the whole plan.
Return all findings via the StructuredOutput tool.`,
  },
  {
    id: 'list-arithmetic-representation',
    prompt: `${COMMON}
LANE: List-column arithmetic + conditionals representation (THE potentially biggest architectural lever).

The model has dozens of formula lines like 'af.claims = af.sum_assured * af.pols_death',
'af.net_cf = af.premiums - af.claims - af.expenses', and when(...).then(...).otherwise(...).
Each operand is a List(Float64) column (one list per policy). Determine HOW the framework evaluates
element-wise arithmetic and conditionals on list columns.

Read: bindings/python/gaspatchio_core/column/column_proxy.py, expression_proxy.py, dispatch.py,
condition_expression.py, _dispatch_*.py, shape.py; bindings/python/gaspatchio_core/functions/conditional.py,
vector.py; bindings/python/gaspatchio_core/frame/base.py, execution.py, and frame/graph/* (there is a
calc_graph execution layer — understand what it does at collect time).
Rust: core/src/polars_functions/list_conditional.rs, list_pow.rs, list_clip.rs, accumulate.rs, vector.rs.

CRITICAL QUESTIONS:
  1. For 'list * list' / 'list - list', does it use Polars native list arithmetic, or list.eval(per-list closure),
     or explode-both-then-implode, or a custom plugin? Per-op explode/implode or per-list Python-less closures
     are O(rows) allocations repeated for EVERY formula line — a dominant, general cost.
  2. THE ARCHITECTURAL HYPOTHESIS: during Phase 3 (projection calc), could the framework hold data in FLAT
     long-form (policy×period rows, scalar Float64 columns) and do all arithmetic as NATIVE vectorized column
     ops (zero per-op list overhead), imploding back to List columns only once at collect()? Assess feasibility
     given jagged per-policy timelines (variable list lengths) and the when/then broadcasting semantics.
     Estimate the multiple if Phase-3 arithmetic is currently list-wise.
  3. when/then/otherwise on list columns: implementation + per-call cost.
Return findings via StructuredOutput.`,
  },
  {
    id: 'projection-accessors',
    prompt: `${COMMON}
LANE: Projection accessors + timeline + rollforward kernel.

Hot operations: cumulative_survival() (cumulative product over each list), previous_period()/next_period()/
at_period() (shift within each list), create_projection_timeline (builds the list scaffolding), and the
jagged per-policy rollforward state machine (this branch made jagged the DEFAULT — check the cost of that).

Read: bindings/python/gaspatchio_core/accessors/* (projection accessor, date accessor),
bindings/python/gaspatchio_core/rollforward/* (grep for the dir), functions/vector.py;
Rust: core/src/polars_functions/accumulate.rs, vector.rs, rollforward.rs, list_pow.rs.

Evaluate:
  (a) cumulative_survival / accumulate: does it allocate a fresh buffer + rebuild ListChunked, or can it write
      in place over the inner values reusing offsets? Is it elementwise-streamable?
  (b) previous_period/at_period shift: a shift-by-k within each list is pure offset arithmetic on the inner
      array — is it currently implemented as a full copy (e.g. Polars list.shift / gather) instead?
  (c) Jagged-by-default cost: did making per_policy jagged the default add per-policy branching / lost
      vectorization / extra allocations vs the old uniform-timeline path? Quantify the regression if any
      (the user is ON the branch that flipped this default — a regression here is a 'general' win to reclaim).
  (d) timeline creation allocations.
Return findings via StructuredOutput.`,
  },
  {
    id: 'plan-and-build',
    prompt: `${COMMON}
LANE: Query-plan structure, plugin streaming flags, and build configuration.

PART A — Build profile (analyse, do NOT benchmark):
  Read bindings/python/pyproject.toml ([tool.uv] config-settings, [tool.maturin]), .github/workflows/evals.yml
  (the model-benchmarks job), .github/workflows/CI.yml (wheel build), and all Cargo.toml
  (${ROOT}/Cargo.toml if it exists, core/Cargo.toml, bindings/python/Cargo.toml).
  Determine: what Rust profile does the CI 'model-benchmarks' job actually run (it does 'uv sync' then runs the
  bench)? Does '[tool.uv] config-settings build-args=--profile=dev' make 'uv sync' build a DEBUG extension,
  while shipped wheels build --release? If the dashboard measures a debug build of the custom kernels, that is a
  large, free, framework-level win. State the expected_multiple range for debug→release of the gaspatchio
  kernels (note: Polars itself is a prebuilt release dep; only gaspatchio's own Rust is affected).
  Also: there is NO [profile.release] tuning anywhere — assess lto=fat, codegen-units=1, panic=abort, and
  target-cpu (portability caveat for shipped wheels vs local) as additional build-config wins.

PART B — Plugin streaming flags:
  Grep every #[polars_expr] in core/src and every plugin registration on the Python side
  (register_plugin / is_elementwise). List any plugin that is NOT elementwise — per core/AGENTS.md, a single
  is_elementwise=False forces the WHOLE plan into in-memory execution, killing the streaming engine (documented
  as a 6x bottleneck historically). Flag any offender (cumulative ops, rollforward).

PART C — Query-plan node count:
  In bindings/python/gaspatchio_core/frame/base.py + execution.py + frame/graph/*, determine how 'af.x = expr'
  accumulates into the lazy plan. AGENTS.md mentions '54 chained with_columns nodes'. Could independent columns
  be batched into fewer with_columns (fewer plan nodes → less optimizer + materialization overhead)? Is there
  common-subexpression duplication (e.g. pols_if recomputed)? Estimate the multiple.
Return findings via StructuredOutput.`,
  },
]

const mapResults = await parallel(
  lanes.map((l) => () =>
    agent(l.prompt, { label: `map:${l.id}`, phase: 'Map', schema: FINDINGS_SCHEMA })
  )
)

const valid = mapResults.filter(Boolean)
log(`Map complete: ${valid.length}/${lanes.length} lanes returned; ${valid.reduce((n, r) => n + (r.findings?.length || 0), 0)} findings`)

phase('Synthesize')

const SYNTH_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['ranked_spikes', 'combined_ceiling', 'narrative'],
  properties: {
    combined_ceiling: { type: 'string', description: 'realistic combined throughput multiple if the top independent wins are stacked, with reasoning about overlap' },
    narrative: { type: 'string', description: '3-6 sentence executive read: where the time goes, the single biggest lever, and whether 2x is plausibly reachable on framework-only changes' },
    ranked_spikes: {
      type: 'array',
      description: 'ordered best-first; the top 3-4 are what Workflow 2 will actually implement+measure',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['rank', 'id', 'title', 'scope', 'expected_multiple', 'confidence', 'spike_spec', 'measure', 'independent_of', 'needs_rust_build'],
        properties: {
          rank: { type: 'number' },
          id: { type: 'string' },
          title: { type: 'string' },
          scope: { type: 'string' },
          expected_multiple: { type: 'string' },
          confidence: { type: 'string', enum: ['low', 'medium', 'high'] },
          spike_spec: { type: 'string', description: 'precise, minimal, ready-to-run implementation steps: exact files/functions, the change, how to keep it correct (preserve jagged + reconciliation). Small enough to build+measure in one warm incremental rebuild.' },
          measure: { type: 'string', description: 'exact command(s) to benchmark + the output column equivalence check to prove correctness was preserved' },
          independent_of: { type: 'string', description: 'which other spikes this overlaps/double-counts with' },
          needs_rust_build: { type: 'boolean' },
        },
      },
    },
  },
}

const synth = await agent(
  `${COMMON}
You are the synthesis lane. Below are the four map lanes' structured findings. Produce a RANKED set of spike
specs for the deep performance work. Rank by (realistic expected_multiple × confidence), preferring GENERAL,
INDEPENDENT, high-leverage changes. Separate the free build-config win from the algorithmic wins (don't let the
build win mask the algorithmic ones — the user explicitly wants the deep framework work, not just the release flag).
For the combined_ceiling, reason about which wins overlap (e.g. zero-copy lookup and long-form representation may
both target the same explode cost) so you don't multiply double-counted gains.
Each top spike's spike_spec must be concrete enough that an implementer can apply it in ONE warm incremental
rebuild and measure it, and must say how to preserve correctness (jagged per-policy timelines + lifelib reconciliation).

MAP FINDINGS (JSON):
${JSON.stringify(valid, null, 2)}

Return via StructuredOutput.`,
  { label: 'synthesize', phase: 'Synthesize', schema: SYNTH_SCHEMA }
)

return { map: valid, synthesis: synth }
