# Graph preview conformance evidence

This kit supplies synthetic examples for the bounded value clauses in the
graph specification, plus an independent reproduction of its identity corpus.
It uses the current `v0-preview.3` / `gspv0-preview-3` tokens. It is a review
candidate, not the final v0 stamp or a production execution backend.

Copy this directory and the adjacent `vectors` directory anywhere. With
Python 3.11 or later, run from this directory:

```sh
python -I reader.pyz ../vectors/*.json
python -I reader.pyz --identity corpus.json
python -I reader.pyz --content content-identity.json
python -I reader.pyz --citation citations.json
```

The reader uses only the Python standard library; neither command imports
Gaspatchio, Polars, NumPy or JAX. `reader.pyz` contains its readable source.
The source of truth and deterministic archive builder are in the public
repository at `spec/graph-artifact/conformance/`. There are no private model
files or private `ref` dependencies in the kit.

`index.json` maps all 101 core identifiers to specification clauses and case
ids. It distinguishes 99 bounded value contracts, the structural `rollforward`
identity, and the explicit portable-output exclusion for `rollforward.struct` (§16.3). The
conditional `when_then` tree has its own examples without becoming a 102nd
operation. A positive example establishes only the invocation it checks:
the index does **not** claim exhaustive coverage of each clause's boundaries.

The kit publishes 909 operation cases in 23 bundles under `vectors/` (their
counts by kind are `index.json`'s `case_counts`, each bundle's its `cases`),
the fourteen content-grammar cases of `content-identity.json` (two of them
refusals), the corpus, and the two citation cases of `citations.json`.

`citations.json` carries §13.1's citation rule: a record that points at a
document it does not enclose carries that document's `document_digest` beside
the identity it already carries. Each case is a comparison report
(`gaspatchio-graph-compare/v0-preview.2`) written by the producer over the
corpus, with the findings a reader owes it. The reader recomputes the corpus's
seal from its bytes: a report citing the corpus by its fingerprint and its seal
has no finding, and one citing another export of the same model — one
fingerprint, another seal — has a `document_digest` finding. The seal is
recorded and never compared; the two reports' verdicts are the same.

`boundary-review.json` records the clause review, linking selected boundaries
and exclusions to cases and producer tests. Every bounded value identifier
has an empty-portfolio check; this review is not exhaustive cross-product
coverage. `producer_setup.table_storage` can select hash storage for a synthetic
lookup fixture without changing its value identity.

`vectors/nulls.json` carries the null-bearing cases for the clauses that state
what a null input does: §11.1.8 and §11.1.12, where a null value stays null;
§§11.1.14–11.1.17, where a null period makes the total null — neither absent
to the fold nor read as a nought — and so does a run of nothing but nulls,
while an empty run still sums to nought; and the running folds of §11.1.9
(`cum_prod`, `cum_sum`), §11.1.19 (`projection.cumulative_survival`), §11.1.20
(`projection.accumulate`, `projection.remaining_sum`) and §11.1.21
(`projection.prospective_value`), where a lost period nulls that position and
every position after it in the direction the fold runs. A clause stating no
null rule gets no case, because §10 leaves behaviour a clause does not state
engine-defined.

`vectors/logical.json` carries §11.1.27's stored indicators: a direct
reference to an `f64` or `list[f64]` column as an operand of `and`, `or` or
`not_`, read under §11.1.18's exact 0/1 rule. A per-policy one stands for its
Boolean and a per-period one for its 0/1 run; a negative zero is zero, and a
null, NaN, infinity or any other number is a refusal rather than a truth value
or a null.

`vectors/flag-extremes.json` carries §§11.1.16–11.1.17 over a run of flags:
`min` and `max` answer one of the periods' own values in their type, so a run of
flags answers `bool` (whether every period was set, whether any was), never the
0 or 1 the totals count it as. `vectors/duration-refusals.json` carries the calls
that would read a number out of a duration, which section 10 has no type for:
the thirteen maths calls other than `abs`, plus `cum_prod` and
`projection.cumulative_survival`, are refused (`duration-read-as-a-number`) per
policy and per period. `duration` and `list[duration]` are input-only names, a
whole number of microseconds per value. A call answering a duration (`abs`, the
totals, `min`, `max`) has no case: no result can be named as one.

