// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

// ABOUTME: The content grammar of the graph artifact specification (section 12.3) over a Polars frame.
// ABOUTME: Byte-identical to gaspatchio._identity's Python reference; the digest streams through SHA-256.

//! The content grammar: the bytes a frame of values is identified by.
//!
//! An assumption table's content stamp, a join's right-hand fingerprint, an
//! injected column's stamp and a result's `inputs_digest` are all SHA-256 over
//! these bytes. The grammar is the specification's own
//! (`spec/graph-artifact/v0-preview.md`, section 12.3) and deliberately not any
//! engine's serialisation, so that a reviewer holding the values and nothing
//! else -- no Polars, no gaspatchio -- can re-derive the digest and check that
//! the book a result names is the book they hold.
//!
//! **Why it lives here.** Since a result's manifest digests every cell of the
//! book it ran over, the encoder reads every value of every run. In Python
//! that was seconds at a million policies and most of a ten-million-policy fold
//! on a GPU, so the encoder moved into the core. The Python encoder in
//! `gaspatchio._identity` stays as the reference this one is held byte-identical
//! to by test: the bytes are the grammar's, and only where they are computed
//! moved.
//!
//! **The rules, each one a reason a stamp does or does not move.**
//!
//! - Storage width is not content: every integer width is a whole number and
//!   every float width a decimal, so an `Int32` and an `Int64` column holding
//!   the same numbers write the same bytes.
//! - A decimal is its eight IEEE-754 bytes, most significant first, with a
//!   negative zero written as zero and every NaN as the one quiet payload: two
//!   runs that both produced a NaN, or a zero of either sign, have not drifted.
//! - A date is the whole number of days since 1970-01-01. A timestamp is the
//!   whole number of microseconds since then and the nanoseconds past that
//!   microsecond, whatever unit the column was kept in, so one instant has one
//!   encoding and two instants a nanosecond apart have two. A timestamp column
//!   carries its zone in its header -- empty for a naive or a UTC column, which
//!   read alike -- because the calendar a model reads off an instant is the
//!   zone's, and two books one zone apart are two books.
//! - Text is UTF-8 behind its byte length; a flag is one byte; a whole number is
//!   a zigzag varint, so a small negative number costs one byte rather than ten.
//! - Every value carries a marker saying whether it is there. A rate nobody
//!   supplied and a rate of nought are different assumptions, so a missing
//!   value is its marker and one placeholder byte, at every level of nesting.
//! - A list (and a fixed-width array, which is a list whose length is storage)
//!   writes each row's marker and member count, then its members under the
//!   element's own form, each with its own marker.

use polars::prelude::{DataFrame, DataType, Series, TimeUnit, TimeZone};
use polars_arrow::array::{
    Array, BooleanArray, FixedSizeListArray, ListArray, PrimitiveArray, Utf8ViewArray,
};
use polars_arrow::types::NativeType;
use sha2::{Digest, Sha256};
use std::ops::Range;

// One tag byte per type, from the block the calculation graph's scalar tags
// occupy, so a reader holding both grammars meets one number per type.
const TAG_FLAG: u8 = 0x11;
const TAG_WHOLE_NUMBER: u8 = 0x12;
const TAG_DECIMAL: u8 = 0x13;
const TAG_TEXT: u8 = 0x14;
const TAG_SEQUENCE: u8 = 0x15;
const TAG_DATE: u8 = 0x16;
const TAG_DATETIME: u8 = 0x17;

// The marker in front of every value, and what a missing one is written as.
const PRESENT: u8 = 0x02;
const MISSING: [u8; 2] = [0x01, 0x00];

// Every NaN is written as this one quiet payload.
const QUIET_NAN: u64 = 0x7FF8_0000_0000_0000;

// How deep `list[...]` may nest: the published schema's own pattern spells out
// three levels and stops, so a fourth has no name to be written under.
const MAX_LIST_DEPTH: usize = 3;

// A varint is seven bits a byte, low group first, the high bit set on every
// byte but the last; a sixty-four-bit value runs to ten groups.
const GROUP_BITS: u32 = 7;
const GROUP_MASK: u64 = 0x7F;
const CONTINUES: u8 = 0x80;
const VARINT_GROUPS: usize = 10;

// How much encoded content is staged before it is handed to SHA-256 in one
// call. Large enough that the hasher sees long runs of whole blocks, small
// enough that a whole book's bytes never exist at once.
const STAGE_BYTES: usize = 1 << 18;

// Microseconds are the unit a timestamp travels in, and the nanoseconds past
// the microsecond travel beside it.
const MICROS_PER_MILLI: i64 = 1_000;
const NANOS_PER_MICRO: i64 = 1_000;

// The zone a naive timestamp is read in, and so the one a UTC column is
// written as: the two name one instant per value, and digest alike.
const UTC: &str = "UTC";

/// Why the content grammar would not encode a frame.
///
/// The Python layer refuses a type the vocabulary cannot name before it ever
/// reaches here, with the column and the cast in its own words. These are the
/// grammar's own refusals, kept so that a frame arriving by any other route
/// stops the hash rather than being written as something it is not.
#[derive(Debug, thiserror::Error)]
pub enum ContentGrammarError {
    /// A column carries a type the grammar has no tag for.
    #[error(
        "Column '{column}' has type {dtype}, which the content grammar has no tag for. \
         It can hash bool, i64, f64, str, date and datetime, and list[...] of any of \
         those nested at most three deep."
    )]
    NoTag {
        /// The column whose type stopped the hash.
        column: String,
        /// The type, as the engine names it.
        dtype: String,
    },

    /// A column's storage is not the layout its type says it has.
    #[error(
        "Column '{column}' is typed {dtype} but is stored as {storage}, which the \
         content grammar cannot read its values out of."
    )]
    Storage {
        /// The column whose storage could not be read.
        column: String,
        /// The column's type.
        dtype: String,
        /// What the storage turned out to be.
        storage: String,
    },

    /// The names handed in are not one per column.
    #[error(
        "The content grammar was handed {names} column names for a frame of {columns} \
         columns; it writes one name per column, in the frame's order."
    )]
    Names {
        /// How many names were handed in.
        names: usize,
        /// How many columns the frame holds.
        columns: usize,
    },

    /// A timestamp's count in microseconds leaves the 64-bit whole number the
    /// grammar writes an instant as.
    #[error(
        "Column '{column}' holds the timestamp {count} ms past 1970-01-01, whose count \
         in microseconds leaves the 64-bit whole number section 12.3 writes an instant \
         as (it holds about 292,000 years either side of 1970). Two such instants \
         would otherwise wrap onto one digest. No calendar a model reads reaches \
         this far: check the column was read in the unit it was written in, or drop \
         the value before it is hashed."
    )]
    InstantPastI64 {
        /// The column whose value stopped the hash.
        column: String,
        /// The value, in the milliseconds the column keeps.
        count: i64,
    },

    /// A run of rows fell outside the storage it was to be read from.
    #[error(
        "The content grammar was asked for rows {start}..{end} of {storage} storage \
         holding {len} values; storage Polars built never asks for that."
    )]
    OutOfBounds {
        /// The storage, as the engine names its layout.
        storage: String,
        /// How many values the storage holds.
        len: usize,
        /// The first row asked for.
        start: usize,
        /// One past the last row asked for.
        end: usize,
    },
}

/// Return the content grammar's bytes for `frame`: its columns, in the order
/// the frame holds them, and every value in row order.
///
/// The whole encoding in memory, for callers that need the bytes themselves --
/// a test holding them against the specification's worked example, or against
/// the Python reference. A caller that wants only the digest should use
/// [`content_sha256_of`], which never builds this buffer.
///
/// # Arguments
///
/// * `frame` - The columns to encode, with rows in the order the caller put
///   them in. Row order is the caller's: a table sorts by its keys first, an
///   injected column does not sort at all.
///
/// # Returns
///
/// The encoded bytes: a count of columns, then for each column its name, its
/// type tag, a count of rows and every value's bytes.
///
/// # Examples
///
/// ```
/// use gaspatchio_core_lib::identity::content_bytes_of;
/// use polars::prelude::*;
///
/// let ages = df!("age" => [45i64])?;
/// assert_eq!(content_bytes_of(&ages)?, vec![0x01, 0x03, b'a', b'g', b'e', 0x12, 0x01, 0x02, 0x5a]);
/// # Ok::<(), Box<dyn std::error::Error>>(())
/// ```
///
/// # Errors
///
/// Returns [`ContentGrammarError::NoTag`] if a column's type has no tag, and
/// [`ContentGrammarError::Storage`] or [`ContentGrammarError::OutOfBounds`] if
/// a column's storage is not what its type says it is.
pub fn content_bytes_of(frame: &DataFrame) -> Result<Vec<u8>, ContentGrammarError> {
    content_bytes_of_named(frame, &own_names(frame))
}

