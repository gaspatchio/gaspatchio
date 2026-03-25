// ABOUTME: Rollforward kernel for non-linear account value projections
// ABOUTME: Step-dispatch inner loop with single-state and multi-state support

use polars::prelude::*;
use polars_arrow::array::PrimitiveArray;
use polars_arrow::offset::OffsetsBuffer;
use serde::Deserialize;

/// Configuration for the rollforward kernel.
///
/// Receives all pre-resolved index references from Python. No string lookups
/// occur in the hot loop — Python's `_compile()` method resolves column names
/// to integer indices before serializing to JSON.
#[derive(Deserialize)]
pub struct RollforwardKwargs {
    pub states: Vec<StateSpec>,
    pub steps: Vec<StepSpec>,
    pub track_increments: bool,
    pub assertion_mode: Option<AssertionMode>,
    pub num_captures: usize,
    pub lapse_condition: Option<LapseCondition>,
}

/// Specifies how assertion failures are surfaced.
#[derive(Deserialize)]
pub enum AssertionMode {
    Flag,
    Warn,
    Error,
}

/// Identifies a state variable and the column index of its initial value.
#[derive(Deserialize)]
pub struct StateSpec {
    pub name: String,
    pub initial_col_index: usize,
}

/// A single operation in the rollforward step sequence.
///
/// All index fields are pre-resolved by Python. `target_index` is the
/// zero-based index into the states slice. `input_index`, `rate_index`,
/// etc. reference input columns passed to the kernel.
#[derive(Deserialize)]
pub enum StepSpec {
    Add {
        target_index: usize,
        input_index: usize,
        label: Option<String>,
        expected_input_index: Option<usize>,
    },
    Subtract {
        target_index: usize,
        input_index: usize,
        label: Option<String>,
        expected_input_index: Option<usize>,
    },
    Charge {
        target_index: usize,
        input_index: usize,
        label: Option<String>,
        expected_input_index: Option<usize>,
    },
    Grow {
        target_index: usize,
        input_index: usize,
        label: Option<String>,
        expected_input_index: Option<usize>,
    },
    GrowCapped {
        target_index: usize,
        input_index: usize,
        rate_floor: f64,
        rate_cap: f64,
        label: Option<String>,
        expected_input_index: Option<usize>,
    },
    DeductNar {
        target_index: usize,
        rate_index: usize,
        db_index: usize,
        label: Option<String>,
        expected_input_index: Option<usize>,
    },
    Floor {
        target_index: usize,
        value: f64,
        label: Option<String>,
    },
    Cap {
        target_index: usize,
        value: f64,
        label: Option<String>,
    },
    RatchetTo {
        target_index: usize,
        other_state_index: usize,
        label: Option<String>,
    },
    ProRataWith {
        target_index: usize,
        capture_index: usize,
        amount_index: usize,
        label: Option<String>,
    },
    Capture {
        target_index: usize,
        capture_index: usize,
    },
    LapseIfZero {
        target_index: usize,
    },
    AddIf {
        target_index: usize,
        condition_index: usize,
        amount_index: usize,
        label: Option<String>,
    },
    ChargeIf {
        target_index: usize,
        condition_index: usize,
        rate_index: usize,
        label: Option<String>,
    },
}

impl StepSpec {
    /// Returns the index of the state that this step writes to.
    pub fn target_index(&self) -> usize {
        match self {
            Self::Add { target_index, .. }
            | Self::Subtract { target_index, .. }
            | Self::Charge { target_index, .. }
            | Self::Grow { target_index, .. }
            | Self::GrowCapped { target_index, .. }
            | Self::DeductNar { target_index, .. }
            | Self::Floor { target_index, .. }
            | Self::Cap { target_index, .. }
            | Self::RatchetTo { target_index, .. }
            | Self::ProRataWith { target_index, .. }
            | Self::Capture { target_index, .. }
            | Self::LapseIfZero { target_index }
            | Self::AddIf { target_index, .. }
            | Self::ChargeIf { target_index, .. } => *target_index,
        }
    }

    /// Returns the human-readable label for this step, if any.
    ///
    /// `Capture` and `LapseIfZero` have no label field and always return `None`.
    pub fn label(&self) -> Option<&str> {
        match self {
            Self::Add { label, .. }
            | Self::Subtract { label, .. }
            | Self::Charge { label, .. }
            | Self::Grow { label, .. }
            | Self::GrowCapped { label, .. }
            | Self::DeductNar { label, .. }
            | Self::Floor { label, .. }
            | Self::Cap { label, .. }
            | Self::RatchetTo { label, .. }
            | Self::ProRataWith { label, .. }
            | Self::AddIf { label, .. }
            | Self::ChargeIf { label, .. } => label.as_deref(),
            Self::Capture { .. } | Self::LapseIfZero { .. } => None,
        }
    }
}

/// Condition under which a policy lapses during the rollforward.
#[derive(Deserialize)]
pub enum LapseCondition {
    AllNonPositive { state_indices: Vec<usize> },
}

/// Rollforward kernel for non-linear account value projections.
///
/// Receives pre-resolved column indices from Python's `_compile()` method and
/// dispatches step operations in the inner loop. For single-state, returns a
/// Struct with a `"result"` field. For multi-state, returns a Struct with one
/// field per state (named by `StateSpec::name`) plus optional increment fields.
///
/// # Arguments
///
/// * `inputs` - Array of Series: initial value scalars and list input columns.
///   Index mapping is pre-resolved by Python. `inputs[state.initial_col_index]`
///   gives the initial scalar; `inputs[step.input_index]` gives list columns.
/// * `kwargs` - Pre-compiled rollforward configuration with states and steps.
///
/// # Errors
///
/// Returns `PolarsError::ComputeError` if:
/// - No states are specified
/// - Input columns contain nulls (slow path not yet implemented)
/// - Inner list lengths are mismatched across columns within a row
/// - Input columns are not List type or initial values are not castable to Float64
pub fn rollforward(inputs: &[Series], kwargs: &RollforwardKwargs) -> PolarsResult<Series> {
    if kwargs.states.is_empty() {
        return Err(PolarsError::ComputeError(
            "rollforward: at least one state is required".into(),
        ));
    }

    // 1. Collect all list column indices referenced by steps
    let list_input_indices: Vec<usize> = collect_list_input_indices(&kwargs.steps);

    // Extract and validate list columns for nulls
    let list_columns: Vec<&ListChunked> = list_input_indices
        .iter()
        .map(|&idx| {
            inputs[idx].list().map_err(|_| {
                PolarsError::ComputeError(
                    format!("rollforward: input at index {} must be List dtype", idx).into(),
                )
            })
        })
        .collect::<PolarsResult<Vec<_>>>()?;

    for (i, lc) in list_columns.iter().enumerate() {
        if lc.null_count() > 0 {
            return Err(PolarsError::ComputeError(
                format!(
                    "rollforward: null outer list at input index {} not yet supported",
                    list_input_indices[i]
                )
                .into(),
            ));
        }
        // Check inner nulls
        let rechunked = lc.rechunk();
        let inner_nulls = rechunked
            .downcast_iter()
            .next()
            .map(|arr| arr.values().null_count())
            .unwrap_or(0);
        if inner_nulls > 0 {
            return Err(PolarsError::ComputeError(
                format!(
                    "rollforward: null inner values at input index {} not yet supported",
                    list_input_indices[i]
                )
                .into(),
            ));
        }
    }

    // 2. Route to single-state or multi-state path
    let output_series = if kwargs.states.len() == 1 {
        let state_spec = &kwargs.states[0];
        let initial = &inputs[state_spec.initial_col_index];
        let initial_f64 = initial.cast(&DataType::Float64)?;
        let initial_ca = initial_f64.f64()?;
        let initial_is_broadcast = initial_ca.len() == 1;

        if initial_ca.null_count() > 0 {
            return Err(PolarsError::ComputeError(
                "rollforward: null initial values not yet supported (slow path not implemented)"
                    .into(),
            ));
        }

        rollforward_fast_single_state(
            initial_ca,
            initial_is_broadcast,
            inputs,
            &kwargs.steps,
            &list_input_indices,
            kwargs.num_captures,
            kwargs.track_increments,
        )?
    } else {
        // Multi-state: extract and validate all initial value columns
        let mut initial_columns: Vec<(&Float64Chunked, bool)> = Vec::with_capacity(kwargs.states.len());
        // We need owned copies because cast() returns owned Series
        let mut initial_owned: Vec<Series> = Vec::with_capacity(kwargs.states.len());

        for state_spec in &kwargs.states {
            let initial = &inputs[state_spec.initial_col_index];
            let initial_f64 = initial.cast(&DataType::Float64)?;
            initial_owned.push(initial_f64);
        }

        for s in &initial_owned {
            let ca = s.f64()?;
            if ca.null_count() > 0 {
                return Err(PolarsError::ComputeError(
                    "rollforward: null initial values not yet supported (slow path not implemented)"
                        .into(),
                ));
            }
            let is_broadcast = ca.len() == 1;
            initial_columns.push((ca, is_broadcast));
        }

        rollforward_fast_multi_state(
            &initial_columns,
            inputs,
            &kwargs.states,
            &kwargs.steps,
            &list_input_indices,
            kwargs.num_captures,
            kwargs.track_increments,
            &kwargs.lapse_condition,
        )?
    };

    // 3. Wrap result(s) in Struct
    let num_rows = output_series[0].len();
    let struct_chunked = StructChunked::from_series(
        PlSmallStr::from_static("rollforward"),
        num_rows,
        output_series.iter(),
    )?;

    Ok(struct_chunked.into_series())
}

