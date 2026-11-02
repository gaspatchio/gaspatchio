# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Strategy implementations for overflow and fill operations.

This module provides composable strategies for handling overflow columns and
filling missing values in assumption tables. Strategies are designed to work
with the new dimension-based API and avoid magic column names.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Final, Literal

import polars as pl
from loguru import logger

from gaspatchio._warning import warn

# How many rows an overflow extension may add before it warns: each overflow
# row is copied once per value up to `to_value`, so a wide table extended far
# multiplies quickly.
_LARGE_EXPANSION_ROWS: Final = 1_000_000


class OverflowStrategy(ABC):
    """Base class for overflow handling strategies."""

    @abstractmethod
    def apply(self, df: pl.DataFrame, dimension_name: str) -> pl.DataFrame:
        """Apply overflow strategy to the DataFrame.

        Args:
            df: DataFrame to process
            dimension_name: Name of the dimension column containing overflow values

        Returns:
            Processed DataFrame with overflow expansion applied

        """


class FillStrategy(ABC):
    """Base class for fill strategies."""

    @abstractmethod
    def apply(
        self,
        df: pl.DataFrame,
        group_columns: list[str] | None = None,
    ) -> pl.DataFrame:
        """Apply fill strategy to the DataFrame.

        Args:
            df: DataFrame to process
            group_columns: Column names identifying the group each row belongs
                to. When provided, the fill is applied independently *within*
                each group via a window (``.over(...)``) expression, so values
                never bleed across groups. When ``None`` or empty, the fill is
                applied globally across the whole ``value`` column.

        Returns:
            Processed DataFrame with missing values filled

        """


@dataclass
class ExtendOverflow(OverflowStrategy):
    """Extend an overflow column to a specified value.

    This strategy finds rows where a dimension contains the specified overflow
    column value and creates additional rows extending from the detected maximum
    numeric value up to the specified to_value.
    """

    column: str  # Column name like "Ultimate", "Ult."
    to_value: int = 200
    from_value: int | None = None  # Auto-detect if None

    def apply(self, df: pl.DataFrame, dimension_name: str) -> pl.DataFrame:
        """Apply overflow extension to the DataFrame."""
        if df.is_empty():
            return df

        # Check if the overflow column exists in the dimension values
        unique_values = df[dimension_name].unique().to_list()

        if self.column not in unique_values:
            logger.debug(
                f"Overflow column '{self.column}' not found in dimension "
                f"'{dimension_name}'. Available values: {unique_values}",
            )
            return df

        # Determine starting value for extension
        start_value = self._determine_start_value(unique_values)
        if start_value is None:
            warn(
                f"Cannot determine starting point for overflow extension in "
                f"dimension '{dimension_name}', so the '{self.column}' rows are "
                f"not extended. Pass from_value= to ExtendOverflow to say where "
                f"the extension starts.",
            )
            return df
        if start_value > self.to_value:
            # The ultimate rows would extend over no key at all and drop out of
            # the table, so a lookup past the select period misses -- or, under
            # on_missing, answers its fill -- with nothing naming the cause.
            where = (
                f"from_value={start_value}"
                if self.from_value is not None
                else f"duration {start_value}, after the last select column"
            )
            msg = (
                f"ExtendOverflow({self.column!r}, to_value={self.to_value}) would "
                f"extend the {self.column!r} rows from {where}, which is past "
                f"to_value={self.to_value}, so they would cover no key of "
                f"{dimension_name!r} and drop out of the table. Set to_value to "
                f"the last {dimension_name!r} the table must answer, at least "
                f"{start_value}, or leave the {self.column!r} column out."
            )
            raise ValueError(msg)

        # Split data into overflow and non-overflow
        non_overflow_data = df.filter(pl.col(dimension_name) != self.column)
        overflow_data = df.filter(pl.col(dimension_name) == self.column)

        if overflow_data.is_empty():
            logger.debug(f"No overflow data found for '{self.column}'")
            return non_overflow_data

        # Create expansion rows
        expansion_df = self._create_expansion_rows(
            overflow_data,
            dimension_name,
            start_value,
        )

        # Combine results
        if expansion_df.is_empty():
            result = non_overflow_data
        else:
            result = pl.concat([non_overflow_data, expansion_df])

        logger.debug(
            f"Extended overflow from {start_value} to {self.to_value} "
            f"for '{self.column}' in dimension '{dimension_name}' "
            f"(added {len(expansion_df) if not expansion_df.is_empty() else 0} rows)",
        )

        return result

    def _determine_start_value(self, unique_values: list[str]) -> int | None:
        """Determine the starting value for overflow extension."""
        if self.from_value is not None:
            return self.from_value

        # Auto-detect: get maximum numeric value (excluding overflow column)
        numeric_values = []
        for val in unique_values:
            if val != self.column:
                # Try direct conversion first
                try:
                    numeric_values.append(int(val))
                    continue
                except ValueError:
                    pass

                # Try to extract numeric parts for mixed formats
                numeric_matches = re.findall(r"\d+", str(val))
                if numeric_matches:
                    try:
                        # Take the last numeric part found
                        numeric_values.append(int(numeric_matches[-1]))
                    except ValueError:
                        continue

        if not numeric_values:
            return None

        return max(numeric_values) + 1

    def _create_expansion_rows(
        self,
        overflow_data: pl.DataFrame,
        dimension_name: str,
        start_value: int,
    ) -> pl.DataFrame:
        """Create expansion rows for the overflow data."""
        if start_value > self.to_value:
            return pl.DataFrame(schema=overflow_data.schema).clear()

        expansion_range = self.to_value - start_value + 1
        original_rows = len(overflow_data)
        total_new_rows = original_rows * expansion_range

        # Memory warning for large expansions
        if total_new_rows > _LARGE_EXPANSION_ROWS:
            warn(
                f"Large overflow expansion: {total_new_rows:,} rows will be created "
                f"({original_rows:,} overflow rows × {expansion_range} values). "
                f"Consider reducing to_value parameter.",
            )

        # Generate expansion rows
        expansion_rows = []
        for new_value in range(start_value, self.to_value + 1):
            expanded = overflow_data.with_columns(
                pl.lit(str(new_value)).alias(dimension_name),
            )
            expansion_rows.append(expanded)

        return (
            pl.concat(expansion_rows)
            if expansion_rows
            else pl.DataFrame(schema=overflow_data.schema).clear()
        )


