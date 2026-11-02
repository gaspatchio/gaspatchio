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
//! plus, when track_increments=True, one field per Op (named
//! `"increment_{key}"`, in declared order) holding the SIGNED per-period
//! delta the Op applied to its target: negative for charges, positive for
//! credits, zero after a stop or lapse.
//!
//! EVERY Op emits, not only the ones the modeller named. A labelled Op's key
//! is its label; a structural Op — `Floor`, `Round`, which carry no label
//! field and are not flows anyone booked — emits under the synthetic key
//! `{kind}@{ordinal}`, `floor@3`, whose ordinal is the Op's 1-based position
//! in the declared chain. That is what makes `closing = opening + Σ
//! increments` the kernel's own arithmetic rather than one with a residual:
//! a floor that absorbs 1e-6 is a row on the auditor's waterfall, quoted,
//! and the amount is off the file if the step that took it emits nothing.

// Every rounding the kernel does -- the `Round` op on the balance and the
// `round_charge` knob on a charge or credit -- is Excel's ROUND over the
// value's fifteen significant digits, the one rule `.excel.round` applies to
// a column, so a rounding inside the recursion and one outside it agree.
use crate::excel::excel_round;
use polars::prelude::*;
use polars_arrow::array::PrimitiveArray;
use polars_arrow::offset::OffsetsBuffer;
use serde::Deserialize;

use super::slices::{own_rows, period_count_message, same_periods};

/// Plugin kwargs payload — direct mirror of the dict produced by
/// `LowerToPolarsPlugin.lower(ir, slots)` in
/// `gaspatchio.rollforward._passes`.
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
    /// True when the schedule declares a uniform book (`from_calendar_grid`
    /// / `from_inception`): every policy's input lists must then have exactly
    /// `n_periods` elements, checked per row. Jagged horizons require a
    /// `per_policy_grid` schedule. This is declared intent from the lowering —
    /// the kernel must never infer book shape from the batch it happens to
    /// see, because batch boundaries are an engine choice (streaming chunks)
    /// and any cross-row heuristic makes row behaviour depend on batchmates.
    #[serde(default)]
    pub require_uniform: bool,
}

/// Resolved (state, point) capture slot — indices into ir.states / ir.points.
#[derive(Deserialize)]
pub struct CaptureSlot {
    pub state: usize,
    pub point: usize,
}

/// Op enum — mirrors the typed Op classes in
/// `gaspatchio.rollforward._ops`. Tag is the bare class name; payload
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
        /// Round the computed charge (half away from zero) to this many
        /// decimals before applying it, leaving the running state unrounded —
        /// the placement spreadsheets use: `s -= ROUND(s * rate, d)`.
        #[serde(default)]
        round_charge: Option<i32>,
        label: Option<String>,
    },
    Grow {
        target_state: usize,
        target_point: usize,
        rate_arg: ArgRef,
        /// Round the computed credit (half away from zero) to this many
        /// decimals before applying it, leaving the running state unrounded —
        /// the placement spreadsheets use: `s += ROUND(s * rate, d)`.
        #[serde(default)]
        round_charge: Option<i32>,
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
        /// True when the net amount at risk is measured at END of period —
        /// the COI is charged now for a benefit paid then, so the amount at
        /// risk is `death_benefit - accumulated balance` and the charge is
        /// discounted back. Requires both rate args. False (the default) keeps
        /// the beginning-of-period convention: NAR measured where the charge
        /// is taken, no discount.
        #[serde(default)]
        nar_at_end_of_period: bool,
        /// Rate used to discount the COI charge back from the benefit
        /// payment. Only read when `nar_at_end_of_period`.
        #[serde(default)]
        coi_discount_rate_arg: Option<ArgRef>,
        /// Rate the balance accumulates at over the period. Only read when
        /// `nar_at_end_of_period`.
        #[serde(default)]
        credited_rate_arg: Option<ArgRef>,
        /// Corridor factor `y` — the multiple of the account value the death
        /// benefit must at least equal (IRC §7702 and its equivalents). When
        /// present the amount at risk is `MAX(NARf, NARc)`, which is exactly
        /// `death_benefit = MAX(face, y * account_value)`. Absent, only the
        /// fixed-benefit branch is computed.
        #[serde(default)]
        corridor_factor_arg: Option<ArgRef>,
        /// Round the COI charge (half away from zero) to this many decimals
        /// before applying it, leaving the running state unrounded — the
        /// placement spreadsheets use: `s -= ROUND(coi, d)`. Under the
        /// end-of-period convention the exact charge is solved first, then
        /// rounded — rounding does not participate in the closed-form solve.
        #[serde(default)]
        round_charge: Option<i32>,
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
    /// Round the running state to `decimals` places, half away from zero.
    ///
    /// This is Excel's ROUND, not banker's rounding, because the op exists to
    /// reproduce spreadsheets that round inside the recursion — where the
    /// rounding compounds and the tie-breaking rule is therefore load-bearing.
    Round {
        target_state: usize,
        target_point: usize,
        decimals: i32,
    },
    Apply {
        target_state: usize,
        target_point: usize,
        body_arg: ArgRef,
        label: Option<String>,
    },
}

/// Owned per-row List<Float64> input slice — offsets + flat values.
///
/// ``broadcast`` marks a scalar input: one value per row, held constant across
/// every period. A level death benefit or a flat charge rate is naturally
/// scalar, so requiring the caller to materialise `n_periods` copies of the
/// same number would be ceremony with no meaning.
struct OwnedListSlice {
    offsets: Vec<i64>,
    values: Vec<f64>,
    broadcast: bool,
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
        // The streaming engine hands this kernel a slice of each list column
        // whose inner values are still the whole column's. Everything below
        // reads those flat values -- casts them, refuses a null among them,
        // copies them out -- so it is handed the slice's own elements: the
        // whole column's would cost every morsel a copy of the portfolio, and
        // would refuse a slice for a null in a policy it was never given.
        let series = &own_rows(&inputs[n_states + i]);

        // A scalar (non-List) column is a per-policy constant: broadcast it
        // across every period rather than demanding n_periods copies.
        if !matches!(series.dtype(), DataType::List(_)) {
            // Check the dtype rather than relying on the cast failing: casting a
            // String column to Float64 silently yields nulls, which would surface
            // as a confusing "null value not supported" instead of naming the
            // real problem.
            //
            // Boolean is admitted alongside the numeric types because the List
            // path casts its inner values unconditionally, so a per-period
            // condition mask already works. Rejecting the scalar form would mean
            // a policy-level flag — a `when=` on a ratchet, say — was accepted as
            // a list and refused as the single value it naturally is.
            if !series.dtype().is_numeric() && !matches!(series.dtype(), DataType::Boolean) {
                return Err(PolarsError::ComputeError(
                    format!(
                        "rollforward: input column {} (arg index {}) must be List, Boolean, or \
                         numeric dtype, got {}",
                        kwargs.input_columns[i],
                        n_states + i,
                        series.dtype()
                    )
                    .into(),
                ));
            }
            let cast = series.cast(&DataType::Float64)?;
            let ca = cast.f64()?;
            if ca.null_count() > 0 {
                return Err(PolarsError::ComputeError(
                    format!(
                        "rollforward: null value at scalar input column {} not supported",
                        kwargs.input_columns[i]
                    )
                    .into(),
                ));
            }
            let rechunked = ca.rechunk();
            let values = rechunked
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
            // One value per row; offsets index the row, not the period.
            let offsets: Vec<i64> = (0..=values.len() as i64).collect();
            owned_slices.push(OwnedListSlice {
                offsets,
                values,
                broadcast: true,
            });
            continue;
        }

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
        owned_slices.push(OwnedListSlice {
            offsets,
            values,
            broadcast: false,
        });
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

