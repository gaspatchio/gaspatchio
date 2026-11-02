# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The examples a reader is shown of what produced a result are executed.

``_final_schema_manifest`` and ``RunSummary.versions`` answer "which model,
which book, which library?" in ``>>>`` examples, and those examples ran only
under ``pytest --doctest-modules``, which is not how the suite is invoked.
Every example in the two modules is discovered rather than listed, so one
added later is held from the moment it is written, under the option flags
``--doctest-modules`` applies by default.
"""

from __future__ import annotations

import doctest
import io

import pytest

from gaspatchio.engines import reference, report


def _runnable_examples() -> list[doctest.DocTest]:
    """Every docstring in the two modules that carries a runnable example."""
    found = [
        test
        for module in (reference, report)
        for test in doctest.DocTestFinder().find(module)
        if test.examples
    ]
    if not found:
        message = (
            "no runnable docstring example found in gaspatchio.engines.reference "
            "or gaspatchio.engines.report -- either the examples were removed, "
            "or the docstrings stopped using '>>>'"
        )
        raise RuntimeError(message)
    return found


EXAMPLES = _runnable_examples()


@pytest.mark.parametrize("documented", EXAMPLES, ids=[one.name for one in EXAMPLES])
def test_engine_docstring_examples_run(documented: doctest.DocTest) -> None:
    """Each example produces exactly the output its docstring shows."""
    said = io.StringIO()
    runner = doctest.DocTestRunner(optionflags=doctest.ELLIPSIS)
    runner.run(documented, out=said.write)

    assert runner.failures == 0, (
        f"{documented.name}: {runner.failures} docstring example(s) did not "
        f"produce the documented output.\n{said.getvalue()}"
    )
