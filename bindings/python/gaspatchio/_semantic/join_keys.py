# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""How a join's key columns are written into its record, and read back out.

A join's record states its keys in one flat attribute, ``on`` -- a call's
attribute is a single typed value, never a container -- and section 11.1.2 of
the specification spells it: one key is its own name, several are separated by
``,`` in the order they were given, and where the two sides name the key
differently the attribute is this frame's keys, ``=``, then the other table's.

Both halves live here so that they cannot come apart. The frame writes the
attribute with :func:`join_on_attribute`; everything that reads it -- the
graph's lineage, the execution inspector, an engine binding the key -- reads it
with :func:`join_key_sides`, exactly as written: a name is every character
between the separators, spaces included, because a column called ``" code "``
is a different column from one called ``"code"``. A name holding either
separator cannot be written so that it reads back as itself, so
:func:`unwritable_join_keys` names it for the frame to refuse before the join
happens.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "KEY_SEPARATOR",
    "SIDE_SEPARATOR",
    "join_key_sides",
    "join_on_attribute",
    "unwritable_join_keys",
]

# Between two keys on one side.
KEY_SEPARATOR: Final[str] = ","

# Between this frame's keys and the other table's, where they are named apart.
SIDE_SEPARATOR: Final[str] = "="


def _names(keys: str | Sequence[str] | None) -> list[str]:
    """Return one side's key names as a list, however the caller wrote them."""
    if keys is None:
        return []
    if isinstance(keys, str):
        return [keys]
    return list(keys)


def join_on_attribute(
    on: str | Sequence[str] | None,
    left_on: str | Sequence[str] | None,
    right_on: str | Sequence[str] | None,
) -> str | None:
    """Return a join's keys as the one attribute value its record carries.

    ``on=["policy_id", "product_code"]`` is ``"policy_id,product_code"``;
    ``left_on="pol_num", right_on="policy_id"`` is ``"pol_num=policy_id"``. A
    join with no keys at all -- a cross join -- has nothing to name, so the
    attribute is None rather than an empty string that would read as a key
    nobody wrote.

    Args:
        on: The key columns both sides share, or None.
        left_on: This frame's key columns, where the sides name them apart.
        right_on: The other table's key columns, in the same order.

    Returns:
        The attribute value, or None for a join that states no key.

    Examples:
        >>> join_on_attribute(["product_code", "issue_age"], None, None)
        'product_code,issue_age'
        >>> join_on_attribute(None, "pol_num", "policy_id")
        'pol_num=policy_id'
        >>> join_on_attribute(None, None, None) is None
        True

    """
    if on is not None:
        return KEY_SEPARATOR.join(_names(on))
    if left_on is None and right_on is None:
        return None
    this_frame = KEY_SEPARATOR.join(_names(left_on))
    other_table = KEY_SEPARATOR.join(_names(right_on))
    return f"{this_frame}{SIDE_SEPARATOR}{other_table}"


def join_key_sides(stated: object) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return the key columns a join's ``on`` attribute names, on each side.

    This frame's keys first, then the other table's, each in the order the
    attribute lists them. Where the attribute names one set of keys, both
    sides share it. Names are read exactly as written -- nothing is trimmed --
    so a key with a space in it binds to the column that has one. An
    attribute that is absent or not text names no key, which is a cross join.

    Args:
        stated: The ``on`` attribute as the record carries it.

    Returns:
        This frame's key columns and the other table's.

    Examples:
        >>> join_key_sides("product_code,issue_age")
        (('product_code', 'issue_age'), ('product_code', 'issue_age'))
        >>> join_key_sides("pol_num=policy_id")
        (('pol_num',), ('policy_id',))
        >>> join_key_sides(" code ")
        ((' code ',), (' code ',))
        >>> join_key_sides(None)
        ((), ())

    """
    if not isinstance(stated, str) or not stated:
        return (), ()
    left, sides, right = stated.partition(SIDE_SEPARATOR)
    this_frame = tuple(left.split(KEY_SEPARATOR)) if left else ()
    if not sides:
        return this_frame, this_frame
    return this_frame, tuple(right.split(KEY_SEPARATOR)) if right else ()


def unwritable_join_keys(
    on: str | Sequence[str] | None,
    left_on: str | Sequence[str] | None,
    right_on: str | Sequence[str] | None,
) -> list[str]:
    """Return the key names the ``on`` attribute cannot carry, in the order given.

    A name holding ``,`` or ``=`` would read back as two names, or as a name
    on each side; an empty name would read back as none at all. Either way the
    record would name different keys from the ones the join used.

    Args:
        on: The key columns both sides share, or None.
        left_on: This frame's key columns, where the sides name them apart.
        right_on: The other table's key columns, in the same order.

    Returns:
        Each name that cannot be written, once, in the order it was given.

    Examples:
        >>> unwritable_join_keys("prod,code", None, None)
        ['prod,code']
        >>> unwritable_join_keys(None, ["a=b", "age"], ["x", "age"])
        ['a=b']
        >>> unwritable_join_keys("product_code", None, None)
        []

    """
    found: list[str] = []
    for name in (*_names(on), *_names(left_on), *_names(right_on)):
        cannot = not name or KEY_SEPARATOR in name or SIDE_SEPARATOR in name
        if cannot and name not in found:
            found.append(name)
    return found
