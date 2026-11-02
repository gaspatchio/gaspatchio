# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Live table data, lookup meaning and identity guards shared by all consumers."""

from __future__ import annotations

from difflib import get_close_matches
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import polars as pl

from gaspatchio._scenario_reads import check_frame_read
from gaspatchio.assumptions._dimensions import DataDimension

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from gaspatchio.assumptions._dimensions import Dimension

# Content hash (``sha256:<hex>``) of the last data registered under each table
# name in this process. Tables in the Rust registry resolve by name at execution
# time, and the kernel refuses a plan whose recorded identity no longer matches.
# We also track the last-seen content hash to warn at replacement and refuse
# stale objects early, while staying silent for the common issue-#39
# reentrancy case (re-running the same model re-registers byte-identical data).
_REGISTERED_TABLE_SHAS: dict[str, str] = {}


def _suggest_dimension(invalid_name: str, valid_names: list[str]) -> str | None:
    """Suggest a valid dimension name based on fuzzy matching.

    Uses difflib.get_close_matches for fuzzy matching, with fallback to
    prefix and suffix matching for cases like 'age' -> 'age_last'.

    Args:
        invalid_name: The invalid dimension name provided by the user
        valid_names: List of valid dimension names

    Returns:
        The suggested dimension name, or None if no close match found

    """
    # Try fuzzy match first (cutoff=0.6 catches most typos)
    matches = get_close_matches(invalid_name, valid_names, n=1, cutoff=0.6)
    if matches:
        return matches[0]

    # Try prefix matching (e.g., 'age' matches 'age_last')
    prefix_matches = [v for v in valid_names if v.startswith(invalid_name)]
    if len(prefix_matches) == 1:
        return prefix_matches[0]

    # Try suffix matching (e.g., 'last' matches 'age_last')
    suffix_matches = [v for v in valid_names if v.endswith(invalid_name)]
    if len(suffix_matches) == 1:
        return suffix_matches[0]

    return None


class TableSupersededError(RuntimeError):
    """A lookup was built from a Table whose name now resolves to different data.

    Tables resolve by name at execution time (last-writer-wins), so a lookup
    from a superseded object would silently read the newer table's values —
    the shape where a scenario override resolves to base data and a
    sensitivity sweep reports zero sensitivity. Raised at ``lookup()`` so the
    wrong number is never produced.
    """


def _normalise_on_missing(value: str | float) -> tuple[str, float | None]:
    """Validate an ``on_missing`` policy and split it into (mode, fill).

    ``"raise"`` and ``"nan"`` pass through as modes; any real number becomes
    the ``"fill"`` mode with that constant. Anything else is a ValueError.
    """
    if isinstance(value, str):
        if value in {"raise", "nan"}:
            return value, None
        msg = (
            f"on_missing must be 'raise', 'nan', or a numeric fill value; got {value!r}"
        )
        raise ValueError(msg)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "fill", float(value)
    msg = (
        "on_missing must be 'raise', 'nan', or a numeric fill value; "
        f"got {type(value).__name__}"
    )
    raise ValueError(msg)


def _declared_output_columns(dimensions: dict[str, Dimension]) -> dict[str, str]:
    """Map each dimension name to the column its processing step produces.

    A ``DataDimension`` surfaces ``rename_to`` (or its source column); melt,
    categorical, and computed dimensions surface their ``name`` attribute,
    falling back to the dict key. These are the only columns the caller
    declared as keys — everything else in the processed frame is auxiliary.
    """
    spec: dict[str, str] = {}
    for dim_name, dim in dimensions.items():
        if isinstance(dim, DataDimension):
            spec[dim_name] = dim.rename_to or dim.column
        else:
            spec[dim_name] = getattr(dim, "name", None) or dim_name
    return spec


def _declared_text_columns(dimensions: Mapping[str, Dimension]) -> set[str]:
    """Name the processed key columns the author declared as text.

    A key column whose cells all spell numbers is judged on those numbers
    when nothing says otherwise (§15 of ``spec/graph-artifact/v0-preview.md``).
    ``DataDimension(dtype=pl.String)`` says otherwise: the author has stated
    that ``"05"`` and ``"5"`` are two labels, not one quantity, and a stated
    meaning is not re-inferred from the spelling.
    """
    return {
        dim.rename_to or dim.column
        for dim in dimensions.values()
        if isinstance(dim, DataDimension)
        and dim.dtype is not None
        and dim.dtype == pl.String
    }


