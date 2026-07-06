// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

//! Rollforward kernel — consumes the LowerToPolarsPlugin kwargs schema.
//!
//! Schema (JSON-decoded):
//!   ir:                          canonical-form dict (states, points, transitions, …)
//!   captures:                    Vec<[state, point]> in slot order
//!   track_increments:            bool
//!   lapse_when_all_non_positive: Vec<String> (sorted)
//!   contract_boundary:           Option<String> (Polars Expr serialised string)
//!   n_states, n_points, n_periods: usize
//!   bop_idx, eop_idx:            usize indices into ir.points
//!   input_columns:               Vec<String> (column names referenced by Ops)
//!   ops:                         Vec<OpV2> with arg-indices
//!   captures_resolved:           Vec<CaptureSlot> (state-index, point-index)
//!
//! The kernel walks transitions in declared order per period, evaluating
//! each Op against the current per-row state vector. Output is a Polars
//! Struct with one field per capture slot (named `"{state}@{point}"`) —
//! plus one field per labelled increment when track_increments=True
//! (increment emission is not yet implemented).

use polars::prelude::*;
use polars_arrow::array::PrimitiveArray;
use polars_arrow::offset::OffsetsBuffer;
use serde::Deserialize;

/// Plugin kwargs payload — direct mirror of the dict produced by
/// `LowerToPolarsPlugin.lower(ir, slots)` in
/// `gaspatchio_core.rollforward._passes`.
#[derive(Deserialize)]
pub struct RollforwardKwargs {
    pub ir: serde_json::Value,
    pub captures: Vec<Vec<String>>,
    pub track_increments: bool,
    pub lapse_when_all_non_positive: Vec<String>,
    pub contract_boundary: Option<String>,
    pub n_states: usize,
    pub n_points: usize,
    pub n_periods: usize,
    pub bop_idx: usize,
    pub eop_idx: usize,
    pub input_columns: Vec<String>,
    pub ops: Vec<OpV2>,
    pub captures_resolved: Vec<CaptureSlot>,
    #[serde(default)]
    pub lapse_state_indices: Vec<usize>,
    #[serde(default)]
    pub contract_boundary_arg: Option<usize>,
    /// Index (into `inputs`, after the state inits and input columns) of an
    /// i64 column giving each policy's authoritative period count. Set by the
    /// lowering for `per_policy_grid` schedules so the kernel sizes each
    /// policy's projection from its own horizon — even when there are no input
    /// list columns to infer length from. `None` => uniform (use `n_periods`).
    #[serde(default)]
    pub per_policy_lengths_arg: Option<usize>,
}

/// Resolved (state, point) capture slot — indices into ir.states / ir.points.
#[derive(Deserialize)]
pub struct CaptureSlot {
    pub state: usize,
    pub point: usize,
}

/// Op enum — mirrors the typed Op classes in
/// `gaspatchio_core.rollforward._ops`. Tag is the bare class name; payload
/// fields use pre-resolved arg-indices (state, point, input-column slots) so
/// the kernel's hot loop never does string lookups.
///
/// Every ``*_arg`` field is an ``ArgRef``. ``ArgRef::Input { idx }`` reads
/// from a precomputed list-column input; ``ArgRef::State { state, point }``
/// reads from the live per-row state vector — the value most recently
/// written to ``(state, point)`` during this period's Op walk (or carried
/// from t-1).
#[derive(Deserialize, Clone, Copy, Debug)]
#[serde(tag = "kind")]
#[serde(rename_all = "lowercase")]
pub enum ArgRef {
    Input { idx: usize },
    State { state: usize, point: usize },
}

#[derive(Deserialize)]
#[serde(tag = "op")]
pub enum OpV2 {
    Add {
        target_state: usize,
        target_point: usize,
        expr_arg: ArgRef,
        label: Option<String>,
    },
    Subtract {
        target_state: usize,
        target_point: usize,
        expr_arg: ArgRef,
        label: Option<String>,
    },
    Charge {
        target_state: usize,
        target_point: usize,
        rate_arg: ArgRef,
        label: Option<String>,
    },
    Grow {
        target_state: usize,
        target_point: usize,
        rate_arg: ArgRef,
        label: Option<String>,
    },
    GrowCapped {
        target_state: usize,
        target_point: usize,
        rate_arg: ArgRef,
        floor_arg: ArgRef,
        cap_arg: ArgRef,
        label: Option<String>,
    },
    DeductNAR {
        target_state: usize,
        target_point: usize,
        coi_rate_arg: ArgRef,
        death_benefit_arg: ArgRef,
        label: Option<String>,
    },
    Ratchet {
        target_state: usize,
        target_point: usize,
        to_arg: ArgRef,
        when_arg: Option<ArgRef>,
        label: Option<String>,
    },
    Floor {
        target_state: usize,
        target_point: usize,
        value: f64,
    },
    Apply {
        target_state: usize,
        target_point: usize,
        body_arg: ArgRef,
        label: Option<String>,
    },
}