@dataclass
class AutoDetectOverflow(OverflowStrategy):
    """Automatically detect and extend overflow column.

    This strategy automatically detects overflow columns using common patterns
    and then applies overflow extension using the ExtendOverflow strategy.
    """

    patterns: list[str] = field(
        default_factory=lambda: [
            "ult",
            "ult.",
            "ultimate",
            "term",
            "999",
            "",
        ],
    )
    to_value: int = 200

    def apply(self, df: pl.DataFrame, dimension_name: str) -> pl.DataFrame:
        """Apply auto-detected overflow extension to the DataFrame."""
        if df.is_empty():
            return df

        # Get unique values in the dimension
        unique_values = df[dimension_name].unique().to_list()

        # Try to detect overflow column
        overflow_col = self._detect_overflow_column(unique_values)

        if overflow_col is None:
            logger.debug(
                f"No overflow column detected in dimension '{dimension_name}' "
                f"using patterns {self.patterns}. Available values: {unique_values}",
            )
            return df

        # Use ExtendOverflow strategy with detected column
        extend_strategy = ExtendOverflow(column=overflow_col, to_value=self.to_value)
        return extend_strategy.apply(df, dimension_name)

    def _detect_overflow_column(self, values: list[str]) -> str | None:
        """Detect overflow column using pattern matching."""
        for value in values:
            value_lower = str(value).lower().strip()
            if value_lower in self.patterns:
                return value
        return None