/// Return the content grammar's bytes for `frame`, each column written under
/// the name `names` gives it, position for position.
///
/// The frame's own names are not read. This is the door a frame from Python
/// comes through: the Arrow C interface it crosses carries every column name
/// as a NUL-terminated string, and a Polars name may hold a NUL -- a name the
/// grammar hashes like any other, and one the crossing cannot carry. So the
/// names come across as a list beside the frame, and the frame's own are
/// placeholders.
///
/// # Arguments
///
/// * `frame` - The columns to encode, rows in the caller's order.
/// * `names` - One name per column, in the frame's column order.
///
/// # Returns
///
/// The encoded bytes, as [`content_bytes_of`] would write them had the frame
/// held these names.
///
/// # Examples
///
/// ```
/// use gaspatchio_core_lib::identity::{content_bytes_of, content_bytes_of_named};
/// use polars::prelude::*;
///
/// let under_a_placeholder = df!("0" => [45i64])?;
/// let under_its_own_name = df!("rate\0note" => [45i64])?;
/// assert_eq!(
///     content_bytes_of_named(&under_a_placeholder, &["rate\0note"])?,
///     content_bytes_of(&under_its_own_name)?
/// );
/// # Ok::<(), Box<dyn std::error::Error>>(())
/// ```
///
/// # Errors
///
/// [`ContentGrammarError::Names`] if there is not one name per column, and
/// otherwise the same refusals as [`content_bytes_of`], naming the column by
/// the name given.
pub fn content_bytes_of_named<N: AsRef<str>>(
    frame: &DataFrame,
    names: &[N],
) -> Result<Vec<u8>, ContentGrammarError> {
    let mut bytes = Vec::new();
    write_frame(frame, names, &mut bytes)?;
    Ok(bytes)
}

/// Return SHA-256 over the content grammar's bytes for `frame`, as raw bytes.
///
/// The bytes are streamed into the hasher as they are encoded, a few hundred
/// kilobytes at a time, so digesting a ten-million-policy book costs one pass
/// over its values and no buffer the size of the book.
///
/// # Arguments
///
/// * `frame` - The columns to digest, rows in the caller's order.
///
/// # Returns
///
/// The thirty-two bytes of the digest. [`lowercase_hex`] spells them the way a
/// stamp carries them, behind `sha256:`.
///
/// # Examples
///
/// ```
/// use gaspatchio_core_lib::identity::{content_bytes_of, content_sha256_of};
/// use polars::prelude::*;
/// use sha2::{Digest, Sha256};
///
/// let basis = df!("age" => [45i64, 46, 47], "rate" => [0.001, 0.0012, 0.0015])?;
/// let whole: [u8; 32] = Sha256::digest(content_bytes_of(&basis)?).into();
/// assert_eq!(content_sha256_of(&basis)?, whole);
/// # Ok::<(), Box<dyn std::error::Error>>(())
/// ```
///
/// # Errors
///
/// The same refusals as [`content_bytes_of`].
pub fn content_sha256_of(frame: &DataFrame) -> Result<[u8; 32], ContentGrammarError> {
    content_sha256_of_named(frame, &own_names(frame))
}

/// Return SHA-256 over [`content_bytes_of_named`]'s bytes, streamed as they
/// are encoded.
///
/// The door the digest of a frame from Python comes through, for the reason
/// [`content_bytes_of_named`] gives: the names cross beside the frame.
///
/// # Arguments
///
/// * `frame` - The columns to digest, rows in the caller's order.
/// * `names` - One name per column, in the frame's column order.
///
/// # Returns
///
/// The thirty-two bytes of the digest.
///
/// # Examples
///
/// ```
/// use gaspatchio_core_lib::identity::{content_sha256_of, content_sha256_of_named};
/// use polars::prelude::*;
///
/// let basis = df!("0" => [0.001, 0.0012])?;
/// let named = df!("rate" => [0.001, 0.0012])?;
/// assert_eq!(content_sha256_of_named(&basis, &["rate"])?, content_sha256_of(&named)?);
/// # Ok::<(), Box<dyn std::error::Error>>(())
/// ```
///
/// # Errors
///
/// The same refusals as [`content_bytes_of_named`].
pub fn content_sha256_of_named<N: AsRef<str>>(
    frame: &DataFrame,
    names: &[N],
) -> Result<[u8; 32], ContentGrammarError> {
    let mut digest = Digesting::new(STAGE_BYTES);
    write_frame(frame, names, &mut digest)?;
    Ok(digest.finish())
}

/// Return the frame's own column names, in its order.
fn own_names(frame: &DataFrame) -> Vec<&str> {
    frame
        .columns()
        .iter()
        .map(|column| column.name().as_str())
        .collect()
}

/// Return `bytes` as lowercase hexadecimal, two digits a byte.
///
/// The form a digest is stamped in after `sha256:`.
///
/// # Examples
///
/// ```
/// use gaspatchio_core_lib::identity::lowercase_hex;
///
/// assert_eq!(lowercase_hex(&[0x00, 0x5a, 0xff]), "005aff");
/// ```
pub fn lowercase_hex(bytes: &[u8]) -> String {
    const DIGITS: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        out.push(char::from(DIGITS[usize::from(byte >> 4)]));
        out.push(char::from(DIGITS[usize::from(byte & 0x0F)]));
    }
    out
}

/// Where encoded bytes go: a buffer that keeps them, or a hasher that does not.
///
/// Every value is written straight into [`Sink::staged`], a marker and a few
/// bytes at a time, and [`Sink::settle`] is called after it. A buffer keeping
/// the bytes has nothing to settle; a hasher takes the stage once it is full.
trait Sink {
    /// The buffer the next value's bytes are written into.
    fn staged(&mut self) -> &mut Vec<u8>;

    /// Hand the staged bytes on, if there are enough of them to be worth it.
    fn settle(&mut self);
}

impl Sink for Vec<u8> {
    #[inline]
    fn staged(&mut self) -> &mut Vec<u8> {
        self
    }

    #[inline]
    fn settle(&mut self) {}
}

/// SHA-256 fed from a small staging buffer.
///
/// Encoding writes a value a few bytes at a time; SHA-256 is fastest fed long
/// runs of whole blocks. The stage turns the one into the other without ever
/// holding more than `stage` bytes plus the one value that crossed the line.
struct Digesting {
    hasher: Sha256,
    staged: Vec<u8>,
    stage: usize,
}

impl Digesting {
    fn new(stage: usize) -> Self {
        Self {
            hasher: Sha256::new(),
            staged: Vec::with_capacity(stage + VARINT_GROUPS + 1),
            stage,
        }
    }

    fn finish(mut self) -> [u8; 32] {
        self.hasher.update(&self.staged);
        self.hasher.finalize().into()
    }
}

impl Sink for Digesting {
    #[inline]
    fn staged(&mut self) -> &mut Vec<u8> {
        &mut self.staged
    }

    #[inline]
    fn settle(&mut self) {
        if self.staged.len() >= self.stage {
            self.hasher.update(&self.staged);
            self.staged.clear();
        }
    }
}

/// Write the whole frame: a count of columns, then each column in turn,
/// under the name `names` gives it.
fn write_frame<S: Sink, N: AsRef<str>>(
    frame: &DataFrame,
    names: &[N],
    sink: &mut S,
) -> Result<(), ContentGrammarError> {
    if names.len() != frame.width() {
        return Err(ContentGrammarError::Names {
            names: names.len(),
            columns: frame.width(),
        });
    }
    push_varint(sink.staged(), as_count(frame.width()));
    for (column, name) in frame.columns().iter().zip(names) {
        write_column(column.as_materialized_series(), name.as_ref(), sink)?;
    }
    Ok(())
}