/// Collects the unique set of input column indices referenced by steps,
/// preserving order of first occurrence.
fn collect_list_input_indices(steps: &[StepSpec]) -> Vec<usize> {
    let mut indices = Vec::new();
    for step in steps {
        let idx = match step {
            StepSpec::Add { input_index, .. }
            | StepSpec::Subtract { input_index, .. }
            | StepSpec::Charge { input_index, .. }
            | StepSpec::Grow { input_index, .. }
            | StepSpec::GrowCapped { input_index, .. } => Some(*input_index),
            StepSpec::DeductNar {
                rate_index,
                db_index,
                ..
            } => {
                // DeductNar references two inputs
                if !indices.contains(rate_index) {
                    indices.push(*rate_index);
                }
                if !indices.contains(db_index) {
                    indices.push(*db_index);
                }
                None
            }
            StepSpec::AddIf {
                condition_index,
                amount_index,
                ..
            } => {
                if !indices.contains(condition_index) {
                    indices.push(*condition_index);
                }
                if !indices.contains(amount_index) {
                    indices.push(*amount_index);
                }
                None
            }
            StepSpec::ChargeIf {
                condition_index,
                rate_index,
                ..
            } => {
                if !indices.contains(condition_index) {
                    indices.push(*condition_index);
                }
                if !indices.contains(rate_index) {
                    indices.push(*rate_index);
                }
                None
            }
            StepSpec::ProRataWith { amount_index, .. } => Some(*amount_index),
            StepSpec::Floor { .. }
            | StepSpec::Cap { .. }
            | StepSpec::RatchetTo { .. }
            | StepSpec::Capture { .. }
            | StepSpec::LapseIfZero { .. } => None,
        };
        if let Some(i) = idx {
            if !indices.contains(&i) {
                indices.push(i);
            }
        }
    }
    indices
}

