# Token batch — the design, ahead of the wire

**DRAFT.** Nothing here is shipped. This document is the design half of six changes to
`spec/graph-artifact/v0-preview.md` that share one grammar token and one corpus
regeneration. The wire changes, the schema edit and the regeneration land as follow-on
units; the ordering, the digests that move and the public decision record are in
`ref/17-calc-graph/plans/2026-09-03-regeneration-manifest.md`.

The six: the node-record collapse, the edge facet move, the date-literal tag, the
list-reduction family, the closed operation-tree branches, and the rollforward increments
summary. They are designed together because between them they move the grammar token once,
the schema identifier once and the conformance corpus once — and the format's users are
owed one documented change rather than six quiet ones.

---

## 0. Where every number below comes from

Every shape claim in this document was measured on 2026-09-03 and the census re-derived later
that day, after the teaching models' discount change described below, against a corpus of
seven documents and **348 node records**:

| Document | Nodes | Edges | Operation-tree nodes |
|---|---|---|---|
| `level-4-lifelib/base` (the flagship), `executable` export | 128 | 184 | 454 |
| `level-3-mini-va/base`, `executable` export | 69 | 101 | 211 |
| `level-5-scenarios/base`, `executable` export | 125 | 180 | 435 |
| `goldens/conformance_corpus.json` | 8 | 10 | 0 (`audit`) |
| `goldens/annex_example_artifact.json` | 6 | 4 | 0 |
| `goldens/state_graph_example.json` | 7 | 6 | 0 |
| `goldens/nested_valuation_example.json` | 5 | 4 | 0 |
| **Total** | **348** | **489** | **1100** |

The three model exports were produced by running each model's own `main()` over its own
model points and calling `GraphExporter(af).export(profile="executable")`. The frozen
corpus digest at both commits is
`sha256:2fbb4e8f3ab24542a1f53715aef273e50f4e3c7888a11f52b0f5d3433ce4b42e`, and it did not
move while this design was written: no wire, schema, golden or corpus file was touched.

**The shipped tutorials moved under this document, and where a figure moved with them it is
stated after the move.** In that change two teaching models stopped computing their discount
factors in Python and broadcasting the answers back in, and now read the curve on the frame.
One of the two is in this census — `level-5-scenarios/base` — and it no longer builds a
`disc_factors_full` column, so the two engine-native nodes those lines minted are gone.

**What the change moved in these two documents**, found by re-deriving the census above and
resolving every `file.py:NNN` citation in both — six things, each stated where it occurs:

- level 5's operation-tree count, **433 → 435**, and the total with it, **1098 → 1100** (this
  table, §4.3, and the manifest's row 5);
- the `tier` split, `core` **263 → 265** and `engine_native` **29 → 27** (§1.1, §1.5);
- the `engines` split, `[]` **261 → 263** and `["polars"]` **29 → 27** (§1.1, §1.5);
- the engine-native inventory, **29 → 27**, with the two-node remainder gone rather than
  reclassified (§2.1, §3.2);
- `.list.len()` under the tutorials, **4 → 1** (§3.5);
- level 5's date line, `model.py:423` → **`model.py:413`** (§2.1).

**What was re-derived after the move and did not move:** 348 records over 489 edges, the seven
per-document node and edge counts, the `kind`, `source`, `origin` and `value_kind`
distributions, the ten triples, the thirteen six-axis combinations, 344/1/3, the edge subtype
split, the twelve `(tier, engines)` states all admitted by today's schema, 1100 tree nodes with
zero refused after §4.2's patch, 0 of 322, `.list.sum()` at 136 in the tutorials and 172 across
the package's Python, and the flagship's 128 nodes, 184 edges and ten engine-native records.

**Line citations are a different kind of claim from a count, and they age faster.** Every
`file.py:NNN` below was resolved and read on 2026-09-03; where the code has since moved, locate
the target by the name or the sentence quoted beside it rather than by the number.

**Two rows of §1.2's migration table were established outside this corpus, and this is
where that is said.** No `state` and no `rollforward` node is among the 348 — §12.5 excludes
the rollforward from the corpus deliberately, and neither kind occurs in the three model
exports or the three hand-built goldens. Both rows were measured instead against a live
compilation of the §5.1 fixture (one state `av`; a `Grow` labelled `fund_return`, a `Charge`
labelled `me_charge`, a `Floor` at nought), which emits `rollforward:ff70eb792aee` with
`source: null`, `origin: "rollforward"` and `state:av@eop` with both fields null — exactly
the two rows the table states. Everything else below is a count over the seven documents.

