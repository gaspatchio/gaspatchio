"""A simple module fixture for testing docstring parsing and validation."""


class SimpleDateTimeProcessor:
    """A simple class that processes date strings."""

    def __init__(self, data_source: str):
        self.data_source = data_source

    def get_year(self, date_input: str) -> str:
        """Extract the year from a given date input.

        Examples:
        ---------
        ```python
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

        Examples:
        ---------
        ```python
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
        (No examples for this one)
        """
        if not isinstance(date_input, str) or len(date_input) < 10:
            raise ValueError("Invalid date string format")
        return date_input[8:10]


def utility_function(name: str, value: int = 0) -> str:
    """
    A simple utility function with a docstring.

    Args:
        name (str): The name to include in the greeting.
        value (int): A numerical value.

    Returns:
        str: A greeting string.
    """
    return f"Hello, {name}! Value is {value}."


def module_level_function_simple():
    """A simple module level function with no examples."""
    return "module_level_output"
