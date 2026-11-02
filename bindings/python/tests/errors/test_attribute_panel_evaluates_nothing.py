# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The attribute panel looks a type up by name and never runs the name as code.

``AttributeErrorFormatter`` reads the type out of a message of the shape
``type object 'X' has no attribute 'y'`` and lists X's attributes as
did-you-mean suggestions. X is text out of an exception message, and any code
can raise an ``AttributeError`` with any message, so X is looked up -- among
the builtins, or in a module already imported -- and never evaluated. It used
to be handed to ``eval``.
"""

from __future__ import annotations

import builtins

from gaspatchio.errors.formatter import AttributeErrorFormatter

_PROBE = "gaspatchio_attribute_panel_probe"


def test_a_type_name_carrying_code_is_not_run() -> None:
    """Text that would set a builtin if run leaves the builtins untouched.

    The text has no dot in it, so it reaches the branch that read a bare
    name as a builtin type -- the branch that evaluated it.
    """
    smuggled = f'setattr(__import__("builtins"), "{_PROBE}", 1) or str'
    error = AttributeError(f"type object '{smuggled}' has no attribute 'uper'")

    try:
        AttributeErrorFormatter(error).format_error()
        assert not hasattr(builtins, _PROBE)
    finally:
        if hasattr(builtins, _PROBE):
            delattr(builtins, _PROBE)


def test_a_builtin_type_still_offers_its_attributes() -> None:
    """``str`` is found among the builtins, so ``upper`` is suggested."""
    error = AttributeError("type object 'str' has no attribute 'uper'")

    assert "upper" in AttributeErrorFormatter(error).suggestions


def test_a_dotted_type_still_offers_its_attributes() -> None:
    """``datetime.date`` is found in its module, so ``today`` is suggested."""
    error = AttributeError("type object 'datetime.date' has no attribute 'tody'")

    assert "today" in AttributeErrorFormatter(error).suggestions


def test_a_name_that_is_not_a_type_offers_nothing_from_it() -> None:
    """An unknown name is not found, and the panel still renders."""
    error = AttributeError("type object 'NoSuchType' has no attribute 'tody'")

    assert "NoSuchType" in AttributeErrorFormatter(error).format_error()
