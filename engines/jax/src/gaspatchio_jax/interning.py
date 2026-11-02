# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Text inside the trace: one code per string, for one run, equality only.

XLA has no string. What it has is integers, and what this vocabulary asks of
text is what integers answer once a run has named its strings: section
11.1.24 keys a lookup on text, and section 11.1.26 compares it for equality
and orders it by code point. So a run builds a dictionary on the host -- every
string the inputs carry and every string a literal names -- and the trace sees
codes.

**The codes are this run's and nothing else's.** They are not stable across
runs, not written into a result, and never compared between two runs: a code
is an implementation of equality within one trace. Anything that leaves the
trace as text leaves through :meth:`Dictionary.text_of`, which puts the string
back.

**Order is insertion order and means nothing.** A code says which string,
never where the string sorts: a dictionary whose codes happened to sort would
let an ordering read off the codes pass its tests on one book and fail on the
next. An ordering over text reads the strings themselves -- the comparison
lowering ranks every interned string by code point and reads each code's
rank (:func:`gaspatchio_jax.lowerings.comparisons.code_point_ranks`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

import numpy as np
import polars as pl

__all__ = ["ABSENT", "Dictionary"]

# The code a key that is not there takes. No string is ever minted onto it,
# so a lookup keyed on it matches no row and is a miss, which is what section
# 11.1.24 makes a null key -- and that is what lets a surrender-charge
# identifier that is null on the plans with no schedule travel into the trace
# rather than refuse at the door.
ABSENT: Final[int] = -1


@dataclass(slots=True)
class Dictionary:
    """One run's interning table: text to code, and back."""

    codes: dict[str, int] = field(default_factory=dict)
    texts: list[str] = field(default_factory=list)

    def code_for(self, text: str) -> int:
        """Return the code for one string, minting one where it is new."""
        found = self.codes.get(text)
        if found is not None:
            return found
        minted = len(self.texts)
        self.codes[text] = minted
        self.texts.append(text)
        return minted

    def codes_for(self, values: list[str | None]) -> np.ndarray:
        """Return a column of text as a column of codes, absence at :data:`ABSENT`."""
        return np.asarray(
            [ABSENT if value is None else self.code_for(value) for value in values],
            dtype=np.int32,
        )

    def codes_for_series(self, series: pl.Series) -> np.ndarray:
        """Return a text column as codes, encoding each distinct string once.

        The same codes :meth:`codes_for` gives over the column's values: the
        distinct strings are minted in the order they first appear, which is
        the order a value-by-value pass meets them, and every row then takes
        its string's code. A book of a million policies carries a few hundred
        distinct plan codes, so this is a few hundred dictionary visits
        rather than a million.
        """
        text = series.cast(pl.String)
        distinct = text.drop_nulls().unique(maintain_order=True)
        minted = [self.code_for(value) for value in distinct.to_list()]
        return (
            text.replace_strict(distinct, minted, default=None, return_dtype=pl.Int32)
            .fill_null(ABSENT)
            .to_numpy()
            .astype(np.int32)
        )

    def text_of(self, code: int) -> str | None:
        """Return the string one code stands for, or None for a code from nowhere."""
        return self.texts[code] if 0 <= code < len(self.texts) else None

    def texts_of(self, codes: np.ndarray) -> list[str | None]:
        """Return a column of codes as the strings they stand for."""
        return [self.text_of(int(code)) for code in codes.reshape(-1)]