Two facts about the identity chain are load-bearing throughout and were read off
`frame/graph/fingerprint.py` rather than assumed. **The only node-record fields inside any
canonical byte stream are `kind` (which selects a leaf's tag), the leaf's name (`column`,
or the state reference for a running state) and `dtype` (a leaf's type).** `source`,
`origin`, `value_kind`, `tier` and `engines` are hashed nowhere. And `edges` enter no
digest at all: §12.4's three sections are (node id, node fingerprint) pairs, assumption
table content hashes, and unaccounted column names.

---

## 1. V6(b) — the node record collapse, and V14(c)'s facet move

### 1.1 What the two fields are today, measured

`source` and `origin` are two required, nullable enums answering two questions §8 states
separately: `source` is "where an input's values came from" and is null on anything
computed; `origin` is "which recording door the definition came through" and is null on a
leaf.

Across the 348 records:

| Axis | Distribution |
|---|---|
| `kind` | `computed` 290, `input` 55, `hole` 1, `state_graph` 1, `nested_valuation` 1 |
| `source` | null 293, `model_points` 53, `injected` 1, `assumptions` 1 |
| `origin` | `assignment` 232, null 57, `join` 46, `projection` 12, `batch` 1 |
| `value_kind` | `value` 339, `boolean_mask` 6, `unknown` 3 |
| `tier` | `core` 265, null 56, `engine_native` 27 |
| `engines` | `[]` 263, absent 58, `["polars"]` 27 |

Ten distinct `(kind, source, origin)` triples occur. The published schema admits
**7 × 4 × 9 = 252**. Widening the count to the six fields above — `kind`, `source`,
`origin`, `value_kind`, `tier`, and whether `engines` is present — the schema admits
**6048** combinations and **13** occur.

The ten triples, in full:

| `kind` | `source` | `origin` | Count |
|---|---|---|---|
| `computed` | null | `assignment` | 231 |
| `input` | `model_points` | null | 53 |
| `computed` | null | `join` | 46 |
| `computed` | null | `projection` | 12 |
| `computed` | null | `batch` | 1 |
| `input` | `injected` | `assignment` | 1 |
| `input` | `assumptions` | null | 1 |
| `hole` | null | null | 1 |
| `state_graph` | null | null | 1 |
| `nested_valuation` | null | null | 1 |

Two findings the table earns.

**The two fields are near-disjoint.** In **344** of 348 records exactly one of them is
non-null; **one** record carries both, and **three** carry neither. (347 is the count of
records that do not carry both, which is a different claim and is not the one being made
here.) The single overlap is the injected column — `kind: "input"`, `source: "injected"`,
`origin: "assignment"` — and §7.2 defines a second member of that same class that no
shipped document yet carries: a column returning through an explicit re-entry, as
`kind: "input"`, `source: "injected"`, `origin: "continuation"`. So the overlap is a class
of two, not an accident of one.

The three both-null records are the hole (`reserve_override`) and the two reserved kinds
(`state_graph:disability_income_3state`, `nested_valuation:present_value_of_guarantee`).
Nothing below leans on the wrong figure: the migration table maps all three to
`provenance: null`, and §1.3 constrains all three kinds to null.

**One `source` value has no producer path at all.** `DataSource.ASSUMPTIONS` exists in the
enum (`frame/graph/graph_models.py:101`) and is assigned nowhere: `graph_builder.py`
assigns `MODEL_POINTS` at `:652` and `INJECTED` at `:1194`, and that is the whole set. The
only document in the corpus carrying `source: "assumptions"` is the hand-built annex
example. A model that reads an assumption base carries the read on a `computed` node's
`lookup` call and in `reads_assumptions`, not on an `input` node.

### 1.2 The merged field

`source` and `origin` become one required, nullable field, **`provenance`**, carrying the
union of their two vocabularies — eleven values, none dropped:

`model_points`, `assumptions`, `injected`, `assignment`, `batch`, `rename`, `join`,
`projection`, `date`, `rollforward`, `continuation`.

The doors survive as first-class provenance values. A column arriving from the right side
of a join says `join`; a column carried forward under a new name says `rename`; a column a
single call minted as a batch says `batch`. A rename is a rename in the fingerprints —
§12's leaf rule and §8.1's identity record are what report one — and `provenance` says only
which door it came through.

**The migration is total and is stated as a table, not left to be derived:**

| Today `(kind, source, origin)` | `provenance` |
|---|---|
| `input`, `model_points`, null | `model_points` |
| `input`, `assumptions`, null | `assumptions` |
| `input`, `injected`, `assignment` | `injected` |
| `input`, `injected`, `continuation` | `continuation` |
| `computed`, null, *D* | *D* — the door, unchanged |
| `hole`, null, null | null |
| `state`, null, null | null |
| `rollforward`, null, `rollforward` | `rollforward` |

One row is lossy and it is the only one: on an injected column the `assignment` label is
dropped. It is dropped because it is not a fact about the values, which is what the field
asks, and because `injected` already says the values were handed over at a located line.
The distinction that *is* load-bearing on an injected column — handed over at a line
against returning through a re-entry — survives as `injected` against `continuation`,
which is precisely the split §7.2 draws.

**And the merge closes a collision this document currently has to state rather than fix.**
§12.1 says of an injected column's canonical bytes: *"This attribute is distinct from the
node record's `origin` field, which names the recording door the definition came through
(§8) … they share a name and hold different things, and a consumer that built these bytes
from the record's field would reach a well-formed digest matching nothing. Neither is
renamed here — the wire is fixed for this preview — so the collision is stated instead."*
After the merge the record's field is `provenance` and the injected call's attribute is
`origin` (the container: `series` or `array`), and there is nothing left to collide. The
paragraph shortens to a sentence naming the container.

### 1.3 Impossible states the old shape allowed, and what refuses them

The new shape carries a per-`kind` constraint on `provenance`, stated in §8 and enforced by
the schema through `if`/`then` on `kind` (the mechanism `$defs.edge` already uses for
`type`/`subtype`):

| `kind` | Legal `provenance` |
|---|---|
| `input` | `model_points`, `assumptions`, `injected`, `continuation` |
| `computed` | `assignment`, `batch`, `rename`, `join`, `projection`, `date` |
| `hole` | null only |
| `state` | null only |
| `rollforward` | `rollforward` only |
| `state_graph`, `nested_valuation` | null only |

**The two reserved kinds are constrained now, at null, rather than left to §17's producer.**
Deferring them to the producer that first emits one is the one answer this section cannot
give: under an `if`/`then`-on-`kind` schema, two of the seven kinds would accept any of the
eleven values *or* null, which reintroduces exactly the guessing the collapse exists to
remove. The answer is measured rather than chosen — both hand-built goldens carry
`source: null` and `origin: null` today, so null is what the migration already says — and the
cost to §17 is bounded rather than nil. A producer that later needs a value for either kind
widens the per-`kind` enum rather than reshaping the record, so §17 is not redesigned; but
widening makes a document that was refused newly valid, which moves the schema identifier by
the same rule that moves it for the collapse — *a document valid under the old shape stops
being valid, **or vice versa***. An identifier move and a §14.1 line is what it costs, which
is what any conditional member costs.

Thirteen legal `(kind, provenance)` pairs across the five kinds this producer emits —
`input`, `computed`, `hole`, `state` and `rollforward`, the last two of them outside the
corpus and neither of them among the five §1.1 counts — fifteen across all seven, against
252 `(kind, source, origin)` triples the current schema admits. Seven states
the old shape lets a producer write, each of which contradicts something §8, §16 or §17 says
in prose:

1. **`kind: "computed"` with `source: "model_points"`** — a column both derived and
   arrived. §8: "`source` is null on anything computed." Refused: a node has one
   provenance, and `model_points` is not legal on `computed`.
2. **`kind: "hole"` with `source: "assumptions"`** — a column nothing accounts for, whose
   values came from an assumption base. §8 says a hole's source is null and its account of
   itself is that it has none. Refused: `hole` admits null only.
3. **`kind: "input"` with `origin: "rename"`** — an arriving column that came through a
   rename door. Refused: `rename` is legal on `computed` alone.
4. **`kind: "state"` with `source: "model_points"` and `origin: "join"`** — a running
   rollforward state that arrived from the right side of a join. §16: a state "is not a
   column: nothing on the model holds it, nothing can be asked to supply it, and it reads
   nothing." Refused: `state` admits null only.
5. **`kind: "input"` with both fields null** — an input whose account of where it came from
   is silence, in a record where §8 says "a null here is a claim rather than a gap".
   Refused: `input` requires one of its four values.
6. **`kind: "rollforward"` with `origin: "assignment"`** — a compiled state machine that
   came through a plain assignment, when §16 says "no statement in the model's source
   defines it". Refused: `rollforward` admits `rollforward` only.
7. **`kind: "state_graph"` with `source: "model_points"`** — the states of one rollforward
   taken together, claiming to have arrived as policy data. §17 makes a `state_graph` the
   entry a reader follows to reach declared states, which is a thing the model computes and
   not a thing it was handed. Refused: both reserved kinds admit null only, which is what
   both hand-built examples already carry.

### 1.4 `value_kind` folds into `dtype`

`value_kind` is a required enum of `value`, `boolean_mask`, `unknown`. **Across all 348
records it is a function of `dtype` with no exception**: `bool` → `boolean_mask` (6
records), `unknown` → `unknown` (3), and every other type → `value` (339). The producer
computes it that way and nowhere else: every construction site passes `kind_from_dtype(...)`
(`graph_builder.py:807, :923, :1095, :1193`), and the backfill in `calc_graph.py:613`
(`data.value_kind = kind_from_dtype(dtype)`) does the same. `kind_from_dtype`'s whole body is three tests and a default: null →
`unknown`, `Boolean` or `List(Boolean)` → `boolean_mask`, everything else → `value`.

**The three real boolean masks, named.** The six `boolean_mask` records are three distinct
columns appearing in two models: `has_gmdb@1`, `has_gmab@1` and `has_surr_charge@1`, each
in the flagship and in level-5, each `kind: "computed"`, each through the `join` door, each
`dtype: "bool"`. There is no fourth anywhere in the corpus, and no `input` node carries the
value.

**The field does not carry the claim its name suggests, and this is measured rather than
argued.** A model that compares a date column against a date literal —
`af.is_post_reform = af.entry_date > datetime.date(2020, 1, 1)` — produces a column the
finished frame holds as `Float64`, a 0/1 mask, and the record reports `dtype: "f64"`,
`value_kind: "value"`.

**And the date is not the special case — every bare comparison this framework writes is
one.** Measured at the same tip, `af.plain_bool = af.sum_assured > 1.5` is `dtype: "f64"`,
`value_kind: "value"`, `tier: "core"`, and the finished frame holds `Float64`. The corpus
contains no such record only because every comparison in the three shipped models is nested
inside a `when`/`then`: across all 348 records **not one** has a comparison as its top-level
`expr`, while `gt`/`eq`/`lt`/`le`/`ge` occur **57** times nested. So the class where
`value_kind` says `value` of something a reader would call a selection is not one prospective
case — it is present-tense, it is this producer, and it is every comparison it writes down.

**The fold.** The field is removed from the node record. Its rule moves into §10 as one
sentence — *a column whose `dtype` is `bool` or `list[bool]` holds a selection rather than
a quantity, **and a selection may also arrive as a numeric 0/1 mask, which the type
vocabulary cannot tell from a quantity*** — where a reader looking up the type vocabulary
meets it. The second clause is not decoration: without it a reader takes `bool` ⟹ selection
and infers `f64` ⟹ quantity, which is false of this producer on every comparison it writes.
A consumer that was reading `value_kind` reads `dtype` instead, and the substitution is
exact on every record this producer has ever written — including the comparisons, where
`value_kind` said `value` and `dtype` says `f64` and the two agree in being silent about the
same thing.

**Not a facet.** A facet is for something the specification does not define (§6); this is
something it defines twice. Carrying the restatement in a facet would keep two fields free
to disagree, in a document whose whole claim is that it can be checked.

**What is lost, stated.** Nothing that was true. What is given up is a *place to put* the
claim that an `f64` column is semantically a mask — a claim this producer could already make
about 57 nested comparisons and never has, because the removed field never carried it
either. When that claim is wanted it is a facet of its own — a positive statement about
meaning that `dtype` cannot make — and it arrives additively, with a name that says it is a
claim rather than a type restated.

### 1.5 `engines` required iff `engine_native` — and the third-party exporter

§8.3 makes `engines` optional on purpose: *"The field is optional precisely so that a
third-party exporter can conform without computing something it has no way to know."* An
absent field is no claim; a present empty field is a positive claim of engine-freedom.
Both halves stay.

Measured, the field and the tier move together with no exception:

| `tier` | `engines` | Count |
|---|---|---|
| `core` | `[]` | 263 |
| null | absent | 56 |
| `engine_native` | `["polars"]` | 27 |
| `core` | absent | 2 |

Never `engine_native` with `engines` absent. Never `engine_native` with `engines: []`.
Never a non-empty `engines` beside a null `tier`. All three are admitted by the schema
today.

**The rule, and it is profile-aware, which is where §8.3's rationale is honoured:**

- **`engines` non-empty ⟹ `tier` is `engine_native` *or* `opaque`.** Naming an engine *is*
  a claim that something in the tree reaches into one, which contradicts `core` and
  contradicts a null tier — and stops there. It does **not** imply `engine_native`, because
  §11.2's ladder is about the *weakest* thing in the tree: *"A node's tier is the weakest
  tier reached anywhere in its operation tree. `core` is stronger than `engine_native`,
  which is stronger than `opaque`; one unclassifiable leaf makes the whole node opaque."*
  A tree holding both an engine fragment and an unclassifiable identifier is `opaque` and
  still has a true engine to name.
- **`engines` present and empty ⟹ `tier` is not `engine_native`.** The positive
  engine-free claim and the engine-native claim are contradictories, and a record must not
  make both. That is the whole of what this bullet knows, and it is stated as a refusal of
  one tier rather than a list of the permitted ones, so that it does not quietly refuse a
  null tier the bullet below permits.
- **`tier: null` ⟹ `engines` is absent or empty.** A leaf has nothing to execute; a leaf
  naming the engines its non-existent text needs is a statement about nothing.
- **In the `executable` profile, a `core` or `engine_native` `tier` carries `engines` —
  non-empty where the tier is `engine_native`. An `opaque` tier carries it where the tree's
  walk reaches an engine, and is not required to where the walk reaches none.** This is the
  "required iff" half, widened from `engine_native` because `executable` is the profile where
  the tree is in the file — and stopping one tier short of "every non-null tier" for a reason
  that is measured rather than assumed.

  On `core` and `engine_native` the tree in the file contains the answer and the walk over it
  is exhaustive. A `core` node holds no engine fragment by the definition of its tier, so `[]`
  is true of it; an `engine_native` node holds at least one, so a non-empty list is true of
  it. §12.1's engine-native node **requires** an `engine` field and the schema closes that
  field to `polars`, `jax`, `python`, so the list is a walk of a document the producer already
  holds rather than a fact it has to discover. On those two tiers it costs a third-party
  exporter nothing.

  **`opaque` is the tier where the walk's silence is not evidence, and that is where the
  requirement stops.** Measured at this tip, on the producer's own two walks:
  `Call("acme.unclassifiable", args=(Col("x"), EngineNative("polars", …)))` gives
  `tier_of = opaque` with `_engines_reached = ("polars",)`, and
  `Call("acme.unclassifiable", args=(Col("x"),))` gives `tier_of = opaque` with
  `_engines_reached = ()` (`graph_builder.py:488`). The first has a true engine to name and
  `executable` requires it to name it. The second has none *the producer could see* — the leaf
  that made the node opaque is the one nothing could read — so requiring the field of it would
  require `engines: []`, the positive claim of engine-freedom §8.3 refuses in the words quoted
  three paragraphs below (*"rather than emitting an empty array and saying something false"*).
  A batch that made the format demand that would have made it worse at the first opaque
  emission.

  On this producer the widening costs nothing today: measured across the three `executable`
  exports, **0** of their 322 records carry a non-null tier without `engines`, because
  `engines` is emitted on every `computed` node and a non-null tier occurs on no other kind in
  them. **That measurement covers no `opaque` record** — there are none, as the row below
  says — so it is evidence about the `core` and `engine_native` halves of the rule and about
  nothing else.
- **In the `audit` profile the tree is absent, and the field stays optional exactly as
  §8.3 says.** An `audit` artifact carrying `tier: "engine_native"` with `engines` absent
  is a third-party exporter saying: the tier I was told, the engines I was not. That is the
  case §8.3 was written for, and it survives untouched.

So the answer to the first V6 risk is that the requirement is not on producers, it is on
documents that carry the evidence. Where the evidence is in the file, the claim is
required. Where it is not, the field says nothing, which is what §8.3 built it to do.

**Every `(tier, engines)` state, and which of them the rule refuses.** `tier` has four values
and `engines` has three states — absent, present and empty, present and non-empty — so there
are **twelve**, and all twelve are written out rather than left to be derived from the
bullets above. Measured at this tip, today's schema admits every one of them: `tier` and
`engines` are declared independently with no interdependency between them, so each of the
twelve validates before any of this lands.

| `tier` | `engines` | Verdict | Why |
|---|---|---|---|
| `core` | `[]` | legal | 263 records. Engine-free, and says so. |
| `core` | absent | legal in `audit`, **refused in `executable`** | 2 records, both in hand-built `audit` goldens. No claim either way — §8.3's case. |
| `core` | non-empty | refused | Naming an engine contradicts the core claim. |
| `engine_native` | non-empty | legal | 27 records. The tier and the list agree. |
| `engine_native` | absent | legal in `audit`, **refused in `executable`** | The "required iff" half: where the tree is in the file, the list is a walk of it. |
| `engine_native` | `[]` | refused | A positive engine-free claim beside an engine-native tier. |
| **`opaque`** | **non-empty** | **legal** | **A tree holding an engine fragment *and* an unclassifiable identifier. 0 records today, constructible now.** |
| `opaque` | `[]` | legal | A producer that walked the tree, found no engine fragment in it and is willing to say so. What the walk shows is that no *declared* `EngineNative` is anywhere in the tree; the unclassifiable leaf itself could be anything, so this is a claim the producer makes rather than one the tree proves — which is why the profile rule never forces it. |
| `opaque` | absent | legal in `audit`; in `executable` **refused where the walk reaches an engine**, legal where it reaches none | Two different nodes under one row. The one holding an engine fragment has a true engine to name, and in `executable` it names it rather than taking the out §8.3 built for a producer that cannot see one. The one holding none keeps that out: `_engines_reached` returns `()` there, so the only thing the rule could make it write is the empty array §8.3 declines to require. |
| null | absent | legal | 56 records. A leaf has nothing to execute. |
| null | `[]` | legal, and nothing emits it | The twelfth state, and the one the second and third bullets above are worded to agree on. A leaf making a positive engine-free claim, which is true and useless: nothing in a tree that does not exist reaches an engine. Legal because refusing it would refuse a true record; 0 records carry it. |
| null | non-empty | refused | A leaf naming the engines its non-existent text needs. |

**The `opaque`-with-engines row is measured, not imagined.** The producer's two walks
already disagree with the stronger reading. Given a tree that is a call to an
identifier `TIERS` does not classify, one of whose operands is a Polars fragment,
`tier_of` (`frame/graph/tiers.py:185`, folding by `_STRENGTH` at `:182`) returns `opaque`,
while `_engines_reached` (`graph_builder.py:488`) returns `("polars",)`. A rule reading
"`engines` non-empty ⟹ `engine_native`" would leave that producer three moves and all
three bad: write `engines: []`, which is the positive false claim of engine-freedom §8.3
forbids in its own words (*"rather than emitting an empty array and saying something
false"*); omit the field, and say nothing where it holds a fact; or write
`tier: "engine_native"` and contradict §11.2. **Today's schema admits
`tier: "opaque", engines: ["polars"]`, and that record is true.** A rule going into the
schema as an `if`/`then` must keep admitting it — otherwise this batch makes the format
worse than the one it replaces at the first opaque emission, which is the one thing a
grammar change is not allowed to do quietly.

### 1.6 V14(c) — the facet move, executed

**Decided 2026-09-02, as option (c).** No options are presented. The core edge keeps the endpoints and
the relationship; the subtype moves whole into a producer facet carrying the OpenLineage
vocabulary verbatim; promotion back is additive.

**The core edge becomes three fields:**

```json
{"source": "<node id>", "target": "<node id>", "relationship": "DIRECT"}
```

`relationship` is `DIRECT` or `INDIRECT`, and it is the field §9's own closing sentence is
about: *"'what does this reserve depend on?' and 'what selected the row?' are different
questions, and an impact cone drawn through a key edge is a wrong answer to the first."*
That question is answered by the two-value split and by nothing narrower. The name changes
from `type` because the record already uses "type" for §10's type vocabulary, and because
an edge states a relationship rather than has a type.

**Why the subtype earns a facet rather than the core, measured.** Across 489 edges:

| `type` / `subtype` | Count | Share |
|---|---|---|
| `DIRECT` / `TRANSFORMATION` | 404 | 82.6% |
| `INDIRECT` / `CONDITIONAL` | 37 | 7.6% |
| `INDIRECT` / `JOIN` | 26 | 5.3% |
| `DIRECT` / `AGGREGATION` | 18 | 3.7% |
| `DIRECT` / `IDENTITY` | 4 | 0.8% |

`DIRECT` 426, `INDIRECT` 63. Four of the nine subtype values — `GROUP_BY`, `FILTER`,
`SORT`, `WINDOW` — are emitted by no rule §9 states and appear in no document; §9 already
says so. Of the five that are emitted, one covers 82.6% of every edge in the corpus. The
core carries the distinction that changes an answer, and the narrowing travels beside it.

**The facet.** §6 puts facets in exactly two places — the envelope's `facets` object and a
node's `facets` object — and an edge has neither. So the facet hangs on the **target
node**, which is the natural index: §9 says there is one edge per entry of the target's
`reads`, so the target's own read list is the key, in `reads` order.

```json
"facets": {
  "gaspatchio_column_transformation": {
    "_producer": "https://gaspatchio.dev/spec/graph-artifact/v0-preview.2",
    "_schemaURL": "https://gaspatchio.dev/schemas/facets/gaspatchio_column_transformation-v0-preview.1.json",
    "reads": [
      {"source": "sum_assured",
       "transformations": [{"type": "INDIRECT", "subtype": "CONDITIONAL"}]},
      {"source": "death_claims@1",
       "transformations": [{"type": "DIRECT", "subtype": "TRANSFORMATION"}]}
    ]
  }
}
```

**Verbatim means the inner objects.** `transformations` is OpenLineage's own array name;
`type` and `subtype` are its own key names; the enum spellings are its own, in its own
upper case, with the same pairing rule (`IDENTITY`/`TRANSFORMATION`/`AGGREGATION` with
`DIRECT`; `JOIN`/`GROUP_BY`/`FILTER`/`SORT`/`WINDOW`/`CONDITIONAL` with `INDIRECT`).
OpenLineage's two further members, `description` and `masking`, are available and this
producer writes neither; a consumer must not read their absence as a claim. What is *not*
verbatim is the outer indexing: OpenLineage keys by dataset and field, this document keys
by node id, and pretending otherwise would be borrowing a shape that does not fit.

**Announced, never required.** The facet goes in `facets_used` and never in
`facets_required`: a consumer that has never heard of it reads the same graph, with the
same relationships, and loses only a narrowing. That is exactly §6's test for what may be
optional.

**Promotion back stays additive.** If the narrowing is later wanted in the core, `subtype`
returns as an added required edge field, which §14's additive rule permits without a second
identifier move. The facet is then the older spelling and is retired with a change-log
line. Designing the move so that undoing it is additive is the point of doing it this way
round rather than the other.

### 1.7 The node record after V6 and V14

Removed: `source`, `origin`, `value_kind` (three required fields). Added: `provenance`
(one required field). Net: the node record loses two required fields. The edge loses one
required field and renames another. Nothing in any canonical byte stream moves, because
none of the five fields was ever in one, and edges enter no digest.

---

## 2. V4(b) — the date-literal tag

### 2.1 What the refusal costs today, on the flagship's own first date line

§12.1 states the position: *"A date is not a scalar in this grammar, and the refusal is the
position … a producer handed a date in either place refuses to produce the artifact rather
than encoding it."*

The reference producer does not refuse. It reaches for the escape hatch. Measured on the
flagship at `model.py:294`:

```python
af.duration_mth_init = af.entry_date_parsed.date.months_between(VALUATION_DATE)
```

exports as

```json
{"op": "call", "name": "date.months_between",
 "args": [{"op": "col", "name": "entry_date_parsed"},
          {"op": "engine_native", "engine": "polars", "text": "2024-01-01", "deps": []}],
 "attrs": {}}
```

with `tier: "engine_native"` and `engines: ["polars"]`.

Read that node carefully. The identifier is `date.months_between`, which §11.1 lists at
tier `core` and §11.1.11 gives a signature for — *2 — the start date, then the end date*.
The call was recognised. The operand order is right. The **only** thing making this node
unportable is that its second operand is a date, and the grammar has no tag for one. A core
operation with a stated signature reaches the artifact as something a second implementation
must treat as opaque engine text, and a consumer is told the node needs Polars when what it
needs is a calendar date.

The same line, the same node id, the same fragment text pattern, appears in all three
shipped model exports: `duration_mth_init@1` in the flagship (`model.py:294`), in level-3
(`model.py:237`) and in level-5 (`model.py:413`). One per model; three of the twenty-seven
engine-native nodes across the three model exports.

### 2.2 The tag

**`0x16` — date. A zigzag varint of days since 1970-01-01.**

The number and the layout are the content grammar's, unchanged. §12.3 already assigns
`0x16` to `date` with exactly those bytes, and says why the two grammars share the block:
*"taken from the same block section 12.1's scalar tags occupy, so that a reader holding
both grammars meets one number per type rather than two."* Minting a different number for
the tree would break the one property §12.3 went out of its way to keep.

**The two sections disagree today, and this change picks a side rather than discovering
one.** §12.1 justifies its refusal with *"Reaching for the content grammar's date tags here
would have them mean two things in two grammars"* — the opposite reading of the same shared
block §12.3 calls a feature. Both sentences are in the shipped document. The disagreement is
resolved in §12.3's favour, and the reason is that §12.3 is the section that already made
the block shared and already documented the one place the sharing is a number without a
layout (*"`0x15` shares the number and not the layout"*): a grammar that borrows a byte and
its bytes has not made the byte mean two things, it has made it mean one. Since the whole
§12.1 paragraph is being replaced anyway, the replacement says so, so that the resolution
reads as a decision and not as an oversight.

**`0x17` (datetime) is deliberately not minted for the tree**, and the boundary is stated
rather than left to be discovered. No shipped model writes a datetime literal into a
formula; a tag nothing writes is an untested token in a grammar whose whole value is that
two implementations agree on it. A model comparing against an instant writes the instant
onto the frame in a line of its own and compares against the column, which is what §12.1
told every model to do about dates until now. When a producer holds one, `0x17` lands
additively with a change-log line, and it will already have the content grammar's layout to
copy.

### 2.3 A date is a scalar and not a member: the sequence stays out

**A date may be a literal's whole payload. It may not be a member of a sequence literal.**
The withdrawal of §12.1's refusal is partial, and the boundary is stated here because the
silence would route an implementer to the failure the same section warns about.

The mechanism that makes the silence dangerous is two functions of one file. `_literal`
(`frame/graph/fingerprint.py:274`) hands a tuple's members straight to `_scalar` (`:245`) —

```python
if isinstance(value, tuple):
    return _TAG_SEQUENCE + _sequence([_scalar(member) for member in value])
```

— so the moment `_scalar` learns `0x16`, `Lit((date, date))` becomes **hashable** as `0x15`
over two `0x16` members. Meanwhile the wire has no way to spell it: `op_json._lit_scalar`
(`op_json.py:335`) accepts `bool`, `int`, `float`, `str` and nothing else, and the schema's
`values` items are `boolean`/`number`/`string`. An implementer who meets only the scalar
rule picks one of two outcomes and both are wrong. Widen `values` and `_lit_scalar`, and a
date sequence is written as ISO **text**, encodes as `0x14` and its eleven bytes per member,
and reaches a well-formed digest matching nothing — the failure §12.1's own prose warns
about for scalars, one level down. Leave it, and the IR accepts a tree the wire cannot
write, an inconsistency that surfaces only when some producer path mints one.

**So the boundary is minted in the type and enforced at the door.** `LitScalar` widens for
the scalar position only; the sequence member type does not widen with it:

```python
LitScalar = float | int | bool | str | datetime.date      # one value on its own
LitSequenceMember = float | int | bool | str              # a member of a sequence
```

and `Lit.value` is `LitScalar | tuple[LitSequenceMember, ...]`, so the boundary is a fact a
type checker already knows. `Lit.__post_init__` in `frame/graph/ir.py` refuses a date inside a tuple
at run time as well, beside the finiteness check it already carries, because a producer
reached through untyped code is exactly the caller the type cannot stop. **It raises
`TypeError`, not the `ValueError` the finiteness check beside it raises**, and the choice is
named here because the implementer otherwise has to make it: a date where the member type
admits four other types is a type refused at a type's door, it is what `op_json._lit_scalar`
already raises for the same value in the same position, and it is what §2.5's encoder raises
for the datetime. One mistake, one exception type, three doors. The message is **in the
framework's own voice, naming the position and the next move**:

> `datetime.date(2018, 1, 1)` is not a valid member of a sequence literal at position 0: a
> date is a literal on its own in this grammar and not a member of a band. A membership test
> against a set of dates stays an engine fragment and the node says so; write the dates onto
> the frame as a column and test against the column if the calculation should be in the
> record.

`_lit_scalar`'s refusal already names the sequence it was reading (*"inside a sequence of
N values"*) and keeps doing so, with dates added to the scalar path's accepted list and not
to the sequence path's.

**What that costs, measured.** A date membership set degrades today and keeps degrading.
At this tip `af.entry_date.is_in([date(2018, 1, 1), date(2021, 6, 1)])` exports as

```json
{"op": "engine_native", "engine": "polars",
 "text": "col(\"entry_date\").is_in([[2018-01-01, 2021-06-01]])", "deps": ["entry_date"]}
```

`tier: "engine_native"`, `engines: ["polars"]` — even though `is_in` is a `core` identifier
whose §11.1.11 signature is *"2 — the value, the membership set"*, and §11.1.11 says in its
own words that *"`cut`'s breakpoints and `is_in`'s membership set are operands and not
configuration"*. That is a real remainder and it is named as one, in the same
voice §11.1.9 used for the reduction before §3 closed it: the line stays an engine fragment,
the node says so, and the vocabulary grows when there is something to grow it for.

**Why not mint the sequence form now.** The same reason §2.2 declines `0x17`, and one more.
Nothing writes a date sequence into a formula in any shipped model, so the form would be an
untested token in a grammar whose whole value is agreement. And spelling it is not one key:
`{"op": "lit", "date": "..."}` works for a scalar because JSON has no date token and a key
can carry what a token cannot — but a *sequence* would need either a second key (`dates`,
with a third arm on the branch's `oneOf` and a third refusal surface) or a per-member tagged
form, and picking between those without a producer to check either against is exactly the
guessing this batch exists to remove. When a producer holds one, the form lands additively
with a change-log line, the same way `0x17` will.

### 2.4 §12.1 prose, written to the blind-consumer bar

The bar is the one the document closed to when it was made independently implementable: a
script using nothing but its host language's standard library must derive the encoding from
these words alone, without the reference implementation in front of it. The text below is drafted for §12.1, replacing
the paragraph beginning "A date is not a scalar in this grammar".

> **One tag byte per scalar type** (the existing table gains one row):
>
> | Tag | Scalar type |
> |---|---|
> | `0x16` | date |
>
> **A date** is the number of whole days from 1970-01-01 to the date, counted forward,
> zigzag-encoded and then written as a varint by the rules already given for a whole
> number. 1970-01-01 is `0` and encodes as the single byte `0x00`; 1970-01-02 is `1` and
> encodes as `0x02`; 1969-12-31 is `-1` and encodes as `0x01`. The count is of days and
> never of seconds, milliseconds or microseconds, and it is the same count the content
> grammar of section 12.3 writes behind the same tag, deliberately: a reader holding both
> grammars meets one number and one layout for a date.
>
> **The day count runs on the proleptic Gregorian calendar**, which is the calendar every
> date type in section 10's vocabulary is held on, extended backwards without limit. There
> is no time zone in a date, no offset applied on the way in or out, and no leap second: a
> date is a calendar day, and the count is a count of calendar days.
>
> **A date is not a text and a text is not a date, and JSON cannot tell a reader which it
> is holding.** The wire form is therefore structural and not a spelling: a date literal is
> written `{"op": "lit", "date": "2024-01-01"}`, under its own key, and **exactly one of
> `value`, `values` and `date` is present on a literal**. This is the same discipline the
> section already applies to whole numbers and decimals — the tag comes off the document as
> written, before any parse that would destroy it — arriving through a key rather than
> through a token because JSON has a number token and no date token. A producer that wrote
> a date under `value` has written the text `"2024-01-01"`, which encodes as `0x14` and its
> eleven bytes; a consumer that read `date` as `value` reproduces a well-formed digest
> matching nothing.
>
> **A date is a literal's whole payload and never a member of a sequence.** `values` holds
> flags, whole numbers, decimals and text, as it always has; a date under it is refused. The
> two grammars share this block, and this is the second place where they agree on a number
> and part below it — section 12.3 already says `0x15` shares the number and not the layout,
> and here `0x16` shares both, in a literal and not in a member of one. A membership test
> against a set of dates is therefore an engine fragment, and the node says so, which is what
> this document says about every calculation it cannot yet spell. The sequence form is a
> grammar change like any other, and it lands the day a producer holds one.
>
> **The text under `date` is a calendar date in ISO 8601 extended form and nothing else** —
> four digits, a hyphen, two digits, a hyphen, two digits, for a year in `0000`–`9999` —
> with no time, no offset, no `Z`, and no compact form. A wider year range and the other
> forms are refused rather than accommodated: the value hashed is the day count, so two
> spellings of one day would be one digest under two documents, and a consumer checking one
> against the other could not say which spelling the producer wrote.
>
> **A worked example**, and it is the flagship's own first date line. The date `2024-01-01`
> is 19 723 days after 1970-01-01. Zigzagged that is 39 446, and as a varint, low group
> first, `96 b4 02`. So the literal encodes as five bytes:
>
> ```text
> 02                                       literal
> 16                                       date
> 96 b4 02                                 19723 days, zigzagged, as a varint
> ```
>
> ```text
> 021696b402
> ```
>
> **A date may be a call attribute's value as well as a literal's payload**, by the same
> encoding, because the two share one scalar block. No identifier's signature in section
> 11.1.11 currently puts a date in an attribute — `projection_set`'s `valuation_date` is
> text, an ISO date, and stays text, because the signature says so and moving it would move
> every projection's digest to say something the schedule already says. A signature that
> wants a real date can take one additively.

### 2.5 Encoder and decoder shape

In `frame/graph/fingerprint.py`:

```python
_TAG_DATE: Final[bytes] = b"\x16"
_EPOCH: Final[datetime.date] = datetime.date(1970, 1, 1)
```

Both constants are minted by this change. `_zigzag` (`fingerprint.py:216`) is already in the
module and already takes the whole number the branch below hands it; the epoch is not, and a
branch written against an `_EPOCH` that nothing declares does not run.

Then one branch in `_scalar`, under **two** ordering constraints and no others. The first is
the pair's own — the instant tested before the date. The second is that the pair goes above
the function's terminal refusal: `_scalar` ends in an unconditional `raise TypeError`
(`fingerprint.py:271`) after its five branches, so a date branch written below
that line never runs at all. Nothing else binds — a `date` is not a `bool`, an `int`, a
`float` or a `str`, so no branch already there can claim one, and the pair may sit anywhere
above the raise. The first constraint is exactly the trap the section already documents for
flags:

```python
if isinstance(value, datetime.datetime):
    raise TypeError(...)          # a datetime is not a date in this grammar
if isinstance(value, datetime.date):
    return _TAG_DATE + _zigzag((value - _EPOCH).days)
```

`datetime.datetime` is a **subclass** of `datetime.date` in Python, so a producer that
tested for `date` first would encode an instant as its calendar day and lose the time
silently. That is the same shape of mistake as encoding `True` as the whole number `1`,
which §12.1 already warns about in its own words — *"test for the flag before the number"* —
and the new sentence in the prose above says the same thing for the pair below it: **test
for the instant before the date, or a datetime encodes as a date and `0x17` is never
reached.**

In `frame/graph/ir.py` (`LitScalar` at `:66`, `Lit.__post_init__` at `:101`), `LitScalar`
widens from `float | int | bool | str` to include `datetime.date`, the sequence member type
splits off and does **not** widen with it (§2.3), and the finiteness check gains two
companion refusals: `datetime.datetime` anywhere, and `datetime.date` inside a tuple. In
`frame/graph/op_json.py`, a `Lit` holding a date serialises under the `date` key, and
`_lit_scalar` (`:335`) accepts a date in the scalar position only, its existing
sequence-naming refusal unchanged. `frame/lowering/methods.py` already accepts
`datetime.date` as an operand value (`_OPERAND_VALUES` at `:89` names it), so the
recognition door needs no change: what changes is that `ingress.to_node` mints a `Lit` for a
date operand rather than falling through to `EngineNative`. A *sequence* of dates keeps
falling through, which is the boundary §2.3 states and the reason the two halves of this
change are written down apart.

**Two more edits inside `fingerprint.py` itself, named because a reader checking the file
will meet them and the list above did not.** The terminal refusal's message enumerates the
five types the encoder accepts — *"a formula's literals and configuration must each be text,
a whole number, a decimal, a true/false flag, or absent"* — and after this change it accepts
a sixth, so the message gains the date or it describes a function that no longer exists. And
`_literal`'s own annotation (`:274`) is `LitScalar | tuple[LitScalar, ...]`: the moment
`LitScalar` widens, that signature says a tuple may hold dates, which is precisely the
boundary §2.3 mints. Its tuple arm takes the split member type —
`LitScalar | tuple[LitSequenceMember, ...]` — so the annotation states the boundary instead
of contradicting it one line above the code that enforces it.

### 2.6 The corpus case that covers it

The corpus model (§12.5) carries no date today — no column of one and no literal. It gains
both, in one line, so that the new tag is exercised by the one artifact whose job is to
prove two implementations agree:

- the source frame gains an `entry_date` column of three dates, which makes a **leaf whose
  type is `date`** and whose bytes are `0x20`, its name and the text `date`;
- one new statement compares against a date literal, minting a computed node whose tree
  carries `{"op": "lit", "date": "..."}` and therefore the tag `0x16`.

That is the smallest addition that covers the leaf type and the literal tag together. Its
digests are computed and reprinted in the regeneration unit, not here.

### 2.7 What it buys, counted

The three `duration_mth_init@1` nodes stop being engine fragments. On the flagship that is
one of ten engine-native nodes; the other nine are §3's subject.

---

## 3. V5(a) — the list-reduction family

### 3.1 The hole, in the document's own words

§11.1.9 already names it and says why it is open:

> **What a conforming producer will add.** The reduction of a per-period column to one
> number per policy — the present value that sums a whole discounted cashflow list — is not
> in this vocabulary. Its result has a different shape from its operand, and this document
> has not yet said how an operation states that. Until it does, such a line stays an engine
> fragment and says so.

### 3.2 The flagship's nine lines, counted

`gaspatchio/tutorials/level-4-lifelib/base/model.py:943-951`:

```python
af.pv_claims          = (af.claims * af.disc_factors).list.sum()
af.pv_claims_death    = (af.claims_death * af.disc_factors).list.sum()
af.pv_claims_lapse    = (af.claims_lapse * af.disc_factors).list.sum()
af.pv_claims_maturity = (af.claims_maturity * af.disc_factors).list.sum()
af.pv_expenses        = (af.expenses * af.disc_factors).list.sum()
af.pv_commissions     = (af.commissions * af.disc_factors).list.sum()
af.pv_premiums        = (af.premiums * af.disc_factors).list.sum()
af.pv_inv_income      = (af.inv_income * af.disc_factors).list.sum()
af.pv_av_change       = (af.av_change * af.disc_factors).list.sum()
```

Nine lines. Nine present values. These are the numbers the model reconciles to lifelib at
0.0000%, and the ones a supervisory reader asks for by name.

**Before**, measured: nine nodes, every one `tier: "engine_native"`, `engines: ["polars"]`,
each carrying one tree that is a single engine fragment —

```json
{"op": "engine_native", "engine": "polars",
 "text": "[(col(\"claims\")) * (col(\"disc_factors\"))].list.sum()",
 "deps": ["claims", "disc_factors"]}
```

The multiplication is inside the fragment too. A node that computes a discounted present
value tells its reader: this is Polars text, and the columns it declares it reads are
`claims` and `disc_factors`. The `mul` the actuary wrote is invisible.

**After**, designed:

```json
{"op": "call", "name": "sum",
 "args": [{"op": "binop", "kind": "mul",
           "left": {"op": "col", "name": "claims"},
           "right": {"op": "col", "name": "disc_factors"}}]}
```

`tier: "core"`, `engines: []`. The multiplication reappears as a `binop`. The fold reappears
as a named operation. Nine of the flagship's ten engine-native nodes flip; §2's date literal
is the tenth. **The flagship's engine-native count goes 10 → 0**, and every one of its 128
nodes reports `core` or null.

Across all three model exports: **27 engine-native nodes, and under V4 and V5 together every
one of the 27 flips.** Twenty-four are `.list.sum()` fragments — nine on the flagship, nine on
level 5, six on level 3 — and the other three are the `duration_mth_init@1` date literals §2
is about. There is no remainder.

**There was one until the teaching models' discount change, and it is worth saying where it went rather than quietly
dropping it.** The count was 29 with two that did not flip, both in level 5:
`Series[_disc_factors_full].first()` and
`col("disc_factors_full").list.slice([dyn int: 0, col("month").list.length()])` — neither a
reduction of a period axis, and neither in this design's scope. Level 5 no longer builds a
`disc_factors_full` column at all: it discounts on `af.projection.t_years()`, the jagged
timeline the projection was built on, so the two nodes those lines minted are gone rather
than reclassified. Measured after that change, `disc_factors_full` occurs zero times in all three
exports, and level 5's one `disc_factors@1` node is `core`.

### 3.3 The identifiers and their §11.1 entries

**The identifiers are `sum`, `mean`, `min` and `max`, in the unnamed domain.** Alongside
`cum_prod` and `cum_sum`, which §11.1.9 already establishes as period-axis folds carrying
the engine's own method name. §11's count of the operations that take no domain moves from
fourteen to eighteen. `sum` is the one the census found in the field, and the one the entry
below is written for.

The alternatives were considered and named rather than passed over. `projection.sum` puts a
period-axis fold in the domain whose other members are period-axis operations, but leaves
`cum_sum` — the same axis, the same discipline — in the unnamed domain, and two homes for
one idea is worse than one imperfect home. `period_sum` collides with `PeriodSum`, a
shipped scenario aggregator that folds *across policies* at each period, which is a
different axis and would make one name mean two folds.

Drafted for §11.1.12:

> #### 11.1.12 `sum`
>
> `sum` folds one policy's per-period column to one number: the present value of a whole
> discounted cashflow, the total premium over a projection, the claims paid across a
> lifetime. It is the operation behind the line an actuary writes as
> `(cashflow * discount_factor).list.sum()` and reads as "the PV".
>
> **The semantics.** For a value with `n` periods the result is the sum of periods `0` to
> `n - 1` inclusive. There is no `reverse`: a fold over the whole axis reaches the same
> number in either direction, and an attribute that could not change an answer would be a
> distinction nothing is on either side of. There is no `start_at` and no seed: the sum of
> an empty run is nought, and the sum of one period is that period.
>
> **The shape changes, and the entry is where that is stated.** Every other operation in
> this vocabulary answers in its operand's shape; this one takes a `list` and answers
> `scalar`. Section 11.1.9 left that open — an operation whose result has a different shape
> from its operand had no way to say so — and it is said here, per entry, in prose,
> alongside the operation whose shape it is a fact about. It is not a new field on the node
> record: a node already states the shape of its own answer, and its operand's node states
> the shape of the operand, so a second field would be a third copy free to disagree with
> the two that already exist.
>
> **The fold is along the periods, and along nothing else.** Section 11.1.9's paragraph
> applies here word for word: the operand is one policy's own sequence of periods, and no
> value of one policy reaches another's answer. An engine's method of the same name applied
> to a per-policy column folds down the rows of the model-point file — a different
> calculation, whose answer depends on the order those rows happen to stand in, and one this
> vocabulary does not name. A producer must not write this identifier for it; such a line is
> an engine fragment and the node says so.
>
> **An edge into `sum` is `DIRECT` / `AGGREGATION`** (section 9), by the same rule and for
> the same reason as `cum_sum`: every period is in the answer, and an impact cone told this
> was a transformation of one period's value would be told the opposite of the truth.

**The three siblings take §11.1.13 to §11.1.15 in that same shape, and one paragraph
each differs: the semantics.** `mean` divides the sum by the count of the operand's
own periods that carry a value — the period-axis paragraph above is what fixes that
denominator, since the operand is one policy's own sequence of periods and not the
grid's. `min` and `max` answer the least and the greatest of those periods. **A null
period is absent to the fold — to `sum`'s as much as to these three — and the four
entries state it once, here.** Measured on Polars 1.42.1 along the `.list` axis, one
list per policy folded over that policy's own periods: `[10.0, None, 30.0, 40.0]`
answers `sum` 80.0, `mean` 26.666666666666668, `min` 10.0 and `max` 40.0 — every one
the answer `[10.0, 30.0, 40.0]` gives, and, on the two folds that can tell the readings
apart, not the answer a null read as zero would give (`mean` 20.0, `min` 0.0); `sum`
and `max` give the same number under both readings, as §3.5 says of `sum` — and
`[None]` answers `sum` 0.0 and `mean` null. The shape change, the period-axis rule and
the `DIRECT` / `AGGREGATION` edge are `sum`'s word for word.

And §11.1.11's schedule gains four rows:

| Identifier | Positional operands | Attributes |
|---|---|---|
| `sum` | 1 — the per-period value | none |
| `mean` | 1 — the per-period value | none |
| `min` | 1 — the per-period value | none |
| `max` | 1 — the per-period value | none |

### 3.4 The recogniser

The recognition surface today has two doors and the `.list` namespace has neither.
`_COLUMN_METHODS` (nine entries, `frame/lowering/methods.py`) is reached from
`column/_dispatch_execution.py:348-354`; `_STRING_METHODS` is reached from
`column/namespaces/string_proxy.py:233`. Everything else — `list`, `arr`, `struct`, `cat`,
`bin` — goes through `GenericNamespaceProxy.__getattr__`
(`column/_dispatch_namespaces.py:73-103`), which unwraps the arguments, calls Polars, and
re-wraps the result, so the operation tree only ever meets the finished engine expression.

The design mints a third door in the shape of the second — **but it needs a guard the second
does not have, and copying the string proxy would miss it.** `_STRING_METHODS`'s door asks no
question about the receiver's shape, because no string method is a fold along an axis. The
shape test lives on the *first* door (`_dispatch_execution.py:352`), and all four need it. So
`ListNamespaceProxy` takes its wiring from the string proxy and its guard from the column
door, and the two halves are named apart here so that an implementer copying one file does
not inherit the absence of the other.

- `_LIST_METHODS: Final[dict[str, _Recogniser]] = {"sum": _list_sum, "mean": _list_mean,
  "min": _list_min, "max": _list_max}` in `frame/lowering/methods.py`, with
  `core_list_call(method, receiver, args, kwargs)` beside `core_string_call`. Four
  recognisers of one shape, one per identifier.
- A specialised `ListNamespaceProxy`, added to `SPECIALIZED_NAMESPACES` in
  `column/_dispatch_namespaces.py:40` beside `dt` and `str`, which asks the door first and
  falls through to the engine path when the answer is `None`. The generic proxy stays
  generic; `arr`, `struct`, `cat` and `bin` are untouched.
- Each of the four declines any call carrying arguments — Polars' own `.list.sum()`,
  `.list.mean()`, `.list.min()` and `.list.max()` take none, and minting a node for a call
  the engine refuses would record a calculation that cannot run. This is `_accumulation`'s
  existing discipline, reused.

**The shape test.** `ALONG_THE_PERIOD_AXIS` is the shipped precedent: at
`column/_dispatch_execution.py:352` the mint is declined when the receiver's shape is not
`list`, so that `cum_sum` never names a fold down the model points. All four are subject to
the same test and for a stronger reason — it is only *because* the receiver is a per-period
column that this is the period axis at all. Where the receiver's shape resolves to `scalar`
or `unknown`, the door declines and the call takes the path it always took.

### 3.5 The boundary — which reductions ride now, and what the others wait for

**`sum`, `mean`, `min` and `max` ride. `first`, `last`, `len`, `std` and `median` wait.** The
boundary is stated with the reason the four ride and the two reasons the others wait, so
that a reader meeting it knows it is a position and not an omission.

**First, the measurement that makes the family free.** Counted across the shipped tutorials:

| Method | Occurrences in `gaspatchio/tutorials/**/*.py` | On the flagship |
|---|---|---|
| `.list.sum()` | 136 | 9 |
| `.list.mean()` | 0 | 0 |
| `.list.max()` | 0 | 0 |
| `.list.min()` | 0 | 0 |
| `.list.first()` | 0 | 0 |
| `.list.last()` | 0 | 0 |
| `.list.len()` | 1 | 0 |

**The same counts stated per axis, because the axis is what makes the claim checkable.**
Re-run on 2026-09-03: under `gaspatchio/` — the package and the tutorials it ships, non-test
— `.list.mean(`, `.list.min(` and `.list.max(` occur **zero** times each and `.list.sum(`
occurs **136**; under `tests/` the three siblings are **zero** again and `.list.sum(` is
**36**; across the two together `.list.sum()` occurs **172** times, which is the figure §0
re-derived and did not move.

**Therefore the flip census is unmoved.** The 24 `.list.sum()` fragments of §3.2 remain the
only engine-native flips this unit causes, and no digest anywhere moves for a sibling. The
siblings are covered so that a model written tomorrow records them, not because any shipped
model holds one — and they are covered *in this regeneration* rather than after it because
a sibling added later would move every digest downstream of it a second time, under a token
that had already settled. Batching them is what spares the format that second move.

**Second, the denominator question, and what `std` and `median` wait on beyond it.** A
per-policy timeline gives each policy its own number of periods (§8's `month` is
jagged there, and `schedule.per_policy_period_count` exists for exactly that reason).
Averaged over *which* periods — the policy's own, or the grid's? The two differ for
every policy but the longest, and the difference is a valuation error that survives
testing because a level timeline hides it. For `mean` the answer is the one §11.1.12's
period-axis paragraph already fixes: the operand is one policy's own sequence of
periods, so the denominator is the count of that policy's own periods that carry a
value, and never the grid's. `sum` never had the question — an absent period
contributes nothing under addition, and the two readings give the same number — and `min`
and `max` have no denominator to pick. `std` has a second question the entry shape has no
room for: Polars' `.list.std()` takes a `ddof`, and an identifier carrying a default the
vocabulary never stated would be configuration hidden inside a name. `median` needs a stated
convention for an even period count before it can promise a number.

**Third, `first` and `last` are already in the vocabulary under another name.**
`projection.at_period` with a boundary offset is what they are, and minting a second
spelling of an operation the vocabulary already has is precisely what §11.1.11's four rules
exist to prevent. `len` is a length rather than a fold of values — it is the projection's
own period count, which `projection_set`'s record already carries.

---

## 4. V2(b) — closed operation-tree branches

### 4.1 What is open, and what walks through it

`$defs.expr` is a `oneOf` over seven branches — column reference, literal, binary
operation, call, conditional, state reference, engine-native fragment. **Not one of the
seven carries `additionalProperties` or `unevaluatedProperties`**, so every branch accepts
any key beside the ones it declares.

Six documents that should be refused and were accepted when this was written:

| The slip | Accepted today |
|---|---|
| A `call` relabelled to `state`, its `args` and `attrs` surviving | yes |
| A `call` relabelled to `col`, its `args` surviving | yes |
| A `binop` carrying a stray `attrs` | yes |
| An `engine_native` relabelled to `call`, its `engine` and `text` surviving | yes |
| A `when_then` carrying a fourth branch, `elsewhen` | yes |
| A `lit` carrying a `name` | yes |

The first is the one that matters, and it is the reason the row exists. A node that was a
`call` and now says `state`:

```json
{"op": "state", "name": "projection.at_period",
 "args": [{"op": "col", "name": "select_loaded_claims"}, {"op": "lit", "value": 0.0}],
 "attrs": {"relative_period": -1}}
```

validates clean. It hashes as a state reference — `0x06` and the text
`projection.at_period` — because §12.1's grammar reads the tag off `op` and encodes a
state's bytes as its tag and its name. The operands and the offset are simply not in the
digest.

That node is `prior_period_claims@1` of §12.5's own corpus, with one word changed. Its
canonical bytes as written are seventy-four:

```text
041470726f6a656374696f6e2e61745f706572696f640201147365
6c6563745f6c6f616465645f636c61696d730213000000000000
0000010f72656c61746976655f706572696f641201
```

reaching `sha256:55364b07a9c09f8a1357b7b85e7575b66e13e7d5a7d03cda49985f69860d3795`, which
is the `local_fingerprint` §12.5 publishes for it. Relabelled to `state`, the same document
encodes as twenty-two bytes —

```text
061470726f6a656374696f6e2e61745f706572696f64
```

— reaching `sha256:2e94ac2bdc13ea1044e7bb8f626aae35f958287c10cfd7d5dd47f8c1a5025ef8`.
**Fifty-two bytes of operands and configuration leave the digest, and the document is
valid on the way out.** A file in which one node's whole calculation has been struck out
passes validation and carries a digest that no longer covers what it dropped.

### 4.2 The patch

Each of the seven branches gains `"unevaluatedProperties": false`. Not
`additionalProperties`, and the reason is **robustness rather than necessity** — the
distinction matters, because an implementer who checks a stated necessity, finds it false,
and substitutes the simpler keyword gets something that works today and breaks quietly
later.

Measured: the `lit` branch's nested `oneOf` carries only `required` on each arm and no
`properties` of its own, so `value` and `values` are annotated by the branch's own
`properties` and `additionalProperties: false` **would** refuse a stray `name` today — and
would still after §2 adds `date` to those same outer `properties`. The keyword is chosen
anyway because `unevaluatedProperties` accounts for every key the branch *and its own
subschemas* evaluated, so it survives the day a nested arm declares a property of its own,
which is a change nobody would think to re-audit the closure for. Each branch redeclares
`op` with its own `const`, so `op` is evaluated within the branch and is covered under
either keyword.

All six slips are refused after the patch, verified in memory against the shipped schema
without writing it.

### 4.3 Neutrality, and the envelope's openness left alone

**1100 operation-tree nodes across the three `executable` exports; zero refused after the
patch.** All seven documents validate whole, before and after.

The envelope's stated openness is untouched, and the check is explicit rather than assumed.
The top level declares neither `additionalProperties` nor `unevaluatedProperties`, and
neither does `$defs.node`. A corpus copy carrying an unknown envelope key and an unknown
node key validates **before and after** the patch. §6's round-trip promise — *"a consumer
that meets a facet it does not know … must ignore it, and must preserve it unchanged on any
round-trip"* — rests on that openness, and closing an operation-tree branch does not touch
it. **The closure is of the seven trees and of nothing above them.**

### 4.4 One thing the patch does not do, and the design says so

`oneOf` reports a refusal as *"is not valid under any of the given schemas"*, which names no
key. The message a producer needs is the key it wrote. So the closure lands with a
corresponding finding in `validate.py`'s schema section: where a tree node's `op` names a
branch and the node carries a key that branch does not declare, the finding names the `op`,
the key and the JSON pointer. The schema is what refuses; the validator is what says why.

---

## 5. V24(a) — the rollforward increments summary

**Decided 2026-09-02, as option (a).** The `audit` profile gains a stable record of a compiled
rollforward's working: each increment's label, the order they apply in, and the identities
they carry. Not the full IR.

### 5.1 What a reader can see today, measured

§16 ends by saying what is missing: *"The compiled state machine itself — the states, the
operations, the order they apply in — is not in the `audit` profile."*

A compiled rollforward exported when this was written produces one node —

```
rollforward:ff70eb792aee   kind=rollforward  provenance=rollforward  tier=core  states=['av']
   expr: {"op": "call", "name": "rollforward", "args": [],
          "attrs": {"fingerprint": "sha256:ff70eb792aee2ec58730..."}}
```

— and one running-state node, `state:av@eop`. The machine behind it — a `Grow` labelled
`fund_return`, then a `Charge` labelled `me_charge`, then a `Floor` at nought — travels only
in the `gaspatchio_rollforward_ir` facet (`rollforward_ir_facet` in `frame/graph/rollforward_ir.py`), announced in
`facets_used`, never in `facets_required`, and declared unhashed by its own module: *"Nothing
here is hashed, either -- a facet is wire-side, so a model's fingerprints are what they
were."* The module makes no claim either way about the facet's stability: the word *unstable*
does not appear in it.

**And that facet is not in the `audit` profile at all.** Measured on the same fixture: the
`executable` export carries `facets_used: ["gaspatchio_rollforward_ir"]`, the `audit` export
carries `facets_used: []` and an empty `facets` object, because the emitter returns `{}` on
any profile but `executable` — `if profile != PROFILE_EXECUTABLE: return {}`, at
`frame/graph/artifact.py:422-423`. So an `audit` reader does not
have an unhashed account of the machine — they have none.

So an IFRS 17 CSM roll-forward or a capital roll-forward reaches a supervisory reader as an
identity and a list of state names. The order of the movements — which is the roll-forward —
is in a block that reader is not given, and that a reader who *is* given it receives outside
every fingerprint, with nothing said anywhere today about whether it may change — the
explicit non-promise §5.5 drafts is exactly what is missing.

### 5.2 The label contract

Today a label is free text. `label: str | None = None` on eight of the ten concrete
operations — `Add`, `Subtract`, `Charge`, `Grow`, `GrowCapped`, `DeductNAR`, `Ratchet`,
`Apply`. `Floor` and `Round` carry no `label` field at all. Uniqueness is enforced only
under `track_increments=True` — `_verify_unique_increment_labels`
(`rollforward/_passes.py:47-65`), called from the guard at `:110-111`. That is the exact
citation; `:101-102` is a different `track_increments` guard, the one that checks a label is
present at all.

**Two measurements settle what may be promised about it.**

First, `CompiledRollforward.increment_for(label)` (`rollforward/_compiled.py:203`) resolves
a label to a per-period delta column and refuses an unknown one at the call. **A label is
therefore an interface, not a caption** — something a model reads back by name. Precisely:
it is an interface where `track_increments=True`, and `increment_for` refuses outright
otherwise (`_validate_increment_label`, `_compiled.py:214`), which is the same condition
under which the compiler already guarantees the labels are distinct. That coincidence is not
an accident, and this section's last paragraph is built on it.

Second, and this is the one that decides the contract: a label is already inside the
identity chain. Renaming one label of one increment, changing nothing else, moved every one
of these when this was written:

| | Base | After renaming `fund_return` → `investment_return` |
|---|---|---|
| compiled fingerprint | `sha256:ff70eb79…` | **moved** — `sha256:e30742aa…` |
| the rollforward node's id | `rollforward:ff70eb792aee` | **moved** — `rollforward:e30742aa4004` |
| the rollforward node's `local_fingerprint` | `sha256:d089577e…` | **moved** |
| the rollforward node's `fingerprint` | `sha256:a1f3da08…` | **moved** |
| the reading column's `local_fingerprint` | `sha256:7feb1171…` | **moved** |
| the reading column's `fingerprint` | `sha256:2a12bb74…` | **moved** |
| the artifact's `graph_fingerprint` | `sha256:30ecfbcf…` | **moved** |

Because `_op_canonical` (`rollforward/_canonical.py`) walks every dataclass field of every
operation, and `label` is one.

**So the contract is the one the tree already keeps, stated rather than newly imposed:**

> A label is a name the model's author gave one increment, and it is part of what the
> compilation is. Two compilations differing only in a label are two compilations, they
> carry two fingerprints, and the artifact reports the change. A label is therefore not
> prose in the sense section 8.2 gives `formula`: the quotation of an author sits outside
> identity because editing it changes no calculation, while a label can be read back by
> name and moves the identity of everything downstream when it changes.

There is a real tension there and this design names it rather than hiding it. §8.2's
principle is that identity moves when the computation moves and not otherwise, and a
relabelled increment computes the same numbers. The resolution is that a label is not only
a description: `increment_for` makes it an addressable name, and under
`track_increments=True` it names an emitted field. A name a model can dereference is part of
what the model is. The alternative — excluding untracked labels from the compiled
fingerprint — would make the same string load-bearing or not depending on a flag set
elsewhere, which is a worse contract than either of the two clean ones.

**What is added, and what deliberately is not.** Nothing may be a label that is not a name:
the record requires a label to be non-empty where present. **Uniqueness is required of the
summary and not imposed on the compiler**, and the difference is the whole of this
paragraph.

Today uniqueness is enforced only under `track_increments=True`, by
`_verify_unique_increment_labels` at `rollforward/_passes.py:47-65`, called from the guard
at `:110-111`. The obvious move is to
extend that to every compilation, and it is the wrong one. **That is a breaking change to
the modelling API, not to the artifact format**: a model that compiles today would stop
compiling, and none of §1's four identity surfaces would show it, so the user whose model
broke would not find the reason in §14.1 either. This batch is a format change and it does
not spend a modelling break it does not need.

What it needs instead is that the *document* be citable, and that is a smaller requirement
with a stated home:

- **The requirement.** Within one `increments` array, no label appears twice. Nothing is
  said about compilations that do not produce one.
- **The enforcement point.** The validator's semantic layer, beside the ordinal check §5.4
  already puts there — JSON Schema 2020-12 has no cross-item uniqueness on a member, so the
  schema cannot carry this and saying it in the schema's voice would be saying it nowhere.
- **What a producer does when it cannot meet it.** It omits the summary, which is the same
  conditional presence §5.5 gives the member as a whole. A producer never writes a document
  its own validator refuses, and a model whose labels collide still compiles and still runs.

**And what is given up by not extending the compiler is measured to be nothing that is
reachable.** Where increments are tracked, uniqueness is already guaranteed. Where they are
not, `increment_for` refuses at the call, so no caller can dereference a label at all — the
label is inside the identity chain and nothing else, and two increments sharing one there
name two positions of one compilation, which the ordinal tells apart. The only surface the
duplicate could still blunt is §5.3's cross-artifact fallback — matching on the label where
two compilation fingerprints disagree — and that fallback is already declared a hint and
never an assertion.

An increment with no label — `Floor` and `Round`, which have no field for one — carries
`label: null`, and null is a claim in this record as it is everywhere else in §8: the
producer looked, and the operation carries no name.

### 5.3 What identity an increment carries

**An increment's identity is its position in its compilation: the pair (the compilation's
`fingerprint`, the increment's `ordinal`).** No per-increment digest is minted.

The record carries `ordinal`, counting from 1 in the order the increments apply, which is
the order the array holds them in.

Two arguments, both from doctrine this document already follows.

**A per-increment digest would be a second grammar for a structure the compiler already
hashes once.** §12.1 refuses to restate the machine inside the rollforward node's bytes for
exactly this reason: *"That identity is already a hash over the whole state machine — every
state, every operation, in order — so restating the machine here would hash one structure
twice under two grammars, and the second of them would be this section's rather than the
compiler's."* An increment digest taken under §12.1's grammar would be a third reading of
the same operation, free to disagree with the compiler's.

**And positional identity is what this document already uses for a thing that lives inside
one document.** §8.1: *"Ids are positional within one artifact and carry no meaning across
artifacts, in the way a line number is a position in one document."* An increment is a
position in one compilation. Matching an increment across two artifacts is done on
(compilation fingerprint, ordinal) where the fingerprints agree, and on the label where they
do not — with the same honesty §14.2's change report already applies to a rename: a label
match is a hint, never an assertion.

### 5.4 Order, and whether it gets its own integrity

**It does not get its own integrity field, and it does not need one — it is covered twice
already.**

Measured: swapping two increments moves the compiled fingerprint, the rollforward node's id
and both of its digests, the reading column's digests, and the artifact's
`graph_fingerprint` — the same seven surfaces as a relabelling, none of them still. So the
order is inside the identity chain today. And the document seal — the mechanism has landed;
only its default emission has not — hashes the document's canonical serialization, in which
a JSON array is ordered, so the order is inside document integrity too the moment a document
carries a seal.

Adding a third integrity claim over the order would be the move §17 refuses for a
`state_graph`'s derivable facts — *"written down twice would be free to disagree with what
they were derived from"*.

**The `ordinal` is carried anyway, and it is not an integrity claim.** It is there because a
reader cites "increment 3" and needs the document to number them. The array order is
normative; the ordinal restates it; **and the validator checks the restatement** — ordinals
contiguous from 1, each matching its array position — which is exactly the discipline the
validator already applies to a column's definition ordinals.

### 5.5 The shape

The payload sits on the `rollforward` node, in the `audit` profile, **required where it can
be derived and absent otherwise — exactly the way `states` already is**, which §16 states in
its own words: a producer that cannot reach the compiled artefact *"**omits the field**
rather than writing an empty array"*. "Required" without that qualification would be wrong
and would matter: a producer legitimately omitting the summary would be writing a document
its own schema refuses. The schema identifier still moves — a conditional member added to a
kind is a shape change like any other — so only the reason changes, not the conclusion.

The three conditions under which a producer omits it are collected here rather than left
scattered: the compiled artefact is out of reach (§16's own case, the same one that drops
`states`); an operation the closed list below does not name; or labels that collide within
the one array (§5.2).

```json
{
  "id": "rollforward:ff70eb792aee",
  "kind": "rollforward",
  "states": ["av"],
  "increments": [
    {"ordinal": 1, "label": "fund_return", "operation": "Grow",   "target": "av@eop",
     "reads_running_balance": true},
    {"ordinal": 2, "label": "me_charge",   "operation": "Charge", "target": "av@eop",
     "reads_running_balance": true},
    {"ordinal": 3, "label": null,          "operation": "Floor",  "target": "av@eop",
     "reads_running_balance": true}
  ]
}
```

Five members, and each is chosen against what a reader has to be able to do with it.

- **`ordinal`** — cite one movement.
- **`label`** — name it in the words the model's author used, or null.
- **`operation`** — say what kind of movement it is. The vocabulary is the compiler's own
  operation names, closed at ten: `Add`, `Subtract`, `Charge`, `Grow`, `GrowCapped`,
  `DeductNAR`, `Ratchet`, `Floor`, `Round`, `Apply`. A producer meeting an operation this
  list does not name omits the summary rather than inventing an entry — the same choice §16
  already makes for `states` when the compiled artefact is out of reach.

  **The list has no normative home today and this change gives it one.** Measured: a
  per-name grep over `spec/graph-artifact/v0-preview.md` at this tip returns **0** for all
  ten — `Add` 0, `Subtract` 0, `Charge` 0, `Grow` 0, `GrowCapped` 0, `DeductNAR` 0,
  `Ratchet` 0, `Floor` 0, `Round` 0, `Apply` 0 — and §16 reads whole without listing any of
  them. So a claim that the vocabulary is already "closed and listed in §16" would be citing
  a silent section. **The ten-name enum is added to §16 by the unit that lands this
  payload**, and the manifest says so in that unit's scope and in its §14.1 line, because
  publishing it is a decision and not a citation.

  **The decision, named rather than slipped in.** Publishing the compiler's own Python class
  identifiers as a closed wire enum couples the artifact to `rollforward/_ops.py`'s class
  names: renaming `DeductNAR` in the framework becomes a format change with a change-log
  line, not a refactor. That is accepted, and the reason is that any second vocabulary would
  be a translation table between two names for one operation, free to drift from the thing it
  translates — the same argument §12.1 makes for not restating the machine under a second
  grammar. The names are already load-bearing elsewhere: `_op_canonical` walks the dataclass
  and the class name is inside the compiled fingerprint, so a rename already moves every
  identity in §5.2's table. Publishing them adds a change-log obligation to a rename that was
  never free.
- **`target`** — which running balance the movement lands on, as the state reference
  (`av@eop`), not the `state:` id. §12.1's rule for a running state's name, applied to the
  same string for the same reason.
- **`reads_running_balance`** — whether this increment's amount depends on the balance it is
  changing. This is the framework's own escalation criterion, and it is the answer to the
  question a reviewer asks first about a rollforward: *was a state machine the right tool
  here at all?* §16 says the escalation "is the whole justification for the machinery"; this
  is where the artifact shows it per movement rather than as a claim about the whole.

  **Seven of the ten answer from the operation. Three answer from the expression they carry,
  and the compiler has already read all three.** `Charge`, `Grow`, `GrowCapped`, `DeductNAR`,
  `Ratchet`, `Floor` and `Round` each take the running balance as an operand of the amount
  they apply — a charge struck on the balance, a growth of it, a cost of insurance on the net
  amount at risk, a ratchet or a floor comparing against it, a rounding of it — so all seven
  are `true` **whatever expression they were handed**, because it is the shape of the
  operation and not the shape of its operand that puts the balance in the amount. That is a
  constant per operation and needs no inspection.

  **`Add`, `Subtract` and `Apply` are the three whose expression *is* the amount**, and the
  rule for them is one rule rather than one rule and two assumptions. `Add` is `s += expr`
  and `Subtract` is `s -= expr`, so whether either reads the balance is a fact about `expr`
  and about nothing else — exactly as it is for `Apply`'s `body`. Measured at this tip, on a
  builder whose only state is `av`, all three lower through the same `_classify_arg`
  (`rollforward/_passes.py:270`) and reach the same classification on the same state
  reference:

  ```text
  Add(expr=col("av@eop"))       COMPILES   expr_arg = {"kind": "state", "state": 0, "point": 1}
  Subtract(expr=col("av@bop"))  COMPILES   expr_arg = {"kind": "state", "state": 0, "point": 0}
  Apply(body=col("av@eop"))     COMPILES   body_arg = {"kind": "state", "state": 0, "point": 1}
  ```

  and their canonical forms are the same shape reached through the same door —
  `{"op": "Add", "target": "av@eop", "expr": "col(\"av@eop\")", …}` beside
  `{"op": "Apply", "target": "av@eop", "body": "col(\"av@eop\")", …}`. There is no property
  of `Add` that makes its amount computed without the balance; that is a statement about how
  people usually write one, and a producer built on it would write `false` on a movement
  whose amount **is** the balance it changes — a false answer to the one question the member
  exists to answer, on the movement that most plainly justifies the escalation.

  What bounds all three is the same guard. `Apply`'s docstring calls `body` *"an unbounded
  `pl.Expr`"* — true of the dataclass field and **not** true of anything that reaches a
  compiled artefact. `_classify_arg` reaches `_single_column_name` (`:188`), whose own
  docstring names the fields it governs — *"Add.expr, Subtract.expr, Charge.rate, Grow.rate,
  etc."* — and which **refuses anything that is not a bare `pl.col(...)`**:
  `pl.col("av@eop") + pl.col("override")` raises `NotImplementedError` naming two columns,
  and `pl.col("override") * 2` raises naming the expression, on `Add.expr` exactly as on
  `Apply.body`. What survives is classified into exactly two shapes:
  `{"kind": "state", "state": i, "point": j}` where the name has the `state@point` form and
  both halves are declared, and `{"kind": "input", "idx": k}` otherwise.

  **So the rule for the three is exact and is a reading of the compiler's own classification:
  `reads_running_balance` is `true` where the expression classifies as a read of the same
  state the increment's `target` names, at either point, and `false` otherwise.** The
  comparison is between two *states* and not between two state references, and the case that
  separates the two readings is constructible today: `Apply(body=pl.col("av@bop"))` on target
  `av@eop` classifies as `{"kind": "state", "state": 0, "point": 0}` against a target of
  state 0 at point 1. An amount read off the opening balance of the state being changed is an
  amount that depends on that balance, so the answer is `true`, and comparing the references
  would write a false negative on exactly the criterion the member exists for. A body naming
  `av` without a point is an input column and not the balance — the classifier says so, and
  the summary says what the classifier says rather than what the name looks like.

  **And the member is nullable, for the day that stops being enough.** If the bare-reference
  guard is ever relaxed on any of the three, a producer that cannot classify an expression
  writes `null`, which carries the meaning null carries everywhere else in §8 — the producer
  looked and cannot say — rather than guessing `true` and telling a reviewer a state machine
  was justified when nothing checked. Omission is not the answer there: the omission rule is
  for an operation the vocabulary does not name, and all three are in the list.

**The explicit non-promise, stated in the section's own voice** and drafted for §16:

> **This is a summary and not the machine.** What it carries is the movements, in order,
> with the name each was given and which balance each lands on. What it deliberately does
> **not** carry is the amount of any movement, the expression behind it, its rounding, its
> stopping conditions, its schedule, or the opening value of any state. Those are the
> compiled state machine; they travel in the `gaspatchio_rollforward_ir` facet, which the
> `executable` profile carries and this one does not, **that facet is unstable and will
> change without a compatibility path while this preview is open**, and a consumer must not
> read this summary as a stable projection of it. A reader who wants to re-run the machine
> asks for the `executable` profile, fetches the facet, and accepts what the facet says
> about itself. A reader who wants to know what moved, in what order, and under what name
> reads this, and this is what the `audit` profile promises.

### 5.6 The relationship to §17's `state_graph`

The two are siblings and are easily confused, so §16 gains a sentence pointing at §17 and
§17 gains one pointing back.

**They answer different questions about different objects.** §16's compilation is *one
running balance* accumulating through a sequence of movements within each period — the
escalation the framework takes when a within-period charge depends on the balance. §17's
`state_graph` is a *product whose states are the product* — an income benefit that runs while
a life is disabled, a long-term-care benefit stepping between levels of care — where the
calculation is a solve over transitions.

The structural difference decides the shape of each record. A compilation's increments are
**ordered and applied**: increment 2 lands on the balance increment 1 left, which is why the
order is the calculation and why swapping two moves every digest. A state graph's transitions
are **declared and simultaneous**: the payload carries "one entry per declared transition —
the state left, the state entered, and the intensity governing the move", and no transition
is applied after another.

So: an ordinal here, a state pair there; a `target` here, a `from`/`to` there; an intensity
there and no amount here. **Neither record is the other's shape and neither should grow into
it.** And this record is emitted, against a live compilation, which is the one thing §17's
two sections still cannot say about themselves — §14's first preview-closing condition asks
for exactly that, and this is the section that supplies it for the first of the three.

---

## 6. Principles

Every one of the six serves *Audit by default*: the record says more about the model, in the
`audit` profile, without anyone running a separate workflow to make it say it.

Four of them strain *Meet you where you are* in the same direction and the strain is worth
naming. V6 removes three fields a consumer may be reading, V14 moves a fourth out of the
core, and both refuse documents that were valid yesterday. The answer is that this is a
preview whose stated change policy is documentation rather than compatibility work (§1), the
counter exists so a consumer can tell one from the other (§14), and the alternative — a
record whose six axes admit 6048 combinations of which 13 are meaningful — is a document a
second implementer has to guess at. *Sharp knives, no magic* settles it: refusing the
impossible state is better than accepting it and hoping nobody writes one.

V2 is *Sharp knives* alone: a relabelled node that validates clean and hashes as something
else is the schema failing at the one job the format hired it for.

V4 and V5 serve *Closed-form by default* on the surface where the framework has been telling
its own users the opposite. A present value is a sum of a discounted list — a closed form,
the plainest one in the model — and the artifact has been reporting nine of them on the
flagship as engine text. V5 also serves *No vendor lock-in, by construction*: the flagship
goes from ten nodes a second implementation cannot execute to none.

V24 serves *Audit by default* at the one place the record currently stops: the roll-forward,
which is the disclosure a CSM or capital story is built out of.
