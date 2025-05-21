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
                schema = self._parent_af._df.collect_schema()
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

        This method searches for a pattern within string values, returning a boolean
        indicating if the pattern exists in each string. It's useful for filtering,
        data categorization, and identifying records with specific text patterns.

        !!! note "When to use"
            In actuarial work, this function is invaluable when you need to:

            * Identify policies with specific riders or endorsements from description fields
            * Find claims that mention particular medical conditions or causes
            * Filter customer feedback containing specific keywords for risk analysis
            * Segment policyholders based on address information (e.g., rural vs urban)
            * Flag policies or claims with special handling notes (e.g., "legal review")
            * Screen underwriting notes for high-risk indicators

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
                    "Universal Life, includes ADB rider and Accidental Death Benefit (ADB)",
                    "Term Life, no Accidental Death Benefit rider"
                ]
            }
            af = ActuarialFrame(data)
            af_with_adb_rider = af.select(
                af["description"].str.contains("ADB rider", literal=True).alias("has_adb_rider")
            )
            print(af_with_adb_rider.collect())
            ```

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

            **Vector Example: Checking underwriter notes for high-risk keywords**

            Suppose each policy has a list of notes from underwriters. We want to check
            if any note for a given policy contains keywords like "medical history"
            or "hazardous occupation", which might indicate higher risk.

            ```python
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl

            uw_notes_data = {
                "policy_id": ["UW001", "UW002", "UW003"],
                "underwriter_notes": [
                    ["Standard risk.", "Family history clear."],
                    ["Applicant works in construction.", "Reviewed medical history: smoker."],
                    ["No concerning notes.", None, "Possible hazardous occupation mentioned."]
                ]
            }
            af_notes_initial = ActuarialFrame(uw_notes_data)
            # Step 1: Cast to list of strings
            af_notes_casted = af_notes_initial.with_columns(
                af_notes_initial["underwriter_notes"].cast(pl.List(pl.String)).alias("notes_casted")
            )

            # Step 2: Perform contains checks
            af_results = af_notes_casted.with_columns(
                pl.col("notes_casted")
                .list.eval(pl.element().str.contains(r"medical history").alias("contains_check"))
                .list.any()
                .alias("mentions_medical_history"),
                pl.col("notes_casted")
                .list.eval(pl.element().str.contains(r"(?i)hazardous occupation").alias("contains_check"))
                .list.any()
                .alias("mentions_hazardous_occupation"),
            ).select(
                "mentions_medical_history", "mentions_hazardous_occupation"
            )

            print(af_results.collect())
            ```

            ```text
            shape: (3, 2)
            ┌──────────────────────────┬─────────────────────────────────┐
            │ mentions_medical_history │ mentions_hazardous_occupation │
            │ ---                      │ ---                             │
            │ bool                     │ bool                            │
            ╞══════════════════════════╪═════════════════════════════════╡
            │ false                    │ false                           │
            │ true                     │ false                           │
            │ false                    │ true                            │
            └──────────────────────────┴─────────────────────────────────┘
            ```

            **Using `contains` with a list of patterns (regex and literal)**

            Suppose we want to check for multiple keywords in underwriter notes using both
            literal and regex matching.

            ```python
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl

            uw_notes_data_multi = { # Renamed to avoid conflict
                "policy_id": ["UW001", "UW002", "UW003"],
                "underwriter_notes": [
                    ["Standard risk.", "Family history clear."],
                    ["Applicant works in construction.", "Reviewed medical history: smoker."],
                    ["No concerning notes.", None, "Possible hazardous occupation mentioned."]
                ]
            }
            af_multi = ActuarialFrame(uw_notes_data_multi)
            af_multi_processed = af_multi.with_columns(
                af_multi["underwriter_notes"].cast(pl.List(pl.String)).alias("notes_casted")
            ).with_columns(
                # Literal check
                pl.col("notes_casted") # Corrected: use alias within the expression
                    .list.eval(pl.element().str.contains("medical history", literal=True))
                    .list.any()
                    .alias("lit_medical"),
                # Regex check (case insensitive)
                pl.col("notes_casted") # Corrected: use alias within the expression
                    .list.eval(pl.element().str.contains(r"(?i)hazardous occupation"))
                    .list.any()
                    .alias("re_hazardous"),
                # Another Regex check (case insensitive) for medical history
                pl.col("notes_casted") # Corrected: use alias within the expression
                    .list.eval(pl.element().str.contains(r"(?i)medical history"))
                    .list.any()
                    .alias("re_medical"),
            ).select(
                pl.col("lit_medical").alias("mentions_medical_history_literal"),
                pl.col("re_hazardous").alias("mentions_hazardous_occupation_regex"),
                pl.col("re_medical").alias("mentions_medical_history_regex")
            )
            print(af_multi_processed.collect())
            ```

            ```text
            shape: (3, 3)
            ┌────────────────────────────────────┬───────────────────────────────────────┬──────────────────────────────────┐
            │ mentions_medical_history_literal │ mentions_hazardous_occupation_regex │ mentions_medical_history_regex │
            │ ---                                │ ---                                   │ ---                              │
            │ bool                               │ bool                                  │ bool                             │
            ╞════════════════════════════════════╪═══════════════════════════════════════╪══════════════════════════════════╡
            │ false                              │ false                                 │ false                            │
            │ true                               │ false                                 │ true                             │
            │ false                              │ true                                  │ false                            │
            └────────────────────────────────────┴───────────────────────────────────────┴──────────────────────────────────┘
            ```
        """
        return self._call_string_method(
            "contains", pattern=pattern, literal=literal, strict=strict
        )

    def to_uppercase(self) -> "ExpressionProxy":
        """Converts all characters in string columns to uppercase.

        This function standardizes textual data by converting all characters in a
        string column to uppercase. This is essential for ensuring consistency
        in data fields critical for actuarial analysis, such as policy status
        codes, product identifiers, or geographical regions, facilitating
        accurate matching, aggregation, and reporting.

        !!! note "When to use"
            In actuarial modeling and data processing, converting text to uppercase is vital for:

            *   **Standardizing Categorical Data:** Ensuring that codes like policy status
                (e.g., "active", "Lapsed", "ACTIVE" all become "ACTIVE"), gender codes
                (e.g., "m", "F" become "M", "F"), or smoker status (e.g. "non-smoker",
                "Smoker" become "NON-SMOKER", "SMOKER") are consistent for grouping
                and analysis.
            *   **Improving Data Matching:** Facilitating joins and lookups between
                different datasets where case sensitivity might cause mismatches
                (e.g., matching policyholder names or addresses from different sources).
            *   **Enhancing Readability and Reporting:** Presenting data in a uniform
                case for reports and dashboards, especially for identifiers or codes.
            *   **Preparing Text for Analysis:** As a preprocessing step before text
                mining or natural language processing tasks on fields like claim
                descriptions or underwriter notes, where case normalization can
                simplify pattern recognition.
            *   **Simplifying Rule-Based Logic:** When applying business rules that
                depend on string comparisons (e.g., identifying policies with specific
                rider codes like "ADB" or "WP" irrespective of their original casing).

        Returns:
            ExpressionProxy: A new `ExpressionProxy` with strings converted to uppercase.

        Examples:
            **Scalar Example: Standardizing policy status codes**

            Policy status might be entered in various cases ("active", "lapsed", "ACTIVE").
            Converting to uppercase ensures consistency for analysis.

            ```python
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

            ```text
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

            **Vector Example: Uppercasing rider codes for a policy**

            A policy might have multiple rider codes stored in a list. To ensure
            uniformity, we can convert all rider codes to uppercase.

            ```python
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl # Needed for pl.List, pl.String

            data_policy_riders = {
                "policy_id": ["R4001", "R4002", "R4003"],
                "rider_codes_list": [
                    ["adb", "wp"],
                    ["ci", None, "ltc", "acc_death"],
                    ["gio"]
                ]
            }
            af_riders = ActuarialFrame(data_policy_riders)
            # Ensure the list column has the correct Polars type for the string operation
            af_riders = af_riders.with_columns(
                af_riders["rider_codes_list"].cast(pl.List(pl.String))
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
        """Converts all characters in string columns to lowercase.

        This function standardizes textual data by converting all characters in a
        string column to lowercase. This is essential for ensuring consistency
        in data fields critical for actuarial analysis, such as system codes,
        free-text fields like occupation or medical conditions, or external data sources,
        facilitating accurate matching, aggregation, and text analysis.

        !!! note "When to use"
            In actuarial modeling and data processing, converting text to lowercase is valuable for:

            *   **Normalizing Text for Analysis:** Preparing free-text fields (e.g.,
                underwriting notes, claim descriptions, occupation details) for text mining
                or NLP by ensuring terms like "SMOKER", "Smoker", and "smoker" are
                treated identically.
            *   **Improving Data Matching with External Sources:** When integrating data
                from various systems or third-party providers where case consistency
                is not guaranteed (e.g., matching addresses, names, or city information).
            *   **Standardizing User Input:** Converting user-entered data (e.g., search
                terms, filter criteria) to a consistent case before processing or
                querying.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with strings converted to lowercase.

        Examples:
            **Scalar Example: Normalizing occupation descriptions for risk analysis**

            Occupation descriptions might be entered in various casings. Converting to
            lowercase helps in standardizing them for consistent risk factor analysis
            or grouping.

            ```python
            from gaspatchio_core.frame.base import ActuarialFrame

            data = {
                "policy_id": ["POL001", "POL002", "POL003", "POL004"],
                "occupation_raw": ["Engineer", "software DEVELOPER", "Teacher", "Project Manager"]
            }
            af = ActuarialFrame(data)
            af_lower_occupation = af.select(
                af["occupation_raw"].str.to_lowercase().alias("occupation_normalized")
            )
            print(af_lower_occupation.collect())
            ```

            ```text
            shape: (4, 1)
            ┌───────────────────────┐
            │ occupation_normalized │
            │ ---                   │
            │ str                   │
            ╞═══════════════════════╡
            │ engineer              │
            │ software developer    │
            │ teacher               │
            │ project manager       │
            └───────────────────────┘
            ```

            **Vector Example: Lowercasing medical condition codes from multiple sources**

            Medical condition codes might come from different systems with varying casing.
            Lowercasing them ensures they can be consistently mapped or analyzed.

            ```python
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl

            data_medical_codes = {
                "claim_id": ["C001", "C002"],
                "condition_codes_list": [
                    ["DIAB_T2", "HBP", "ASTHMA"], # DIAB_T2 = Type 2 Diabetes, HBP = High Blood Pressure
                    ["hbp", None, "copd"]         # COPD = Chronic Obstructive Pulmonary Disease
                ]
            }
            af_codes = ActuarialFrame(data_medical_codes)
            # Ensure the list column has the correct Polars type for the string operation
            af_codes = af_codes.with_columns(
                af_codes["condition_codes_list"].cast(pl.List(pl.String))
            )
            af_lower_codes = af_codes.select(
                af_codes["condition_codes_list"].str.to_lowercase().alias("lower_condition_codes")
            )
            print(af_lower_codes.collect())
            ```

            ```text
            shape: (2, 1)
            ┌─────────────────────────────────────┐
            │ lower_condition_codes               │
            │ ---                                 │
            │ list[str]                           │
            ╞═════════════════════════════════════╡
            │ ["diab_t2", "hbp", "asthma"]        │
            │ ["hbp", null, "copd"]               │
            └─────────────────────────────────────┘
            ```
        """
        return self._call_string_method("to_lowercase")

    def n_chars(self) -> "ExpressionProxy":
        """Get the number of characters in each string.

        This function calculates the length of each string in a column, returning
        an integer representing the number of characters. It's a fundamental
        operation for understanding string data characteristics.

        !!! note "When to use"
            In actuarial work, determining the length of string fields is useful for:

            *   **Data Quality Checks:** Identifying unexpectedly short or long strings
                that might indicate data entry errors or truncation (e.g., validating
                the length of policy numbers, postal codes, or identification numbers).
            *   **Feature Engineering:** Creating new features based on string length
                for predictive models (e.g., the length of a claim description might
                correlate with claim complexity).
            *   **Data Cleaning & Transformation:** Deciding on padding or truncation
                strategies if string fields need to conform to a fixed length for
                system integration or reporting.
            *   **Understanding Free-Text Fields:** Analyzing the distribution of lengths
                in fields like underwriter notes or medical descriptions to gauge the
                amount of detail typically provided.
            *   **Filtering or Segmenting Data:** Selecting records based on the length
                of a specific string field (e.g., finding all policyholder names
                shorter than 3 characters for review).

        Returns:
            ExpressionProxy: An `ExpressionProxy` with the character count (as UInt32)
                             for each string.

        Examples:
            **Scalar Example: Length of product names**

            To understand the typical length of product names in your portfolio,
            or to identify names that might be too long for certain display formats.

            ```python
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

            ```text
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

            **Vector Example: Length of beneficiary names in a list**

            For policies with multiple beneficiaries, you might want to check the length
            of each beneficiary's name, perhaps to ensure it fits within system limits
            or for data validation.

            ```python
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl

            data_list = {
                "policy_id": ["P001", "P002"],
                "beneficiaries": [["John A. Doe", "Jane B. Smith"], ["Robert King", None, "Alice Wonderland"]]
            }
            af_list_initial = ActuarialFrame(data_list)
            af_list = af_list_initial.with_columns(
                af_list_initial["beneficiaries"].cast(pl.List(pl.String))
            )
            af_bene_len = af_list.select(
                af_list["beneficiaries"].str.n_chars().alias("beneficiary_name_lengths")
            )
            print(af_bene_len.collect())
            ```

            ```text
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

        Calculates the length of each string in a column, returning an integer
        representing the number of characters. This is an alias for `n_chars()`.

        !!! note "When to use"
            In actuarial practice, determining the character length of string fields is
            important for:

            *   **Data Validation:** Ensuring identifiers like policy numbers, social
                security numbers, or postal codes adhere to expected length constraints,
                helping to identify data entry errors.
            *   **System Integration:** Verifying that string data, such as client names or
                addresses, does not exceed length limitations of downstream systems or
                databases.
            *   **Feature Engineering:** Using the length of free-text fields (e.g., claim
                descriptions, underwriter notes) as a potential feature in predictive
                models, where length might correlate with complexity or severity.
            *   **Data Quality Assessment:** Identifying outliers or anomalies in string
                lengths that might indicate corrupted or incomplete data.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with the character count (as UInt32)
                             for each string. If the input was `List[String]`,
                             the output will be `List[UInt32]`.

        Examples:
            **Scalar Example: Validating policy number length**

            Scenario: You need to check if policy numbers in your dataset conform to an
            expected length, say 7 characters.

            ```python
            from gaspatchio_core.frame.base import ActuarialFrame

            data = {
                "policy_id_raw": ["POL1234", "POL567", "POL89012", None, "POL3456"],
                "premium": [100.0, 150.0, 200.0, 50.0, 120.0]
            }
            af = ActuarialFrame(data)

            # Calculate the length of each policy_id_raw
            af_len_check = af.select(
                af["policy_id_raw"].str.len_chars().alias("policy_id_length")
            )
            print(af_len_check.collect())
            ```

            ```text
            shape: (5, 1)
            ┌──────────────────┐
            │ policy_id_length │
            │ ---              │
            │ u32              │
            ╞══════════════════╡
            │ 7                │
            │ 6                │
            │ 8                │
            │ null             │
            │ 7                │
            └──────────────────┘
            ```

            **Vector Example: Character count of claim notes**

            Scenario: Each policy may have a list of associated claim notes. You want to find
            the character length of each note to understand the verbosity or for display purposes.

            ```python
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl

            data_list = {
                "policy_id": ["P7001", "P7002"],
                "claim_notes_list": [
                    ["Short note.", "This is a much longer note regarding the claim details.", None],
                    ["Urgent review needed!", "All clear."]
                ]
            }
            af_list_notes = ActuarialFrame(data_list)
            # Ensure the list column has the correct Polars type
            af_list_notes = af_list_notes.with_columns(
                af_list_notes["claim_notes_list"].cast(pl.List(pl.String))
            )

            af_notes_len = af_list_notes.select(
                af_list_notes["claim_notes_list"].str.len_chars().alias("note_char_lengths")
            )
            print(af_notes_len.collect())
            ```

            ```text
            shape: (2, 1)
            ┌───────────────────────────┐
            │ note_char_lengths         │
            │ ---                       │
            │ list[u32]                 │
            ╞═══════════════════════════╡
            │ [11, 53, null]            │
            │ [20, 9]                   │
            └───────────────────────────┘
            ```
        """
        return self._call_string_method("len_chars")

    def len_bytes(self) -> "ExpressionProxy":
        """Get the number of bytes in each string.

        Calculates the byte length of each string in a column. This is particularly
        useful when dealing with multi-byte character encodings (like UTF-8) where
        the number of characters may not equal the number of bytes.

        !!! note "When to use"
            In actuarial contexts, understanding the byte length of string data can be important for:

            *   **Data Storage Estimation:** Accurately estimating storage requirements for
                datasets containing text fields, especially with international character sets
                (e.g., policyholder names, addresses from various regions).
            *   **System Integration Limits:** Ensuring that string data, when exported or
                sent to other systems, conforms to byte-length restrictions imposed by
                those systems (e.g., fixed-width file formats or database field constraints
                defined in bytes).
            *   **Performance Considerations:** Recognizing that operations on strings with
                many multi-byte characters might be more resource-intensive.
            *   **Encoding Issue Detection:** While not a direct detection method, unexpected
                byte lengths compared to character lengths might hint at encoding problems
                or the presence of unusual characters.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with the byte count (as UInt32)
                             for each string. If the input was `List[String]`,
                             the output will be `List[UInt32]`.

        Examples:
            **Scalar Example: Byte length of UTF-8 encoded client names**

            Scenario: You have client names that may include characters from various
            languages, and you need to understand their storage size in bytes.

            ```python
            from gaspatchio_core.frame.base import ActuarialFrame

            data = {
                "client_id": ["C001", "C002", "C003", "C004"],
                "client_name": ["René", "沐宸", "Zoë", "John Doe"] # French, Chinese, German, English names
            }
            af = ActuarialFrame(data)
            af_byte_len = af.select(
                af["client_name"].str.len_bytes().alias("name_byte_length")
            )
            print(af_byte_len.collect())
            ```

            ```text
            shape: (4, 1)
            ┌──────────────────┐
            │ name_byte_length │
            │ ---              │
            │ u32              │
            ╞══════════════════╡
            │ 5                │
            │ 6                │
            │ 4                │
            │ 8                │
            └──────────────────┘
            ```

            **Vector Example: Byte length of free-text comments in a list**

            Scenario: A policy record contains a list of comments, potentially with
            special characters or different languages. You need to find the byte
            length of each comment.

            ```python
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl

            data_list_comments = {
                "policy_id": ["P501", "P502"],
                "comments_list": [
                    ["Test € symbol", "Standard comment.", None], # Euro symbol is multi-byte
                    ["Résumé", "日本語のコメント"] # French with accent, Japanese comment
                ]
            }
            af_comments = ActuarialFrame(data_list_comments)
            # Ensure the list column has the correct Polars type
            af_comments = af_comments.with_columns(
                af_comments["comments_list"].cast(pl.List(pl.String))
            )

            af_comment_byte_len = af_comments.select(
                af_comments["comments_list"].str.len_bytes().alias("comment_byte_lengths")
            )
            print(af_comment_byte_len.collect())
            ```

            ```text
            shape: (2, 1)
            ┌──────────────────────────┐
            │ comment_byte_lengths     │
            │ ---                      │
            │ list[u32]                │
            ╞══════════════════════════╡
            │ [13, 17, null]           │
            │ [7, 21]                  │
            └──────────────────────────┘
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

        !!! note "When to use"
            In actuarial data preparation, `strip_chars` is frequently used to:

            *   **Cleanse Identifier Fields:** Remove extraneous characters (e.g., spaces, hyphens, special symbols)
                from policy numbers, claim IDs, or client identifiers to ensure consistency for matching and lookups.
                For example, "POL- 123* " could become "POL-123" by stripping " *".
            *   **Standardize Textual Data:** Trim leading/trailing whitespace from free-text fields like
                occupation descriptions, addresses, or underwriter notes before analysis or storage.
            *   **Prepare Data for Joins:** Ensure that join keys consisting of string data are clean and consistently
                formatted to avoid join failures due to subtle differences like trailing spaces.
            *   **Sanitize User Input:** Clean user-provided search terms or filter values by removing
                unwanted characters before using them in queries.

        Args:
            characters (str | pl.Expr, optional): A string of characters to remove
                from both ends of each string. Can also be a Polars expression that
                evaluates to a string of characters. If None (default), removes
                whitespace (spaces, tabs, newlines, etc.).

        Returns:
            ExpressionProxy: A new `ExpressionProxy` with the specified characters
                stripped from the strings.

        Examples:
            **Scalar Example 1: Cleaning policy numbers by removing specific prefixes/suffixes and whitespace**

            Policy numbers might be recorded with inconsistent characters (e.g., "ID-", "*", spaces).
            We want to standardize them by removing these specific characters and any surrounding whitespace.

            ```python
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl

            data_policy_nos = {
                "raw_policy_id": [
                    "ID-A123-XYZ*",
                    " B456 ",
                    "ID-C789*",
                    "D012-XYZ",
                    None,
                    " ID-E345* ",
                ],
                "chars_to_remove_col": ["ID-*XYZ ", " ", "ID-*", "-XYZ", None, " *ID-"]
            }
            af = ActuarialFrame(data_policy_nos)

            # Example 1a: Remove a fixed set of characters "ID-*XYZ " from policy IDs
            af_cleaned_fixed = af.select(
                af["raw_policy_id"].str.strip_chars("ID-*XYZ ").alias("cleaned_fixed_chars")
            )
            print("Cleaned with fixed characters 'ID-*XYZ ':")
            print(af_cleaned_fixed.collect())

            # Example 1b: Remove characters specified in another column
            # This dynamically strips characters based on the 'chars_to_remove_col' for each row.
            af_cleaned_dynamic = af.select(
                af["raw_policy_id"].str.strip_chars(pl.col("chars_to_remove_col")).alias("cleaned_dynamic_chars")
            )
            print("\\nCleaned with characters from 'chars_to_remove_col':")
            print(af_cleaned_dynamic.collect())

            # Example 1c: Remove only leading and trailing whitespace
            af_trimmed_whitespace = af.select(
                af["raw_policy_id"].str.strip_chars().alias("trimmed_whitespace_only") # characters=None
            )
            print("\\nCleaned with default whitespace stripping:")
            print(af_trimmed_whitespace.collect())
            ```

            ```text
            Cleaned with fixed characters 'ID-*XYZ ':
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

            Cleaned with characters from 'chars_to_remove_col':
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
            │ E345                  │
            └───────────────────────┘

            Cleaned with default whitespace stripping:
            shape: (6, 1)
            ┌───────────────────────────┐
            │ trimmed_whitespace_only   │
            │ ---                       │
            │ str                       │
            ╞═══════════════════════════╡
            │ ID-A123-XYZ*              │
            │ B456                      │
            │ ID-C789*                  │
            │ D012-XYZ                  │
            │ null                      │
            │ ID-E345*                  │
            └───────────────────────────┘
            ```

            **Vector (List Shimming) Example: Cleaning lists of product add-on codes**

            Product codes for add-ons might be stored in a list, with potential unwanted
            characters like asterisks, hyphens, or spaces.

            ```python
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl

            data_addons = {
                "policy_id": ["P1001", "P1002"],
                "addon_codes_raw": [
                    ["*RIDER_A- ", " -RIDER_B*", "BASE_PLAN"],
                    [None, " *-RIDER_C- ", "\\tRIDER_D\\t*"]
                ]
            }
            af_addons = ActuarialFrame(data_addons).with_columns(
                pl.col("addon_codes_raw").cast(pl.List(pl.String))
            )

            # Strip asterisks, hyphens, spaces, and tabs from each code in the lists
            af_cleaned_addons = af_addons.select(
                af_addons["addon_codes_raw"].str.strip_chars(" *-#\\t").alias("cleaned_addon_codes") # Added '#' to demonstrate it's ignored if not present
            )
            print(af_cleaned_addons.collect())
            ```

            ```text
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

        !!! note "When to use"
            In actuarial data processing, `strip_chars_start` is valuable for:

            *   **Normalizing Prefixed Identifiers:** Removing consistent prefixes from
                identifiers like policy numbers (e.g., "PN-", "TEMP_"), claim codes
                (e.g., "CL-"), or agent codes to get the core identifier.
            *   **Cleaning Leading Characters in Text Fields:** Removing leading non-essential
                characters (e.g., bullets, numbers, special symbols, spaces) from free-text
                fields like notes, descriptions, or imported data before further processing.
            *   **Standardizing Data from Multiple Sources:** If different source systems prefix
                the same data differently, this function can help unify them by removing
                those specific leading characters.

        Args:
            characters (str | pl.Expr, optional): A string of characters to remove
                from the start of each string. Can also be a Polars expression that
                evaluates to a string of characters. If None (default), removes
                leading whitespace (spaces, tabs, newlines, etc.).

        Returns:
            ExpressionProxy: A new `ExpressionProxy` with specified leading
                characters stripped from the strings.

        Examples:
            **Scalar Example: Removing prefixes from legacy system IDs and leading whitespace**

            Legacy system IDs might have prefixes like "LEG_", "OLD-", or be padded with spaces.

            ```python
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl

            data_ids = {
                "legacy_id": [
                    "LEG_POL123",
                    "  OLD-CLM456",
                    "POL789",
                    None,
                    "LEG_ UW001", # Note the space after LEG_
                    "  TRN999"
                ],
                "prefixes_to_strip": ["LEG_", "OLD-", "NONEXISTENT_", None, "LEG_ ", "  "]
            }
            af = ActuarialFrame(data_ids)

            # Example 1a: Remove a fixed prefix "LEG_"
            af_no_leg_prefix = af.select(
                af["legacy_id"].str.strip_chars_start("LEG_").alias("id_no_leg_prefix")
            )
            print("Stripping fixed prefix 'LEG_':")
            print(af_no_leg_prefix.collect())

            # Example 1b: Remove leading whitespace only (characters=None)
            af_trimmed_space = af.select(
                af["legacy_id"].str.strip_chars_start().alias("id_trimmed_leading_space")
            )
            print("\\nStripping leading whitespace only:")
            print(af_trimmed_space.collect())

            # Example 1c: Remove prefixes defined in another column
            # This will strip any character found in the corresponding 'prefixes_to_strip' string from the start.
            af_dynamic_prefix = af.select(
                af["legacy_id"].str.strip_chars_start(pl.col("prefixes_to_strip")).alias("id_dynamic_prefix_removed")
            )
            print("\\nStripping prefixes from 'prefixes_to_strip' column (character-wise from start):")
            print(af_dynamic_prefix.collect())
            ```

            ```text
            Stripping fixed prefix 'LEG_':
            shape: (6, 1)
            ┌────────────────────┐
            │ id_no_leg_prefix   │
            │ ---                │
            │ str                │
            ╞════════════════════╡
            │ POL123             │
            │   OLD-CLM456       │
            │ POL789             │
            │ null               │
            │ UW001              │
            │   TRN999           │
            └────────────────────┘

            Stripping leading whitespace only:
            shape: (6, 1)
            ┌───────────────────────────┐
            │ id_trimmed_leading_space  │
            │ ---                       │
            │ str                       │
            ╞═══════════════════════════╡
            │ LEG_POL123                │
            │ OLD-CLM456                │
            │ POL789                    │
            │ null                      │
            │ LEG_ UW001                │
            │ TRN999                    │
            └───────────────────────────┘

            Stripping prefixes from 'prefixes_to_strip' column (character-wise from start):
            shape: (6, 1)
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
            │ TRN999                      │
            └─────────────────────────────┘
            ```

            **Vector (List Shimming) Example: Cleaning lists of temporary transaction remarks**

            Transaction remarks might be stored in lists, with some prefixed by "TEMP: " or spaces.

            ```python
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl

            data_remarks = {
                "policy_id": ["TRN01", "TRN02"],
                "transaction_remarks_raw": [
                    ["TEMP: Initial assessment", "  Adjustment processed", "Final Review"],
                    [None, "TEMP: Hold for now", "TEMP: Resolved", "Status: OK"]
                ]
            }
            af_remarks = ActuarialFrame(data_remarks).with_columns(
                pl.col("transaction_remarks_raw").cast(pl.List(pl.String))
            )

            # Example 2a: Strip fixed prefix "TEMP: " from each remark in the lists
            af_cleaned_remarks_prefix = af_remarks.select(
                af_remarks["transaction_remarks_raw"].str.strip_chars_start("TEMP: ").alias("cleaned_remarks_prefix")
            )
            print("Cleaned remarks (prefix 'TEMP: '):")
            print(af_cleaned_remarks_prefix.collect())

            # Example 2b: Strip leading whitespace from list elements
            af_cleaned_remarks_space = af_remarks.select(
                af_remarks["transaction_remarks_raw"].str.strip_chars_start().alias("cleaned_remarks_space")
            )
            print("\\nCleaned remarks (leading whitespace):")
            print(af_cleaned_remarks_space.collect())
            ```

            ```text
            Cleaned remarks (prefix 'TEMP: '):
            shape: (2, 1)
            ┌────────────────────────────────────────────────────────────────────────────┐
            │ cleaned_remarks_prefix                                                     │
            │ ---                                                                        │
            │ list[str]                                                                  │
            ╞════════════════════════════════════════════════════════════════════════════╡
            │ ["Initial assessment", "  Adjustment processed", "Final Review"]            │
            │ [null, "Hold for now", "Resolved", "Status: OK"]                           │
            └────────────────────────────────────────────────────────────────────────────┘

            Cleaned remarks (leading whitespace):
            shape: (2, 1)
            ┌────────────────────────────────────────────────────────────────────────────┐
            │ cleaned_remarks_space                                                      │
            │ ---                                                                        │
            │ list[str]                                                                  │
            ╞════════════════════════════════════════════════════════════════════════════╡
            │ ["TEMP: Initial assessment", "Adjustment processed", "Final Review"]       │
            │ [null, "TEMP: Hold for now", "TEMP: Resolved", "Status: OK"]               │
            └────────────────────────────────────────────────────────────────────────────┘
            ```
        """
        return self._call_string_method("strip_chars_start", characters=characters)

    def strip_prefix(self, prefix: str | pl.Expr) -> "ExpressionProxy":
        """Remove a given prefix from each string.

        This function is used to remove a specified leading substring (prefix)
        from each string in a column. If a string does not start with the
        given prefix, it remains unchanged. This is particularly useful for
        cleaning and standardizing data where identifiers or codes might have
        consistent but unwanted prefixes.

        For `List[String]` columns, the operation is applied element-wise to each
        string within each list.

        !!! note "When to use"
            In actuarial data management, `strip_prefix` is valuable for:

            *   **Standardizing Product Codes:** If product codes are prefixed with
                system identifiers (e.g., "SYS_TERM", "SYS_WL"), you can remove "SYS_"
                to get the core product code ("TERM", "WL") for analysis or mapping.
            *   **Cleaning Client Identifiers:** Removing prefixes from client IDs
                that might indicate the source system or a temporary status (e.g.,
                "TEMP-CLIENT123" becomes "CLIENT123").
            *   **Normalizing Location Data:** If geographical codes have a regional
                prefix (e.g., "US-NY", "CA-ON"), stripping the country prefix might be
                needed for specific regional analyses.
            *   **Processing External Data Feeds:** When data from external vendors
                includes prefixed identifiers that need to be aligned with internal
                formats.

        Args:
            prefix: The prefix to remove from each string.
                        Can also be a Polars expression that evaluates to a string.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with the specified prefix removed.

        Examples:
            **Scalar Example: Removing 'TEMP-' prefix from temporary policy IDs**

            Scenario: You have a column of policy IDs where some are temporary and
            prefixed with "TEMP-". You need to clean these IDs by removing the prefix.

            ```python
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl

            data_strip_prefix = {
                "policy_id_raw": ["TEMP-001", "TEMP-002", "003", None, "TEMP-004", "POL-005"],
                "processing_prefix": ["TEMP-", "TEMP-", "TEMP-", "TEMP-", "TEMP-", "POL-"]
            }
            af = ActuarialFrame(data_strip_prefix)

            # Example 1a: Strip a fixed prefix "TEMP-"
            af_stripped_fixed = af.select(
                af["policy_id_raw"].str.remove_prefix("TEMP-").alias("cleaned_id_fixed")
            )
            print("Stripped with fixed prefix 'TEMP-' using remove_prefix:")
            print(af_stripped_fixed.collect())

            # Example 1b: Strip prefix defined in another column
            af_stripped_dynamic = af.select(
                af["policy_id_raw"].str.remove_prefix(pl.col("processing_prefix")).alias("cleaned_id_dynamic")
            )
            print("\nStripped with dynamic prefix from 'processing_prefix' column using remove_prefix:")
            print(af_stripped_dynamic.collect())
            ```

            ```text
            Stripped with fixed prefix 'TEMP-' using remove_prefix:
            shape: (6, 1)
            ┌──────────────────┐
            │ cleaned_id_fixed │
            │ ---              │
            │ str              │
            ╞══════════════════╡
            │ 001              │
            │ 002              │
            │ 003              │
            │ null             │
            │ 004              │
            │ POL-005          │
            └──────────────────┘

            Stripped with dynamic prefix from 'processing_prefix' column using remove_prefix:
            shape: (6, 1)
            ┌────────────────────┐
            │ cleaned_id_dynamic │
            │ ---                │
            │ str                │
            ╞════════════════════╡
            │ 001                │
            │ 002                │
            │ 003                │
            │ null               │
            │ 004                │
            │ 005                │
            └────────────────────┘
            ```

            **Vector (List Shimming) Example: Removing 'LEGACY-' prefix from lists of product feature codes**

            Scenario: A policy has a list of associated feature codes, some of which
            are from a legacy system and prefixed with "LEGACY-".

            ```python
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl

            data_list = {
                "policy_key": ["POLICY_A", "POLICY_B"],
                "feature_codes_raw": [
                    ["LEGACY-RIDER1", "NEW_FEATURE_X", "LEGACY-BENEFIT2"],
                    [None, "LEGACY-COVERAGE_Y", "STANDARD_Z"]
                ]
            }
            af_list = ActuarialFrame(data_list)
            af_list = af_list.with_columns(
                af_list["feature_codes_raw"].cast(pl.List(pl.String))
            )
            af_list_stripped = af_list.select(
                af_list["feature_codes_raw"].str.remove_prefix("LEGACY-").alias("cleaned_feature_codes")
            )
            # Use pl.Config to ensure consistent output for doctest
            with pl.Config(fmt_str_lengths=100):
                print(af_list_stripped.collect())
            ```

            ```text
            shape: (2, 1)
            ┌────────────────────────────────────────────┐
            │ cleaned_feature_codes                      │
            │ ---                                        │
            │ list[str]                                  │
            ╞════════════════════════════════════════════╡
            │ ["RIDER1", "NEW_FEATURE_X", "BENEFIT2"]    │
            │ [null, "COVERAGE_Y", "STANDARD_Z"]         │
            └────────────────────────────────────────────┘
            ```
        """
        return self._call_string_method("strip_prefix", prefix=prefix)

    def remove_prefix(self, prefix: str | pl.Expr) -> "ExpressionProxy":
        """Alias for `strip_prefix`. Remove a prefix from each string.

        This function is an alias for `strip_prefix`. It removes a specified
        leading substring (prefix) from each string in a column. If a string
        does not start with the given prefix, it remains unchanged. This is
        particularly useful for cleaning and standardizing data where
        identifiers or codes might have consistent but unwanted prefixes.

        For `List[String]` columns, the operation is applied element-wise to each
        string within each list.

        !!! note "When to use"
            In actuarial data management, `remove_prefix` (or `strip_prefix`)
            is valuable for:

            *   **Standardizing Product Codes:** If product codes are prefixed with
                system identifiers (e.g., "SYS_TERM", "SYS_WL"), you can remove "SYS_"
                to get the core product code ("TERM", "WL") for analysis or mapping.
            *   **Cleaning Client Identifiers:** Removing prefixes from client IDs
                that might indicate the source system or a temporary status (e.g.,
                "TEMP-CLIENT123" becomes "CLIENT123").
            *   **Normalizing Location Data:** If geographical codes have a regional
                prefix (e.g., "US-NY", "CA-ON"), stripping the country prefix might be
                needed for specific regional analyses.
            *   **Processing External Data Feeds:** When data from external vendors
                includes prefixed identifiers that need to be aligned with internal
                formats.

        Args:
            prefix: The prefix to remove from each string.
                        Can also be a Polars expression that evaluates to a string.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with the specified prefix removed.

        Examples:
            **Scalar Example: Removing 'TEMP-' prefix from temporary policy IDs**

            Scenario: You have a column of policy IDs where some are temporary and
            prefixed with "TEMP-". You need to clean these IDs by removing the prefix.

            ```python
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl

            data_strip_prefix = {
                "policy_id_raw": ["TEMP-001", "TEMP-002", "003", None, "TEMP-004", "POL-005"],
                "processing_prefix": ["TEMP-", "TEMP-", "TEMP-", "TEMP-", "TEMP-", "POL-"]
            }
            af = ActuarialFrame(data_strip_prefix)

            # Example 1a: Strip a fixed prefix "TEMP-"
            af_stripped_fixed = af.select(
                af["policy_id_raw"].str.remove_prefix("TEMP-").alias("cleaned_id_fixed")
            )
            print("Stripped with fixed prefix 'TEMP-' using remove_prefix:")
            print(af_stripped_fixed.collect())

            # Example 1b: Strip prefix defined in another column
            af_stripped_dynamic = af.select(
                af["policy_id_raw"].str.remove_prefix(pl.col("processing_prefix")).alias("cleaned_id_dynamic")
            )
            print("\nStripped with dynamic prefix from 'processing_prefix' column using remove_prefix:")
            print(af_stripped_dynamic.collect())
            ```

            ```text
            Stripped with fixed prefix 'TEMP-' using remove_prefix:
            shape: (6, 1)
            ┌──────────────────┐
            │ cleaned_id_fixed │
            │ ---              │
            │ str              │
            ╞══════════════════╡
            │ 001              │
            │ 002              │
            │ 003              │
            │ null             │
            │ 004              │
            │ POL-005          │
            └──────────────────┘

            Stripped with dynamic prefix from 'processing_prefix' column using remove_prefix:
            shape: (6, 1)
            ┌────────────────────┐
            │ cleaned_id_dynamic │
            │ ---                │
            │ str                │
            ╞════════════════════╡
            │ 001                │
            │ 002                │
            │ 003                │
            │ null               │
            │ 004                │
            │ 005                │
            └────────────────────┘
            ```

            **Vector (List Shimming) Example: Removing 'LEGACY-' prefix from lists of product feature codes**

            Scenario: A policy has a list of associated feature codes, some of which
            are from a legacy system and prefixed with "LEGACY-".

            ```python
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl

            data_list = {
                "policy_key": ["POLICY_A", "POLICY_B"],
                "feature_codes_raw": [
                    ["LEGACY-RIDER1", "NEW_FEATURE_X", "LEGACY-BENEFIT2"],
                    [None, "LEGACY-COVERAGE_Y", "STANDARD_Z"]
                ]
            }
            af_list = ActuarialFrame(data_list)
            af_list = af_list.with_columns(
                af_list["feature_codes_raw"].cast(pl.List(pl.String))
            )
            af_list_stripped = af_list.select(
                af_list["feature_codes_raw"].str.remove_prefix("LEGACY-").alias("cleaned_feature_codes")
            )
            # Use pl.Config to ensure consistent output for doctest
            with pl.Config(fmt_str_lengths=100):
                print(af_list_stripped.collect())
            ```

            ```text
            shape: (2, 1)
            ┌────────────────────────────────────────────┐
            │ cleaned_feature_codes                      │
            │ ---                                        │
            │ list[str]                                  │
            ╞════════════════════════════════════════════╡
            │ ["RIDER1", "NEW_FEATURE_X", "BENEFIT2"]    │
            │ [null, "COVERAGE_Y", "STANDARD_Z"]         │
            └────────────────────────────────────────────┘
            ```
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
            ```
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

            ```
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
            ```
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

            ```
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

            ```
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

            ```
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

            ```
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

            ```
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
        """Check if strings end with a specific substring.

        This method returns a boolean expression showing whether each string
        value ends with the provided suffix. For columns containing
        `List[String]`, the check is applied to every element within each list.

        !!! note "When to use"
            Use this function when you need to:
            * Verify that policy identifiers end with region or product codes.
            * Flag claim or log entries that end with status markers like "OK"
              or "PENDING".
            * Validate strings against suffixes supplied in another column, such
              as checking payout account numbers.

        Args:
            suffix: The substring to test for at the end of each string. It can
                be a literal value or a Polars expression.

        Returns:
            ExpressionProxy: A boolean result indicating whether each string
            ends with ``suffix``. For list columns, the result is a list of
            booleans.

        Examples
        --------
        Scalar example – region codes::

            ```python
            from gaspatchio_core.frame.base import ActuarialFrame

            af = ActuarialFrame({
                "policy_id": ["P100-US", "P101-CA", "P102-US", None, "P103-EU"]
            })
            result = af.select(
                af["policy_id"].str.ends_with("-US").alias("is_us_policy")
            )
            print(result.collect())
            ```

            ```text
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
            ```

        Vector (list) example – status flags::

            ```python
            from gaspatchio_core.frame.base import ActuarialFrame
            import polars as pl

            logs = {
                "policy_id": ["A100", "A101"],
                "update_notes": [
                    ["Issued OK", "Review PENDING"],
                    [None, "Paid OK"],
                ],
            }
            af_logs = ActuarialFrame(logs)
            af_logs = af_logs.with_columns(
                af_logs["update_notes"].cast(pl.List(pl.String))
            )
            status_ok = af_logs.select(
                af_logs["update_notes"].str.ends_with("OK").alias("ends_with_ok")
            )
            print(status_ok.collect())
            ```

            ```text
            shape: (2, 1)
            ┌───────────────┐
            │ ends_with_ok  │
            │ ---           │
            │ list[bool]    │
            ╞═══════════════╡
            │ [true, false] │
            │ [null, true]  │
            └───────────────┘
            ```
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
        return self._call_string_method("extract_all", pattern=pattern)

    def replace(
        self,
        pattern: str | pl.Expr,
        value: str | pl.Expr,
        literal: bool = False,
        n: int = 1,
    ) -> "ExpressionProxy":
        return self._call_string_method(
            "replace", pattern=pattern, value=value, literal=literal, n=n
        )

    def replace_all(
        self, pattern: str | pl.Expr, value: str | pl.Expr, literal: bool = False
    ) -> "ExpressionProxy":
        return self._call_string_method(
            "replace_all", pattern=pattern, value=value, literal=literal
        )

    def split(self, by: str | pl.Expr, inclusive: bool = False) -> "ExpressionProxy":
        return self._call_string_method("split", by=by, inclusive=inclusive)

    def slice(
        self, offset: int | pl.Expr, length: Optional[int | pl.Expr] = None
    ) -> "ExpressionProxy":
        return self._call_string_method("slice", offset=offset, length=length)