def _interpolation_key(df: pl.DataFrame, group_columns: list[str]) -> pl.Expr:
    """Return the numeric key a blank is interpolated along, or refuse.

    The key is the one column that is neither a group column nor ``value``:
    for a melted dimension it is the melted column, whose labels are the
    column headers (``"1"``, ``"2"``, ``"5"``). Interpolating by row position
    instead reads the headers in whatever order they were listed, so a
    ``"1", "10", "2", "3", "5"`` header order, or a gap in the durations,
    gives a value no actuary would. A label that is not a number has no
    distance between neighbours, so nothing can be interpolated along it.
    """
    candidates = [c for c in df.columns if c not in group_columns and c != "value"]
    if len(candidates) != 1:
        msg = (
            f"LinearInterpolate cannot tell which column to interpolate along: "
            f"the rows carry {candidates} besides the group columns "
            f"{group_columns} and 'value'. Interpolation fills a blank from its "
            f"neighbours along one key, so pass every other column as a group "
            f"column, or use it through MeltDimension(fill=...), which does."
        )
        raise ValueError(msg)
    return _numeric_key(df, candidates[0], _INTERPOLATION_REFUSALS)


# What each fill along a key says when the key cannot be read as a number:
# the label that is not one, then a key of a type that is not text either.
_INTERPOLATION_REFUSALS: Final = (
    (
        "LinearInterpolate cannot fill the blanks in this table: it interpolates "
        "along '{key}' by the key's value, and {shown} is not a number, so there "
        "is no distance between neighbours to interpolate over. Name the columns "
        "by the number they stand for (a duration of 1, 2, 5 years as '1', '2', "
        "'5'), or fill the blanks before building the table."
    ),
    (
        "LinearInterpolate cannot fill the blanks in this table: it interpolates "
        "along '{key}' by the key's value, and a {dtype} key has no distance "
        "between neighbours. Fill the blanks before building the table."
    ),
)
_FORWARD_FILL_REFUSALS: Final = (
    (
        "FillForward cannot fill the blanks in this table: it carries a value "
        "forward along '{key}' in the order of the key's value, and {shown} is "
        "not a number, so the only order to fill along is the order the columns "
        "were listed in. Name the columns by the number they stand for (a "
        "duration of 1, 2, 5 years as '1', '2', '5'), or fill the blanks before "
        "building the table."
    ),
    (
        "FillForward cannot fill the blanks in this table: it carries a value "
        "forward along '{key}' in the order of the key's value, and a {dtype} key "
        "is not a number. Fill the blanks before building the table."
    ),
)


def _numeric_key(df: pl.DataFrame, key: str, refusals: tuple[str, str]) -> pl.Expr:
    """Return one key column read as a number, or refuse in the fill's own words.

    A numeric key as it is, and text that spells a number -- a melted
    dimension's column headers -- read as that number. Anything else has no
    value to fill along, and the refusal names the first labels that are not
    numbers.
    """
    dtype = df.schema[key]
    if dtype.is_numeric():
        return pl.col(key).cast(pl.Float64)
    if dtype == pl.String:
        as_number = df[key].str.strip_chars().cast(pl.Float64, strict=False)
        not_numbers = df[key].filter(as_number.is_null() & df[key].is_not_null())
        if not_numbers.is_empty():
            return pl.col(key).str.strip_chars().cast(pl.Float64)
        shown = ", ".join(repr(v) for v in not_numbers.unique(maintain_order=True)[:3])
        raise ValueError(refusals[0].format(key=key, shown=shown))
    raise ValueError(refusals[1].format(key=key, dtype=dtype))