class TableData:
    """Hold the processed table and prepare reads without constructing proxies.

    Table owns loading, mutation and the formula-writing API. These fields remain
    live so extending or superseding a table cannot leave a copied view looking valid.
    """

    _name: str
    _registered_sha: str
    _value: str
    _df: pl.DataFrame | None
    _dimensions: dict[str, Dimension]
    _validate: bool
    _on_missing_mode: str
    _on_missing_fill: float | None
    # The sorted labels of each key column the source held as text, captured
    # before the build judges a run of digits on its numbers.
    _key_categories: dict[str, pl.Enum]
    # The file the table was read from where it was handed a path, resolved;
    # None where it was handed a frame, or where an extension appended rows
    # the file does not hold. The run record names it, so a reviewer holding
    # the file can re-read it as this table (``gspio verify --assumptions``).
    _source_file: Path | None = None
    # The steps a table built from another one carries over from it: that
    # table's own recipe steps and inherited ones, then the shock or the
    # stacking that made this one. A shocked or stacked copy names the file
    # its base was read from, and these say it is not a plain read of it.
    _inherited_steps: tuple[dict[str, Any], ...] = ()
    # The kind each key column held as a date or a timestamp had before the
    # build held it as a whole number of its unit.
    _key_kinds: Mapping[str, pl.DataType] = MappingProxyType({})

    def _reconstruction_dimensions(self) -> dict[str, str]:
        """Dimensions spec that rebuilds this table from its PROCESSED frame.

        Reconstruction (with_shock/from_shocks) feeds the processed DataFrame
        back through the Table constructor, so each dimension key must point
        at its PROCESSED column name — which differs from the key only when
        an explicit ``DataDimension(rename_to=...)`` was used. The dict keys
        (the lookup vocabulary) are preserved either way.
        """
        return _declared_output_columns(self._dimensions)

    def _rebuild_dimensions(self) -> dict[str, str | Dimension]:
        """Dimensions that rebuild this table from its processed frame unchanged.

        ``_reconstruction_dimensions`` names the columns; this also keeps each
        text key column text. A text column in the processed frame is one the
        build left as text -- declared so, or not a run of numbers at all -- and
        handing it back undeclared would let the rebuild judge a declared
        ``["1", "5"]`` on its numbers, so a shocked copy would answer a
        different key family from the table it was shocked from.
        """
        if self._df is None:
            msg = "Table data not processed. This should not happen."
            raise RuntimeError(msg)
        schema = self._df.schema
        return {
            name: DataDimension(column=column, dtype=pl.String())
            if schema.get(column) == pl.String
            else column
            for name, column in self._reconstruction_dimensions().items()
        }

    @property
    def name(self) -> str:
        """Get the table name supplied at construction.

        Returns the stable identifier used by the registry, the typed-input
        audit trail (e.g. :class:`gaspatchio.MortalityTable.source_sha`),
        and any external consumer that needs a consistent reference for this
        table.

        !!! note "When to use"
            *   **Audit trail**: Record the table's name alongside model
                results so reviewers can identify which assumption set
                produced each valuation.
            *   **Registry lookups**: Pass the name to other gaspatchio
                components (typed inputs, scenario configs) that need a
                consistent reference for this table across the model.
            *   **Reproducibility**: Pin the name into release manifests
                so a future rerun can confirm the same table was used.

        Returns:
            str: The name string passed to the constructor

        Examples:
        --------
        ```python
        from gaspatchio.assumptions import Table
        import polars as pl

        data = pl.DataFrame({"age": [30, 35], "rate": [0.001, 0.002]})
        table = Table("mortality_standard", data, {"age": "age"}, "rate")

        print(table.name)
        ```

        """
        return self._name

    def to_dataframe(self) -> pl.DataFrame:
        """Export the complete table as a DataFrame.

        Returns the complete processed assumption table as a Polars DataFrame,
        including all key columns and the value column after dimension processing.
        Useful for data inspection, validation, and integration with external systems.

        !!! note "When to use"
            * **Data Inspection:** Export table data for validation, quality
                checks, and manual review of assumption values.
            * **Integration:** Export assumption data for use in external
                systems, reporting tools, or alternative calculation engines.
            * **Debugging:** Examine processed table structure and data
                after dimension transformations and validation.

        Returns:
            pl.DataFrame: Complete table with all processed data

        Examples:
        --------
        ```python
        from gaspatchio.assumptions import Table
        import polars as pl

        data = pl.DataFrame({"age": [30, 35], "rate": [0.001, 0.002]})
        table = Table("test", data, {"age": "age"}, "rate")

        df = table.to_dataframe()
        print(f"Exported {len(df)} rows")
        ```

        """
        if self._df is None:
            msg = "Table data not processed"
            raise RuntimeError(msg)
        # Inside a scenario run that shocks this table, its rows differ by
        # scenario, so the base rows handed back here would be BASE's alone.
        check_frame_read(self)
        return self._df.clone()

    def _materialised_df(self) -> pl.DataFrame:
        """Return a materialised polars DataFrame view of the table's data.

        ``Table._df`` is set to a materialised ``pl.DataFrame`` by
        ``_process_data`` before any user code sees it; the ``LazyFrame``
        branch is defensive (handles a hypothetical future where a lazy
        frame is stored directly).

        Raises:
            RuntimeError: If ``_df`` is None (table has no materialised source).
        """
        if self._df is not None:
            if isinstance(self._df, pl.LazyFrame):
                return self._df.collect()
            return self._df
        msg = "Table has no materialisable source"
        raise RuntimeError(msg)

    def validate_lookup(
        self,
        _dimensions: Mapping[str, object] | None = None,
        **kwargs: object,
    ) -> None:
        """Validate a lookup configuration without executing.

        Checks that a lookup configuration provides all required dimensions
        and that dimension names match the table's configuration. Useful
        for validating lookup calls before execution and catching errors early.

        !!! note "When to use"
            * **Error Prevention:** Validate lookup configurations before
                execution to catch missing or invalid dimensions early.
            * **Dynamic Validation:** Check programmatically generated
                lookup calls for correctness in complex model workflows.
            * **Testing:** Validate lookup configurations in unit tests
                without executing expensive lookup operations.

        Args:
            _dimensions: Optional mapping of dimension names to operands.
            **kwargs: Dimension name to column/expression mapping

        Raises:
            ValueError: If dimension configuration is invalid

        Examples:
        --------
        ```python
        from gaspatchio.assumptions import Table
        import polars as pl

        data = pl.DataFrame({"age": [30, 35], "rate": [0.001, 0.002]})

        table = Table("test", data, {"age": "age"}, "rate")

        # Valid lookup - no error
        table.validate_lookup(age="current_age")

        # Invalid lookup - raises ValueError
        try:
            table.validate_lookup(invalid_dim="some_col")
        except ValueError as e:
            print(f"Validation error: {e}")
        ```

        """
        # Merge both sources of dimensions
        all_dimensions: dict[str, object] = {}
        if _dimensions:
            all_dimensions.update(_dimensions)
        all_dimensions.update(kwargs)

        # Check that all provided dimensions exist
        for dim_name in all_dimensions:
            if dim_name not in self._dimensions:
                available = list(self._dimensions.keys())
                suggestion = _suggest_dimension(dim_name, available)

                msg = f"Invalid dimension '{dim_name}' for table '{self._name}'."
                if suggestion:
                    msg += f"\n\nDid you mean '{suggestion}'?"
                msg += f"\n\nAvailable dimensions: {', '.join(available)}"

                raise ValueError(msg)

        # Check that all required dimensions are provided
        required_dims = set(self._dimensions.keys())
        provided_dims = set(all_dimensions.keys())

        if required_dims != provided_dims:
            missing = required_dims - provided_dims
            extra = provided_dims - required_dims

            error_parts = []
            if missing:
                error_parts.append(f"Missing: {sorted(missing)}")
            if extra:
                error_parts.append(f"Extra: {sorted(extra)}")

            raise ValueError(
                f"Dimension mismatch for table '{self._name}': "
                + "; ".join(error_parts),
            )

    def _lookup_schema(self) -> tuple[list[str], str]:
        """Return the processed key and answer columns, in native lookup order.

        The lowering that registers this table with the native store and the
        artefact exporter both read the table through this pair, so the key
        columns they see are the processed ones, in the order the native
        lookup encodes them, with the answer column named apart.
        """
        return (
            [
                column
                for column in self._materialised_df().columns
                if column != self._value
            ],
            self._value,
        )

    def _lookup_inputs(
        self,
        all_dimensions: Mapping[str, object],
        on_missing: str | float | None,
    ) -> tuple[list[object], str, float | None]:
        """Validate a read and return ordered operands and its missing-key policy.

        Refuses a table that another registration has superseded, runs the
        optional dimension validation, then requires exactly the declared
        dimensions whether or not validation is on. The key operands come back
        in processed key-column order, translated from the user's dimension
        names, and the miss policy is the per-lookup override when one is
        given, else the table's default.
        """
        # Refuse the stale object at lookup construction as well as execution.
        # The native check also covers replacement AFTER this expression is
        # built (#116 — a lost override can report zero scenario sensitivity).
        registered_sha = _REGISTERED_TABLE_SHAS.get(self._name)
        if registered_sha is not None and registered_sha != self._registered_sha:
            msg = (
                f"Assumption table '{self._name}' has been superseded: another "
                f"Table was registered under this name with different data "
                f"after this object was built. This lookup is refused so a "
                f"scenario override cannot silently read newer assumptions "
                f"and report zero sensitivity. Look up from the most recently "
                f"built '{self._name}' Table, or give the tables distinct "
                f"names."
            )
            raise TableSupersededError(msg)

        if self._validate:
            # Dimension names are data, including a name matching this parameter.
            self.validate_lookup(_dimensions=all_dimensions)

        # Preserve processed key ordering and the declared dimension vocabulary.
        if self._df is None:
            msg = "Table data not processed. This should not happen."
            raise RuntimeError(msg)

        key_columns = [col for col in self._df.columns if col != self._value]

        self._require_lookup_dimensions(all_dimensions)

        # Lookups always speak the user's dimension names (the dict keys).
        # Processed key columns normally carry those names already (the
        # shorthand rename), but an explicit DataDimension(rename_to=...) or
        # a Melt/Categorical/Computed dimension whose `name` differs from its
        # dict key gives the processed column another name — translate back.
        col_to_dim = {
            column: name for name, column in self._reconstruction_dimensions().items()
        }

        # Build the key nodes in key column order. A bare string is a
        # dimension VALUE, not a column name (#37): `lookup(product="annuity")`
        # is what an actuary means by VLOOKUP, and reading it as a column
        # forced `pl.lit("annuity")` on them — Polars leaking into an ordinary
        # lookup. Reference a column with `af.product`, `af["product"]` or
        # `pl.col("product")`. `to_node` already draws that line: a string is
        # a literal, a proxy contributes its own node, a raw expression is
        # engine-native. String key columns need no pre-cast either — the Rust
        # CategoricalWithStringFallback encoder maps raw strings to the
        # table's internal categorical indices.
        key_nodes = []
        for col in key_columns:
            dim_key = col if col in all_dimensions else col_to_dim.get(col)
            if dim_key is not None and dim_key in all_dimensions:
                key_nodes.append(all_dimensions[dim_key])
            else:
                # Reachable when a dimension produces a processed column whose
                # name differs from its lookup key (e.g. a custom Dimension
                # with its own naming); tell the user both vocabularies.
                msg = (
                    f"No value provided for key column '{col}'. The processed "
                    f"table's key columns are {key_columns}; the lookup "
                    f"received {sorted(all_dimensions)}."
                )
                raise ValueError(msg)

        # Resolve the miss policy: per-lookup override beats the table default
        if on_missing is None:
            miss_mode, miss_fill = self._on_missing_mode, self._on_missing_fill
        else:
            miss_mode, miss_fill = _normalise_on_missing(on_missing)

        return key_nodes, miss_mode, miss_fill

    def _require_lookup_dimensions(self, all_dimensions: Mapping[str, object]) -> None:
        """Refuse missing/extra keys, including when optional validation is disabled.

        A lookup that names a dimension the table does not have, or omits one
        it does, would otherwise read the wrong rate or fail inside the native
        store with no mention of the table. The refusal names the table, the
        missing and extra dimensions, a close-match suggestion for each extra
        one, and the full required set.
        """
        # Validate that all required dimensions are provided
        if set(all_dimensions.keys()) != set(self._dimensions.keys()):
            provided = set(all_dimensions.keys())
            required = set(self._dimensions.keys())
            missing = required - provided
            extra = provided - required

            error_parts = []
            if missing:
                error_parts.append(f"Missing dimensions: {sorted(missing)}")
            if extra:
                # Add suggestions for extra (invalid) dimensions
                extra_with_suggestions = []
                for extra_dim in sorted(extra):
                    suggestion = _suggest_dimension(extra_dim, list(required))
                    if suggestion:
                        extra_with_suggestions.append(
                            f"'{extra_dim}' (did you mean '{suggestion}'?)"
                        )
                    else:
                        extra_with_suggestions.append(f"'{extra_dim}'")
                error_parts.append(f"Extra dimensions: {extra_with_suggestions}")

            raise ValueError(
                f"Dimension mismatch for table '{self._name}'. "
                + "; ".join(error_parts)
                + f"\nRequired dimensions: {sorted(required)}",
            )