/// Owned per-row List<Float64> input slice — offsets + flat values.
struct OwnedListSlice {
    offsets: Vec<i64>,
    values: Vec<f64>,
}

/// Plugin entry point — the function Polars discovers via the
/// `#[polars_expr]` wrapper in `bindings/python/src/vector.rs`.
pub fn rollforward_kernel(inputs: &[Series], kwargs: &RollforwardKwargs) -> PolarsResult<Series> {
    let n_states = kwargs.n_states;
    let n_points = kwargs.n_points;
    let n_periods = kwargs.n_periods;
    let bop_idx = kwargs.bop_idx;
    let eop_idx = kwargs.eop_idx;

    if n_states == 0 {
        return Err(PolarsError::ComputeError(
            "rollforward: at least one state is required".into(),
        ));
    }
    let n_extra = usize::from(kwargs.per_policy_lengths_arg.is_some());
    if inputs.len() != n_states + kwargs.input_columns.len() + n_extra {
        return Err(PolarsError::ComputeError(
            format!(
                "rollforward: expected {} inputs (n_states={} + input_columns={} \
                 + per_policy_lengths={}); got {}",
                n_states + kwargs.input_columns.len() + n_extra,
                n_states,
                kwargs.input_columns.len(),
                n_extra,
                inputs.len()
            )
            .into(),
        ));
    }

    // ---- 1. Extract state-init scalars ----
    // Each is Float64-cast-able; broadcast-of-1 or per-row.
    let mut init_owned: Vec<Series> = Vec::with_capacity(n_states);
    for s in 0..n_states {
        let init = inputs[s].cast(&DataType::Float64)?;
        init_owned.push(init);
    }
    let init_slices: Vec<(Vec<f64>, bool)> = init_owned
        .iter()
        .map(|s| {
            let ca = s.f64()?;
            if ca.null_count() > 0 {
                return Err(PolarsError::ComputeError(
                    "rollforward: null state-init values not yet supported".into(),
                ));
            }
            let rechunked = ca.rechunk();
            let slice = rechunked
                .cont_slice()
                .map_err(|_| {
                    PolarsError::ComputeError(
                        "rollforward: state-init values not contiguous".into(),
                    )
                })?
                .to_vec();
            let is_broadcast = slice.len() == 1;
            Ok((slice, is_broadcast))
        })
        .collect::<PolarsResult<Vec<_>>>()?;

    // ---- 2. Extract input List<Float64> columns ----
    let mut owned_slices: Vec<OwnedListSlice> = Vec::with_capacity(kwargs.input_columns.len());
    for (i, _name) in kwargs.input_columns.iter().enumerate() {
        let series = &inputs[n_states + i];
        let list_ca = series.list().map_err(|_| {
            PolarsError::ComputeError(
                format!(
                    "rollforward: input column {} (arg index {}) must be List dtype",
                    kwargs.input_columns[i],
                    n_states + i
                )
                .into(),
            )
        })?;
        if list_ca.null_count() > 0 {
            return Err(PolarsError::ComputeError(
                format!(
                    "rollforward: null outer list at input column {} not supported",
                    kwargs.input_columns[i]
                )
                .into(),
            ));
        }
        let rechunked = list_ca.rechunk();
        let arr = rechunked.downcast_iter().next().ok_or_else(|| {
            PolarsError::ComputeError(
                format!(
                    "rollforward: empty chunk for input column {}",
                    kwargs.input_columns[i]
                )
                .into(),
            )
        })?;
        let offsets = arr.offsets().as_slice().to_vec();
        let values_series = Series::from_arrow(PlSmallStr::EMPTY, arr.values().clone())?
            .cast(&DataType::Float64)?;
        let values_f64 = values_series.f64()?;
        if values_f64.null_count() > 0 {
            return Err(PolarsError::ComputeError(
                format!(
                    "rollforward: null inner values at input column {} not supported",
                    kwargs.input_columns[i]
                )
                .into(),
            ));
        }
        let values_rechunked = values_f64.rechunk();
        let values = values_rechunked
            .cont_slice()
            .map_err(|_| {
                PolarsError::ComputeError(
                    format!(
                        "rollforward: values not contiguous at input column {}",
                        kwargs.input_columns[i]
                    )
                    .into(),
                )
            })?
            .to_vec();
        owned_slices.push(OwnedListSlice { offsets, values });
    }

    // ---- 2b. Authoritative per-policy period counts (per_policy_grid) ----
    // When set, this is the single source of truth for each policy's horizon —
    // not inferred from whichever input column happens to be first — so a
    // jagged rollforward sizes correctly even with no input list columns.
    let per_policy_lengths: Option<Vec<i64>> = match kwargs.per_policy_lengths_arg {
        Some(idx) => {
            let s = inputs[idx].cast(&DataType::Int64)?;
            let ca = s.i64()?;
            if ca.null_count() > 0 {
                return Err(PolarsError::ComputeError(
                    "rollforward: null per-policy length not supported".into(),
                ));
            }
            Some(
                ca.rechunk()
                    .cont_slice()
                    .map_err(|_| {
                        PolarsError::ComputeError(
                            "rollforward: per-policy lengths not contiguous".into(),
                        )
                    })?
                    .to_vec(),
            )
        }
        None => None,
    };

    // ---- 3. Determine number of rows ----
    let num_rows = if let Some(ref lengths) = per_policy_lengths {
        lengths.len()
    } else if !owned_slices.is_empty() {
        owned_slices[0].offsets.len() - 1
    } else if init_slices[0].1 {
        // broadcast: only 1 logical row (caller will broadcast the result)
        1
    } else {
        init_slices[0].0.len()
    };

    // ---- 3b. Uniform-schedule footgun guard ----
    // A uniform (non per-policy-grid) schedule means every policy shares one
    // horizon = n_periods. If EVERY policy's input lists instead share one
    // length L that disagrees with n_periods, that is almost certainly a
    // uniform book fed stale/short inputs — fail loudly rather than silently
    // truncating the whole projection to L. Genuinely jagged books have inputs
    // whose lengths VARY across policies (handled per-row below), so they are
    // deliberately left untouched by this check.
    if per_policy_lengths.is_none() && !owned_slices.is_empty() && num_rows > 0 {
        let first = &owned_slices[0];
        let row_len = |r: usize| (first.offsets[r + 1] - first.offsets[r]) as usize;
        let l0 = row_len(0);
        if (1..num_rows).all(|r| row_len(r) == l0) && l0 != n_periods {
            return Err(PolarsError::ComputeError(
                format!(
                    "rollforward: every policy's input lists have length {l0}, but the \
                     schedule's n_periods is {n_periods}. For a uniform book the input list \
                     columns must have n_periods = {n_periods} elements per policy. Fix: set \
                     the Schedule's n_periods to {l0}, or build the inputs with {n_periods} \
                     elements per policy. If policies genuinely have different horizons, use a \
                     per-policy grid (af.projection.set(..., per_policy=True)) so input lengths \
                     may vary across policies."
                )
                .into(),
            ));
        }
    }

    // ---- 4. Decode state names (for output field names) ----
    let state_names: Vec<String> = decode_state_names(&kwargs.ir)?;
    let point_names: Vec<String> = decode_point_names(&kwargs.ir)?;

    // ---- 5. Per-capture output buffers ----
    let n_captures = kwargs.captures_resolved.len();
    let total_len = num_rows * n_periods;
    let mut capture_values: Vec<Vec<f64>> = (0..n_captures)
        .map(|_| Vec::with_capacity(total_len))
        .collect();
    let mut capture_offsets: Vec<Vec<i64>> = (0..n_captures)
        .map(|_| {
            let mut v = Vec::with_capacity(num_rows + 1);
            v.push(0i64);
            v
        })
        .collect();

    // ---- 6. Per-row state walk ----
    // Jagged-aware: each policy projects over its OWN period count. The
    // recurrence value[t] = f(value[t-1], inputs[t]) has no cross-policy
    // coupling — every read is policy-relative (offsets[row]+t) — so a
    // policy's local `t` indexes its own input lists correctly regardless of
    // any other policy's length. Per-row state[s][p][t] flat index:
    //   s * (n_points * row_periods) + p * row_periods + t
    // `kwargs.n_periods` is a portfolio-max capacity hint only, not a per-row
    // invariant; the uniform path is the special case row_periods == n_periods.
    for row_idx in 0..num_rows {
        // This policy's period count. Priority: (1) the authoritative
        // schedule-supplied per-policy length, (2) the length of the first
        // input list, (3) the kwargs n_periods (broadcast / state-init-only,
        // uniform schedules). Every input column must then agree with it
        // WITHIN the row — a length mismatch (e.g. a feeder built one period
        // too long, or disagreeing with the schedule) is rejected loudly.
        let row_periods = if let Some(ref lengths) = per_policy_lengths {
            usize::try_from(lengths[row_idx]).map_err(|_| {
                PolarsError::ComputeError(
                    format!("rollforward: negative per-policy length at row {row_idx}").into(),
                )
            })?
        } else if owned_slices.is_empty() {
            n_periods
        } else {
            let first = &owned_slices[0];
            first.offsets[row_idx + 1] as usize - first.offsets[row_idx] as usize
        };
        for (slot_idx, slice) in owned_slices.iter().enumerate() {
            let s = slice.offsets[row_idx] as usize;
            let e = slice.offsets[row_idx + 1] as usize;
            let len = e - s;
            if len != row_periods {
                return Err(PolarsError::ComputeError(
                    format!(
                        "rollforward: input column {} row {}: list length {} != row period \
                         count {} (all input columns must share one length within a policy)",
                        kwargs.input_columns[slot_idx], row_idx, len, row_periods
                    )
                    .into(),
                ));
            }
        }

        // Zero-period policy (e.g. a fully matured / zero-term row): emit an
        // empty capture list and skip — the state buffer would be empty, so the
        // init write below must not run.
        if row_periods == 0 {
            for cap_idx in 0..n_captures {
                capture_offsets[cap_idx].push(capture_values[cap_idx].len() as i64);
            }
            continue;
        }

        // Per-row flat-index strides — keyed off THIS policy's length.
        let stride_state = n_points * row_periods;
        let stride_point = row_periods;

        // Initialise the per-row state buffer (sized to this policy's length).
        let mut state: Vec<f64> = vec![0.0; n_states * n_points * row_periods];
        for (s, (slice, is_broadcast)) in init_slices.iter().enumerate() {
            let init_val = if *is_broadcast {
                slice[0]
            } else {
                slice[row_idx]
            };
            // state[s][bop][0] = init
            state[s * stride_state + bop_idx * stride_point] = init_val;
        }

        // Walk periods. ``stopped`` flips True the first time a stop
        // condition fires; subsequent periods write zeros to all cells.
        let mut stopped = false;
        for t in 0..row_periods {
            if stopped {
                // Already stopped — leave state cells at 0 for this period.
                continue;
            }

            // Carry-forward bop = previous eop (for t > 0).
            if t > 0 {
                for s in 0..n_states {
                    let prev_eop = state[s * stride_state + eop_idx * stride_point + (t - 1)];
                    state[s * stride_state + bop_idx * stride_point + t] = prev_eop;
                }
            }

            // contract_boundary fires AT the period boundary (before Ops):
            // if the mask is True at t, this period and all later periods
            // are zeroed.
            if let Some(boundary_arg) = kwargs.contract_boundary_arg {
                let mask_val = read_list_at(&owned_slices, boundary_arg, row_idx, t);
                if mask_val != 0.0 {
                    // Zero this period across all states/points.
                    for s in 0..n_states {
                        for p in 0..n_points {
                            state[s * stride_state + p * stride_point + t] = 0.0;
                        }
                    }
                    stopped = true;
                    continue;
                }
            }

            // Seed every point cell from bop so Ops chain correctly within
            // the period — supports between() Ops writing to mid-period points.
            for s in 0..n_states {
                let bop_val = state[s * stride_state + bop_idx * stride_point + t];
                for p in 0..n_points {
                    if p == bop_idx {
                        continue;
                    }
                    state[s * stride_state + p * stride_point + t] = bop_val;
                }
            }

            // Apply Ops in declared order. After each Op, propagate the new
            // (state, target_point) value to all later points in declared
            // order so subsequent Ops chain correctly.
            for op in &kwargs.ops {
                apply_op(
                    op,
                    &mut state,
                    t,
                    &owned_slices,
                    row_idx,
                    stride_state,
                    stride_point,
                )?;
                let (op_target_state, op_target_point) = op_target(op);
                let new_val =
                    state[op_target_state * stride_state + op_target_point * stride_point + t];
                for p in (op_target_point + 1)..n_points {
                    state[op_target_state * stride_state + p * stride_point + t] = new_val;
                }
            }

            // lapse_when_all_non_positive fires AFTER the period's Op walk:
            // if every named state's eop is <= 0, this period's values are
            // kept (the lapse triggers at this boundary), and all subsequent
            // periods are zeroed.
            if !kwargs.lapse_state_indices.is_empty() {
                let all_lapsed = kwargs
                    .lapse_state_indices
                    .iter()
                    .all(|&s| state[s * stride_state + eop_idx * stride_point + t] <= 0.0);
                if all_lapsed {
                    stopped = true;
                }
            }
        }

        // Emit per-capture per-row lists.
        for (cap_idx, cap) in kwargs.captures_resolved.iter().enumerate() {
            let base = cap.state * stride_state + cap.point * stride_point;
            for t in 0..row_periods {
                capture_values[cap_idx].push(state[base + t]);
            }
            capture_offsets[cap_idx].push(capture_values[cap_idx].len() as i64);
        }
    }

    // ---- 7. Build output Struct ----
    let mut output_series: Vec<Series> = Vec::with_capacity(n_captures);
    for (cap_idx, cap) in kwargs.captures_resolved.iter().enumerate() {
        let state_name = &state_names[cap.state];
        let point_name = &point_names[cap.point];
        let field_name = format!("{}@{}", state_name, point_name);
        let values = std::mem::take(&mut capture_values[cap_idx]);
        let offsets_vec = std::mem::take(&mut capture_offsets[cap_idx]);
        output_series.push(build_list_series(values, offsets_vec, field_name.as_str())?);
    }

    let struct_chunked = StructChunked::from_series(
        PlSmallStr::from_static("rollforward"),
        num_rows,
        output_series.iter(),
    )?;
    Ok(struct_chunked.into_series())
}