/// Write one column: its name, its tag, its row count and its values.
///
/// The form is read off the type before a byte of the column is written, so a
/// column with no tag stops the hash at its name rather than part-way through
/// its values.
fn write_column<S: Sink>(
    series: &Series,
    name: &str,
    sink: &mut S,
) -> Result<(), ContentGrammarError> {
    let form = Form::of(series.dtype(), name)?;

    let header = sink.staged();
    push_text(header, name.as_bytes());
    form.tag(header);
    push_varint(header, as_count(series.len()));
    sink.settle();

    // A column arrives in however many chunks the engine left it in, each
    // possibly a slice of a larger buffer; the rows are the rows in order.
    for chunk in series.chunks() {
        let values = Values::of(&form, chunk.as_ref(), name, series)?;
        values.write(0..chunk.len(), sink)?;
    }
    Ok(())
}

/// How a column's values are written, read off its type once.
#[derive(Debug, Clone, PartialEq)]
enum Form {
    /// A true/false flag: the marker, then one byte.
    Flag,
    /// A whole number held at one of the widths that fits `i64`.
    Whole(Width),
    /// A date, as a whole number of days since 1970-01-01.
    Days,
    /// A timestamp, as a whole number of microseconds since 1970-01-01 and the
    /// nanoseconds past it, from whatever unit it was kept in; the zone, empty
    /// for a naive or a UTC column, is written in the header.
    Instant(TimeUnit, String),
    /// A decimal held at either float width.
    Decimal(Precision),
    /// Text, as UTF-8 behind its byte length.
    Text,
    /// A list or a fixed-width array of values of the inner form.
    Sequence(Box<Form>),
}

/// The integer widths the vocabulary calls `i64`: every one whose values all fit.
#[derive(Debug, Clone, Copy, PartialEq)]
enum Width {
    I8,
    I16,
    I32,
    I64,
    U8,
    U16,
    U32,
}

/// The float widths the vocabulary calls `f64`.
#[derive(Debug, Clone, Copy, PartialEq)]
enum Precision {
    Single,
    Double,
}

impl Form {
    /// Return the form for a column of type `dtype`, or refuse naming the
    /// column and its whole type.
    ///
    /// `UInt64`, `Int128` and `UInt128` are refused by width, as the Python
    /// vocabulary refuses them when it is not handed the values: each can hold
    /// numbers no `i64` carries, and naming the column `i64` would declare a
    /// type that cannot hold the value written beside it. The refusal names
    /// the column's type rather than the element that has no tag, so a list of
    /// categories reads as the list the column is.
    fn of(dtype: &DataType, column: &str) -> Result<Self, ContentGrammarError> {
        Self::read(dtype, 0).ok_or_else(|| ContentGrammarError::NoTag {
            column: column.to_owned(),
            dtype: dtype.to_string(),
        })
    }

    /// Return the form for `dtype` found `depth` lists down, or nothing where
    /// the grammar has no tag for it.
    fn read(dtype: &DataType, depth: usize) -> Option<Self> {
        let form = match dtype {
            DataType::Boolean => Self::Flag,
            DataType::Int8 => Self::Whole(Width::I8),
            DataType::Int16 => Self::Whole(Width::I16),
            DataType::Int32 => Self::Whole(Width::I32),
            DataType::Int64 => Self::Whole(Width::I64),
            DataType::UInt8 => Self::Whole(Width::U8),
            DataType::UInt16 => Self::Whole(Width::U16),
            DataType::UInt32 => Self::Whole(Width::U32),
            DataType::Float32 => Self::Decimal(Precision::Single),
            DataType::Float64 => Self::Decimal(Precision::Double),
            DataType::String => Self::Text,
            DataType::Date => Self::Days,
            DataType::Datetime(unit, zone) => Self::Instant(*unit, zone_written(zone.as_ref())),
            DataType::List(inner) | DataType::Array(inner, _) if depth < MAX_LIST_DEPTH => {
                Self::Sequence(Box::new(Self::read(inner, depth + 1)?))
            }
            _ => return None,
        };
        Some(form)
    }

    /// Append the tag: one byte, or for a list the sequence tag and then the
    /// element's own, so `list[list[f64]]` is three bytes.
    fn tag(&self, out: &mut Vec<u8>) {
        match self {
            Self::Flag => out.push(TAG_FLAG),
            Self::Whole(_) => out.push(TAG_WHOLE_NUMBER),
            Self::Days => out.push(TAG_DATE),
            Self::Instant(_, zone) => {
                out.push(TAG_DATETIME);
                push_text(out, zone.as_bytes());
            }
            Self::Decimal(_) => out.push(TAG_DECIMAL),
            Self::Text => out.push(TAG_TEXT),
            Self::Sequence(element) => {
                out.push(TAG_SEQUENCE);
                element.tag(out);
            }
        }
    }
}

