# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What a mortality read does when the basis under it is rebuilt mid-process.

A scenario sweep stacks its assumption tables once per batch: each batch
builds one ``Table`` under the same name over that batch's own scenarios,
and the model re-wraps mortality around whatever it was handed. So one
process holds several bases with one name, one convention and different
rates, and each read has to reach the base it was actually written over.

That is the shape these tests hold, in the smallest form that has it --
two bases under one name, two wrappers with identical conventions, two
reads -- because the whole of a shipped sweep was needed to see it break
and none of it was needed to state it.

The wrapper's own digest cannot be the thing that tells the two reads
apart: it covers the convention and the base's name and dimension set,
never the rates, so both wrappers publish the same digest by design. What
tells them apart is the pair the node already carries: the base's **name**,
which is what the read resolves by, and the base's content hash, which is
what the resolved base has to still hold before the read will run.

The mirror shape is here too, and it is why a name alone is not enough
either. Two bases under two names over one set of rates share a content
hash, because a hash of the values is blind to what the table is called.
A read that resolved by that hash could be handed a base the model never
named -- and then look its rates up under *that* name at execution, which
is a wrong number rather than a refusal.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, MortalityTable
from gaspatchio._semantic.ir import Call
from gaspatchio.assumptions import Table, TableSupersededError
from gaspatchio.frame.graph.graph_builder import fold
from gaspatchio.frame.lowering.polars import lower_polars

# One name, the way a batch's stacked table keeps one name across batches.
_NAME = "rebuilt_select_basis"

# The select period both wrappers declare. Identical conventions are the
# point: nothing about the convention distinguishes the two reads.
_SELECT_PERIOD = 3


def _basis_named(name: str, rates: list[float]) -> MortalityTable:
    """Return a select and ultimate basis over ``rates``, under ``name``."""
    table = Table(
        name=name,
        source=pl.DataFrame(
            {
                "age": [40, 40, 40],
                "duration": [1, 2, 3],
                "qx": rates,
            }
        ),
        dimensions={"age": "age", "duration": "duration"},
        value="qx",
    )
    return MortalityTable(
        table=table,
        age_basis="age_last_birthday",
        structure="select_ultimate",
        select_period=_SELECT_PERIOD,
    )


def _basis_over(rates: list[float]) -> MortalityTable:
    """Return a select and ultimate basis over ``rates``, under the shared name.

    Each call registers a ``Table`` under ``_NAME``. Registering a second
    one with different rates supersedes the first, exactly as the next
    batch of a sweep does.
    """
    return _basis_named(_NAME, rates)


def _read(basis: MortalityTable) -> ActuarialFrame:
    """Return a frame whose rate came from ``basis``, read at duration 1."""
    frame = ActuarialFrame(pl.DataFrame({"age": [40], "duration": [1]}))
    frame.qx = basis.at(age=frame.age, duration=frame.duration)
    return frame


class TestABasisRebuiltUnderOneName:
    """A sweep's second batch reads its own rates, not the first batch's."""

    def test_the_second_batch_reads_the_rates_it_was_built_over(self) -> None:
        """The shocked base answers, and the read does not refuse.

        The refusal that used to land here is a real one -- a lookup whose
        table has been superseded would serve the newer values under the
        older object's name, which is how a shock arrives as zero
        sensitivity. What was wrong was the object it fired on: the read
        was handed the first batch's wrapper, because the wrapper digest
        the read resolved by is blind to the rates and both batches print
        the same one.
        """
        base = _read(_basis_over([0.010, 0.020, 0.030]))
        assert base.collect()["qx"].to_list() == pytest.approx([0.010])

        shocked = _read(_basis_over([0.015, 0.030, 0.045]))
        assert shocked.collect()["qx"].to_list() == pytest.approx([0.015])

    def test_a_rebuild_over_the_same_rates_reads_the_same_answers(self) -> None:
        """Byte-identical bases are interchangeable, which is what a hash means."""
        first = _read(_basis_over([0.011, 0.022, 0.033]))
        second = _read(_basis_over([0.011, 0.022, 0.033]))

        assert (
            first.collect()["qx"].to_list()
            == second.collect()["qx"].to_list()
            == pytest.approx([0.011])
        )

    def test_the_wrapper_digest_and_the_base_hash_both_follow_the_rates(self) -> None:
        """Two bases under one name never share an identity on the node.

        Both wrappers have the same convention, table name and dimension
        set, and different rates. ``source_sha()`` carries the base's content
        fingerprint, so the ``mortality`` attribute moves with the rates, and
        so does the ``table_fingerprint`` beside it on the very same node --
        which is still the pair the lowering resolves the base by.

        Each basis is read where a batch would read it, before the next one
        is built, because a wrapper held over a rebuild is a stale object
        and refusing it is the next test's subject.
        """
        digests: list[str] = []
        attrs: list[dict[str, object]] = []
        for rates in ([0.010, 0.020, 0.030], [0.015, 0.030, 0.045]):
            basis = _basis_over(rates)
            digests.append(basis.source_sha())
            tree = fold(_read(basis)).op_trees["qx@1"]
            assert isinstance(tree, Call)
            attrs.append(dict(tree.attrs))

        assert digests[0] != digests[1]
        assert attrs[0]["mortality"] == digests[0]
        assert attrs[1]["mortality"] == digests[1]
        assert attrs[0]["table"] == attrs[1]["table"] == _NAME
        assert attrs[0]["table_fingerprint"] != attrs[1]["table_fingerprint"]

    def test_a_basis_the_next_batch_superseded_is_still_refused(self) -> None:
        """The refusal the guard exists for is untouched, and lands where it is right.

        Resolving by content is not a way around the guard. A wrapper held
        past the rebuild of its own base really would read the newer rates
        under the older object's name -- the zero-sensitivity failure -- and
        a read through it is refused exactly as before. What changed is
        which object a fresh read is handed, not what a stale one may do.
        """
        stale = _basis_over([0.010, 0.020, 0.030])
        _basis_over([0.015, 0.030, 0.045])

        with pytest.raises(TableSupersededError, match="has been superseded"):
            _read(stale)