/// Fast path for single-state rollforward with no nulls.
///
/// Works directly with underlying arrays to avoid per-row allocations.
/// All list columns must have matching inner list lengths per row.
///
/// Returns a `Vec<Series>` where:
/// - `[0]` is always the `"result"` `List<Float64>` series
/// - `[1..]` are increment `List<Float64>` series, one per labeled step
///   (only present when `track_increments` is `true`)
fn rollforward_fast_single_state(
    initial_ca: &Float64Chunked,
    initial_is_broadcast: bool,
    inputs: &[Series],
    steps: &[StepSpec],
    list_input_indices: &[usize],
    num_captures: usize,
    track_increments: bool,
) -> PolarsResult<Vec<Series>> {
    // Build a mapping from input index to position in our extracted slices
    let index_to_slot: std::collections::HashMap<usize, usize> = list_input_indices
        .iter()
        .enumerate()
        .map(|(slot, &idx)| (idx, slot))
        .collect();

    // Owned slice storage for each list column: offsets + flat values
    struct OwnedListSlice {
        offsets: Vec<i64>,
        values: Vec<f64>,
    }

    let mut owned_slices: Vec<OwnedListSlice> = Vec::with_capacity(list_input_indices.len());

    for &col_idx in list_input_indices {
        let list_ca = inputs[col_idx].list()?;
        let rechunked = list_ca.rechunk();
        let arr = rechunked.downcast_iter().next().unwrap();

        let offsets = arr.offsets().as_slice().to_vec();

        let inner_dtype = list_ca.inner_dtype();
        // SAFETY: dtype matches the array
        let values_series = unsafe {
            Series::from_chunks_and_dtype_unchecked(
                PlSmallStr::EMPTY,
                vec![arr.values().clone()],
                &inner_dtype.to_physical(),
            )
        }
        .cast(&DataType::Float64)?;

        let values_f64 = values_series.f64()?;
        let values_rechunked = values_f64.rechunk();
        let values = values_rechunked
            .cont_slice()
            .map_err(|_| {
                PolarsError::ComputeError(
                    format!(
                        "rollforward: values not contiguous at input index {}",
                        col_idx
                    )
                    .into(),
                )
            })?
            .to_vec();

        owned_slices.push(OwnedListSlice { offsets, values });
    }

    // Determine number of rows from the first list column (or initial if no list cols)
    let num_rows = if owned_slices.is_empty() {
        initial_ca.len()
    } else {
        owned_slices[0].offsets.len() - 1
    };

    // Get initial values as a contiguous slice
    let initial_rechunked = initial_ca.rechunk();
    let initial_slice = initial_rechunked
        .cont_slice()
        .map_err(|_| PolarsError::ComputeError("rollforward: initial values not contiguous".into()))?;

    // Pre-calculate total output length from the first list column's offsets
    // (or 0 if no list columns)
    let total_len: usize = if owned_slices.is_empty() {
        0
    } else {
        *owned_slices[0].offsets.last().unwrap_or(&0) as usize
    };

    let mut output_values: Vec<f64> = Vec::with_capacity(total_len);
    let mut output_offsets: Vec<i64> = Vec::with_capacity(num_rows + 1);
    output_offsets.push(0);

    // Captures buffer: one slot per capture index, reset per row
    let mut captures: Vec<f64> = vec![0.0; num_captures];

    // Increment tracking setup: build label names and per-step buffer index mapping
    // step_label_buf_idx[i] = Some(buf_idx) if steps[i] has a label and track_increments is on
    let label_names: Vec<String>;
    let step_label_buf_idx: Vec<Option<usize>>;
    let mut increment_buffers: Vec<Vec<f64>>;
    let mut increment_offsets: Vec<Vec<i64>>;

    if track_increments {
        let mut names: Vec<String> = Vec::new();
        let mut mapping: Vec<Option<usize>> = Vec::with_capacity(steps.len());
        for step in steps {
            if let Some(lbl) = step.label() {
                let buf_idx = names.len();
                names.push(lbl.to_string());
                mapping.push(Some(buf_idx));
            } else {
                mapping.push(None);
            }
        }
        let num_labels = names.len();
        label_names = names;
        step_label_buf_idx = mapping;
        increment_buffers = (0..num_labels)
            .map(|_| Vec::with_capacity(total_len))
            .collect();
        increment_offsets = (0..num_labels)
            .map(|_| {
                let mut v = Vec::with_capacity(num_rows + 1);
                v.push(0i64);
                v
            })
            .collect();
    } else {
        label_names = Vec::new();
        step_label_buf_idx = Vec::new();
        increment_buffers = Vec::new();
        increment_offsets = Vec::new();
    }

    for row_idx in 0..num_rows {
        // Determine timestep count from the first list column
        let timesteps = if owned_slices.is_empty() {
            0usize
        } else {
            let start = owned_slices[0].offsets[row_idx] as usize;
            let end = owned_slices[0].offsets[row_idx + 1] as usize;
            end - start
        };

        // Verify all list columns have the same length for this row
        for (slot, slice) in owned_slices.iter().enumerate() {
            let s = slice.offsets[row_idx] as usize;
            let e = slice.offsets[row_idx + 1] as usize;
            let len = e - s;
            if len != timesteps {
                return Err(PolarsError::ComputeError(
                    format!(
                        "rollforward: mismatched inner list lengths at row {}: expected {}, got {} at input index {}",
                        row_idx, timesteps, len, list_input_indices[slot]
                    )
                    .into(),
                ));
            }
        }

        // Get initial value (broadcast or per-row)
        let initial_idx = if initial_is_broadcast { 0 } else { row_idx };
        let mut state = initial_slice[initial_idx];

        // Reset captures for this row
        for c in captures.iter_mut() {
            *c = 0.0;
        }

        // For each timestep, dispatch all steps
        let mut lapsed = false;
        for t in 0..timesteps {
            for (step_idx, step) in steps.iter().enumerate() {
                let av_before = state;
                match step {
                    StepSpec::Add { input_index, .. } => {
                        let slot = index_to_slot[input_index];
                        let flat_idx = owned_slices[slot].offsets[row_idx] as usize + t;
                        state += owned_slices[slot].values[flat_idx];
                    }
                    StepSpec::Subtract { input_index, .. } => {
                        let slot = index_to_slot[input_index];
                        let flat_idx = owned_slices[slot].offsets[row_idx] as usize + t;
                        state -= owned_slices[slot].values[flat_idx];
                    }
                    StepSpec::Charge { input_index, .. } => {
                        let slot = index_to_slot[input_index];
                        let flat_idx = owned_slices[slot].offsets[row_idx] as usize + t;
                        state *= 1.0 - owned_slices[slot].values[flat_idx];
                    }
                    StepSpec::Grow { input_index, .. } => {
                        let slot = index_to_slot[input_index];
                        let flat_idx = owned_slices[slot].offsets[row_idx] as usize + t;
                        state *= 1.0 + owned_slices[slot].values[flat_idx];
                    }
                    StepSpec::GrowCapped {
                        input_index,
                        rate_floor,
                        rate_cap,
                        ..
                    } => {
                        let slot = index_to_slot[input_index];
                        let flat_idx = owned_slices[slot].offsets[row_idx] as usize + t;
                        let rate = owned_slices[slot].values[flat_idx];
                        state *= 1.0 + rate.clamp(*rate_floor, *rate_cap);
                    }
                    StepSpec::DeductNar {
                        rate_index,
                        db_index,
                        ..
                    } => {
                        let rate_slot = index_to_slot[rate_index];
                        let db_slot = index_to_slot[db_index];
                        let rate_flat = owned_slices[rate_slot].offsets[row_idx] as usize + t;
                        let db_flat = owned_slices[db_slot].offsets[row_idx] as usize + t;
                        let rate = owned_slices[rate_slot].values[rate_flat];
                        let db = owned_slices[db_slot].values[db_flat];
                        let nar = f64::max(0.0, db - state);
                        state -= rate * nar;
                    }
                    StepSpec::Floor { value, .. } => {
                        state = f64::max(state, *value);
                    }
                    StepSpec::Cap { value, .. } => {
                        state = f64::min(state, *value);
                    }
                    StepSpec::AddIf {
                        condition_index,
                        amount_index,
                        ..
                    } => {
                        let cond_slot = index_to_slot[condition_index];
                        let amt_slot = index_to_slot[amount_index];
                        let cond_flat = owned_slices[cond_slot].offsets[row_idx] as usize + t;
                        let amt_flat = owned_slices[amt_slot].offsets[row_idx] as usize + t;
                        if owned_slices[cond_slot].values[cond_flat] > 0.0 {
                            state += owned_slices[amt_slot].values[amt_flat];
                        }
                    }
                    StepSpec::ChargeIf {
                        condition_index,
                        rate_index,
                        ..
                    } => {
                        let cond_slot = index_to_slot[condition_index];
                        let rate_slot = index_to_slot[rate_index];
                        let cond_flat = owned_slices[cond_slot].offsets[row_idx] as usize + t;
                        let rate_flat = owned_slices[rate_slot].offsets[row_idx] as usize + t;
                        if owned_slices[cond_slot].values[cond_flat] > 0.0 {
                            state *= 1.0 - owned_slices[rate_slot].values[rate_flat];
                        }
                    }
                    StepSpec::LapseIfZero { .. } => {
                        if state <= 0.0 {
                            lapsed = true;
                        }
                    }
                    StepSpec::Capture { capture_index, .. } => {
                        captures[*capture_index] = state;
                    }
                    StepSpec::RatchetTo { .. } | StepSpec::ProRataWith { .. } => {
                        panic!(
                            "rollforward: multi-state step variant not yet implemented in single-state fast path"
                        );
                    }
                }
                // Record increment for this step if tracking is on and the step has a label
                if track_increments {
                    if let Some(buf_idx) = step_label_buf_idx[step_idx] {
                        increment_buffers[buf_idx].push(state - av_before);
                    }
                }
            }
            output_values.push(state);

            if lapsed {
                // Zero all remaining timesteps and exit the timestep loop
                let remaining = timesteps - t - 1;
                for _ in 0..remaining {
                    output_values.push(0.0);
                }
                // Push zeros into all increment buffers for the remaining timesteps
                if track_increments {
                    for buf in increment_buffers.iter_mut() {
                        for _ in 0..remaining {
                            buf.push(0.0);
                        }
                    }
                }
                break;
            }
        }

        output_offsets.push(output_values.len() as i64);

        // After each row, record current position in each increment offset vec
        if track_increments {
            for (buf_idx, buf) in increment_buffers.iter().enumerate() {
                increment_offsets[buf_idx].push(buf.len() as i64);
            }
        }
    }

    // Helper closure to build a List<Float64> Series from flat values + offsets
    let build_list_series = |flat_values: Vec<f64>, offsets_vec: Vec<i64>, name: PlSmallStr| -> Series {
        // SAFETY: offsets are monotonically increasing and valid
        let offsets = unsafe { OffsetsBuffer::new_unchecked(offsets_vec.into()) };
        let values_arr = PrimitiveArray::from_vec(flat_values);
        let list_arr = LargeListArray::new(
            ArrowDataType::LargeList(Box::new(ArrowField::new(
                PlSmallStr::from_static("item"),
                ArrowDataType::Float64,
                true,
            ))),
            offsets,
            Box::new(values_arr),
            None, // no validity — no nulls in fast path
        );
        // SAFETY: we constructed this correctly
        let chunked =
            unsafe { ListChunked::from_chunks(name, vec![Box::new(list_arr)]) };
        chunked.into_series()
    };

    // Build "result" series
    let result_series =
        build_list_series(output_values, output_offsets, PlSmallStr::from_static("result"));

    let mut output_series: Vec<Series> = Vec::with_capacity(1 + increment_buffers.len());
    output_series.push(result_series);

    // Build increment series (one per label, in label order)
    for (buf_idx, (flat_values, offsets_vec)) in increment_buffers
        .into_iter()
        .zip(increment_offsets.into_iter())
        .enumerate()
    {
        let name = PlSmallStr::from(label_names[buf_idx].as_str());
        output_series.push(build_list_series(flat_values, offsets_vec, name));
    }

    Ok(output_series)
}