@dataclass
class LinearInterpolate(FillStrategy):
    """Interpolate missing values using various methods.

    Provides linear, log-linear, and cubic interpolation methods for filling
    missing values in assumption tables. A blank is interpolated along the
    key's value, not the row order: with durations ``1, 2, 3, 5`` and the
    duration-3 cell blank, the fill is one third of the way from duration 2
    to duration 5, whatever order the columns were listed in. The key must be
    numeric (or text spelling a number, as melted column headers are).

    ``fill_gaps`` fills a blank that has a value on each side of it (the
    default); ``fill_gaps=False`` leaves those blanks as they are.
    ``extrapolate=True`` also fills a blank before the first value or after
    the last, along the line through the two nearest values (in log space
    for ``"log-linear"``): with durations 1 to 5 holding 0.01 to 0.04 and
    duration 5 blank, duration 5 is 0.05. A group with fewer than two values
    has no line to extend and keeps its blanks, which a lookup then reports
    as missing.
    """

    method: Literal["linear", "log-linear", "cubic"] = "linear"
    fill_gaps: bool = True
    extrapolate: bool = False

    def __post_init__(self) -> None:
        """Refuse a fill asked to fill nothing."""
        if not self.fill_gaps and not self.extrapolate:
            msg = (
                "LinearInterpolate(fill_gaps=False, extrapolate=False) fills no "
                "blank: fill_gaps fills a blank between two values and extrapolate "
                "one past the first or last. Ask for one of them, or leave fill= "
                "out to keep the blanks."
            )
            raise ValueError(msg)

    def apply(
        self,
        df: pl.DataFrame,
        group_columns: list[str] | None = None,
    ) -> pl.DataFrame:
        """Apply interpolation to fill missing values."""
        if df.is_empty():
            return df

        if self.method == "cubic":
            # Polars doesn't have cubic interpolation, fall back to linear
            warn(
                "Cubic interpolation is not available, so linear interpolation "
                'is used instead. Ask for method="linear" to choose it '
                "deliberately, or fit the curve you want and fill the gaps "
                "before building the table.",
            )
        elif self.method not in ("linear", "log-linear"):
            msg = f"Unknown interpolation method: {self.method}"
            raise ValueError(msg)
        if df["value"].null_count() == 0:
            return df

        # Interpolate along the key's value, never the row order (the order
        # the wide columns happened to be listed in).
        key = _interpolation_key(df, group_columns or [])
        value = pl.col("value").cast(pl.Float64)
        result = df
        if self.fill_gaps:
            if self.method == "log-linear":
                # Log-linear interpolation: log -> interpolate -> exp
                # Apply to the whole column after handling zeros/negatives
                expr = value.log().interpolate_by(key).exp()
            else:
                expr = value.interpolate_by(key)

            # Interpolate within each group so values never bleed across groups.
            if group_columns:
                expr = expr.over(group_columns)
            result = result.with_columns(expr.alias("value"))
        if self.extrapolate:
            result = self._extrapolated(result, key, group_columns or [])

        logger.debug(f"Applied {self.method} interpolation to fill missing values")
        return result

    def _extrapolated(
        self, df: pl.DataFrame, key: pl.Expr, group_columns: list[str]
    ) -> pl.DataFrame:
        """Fill the blanks before a group's first value and after its last.

        Each is read off the line through the group's two nearest values
        along the key: the first two for a leading blank, the last two for a
        trailing one. Interior blanks are left to ``fill_gaps``.
        """
        log = self.method == "log-linear"
        groups = group_columns or ["__fill_group"]
        work = df.with_row_index("__fill_row").with_columns(
            key.alias("__fill_x"),
            (
                pl.col("value").cast(pl.Float64).log()
                if log
                else pl.col("value").cast(pl.Float64)
            ).alias("__fill_y"),
            *([] if group_columns else [pl.lit(0).alias("__fill_group")]),
        )
        x, y = pl.col("__fill_x"), pl.col("__fill_y")
        ends = (
            work.filter(y.is_not_null())
            .sort([*groups, "__fill_x"])
            .group_by(groups, maintain_order=True)
            .agg(
                x.first().alias("__x0"),
                y.first().alias("__y0"),
                x.slice(1, 1).first().alias("__x1"),
                y.slice(1, 1).first().alias("__y1"),
                x.slice(-2, 1).first().alias("__xa"),
                y.slice(-2, 1).first().alias("__ya"),
                x.last().alias("__xb"),
                y.last().alias("__yb"),
                pl.len().alias("__known"),
            )
        )
        lines = work.join(ends, on=groups, how="left", nulls_equal=True).sort(
            "__fill_row"
        )
        x0, y0, x1, y1 = (pl.col(c) for c in ("__x0", "__y0", "__x1", "__y1"))
        xa, ya, xb, yb = (pl.col(c) for c in ("__xa", "__ya", "__xb", "__yb"))
        line = pl.col("__known") >= 2  # noqa: PLR2004 -- two points make a line
        # The table's own rows while it is built, so the choice of value is
        # made over the eager columns rather than as an expression.
        ends_of = lines.select(
            (y.is_null() & line & (x < x0)).fill_null(value=False).alias("lead_at"),
            (y0 + (x - x0) * (y1 - y0) / (x1 - x0)).alias("lead"),
            (y.is_null() & line & (x > xb)).fill_null(value=False).alias("trail_at"),
            (yb + (x - xb) * (yb - ya) / (xb - xa)).alias("trail"),
        )
        nothing = pl.Series("filled", [None] * lines.height, dtype=pl.Float64)
        filled = ends_of["lead"].zip_with(
            ends_of["lead_at"], ends_of["trail"].zip_with(ends_of["trail_at"], nothing)
        )
        if log:
            filled = filled.exp()
        value = lines["value"].cast(pl.Float64)
        return lines.with_columns(
            value.zip_with(value.is_not_null(), filled).alias("value")
        ).select(df.columns)


