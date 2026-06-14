# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

class SimpleDateTimeProcessor:
    """A simple class that processes date strings.

    This class takes a data source identifier upon initialization and provides methods
    to extract year, month, and day components from date strings. It is primarily
    used to test docstring parsing for classes and their methods.

    !!! note "When to use"

        Instantiate this class if you need a basic date string processor for testing
        purposes. Its methods demonstrate docstring example extraction and validation.

    Examples:
    ---------
    ```python
    # Define the class for the example
    class SimpleDateTimeProcessor:
        def __init__(self, data_source: str): self.data_source = data_source
        # Add other methods that might be type checked or called if necessary for a valid example
        def get_year(self, date_input: str) -> str: return date_input[:4]
        def get_month(self, date_input: str) -> str: return str(int(date_input[5:7]))
        def get_day(self, date_input: str) -> str: return date_input[8:10]

    processor = SimpleDateTimeProcessor(data_source="test_source")
    print(processor.data_source)
    ```
    ```text
    test_source
    ```
    """

    def __init__(self, data_source: str):
        """Initializes the SimpleDateTimeProcessor.

        Stores the provided data source identifier.

        !!! note "When to use"
            Called when creating a `SimpleDateTimeProcessor` instance. Provides a way
            to associate a data source with the processor, though this is not strictly
            used by the date extraction methods in this illustrative example.

        Args:
            data_source (str): An identifier for the data source.

        Examples:
        ---------
        ```python
        # Define the class for the example
        class SimpleDateTimeProcessor:
            def __init__(self, data_source: str): self.data_source = data_source
            # Add other methods if necessary
            def get_year(self, date_input: str) -> str: return date_input[:4]

        proc = SimpleDateTimeProcessor(data_source="my_data")
        print(proc.data_source)
        ```
        ```text
        my_data
        ```
        """
        self.data_source = data_source

    def get_year(self, date_input: str) -> str:
        """Extract the year from a given date input.

        This method assumes a date string format like 'YYYY-MM-DD' and extracts
        the first four characters as the year. It includes basic error handling for invalid input.

        !!! note "When to use"
            Use this method to get the year part of a date string. Ensure the input string
            is in a format where the year is represented by the first four characters.
            Suitable for testing docstring examples that include self-contained class definitions.

        Examples:
        ---------
        ```python
        # Define needed class for self-contained example
        class SimpleDateTimeProcessor:
            def __init__(self, data_source: str): self.data_source = data_source
            def get_year(self, date_input: str) -> str: return date_input[:4]

        processor = SimpleDateTimeProcessor(\"dummy_data\")
        processor.get_year(\"2023-01-01\")
        ```
        ```text
        2023
        ```
        """
        if not isinstance(date_input, str) or len(date_input) < 4:
            raise ValueError("Invalid date string format")
        return date_input[:4]

    def get_month(self, date_input: str) -> str:
        """Extract the month from a given date input.

        Assumes a date format like 'YYYY-MM-DD' and extracts the month part (characters 5-7).
        It performs minimal validation and converts the month to an integer string (e.g., "07" to "7").

        !!! note "When to use"
            Use to retrieve the month from a date string. Be mindful of the expected input format.
            This method is also a test case for docstring examples that include self-contained
            class definitions for execution.

        Examples:
        ---------
        ```python
        # Define needed class for self-contained example
        class SimpleDateTimeProcessor:
            def __init__(self, data_source: str): self.data_source = data_source
            def get_month(self, date_input: str) -> str: return str(int(date_input[5:7])) # Simplified for example

        processor = SimpleDateTimeProcessor(\"dummy_data\")
        processor.get_month(\"2023-07-15\")
        ```
        ```text
        7
        ```
        """
        if (
            not isinstance(date_input, str)
            or len(date_input) < 7
            or date_input[4] != "-"
            or date_input[7] != "-"
        ):
            # Simplified check for yyyy-mm-dd like structure for month extraction
            # In a real scenario, proper date parsing (e.g., datetime.strptime) would be used.
            try:
                # Attempt to parse to validate structure for month extraction
                # Not a full validation, just enough for this example method
                _ = int(date_input[5:7])
            except ValueError:
                raise ValueError("Invalid date string format for month extraction")
            month_part = date_input[5:7]
            return str(int(month_part))  # Return as integer string e.g. "07" -> "7"
        month_part = date_input[5:7]
        return str(int(month_part))

    def get_day(self, date_input: str) -> str:
        """Extract the day from a given date input.

        This method assumes a date format like 'YYYY-MM-DD' and extracts the day part.
        It contains no executable examples in its docstring, serving as a test case
        for validation of missing examples when they might be expected or desired.

        !!! note "When to use"
            Use to get the day component from a date string. Note that this docstring intentionally
            omits runnable examples to test validation rules concerning missing examples.

        Examples:
        ---------
        ```python
        # This is a placeholder example as the original had none.
        # Define needed class for self-contained example
        class SimpleDateTimeProcessor:
            def __init__(self, data_source: str): self.data_source = data_source
            def get_day(self, date_input: str) -> str: return date_input[8:10]

        processor = SimpleDateTimeProcessor(\"dummy_data\")
        print(processor.get_day(\"2023-04-20\"))
        ```
        ```text
        20
        ```
        """
        if not isinstance(date_input, str) or len(date_input) < 10:
            raise ValueError("Invalid date string format")
        return date_input[8:10]


