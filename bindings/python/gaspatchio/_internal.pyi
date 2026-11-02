# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from typing import final

import polars as pl

__version__: str

# Handle on the process-wide Rust store of assumption tables. Every instance
# addresses the same global store, so constructing one costs nothing and holds
# nothing. `fingerprint` and `expected_fingerprint` carry the identity stamp a
# table publishes under: supplying them is what makes an append or a
# replacement refuse when the stored data is not the data the caller thinks it
# is. PYI021 keeps this a comment rather than a docstring.
@final
class PyAssumptionTableRegistry:
    def __init__(self) -> None: ...
    def register_table(
        self,
        name: str,
        df: pl.DataFrame,
        keys: list[str],
        value_column: str,
        storage_mode: str | None = "auto",
    ) -> None: ...
    def append_to_table(
        self,
        name: str,
        df: pl.DataFrame,
        keys: list[str],
        value_column: str,
        *,
        fingerprint: str | None = None,
        expected_fingerprint: str | None = None,
    ) -> None: ...
    def register_or_replace_table(
        self,
        name: str,
        df: pl.DataFrame,
        keys: list[str],
        value_column: str,
        force_replace: bool | None = True,
        storage_mode: str | None = "auto",
        *,
        fingerprint: str | None = None,
    ) -> None: ...
    def get_table(self, name: str) -> bool: ...
    def get_table_metadata(self, name: str) -> tuple[int, list[str]] | None: ...
    def get_table_storage_mode(self, name: str) -> str | None: ...
    def list_tables(self) -> list[str]: ...
    def table_exists(self, name: str) -> bool: ...
    def reset(self) -> None: ...

# The content grammar of spec/graph-artifact/v0-preview.md section 12.3, in the
# Rust core, with the GIL released while it encodes. Each column is written
# under the name `names` gives it, position for position; the frame's own
# names are not read. `content_sha256` streams the bytes into SHA-256 and
# returns the sixty-four lowercase hex digits, building no buffer the size of
# the frame; `content_bytes` returns the bytes themselves.
#
# Reach both through gaspatchio._identity. It names every column's type first,
# so a refusal reads as the vocabulary writes it, and hands the frame over in
# the one shape the Arrow C interface it crosses can carry (pyo3-polars 0.26,
# polars-arrow 0.53):
# - names: the interface spells a name as a NUL-terminated string, and a
#   Polars name may hold a NUL, so the frame crosses under positional
#   placeholders and the real names cross here, as Python strings;
# - time zones: a zone rides in the type's format string, so it is dropped;
#   the grammar hashes the UTC instant, which dropping it does not move;
# - fixed-width arrays: the importer slices a child the exporter already
#   sliced, so an array sliced where its window holds a null panics, and one
#   of width zero with rows panics or is refused; each crosses as the list
#   it holds, which is how the grammar carries it anyway;
# - half-precision floats: the core is not built to read them, so each
#   crosses widened, exactly, to a double.
# A type with no tag that reaches here anyway raises ValueError naming the
# column. PYI021 keeps this a comment.
def content_bytes(frame: pl.DataFrame, names: list[str]) -> bytes: ...
def content_sha256(frame: pl.DataFrame, names: list[str]) -> str: ...
