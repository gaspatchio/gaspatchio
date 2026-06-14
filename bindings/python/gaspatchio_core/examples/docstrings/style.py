# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Style validation for docstring code examples.

ABOUTME: Style validation for docstring code examples
ABOUTME: Detects and reports style violations with helpful suggestions
"""

from __future__ import annotations

import ast
import keyword
from typing import Protocol, TypedDict


class StyleViolation(TypedDict):
    """Structure for a single style violation."""

    code: str  # e.g., "GP001"
    message: str  # Human-readable violation message
    line: int  # Line number in snippet (1-indexed)
    column: int  # Column number (0-indexed)
    suggestion: str | None  # Optional suggestion for fixing


class StyleRule(Protocol):
    """Protocol for style checking rules."""

    def check(self, code: str) -> list[StyleViolation]:
        """Check code for violations of this rule.

        Args:
            code: The code snippet to check

        Returns:
            List of violations found

        """
        ...

    @property
    def code(self) -> str:
        """The rule code (e.g., 'GP001')."""
        ...

    @property
    def name(self) -> str:
        """Human-readable rule name."""
        ...


class BracketNotationRule:
    """Detects bracket notation (af["column"]) and suggests af.column.

    This rule checks for subscript operations like af["column_name"] where:
    1. The object being subscripted appears to be an ActuarialFrame
       (variable named 'af' or similar)
    2. The subscript is a string literal
    3. The string is a valid Python identifier (not a keyword, no
       underscores, etc.)

    When these conditions are met, suggests using attribute notation instead.
    """

    code: str = "GP001"
    name: str = "Prefer attribute notation over bracket notation"

    def check(self, code: str) -> list[StyleViolation]:
        """Check for bracket notation that could be attribute notation."""
        violations: list[StyleViolation] = []

        try:
            tree = ast.parse(code)
        except SyntaxError:
            # If code doesn't parse, skip style checking (linting will catch it)
            return violations

        # Walk the AST looking for subscript operations
        for node in ast.walk(tree):
            # Check if this is a simple string subscript (af["column"])
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)
                and self._should_use_attribute_notation(node.slice.value)
            ):
                column_name = node.slice.value
                # Get the name of the object being subscripted
                obj_name = self._get_object_name(node.value)

                if obj_name:
                    msg = (
                        f"Use attribute notation '{obj_name}.{column_name}' "
                        f"instead of '{obj_name}[\"{column_name}\"]'"
                    )
                    violation = StyleViolation(
                        code=self.code,
                        message=msg,
                        line=node.lineno,
                        column=node.col_offset,
                        suggestion=f"{obj_name}.{column_name}",
                    )
                    violations.append(violation)

        return violations

    def _should_use_attribute_notation(self, name: str) -> bool:
        """Check if a name is eligible for attribute notation.

        Args:
            name: The column name to check

        Returns:
            True if attribute notation should be used, False otherwise

        """
        # Must be a valid Python identifier
        if not name.isidentifier():
            return False

        # Must not be a Python keyword
        if keyword.iskeyword(name):
            return False

        # Must not start with underscore (private/protected naming convention)
        return not name.startswith("_")

    def _get_object_name(self, node: ast.expr) -> str | None:
        """Extract the name of the object being subscripted.

        Args:
            node: The AST node representing the object

        Returns:
            The object name (e.g., "af") or None if not a simple name

        """
        if isinstance(node, ast.Name):
            return node.id
        # Could extend to handle more complex cases like af.select()[0] etc.
        return None


class ImplicitOutputRule:
    """Detects expressions that produce output but lack output blocks.

    When a code example ends with an expression (not a statement), the output
    should be explicitly documented. This rule helps catch missing output blocks.
    """

    code: str = "GP002"
    name: str = "Expression requires output block"

    def check(self, _code: str) -> list[StyleViolation]:
        """Check for expressions that need output documentation."""
        violations: list[StyleViolation] = []

        # This is a simplified version - the full implementation would need
        # access to whether an output block exists, which requires integration
        # with the DocstringCodeExample model
        # For now, return empty - this will be implemented as needed

        return violations


class StyleChecker:
    """Orchestrates running multiple style rules on code snippets."""

    def __init__(self, enabled_rules: list[str] | None = None) -> None:
        """Initialize the style checker.

        Args:
            enabled_rules: List of rule codes to enable (e.g., ["GP001", "GP002"]).
                          If None, all rules are enabled.

        """
        # Registry of all available rules
        self._all_rules: list[StyleRule] = [
            BracketNotationRule(),
        ]

        # Filter to enabled rules
        if enabled_rules is None:
            self._enabled_rules = self._all_rules
        else:
            self._enabled_rules = [
                rule for rule in self._all_rules if rule.code in enabled_rules
            ]

    def check(self, code: str) -> list[StyleViolation]:
        """Run all enabled rules on the code.

        Args:
            code: The code snippet to check

        Returns:
            List of all violations found across all rules, sorted by line number

        """
        violations: list[StyleViolation] = []

        for rule in self._enabled_rules:
            violations.extend(rule.check(code))

        # Sort by line number for consistent reporting
        violations.sort(key=lambda v: (v["line"], v["column"]))

        return violations

    def format_violation(self, violation: StyleViolation) -> str:
        """Format a violation as a human-readable message.

        Args:
            violation: The violation to format

        Returns:
            Formatted message string

        """
        msg = f"{violation['code']}: {violation['message']} at line {violation['line']}"
        if violation.get("suggestion"):
            msg += f" (suggest: {violation['suggestion']})"
        return msg
