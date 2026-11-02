# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The traced run's panel and the default block answer to one standard of proof.

A collect-time failure is diagnosed on one of two paths. The default path
replays through ``search_collect_failure``: only the classes the tuple
admits, the replayed error's leading line must match the original's, a
second definition that also reproduces makes the window ambiguous and
nothing is named, and a window whose plan will not rebuild is passed over.
The traced run's panel (``--mode debug``) built the base
``ErrorBoundaryFinder`` instead -- class-only, no leading-line check, no
ambiguity pass, not admitted by the tuple -- over the live window alone. So
the same model answered two ways depending on a flag: two lookups on one
table, both broken with one first line, were refused by the block and named
``rate_a`` by the panel, at its own line, for a message that may have been
``rate_b``'s.

The panel path now calls the same search the block does, and renders its
record as the panel or its refusal through the same ``_attribution_text``.
Pinned here: the two-breaks shape under the flag is refused exactly as it
is without it, the healed shape is refused too, a plain dtype failure still
gets its panel, a panel that cannot be built degrades to the block, and the
search hands the panel the state the named calculation ran on.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
from gaspatchio.errors.boundary import (
    AmbiguousAttribution,
    ErrorBoundaryFinder,
    _AttributionReplayFinder,
)
from gaspatchio.errors.formatter import FriendlyErrorFormatter
from gaspatchio.frame.calculations import CalculationRecord

# ``search_collect_failure`` is imported inside the two tests that read it,
# so that at a package without it the behaviour pins above still collect and
# fail on behaviour rather than the whole file failing to import.

# The labels a user reads, spelled out rather than imported: these tests are
# the record of what each path carries.
NAMED = "Failing column:"
REFUSAL = "Not attributed:"
PANEL = "Calculation Error"


@pytest.fixture(autouse=True)
def _enhanced_error_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the ambient error mode -- earlier suites leak ``AF_ERROR_MODE``."""
    monkeypatch.setenv("AF_ERROR_MODE", "enhanced")


def _table(name: str) -> Table:
    """Build an age table covering 30, 40 and 50, registered under its own name."""
    return Table(
        name=name,
        source=pl.DataFrame({"age": [30, 40, 50], "rate": [0.001, 0.002, 0.003]}),
        dimensions={"age": "age"},
        value="rate",
    )


def _policies() -> pl.DataFrame:
    """Build two policies: ``dur_a`` misses on the second, ``dur_b`` on the first."""
    return pl.DataFrame(
        {
            "policy_id": [1, 2],
            "status": ["IF", "LAPSED"],
            "issue_age": [30, 40],
            "dur_a": [0, 59],
            "dur_b": [69, 0],
        }
    )


def _two_breaks(name: str, *, traced: bool) -> ActuarialFrame:
    """Both lookups broken, one first line, no filter: the refusal's own shape."""
    table = _table(name)
    af = ActuarialFrame(_policies())
    af._traced_run = traced  # noqa: SLF001 -- the flag the trace decorator sets
    af.rate_a = table.lookup(age=af.issue_age + af.dur_a)
    af.rate_b = table.lookup(age=af.issue_age + af.dur_b)
    return af


def _healed_then_a_break(name: str, *, traced: bool) -> ActuarialFrame:
    """Build the healed shape: healthy lookup, real break, a filter that heals it."""
    af = _two_breaks(name, traced=traced)
    return af.filter(pl.col("status") == "IF")