    // Period lengths come from genuine per-period lists only. A broadcast
    // (scalar) input carries one value per row, so its offsets index rows, not
    // periods — using it to infer a horizon would report every policy as
    // 1 period long.
    let first_periodic: Option<&OwnedListSlice> = owned_slices.iter().find(|s| !s.broadcast);

    // ---- 3. Determine number of rows ----
    let num_rows = if let Some(ref lengths) = per_policy_lengths {
        lengths.len()
    } else if let Some(first) = first_periodic {
        first.offsets.len() - 1
    } else if !owned_slices.is_empty() {
        // Only scalar inputs: one value per row.
        owned_slices[0].values.len()
    } else if init_slices[0].1 {
        // broadcast: only 1 logical row (caller will broadcast the result)
        1
    } else {
        init_slices[0].0.len()
    };

    // ---- 3b. Uniform-schedule footgun guard (per-row, chunk-stable) ----
    // A uniform (non per-policy-grid) schedule declares that every policy
    // shares one horizon = n_periods, so any row whose input lists have a
    // different length is stale/short/over-long inputs — fail loudly rather
    // than silently projecting the wrong horizon. The check is per ROW, never
    // across rows: this plugin is elementwise, batch boundaries are an engine
    // choice (streaming chunks), and a cross-row heuristic would make a row's
    // behaviour depend on its batchmates — the earlier all-rows-share-one-
    // length version of this guard misfired or missed depending on chunk
    // width. Jagged horizons are declared, not inferred: use a per-policy
    // grid, which supplies authoritative per-row lengths.
    if let (true, None, Some(first)) = (kwargs.require_uniform, &per_policy_lengths, first_periodic)
    {
        for r in 0..num_rows {
            let row_len = (first.offsets[r + 1] - first.offsets[r]) as usize;
            if row_len != n_periods {
                // Off-by-exactly-one is almost always the point-vs-period trap:
                // every projection axis carries one value per period BOUNDARY
                // (n_periods + 1), and columns derived from an axis inherit
                // that length. Name the actual rule and the moves that work —
                // the earlier advice ("build the inputs on the schedule's
                // axis") pointed straight back at what fails (gh#73), and the
                // one after it named a bare `.list.head(n)`, which is not a
                // declared operation. No declared operation drops a column's
                // final boundary, so the period-indexed builds come first and
                // the escape is named with what it costs.
                // The first line is the shared one, and names nothing that
                // varies from policy to policy -- the length goes on the next
                // line -- so the collect-time replay, which matches a failure
                // by its exact first line, can match it in either engine.
                let advice = if row_len == n_periods + 1 {
                    format!(
                        "Exactly one more than the uniform schedule's n_periods = \
                         {n_periods}: projection axes (month, t_years(), \
                         period_dates()) are point-indexed, one value per period \
                         boundary, n_periods + 1 in total, and every column derived \
                         from an axis inherits the extra value. Rollforward inputs \
                         are period-indexed: exactly one value per period. Fix: build \
                         the input with one value per period — pass a per-policy \
                         value as it stands, which the rollforward reads in every \
                         period, repeat one with \
                         `.projection.broadcast_to_periods(like=af.projection.year_fractions())`, \
                         or derive the column from `af.projection.year_fractions()`, \
                         which holds one value per period. To cut a column already \
                         derived from an axis, \
                         `.polars_native().list.head({n_periods})` drops its final \
                         boundary, and records the line as engine_native: it runs \
                         only on Polars, and so does every calculation that reads it."
                    )
                } else {
                    format!(
                        "The schedule is uniform with n_periods = {n_periods}, so \
                         every policy's input lists must have exactly {n_periods} \
                         elements. If policies genuinely have different horizons, \
                         use a per-policy grid (af.projection.set(..., \
                         per_policy=True), or Schedule.from_per_policy_grid) so each \
                         policy carries its own length."
                    )
                };
                let msg = format!(
                    "{}\n{advice}",
                    period_count_message(
                        "the uniform schedule's n_periods",
                        n_periods,
                        "rollforward input lists",
                        row_len,
                    )
                );
                return Err(PolarsError::ComputeError(msg.into()));
            }
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

    // ---- 5b. Increment output buffers (track_increments) ----
    // One field per Op, in declared order: the SIGNED delta the Op applied to
    // its target slot in each period (state_after − state_before — negative
    // for charges, positive for credits). Zero for periods after a stop or
    // lapse: the kernel applied nothing, which is distinct from a source
    // model that keeps computing a notional charge (gh#69).
    let tracked_ops = tracked_increments(kwargs)?;
    let n_incs = tracked_ops.len();
    let mut inc_slot: Vec<Option<usize>> = vec![None; kwargs.ops.len()];
    for (k, (op_idx, _)) in tracked_ops.iter().enumerate() {
        inc_slot[*op_idx] = Some(k);
    }
    let mut increment_values: Vec<Vec<f64>> =
        (0..n_incs).map(|_| Vec::with_capacity(total_len)).collect();
    let mut increment_offsets: Vec<Vec<i64>> = (0..n_incs)
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
                    "rollforward: a negative per-policy length for one policy".into(),
                )
            })?
        } else if let Some(first) = first_periodic {
            first.offsets[row_idx + 1] as usize - first.offsets[row_idx] as usize
        } else {
            n_periods
        };
        for (slot_idx, slice) in owned_slices.iter().enumerate() {
            if slice.broadcast {
                continue; // scalar: one value per row, no period axis to check
            }
            let s = slice.offsets[row_idx] as usize;
            let e = slice.offsets[row_idx + 1] as usize;
            let len = e - s;
            same_periods(
                "the policy's period count",
                row_periods,
                &format!(
                    "rollforward input column {}",
                    kwargs.input_columns[slot_idx]
                ),
                len,
            )?;
        }

        // Zero-period policy (e.g. a fully matured / zero-term row): emit an
        // empty capture list and skip — the state buffer would be empty, so the
        // init write below must not run.
        if row_periods == 0 {
            for cap_idx in 0..n_captures {
                capture_offsets[cap_idx].push(capture_values[cap_idx].len() as i64);
            }
            for k in 0..n_incs {
                increment_offsets[k].push(increment_values[k].len() as i64);
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

        // Per-row increment scratch: [labelled_op][t], zero-filled so stopped
        // periods read as "nothing applied" without special-casing.
        let mut row_incs: Vec<f64> = vec![0.0; n_incs * row_periods];

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
            for (op_idx, op) in kwargs.ops.iter().enumerate() {
                let (op_target_state, op_target_point) = op_target(op);
                let slot = op_target_state * stride_state + op_target_point * stride_point + t;
                let before = state[slot];
                apply_op(
                    op,
                    &mut state,
                    t,
                    &owned_slices,
                    row_idx,
                    stride_state,
                    stride_point,
                )?;
                let new_val = state[slot];
                if let Some(k) = inc_slot[op_idx] {
                    row_incs[k * row_periods + t] = new_val - before;
                }
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
        // Emit per-op increment lists.
        for k in 0..n_incs {
            increment_values[k]
                .extend_from_slice(&row_incs[k * row_periods..(k + 1) * row_periods]);
            increment_offsets[k].push(increment_values[k].len() as i64);
        }
    }

    // ---- 7. Build output Struct ----
    let mut output_series: Vec<Series> = Vec::with_capacity(n_captures + n_incs);
    for (cap_idx, cap) in kwargs.captures_resolved.iter().enumerate() {
        let state_name = &state_names[cap.state];
        let point_name = &point_names[cap.point];
        let field_name = format!("{}@{}", state_name, point_name);
        let values = std::mem::take(&mut capture_values[cap_idx]);
        let offsets_vec = std::mem::take(&mut capture_offsets[cap_idx]);
        output_series.push(build_list_series(values, offsets_vec, field_name.as_str())?);
    }
    for (k, (_, key)) in tracked_ops.iter().enumerate() {
        let field_name = format!("increment_{key}");
        let values = std::mem::take(&mut increment_values[k]);
        let offsets_vec = std::mem::take(&mut increment_offsets[k]);
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
            round_charge,
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
            match round_charge {
                // Spreadsheet placement: the charge is rounded, the state
                // carries its sub-unit residue forward unrounded.
                Some(d) => state[i] -= excel_round(state[i] * r, *d),
                None => state[i] *= 1.0 - r,
            }
            Ok(())
        }
        OpV2::Grow {
            target_state,
            target_point,
            rate_arg,
            round_charge,
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
            match round_charge {
                // Spreadsheet placement: the credit is rounded, the state
                // carries its sub-unit residue forward unrounded.
                Some(d) => state[i] += excel_round(state[i] * r, *d),
                None => state[i] *= 1.0 + r,
            }
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
        OpV2::Round {
            target_state,
            target_point,
            decimals,
        } => {
            let i = *target_state * stride_state + *target_point * stride_point + t;
            // Excel's ROUND: the balance's fifteen significant digits, half
            // away from zero. Non-finite balances pass through unchanged.
            state[i] = excel_round(state[i], *decimals);
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
            nar_at_end_of_period,
            coi_discount_rate_arg,
            credited_rate_arg,
            corridor_factor_arg,
            round_charge,
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
            // The corridor factor, when supplied, adds a second branch to the
            // amount-at-risk calculation. `MAX(NARf, NARc)` is exactly
            // `death_benefit = MAX(face, y * account_value)`: the amount at
            // risk is monotonic in the benefit and each branch is self-
            // consistent, so the larger is the binding one.
            let corridor = corridor_factor_arg.map(|a| {
                resolve_arg(
                    a,
                    owned_slices,
                    state,
                    row_idx,
                    t,
                    stride_state,
                    stride_point,
                )
            });
            let (nar, charge, balance) = if *nar_at_end_of_period {
                // The benefit is paid at end of period, so the amount at risk
                // is measured against the accumulated balance — and the COI,
                // charged now, is discounted back. Deducting the COI lowers
                // the balance, which raises the amount at risk, so the two are
                // mutually dependent. Closed form of that solve:
                //
                //   NARf = (db - s*accum) / (1 - coi*accum*v)
                //   COI  = coi * NAR * v
                //
                // Both rates are required by `DeductNAR.verify()`; the 1.0
                // fallbacks here are unreachable from the Python API and exist
                // only so the kernel stays total on hand-written kwargs.
                let v = coi_discount_rate_arg.map_or(1.0, |a| {
                    let r = resolve_arg(
                        a,
                        owned_slices,
                        state,
                        row_idx,
                        t,
                        stride_state,
                        stride_point,
                    );
                    1.0 / (1.0 + r)
                });
                let accum = credited_rate_arg.map_or(1.0, |a| {
                    1.0 + resolve_arg(
                        a,
                        owned_slices,
                        state,
                        row_idx,
                        t,
                        stride_state,
                        stride_point,
                    )
                });
                let accumulated = state[i] * accum;
                let nar_face = (db - accumulated) / (1.0 - coi * accum * v);
                let nar = match corridor {
                    // Under a proportional benefit the COI shrinks the benefit
                    // too, so the amount at risk falls rather than rises — the
                    // sign in the denominator flips, and this branch is
                    // self-limiting rather than divergent.
                    Some(y) => {
                        let y_less_1 = y - 1.0;
                        let nar_corridor =
                            (y_less_1 * accumulated) / (1.0 + y_less_1 * coi * accum * v);
                        nar_face.max(nar_corridor)
                    }
                    None => nar_face,
                };
                (nar, coi * nar * v, accumulated)
            } else {
                // Beginning of period: amount at risk measured where the
                // charge is taken, no discount. No solve — benefit and balance
                // are read at the same point.
                let nar_face = db - state[i];
                let nar = match corridor {
                    Some(y) => nar_face.max((y - 1.0) * state[i]),
                    None => nar_face,
                };
                (nar, coi * nar, state[i])
            };
            if nar < 0.0 {
                // A negative amount at risk makes the COI a credit to the
                // account, which enlarges the account, which makes the amount
                // at risk more negative. Nothing bounds the loop, and every
                // period of it looks plausible — so refuse rather than return
                // a number.
                return Err(PolarsError::ComputeError(
                    format!(
                        "deduct_nar: net amount at risk is negative in period {t} \
                         (account value {balance:.2} exceeds death benefit {db:.2}). \
                         A negative amount at risk credits the account value instead \
                         of charging it, and compounds. Pass corridor_factor= for the \
                         standard corridor test, or raise the death benefit."
                    )
                    .into(),
                ));
            }
            // Spreadsheet placement: the charge is rounded, the state carries
            // its sub-cent residue forward unrounded. Under end-of-period
            // timing the exact charge is solved first, then rounded — the
            // rounding does not participate in the closed-form solve.
            let charge = match round_charge {
                Some(d) => excel_round(charge, *d),
                None => charge,
            };
            state[i] -= charge;
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

/// Return an Op's label, if it carries one. Floor and Round are structural
/// ops with no label field; everything else is a flow the user may name.
///
/// None here does not mean "emits nothing" — see [`increment_key`]. It means
/// the model's author gave this step no name, because a floor is a constraint
/// on the balance rather than a movement anyone booked, and a label field on
/// it would invite a modeller to book it as one.
fn op_label(op: &OpV2) -> Option<&str> {
    match op {
        OpV2::Add { label, .. }
        | OpV2::Subtract { label, .. }
        | OpV2::Charge { label, .. }
        | OpV2::Grow { label, .. }
        | OpV2::GrowCapped { label, .. }
        | OpV2::DeductNAR { label, .. }
        | OpV2::Ratchet { label, .. }
        | OpV2::Apply { label, .. } => label.as_deref(),
        OpV2::Floor { .. } | OpV2::Round { .. } => None,
    }
}

/// Return the key an Op's increment field is named under, given its 1-based
/// position in the declared chain.
///
/// A labelled Op's key is its label. A structural Op has no label to give, so
/// it takes the synthetic key `{kind}@{ordinal}` — `floor@3` for a `Floor`
/// declared third. The ordinal is the same number the artifact's `increments`
/// array lists against that step, so the waterfall row and the summary entry
/// name one step rather than two.
///
/// `@` is reserved for this form and refused in a user label at compile time,
/// one layer up in `rollforward/_passes.py`. A label `"floor@3"` reaching the
/// kernel anyway would collide here, and the duplicate guard below catches it
/// rather than letting two movements share one struct field.
///
/// # Errors
///
/// Returns `ComputeError` for a label-bearing Op carrying no label. The
/// synthetic form is closed to the two structural Ops, so there is no honest
/// key left to give; the compiler already refuses this before the kwargs are
/// built, and inventing a third kind here would put a name on the wire that
/// the spec does not define.
fn increment_key(op: &OpV2, ordinal: usize) -> PolarsResult<String> {
    if let Some(label) = op_label(op) {
        return Ok(label.to_string());
    }
    match op {
        OpV2::Floor { .. } => Ok(format!("floor@{ordinal}")),
        OpV2::Round { .. } => Ok(format!("round@{ordinal}")),
        _ => Err(PolarsError::ComputeError(
            format!(
                "rollforward: op {ordinal} carries no label with \
                 track_increments=True, and only Floor and Round are named \
                 for the step instead — give it label=..."
            )
            .into(),
        )),
    }
}

/// The Ops that emit increment fields when `track_increments`, as
/// `(op_index, key)` in declared order. One source of truth shared by the
/// kernel's emission and the plugin's output-schema declaration, so the two
/// cannot drift.
///
/// Every Op emits. A step that moved the balance and reported nothing is a
/// gap in the audit trail exactly where the balance is hardest to explain —
/// the floor that absorbed the overdraft — and the check line
/// `closing = opening + Σ increments` would then close only by luck.
///
/// # Errors
///
/// Returns `ComputeError` when two Ops would emit under one key — two labels
/// the same, or a label colliding with a structural step's reserved key — and
/// when a label-bearing Op carries no label ([`increment_key`]).
pub fn tracked_increments(kwargs: &RollforwardKwargs) -> PolarsResult<Vec<(usize, String)>> {
    if !kwargs.track_increments {
        return Ok(Vec::new());
    }
    let mut seen: Vec<String> = Vec::new();
    let mut out: Vec<(usize, String)> = Vec::new();
    for (i, op) in kwargs.ops.iter().enumerate() {
        let key = increment_key(op, i + 1)?;
        if seen.contains(&key) {
            return Err(PolarsError::ComputeError(
                format!(
                    "rollforward: duplicate op label {key:?} with \
                     track_increments=True — each labelled op emits its own \
                     increment field, so labels must be unique"
                )
                .into(),
            ));
        }
        seen.push(key.clone());
        out.push((i, key));
    }
    Ok(out)
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
        | OpV2::Round {
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
    if slice.broadcast {
        // Scalar input: one value per row, constant across periods.
        return slice.values[row_idx];
    }
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
        run_av_eop_series(init_series, prem_list)
    }

    /// [`run_av_eop`] over columns built by the caller -- a slice, say.
    fn run_av_eop_series(init_series: Series, prem_list: Series) -> PolarsResult<Vec<Vec<f64>>> {
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

    /// Four policies of three periods; the last one's second premium is
    /// missing when `hole` is set.
    fn four_premium_rows(hole: bool) -> (Series, Series) {
        let init = Series::new("av_init".into(), vec![100.0, 200.0, 300.0, 400.0]);
        let premiums = ListChunked::from_iter((0..4).map(|r| {
            let p = 10.0 * (r + 1) as f64;
            let middle = if hole && r == 3 { None } else { Some(p + 1.0) };
            Some(Series::new("".into(), vec![Some(p), middle, Some(p + 2.0)]))
        }))
        .into_series();
        (init, premiums)
    }

    #[test]
    fn a_slice_answers_what_the_whole_column_answers_for_those_rows() -> PolarsResult<()> {
        // The streaming engine hands the kernel a slice whose inner values are
        // the whole column's; its offsets do not start at zero.
        let (init, premiums) = four_premium_rows(false);
        let whole = run_av_eop_series(init.clone(), premiums.clone())?;
        let part = run_av_eop_series(init.slice(1, 2), premiums.slice(1, 2))?;
        assert_eq!(part, whole[1..3].to_vec());
        Ok(())
    }

    #[test]
    fn a_slice_is_not_refused_for_a_hole_in_a_policy_it_was_not_given() -> PolarsResult<()> {
        // The missing premium belongs to the fourth policy, which this slice
        // leaves out: the slice's own two policies have every period.
        let (init, premiums) = four_premium_rows(true);
        let part = run_av_eop_series(init.slice(0, 2), premiums.slice(0, 2))?;
        let (init, premiums) = four_premium_rows(false);
        let expected = run_av_eop_series(init.slice(0, 2), premiums.slice(0, 2))?;
        assert_eq!(part, expected);
        assert_eq!(part[0], vec![110.0, 121.0, 133.0]);
        // The hole itself is still refused when its policy is in the batch.
        let (init, premiums) = four_premium_rows(true);
        let err = run_av_eop_series(init.slice(2, 2), premiums.slice(2, 2)).unwrap_err();
        assert!(err.to_string().contains("null inner values"), "{err}");
        Ok(())
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

    /// Run a 3-period rollforward adding `premium` (a List column) and a
    /// scalar `bonus` (Float64, no period axis) at each period.
    fn run_scalar_and_list(
        init: Vec<f64>,
        premium: Vec<Vec<f64>>,
        bonus: Series,
    ) -> PolarsResult<Vec<Vec<f64>>> {
        let init = Series::new("av_init".into(), init);
        let prem =
            ListChunked::from_iter(premium.into_iter().map(|v| Some(Series::new("".into(), v))))
                .into_series();
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
            "require_uniform": true,
            "input_columns": ["premium", "bonus"],
            "ops": [
                {"op": "Add", "target_state": 0, "target_point": 1,
                 "expr_arg": {"kind": "input", "idx": 0}, "label": "Premium"},
                {"op": "Add", "target_state": 0, "target_point": 1,
                 "expr_arg": {"kind": "input", "idx": 1}, "label": "Bonus"}
            ],
            "captures_resolved": [{"state": 0, "point": 1}]
        }"#;
        let kwargs: RollforwardKwargs = serde_json::from_str(kwargs_json).unwrap();
        let out = rollforward_kernel(&[init, prem, bonus], &kwargs)?;
        let field = out.struct_().unwrap().fields_as_series()[0].clone();
        let list = field.list().unwrap();
        Ok((0..list.len())
            .map(|r| {
                let s = list.get_as_series(r).unwrap();
                let f = s.f64().unwrap();
                (0..f.len()).map(|i| f.get(i).unwrap()).collect()
            })
            .collect())
    }

    #[test]
    fn scalar_input_broadcasts_across_periods() {
        // `bonus` is a plain Float64 column — one value per policy, held
        // constant across every period. A level death benefit or flat charge
        // rate has this shape; requiring n_periods copies would be ceremony.
        let out = run_scalar_and_list(
            vec![0.0, 0.0],
            vec![vec![10.0, 20.0, 30.0], vec![10.0, 20.0, 30.0]],
            Series::new("bonus".into(), vec![1.0, 2.0]),
        )
        .unwrap();
        // Policy 0 adds 1.0 each period; policy 1 adds 2.0.
        assert_eq!(out[0], vec![11.0, 32.0, 63.0]);
        assert_eq!(out[1], vec![12.0, 34.0, 66.0]);
    }

    #[test]
    fn scalar_input_equals_explicit_list_of_same_value() {
        // A broadcast scalar must give bit-identical results to the caller
        // materialising the same value n_periods times.
        let scalar = run_scalar_and_list(
            vec![100.0],
            vec![vec![10.0, 20.0, 30.0]],
            Series::new("bonus".into(), vec![5.0]),
        )
        .unwrap();
        let listed = run_scalar_and_list(
            vec![100.0],
            vec![vec![10.0, 20.0, 30.0]],
            ListChunked::from_iter([Some(Series::new("".into(), vec![5.0, 5.0, 5.0]))])
                .into_series()
                .with_name("bonus".into()),
        )
        .unwrap();
        assert_eq!(scalar, listed);
    }

    #[test]
    fn scalar_input_does_not_trip_the_uniform_length_guard() {
        // Regression: the uniform-schedule guard and the per-row length check
        // both used owned_slices[0]. With a scalar column first, they would
        // read a length of 1 and reject every policy. Order must not matter,
        // so this is the same run with the scalar column registered first.
        let init = Series::new("av_init".into(), vec![0.0]);
        let bonus = Series::new("bonus".into(), vec![7.0]);
        let prem = ListChunked::from_iter([Some(Series::new("".into(), vec![1.0, 2.0, 3.0]))])
            .into_series();
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
            "require_uniform": true,
            "input_columns": ["bonus", "premium"],
            "ops": [
                {"op": "Add", "target_state": 0, "target_point": 1,
                 "expr_arg": {"kind": "input", "idx": 0}, "label": "Bonus"},
                {"op": "Add", "target_state": 0, "target_point": 1,
                 "expr_arg": {"kind": "input", "idx": 1}, "label": "Premium"}
            ],
            "captures_resolved": [{"state": 0, "point": 1}]
        }"#;
        let kwargs: RollforwardKwargs = serde_json::from_str(kwargs_json).unwrap();
        let out = rollforward_kernel(&[init, bonus, prem], &kwargs)
            .expect("scalar-first input order must not trip the length guard");
        let field = out.struct_().unwrap().fields_as_series()[0].clone();
        let list = field.list().unwrap();
        let s = list.get_as_series(0).unwrap();
        let f = s.f64().unwrap();
        let row: Vec<f64> = (0..f.len()).map(|i| f.get(i).unwrap()).collect();
        assert_eq!(row, vec![8.0, 17.0, 27.0]);
    }

    /// Runs one policy's `premium` list through a uniform 3-period schedule
    /// and returns the guard's error message ("" if it passed).
    fn uniform_guard_error(premium: Vec<f64>) -> String {
        let init = Series::new("av_init".into(), vec![0.0]);
        let prem = ListChunked::from_iter([Some(Series::new("".into(), premium))]).into_series();
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
            "require_uniform": true,
            "input_columns": ["premium"],
            "ops": [
                {"op": "Add", "target_state": 0, "target_point": 1,
                 "expr_arg": {"kind": "input", "idx": 0}, "label": "Premium"}
            ],
            "captures_resolved": [{"state": 0, "point": 1}]
        }"#;
        let kwargs: RollforwardKwargs = serde_json::from_str(kwargs_json).unwrap();
        match rollforward_kernel(&[init, prem], &kwargs) {
            Ok(_) => String::new(),
            Err(e) => e.to_string(),
        }
    }

    #[test]
    fn off_by_one_length_names_the_point_indexed_trap() {
        // Length n_periods + 1 is what every axis-derived input produces, so
        // the error must state the point- vs period-indexed rule and moves
        // that work — not point back at the axis that caused it (gh#73), and
        // not a bare `.list.head`, which is no declared operation: the cut
        // is the escape, named with its cost.
        let msg = uniform_guard_error(vec![1.0, 2.0, 3.0, 4.0]);
        assert!(msg.contains("point-indexed"), "{msg}");
        assert!(
            msg.contains("broadcast_to_periods(like=af.projection.year_fractions())"),
            "{msg}"
        );
        assert!(msg.contains("`.polars_native().list.head(3)`"), "{msg}");
        assert!(!msg.contains("e.g. `.list.head("), "{msg}");
        assert!(msg.contains("engine_native"), "{msg}");
        assert!(msg.contains("n_periods = 3"), "{msg}");
        assert!(
            !msg.contains("build the inputs on the schedule's axis"),
            "the old advice reproduces the failure and must not return: {msg}"
        );
    }

    #[test]
    fn other_length_mismatch_keeps_the_generic_uniform_message() {
        let msg = uniform_guard_error(vec![1.0, 2.0]);
        assert!(msg.contains("must have exactly 3"), "{msg}");
        assert!(msg.contains("per-policy grid"), "{msg}");
        assert!(!msg.contains("point-indexed"), "{msg}");
    }

    #[test]
    fn non_numeric_scalar_input_is_rejected_by_name() {
        // A String column cannot be a rollforward input; the error must name
        // the column and its dtype rather than saying "must be List".
        let init = Series::new("av_init".into(), vec![0.0]);
        let bad = Series::new("bonus".into(), vec!["not a number"]);
        let prem = ListChunked::from_iter([Some(Series::new("".into(), vec![1.0, 2.0, 3.0]))])
            .into_series();
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
            "input_columns": ["premium", "bonus"],
            "ops": [
                {"op": "Add", "target_state": 0, "target_point": 1,
                 "expr_arg": {"kind": "input", "idx": 0}, "label": "Premium"}
            ],
            "captures_resolved": [{"state": 0, "point": 1}]
        }"#;
        let kwargs: RollforwardKwargs = serde_json::from_str(kwargs_json).unwrap();
        let err = rollforward_kernel(&[init, prem, bad], &kwargs).unwrap_err();
        let msg = err.to_string();
        assert!(msg.contains("bonus"), "error must name the column: {msg}");
        assert!(
            msg.contains("List, Boolean, or numeric"),
            "error must say what is accepted: {msg}"
        );
    }

    #[test]
    fn boolean_scalar_input_broadcasts() {
        // The List path casts its inner values unconditionally, so a per-period
        // Boolean mask already works. A policy-level flag — a ratchet `when=`,
        // say — must not be refused merely for being the single value it is.
        let init = Series::new("av_init".into(), vec![100.0]);
        let flag = Series::new("flag".into(), vec![true]);
        let to = ListChunked::from_iter([Some(Series::new("".into(), vec![150.0, 150.0, 150.0]))])
            .into_series();
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
            "input_columns": ["to", "flag"],
            "ops": [
                {"op": "Ratchet", "target_state": 0, "target_point": 1,
                 "to_arg": {"kind": "input", "idx": 0},
                 "when_arg": {"kind": "input", "idx": 1}, "label": null}
            ],
            "captures_resolved": [{"state": 0, "point": 1}]
        }"#;
        let kwargs: RollforwardKwargs = serde_json::from_str(kwargs_json).unwrap();
        let out = rollforward_kernel(&[init, to, flag], &kwargs)
            .expect("a scalar Boolean flag must broadcast, not error");
        let field = out.struct_().unwrap().fields_as_series();
        let s = field[0].list().unwrap().get_as_series(0).unwrap();
        let f = s.f64().unwrap();
        let row: Vec<f64> = (0..f.len()).map(|i| f.get(i).unwrap()).collect();
        // The flag is true in every period, so the ratchet fires every period.
        assert_eq!(row, vec![150.0, 150.0, 150.0]);
    }

    #[test]
    fn the_kernel_rounds_as_excel_does() {
        // Ties chosen to be exact in binary, so the rule is what's under test.
        assert_eq!(excel_round(2.5, 0), 3.0);
        assert_eq!(excel_round(-2.5, 0), -3.0);
        assert_eq!(excel_round(0.375, 2), 0.38);
        assert_eq!(excel_round(-0.375, 2), -0.38);
        assert_eq!(excel_round(125.0, -1), 130.0);
        // A double just under a half is a half at fifteen digits, as in Excel.
        assert_eq!(excel_round(5657268.499999999 * 0.03, 2), 169718.06);
        // Non-finite values and magnitudes past the scaling pass through.
        assert!(excel_round(f64::NAN, 2).is_nan());
        assert_eq!(excel_round(f64::INFINITY, 2), f64::INFINITY);
        assert_eq!(excel_round(1.7e308, 2), 1.7e308);
    }

    /// One-state, one-input helper: run `ops_json` over 2 periods with the
    /// given init and per-period input values, returning the eop capture row.
    fn run_one_input(init_v: f64, input: Vec<f64>, ops_json: &str) -> Vec<f64> {
        let init = Series::new("av_init".into(), vec![init_v]);
        let inp =
            ListChunked::from_iter([Some(Series::new("".into(), input.clone()))]).into_series();
        let kwargs_json = format!(
            r#"{{
            "ir": {{"states": [{{"name": "av"}}], "points": ["bop", "eop"], "transitions": []}},
            "captures": [["av", "eop"]],
            "track_increments": false,
            "lapse_when_all_non_positive": [],
            "contract_boundary": null,
            "n_states": 1,
            "n_points": 2,
            "n_periods": {},
            "bop_idx": 0,
            "eop_idx": 1,
            "input_columns": ["x"],
            "ops": [{}],
            "captures_resolved": [{{"state": 0, "point": 1}}]
        }}"#,
            input.len(),
            ops_json
        );
        let kwargs: RollforwardKwargs = serde_json::from_str(&kwargs_json).unwrap();
        let out = rollforward_kernel(&[init, inp], &kwargs).unwrap();
        let field = out.struct_().unwrap().fields_as_series()[0].clone();
        let s = field.list().unwrap().get_as_series(0).unwrap();
        let f = s.f64().unwrap();
        (0..f.len()).map(|i| f.get(i).unwrap()).collect()
    }

    #[test]
    fn charge_round_charge_rounds_the_flow_not_the_state() {
        // Spreadsheet placement: s -= ROUND(s * rate, 2), state unrounded.
        // t1: 1000 * 0.033333 = 33.333 -> 33.33; s = 966.67
        // t2: 966.67 * 0.033333 = 32.2221... -> 32.22; s = 934.45
        let row = run_one_input(
            1000.0,
            vec![0.033333, 0.033333],
            r#"{"op": "Charge", "target_state": 0, "target_point": 1,
                "rate_arg": {"kind": "input", "idx": 0},
                "round_charge": 2, "label": null}"#,
        );
        assert!((row[0] - 966.67).abs() < 1e-9, "t1: {}", row[0]);
        assert!((row[1] - 934.45).abs() < 1e-9, "t2: {}", row[1]);
    }

    #[test]
    fn grow_round_charge_rounds_the_credit() {
        // s += ROUND(s * rate, 2): 1000 * 0.0333333 = 33.3333 -> 33.33.
        let row = run_one_input(
            1000.0,
            vec![0.0333333],
            r#"{"op": "Grow", "target_state": 0, "target_point": 1,
                "rate_arg": {"kind": "input", "idx": 0},
                "round_charge": 2, "label": null}"#,
        );
        assert!((row[0] - 1033.33).abs() < 1e-9, "t1: {}", row[0]);
    }

    #[test]
    fn grow_round_charge_rounds_the_fifteen_digit_credit_as_excel_does() {
        // UniversalLife.xlsx, 'Account Values -- Type A', row 74, column Q =
        // ROUND(MAX((H-P)*3%,0),2) with column H = 5657268.499999999 and
        // column P = 0. The credit is the double 169718.05499999996…, whose
        // fifteen digits read 169718.055000000, and Excel credits 169718.06.
        let row = run_one_input(
            5657268.499999999,
            vec![0.03],
            r#"{"op": "Grow", "target_state": 0, "target_point": 1,
                "rate_arg": {"kind": "input", "idx": 0},
                "round_charge": 2, "label": null}"#,
        );
        assert_eq!(row[0], 5657268.499999999 + 169718.06);
    }

    #[test]
    fn round_rounds_the_fifteen_digit_balance_as_excel_does() {
        // A balance of 1.5 * 45366.20999999999 is 68049.31499999999… as a
        // double and 68049.3150000000 at fifteen digits; ROUND gives 68049.32.
        let row = run_one_input(
            1.5 * 45366.20999999999,
            vec![0.0],
            r#"{"op": "Round", "target_state": 0, "target_point": 1, "decimals": 2}"#,
        );
        assert_eq!(row[0], 68049.32);
    }

    #[test]
    fn deduct_nar_round_charge_rounds_the_solved_coi() {
        // BOP: NAR = 10000 - 1000 = 9000; charge = 9000 * 0.0012345
        // = 11.1105 -> ROUND -> 11.11; s = 988.89 (unrounded state would
        // be 988.8895).
        let init = Series::new("av_init".into(), vec![1000.0]);
        let coi =
            ListChunked::from_iter([Some(Series::new("".into(), vec![0.0012345]))]).into_series();
        let db =
            ListChunked::from_iter([Some(Series::new("".into(), vec![10000.0]))]).into_series();
        let kwargs_json = r#"{
            "ir": {"states": [{"name": "av"}], "points": ["bop", "eop"], "transitions": []},
            "captures": [["av", "eop"]],
            "track_increments": false,
            "lapse_when_all_non_positive": [],
            "contract_boundary": null,
            "n_states": 1,
            "n_points": 2,
            "n_periods": 1,
            "bop_idx": 0,
            "eop_idx": 1,
            "input_columns": ["coi", "db"],
            "ops": [{"op": "DeductNAR", "target_state": 0, "target_point": 1,
                     "coi_rate_arg": {"kind": "input", "idx": 0},
                     "death_benefit_arg": {"kind": "input", "idx": 1},
                     "nar_at_end_of_period": false,
                     "round_charge": 2, "label": null}],
            "captures_resolved": [{"state": 0, "point": 1}]
        }"#;
        let kwargs: RollforwardKwargs = serde_json::from_str(kwargs_json).unwrap();
        let out = rollforward_kernel(&[init, coi, db], &kwargs).unwrap();
        let field = out.struct_().unwrap().fields_as_series()[0].clone();
        let s = field.list().unwrap().get_as_series(0).unwrap();
        let v = s.f64().unwrap().get(0).unwrap();
        assert!((v - 988.89).abs() < 1e-9, "eop: {v}");
    }

    #[test]
    fn round_charge_defaults_absent_in_serialised_ops() {
        // Ops serialised before the knob existed must still deserialise,
        // with the unrounded behaviour.
        let json = r#"{
            "op": "Charge",
            "target_state": 0,
            "target_point": 1,
            "rate_arg": {"kind": "input", "idx": 0},
            "label": null
        }"#;
        let op: OpV2 = serde_json::from_str(json).unwrap();
        match op {
            OpV2::Charge { round_charge, .. } => assert!(round_charge.is_none()),
            _ => panic!("expected Charge"),
        }
    }

    #[test]
    fn track_increments_emits_signed_per_op_deltas() {
        // Add "Premium" then Charge "Fee" over 3 periods; the struct gains
        // increment_Premium and increment_Fee fields with the SIGNED deltas.
        //   t: bop -> +100 -> *(1-0.1)
        //   t1: 0    -> 100  -> 90        inc_P=+100, inc_F=-10
        //   t2: 90   -> 190  -> 171       inc_P=+100, inc_F=-19
        //   t3: 171  -> 271  -> 243.9     inc_P=+100, inc_F=-27.1
        let init = Series::new("av_init".into(), vec![0.0]);
        let prem =
            ListChunked::from_iter([Some(Series::new("".into(), vec![100.0, 100.0, 100.0]))])
                .into_series();
        let rate = ListChunked::from_iter([Some(Series::new("".into(), vec![0.1, 0.1, 0.1]))])
            .into_series();
        let kwargs_json = r#"{
            "ir": {"states": [{"name": "av"}], "points": ["bop", "eop"], "transitions": []},
            "captures": [["av", "eop"]],
            "track_increments": true,
            "lapse_when_all_non_positive": [],
            "contract_boundary": null,
            "n_states": 1,
            "n_points": 2,
            "n_periods": 3,
            "bop_idx": 0,
            "eop_idx": 1,
            "input_columns": ["premium", "rate"],
            "ops": [
                {"op": "Add", "target_state": 0, "target_point": 1,
                 "expr_arg": {"kind": "input", "idx": 0}, "label": "Premium"},
                {"op": "Charge", "target_state": 0, "target_point": 1,
                 "rate_arg": {"kind": "input", "idx": 1}, "label": "Fee"}
            ],
            "captures_resolved": [{"state": 0, "point": 1}]
        }"#;
        let kwargs: RollforwardKwargs = serde_json::from_str(kwargs_json).unwrap();
        let out = rollforward_kernel(&[init, prem, rate], &kwargs).unwrap();
        let fields = out.struct_().unwrap().fields_as_series();
        let names: Vec<&str> = fields.iter().map(|s| s.name().as_str()).collect();
        assert_eq!(names, vec!["av@eop", "increment_Premium", "increment_Fee"]);

        let row = |f: usize| -> Vec<f64> {
            let s = fields[f].list().unwrap().get_as_series(0).unwrap();
            let ca = s.f64().unwrap();
            (0..ca.len()).map(|i| ca.get(i).unwrap()).collect()
        };
        let approx = |got: &[f64], want: &[f64]| {
            assert_eq!(got.len(), want.len());
            for (g, w) in got.iter().zip(want) {
                assert!((g - w).abs() < 1e-9, "got {got:?}, want {want:?}");
            }
        };
        approx(&row(0), &[90.0, 171.0, 243.9]);
        approx(&row(1), &[100.0, 100.0, 100.0]);
        approx(&row(2), &[-10.0, -19.0, -27.1]);
    }

    #[test]
    fn increments_are_zero_after_lapse() {
        // Subtract drives the state non-positive at t2; the lapse stop fires
        // and t3's increments read zero — the kernel applied nothing, which
        // is distinct from a sheet's notional post-lapse charge (gh#69).
        let init = Series::new("av_init".into(), vec![100.0]);
        let w = ListChunked::from_iter([Some(Series::new("".into(), vec![50.0, 60.0, 50.0]))])
            .into_series();
        let kwargs_json = r#"{
            "ir": {"states": [{"name": "av"}], "points": ["bop", "eop"], "transitions": []},
            "captures": [["av", "eop"]],
            "track_increments": true,
            "lapse_when_all_non_positive": ["av"],
            "contract_boundary": null,
            "n_states": 1,
            "n_points": 2,
            "n_periods": 3,
            "bop_idx": 0,
            "eop_idx": 1,
            "input_columns": ["w"],
            "ops": [
                {"op": "Subtract", "target_state": 0, "target_point": 1,
                 "expr_arg": {"kind": "input", "idx": 0}, "label": "Withdrawal"}
            ],
            "captures_resolved": [{"state": 0, "point": 1}],
            "lapse_state_indices": [0]
        }"#;
        let kwargs: RollforwardKwargs = serde_json::from_str(kwargs_json).unwrap();
        let out = rollforward_kernel(&[init, w], &kwargs).unwrap();
        let fields = out.struct_().unwrap().fields_as_series();
        let s = fields[1].list().unwrap().get_as_series(0).unwrap();
        let ca = s.f64().unwrap();
        let incs: Vec<f64> = (0..ca.len()).map(|i| ca.get(i).unwrap()).collect();
        assert_eq!(incs, vec![-50.0, -60.0, 0.0]);
    }

    #[test]
    fn duplicate_labels_with_track_increments_are_refused() {
        let json = r#"{
            "ir": {"states": [{"name": "av"}], "points": ["bop", "eop"], "transitions": []},
            "captures": [["av", "eop"]],
            "track_increments": true,
            "lapse_when_all_non_positive": [],
            "contract_boundary": null,
            "n_states": 1,
            "n_points": 2,
            "n_periods": 1,
            "bop_idx": 0,
            "eop_idx": 1,
            "input_columns": ["a"],
            "ops": [
                {"op": "Add", "target_state": 0, "target_point": 1,
                 "expr_arg": {"kind": "input", "idx": 0}, "label": "X"},
                {"op": "Subtract", "target_state": 0, "target_point": 1,
                 "expr_arg": {"kind": "input", "idx": 0}, "label": "X"}
            ],
            "captures_resolved": [{"state": 0, "point": 1}]
        }"#;
        let kwargs: RollforwardKwargs = serde_json::from_str(json).unwrap();
        let err = tracked_increments(&kwargs).unwrap_err();
        assert!(err.to_string().contains("duplicate op label"));
    }

    // ---- Structural increments: every step emits, a floor or a round too ----

    /// Build a one-state, one-policy kernel run over `ops`, tracking on.
    ///
    /// The chains below all charge or credit a single balance, so one input
    /// list and one capture is the whole shape; what varies between them is
    /// which structural steps the chain declares and where.
    fn run_tracked(init_v: f64, input: Vec<f64>, ops_json: &str) -> (Vec<String>, Vec<Vec<f64>>) {
        let n = input.len();
        let init = Series::new("av_init".into(), vec![init_v]);
        let arg = ListChunked::from_iter([Some(Series::new("".into(), input))]).into_series();
        let kwargs_json = format!(
            r#"{{
                "ir": {{"states": [{{"name": "av"}}], "points": ["bop", "eop"], "transitions": []}},
                "captures": [["av", "eop"]],
                "track_increments": true,
                "lapse_when_all_non_positive": [],
                "contract_boundary": null,
                "n_states": 1,
                "n_points": 2,
                "n_periods": {n},
                "bop_idx": 0,
                "eop_idx": 1,
                "input_columns": ["a"],
                "ops": {ops_json},
                "captures_resolved": [{{"state": 0, "point": 1}}]
            }}"#
        );
        let kwargs: RollforwardKwargs = serde_json::from_str(&kwargs_json).unwrap();
        let out = rollforward_kernel(&[init, arg], &kwargs).unwrap();
        let fields = out.struct_().unwrap().fields_as_series();
        let names: Vec<String> = fields.iter().map(|s| s.name().to_string()).collect();
        let rows: Vec<Vec<f64>> = fields
            .iter()
            .map(|f| {
                let s = f.list().unwrap().get_as_series(0).unwrap();
                let ca = s.f64().unwrap();
                (0..ca.len()).map(|i| ca.get(i).unwrap()).collect()
            })
            .collect();
        (names, rows)
    }

    const SUBTRACT_THEN_FLOOR: &str = r#"[
        {"op": "Subtract", "target_state": 0, "target_point": 1,
         "expr_arg": {"kind": "input", "idx": 0}, "label": "drawdown"},
        {"op": "Floor", "target_state": 0, "target_point": 1, "value": 0.0}
    ]"#;

    #[test]
    fn a_floor_that_bites_reports_what_it_absorbed() {
        // 100 − 60 = 40; 40 − 60 = −20, floored to 0. The floor's increment
        // is +20 in that period: the amount it put back, signed as §16.2
        // defines every increment, after − before.
        let (names, rows) = run_tracked(100.0, vec![60.0, 60.0], SUBTRACT_THEN_FLOOR);
        assert_eq!(
            names,
            vec!["av@eop", "increment_drawdown", "increment_floor@2"]
        );
        assert_eq!(rows[0], vec![40.0, 0.0]);
        assert_eq!(rows[1], vec![-60.0, -60.0]);
        assert_eq!(rows[2], vec![0.0, 20.0]);
    }

    #[test]
    fn a_floor_that_never_bites_reports_zero_in_every_period() {
        // The field is emitted regardless: a reader counting rows against the
        // chain's steps must not have to know whether a floor fired, and a
        // missing column and a column of zeros say different things.
        let (names, rows) = run_tracked(100.0, vec![10.0, 10.0], SUBTRACT_THEN_FLOOR);
        assert_eq!(
            names,
            vec!["av@eop", "increment_drawdown", "increment_floor@2"]
        );
        assert_eq!(rows[2], vec![0.0, 0.0]);
    }

    #[test]
    fn a_round_reports_the_rounding_delta() {
        // 100 − 33.333 = 66.667 → 66.67, so the round put back +0.003;
        // 66.67 − 33.333 = 33.337 → 33.34, +0.003 again. The sign is the
        // same after − before every other increment carries: a round that
        // takes the balance down reports a negative delta.
        let ops = r#"[
            {"op": "Subtract", "target_state": 0, "target_point": 1,
             "expr_arg": {"kind": "input", "idx": 0}, "label": "drawdown"},
            {"op": "Round", "target_state": 0, "target_point": 1, "decimals": 2}
        ]"#;
        let (names, rows) = run_tracked(100.0, vec![33.333, 33.333], ops);
        assert_eq!(
            names,
            vec!["av@eop", "increment_drawdown", "increment_round@2"]
        );
        for (got, want) in rows[0].iter().zip([66.67, 33.34]) {
            assert!((got - want).abs() < 1e-9, "eop {:?}", rows[0]);
        }
        for got in &rows[2] {
            assert!((got - 0.003).abs() < 1e-9, "round delta {:?}", rows[2]);
        }
    }

    #[test]
    fn a_chain_carrying_both_names_each_by_its_own_ordinal() {
        // The ordinal is the step's 1-based position in the declared chain —
        // the same number the artifact's `increments` array lists against it
        // — so `floor@2` and `round@3` are the second and third steps and a
        // reader citing one movement reaches one step.
        let ops = r#"[
            {"op": "Subtract", "target_state": 0, "target_point": 1,
             "expr_arg": {"kind": "input", "idx": 0}, "label": "drawdown"},
            {"op": "Floor", "target_state": 0, "target_point": 1, "value": 0.0},
            {"op": "Round", "target_state": 0, "target_point": 1, "decimals": 2}
        ]"#;
        let (names, _) = run_tracked(100.0, vec![60.0, 60.0], ops);
        assert_eq!(
            names,
            vec![
                "av@eop",
                "increment_drawdown",
                "increment_floor@2",
                "increment_round@3"
            ]
        );
    }

    #[test]
    fn a_chain_with_no_structural_step_keeps_the_shape_it_had() {
        // The change is additive: a fully labelled chain emits exactly the
        // fields it emitted before, in the order it emitted them.
        let ops = r#"[
            {"op": "Add", "target_state": 0, "target_point": 1,
             "expr_arg": {"kind": "input", "idx": 0}, "label": "Premium"},
            {"op": "Subtract", "target_state": 0, "target_point": 1,
             "expr_arg": {"kind": "input", "idx": 0}, "label": "Withdrawal"}
        ]"#;
        let (names, rows) = run_tracked(0.0, vec![100.0, 100.0], ops);
        assert_eq!(
            names,
            vec!["av@eop", "increment_Premium", "increment_Withdrawal"]
        );
        assert_eq!(rows[1], vec![100.0, 100.0]);
        assert_eq!(rows[2], vec![-100.0, -100.0]);
    }

    #[test]
    fn the_increments_sum_to_the_period_change_in_the_balance() {
        // The check line under a rollforward's movements, closing on the
        // kernel's own rows with nothing derived: closing − opening =
        // Σ increments, in every period, with the floor biting in one of them.
        // Opening at t is closing at t−1, with the initial state in front.
        let (_, rows) = run_tracked(100.0, vec![60.0, 60.0, 10.0], SUBTRACT_THEN_FLOOR);
        let closing = &rows[0];
        let mut opening = 100.0;
        for t in 0..closing.len() {
            let summed: f64 = rows[1..].iter().map(|inc| inc[t]).sum();
            let moved = closing[t] - opening;
            assert!(
                (moved - summed).abs() < 1e-12,
                "period {t}: moved {moved}, increments summed {summed}"
            );
            opening = closing[t];
        }
    }

    /// Hands `ops` to the key pass on the same one-state, one-period shape
    /// `run_tracked` builds, and returns the refusal.
    ///
    /// Both guards below are about the key a step would emit, not about any
    /// value it computes, so neither needs the kernel run — the op list is
    /// the whole of what the two cases differ in.
    fn tracked_key_error(ops_json: &str) -> String {
        let kwargs_json = format!(
            r#"{{
                "ir": {{"states": [{{"name": "av"}}], "points": ["bop", "eop"], "transitions": []}},
                "captures": [["av", "eop"]],
                "track_increments": true,
                "lapse_when_all_non_positive": [],
                "contract_boundary": null,
                "n_states": 1,
                "n_points": 2,
                "n_periods": 1,
                "bop_idx": 0,
                "eop_idx": 1,
                "input_columns": ["a"],
                "ops": {ops_json},
                "captures_resolved": [{{"state": 0, "point": 1}}]
            }}"#
        );
        let kwargs: RollforwardKwargs = serde_json::from_str(&kwargs_json).unwrap();
        tracked_increments(&kwargs).unwrap_err().to_string()
    }

    #[test]
    fn a_user_label_colliding_with_a_structural_key_is_refused() {
        // `@` is reserved and refused in a user label at compile time, one
        // layer up. Kwargs handed to the kernel by anything else still meet
        // the guard here rather than producing two fields with one name.
        let err = tracked_key_error(
            r#"[
                {"op": "Add", "target_state": 0, "target_point": 1,
                 "expr_arg": {"kind": "input", "idx": 0}, "label": "floor@2"},
                {"op": "Floor", "target_state": 0, "target_point": 1, "value": 0.0}
            ]"#,
        );
        assert!(err.contains("duplicate op label"));
    }

    #[test]
    fn a_flow_with_no_label_is_refused_rather_than_given_an_invented_name() {
        // Only Floor and Round are named for the step. A flow reaching the
        // kernel unlabelled under tracking has no honest key left, and the
        // compiler refuses it one layer up; a third synthetic kind here would
        // put a name on the wire that the format does not define.
        let err = tracked_key_error(
            r#"[
                {"op": "Add", "target_state": 0, "target_point": 1,
                 "expr_arg": {"kind": "input", "idx": 0}, "label": null}
            ]"#,
        );
        assert!(err.contains("carries no label"));
    }

    #[test]
    fn tracking_off_emits_no_increment_field_for_any_step() {
        let (names, _) = {
            let init = Series::new("av_init".into(), vec![100.0]);
            let arg =
                ListChunked::from_iter([Some(Series::new("".into(), vec![60.0]))]).into_series();
            let json = format!(
                r#"{{
                    "ir": {{"states": [{{"name": "av"}}], "points": ["bop", "eop"], "transitions": []}},
                    "captures": [["av", "eop"]],
                    "track_increments": false,
                    "lapse_when_all_non_positive": [],
                    "contract_boundary": null,
                    "n_states": 1,
                    "n_points": 2,
                    "n_periods": 1,
                    "bop_idx": 0,
                    "eop_idx": 1,
                    "input_columns": ["a"],
                    "ops": {SUBTRACT_THEN_FLOOR},
                    "captures_resolved": [{{"state": 0, "point": 1}}]
                }}"#
            );
            let kwargs: RollforwardKwargs = serde_json::from_str(&json).unwrap();
            let out = rollforward_kernel(&[init, arg], &kwargs).unwrap();
            let fields = out.struct_().unwrap().fields_as_series();
            let names: Vec<String> = fields.iter().map(|s| s.name().to_string()).collect();
            (names, ())
        };
        assert_eq!(names, vec!["av@eop"]);
    }
}