def utility_function(name: str, value: int = 0) -> str:
    """
    A simple utility function with a docstring.

    This function provides a basic greeting and incorporates a numerical value.
    It is used to test docstring parsing for standalone functions, including arguments and return types.

    !!! note "When to use"
        Call this function when you need a simple greeting string. It serves as a basic
        test case for function-level docstring processing.

    Args:
        name (str): The name to include in the greeting.
        value (int): A numerical value.

    Returns:
        str: A greeting string.

    Examples:
    ---------
    ```python
    # Example for utility_function
    # To make it self-contained for linting, we'd typically define it here or import it.
    # Assuming it's available in the execution scope provided by the test runner for such examples.
    # For a truly isolated snippet, it would need definition or import.
    # However, for testing docstring extraction, we assume the test runner handles scope.
    # For strict linting of the snippet alone, it would fail without this.
    # Let's define it for robust linting of the snippet itself.
    def utility_function(name: str, value: int = 0) -> str:
        return f"Hello, {name}! Value is {value}."

    print(utility_function(name="Alice", value=42))
    ```
    ```text
    Hello, Alice! Value is 42.
    ```
    """
    return f"Hello, {name}! Value is {value}."


def module_level_function_simple():
    """This is a simple module-level function.

    It demonstrates a basic docstring example.

    !!! note "When to use"
        Use this function when you need a straightforward example
        of a module-level function with a docstring.

    Examples:
    ---------
    ```python
    def module_level_function_simple():
        return "module_level_output"
    assert module_level_function_simple() == "module_level_output"
    ```
    """
    return "module_level_output"


def module_level_function_with_params(param1: int, param2: str = "default") -> str:
    """A module level function with parameters and type hints.

    This function demonstrates how parameters, type hints, and default values
    are handled in docstring parsing and display.

    !!! note "When to use"
        Use this function to test docstring processing for functions
        with multiple parameters, type annotations, and default values.

    Args:
        param1 (int): The first parameter, an integer.
        param2 (str, optional): The second parameter, a string. Defaults to "default".

    Returns:
        str: A string combining the parameters.

    Examples:
    ---------
    ```python
    def module_level_function_with_params(param1: int, param2: str = "default") -> str:
        return f"{param1} and {param2}"
    module_level_function_with_params(1, "test") # Corrected example
    '1 and test'
    module_level_function_with_params(5)
    ```
    ```text
    5 and default
    ```
    """
    return f"{param1} and {param2}"


class SimpleClass:
    # ... existing code ...
    pass
