# ScenarioRun streaming + progress type — Design

**Date:** 2026-06-14
**Status:** Design (awaiting review → writing-plans)
**Branch:** `design/scenario-streaming-progress` (off `develop`)

## Goal

Surface the streaming-convergence hook (`on_batch` / `progress`) on `ScenarioRun.run()`, and
turn the per-batch snapshot into a real **progress type** that answers "how far through / how
long left" — plus a small run-summary on the final result. One small forward, one shared
snapshot enrichment, one result field.

## Why

`ScenarioRun.run()` is already a thin wrapper over `for_each_scenario` (`_run.py:187-202`,
docstring: *"Run the plan via `for_each_scenario`"*), and `for_each_scenario` already
implements the entire `on_batch` / `BatchSnapshot` machinery (`_for_each.py:512-513`,
`683-703`). It simply does not accept or forward `progress` / `on_batch`. So the docs claim
that "`ScenarioRun` returns its results in one piece" describes the current *API surface*, not
a design constraint — the streaming is right there, unsurfaced.

Separately, the snapshot today carries only counts (`scenarios_done` / `total_scenarios`), so
**progress %** is computable but **ETA** is not (no timing field). Adding a single `elapsed_s`
turns the snapshot into a progress object that drives a real progress line and ETA.

## Decisions (from brainstorm, 2026-06-14)

1. **Scope: `ScenarioRun` only.** `run_aggregated` streaming is a separate follow-up (it owns
   its own policy-axis fold loop and needs a `policies_done`/`total_policies` snapshot vocab).
2. **Live channel only.** `on_batch` is pure live observation. `source_sha()`,
   `canonical_form()`, and the audit sidecar are **unchanged**. Rationale: under
   `batch_size="auto"` (the `ScenarioRun` default) batch boundaries are non-deterministic, so a
   convergence trace is not reproducible and must not live in a "reproducible" artifact.
3. **Progress type = enriched live snapshot + result metadata.** Enrich the *shared*
   `BatchSnapshot` with timing (`for_each_scenario` benefits too); add `n_batches` to the
   final `ScenarioResult` (telemetry, excluded from the plan hash).

## What already exists (so the change stays small)

- `for_each_scenario` already stamps `started = time.perf_counter()` (`_for_each.py:623`) and
  builds the final result with `wall_time_s=time.perf_counter() - started` (`_for_each.py:851`).
- `ScenarioResult` (`_result.py:40-83`) already has `wall_time_s`, `peak_rss_mb`, and
  `n_scenarios`; its docstring states result fields are **not** part of `plan_sha`. There is
  exactly **one** `ScenarioResult(...)` construction site (`_for_each.py:845`).
- So "result metadata" reduces to adding **only `n_batches`**, and snapshot `elapsed_s` is a
  one-line subtract using the existing `started`.

## Components

### 1. `ScenarioRun.run()` — surface the hooks (`scenarios/_run.py`)

Add two params mirroring `for_each_scenario` exactly, placed after `sink_dir`:

```python
def run(  # noqa: PLR0913
    self,
    af: ActuarialFrame,
    model_fn: Callable[..., ActuarialFrame],
    *,
    batch_size: int | Literal["auto"] = "auto",
    target_memory_fraction: float = 0.5,
    return_full_grid: bool = False,
    sink_dir: Path | None = None,
    progress: bool = False,
    on_batch: Callable[[BatchSnapshot], None] | None = None,
    audit: bool | Path = False,
) -> ScenarioResult:
```

Forward both into the existing `for_each_scenario(...)` call (`_run.py:190`):

```python
    result = for_each_scenario(
        af,
        scenarios=self.shocks,
        model_fn=model_fn,
        aggregations=self.aggregations,
        base_tables=self.base_tables,
        batch_size=batch_size,
        target_memory_fraction=target_memory_fraction,
        return_full_grid=return_full_grid,
        sink_dir=sink_dir,
        master_seed=self.master_seed,
        progress=progress,
        on_batch=on_batch,
        plan_sha=plan_sha,
    )
```