/// One chunk's storage, read through its form: every downcast done once,
/// before the first value is written.
enum Values<'a> {
    Flag(&'a BooleanArray),
    I8(&'a PrimitiveArray<i8>),
    I16(&'a PrimitiveArray<i16>),
    I32(&'a PrimitiveArray<i32>),
    I64(&'a PrimitiveArray<i64>),
    U8(&'a PrimitiveArray<u8>),
    U16(&'a PrimitiveArray<u16>),
    U32(&'a PrimitiveArray<u32>),
    Days(&'a PrimitiveArray<i32>),
    Instant(&'a PrimitiveArray<i64>, TimeUnit, String),
    Single(&'a PrimitiveArray<f32>),
    Double(&'a PrimitiveArray<f64>),
    Text(&'a Utf8ViewArray),
    List(&'a ListArray<i64>, Box<Values<'a>>),
    FixedWidth(&'a FixedSizeListArray, Box<Values<'a>>),
}

impl<'a> Values<'a> {
    /// Read `array` as `form` says its values are kept, or say it cannot be.
    ///
    /// `name` and `series` are only for the refusal, which names the column
    /// and its type.
    fn of(
        form: &Form,
        array: &'a dyn Array,
        name: &str,
        series: &Series,
    ) -> Result<Self, ContentGrammarError> {
        let values = match form {
            Form::Flag => Self::Flag(downcast(array, name, series)?),
            Form::Whole(Width::I8) => Self::I8(downcast(array, name, series)?),
            Form::Whole(Width::I16) => Self::I16(downcast(array, name, series)?),
            Form::Whole(Width::I32) => Self::I32(downcast(array, name, series)?),
            Form::Whole(Width::I64) => Self::I64(downcast(array, name, series)?),
            Form::Whole(Width::U8) => Self::U8(downcast(array, name, series)?),
            Form::Whole(Width::U16) => Self::U16(downcast(array, name, series)?),
            Form::Whole(Width::U32) => Self::U32(downcast(array, name, series)?),
            Form::Days => Self::Days(downcast(array, name, series)?),
            Form::Instant(unit, _) => {
                Self::Instant(downcast(array, name, series)?, *unit, name.to_owned())
            }
            Form::Decimal(Precision::Single) => Self::Single(downcast(array, name, series)?),
            Form::Decimal(Precision::Double) => Self::Double(downcast(array, name, series)?),
            Form::Text => Self::Text(downcast(array, name, series)?),
            Form::Sequence(element) => {
                if let Some(list) = array.as_any().downcast_ref::<ListArray<i64>>() {
                    Self::List(
                        list,
                        Box::new(Self::of(element, list.values().as_ref(), name, series)?),
                    )
                } else if let Some(fixed) = array.as_any().downcast_ref::<FixedSizeListArray>() {
                    Self::FixedWidth(
                        fixed,
                        Box::new(Self::of(element, fixed.values().as_ref(), name, series)?),
                    )
                } else {
                    return Err(unreadable(array, name, series));
                }
            }
        };
        Ok(values)
    }

    /// Write the values at `rows`, each behind its marker.
    fn write<S: Sink>(&self, rows: Range<usize>, sink: &mut S) -> Result<(), ContentGrammarError> {
        match self {
            Self::Flag(array) => write_flags(array, rows, sink),
            Self::I8(array) => write_primitives(array, rows, sink, |s, v| put_whole(s, v.into())),
            Self::I16(array) => write_primitives(array, rows, sink, |s, v| put_whole(s, v.into())),
            Self::I32(array) | Self::Days(array) => {
                write_primitives(array, rows, sink, |s, v| put_whole(s, v.into()))
            }
            Self::I64(array) => write_primitives(array, rows, sink, put_whole),
            Self::U8(array) => write_primitives(array, rows, sink, |s, v| put_whole(s, v.into())),
            Self::U16(array) => write_primitives(array, rows, sink, |s, v| put_whole(s, v.into())),
            Self::U32(array) => write_primitives(array, rows, sink, |s, v| put_whole(s, v.into())),
            Self::Instant(array, unit, column) => {
                let unit = *unit;
                refuse_instants_past_i64(array, rows.clone(), unit, column)?;
                write_primitives(array, rows, sink, |s, v| {
                    // Every present count was judged above, so the microseconds
                    // are there; a missing row's placeholder value is never read.
                    put_whole(s, microseconds(v, unit).unwrap_or_default());
                    push_varint(s, nanoseconds_past(v, unit));
                })
            }
            Self::Single(array) => {
                write_primitives(array, rows, sink, |s, v| put_decimal(s, v.into()))
            }
            Self::Double(array) => write_primitives(array, rows, sink, put_decimal),
            Self::Text(array) => write_text(array, rows, sink),
            Self::List(array, members) => write_lists(array, members, rows, sink),
            Self::FixedWidth(array, members) => write_fixed_width(array, members, rows, sink),
        }
    }
}

/// Return `array` as the concrete storage `T`, or refuse naming the column.
fn downcast<'a, T: 'static>(
    array: &'a dyn Array,
    name: &str,
    series: &Series,
) -> Result<&'a T, ContentGrammarError> {
    array
        .as_any()
        .downcast_ref::<T>()
        .ok_or_else(|| unreadable(array, name, series))
}

/// Refuse storage that is not the layout the column's type says it has.
fn unreadable(array: &dyn Array, name: &str, series: &Series) -> ContentGrammarError {
    ContentGrammarError::Storage {
        column: name.to_owned(),
        dtype: series.dtype().to_string(),
        storage: format!("{:?}", array.dtype()),
    }
}

/// Refuse a run of rows that falls outside the storage it was read from.
///
/// Unreachable for storage Polars built, whose offsets always lie inside
/// their values; checked rather than trusted, because the alternative is a
/// panic inside the one stamp whose whole value is being right.
fn out_of_bounds(array: &dyn Array, rows: &Range<usize>) -> ContentGrammarError {
    ContentGrammarError::OutOfBounds {
        storage: format!("{:?}", array.dtype()),
        len: array.len(),
        start: rows.start,
        end: rows.end,
    }
}

/// Write true/false flags: the marker, then `0x01` or `0x00`.
fn write_flags<S: Sink>(
    array: &BooleanArray,
    rows: Range<usize>,
    sink: &mut S,
) -> Result<(), ContentGrammarError> {
    if rows.end > array.len() {
        return Err(out_of_bounds(array, &rows));
    }
    let flags = array.values();
    let validity = array.validity().filter(|valid| valid.unset_bits() > 0);
    for row in rows {
        if validity.is_some_and(|valid| !valid.get_bit(row)) {
            sink.staged().extend_from_slice(&MISSING);
        } else {
            sink.staged()
                .extend_from_slice(&[PRESENT, u8::from(flags.get_bit(row))]);
        }
        sink.settle();
    }
    Ok(())
}

/// Write fixed-width values -- whole numbers, dates, timestamps, decimals --
/// each by `put_value`, or as missing where the validity says so.
fn write_primitives<T: NativeType, S: Sink>(
    array: &PrimitiveArray<T>,
    rows: Range<usize>,
    sink: &mut S,
    put_value: impl Fn(&mut Vec<u8>, T),
) -> Result<(), ContentGrammarError> {
    let Some(values) = array.values().get(rows.clone()) else {
        return Err(out_of_bounds(array, &rows));
    };
    // A bitmap with no unset bit says every value is there, and a column
    // read back from Parquet often carries one; it takes the plain loop.
    match array.validity().filter(|valid| valid.unset_bits() > 0) {
        None => {
            for &value in values {
                put_value(sink.staged(), value);
                sink.settle();
            }
        }
        Some(validity) => {
            for (row, &value) in rows.zip(values) {
                if validity.get_bit(row) {
                    put_value(sink.staged(), value);
                } else {
                    sink.staged().extend_from_slice(&MISSING);
                }
                sink.settle();
            }
        }
    }
    Ok(())
}

/// Write text: the marker, the UTF-8 byte length as a varint, then the UTF-8.
fn write_text<S: Sink>(
    array: &Utf8ViewArray,
    rows: Range<usize>,
    sink: &mut S,
) -> Result<(), ContentGrammarError> {
    if rows.end > array.len() {
        return Err(out_of_bounds(array, &rows));
    }
    let validity = array.validity().filter(|valid| valid.unset_bits() > 0);
    for row in rows {
        let staged = sink.staged();
        if validity.is_some_and(|valid| !valid.get_bit(row)) {
            staged.extend_from_slice(&MISSING);
        } else {
            staged.push(PRESENT);
            push_text(staged, array.value(row).as_bytes());
        }
        sink.settle();
    }
    Ok(())
}

/// Write list rows: each row's marker and count of members, then the members.
///
/// A missing row writes nothing of its members -- whatever its offsets span --
/// and a row holding no members writes a count of nought: the two are
/// different projections, and the marker is what tells them apart.
fn write_lists<S: Sink>(
    array: &ListArray<i64>,
    members: &Values<'_>,
    rows: Range<usize>,
    sink: &mut S,
) -> Result<(), ContentGrammarError> {
    if rows.end > array.len() {
        return Err(out_of_bounds(array, &rows));
    }
    let offsets = array.offsets().as_slice();
    let validity = array.validity().filter(|valid| valid.unset_bits() > 0);
    for row in rows.clone() {
        if validity.is_some_and(|valid| !valid.get_bit(row)) {
            sink.staged().extend_from_slice(&MISSING);
            sink.settle();
            continue;
        }
        let (Some(&start), Some(&end)) = (offsets.get(row), offsets.get(row + 1)) else {
            return Err(out_of_bounds(array, &rows));
        };
        let (Ok(start), Ok(end)) = (usize::try_from(start), usize::try_from(end)) else {
            return Err(out_of_bounds(array, &rows));
        };
        if end < start {
            return Err(out_of_bounds(array, &rows));
        }
        put_count(sink.staged(), end - start);
        sink.settle();
        members.write(start..end, sink)?;
    }
    Ok(())
}

/// Write fixed-width array rows exactly as the list rows they stand for.
///
/// A fixed length is storage, not content, so an array is hashed as the list
/// of values it holds: each row's marker, its width as the count, its members.
fn write_fixed_width<S: Sink>(
    array: &FixedSizeListArray,
    members: &Values<'_>,
    rows: Range<usize>,
    sink: &mut S,
) -> Result<(), ContentGrammarError> {
    if rows.end > array.len() {
        return Err(out_of_bounds(array, &rows));
    }
    let width = array.size();
    let validity = array.validity().filter(|valid| valid.unset_bits() > 0);
    for row in rows {
        if validity.is_some_and(|valid| !valid.get_bit(row)) {
            sink.staged().extend_from_slice(&MISSING);
            sink.settle();
            continue;
        }
        put_count(sink.staged(), width);
        sink.settle();
        members.write(row * width..(row + 1) * width, sink)?;
    }
    Ok(())
}

/// Return a timestamp's count in microseconds, from the unit it was kept in.
///
/// Nanoseconds floor towards the earlier microsecond. Milliseconds scale up,
/// and a count whose microseconds leave `i64` -- which Polars' own
/// `cast_time_unit` would wrap onto another instant -- is `None`: two
/// instants must not share a digest, so it is refused before anything is
/// written ([`refuse_instants_past_i64`]).
fn microseconds(value: i64, unit: TimeUnit) -> Option<i64> {
    match unit {
        TimeUnit::Nanoseconds => Some(value.div_euclid(NANOS_PER_MICRO)),
        TimeUnit::Microseconds => Some(value),
        TimeUnit::Milliseconds => value.checked_mul(MICROS_PER_MILLI),
    }
}

/// Refuse, naming the column, a present timestamp at `rows` whose count in
/// microseconds leaves `i64`.
///
/// Only a millisecond column can hold one; nanoseconds divide down and
/// microseconds are the count itself. Checked over the rows before any byte
/// is staged, so a refused column writes nothing.
///
/// # Errors
///
/// Returns [`ContentGrammarError::InstantPastI64`] for the first such value,
/// and [`ContentGrammarError::OutOfBounds`] if `rows` lies outside the storage.
fn refuse_instants_past_i64(
    array: &PrimitiveArray<i64>,
    rows: Range<usize>,
    unit: TimeUnit,
    column: &str,
) -> Result<(), ContentGrammarError> {
    if unit != TimeUnit::Milliseconds {
        return Ok(());
    }
    let Some(values) = array.values().get(rows.clone()) else {
        return Err(out_of_bounds(array, &rows));
    };
    let validity = array.validity();
    let past = rows.zip(values).find(|&(row, &value)| {
        validity.is_none_or(|valid| valid.get_bit(row)) && microseconds(value, unit).is_none()
    });
    match past {
        Some((_, &count)) => Err(ContentGrammarError::InstantPastI64 {
            column: column.to_owned(),
            count,
        }),
        None => Ok(()),
    }
}

/// Return the nanoseconds past the microsecond a timestamp's count names, 0 to 999.
///
/// Only a nanosecond column holds any; the remainder is taken towards the
/// earlier microsecond, as the microseconds are, so the pair always names the
/// instant: `-1` ns is microsecond `-1` and 999 ns past it.
fn nanoseconds_past(value: i64, unit: TimeUnit) -> u64 {
    match unit {
        // `rem_euclid` by a positive divisor is in `0..1000`, so the cast
        // reinterprets nothing.
        TimeUnit::Nanoseconds => value.rem_euclid(NANOS_PER_MICRO) as u64,
        TimeUnit::Microseconds | TimeUnit::Milliseconds => 0,
    }
}

/// Return the zone a timestamp column is written under: its own name, or
/// nothing for a naive column and for UTC, which read a value as one instant.
fn zone_written(zone: Option<&TimeZone>) -> String {
    match zone {
        Some(zone) if zone.as_str() != UTC => zone.as_str().to_owned(),
        _ => String::new(),
    }
}

/// Return the zigzag form of a whole number: `0, -1, 1, -2` become `0, 1, 2, 3`.
///
/// The cast reinterprets the sixty-four bits the shift and the sign mask
/// produce; that reinterpretation is the encoding, not a conversion.
fn zigzag(value: i64) -> u64 {
    ((value << 1) ^ (value >> 63)) as u64
}

/// Return a length or a count as the unsigned value its varint carries.
///
/// Lossless: a `usize` is at most sixty-four bits on every target Polars
/// builds for.
fn as_count(value: usize) -> u64 {
    value as u64
}

/// Append `value` as a varint: seven bits a byte, low group first, the high
/// bit set on every byte but the last.
#[inline]
fn push_varint(out: &mut Vec<u8>, mut value: u64) {
    while value > GROUP_MASK {
        // The mask keeps seven bits, so the narrowing loses nothing.
        out.push((value & GROUP_MASK) as u8 | CONTINUES);
        value >>= GROUP_BITS;
    }
    out.push(value as u8);
}

/// Append a present whole number as its zigzag varint.
#[inline]
fn put_whole(out: &mut Vec<u8>, value: i64) {
    out.push(PRESENT);
    push_varint(out, zigzag(value));
}

/// Append a present row's marker and its count of members.
#[inline]
fn put_count(out: &mut Vec<u8>, count: usize) {
    out.push(PRESENT);
    push_varint(out, as_count(count));
}

/// Append text behind its byte length, unmarked: a column's name, or a value
/// once its marker is written.
#[inline]
fn push_text(out: &mut Vec<u8>, text: &[u8]) {
    push_varint(out, as_count(text.len()));
    out.extend_from_slice(text);
}

/// Append a present decimal: negative zero as zero, every NaN as one payload.
#[inline]
fn put_decimal(out: &mut Vec<u8>, value: f64) {
    let bits = if value == 0.0 {
        0
    } else if value.is_nan() {
        QUIET_NAN
    } else {
        value.to_bits()
    };
    out.push(PRESENT);
    out.extend_from_slice(&bits.to_be_bytes());
}

#[cfg(test)]
mod tests {
    use super::*;
    use polars::prelude::*;

    type TestResult = Result<(), Box<dyn std::error::Error>>;

    /// Return the bytes for a frame of the one column `series`.
    fn bytes_of(series: Series) -> Result<Vec<u8>, Box<dyn std::error::Error>> {
        let frame = DataFrame::new_infer_height(vec![series.into_column()])?;
        Ok(content_bytes_of(&frame)?)
    }

    /// Return the bytes a column's values write, after its name, tag and count.
    fn values_of(series: Series, header: &[u8]) -> Result<Vec<u8>, Box<dyn std::error::Error>> {
        let bytes = bytes_of(series)?;
        assert!(
            bytes.starts_with(header),
            "expected the header {header:02x?}, got {bytes:02x?}"
        );
        Ok(bytes[header.len()..].to_vec())
    }

    /// Parse hexadecimal written with any whitespace between the pairs.
    fn hex(text: &str) -> Vec<u8> {
        let digits: Vec<u32> = text
            .chars()
            .filter(|c| !c.is_whitespace())
            .filter_map(|c| c.to_digit(16))
            .collect();
        digits
            .chunks(2)
            .map(|pair| (pair[0] * 16 + pair[1]) as u8)
            .collect()
    }

    /// A zigzag varint, worked in 128 bits so it shares no code with the encoder.
    fn whole_number_reference(value: i64) -> Vec<u8> {
        let wide = i128::from(value);
        let mut zigzagged: u128 = if wide < 0 {
            ((-wide) as u128) * 2 - 1
        } else {
            (wide as u128) * 2
        };
        let mut out = vec![PRESENT];
        loop {
            let group = (zigzagged % 128) as u8;
            zigzagged /= 128;
            if zigzagged == 0 {
                out.push(group);
                return out;
            }
            out.push(group + 128);
        }
    }

    fn list_of(name: &str, rows: Vec<Option<Series>>) -> Series {
        let mut list: ListChunked = rows.into_iter().collect();
        list.rename(name.into());
        list.into_series()
    }

    fn floats(values: &[Option<f64>]) -> Series {
        Series::new(PlSmallStr::EMPTY, values)
    }

    // --- the specification's worked examples ----------------------------------

    #[test]
    fn the_section_12_3_worked_example_reproduces() -> TestResult {
        // Three attained ages and the mortality rates against them, sorted by
        // the dimension, exactly as a table orders its frame before stamping.
        let basis = df!("age" => [45i64, 46, 47], "rate" => [0.001, 0.0012, 0.0015])?;

        assert_eq!(
            content_bytes_of(&basis)?,
            hex("02 03616765 12 03 025a 025c 025e 0472617465 13 03
                 023f50624dd2f1a9fc 023f53a92a30553261 023f589374bc6a7efa")
        );
        assert_eq!(
            lowercase_hex(&content_sha256_of(&basis)?),
            "5267aed7a08b589310c079677eddd6128fb44af9f9fbfbb1dc3d58e2b6dcd277"
        );
        Ok(())
    }

    #[test]
    fn the_injected_column_worked_example_reproduces() -> TestResult {
        // Section 12.1's `simulated_shock@1`: three values handed over as a
        // column object, hashed under the placeholder name `injected`.
        let shock = df!("injected" => [0.01, -0.02, 0.03])?;

        assert_eq!(
            content_bytes_of(&shock)?,
            hex("01 08696e6a6563746564 13 03
                 023f847ae147ae147b 02bf947ae147ae147b 023f9eb851eb851eb8")
        );
        assert_eq!(
            lowercase_hex(&content_sha256_of(&shock)?),
            "6103a3a7d560f2d5efc89e7822a8520aeda0062eaf4a44ba9632d872d819ed23"
        );
        Ok(())
    }

    #[test]
    fn one_row_is_the_grammar_s_bytes_and_no_writer_s() -> TestResult {
        let one_policy = df!(
            "attained_age" => [45i64],
            "mortality_rate" => [0.001],
            "in_force" => [true]
        )?;

        assert_eq!(
            content_bytes_of(&one_policy)?,
            hex("03
                 0c 6174746169 6e65645f616765 12 01 025a
                 0e 6d6f7274616c6974795f72617465 13 01 023f50624dd2f1a9fc
                 08 696e5f666f726365 11 01 0201")
        );
        Ok(())
    }

    // --- storage width is not content -----------------------------------------

    #[test]
    fn every_integer_width_writes_the_bytes_of_the_same_numbers() -> TestResult {
        let int64 = bytes_of(Series::new("v".into(), &[0i64, 1, 100, 127]))?;
        for dtype in [
            DataType::Int8,
            DataType::Int16,
            DataType::Int32,
            DataType::UInt8,
            DataType::UInt16,
            DataType::UInt32,
        ] {
            let narrow = Series::new("v".into(), &[0i64, 1, 100, 127]).cast(&dtype)?;
            assert_eq!(bytes_of(narrow)?, int64, "{dtype}");
        }
        Ok(())
    }

    #[test]
    fn a_single_precision_float_writes_the_double_it_widens_to() -> TestResult {
        let values = [Some(0.5f64), Some(-2.25), None, Some(1024.0), Some(-0.0)];
        let double = bytes_of(floats(&values).with_name("v".into()))?;
        let single = floats(&values)
            .with_name("v".into())
            .cast(&DataType::Float32)?;

        assert_eq!(bytes_of(single)?, double);
        Ok(())
    }

    // --- the primitive encodings -----------------------------------------------

    #[test]
    fn a_whole_number_is_a_zigzag_varint_at_every_group_boundary() -> TestResult {
        let mut values = vec![0i64, -1, 1, -2, 63, -64, 64, -65, i64::MAX, i64::MIN];
        for groups in 1..=9u32 {
            let edge = (1i64 << (7 * groups).min(62)) - 1;
            values.extend([edge, edge + 1, -edge, -edge - 1]);
        }
        let expected: Vec<u8> = values
            .iter()
            .flat_map(|value| whole_number_reference(*value))
            .collect();
        let column = Series::new("v".into(), &values);

        let written = values_of(column, &[0x01, 0x01, b'v', TAG_WHOLE_NUMBER])?;

        // The row count's own varint, then the values.
        let mut count = Vec::new();
        push_varint(&mut count, as_count(values.len()));
        assert_eq!(written, [count, expected].concat());
        Ok(())
    }

    #[test]
    fn the_top_of_the_unsigned_32_bit_range_is_an_ordinary_whole_number() -> TestResult {
        let top = Series::new("v".into(), &[u32::MAX]);

        assert_eq!(bytes_of(top)?, hex("01 0176 12 01 02 feffffff1f"));
        Ok(())
    }

    #[test]
    fn negative_zero_is_zero_and_every_nan_is_the_one_quiet_payload() -> TestResult {
        let nans = [
            0x7FF8_0000_0000_0000u64, // the quiet NaN
            0xFFF8_0000_0000_0000,    // the same, sign bit set
            0x7FF8_DEAD_BEEF_0000,    // a quiet NaN carrying a payload
            0x7FF0_0000_0000_0001,    // a signalling NaN
        ];
        let column: Vec<Option<f64>> = nans.iter().map(|b| Some(f64::from_bits(*b))).collect();
        let quiet = hex("02 7ff8000000000000");

        assert_eq!(
            values_of(floats(&column).with_name("v".into()), &hex("01 0176 13 04"))?,
            quiet.repeat(4)
        );
        assert_eq!(
            bytes_of(floats(&[Some(-0.0)]).with_name("v".into()))?,
            bytes_of(floats(&[Some(0.0)]).with_name("v".into()))?
        );

        let single_nan = Series::new("v".into(), &[f32::NAN, -f32::NAN]);
        assert_eq!(
            values_of(single_nan, &hex("01 0176 13 02"))?,
            quiet.repeat(2)
        );
        Ok(())
    }

    #[test]
    fn infinities_and_subnormals_keep_their_own_bits() -> TestResult {
        let values = [
            f64::INFINITY,
            f64::NEG_INFINITY,
            f64::MIN_POSITIVE / 2.0,
            -f64::MIN_POSITIVE / 4.0,
            f64::MAX,
            f64::MIN,
        ];
        let expected: Vec<u8> = values
            .iter()
            .flat_map(|value| [vec![PRESENT], value.to_bits().to_be_bytes().to_vec()].concat())
            .collect();
        let column = Series::new("v".into(), &values);

        assert_eq!(values_of(column, &hex("01 0176 13 06"))?, expected);
        Ok(())
    }

    #[test]
    fn a_date_is_a_count_of_days_since_1970() -> TestResult {
        let days = Series::new("v".into(), &[Some(1i32), Some(-1), None, Some(19_723)])
            .cast(&DataType::Date)?;

        assert_eq!(
            bytes_of(days)?,
            hex("01 0176 16 04 0202 0201 0100 0296b402")
        );
        Ok(())
    }

    /// A count of nanoseconds past the microsecond, as the varint it is written as.
    fn past_reference(nanos: u64) -> Vec<u8> {
        let mut out = Vec::new();
        push_varint(&mut out, nanos);
        out
    }

    /// The bytes of one instant: its microseconds, then the nanoseconds past them.
    fn instant_reference(micros: i64, nanos: u64) -> Vec<u8> {
        [whole_number_reference(micros), past_reference(nanos)].concat()
    }

    #[test]
    fn one_instant_has_one_encoding_whatever_unit_it_was_kept_in() -> TestResult {
        // A millisecond past the epoch, kept three ways: the naive header
        // writes an empty zone, and the value no nanoseconds past it.
        let expected = hex("01 0176 17 00 01 02d00f 00");
        for (unit, count) in [
            (TimeUnit::Microseconds, 1_000i64),
            (TimeUnit::Milliseconds, 1),
            (TimeUnit::Nanoseconds, 1_000_000),
        ] {
            let instant =
                Series::new("v".into(), &[count]).cast(&DataType::Datetime(unit, None))?;
            assert_eq!(bytes_of(instant)?, expected, "{unit:?}");
        }

        let in_utc = Series::new("v".into(), &[1_000i64]).cast(&DataType::Datetime(
            TimeUnit::Microseconds,
            Some(TimeZone::UTC),
        ))?;
        assert_eq!(bytes_of(in_utc)?, expected);
        Ok(())
    }

    #[test]
    fn nanoseconds_are_kept_past_the_earlier_microsecond() -> TestResult {
        let nanos = Series::new("v".into(), &[-1i64, -999, -1_000, -1_001, 999, i64::MIN])
            .cast(&DataType::Datetime(TimeUnit::Nanoseconds, None))?;
        let expected: Vec<u8> = [
            (-1i64, 999u64),
            (-1, 1),
            (-1, 0),
            (-2, 999),
            (0, 999),
            (-9_223_372_036_854_776, 192),
        ]
        .iter()
        .flat_map(|(micros, past)| instant_reference(*micros, *past))
        .collect();

        assert_eq!(values_of(nanos, &hex("01 0176 17 00 06"))?, expected);
        Ok(())
    }

    #[test]
    fn two_instants_half_a_microsecond_apart_are_two_books() -> TestResult {
        let at = |nanos: i64| -> Result<Vec<u8>, Box<dyn std::error::Error>> {
            bytes_of(
                Series::new("v".into(), &[1_577_880_000_000_000_000i64 + nanos])
                    .cast(&DataType::Datetime(TimeUnit::Nanoseconds, None))?,
            )
        };

        assert_ne!(at(0)?, at(500)?);
        assert_ne!(at(0)?, at(1)?);
        assert_eq!(at(0)?, at(0)?);
        Ok(())
    }

    #[test]
    fn a_zone_is_written_in_the_header_and_utc_reads_as_naive() -> TestResult {
        let kept = |zone: Option<TimeZone>| -> Result<Vec<u8>, Box<dyn std::error::Error>> {
            bytes_of(
                Series::new("v".into(), &[1_000i64])
                    .cast(&DataType::Datetime(TimeUnit::Microseconds, zone))?,
            )
        };
        let auckland = TimeZone::opt_try_new(Some("Pacific/Auckland"))?;

        let mut header = hex("01 0176 17");
        push_text(&mut header, b"Pacific/Auckland");
        header.extend_from_slice(&hex("01"));
        assert_eq!(
            values_of_bytes(kept(auckland.clone())?, &header),
            hex("02d00f 00")
        );
        assert_ne!(kept(auckland)?, kept(None)?);
        assert_eq!(kept(Some(TimeZone::UTC))?, kept(None)?);
        Ok(())
    }

    #[test]
    fn a_list_of_instants_carries_the_zone_behind_its_element_tag() -> TestResult {
        let auckland = TimeZone::opt_try_new(Some("Pacific/Auckland"))?;
        let inner = Series::new("".into(), &[1_000i64])
            .cast(&DataType::Datetime(TimeUnit::Microseconds, auckland))?;
        let column = list_of("v", vec![Some(inner)]);

        let mut header = hex("01 0176 15 17");
        push_text(&mut header, b"Pacific/Auckland");
        header.extend_from_slice(&hex("01"));
        assert_eq!(
            values_of_bytes(bytes_of(column)?, &header),
            hex("02 01 02d00f 00")
        );
        Ok(())
    }

    /// Return the bytes after `header`, asserting the header is where they start.
    fn values_of_bytes(bytes: Vec<u8>, header: &[u8]) -> Vec<u8> {
        assert!(
            bytes.starts_with(header),
            "expected the header {header:02x?}, got {bytes:02x?}"
        );
        bytes[header.len()..].to_vec()
    }

    #[test]
    fn milliseconds_at_the_edge_of_i64_scale_up_exactly() -> TestResult {
        // The largest millisecond counts whose microseconds an i64 holds.
        let millis = Series::new(
            "v".into(),
            &[9_223_372_036_854_775i64, -9_223_372_036_854_775],
        )
        .cast(&DataType::Datetime(TimeUnit::Milliseconds, None))?;
        let expected: Vec<u8> = [9_223_372_036_854_775_000i64, -9_223_372_036_854_775_000]
            .iter()
            .flat_map(|micros| instant_reference(*micros, 0))
            .collect();

        assert_eq!(values_of(millis, &hex("01 0176 17 00 02"))?, expected);
        Ok(())
    }

    /// Return the refusal both content doors meet hashing the one column `series`.
    fn refusal_of_millis(
        series: Series,
    ) -> Result<ContentGrammarError, Box<dyn std::error::Error>> {
        let frame = DataFrame::new_infer_height(vec![series.into_column()])?;
        let bytes = content_bytes_of(&frame).err();
        let digest = content_sha256_of(&frame).err();
        match (bytes, digest) {
            (Some(bytes), Some(digest)) => {
                assert_eq!(bytes.to_string(), digest.to_string());
                Ok(bytes)
            }
            other => Err(format!("expected both doors to refuse, got {other:?}").into()),
        }
    }

    #[test]
    fn milliseconds_whose_microseconds_leave_i64_are_refused_by_name() -> TestResult {
        // 9_223_372_036_854_776 ms once wrapped onto the microsecond count
        // -9_223_372_036_854_775_616 and wrote that instant's bytes; it is refused (section 12.3).
        for count in [
            9_223_372_036_854_776i64,
            -9_223_372_036_854_776,
            i64::MAX,
            i64::MIN,
        ] {
            let millis = Series::new("when".into(), &[Some(0i64), None, Some(count)])
                .cast(&DataType::Datetime(TimeUnit::Milliseconds, None))?;
            match refusal_of_millis(millis)? {
                ContentGrammarError::InstantPastI64 {
                    column,
                    count: held,
                } => {
                    assert_eq!((column.as_str(), held), ("when", count));
                }
                other => return Err(format!("{count}: refused as {other}").into()),
            }
        }
        Ok(())
    }

    #[test]
    fn a_millisecond_list_member_past_i64_is_refused_naming_the_column() -> TestResult {
        let members = Series::new("m".into(), &[1i64, 9_223_372_036_854_776])
            .cast(&DataType::Datetime(TimeUnit::Milliseconds, None))?;
        let lists = list_of("runs", vec![Some(members)]);
        match refusal_of_millis(lists)? {
            ContentGrammarError::InstantPastI64 { column, count } => {
                assert_eq!((column.as_str(), count), ("runs", 9_223_372_036_854_776));
            }
            other => return Err(format!("refused as {other}").into()),
        }
        Ok(())
    }

    #[test]
    fn the_refusal_message_names_the_column_the_count_and_the_move() {
        let message = ContentGrammarError::InstantPastI64 {
            column: "when".to_owned(),
            count: 9_223_372_036_854_776,
        }
        .to_string();
        for part in [
            "Column 'when'",
            "9223372036854776 ms",
            "leaves the 64-bit whole number",
            "read in the unit it was written in",
        ] {
            assert!(message.contains(part), "{part:?} not in {message:?}");
        }
    }

    #[test]
    fn text_is_utf8_behind_its_byte_length() -> TestResult {
        let long_127 = "a".repeat(127);
        let long_128 = "a".repeat(128);
        let long_16384 = "é".repeat(8_192);
        let values = [
            Some(""),
            Some("\0"),
            Some("ß"),
            Some("中"),
            Some("😀"),
            None,
            Some(long_127.as_str()),
            Some(long_128.as_str()),
            Some(long_16384.as_str()),
        ];
        let mut expected = Vec::new();
        for value in values {
            match value {
                None => expected.extend(MISSING),
                Some(text) => {
                    expected.push(PRESENT);
                    push_varint(&mut expected, as_count(text.len()));
                    expected.extend(text.as_bytes());
                }
            }
        }
        let column = Series::new("v".into(), &values);

        assert_eq!(values_of(column, &hex("01 0176 14 09"))?, expected);
        Ok(())
    }

    #[test]
    fn a_flag_is_its_marker_and_one_byte() -> TestResult {
        let flags = Series::new("v".into(), &[Some(true), Some(false), None]);

        assert_eq!(bytes_of(flags)?, hex("01 0176 11 03 0201 0200 0100"));
        Ok(())
    }

    // --- sequences, and a missing value at every level -------------------------

    #[test]
    fn a_sequence_is_the_element_s_tag_and_a_counted_run_per_row() -> TestResult {
        let paths = list_of(
            "v",
            vec![Some(floats(&[Some(1.0), None])), Some(floats(&[])), None],
        );

        assert_eq!(
            bytes_of(paths)?,
            hex("01 0176 1513 03
                 02 02 023ff0000000000000 0100
                 02 00
                 0100")
        );
        Ok(())
    }

    #[test]
    fn a_missing_value_is_its_marker_and_the_placeholder_at_every_level() -> TestResult {
        let inner_a = list_of("", vec![Some(floats(&[Some(1.0), None])), None]);
        let inner_b = list_of("", vec![Some(floats(&[]))]);
        let nested = list_of(
            "v",
            vec![
                Some(inner_a),
                None,
                Some(inner_b),
                Some(Series::new_empty(
                    PlSmallStr::EMPTY,
                    &DataType::List(Box::new(DataType::Float64)),
                )),
            ],
        );

        assert_eq!(
            bytes_of(nested)?,
            hex("01 0176 151513 04
                 02 02  02 02 023ff0000000000000 0100  0100
                 0100
                 02 01  02 00
                 02 00")
        );
        Ok(())
    }

    #[test]
    fn a_fixed_width_array_is_hashed_as_the_list_it_holds() -> TestResult {
        let rows = vec![
            Some(floats(&[Some(1.0), Some(2.0)])),
            None,
            Some(floats(&[Some(3.0), None])),
        ];
        let as_list = list_of("v", rows.clone());
        let as_array = list_of("v", rows).cast(&DataType::Array(Box::new(DataType::Float64), 2))?;
        assert!(matches!(as_array.dtype(), DataType::Array(_, 2)));

        assert_eq!(bytes_of(as_array.clone())?, bytes_of(as_list.clone())?);

        // An array cut from a larger one is the rows it holds.
        assert_eq!(
            bytes_of(as_array.slice(1, 2))?,
            bytes_of(as_list.slice(1, 2))?
        );
        let zero_width = list_of("v", vec![Some(floats(&[])), None])
            .cast(&DataType::Array(Box::new(DataType::Float64), 0))?;
        assert_eq!(bytes_of(zero_width)?, hex("01 0176 1513 02 0200 0100"));

        // An array inside a list is carried the same way.
        let listed_arrays = list_of(
            "v",
            vec![
                Some(as_list.cast(&DataType::Array(Box::new(DataType::Float64), 2))?),
                None,
            ],
        );
        let listed_lists = list_of("v", vec![Some(as_list), None]);
        assert_eq!(bytes_of(listed_arrays)?, bytes_of(listed_lists)?);
        Ok(())
    }

    #[test]
    fn a_list_nests_three_deep_and_no_deeper() -> TestResult {
        let one = list_of("", vec![Some(floats(&[Some(1.0)]))]);
        let two = list_of("", vec![Some(one)]);
        let three = list_of("v", vec![Some(two.clone())]);
        assert!(bytes_of(three)?.starts_with(&hex("01 0176 15151513")));

        // Refused naming the column's own type, not the element a level
        // too deep: the list is what the column is.
        let four = list_of("v", vec![Some(list_of("", vec![Some(two)]))]);
        let refused = bytes_of(four);
        assert!(
            refused.as_ref().is_err_and(|e| e
                .to_string()
                .contains("Column 'v' has type list[list[list[list[f64]]]],")),
            "{refused:?}"
        );
        Ok(())
    }

    #[test]
    fn a_type_with_no_tag_is_refused_naming_the_column() -> TestResult {
        let refused = [
            Series::new("policy_id".into(), &[7u64]),
            Series::new_null("blank".into(), 2),
            Series::new("gap".into(), &[1i64]).cast(&DataType::Duration(TimeUnit::Microseconds))?,
            Series::new("raw".into(), &[b"x".as_slice()]),
            StructChunked::from_series(
                "record".into(),
                1,
                [Series::new("a".into(), &[1i64])].iter(),
            )?
            .into_series(),
        ];
        for series in refused {
            let name = series.name().to_string();
            let whole_type = series.dtype().to_string();
            let frame = DataFrame::new_infer_height(vec![series.into_column()])?;
            match content_sha256_of(&frame) {
                Err(ContentGrammarError::NoTag { column, dtype }) => {
                    assert_eq!((column, dtype), (name, whole_type));
                }
                other => panic!("{name} was not refused: {other:?}"),
            }
        }

        // A list of something with no tag is refused as the list it is.
        let listed = list_of(
            "durations",
            vec![Some(
                Series::new("".into(), &[1i64])
                    .cast(&DataType::Duration(TimeUnit::Microseconds))?,
            )],
        );
        let frame = DataFrame::new_infer_height(vec![listed.into_column()])?;
        match content_bytes_of(&frame) {
            Err(ContentGrammarError::NoTag { dtype, .. }) => {
                assert_eq!(dtype, "list[duration[\u{3bc}s]]")
            }
            other => panic!("the list of durations was not refused: {other:?}"),
        }
        Ok(())
    }

    // --- names --------------------------------------------------------------------

    #[test]
    fn a_name_holding_a_nul_is_written_like_any_other() -> TestResult {
        // A Polars name may hold a NUL, and the grammar writes it as the UTF-8
        // it is, behind its length -- wherever in the name it falls.
        let names = ["\0rate", "rate\0note", "rate\0", "\0"];
        let own = DataFrame::new_infer_height(
            names
                .iter()
                .map(|name| Series::new((*name).into(), &[1i64]).into_column())
                .collect(),
        )?;
        let mut expected = vec![0x04];
        for name in names {
            push_text(&mut expected, name.as_bytes());
            expected.extend(hex("12 01 0202"));
        }
        assert_eq!(content_bytes_of(&own)?, expected);

        // Handed over under placeholders with the names beside the frame, as a
        // frame from Python is, the bytes and the digest are the same.
        let placeholders = DataFrame::new_infer_height(
            (0..names.len())
                .map(|index| Series::new(index.to_string().into(), &[1i64]).into_column())
                .collect(),
        )?;
        assert_eq!(content_bytes_of_named(&placeholders, &names)?, expected);
        assert_eq!(
            content_sha256_of_named(&placeholders, &names)?,
            content_sha256_of(&own)?
        );
        Ok(())
    }

    #[test]
    fn names_that_are_not_one_per_column_are_refused() -> TestResult {
        let frame = df!("0" => [1i64], "1" => [2i64])?;

        for names in [vec!["a"], vec!["a", "b", "c"], vec![]] {
            match content_sha256_of_named(&frame, &names) {
                Err(ContentGrammarError::Names {
                    names: given,
                    columns: 2,
                }) => {
                    assert_eq!(given, names.len());
                }
                other => panic!("{names:?} was not refused: {other:?}"),
            }
        }
        Ok(())
    }

    #[test]
    fn a_refusal_names_the_column_by_the_name_it_was_given() -> TestResult {
        let placeholder = df!("0" => [7u64])?;

        match content_bytes_of_named(&placeholder, &["policy\0id"]) {
            Err(ContentGrammarError::NoTag { column, .. }) => assert_eq!(column, "policy\0id"),
            other => panic!("the u64 column was not refused: {other:?}"),
        }
        Ok(())
    }

    // --- frames, chunks and slices ---------------------------------------------

    #[test]
    fn an_empty_frame_is_a_count_of_nought() -> TestResult {
        assert_eq!(content_bytes_of(&DataFrame::empty())?, vec![0x00]);

        let no_rows = Series::new_empty("v".into(), &DataType::Float64);
        assert_eq!(bytes_of(no_rows)?, hex("01 0176 13 00"));

        let all_missing =
            Series::full_null("v".into(), 2, &DataType::List(Box::new(DataType::String)));
        assert_eq!(bytes_of(all_missing)?, hex("01 0176 1514 02 0100 0100"));
        Ok(())
    }

    #[test]
    fn chunks_and_slices_are_the_rows_they_hold() -> TestResult {
        let words = [
            Some("TERM"),
            None,
            Some("ß"),
            Some(""),
            Some("WL"),
            Some("中"),
        ];
        let whole = Series::new("v".into(), &words);

        let mut chunked = Series::new("v".into(), &words[..2]);
        chunked.append(&Series::new("v".into(), &words[2..]))?;
        assert_eq!(chunked.n_chunks(), 2);
        assert_eq!(bytes_of(chunked)?, bytes_of(whole.clone())?);

        let sliced = whole.slice(1, 4);
        assert_eq!(
            bytes_of(sliced)?,
            bytes_of(Series::new("v".into(), &words[1..5]))?
        );

        let numbers = Series::new("v".into(), &[Some(1i64), None, Some(-3), Some(4)]);
        assert_eq!(
            bytes_of(numbers.slice(1, 3))?,
            bytes_of(Series::new("v".into(), &[None, Some(-3i64), Some(4)]))?
        );

        let lists = list_of(
            "v",
            vec![
                Some(floats(&[Some(1.0)])),
                None,
                Some(floats(&[Some(2.0), None])),
                Some(floats(&[])),
            ],
        );
        let rebuilt = list_of(
            "v",
            vec![None, Some(floats(&[Some(2.0), None])), Some(floats(&[]))],
        );
        assert_eq!(bytes_of(lists.slice(1, 3))?, bytes_of(rebuilt)?);
        Ok(())
    }

    // --- the digest -------------------------------------------------------------

    #[test]
    fn the_streamed_digest_is_the_digest_of_the_bytes() -> TestResult {
        let long_text = "x".repeat(50);
        let frame = df!(
            "n" => (0..5_000i64).collect::<Vec<_>>(),
            "text" => (0..5_000).map(|i| if i % 7 == 0 { None } else { Some(long_text.as_str()) }).collect::<Vec<_>>(),
            "rate" => (0..5_000).map(|i| f64::from(i) / 3.0).collect::<Vec<_>>()
        )?;
        let bytes = content_bytes_of(&frame)?;
        let whole: [u8; 32] = Sha256::digest(&bytes).into();

        // The book's own stage, and stages small enough that nearly every value
        // overflows one and some values are wider than the stage itself.
        assert!(bytes.len() > STAGE_BYTES / 4);
        assert_eq!(content_sha256_of(&frame)?, whole);
        for stage in [1, 7, 64, 4_096] {
            let mut digest = Digesting::new(stage);
            write_frame(&frame, &own_names(&frame), &mut digest)?;
            assert_eq!(digest.finish(), whole, "stage of {stage} bytes");
        }
        Ok(())
    }

    #[test]
    fn a_digest_is_stamped_in_lowercase_hex() {
        assert_eq!(lowercase_hex(&[]), "");
        assert_eq!(lowercase_hex(&[0x00, 0x0f, 0xa0, 0xff]), "000fa0ff");
    }
}