`vectors/conversions.json` carries the named conversions of §§11.1.23 and
11.1.38–11.1.40. Three of those clauses exist because a column arrives in a
storage type §10 has no name for, so the envelope names those types on
**inputs only**: `u64`, `i128`, `u128`, `categorical` and
`array[<element>,<n>]`. A result is still named from §10's closed vocabulary,
and an input column carrying one of these names is dropped before the
producer's export — which is what an author following the refusal that named
the conversion does.

`vectors/reversal.json` carries the backward recurrence of §11.1.20 —
`projection.accumulate` under `reverse: true`, run from each policy's own last
period — and `list.reverse` of §11.1.41, on jagged books, every list element
type the envelope names, a null moving with a reversal and a lost step nulling
the recurrence toward period zero. One case writes the forward recurrence
between two reversals and states the same doubles as the backward one. Every
`projection.accumulate` case in the other bundles carries `reverse: false`.

`vectors/nan-fill.json` carries §11.1.13's `fill_nan`: the fill where a value
is NaN, an infinity and a null kept, over policies and periods, with a value,
a column and an expression as the fill, and over whole numbers, which hold no
NaN and stand in the type they share with the fill.

`vectors/normal-cdf.json` carries `norm_cdf` of §11.1.12, the standard normal
distribution function: the body, both tails to the end of the normal range at
-37.5 under the family's 1e-12 relative budget, the subnormal and underflowed
answers below it under the line rule, NaN and the infinities exactly, nulls on
both shapes and an empty portfolio. Each expected answer is the double nearest
Φ worked to 60 digits by the bundle's generator, never a library's. No case
claims Excel's own bits.

`vectors/list-dates.json` carries §11.1.26's list-shaped date comparisons: a run
against a date column, one policy's leap day against itself, a date literal on the
left, and two runs of one length with a null element answering null. The answer
is the per-period 0/1 indicator, `list[f64]`.

`vectors/text-order.json` carries §11.1.26's ordering over text, by code point:
one value per policy against a column and against a literal on the left, a run
against a run and against one value per policy, and a null on either shape
answering null. The cases tell code-point order from a case-folded or collated
one — `"B" < "a"`, `"ab" < "abc"`, `"z" < "é"` — and no locale is claimed.

`vectors/fixed-step.json` carries §11.1.1's fixed-step axis: the `step` index
and the `month` a declaration mints where a step is whole months, and
`t_years` in both spellings at zero tolerance.

`vectors/windows.json` carries the perturbation vectors for the windows
section 9 has an edge state: `periods: {from, to}` on an aggregation read and
`position: k` on a literal `list.get`. Each moved case is a base case beside it
with one operand cell moved, and names its base, the cell and the window in
`perturbation`; every period of the answer the window excludes, and every other
policy, keeps the base's value, and something inside the window moves. Each is
an ordinary value case as well, so this reader checks its numbers as it checks
any other; the relation itself is checked by the producer's tests and by each
engine's.

