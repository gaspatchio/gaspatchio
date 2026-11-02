# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A JAX engine over the gaspatchio graph artifact's executable profile.

Importing this package is what puts the engine within reach: the core knows
the *name* ``jax`` and the module this lives in, and reaches for it only when
somebody asks for that name. So a core installation without this package
installed loads none of jax's dependencies, which is what the core's
clean-process test holds it to.

**Two things happen at import, and both have to happen before anything is
compiled.** The persistent compilation cache is pointed at the user's cache
directory, because XLA reads that location when it first compiles and never
again; and 64-bit values are turned on.

**x64 is enabled here, and a refusal is the alternative.** JAX defaults to
32-bit floats and 32-bit integers. Every value this engine holds is the type
the node record declares -- ``f64`` in float64, ``i64`` in int64, the widths
section 10 of the specification states -- and none of that is available at
32 bits: a reserve in float32 is wrong in the sixth digit and an integer in
int32 has left the range before a policy count gets interesting. So the flag
is set at import, read back, and a failure to set it refuses the package
rather than letting a run produce numbers in the wrong width and publish
them.
"""

from __future__ import annotations

import jax

from gaspatchio.engines import register_engine
from gaspatchio.engines.report import EngineRefusal, Refusal, RunReport

from .cache import configure
from .engine import JaxEngine

__all__ = ["JaxEngine", "__version__"]

__version__ = "0.1.0rc1"

# The flag, and the reading back of it. Two steps rather than one, because a
# jax configured elsewhere in the process can refuse the update quietly, and a
# package that assumed it took would be publishing float32 reserves.
_X64 = "jax_enable_x64"

# Where the widths are stated: section 10's typing table carries an i64 as a
# signed 64-bit integer and an f64 as a double, for execution.
_WIDTHS = "10"


def _enable_x64() -> None:
    """Turn on 64-bit values, or refuse the package by name.

    Raises:
        EngineRefusal: If x64 cannot be enabled in this process.

    """
    # jax ships no annotations for either call, and both are one line into a
    # library this package does not own; a typed wrapper would be the same
    # call with a signature written on the outside of it.
    jax.config.update(_X64, True)  # type: ignore[no-untyped-call]  # noqa: FBT003 -- the flag's own API takes a bare bool
    if bool(jax.config.read(_X64)):  # type: ignore[no-untyped-call]
        return
    raise EngineRefusal(
        RunReport(
            refusals=(
                Refusal(
                    group="tree",
                    where="jax",
                    count=None,
                    what=(
                        "this process could not enable jax's 64-bit values "
                        "(jax_enable_x64), so every value would be held at "
                        "half the width the artifact declares"
                    ),
                    move=(
                        "import gaspatchio_jax before anything else configures "
                        "jax, or unset JAX_ENABLE_X64 if something has pinned "
                        "it off"
                    ),
                    clause=_WIDTHS,
                ),
            ),
            notes=(),
        )
    )


_enable_x64()
# Before anything is compiled, which is the only moment XLA reads it. A run
# that turned the cache on later would write nothing and read nothing, and
# every second run of a model would pay the compiler again.
configure()
register_engine("jax", JaxEngine)