/// Apply a single Op to the per-row state buffer at period ``t``.
fn apply_op(
    op: &OpV2,
    state: &mut [f64],
    t: usize,
    owned_slices: &[OwnedListSlice],
    row_idx: usize,
    stride_state: usize,
    stride_point: usize,
) -> PolarsResult<()> {
    match op {
        OpV2::Add {
            target_state,
            target_point,
            expr_arg,
            ..
        } => {
            let v = resolve_arg(
                *expr_arg,
                owned_slices,
                state,
                row_idx,
                t,
                stride_state,
                stride_point,
            );
            let i = *target_state * stride_state + *target_point * stride_point + t;
            state[i] += v;
            Ok(())
        }
        OpV2::Subtract {
            target_state,
            target_point,
            expr_arg,
            ..
        } => {
            let v = resolve_arg(
                *expr_arg,
                owned_slices,
                state,
                row_idx,
                t,
                stride_state,
                stride_point,
            );
            let i = *target_state * stride_state + *target_point * stride_point + t;
            state[i] -= v;
            Ok(())
        }
        OpV2::Charge {
            target_state,
            target_point,
            rate_arg,
            ..
        } => {
            let r = resolve_arg(
                *rate_arg,
                owned_slices,
                state,
                row_idx,
                t,
                stride_state,
                stride_point,
            );
            let i = *target_state * stride_state + *target_point * stride_point + t;
            state[i] *= 1.0 - r;
            Ok(())
        }
        OpV2::Grow {
            target_state,
            target_point,
            rate_arg,
            ..
        } => {
            // schedule dt is not threaded through yet — rates are taken
            // as-quoted on the input list, period-by-period.
            let r = resolve_arg(
                *rate_arg,
                owned_slices,
                state,
                row_idx,
                t,
                stride_state,
                stride_point,
            );
            let i = *target_state * stride_state + *target_point * stride_point + t;
            state[i] *= 1.0 + r;
            Ok(())
        }
        OpV2::Floor {
            target_state,
            target_point,
            value,
        } => {
            let i = *target_state * stride_state + *target_point * stride_point + t;
            if state[i] < *value {
                state[i] = *value;
            }
            Ok(())
        }
        OpV2::GrowCapped {
            target_state,
            target_point,
            rate_arg,
            floor_arg,
            cap_arg,
            ..
        } => {
            // schedule dt is not threaded through yet.
            let r = resolve_arg(
                *rate_arg,
                owned_slices,
                state,
                row_idx,
                t,
                stride_state,
                stride_point,
            );
            let f = resolve_arg(
                *floor_arg,
                owned_slices,
                state,
                row_idx,
                t,
                stride_state,
                stride_point,
            );
            let c = resolve_arg(
                *cap_arg,
                owned_slices,
                state,
                row_idx,
                t,
                stride_state,
                stride_point,
            );
            let clamped = r.clamp(f, c);
            let i = *target_state * stride_state + *target_point * stride_point + t;
            state[i] *= 1.0 + clamped;
            Ok(())
        }
        OpV2::DeductNAR {
            target_state,
            target_point,
            coi_rate_arg,
            death_benefit_arg,
            ..
        } => {
            let coi = resolve_arg(
                *coi_rate_arg,
                owned_slices,
                state,
                row_idx,
                t,
                stride_state,
                stride_point,
            );
            let db = resolve_arg(
                *death_benefit_arg,
                owned_slices,
                state,
                row_idx,
                t,
                stride_state,
                stride_point,
            );
            let i = *target_state * stride_state + *target_point * stride_point + t;
            // Net amount at risk = death_benefit - state; charge coi over NAR.
            state[i] -= coi * (db - state[i]);
            Ok(())
        }
        OpV2::Ratchet {
            target_state,
            target_point,
            to_arg,
            when_arg,
            ..
        } => {
            let fire = match when_arg {
                Some(arg) => {
                    resolve_arg(
                        *arg,
                        owned_slices,
                        state,
                        row_idx,
                        t,
                        stride_state,
                        stride_point,
                    ) != 0.0
                }
                None => true,
            };
            if fire {
                let to_val = resolve_arg(
                    *to_arg,
                    owned_slices,
                    state,
                    row_idx,
                    t,
                    stride_state,
                    stride_point,
                );
                let i = *target_state * stride_state + *target_point * stride_point + t;
                if to_val > state[i] {
                    state[i] = to_val;
                }
            }
            Ok(())
        }
        OpV2::Apply { .. } => Err(PolarsError::ComputeError(
            "rollforward: Apply is an escape hatch and is not yet \
             evaluable by the kernel"
                .into(),
        )),
    }
}

