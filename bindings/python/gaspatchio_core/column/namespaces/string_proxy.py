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

        data_for_class_doctest = { # Renamed to avoid conflict with other examples
            "policy_holder_name": ["John Doe", "Jane Smith", "Robert Jones"],
            "policy_type_codes": [["TERM", "WL"], ["UL"], ["TERM", "CI"]]
        }
        af_scalar = ActuarialFrame(data_for_class_doctest)
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

            ```
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

            ```
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

            ```
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

            ```
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
        """Converts all characters in strings to uppercase.

        This is useful for standardizing text data, such as policy status codes,
        product codes, or any textual field where case consistency is important
        for matching or aggregation. It mirrors Polars' `Expr.str.to_uppercase`.
        For `List[String]` columns, such as a list of rider codes attached to a
        policy, the operation is applied element-wise to each string in the list.

        Returns:
            ExpressionProxy: A new `ExpressionProxy` with strings converted to uppercase.

        Examples:
            **Scalar Example: Standardizing policy status codes**

            Policy status might be entered in various cases ("active", "Lapsed", "ACTIVE").
            Converting to uppercase ensures consistency for analysis.

            ```
            from gaspatchio_core.frame.base import ActuarialFrame

            data = {
                "policy_id": ["S3001", "S3002", "S3003", "S3004"],
                "status_raw": ["active", "lapsed", "Active", "PENDING"]
            }
            af = ActuarialFrame(data)
            af_upper_status = af.select(
                af["status_raw"].str.to_uppercase().alias("status_standardized")
            )
            print(af_upper_status.collect())
            ```

            ```
            shape: (4, 1)
            ┌─────────────────────┐
            │ status_standardized │
            │ ---                 │
            │ str                 │
            ╞═════════════════════╡
            │ ACTIVE              │
            │ LAPSED              │
            │ ACTIVE              │
            │ PENDING             │
            └─────────────────────┘
            ```

            **Vector (List Shimming) Example: Uppercasing rider codes for a policy**

            A policy might have multiple rider codes stored in a list. To ensure
            uniformity, we can convert all rider codes to uppercase.

            ```
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl

            data_policy_riders = {
                "policy_id": ["R4001", "R4002", "R4003"],
                "rider_codes_list": [
                    ["adb", "wp"],
                    ["ci", None, "ltc", "acc_death"],
                    ["gio"]
                ]
            }
            af_riders = ActuarialFrame(data_policy_riders).with_columns(
                pl.col("rider_codes_list").cast(pl.List(pl.String))
            )
            af_upper_riders = af_riders.select(
                af_riders["rider_codes_list"].str.to_uppercase().alias("upper_rider_codes")
            )
            print(af_upper_riders.collect())
            ```

            ```text
            shape: (3, 1)
            ┌───────────────────────────┐
            │ upper_rider_codes         │
            │ ---                       │
            │ list[str]                 │
            ╞═══════════════════════════╡
            │ ["ADB", "WP"]             │
            │ ["CI", null, … "ACC_DEATH"] │
            │ ["GIO"]                   │
            └───────────────────────────┘
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

            ```
            from gaspatchio_core.frame.base import ActuarialFrame

            data = {
                "client_id": [101, 102, 103],
                "email_domain": ["Example.COM", "Test.Org", "Sample.NET"]
            }
            af = ActuarialFrame(data)
            af_lower_domain = af.select(
                af["email_domain"].str.to_lowercase().alias("lower_domain")
            )
            print(af_lower_domain.collect())
            ```

            ```
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
            ```

            **Vector (List Shimming) Example: Lowercasing product feature tags**

            ```
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl

            data_list = {
                "product_id": ["P501", "P502"],
                "feature_tags": [["GUARANTEED_ISSUE", "Online"], ["FLEXIBLE_PREMIUM", "RIDER_Available"]]
            }
            af_list = ActuarialFrame(data_list).with_columns(
                pl.col("feature_tags").cast(pl.List(pl.String))
            )
            af_lower_tags = af_list.select(
                af_list["feature_tags"].str.to_lowercase().alias("lower_feature_tags")
            )
            print(af_lower_tags.collect())
            ```

            ```
            shape: (2, 1)
            ┌─────────────────────────────────────────┐
            │ lower_feature_tags                      │
            │ ---                                     │
            │ list[str]                               │
            ╞═════════════════════════════════════════╡
            │ ["guaranteed_issue", "online"]          │
            │ ["flexible_premium", "rider_available"] │
            └─────────────────────────────────────────┘
            ```
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

            ```
            from gaspatchio_core.frame.base import ActuarialFrame

            data = {
                "product_code": ["L-TERM-10", "L-WL-P", "ANN-SDA"],
                "product_name": ["Term Life 10 Year", "Whole Life Par", "Single Deferred Annuity"]
            }
            af = ActuarialFrame(data)
            af_len = af.select(
                af["product_name"].str.n_chars().alias("name_length")
            )
            print(af_len.collect())
            ```

            ```
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
            ```

            **Vector (List Shimming) Example: Length of beneficiary names in a list**

            ```
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl

            data_list = {
                "policy_id": ["P001", "P002"],
                "beneficiaries": [["John A. Doe", "Jane B. Smith"], ["Robert King", None, "Alice Wonderland"]]
            }
            af_list = ActuarialFrame(data_list).with_columns(
                pl.col("beneficiaries").cast(pl.List(pl.String))
            )
            af_bene_len = af_list.select(
                af_list["beneficiaries"].str.n_chars().alias("beneficiary_name_lengths")
            )
            print(af_bene_len.collect())
            ```

            ```
            shape: (2, 1)
            ┌──────────────────────────┐
            │ beneficiary_name_lengths │
            │ ---                      │
            │ list[u32]                │
            ╞══════════════════════════╡
            │ [11, 13]                 │
            │ [11, null, 16]           │
            └──────────────────────────┘
            ```
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
            ```
            from gaspatchio_core.frame.base import ActuarialFrame
            af = ActuarialFrame({"city_names": ["New York", "Los Angeles", None, "Chicago"]})
            result = af.select(af["city_names"].str.len_chars().alias("char_count"))
            print(result.collect())
            ```

            ```
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
            ```
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

            ```
            from gaspatchio_core.frame.base import ActuarialFrame

            data = {
                "client_id": ["C001", "C002", "C003"],
                "client_name": ["René", "沐宸", "Zoë"]
            }
            af = ActuarialFrame(data)
            af_len = af.select(
                af["client_name"].str.len_bytes().alias("name_byte_length")
            )
            print(af_len.collect())
            ```

            ```
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
            ```

            **Vector (List Shimming) Example: Byte length of comments in a list**

            ```
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl

            data_list = {
                "case_id": ["Case1", "Case2"],
                "comments": [["Test €", "OK"], ["€€", None]]
            }
            af_list = ActuarialFrame(data_list).with_columns(
                pl.col("comments").cast(pl.List(pl.String))
            )
            af_comm_len = af_list.select(
                af_list["comments"].str.len_bytes().alias("comment_byte_lengths")
            )
            print(af_comm_len.collect())
            ```

            ```
            shape: (2, 1)
            ┌──────────────────────┐
            │ comment_byte_lengths │
            │ ---                  │
            │ list[u32]            │
            ╞══════════════════════╡
            │ [8, 2]               │
            │ [6, null]            │
            └──────────────────────┘
            ```
        """
        return self._call_string_method("len_bytes")

    def strip_chars(
        self, characters: Optional[str | pl.Expr] = None
    ) -> "ExpressionProxy":
        """Removes specified leading and trailing characters from strings.

        This is useful for cleaning data, such as removing unwanted prefixes,
        suffixes, or whitespace from policy numbers, client names, or address fields.
        It mirrors Polars' `Expr.str.strip_chars`. If no characters are specified,
        it defaults to removing leading and trailing whitespace.
        For `List[String]` columns, like a list of addresses for a client,
        the operation is applied element-wise to each string in the list.

        Args:
            characters (str | pl.Expr, optional): A string of characters to remove
                from both ends of each string. Can also be a Polars expression that
                evaluates to a string of characters. If None (default), removes
                whitespace (spaces, tabs, newlines, etc.).

        Returns:
            ExpressionProxy: A new `ExpressionProxy` with the specified characters
                stripped from the strings.

        Examples:
            **Scalar Example 1: Cleaning policy numbers by removing specific prefixes/suffixes**

            Imagine policy numbers are sometimes recorded with "POL-", "-TEMP", or extraneous spaces.
            We want to standardize them.

            ```
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl

            data_policy_nos = {
                "raw_policy_id": [
                    "POL-A123-TEMP",
                    " B456 ",
                    "POL-C789",
                    "D012-TEMP",
                    None,
                    " POL-E345 ",
                ],
                "strip_chars_col": ["POL-TEMP ", " ", "POL-", "-TEMP", None, " "]
            }
            af = ActuarialFrame(data_policy_nos)

            # Example 1a: Remove a fixed set of characters "POL-TEMP "
            af_cleaned_fixed = af.select(
                af["raw_policy_id"].str.strip_chars("POL-TEMP ").alias("cleaned_fixed_chars")
            )
            print("Cleaned with fixed characters 'POL-TEMP ':")
            print(af_cleaned_fixed.collect())

            # Example 1b: Remove characters specified in another column
            af_cleaned_dynamic = af.select(
                af["raw_policy_id"].str.strip_chars(pl.col("strip_chars_col")).alias("cleaned_dynamic_chars")
            )
            print("\\nCleaned with characters from 'strip_chars_col':")
            print(af_cleaned_dynamic.collect())
            ```

            ```
            Cleaned with fixed characters 'POL-TEMP ':
            shape: (6, 1)
            ┌─────────────────────┐
            │ cleaned_fixed_chars │
            │ ---                 │
            │ str                 │
            ╞═════════════════════╡
            │ A123                │
            │ B456                │
            │ C789                │
            │ D012                │
            │ null                │
            │ E345                │
            └─────────────────────┘

            Cleaned with characters from 'strip_chars_col':
            shape: (6, 1)
            ┌───────────────────────┐
            │ cleaned_dynamic_chars │
            │ ---                   │
            │ str                   │
            ╞═══════════════════════╡
            │ A123                  │
            │ B456                  │
            │ C789                  │
            │ D012                  │
            │ null                  │
            │ POL-E345              │
            └───────────────────────┘
            ```

            **Scalar Example 2: Trimming leading/trailing whitespace from client names**

            Client names might have extra spaces from data entry.

            ```
            from gaspatchio_core.frame.base import ActuarialFrame

            data_names = {
                "client_name_raw": ["  John Doe  ", "Jane Smith", "  Robert Jones Jr. ", None]
            }
            af_names = ActuarialFrame(data_names)
            af_trimmed_names = af_names.select(
                af_names["client_name_raw"].str.strip_chars().alias("client_name_trimmed") # characters=None
            )
            print(af_trimmed_names.collect())
            ```

            ```
            shape: (4, 1)
            ┌─────────────────────┐
            │ client_name_trimmed │
            │ ---                 │
            │ str                 │
            ╞═════════════════════╡
            │ John Doe            │
            │ Jane Smith          │
            │ Robert Jones Jr.    │
            │ null                │
            └─────────────────────┘
            ```

            **Vector (List Shimming) Example: Cleaning lists of product add-on codes**

            Product codes for add-ons might be stored in a list, with potential unwanted
            characters like asterisks or spaces.

            ```
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl

            data_addons = {
                "policy_id": ["P1001", "P1002"],
                "addon_codes_raw": [
                    ["*RIDER_A ", " RIDER_B*", "BASE_PLAN"],
                    [None, " *RIDER_C ", "\\tRIDER_D\\t"]
                ]
            }
            af_addons = ActuarialFrame(data_addons).with_columns(
                pl.col("addon_codes_raw").cast(pl.List(pl.String))
            )

            # Strip asterisks, spaces, and tabs from each code in the lists
            af_cleaned_addons = af_addons.select(
                af_addons["addon_codes_raw"].str.strip_chars(" *\\t").alias("cleaned_addon_codes")
            )
            print(af_cleaned_addons.collect())
            ```

            ```
            shape: (2, 1)
            ┌───────────────────────────────────┐
            │ cleaned_addon_codes               │
            │ ---                               │
            │ list[str]                         │
            ╞═══════════════════════════════════╡
            │ ["RIDER_A", "RIDER_B", "BASE_PLA… │
            │ [null, "RIDER_C", "RIDER_D"]      │
            └───────────────────────────────────┘
            ```
        """
        return self._call_string_method("strip_chars", characters=characters)

    def strip_chars_start(
        self, characters: Optional[str | pl.Expr] = None
    ) -> "ExpressionProxy":
        """Removes specified leading characters from strings.

        Useful for standardizing data by removing known prefixes or initial
        whitespace. For instance, cleaning policy numbers by removing a
        "TEMP-" prefix or trimming spaces from the beginning of address lines.
        It mirrors Polars' `Expr.str.strip_chars_start`. If no characters are
        specified, it defaults to removing leading whitespace.
        When applied to `List[String]` columns (e.g., a list of historical
        status codes for a policy), the operation is performed element-wise.

        Args:
            characters (str | pl.Expr, optional): A string of characters to remove
                from the start of each string. Can also be a Polars expression that
                evaluates to a string of characters. If None (default), removes
                leading whitespace (spaces, tabs, newlines, etc.).

        Returns:
            ExpressionProxy: A new `ExpressionProxy` with specified leading
                characters stripped from the strings.

        Examples:
            **Scalar Example: Removing prefixes from legacy system IDs**

            Imagine IDs from an old system have prefixes like "LEGACY_", "OLD_",
            or are padded with spaces.

            ```
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl

            data_ids = {
                "legacy_id": [
                    "LEGACY_POL123",
                    "  OLD_CLM456",
                    "POL789",
                    None,
                    "LEGACY_ UW001"
                ],
                "prefixes_to_strip": ["LEGACY_", "OLD_", "NONEXISTENT_", None, "LEGACY_ "]
            }
            af = ActuarialFrame(data_ids)

            # Example 1a: Remove a fixed prefix "LEGACY_"
            af_no_legacy = af.select(
                af["legacy_id"].str.strip_chars_start("LEGACY_").alias("id_no_legacy_prefix")
            )
            print("Stripping fixed prefix 'LEGACY_':")
            print(af_no_legacy.collect())

            # Example 1b: Remove leading whitespace only
            af_trimmed_space = af.select(
                af["legacy_id"].str.strip_chars_start().alias("id_trimmed_space_only") # characters=None
            )
            print("\\nStripping leading whitespace only:")
            print(af_trimmed_space.collect())

            # Example 1c: Remove prefixes defined in another column
            # Note: If the prefix in 'prefixes_to_strip' is not at the start, or is None, no change for that row.
            af_dynamic_prefix = af.select(
                af["legacy_id"].str.strip_chars_start(pl.col("prefixes_to_strip")).alias("id_dynamic_prefix_removed")
            )
            print("\\nStripping prefixes from 'prefixes_to_strip' column:")
            print(af_dynamic_prefix.collect())
            ```

            ```
            Stripping fixed prefix 'LEGACY_':
            shape: (5, 1)
            ┌───────────────────────┐
            │ id_no_legacy_prefix   │
            │ ---                   │
            │ str                   │
            ╞═══════════════════════╡
            │ POL123                │
            │   OLD_CLM456          │
            │ POL789                │
            │ null                  │
            │ UW001                 │
            └───────────────────────┘

            Stripping leading whitespace only:
            shape: (5, 1)
            ┌─────────────────────────┐
            │ id_trimmed_space_only   │
            │ ---                     │
            │ str                     │
            ╞═════════════════════════╡
            │ LEGACY_POL123           │
            │ OLD_CLM456              │
            │ POL789                  │
            │ null                    │
            │ LEGACY_ UW001           │
            └─────────────────────────┘

            Stripping prefixes from 'prefixes_to_strip' column:
            shape: (5, 1)
            ┌─────────────────────────────┐
            │ id_dynamic_prefix_removed   │
            │ ---                         │
            │ str                         │
            ╞═════════════════════════════╡
            │ POL123                      │
            │   CLM456                    │
            │ POL789                      │
            │ null                        │
            │ UW001                       │
            └─────────────────────────────┘
            ```

            **Vector (List Shimming) Example: Cleaning lists of temporary transaction remarks**

            Transaction remarks might be stored in lists, with some prefixed by "TEMP: " or spaces.

            ```
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl

            data_remarks = {
                "policy_id": ["TRN01", "TRN02"],
                "transaction_remarks_raw": [
                    ["TEMP: Initial assessment", "  Adjustment processed", "Final Review"],
                    [None, "TEMP: Hold for now", "TEMP: Resolved"]
                ]
            }
            af_remarks = ActuarialFrame(data_remarks).with_columns(
                pl.col("transaction_remarks_raw").cast(pl.List(pl.String))
            )

            # Strip "TEMP: " prefix from each remark in the lists
            # Also handles leading spaces if "TEMP: " is not present by chaining or using a regex in a real scenario.
            # For simplicity, this example focuses on strip_chars_start with a fixed string.
            af_cleaned_remarks_prefix = af_remarks.select(
                af_remarks["transaction_remarks_raw"].str.strip_chars_start("TEMP: ").alias("cleaned_remarks_prefix")
            )
            print("Cleaned remarks (prefix 'TEMP: '):")
            print(af_cleaned_remarks_prefix.collect())

            # To strip leading whitespace from list elements:
            af_cleaned_remarks_space = af_remarks.select(
                af_remarks["transaction_remarks_raw"].str.strip_chars_start().alias("cleaned_remarks_space")
            )
            print("\\nCleaned remarks (leading whitespace):")
            print(af_cleaned_remarks_space.collect())
            ```

            ```
            Cleaned remarks (prefix 'TEMP: '):
            shape: (2, 1)
            ┌────────────────────────────────────────────────────────────┐
            │ cleaned_remarks_prefix                                     │
            │ ---                                                        │
            │ list[str]                                                  │
            ╞════════════════════════════════════════════════════════════╡
            │ ["Initial assessment", "  Adjustment processed", "Final … │
            │ [null, "Hold for now", "Resolved"]                         │
            └────────────────────────────────────────────────────────────┘

            Cleaned remarks (leading whitespace):
            shape: (2, 1)
            ┌────────────────────────────────────────────────────────────┐
            │ cleaned_remarks_space                                      │
            │ ---                                                        │
            │ list[str]                                                  │
            ╞════════════════════════════════════════════════════════════╡
            │ ["TEMP: Initial assessment", "Adjustment processed", "Fin… │
            │ [null, "TEMP: Hold for now", "TEMP: Resolved"]             │
            └────────────────────────────────────────────────────────────┘
            ```
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

            ```
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

            ```
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

            ```
            data_list = {
                "case_id": ["C01", "C02"],
                "ref_codes": [["TEMP-A1", "B2", "TEMP-C3"], [None, "TEMP-D4"]]
            }
            af_list = ActuarialFrame(data_list).with_columns(
                pl.col("ref_codes").cast(pl.List(pl.String))
            )
            af_list_stripped = af_list.select(
                af_list["ref_codes"].str.strip_prefix("TEMP-").alias("cleaned_codes")
            )
            print(af_list_stripped.collect())
            ```

            ```
            shape: (2, 1)
            ┌────────────────────┐
            │ cleaned_codes      │
            │ ---                │
            │ list[str]          │
            ╞════════════════════╡
            │ ["A1", "B2", "C3"] │
            │ [null, "D4"]       │
            └────────────────────┘
            ```
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

            ```
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl
            data_strip_end = {
                "description_raw": ["Term Life Plan - Basic", "Whole Life - OptA  ", "Annuity - TypeB*", None],
                "codes_to_strip": ["- Basic", " OptA  ", "*", "XXX"]
            }
            # Scalar Example Part 1: Strip specific trailing suffixes
            af1_se = ActuarialFrame(data_strip_end)
            af_stripped = af1_se.select(
                af1_se["description_raw"].str.strip_chars_end(pl.col("codes_to_strip")).alias("base_description_attempt")
            )
            print(af_stripped.collect())

            # Scalar Example Part 2: Strip trailing whitespace only
            af2_se = ActuarialFrame(data_strip_end) # Use a fresh frame instance
            af_rstripped_ws = af2_se.select(
                af2_se["description_raw"].str.strip_chars_end().alias("rstrip_whitespace")
            )
            print(af_rstripped_ws.collect())
            ```

            ```
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
            ```

            **Vector (List Shimming) Example: Removing trailing punctuation from agent notes**

            ```
            # Set string length for more consistent doctest output
            with pl.Config(fmt_str_lengths=100):
                data_list_se = {
                    "agent_id": [101, 102],
                    "notes_list": [["Client interested!!", "Done."], [None, "Call back asap."]]
                }
                af_list_se = ActuarialFrame(data_list_se).with_columns(
                    pl.col("notes_list").cast(pl.List(pl.String))
                )
                af_list_stripped = af_list_se.select(
                    af_list_se["notes_list"].str.strip_chars_end(".! ").alias("cleaned_notes")
                )
                print(af_list_stripped.collect())
            ```

            ```
            shape: (2, 1)
            ┌───────────────────────────────┐
            │ cleaned_notes                 │
            │ ---                           │
            │ list[str]                     │
            ╞═══════════════════════════════╡
            │ ["Client interested", "Done"] │
            │ [null, "Call back asap"]      │
            └───────────────────────────────┘
            ```
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
            ```
            # Test with pl.Config to ensure consistent display
            with pl.Config(fmt_str_lengths=100):
                from gaspatchio_core.frame.base import ActuarialFrame
                import polars as pl
                data = {
                    "policy_serial": ["123", "45", "6789", None, "1"],
                }
                af = ActuarialFrame(data)
                af_zfilled = af.select(
                    af["policy_serial"].str.zfill(5).alias("zfilled_serial")
                )
                print(af_zfilled.collect())
            ```

            ```
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
            ```

            **Vector (List Shimming) Example: Padding numerical components in claim codes**
            ```
            with pl.Config(fmt_str_lengths=100):
                data_list = {
                    "claim_batch": ["B01", "B02"],
                    "item_codes": [["A1", "B123", "C04"], [None, "D56"]]
                }
                af_list = ActuarialFrame(data_list).with_columns(
                    pl.col("item_codes").cast(pl.List(pl.String))
                )
                af_list_zfilled = af_list.select(
                    af_list["item_codes"].str.zfill(4).alias("zfilled_item_codes")
                )
                print(af_list_zfilled.collect())
            ```

            ```
            shape: (2, 1)
            ┌──────────────────────────┐
            │ zfilled_item_codes       │
            │ ---                      │
            │ list[str]                │
            ╞══════════════════════════╡
            │ ["00A1", "B123", "0C04"] │
            │ [null, "0D56"]           │
            └──────────────────────────┘
            ```
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
            ```
            # Test with pl.Config to ensure consistent display
            with pl.Config(fmt_str_lengths=100):
                from gaspatchio_core.frame.base import ActuarialFrame
                import polars as pl
                data = {
                    "account_code": ["A1", "B123", None, "C"],
                }
                af = ActuarialFrame(data)
                af_ljust = af.select(
                    af["account_code"].str.ljust(6, "-").alias("ljust_code")
                )
                print(af_ljust.collect())
            ```

            ```
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
            ```

            **Vector (List Shimming) Example: Padding list elements**

            ```
            with pl.Config(fmt_str_lengths=100):
                data_list = {
                    "batch_id": ["X01"],
                    "sub_codes": [["S1", "LONGCODE", "S23"]]
                }
                af_list = ActuarialFrame(data_list).with_columns(
                    pl.col("sub_codes").cast(pl.List(pl.String))
                )
                af_list_ljust = af_list.select(
                    af_list["sub_codes"].str.ljust(8, "X").alias("ljust_sub_codes")
                )
                print(af_list_ljust.collect())
            ```

            ```
            shape: (1, 1)
            ┌──────────────────────────────────────┐
            │ ljust_sub_codes                      │
            │ ---                                  │
            │ list[str]                            │
            ╞══════════════════════════════════════╡
            │ ["S1XXXXXX", "LONGCODE", "S23XXXXX"] │
            └──────────────────────────────────────┘
            ```
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
            ```python
            # Test with pl.Config to ensure consistent display
            with pl.Config(fmt_str_lengths=100):
                from gaspatchio_core.frame.base import ActuarialFrame
                import polars as pl
                data = {
                    "amount_str": ["12.3", "1234.56", None, "7"],
                }
                af = ActuarialFrame(data)
                af_rjust = af.select(
                    af["amount_str"].str.rjust(10, " ").alias("rjust_amount")
                )
                print(af_rjust.collect())
            ```

            ```text
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
            ```

            **Vector (List Shimming) Example: Right-padding list elements**
            ```python
            with pl.Config(fmt_str_lengths=100):
                from gaspatchio_core.frame.base import ActuarialFrame # Added import
                import polars as pl # Added import
                data_list = {
                    "batch_id": ["Y01"],
                    "item_ids": [["ID1", "SHORT", "ID12345"]]
                }
                af_list = ActuarialFrame(data_list).with_columns(
                    pl.col("item_ids").cast(pl.List(pl.String))
                )
                af_list_rjust = af_list.select(
                    af_list["item_ids"].str.rjust(10, "0").alias("rjust_item_ids")
                )
                print(af_list_rjust.collect())
            ```

            ```text
            shape: (1, 1)
            ┌────────────────────────────────────────────┐
            │ rjust_item_ids                             │
            │ ---                                        │
            │ list[str]                                  │
            ╞════════════════════════════════════════════╡
            │ ["0000000ID1", "00000SHORT", "000ID12345"] │
            └────────────────────────────────────────────┘
            ```
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
        """Check if strings in a column start with a given substring.

        This is useful for categorizing or flagging records based on prefixes in
        textual data. For example, identifying policies based on product code prefixes
        (e.g., "TERM-" for term life, "WL-" for whole life) or segmenting claims
        by a prefix in their claim ID (e.g., "AUTO-" for auto claims).

        When applied to a column of `List[String]`, such as a list of associated
        product features for a policy, the operation is performed element-wise on
        each string within each list, returning a list of booleans.

        Args:
            prefix: The substring to check for at the beginning of each string.
                    Can be a literal string (e.g., "TERM-") or a Polars expression
                    (e.g., `pl.col("another_column_with_prefixes")`).

        Returns:
            ExpressionProxy: A new `ExpressionProxy` containing a boolean Series
                indicating for each input string whether it starts with the prefix.
                If the input was `List[String]`, the output will be `List[bool]`.

        Examples:
            **Scalar Example: Identifying Term Life policies by policy number prefix**

            Suppose policy numbers are prefixed to indicate the general product category.
            We want to identify all "TERM-" policies.

            ```python
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl

            data_policies = {
                "policy_no": ["TERM-1001", "WL-2002", "TERM-1003", None, "UL-3004", "TERM-1004"],
                "issue_age": [25, 30, 28, 45, 35, 40]
            }
            af = ActuarialFrame(data_policies)

            # Check if policy_no starts with "TERM-"
            af_term_policies = af.select(
                af["policy_no"].str.starts_with("TERM-").alias("is_term_policy")
            )
            print(af_term_policies.collect())
            ```

            ```text
            shape: (6, 1)
            ┌────────────────┐
            │ is_term_policy │
            │ ---            │
            │ bool           │
            ╞════════════════╡
            │ true           │
            │ false          │
            │ true           │
            │ null           │
            │ false          │
            │ true           │
            └────────────────┘
            ```

            **Vector Example: Checking for primary benefit riders in a list of rider codes**

            Each policy might have a list of rider codes. We want to check if any of these
            codes start with "B-" indicating a primary benefit rider.

            ```python
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl

            data_policy_riders = {
                "policy_id": ["P201", "P202", "P203"],
                "rider_codes_list": [
                    ["B-ADB", "S-WP", "S-CI"], # B-AccidentalDeathBenefit, S-WaiverOfPremium, S-CriticalIllness
                    ["S-LTC", None, "B-GIO"],  # S-LongTermCare, B-GuaranteedInsurabilityOption
                    ["S-WPR", "S-CIR"]
                ]
            }
            af_riders = ActuarialFrame(data_policy_riders).with_columns(
                pl.col("rider_codes_list").cast(pl.List(pl.String))
            )

            af_primary_benefit_check = af_riders.select(
                af_riders["rider_codes_list"].str.starts_with("B-").alias("has_primary_benefit_rider")
            )
            print(af_primary_benefit_check.collect())
            ```

            ```text
            shape: (3, 1)
            ┌───────────────────────────┐
            │ has_primary_benefit_rider │
            │ ---                       │
            │ list[bool]                │
            ╞═══════════════════════════╡
            │ [true, false, false]      │
            │ [false, null, true]       │
            │ [false, false]            │
            └───────────────────────────┘
            ```
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
