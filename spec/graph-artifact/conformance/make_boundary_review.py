# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Publish the reviewed clause checklist with resolvable public evidence links.

Stdlib only, and it reads nothing but the published bundles, ``contracts.json``
and the prose below. Run from ``bindings/python`` after any change to the
vectors, then rebuild the index::

    .venv/bin/python ../../spec/graph-artifact/conformance/make_boundary_review.py
    .venv/bin/python ../../spec/graph-artifact/conformance/build_kit.py

``reviewed_boundaries`` is a claim about what a clause's published cases show,
and ``tests/graph/test_operation_vectors.py`` holds it to that: a clause naming
an identifier and claiming a null boundary must have an indexed case with a
null in its inputs. A boundary that was looked at and found unstated belongs in
``limits``.

This file supersedes the copy sealed in the 2026-09-10 contract-closure record.
That copy reproduces the checklist exactly as published on the day, including
11.1.9's claim to have reviewed nullable elements for two scans whose clause
then said nothing about a null; this one is the version the repository builds
from, and 11.1.9 now states the rule those scans follow.
"""

import json
from pathlib import Path

source = Path(__file__).resolve().parent
schemas = source.parents[2] / "bindings/python/gaspatchio/schemas"
tests = schemas.parents[1] / "tests"
contracts = json.loads((source / "contracts.json").read_text())
cases = [
    c
    for p in sorted((schemas / "vectors").glob("*.json"))
    for c in json.loads(p.read_text())["cases"]
]
notes = {
    "10": (
        "Supported typed null scalar/outer/item and empty lists; untyped passengers refuse both profiles without mutation.",
        "No neutral Null or Struct type; unknown remains unresolved history. Raw cut category/Struct outputs still need named supported columns.",
    ),
    "11.1.1": (
        "Synthetic monthly month index, boundary count and empty portfolio; the fixed-step form's step index and its month where a step is whole months.",
        "Reader checks the synthetic month column and the fixed-step step/month columns only. Other axis columns/cadences/horizon doors have producer tests; data-derived unrecorded horizons are not portable replay promises.",
    ),
    "11.1.2": (
        "Left join, key match/miss and empty left portfolio; compare by policy identity.",
        "Right data is supplied in the fixture. General relational replay, cross and full joins, ambiguous encoded names and ordering are not claimed by the reader; semi and anti joins are claimed only as the selection steps of section 7.6, on one key.",
    ),
    "11.1.3": (
        "Inclusive bounds, lower/upper-only, crossed bounds in both shapes, null source, empty portfolio.",
        "Ordered lower-first evaluation is observable for crossed bounds. Nonfinite/mixed-type bounds are not established by these numeric fixtures.",
    ),
    "11.1.4": (
        "Named interval through a label comparison and empty portfolio.",
        "Raw category/include_breaks output has no portable type; implicit label spelling remains producer-specific. Producer emission tests cover both closure modes.",
    ),
    "11.1.5": (
        "Membership equality and nullable input; empty portfolio; a NaN is a member of no set (11.1.26), per policy and per period, and not of a set held per policy that holds a NaN.",
        "Fixture set is an explicit ordered sequence, except the one case whose set is a per-policy column holding a NaN. Unordered Python collections stay engine-native; general expression-supplied sets are not independently certified. A NaN written into a set literal has no document form (a vector cell's non-finite tag is never an operation literal); the producer refuses it where the formula is written, held by producer tests.",
    ),
    "11.1.6": (
        "Simultaneous replacement, unmatched/null preservation, canonical operand order, empty portfolio.",
        "Producer grammar/emission checks cover the mapping spelling; no iterative substitution is inferred.",
    ),
    "11.1.7": (
        "Explicit format, invalid-to-null and strict refusal, empty portfolio; substring/inferred-format capability refusals.",
        "The stdlib reader only implements exact parsing with an explicit format. Producer supports additional format/substring forms; null format is not independently reproducible.",
    ),
    "11.1.8": (
        "Positive/negative values, both tie modes, scalar/list, null, empty portfolio; a negative decimals over doubles and whole numbers in both tie modes, per policy and per period, a reading that is a half only at fifteen digits, a whole number past 2**53, both type limits, and a whole number refused past i64; a stored flag per policy and a comparison per period read as their 0.0/1.0, answering f64; floor and ceil of a whole number past 2**53 and at the edge of i64, answering the i64 itself.",
        "Past 22 places either side of the point, and from 10**37, a producer may answer by its native scaling, and no case claims those bits. A fixed-point decimal under a negative decimals is outside the vocabulary. Significant figures have their own identifier in 11.1.12. A null flag, a mask and a stored run of flags under these three are held by producer tests, not by published cases.",
    ),
    "11.1.9": (
        "Forward/reverse scans, jagged and empty lists, a lost period propagating in each direction, null outer list, empty portfolio; whole-number runs past 2**53 summed and multiplied exactly in both directions, and a running sum or product with a period past i64 refused.",
        "Periods never reduce across policies. Nonfinite scan behavior is not a numerical agreement claim; past i64 a period is outside the portable domain, which the published refusals show.",
    ),
    "11.1.10": (
        "Select/ultimate duration clamp and empty portfolio.",
        "Aggregate/joint producer paths are separately tested. Wrapper identity cannot be independently authenticated from the table payload alone; age basis is descriptive, never converted.",
    ),
    "11.1.11": (
        "Producer signature census, typed attributes, operand order and rejected variants.",
        "This is a grammar checklist, not an additional value identifier. The standalone invocation reader is not a general signature validator.",
    ),
    "11.1.12": (
        "Ten named elementary functions in scalar/list form, nullable cells, exact/toleranced values and empty portfolio; norm_cdf against a 60-digit Phi through the body, both tails to -37.5, the subnormal and underflowed answers under the line rule, and its exact null, NaN and infinite values; each of the ten over a stored flag per policy and a comparison per period, read as its 0.0/1.0 and answering f64, log and log10 of the false one minus infinity; abs and sign of a whole number past 2**53 keeping i64, round_sig_figs of one to seventeen figures, the six transcendental calls of a whole number answering f64, and the absolute value of -2**63 refused.",
        "Bounded finite examples do not certify every transcendental exceptional input or underflow. No case claims Excel's own bits for norm_cdf. A null flag, a mask and a stored run of flags under these ten are held by producer tests, not by published cases.",
    ),
    "11.1.13": (
        "Null vs NaN/infinity, predicates, fill_null preserving NaN, fill_nan replacing NaN while keeping an infinity, a null period and a null outer list, a value, column, per-policy-over-period, per-period and expression fill, whole-number values and fills, scalar/list and empty portfolio.",
        "Producer suites cover whole-number predicates and unsupported semantic families, and fill_null's bounded domain: a fill of another family than the value's, or a number filling a bool, is refused while the formula is written. No extra numeric truthiness is inferred. fill_nan over a Boolean, text or date value states no answer, and a per-period fill over a per-policy value is outside the entry.",
    ),
    "11.1.14": (
        "Per-policy sum, a null period nulling the total, all-null run answering null, empty list still summing to nought, null outer list and empty portfolio; whole numbers past 2**53 summed exactly, a total that fits answered where a running total on the way passed i64, and a total past i64 refused.",
        "No row-axis aggregation or arbitrary reassociation budget.",
    ),
    "11.1.15": (
        "Per-policy mean over its own periods, a null period nulling the answer instead of leaving the denominator, empty/all-null/null outer and empty portfolio; the mean of whole numbers, to the edge of i64, answering f64.",
        "No padded common-grid denominator.",
    ),
    "11.1.16": (
        "Per-policy min, a null period nulling the answer on the clause's own run and on values it does not reach, empty/all-null/null outer and empty portfolio.",
        "No replacement of missing values by zero.",
    ),
    "11.1.17": (
        "Per-policy max, a null period nulling the answer above and below zero, empty/all-null/null outer and empty portfolio.",
        "No replacement of missing values by zero.",
    ),
    "11.1.18": (
        "Every bounded value identifier has a zero-policy case; scalar/list broadcasting, jagged lists, null outer lists and unequal-length refusal.",
        "Backend rectangular-only capability is distinct from the portable per-policy shape rule. Not every dtype/configuration Cartesian product is enumerated.",
    ),
    "11.1.19": (
        "Shift direction/fill, cumulative-survival opening value with and without start_at, a lost decrement propagating through the running survival, empty lists and empty portfolio.",
        "Finite list values, numeric literal fill and from_survival=false only. The shifts' null boundary and alternative survival modes are not certified by these fixtures. A shifted run of Booleans is outside the entry; the producer's refusal of a numeric fill for one is a producer test.",
    ),
    "11.1.20": (
        "Linear recurrence in both directions, including zero/negative multiplier, literal steps, a jagged book whose reverse runs each open at their own last period, the workbook rollback and its spelling between two reversals, a lost step or a lost opening state nulling it from there on in the run's own direction, and a run whose every step is lost; suffix sums with a lost period nulling back toward period zero, an all-null run and a null outer list; suffix sums of whole numbers past 2**53 and to the edge of i64 answering list[i64] exactly, and one past i64 refused; empty lists/portfolio.",
        "Finite f64 domain. A non-finite operand and a null outer list to the recurrence stay outside the entry in either direction. No scalar-column step, nonfinite-state or two-scalar-axis interpretation is promised. The to_float a producer writes around a whole-number operand, and its refusal of a Boolean one, are producer tests.",
    ),
    "11.1.21": (
        "Both timings under varying rates, scalar-rate forms, a lost cashflow period nulling back toward period zero under either timing, an all-null run and a null outer list, empty lists and empty portfolio.",
        "Rate inputs only, and a null rate stays outside the clause. Factor mode and literal end-of-period behavior remain outside this clause.",
    ),
    "11.1.22": (
        "Negative and positive positions, selected null, null list/position, empty/out-of-bounds refusal and empty portfolio.",
        "Decimal position refused even when integral; no null-on-bounds fallback.",
    ),
    "11.1.23": (
        "Checked conversion, empty portfolio/list, fractional/null scalar/item/outer, nonfinite and signed upper-overflow refusal, and the wider storage widths judged on their value at both ends of the i64 range.",
        "No truncation, bool/text conversion or unknown type substitution. A width past i64 refuses as a range rather than as a fraction; the two refusals are separate and each names its own door.",
    ),
    "11.1.38": (
        "Widening on a scalar and a list, both signs of the 2**53 boundary and the first value past each, a null carried on scalar/item/outer, empty list and empty portfolio, a double returned unchanged, and an unsigned width judged on its value.",
        "Bool, text and date refuse on type while the formula is written rather than while it runs. Non-finite doubles pass through as themselves and are not re-examined here; no rounding, nearest-double or saturating mode exists to be reviewed.",
    ),
    "11.1.39": (
        "Every accepted type written out -- integer, shortest-form double, bool, date, text, category -- on a scalar and a list, a null carried on scalar/item/outer, empty list and empty portfolio, and the two doors from outside: an unsigned value past 2**63 and a 128-bit value, each keeping every digit.",
        "Only floats whose shortest form carries no exponent or a positive one are published, because the spelling of a small negative exponent is a printer's habit rather than the clause's claim. Datetime text is stated but not exhibited: its fractional digits follow a time unit section 10 does not record. Duration, decimal, time-of-day and binary refusals are producer tests; the envelope has no name to exhibit them under.",
    ),
    "11.1.40": (
        "A two-element and a three-element array, a null element and a null array, an array of width zero, an empty portfolio, and the refusals of a list and of a scalar.",
        "An array whose element type section 10 cannot name is a producer test; the envelope's array name admits section 10 element types only, so there is no case to exhibit it with. Nested arrays and re-widthing are outside the entry.",
    ),
    "11.1.41": (
        "Jagged lists including a one-period and an empty one, every list element type the envelope names, a null moving with its position, a null outer list, reversal applied twice, the forward recurrence between two reversals and an empty portfolio.",
        "A per-policy operand has no periods to turn and is outside the entry. Nothing is folded, so no null propagation is claimed or exhibited beyond the null moving.",
    ),
    "11.1.24": (
        "Ordered tuple keys, scalar/list and empty keys/portfolio, safe numeric endpoints/fractions, all miss modes, duplicate/empty table, answer-layout/arity and exact payload identity refusals.",
        "Only present bounded string/numeric keys with finite f64 answers. An answer column of whole numbers or single-precision values read as f64, and one past 2**53 or not a number refused, is held by producer tests, not by a published case. The extreme fractional fixture explicitly uses hash storage; this does not certify auto storage selection.",
    ),
    "11.1.25": (
        "Both shapes and operand orders, signed division/remainder, zero divisor, nullable inputs, empty portfolio, exact integer endpoints, huge-exponent/overflow and mixed-range refusals.",
        "Producer wrapping outside i64 range is not portable agreement. Negative scalar base with list exponent and nonfinite inputs remain excluded. A Boolean operand, per period or per policy, read as its f64 indicator, an integer power under a written exponent outside [0, 2^32-1] answering f64, and a column exponent past that range refused naming to_float(), are held by producer tests, not by published cases.",
    ),
    "11.1.26": (
        "All six predicates in both shapes, inline predicate vs stored indicator, scalar semantic types, nullable/empty input; NaN refusal; whole numbers past 2**53 compared exactly per policy and per period; list-shaped dates against a date and against a date run, with a null element; text ordered by code point per policy and per period -- a capital before a small letter, a prefix before its extension, the empty string first, an accent after every ASCII letter -- against a column, a literal on the left and a run, with a null on either shape; a comparison of a table lookup stored as the f64 indicator.",
        "Only a whole number compared with a decimal is bounded by the exact numeric range; no NaN ordering or cross-family ordering is selected, and the producer refuses a comparison across families while the formula is written. Text order is code-point order only: no case folding, collation or locale is claimed. List-shaped text equality is held by producer tests, not by a published case; date/datetime mixing stays outside the entry. Date-and-time and duration comparisons exact to the last unit, and a column wider than i64 compared in its own width, are held by producer tests, not by published cases.",
    ),
    "11.1.27": (
        "Scalar Kleene truth table and list null propagation, not_, empty portfolio; a per-policy null beside a test a NaN left unknown, in either order under and/or and as a condition, the null winning; a per-policy result a NaN left null read inline by is_in, is_null, fill_null, a comparison, arithmetic, a when and an enclosing and/or; stored f64 indicators per policy and per period, negative zero, a nullable Boolean beside one, mixed shapes, use as a condition, and null/NaN/infinity/2.0/0.5 refusal.",
        "Only a direct stored f64 column is an indicator operand. i64 operands, numeric literals and arithmetic results stay outside the clause, and the producer refuses them while the formula is written.",
    ),
    "11.1.28": (
        "Both branch shapes, Boolean and checked numeric masks, nullable scalar/list distinction, inline comparison/logical masks, invalid unused-branch refusal; a null run in the selected and in the unselected branch, beside a run and beside a per-policy condition, nulling the policy; a per-policy NaN test combined with a whole-number, text, date or flag run (no truth value in any period); a flag answer left null per period read by arithmetic, not_, and, is_null and another when; a condition a NaN left without a truth value beside a null in either branch at that cell (NaN in a double answer).",
        "Selection does not suppress branch evaluation errors. Invalid numeric masks are refused rather than cast by truthiness.",
    ),
    "11.1.29": (
        "Simple/compound monthly conversion, negative/zero periods, nulls, zero base, scalar discounts/contributions, empty portfolio and unknown configuration refusal.",
        "Finite representable factors only. List cashflow valuation uses prospective_value, not the scalar discount forms.",
    ),
    "11.1.30": (
        "Spot/forward, varying and negative rates, scalar/list operand positions, retained unused periods, empty portfolio and method refusal.",
        "Rates > -1, non-null finite domain. No forward/spot convention substitution.",
    ),
    "11.1.31": (
        "Knots, interior interpolation, both flat endpoints, scalar/list, empty portfolio; changed/missing/ambiguous payload refusal.",
        "Linear/flat knot recipe only. Parametric and nonlinear identities remain outside this reader capability.",
    ),
    "11.1.32": (
        "Positive/negative/out-of-range override, no extension, null element/outer; typed broadcasts over jagged/empty axes, empty portfolio; implicit month graph dependency.",
        "Historical one-operand broadcast recognized but not evaluated; other override dtypes are outside the clause.",
    ),
    "11.1.33": (
        "Date order, period starts, signed/leap-clamped offsets, original-start ranges/closure/reversal/null, serial 59/60/61 and epochs, empty portfolio and unsupported token refusal.",
        "Date-only scalar domain, finite serials, years 1..9999. Compound durations and offsets outside the date range are excluded.",
    ),
    "11.1.34": (
        "All five bases and every named alias, forward/reversed/equal dates, leap/February anniversaries, nullable elements and empty portfolio; unsupported basis refusal.",
        "No null outer list; basis 1 is not Actual/Actual ISDA.",
    ),
    "11.1.35": (
        "Away-from-zero ties in both shapes; the fifteen-digit value rounded rather than the double (a workbook's cached values, doubles just under a decimal tie, whole units just under a half, a sixteenth digit that is an exact 5 at a negative place, fifteen digits coarser than the step), both signs and a negative place; PV zero rate/period/default/timing/null and empty portfolio.",
        "Bounded scale, integral nonnegative scalar periods and typ 0/1; no arbitrary overflow/cancellation budget.",
    ),
    "11.1.36": (
        "Unique root, unavailable streams, absent/null/per-policy guesses, 600-period zero root, empty portfolio and multiple-root exclusion.",
        "Unique root in [-.9,1], one sign change, bounded cashflows; no general solver convergence or Excel multi-root selection claim.",
    ),
    "11.1.37": (
        "All eleven identifiers and three calendar kinds, month-aligned cadences, T versus T+1, expiry inclusive/null, null/negative term counts, zero horizon/portfolio, month-end clamp distinctions and unsupported recipe refusals; fixed_step t_years exact in both spellings, discriminating the other spelling and a running sum.",
        "NullCalendar/Unadjusted/OneTwelfth only. Shared exact_date advances successively; inception/per-policy grids offset from original start. Other calendars/anchors/cadences need separate capabilities. fixed_step's other readings and its refusals have producer and engine tests, not published cases.",
    ),
    "16.1": (
        "State values, both shipped rollforward patterns replayed against the state arrays their own exports carry, two floors biting in serialized order on a chain that tells them apart by ordinal alone, exact compilation selection, T=0/zero policies, state/point/axis/operand/period binding refusals, the ratchet gate's own column type, and structural identity.",
        "Bounded BOP/EOP machine only, over Add, Subtract, Charge, Grow, Floor and Ratchet in the forms a compilation writes them. GrowCapped, DeductNAR, Round and Apply stay outside, as do a rounded Charge or Grow, a Floor without a finite bound, a Ratchet lifting to anything but a declared state, and an ungated Ratchet. No general independent compiler digest or version-binding reconstruction is claimed.",
    ),
    "16.2": (
        "Signed credit/charge, after-minus-before cancellation, T=0/zero policies, tracking/label/settings/arity refusals.",
        "Tracked subset only; delta is not the notional operand or full-period change. A structural step's movement is named by the reserved {kind}@{ordinal}, and no published case extracts one: the movements a node carries are the producer's re-track, not a reader's to reproduce.",
    ),
    "16.3": (
        "Native raw result refuses both export profiles with named state/increment guidance.",
        "Excluded portable output, retained core identifier; no Struct type or implicit flattening.",
    ),
}
extra_cases = {
    "11.1.18": [
        "arithmetic-length-mismatch",
        "broadcast-explicit-jagged",
        "comparison-null-list",
    ],
    "11.1.28": [c["id"] for c in cases if c["id"].startswith("conditional-")],
    "10": ["raw-struct-export-refuses"],
    "11.1.11": [
        "lookup-keyword-order",
        "lookup-arity",
        "list-get-integral-decimal-position",
    ],
}
producer = {
    "10": [
        "tests/graph/test_portable_output_boundaries.py",
        "tests/graph/test_dtypes.py",
        "tests/frame/test_integers_arrive_as_i64.py",
    ],
    "11.1.1": [
        "tests/accessors/test_projection_set.py",
        "tests/accessors/test_maximum_age_per_policy.py",
        "tests/graph/test_executable_profile.py",
        "tests/projection/test_fixed_step_axis.py",
    ],
    "11.1.2": ["tests/graph/test_executable_profile.py"],
    "11.1.3": ["tests/polars_backend/test_list_clip_matches_engine.py"],
    "11.1.4": ["tests/graph/test_executable_profile.py"],
    "11.1.6": ["tests/graph/test_executable_profile.py"],
    "11.1.10": ["tests/mortality/test_at_joint.py"],
    "11.1.5": [
        "tests/graph/test_operation_vectors.py",
        "tests/functions/test_is_in_members_keep_to_one_kind.py",
        "tests/frame/test_is_in_of_a_nan_is_false.py",
    ],
    "11.1.13": [
        "tests/graph/test_operation_vectors.py",
        "tests/graph/test_fill_nan.py",
        "tests/functions/test_fills_over_flags_text_and_dates.py",
    ],
    "11.1.19": [
        "tests/graph/test_operation_vectors.py",
        "tests/frame/test_per_period_flags.py",
    ],
    "11.1.20": [
        "tests/graph/test_operation_vectors.py",
        "tests/graph/test_dtypes.py",
        "tests/accessors/test_projection.py",
    ],
    "11.1.25": [
        "tests/graph/test_operation_vectors.py",
        "tests/frame/test_per_period_flags.py",
        "tests/frame/test_per_policy_flag_arithmetic.py",
        "tests/frame/test_integer_power_written_exponent.py",
        "tests/errors/test_an_integer_power_past_its_range_names_to_float.py",
    ],
    "11.1.34": [
        "tests/graph/test_operation_vectors.py",
        "tests/accessors/excel_functions/test_yearfrac_is_excels.py",
    ],
    "11.1.26": [
        "tests/graph/test_operation_vectors.py",
        "tests/functions/test_a_comparison_keeps_to_one_kind.py",
        "tests/functions/test_text_list_comparison.py",
    ],
    "11.1.11": [
        "tests/graph/test_executable_profile.py",
        "tests/graph/test_artifact_conformance.py",
    ],
    "11.1.24": [
        "tests/assumptions/test_lookup_portable_contract.py",
        "tests/assumptions/test_lookup_operand_order.py",
        "tests/assumptions/test_integer_answer_column.py",
    ],
    "11.1.12": [
        "tests/graph/test_operation_vectors.py",
        "tests/graph/test_normal_cdf.py",
        "tests/column/test_maths_over_a_flag_reads_its_0_or_1.py",
    ],
    "11.1.8": [
        "tests/graph/test_operation_vectors.py",
        "tests/column/test_maths_over_a_flag_reads_its_0_or_1.py",
    ],
    "11.1.27": [
        "tests/graph/test_operation_vectors.py",
        "tests/frame/test_a_nan_has_no_order.py",
        "tests/frame/test_a_null_beside_an_unknown_wins.py",
    ],
    "11.1.41": ["tests/graph/test_backward_recurrence.py"],
    "16.1": ["tests/graph/test_portable_rollforward_execution.py"],
}
# The clauses whose operations section 9 has an edge state a window for: each
# is held by a perturbation vector in windows.json, which moves one operand
# cell and keeps every period outside the stated window where it was.
windowed = {
    "11.1.9",
    "11.1.14",
    "11.1.15",
    "11.1.16",
    "11.1.17",
    "11.1.19",
    "11.1.20",
    "11.1.21",
    "11.1.22",
    "11.1.30",
    "11.1.36",
    "11.1.41",
    "16.1",
}
window_review = (
    " The window its edge states (section 9) is held by a perturbation vector:"
    " one operand cell moved outside it leaves every period it excludes, and"
    " every other policy, where they stood."
)
rows = []
for clause, (review, limits) in notes.items():
    if clause in windowed:
        review += window_review
    operations = [name for name, section in contracts.items() if section == clause]
    ids = sorted(
        {
            c["id"]
            for c in cases
            if set(c["covers"]) & set(operations)
            or set(c.get("structural_covers", [])) & set(operations)
        }
        | set(extra_cases.get(clause, []))
    )
    rows.append(
        {
            "clause": clause,
            "identifiers": operations,
            "reviewed_boundaries": review,
            "limits": limits,
            "case_ids": ids,
            "producer_tests": producer.get(
                clause, ["tests/graph/test_operation_vectors.py"]
            )
            + (["tests/graph/test_period_windows.py"] if clause in windowed else []),
        }
    )
assert set(contracts.values()) <= set(notes)
assert {c["id"] for c in cases} >= {id for row in rows for id in row["case_ids"]}
assert all(
    (tests.parent / test).exists() for row in rows for test in row["producer_tests"]
)
doc = {
    "schema": "gaspatchio-boundary-review/v0-preview.1",
    "artifact_schema": "gaspatchio-graph/v0-preview.2",
    "claim": "Reviewed selected boundaries and explicit exclusions for every stated operation clause; not exhaustive combinations or a general backend certificate.",
    "clauses": rows,
}
(schemas / "conformance/boundary-review.json").write_text(
    json.dumps(doc, indent=2, allow_nan=False) + "\n"
)
print("reviewed clauses", len(rows))