/// Resolve an ``ArgRef`` to a scalar f64 value at (row, period). For Input,
/// reads from the precomputed list-column slice. For State, reads from the
/// live per-row state vector — i.e. the most-recently-written value at
/// ``(state, point)`` for this period.
#[inline]
fn resolve_arg(
    arg: ArgRef,
    owned_slices: &[OwnedListSlice],
    state: &[f64],
    row_idx: usize,
    t: usize,
    stride_state: usize,
    stride_point: usize,
) -> f64 {
    match arg {
        ArgRef::Input { idx } => read_list_at(owned_slices, idx, row_idx, t),
        ArgRef::State { state: s, point: p } => state[s * stride_state + p * stride_point + t],
    }
}

/// Return the (target_state, target_point) for an Op so the period walker
/// can propagate the post-Op value to later points.
fn op_target(op: &OpV2) -> (usize, usize) {
    match op {
        OpV2::Add {
            target_state,
            target_point,
            ..
        }
        | OpV2::Subtract {
            target_state,
            target_point,
            ..
        }
        | OpV2::Charge {
            target_state,
            target_point,
            ..
        }
        | OpV2::Grow {
            target_state,
            target_point,
            ..
        }
        | OpV2::GrowCapped {
            target_state,
            target_point,
            ..
        }
        | OpV2::DeductNAR {
            target_state,
            target_point,
            ..
        }
        | OpV2::Ratchet {
            target_state,
            target_point,
            ..
        }
        | OpV2::Floor {
            target_state,
            target_point,
            ..
        }
        | OpV2::Apply {
            target_state,
            target_point,
            ..
        } => (*target_state, *target_point),
    }
}