class TestTwoBasesWithOneSetOfRatesUnderTwoNames:
    """A read answers with the base it named, never with a look-alike.

    That holds where the read is resolved. The expression the resolution
    hands back carries the base's *name*, and the kernel resolves that
    name again at collect time, so a frame held across a rebuild of its
    own name is collected against whatever the name has come to hold --
    the footgun the re-registration warning already names, and not
    something a resolution can answer for. What no test below does, for
    exactly that reason, is hold a built frame across a rebuild of the
    name it reads and collect it afterwards.

    Each test uses rates of its own, because the shape turns on which base
    registered a set of values first and a set shared with another test
    would make that order somebody else's to decide.
    """

    def test_a_read_answers_with_the_base_whose_name_is_on_it(self) -> None:
        """The shape the sweep does not have and an alias does.

        Two tables, two names, one set of rates. The first is read, which
        puts those values in this process under the first name. The second
        is read next -- and if the resolution went by the values it would be
        handed the first table, whose name is the one the lookup then
        resolves by at execution time. Superseding the first name is what
        makes that visible: the second model's read would answer with rates
        it never named, and nothing downstream would say so.
        """
        shared = [0.11, 0.22, 0.33]
        assert _read(_basis_named("alias_read_first", shared)).collect()[
            "qx"
        ].to_list() == pytest.approx([0.11])

        second = _read(_basis_named("alias_read_second", shared))
        _basis_named("alias_read_first", [9.11, 9.22, 9.33])

        assert second.collect()["qx"].to_list() == pytest.approx([0.11])

    def test_the_same_shape_with_nothing_read_first_answers_the_same_way(
        self,
    ) -> None:
        """The control the defect was invisible in.

        Nothing reads the first base, so this process learns those values
        under the second name and a read resolving by values alone happens
        to land on the right table. It answered correctly before and it
        answers correctly now: the point of holding it is that the two
        orders must not disagree.
        """
        shared = [0.12, 0.24, 0.36]
        _basis_named("alias_unread_first", shared)
        second = _read(_basis_named("alias_unread_second", shared))
        _basis_named("alias_unread_first", [9.12, 9.24, 9.36])

        assert second.collect()["qx"].to_list() == pytest.approx([0.12])

    def test_a_read_is_never_refused_in_the_name_of_a_base_it_did_not_name(
        self,
    ) -> None:
        """The refusal that used to name a table appearing nowhere in the model.

        Same two names over one set of rates, with the supersede moved
        ahead of the second model's read. Resolving by values handed that
        read the first table, which had been superseded, so the guard fired
        and named a base the model never wrote -- an actuary's next move
        being to search their own code for a name that is not in it. The
        read names its own base, that base is current, and it answers.
        """
        shared = [0.13, 0.26, 0.39]
        _read(_basis_named("alias_refusal_first", shared)).collect()
        later = _basis_named("alias_refusal_second", shared)
        _basis_named("alias_refusal_first", [9.13, 9.26, 9.39])

        assert _read(later).collect()["qx"].to_list() == pytest.approx([0.13])

    def test_a_recorded_read_lowered_again_after_its_base_moved_is_refused(
        self,
    ) -> None:
        """Verification is a refusal, never a quiet fall back to the values.

        A node is a record, and lowering one again is how anything reads a
        model back. If the base under that name has been rebuilt in the
        meantime, the values the record was written over are not the ones
        this process would answer with, and there is no honest expression
        to build: the refusal names the base, both hashes and the next
        move, so the reader can see which of the two the record wanted.
        """
        recorded = fold(_read(_basis_named("relowered_basis", [0.14, 0.28, 0.42])))
        tree = recorded.op_trees["qx@1"]
        assert isinstance(tree, Call)
        written_over = dict(tree.attrs)["table_fingerprint"]

        _read(_basis_named("relowered_basis", [0.15, 0.30, 0.45]))

        with pytest.raises(TableSupersededError) as refusal:
            lower_polars(tree)

        message = str(refusal.value)
        assert "relowered_basis" in message
        assert str(written_over) in message
        assert "now holds" in message


