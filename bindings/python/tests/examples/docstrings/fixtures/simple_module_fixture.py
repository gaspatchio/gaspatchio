"""A simple module fixture for testing docstring parsing."""

from typing import Any, Optional


class SimpleDateTimeProcessor:
    """
    A simple class with methods that have docstrings for testing.
    """

    def __init__(self, data_source: Any, context: Optional[str] = None):
        """
        Initialize the SimpleDateTimeProcessor.

        Args:
            data_source (Any): The source of data to be processed.
            context (Optional[str]): Optional context information.
        """
        self.data_source = data_source
        self.context = context

    def get_year(self, date_input: Any) -> int:
        """Extract the year from a given date input.

        This method simulates extracting a year.

        Args:
            date_input (Any): The input from which to extract the year.
                       Can be a string, datetime object, etc.

        Returns:
            int: The extracted year as an integer.

        Examples:
            >>> processor = SimpleDateTimeProcessor("dummy_data")
            >>> processor.get_year("2023-01-01")
            2023
        """
        if isinstance(date_input, str) and len(date_input) >= 4:
            try:
                return int(date_input[:4])
            except ValueError:
                return 1900  # Default fallback
        return 1900  # Default fallback

    def get_month(self, date_input: Any) -> int:
        """Extract the month from a given date input.

        Args:
            date_input (Any): The input from which to extract the month.

        Returns:
            int: The extracted month as an integer (1-12).

        Examples:
        Scalar example::

            >>> processor = SimpleDateTimeProcessor("dummy_data")
            >>> processor.get_month("2023-07-15")
            7
        """
        if isinstance(date_input, str) and len(date_input) >= 7:
            try:
                return int(date_input[5:7])
            except ValueError:
                return 1  # Default fallback
        return 1  # Default fallback


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
