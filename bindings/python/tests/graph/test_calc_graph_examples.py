# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The calculation-graph query examples are executed, not merely displayed.

`gaspatchio/frame/graph/calc_graph.py` answers "what does this read", "what
reads this", "what is behind this" and "what moves with this" in `>>>`
examples, and those examples are the whole published evidence for what a cone
holds. They ran only under `pytest --doctest-modules`, which is not how the
suite is normally invoked -- so an expected cone could be corrupted and the
whole default run stayed green. A documented cone no harness executes is a
claim about a model that nothing checks, which is the one thing a lineage
story cannot afford.

The same holds for the reader that answers those questions from an exported
file (`gaspatchio/graph.py`), whose example is the claim that
the file and the frame agree.

Every example in the module is discovered rather than listed, so an example
added to a query that has none today is enforced from the moment it is
written. The runner uses the option flags pytest's `--doctest-modules` applies
by default, so an example cannot pass by one route and fail by the other.

The module keeps `>>>` examples rather than the fenced-block house style
because that is what `--doctest-modules` executes; the curated docstring
plugin, which reads the fenced style, is not pointed at `calc_graph.py`, so
nothing here is executed twice.
"""

from __future__ import annotations

import doctest
import io

import pytest

from gaspatchio import graph as document
from gaspatchio.frame.graph import calc_graph


def _runnable_examples() -> list[doctest.DocTest]:
    """Every docstring in the query module that carries a runnable example."""
    found = [
        test
        for module in (calc_graph, document)
        for test in doctest.DocTestFinder().find(module)
        if test.examples
    ]
    if not found:
        msg = (
            "no runnable docstring example found in "
            "gaspatchio.frame.graph.calc_graph or gaspatchio.graph -- either the "
            "examples were removed, or the docstrings stopped using '>>>'"
        )
        raise RuntimeError(msg)
    return found


DOCSTRING_EXAMPLES = _runnable_examples()


@pytest.mark.parametrize(
    "documented",
    DOCSTRING_EXAMPLES,
    ids=[test.name.rpartition(".")[2] for test in DOCSTRING_EXAMPLES],
)
def test_calc_graph_docstring_examples_run(documented: doctest.DocTest) -> None:
    """Each example produces exactly the cone its docstring shows."""
    report = io.StringIO()
    # ELLIPSIS is what pytest's --doctest-modules enables by default; matching
    # it keeps the two routes to these examples in agreement.
    runner = doctest.DocTestRunner(optionflags=doctest.ELLIPSIS)
    runner.run(documented, out=report.write)

    assert runner.failures == 0, (
        f"{documented.name}: {runner.failures} docstring example(s) did not "
        f"produce the documented output.\n{report.getvalue()}"
    )