`vectors/selection.json` carries §7.6's recorded selection, the
`selection-value` case class: a book under `inputs`, the steps a document
records under `selection` (each step's `kind` and predicate `expr`, and a semi
or anti join's right side under `right`), and an `expr` evaluated over the rows
the steps keep. A filter keeps a row its predicate answers true for and drops
one it answers false or null for; a semi join keeps a row whose key the right
side holds and an anti join one whose key it does not; steps compose in order.
This reader checks each join's `right_fingerprint` against the right side
before it uses it, under §12.3's content grammar.

`vector-envelope.schema.json` checks envelope structure. The artifact schema
checks expression grammar separately. Inputs use model-point rows, with
one inner list per policy for a list column. Dates are ISO date strings.
Non-finite vector cells use `{"nonfinite":"nan"}`, `{"nonfinite":"+inf"}` or
`{"nonfinite":"-inf"}`; artifact literals and table payloads retain their own
encodings. Integer, Boolean, null, shape and date results compare exactly;
finite floating results use the budget written on each case. No case budget
is a whole-model error allowance.

The seven case classes are kept separate:

- `value`: a numerical or typed-value invocation with expected output.
- `recording-door-value`: projection setup or join, with invocation data in
  `producer_setup`. Join output is compared after `sort_output_by` because
  streaming row position does not establish policy identity.
- `portable-domain-refusal`: outside the stated portable subset. A false
  `producer_check` does not claim that the producer refuses this input.
- `backend-capability-refusal`: the example reader declines a declared
  capability, even if another engine supports it.
- `selection-value`: a recorded selection (section 7.6) -- the steps under
  `selection` applied to the book in order -- before `expr` is evaluated over
  the rows they keep.
- `integrity-mutation`: changed, duplicated or missing identity-bound data.
- `artifact-type-refusal`: a native result whose type cannot be exported;
  the producer check exercises both audit and executable export.

Curve and schedule cases carry synthetic canonical recipes in `assumptions`;
table cases carry the artifact's typed table payload. The reader independently
recomputes those identities before evaluating. Rollforward cases carry the
compilation facet and a public construction recipe for producer replay. The
reader computes states and deltas from the facet, not the construction recipe
or expected results. It checks exact facet resolution; a general independent
compiler-fingerprint implementation remains outside this reader's scope.

The invocation reader is an oracle for the published cases. It does not load
arbitrary artifacts, resolve all versioned bindings, or enforce every excluded
form on arbitrary inputs. Its narrower edges are stated so that nobody meets
them as a surprise:

- **Its table identity names `i64`, `f64` and `str` columns only.** Section
  12.3's content grammar also writes a Boolean cell, and a table or join right
  side carrying one is declined by name (`lookup-table-type`) rather than
  hashed; no published case carries one.
- **Its join is a left join on one key the two sides spell alike**, and its
  projection reads the synthetic monthly `month` index and the fixed-step
  form's `step` and `month`. A composite or renamed key, another join type and
  another axis column are declined by name.
- **It reads no Parquet.** A reader holding an artifact's `model.results` file
  and checking a policy's timeline against it brings its own Parquet reader.
- **A vector case's curve and schedule recipes are found by `source_sha`.**
  That is the vector envelope's name for the recipe digest; an artifact's
  section 15 entry carries the same digest as its `fingerprint`, and this
  reader reads envelopes, not artifacts.

`content-identity.json` carries section 12.3's content grammar: each case is a
frame described in plain JSON — its columns in order, each a name, a type and
its values — with the bytes the grammar writes for it and their SHA-256, so an
implementation can check its encoder byte for byte. The datetime carrier is
most of it: a `datetime` column states its `unit` (`ms`, `us`, `ns`) and its
`zone` (null for zone-naive), each value a whole count of that unit since the
epoch. The cases hold one instant in three units writing one encoding, a UTC
column writing as a naive one, the zone in the header (and behind the
element's tag in a `list[datetime]`), nanoseconds past the earlier microsecond
(`-1` ns, `i64`'s least, two instants 500 ns apart), a missing value, and
the millisecond counts at the edge of `i64` in microseconds; section 12.3's
worked example anchors the rest. A case holding `refusal` in place of `bytes`
and `digest` is a frame no encoder may write -- a millisecond count one past
that edge, either side, which a wrap-around would write as another instant --
and names the refusal every encoder must meet instead. `reader.pyz --content`
re-derives every case with the standard library.

The identity reader independently transcribes the specification's fixed model
— eleven columns, twelve nodes — and recomputes its local, upstream, graph, formulas-only
(section 12.6) and document digests; it is neither an authenticity check nor
a general artifact validator. Wrong-answer and digest-mutation tests accompany
the kit in the producer repository.

All fixtures are synthetic. Code and fixtures are Apache-2.0, under the same
terms as the project; copyright 2026 Opio Inc.
