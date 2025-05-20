"""Proxy for Polars string (str) namespace operations within ActuarialFrame.

This module provides the `StringNamespaceProxy` class, which enables access
to Polars' string manipulation functionalities on columns of an `ActuarialFrame`.
It ensures that these operations can be chained and are integrated within the
ActuarialFrame's lazy evaluation and tracing capabilities.

The proxy supports operations on both scalar string columns and columns containing
lists of strings (e.g., `List[String]`), applying operations element-wise
in the latter case (shimming)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Optional

import polars as pl

# Avoid circular imports at runtime but allow type checking
if TYPE_CHECKING:
    from ...frame.base import ActuarialFrame
    from ..column_proxy import ColumnProxy
    from ..expression_proxy import ExpressionProxy

    # Define a type alias for proxy types, consistent with dispatch.py
    ProxyType = ColumnProxy | ExpressionProxy
    # Type alias for Polars temporal types used in strptime
    PolarsTemporalType = pl.Date | pl.Datetime | pl.Time


class StringNamespaceProxy:
    """A proxy for Polars expression string (str) namespace operations.

    This proxy is typically accessed via the `.str` attribute of a `ColumnProxy`
    or `ExpressionProxy` that refers to a string or list-of-strings column
    within an `ActuarialFrame`. It allows for intuitive, Polars-like string
    manipulations while remaining integrated with the ActuarialFrame ecosystem.

    It automatically handles shimming for `List[String]` columns, applying
    string methods element-wise to the contents of the lists.

    Examples:
        **Scalar Example: Uppercasing policyholder names**

        This demonstrates applying a string operation to a scalar string column.
        We'll convert policyholder names to uppercase.

        ```python
        from gaspatchio_core.frame.base import ActuarialFrame

        data = {
            "policy_id": ["POL001", "POL002", "POL003"],
            "policy_type_codes": [["TERM", "WL"], ["UL"], ["TERM", "CI"]]
        }
        af_scalar = ActuarialFrame(data)
        af_upper_names = af_scalar.select(
            af_scalar["policy_holder_name"].str.to_uppercase().alias("upper_name")
        )
        print(af_upper_names.collect())
        ```

        ```text
        shape: (3, 1)
        ┌──────────────┐
        │ upper_name   │
        │ ---          │
        │ str          │
        ╞══════════════╡
        │ JOHN DOE     │
        │ JANE SMITH   │
        │ ROBERT JONES │
        └──────────────┘
        ```

        **Vector (List Shimming) Example: Lowercasing policy type codes**

        This demonstrates applying a string operation to a list-of-strings column.
        We'll convert lists of policy type codes to lowercase.

        ```python
        from gaspatchio_core.frame.base import ActuarialFrame
        import polars as pl

        data_for_class_doctest = {
            "policy_holder_name": ["John Doe", "Jane Smith", "Robert Jones"],
            "policy_type_codes": [["TERM", "WL"], ["UL"], ["TERM", "CI"]]
        }
        af_vector = ActuarialFrame(data_for_class_doctest).with_columns(
            pl.col("policy_type_codes").cast(pl.List(pl.String))
        )
        af_lower_codes = af_vector.select(
           af_vector["policy_type_codes"].str.to_lowercase().alias("lower_codes")
        )
        print(af_lower_codes.collect())
        ```

        ```text
        shape: (3, 1)
        ┌────────────────┐
        │ lower_codes    │
        │ ---            │
        │ list[str]      │
        ╞════════════════╡
        │ ["term", "wl"] │
        │ ["ul"]         │
        │ ["term", "ci"] │
        └────────────────┘
        ```
    """

    def __init__(
        self, parent_proxy: "ProxyType", parent_af: Optional["ActuarialFrame"]
    ):
        """Initialize the StringNamespaceProxy.

        This constructor is not typically called directly by users. Instances are
        created by the dispatch mechanism when accessing `.str` on a ColumnProxy
        or ExpressionProxy.

        Args:
            parent_proxy: The parent ColumnProxy or ExpressionProxy from which
                          `.str` was accessed.
            parent_af: The parent ActuarialFrame, providing context such as the
                       underlying DataFrame/LazyFrame and schema.
        """
        self._parent_proxy = parent_proxy
        self._parent_af = parent_af

    def _get_base_expr(self) -> pl.Expr:
        """Retrieve the underlying Polars expression from the parent proxy.

        This internal method is used to get the core `polars.Expr` that this
        string namespace proxy operates on. It handles whether the parent was a
        `ColumnProxy` (referring to a column by name) or an `ExpressionProxy`
        (referring to a more complex Polars expression).

        Returns:
            pl.Expr: The base Polars expression.

        Raises:
            TypeError: If the parent proxy is not a ColumnProxy or ExpressionProxy.
        """
        from ..column_proxy import ColumnProxy
        from ..expression_proxy import ExpressionProxy

        if isinstance(self._parent_proxy, ColumnProxy):
            return pl.col(self._parent_proxy.name)
        if isinstance(self._parent_proxy, ExpressionProxy):
            return self._parent_proxy._expr
        raise TypeError(
            "StringNamespaceProxy parent must be ColumnProxy or ExpressionProxy, "
            f"got {type(self._parent_proxy).__name__}"
        )

    def _is_list_of_strings(self) -> bool:
        """Check if the parent proxy likely refers to a List of Strings column.

        This internal helper determines if list shimming should be applied for string
        operations. It inspects the schema of the parent `ActuarialFrame` if the
        parent proxy is a `ColumnProxy`.

        Currently, this check is only effective for ColumnProxy parents. For
        ExpressionProxy parents, it conservatively defaults to False, as reliably
        inferring the exact lazy type of a complex expression without collection
        can be challenging and expensive.

        Returns:
            bool: True if the parent is a ColumnProxy for a List[String] column,
                  False otherwise or if type cannot be reliably determined.
        """
        from ..column_proxy import ColumnProxy

        if (
            not self._parent_af
            or not hasattr(self._parent_af, "_df")
            or self._parent_af._df is None
        ):
            return False

        if isinstance(self._parent_proxy, ColumnProxy):
            try:
                schema = self._parent_af._df.schema
                dtype = schema.get(self._parent_proxy.name)
                if isinstance(dtype, pl.List):
                    inner_type = dtype.inner
                    return inner_type == pl.String
            except (AttributeError, KeyError, TypeError):
                return False
        return False

    def _call_string_method(
        self, method_name: str, *args: Any, **kwargs: Any
    ) -> "ExpressionProxy":
        """Core internal method to call a method on the Polars string namespace.

        This method handles the actual dispatch of a string operation to the underlying
        Polars expression. It incorporates logic for:
        1. Unwrapping arguments if they are `ColumnProxy` or `ExpressionProxy` instances.
        2. Applying list shimming: if `_is_list_of_strings()` is true, it applies
           the string method element-wise to items within lists using `list.eval()`.
        3. Directly calling the string method on the Polars expression otherwise.
        4. Wrapping the resulting Polars expression in an `ExpressionProxy`.
        5. Raising informative errors if the method doesn't exist or if Polars errors occur.

        Args:
            method_name: The name of the string method to call (e.g., "contains", "to_uppercase").
            *args: Positional arguments for the Polars string method.
            **kwargs: Keyword arguments for the Polars string method.

        Returns:
            ExpressionProxy: An ExpressionProxy wrapping the result of the Polars call.

        Raises:
            AttributeError: If the method doesn't exist on Polars' str namespace
                            or if the base expression doesn't have a str namespace.
            Exception: Propagates exceptions from the underlying Polars call.
        """
        from ..dispatch import _unwrap, _wrap

        base_expr = self._get_base_expr()
        unwrapped_args = [_unwrap(arg) for arg in args]
        unwrapped_kwargs = {key: _unwrap(val) for key, val in kwargs.items()}

        if self._is_list_of_strings():
            try:
                polars_element_str_namespace = getattr(pl.element(), "str")
                element_method = getattr(polars_element_str_namespace, method_name)
                shimming_expr = element_method(*unwrapped_args, **unwrapped_kwargs)
                result_expr = base_expr.list.eval(shimming_expr)
            except AttributeError as e:
                raise AttributeError(
                    f"Failed to construct shimming operation for str.{method_name} on a list. "
                    f"Ensure method '{method_name}' exists on pl.element().str and supports these arguments. Original error: {e}"
                ) from e
            except Exception as e:
                raise type(e)(
                    f"Error applying Polars str.{method_name} with list shimming to expression "
                    f"derived from '{self._parent_proxy}': {e}"
                ) from e
        else:
            polars_str_namespace = getattr(base_expr, "str")
            try:
                actual_polars_method = getattr(polars_str_namespace, method_name)
            except AttributeError:
                raise AttributeError(
                    f"Polars 'str' namespace has no method '{method_name}'."
                )
            try:
                result_expr = actual_polars_method(*unwrapped_args, **unwrapped_kwargs)
            except Exception as e:
                raise type(e)(
                    f"Error calling Polars str.{method_name} on expression "
                    f"derived from '{self._parent_proxy}': {e}"
                ) from e
        return _wrap(self._parent_af, result_expr)

    # --- Explicitly Proxied Methods ---
    def contains(
        self, pattern: str | pl.Expr, literal: bool = False, strict: bool = False
    ) -> "ExpressionProxy":
        """Checks if strings in a column contain a specified pattern.

        This method is essential for tasks like identifying policies with specific
        riders, flagging claims based on keywords in descriptions, or segmenting
        customers based on free-text survey responses. It mirrors Polars'
        `Expr.str.contains` and supports both literal string matching and regex.
        When applied to a column of `List[String]`, such as a list of claim notes
        for a single policy, the operation is performed element-wise on each
        string within each list, returning a list of booleans.

        Args:
            pattern (str | pl.Expr): The substring or regex pattern to search for.
                Can be a literal string (e.g., "RiderX") or a Polars expression
                (e.g., `pl.col("other_column_with_patterns")`).
            literal (bool, optional): If True, `pattern` is treated as a literal string.
                If False (default), `pattern` is treated as a regex.
            strict (bool, optional): If True and `pattern` is a Polars expression,
                an error is raised if `pattern` is not a string type. If False
                (default), `pattern` is cast to string if possible.

        Returns:
            ExpressionProxy: A new `ExpressionProxy` containing a boolean Series
                indicating for each input string whether the pattern was found.
                If the input was `List[String]`, the output will be `List[bool]`.

        Examples:
            **Scalar Example: Identifying policies with an Accidental Death Benefit (ADB) rider**

            Imagine you have a dataset of policy descriptions and you want to flag
            all policies that include an "ADB" rider.

            ```python
            from gaspatchio_core.frame.base import ActuarialFrame

            data = {
                "policy_id": ["POL001", "POL002", "POL003", "POL004"],
                "description": [
                    "Term Life Plan with ADB rider",
                    "Whole Life - Standard",
                    "Universal Life, includes Accidental Death Benefit (ADB)",
                    "Term Life, no ADB"
                ]
            }
            af = ActuarialFrame(data)
            af_with_adb_rider = af.select(
                af["description"].str.contains("ADB").alias("has_adb_rider")
            )
            print(af_with_adb_rider.collect())
            ```

            Output:
            ```text
            shape: (4, 1)
            ┌───────────────┐
            │ has_adb_rider │
            │ ---           │
            │ bool          │
            ╞═══════════════╡
            │ true          │
            │ false         │
            │ true          │
            │ false         │
            └───────────────┘
            ```

            **Vector (List Shimming) Example: Checking underwriter notes for high-risk keywords**

            Suppose each policy has a list of notes from underwriters. We want to check
            if any note for a given policy contains keywords like "medical history"
            or "hazardous occupation", which might indicate higher risk.

            ```python
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl # Keep this import if pl.List or pl.String is used explicitly

            uw_notes_data = {
                "policy_id": ["UW001", "UW002", "UW003"],
                "underwriter_notes": [
                    ["Standard risk.", "Family history clear."],
                    ["Applicant works in construction.", "Reviewed medical history: smoker."],
                    ["No concerning notes.", None, "Possible hazardous occupation mentioned."]
                ]
            }
            # Ensure the list column has the correct Polars type for shimming
            af_notes = ActuarialFrame(uw_notes_data).with_columns(
                pl.col("underwriter_notes").cast(pl.List(pl.String))
            )

            # Check for "medical history" (literal match)
            af_medical_check = af_notes.select(
                af_notes["underwriter_notes"].str.contains(
                    "medical history", literal=True
                ).alias("mentions_medical_history")
            )
            print("Medical History Check:")
            print(af_medical_check.collect())

            # Check for "hazardous occupation" using regex (case-insensitive)
            # Note: Polars regex is case-sensitive by default. For case-insensitivity,
            # you'd typically use regex flags like `(?i)`.
            af_hazardous_check = af_notes.select(
                af_notes["underwriter_notes"].str.contains(
                    r"(?i)hazardous occupation" # Case-insensitive regex
                ).alias("mentions_hazardous_occupation")
            )
            print("\\nHazardous Occupation Check:")
            print(af_hazardous_check.collect())
            ```

            Output:
            ```text
            Medical History Check:
            shape: (3, 1)
            ┌──────────────────────────┐
            │ mentions_medical_history │
            │ ---                      │
            │ list[bool]               │
            ╞══════════════════════════╡
            │ [false, false]           │
            │ [false, true]            │
            │ [false, null, false]     │
            └──────────────────────────┘

            Hazardous Occupation Check:
            shape: (3, 1)
            ┌─────────────────────────────────┐
            │ mentions_hazardous_occupation   │
            │ ---                             │
            │ list[bool]                      │
            ╞═════════════════════════════════╡
            │ [false, false]                  │
            │ [false, false]                  │
            │ [false, null, true]             │
            └─────────────────────────────────┘
            ```
        """
        return self._call_string_method(
            "contains", pattern=pattern, literal=literal, strict=strict
        )

    def to_uppercase(self) -> "ExpressionProxy":
        """Convert strings to uppercase.

        Mirrors Polars' `Expr.str.to_uppercase`.
        For `List[String]` columns, applies element-wise.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with strings converted to uppercase.

        Examples:
            **Scalar Example: Standardizing policy status codes**

            Converts policy status codes to uppercase for consistency.

            ```python
            from gaspatchio_core.frame.base import ActuarialFrame
            data = {
                "policy_id": ["S3001", "S3002", "S3003"],
                "status": ["active", "lapsed", "Active"]
            }
            af = ActuarialFrame(data)
            af_upper_status = af.select(
                af["status"].str.to_uppercase().alias("upper_status")
            )
            print(af_upper_status.collect())
            ```

            ```text
            shape: (3, 1)
            ┌──────────────┐
            │ upper_status │
            │ ---          │
            │ str          │
            ╞══════════════╡
            │ ACTIVE       │
            │ LAPSED       │
            │ ACTIVE       │
            └──────────────┘
            ```

            **Vector (List Shimming) Example: Uppercasing rider codes**

            Converts rider codes to uppercase for consistency.

            ```python
            data_list = {
                "policy_id": ["R4001", "R4002"],
                "rider_codes": [["adb", "wp"], ["ci", None, "ltc"]]
            }
            af_list = ActuarialFrame(data_list).with_columns(
                pl.col("rider_codes").cast(pl.List(pl.String))
            )
            af_upper_riders = af_list.select(
                af_list["rider_codes"].str.to_uppercase().alias("upper_rider_codes")
            )
            print(af_upper_riders.collect())
            ```

            ```text
            shape: (2, 1)
            ┌─────────────────────┐
            │ upper_rider_codes   │
            │ ---                 │
            │ list[str]           │
            ╞═════════════════════╡
            │ ["ADB", "WP"]       │
            │ ["CI", null, "LTC"] │
            └─────────────────────┘
            ```
        """
        return self._call_string_method("to_uppercase")

    def to_lowercase(self) -> "ExpressionProxy":
        """Convert strings to lowercase.

        Mirrors Polars' `Expr.str.to_lowercase`.
        For `List[String]` columns, applies element-wise.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with strings converted to lowercase.

        Examples:
            **Scalar Example: Normalizing email domains**

            >>> from gaspatchio_core.frame.base import ActuarialFrame
            >>> data = {
            ...     "client_id": [101, 102, 103],
            ...     "email_domain": ["Example.COM", "Test.Org", "Sample.NET"]
            ... }
            >>> af = ActuarialFrame(data)
            >>> af_lower_domain = af.select(
            ...     af["email_domain"].str.to_lowercase().alias("lower_domain")
            ... )
            >>> print(af_lower_domain.collect()) # doctest: +NORMALIZE_WHITESPACE
            shape: (3, 1)
            ┌──────────────┐
            │ lower_domain │
            │ ---          │
            │ str          │
            ╞══════════════╡
            │ example.com  │
            │ test.org     │
            │ sample.net   │
            └──────────────┘

            **Vector (List Shimming) Example: Lowercasing product feature tags**
            >>> data_list = {
            ...     "product_id": ["P501", "P502"],
            ...     "feature_tags": [["GUARANTEED_ISSUE", "Online"], ["FLEXIBLE_PREMIUM", "RIDER_Available"]]
            ... }
            >>> af_list = ActuarialFrame(data_list).with_columns(
            ...     pl.col("feature_tags").cast(pl.List(pl.String))
            ... )
            >>> af_lower_tags = af_list.select(
            ...     af_list["feature_tags"].str.to_lowercase().alias("lower_feature_tags")
            ... )
            >>> print(af_lower_tags.collect()) # doctest: +NORMALIZE_WHITESPACE
            shape: (2, 1)
            ┌─────────────────────────────────────────┐
            │ lower_feature_tags                      │
            │ ---                                     │
            │ list[str]                               │
            ╞═════════════════════════════════════════╡
            │ ["guaranteed_issue", "online"]          │
            │ ["flexible_premium", "rider_available"] │
            └─────────────────────────────────────────┘
        """
        return self._call_string_method("to_lowercase")

    def n_chars(self) -> "ExpressionProxy":
        """Get the number of characters in each string.

        Mirrors Polars' `Expr.str.len_chars` (Polars' `n_chars` is an alias for `len_chars`).
        For `List[String]` columns, applies element-wise, returning a `List[UInt32]`.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with the character count (as UInt32)
                             for each string.

        Examples:
            **Scalar Example: Length of product names**

            >>> from gaspatchio_core.frame.base import ActuarialFrame
            >>> data = {
            ...     "product_code": ["L-TERM-10", "L-WL-P", "ANN-SDA"],
            ...     "product_name": ["Term Life 10 Year", "Whole Life Par", "Single Deferred Annuity"]
            ... }
            >>> af = ActuarialFrame(data)
            >>> af_len = af.select(
            ...     af["product_name"].str.n_chars().alias("name_length")
            ... )
            >>> print(af_len.collect()) # doctest: +NORMALIZE_WHITESPACE
            shape: (3, 1)
            ┌─────────────┐
            │ name_length │
            │ ---         │
            │ u32         │
            ╞═════════════╡
            │ 17          │
            │ 14          │
            │ 23          │
            └─────────────┘

            **Vector (List Shimming) Example: Length of beneficiary names in a list**

            >>> data_list = {
            ...     "policy_id": ["P001", "P002"],
            ...     "beneficiaries": [["John A. Doe", "Jane B. Smith"], ["Robert King", None, "Alice Wonderland"]]
            ... }
            >>> af_list = ActuarialFrame(data_list).with_columns(
            ...     pl.col("beneficiaries").cast(pl.List(pl.String))
            ... )
            >>> af_bene_len = af_list.select(
            ...     af_list["beneficiaries"].str.n_chars().alias("beneficiary_name_lengths")
            ... )
            >>> print(af_bene_len.collect()) # doctest: +NORMALIZE_WHITESPACE
            shape: (2, 1)
            ┌──────────────────────────┐
            │ beneficiary_name_lengths │
            │ ---                      │
            │ list[u32]                │
            ╞══════════════════════════╡
            │ [11, 13]                 │
            │ [11, null, 16]           │
            └──────────────────────────┘
        """
        return self._call_string_method("len_chars")

    def len_chars(self) -> "ExpressionProxy":
        """Alias for `n_chars`. Get the number of characters in each string.

        Mirrors Polars' `Expr.str.len_chars`.
        For `List[String]` columns, applies element-wise, returning a `List[UInt32]`.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with the character count (as UInt32)
                             for each string.

        Examples:
            >>> from gaspatchio_core.frame.base import ActuarialFrame
            >>> af = ActuarialFrame({"city_names": ["New York", "Los Angeles", None, "Chicago"]})
            >>> result = af.select(af["city_names"].str.len_chars().alias("char_count"))
            >>> print(result.collect()) # doctest: +NORMALIZE_WHITESPACE
            shape: (4, 1)
            ┌────────────┐
            │ char_count │
            │ ---        │
            │ u32        │
            ╞════════════╡
            │ 8          │
            │ 11         │
            │ null       │
            │ 7          │
            └────────────┘
        """
        return self._call_string_method("len_chars")

    def len_bytes(self) -> "ExpressionProxy":
        """Get the number of bytes in each string.

        Mirrors Polars' `Expr.str.len_bytes`.
        For `List[String]` columns, applies element-wise, returning a `List[UInt32]`.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with the byte count (as UInt32)
                             for each string.

        Examples:
            **Scalar Example: Byte length of UTF-8 encoded client names**

            >>> from gaspatchio_core.frame.base import ActuarialFrame
            >>> data = {
            ...     "client_id": ["C001", "C002", "C003"],
            ...     "client_name": ["René", "沐宸", "Zoë"]
            ... }
            >>> af = ActuarialFrame(data)
            >>> af_len = af.select(
            ...     af["client_name"].str.len_bytes().alias("name_byte_length")
            ... )
            >>> print(af_len.collect()) # doctest: +NORMALIZE_WHITESPACE
            shape: (3, 1)
            ┌──────────────────┐
            │ name_byte_length │
            │ ---              │
            │ u32              │
            ╞══════════════════╡
            │ 5                │
            │ 6                │
            │ 4                │
            └──────────────────┘

            **Vector (List Shimming) Example: Byte length of comments in a list**

            >>> data_list = {
            ...     "case_id": ["Case1", "Case2"],
            ...     "comments": [["Test €", "OK"], ["€€", None]]
            ... }
            >>> af_list = ActuarialFrame(data_list).with_columns(
            ...     pl.col("comments").cast(pl.List(pl.String))
            ... )
            >>> af_comm_len = af_list.select(
            ...     af_list["comments"].str.len_bytes().alias("comment_byte_lengths")
            ... )
            >>> # 'Test €': Test (4) + space (1) + € (3) = 8 bytes
            >>> # 'OK': 2 bytes
            >>> # '€€': 3 + 3 = 6 bytes
            >>> print(af_comm_len.collect())
            shape: (2, 1)
            ┌──────────────────────┐
            │ comment_byte_lengths │
            │ ---                  │
            │ list[u32]            │
            ╞══════════════════════╡
            │ [8, 2]               │
            │ [6, null]            │
            └──────────────────────┘
        """
        return self._call_string_method("len_bytes")

    def strip_chars(
        self, characters: Optional[str | pl.Expr] = None
    ) -> "ExpressionProxy":
        """Remove leading and trailing characters from each string.

        Mirrors Polars' `Expr.str.strip_chars`.
        If `characters` is None, whitespace is removed.
        For `List[String]` columns, applies element-wise.

        Args:
            characters: Optional string of characters to remove.
                        Can also be a Polars expression that evaluates to a string.
                        If None (default), removes whitespace.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with specified characters stripped.

        Examples:
            >>> from gaspatchio_core.frame.base import ActuarialFrame
            >>> import polars as pl
            >>> data_strip = {
            ...     "raw_policy_no": ["POL-001-X", "POL-002-Y", "  003-Z  ", None, "TEMP-004"]
            ... }
            >>> # Scalar Example Part 1: Remove specific prefix/suffix characters
            >>> af1 = ActuarialFrame(data_strip)
            >>> af_stripped_specific = af1.select(
            ...     af1["raw_policy_no"].str.strip_chars("POL-XYTMEP ").alias("specific_stripped")
            ... )
            >>> print(af_stripped_specific.collect())
            shape: (5, 1)
            ┌───────────────────┐
            │ specific_stripped │
            │ ---               │
            │ str               │
            ╞═══════════════════╡
            │ 001               │
            │ 002               │
            │ 003-Z             │
            │ null              │
            │ 004               │
            └───────────────────┘
            >>> # Scalar Example Part 2: Remove only whitespace
            >>> af2 = ActuarialFrame(data_strip) # Use a fresh frame instance
            >>> af_stripped_ws = af2.select(
            ...     af2["raw_policy_no"].str.strip_chars().alias("whitespace_stripped")
            ... )
            >>> print(af_stripped_ws.collect())
            shape: (5, 1)
            ┌─────────────────────┐
            │ whitespace_stripped │
            │ ---                 │
            │ str                 │
            ╞═════════════════════╡
            │ POL-001-X           │
            │ POL-002-Y           │
            │ 003-Z               │
            │ null                │
            │ TEMP-004            │
            └─────────────────────┘

            **Vector (List Shimming) Example: Cleaning lists of product codes**

            >>> data_list = {
            ...     "policy_id": ["V001", "V002"],
            ...     "product_codes": [[" PROD_A* ", "*PROD_B "], [None, "  PROD_C*\t"]]
            ... }
            >>> af_list = ActuarialFrame(data_list).with_columns(
            ...     pl.col("product_codes").cast(pl.List(pl.String))
            ... )
            >>> # Strip asterisks and surrounding whitespace
            >>> af_list_stripped = af_list.select(
            ...     af_list["product_codes"].str.strip_chars(" *\t").alias("stripped_codes")
            ... )
            >>> print(af_list_stripped.collect())
            shape: (2, 1)
            ┌──────────────────────┐
            │ stripped_codes       │
            │ ---                  │
            │ list[str]            │
            ╞══════════════════════╡
            │ ["PROD_A", "PROD_B"] │
            │ [null, "PROD_C"]     │
            └──────────────────────┘
        """
        return self._call_string_method("strip_chars", characters=characters)

    def strip_chars_start(
        self, characters: Optional[str | pl.Expr] = None
    ) -> "ExpressionProxy":
        """Remove leading characters from each string.

        Mirrors Polars' `Expr.str.strip_chars_start`.
        If `characters` is None, leading whitespace is removed.
        For `List[String]` columns, applies element-wise.

        Args:
            characters: Optional string of characters to remove from the start.
                        Can also be a Polars expression that evaluates to a string.
                        If None (default), removes leading whitespace.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with specified leading characters stripped.

        Examples:
            **Scalar Example: Removing department prefixes from employee IDs**

            Cleans employee IDs by removing known department prefixes like 'UW-' (Underwriting)
            or 'ACT-' (Actuarial), or just leading whitespace.

            ```python
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl
            data_strip_start = {
                "emp_id_raw": ["UW-001A", "ACT-002B", "  CLAIM-003C", None, "UW-004D", "MKT005E"],
                "dept_codes_to_strip": ["UW-", "ACT-", "CLAIM-", "MKT", None, "FIN-"]
            }
            af = ActuarialFrame(data_strip_start)

            # Example 1: Strip specific prefixes defined in another column
            af_stripped_dynamic = af.select(
                af["emp_id_raw"].str.strip_chars_start(pl.col("dept_codes_to_strip")).alias("id_no_dynamic_prefix")
            )
            print("Stripping dynamic prefixes:")
            print(af_stripped_dynamic.collect())
            ```

            ```text
            Stripping dynamic prefixes:
            shape: (6, 1)
            ┌──────────────────────┐
            │ id_no_dynamic_prefix │
            │ ---                  │
            │ str                  │
            ╞══════════════════════╡
            │ 001A                 │
            │ 002B                 │
            │   CLAIM-003C         │
            │ null                 │
            │ UW-004D              │
            │ 005E                 │
            └──────────────────────┘
            ```

            ```python
            # Example 2: Strip only leading whitespace
            af_lstripped_ws = af.select(
                af["emp_id_raw"].str.strip_chars_start().alias("lstrip_whitespace_only") # characters=None
            )
            print("\\nStripping leading whitespace only:")
            print(af_lstripped_ws.collect())
            ```

            ```text
            Stripping leading whitespace only:
            shape: (6, 1)
            ┌─────────────────────────┐
            │ lstrip_whitespace_only  │
            │ ---                     │
            │ str                     │
            ╞═════════════════════════╡
            │ UW-001A                 │
            │ ACT-002B                │
            │ CLAIM-003C              │
            │ null                    │
            │ UW-004D                 │
            │ MKT005E                 │

            **Vector (List Shimming) Example: Removing 'TEMP-' prefix from temporary reference codes**

            >>> data_list = {
            ...     "case_id": ["C01", "C02"],
            ...     "ref_codes": [["TEMP-A1", "B2", "TEMP-C3"], [None, "TEMP-D4"]]
            ... }
            >>> af_list = ActuarialFrame(data_list).with_columns(
            ...     pl.col("ref_codes").cast(pl.List(pl.String))
            ... )
            >>> af_list_stripped = af_list.select(
            ...     af_list["ref_codes"].str.strip_prefix("TEMP-").alias("cleaned_codes")
            ... )
            >>> print(af_list_stripped.collect())
            shape: (2, 1)
            ┌────────────────────┐
            │ cleaned_codes      │
            │ ---                │
            │ list[str]          │
            ╞════════════════════╡
            │ ["A1", "B2", "C3"] │
            │ [null, "D4"]       │
            └────────────────────┘
        """
        return self._call_string_method("strip_chars_start", characters=characters)

    def strip_prefix(self, prefix: str | pl.Expr) -> "ExpressionProxy":
        """Remove a given prefix from each string.

        Mirrors Polars' `Expr.str.strip_prefix`.
        For `List[String]` columns, applies element-wise.

        Args:
            prefix: The prefix to remove from each string.
                        Can also be a Polars expression that evaluates to a string.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with the specified prefix removed.

        Examples:
            **Scalar Example: Removing 'TEMP-' prefix from temporary policy IDs**

            Cleans temporary policy IDs by removing the 'TEMP-' prefix.

            ```python
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl
            data_strip_prefix = {
                "temp_policy_id": ["TEMP-001", "TEMP-002", "003", None, "TEMP-004"]
            }
            af = ActuarialFrame(data_strip_prefix)
            af_stripped_prefix = af.select(
                af["temp_policy_id"].str.strip_prefix("TEMP-").alias("cleaned_policy_id")
            )
            print(af_stripped_prefix.collect())
            ```

            ```text
            shape: (5, 1)
            ┌─────────────────────┐
            │ cleaned_policy_id   │
            │ ---                 │
            │ str                 │
            ╞═════════════════════╡
            │ 001                 │
            │ 002                 │
            │ 003                 │
            │ null                │
            │ 004                 │
            └─────────────────────┘
            ```

            **Vector (List Shimming) Example: Removing 'TEMP-' prefix from temporary reference codes**

            >>> data_list = {
            ...     "case_id": ["C01", "C02"],
            ...     "ref_codes": [["TEMP-A1", "B2", "TEMP-C3"], [None, "TEMP-D4"]]
            ... }
            >>> af_list = ActuarialFrame(data_list).with_columns(
            ...     pl.col("ref_codes").cast(pl.List(pl.String))
            ... )
            >>> af_list_stripped = af_list.select(
            ...     af_list["ref_codes"].str.strip_prefix("TEMP-").alias("cleaned_codes")
            ... )
            >>> print(af_list_stripped.collect())
            shape: (2, 1)
            ┌────────────────────┐
            │ cleaned_codes      │
            │ ---                │
            │ list[str]          │
            ╞════════════════════╡
            │ ["A1", "B2", "C3"] │
            │ [null, "D4"]       │
            └────────────────────┘
        """
        return self._call_string_method("strip_prefix", prefix=prefix)

    def remove_prefix(self, prefix: str | pl.Expr) -> "ExpressionProxy":
        """Alias for `strip_prefix`. Remove a prefix from each string.

        Args:
            prefix: The prefix to remove.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with the prefix removed.
        """
        return self.strip_prefix(prefix=prefix)

    def strip_suffix(self, suffix: str | pl.Expr) -> "ExpressionProxy":
        """Remove a suffix from each string.

        Mirrors Polars' `Expr.str.strip_suffix`.
        If the string does not end with the suffix, it is returned unchanged.
        For `List[String]` columns, applies element-wise.

        Args:
            suffix: The suffix to remove. Can be a literal string or a Polars expression
                    that evaluates to a string.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with the suffix removed.

        Examples:
            **Scalar Example: Cleaning up trailing codes from product descriptions**

            >>> from gaspatchio_core.frame.base import ActuarialFrame
            >>> import polars as pl
            >>> data_strip_end = {
            ...     "description_raw": ["Term Life Plan - Basic", "Whole Life - OptA  ", "Annuity - TypeB*", None],
            ...     "codes_to_strip": ["- Basic", " OptA  ", "*", "XXX"]
            ... }
            >>> # Scalar Example Part 1: Strip specific trailing suffixes
            >>> af1_se = ActuarialFrame(data_strip_end)
            >>> af_stripped = af1_se.select(
            ...     af1_se["description_raw"].str.strip_chars_end(pl.col("codes_to_strip")).alias("base_description_attempt")
            ... )
            >>> print(af_stripped.collect())
            shape: (4, 1)
            ┌──────────────────────────┐
            │ base_description_attempt │
            │ ---                      │
            │ str                      │
            ╞══════════════════════════╡
            │ Term Life Plan           │
            │ Whole Life -             │
            │ Annuity - TypeB          │
            │ null                     │
            └──────────────────────────┘
            >>> # Scalar Example Part 2: Strip trailing whitespace only
            >>> af2_se = ActuarialFrame(data_strip_end) # Use a fresh frame instance
            >>> af_rstripped_ws = af2_se.select(
            ...     af2_se["description_raw"].str.strip_chars_end().alias("rstrip_whitespace")
            ... )
            >>> print(af_rstripped_ws.collect())
            shape: (4, 1)
            ┌────────────────────────┐
            │ rstrip_whitespace      │
            │ ---                    │
            │ str                    │
            ╞════════════════════════╡
            │ Term Life Plan - Basic │
            │ Whole Life - OptA      │
            │ Annuity - TypeB*       │
            │ null                   │
            └────────────────────────┘

            **Vector (List Shimming) Example: Removing trailing punctuation from agent notes**

            >>> # Set string length for more consistent doctest output
            >>> with pl.Config(fmt_str_lengths=100):
            ...     data_list_se = {
            ...         "agent_id": [101, 102],
            ...         "notes_list": [["Client interested!!", "Done."], [None, "Call back asap."]]
            ...     }
            ...     af_list_se = ActuarialFrame(data_list_se).with_columns(
            ...         pl.col("notes_list").cast(pl.List(pl.String))
            ...     )
            ...     af_list_stripped = af_list_se.select(
            ...         af_list_se["notes_list"].str.strip_chars_end(".! ").alias("cleaned_notes")
            ...     )
            ...     print(af_list_stripped.collect())
            shape: (2, 1)
            ┌───────────────────────────────┐
            │ cleaned_notes                 │
            │ ---                           │
            │ list[str]                     │
            ╞═══════════════════════════════╡
            │ ["Client interested", "Done"] │
            │ [null, "Call back asap"]      │
            └───────────────────────────────┘
        """
        return self._call_string_method("strip_suffix", suffix=suffix)

    def remove_suffix(self, suffix: str | pl.Expr) -> "ExpressionProxy":
        """Alias for `strip_suffix`. Remove a suffix from each string.

        Args:
            suffix: The suffix to remove.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with the suffix removed.
        """
        return self.strip_suffix(suffix=suffix)

    def zfill(self, length: int) -> "ExpressionProxy":
        """Pad the start of strings with zeros until the string reaches a certain length.

        Mirrors Polars' `Expr.str.zfill`.
        Strings that are already at least `length` characters long are unchanged.
        For `List[String]` columns, applies element-wise.

        Args:
            length: The desired minimum length of the string.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with strings padded with leading zeros.

        Examples:
            **Scalar Example: Standardizing policy serial numbers to a fixed length**
            >>> # Test with pl.Config to ensure consistent display
            >>> with pl.Config(fmt_str_lengths=100):
            ...     from gaspatchio_core.frame.base import ActuarialFrame
            ...     import polars as pl
            ...     data = {
            ...         "policy_serial": ["123", "45", "6789", None, "1"],
            ...     }
            ...     af = ActuarialFrame(data)
            ...     af_zfilled = af.select(
            ...         af["policy_serial"].str.zfill(5).alias("zfilled_serial")
            ...     )
            ...     print(af_zfilled.collect())
            shape: (5, 1)
            ┌────────────────┐
            │ zfilled_serial │
            │ ---            │
            │ str            │
            ╞════════════════╡
            │ 00123          │
            │ 00045          │
            │ 06789          │
            │ null           │
            │ 00001          │
            └────────────────┘

            **Vector (List Shimming) Example: Padding numerical components in claim codes**
            >>> with pl.Config(fmt_str_lengths=100):
            ...     data_list = {
            ...         "claim_batch": ["B01", "B02"],
            ...         "item_codes": [["A1", "B123", "C04"], [None, "D56"]]
            ...     }
            ...     af_list = ActuarialFrame(data_list).with_columns(
            ...         pl.col("item_codes").cast(pl.List(pl.String))
            ...     )
            ...     af_list_zfilled = af_list.select(
            ...         af_list["item_codes"].str.zfill(4).alias("zfilled_item_codes")
            ...     )
            ...     print(af_list_zfilled.collect())
            shape: (2, 1)
            ┌──────────────────────────┐
            │ zfilled_item_codes       │
            │ ---                      │
            │ list[str]                │
            ╞══════════════════════════╡
            │ ["00A1", "B123", "0C04"] │
            │ [null, "0D56"]           │
            └──────────────────────────┘
        """
        return self._call_string_method("zfill", length=length)

    def ljust(self, width: int, fill_char: str = " ") -> "ExpressionProxy":
        """Pad the end of strings with a specified character (left-aligns content).

        Mirrors Polars' `Expr.str.pad_end`.
        Strings that are already at least `width` characters long are unchanged.
        For `List[String]` columns, applies element-wise.

        Args:
            width: The desired total length of the string after padding.
            fill_char: The character to pad with. Defaults to a space.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with strings padded at the end.

        Examples:
            **Scalar Example: Formatting account codes to a fixed width**
            >>> # Test with pl.Config to ensure consistent display
            >>> with pl.Config(fmt_str_lengths=100):
            ...     from gaspatchio_core.frame.base import ActuarialFrame
            ...     import polars as pl
            ...     data = {
            ...         "account_code": ["A1", "B123", None, "C"],
            ...     }
            ...     af = ActuarialFrame(data)
            ...     af_ljust = af.select(
            ...         af["account_code"].str.ljust(6, "-").alias("ljust_code")
            ...     )
            ...     print(af_ljust.collect())
            shape: (4, 1)
            ┌────────────┐
            │ ljust_code │
            │ ---        │
            │ str        │
            ╞════════════╡
            │ A1----     │
            │ B123--     │
            │ null       │
            │ C-----     │
            └────────────┘

            **Vector (List Shimming) Example: Padding list elements**

            >>> with pl.Config(fmt_str_lengths=100):
            ...     data_list = {
            ...         "batch_id": ["X01"],
            ...         "sub_codes": [["S1", "LONGCODE", "S23"]]
            ...     }
            ...     af_list = ActuarialFrame(data_list).with_columns(
            ...         pl.col("sub_codes").cast(pl.List(pl.String))
            ...     )
            ...     af_list_ljust = af_list.select(
            ...         af_list["sub_codes"].str.ljust(8, "X").alias("ljust_sub_codes")
            ...     )
            ...     print(af_list_ljust.collect())
            shape: (1, 1)
            ┌──────────────────────────────────────┐
            │ ljust_sub_codes                      │
            │ ---                                  │
            │ list[str]                            │
            ╞══════════════════════════════════════╡
            │ ["S1XXXXXX", "LONGCODE", "S23XXXXX"] │
            └──────────────────────────────────────┘
        """
        return self._call_string_method("pad_end", length=width, fill_char=fill_char)

    def pad_start(self, width: int, fill_char: str = " ") -> "ExpressionProxy":
        """Alias for `rjust`. Pads the start of strings (right-aligns content).

        Args:
            width: The desired minimum length of the string.
            fill_char: The character to pad with. Defaults to a space.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with strings padded at the start.
        """
        return self.rjust(width=width, fill_char=fill_char)

    def rjust(self, width: int, fill_char: str = " ") -> "ExpressionProxy":
        """Pad the start of strings with a specified character (right-aligns content).

        Mirrors Polars' `Expr.str.pad_start`.
        Strings that are already at least `width` characters long are unchanged.
        For `List[String]` columns, applies element-wise.

        Args:
            width: The desired total length of the string after padding.
            fill_char: The character to pad with. Defaults to a space.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with strings padded at the start.

        Examples:
            **Scalar Example: Right-aligning numeric strings for reports**
            >>> # Test with pl.Config to ensure consistent display
            >>> with pl.Config(fmt_str_lengths=100):
            ...     from gaspatchio_core.frame.base import ActuarialFrame
            ...     import polars as pl
            ...     data = {
            ...         "amount_str": ["12.3", "1234.56", None, "7"],
            ...     }
            ...     af = ActuarialFrame(data)
            ...     af_rjust = af.select(
            ...         af["amount_str"].str.rjust(10, " ").alias("rjust_amount")
            ...     )
            ...     print(af_rjust.collect())
            shape: (4, 1)
            ┌──────────────┐
            │ rjust_amount │
            │ ---          │
            │ str          │
            ╞══════════════╡
            │       12.3   │
            │    1234.56   │
            │ null         │
            │          7   │
            └──────────────┘

            **Vector (List Shimming) Example: Right-padding list elements**
            >>> with pl.Config(fmt_str_lengths=100):
            ...     data_list = {
            ...         "batch_id": ["Y01"],
            ...         "item_ids": [["ID1", "SHORT", "ID12345"]]
            ...     }
            ...     af_list = ActuarialFrame(data_list).with_columns(
            ...         pl.col("item_ids").cast(pl.List(pl.String))
            ...     )
            ...     af_list_rjust = af_list.select(
            ...         af_list["item_ids"].str.rjust(10, "0").alias("rjust_item_ids")
            ...     )
            ...     print(af_list_rjust.collect())
            shape: (1, 1)
            ┌────────────────────────────────────────────┐
            │ rjust_item_ids                             │
            │ ---                                        │
            │ list[str]                                  │
            ╞════════════════════════════════════════════╡
            │ ["0000000ID1", "00000SHORT", "000ID12345"] │
            └────────────────────────────────────────────┘
        """
        return self._call_string_method("pad_start", length=width, fill_char=fill_char)

    def pad_end(self, width: int, fill_char: str = " ") -> "ExpressionProxy":
        """Alias for `ljust`. Pads the end of strings (left-aligns content).

        Args:
            width: The desired total length of the string after padding.
            fill_char: The character to pad with. Defaults to a space.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with strings padded at the end.
        """
        return self.ljust(width=width, fill_char=fill_char)

    def starts_with(self, prefix: str | pl.Expr) -> "ExpressionProxy":
        """Check if strings start with a given substring.

        Mirrors Polars' `Expr.str.starts_with`.
        For `List[String]` columns, applies element-wise.

        Args:
            prefix: The substring to check for at the beginning of each string.
                    Can be a literal string or a Polars expression.

        Returns:
            ExpressionProxy: A boolean `ExpressionProxy` indicating if strings start with the prefix.

        Examples:
            **Scalar Example: Identifying policies by type prefix**

            >>> from gaspatchio_core.frame.base import ActuarialFrame
            >>> import polars as pl
            >>> data_strip_prefix = {
            ...     "uw_id_full": ["UW-1001", "UW-1002", "ACT-1003", None, "UW-1004"],
            ...     "prefix_to_remove": ["UW-", "UW-", "UW-", "UW-", "ACT-"]
            ... }
            >>> # Scalar Example Part 1: Remove fixed prefix
            >>> af1_sp = ActuarialFrame(data_strip_prefix)
            >>> af_stripped_fixed = af1_sp.select(
            ...     af1_sp["uw_id_full"].str.strip_prefix("UW-").alias("id_no_fixed_prefix")
            ... )
            >>> print(af_stripped_fixed.collect())
            shape: (5, 1)
            ┌────────────────────┐
            │ id_no_fixed_prefix │
            │ ---                │
            │ str                │
            ╞════════════════════╡
            │ 1001               │
            │ 1002               │
            │ ACT-1003           │
            │ null               │
            │ 1004               │
            └────────────────────┘
            >>> # Scalar Example Part 2: Remove prefix based on another column
            >>> af2_sp = ActuarialFrame(data_strip_prefix) # Use a fresh frame instance
            >>> af_stripped_dynamic = af2_sp.select(
            ...     af2_sp["uw_id_full"].str.strip_prefix(pl.col("prefix_to_remove")).alias("id_no_dynamic_prefix")
            ... )
            >>> print(af_stripped_dynamic.collect())
            shape: (5, 1)
            ┌──────────────────────┐
            │ id_no_dynamic_prefix │
            │ ---                  │
            │ str                  │
            ╞══════════════════════╡
            │ 1001                 │
            │ 1002                 │
            │ ACT-1003             │
            │ null                 │
            │ UW-1004              │
            └──────────────────────┘

            **Vector (List Shimming) Example: Checking prefixes in lists of rider codes**

            >>> with pl.Config(fmt_str_lengths=120, tbl_width_chars=100): # Added Config
            ...     data_list = {
            ...         "policy_id": ["P77", "P88"],
            ...         "rider_codes": [["R-ADB", "R-WP", "CI"], [None, "R-LTC", "R-GIO"]]
            ...     }
            ...     af_list = ActuarialFrame(data_list).with_columns(
            ...         pl.col("rider_codes").cast(pl.List(pl.String))
            ...     )
            ...     af_list_check = af_list.select(
            ...         af_list["rider_codes"].str.starts_with("R-").alias("is_standard_rider")
            ...     )
            ...     print(af_list_check.collect())
            shape: (2, 1)
            ┌─────────────────────┐
            │ is_standard_rider   │
            │ ---                 │
            │ list[bool]          │
            ╞═════════════════════╡
            │ [true, true, false] │
            │ [null, true, true]  │
            └─────────────────────┘
        """
        return self._call_string_method("starts_with", prefix=prefix)

    def ends_with(self, suffix: str | pl.Expr) -> "ExpressionProxy":
        """Check if strings end with a given substring.

        Mirrors Polars' `Expr.str.ends_with`.
        For `List[String]` columns, applies element-wise.

        Args:
            suffix: The substring to check for at the end of each string.
                    Can be a literal string or a Polars expression.

        Returns:
            ExpressionProxy: A boolean `ExpressionProxy` indicating if strings end with the suffix.

        Examples:
            **Scalar Example: Identifying policies by region suffix**

            >>> from gaspatchio_core.frame.base import ActuarialFrame
            >>> import polars as pl
            >>> data = {
            ...     "policy_id": ["P100-US", "P101-CA", "P102-US", None, "P103-EU"],
            ...     "check_suffix": ["-US", "-US", "-CA", "-EU", "-EU"]
            ... }
            >>> # Scalar Example Part 1: Remove fixed suffix "-US"
            >>> af_is_us_frame = ActuarialFrame(data)
            >>> af_is_us = af_is_us_frame.select(
            ...     af_is_us_frame["policy_id"].str.ends_with("-US").alias("is_us_policy")
            ... )
            >>> print(af_is_us.collect())
            shape: (5, 1)
            ┌──────────────┐
            │ is_us_policy │
            │ ---          │
            │ bool         │
            ╞══════════════╡
            │ true         │
            │ false        │
            │ true         │
            │ null         │
            │ false        │
            └──────────────┘
            >>> # Check for suffix from another column
            >>> af_is_us_data_for_dynamic = { # Renamed to avoid conflict and ensure self-containment
            ...     "policy_id": ["P100-US", "P101-CA", "P102-US", None, "P103-EU"],
            ...     "check_suffix": ["-US", "-US", "-CA", "-EU", "-EU"]
            ... }
            >>> af_dynamic_suffix_frame = ActuarialFrame(af_is_us_data_for_dynamic)
            >>> af_dynamic_suffix = af_dynamic_suffix_frame.select(
            ...     af_dynamic_suffix_frame["policy_id"].str.ends_with(pl.col("check_suffix")).alias("ends_dynamic_suffix")
            ... )
            >>> print(af_dynamic_suffix.collect())
            shape: (5, 1)
            ┌─────────────────────┐
            │ ends_dynamic_suffix │
            │ ---                 │
            │ bool                │
            ╞═════════════════════╡
            │ true                │
            │ false               │
            │ false               │
            │ null                │
            │ true                │
            └─────────────────────┘

            **Vector (List Shimming) Example: Checking for status suffixes in comments**

            >>> with pl.Config(fmt_str_lengths=100):
            ...     data_list = {
            ...         "item_id": ["I01", "I02"],
            ...         "log_entries": [["Transaction OK", "Review PENDING"], [None, "Approved:FINAL"]]
            ...     }
            ...     af_list = ActuarialFrame(data_list).with_columns(
            ...         pl.col("log_entries").cast(pl.List(pl.String))
            ...     )
            ...     af_list_check = af_list.select(
            ...         af_list["log_entries"].str.ends_with("OK").alias("is_status_ok")
            ...     )
            ...     print(af_list_check.collect())
            shape: (2, 1)
            ┌───────────────┐
            │ is_status_ok  │
            │ ---           │
            │ list[bool]    │
            ╞═══════════════╡
            │ [true, false] │
            │ [null, false] │
            └───────────────┘
        """
        return self._call_string_method("ends_with", suffix=suffix)

    def __getattr__(self, name: str) -> Callable[..., "ExpressionProxy"]:
        """Dynamically handle calls to Polars string methods not explicitly defined.

        This allows the proxy to support any method available on Polars' str namespace
        without needing to define each one explicitly on this proxy class.

        Args:
            name: The name of the string method to call.

        Returns:
            A callable that, when invoked, will execute the corresponding Polars
            string method via `_call_string_method`.

        Raises:
            AttributeError: If the method does not exist on the Polars string namespace
                            (this is typically raised by `_call_string_method`), or if
                            a dunder method (e.g. `__repr__`) is accessed that isn't defined.
        """
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}'"
            )

        def dynamic_method_caller(*args: Any, **kwargs: Any) -> "ExpressionProxy":
            return self._call_string_method(name, *args, **kwargs)

        return dynamic_method_caller

    # --- New methods to be added ---

    def strptime(
        self,
        dtype: "PolarsTemporalType",
        format: Optional[str] = None,
        *,
        strict: bool = True,
        exact: bool = True,
        cache: bool = True,
        ambiguous: str | pl.Expr = "raise",
        **kwargs: Any,  # Capture additional kwargs like time_unit, time_zone
    ) -> "ExpressionProxy":
        """Convert string values to Date, Datetime, or Time.

        Mirrors Polars' `Expr.str.strptime`.
        For `List[String]` columns, applies element-wise.

        Args:
            dtype: The Polars temporal type to convert to (pl.Date, pl.Datetime, or pl.Time).
            format: The strf/strptime format string. If None, attempts to infer.
                    See `chrono crate documentation` for format specifiers.
            strict: If True (default), raise an error on parsing failure.
            exact: If True (default), require an exact format match.
            cache: If True (default), cache parsing results for performance.
            ambiguous: How to handle ambiguous datetimes (e.g., due to DST transitions).
                       Can be 'raise' (default), 'earliest', 'latest', or 'null'.
                       Can also be a Polars expression.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with strings converted to the specified temporal type.

        Examples:
            **Scalar Example: Parsing policy issue dates**

            >>> from gaspatchio_core.frame.base import ActuarialFrame
            >>> import polars as pl
            >>> data = {
            ...     "policy_id": ["A100", "B200", "C300"],
            ...     "issue_date_str": ["2021-01-15", "20/02/2022", "2023-03-10 14:30:00"] # Restored input
            ... }
            >>> af = ActuarialFrame(data)
            >>> af_parsed_dates = af.select(
            ...     af["issue_date_str"].str.strptime(pl.Date, "%Y-%m-%d", strict=False).alias("issue_date_strict_fmt"),
            ...     af["issue_date_str"].str.strptime(pl.Date, "%d/%m/%Y", strict=False).alias("issue_date_dmy_fmt"),
            ...     af["issue_date_str"].str.strptime(pl.Datetime, "%Y-%m-%d %H:%M:%S", strict=False).alias("issue_datetime")
            ... )
            >>> with pl.Config(fmt_str_lengths=120, tbl_width_chars=100):
            ...     print(af_parsed_dates.collect()) # doctest: +NORMALIZE_WHITESPACE
            shape: (3, 3)
            ┌───────────────────────┬────────────────────┬─────────────────────┐
            │ issue_date_strict_fmt ┆ issue_date_dmy_fmt ┆ issue_datetime      │
            │ ---                   ┆ ---                ┆ ---                 │
            │ date                  ┆ date               ┆ datetime[μs]        │
            ╞═══════════════════════╪════════════════════╪═════════════════════╡
            │ 2021-01-15            ┆ null               ┆ null                │
            │ null                  ┆ 2022-02-20         ┆ null                │
            │ null                  ┆ null               ┆ 2023-03-10 14:30:00 │
            └───────────────────────┴────────────────────┴─────────────────────┘

            **Vector (List Shimming) Example: Parsing lists of event timestamps**

            >>> data_list = {
            ...     "claim_id": ["CL001"],
            ...     "event_timestamps_str": [["2023-04-01T10:00:00", "2023-04-01T10:05:00", "Invalid"]]
            ... }
            >>> af_list = ActuarialFrame(data_list).with_columns(
            ...     pl.col("event_timestamps_str").cast(pl.List(pl.String))
            ... )
            >>> af_parsed_list = af_list.select(
            ...     af_list["event_timestamps_str"].str.strptime(
            ...         pl.Datetime, "%Y-%m-%dT%H:%M:%S", strict=False
            ...     ).alias("event_datetimes_μs")
            ... )
            >>> result = af_parsed_list.collect()
            >>> with pl.Config(fmt_str_lengths=120, tbl_width_chars=100):
            ...     print(result) # doctest: +NORMALIZE_WHITESPACE
            shape: (1, 1)
            ┌──────────────────────────────────────────────────┐
            │ event_datetimes_μs                               │
            │ ---                                              │
            │ list[datetime[μs]]                               │
            ╞══════════════════════════════════════════════════╡
            │ [2023-04-01 10:00:00, 2023-04-01 10:05:00, null] │
            └──────────────────────────────────────────────────┘
        """
        from ..dispatch import _ensure_polars_expr_or_literal

        ambiguous_arg = _ensure_polars_expr_or_literal(ambiguous)

        # Correctly prepare kwargs for Polars' strptime, which does not take time_unit/time_zone directly
        kwargs_for_polars_strptime = {
            "dtype": dtype,
            "format": format,
            "strict": strict,
            "exact": exact,
            "cache": cache,
            "ambiguous": ambiguous_arg,
        }

        # Do NOT pass time_unit/time_zone from self.strptime's **kwargs to polars.strptime
        # polars.strptime internally calls to_datetime which handles those if passed from there.
        # Our proxy should only pass what polars.strptime itself accepts.

        return self._call_string_method("strptime", **kwargs_for_polars_strptime)

    def extract(self, pattern: str, group_index: int = 1) -> "ExpressionProxy":
        """Extract a capturing group from a regex pattern.

        Mirrors Polars' `Expr.str.extract`.
        For `List[String]` columns, applies element-wise.

        Args:
            pattern: The regex pattern with capturing groups.
            group_index: The 1-based index of the group to extract.

        Returns:
            ExpressionProxy: An `ExpressionProxy` containing the extracted group.

        Examples:
            **Scalar Example: Extracting policy numbers from combined IDs**

            >>> from gaspatchio_core.frame.base import ActuarialFrame
            >>> data = {
            ...     "full_id": ["POLICY-12345-AB", "CLAIM-67890-CD", "POLICY-ABCDE-FG"],
            ... }
            >>> af = ActuarialFrame(data)
            >>> af_extracted = af.select(
            ...     af["full_id"].str.extract(r"POLICY-(\\w+)-.*", group_index=1).alias("policy_num")
            ... )
            >>> print(af_extracted.collect())
            shape: (3, 1)
            ┌────────────┐
            │ policy_num │
            │ ---        │
            │ str        │
            ╞════════════╡
            │ 12345      │
            │ null       │
            │ ABCDE      │
            └────────────┘

            **Vector (List Shimming) Example: Extracting amounts from transaction descriptions**

            >>> data_list = {
            ...     "policy_id": ["P001"],
            ...     "transactions": [["Premium paid: $100.50", "Fee: $10.00", "Adjustment: $-5.25"]]
            ... }
            >>> af_list = ActuarialFrame(data_list).with_columns(
            ...     pl.col("transactions").cast(pl.List(pl.String))
            ... )
            >>> af_list_extracted = af_list.select(
            ...     af_list["transactions"].str.extract(r"\\$?([-+]?\\d+\\.\\d{2})", group_index=1).alias("amounts_str")
            ... )
            >>> with pl.Config(fmt_str_lengths=120, tbl_width_chars=100):
            ...     print(af_list_extracted.collect()) # doctest: +NORMALIZE_WHITESPACE
            shape: (1, 1)
            ┌──────────────────────────────┐
            │ amounts_str                  │
            │ ---                          │
            │ list[str]                    │
            ╞══════════════════════════════╡
            │ ["100.50", "10.00", "-5.25"] │
            └──────────────────────────────┘
        """
        return self._call_string_method(
            "extract", pattern=pattern, group_index=group_index
        )

    def extract_all(self, pattern: str) -> "ExpressionProxy":
        """Extract all occurrences of a regex pattern.

        Mirrors Polars' `Expr.str.extract_all`.
        Returns a list of strings for each input string.
        For `List[String]` columns, this means it will produce a `List[List[String]]`.

        Args:
            pattern: The regex pattern to extract.

        Returns:
            ExpressionProxy: An `ExpressionProxy` of type `List[String]`.

        Examples:
            **Scalar Example: Extracting all rider codes from a description string**

            >>> from gaspatchio_core.frame.base import ActuarialFrame
            >>> data = {
            ...     "policy_desc": ["Policy with riders ADB, WP, CI.", "Base policy only.", "Riders: LTC, GIO.", None]
            ... }
            >>> af = ActuarialFrame(data)
            >>> af_extracted = af.select(
            ...     af["policy_desc"].str.extract_all(r"([A-Z]{2,3})").alias("rider_codes_extracted")
            ... )
            >>> print(af_extracted.collect()) # doctest: +NORMALIZE_WHITESPACE
            shape: (4, 1)
            ┌───────────────────────┐
            │ rider_codes_extracted │
            │ ---                   │
            │ list[str]             │
            ╞═══════════════════════╡
            │ ["ADB", "WP", "CI\"]   │
            │ []                    │
            │ ["LTC", "GIO\"]        │
            │ null                  │
            └───────────────────────┘

            **Vector (List Shimming) Example: Extracting tags from lists of notes**

            >>> data_list = {
            ...     "record_id": ["R1"],
            ...     "note_entries": [["Call #urgent, Follow-up #important", "Meeting #Q1, Review #pending"]]
            ... }
            >>> af_list = ActuarialFrame(data_list).with_columns(
            ...     pl.col("note_entries").cast(pl.List(pl.String))
            ... )
            >>> # This will result in List[List[String]] due to shimming extract_all
            >>> af_list_extracted = af_list.select(
            ...     af_list["note_entries"].str.extract_all(r"#\w+").alias("all_tags_per_note")
            ... )
            >>> with pl.Config(fmt_str_lengths=120, tbl_width_chars=100):
            ...     print(af_list_extracted.collect()) # doctest: +NORMALIZE_WHITESPACE
            shape: (1, 1)
            ┌──────────────────────────────────────────────────┐
            │ all_tags_per_note                                │
            │ ---                                              │
            │ list[list[str]]                                  │
            ╞══════════════════════════════════════════════════╡
            │ [["#urgent", "#important"], ["#Q1", "#pending"]] │
            └──────────────────────────────────────────────────┘
        """
        return self._call_string_method("extract_all", pattern=pattern)

    def replace(
        self,
        pattern: str | pl.Expr,
        value: str | pl.Expr,
        literal: bool = False,
        n: int = 1,
    ) -> "ExpressionProxy":
        """Replace occurrences of a regex pattern with a replacement string.

        Mirrors Polars' `Expr.str.replace`.
        For `List[String]` columns, applies element-wise.

        Args:
            pattern: Regex pattern or literal string to search for.
            value: String or expression to replace with.
            literal: Treat `pattern` as a literal if True. Default is False (regex).
            n: Maximum number of replacements to make. Default is 1. Use -1 for all.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with strings after replacement.

        Examples:
            **Scalar Example: Standardizing state abbreviations**

            >>> from gaspatchio_core.frame.base import ActuarialFrame
            >>> import polars as pl
            >>> data = {
            ...     "address_line": ["PO Box 123, New York, N.Y.", "1 Main St, Calif.", "Suite 5, Florida"],
            ... }
            >>> af = ActuarialFrame(data)
            >>> af_replaced = af.select(
            ...     af["address_line"].str.replace(r"N\.Y\.", "NY", n=-1).alias("std_address_1"),
            ... )
            >>> af_replaced = af_replaced.with_columns( # Apply second replace in a new step for clarity in doctest
            ...     pl.col("std_address_1").str.replace(r"Calif\.", "CA", n=-1).alias("std_address_2")
            ... )
            >>> with pl.Config(fmt_str_lengths=120, tbl_width_chars=100):
            ...     print(af_replaced.collect().select("std_address_2")) # doctest: +NORMALIZE_WHITESPACE
            shape: (3, 1)
            ┌──────────────────────────┐
            │ std_address_2            │
            │ ---                      │
            │ str                      │
            ╞══════════════════════════╡
            │ PO Box 123, New York, NY │
            │ 1 Main St, CA            │
            │ Suite 5, Florida         │
            └──────────────────────────┘

            **Vector (List Shimming) Example: Masking PII in lists of comments**

            >>> data_list = {
            ...     "case_id": ["C001"],
            ...     "comments": [["Client phone: 555-1234", "Email: test@example.com", "DOB: 01/01/1990"]]
            ... }
            >>> af_list = ActuarialFrame(data_list).with_columns(
            ...     pl.col("comments").cast(pl.List(pl.String))
            ... )
            >>> # Break down chained replace for doctest stability and to avoid shimming issues with chained calls
            >>> temp_af = af_list.select( # Corrected: Ensure select() is properly closed
            ...     af_list["comments"].str.replace(r"\d{3}-\d{4}", "[PHONE]", n=-1).alias("temp_masked")
            ... )
            >>> af_list_masked = temp_af.select( # Second replace on the result of the first
            ...     temp_af["temp_masked"].str.replace(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "[EMAIL]", n=-1).alias("masked_comments")
            ... )
            >>> with pl.Config(fmt_str_lengths=120, tbl_width_chars=100):
            ...     print(af_list_masked.collect().select("masked_comments")) # doctest: +NORMALIZE_WHITESPACE
            shape: (1, 1)
            ┌────────────────────────────────────────────────────────────────┐
            │ masked_comments                                                │
            │ ---                                                            │
            │ list[str]                                                      │
            ╞════════════════════════════════════════════════════════════════╡
            │ ["Client phone: [PHONE]", "Email: [EMAIL]", "DOB: 01/01/1990"] │
            └────────────────────────────────────────────────────────────────┘
        """
        return self._call_string_method(
            "replace", pattern=pattern, value=value, literal=literal, n=n
        )

    def replace_all(
        self, pattern: str | pl.Expr, value: str | pl.Expr, literal: bool = False
    ) -> "ExpressionProxy":
        """Replace all occurrences of a regex pattern with a replacement string.

        This is a convenience method for `replace` with `n=-1`.
        Mirrors Polars' `Expr.str.replace_all`.
        For `List[String]` columns, applies element-wise.

        Args:
            pattern: Regex pattern or literal string to search for.
            value: String or expression to replace with.
            literal: Treat `pattern` as a literal if True. Default is False (regex).

        Returns:
            ExpressionProxy: An `ExpressionProxy` with strings after replacement.

        Examples:
            **Scalar Example: Replacing all instances of 'Temp' with 'Temporary'**

            >>> from gaspatchio_core.frame.base import ActuarialFrame
            >>> data = {"status_desc": ["Temp Status", "Another Temp Note", "Permanent"]}
            >>> af = ActuarialFrame(data)
            >>> af_replaced = af.select(
            ...     af["status_desc"].str.replace_all("Temp", "Temporary").alias("full_status_desc")
            ... )
            >>> with pl.Config(fmt_str_lengths=120, tbl_width_chars=100):
            ...    print(af_replaced.collect()) # doctest: +NORMALIZE_WHITESPACE
            shape: (3, 1)
            ┌────────────────────────┐
            │ full_status_desc       │
            │ ---                    │
            │ str                    │
            ╞════════════════════════╡
            │ Temporary Status       │
            │ Another Temporary Note │
            │ Permanent              │
            └────────────────────────┘

            **Vector (List Shimming) Example: Normalizing currency symbols in lists**

            >>> data_list = {
            ...     "policy_id": ["P001"],
            ...     "premium_notes": [["Amt: $100", "Fee: USD 20", "Total: CAD 50"]]
            ... }
            >>> af_list = ActuarialFrame(data_list).with_columns(
            ...     pl.col("premium_notes").cast(pl.List(pl.String))
            ... )
            >>> af_list_norm = af_list.select(
            ...     af_list["premium_notes"].str.replace_all(r"\$|USD|CAD", "CUR", literal=False).alias("normalized_currency")
            ... )
            >>> with pl.Config(fmt_str_lengths=120, tbl_width_chars=100):
            ...    print(af_list_norm.collect()) # doctest: +NORMALIZE_WHITESPACE
            shape: (1, 1)
            ┌─────────────────────────────────────────────────┐
            │ normalized_currency                             │
            │ ---                                             │
            │ list[str]                                       │
            ╞═════════════════════════════════════════════════╡
            │ ["Amt: CUR100", "Fee: CUR 20", "Total: CUR 50"] │
            └─────────────────────────────────────────────────┘
        """
        return self._call_string_method(
            "replace_all", pattern=pattern, value=value, literal=literal
        )

    def split(self, by: str | pl.Expr, inclusive: bool = False) -> "ExpressionProxy":
        """Split strings by a delimiter.

        Mirrors Polars' `Expr.str.split`. Returns a `List[String]`.
        For `List[String]` columns, this means it will produce a `List[List[String]]`.

        Args:
            by: The delimiter to split by (string or expression).
            inclusive: If True, include the delimiter in the result. Default is False.

        Returns:
            ExpressionProxy: An `ExpressionProxy` of type `List[String]`.

        Examples:
            **Scalar Example: Splitting policyholder names into parts**

            >>> from gaspatchio_core.frame.base import ActuarialFrame
            >>> data = {"full_name": ["Doe, John A.", "Smith, Jane B.", None, "O'Malley, Pat"]}
            >>> af = ActuarialFrame(data)
            >>> af_split = af.select(
            ...     af["full_name"].str.split(by=", ").alias("name_parts")
            ... )
            >>> with pl.Config(fmt_str_lengths=120, tbl_width_chars=100): # Added Config
            ...     print(af_split.collect()) # doctest: +NORMALIZE_WHITESPACE
            shape: (4, 1)
            ┌──────────────────────┐
            │ name_parts           │
            │ ---                  │
            │ list[str]            │
            ╞══════════════════════╡
            │ ["Doe", "John A."]   │
            │ ["Smith", "Jane B."] │
            │ null                 │
            │ ["O'Malley", "Pat"]  │
            └──────────────────────┘

            **Vector (List Shimming) Example: Splitting lists of comma-separated tags**

            >>> data_list = {
            ...     "policy_id": ["POL1"],
            ...     "tag_strings": [["urgent,high-value", "internal,review-needed", None]]
            ... }
            >>> af_list = ActuarialFrame(data_list).with_columns(
            ...     pl.col("tag_strings").cast(pl.List(pl.String))
            ... )
            >>> af_list_split = af_list.select(
            ...     af_list["tag_strings"].str.split(by=",").alias("tags_split_list")
            ... )
            >>> with pl.Config(fmt_str_lengths=120, tbl_width_chars=100): # Added Config
            ...    print(af_list_split.collect()) # doctest: +NORMALIZE_WHITESPACE
            shape: (1, 1)
            ┌─────────────────────────────────────────────────────────────────┐
            │ tags_split_list                                                 │
            │ ---                                                             │
            │ list[list[str]]                                                 │
            ╞═════════════════════════════════════════════════════════════════╡
            │ [["urgent", "high-value"], ["internal", "review-needed"], null] │
            └─────────────────────────────────────────────────────────────────┘
        """
        return self._call_string_method("split", by=by, inclusive=inclusive)

    def slice(
        self, offset: int | pl.Expr, length: Optional[int | pl.Expr] = None
    ) -> "ExpressionProxy":
        """Slice substrings from strings.

        Mirrors Polars' `Expr.str.slice`.
        For `List[String]` columns, applies element-wise.

        Args:
            offset: Start of the slice (0-indexed). Negative values count from the end.
                    Can be an integer or a Polars expression.
            length: Optional length of the slice. If None, slices to the end of the string.
                    Can be an integer or a Polars expression.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with the sliced substrings.

        Examples:
            **Scalar Example: Extracting year from YYYY-MM-DD date strings**

            >>> from gaspatchio_core.frame.base import ActuarialFrame
            >>> data = {"date_str": ["2023-10-26", "2024-01-15", None]}
            >>> af = ActuarialFrame(data)
            >>> af_sliced = af.select(
            ...     af["date_str"].str.slice(offset=0, length=4).alias("year"),
            ...     af["date_str"].str.slice(offset=-2).alias("day") # Last 2 characters
            ... )
            >>> with pl.Config(fmt_str_lengths=120, tbl_width_chars=100): # Added Config
            ...     print(af_sliced.collect()) # doctest: +NORMALIZE_WHITESPACE
            shape: (3, 2)
            ┌──────┬──────┐
            │ year ┆ day  │
            │ ---  ┆ ---  │
            │ str  ┆ str  │
            ╞══════╪══════╡
            │ 2023 ┆ 26   │
            │ 2024 ┆ 15   │
            │ null ┆ null │
            └──────┴──────┘

            **Vector (List Shimming) Example: Getting initials from lists of names**

            >>> data_list = {
            ...     "policy_id": ["P007"],
            ...     "agent_names": [["John Doe", "Alice Wonderland", None, "Bob"]]
            ... }
            >>> af_list = ActuarialFrame(data_list).with_columns(
            ...     pl.col("agent_names").cast(pl.List(pl.String))
            ... )
            >>> af_list_sliced = af_list.select(
            ...     af_list["agent_names"].str.slice(offset=0, length=1).alias("first_initials")
            ... )
            >>> af_list_sliced_result = af_list_sliced.collect() # Collect first
            >>> print(af_list_sliced_result["first_initials"].to_list()) # Print as Python list
            [['J', 'A', None, 'B']]
        """
        return self._call_string_method("slice", offset=offset, length=length)
