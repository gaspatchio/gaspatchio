# The regeneration manifest

**DRAFT.** The design it manifests is
`ref/17-calc-graph/specs/2026-09-03-token-batch-design.md`. Nothing here has landed. Every
figure was measured on 2026-09-03, on a tree where the frozen corpus digest is
`sha256:2fbb4e8f3ab24542a1f53715aef273e50f4e3c7888a11f52b0f5d3433ce4b42e` and has not moved.
The shipped tutorials have changed since, and every figure re-measured against that change was
re-taken after it, later the same day, and says so where it stands; the frozen digest has not
moved there either. `uv run pytest tests/graph` is **1262 passed** before the tutorials' change
and **1279 passed** after it. The baseline a "stays green" claim below is measured against is
the count at the implementer's own tip; both figures are printed so that neither is mistaken
for a constant.

The format's users are owed **one** loud, documented digest change with its reasons
attached, not several quiet ones. This document is the list of everything that travels in
it, the order the work lands in, and the public record that ships in the same commit.

---

## 1. Every digest that moves

Read the table with §12 in hand. There are four independent identity surfaces and a change
can touch any subset of them:

- **`fingerprint_algorithm`** — the byte-grammar token. Moves iff §12.1's or §12.3's grammar
  moves, for any reason, however cosmetic.