Import `BatchSnapshot` under `TYPE_CHECKING` in `_run.py`. Add one docstring paragraph: the
streamed partials are a **live observation channel** — `source_sha()` and the audit sidecar are
unaffected by `on_batch`; to persist a convergence trace, write it from the callback (the JSONL
pattern in the docs).

### 2. Enrich `BatchSnapshot` into a progress type (`scenarios/_for_each.py:81-108`)

Add one field and three computed properties (properties are class-level, compatible with the
existing frozen/slots dataclass):

```python
    elapsed_s: float          # wall seconds since the run started

    @property
    def fraction_done(self) -> float:
        """Fraction of real scenarios folded so far, in [0, 1]."""
        if self.total_scenarios == 0:
            return 0.0
        return self.scenarios_done / self.total_scenarios

    @property
    def eta_s(self) -> float | None:
        """Rough estimated seconds remaining; None before any progress.

        Linear extrapolation from elapsed wall time and fraction done. A guide
        only: under ``batch_size='auto'`` batch sizes vary (and the streaming
        search probes deliberately differ), so this is approximate.
        """
        if self.scenarios_done >= self.total_scenarios:
            return 0.0
        if self.scenarios_done <= 0:
            return None
        return self.elapsed_s * (self.total_scenarios / self.scenarios_done - 1.0)

    @property
    def throughput(self) -> float | None:
        """Real scenarios folded per second so far; None if no time elapsed."""
        if self.elapsed_s <= 0:
            return None
        return self.scenarios_done / self.elapsed_s
```

Populate `elapsed_s` at the snapshot construction (`_for_each.py:696-702`), reading the existing
`started` closure variable:

```python
                    BatchSnapshot(
                        batch_idx=batch_idx,
                        scenarios_done=len(folded),
                        total_scenarios=len(sids),
                        outputs=_snap_outputs,
                        peak_rss_mb=_snap_peak_mb,
                        elapsed_s=time.perf_counter() - started,
                    )
```

Update the class docstring `Attributes:` block to document `elapsed_s` and the three properties.

**Caveat to encode in the docstring:** `elapsed_s` includes streaming-search probe time, while
`scenarios_done` excludes probe scenarios, so `eta_s`/`throughput` are approximate under `auto`.

### 3. Upgrade the default `progress=True` hook (`scenarios/_for_each.py:608-615`)

Replace the bare `done/total` line with percent + ETA, using the new properties:

```python
        def _default_progress(snap: BatchSnapshot) -> None:
            eta = snap.eta_s
            tail = f" · ETA {_fmt_duration(eta)}" if eta else ""
            logger.info(
                "scenarios {}/{} ({:.0%}){}",
                snap.scenarios_done,
                snap.total_scenarios,
                snap.fraction_done,
                tail,
            )
```

Add a small module-level helper `_fmt_duration(seconds: float) -> str` rendering e.g. `"3m12s"`
/ `"45s"` / `"1h04m"`. Pure function, unit-tested.

### 4. Run-summary on `ScenarioResult` (`scenarios/_result.py` + `_for_each.py:845`)

Add one field to `ScenarioResult` (a required field, placed before the defaulted fields):

```python
    wall_time_s: float
    peak_rss_mb: float | None
    n_batches: int
    sink_dir: Path | None
    selection: SelectionDecision | None = None
    audit_path: Path | None = None
```

Set it at the single construction site (`_for_each.py:845`), where `batch_idx` already equals
the number of batches folded after the loop:

```python
    return ScenarioResult(
        ...,
        wall_time_s=time.perf_counter() - started,
        peak_rss_mb=peak_rss_mb,
        n_batches=batch_idx,
        sink_dir=sink_dir if return_full_grid else None,
        selection=selection,
    )
```

Update the `ScenarioResult` docstring to note `n_batches` is runtime metadata, not part of the
SHA (consistent with the existing `batch_size` note). No other construction site exists.

### 5. Tests (`tests/scenarios/test_run_streaming.py`, plus a snapshot-property unit test)

- **ScenarioRun streaming parity** — `ScenarioRun(...).run(on_batch=snaps.append)` fires per
  batch; final `scenarios_done == n`; mirrors the `test_for_each_streaming.py` cases through the
  plan.