/// Read a list-arg's value at (row_idx, t).
fn read_list_at(owned_slices: &[OwnedListSlice], arg_idx: usize, row_idx: usize, t: usize) -> f64 {
    let slice = &owned_slices[arg_idx];
    let flat_idx = slice.offsets[row_idx] as usize + t;
    // Jagged-safety: t must stay within THIS row's slice (offsets[row]..offsets[row+1]).
    debug_assert!(
        flat_idx < slice.offsets[row_idx + 1] as usize,
        "rollforward: period index {t} out of row {row_idx}'s list bounds"
    );
    slice.values[flat_idx]
}

/// Build a List<Float64> Series from flat values + offsets.
fn build_list_series(
    flat_values: Vec<f64>,
    offsets_vec: Vec<i64>,
    name: &str,
) -> PolarsResult<Series> {
    let offsets = OffsetsBuffer::try_from(offsets_vec)
        .map_err(|e| PolarsError::ComputeError(format!("invalid offsets: {e}").into()))?;
    let values_arr = PrimitiveArray::from_vec(flat_values);
    let list_arr = LargeListArray::new(
        ArrowDataType::LargeList(Box::new(ArrowField::new(
            PlSmallStr::from_static("item"),
            ArrowDataType::Float64,
            true,
        ))),
        offsets,
        Box::new(values_arr),
        None,
    );
    let series = Series::from_arrow(PlSmallStr::from(name), Box::new(list_arr))?;
    Ok(series)
}