@dataclass
class FillConstant(FillStrategy):
    """Fill missing values with a constant value."""

    value: Any

    def apply(
        self,
        df: pl.DataFrame,
        group_columns: list[str] | None = None,  # noqa: ARG002
    ) -> pl.DataFrame:
        """Apply constant fill to missing values.

        ``group_columns`` is accepted for interface consistency but ignored:
        filling nulls with a scalar constant is independent of any grouping.
        """
        if df.is_empty():
            return df

        result = df.with_columns(
            pl.col("value").fill_null(self.value).alias("value"),
        )

        logger.debug(f"Filled missing values with constant {self.value}")
        return result


@dataclass
class FillForward(FillStrategy):
    """Forward fill missing values.

    Fills missing values by carrying forward the last valid observation along
    the key's value, not the row order: with durations listed ``"1", "10",
    "2", "3"`` and duration 3 blank, the fill is duration 2's rate, whatever
    order the columns were listed in. The key must be numeric (or text
    spelling a number, as melted column headers are); a blank along a label
    that is not a number is refused. Optionally limits the number of
    consecutive fills.
    """

    limit: int | None = None

    def apply(
        self,
        df: pl.DataFrame,
        group_columns: list[str] | None = None,
    ) -> pl.DataFrame:
        """Apply forward fill to missing values."""
        if df.is_empty():
            return df

        if self.limit is not None:
            # Implement limited forward fill using a more complex approach
            # This is a simplified version - a full implementation would need
            # to track consecutive null counts
            warn(
                f"Forward fill limit ({self.limit}) is not implemented, so the "
                f"fill is unlimited: every gap is filled, however long it is. "
                f"Leave limit unset to say so, or fill the gaps yourself before "
                f"building the table where a long gap must stay empty.",
            )

        if df["value"].null_count() == 0:
            return df

        # Fill along the key's value, never the row order (the order the wide
        # columns happened to be listed in): the rows are put in key order,
        # filled, and handed back in the order they came.
        groups = group_columns or []
        candidates = [c for c in df.columns if c not in groups and c != "value"]
        if len(candidates) != 1:
            msg = (
                f"FillForward cannot tell which column to fill along: the rows "
                f"carry {candidates} besides the group columns {groups} and "
                f"'value'. A forward fill carries a value along one key to the "
                f"blanks after it, so pass every other column as a group "
                f"column, or use it through MeltDimension(fill=...), which does."
            )
            raise ValueError(msg)
        key = _numeric_key(df, candidates[0], _FORWARD_FILL_REFUSALS)
        # Forward-fill within each group so a group never inherits a
        # neighbouring group's trailing value.
        expr = pl.col("value").forward_fill()
        if groups:
            expr = expr.over(groups)
        position = "__gaspatchio_fill_position__"
        result = (
            df.with_row_index(position)
            .sort(key, maintain_order=True)
            .with_columns(expr.alias("value"))
            .sort(position)
            .drop(position)
        )

        logger.debug("Applied forward fill to missing values")
        return result
