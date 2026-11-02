# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A division and a product the compiler performs as written: one IEEE operation each.

Every floating-point division a lowering writes goes through
:func:`divided`, because XLA's algebraic simplifier is entitled to rewrite a
quotient into a different one, and every rewrite it knows moves the answer
by a unit in the last place somewhere -- which is where the reference
producer, dividing each element by its own divisor, and this engine would
part company:

- ``a / c``, a constant or a broadcast one, becomes ``a * (1 / c)``:
  ``444391 / 10`` is ``44439.1`` and ``444391 * 0.1`` is
  ``44439.100000000006``;
- ``a / pow(b, e)`` becomes ``a * pow(b, -e)`` -- a discount by
  ``(1 + r) ** t``, a rounding by ``10 ** k`` -- and ``a / exp(b)`` and
  ``a / sqrt(b)`` their own products;
- ``(a / b) / c`` becomes ``a / (b * c)``, and ``a / (b / c)`` becomes
  ``(a * c) / b``, so a quotient of a quotient is not two quotients.

Each rewrite matches the *form* of an operand: a constant, a power, an
exponential, another division. :func:`apart` hands both operands to the
division in a form none of them matches -- a selection that depends on the
data -- whatever the operands are, on any backend, in any order the
compiler runs its passes.

**A product is rounded before anything reads it.** XLA's CPU backend lets a
multiply that feeds an addition fuse with it into one multiply-add, which
rounds once where 11.1.25 rounds the product and then the sum. Inside the
agreement band that is a unit in the last place; under a comparison, a
``when``, a floor or a remainder it is a whole step -- ``0.5 + 5 * 0.011 >=
0.555`` answered 1 here and 0 on the reference producer (audit C2-F2).
:func:`multiplied` hands the product on through the same
data-dependent selection, so no addition reads it before it is rounded.

A data-dependent selection rather than an optimization barrier, because
where a barrier is expanded is the compiler's own pipeline: on jax 0.4.38's
CPU backend it is expanded straight after the first simplification, so its
protection is an accident of pass order, and on a GPU it is kept through
fusion and costs a round trip through memory. A selection costs a compare
per element, fused into the loop the division is already in.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import jax.numpy as jnp

if TYPE_CHECKING:
    import jax

__all__ = ["Operand", "apart", "divided", "multiplied"]

# An operand is an array, or a number the lowering wrote -- a literal step,
# a day count, the one over which a discount is taken.
type Operand = jax.Array | float


def apart(value: Operand, witness: Operand) -> jax.Array:
    """Return ``value`` as an operand the compiler cannot rewrite by its form.

    The witness where the witness is NaN, ``value`` everywhere else. A caller
    passes a witness that is NaN wherever its own answer is NaN anyway, so
    the answer is the same number either way; what the selection buys is that
    ``value`` is no longer a constant, a power, a quotient or a product
    feeding a subtraction, as far as the compiler can prove -- it depends on
    the data.

    The witness should vary as finely as the expression does. One that varies
    only per policy, beside an expression that varies per period, lets LLVM
    hoist the choice out of the loop over the periods and rewrite what is
    left inside it.
    """
    return jnp.where(jnp.isnan(witness), witness, value)


def divided(numerator: Operand, divisor: Operand) -> jax.Array:
    """Return ``numerator / divisor``, one IEEE division per element.

    Both operands are held apart under one witness, their sum. It is NaN
    where either is NaN, and where they are infinities of opposite sign --
    and in each of those cases the quotient is NaN too, so the selection
    never changes a number. It depends on the data whenever either operand
    does, and it varies element by element as the wider of the two does:
    a witness taken from one operand alone would be a constant beside a
    literal, which the compiler folds, or a per-policy value beside a
    per-period one, which it hoists out of the loop over the periods. A
    zero divisor gives IEEE's signed infinity, or NaN over nought, as
    11.1.25 states.
    """
    witness = numerator + divisor
    return apart(numerator, witness) / apart(divisor, witness)


def multiplied(left: Operand, right: Operand) -> jax.Array:
    """Return ``left * right``, rounded before any addition can read it.

    The product is held apart under one witness, ``|left| + |right|``. It is
    NaN exactly where either operand is, and the product is NaN there too, so
    the selection never changes a number -- an infinity against a nought
    makes the product NaN and leaves the witness infinite, which the
    selection passes through untouched. Unlike either operand alone, the
    witness varies element by element as the wider of the two does, so a
    per-policy factor beside a per-period one cannot be hoisted out of the
    loop over the periods and the product fused with what reads it there.
    """
    witness = jnp.abs(left) + jnp.abs(right)
    return apart(left * right, witness)
