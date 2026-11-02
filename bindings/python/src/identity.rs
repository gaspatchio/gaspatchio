// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

// ABOUTME: Python's door to the core's content grammar encoder: a frame's bytes, or their digest.
// ABOUTME: Encodes with the GIL released; gaspatchio._identity names every type and every column first.

use gaspatchio_core_lib::identity::{
    content_bytes_of_named, content_sha256_of_named, lowercase_hex, ContentGrammarError,
};
use polars::prelude::DataFrame;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use pyo3_polars::PyDataFrame;

/// Return the content grammar's bytes for `frame` (specification section
/// 12.3), each column written under the name `names` gives it.
///
/// The names cross as Python strings beside the frame, never as the frame's
/// own: the Arrow C interface the frame is imported through carries a column
/// name as a NUL-terminated string, and a Polars name may hold a NUL. The
/// encoding runs with the GIL released, so another Python thread keeps
/// working while a large frame is read.
#[pyfunction]
pub fn content_bytes(
    py: Python<'_>,
    frame: PyDataFrame,
    names: Vec<String>,
) -> PyResult<Bound<'_, PyBytes>> {
    let frame: DataFrame = frame.into();
    let bytes = py
        .detach(move || content_bytes_of_named(&frame, &names))
        .map_err(refused)?;
    Ok(PyBytes::new(py, &bytes))
}

/// Return SHA-256 over the content grammar's bytes for `frame`, each column
/// under the name `names` gives it, as sixty-four lowercase hex digits.
///
/// The bytes stream into the hasher as they are encoded, with the GIL
/// released, so digesting a whole book builds no buffer the size of the book
/// and holds up no other Python thread.
#[pyfunction]
pub fn content_sha256(py: Python<'_>, frame: PyDataFrame, names: Vec<String>) -> PyResult<String> {
    let frame: DataFrame = frame.into();
    let digest = py
        .detach(move || content_sha256_of_named(&frame, &names))
        .map_err(refused)?;
    Ok(lowercase_hex(&digest))
}

/// Raise the grammar's own refusal as a `ValueError`, the base of the
/// `UnmappedDtypeError` the Python layer raises for the same cases first.
fn refused(error: ContentGrammarError) -> PyErr {
    PyValueError::new_err(error.to_string())
}