/// Fast path for multi-state rollforward with no nulls.
///
/// Uses a `Vec<f64>` state array indexed by `target_index`. Supports
/// cross-state operations (`RatchetTo`, `ProRataWith`) and a
/// `LapseCondition` that checks multiple states at end of each timestep.
///
/// Returns a `Vec<Series>` where:
/// - `[0..num_states]` are named `List<Float64>` series, one per state
/// - `[num_states..]` are increment `List<Float64>` series, one per labeled step
///   (only present when `track_increments` is `true`)
#[allow(clippy::too_many_arguments)]
fn rollforward_fast_multi_state(
    initial_columns: &[(&Float64Chunked, bool)],
    inputs: &[Series],
    state_specs: &[StateSpec],
    steps: &[StepSpec],
    list_input_indices: &[usize],
    num_captures: usize,
    track_increments: bool,
    lapse_condition: &Option<LapseCondition>,
) -> PolarsResult<Vec<Series>> {
    let num_states = state_specs.len();

    // Build a mapping from input index to position in our extracted slices
    let index_to_slot: std::collections::HashMap<usize, usize> = list_input_indices
        .iter()
        .enumerate()
        .map(|(slot, &idx)| (idx, slot))
        .collect();

    // Owned slice storage for each list column: offsets + flat values
    struct OwnedListSlice {
        offsets: Vec<i64>,
        values: Vec<f64>,
    }

    let mut owned_slices: Vec<OwnedListSlice> = Vec::with_capacity(list_input_indices.len());

    for &col_idx in list_input_indices {
        let list_ca = inputs[col_idx].list()?;
        let rechunked = list_ca.rechunk();
        let arr = rechunked.downcast_iter().next().unwrap();

        let offsets = arr.offsets().as_slice().to_vec();

        let inner_dtype = list_ca.inner_dtype();
        // SAFETY: dtype matches the array
        let values_series = unsafe {
            Series::from_chunks_and_dtype_unchecked(
                PlSmallStr::EMPTY,
                vec![arr.values().clone()],
                &inner_dtype.to_physical(),
            )
        }
        .cast(&DataType::Float64)?;

        let values_f64 = values_series.f64()?;
        let values_rechunked = values_f64.rechunk();
        let values = values_rechunked
            .cont_slice()
            .map_err(|_| {
                PolarsError::ComputeError(
                    format!(
                        "rollforward: values not contiguous at input index {}",
                        col_idx
                    )
                    .into(),
                )
            })?
            .to_vec();

        owned_slices.push(OwnedListSlice { offsets, values });
    }

    // Determine number of rows from the first list column (or first initial if no list cols)
    let num_rows = if owned_slices.is_empty() {
        initial_columns[0].0.len()
    } else {
        owned_slices[0].offsets.len() - 1
    };

    // Get initial values as contiguous slices for each state
    let initial_slices: Vec<(Vec<f64>, bool)> = initial_columns
        .iter()
        .map(|(ca, is_broadcast)| {
            let rechunked = ca.rechunk();
            let slice = rechunked.cont_slice().map_err(|_| {
                PolarsError::ComputeError("rollforward: initial values not contiguous".into())
            })?;
            Ok((slice.to_vec(), *is_broadcast))
        })
        .collect::<PolarsResult<Vec<_>>>()?;

    // Pre-calculate total output length from the first list column's offsets
    let total_len: usize = if owned_slices.is_empty() {
        0
    } else {
        *owned_slices[0].offsets.last().unwrap_or(&0) as usize
    };

    // Per-state output buffers
    let mut result_buffers: Vec<Vec<f64>> = (0..num_states)
        .map(|_| Vec::with_capacity(total_len))
        .collect();
    let mut result_offsets: Vec<Vec<i64>> = (0..num_states)
        .map(|_| {
            let mut v = Vec::with_capacity(num_rows + 1);
            v.push(0i64);
            v
        })
        .collect();

    // Captures buffer: one slot per capture index, reset per row
    let mut captures: Vec<f64> = vec![0.0; num_captures];

    // Increment tracking setup
    let label_names: Vec<String>;
    let step_label_buf_idx: Vec<Option<usize>>;
    let mut increment_buffers: Vec<Vec<f64>>;
    let mut increment_offsets: Vec<Vec<i64>>;

    if track_increments {
        let mut names: Vec<String> = Vec::new();
        let mut mapping: Vec<Option<usize>> = Vec::with_capacity(steps.len());
        for step in steps {
            if let Some(lbl) = step.label() {
                let buf_idx = names.len();
                names.push(lbl.to_string());
                mapping.push(Some(buf_idx));
            } else {
                mapping.push(None);
            }
        }
        let num_labels = names.len();
        label_names = names;
        step_label_buf_idx = mapping;
        increment_buffers = (0..num_labels)
            .map(|_| Vec::with_capacity(total_len))
            .collect();
        increment_offsets = (0..num_labels)
            .map(|_| {
                let mut v = Vec::with_capacity(num_rows + 1);
                v.push(0i64);
                v
            })
            .collect();
    } else {
        label_names = Vec::new();
        step_label_buf_idx = Vec::new();
        increment_buffers = Vec::new();
        increment_offsets = Vec::new();
    }

    for row_idx in 0..num_rows {
        // Determine timestep count from the first list column
        let timesteps = if owned_slices.is_empty() {
            0usize
        } else {
            let start = owned_slices[0].offsets[row_idx] as usize;
            let end = owned_slices[0].offsets[row_idx + 1] as usize;
            end - start
        };

        // Verify all list columns have the same length for this row
        for (slot, slice) in owned_slices.iter().enumerate() {
            let s = slice.offsets[row_idx] as usize;
            let e = slice.offsets[row_idx + 1] as usize;
            let len = e - s;
            if len != timesteps {
                return Err(PolarsError::ComputeError(
                    format!(
                        "rollforward: mismatched inner list lengths at row {}: expected {}, got {} at input index {}",
                        row_idx, timesteps, len, list_input_indices[slot]
                    )
                    .into(),
                ));
            }
        }

        // Initialize state vector from per-state initial value columns
        let mut states: Vec<f64> = (0..num_states)
            .map(|i| {
                let (ref slice, is_broadcast) = initial_slices[i];
                let idx = if is_broadcast { 0 } else { row_idx };
                slice[idx]
            })
            .collect();

        // Reset captures for this row
        for c in captures.iter_mut() {
            *c = 0.0;
        }

        // For each timestep, dispatch all steps
        let mut lapsed = false;
        for t in 0..timesteps {
            for (step_idx, step) in steps.iter().enumerate() {
                let ti = step.target_index();
                let state_before = states[ti];
                match step {
                    StepSpec::Add { input_index, .. } => {
                        let slot = index_to_slot[input_index];
                        let flat_idx = owned_slices[slot].offsets[row_idx] as usize + t;
                        states[ti] += owned_slices[slot].values[flat_idx];
                    }
                    StepSpec::Subtract { input_index, .. } => {
                        let slot = index_to_slot[input_index];
                        let flat_idx = owned_slices[slot].offsets[row_idx] as usize + t;
                        states[ti] -= owned_slices[slot].values[flat_idx];
                    }
                    StepSpec::Charge { input_index, .. } => {
                        let slot = index_to_slot[input_index];
                        let flat_idx = owned_slices[slot].offsets[row_idx] as usize + t;
                        states[ti] *= 1.0 - owned_slices[slot].values[flat_idx];
                    }
                    StepSpec::Grow { input_index, .. } => {
                        let slot = index_to_slot[input_index];
                        let flat_idx = owned_slices[slot].offsets[row_idx] as usize + t;
                        states[ti] *= 1.0 + owned_slices[slot].values[flat_idx];
                    }
                    StepSpec::GrowCapped {
                        input_index,
                        rate_floor,
                        rate_cap,
                        ..
                    } => {
                        let slot = index_to_slot[input_index];
                        let flat_idx = owned_slices[slot].offsets[row_idx] as usize + t;
                        let rate = owned_slices[slot].values[flat_idx];
                        states[ti] *= 1.0 + rate.clamp(*rate_floor, *rate_cap);
                    }
                    StepSpec::DeductNar {
                        rate_index,
                        db_index,
                        ..
                    } => {
                        let rate_slot = index_to_slot[rate_index];
                        let db_slot = index_to_slot[db_index];
                        let rate_flat = owned_slices[rate_slot].offsets[row_idx] as usize + t;
                        let db_flat = owned_slices[db_slot].offsets[row_idx] as usize + t;
                        let rate = owned_slices[rate_slot].values[rate_flat];
                        let db = owned_slices[db_slot].values[db_flat];
                        let nar = f64::max(0.0, db - states[ti]);
                        states[ti] -= rate * nar;
                    }
                    StepSpec::Floor { value, .. } => {
                        states[ti] = f64::max(states[ti], *value);
                    }
                    StepSpec::Cap { value, .. } => {
                        states[ti] = f64::min(states[ti], *value);
                    }
                    StepSpec::AddIf {
                        condition_index,
                        amount_index,
                        ..
                    } => {
                        let cond_slot = index_to_slot[condition_index];
                        let amt_slot = index_to_slot[amount_index];
                        let cond_flat = owned_slices[cond_slot].offsets[row_idx] as usize + t;
                        let amt_flat = owned_slices[amt_slot].offsets[row_idx] as usize + t;
                        if owned_slices[cond_slot].values[cond_flat] > 0.0 {
                            states[ti] += owned_slices[amt_slot].values[amt_flat];
                        }
                    }
                    StepSpec::ChargeIf {
                        condition_index,
                        rate_index,
                        ..
                    } => {
                        let cond_slot = index_to_slot[condition_index];
                        let rate_slot = index_to_slot[rate_index];
                        let cond_flat = owned_slices[cond_slot].offsets[row_idx] as usize + t;
                        let rate_flat = owned_slices[rate_slot].offsets[row_idx] as usize + t;
                        if owned_slices[cond_slot].values[cond_flat] > 0.0 {
                            states[ti] *= 1.0 - owned_slices[rate_slot].values[rate_flat];
                        }
                    }
                    StepSpec::LapseIfZero { .. } => {
                        if states[ti] <= 0.0 {
                            lapsed = true;
                        }
                    }
                    StepSpec::Capture { capture_index, .. } => {
                        captures[*capture_index] = states[ti];
                    }
                    StepSpec::RatchetTo {
                        other_state_index, ..
                    } => {
                        states[ti] = f64::max(states[ti], states[*other_state_index]);
                    }
                    StepSpec::ProRataWith {
                        capture_index,
                        amount_index,
                        ..
                    } => {
                        let ref_val = captures[*capture_index];
                        if ref_val > 0.0 {
                            let amt_slot = index_to_slot[amount_index];
                            let amt_flat = owned_slices[amt_slot].offsets[row_idx] as usize + t;
                            states[ti] *=
                                1.0 - owned_slices[amt_slot].values[amt_flat] / ref_val;
                        }
                    }
                }
                // Record increment for this step if tracking is on and the step has a label
                if track_increments {
                    if let Some(buf_idx) = step_label_buf_idx[step_idx] {
                        increment_buffers[buf_idx].push(states[ti] - state_before);
                    }
                }
            }

            // Record all state values at this timestep
            for i in 0..num_states {
                result_buffers[i].push(states[i]);
            }

            if lapsed {
                // Zero remaining timesteps across all states and increments
                let remaining = timesteps - t - 1;
                for _ in 0..remaining {
                    for buf in result_buffers.iter_mut() {
                        buf.push(0.0);
                    }
                    if track_increments {
                        for buf in increment_buffers.iter_mut() {
                            buf.push(0.0);
                        }
                    }
                }
                break;
            }

            // Check cross-state lapse condition at end of timestep
            if let Some(LapseCondition::AllNonPositive { ref state_indices }) = lapse_condition {
                if state_indices.iter().all(|&i| states[i] <= 0.0) {
                    let remaining = timesteps - t - 1;
                    for _ in 0..remaining {
                        for buf in result_buffers.iter_mut() {
                            buf.push(0.0);
                        }
                        if track_increments {
                            for buf in increment_buffers.iter_mut() {
                                buf.push(0.0);
                            }
                        }
                    }
                    break;
                }
            }
        }

        // Record offsets for all state buffers
        for i in 0..num_states {
            result_offsets[i].push(result_buffers[i].len() as i64);
        }

        // Record offsets for increment buffers
        if track_increments {
            for (buf_idx, buf) in increment_buffers.iter().enumerate() {
                increment_offsets[buf_idx].push(buf.len() as i64);
            }
        }
    }

    // Helper closure to build a List<Float64> Series from flat values + offsets
    let build_list_series =
        |flat_values: Vec<f64>, offsets_vec: Vec<i64>, name: PlSmallStr| -> Series {
            // SAFETY: offsets are monotonically increasing and valid
            let offsets = unsafe { OffsetsBuffer::new_unchecked(offsets_vec.into()) };
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
            // SAFETY: we constructed this correctly
            let chunked = unsafe { ListChunked::from_chunks(name, vec![Box::new(list_arr)]) };
            chunked.into_series()
        };

    // Build per-state series (named by state_specs[i].name)
    let mut output_series: Vec<Series> =
        Vec::with_capacity(num_states + increment_buffers.len());

    for i in 0..num_states {
        let name = PlSmallStr::from(state_specs[i].name.as_str());
        let flat = std::mem::take(&mut result_buffers[i]);
        let offs = std::mem::take(&mut result_offsets[i]);
        output_series.push(build_list_series(flat, offs, name));
    }

    // Build increment series (one per label, in label order)
    for (buf_idx, (flat_values, offsets_vec)) in increment_buffers
        .into_iter()
        .zip(increment_offsets.into_iter())
        .enumerate()
    {
        let name = PlSmallStr::from(label_names[buf_idx].as_str());
        output_series.push(build_list_series(flat_values, offsets_vec, name));
    }

    Ok(output_series)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_kwargs_deserialization() {
        let json = r#"
        {
            "states": [
                { "name": "account_value", "initial_col_index": 0 }
            ],
            "steps": [
                {
                    "Add": {
                        "target_index": 0,
                        "input_index": 1,
                        "label": "premium",
                        "expected_input_index": null
                    }
                }
            ],
            "track_increments": false,
            "assertion_mode": null,
            "num_captures": 0,
            "lapse_condition": null
        }
        "#;

        let kwargs: RollforwardKwargs =
            serde_json::from_str(json).expect("deserialization should succeed");

        assert_eq!(kwargs.states.len(), 1);
        assert_eq!(kwargs.states[0].name, "account_value");
        assert_eq!(kwargs.states[0].initial_col_index, 0);

        assert_eq!(kwargs.steps.len(), 1);
        assert_eq!(kwargs.steps[0].target_index(), 0);
        assert_eq!(kwargs.steps[0].label(), Some("premium"));

        assert!(!kwargs.track_increments);
        assert!(kwargs.assertion_mode.is_none());
        assert_eq!(kwargs.num_captures, 0);
        assert!(kwargs.lapse_condition.is_none());
    }

    #[test]
    fn test_multi_state_kwargs() {
        let json = r#"
        {
            "states": [
                { "name": "account_value", "initial_col_index": 0 },
                { "name": "gmdb_benefit_base", "initial_col_index": 1 }
            ],
            "steps": [
                {
                    "Grow": {
                        "target_index": 0,
                        "input_index": 2,
                        "label": "crediting",
                        "expected_input_index": null
                    }
                },
                {
                    "RatchetTo": {
                        "target_index": 1,
                        "other_state_index": 0,
                        "label": "ratchet_db"
                    }
                },
                {
                    "LapseIfZero": {
                        "target_index": 0
                    }
                }
            ],
            "track_increments": true,
            "assertion_mode": "Warn",
            "num_captures": 2,
            "lapse_condition": {
                "AllNonPositive": {
                    "state_indices": [0, 1]
                }
            }
        }
        "#;

        let kwargs: RollforwardKwargs =
            serde_json::from_str(json).expect("deserialization should succeed");

        assert_eq!(kwargs.states.len(), 2);
        assert_eq!(kwargs.states[1].name, "gmdb_benefit_base");

        assert_eq!(kwargs.steps.len(), 3);

        // RatchetTo step
        let ratchet = &kwargs.steps[1];
        assert_eq!(ratchet.target_index(), 1);
        assert_eq!(ratchet.label(), Some("ratchet_db"));

        // LapseIfZero step — no label
        let lapse_step = &kwargs.steps[2];
        assert_eq!(lapse_step.target_index(), 0);
        assert_eq!(lapse_step.label(), None);

        assert!(kwargs.track_increments);
        assert!(matches!(
            kwargs.assertion_mode,
            Some(AssertionMode::Warn)
        ));
        assert_eq!(kwargs.num_captures, 2);

        match &kwargs.lapse_condition {
            Some(LapseCondition::AllNonPositive { state_indices }) => {
                assert_eq!(state_indices, &[0, 1]);
            }
            None => panic!("expected lapse_condition to be Some"),
        }
    }

    /// Helper to build kwargs for single-state rollforward tests.
    fn make_single_state_kwargs(initial_col_index: usize, steps: Vec<StepSpec>) -> RollforwardKwargs {
        RollforwardKwargs {
            states: vec![StateSpec {
                name: "av".to_string(),
                initial_col_index,
            }],
            steps,
            track_increments: false,
            assertion_mode: None,
            num_captures: 0,
            lapse_condition: None,
        }
    }

    #[test]
    fn test_single_state_add_only() {
        // initial=1000, premium=[100,100,100]
        // t0: 1000 + 100 = 1100
        // t1: 1100 + 100 = 1200
        // t2: 1200 + 100 = 1300
        let initial = Series::new("initial".into(), vec![1000.0_f64]);
        let premium = ListChunked::from_iter([Some(Series::new(
            "".into(),
            vec![100.0, 100.0, 100.0],
        ))]);

        let kwargs = make_single_state_kwargs(
            0,
            vec![StepSpec::Add {
                target_index: 0,
                input_index: 1,
                label: Some("premium".to_string()),
                expected_input_index: None,
            }],
        );

        let result = rollforward(&[initial, premium.into_series()], &kwargs).unwrap();
        let s = result.struct_().unwrap();
        let av = s.field_by_name("result").unwrap();
        let row0 = av.list().unwrap().get_as_series(0).unwrap();
        let vals = row0.f64().unwrap();

        assert_eq!(vals.get(0), Some(1100.0));
        assert_eq!(vals.get(1), Some(1200.0));
        assert_eq!(vals.get(2), Some(1300.0));
    }

    #[test]
    fn test_single_state_charge_and_grow() {
        // initial=1000, admin_rate=[0.01], interest=[0.05]
        // t0: charge admin: 1000 * (1 - 0.01) = 990
        //     grow interest: 990 * (1 + 0.05) = 1039.5
        let initial = Series::new("initial".into(), vec![1000.0_f64]);
        let admin_rate = ListChunked::from_iter([Some(Series::new("".into(), vec![0.01]))]);
        let interest = ListChunked::from_iter([Some(Series::new("".into(), vec![0.05]))]);

        let kwargs = make_single_state_kwargs(
            0,
            vec![
                StepSpec::Charge {
                    target_index: 0,
                    input_index: 1,
                    label: Some("admin".to_string()),
                    expected_input_index: None,
                },
                StepSpec::Grow {
                    target_index: 0,
                    input_index: 2,
                    label: Some("interest".to_string()),
                    expected_input_index: None,
                },
            ],
        );

        let result =
            rollforward(&[initial, admin_rate.into_series(), interest.into_series()], &kwargs)
                .unwrap();
        let s = result.struct_().unwrap();
        let av = s.field_by_name("result").unwrap();
        let row0 = av.list().unwrap().get_as_series(0).unwrap();
        let vals = row0.f64().unwrap();

        assert!((vals.get(0).unwrap() - 1039.5).abs() < 1e-10);
    }

    #[test]
    fn test_floor_clamps_negative() {
        // initial=100, subtract=[150], floor(0)
        // t0: 100 - 150 = -50, then floor(0) → 0
        let initial = Series::new("initial".into(), vec![100.0_f64]);
        let withdraw = ListChunked::from_iter([Some(Series::new("".into(), vec![150.0]))]);

        let kwargs = make_single_state_kwargs(
            0,
            vec![
                StepSpec::Subtract {
                    target_index: 0,
                    input_index: 1,
                    label: Some("withdraw".to_string()),
                    expected_input_index: None,
                },
                StepSpec::Floor {
                    target_index: 0,
                    value: 0.0,
                    label: Some("floor_zero".to_string()),
                },
            ],
        );

        let result = rollforward(&[initial, withdraw.into_series()], &kwargs).unwrap();
        let s = result.struct_().unwrap();
        let av = s.field_by_name("result").unwrap();
        let row0 = av.list().unwrap().get_as_series(0).unwrap();
        let vals = row0.f64().unwrap();

        assert_eq!(vals.get(0), Some(0.0));
    }

    #[test]
    fn test_grow_capped() {
        // initial=1000, rate=[0.15, -0.05, 0.20], floor=0.0, cap=0.12
        // clamped rates: [0.12, 0.0, 0.12]
        // t0: 1000 * 1.12 = 1120.0
        // t1: 1120 * 1.0  = 1120.0
        // t2: 1120 * 1.12 = 1254.4
        let initial = Series::new("initial".into(), vec![1000.0_f64]);
        let rate = ListChunked::from_iter([Some(Series::new("".into(), vec![0.15_f64, -0.05, 0.20]))]);

        let kwargs = make_single_state_kwargs(
            0,
            vec![StepSpec::GrowCapped {
                target_index: 0,
                input_index: 1,
                rate_floor: 0.0,
                rate_cap: 0.12,
                label: Some("crediting".to_string()),
                expected_input_index: None,
            }],
        );

        let result = rollforward(&[initial, rate.into_series()], &kwargs).unwrap();
        let s = result.struct_().unwrap();
        let av = s.field_by_name("result").unwrap();
        let row0 = av.list().unwrap().get_as_series(0).unwrap();
        let vals = row0.f64().unwrap();

        assert!((vals.get(0).unwrap() - 1120.0).abs() < 1e-10, "t0 expected 1120.0, got {:?}", vals.get(0));
        assert!((vals.get(1).unwrap() - 1120.0).abs() < 1e-10, "t1 expected 1120.0, got {:?}", vals.get(1));
        assert!((vals.get(2).unwrap() - 1254.4).abs() < 1e-10, "t2 expected 1254.4, got {:?}", vals.get(2));
    }

    #[test]
    fn test_deduct_nar() {
        // initial=1000, coi_rate=[0.001], death_benefit=[5000]
        // NAR = max(0, 5000 - 1000) = 4000
        // COI  = 0.001 * 4000 = 4.0
        // AV   = 1000 - 4.0 = 996.0
        let initial = Series::new("initial".into(), vec![1000.0_f64]);
        let coi_rate = ListChunked::from_iter([Some(Series::new("".into(), vec![0.001_f64]))]);
        let death_benefit = ListChunked::from_iter([Some(Series::new("".into(), vec![5000.0_f64]))]);

        let kwargs = make_single_state_kwargs(
            0,
            vec![StepSpec::DeductNar {
                target_index: 0,
                rate_index: 1,
                db_index: 2,
                label: Some("coi".to_string()),
                expected_input_index: None,
            }],
        );

        let result = rollforward(
            &[initial, coi_rate.into_series(), death_benefit.into_series()],
            &kwargs,
        )
        .unwrap();
        let s = result.struct_().unwrap();
        let av = s.field_by_name("result").unwrap();
        let row0 = av.list().unwrap().get_as_series(0).unwrap();
        let vals = row0.f64().unwrap();

        assert!((vals.get(0).unwrap() - 996.0).abs() < 1e-10, "expected 996.0, got {:?}", vals.get(0));
    }

    #[test]
    fn test_lapse_if_zero() {
        // initial=50, subtract=[100, 100, 100]
        // t0: 50 - 100 = -50  → lapse fires after recording -50
        // t1: 0 (zeroed by lapse)
        // t2: 0 (zeroed by lapse)
        let initial = Series::new("initial".into(), vec![50.0_f64]);
        let subtract_vals = ListChunked::from_iter([Some(Series::new(
            "".into(),
            vec![100.0_f64, 100.0, 100.0],
        ))]);

        let kwargs = make_single_state_kwargs(
            0,
            vec![
                StepSpec::Subtract {
                    target_index: 0,
                    input_index: 1,
                    label: Some("withdraw".to_string()),
                    expected_input_index: None,
                },
                StepSpec::LapseIfZero { target_index: 0 },
            ],
        );

        let result = rollforward(&[initial, subtract_vals.into_series()], &kwargs).unwrap();
        let s = result.struct_().unwrap();
        let av = s.field_by_name("result").unwrap();
        let row0 = av.list().unwrap().get_as_series(0).unwrap();
        let vals = row0.f64().unwrap();

        assert!((vals.get(0).unwrap() - (-50.0)).abs() < 1e-10, "t0 expected -50.0, got {:?}", vals.get(0));
        assert_eq!(vals.get(1), Some(0.0), "t1 expected 0.0 after lapse");
        assert_eq!(vals.get(2), Some(0.0), "t2 expected 0.0 after lapse");
    }

    #[test]
    fn test_add_if() {
        // initial=1000, condition=[1.0, 0.0, 1.0], amount=[100, 100, 100]
        // t0: cond=1.0 → 1000 + 100 = 1100
        // t1: cond=0.0 → 1100 (no add)
        // t2: cond=1.0 → 1100 + 100 = 1200
        let initial = Series::new("initial".into(), vec![1000.0_f64]);
        let condition = ListChunked::from_iter([Some(Series::new(
            "".into(),
            vec![1.0_f64, 0.0, 1.0],
        ))]);
        let amount = ListChunked::from_iter([Some(Series::new(
            "".into(),
            vec![100.0_f64, 100.0, 100.0],
        ))]);

        let kwargs = make_single_state_kwargs(
            0,
            vec![StepSpec::AddIf {
                target_index: 0,
                condition_index: 1,
                amount_index: 2,
                label: Some("conditional_add".to_string()),
            }],
        );

        let result = rollforward(
            &[initial, condition.into_series(), amount.into_series()],
            &kwargs,
        )
        .unwrap();
        let s = result.struct_().unwrap();
        let av = s.field_by_name("result").unwrap();
        let row0 = av.list().unwrap().get_as_series(0).unwrap();
        let vals = row0.f64().unwrap();

        assert!((vals.get(0).unwrap() - 1100.0).abs() < 1e-10, "t0 expected 1100.0, got {:?}", vals.get(0));
        assert!((vals.get(1).unwrap() - 1100.0).abs() < 1e-10, "t1 expected 1100.0, got {:?}", vals.get(1));
        assert!((vals.get(2).unwrap() - 1200.0).abs() < 1e-10, "t2 expected 1200.0, got {:?}", vals.get(2));
    }

    #[test]
    fn test_multiple_policies() {
        // Policy 0: initial=1000, premium=[100, 200]
        //   t0: 1000 + 100 = 1100
        //   t1: 1100 + 200 = 1300
        // Policy 1: initial=500, premium=[50, 50]
        //   t0: 500 + 50 = 550
        //   t1: 550 + 50 = 600
        let initial = Series::new("initial".into(), vec![1000.0_f64, 500.0]);
        let premium = ListChunked::from_iter([
            Some(Series::new("".into(), vec![100.0, 200.0])),
            Some(Series::new("".into(), vec![50.0, 50.0])),
        ]);

        let kwargs = make_single_state_kwargs(
            0,
            vec![StepSpec::Add {
                target_index: 0,
                input_index: 1,
                label: Some("premium".to_string()),
                expected_input_index: None,
            }],
        );

        let result = rollforward(&[initial, premium.into_series()], &kwargs).unwrap();
        let s = result.struct_().unwrap();
        let av = s.field_by_name("result").unwrap();
        let list_ca = av.list().unwrap();

        // Policy 0
        let row0 = list_ca.get_as_series(0).unwrap();
        let vals0 = row0.f64().unwrap();
        assert_eq!(vals0.get(0), Some(1100.0));
        assert_eq!(vals0.get(1), Some(1300.0));

        // Policy 1
        let row1 = list_ca.get_as_series(1).unwrap();
        let vals1 = row1.f64().unwrap();
        assert_eq!(vals1.get(0), Some(550.0));
        assert_eq!(vals1.get(1), Some(600.0));
    }

    #[test]
    fn test_increment_tracking_single_state() {
        // initial=1000, premium=[100], admin_rate=[0.01], interest=[0.05]
        // After Add:    1000 + 100         = 1100.0.   Increment: 100.0
        // After Charge: 1100 * (1 - 0.01) = 1089.0.   Increment: -11.0
        // After Grow:   1089 * (1 + 0.05) = 1143.45.  Increment: 54.45
        let initial = Series::new("initial".into(), vec![1000.0_f64]);
        let premium = ListChunked::from_iter([Some(Series::new("".into(), vec![100.0_f64]))]);
        let admin = ListChunked::from_iter([Some(Series::new("".into(), vec![0.01_f64]))]);
        let interest = ListChunked::from_iter([Some(Series::new("".into(), vec![0.05_f64]))]);

        let kwargs = RollforwardKwargs {
            states: vec![StateSpec {
                name: "__default__".to_string(),
                initial_col_index: 0,
            }],
            steps: vec![
                StepSpec::Add {
                    target_index: 0,
                    input_index: 1,
                    label: Some("Premium".to_string()),
                    expected_input_index: None,
                },
                StepSpec::Charge {
                    target_index: 0,
                    input_index: 2,
                    label: Some("Admin".to_string()),
                    expected_input_index: None,
                },
                StepSpec::Grow {
                    target_index: 0,
                    input_index: 3,
                    label: Some("Interest".to_string()),
                    expected_input_index: None,
                },
            ],
            track_increments: true,
            assertion_mode: None,
            num_captures: 0,
            lapse_condition: None,
        };

        let result = rollforward(
            &[
                initial,
                premium.into_series(),
                admin.into_series(),
                interest.into_series(),
            ],
            &kwargs,
        )
        .unwrap();
        let s = result.struct_().unwrap();

        // Check result field
        let av = s.field_by_name("result").unwrap();
        let row0 = av.list().unwrap().get_as_series(0).unwrap();
        assert!(
            (row0.f64().unwrap().get(0).unwrap() - 1143.45).abs() < 1e-10,
            "result expected 1143.45, got {:?}",
            row0.f64().unwrap().get(0)
        );

        // Check Premium increment: +100
        let prem_inc = s.field_by_name("Premium").unwrap();
        let prem_row0 = prem_inc.list().unwrap().get_as_series(0).unwrap();
        assert!(
            (prem_row0.f64().unwrap().get(0).unwrap() - 100.0).abs() < 1e-10,
            "Premium increment expected 100.0, got {:?}",
            prem_row0.f64().unwrap().get(0)
        );

        // Check Admin increment: 1089 - 1100 = -11
        let admin_inc = s.field_by_name("Admin").unwrap();
        let admin_row0 = admin_inc.list().unwrap().get_as_series(0).unwrap();
        assert!(
            (admin_row0.f64().unwrap().get(0).unwrap() - (-11.0)).abs() < 1e-10,
            "Admin increment expected -11.0, got {:?}",
            admin_row0.f64().unwrap().get(0)
        );

        // Check Interest increment: 1143.45 - 1089 = 54.45
        let int_inc = s.field_by_name("Interest").unwrap();
        let int_row0 = int_inc.list().unwrap().get_as_series(0).unwrap();
        assert!(
            (int_row0.f64().unwrap().get(0).unwrap() - 54.45).abs() < 1e-10,
            "Interest increment expected 54.45, got {:?}",
            int_row0.f64().unwrap().get(0)
        );
    }

    #[test]
    fn test_no_tracking_only_result_field() {
        // Same as basic add test but verify struct only has "result" (no increment fields)
        let initial = Series::new("initial".into(), vec![1000.0_f64]);
        let premium = ListChunked::from_iter([Some(Series::new("".into(), vec![100.0_f64]))]);

        let kwargs = RollforwardKwargs {
            states: vec![StateSpec {
                name: "av".to_string(),
                initial_col_index: 0,
            }],
            steps: vec![StepSpec::Add {
                target_index: 0,
                input_index: 1,
                label: Some("Premium".to_string()),
                expected_input_index: None,
            }],
            track_increments: false,
            assertion_mode: None,
            num_captures: 0,
            lapse_condition: None,
        };

        let result = rollforward(&[initial, premium.into_series()], &kwargs).unwrap();
        let s = result.struct_().unwrap();

        // Should have "result" field
        assert!(
            s.field_by_name("result").is_ok(),
            "expected 'result' field to exist"
        );
        // Should NOT have increment field even though the step has a label
        assert!(
            s.field_by_name("Premium").is_err(),
            "expected no 'Premium' increment field when track_increments=false"
        );
    }

    // ==================== Multi-state tests ====================

    #[test]
    fn test_multi_state_va_gmdb() {
        // Two states: av (idx 0), guarantee (idx 1)
        // initial av=1000, guarantee=1000
        // Steps: Add premium to av, Grow av by fund_return, RatchetTo guarantee from av
        // t0: av = (1000+100)*1.10 = 1210, guarantee = max(1000, 1210) = 1210
        let initial_av = Series::new("av_init".into(), vec![1000.0_f64]);
        let initial_g = Series::new("g_init".into(), vec![1000.0_f64]);
        let premium =
            ListChunked::from_iter([Some(Series::new("".into(), vec![100.0_f64]))]);
        let fund_ret =
            ListChunked::from_iter([Some(Series::new("".into(), vec![0.10_f64]))]);

        // inputs: [0]=av_init, [1]=g_init, [2]=premium_list, [3]=fund_ret_list
        let kwargs = RollforwardKwargs {
            states: vec![
                StateSpec {
                    name: "av".to_string(),
                    initial_col_index: 0,
                },
                StateSpec {
                    name: "guarantee".to_string(),
                    initial_col_index: 1,
                },
            ],
            steps: vec![
                StepSpec::Add {
                    target_index: 0,
                    input_index: 2,
                    label: Some("Premium".to_string()),
                    expected_input_index: None,
                },
                StepSpec::Grow {
                    target_index: 0,
                    input_index: 3,
                    label: Some("FundReturn".to_string()),
                    expected_input_index: None,
                },
                StepSpec::RatchetTo {
                    target_index: 1,
                    other_state_index: 0,
                    label: Some("Ratchet".to_string()),
                },
            ],
            track_increments: false,
            assertion_mode: None,
            num_captures: 0,
            lapse_condition: None,
        };

        let result = rollforward(
            &[
                initial_av,
                initial_g,
                premium.into_series(),
                fund_ret.into_series(),
            ],
            &kwargs,
        )
        .unwrap();
        let s = result.struct_().unwrap();

        // Verify Struct has "av" and "guarantee" fields
        let av_field = s.field_by_name("av").unwrap();
        let av_row0 = av_field.list().unwrap().get_as_series(0).unwrap();
        let av_vals = av_row0.f64().unwrap();
        // av = (1000 + 100) * 1.10 = 1210.0
        assert!(
            (av_vals.get(0).unwrap() - 1210.0).abs() < 1e-10,
            "av t0 expected 1210.0, got {:?}",
            av_vals.get(0)
        );

        let g_field = s.field_by_name("guarantee").unwrap();
        let g_row0 = g_field.list().unwrap().get_as_series(0).unwrap();
        let g_vals = g_row0.f64().unwrap();
        // guarantee = max(1000, 1210) = 1210.0
        assert!(
            (g_vals.get(0).unwrap() - 1210.0).abs() < 1e-10,
            "guarantee t0 expected 1210.0, got {:?}",
            g_vals.get(0)
        );
    }

    #[test]
    fn test_lapse_when_all_non_positive() {
        // Two states: av (idx 0) starts at 50, guarantee (idx 1) starts at 50
        // Subtract 100 from each at t0 → av=-50, guarantee=-50
        // Both non-positive → cross-state lapse fires
        // t1: both 0
        let initial_av = Series::new("av_init".into(), vec![50.0_f64]);
        let initial_g = Series::new("g_init".into(), vec![50.0_f64]);
        let subtract_av =
            ListChunked::from_iter([Some(Series::new("".into(), vec![100.0_f64, 100.0]))]);
        let subtract_g =
            ListChunked::from_iter([Some(Series::new("".into(), vec![100.0_f64, 100.0]))]);

        let kwargs = RollforwardKwargs {
            states: vec![
                StateSpec {
                    name: "av".to_string(),
                    initial_col_index: 0,
                },
                StateSpec {
                    name: "guarantee".to_string(),
                    initial_col_index: 1,
                },
            ],
            steps: vec![
                StepSpec::Subtract {
                    target_index: 0,
                    input_index: 2,
                    label: None,
                    expected_input_index: None,
                },
                StepSpec::Subtract {
                    target_index: 1,
                    input_index: 3,
                    label: None,
                    expected_input_index: None,
                },
            ],
            track_increments: false,
            assertion_mode: None,
            num_captures: 0,
            lapse_condition: Some(LapseCondition::AllNonPositive {
                state_indices: vec![0, 1],
            }),
        };

        let result = rollforward(
            &[
                initial_av,
                initial_g,
                subtract_av.into_series(),
                subtract_g.into_series(),
            ],
            &kwargs,
        )
        .unwrap();
        let s = result.struct_().unwrap();

        let av_field = s.field_by_name("av").unwrap();
        let av_row0 = av_field.list().unwrap().get_as_series(0).unwrap();
        let av_vals = av_row0.f64().unwrap();
        // t0: 50 - 100 = -50 (recorded), then lapse fires
        assert!(
            (av_vals.get(0).unwrap() - (-50.0)).abs() < 1e-10,
            "av t0 expected -50.0, got {:?}",
            av_vals.get(0)
        );
        // t1: zeroed by lapse
        assert_eq!(av_vals.get(1), Some(0.0), "av t1 expected 0.0 after lapse");

        let g_field = s.field_by_name("guarantee").unwrap();
        let g_row0 = g_field.list().unwrap().get_as_series(0).unwrap();
        let g_vals = g_row0.f64().unwrap();
        assert!(
            (g_vals.get(0).unwrap() - (-50.0)).abs() < 1e-10,
            "guarantee t0 expected -50.0, got {:?}",
            g_vals.get(0)
        );
        assert_eq!(
            g_vals.get(1),
            Some(0.0),
            "guarantee t1 expected 0.0 after lapse"
        );
    }

    #[test]
    fn test_pro_rata_with_capture() {
        // Two states: av (idx 0) = 1000, benefit_base (idx 1) = 500
        // Steps:
        //   1. Capture av as capture[0]
        //   2. Subtract 200 from av → av = 800
        //   3. ProRata on benefit_base using capture[0]: 500 * (1 - 200/1000) = 400
        let initial_av = Series::new("av_init".into(), vec![1000.0_f64]);
        let initial_bb = Series::new("bb_init".into(), vec![500.0_f64]);
        let withdraw =
            ListChunked::from_iter([Some(Series::new("".into(), vec![200.0_f64]))]);

        // inputs: [0]=av_init, [1]=bb_init, [2]=withdraw_list
        let kwargs = RollforwardKwargs {
            states: vec![
                StateSpec {
                    name: "av".to_string(),
                    initial_col_index: 0,
                },
                StateSpec {
                    name: "benefit_base".to_string(),
                    initial_col_index: 1,
                },
            ],
            steps: vec![
                StepSpec::Capture {
                    target_index: 0,
                    capture_index: 0,
                },
                StepSpec::Subtract {
                    target_index: 0,
                    input_index: 2,
                    label: Some("Withdraw".to_string()),
                    expected_input_index: None,
                },
                StepSpec::ProRataWith {
                    target_index: 1,
                    capture_index: 0,
                    amount_index: 2,
                    label: Some("ProRata".to_string()),
                },
            ],
            track_increments: false,
            assertion_mode: None,
            num_captures: 1,
            lapse_condition: None,
        };

        let result = rollforward(
            &[initial_av, initial_bb, withdraw.into_series()],
            &kwargs,
        )
        .unwrap();
        let s = result.struct_().unwrap();

        // av = 1000 - 200 = 800
        let av_field = s.field_by_name("av").unwrap();
        let av_row0 = av_field.list().unwrap().get_as_series(0).unwrap();
        let av_vals = av_row0.f64().unwrap();
        assert!(
            (av_vals.get(0).unwrap() - 800.0).abs() < 1e-10,
            "av t0 expected 800.0, got {:?}",
            av_vals.get(0)
        );

        // benefit_base = 500 * (1 - 200/1000) = 500 * 0.8 = 400
        let bb_field = s.field_by_name("benefit_base").unwrap();
        let bb_row0 = bb_field.list().unwrap().get_as_series(0).unwrap();
        let bb_vals = bb_row0.f64().unwrap();
        assert!(
            (bb_vals.get(0).unwrap() - 400.0).abs() < 1e-10,
            "benefit_base t0 expected 400.0, got {:?}",
            bb_vals.get(0)
        );
    }

    #[test]
    fn test_multi_state_with_increment_tracking() {
        // Two states: av (idx 0), guarantee (idx 1)
        // Steps: Add premium to av (labeled), RatchetTo guarantee (labeled)
        // track_increments = true
        // Verify Struct has state fields AND increment fields
        let initial_av = Series::new("av_init".into(), vec![1000.0_f64]);
        let initial_g = Series::new("g_init".into(), vec![900.0_f64]);
        let premium =
            ListChunked::from_iter([Some(Series::new("".into(), vec![100.0_f64, 50.0]))]);

        let kwargs = RollforwardKwargs {
            states: vec![
                StateSpec {
                    name: "av".to_string(),
                    initial_col_index: 0,
                },
                StateSpec {
                    name: "guarantee".to_string(),
                    initial_col_index: 1,
                },
            ],
            steps: vec![
                StepSpec::Add {
                    target_index: 0,
                    input_index: 2,
                    label: Some("Premium".to_string()),
                    expected_input_index: None,
                },
                StepSpec::RatchetTo {
                    target_index: 1,
                    other_state_index: 0,
                    label: Some("Ratchet".to_string()),
                },
            ],
            track_increments: true,
            assertion_mode: None,
            num_captures: 0,
            lapse_condition: None,
        };

        let result = rollforward(
            &[initial_av, initial_g, premium.into_series()],
            &kwargs,
        )
        .unwrap();
        let s = result.struct_().unwrap();

        // State fields
        let av_field = s.field_by_name("av").unwrap();
        let av_row0 = av_field.list().unwrap().get_as_series(0).unwrap();
        let av_vals = av_row0.f64().unwrap();
        // t0: 1000 + 100 = 1100
        assert!(
            (av_vals.get(0).unwrap() - 1100.0).abs() < 1e-10,
            "av t0 expected 1100.0, got {:?}",
            av_vals.get(0)
        );
        // t1: 1100 + 50 = 1150
        assert!(
            (av_vals.get(1).unwrap() - 1150.0).abs() < 1e-10,
            "av t1 expected 1150.0, got {:?}",
            av_vals.get(1)
        );

        let g_field = s.field_by_name("guarantee").unwrap();
        let g_row0 = g_field.list().unwrap().get_as_series(0).unwrap();
        let g_vals = g_row0.f64().unwrap();
        // t0: max(900, 1100) = 1100
        assert!(
            (g_vals.get(0).unwrap() - 1100.0).abs() < 1e-10,
            "guarantee t0 expected 1100.0, got {:?}",
            g_vals.get(0)
        );
        // t1: max(1100, 1150) = 1150
        assert!(
            (g_vals.get(1).unwrap() - 1150.0).abs() < 1e-10,
            "guarantee t1 expected 1150.0, got {:?}",
            g_vals.get(1)
        );

        // Increment fields
        let prem_inc = s.field_by_name("Premium").unwrap();
        let prem_row0 = prem_inc.list().unwrap().get_as_series(0).unwrap();
        let prem_vals = prem_row0.f64().unwrap();
        // t0: 1100 - 1000 = 100
        assert!(
            (prem_vals.get(0).unwrap() - 100.0).abs() < 1e-10,
            "Premium increment t0 expected 100.0, got {:?}",
            prem_vals.get(0)
        );
        // t1: 1150 - 1100 = 50
        assert!(
            (prem_vals.get(1).unwrap() - 50.0).abs() < 1e-10,
            "Premium increment t1 expected 50.0, got {:?}",
            prem_vals.get(1)
        );

        let ratchet_inc = s.field_by_name("Ratchet").unwrap();
        let ratchet_row0 = ratchet_inc.list().unwrap().get_as_series(0).unwrap();
        let ratchet_vals = ratchet_row0.f64().unwrap();
        // t0: guarantee went from 900 to 1100, increment = 200
        assert!(
            (ratchet_vals.get(0).unwrap() - 200.0).abs() < 1e-10,
            "Ratchet increment t0 expected 200.0, got {:?}",
            ratchet_vals.get(0)
        );
        // t1: guarantee went from 1100 to 1150, increment = 50
        assert!(
            (ratchet_vals.get(1).unwrap() - 50.0).abs() < 1e-10,
            "Ratchet increment t1 expected 50.0, got {:?}",
            ratchet_vals.get(1)
        );
    }
}