- **Node `local_fingerprint` / `fingerprint`** — moves iff a node's canonical bytes move.
  The only node-record fields inside those bytes are `kind` (a leaf's tag), the leaf's name
  and a leaf's `dtype`; everything else in the record is outside them, verified in
  `frame/graph/fingerprint.py`.
- **`graph_fingerprint`** — §12.4's three sections: (node id, node fingerprint) pairs,
  assumption table content hashes, unaccounted column names. Edges are in none of them.
- **The `schema` identifier** — moves when a document valid under the old shape stops being
  valid, or vice versa.

| # | Passenger | Grammar token | Node digests | `graph_fingerprint` | Schema identifier | Why |
|---|---|---|---|---|---|---|
| 1 | **V6(b)** node-record collapse (`source`+`origin` → `provenance`; `value_kind` folded into `dtype`; `engines`/`tier` rule) | **no** | **no** | **no** | **yes** | None of the five fields is in any canonical byte stream. Three required fields are removed and one added, so a document valid before is invalid after and the reverse. |
| 2 | **V14(c)** edge facet move (`type`→`relationship`; `subtype` → `gaspatchio_column_transformation`) | **no** | **no** | **no** | **yes** | Edges enter no digest. A required edge field is removed and another renamed. |
| 3 | **V4(b)** date-literal tag `0x16` | **YES** | only nodes carrying a date literal | only artifacts holding such a node | **yes** | A new tag byte is a grammar change (§12.2), and the token moves for any grammar change at all. The `lit` branch gains a `date` key; `values` does not widen, and a date inside a sequence stays refused (§7). |
| 4 | **V5(a)** the list-reduction family — `sum`, `mean`, `min`, `max` | no | **YES** — every node that was a `.list.sum()` fragment, and everything downstream of one | **YES** on any artifact holding one | no | A `call` has been hashable under §12.1 since it was written; what changes is what the producer emits. Same reasoning as `mortality.at`'s change-log line. Only `sum` moves a digest: the three siblings occur zero times in the package, the tutorials and the tests, so they are covered for a model written tomorrow rather than for one that exists (design §3.5). |
| 5 | **V2(b)** closed `$defs.expr` branches | no | no | no | **yes** | Documents with stray keys inside a tree stop validating. Measured after the tutorials' change: 1100 shipped tree nodes, none refused. |
| 6 | **V24(a)** rollforward increments summary | no | no | no | **yes** | A member added to `rollforward` nodes — required where derivable, absent otherwise, exactly as `states` is (§16 omits that field rather than writing an empty array). An added conditional member on a kind is still a shape change. Nothing about it is hashed — the compiled fingerprint already covers the labels and the order. |
| 7 | deferred corpus-member migrations from the re-entry work | — | — | — | — | **There are none.** See §2. |
| 8 | **document-seal** `document_digest`, default emission flipped on | no | no | no | **yes** | An envelope field, outside every canonical byte stream (it seals a written record, not an identity, and includes `created_at`). **Defined and optional under `v0-preview.1`**, which is where §7, §13.1 and its §14.1 line already are: an optional member changes no document's validity, so nothing about defining it reached the identifier. What travels here is the default emission and, with it, the member becoming **required** — the half that breaks validity, since a document written without a seal stops validating. That break is what the change log has to announce, and it is not on its own what moves the identifier: §14.1's `reads_assumptions` line added a **required** field inside `v0-preview.1` with the counter unmoved, which is the wart §14 spends a paragraph on. The identifier moves here for rows 1-3, 5 and 6 in any case, so this passenger travels with it either way. |
| 9 | anything else the tree holds behind a flag | — | — | — | — | **Nothing.** See §2. |

**The four crossings this table is for.**

- **The grammar token moves exactly once, and only V4 moves it.** `gspv0-preview-1` →
  `gspv0-preview-2`. V5 emits different documents under an unchanged grammar; V6, V14, V2,
  V24 and document-seal touch no bytes any digest is taken over.
- **The schema identifier moves exactly once.** `gaspatchio-graph/v0-preview.1` →
  `gaspatchio-graph/v0-preview.2`. Six of the nine rows force it; one move covers all six.
  §14's monotone-counter rule is what the counter is for, and §5's dispatch means a tool
  holding only `v0-preview.1` fails loudly rather than misreading a `v0-preview.2` document.
  §12.2's schema pin on `fingerprint_algorithm` moves in the same edit, since the schema
  pins the token by `const` today and that pin only relaxes at `/v0` final.
- **The corpus's own node digests move only because the corpus model grows.** V6, V14, V2,
  V24 and document-seal move none of the corpus's eight nodes' bytes, and V5 moves none
  either — the corpus writes no reduction. **V4's tag moves nothing in the corpus as it
  stands**, because the corpus holds no date. So without a deliberate addition the corpus
  would come out of a grammar change byte-identical in every digest, under a new token: two
  artifacts, one per token, carrying the same `graph_fingerprint`, which §12.2 says must not
  be compared. §3 is where that is resolved rather than tolerated, for the corpus (§3.1)
  and for the three other pinned goldens (§3.3).
- **The flagship is not a corpus member and no golden pins its export.** The only pinned
  digests in the tree are `goldens/conformance_corpus.json` with §12.5's table, and the
  §12.3 worked example in `tests/test_content_identity_grammar.py:50`, which the content
  grammar's stillness leaves alone.

### What each passenger costs the flagship, counted before the tutorials' change

The flagship — `level-4-lifelib/base`, the model reconciled to lifelib at 0.0000% — is 128
nodes and 184 edges. Before: **10 engine-native nodes**, nine from `.list.sum()`
(`model.py:943-951`) and one from a date literal (`model.py:294`, an otherwise-core
`date.months_between`). After V4 and V5: **none**. Every node reports `core` or null, and
its `graph_fingerprint` moves once, through the nine reduction nodes and everything
downstream of them.

---

## 2. Two claims verified rather than relayed

**The re-entry work deferred no corpus migration, and the claim is checked here rather than
taken.** The corpus model is `_the_corpus_model()` at
`tests/graph/test_conformance_corpus.py:66` — seven hand-built columns defined inside the
test module itself *"so that it cannot drift from the file it produced"* — and
`goldens/conformance_corpus.json` is that function's export and nothing else's. No tutorial
model contributes a node to it, so no change to a tutorial can put a member into the corpus
to be migrated. **Row 7 of the table is empty and stays empty.**

One nearby item is worth naming so it is not mistaken for a deferred migration: the
flagship's own setup-stage round-trip is untouched, because it belongs with a reconciliation
run. That is a decision about a tutorial, not a corpus constraint, and it is neither a
passenger nor a blocker.

**Nothing else in the tree is held behind a flag against the token.** Searched for environment
switches and feature toggles across `frame/graph/` and `frame/lowering/`: none at the tip this
was measured at. The only flag this batch is waiting on is document-seal's, whose wire change
lands only with the token-finalisation regeneration and whose default flips in that commit.
**Row 9 is empty at this tip and must be re-checked immediately before the regeneration
lands**, because any later unit may add one.

That flag now exists and is named, so the flip is a known edit rather than a search:
`SEAL_BY_DEFAULT` in `frame/graph/artifact.py`, `False`, read as the default of both
`build_artifact(..., seal=)` and `GraphExporter.export(..., seal=)`. It is an ordinary module
constant and not an environment switch, deliberately — a document's contents should not depend
on what was exported in the shell — and moving it to `True` is the whole of row 8's emission
half.

**One class of pending change can be ruled out of row 9 now rather than re-discovered.** Any
change to how an assumption artefact is named or identified is incapable of moving a corpus
digest, because the corpus model carries no assumption entries at all:
`test_the_corpus_holds_no_rollforward_and_no_assumption_payload`
(`tests/graph/test_conformance_corpus.py:310`) asserts `published["assumptions"] == []`, and
the published file carries `"assumptions": []` at this tip. §12.5's stated exclusions are
what make that permanent rather than incidental. Anything touching assumption naming is
therefore not a passenger, and the generic hedge above does not have to cover it.

---

## 3. The corpus, and what the new frozen digest covers

### 3.1 Why the corpus model grows

§12.5's corpus exists so *"a second implementation can prove agreement before claiming
it"*, and the same section requires it to be *"regenerated and reprinted whenever
`fingerprint_algorithm` changes"*. A grammar that grows a date tag, with a corpus that
writes no date, would leave the one new token in the grammar untested by the one artifact
whose job is to test it — and would publish two artifacts under two tokens carrying
identical digests, which is the shape §12.2 forbids comparing and which a careless consumer
would compare.

So the corpus model gains a column and two statements, and the additions are the minimum that
exercises what moved:

```python
# a date column, so that a leaf of type `date` is hashed
af = ActuarialFrame(pl.DataFrame({
    "sum_assured": [100_000.0, 250_000.0, 500_000.0],
    "entry_date": [date(2019, 3, 1), date(2021, 7, 15), date(2023, 11, 30)],
}))
...
# a date literal in a tree -> tag 0x16 (V4)
af.post_reform = when(af.entry_date > date(2022, 1, 1)).then(1.0).otherwise(0.0)
# a reduction -> the `sum` identifier, list operand, scalar answer (V5)
af.total_claims = af.select_loaded_claims.list.sum()
```

**`.list.sum()` and not `.sum()`, and the difference is the whole of what this line is for.**
`select_loaded_claims` is `list[f64]`, and a bare `.sum()` on it is the engine's fold down the
*rows* of the model-point file: measured at this tip it does not resolve at all
(`InvalidOperationError: 'sum' operation not supported for dtype 'list[f64]'`). `.list.sum()`
resolves — `[461.25, 1153.125, 2306.25]` on the three model points above — and it is also the
only spelling V5 recognises, because §3.4's new door is `_LIST_METHODS` on a
`ListNamespaceProxy`. §11.1.12 says the same thing from the other side, and in its own voice
forbids writing this identifier for the fold down the rows. A corpus grown with the bare
spelling would exercise neither half of V5.

That covers, in one artifact: the new scalar tag; a leaf whose `dtype` is `date`, which no
corpus leaf has carried; the new `sum` identifier with its shape change; and the
`DIRECT`/`AGGREGATION` edge the reduction takes. It leaves §12.5's stated exclusions intact —
still no rollforward and no assumption table, so the corpus does not move when §15, §16 or
§17 land.

### 3.2 What the new frozen digest covers

The new `graph_fingerprint` replaces
`sha256:2fbb4e8f3ab24542a1f53715aef273e50f4e3c7888a11f52b0f5d3433ce4b42e` and covers a
strictly wider surface:

| Covered before | Added |
|---|---|
| arriving column; arithmetic; conditional; sequence literal; accessor call with a typed offset; injected column; a column written twice | a `date` leaf type; a date literal under tag `0x16`; a `call` whose answer's shape differs from its operand's |
| eight nodes over seven columns, ten edges | eleven nodes over ten columns, twelve edges, one of them the `DIRECT`/`AGGREGATION` edge — and three of those four are measurable on the grown model today while the fourth is a consequence: built at this tip the twelfth edge is `DIRECT`/`TRANSFORMATION`, and it becomes `AGGREGATION` when V5 lands and §11.1.12's rule reaches it, which is the state the new frozen digest is taken over |
| taken under `gspv0-preview-1` | taken under `gspv0-preview-2` |

Every node record in the file also carries the new `provenance` in place of `source`,
`origin` and `value_kind`, the new `document_digest` on the envelope, and edges of the new
three-field shape — none of which moves a digest, all of which changes the published file.

**The old digest is retired, not superseded in place.** §12.2's rule is that two artifacts
carrying different tokens must not be compared — *"Not 'compared with care' — not
compared."* The decision record (§6) says so in the words a reader will meet.

### 3.3 Three more pinned goldens, exempt because nothing asks them to prove anything — decided, not deferred

§3.1's finding is that without a deliberate addition the corpus would come out of a grammar
change byte-identical in every digest under a new token. Measured at this tip, three more
pinned documents have that property. **They are exempt, and the reason is that nothing asks
them to prove anything and nothing re-derives what they carry.** §12.5's regeneration
obligation names the corpus — *"regenerated and reprinted whenever `fingerprint_algorithm`
changes"* — and no other document, and the digest table printed below it in that same section
is the corpus's and no one else's: two facts about one section. **Not §12.2.** That section is
the token's — opaque, equality the only operation, moves for any grammar change — and carries
no regeneration language at all; the word occurs twice in the whole specification, at §12.5
and in a §14.1 line reporting a regeneration that had already happened. Their own digests are
written-in constants in hand-built JSON: the tests validate each file
(`validate_artifact(...).ok`) and read fields off it, and not one re-derives a
`local_fingerprint`, a `fingerprint` or a `graph_fingerprint` from a model.

**Measured, and the measurement is stated as it was run rather than as a summary of it.** The
envelope `graph_fingerprint` and both digests of every node in all three files — thirty-nine
values — each replaced with a **different** one: `uv run pytest tests/graph -q -p
no:randomly` is **1279 passed**, unmoved from the baseline. Give all thirty-nine *one* constant
instead and a test does notice, and it is worth naming rather than avoiding, because it is a
live constraint on a file §5 asks unit 7 to hand-edit: `test_supervisory_annex.py:141` asserts
`local != folded` on every node of the annex golden, and the one-constant run is `1 failed,
1278 passed`. **So the invariant a hand edit must keep on that golden is per node:
`local_fingerprint != fingerprint`.** What the distinct-value run establishes is the claim
actually being made — nothing re-derives these digests from a model — and not that any value
whatsoever is admissible.

**The property they share with the corpus is not a reason, and it is worth saying so before a
reader checks it.** All three are `audit` exports carrying **zero operation-tree nodes** — and
so is the corpus, which is not exempt, because its digests are taken over the trees the
`audit` profile declines to print. A tree count separates none of the four.

| Golden | Token | Trees | Holds a date? | Holds a reduction? | `graph_fingerprint` |
|---|---|---|---|---|---|
| `annex_example_artifact.json` | `gspv0-preview-1` | 0 | no | no | `sha256:ef6a6609…` |
| `state_graph_example.json` | `gspv0-preview-1` | 0 | no | no | `sha256:aecf533c…` |
| `nested_valuation_example.json` | `gspv0-preview-1` | 0 | no | no | `sha256:5c44909e…` |

§5 regenerates all three with no digest moving, so each does come out of unit 7 with its
`graph_fingerprint` unchanged under `gspv0-preview-2`. **They are not given the corpus's
treatment, and the reason is that the corpus's treatment was never about the collision.**

§3.1 gives two reasons for growing the corpus and only the first is load-bearing: a corpus
that exercises none of the token's change proves agreement about the *previous* grammar
while being published beside the new one, which is a corpus that has stopped doing its one
job. That reason does not reach the three above, because they prove agreement about nothing
by design. They illustrate a record's shape — an assumption-bearing input, a `state_graph`, a
`nested_valuation` — and §17 asks of two of them only that the schema still accept them
whole, which unit 7 re-checks.

The second reason — a careless consumer comparing two documents under two tokens — survives
for all four and is answered rather than removed. A consumer that obeys §12.2 never reaches
the comparison. A consumer that disobeys it gets, on these three, a **true** answer: no
byte of any node moved, because none of these documents holds a byte the grammar change
touches. That is the difference between a collision and an agreement, and it is why adding
content to three hand-built illustrations — three files rewritten, three sets of node digests
re-derived by hand, §17's acceptance evidence re-run — would buy nothing the rule does not
already give. What each of the three *does* gain is the record-shape change every document
gains: `provenance`, the new edge shape, `document_digest`. Two files under two tokens with
one `graph_fingerprint` and different contents is exactly what "no node's bytes moved" looks
like written down.

---

## 4. Ordering of the follow-on units

Seven units. One edge is forced inside the batch, two more constrain its end; everything
else is free, and the free order below is chosen so that each unit's coverage reads on its
own.

| Order | Unit | What lands | Ordering reason |
|---|---|---|---|
| 1 | `edge-facet` (V14) | Core edge to endpoints plus `relationship`; the `gaspatchio_column_transformation` facet with its own schema; `facets_used` wiring | Free. First because it is the only passenger that touches `facets_used`/`facets_required`, and landing it alone keeps that surface's coverage readable |
| 2 | `node-record-collapse` (V6) | `provenance`; `value_kind` folded into `dtype`; the `engines`/`tier` rule with its profile split; the per-`kind` constraint in the schema; §8, §8.3, §10 and §12.1's collision paragraph rewritten | Free. Second because it is the largest read-side change and everything after it writes node records |
| 3 | `rollforward-increments` (V24) | `increments` on the `rollforward` node; **the ten-name `operation` enum added to §16**, which is where it acquires a normative home; the label contract with its uniqueness scoped to the array and checked in the validator's semantic layer; the ordinal check; the `reads_running_balance` rule for `Add`, `Subtract` and `Apply`, whose expression *is* the amount, beside the constant it is for the other seven; §16's non-promise | Free |
| 4 | `reduction-op` (V5) | The `sum`, `mean`, `min` and `max` identifiers, §11.1.12 to §11.1.15, the four 11.1.11 rows, `ListNamespaceProxy` and `core_list_call` | Free |
| 5 | `date-literal-tag` (V4) | Tag `0x16`; the `date` key on the `lit` branch; §12.1's prose; the encoder's datetime-before-date refusal | **Must precede unit 6** |
| 6 | `expr-branch-closure` (V2) | `unevaluatedProperties: false` on each of the seven branches; the validator finding that names the offending key | **Must follow unit 5** |
| 7 | **`the-regeneration`** | Everything in the list below, in one commit | **Must follow all six, and document-seal** |

**The three forced edges.**

1. **V4 before V2.** V2 closes the `lit` branch; V4 adds a key to it. The other order
   refuses a document the next unit writes.
2. **document-seal's design-and-build half before the regeneration.** Its wire change is
   held behind a flag by its own instructions, and its default flips in the regeneration
   commit. If
   that unit has not run when the regeneration is ready, the regeneration lands without row
   8 and the seal flips in a later commit — which costs the "one loud change" story a
   second, quieter one, and is the reason to run it first.
3. **Everything before the regeneration.** The regeneration is the only commit that moves
   the token, the schema identifier and the corpus. A passenger that lands after it needs a
   second regeneration, which is the failure this whole exercise exists to avoid.

**Units 1–6 land behind the flag, in this sense:** each may change the producer, the schema
and the specification prose, but **none of them regenerates the corpus and none moves the
frozen digest**. Where a unit's change would move a digest — V4 and V5 are the two, as rows 3
and 4 of §1's table say, and V4 alone moves the token — the emission is written and
covered but not turned on by
default until unit 7. Concretely: V5's recogniser lands with its tests exercising it
directly rather than through a corpus export, and V4's encoder lands with the tag defined
and refused-by-default at the door.

### 4.1 Units 1 and 2 rewrite the corpus **file**, and every digest in it stays where it is

**This is the paragraph an implementer is most likely to need and most likely to be misled
by, so it is stated flatly.** "None of them regenerates the corpus" is a statement about
*digests*, not about *bytes*. Two of the six change the published corpus file, and the suite
goes red at both until it is rewritten.

The reason is one assertion:
`tests/graph/test_conformance_corpus.py::test_the_corpus_is_still_the_artifact_this_producer_writes`
(`:378`) exports the corpus model afresh, deletes `created_at` and `producer` from both
sides, and asserts **full-document equality** with the published golden. V14 changes every
edge key in the fresh document; V6 changes every node record. Both go red at their own unit.
`test_the_corpus_covers_every_shape_it_was_built_to_pin` additionally asserts
`nodes["sum_assured"]["source"] == "model_points"` and
`nodes["simulated_shock@1"]["source"] == "injected"` (`:339-340`), both of which break at
unit 2. **13** test files under `tests/` read a node's `source`/`origin`/`value_kind` or an
edge's `subtype` and move with them. The baseline is green — 1279 passed after the tutorials' change — so
this is a transition and not pre-existing red.

| Step | Unit | Corpus file | Corpus digests | How it is verified |
|---|---|---|---|---|
| **R1** | 1 (V14) | **rewritten** — every edge takes the three-field shape; the `gaspatchio_column_transformation` facet appears on reading nodes; `facets_used` grows | **unmoved** | Every `local_fingerprint`, every `fingerprint` and the envelope `graph_fingerprint` compared **byte-identical before and after**, and `graph_fingerprint` still `sha256:2fbb4e8f…`. Edges enter no digest (§1), so a moved digest here is a defect and not a regeneration. |
| **R2** | 2 (V6) | **rewritten** — every node record takes `provenance` and loses `source`, `origin`, `value_kind`; the `engines`/`tier` rule applies | **unmoved** | The same comparison, and the same expected answer. None of the five fields is inside any canonical byte stream, so a moved digest here is a defect. |
| — | 3–6 | untouched | unmoved | The corpus carries no rollforward, no reduction, no date and no tree, so V24, V5, V4 and V2 change nothing in it. |
| **R3** | 7 | **regenerated** | **moved, once** | §5's acceptance condition: the digests are reprinted from the file the regeneration command wrote. |

The three hand-built goldens are hand-edited alongside the corpus at R1 and R2, under the
same rule and the same check: their records change, their digests do not.

**The reflex to be careful of, and what it actually costs — measured, because a warning an
implementer tests and finds false is worse than none.** The obvious reaction to a red suite at
unit 1 is to run the regeneration command and let it rewrite the file. That command is
`_write_the_corpus()` (`tests/graph/test_conformance_corpus.py:117-120`) and it is four lines:
export the model, write the file. Run against the corpus as it is published, it moves
**nothing but `created_at`** — `graph_fingerprint` still `sha256:2fbb4e8f…`, every node
digest byte-identical, the token still `gspv0-preview-1`, the `nodes` and `edges` arrays
unchanged. At units 1 and 2 the same holds, for the reason R1 and R2 give: edges enter no
digest and none of the five node-record fields is inside a canonical byte stream. So what the
command writes at either unit **is** the file those two rows want, digests unmoved. It is not
the failure this batch exists to prevent, and saying it is spends the section's credibility on
a claim that does not survive being run.

**What the command does not do is check, and that is the caution.** The two tests it repairs —
`test_the_published_corpus_is_reproduced_exactly` and
`test_the_corpus_is_still_the_artifact_this_producer_writes` — both hold the published file
against a fresh export, so a regeneration turns them green whether a digest moved or not.
Measured: with the file and the fresh export agreeing and the specification's printed digests
left alone, the only tests that fail are the two comparing §12.5's table against the file — one
for the envelope `graph_fingerprint`, one for the per-node table. So the byte-identical
comparison R1 and R2 specify is not something the suite performs on your behalf at units 1 and
2; it is the step that makes their claim checkable, and the command performs no part of it.

**Where an early emission costs something is not where the reflex suggests, and the difference
is worth measuring rather than warning about.** V5's records and V4's tag are the only changes
in this batch that move a digest, and §4 keeps both off by default until unit 7. But **neither
can move a corpus digest at units 1–6, whatever emission is on and whatever the command is run
against**, for the reason §1's fourth crossing bullet already gives. Measured after the tutorials' change:
`_the_corpus_model()` is seven columns holding no date column, no date literal and no `.list.`
call anywhere, and its exported document contains the substring `date` zero times and `.list.`
zero times. There is nothing in it for either emission to reach until §3.1 grows the model,
and §3.1's growth is unit 7's.

**What an early emission moves is the three shipped model exports, and it moves them
silently.** Measured after the tutorials' change: 27 engine-native nodes across the three, and under V4 and V5
together **all 27 flip** — 24 `.list.sum()` fragments and the three `duration_mth_init@1` date
literals — so the flagship goes 10 → 0 and its `graph_fingerprint` moves with them. **Nothing
pins any of that**: no test asserts a tutorial's `graph_fingerprint`, and no Python file under
`tests/graph/` carries a full `sha256:` constant at all — the four goldens do, and the only
one elsewhere in `tests/` is §12.3's worked-example content hash. So the suite stays green
while the record of every teaching model changes underneath it, and the change reaches the
corpus only in the commit that also grows the corpus model — which is unit 7, where the §14.1
line and the reprinted §12.5 table are.

**That is what "one loud change rather than several quiet ones" is defending against**, stated
on the fact that survives being run: not a corpus rewritten out from under a careless command,
but a batch whose digests moved in stages nobody had to notice, leaving unit 7 to announce a
move that had already happened piecemeal. At R1 and R2 the corpus file is edited to the new
record shape and the digests inside it are left exactly as they are.

So the "stays green" promise is precise: `uv run pytest tests/graph` is green at the end of
every intermediate commit, against a `conformance_corpus.json` whose *digests* have not
moved — not against an unmodified file.

**Unit 7, the regeneration, is one commit** and does all of this at once:

- flips V4's and V5's emission on, and `SEAL_BY_DEFAULT` to `True`;
- adds `document_digest` to the schema's envelope properties **and to its `required` list**,
  which is the half of row 8 that moves the identifier;
- moves `FINGERPRINT_ALGORITHM` to `gspv0-preview-2` and `SCHEMA_ID` to
  `gaspatchio-graph/v0-preview.2` (`frame/graph/artifact.py`, at the two `Final` constants —
  find their lines at the tip, they have moved since this was written), and the two
  matching `const` pins in `schemas/gaspatchio-graph-v0.schema.json`;
- grows the corpus model in `tests/graph/test_conformance_corpus.py` and regenerates
  `goldens/conformance_corpus.json` with
  `uv run python -m tests.graph.test_conformance_corpus`;
- reprints §12.5 — the model, the trees, the reads, and both digests of every node — and the
  new `graph_fingerprint`;
- regenerates the three hand-built goldens (§5);
- lands the decision record (§6).

**Six tests go red the moment the seal is on, so they are written here rather than
discovered.** Measured with `SEAL_BY_DEFAULT` as the only line changed, at the tip this
paragraph was written against, on 2026-09-03: `uv run pytest tests/graph -q -p no:randomly` →
`6 failed, 1271 passed in 41.09s`. They are not one kind of thing. Two are format facts to
state rather than test edits, and one is a class rather than a case.

- **`test_conformance_corpus.py`** —
  `test_the_corpus_is_still_the_artifact_this_producer_writes`
  exports the corpus model afresh, deletes `created_at` and `producer` from both sides, and
  asserts full-document equality against the published golden (§4.1). **Deleting those two is
  no longer enough**: the seal is taken with `created_at` inside it, so the golden's seal is
  over the golden's timestamp and a fresh export's is over a different one, and the two
  documents disagree in a member neither deletion reaches. *Owed:* delete `document_digest`
  from both sides too, for exactly the reason the other two are deleted — the comparison is of
  the record of the calculation, and these three are what a re-export moves without the model
  moving. The same applies anywhere else a fresh export is held against a stored document.
- **`test_artifact_envelope.py`** —
  `test_the_envelope_carries_exactly_the_members_the_specification_defines`
  pins the envelope's members as a tuple in §7's order. *Owed:* `document_digest` joins that
  tuple, **last**, which is where the producer writes it — a seal is taken over a finished
  record. Measured on a flipped export: the final key is `document_digest`.
- **`test_document_seal.py`** —
  `test_nothing_this_producer_exports_carries_a_seal_unless_it_is_asked`
  asserts `SEAL_BY_DEFAULT is False` and that a default export carries no seal. *Owed:* the
  assertion turns over with the default. What is still worth pinning, and was measured on the
  flip, is that a default export carries the member and an explicit `seal=False` still writes
  none, so a caller who wants an unsealed document has one.
- **`test_executable_profile.py`** —
  `test_an_executable_artifact_is_also_a_conforming_audit_artifact`
  deletes `created_at` and `profile` from an `audit` and an `executable` export of one model,
  drops each node's `expr`, and asserts the two are then equal. Sealed, they differ in the
  seal as well — measured on the flip: the two seals are not equal. **This is a format
  fact and not a test defect.** An `audit` view derived from an `executable` document cannot
  carry the executable document's seal, because it is not that document; §13.1's fourth limit
  says what a holder deriving one does about the member. *Owed:* the sentence in §13.1 (it is
  there now), and `document_digest` deleted beside `created_at` and `profile` in the test, as
  one more member by which two records of one calculation honestly differ.
- **`test_validate.py`** —
  `test_the_deep_reading_adds_to_the_shallow_one_rather_than_replacing_it`
  asserts that a clean `audit` artifact's deep reading adds exactly two warnings, the second
  being that the document carries no seal. Sealed, that warning is gone. *Owed:* the count
  goes back to one, and the docstring back to one thing an `audit` artifact cannot check
  about itself — its leaves, whose canonical bytes are the trees the profile does not carry.
- **`test_validate.py`** —
  `test_a_payload_left_out_is_a_claim_about_data_held_somewhere_else`
  exports an artifact, replaces an inlined payload with `{"omitted": "size", "bytes": 4096}`,
  and validates deep expecting `ok`. **This one is a class, not a case:** any test that
  exports, edits and then validates fails once the export is sealed, because the edit is
  precisely what the seal is for. *Owed:* each such test builds its document with `seal=False`
  or re-seals after its edit, chosen by what the test is about; outside the tests the same
  three moves are §13.1's fourth limit, and a holder legitimately transforming a sealed
  document follows the rule stated there.

**A seventh test reddens, and not at the flip — at the regeneration.** Do the whole of unit
7's corpus step, the flip and then
`uv run python -m tests.graph.test_conformance_corpus`, and
`test_validate.py::test_the_published_corpus_survives_the_deep_reading` fails. That test is
one predicate — `validate_artifact(_load("conformance_corpus.json"), deep=True).ok` — and the
document that command would write does not satisfy it. **The corpus harness is a transforming
holder, and unit 7 as drafted publishes a corpus its own validator refuses.**

**The mechanism, verified after the tutorials' change and not reasoned to.** `_export_the_corpus_model()` in
`tests/graph/test_conformance_corpus.py` calls `GraphExporter(...).export()` and **then**
rewrites every node's `source_location` to a repository-relative path. The seal is taken
inside `export()` and covers every byte; §12.1 keeps `source_location` out of the canonical
bytes, so no fingerprint moves — but the seal is not a fingerprint. The same predicate, taken
on the document that command would have written, with `seal=True` and nothing written to
disk:

```text
seal as exported                 : sha256:36e04600aebd29d2…    deep ok: True
source_location before           : /…/bindings/python/tests/graph/test_conformance_corpus.py:82
source_location after            : bindings/python/tests/graph/test_conformance_corpus.py:82
recomputed after the rewrite     : sha256:77d3fc48f8054c4e…    agrees with the stated seal: False
node digests moved by the rewrite: none          graph_fingerprint moved: False
deep ok after the rewrite        : False → "This is not the file the producer wrote."
```

The harness's own docstring sentence — *"Section 12.1 keeps the source location out of the
canonical bytes, so rewriting it moves no digest"* — is true of every digest §12 mints and
false of the seal. And the rewrite is not incidental: §12.5 asserts the repository-relative
path as a property of the published corpus (*"`source_location` names a path inside the
producer's own repository rather than a path on the machine that ran the model"*). So this
format's own publishing pipeline meets §13.1's fourth limit as a transforming holder and takes
the one move that section refuses — leaving the old seal on a record it no longer describes.

**The corpus test named above cannot catch it.**
`test_the_corpus_is_still_the_artifact_this_producer_writes` is the corpus test in the list,
and its *Owed:* edit deletes `document_digest` from both sides — correctly, since two exports'
seals differ over `created_at` — which is exactly the member whose staleness is the defect.
The test that catches it is the one nothing here named.

**Three ways out, and settling the choice is what this document is for.**

- **(a) Re-seal after the rewrite.** It works, and it collides with §13.1's own new rule: the
  seal would then say the corpus is the file *this harness* wrote, so §7's `producer` —
  *"What wrote the file"* — should name the harness, while the corpus's `producer` block names
  `GraphExporter`.
- **(b) Publish the corpus unsealed** (`seal=False` in the harness). It works, and unit 7
  adds `document_digest` to the schema's `required` list in the same commit, so the format's
  flagship artifact would be the one document that does not validate under the identifier it
  exists to demonstrate.
- **(c) Move the repository-relative rewrite into the producer** — a source-root option on
  `export()`, applied before the seal is taken. **This is the recommendation.** Nothing
  post-export then exists to break, and the published corpus is the file its producer wrote,
  which is the seal's whole sentence. **Its cost, named rather than glossed:** a producer
  option added at unit 7, in `frame/graph/artifact.py` rather than in a test module — a public
  surface widened by the commit whose job is to move an identifier, and the only one of the
  three that touches shipped code. Whether widening it there beats (a)'s `producer` wrinkle is
  a judgement about the format's own surface, and the final word belongs to the maintainer's
  read rather than to this list.

**And a naming point about §5's "no digest moves".** That phrase is about node digests and
`graph_fingerprint`, and it stays true. The seal is a digest of a different kind — it moves
whenever *any* byte of the document moves, which is what it is for — so the three hand-built
goldens acquire a seal that has no predecessor to be compared against, and the corpus's seal
moves at the regeneration along with everything else in its file. Neither is a counter-example
to the claim; they are what "the record moved and the calculation did not" looks like written
down.

---

## 5. Which goldens regenerate

Four files under `bindings/python/tests/graph/goldens/`:

| Golden | Regenerates | Why, and by what |
|---|---|---|
| `conformance_corpus.json` | **yes — and its digests move** | The corpus model grows (§3.1); the token moves. `uv run python -m tests.graph.test_conformance_corpus`, which is the one place regeneration lives. §12.5's printed table is reprinted from it. **The seal is the one thing that command does not get right on its own** — the harness seals inside `export()` and rewrites every `source_location` afterwards, so with the seal on the published file would carry a digest taken before the rewrite and its own deep reading would refuse it. §4.1's seventh-test bullet carries the measurement, the three ways out and the recommendation. |
| `annex_example_artifact.json` | **yes — no digest moves** | Hand-built. Node records take `provenance`, lose `value_kind`; edges take the new shape; the envelope takes `document_digest`. Its one `source: "assumptions"` node becomes `provenance: "assumptions"` — the only document in the tree carrying that value. Hand-edited, then re-validated — and the invariant this measurement surfaced is per node: `test_supervisory_annex.py:141` asserts `local_fingerprint != fingerprint` on every node of this file (§3.3). |
| `state_graph_example.json` | **yes — no digest moves** | Hand-built, same three edits. Seven nodes: five `model_points` inputs, one `assignment` computed, and `state_graph:disability_income_3state`, which takes `provenance: null` — the value the design's §1.3 constrains the `state_graph` kind to, and what the file already carries as `source: null, origin: null`. §17 says the schema accepting these two whole *"is the evidence, and it is what these sections cost"*, so both must still be accepted whole after the schema moves. |
| `nested_valuation_example.json` | **yes — no digest moves** | As above. Five nodes: three `model_points` inputs, one `assignment` computed, and `nested_valuation:present_value_of_guarantee` at `provenance: null`. |
| `level3_mini_va_golden.parquet` | **no** | A values golden for `test_reconciliation.py`, not an artifact. Nothing in this batch changes a number any model computes. |

**"No digest moves" on the three hand-built files is the decision §3.3 records**, not an
observation left hanging: their digests are written-in constants that nothing in the tree
re-derives, none of them is under §12.5's regeneration obligation, and a record-shape edit
reaches no byte any of those digests was taken over. They are edited to the new record shape
and re-validated; their digests are compared byte-identical before and after, exactly as the
corpus's are at R1 and R2.

**Two documents outside `goldens/` that must be checked and are expected not to move.**
`tests/test_content_identity_grammar.py:50` pins §12.3's worked-example content hash as
`WORKED_EXAMPLE_DIGEST = sha256:5267aed7…` (its byte string is `WORKED_EXAMPLE_BYTES` at
`:46`); the content grammar is untouched, and a movement there is a defect rather than an
expected regeneration. And the three shipped model exports are pinned by
nothing — no test asserts a tutorial's `graph_fingerprint` — so the flagship's digests move
freely and silently, which is why §1 counts them here instead.

**The acceptance condition for unit 7 is arithmetic, not assertion.** The corpus digests are
reprinted from the file the regeneration command wrote, `test_conformance_corpus.py`'s three
mutually-checking tests pass (the export, the file beside it, and §12.5's printed table all
agreeing), and the whole suite is green. A digest quoted anywhere in prose that the file does
not carry is a defect in the same class as the one this batch is fixing.

---

## 6. The public decision record

It ships **in the regeneration commit**, in the format's own change document, because that
is where §14.1 says a consumer reads a change instead of being carried across it by a shim
that was never written. Three parts.

### 6.1 One §14.1 line per passenger, drafted

Newest last, each against `v0-preview.2`.

> - `v0-preview.2` — **the node record's six axes collapse to three.** `source` and `origin`
>   merge into `provenance`, keeping both vocabularies whole: the recording doors — `join`,
>   `rename`, `batch`, `assignment`, `projection`, `date`, `rollforward`, `continuation` —
>   stand beside the arrival places `model_points`, `assumptions` and `injected`, and every
>   node has exactly one answer to where its definition came from. `value_kind` is removed:
>   it was a restatement of `dtype` on every record ever produced, and section 10 now states
>   the rule where a reader looking up the type vocabulary meets it — with the clause a
>   reader needs beside it, that a selection may also arrive as a numeric 0/1 mask the type
>   vocabulary cannot tell from a quantity, which is what every bare comparison in the
>   reference producer writes. `engines` and `tier` gain the consistency rules they always had
>   in practice — naming an engine says something in the tree reaches into one, which
>   contradicts `core` and contradicts a null tier and stops there; a positive engine-free
>   claim and an engine-native claim are contradictories; a node with nothing to execute names
>   no engines — with the `executable` profile requiring the list on a `core` or
>   `engine_native` node, because that is the profile whose file holds the operation tree the
>   list is a walk of and on those two tiers the walk is exhaustive over it, and requiring it
>   of an `opaque` node only where that walk reaches an engine, because an opaque node's
>   silence is a leaf nobody could classify and not a fact about engines. The `audit` profile
>   leaves the field optional throughout, exactly as section 8.3 intends. **A node whose tree reaches both an engine fragment and an identifier nothing has
>   classified is `opaque` and names its engine**, because section 11.2's ladder takes the
>   weakest tier in the tree: the rules narrow what a record may claim without making that
>   record unwritable, and an artifact valid under the old shape in that respect stays valid.
>   The old shape admitted 252 combinations of `kind`, `source` and `origin`; ten occurred.
>   The new shape admits thirteen `(kind, provenance)` pairs across the five kinds anything
>   emits, and fifteen across all seven: `state_graph` and `nested_valuation` are constrained
>   to null now rather than left open until a producer emits one, which is what both
>   hand-built examples already carry, and a later producer widens the constraint additively.
>   **A document written before this line is refused after it, and the reverse**, which is why
>   the identifier moves. No digest moved: none of the three fields was ever inside a node's
>   canonical bytes. Section 12.1's stated collision between an injected column's `origin`
>   attribute and the node record's `origin` field is closed by the rename rather than
>   restated.
>
> - `v0-preview.2` — **the edge carries the relationship; the narrowing travels beside it.**
>   An edge is `source`, `target` and `relationship` — `DIRECT` or `INDIRECT` — which is the
>   distinction section 9 exists for: what a reserve depends on and what selected the row are
>   different questions. `subtype` moves whole into the `gaspatchio_column_transformation`
>   facet on the reading node, carrying OpenLineage's own `transformations` array with its
>   own `type` and `subtype` keys and its own enum spellings, unaltered. The facet is
>   announced in `facets_used` and never in `facets_required`: a consumer that has never met
>   it reads the same graph and loses only a narrowing. Promotion back to the core edge stays
>   additive. No digest moved — an edge enters none.
>
> - `v0-preview.2` — **the `audit` profile states a compiled rollforward's working.** A
>   `rollforward` node carries `increments`: one entry per movement, in the order the machine
>   applies them, with the ordinal, the label the model's author gave it, the operation, the
>   running balance it lands on, and whether its amount depends on that balance. It is present
>   wherever it can be derived and absent otherwise, exactly as `states` is — a producer that
>   cannot reach the compiled artefact, or that meets an operation the vocabulary does not
>   name, or whose labels collide within the one array, omits the field rather than writing
>   something it cannot stand behind. **`operation` is a closed enum of ten names, listed in
>   section 16 by this line** — `Add`, `Subtract`, `Charge`, `Grow`, `GrowCapped`,
>   `DeductNAR`, `Ratchet`, `Floor`, `Round`, `Apply` — and publishing the framework's own
>   operation identifiers on the wire is a deliberate coupling: renaming one becomes a format
>   change with a line here, which is what a second name for one operation would cost anyway
>   and without a translation table free to drift. **No label may appear twice within one
>   `increments` array**, because the summary is what a reader cites and a matching hint is
>   what a change report falls back on; nothing is required of a compilation that produces no
>   summary, so no model that compiles today stops compiling. An operation with no label
>   carries null, which is the claim it is everywhere else in section 8.
>   `reads_running_balance` is a fact about the operation for seven of the ten — those whose
>   shape puts the balance in the amount however the operand is written — and for `Add`,
>   `Subtract` and `Apply`, whose expression *is* the amount, it is read off that expression,
>   which the compiler has already reduced to a single column reference and classified as
>   either a declared state at a declared point or an input column: it is **true where that
>   classification reads the same state the increment's `target` names, at either point**.
>   Where a producer cannot classify one it writes null rather than guessing, with the meaning
>   null carries throughout section 8. An
>   increment's identity is its position in its compilation — the compilation's `fingerprint`
>   and the increment's ordinal — and no per-increment digest is minted, for the reason
>   section 12.1 gives for not restating the machine inside the node's bytes. **The
>   non-promise is explicit: this is the movements and their order and nothing else.** The
>   amounts, the expressions, the rounding, the stopping conditions, the schedule and the
>   states' opening values are the machine, they travel in the `gaspatchio_rollforward_ir`
>   facet, and that facet is unstable and will change without a compatibility path while this
>   preview is open. No digest moved: the compiled fingerprint already covers every label and
>   the order, which is why this record can promise to be stable.
>
> - `v0-preview.2` — **`sum`, `mean`, `min` and `max` join the vocabulary**: the reduction of
>   one policy's per-period column to one number, which is what a present value is. Section
>   11.1.9 named this gap and said an operation whose answer has a different shape from its
>   operand had no way to state that; 11.1.12 states it, per entry, where the fact belongs,
>   and 11.1.13 to 11.1.15 do the same for the three siblings. One operand, no attributes, no
>   `reverse` — a fold over a whole axis reaches the same number either way. The fold is along
>   the periods and along nothing else: an engine method of the same name applied to a
>   per-policy column folds down the rows of the model-point file, a different calculation
>   whose answer depends on the order those rows stand in, and a producer must not write this
>   identifier for it. **Digests move wherever a producer's record of such a line genuinely
>   changes** — an engine fragment becomes a `call` — and through every node downstream of one.
>   `fingerprint_algorithm` did not move for this: a `call` has been hashable under section
>   12.1 since it was written. Only `sum` moves a digest in any shipped model: the three
>   siblings occur zero times in the package, the tutorials and the tests, and they ride now
>   so that a later addition does not move the same digests a second time. Section 11's count
>   of the operations in the unnamed domain moves from fourteen to eighteen. The reductions that
>   did not ride are named and so is what each waits for: `std` waits on a `ddof` the vocabulary
>   never stated, which an identifier carrying a default would hide inside a name, and `median`
>   on a convention for an even period count, which is a question no denominator of its own
>   asks; `first` and `last` are `projection.at_period` at a boundary and a second spelling is
>   what 11.1.11's rules exist to prevent; `len` is a length and not a fold of values.
>
> - `v0-preview.2` — **a date is a scalar in the tree grammar, and the refusal is withdrawn
>   for a literal on its own.** Tag `0x16`, a zigzag varint of days since 1970-01-01 on the
>   proleptic Gregorian calendar — the same number and the same layout the content grammar of
>   section 12.3 has always written behind that byte, so a reader holding both grammars still
>   meets one encoding per type. Section 12.1 and section 12.3 disagreed about whether sharing
>   that block made a tag mean two things or one; this line settles it in section 12.3's
>   favour, which is the section that made the block shared. On
>   the wire a date literal is `{"op": "lit", "date": "..."}` under its own key, and exactly one
>   of `value`, `values` and `date` is present: JSON has a number token and no date token, so
>   the distinction that whole numbers and decimals draw with a token is drawn here with a key.
>   **The withdrawal is for a literal and not for a member of one.** `values` still holds
>   flags, whole numbers, decimals and text, and a date under it is refused: a date written
>   there is text, encodes as `0x14` and its eleven bytes, and reaches a well-formed digest
>   matching nothing — the failure this section warns about for a scalar, one level down. So a
>   membership test against a set of dates stays an engine fragment and the node says so, as
>   every calculation this document cannot yet spell does. `0x17` is likewise not minted for
>   the tree — nothing writes a datetime literal, and an untested token in a grammar whose
>   value is agreement is worse than a stated absence. Both forms land additively, with a line
>   here, the day a producer holds one.
>   **`fingerprint_algorithm` moves to `gspv0-preview-2`, and it is this line that moves it.**
>   Every digest in every artifact written under `gspv0-preview-1` is a digest under a different
>   grammar; section 12.2's rule applies without exception, and two artifacts carrying different
>   tokens must not be compared. The corpus of section 12.5 is regenerated and reprinted, and it
>   grows a date column and a date literal so that the new tag is exercised by the artifact whose
>   whole job is to let a second implementation prove agreement.
>
> - `v0-preview.2` — **the seven operation-tree branches close.** Each carries
>   `unevaluatedProperties: false`, so a node claiming to be one kind and carrying another
>   kind's fields is refused rather than validated and then hashed as the kind it claims. The
>   case this closes was live: a `call` relabelled `state`, keeping its arguments and its
>   configuration, validated clean and hashed as a state reference — a document with one node's
>   whole configuration struck out, carrying a digest that no longer covered what it dropped.
>   **The envelope's stated openness is untouched**: the top level and the node record still
>   admit keys this document does not define, and section 6's round-trip promise for an unknown
>   facet rests on that and is unchanged. No conforming document was refused by the closure: it
>   was checked against every operation tree in every artifact the reference implementation
>   produces. No digest moved.
>
> - `v0-preview.2` — **`document_digest` becomes required on emission.** The member itself was
>   defined under `v0-preview.1`, where section 7 states it, section 13.1 states the byte stream
>   it is taken over and the limits, and section 14.1 carries its line; what changes here is that
>   a document written without one stops validating. **That is a break in validity and this line
>   is where a consumer is told of it** — which is what this log is for under section 1's preview
>   policy, rather than a claim that required-ness by itself moved the counter: the
>   `reads_assumptions` line above added a required field inside `v0-preview.1` with the counter
>   unmoved, and section 14 says what a reader does about two documents on either side of such a
>   line. The identifier moves at this release for the byte grammar of section 12.1 and for the
>   shape changes landing beside it, and this member becomes required in the same document.
>   It seals a written record rather than an identity — the digest field excluded,
>   `created_at` included — which is the question section 8.2's bound left open and the
>   fingerprint chain deliberately does not answer. Deep validation recomputes it and
>   names the mismatch. Every citation of one document by another carries the cited document's
>   digest beside its identity, which is what makes an edit-and-reseal detectable at all. The
>   limits are stated in section 13.1: this is tamper-evidence and not tamper-proofing, a
>   determined re-sealer beats the standalone file and is caught only by the citation web, and
>   producer signing is future work and is not built. No node digest moved.

### 6.2 One §12.2 paragraph, and it is the loud one

> **`gspv0-preview-2`.** The token moved once, on the date-literal tag of section 12.1, and
> everything that landed beside it — the node record's collapse, the edge's relationship, the
> list reductions, the closed tree branches, the increments summary, the seal becoming
> required — landed
> in the same document so that the format's users read one change rather than several. Section
> 14.1 carries a line for each. Every digest published under `gspv0-preview-1` is a digest under
> a different grammar and must not be compared with one published under this token; the change
> report refuses the comparison rather than reporting on it, and a consumer that wants an answer
> re-derives the fingerprints from the model source under one grammar.

### 6.3 Where else it has to be said

- **`CHANGELOG.md`** — one entry naming the token move, the schema identifier move and the
  retired corpus digest, in the release the regeneration ships in.
- **`spec/graph-artifact/README.md`** — the identifier it points at.
- **The `schema` identifier table** the package carries, which §5 says is how an identifier is
  resolved: `v0-preview.2` is added and `v0-preview.1` stays, so a tool meeting an old document
  says which grammar it is under rather than failing to place it.

**And there is deliberately no fourth item, which is a consequence of a decision and not an
omission.** A fourth would be needed if this batch changed the modelling API — a model that
compiles today refusing to compile tomorrow is a break a user would look for in
`CHANGELOG.md` and never find in §14.1, because §14.1 is the *format's* log. The increments
work would have done exactly that had it extended the compiler's label-uniqueness rule past
`track_increments=True`. It does not: uniqueness is required of the `increments` array and
checked by the validator, the compiler is untouched (`rollforward/_passes.py:47-65` and its
guard at `:110-111` keep the scope they have), and no model's compilation behaviour changes
anywhere in the batch. Every change here is a format change and §14.1 is where a reader
meets all of them.

---

## 7. What is deliberately not in this batch

- **`projection_set`'s `valuation_date` stays text.** V4 makes a date encodable; it does not
  retype an attribute whose signature already says what it is. Retyping it would move every
  projection's digest in every model to say something §11.1.11 already says.
- **The content grammar is untouched.** `0x16` and `0x17` have been there since §12.3 was
  stated; V4 borrows the number and the layout and changes nothing in §12.3.
- **A date inside a sequence literal.** V4 makes a date a literal's whole payload and not a
  member of a band; `values` keeps its three types and a date under it stays refused, in the
  IR and on the wire alike. A membership test against a set of dates therefore remains an
  engine fragment — measured, `col("entry_date").is_in([...])` with `tier: "engine_native"` —
  and the design says so rather than leaving the boundary to be found. Spelling a sequence of
  dates is a second key or a per-member tag, and choosing between them without a producer to
  check either against is the guessing this batch exists to remove.
- **The compiler's label-uniqueness rule.** The `increments` array requires unique labels and
  the validator checks it; `track_increments=False` compilations are untouched, so no model
  that compiles today stops compiling. Extending the compiler's own rule is a modelling-API
  change and belongs to whoever wants it, with its own reasons.
- **`first`, `last`, `len`, `std`, `median`** — `sum`, `mean`, `min` and `max` ride; these
  five wait. The boundary is in the design document with the reason the four ride and the two
  reasons the others wait: `first` and `last` are `projection.at_period` at a boundary, `len`
  is the projection's own period count, `std` waits on a `ddof` the vocabulary never stated
  and `median` on a convention for an even period count. It is a position rather than an
  omission.
- **`state_graph` and `nested_valuation` remain unemitted.** V24 exercises §16's payload
  against a live compilation, which is the first of §14's three preview-closing payload
  conditions; the other two stay where §17 leaves them.
- **Producer signing.** Named in §13.1 as future work by document-seal's own design, and not
  built.