- **Live-channel invariant** — `source_sha()` of the plan and the returned `plan_sha` are
  byte-identical whether or not `on_batch`/`progress` are passed (proves streaming changes no
  identity).
- **Progress type** — across batches, `snap.elapsed_s` is non-decreasing and `> 0`;
  `snap.fraction_done == snap.scenarios_done / snap.total_scenarios`; final snapshot
  `fraction_done == 1.0` and `eta_s == 0.0`.
- **`_fmt_duration` + property edge cases** (unit) — `total_scenarios == 0 → fraction 0.0`;
  `scenarios_done == 0 → eta_s is None`; `done == total → eta_s == 0.0`; `elapsed_s == 0 →
  throughput is None`; duration formatting for sub-minute / minute / hour inputs.
- **`progress=True` logs %+ETA** — capture loguru output; assert the line contains `%` (and
  `ETA` when not the final batch).
- **Raising `on_batch` does not abort** — the run completes and returns the correct aggregate.
- **Result metadata** — `result.n_batches == ceil(n / batch_size)` for an explicit
  `batch_size`; `result.wall_time_s > 0`.

### 6. Docs (`gaspatchio-docs`, separate repo)

Update `docs/concepts/scenarios/streaming-convergence.md`:
- Correct the sentence: `ScenarioRun` is no longer "returns in one piece" — it is the
  reproducible plan that **also** streams (observation only; the run's identity is unchanged).
- Update the "When to reach for `on_batch`" table row for `ScenarioRun`.
- Show progress % and ETA as first-class uses of `on_batch` (`snap.fraction_done`,
  `snap.eta_s`), and note ETA is approximate under `batch_size="auto"`.

This is a coupled cross-repo change; the spec records the exact edits, the docs PR lands in
`gaspatchio-docs`.

## Determinism / reproducibility (the invariant to protect)

`elapsed_s`, `eta_s`, `throughput`, `n_batches`, `wall_time_s`, `peak_rss_mb` are **telemetry** —
they vary every run. They live on the snapshot / result as observation, and are already outside
`plan_sha` / `canonical_form()` (those hash the plan inputs, not the result). The single
`ScenarioResult` construction site and the plan-side SHA make this automatic; the tests pin it
(the `source_sha` byte-identical invariant).

## File structure / units

| Unit | File | Responsibility |
|---|---|---|
| Hook forward | `scenarios/_run.py` | Accept + forward `progress`/`on_batch`; docstring |
| Progress snapshot | `scenarios/_for_each.py` | `elapsed_s` field, 3 properties, populate, default hook, `_fmt_duration` |
| Result metadata | `scenarios/_result.py` + `_for_each.py:845` | `n_batches` field + set it |
| Tests | `tests/scenarios/test_run_streaming.py` | parity, live-channel invariant, progress type, metadata |
| Docs | `gaspatchio-docs/.../streaming-convergence.md` | sentence + table + progress/ETA examples |

## Out of scope (captured follow-ups)

- **`run_aggregated` streaming.** Separate spec. Needs a policy-axis snapshot vocabulary
  (`policies_done`/`total_policies`) and a hook wired into `_aggregated.py`'s own fold loop
  (it does not delegate to `for_each_scenario`). The enriched `BatchSnapshot` here is the
  template; generalising it is that spec's first decision.
- **Convergence-based early stop.** Stop folding once a watched aggregation has converged within
  a threshold. Builds directly on this spec's live channel + running partials. Its own brainstorm
  because of two hard questions: (1) a statistically valid "converged" criterion (false-stop on a
  noisy tail metric ships a wrong capital number); (2) reproducibility — early stop changes the
  *actual result* and scenario count, colliding with `ScenarioRun`'s hashable identity far more
  than telemetry does.

## Non-goals

- No change to `source_sha()` / `canonical_form()` / the audit sidecar schema.
- No construction-time `on_batch` on `ScenarioRun` (run-time only, matching `for_each_scenario`).
- No `BatchSnapshot` generalisation for the policy axis (deferred with `run_aggregated`).