def _dtype_break(*, traced: bool) -> ActuarialFrame:
    """Build a string times a float: one column, one plain failure."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "product_code": ["TERM", "WL"],
                "sum_assured": [1.0, 2.0],
            }
        )
    )
    af._traced_run = traced  # noqa: SLF001 -- the flag the trace decorator sets
    af.reserve_factor = pl.col("product_code") * pl.col("sum_assured")
    return af


def _failure(af: ActuarialFrame) -> BaseException:
    """Collect ``af``, which must fail, and return what it raised."""
    with pytest.raises(Exception) as excinfo:  # noqa: PT011 -- the class is the shape's
        af.collect()
    return excinfo.value


def _refusal_line(message: str) -> str:
    return next(line.strip() for line in message.splitlines() if REFUSAL in line)


# --- the defect: two standards ----------------------------------------------


def test_two_breaks_under_a_traced_run_are_refused_as_they_are_without_it() -> None:
    """The panel named ``rate_a`` where the block refused; now both refuse alike.

    The refusal lines are compared whole: the same helper writes both
    models, so the columns and the lines they were written at agree, and a
    panel that had been built would have replaced the message entirely.
    """
    traced = str(_failure(_two_breaks("one_finder_traced", traced=True)))
    plain = str(_failure(_two_breaks("one_finder_plain", traced=False)))

    assert REFUSAL in traced
    assert PANEL not in traced
    assert "Operation:" not in traced
    assert NAMED not in traced
    assert _refusal_line(traced) == _refusal_line(plain)


def test_a_healed_lookup_under_a_traced_run_is_refused_too() -> None:
    """The healed shape, traced.

    Already refused before this change, and for a reason worth recording:
    with nothing written after the filter the live window is empty, the
    base finder answered "no operations to search", built no panel, and the
    default path's refusal followed. It is pinned so the two paths cannot
    part company on it again.
    """
    message = str(_failure(_healed_then_a_break("one_finder_healed", traced=True)))

    assert REFUSAL in message
    assert PANEL not in message
    assert "Operation: rate_a" not in message
    assert NAMED not in message


# --- the shapes that stay right ---------------------------------------------


def test_a_plain_dtype_failure_under_a_traced_run_still_gets_its_panel() -> None:
    """One column, one failure: the panel is built, and it carries the graph's lines."""
    raised = _failure(_dtype_break(traced=True))
    message = str(raised)

    assert PANEL in message
    assert "Operation: reserve_factor" in message
    assert raised._enhanced_processed is True  # noqa: SLF001 -- the panel path's marker
    assert "Blocks: nothing downstream" in message
    assert "Reading:" not in message


def test_a_panel_that_cannot_be_built_degrades_to_the_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The finder named a record; the panel raised; the terse block delivers it."""

    def _broke(_self: FriendlyErrorFormatter) -> str:
        msg = "the panel broke"
        raise TypeError(msg)

    monkeypatch.setattr(FriendlyErrorFormatter, "format_error", _broke)

    raised = _failure(_dtype_break(traced=True))
    message = str(raised)

    assert PANEL not in message
    assert "Failing column: 'reserve_factor'" in message
    assert raised._column_attributed is True  # noqa: SLF001 -- the block's marker
    assert not hasattr(raised, "_enhanced_processed")
    assert "the panel broke" not in message


# --- the mechanism ------------------------------------------------------------


def test_a_traced_run_builds_the_attribution_finder_and_no_other(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The base finder is not built on the traced path any more."""
    built: list[str] = []
    real_init = ErrorBoundaryFinder.__init__

    def _counting(self: ErrorBoundaryFinder, *args: object, **kwargs: object) -> None:
        built.append(type(self).__name__)
        real_init(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(ErrorBoundaryFinder, "__init__", _counting)

    _failure(_two_breaks("one_finder_built", traced=True))

    assert built
    assert set(built) == {_AttributionReplayFinder.__name__}


def test_the_search_hands_the_panel_the_state_the_named_calculation_ran_on() -> None:
    """A name travels with the frame it was applied to: the state the panel previews."""
    from gaspatchio.errors.boundary import search_collect_failure

    af = _dtype_break(traced=False)
    raised = _failure(af)

    attribution, last_good = search_collect_failure(af, raised)

    assert isinstance(attribution, CalculationRecord)
    assert attribution.column == "reserve_factor"
    assert isinstance(last_good, pl.DataFrame)
    assert last_good.columns == ["policy_id", "product_code", "sum_assured"]


def test_the_search_hands_back_no_state_for_a_refusal() -> None:
    """Nothing is named, so there is no state a panel could honestly preview."""
    from gaspatchio.errors.boundary import search_collect_failure

    af = _two_breaks("one_finder_state", traced=False)
    raised = _failure(af)

    attribution, last_good = search_collect_failure(af, raised)

    assert isinstance(attribution, AmbiguousAttribution)
    assert last_good is None