/// Decode state names from the canonical-form ir["states"][i]["name"].
fn decode_state_names(ir: &serde_json::Value) -> PolarsResult<Vec<String>> {
    let states = ir.get("states").and_then(|v| v.as_array()).ok_or_else(|| {
        PolarsError::ComputeError("rollforward: kwargs.ir.states missing or not an array".into())
    })?;
    let mut names = Vec::with_capacity(states.len());
    for st in states {
        let name = st.get("name").and_then(|v| v.as_str()).ok_or_else(|| {
            PolarsError::ComputeError("rollforward: ir.states[i].name missing".into())
        })?;
        names.push(name.to_string());
    }
    Ok(names)
}

/// Decode point names from the canonical-form ir["points"].
fn decode_point_names(ir: &serde_json::Value) -> PolarsResult<Vec<String>> {
    let points = ir.get("points").and_then(|v| v.as_array()).ok_or_else(|| {
        PolarsError::ComputeError("rollforward: kwargs.ir.points missing or not an array".into())
    })?;
    let mut names = Vec::with_capacity(points.len());
    for p in points {
        let name = p.as_str().ok_or_else(|| {
            PolarsError::ComputeError("rollforward: ir.points entry not str".into())
        })?;
        names.push(name.to_string());
    }
    Ok(names)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn deserialise_minimal_kwargs() {
        let json = r#"{
            "ir": {"states": [], "points": ["bop", "eop"], "transitions": []},
            "captures": [["av", "eop"]],
            "track_increments": false,
            "lapse_when_all_non_positive": [],
            "contract_boundary": null,
            "n_states": 0,
            "n_points": 2,
            "n_periods": 3,
            "bop_idx": 0,
            "eop_idx": 1,
            "input_columns": [],
            "ops": [],
            "captures_resolved": []
        }"#;
        let kwargs: RollforwardKwargs = serde_json::from_str(json).unwrap();
        assert_eq!(kwargs.captures.len(), 1);
        assert_eq!(
            kwargs.captures[0],
            vec!["av".to_string(), "eop".to_string()]
        );
        assert!(!kwargs.track_increments);
        assert!(kwargs.lapse_when_all_non_positive.is_empty());
        assert!(kwargs.contract_boundary.is_none());
        assert_eq!(kwargs.n_periods, 3);
        assert_eq!(kwargs.bop_idx, 0);
        assert_eq!(kwargs.eop_idx, 1);
    }

    #[test]
    fn deserialise_op_add_input_arg() {
        let json = r#"{
            "op": "Add",
            "target_state": 0,
            "target_point": 1,
            "expr_arg": {"kind": "input", "idx": 0},
            "label": "Premium"
        }"#;
        let op: OpV2 = serde_json::from_str(json).unwrap();
        match op {
            OpV2::Add {
                target_state,
                target_point,
                expr_arg,
                label,
            } => {
                assert_eq!(target_state, 0);
                assert_eq!(target_point, 1);
                match expr_arg {
                    ArgRef::Input { idx } => assert_eq!(idx, 0),
                    _ => panic!("expected ArgRef::Input"),
                }
                assert_eq!(label.as_deref(), Some("Premium"));
            }
            _ => panic!("expected Add"),
        }
    }

    #[test]
    fn deserialise_op_ratchet_state_arg() {
        // Cross-state read — Ratchet whose `to` references another
        // state's value at a specific point.
        let json = r#"{
            "op": "Ratchet",
            "target_state": 1,
            "target_point": 1,
            "to_arg": {"kind": "state", "state": 0, "point": 2},
            "when_arg": {"kind": "input", "idx": 0},
            "label": "GMDB"
        }"#;
        let op: OpV2 = serde_json::from_str(json).unwrap();
        match op {
            OpV2::Ratchet {
                target_state,
                target_point,
                to_arg,
                when_arg,
                label,
            } => {
                assert_eq!(target_state, 1);
                assert_eq!(target_point, 1);
                match to_arg {
                    ArgRef::State { state, point } => {
                        assert_eq!(state, 0);
                        assert_eq!(point, 2);
                    }
                    _ => panic!("expected ArgRef::State"),
                }
                match when_arg {
                    Some(ArgRef::Input { idx }) => assert_eq!(idx, 0),
                    _ => panic!("expected Some(ArgRef::Input)"),
                }
                assert_eq!(label.as_deref(), Some("GMDB"));
            }
            _ => panic!("expected Ratchet"),
        }
    }

    #[test]
    fn deserialise_op_floor() {
        let json = r#"{
            "op": "Floor",
            "target_state": 0,
            "target_point": 1,
            "value": 0.0
        }"#;
        let op: OpV2 = serde_json::from_str(json).unwrap();
        match op {
            OpV2::Floor {
                value,
                target_state,
                target_point,
            } => {
                assert_eq!(value, 0.0);
                assert_eq!(target_state, 0);
                assert_eq!(target_point, 1);
            }
            _ => panic!("expected Floor"),
        }
    }

    // ---- Jagged (per-policy variable-length) rollforward ----
    //
    // Single state "av", points [bop, eop]; one Op: Add premium to eop each
    // period. The recurrence is eop[t] = bop[t] + premium[t] with bop[t] =
    // eop[t-1] and bop[0] = init. This is the same linear recurrence that
    // accumulate.rs already runs on jagged input — these tests prove the
    // rollforward kernel can too once it derives each policy's period count
    // from its own list length instead of a single global n_periods.

    /// Run a single-state av rollforward capturing av@eop. ``premiums`` may be
    /// jagged (per-policy different lengths). Returns one eop list per policy.
    fn run_av_eop(init: Vec<f64>, premiums: Vec<Vec<f64>>) -> PolarsResult<Vec<Vec<f64>>> {
        let init_series = Series::new("av_init".into(), init);
        let prem_list = ListChunked::from_iter(
            premiums
                .into_iter()
                .map(|p| Some(Series::new("".into(), p))),
        )
        .into_series();

        // n_periods is the portfolio-max capacity hint; the kernel must size
        // each policy from its own list length, not assume every row == 3.
        let kwargs_json = r#"{
            "ir": {"states": [{"name": "av"}], "points": ["bop", "eop"], "transitions": []},
            "captures": [["av", "eop"]],
            "track_increments": false,
            "lapse_when_all_non_positive": [],
            "contract_boundary": null,
            "n_states": 1,
            "n_points": 2,
            "n_periods": 3,
            "bop_idx": 0,
            "eop_idx": 1,
            "input_columns": ["premium"],
            "ops": [{"op": "Add", "target_state": 0, "target_point": 1, "expr_arg": {"kind": "input", "idx": 0}, "label": "Premium"}],
            "captures_resolved": [{"state": 0, "point": 1}]
        }"#;
        let kwargs: RollforwardKwargs = serde_json::from_str(kwargs_json).unwrap();

        let out = rollforward_kernel(&[init_series, prem_list], &kwargs)?;
        let st = out.struct_().unwrap();
        let field = st.fields_as_series()[0].clone(); // "av@eop", List<Float64>
        let list = field.list().unwrap();
        let mut rows = Vec::with_capacity(list.len());
        for r in 0..list.len() {
            let s = list.get_as_series(r).unwrap();
            let f = s.f64().unwrap();
            rows.push((0..f.len()).map(|i| f.get(i).unwrap()).collect());
        }
        Ok(rows)
    }

    #[test]
    fn jagged_two_policies_different_lengths() {
        // Policy A projects 2 periods, Policy B projects 3 — a jagged frame.
        let out = run_av_eop(
            vec![100.0, 100.0],
            vec![vec![10.0, 20.0], vec![10.0, 20.0, 30.0]],
        )
        .unwrap();
        assert_eq!(out.len(), 2);
        // Policy A: 100 -> 110 -> 130, and ONLY 2 periods (no dead tail).
        assert_eq!(out[0].len(), 2, "policy A must project its own 2 periods");
        assert!((out[0][0] - 110.0).abs() < 1e-9);
        assert!((out[0][1] - 130.0).abs() < 1e-9);
        // Policy B: 100 -> 110 -> 130 -> 160, 3 periods.
        assert_eq!(out[1].len(), 3, "policy B must project its own 3 periods");
        assert!((out[1][0] - 110.0).abs() < 1e-9);
        assert!((out[1][1] - 130.0).abs() < 1e-9);
        assert!((out[1][2] - 160.0).abs() < 1e-9);
    }

    #[test]
    fn uniform_two_policies_same_length_unchanged() {
        // Regression guard: the uniform case (all policies same length) must
        // still produce the identical answer it did before the jagged change.
        let out = run_av_eop(
            vec![100.0, 100.0],
            vec![vec![10.0, 20.0, 30.0], vec![10.0, 20.0, 30.0]],
        )
        .unwrap();
        assert_eq!(out.len(), 2);
        for row in &out {
            assert_eq!(row.len(), 3);
            assert!((row[0] - 110.0).abs() < 1e-9);
            assert!((row[1] - 130.0).abs() < 1e-9);
            assert!((row[2] - 160.0).abs() < 1e-9);
        }
    }

    #[test]
    fn per_policy_lengths_drive_horizon_with_zero_period_row() {
        // Authoritative per-policy lengths [2, 0, 3] supplied via the
        // per_policy_lengths input (idx 2 = n_states 1 + 1 input column). The
        // zero-period policy must emit an EMPTY list (not panic); the others
        // project their own horizon even though the schedule has no single
        // n_periods that fits all rows.
        let init = Series::new("av_init".into(), vec![100.0, 100.0, 100.0]);
        let prem = ListChunked::from_iter([
            Some(Series::new("".into(), vec![10.0, 20.0])),
            Some(Series::new("".into(), Vec::<f64>::new())),
            Some(Series::new("".into(), vec![10.0, 20.0, 30.0])),
        ])
        .into_series();
        let lengths = Series::new("len".into(), vec![2i64, 0, 3]);
        let kwargs_json = r#"{
            "ir": {"states": [{"name": "av"}], "points": ["bop", "eop"], "transitions": []},
            "captures": [["av", "eop"]],
            "track_increments": false,
            "lapse_when_all_non_positive": [],
            "contract_boundary": null,
            "n_states": 1,
            "n_points": 2,
            "n_periods": 3,
            "bop_idx": 0,
            "eop_idx": 1,
            "input_columns": ["premium"],
            "ops": [{"op": "Add", "target_state": 0, "target_point": 1, "expr_arg": {"kind": "input", "idx": 0}, "label": "Premium"}],
            "captures_resolved": [{"state": 0, "point": 1}],
            "per_policy_lengths_arg": 2
        }"#;
        let kwargs: RollforwardKwargs = serde_json::from_str(kwargs_json).unwrap();
        let out = rollforward_kernel(&[init, prem, lengths], &kwargs).unwrap();
        let field = out.struct_().unwrap().fields_as_series()[0].clone();
        let list = field.list().unwrap();
        let row = |r: usize| -> Vec<f64> {
            let s = list.get_as_series(r).unwrap();
            let f = s.f64().unwrap();
            (0..f.len()).map(|i| f.get(i).unwrap()).collect()
        };
        assert_eq!(row(0), vec![110.0, 130.0]);
        assert!(
            row(1).is_empty(),
            "zero-period policy must emit an empty list"
        );
        assert_eq!(row(2), vec![110.0, 130.0, 160.0]);
    }
}