def _recorded(basis: MortalityTable) -> Call:
    """Return the folded ``mortality.at`` node one read of ``basis`` recorded."""
    tree = fold(_read(basis)).op_trees["qx@1"]
    assert isinstance(tree, Call)
    return tree


def _rates_read(node: Call) -> str:
    """Return the content hash the read recorded in ``node`` was written over."""
    fingerprint = dict(node.attrs)["table_fingerprint"]
    assert isinstance(fingerprint, str)
    return fingerprint


def _rates_under(basis: MortalityTable) -> str:
    """Return the content hash of the base under ``basis``, without reading it.

    Reading is what files a base under its name, and the shape the last
    test holds turns on nothing having read either of two bases -- so the
    hash has to come off the object, not off a node a read left behind.
    """
    return basis.table._registered_sha  # noqa: SLF001 - the emitted attribute


class TestABasisRefusedOnItsWayOut:
    """A base that is about to be refused does not file itself under its name.

    A read is emitted before it is refused: the emission builds the node,
    and the node's attributes include the base's content hash, which is
    put there by the same call that files the base under its name. So a
    wrapper held past its own base's rebuild files a superseded base under
    a name that has moved on, and is refused a moment later -- leaving the
    directory pointing at an object the kernel would never resolve that
    name to.

    Nothing reads rates out of that: a lookup through the superseded
    object refuses on its own guard. What comes out of it is a refusal of
    something valid, and a refusal that misstates which rates the name
    holds -- which is the one thing a door built to be audited may not do.
    """

    def test_a_still_valid_read_re_lowers_after_a_refused_emission(self) -> None:
        """The read was written over the base the name still resolves to.

        A record is re-lowered whenever anything reads a model back, and
        this one names the current base and carries its current rates.
        Nothing about it is stale, so nothing about it should refuse --
        including after a stale sibling was refused under the same name.
        """
        name = "refused_emission_relower"
        stale = _basis_named(name, [0.10, 0.20, 0.30])
        _read(stale)

        recorded = _recorded(_basis_named(name, [0.15, 0.30, 0.45]))
        lower_polars(recorded)

        with pytest.raises(TableSupersededError):
            _read(stale)

        lower_polars(recorded)

    def test_the_refusal_names_the_rates_the_name_now_holds(self) -> None:
        """A refusal states what is true, or it is not worth reading.

        Here the record really is superseded and really should be refused.
        What the reader is owed is the hash the name resolves to *now*, so
        that the two in the message are the record's rates and the
        process's rates. A stale base that filed itself on its way to
        being refused puts a third hash there -- one no live base carries,
        and one an actuary bisecting has no route back from.
        """
        name = "refused_emission_message"
        stale = _basis_named(name, [0.10, 0.20, 0.30])
        stale_rates = _rates_read(_recorded(stale))

        recorded = _recorded(_basis_named(name, [0.15, 0.30, 0.45]))
        written_over = _rates_read(recorded)
        current = _rates_read(_recorded(_basis_named(name, [0.16, 0.32, 0.48])))

        with pytest.raises(TableSupersededError):
            _read(stale)

        with pytest.raises(TableSupersededError) as refusal:
            lower_polars(recorded)

        message = str(refusal.value)
        assert written_over in message
        assert current in message
        assert stale_rates not in message

    def test_a_stale_base_whose_name_never_filed_is_still_a_supersede(self) -> None:
        """Refusing is right; reporting the name as absent from the process is not.

        A sweep that stacks all its batches and *then* runs its models has
        several bases under one name and no read through any of them, so
        nothing has filed that name here at all. A read through an earlier
        wrapper is as wrong as it ever was and is refused -- but what it is
        refused with matters. A miss in this directory was reported as the
        table not existing in this process, which is false while several of
        that name are registered, sends the reader to build a table they
        have already built, and hands a bare ``KeyError`` to code that
        catches the documented error.

        What is true is what the other orderings already say: the name has
        moved, and here are the two sets of rates.
        """
        name = "never_read_stale_basis"
        stale = _basis_named(name, [0.10, 0.20, 0.30])
        current = _basis_named(name, [0.15, 0.30, 0.45])

        with pytest.raises(TableSupersededError) as refusal:
            _read(stale)

        message = str(refusal.value)
        assert name in message
        assert _rates_under(stale) in message
        assert _rates_under(current) in message
        assert "does not exist in this process" not in message
