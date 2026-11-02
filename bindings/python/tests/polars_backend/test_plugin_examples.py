# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The plugin docstring examples are executed, not merely displayed.

`gaspatchio/frame/lowering/_polars/plugins.py` documents its Rust-backed expressions
with `>>>` examples. Those only run under `pytest --doctest-modules`, which is
not how the suite is normally invoked -- so four of them sat there showing a
call whose output the docstring claimed was nothing at all, while the call in
fact printed a whole DataFrame. Running them here means the next drift in a
plugin's result is a red test rather than a quietly wrong page of docs.

Every example in the module is discovered rather than listed, so an example
added to a plugin that has none today is enforced from the moment it is
written. The runner uses the option flags pytest's `--doctest-modules` applies
by default, so an example cannot pass by one route and fail by the other.

The module keeps `>>>` examples rather than the fenced-block house style
because that is what `--doctest-modules` executes; the curated docstring
plugin, which reads the fenced style, is not pointed at this file.
"""

from __future__ import annotations

import doctest
import io

import pytest

from gaspatchio.frame.lowering._polars import plugins


def _runnable_examples() -> list[doctest.DocTest]:
    """Every docstring in the plugin module that carries a runnable example."""
    found = [test for test in doctest.DocTestFinder().find(plugins) if test.examples]
    if not found:
        msg = (
            "no runnable docstring example found in "
            "gaspatchio.frame.lowering._polars.plugins -- either the examples were "
            "removed, or the docstrings stopped using '>>>'"
        )
        raise RuntimeError(msg)
    return found


DOCSTRING_EXAMPLES = _runnable_examples()


@pytest.mark.parametrize(
    "documented",
    DOCSTRING_EXAMPLES,
    ids=[test.name.rpartition(".")[2] for test in DOCSTRING_EXAMPLES],
)
def test_plugin_docstring_examples_run(documented: doctest.DocTest) -> None:
    """Each example produces exactly the output its docstring shows."""
    report = io.StringIO()
    # ELLIPSIS is what pytest's --doctest-modules enables by default; matching
    # it keeps the two routes to these examples in agreement.
    runner = doctest.DocTestRunner(optionflags=doctest.ELLIPSIS)
    runner.run(documented, out=report.write)

    assert runner.failures == 0, (
        f"{documented.name}: {runner.failures} docstring example(s) did not "
        f"produce the documented output.\n{report.getvalue()}"
    )
