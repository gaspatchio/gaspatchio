# The gaspatchio-graph calculation-graph artifact

**Identifier:** `gaspatchio-graph/v0-preview.3`

**Prose licence:** Creative Commons Attribution 4.0 International — see
[`LICENSE-CC-BY-4.0`](LICENSE-CC-BY-4.0).

This is the normative document for the artifact. Its section numbering is fixed and is
never renumbered; a section that is not yet written keeps its number reserved.

| § | Section |
|---|---------|
| 1 | Scope and status |
| 2 | Licence and IPR |
| 3 | Conformance profiles |
| 4 | Non-adoptions |
| 5 | Identifier dispatch |
| 6 | Facets |
| 7 | Envelope |
| 8 | Node record |
| 9 | Edges |
| 10 | Type vocabulary |
| 11 | Operation identifiers |
| 12 | Identity and fingerprints |
| 13 | Verification |
| 14 | Versioning and change log |
| 15 | Assumptions |
| 16 | Rollforward |
| 17 | Reserved payload sections |
| Annex A | Solvency II |

---

## 1. Scope and status

A gaspatchio-graph artifact is a record of how every column of an actuarial model was
computed. For each column it carries the columns that column was derived from, the
operation that derived it, and the identity of the assumption data the operation read. The
record is engine-free: it is a document, and a consumer that can read JSON can read it
without the software that produced it being installed, licensed, or still in existence.
Every element of the record carries a content-addressed identity — a fingerprint over
canonical bytes — so that two artifacts can be compared and a claim that nothing changed
can be checked rather than believed.

It is not a model file. The model is Python and stays Python; an artifact is derived from a
model that has been built, and it is never a substitute for writing one. It is not a results
format: it carries no book of per-policy values, no cashflow matrices, and no aggregates over
the book, for the reasons set out in section 4 — only the values of the few policies and folds a
reader asked to see beside the calculation, which sections 7.4 and 8 define as enrichment and
bound by bytes. And it is not an execution protocol: nothing in this document
tells a consumer how, in what order, or on what hardware to evaluate anything. A consumer
that only reads is a conforming consumer.

This document specifies `gaspatchio-graph/v0-preview.3`. It is a preview. The change policy
for a preview is documentation rather than compatibility work: a change to the format is
written down in the change log against the version it landed in, and a consumer is expected
to read that log rather than be carried across the change by a compatibility shim. The
conditions under which the preview closes, and the format becomes one a consumer may hold
still, are stated in section 14.

## 2. Licence and IPR

The prose of this specification is licensed under Creative Commons Attribution 4.0
International (`LICENSE-CC-BY-4.0`).

The schema files this specification refers to are licensed under Apache License 2.0, the
same licence as the reference implementation, and each carries an SPDX licence identifier in
a `$comment` member, with the repository's licence metadata saying the same.

The conformance corpus (section 12.5) is licensed under Apache License 2.0, on the same
footing as the schema files. It is itself a conforming artifact, and this specification is
what defines an artifact's members, so the corpus states its licence in the repository's
licence metadata alone rather than carrying a member that says nothing about the model it
is an account of. It is published in order to be copied: an implementation proving its
agreement against those digests needs the file, not permission to hold it.

Opio Inc. grants a royalty-free, worldwide, non-exclusive licence under any patent claims it
owns that are necessarily infringed by implementing this specification, to any party
implementing it. No implementation fee, licence fee, or registration is required to produce
or consume a conforming artifact.

The licence to a party terminates on the date that party asserts a patent claim against this
specification or any conforming implementation of it.

## 3. Conformance profiles

This specification defines two conformance profiles, `audit` and `executable`. The
envelope's `profile` field says which one an artifact claims.

`audit` requires the envelope, the node record, the edges, and the identity fields. It is
what a reviewer or a supervisor reads: what each column is, what it was derived from, what
assumption data it read, and what the identity of each of those things is. It is also the
profile a third party exporting from its own modelling stack can emit cheaply, because
nothing in it requires reproducing an operation tree but one: a step that chose which rows the
model values carries its predicate's tree in both profiles (section 7.6), because a step
defines no column and the tree is the whole account of it.

`executable` is `audit` plus the per-node operation tree and the compiled-rollforward
payload — everything a consumer would need to evaluate the model rather than only read it.
Each node with an operation tree carries it under `expr` (section 8); a compiled
rollforward's own state machine rides in the envelope's facets (section 16). Hashing a tree
read back out of an `executable` artifact under section 12.1's byte grammar reaches the
`local_fingerprint` the same node already carries, which is what makes such an artifact
self-authenticating rather than merely readable.

**The `executable` profile is unstable in this preview.** The operation trees are what another
engine runs the model from, and they are not yet a stable interface. The JAX engine runs the
operations its coverage table lists and refuses the rest by name, and no engine yet covers
every operation the format names. Its shape will change, without a compatibility path, while
the preview is open, and a consumer that depends on it today accepts that. It is marked unstable in the schema as well
as here, on the definition itself, so that the warning reaches a consumer holding only the
schema. A consumer must not persist it as a long-lived interchange format.

An `executable` artifact is also a conforming `audit` artifact. A consumer that reads only
the `audit` fields reads an `executable` artifact correctly, and may ignore everything the
`executable` profile adds.

## 4. Non-adoptions

This section records what this specification deliberately does not do. A non-adoption is a
decision, not an omission: it says the thing was considered and left out, and it says so
where a reader looking for the thing will find it.

**It does not carry per-policy value matrices or any bulk result data.** No projected
cashflows of the book, no reserves of the book, no policy-level output of the book, and no
aggregate computed from it. The artifact describes the calculation; results live in the Parquet
the model wrote. Carrying results would make the artifact grow with the size of the run rather
than with the size of the model, and would make an artifact that is safe to circulate into one
that carries policyholder data. **The one exception is enrichment**: the values of the policies
and folds a reader asked to see, each a walk-through of the calculation for that policy rather
than a result anyone files (sections 7.4 and 8). It grows with the policies asked for — one,
where nobody asked for more, in the reference producer — and not with the book, a guard over
the finished document bounds it, and a document carrying it carries those policies' values —
which is why §7.4's `why` says which rows they are. A run that folds those results into
reported numbers — a scenario run, an aggregation over a policy book — writes its own record
beside its output (section 13.2),
and that record carries the real numbers this one never will, together with the name of
the graph it folded — one name per scenario, where a run shocks the assumptions its model
reads, because those shocks reach section 12.4's digest and each scenario is therefore its
own calculation — and a content stamp of the data it read. The two are one chain read
from either end: from a reported total, through the fold that produced it, to the
calculation that fold ran and the formula behind it; or from an edited formula forward to
every figure that moved. They stay two documents, linked rather than merged, because one
grows with the model and the other with the run.

**The base record does not carry engine plan text, layout hints, or a live engine
expression in any form.** No serialised query plan, no chunking or partitioning advice, no
column ordering intended as a rendering instruction, and no expression object of any engine,
in any encoding, including a byte string a consumer could deserialise back into one. An
artifact whose meaning depended on an engine expression would be readable only by that
engine at that version, which is exactly the dependency this format exists to remove. A
facet (section 6) may carry an engine's *rendering* of a formula as text, for a reader who
wants to see what the engine was asked to do; it is opt-in, it is never the meaning of a
defined field, and it is never an object a consumer could evaluate. The as-written `formula`
on the node is the calculation; the rendering is a convenience.

**It does not define governance metadata.** A validation stamp, a sign-off function, a risk
tier, a management overlay, a vendor assurance record, and a table datasheet are each a
future facet, not a v0 field. They are real things a governance process needs, and putting
them in the base record now would freeze one organisation's governance vocabulary into the
format for everyone. Section 6 says how a facet is added when one of them is settled.

This document defines a value domain, null behavior, non-finite behavior or
refusal only where an operation's semantics expressly state it. Those
operation-specific rules are normative for the forms they name. A form for
which no such rule is stated remains engine-defined and cannot support a
claim of portable execution conformance. Section 10 defines the type
vocabulary; it does not provide a default that overrides an operation's
explicit domain.

Further non-adoptions are recorded here as they are settled; the section grows and never
shrinks.

## 5. Identifier dispatch

An artifact's `schema` field carries a string identifier, such as
`"gaspatchio-graph/v0-preview.3"`. A consumer resolves that identifier to a schema document
**through a table of known identifiers**. It must not parse the string to derive a version,
a name, or an ordering, and it must not fetch the string as a URL — the identifier is a key,
not a locator, and it is not required to resolve over a network at all.

An implementation must keep an identifier in its table for as long as artifacts bearing that
identifier exist. Removing a row is what breaks a stored artifact; adding one never does.

This rule is what lets the specification move to a different home — a different repository, a
different organisation, a standards body — without invalidating a single artifact already
written to disk. The identifier is stable because it means nothing except "look me up"; the
place the lookup lands can change freely.

The table's rows so far:

| Identifier | Schema document |
|---|---|
| `gaspatchio-graph/v0-preview.1` | `gaspatchio-graph-v0.schema.json` |
| `gaspatchio-graph/v0-preview.2` | `gaspatchio-graph-v0.schema.json` |
| `gaspatchio-graph/v0-preview.3` | `gaspatchio-graph-v0.schema.json` |

**Every row names one document, and while the preview is open that document describes the
latest identifier only.** It pins `schema` and `fingerprint_algorithm` by `const` — section
12.2 says why, and says the pin relaxes to a pattern at `/v0` final — so a `v0-preview.1`
or `v0-preview.2` document resolved through this table reaches a schema that refuses it. The
row is still required and is still worth having: what it buys is **placement rather than
validity**, so a reader meeting an older document is told it is an earlier edition of this
format rather than that its identifier cannot be placed at all. Removing the row is what
would break the stored artifact; keeping it is what lets a consumer say which grammar the
document is under, which is the one thing section 12.2 leaves them able to do about it.

## 6. Facets

A facet is a named, independently versioned, optional block of extra information: a place to
carry something this specification does not define, without changing anything it does. Facets
appear in exactly two places — the envelope's `facets` object, and a node's `facets` object —
and nowhere else.

Every facet object carries two members. `_producer` is a URI identifying who produced the
facet; `_schemaURL` is a URI identifying the facet's own schema. Both are opaque identifiers,
and **a validator must not fetch either.**

The grammar — a named object carrying `_producer` and `_schemaURL`, ignored by a consumer that
does not know it — is the one OpenLineage uses for the same purpose, and it is borrowed rather
than invented. An extension convention with existing tooling and existing readers behind it is
worth more to a second implementer than one designed for this format alone.

Facet names produced by this specification's reference implementation begin `gaspatchio_`. A
third party defining a facet uses its own prefix. A name with no prefix is reserved.

The envelope carries two lists of facet names. `facets_used` names every facet present anywhere
in the artifact — in the envelope and on every node — so a consumer can see what it is about to
meet without walking the whole document first. `facets_required` names the subset a consumer
**must** understand for the artifact to mean what it says.

The two lists are what make the mechanism safe in both directions. A consumer that meets a name
in `facets_required` it does not know **must refuse the artifact**: the producer has said the
artifact does not mean what it appears to mean without that facet, and reading it anyway would
be reading a document the producer did not write. A consumer that meets a facet it does not
know and which is not in `facets_required` **must ignore it, and must preserve it unchanged on
any round-trip** — a facet that passes through a tool which does not understand it is still
there, and still itself, when it comes out.

A facet never changes the meaning of a field defined in this specification. A facet that would
has to be listed in `facets_required`. That is the same rule from the other side: anything a
consumer has to know about in order to read the base record correctly is required, and anything
required is announced.

A worked example:

```json
"facets": {
  "gaspatchio_lowered": {
    "_producer": "https://gaspatchio.dev/spec/graph-artifact/v0-preview.3",
    "_schemaURL": "https://gaspatchio.dev/schemas/facets/gaspatchio_lowered-v0-preview.1.json",
    "engine": "polars",
    "text": "[(col(\"sum_assured\")) * (col(\"death_rate\"))]"
  }
}
```

The URLs in that example are identifiers first. A `_schemaURL` is not required to resolve over
the network for an artifact to be valid, and neither is a `_producer`; a consumer that cannot
reach either has lost nothing it needed in order to read the artifact. The reasoning is the one
section 5 gives for the `schema` identifier, applied to a facet: a document whose validity
depends on a host still answering is a document with an expiry date on it.

### 6.1 Absence has a reason

Where a value this specification defines is absent because the producer chose not to carry it,
the producer states why in place of the value, as an object of the form
`{"omitted": "<reason>", …}`. Three reasons are defined in this preview. **`size`** is a value
the producer holds, weighed, and chose not to carry; it carries `bytes` — the size of the
value the producer declined to inline, measured in the serialisation the enclosing document is
written in, so that a reader can tell what it would cost to obtain the value elsewhere as a
file rather than in the tightest encoding a writer could manage. **`unavailable`** is a value
the producer named the identity of and cannot now vouch for; it carries no `bytes`, because
there was nothing in front of the producer to measure and a nought there would be a
measurement nobody made. **`withheld`** is a value the producer held and was asked not to
disclose; it carries no `bytes` either, because its weight is not what decided it.

**The three are three sentences, not one sentence with three spellings.** `size` says
*fetching this will cost you that much*. `unavailable` says *my own account of this value is
short*. `withheld` says *my account is complete and I am not giving it to you* — a decision
somebody took, which the file records. The alternatives are worse in both directions: a
silence leaves a reader unable to tell a decision from an oversight, and borrowing `size`
would state a reason that is false and a weight nobody measured.

**In this preview the form is accepted where the schema says so, and that is five positions:
an assumption entry's `payload` (section 15), a source entry's `payload` (section 7.3), the
book's `digest` (section 7.5), which admits `unavailable` alone, the producer's `versions`
(section 7), which admits `withheld` alone, and the model block's `git` (section 7), which
admits `unavailable` alone.** At `git` the form carries `detail`: git's own first line where it
ran and refused, or what happened where it did not run or did not finish, so a reader can tell
"git could not be read" from "not under revision control", which is `git: null` and nothing
else. At the book's digest the form
may also carry `detail`: one sentence saying what the producer met — that no book was handed to
it, the opening sentence of the refusal the content grammar or the reader gave, or that the
digest was left to the engine the document was built to be handed to — so that a comparison
which cannot read the book (section 14.2) says why rather than only that it could not. A field this document types
as a string does not also admit an `omitted` object, and a producer that put one there would be
emitting an artifact the schema rejects. Further positions are added additively, each with its
own line in the change log (section 14), so a consumer that meets one has a document to read
rather than a surprise to absorb. At an assumption table's payload, a `size` stand-in may also
carry `roles` (section 15): the columns the omitted frame was keyed by and answered with, so a
reader holding the table's file can still check it against the fingerprint.

**An absent field and a field present with an `omitted` object are different claims**, and
neither is the same as a field present with a null. A field carrying an `omitted` object says
a value exists and was left out, and says why. A null says the value is null. An absent field
says neither of those things. A consumer that collapses the three into one loses the
distinction the form exists to keep: "there was nothing here" and "there was something here
and I chose not to carry it" are different statements about the model, and only one of them
is a reason to go and look somewhere else. The two reasons split that second statement again
— "and here is what fetching it would cost you" against "and I cannot vouch for it from
here" — and only the first is a cost a reader can budget against, while only the second says
the producer's own account of the value is short.

### 6.2 Anchoring

An operation identifier outside the core domain (section 11) and a node whose tier is
`engine_native` **may** each carry `anchors_to`, naming the core operation whose meaning is
closest and at least as wide. At least as wide is the direction that matters: the anchor may
cover more than the operation it anchors, never less, so a reader who knows only the core
domain is never told something narrower than the truth.

A producer that cannot anchor omits the field rather than guessing. An absent `anchors_to` says
the producer had no core operation it was willing to stand behind. A wrong one would say
something false about the model, and say it quietly.

The reference implementation emits `anchors_to` nowhere in this preview. The field exists so
that an exporter for another vendor's models can be honest about what it mapped: it carries
both the operation the model actually used and the core operation it was mapped onto, rather
than only the mapping, and a reader can see where the translation was approximate.

## 7. The envelope

The envelope is the artifact's top-level object. Every field below is required in the `audit`
profile, and an `executable` artifact is a conforming `audit` artifact (section 3), so every
field is required in both. Required means present: several of these fields may be empty, and an
empty one is a claim the producer is making rather than a value it failed to supply.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `schema` | string | yes | The identifier §5's table resolves. |
| `profile` | `"audit"` \| `"executable"` | yes | Which profile this artifact claims. |
| `fingerprint_algorithm` | string | yes | The opaque token naming the byte grammar (§12). |
| `producer` | object `{name, version}`, and optional `versions` | yes | What wrote the file, and what produced the values in it. `versions`, where present, is the mapping a results file's result manifest states, spelled as it spells it, so a document and a results file of one run can be held against each other key for key: `core_version` and `extension_version` — the core package as installed and the version compiled into the extension that process loaded, one number in a release wheel and not necessarily in any other install — `extension_sha256`, that extension's digest or a sentence beginning `unavailable:` where the file on disk was no longer the one loaded, `polars_version`, `python_version` and `platform`. A run on a second engine states what that engine's own manifest says produced it, which may name keys of its own. Beside them `imports` names each installed distribution the model imports — read off the import statements of the model and of every local module `modules` lists — as `{name: version}` under the distribution's own name, ordered by name: the standard library and the producer itself are never listed, and the member is absent where the model block names no model source. **A distribution is identified by its version, as Polars is; no hash is taken.** `versions` is outside every fingerprint and every canonical byte the identity fields are taken over — a model with one `graph_fingerprint` on a new library is one model, and this says which library ran it — and it is inside `document_digest`, as every member is. A producer asked for a reproducible document, such as one committed as a golden, writes §6.1's `withheld` form in its place; that is never the default. Optional, and absent on documents written before the member. |
| `created_at` | RFC 3339 UTC timestamp | yes | When it was written, in UTC: RFC 3339 with the `Z` designator and no numeric offset. |
| `model` | object | yes | The version block: `label`, `source_path`, `source_sha`, `git`, `model_points`, each required and each of which may be null, and `results`, `audit` and `modules`, which are optional. `git` is `{commit, dirty}`; **null where git ran beside the model and found no working tree, which is the one thing null means there**; or §6.1's `unavailable` form, with `detail`, where git could not answer — no git executable, git refusing the directory, a repository with no commit yet, no answer in time. Every absolute path git names in that `detail`, quoted or bare, is written relative to the model's directory, as every other path is — or, where it shares no directory with the model's but the filesystem's root, or sits on another drive, as `<a path outside the model's directory>`, since a climb to the root and back names the machine as surely as the absolute path would. `modules` names every local module the model imports — each file beside the model file, or in a package beside it, that its import statements resolve to, and those files' own in turn — as `{path, fingerprint}`, ordered by `path`, the fingerprint SHA-256 over the file's bytes as `source_sha` is and null only for a file the producer could not read. A name is resolved against the model's own directory, as running the model resolves it, so an installed package and the standard library are never listed; the list is read off the source's import statements rather than off what a process happened to import, so a model exported from a script and from the command line states one list. **A helper the model loads by its path rather than by an import statement** — through `importlib.util.spec_from_file_location`, an `import_module` of a computed name, `runpy`, `exec` or their kin — is on no import statement, so it is on no list and the record does not name it: a verifier holding such a model reports its modules as a check that could not be made, never as agreement (§13), and a model that means its helpers to be held imports them by name. It is empty where the model imports nothing from beside itself, and **absent where the block names no model source**, and on documents written before the member. A helper is as much the model as the file is — an edited accessor moves every figure it computes and no byte of the model file — and §13 states the check. `results` names the output file the run wrote and `audit` the record the run wrote of itself, each `{path, fingerprint}` on exactly the shape `model_points` carries, and each **present only where the run wrote that file** — absent otherwise, not null. A run that keeps a second record of itself — a scenario sweep writes one, naming the plan it ran, the scenarios in it and what each of them folded (§13.2) — names that file here, so the two records of one run are checkable against each other by content rather than adjacent by filename. `scenarios` names the run script of a scenario plan the export ran, `{path, fingerprint}` on the same shape and the fingerprint SHA-256 over the file's bytes, **present only where the run was a scenario plan**: the plan is as much the run as the model is — a shock factor edited in it moves every scenario it shocks and no byte of the model — and a verifier holding it rebuilds the document's graph through it (§13). **Every path in the artifact — `source_path`, `model_points.path`, `results.path`, `audit.path`, `scenarios.path`, each `modules` path, each assumption entry's `source_file` (§15) and every `source_location` — is written relative to the model's root: the directory the model file sits in, or the root of the repository it sits in where `git` is present.** The root itself is not carried, and does not need to be: a reader holding the artifact holds the model file, and `git` says which of the two bases applied. A path outside the root is written with `..` segments, forward-slashed, where the file and the root share a directory below the filesystem's root — a helper in a sibling directory of the checkout is `../shared/helpers.py`. **Where they share only the filesystem's root, or the file is on another drive, the path is the file's name under `<outside the model's root>`** — `<outside the model's root>/inforce_2026Q3.parquet` — because a climb to the root and back down is an absolute path spelled relatively and names the machine as surely as the absolute path would; the name says which file the run read, and a reader resolves neither form. A `source_location` in a file under the producer's temporary directory, where the root is not, is written by the file's name in angle brackets, `<cell.py>:7`: a notebook kernel keeps each cell in such a file, and a climb to it is an absolute path spelled relatively, which names the machine and resolves for nobody. **No absolute path appears anywhere in the artifact** — one names a directory on the exporting machine, resolves nowhere else, and would differ between two runs of one model that never moved. |
| `graph_fingerprint` | `"sha256:<64 hex>"` | yes | One string standing for the whole model (§12). |
| `formulas_fingerprint` | `"sha256:<64 hex>"` | no | One string standing for the model's formulas with its data left out (§12.6): the fold of `graph_fingerprint` taken again over trees in which every attribute naming a table's, a curve's, a schedule's or a handed-over column's content is masked. A re-sourced basis moves `graph_fingerprint` and leaves this where it was; an edited formula moves both. Outside every canonical byte and inside `document_digest`. **Optional**, and absent on documents written before the member; a producer conforming to this edition writes it. |
| `book` | object `{columns, digest}` | yes | The policy data the model was built over, by content: the input columns the model reads, in name order, and their digest under §12.3's grammar — or §6.1's `unavailable` form where the producer could not vouch for its book. §7.5. |
| `facets_used` | array of string | yes | May be empty. |
| `facets_required` | array of string | yes | May be empty. |
| `nodes` | array of node (§8) | yes | |
| `edges` | array of edge (§9) | yes | |
| `assumptions` | array (§15) | yes | May be empty. |
| `holes` | array | yes | **May be empty, and the empty array is the claim worth making.** |
| `boundaries` | array | yes | May be empty. |
| `sources` | array (§7.3) | no | The model's own text, one entry per file any node's `source_location` names. **Optional, and the one optional array in this table**: it was added at `v0-preview.2` and every artifact written before that line carries none, so requiring it would have made a document that was valid invalid. A producer conforming to this edition writes it, and writes it empty where no node has a location at all. |
| `enrichment` | object or null | yes | The **first** evaluation context values in this artifact are interpreted under, or null when the artifact carries no values. Four members, each required and each of which may be null: `policy_id`, the policy the values were read from, or null where the producer could not identify one; `aggregation`, the fold this entry is an account of — named as the framework that performed it spells the aggregator — and null where the values are one policy's rather than a fold of several; `periods`, the array of projection periods the values were taken at, **null meaning every period was taken**; and `filter`, the cut the sampled rows had been narrowed by, written as the producer received it, or null where they were read from the whole frame. **It is `policies[0]` with `why` left off** — the member this edition added and the one before it did not define — so it is the same context written twice and never a second one. |
| `policies` | array | yes | The axis the values are read along: one entry per policy the artifact carries values for, in the order the producer selected them, each carrying `enrichment`'s four members and a fifth, `why`. **Empty exactly where `enrichment` is null**, because an artifact carrying no values states no context to read them under. §7.4. |
| `facets` | object | yes | May be empty. |
| `selection` | array (§7.6) | no | Every step that chose which rows the model values — a filter, a semi join, an anti join — in the order the model took them. **Optional, and absent exactly where the model chose no rows**: a producer conforming to this edition writes it wherever at least one step was taken and never writes it empty, so a model that selects nothing keeps the digests it had. It enters both fingerprints (§12.4, §12.6), its reads are part of the book (§7.5), and a replay applies it before it projects. |

A consumer must accept an artifact carrying fields this specification does not define, and must
preserve them on a round-trip. It is the rule that governs an unknown facet, applied to the
envelope itself: an unknown field is not an error, and a tool that quietly drops one passes on
a document that is missing something it was given.

**One further member closes the envelope, and it is required.** `document_digest`, a
`"sha256:<64 hex>"` string, seals the document as a written record: a hash over the document's
own canonical serialization, that member excluded and `created_at` included. It answers a
question none of the identity fields above answers — *is this the file the producer wrote?* —
and §13.1 states what byte stream it is taken over and what a consumer does with it. **It is
written last**, which is the only place it can be: a seal is taken over a finished record.

It was defined and optional under `v0-preview.1`, and it became required at `v0-preview.2`,
which is a break in validity — a document written without one no longer validates — and
§14.1 carries the line that tells a consumer so. A holder that must transform a document and
cannot re-seal it as the producer of what it wrote has §13.1's fourth limit rather than a
document with the member left out.

<a id="holes"></a>

### 7.1 The holes section

Each entry in `holes` is an object of the form
`{"column": <string>, "reason": <string>, "content": <digest>, "closes_with": <URI>}`, with
`content` present only where the paragraph below says, one per name the model cannot account
for, however many of its nodes stand for that name; where a name has more than one, the entry
carries the reason, and the `content`, of the first of them in node order. A hole is minted at
either of two places: a column that is on the frame with no account of itself anywhere in
what the model logged, or a name a calculation *reads* that no frame ever held — not in the
arriving data, not in the schema, defined by no calculation. The first is a column to
explain; the second is a reference to fix, because there is no column.

`reason` says what the producer saw, and has three values. Each names evidence the producer
met and never an inference about why: a reason a producer could not substantiate would be a
guess wearing a type, and a reader would have no way to tell the guess from the observation.

- **`unrecorded`** — nothing accounted for the column, and the producer cannot see why. A
  query plan written directly, past the interfaces the producer logs at, and a gap in the
  producer's own logging leave the same evidence behind: a column in the data with no
  account of itself. A name a calculation reads that no frame ever held is `unrecorded` too.
- **`overwritten`** — a column the producer had accounted for, a calculation it logged or a
  column the data arrived with, that a write past those interfaces then replaced. The
  producer saw the write happen and read off the plan which names it defined. The hole
  stands for that one definition, which the producer can place and cannot read: it carries
  the definition's ordinal (sections 8 and 8.1), its `source_location` is the line that
  wrote it — null where the producer could not resolve that line, as for any definition
  (section 8) — and a calculation written after it reads it. The definition it replaced
  stays in the document as history.
- **`rebuilt`** — a column the frame arrived with whose values a calculation on another
  frame produced, in the same process. The producer saw that the column's memory was, when
  the frame was built, the memory of a calculated column of another frame's collect, still
  held by that frame or by the caller it handed the values to: values that left one frame
  and came into a new one without the re-entry that carries their calculations across
  (section 7.2). The column arrived, so the hole is unversioned, as an arrival is; what the
  document lacks is the calculation behind its values.

**What each reason cannot see.** An empty array is the claim that the model accounts for
every column it holds, and the claim is exactly as wide as the evidence behind each reason:

- `overwritten` sees a write that passes through the producer's own handle on the plan. A
  write that goes around even that, and an edit to the producer's log, are not seen. A write
  that reorders, filters or moves whole rows defines no column and is not reported — a
  step through the producer's own doors that chooses rows is recorded, in section 7.6's
  selection list, and this sentence is about one written past them — and
  neither is one that hands a column back with its values unchanged. A plan rebuilt in the
  shape of the one it replaces is compared with it on its steps, its text, the memory of
  every table in memory it scans, and the values and parameters of every expression the
  producer's engine shows it — a column of values written as a literal included, on its
  memory or else its values; a difference inside an expression the engine does not show and
  its text does not print — which table a lookup reads, a binning's breaks, two functions of
  the model's own printed alike — is not seen. Where the producer cannot read which names a
  write defined, it reports every column it accounted for that the plan still holds, rather
  than none.
- `rebuilt` sees only shared memory. Values that were copied — filtered, sorted, joined,
  cast, rechunked, sliced, or written out and read back — arrive as data, and so do values
  nobody held any longer when the new frame was built — the other frame had moved on and
  its caller had let go of what the collect handed back — values from another process, and
  a one-row column, which the producer's engine holds as one value rather than as memory of
  its own. A column whose memory is also one of the other frame's arriving columns holds the
  data's own values, and is never reported.
- `unrecorded` is minted where the frame holds a name nothing accounts for. A producer told
  which columns the policy data carried also reports a name the frame arrived holding that
  the data never had; one not told has only the frame's word for what arrived. The reference
  producer is told on the command line, and by every batch runner and scenario plan that ran
  the model, so a record any of them writes names the same holes; an export taken in a session
  that started the model itself is told only where its caller passes the book's columns.

**`content` is present on a hole the frame arrived holding, and only there.** A `rebuilt` hole,
and an `unrecorded` hole for a name the frame arrived holding that the policy data never had,
carry `content`: the content hash (section 12.3) of that one column as the frame arrived
holding it — its name, its type and its values in the order they arrived — read as a book is
read, a category as its text (section 7.5). It says what the column held, never what made it:
the node stays a hole with a null `provenance`, because a stamp is evidence of values and not a
claim about their lineage, as the stamp a column brought back through a re-entry carries is
(section 7.2). An `overwritten` hole and a name no frame ever held carry no `content`, since the
producer holds no arriving values for either, and neither does a hole whose values the producer
could not read. Section 12.4 folds the stamp beside the name, so an edit to a file the model's
setup joined moves `graph_fingerprint`, and every run record's figure for the model, where it
moved none before, and an unchanged file moves nothing; section 12.6 leaves it out, so the
change reads as data and not as a formula. A hole with a stamp is still a hole, and a verifier
holds it open (section 13): the stamp says what the column held, not that it was right.

`closes_with` names documentation describing what closes the hole, so that a reader who meets
one is pointed at what to do about it rather than only told it exists.

The section deliberately restates what the hole nodes already say. The duplication is the
point: "can this model account for every column it holds, and does every name its records
read resolve?" is answered by reading one array, rather than by walking every node and
classifying it — and an empty array is the answer being given, not the question going
unasked.

### 7.2 Boundaries

Each entry in `boundaries` is an object of the form
`{"ordinal": <int>, "position": <int>, "source_location": <string or null>}`, one per point at
which the model froze its plan and kept its formulas.

`ordinal` counts from 0 in the order the boundaries occurred, and is what a node's
`materialized_at` names. `position` locates the boundary in the producer's ordered record of
the model's steps, so a reader can see which definitions fell before it and which after.
`source_location` names the place in the model's source at which the freeze happened, or is
null when the producer could not determine one.

The audit reading is worth stating outright. A column whose value was frozen at a boundary is a
computed column wearing an input's clothes: downstream of the freeze it behaves like data the
model was handed, and a reader given only the frozen value would take it for one. The formulas
survive the freeze, and a node's `materialized_at` is where the artifact says which of the two
it is looking at.

**A hole's `materialized_at` is always null**, whichever side of a boundary its value appeared
on. Nothing in the model accounts for the column, so there is no recorded history in which a
freeze could have settled it, and a producer that cannot see where a value came from cannot see
when it arrived either — the two are one blindness asked about different things. So the field is
read together with the `kind` of section 8: a null on a `computed` or `input` node says no
freeze settled that value, and a null on a `hole` says the producer had nothing to go on.

**Two events produce a boundary, and the section does not distinguish them**, because what a
reader needs from it is the same in both cases: where the freeze happened, and which
definitions it settled.

The first is a model that freezes its plan and carries on — this producer's `materialize()`.
Nothing leaves; the values settle and the same frame goes on being written.

The second is a model that hands its values to something outside itself and takes them back —
a generator drawing decrements, an enrichment step that speaks only the engine's own language.
The values leave, and what comes back is a table of numbers with no account of itself. A
producer may offer an explicit re-entry for this (this one's is
`ActuarialFrame(df, continue_from=af)`); where it does, the boundary is where the values left,
and the columns coming back divide in two:

- A column still holding the values the model's own recorded calculations produce keeps its
  definitions, and reports the boundary in its `materialized_at` exactly as a frozen column
  does. **Whether it still holds them is decided by comparing the values**, never by matching
  the column's name: a node stating a formula that no longer produces the number under it is a
  lineage claim the file cannot support, which is worse than the same file admitting it does
  not know.
- A column the trip changed, and a column the trip added, is not that column any more. It is
  recorded as a definition of its own — `kind: "input"`, `provenance: "continuation"`
  (§8), carrying a content stamp of its values and the source location
  of the statement that brought it back — and its `materialized_at` is null, because it was not
  on the frame when the plan froze.

**That comparison reads the rows in the order they arrive.** So a frame whose rows were
reordered or filtered while they were outside comes back as arriving data — every column whose
values the reorder moved, which is every column but one a permutation cannot change. A flat
loading, a level rate, an all-true indicator compares equal after a whole-row permutation and
keeps its definition, and the rule above is what says so: a column inherits the donor's lineage
only if it still holds the donor's values. The loss on the rest is deliberate. A producer at
this boundary holds two tables of numbers and no account of what happened between them, so a
reorder and a rewrite are one observation; this format has it state less rather than guess
which of the two it met.

A producer that offers no such re-entry emits no boundary for the second case, and the columns
come back as inputs of a new model. That is a true account of what it can see. What no producer
may do is carry the lineage across on the strength of the names agreeing.

<a id="sources"></a>

### 7.3 The sources section

Each entry in `sources` is an object of the form
`{"path": <string>, "fingerprint": <"sha256:<64 hex>" or null>, "payload": <object>}`, **one per
distinct path any node's `source_location` names** (§8), ordered by `path`.

The model's own text travels with the account of it. Until this section the artifact named the
model — `model.source_path`, `model.source_sha` — and every node carried the line its
calculation was written on, and it carried no line of the file. So a consumer could be told
which line computed a figure and could not show it, and a second reader holding the artifact
had the formulas without the code around them: the comments, the section structure, and the
code between the formulas that says what the model is doing and why.

**It is here rather than in `assumptions[]`, and the distinction is the point.** Section 15's
directory is an account of the *bases the model read* — the rate tables, schedules and curves a
formula resolved — and a model's own text is not one of those. A consumer looking for the code
should not have to filter a directory of mortality tables to find it, and a reader asking "what
did this model rest on?" should not be handed the model.

**`path` is the same string the nodes carry.** A node's `source_location` is `<path>:<line>`
written against the model's root (§7); this is that same `<path>`, produced the same way, so a
reader who has followed a node to `model.py:520` looks up `model.py` here and arrives. A section
that spelled its paths its own way — absolute where the node was relative, resolved through a
link the node was not — would leave the lookup missing with nothing in the document to say why.
The ordering by `path` is so that two artifacts of one unchanged model compare as written.

**`fingerprint` is SHA-256 over the file's own bytes.** It is neither of section 12.3's
grammars, and section 12.3 says why: a model file is text somebody wrote rather than a frame of
values or a canonical recipe, so there is nothing to project, order or normalise before hashing.
It is the same stamp `model.source_sha` carries, which makes one guarantee worth stating on its
own: **the entry whose `path` is `model.source_path` carries exactly `model.source_sha`.** That
is what lets a page showing the source say that the source it is showing is the source that ran.
Every other entry carries its own digest under the same rule. It is **null** only where the
producer took no digest at all, and then the payload is an `omitted` object: the two absences
are one event, and an entry claiming text under a digest nobody took would be publishing bytes
nothing in the document identifies.

**`payload` is the file's text or section 6.1's `omitted` object**, and the member named
`omitted` is what tells the two apart, exactly as it does for an assumption entry. An inlined
payload is `{"text": <string>}` and nothing else: the file's bytes decoded as UTF-8, which
re-encode to those same bytes exactly — so a consumer re-encodes what it reads and reaches the
fingerprint beside it, with no rule about line endings and no normalisation on the way through.
Section 13 states that reading.

The three reasons a text is not here are section 6.1's three, and each says something different
about the same file:

- **`size`** — the text was weighed and is above the producer's inline budget, and `bytes` says
  what fetching it would cost. The budget and the stand-in are a table's, unchanged (§15).
- **`unavailable`** — the producer could not read the file from where it was standing. A path
  resolving **outside the model root** is this, and deliberately: the root is the width of what
  an artifact speaks for, a file beyond it belongs to a tree this document does not account for,
  and its path — a `..` climb, or its name under `<outside the model's root>` (§7) — is the only
  honest thing the section can say about it. An entry whose `path` is a name under
  `<outside the model's root>` is `unavailable`, as every file outside the root is. So is a file that has
  moved, and so is one whose bytes are not text.
- **`withheld`** — the producer held the text and was asked not to disclose it. The path and the
  fingerprint still travel, so a reader knows what was left out and can check a copy of their own
  against it.

**Carrying the text is the default, and leaving it out is the act the file records.** A format
in which disclosure were the unusual case would put the burden on the wrong side: the reader
would have to ask, and the file would not say whether asking was worth it. What this costs is
about two per cent of a document on the models measured, and a disclosure decision in front of a
modeller who did not have one before — which is what `withheld` exists to make sayable.

A producer that carries no location on any node writes the empty array, which is the claim the
other sections' empty arrays are: this document accounts for no file, rather than one being left
out.

<a id="policies"></a>

### 7.4 The policy axis

Each entry in `policies` is an object of the form `{"policy_id": <string or null>,
"aggregation": <string or null>, "periods": <array of int or null>, "filter": <string or
null>, "why": <string>}` — **one per policy the artifact carries values for, in the order the
producer selected them**, the folds of the book first. The first four members are `enrichment`'s
own, with `enrichment`'s meanings. The fifth is new.

An artifact used to carry one policy, and the envelope said so in one context object. It still
carries one by default and may now carry several, and the axis is where they are declared. Two
questions a reviewer puts to a model — *how does this policy differ from that one?* and *show
me the twenty where the sign flipped* — have no answer at all in a document holding one model
point, and the second has no answer in a portfolio total either.

**The axis is declared here and nowhere else.** A node carries its values in this array's order
and names no policy of its own. The alternative — a policy named on every value of every node —
was written and rejected for the reason §8's withdrawn window was rejected: it is a document
whose envelope says one thing and whose nodes say another, and the disagreement is discovered by
a reader who has already believed one of them. One declaration cannot disagree with itself.

**`why` is a plain sentence saying how this policy came to be in the file**, recording the row it
sits at and the id it carries. *"row 0 of 1,000 in model_points_1k.parquet"* and *"named on the
command line, row 6 of 1,000 in model_points_1k.parquet"* are both entries. It is on every entry,
including the one a document nobody narrowed produces, and that case is the one it was written
for: a reader who meets a single policy and no account of how it was chosen assumes somebody
chose it, and on the overwhelmingly common export nobody did — it is the first row of the file.
A sentence is the shape because the reasons do not fall into a vocabulary: a producer may select
by identity, by row position, by walking a book ordered on a column, or by having been handed
one policy, and a closed enum over that list would be wrong by the time a second producer wrote
one.

**How a producer names the policies is a producer's business, and one thing about it is not.**
This document does not specify a selection syntax — it specifies what the file says about the
selection that happened. But `why` has to be a sentence a reader can act on, and that means the
producer has to have been able to tell *the seventh policy* from *policy 7*. **A policy
identifier is a string the model's author chose.** It is `POL-000343` and `GB-2019-88231` as
often as it is `7`; it is out of order, it has gaps, and it is occasionally carried by more than
one row. A producer that infers which of the two was meant by looking at what the book happens
to hold makes one instruction mean two things on two books, and a producer that resolves a
repeated identifier to its first row puts one row's numbers under a name the others answer to
as well. The reference producer decides by the *form* of what it was given — a whole-term slice
grammar is a position, a literal escape is an identity, and everything else is an identity —
refuses an identifier more than one row carries, and records the row and the identifier together
on every entry so that a reader never has to work out which was meant.

**Nothing on this axis is chosen for the reader.** This specification defines no automatic
selection — no inferred ranking column, no cohorts, no anomaly rule — and a producer that adds
one is making a claim this format cannot check. A selection that picks badly is worse than a
visibly arbitrary one, because a clever rule looks authoritative: *"row 0 of 1,000"* tells a
reader exactly how much to read into the policy in front of them, and *"the most representative
policy"* tells them something the producer cannot substantiate.

**`enrichment` is `policies[0]` with `why` left off.** The envelope states the same context in
both places, and the omission is exactly the member the edition before this one did not define.
So a consumer written against `gaspatchio-graph/v0-preview.2` reads a document carrying five
policies as the first of them and is not wrong about anything it reads there. What it does not
see is the other four, and that is the whole of what this edition adds to an envelope.

**A document carrying values carries at least one entry.** An empty array beside a stated
`enrichment` is the envelope contradicting itself, and a stated context beside no values is what
`enrichment: null` and `policies: []` say together.

**The values of every carried policy travel, including the walk-throughs.** §8's `trace` is not
the first policy's alone: a policy whose worked example is missing is a policy the document
answers differently about, and a reader who followed a number to its walk-through on one policy
and found none on the next would have learned that the file's own account of itself depends on
which entry they opened.

**Carrying a policy on this axis says which values were sampled and never which rows were
computed.** A producer must not narrow the model run to the policies it selected. A model with a
cross-row step answers differently when the book behind it is smaller — a scenario axis is a
cross-join on the model points, and a fold over one reads across rows — so a narrowed run would
give a policy one value in a two-policy export and another in the run that was actually
performed, and every value in this document is a quotation of a run that was performed. A value
that is only what it is because the export was narrow is a quotation of nothing.

The narrowing a producer *was* asked for is a different member and is already defined:
`filter`, on every entry of this axis, is the cut the sampled rows had been narrowed by. So a
reader holding a value knows whether the rows behind it were cut, and knows it from the field
that says so rather than by inferring it from how many policies the axis happens to carry.

**The book's own fold is an entry on this axis rather than a property of the run.** Its
`policy_id` is null, because no policy is what it is an account of, and its values are the fold
over the policies that entry declares. A portfolio total belongs to that entry; it never belongs
to a policy entry beside it, and a document whose per-policy values quietly became per-selection
values would have put it there without saying so.

**`aggregation` names the fold, as the framework that performed it spells the aggregator.**
`sum`, `period_sum`, `mean`, `count`, `min`, `max`, `variance`, `std`. It is a name and not a
closed list: the two words this member carried were written before there was an aggregator set
to name, and an enum of them would refuse a document stating a fold that had genuinely been
taken. A consumer reads it as a label — the producer's own word for what it did — and a
producer writes the word its framework uses rather than translating it into somebody else's
vocabulary, because a translation is where the document stops being checkable against the run.
A fold down each period of a timeline and a fold across the book are two different statements
about one column, and the name is where a reader is told which one they are reading.

**The fold is the producer's own, over the whole book, and never a re-summation of what the
document carries.** The values on this axis are the handful of policies a reader asked for;
adding them up and publishing the result under the book's name would state a number that is
nobody's. A reader who checks a total against the results file `model.results` names has to
reach the same number, which is only true if the fold read the same rows. **The reference
producer takes the fold over the book as one batch**: the frame is the book, as it is in the run
the document quotes, so the figure does not depend on how much memory the machine that wrote it
had, and a setup that rebuilt its frame from collected values — which a batch of several
refuses (section 13.2) — is folded over the rows that run read rather than refused.

**A fold of one cut of the book uses `filter`, and there is no member for it beyond that.**
A fold partitioned by a column — a scenario axis is the ordinary case — is several folds of
several cuts, and this axis carries one entry per cut. `filter` is already defined as *the cut
the sampled rows had been narrowed by*, and a group is exactly that, so the entry says it in
the member that means it: `scenario_id == "BASE"`. A second member naming the group would state
the same fact twice and let the two disagree, which is the failure §8's withdrawn window and
this section's own "declared here and nowhere else" are both about. The entries of one grouped
fold are ordered by their cut, so two artifacts of one unchanged run compare as written.

**The fold entry's `filter` is the fold's own cut and not the export's.** A producer asked to
narrow the sampled rows narrows the sampled rows; the book it folds is the book. So a document
may carry policy entries stating one cut and a fold entry stating another or none, and each
entry is true about its own values. A reader holding a number knows which rows are behind it
from the entry it sits on.

**A column no accumulator covers carries null at the fold's position**, in `value_sample` as in
`trace` and `branches`. There is no portfolio value of a monthly mortality rate, and a producer
that wrote one — a sum of a thousand rates, a mean of a thousand dates — would publish a figure
under a column name that has never held it. The null is §8's rule applied where it was written
for: a producer with nothing to write at one position writes a null there, and the axis stays
one length throughout.

**`trace` is null at a fold entry on every node, including the covered ones.** A walk-through is
one policy's arithmetic replayed against the row its sample came off, and no such row exists for
the book: nothing ran once over a thousand policies that a reader could be walked through. So a
consumer shows no worked example on a fold entry, and shows it as *absent* rather than as an
empty one.

**A cross-joined book names each policy several times, and that is a fact about the rows rather
than about this section.** A scenario axis in this framework and in others is a cross-join on the
model points, so an identifier naming one policy names one row per scenario. A producer that
refuses a repeated identifier — as this section's own rule requires — therefore refuses to select
by identity on such a frame, and correctly: taking the first row would put one scenario's numbers
under a name the others answer to as well. **There are two ways through and a producer states both
before a reader meets the refusal**: a row position reaches a row — `:N` in the reference
producer's grammar — and `filter` narrows to the scenario meant. The fold is unaffected: it reads
every row, and its grouped entries are how the scenarios are told apart.

**The cut comes first and the selection is made inside it**, and a producer offering `filter` as
the way through a repeated identifier has to order the two that way round or it is offering
nothing. The reference producer resolved the identifier over every row and *then* applied the
cut, so `--policies 7 --filter 'scenario_id == "BASE"'` refused policy 7 as carried by three rows
and recommended, in the same sentence, the filter that leaves one of them. A way through that the
command then refuses is worse than no advice, because a reader spends the attempt before learning
it. So the rows the cut keeps are the rows the selection is made among — a row position, a
spread, `all` and an identifier alike — and an identifier is still refused where more than one of
*those* carries it. Where the cut names a column the model computes rather than the model points
carry, it cannot be taken before the run at all; the producer then narrows the sampled rows as it
always did and the selection is made over every row. The ordering is a producer's business in the
same sense the grammar is. What this format requires is narrower and not negotiable: **a
refusal's named way through is one the producer will accept.**

**Every entry on such a frame states its own cut, the policies as well as the folds.** A row of a
cross-joined frame is one policy under one scenario, and three entries reading `policy_id: "1"`
with nothing between them would be an axis a reader cannot walk — the one failure this section's
`why` and this member exist to prevent. So a policy entry's `filter` names the scenario its row
sits in, in the same form a grouped fold's does: `scenario_id == "DOWN"`. Where the export was
*also* narrowed — the producer was asked for a cut of the periods as well — both are true of the
rows behind that value and both are written, joined. A `filter` that stated one and dropped the
other would understate the narrowing, which is the one direction this member must never be wrong
in.

**How a scenario run reaches this format at all is a producer's business, and one thing about it
is not.** The scenario axis is not the model's doing: the model reads the axis column and
dispatches on it, while the plan is what cross-joins the axis, shocks the bases and folds each
scenario. A producer that ran the model alone would write a document with no scenario anywhere on
it — one assumption entry where the run read three curves, and a lookup proof naming a base the
selected scenario never discounted with. So a producer exporting a scenario run **runs the plan**,
and the reference producer takes it from the modeller's own run script: `gspio calc-graph
--scenarios run_scenarios.py`, reading a plan declared at module level under a name it publishes,
refusing by name where the script declares none. What this format requires is not the mechanism
but its consequences: the values are quotations of the cross-joined run, every entry states its
scenario in `filter`, `assumptions` carries one entry per base the run read rather than one per
stack it was built from, and the run's own record — where the producer keeps one — is named in the
version block by path and digest.

**A selected row is found again after the run; it is never counted to.** The axis is chosen over
the model points and the values are read off the frame the model handed back, and those are two
frames. A model that sorts, filters, joins against a table matching twice, or collects and
rebuilds its frame leaves the second holding the same policies in another arrangement — and a
producer that read row *n* of the finished frame because it had counted row *n* of the book
publishes a document naming one policy over another policy's numbers, with every other claim in
it true. That is the worst failure this format has: not a value missing, which a reader sees, but
a value present and wrong under a name a reader trusts. So a producer carries the selected row's
identity **through** the run — the reference producer stamps each row of the book before the
model starts under a name no model would write, reads the selected rows back out of the finished
frame by that stamp, and takes the stamp off before the document is written, so nothing of the
scaffolding is on the wire and no node, no digest and no `graph_fingerprint` moves for it. Where
the model did not hand the stamp back, the policy identifier stands in on the condition that
makes it sound: exactly one row of the finished frame carries it. **Where neither answers, the
export refuses**, naming what the model did to the book and the ways through. *Meet you where you
are* would rather a document came out of whatever the model did; *Audit by default* would rather
none came out than one carrying somebody else's number. At this boundary the second wins, because
a refusal costs a command line and the alternative costs a valuation somebody signs.

**`why` says both, where they differ.** The row selected is a fact about the model-point file and
a reader should be able to find it there; where the model moved that row, the sentence says where
it ended up as well. A sentence reading *"row 0 of 2"* beside a finished frame whose row 0 is a
different policy is a sentence a reader would check and find wrong.

**A consumer checks this with the one witness the file carries.** A document written by a
producer that got it wrong is internally consistent — the fingerprints hold, the axis is as long
as the enrichment, the walk-through agrees with the sample it was built from — so nothing derived
from the calculation can catch it. What is left is the identifier standing beside the
numbers: **where an entry names a policy and the document carries the model points' own values at
that entry, some value it carries there must be that policy.** A reader that finds none refuses
the document.

The question is asked of the model points and answered by any node, and the two halves are
deliberately different. It is asked only where the model points reached the document, because
that is what makes an identifier answerable at all — a fold entry names no policy, an artifact
carrying no values carries no samples, and a run whose every model-point field was dropped or
made per-period leaves the question unanswerable rather than answered wrongly. It is answered
from anywhere in the entry, because a model that renames its identifier on the way in carries it
on a calculated column, and a reading that insisted on the arriving one would refuse an honest
document over a rename. The result is a floor rather than a proof: a duration that happens to
read `1` beside policy `"1"` satisfies it. It is the floor the failure it was written for falls
straight through, which is the whole of what it is for.

### 7.5 The book

`book` is the envelope's account of the policy data the model was run over, as an object of
the form `{"columns": [<string>, …], "digest": "sha256:<64 hex>"}`.

**The digest is taken over the data, never over a file.** It is section 12.3's content grammar
over the named columns, in name order, with the rows as the book holds them. So the same
in-force written out twice — by two Parquet writers, or with its columns in two orders — is one
book, and one revised premium is another. A file hash answers *which bytes?* and moves when a
writer changes a default; this answers *which policies?*, which is the question a comparison
of two quarters is asking.

**The columns are the ones the model's answers rest on.** Every column the data arrived with
that the finished frame holds, or that some line of the model reads on the way to a column the
finished frame holds, **or that a step choosing which rows were valued reads** (section 7.6):
reached from every node whose `in_final_schema` is true and from every selection step, back
along `reads`, keeping the `input` nodes. The last of those is what a filter on an in-force
flag the model then drops would otherwise lose: which policies were valued rests on that
column, and a book revised there is another valuation. That is the set a consumer executing the document requires of the book it is
handed. **So the digest is the one a result manifest records as `inputs_digest` exactly when
the engine was handed the book itself** — this policy data, with the rows as the book holds
them — and a document and such a result are matched by content. An engine handed anything else
records a digest of what it was handed, and the two differ, as they should: the book crossed
with a scenario axis carries a column the book does not hold on rows the book does not have,
and a book filtered or reordered before the engine saw it is other rows. A column no line reads and the
finished frame does not hold cannot move a number, and is no part of the book's identity: a
book revised only there is the same book. A required column the data never held — a scenario
axis crossed onto the book, whose values the node carries its own stamp for (§8) — is left out,
and `columns` names exactly the columns the digest was taken over, so a reader holding the book
takes it again over those and nothing else.

**Every producer writes it, and writes it by default.** The model block's `model_points` (§7)
names the file a run read, where the run knew it, and is the caller's account; `book` is the
producer's own, taken from the data the model was built over, and it needs nobody to have
named anything. The two are different claims and both are kept. A comparison of two documents
(§14.2) reports a changed book as data drift from these digests.

**A book the producer cannot vouch for is said so.** Where the producer held no data beside the
graph, or a column the model reads holds a type section 12.3's grammar cannot read, `digest` is
section 6.1's `{"omitted": "unavailable"}` and `columns` still names what would have been
digested. The form carries `detail`, saying which of the two it was and, for a refusal, the
refusal's opening sentence — the column and the type it met. **A document built only to be
handed to an engine in the producer's own process**, rather than filed, takes no digest either:
the engine digests the inputs it is handed into its own result manifest, which is the record of
what it ran over, so a digest here would be a pass over the book paid for on every run and read
by nothing. Its `detail` says the digest was left to the engine. A column held as categories is not
such a column: the book's digest reads a `Categorical` or an `Enum` as the text it holds (section
12.3), so the same policies extracted as categories by one pipeline and as text by another are
one book.
There is no `size` form, because the book is never inlined, and no `withheld` form, because a
digest discloses no value.

**It is an identity, not the data.** No value of the book travels in this member. A holder of
the book checks the document against it by taking the digest again over `columns` (section 13);
a holder of a result checks it against the result's own `inputs_digest`, where the engine that
wrote the result was handed the book itself.

<a id="selection"></a>

### 7.6 The selection

`selection` is the record of which policies the model chose to value: one entry per step that
chose rows, in the order the model took them. A filter keeping the in-force business, a semi
join keeping the policies a product list names, an anti join dropping the ones an exclusion
list names — each defines no column, so no node accounts for it, and each decides which
policies every number in the document is a number about.

**The in-force definition is part of the model.** It is the first assumption a reviewer
challenges and one that moves quarter to quarter — paid-up business admitted, a lapse status
recoded — and a record that left it out would tell a reviewer *formulas unchanged* across a
change to which policies were valued, and let a replay of the document value policies the
model left out under the model's own fingerprints. So a step is an entry of its own, it enters
both fingerprints, the columns it reads are part of the book, and every replay makes it again.

Each entry is an object of the form `{"id": <string>, "kind": "filter" | "semi" | "anti",
"expr": <tree>, "tier": <string>, "reads": [<node id>, …], "local_fingerprint": <digest>,
"fingerprint": <digest>, "source_location": <string or null>}`, and an entry whose kind is a
join kind carries one member more, `"right_fingerprint": <digest or null>`.

- **`id`** is `selection:` followed by the step's position in the list, counting from 1. It is
  section 8.1's third reserved namespace, so no column is produced into it, and it is
  positional within one artifact, as a node's ordinal is: it is what a change report and a
  refusal name the step by.
- **`kind`** is what the step keeps. `filter` keeps the rows its predicate holds for. `semi`
  keeps the rows whose key the right side holds, and `anti` the rows whose key it does not.
- **`expr`** is the step's predicate as an operation tree, in the grammar a node's `expr` is
  written in (section 8), and **it travels in both profiles**: a step has no column to quote a
  formula on, and the tree is the whole account of it. A filter's tree is its condition: true
  for a policy kept, and false or null for one dropped — a null answer keeps nothing. A semi or
  anti join's tree is section 11.1.2's `join` call, its `how` the step's kind, its `on` the
  key and its `right_fingerprint` the right side's content identity; the right side itself
  travels as an entry of the assumptions directory of kind `join` (section 15), on exactly the
  terms a column-bringing join's does.
- **`tier`** is the tree's tier (section 11.2), read as a node's is.
- **`reads`** names the nodes the tree's column references bound to **when the step was
  taken**, in the order the tree names them, by section 8's rule: a filter on `status` taken
  before a line rewrote `status` reads the column as it arrived, and one taken after reads the
  rewrite. A semi or anti join reads its left key, as a join node does.
- **`local_fingerprint`** is SHA-256 over the step's kind as text — its byte length, then its
  UTF-8 — followed by the tree's canonical bytes (section 12.1), with nothing between them. The
  kind is in it because a step that went from keeping the rows a key matches to dropping them
  is a different step over a tree of the same shape.
- **`fingerprint`** is section 12's fold over that digest and the published fingerprints of
  what the step reads, in the order `reads` states: a step whose predicate stood still while a
  column it reads was redefined has moved in identity and not in itself.
- **`source_location`** is the line the step was written on, rooted as every location is
  (section 7), or null where the producer could not resolve one.
- **`right_fingerprint`**, on a semi or anti join, restates the join call's attribute, so a
  reader of the list need not parse the tree; null for a right side handed over lazily, which
  carries no identity and no entry (section 11.1.2).

**Absent where the model chose no rows, and never empty.** The member is optional: a document
written before it carries none, and a producer conforming to this edition writes it exactly
where at least one step was taken. That is what lets a model that selects nothing keep the
digests it had — section 12.4's selection section is absent rather than empty — and it is why
no published digest moved when the member arrived. A document written before this line said
nothing about selection, and its fingerprints did not see one; section 14.1 carries the line.

**A model whose only step is a selection is a document like any other.** Its `nodes` are the
columns its book holds, its `edges` are empty, and its `selection` is the whole of its account:
which policies it values is the model. Section 7 asks a document for no calculated node, and a
producer writes such a document in either profile. A frame that neither calculated nor
selected has nothing to account for, and a producer may refuse it.

**Both fingerprints cover it** (sections 12.4 and 12.6). A step's own literal, operator, key or
kind is something a modeller types, so changing it moves `graph_fingerprint` and
`formulas_fingerprint` alike; a semi or anti join's right side is data, so a re-sourced
in-force list moves `graph_fingerprint` and leaves `formulas_fingerprint` where it was, as a
re-sourced join does.

**Its reads are the book's** (section 7.5). A column a step reads — back along `reads` to the
columns that arrived — is in `book.columns` whether or not the finished frame still holds it,
so a holder of the book checking the document against it (section 13) checks the in-force flag
the model filtered on and then dropped. **A column no line and no step reads still cannot move
the book**: the rule of section 7.5 is widened by exactly the columns a selection reads.

**A replay makes the selection again, before it projects.** A consumer executing a document
over a book applies each step, in list order, to the book before it evaluates any node: a
filter keeps the rows its predicate answers true for, a semi join the rows whose key the
carried right side holds, an anti join the rest, and a null key matches nothing. Every node is
computed over the rows the steps keep, in the book's order, and a fold over the run folds those
rows and no others. A result manifest's `inputs_digest` is still the digest of the book the
engine was handed (section 7.5), so a document and the result of replaying it over its own
book are matched by content, the selection having been made by the replay rather than before
it.

**So in the `executable` profile every step is one a replay can make over the book.** Its tree
is `core`, and every column it reads is a column of the book: an arriving column, or one
renamed on the way in, which is the arriving column under another name. A producer refuses to
write an `executable` document carrying any other step, naming the step and its line, and says
what to write instead; the `audit` profile carries every step whatever its tier, a predicate
written in an engine's own language recorded as that engine's text (section 11.2) as a node's
would be. **A step that reads a column the model calculates is refused from the `executable`
profile by this edition.** Its place between the calculations is recorded — its reads bind to
the definitions live when it was taken — but a replay that applies the selection to the book
before it projects has no value for that column yet, and this edition states no replay that
interleaves the two.

A step may read a compiled rollforward's state as a node may. Its tree carries the
`rollforward.*` call (section 16), and its `reads` name the compilation's node, never the column
the producer keeps the run in. A state is calculated, so the rule above refuses such a step from
the `executable` profile.

**A `filter` step's predicate answers once per policy.** A selection keeps or drops a policy in
every period at once, so a predicate with an answer per period — a comparison or a null test on
a per-period column, or on a rollforward's state — is not a selection. The reference producer
refuses it where the author writes it and records no step. A per-period column enters a
predicate through a reduction to one value per policy (`list.get`, `min` or `max`, sections
11.1.22, 11.1.16 and 11.1.17). A consumer handed a document whose `filter` predicate it types as
per period may refuse that step by name.

**A step reading a book column the replay is not handed is refused by name**, as a node's
missing input is: the engine was handed another book than the one the model chose from.

**What this section does not change.** Section 7.4's row identity stands: a policy on the
axis is found again by its identity after the run and never counted to, and a policy the
model's own selection dropped is refused there as before. **The route that selects before the
frame is built records no step**, and is a true account too: a model that collects its model
points, selects in the engine's own language and builds a new frame from the rows it kept has
a book that is those rows — its digest is over them, and a reader comparing it with the book
it was cut from is told the books differ — while the selection itself, made outside the
record, is not in it. Masking with a conditional — keeping every row and zeroing the cash
flows of the policies not valued — is a third route, and a different model: every row is
valued, and the mask is a node like any other.

**What it does not see.** A row-selecting write made past the producer's own handle on the plan
is section 7.1's overwritten write: it defines no column and is not reported, and this section
is about the steps that go through the producer's doors.

## 8. The node record

A node is one account of one column. The `nodes` array carries one entry per account rather
than one per column: a column the model defined three times is three nodes, and the definition
the frame ended up holding is the one whose `in_final_schema` is true. The rest are history,
and that history is what makes a change report possible at all.

Every field marked required below is required in the `audit` profile, and an `executable`
artifact is a conforming `audit` artifact (section 3), so every one of them is required in
both. Several are nullable, and a null here is a claim rather than a gap: it says the
producer looked and there was nothing to find. A consumer that had to infer a structural fact
from a field's absence would get it wrong eventually; an explicit null never lies.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | §8.1. |
| `column` | string or null | yes | The column this node defines or supplies. Null only in a reserved id namespace; §8.1 lists the two this preview defines and §17 may add its own. |
| `version` | integer or null | yes | Which definition of `column` this is, counting from 1. **Null on a node nothing defined** — an arriving column, an `unrecorded` or `rebuilt` hole, a running state. An `overwritten` hole is a definition the producer saw written and could not read, and carries its ordinal (§7.1). |
| `kind` | enum | yes | What account this node gives of its column. |
| `dtype` | string | yes | §10. |
| `shape` | `scalar` \| `list` \| `unknown` | yes | One value per policy, or one per projection period. |
| `provenance` | enum or null | yes | Where this node's values came from, or which recording door defined them. |
| `formula` | string or null | yes | §8.2. |
| `reads` | array of node id | yes | What this node read, in the order its formula names them. |
| `reads_assumptions` | array of string | yes | Names of entries in the envelope's `assumptions` section this node's own formula reads. Usually empty. |
| `extracts` | object, or array of them | **no** | The compilation this column materialises a running balance of, and which balance; §16. Carried by a column whose formula extracts a state, in both profiles. |
| `settings` | object | **no** | The timing convention the operation at the **root** of this node's calculation ran under, as that operation's own §11 attributes. Two identifiers state one: `projection.cumulative_survival` and `projection.prospective_value`. Absent on every other node, and on a node whose accumulation is nested inside a larger formula. `audit` profile, and so both. §8 below. |
| `engines` | array of string | **no** | §8.3. |
| `tier` | enum or null | yes | §11.2. Null on a leaf, which has nothing to execute. |
| `local_fingerprint` | `"sha256:<64 hex>"` | yes | §12. |
| `fingerprint` | `"sha256:<64 hex>"` | yes | §12. |
| `in_final_schema` | boolean | yes | Whether this node is what the frame's column actually holds at the end. Every other node is history rather than an answer. |
| `retained` | boolean | no | Present and true only where `in_final_schema` is false, stating that the producer held this definition's own output to the export and read its enrichment off that. §8 below. |
| `materialized_at` | integer or null | yes | The boundary ordinal (§7.2) at which this node's value was frozen, or null. |
| `source_location` | string or null | yes | `file:line` in the model author's own source, or null where it could not be resolved. The path is relative to the model's root, as the `model` row defines it (§7), and is never absolute. **The file it names is in `sources` (§7.3)**, under that same path and carrying that file's own text where the producer disclosed it — so a reader who has arrived at a line here can read it rather than go looking for a copy of the file and hope it is the right one. |
| `anchors_to` | string or null | no | §6.2. |
| `facets` | object | yes | May be empty. |
| `expr` | operation tree | no | `executable` profile only, marked unstable. |
| `states` | array of string | no | `rollforward` nodes only, `audit` profile (§16). |
| `value_sample`, `trace` | any | no | Enrichment, interpreted only under the envelope's `policies` axis (§7.4). A `value_sample` on a per-period column carries the declared context's **every period**, in order, where that context pinned none. Where the axis carries one policy each field is that value itself; where it carries several each is an array of them, positionally aligned to `policies`. |
| `movements` | object | no | Enrichment, `rollforward` nodes only: what each step of the chain moved, keyed by the kernel's own name for the step — the author's label, or the reserved `{kind}@{ordinal}` on a structural one (§16.2). Every step of the chain is a key. Each value is that step's signed per-period amount in the shape `value_sample` takes, so the axis goes *inside* the member rather than around it. §16. |
| `branches` | object | **no** | Enrichment, and **opt-in**: what each branch of this node's conditional would have held under that same context, and which of the two the condition chose. Absent unless the producer was asked to evaluate them, absent on every node whose whole calculation is not a conditional, and absent where a branch could not be evaluated. It rides the axis with the two fields above: an array of these objects where the axis carries several policies, carrying a null at the position of one whose branches could not be evaluated. §8 below. |

A **leaf** is a node nothing on the model defines: an arriving column, a hole, or a running
state. It has no formula and nothing to execute, which is why `formula` and `tier` are each
null on one. An `overwritten` hole is a leaf although it carries a version: the model defined
it, past the producer's interfaces, and the producer has no formula to give it. A
`rollforward` node is none of those things — it is one compiled state machine, it has an
operation tree of its own (§12.1), and it therefore carries a stated `tier` like anything
else that computes. What it shares with a leaf is `column: null` and
`formula: null` — it is not an account of a column, and no statement in the model's source
defines it (§16).

`formula` and `tier` are null on an injected column as well — a whole column of values handed
over at a line is not an operation (§11), so there is nothing to execute and no expression to
report — while its `provenance` is stated rather than null, because being handed over is
exactly where its values came from.

**`settings` — the convention the accumulation ran under.** "Is this survival
beginning-of-period or end-of-period?" is the first question a reviewing actuary puts to a
survival curve, and "is the current period's cashflow discounted?" the first they put to a
prospective value. The two conventions do not give the same numbers, even at flat rates: a
survival curve differs by one period's decrement, a prospective value by one period's discount.
**What flat rates hide is a wrong conversion between them** — at a constant rate one convention
is the other times one `v`, and discount factors built from each period's own rate equal the
running product — so a model that converts by one multiplication, or builds its factors that
way, passes every flat-rate test it has and is wrong once rates vary by period. The record is
where the mistake is caught, and only if the convention is printed on it. So a node whose
calculation *is* one of the two accumulations carries the convention beside the formula:

```json
"settings": {"start_at": 1.0, "from_survival": false}
"settings": {"timing": "end_of_period", "discount_kind": "rate"}
```

**These are the §11 attributes quoted**, with the same names and the same values the
`executable` profile's operation tree writes — not re-derived from the formula text, not
recovered from a lowered expression, and **not renamed**. The recorded convention is
`start_at`, and §11.1.19 says what it means: null records end-of-period timing and `1.0`
records the beginning of a period. `discount_kind` is the only thing in the record saying
whether `projection.prospective_value`'s second operand is a rate or a factor (§11.1.21), and
a factor read as a rate is a valuation error rather than a parse error. A producer that wrote
its own word here would have the format naming one convention twice.

**The root operation only.** An accumulation nested inside a larger formula —
`af.sum_assured * af.q.projection.cumulative_survival()` — carries no `settings` on the node,
because what the node computes is the multiplication and a reader of a node's settings must
never have to ask which of two operations they describe. That convention travels where a
nested call's configuration has always travelled: in the `executable` profile's tree.

**Absent on every other node**, which is nearly every node — never an empty object, never null.
Two identifiers state settings in this revision. Another may join them by a later revision,
which widens what a conforming document may carry and moves the schema identifier by §14's own
rule; a consumer meeting a shape it does not know passes it on unchanged, as it does any field.

**`value_sample` is what the column held for the declared policy, and for a per-period column
that is the whole timeline.** The envelope declares an evaluation context and the values are
read under it: one policy, and `periods: null` saying no period was pinned. Under that
statement a per-period column's sample is that policy's every period, in order, ending at a
value — a run of 83 periods is 83 numbers. Where the context did pin a period, the sample is
that period's own single value and the envelope's `periods` names it. A column holding one
value per policy carries that one value either way.

**A sampled number is the number the run held, not a display of it.** Every floating-point
value in `value_sample`, `branches` and `movements`, at every position of the axis — a fold's
entry as much as a policy's — and every number a `trace` step carries as a JSON number (its
`result`, and an operand in `values` that is one value) is the full binary64 value the column
held, written as the shortest decimal that reads back to that same double, which is the number
§13.1's seal is already taken over. A consumer parsing a policy's sample therefore holds the
results file's own cell bit for bit, and a reader rebuilding that policy's timeline from the
artifact checks it against the file `model.results` pins at equality rather than at a
tolerance. A non-finite value is §10's sentinel string, as everywhere. **A `trace`'s prose is
a reading aid and not data**: the `expr` a step shows, its `shape` line, and an operand in
`values` written as a run (`[100, 99.6334, …]`) print each number to six significant figures
so that a line stays readable, as a viewer rounds a value it displays, and a reader who needs
the number takes it from the sample or from the step's own `result`. A producer must not round
a value it writes as a number.

**Where the envelope declares more than one policy, the sample is one of these per policy, in
the axis's own order.** `"value_sample": [<first policy's>, <second policy's>, …]`, exactly as
long as `policies`, with a null at the position of a policy the producer had nothing to write
for. `trace` and `branches` are read the same way. **The axis is the outermost container in
every case**, so a per-period column of two policies is two runs and not one run of pairs, and
the question "which policy is this?" is answered in one place for all three fields rather than
three times in three shapes.

**A document carrying one policy writes each field as the value itself**, never an array of
one. That is not a convenience: it is what makes this edition additive. A consumer written
against `gaspatchio-graph/v0-preview.2` reads a single-policy document byte for byte as it
always did, and the only documents whose enrichment it cannot read are documents no producer
could previously write. The shape therefore follows `policies`, which a consumer has already
read by the time it reaches a node: one entry means the value, more than one means the array,
and there is no third case. A producer must not write an array of one, and a consumer meeting
one has met a document that does not conform.

**A node's enrichment is as long as the axis or it is not there at all.** An array shorter or
longer than `policies` puts every value after the first mismatch under some other policy's
name, and a reader checking one of those numbers would be checking a different model point. A
producer with nothing to write at one position writes a null there; a consumer meeting a length
that is not the axis's refuses the node's enrichment rather than reading past it.

The alternative — an opening window of the first few periods and a marker — was written and
is withdrawn. It put the document at odds with its own envelope: the envelope said every
period had been taken and the node carried five. And it broke the one thing enrichment is
for. A reviewer asking what a reserve was at period 84 and what period 83 it was rolled from
is asking for two adjacent cells of one column for one policy; with a window the file held
neither, while a `trace` at period 84 could substitute a number appearing nowhere else in it —
a walk-through the holder of the file cannot re-perform, which is the failure this section
exists to prevent. A `trace` stays abbreviated prose regardless, and its last line is still
the **first** period's value (§8): the walk-through is of one period, the sample is of the
run, and the two are read against each other at that one point.

The cost is bounded and is the reason the fence in the next paragraph is where it is. One
policy's whole timeline across every per-period column, each value the full double, costs a
fraction of the artifact it is written into: 12 % over the same document carrying a five-value
window, on a 128-node projection of 83 periods over a thousand policies whose inlined
assumption tables are the larger part of the file, and 70 % on a 69-node projection of 241
periods whose inlined tables come to 7 KB. **Each further policy on the axis costs its own
enrichment and nothing else** — measured at 139,046 bytes, 20.2 %, of a 689,447-byte document
on the first of those models, so five policies are about 1.25 MB and twenty about 3.3 MB.
Nothing outside the enrichment fields moves: two exports of that model differing only in which
policy they carry differ on 51 of 128 nodes and in `value_sample` and `trace` alone, with every
node fingerprint, the graph fingerprint, `assumptions` and `sources` identical. That is what
makes an axis cheap, and it is a consequence of what a fingerprint is rather than a property
anybody arranged.

**The whole book is still not in here.** A producer must not write a sample holding a value per
policy per period for every policy of the book unless a reader asked for every policy — the
reference producer's `all` selection (§7.4) — and even then the guard over the finished
document bounds it: the axis is the policies a reader asked for, and for the thousand-policy
run above the book's values are two orders of magnitude more than the entire artifact. A guard
over the finished document is how a producer keeps that promise — bytes rather than a count of
policies, because per-policy bytes vary by model by a factor of several — and a document over
the ceiling is refused, never trimmed to fit. The book remains the business of the results
file `model.results` names, which the
envelope pins by content hash for exactly this reason: a reader who needs a policy the axis does
not carry opens that file, checks the digest against the document, and reads it there.

**`branches` — the branch that did not fire, with the value it would have had.** A
conditional's walk-through names the branch the condition chose and says nothing about the
other one, and the other one is in no column of the finished frame: the frame holds the
answer. So "what would this have been if the condition had gone the other way?" — the
question a reviewer puts to every `when` in a model, and the one a regulator puts to a
shock that did not bite — has no answer in the record unless the producer evaluates it.

```json
"branches": {"then": "Yes", "otherwise": "No", "fired": "otherwise"}
```

Three members, all three always. `then` and `otherwise` are what each branch's **whole
subtree** came to for the declared policy, each in the shape and the formatting
`value_sample` is written in: one value for a column holding one per policy, and the
declared context's every period for a per-period column, so that period 37's value and
period 37's alternative are indexed the same way. `fired` names the branch the condition
chose, in the two words the formula itself uses — one word beside a single value, and one
word per period, the sample's own length, beside a run of them.

**On an axis of several policies the member is an array of these objects**, one per policy and
positionally aligned to `policies`, because the axis is the outermost container of every
enrichment field. A policy whose branches the producer could not evaluate carries a null at its
position: the axis is one length throughout, and a shorter array would be a node disagreeing
with the envelope about how many policies the file holds. Inside each object the three members
are what they always were, read against that policy's own sample.

**The outer conditional only.** A conditional nested inside a branch is part of what that
branch evaluates to and states nothing of its own:
`when(a).then(0).otherwise(when(b).then(c).otherwise(d))` states two branches — the `0`, and
whatever the inner conditional came to — because two is what the reader is choosing between
at that line.

**Evaluated by the producer, not derived by a consumer.** The values are the branch
subtrees run against the same row every sample was read from, under the same context the
envelope declares. A consumer cannot reproduce them: it holds the formula and one column of
answers, not the model. That is also why the member is **opt-in** — it costs an evaluation
of both branches of every conditional, and a producer that was not asked writes none.

**Absent, and the absence says which of three things happened**: nobody asked; this node's
whole calculation is not a conditional; or the producer could not evaluate a branch — a
superseded definition whose inputs the frame no longer holds, a subtree its lowering
refuses, an engine-native fragment it cannot run. Never null, and never an empty object. A
node states both branches or neither: one branch and no comparison is not half an answer,
it is a different one.

**A superseded definition may carry enrichment, and only when it declares `retained: true`.**
A value sample is read out of a frame, and the frame a producer holds at export time is the
finished one — so a `value_sample` or a `trace` on a node stating `in_final_schema: false` is,
by default, the number that *replaced* this definition shown against this definition's
formula. That is the wrong number under the right calculation, and it is worse than no number:
a reader who checks the arithmetic finds it correct and has checked the wrong calculation. A
consumer therefore **refuses** enrichment on a node whose `in_final_schema` is false and which
does not carry `retained: true`.

`retained: true` is the producer stating something it can only state if it did it: that it
held *this definition's own* output to the export — the column as it stood before the write
that replaced it — and read the sample and the walk-through off that. Under that declaration
the number belongs to the formula printed beside it, and the refusal above does not apply.
The field is **meaningful only where `in_final_schema` is false**: the definition a column
ends up holding is read off the finished frame like any other live column and has nothing to
retain, so `retained: true` beside `in_final_schema: true` is refused as well. A producer
that did not retain omits the field rather than writing `false`.

`in_final_schema` keeps its meaning unchanged either way: it says which definition the frame
holds, and a retained definition is history that carries its values, not a second answer.
`dtype` and `shape` follow the same line — section 10 permits `unknown` on a superseded
definition because the finished frame holds nothing to read them from, and a producer that
retained one *did* read one, so it states the type it read.

`kind` and `provenance` each carry a closed vocabulary, and each is stated here in full.
`shape` is stated in the table above, `dtype` is section 10's subject, and `tier` is stated
in section 11. **What a column *holds* is not a field of its own**: a `bool` or `list[bool]`
column holds a selection, with the caveat section 10 states, and no second field restates a
type this record already carries.

**`kind` — what account this node gives of its column.**

| Value | The account |
|---|---|
| `input` | The column arrived rather than being derived; `provenance` says where from. |
| `computed` | One definition the model wrote, with an as-written formula behind it. |
| `hole` | Nothing in the model accounts for the name: a column on the frame with no account of itself, or a name a record reads that no frame ever held (§7.1). A versioned hole is one definition of a column, written past the producer's interfaces, that nothing accounts for. |
| `rollforward` | One compiled rollforward, in the `rollforward:` namespace (§8.1, §16). |
| `state` | One running state of a rollforward, in the `state:` namespace (§8.1, §16). It is not a column of the model. |
| `state_graph` | The states of one rollforward taken together, as the entry a reader follows to reach them (§17). |
| `nested_valuation` | A valuation evaluated inside the projection — a reserve struck period by period by an inner model — carried as one node rather than inlined into the graph around it (§17). |

**`provenance` — where this node's values came from, or which recording door defined them.**
One question, and a node has one answer to it. The first four members answer it for a column
that arrived; the rest are the recording doors, which answer it for a column the model wrote.

| Value | Where from, or which door |
|---|---|
| `model_points` | The policy data the model was run over. |
| `assumptions` | An assumption table (§15). |
| `injected` | A whole column of values handed to the model at a known line: data rather than a formula, but *located* data, which is strictly more than a spreadsheet's paste-as-values tells a reviewer. **A scenario axis cross-joined onto the model points is one of these**, and not `model_points`: the file the model was run over has no such column, so filing it under the policy data would be the document making a claim the book cannot back. The line is the one the run's plan was declared or called at. |
| `continuation` | A column that came back through an explicit re-entry (§7.2) holding values the frame's own calculations do not account for: data from outside, located at the statement that brought it back. |
| `assignment` | One column assigned on its own. **A scenario plan's shock on a model-point column is one of these**: the plan rewrites that column per scenario before the model runs, so the node supersedes the book's column, sits at the line the plan was declared or called at, and carries the shock's recipe as its `formula` (on a cross-joined run, the per-scenario read of the factors the plan built, or a `when` chain over the axis). |
| `batch` | A column a single call produced as a batch, whatever the number of columns that call defined (§8.2). |
| `rename` | A column's identity carried forward under a new name (§8.1). |
| `join` | A column arriving from the right side of a join. |
| `projection` | The projection timeline's own configuration. |
| `date` | A column a date operation derived onto a new frame. |
| `rollforward` | A compiled rollforward's own within-period bookkeeping (§16). |

**Which of these a node may state is bound to its `kind`, in both directions.** A record has
one provenance, so the states where it could once claim both an arrival and a door — or
neither, on a node that has one — are refused rather than described.

| `kind` | Legal `provenance` |
|---|---|
| `input` | `model_points`, `assumptions`, `injected`, `continuation` |
| `computed` | `assignment`, `batch`, `rename`, `join`, `projection`, `date` |
| `hole` | null only |
| `state` | null only |
| `rollforward` | `rollforward` only |
| `state_graph`, `nested_valuation` | null only |

A null is a claim rather than a gap here as everywhere else in this record: on a hole it says
the column has no account of itself, and on a running state and the two reserved payload kinds
it says the node is not a thing anything supplied or any statement defined. A producer that
later needs a value for one of those kinds widens the row rather than reshaping the record —
but widening makes a refused document newly valid, which moves the schema identifier by §14's
own rule.

**`reads`, and how an unversioned name in a tree becomes a versioned id.** An operation tree
carries `{"op": "col", "name": "qx_annual"}` — a column name, with no ordinal on it — while
`reads` carries `qx_annual@1`. The binding between the two is a rule and not a convention,
and it is stated here because the `executable` profile claims to be the layer a second
implementation executes the model from, which it cannot be while the binding is left to be
guessed.

**A name in a tree binds to the definition that was live at the moment that line ran.** The
model is a sequence of statements; a producer folds them in that order, holding one binding
per column name, and each statement's own definitions replace those bindings only *after*
every reference in that statement has been resolved. So the rule reads, in full:

- A name with a definition already recorded binds to the **latest** such definition — the
  highest ordinal minted before this statement, not the highest in the finished artifact.
- A name with no definition binds to the **leaf** of that name: the arriving column, or the
  unaccounted column standing where nothing explains it. A leaf's id is the bare name, which
  is why `reads` on a node one hop from the data carries no ordinal.
- Where one statement defines several columns at once — a batch door, a join bringing in a
  right side — **all of them bind against the state before the statement and all advance
  together**, so a sibling of that batch reads the *previous* definition of a name the batch
  also writes, never its new one.
- A join's key is the one name a node reads without its tree naming it as an operand: section
  11.1.2 states it in the `on` attribute. It binds by the rules above, to the definition the key
  held when the join ran, and it is named in `reads` in the order `on` lists it.

**The reassignment idiom is the case this exists for**, and section 8 already calls a
twice-written column normal. `net_cashflow = net_cashflow * (1 + shock)` mints
`net_cashflow@2`, whose tree holds `{"op": "col", "name": "net_cashflow"}` and whose `reads`
name `net_cashflow@1`: a node reading the definition it supersedes. A consumer that bound
the name to the latest definition *in the artifact* would make that node read itself, and
the graph would carry a cycle no model ever wrote. Section 12.5's corpus carries this node,
so an implementation can check its reading rather than reason about it.

**`reads` names each node once, at its first mention.** A formula reading one column twice —
in a conditional's test and again in its then-branch — read one node, and the order is the
order the tree names them on a left-to-right walk. The `edges` array is where the *kind* of
each read is recorded, and two reads of one node meeting there resolve to the stronger claim
(§9); `reads` itself is the list of what was read, in order, without repeats.

### 8.1 The identifier grammar

An id is either a bare column name — the node for a column nothing on the model defines,
which is an arriving column or an `unrecorded` or `rebuilt` hole — or `column@k`, where `k`
is a definition ordinal counting from 1. An `overwritten` hole stands for a definition, and
takes its id as any definition does. `policies_in_force@2` is the second definition of that
column, and a different node from `policies_in_force@1`.

**A consumer must never split an id to recover the column name.** A column name may itself
contain `@`. `column` is the authoritative field, and it is what it is there for. A producer
that meets a genuine collision — a column literally named `policies_in_force@1`, claiming the
id another column's first definition needs — **must refuse to produce the artifact**, and
must name both columns in its refusal.

Three reserved namespaces exist, and a column name may not be produced into any of them.
`state:` names a running rollforward state (`state:account_value@eop`), which is not a column
of the model. `rollforward:` names one compiled rollforward (`rollforward:7be2aa108f31`). A
node in either of those carries `column: null` and `version: null`. `selection:` names one
step that chose which rows the model values (`selection:1`), which is an entry of section
7.6's list and no node at all; it is reserved so that a change report naming a step by its id
(section 14.2) names nothing else.

**That rule is about the name, not about a collision.** A producer meeting a column named into
either namespace **must refuse to produce the artifact**, and must name the column in its
refusal — whether or not anything else in the model claims the id. The point of reserving a
namespace is that a consumer reading ids by namespace can trust what it finds there, and a
column sitting in one is a wrong answer to a question this document says may be asked, whether
or not a compilation happened to contend for the same id. A producer that enforced the rule on
collision alone would refuse the rare model and pass the ordinary one.

Ids are **positional within one artifact** and carry no meaning across artifacts, in the way
a line number is a position in one document. Matching a node across two artifacts is done on
(column, fingerprint), never on id.

**A rename does not move an id.** It mints a new definition with its own ordinal; the
identity record between the two is what ties them, and section 14's change report is where it
is read.

### 8.2 `formula`

`formula` is the as-written right-hand side of the statement that defined the column, as the
model author typed it. **This field is normative, and it is the audit surface**: it is what a
reviewer reads to see the calculation, and what a comparison between two quarters is a
comparison of.

It is null where no single as-written expression defines the column. **The recording door is
the test, not the number of columns behind it.** A `batch` call is null whatever the number of
columns it defined, including one: its right-hand side is the whole call, sibling or no
sibling, and reporting that against a single column would show a reviewer text that does not
compute the number beside it. A `rename`, a `join`, a `projection` timeline configuration and
a `date` derivation are null for the plainer reason that none of them writes an expression
against the column at all. One statement comes through the `assignment` door and still writes
several columns at once — `af.a, af.b = x, y` — and it is null for the batch call's reason
rather than the door's: its right-hand side is the whole tuple, which computes neither column.
It is null again where the source could not be resolved: source read from stdin, an
`exec`-compiled snippet, a `compile('<string>')` fragment and a bare REPL each leave the
interpreter with no retrievable text. A notebook cell is not one of those — the notebook
registers each cell's source where the resolver reads it, so a cell resolves its right-hand
side and reports a location like any file.

**`formula` is free-form author text, not a normalised expression.** It is the source segment
the right-hand side occupies, so a right-hand side written over several lines carries its
embedded newlines, its continuation indentation, and any comment falling between its first
token and its last. A consumer parsing `formula` as a bare expression must expect all three.
The segment stops at the expression itself: the parentheses a wrapped statement is written
inside, a comment before its first token or after its last, and a comment trailing the whole
statement are outside it and are not carried.

**A statement whose assignment target is computed carries the same text on every column it
defined.** A loop writing several columns across its iterations writes one statement, and that
statement is the text each of those columns gets — deliberately, because it is the statement
that defined each of them. What separates them is what the calculation actually was: `reads`
where the iterations read different columns, and `fingerprint` (section 12) where they differ
only in a literal the loop supplied. `source_location` does not separate them, being the one
line the loop body occupies; where two iterations compute the very same thing nothing but
`column` separates them, and nothing should. The alternative — nulling the field whenever the
target is not a literal name — was considered and rejected, because it would discard true
audit text to avoid a diff hazard `reads` and `fingerprint` already resolve.

The engine's own rendering of the same calculation is **not** in the base artifact. It is a
debugging convenience carried by the `gaspatchio_lowered` facet (section 6), it has no
normative force, and a consumer holding both must treat `formula` as authoritative where the
two disagree.

The reason is worth one sentence: a base artifact that churns whenever a dependency changes
how it renders expressions makes quarter-over-quarter comparison unreadable, which is the
whole purpose of the graph-level fingerprint.

**`formula` is quoted, not checked.** That authority is about precedence — which of two
texts describing one calculation a consumer reads first. It is not a claim about
verification, and this is the separate bound: `formula` is the author's text as the author
wrote it, and the producer does not check it against the calculation that ran. Nothing in
this format requires a producer to parse it, and a producer that could parse it is under no
obligation to compare the result with the operation the node records. So a `formula` reading
`premium * 0.95` sits beside whatever the engine was actually handed, and the record does not
assert the two agree. What ties a node to what ran is `reads`, which names the operands the
recorded operation took; the identity fields of section 12, which are computed from that
operation and not from this text; and, where a producer carries one, the `trace` enrichment,
which is a substitution through what actually ran. A reviewer who wants to know what a
column computed reads those. A `formula` on its own is a quotation of the model author,
which is worth having — it is what makes the record legible — and is not evidence about the
run.

**A `formula` that reads a table, a mortality basis, a curve or a schedule has a node that
reads it.** A statement whose read would reach the producer only inside an engine-native
fragment, where the tree could not hold it and the fragment's text names neither the base nor
its content, is refused where it is written rather than recorded (Annex A.2), so a quotation
showing a lookup never sits beside a tree that has lost it.

**The consequence, stated so that a reader does not have to derive it.** `formula` is outside
the identity chain by construction: no node's canonical bytes carry it (section 12.1), so text
altered on its own moves no `local_fingerprint`, no `fingerprint` and no `graph_fingerprint`,
and an artifact whose quotation was edited after it was written verifies exactly as it did
before — in the `audit` profile and, since an `executable` artifact is a conforming `audit` one
(section 3), in that profile too. The exclusion is right and stays: an identity that moved when
prose moved would report a reformatted comment as a model change, and the value of the
quarter-over-quarter digest is precisely that it moves when the computation does and not
otherwise. What follows from it is that the chain is not what would catch a doctored quotation.
Whether a file is the file its producer wrote is a different question from whether a
calculation is the same calculation, and this preview answers only the second; a document-level
integrity mechanism is forthcoming and is not specified here.

### 8.3 `engines`

`engines` names the engines a node's escape-hatch text needs, first mention first. A formula
the framework built for itself reaches into none of them.

**An absent `engines` field is no claim at all. An `engines` field present and empty is a
positive claim that this node is engine-free** and can be executed by anything holding the
operations it names. A validator must not conflate the two.

The field is optional precisely so that a third-party exporter can conform without computing
something it has no way to know. A producer that cannot see which engines a fragment needs
leaves the field out and says nothing, rather than emitting an empty array and saying
something false.

**`engines` is a node's own requirement and not the closure over what it reads.** A node whose
own text reaches into no engine writes `[]` even where a node it reads names one — the field
describes this node's escape-hatch text, as §11.2's tier beside it describes this node's own
tree. It follows that **an empty `engines` is not a statement that the node can be evaluated**:
an evaluation needs the inputs as well as the line, and the line is all this field speaks for.
A consumer asking whether some engine produces a given column walks `reads` and asks the same
question of every node it reaches; a consumer asking which lines have to be rewritten reads
this field as it stands. The three rules below are written for the own-requirement reading and
only hold under it: a closure would put a non-empty `engines` on a `core` node, which the first
of them forbids.

**What the field and the tier beside it may say about each other.** Three rules, and they
hold in both profiles because each turns on nothing but the record itself.

- **A non-empty `engines` requires a `tier` of `engine_native` or `opaque`.** Naming an
  engine *is* a claim that something in the tree reaches into one, which contradicts `core`
  and contradicts a leaf's null tier — and it stops there. It does **not** imply
  `engine_native`, because §11.2's tier is the *weakest* thing reached anywhere in the tree:
  a tree holding both an engine fragment and an identifier nothing can classify is `opaque`
  and still has a true engine to name. A rule reading "engines implies engine-native" would
  leave that producer three moves and all three bad — an empty array, which is the positive
  false claim this section forbids; no field, on a node that holds a fact; or a tier that
  contradicts §11.2.
- **An `engines` present and empty forbids a `tier` of `engine_native`.** The positive
  engine-free claim and the engine-native claim are contradictories, and one record must not
  make both. Stated as the refusal of one tier rather than a list of the permitted ones, so
  that it does not quietly refuse the null tier the next rule allows.
- **A null `tier` requires `engines` absent or empty.** A leaf has nothing to execute, so a
  leaf naming the engines its non-existent text needs is a statement about nothing. Empty
  stays legal there: it is true, if useless, and refusing it would refuse a true record.

**And one rule that turns on the profile, because that is what changes the evidence.** In the
`executable` profile a `computed` node whose `tier` is `core` or `engine_native` **carries**
`engines`. There the tree is in the file and the walk over it is exhaustive: a `core` node
holds no engine fragment by the definition of its tier, so `[]` is true of it, and an
`engine_native` node holds at least one and §12.1 requires each fragment to name its engine —
so the list is a walk of a document the producer already holds rather than a fact it has to
discover. Where the evidence is in the file, the claim is required; where it is not, the field
says nothing, which is what this section built it to do.

The requirement stops at three places, and each is where a walk's silence stops being
evidence.

- **The `audit` profile carries no tree at all** (§3). An `audit` artifact stating
  `tier: "engine_native"` with `engines` absent is a third-party exporter saying: the tier I
  was told, the engines I was not. That is the case this section was written for, and it is
  untouched.
- **An `opaque` node's silence is not evidence.** The leaf that made it opaque is the one
  nothing could read, so a producer whose walk reached no declared fragment has nothing to
  name, and the only claim a requirement could force out of it is the empty array this
  section declines to require. Such a node names an engine where its walk reached one, and
  says nothing where it did not.
- **A compiled rollforward's tree is its identity and not its recipe.** §11.2 states that the
  tier a `rollforward` node earns over the single call it holds is a statement about the
  vocabulary and not about the payload; the state machine's own expressions are no part of
  those bytes, so a walk of them reaches nothing they reach. The rule is on `computed` nodes
  for that reason, and a compilation states its tier with no `engines` beside it.

**What an engine says about an identifier has three answers, and each of the last two carries
its condition.** `engines` above is a node's statement about itself. The other direction — an
engine's statement about the vocabulary, published as a coverage table one row per identifier —
has three statuses and no fourth. **Lowered**: the engine computes it, in whatever it computes
in. **Lowered off the trace**: the engine computes it somewhere its ordinary machinery does not
reach — on the host, from the node's own attributes and operands that arrived with the data or
were written into the formula — and the row states that condition beside the status, because an
identifier alone says nothing about the invocation a model actually wrote. **Refused by name**:
the engine will not compute it, and the row says what it will not compute and why. A table
saying *lowered* of an identifier whose admitted forms the engine refuses would be telling a
reader they can port a model they cannot port, which is the one thing such a table exists to
stop; so the status is a statement about an invocation's form — its operand types and shapes,
its attributes, the checks it owes — and not about the identifier's name. This document states
the three words; which engine claims which is that engine's to publish, and no part of an
artifact.

## 9. Edges

An edge is `{"source": <node id>, "target": <node id>, "relationship": …}`, one per entry of
the target's `reads`. `source` is the node whose value was read; `target` is the node that
read it.

`relationship` is `DIRECT` or `INDIRECT`: whether the value read flows into the result, or
only decided which values did. It is named for what an edge states rather than for the
vocabulary the value is drawn from — this document already spends `type` on §10's type
vocabulary, and an edge states a relationship rather than has a type.

**The narrowing travels beside the edge rather than on it**, in the
`gaspatchio_column_transformation` facet on the **reading node** (§6 puts facets on the
envelope and on a node, and an edge is neither). The narrowing is one of `IDENTITY`,
`TRANSFORMATION`, `AGGREGATION` (with `DIRECT`) or `JOIN`, `GROUP_BY`, `FILTER`, `SORT`,
`WINDOW`, `CONDITIONAL` (with `INDIRECT`). The facet is named in `facets_used` and never in
`facets_required`: a consumer that has never met it reads the same graph, with the same
relationships, and loses only the narrowing. The shape, and where it hangs, are below.

The emission rules:

- the whole formula is one reference to another column (a rename or a plain copy) → `DIRECT` /
  `IDENTITY`;
- an ordinary operand of an arithmetic, comparison or accessor formula → `DIRECT` /
  `TRANSFORMATION`;
- an operand of an accumulating operation (a cumulative product, a prospective value, a
  remaining sum, a linear recurrence in either direction), or of `list.reverse`, whose period
  `t` is the operand's period `T - 1 - t` (11.1.41) → `DIRECT` / `AGGREGATION`;
- a column read **only** inside a conditional's test → `INDIRECT` / `CONDITIONAL`;
- the position operand of `list.get`, including every read nested inside that operand →
  `INDIRECT` / `FILTER`;
- the axis operand of `projection.broadcast_to_periods`, including every read nested inside
  it → `INDIRECT` / `WINDOW`: section 11.1.32 takes only that list's length, so its values
  reach no number, and the read is still recorded because the length is the result's;
- a lookup key, or a join key → `INDIRECT` / `JOIN`;
- a running state read by the compilation that owns it → `DIRECT` / `TRANSFORMATION`.

These contexts nest and a repeated read still produces one edge. An indirect context absorbs
the reads nested inside it: arithmetic used to compute a `list.get` position remains
`INDIRECT` / `FILTER`, and arithmetic used to compute a conditional's test remains
`INDIRECT` / `CONDITIONAL`. Where the same source is also read outside an indirect context and
its value flows into the answer, the direct relationship wins. Where all occurrences are
indirect, the stronger narrowing wins in this order: `JOIN`, then `FILTER`, then
`CONDITIONAL`, then `WINDOW`. This order states how duplicate reads collapse; it does not reorder `reads`,
whose first-mention rule remains section 8's.

**The last rule fires on one node and only there: the `rollforward` node (§16).** A running
state is not a column, so nothing else in a model can read one — a state edge whose target is
anything but a compilation is not a producer being generous, it is a producer saying something
this document does not define. The same node is where a compilation's operand columns are
claimed, and they are `DIRECT` / `AGGREGATION` by the accumulation rule above: a rollforward is
a linear recurrence, so a rate it consumes is in every later period's answer rather than only
in the one being read. Every other node **that reads it** reaches the compilation through
one edge from it, classified by the rules above like any other read: ordinarily `DIRECT` /
`TRANSFORMATION`, and narrowed by a conditional's test or a lookup's keys where the extraction
sits inside one. Most nodes in a rollforward model read no compilation at all — the columns
the data arrived with, the timeline's own columns, every calculation beside the one that
escalated — and this rule says nothing about them.

`FILTER` is emitted for the position operand of `list.get`: that value selects one item within
each policy's list and does not remove a policy row. `WINDOW` is emitted for the axis a
per-policy value is broadcast along: that list supplies the periods the answer is laid over and
none of its values, so `rate.projection.broadcast_to_periods(like=policy_year)` is not a reserve
that moves when a policy year is restated. It is the weakest claim of the four because it says
the least about the number. `GROUP_BY` and `SORT` remain in the vocabulary with no rule above
emitting one. They are there for a producer whose model
shapes rows in those ways, so that a consumer meets a name this document has defined rather
than one it has to guess at.

**The narrowing facet.** It carries one `reads` entry per entry of the reading node's own
`reads`, in that order — which is what makes the read list an index into it, since one edge
is written per entry of that list and no other order is defined.

```json
"facets": {
  "gaspatchio_column_transformation": {
    "_producer": "https://gaspatchio.dev/spec/graph-artifact/v0-preview.3",
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

The inner objects are OpenLineage's own, verbatim: `transformations` is its array name,
`type` and `subtype` are its key names, and the enum spellings and the pairing rule above are
its own. OpenLineage's two further members, `description` and `masking`, are available and
this specification's reference implementation writes neither; a consumer must not read their
absence as a claim. What is **not** verbatim is the outer indexing — OpenLineage keys by
dataset and field, and this document keys by node id, because a node id is what an edge here
names. Borrowing the outer shape as well would be borrowing a shape that does not fit.

A `transformations` array holds one entry per way the read was made. This specification's
reference implementation writes one entry for a read made one way, and for a name read more
than once in one formula it writes the single strongest claim its reads support — except
that a direct read made through two windows (below) writes one entry per window, the
strongest narrowing first, so a consumer that reads only the first entry reads the edge's
own narrowing. A consumer must not read the count as a promise. A node that reads nothing
carries no facet at all, rather than a facet holding an empty array — its empty `reads` has
already said it.

**`offset` — which period the read read.** A narrowing carries one optional member beside
OpenLineage's two, and it is this document's own: `offset`, a whole number saying how far
from the row being computed the value came from. **Negative is a prior period and positive a
later one** — the sign §11's `projection.at_period` already asks an actuary to write. So a
`previous_period` read carries `-1`, a `next_period` read `+1`, and an `at_period` read the
`relative_period` the call stated.

```json
"reads": [
  {"source": "combined_growth_factor@1",
   "transformations": [{"type": "DIRECT", "subtype": "TRANSFORMATION", "offset": -1}]}
]
```

**The value is quoted, not re-derived.** It is the §11 attribute the executable profile's
operation tree serialises — `relative_period` for `projection.at_period`, and for
`projection.previous_period` and `projection.next_period` the distance §11.1.19 fixes on the
identifier itself, which is why neither carries an attribute to quote. A producer must not
recover it by reading an expression's lowered text: that text is one engine's rendering, and
an audit profile that needed it would not be an audit profile.

**Present only where there is a period to state.** A read of the period being computed — which
is nearly every read in any model — carries **no `offset` at all**: never `0`, never `null`.
The absence is the statement, and a second spelling of it would leave a consumer with two
shapes to recognise for one fact. Three further reads carry none. A read whose narrowing is
not `TRANSFORMATION` carries none, because an offset says which period a *value* came from and
a lookup key, a conditional's test or an operand folded across the whole run is not a value
narrowed by a distance — an accumulating read (`projection.cumulative_survival`,
`projection.accumulate`) reads a run of periods, is an `AGGREGATION` already, and states that
run in `periods` below. A name read at two different periods in one formula reaches the edge
as one edge, and carries none, because neither distance is the read's. And a
`relative_period` that is not a whole number is not a distance to quote.

Why it matters: "this month's reserve reads last month's — show me which cell" is the question
a same-period answer gets wrong rather than leaves open, and a wrong proof is worse than an
absent one. The fill value a shift takes at the boundary is read at the period being computed
and carries no offset: it is what stands where the shift runs off the projection, not a value
from another period.

**`periods` and `position` — which periods an aggregation, or a selection, read.** An offset
says which period a value came from; an operand folded across a run comes from many, and a
cumulative sum, a remaining sum and a total all read `DIRECT` / `AGGREGATION` while reading
three different runs. So a narrowing carries two more members of this document's own, beside
`offset`:

- `periods: {"from": a, "to": b}` on an `AGGREGATION` read: the run of the operand that one
  period of the answer reads. Each bound is a whole number of periods from the period being
  computed — negative before it, positive after it, the sign `offset` uses — or `"first"` or
  `"last"`, the first and last period of that policy's own run. A cumulative sum's read is
  `{"from": "first", "to": 0}`; a remaining sum's `{"from": 0, "to": "last"}`; a total's
  `{"from": "first", "to": "last"}`.
- `position: k` on a direct read made through a literal `list.get` (11.1.22): the stored
  position the call names, quoted as written, so `0` is the first period and `-1` the last.
  It is a position in the list and not a distance from the period being computed, which is
  why it is a member of its own; a position held in a column differs by policy and states
  none.

```json
"reads": [
  {"source": "deaths@1",
   "transformations": [{"type": "DIRECT", "subtype": "AGGREGATION",
                        "periods": {"from": "first", "to": 0}}]}
]
```

**The window is quoted, not re-derived**, by the rule `offset` follows: it is the identifier's
own, under the attributes §11 states for it, and a producer must not recover it from an
expression's lowered text. The table is this:

| Read | Stated |
|---|---|
| `cum_sum`, `cum_prod` (11.1.9) | `{first, 0}`; under `reverse: true`, `{0, last}` |
| `projection.cumulative_survival` (11.1.19), `start_at` null | `{first, 0}` |
| `projection.cumulative_survival`, `start_at` stated | `{first, -1}` |
| `projection.accumulate` (11.1.20), multiplier and addend | `{first, 0}`; under `reverse: true`, `{0, last}` |
| `rollforward` (§16), every column a compilation reads | `{first, 0}` |
| `projection.remaining_sum` (11.1.20) | `{0, last}` |
| `projection.prospective_value` (11.1.21), cashflows, and a list rate under `discount_kind: "rate"` | `{0, last}` |
| `sum`, `mean`, `min`, `max` (11.1.14–11.1.17), and `excel.irr`'s cashflows (11.1.36) | `{first, last}` |
| `list.reverse` (11.1.41) | `{first, last}` |
| `finance.discount_factor` (11.1.30) under `method: "forward"`, the rate | `{first, -1}` |
| `list.get(x, k)` (11.1.22), `k` a whole-number literal | `position: k` |

Some reads state no window, and their absence is the statement that there is none to quote: a
column holding one value per policy, which has no periods — `projection.accumulate`'s opening
value, a scalar rate, `excel.irr`'s guess; the period operand a forward discount factor records
and never reads; a prospective value's discount under `discount_kind: "factor"`, a form 11.1.21
does not state; and every read of the period being computed, which says so by carrying
neither member, exactly as it carries no `offset`. A window is never written as `null` and
never on an `INDIRECT` read: a lookup key, a conditional's test, a selection's position and a
broadcast's axis read no value into the answer for a window to bound.

**A read through two operations states the window the two compose to**, where the members can
write it exactly: a cumulative sum of last period's deaths, `cum_sum` of `previous_period`,
reads `{first, -1}`; the last period of a cumulative sum, `list.get(cum_sum(x), -1)`, reads
`{first, last}`; a literal position inside a fold reads that one `position` at every period. A
composition they cannot write — a fold of a value read one period ahead, a position taken off a
shifted list — states no window rather than an approximate one.

**A window is a bound.** An operand moved outside it moves no period of the answer, on any
engine; that is the stated contract, and the conformance kit's perturbation vectors (§11.3)
hold every engine to it. It is not a promise that every period inside it moves the answer. Two
reads are wider than what they read because the members cannot write it: `list.reverse`'s
period `t` reads the operand's period `T_i - 1 - t`, which is no fixed distance and no fixed
end; and a prospective value's beginning-of-period form never discounts by the last period's
rate, which `{0, last}` still includes.

**A name read through two windows in one formula writes one entry per window**, `periods` or
`position` on each, in the order the ladder above names them and then the order the formula
first made them. `cum_sum(x) - x` writes `TRANSFORMATION` and then `AGGREGATION` with
`{first, 0}`, where a single strongest claim would have told a reviewer the cumulative read was
a read of this period. `offset` stays on the entry that states no window, under the rule above.

Why it matters: "does this reserve read the same periods as the workbook's column?" is the
timing half of reconciling a model to a workbook, and without these members the only way to
answer it from the record was to parse the formula text — which five of seven reconciliations
did, with regular expressions that a misread call turns into a wrong verdict.

**Promoting the narrowing back into the core edge is additive**, and stays so deliberately.
If it is later wanted there, `subtype` returns as an added required edge field, which §14's
additive rule permits without a second identifier move; the facet is then the older spelling
and is retired with a change-log line.

Why it matters: "what does this reserve depend on?" and "what selected the row?" are
different questions, and an impact cone drawn through a key edge is a wrong answer to the
first. That question is answered by the two-value split and by nothing narrower, which is
why the split is on the edge and the narrowing is not: four edges in five carry one
narrowing, and none of them changes the answer.

## 10. The type vocabulary

`dtype` carries a type from a closed list: `bool`, `i64`, `f64`, `str`, `date`, `datetime`,
and `list[T]` where `T` is itself one of these. **`list[T]` nests to three levels in this
preview** — `list[list[list[f64]]]` is in the vocabulary and a fourth level is refused — and
the schema enforces the limit. A producer that meets a type it cannot map **must refuse to
produce the artifact**, naming the column and the type it could not map. A guess here is not
a smaller failure than a refusal; it is the same failure made quietly, in a document whose
whole claim is that it can be checked.

**This is the type of a column, and it is not the shape of a literal.** `list[T]` nesting
three deep says what a column may hold; a *sequence literal* inside a formula — a band's
breakpoints, a set of product codes — is flat, holds scalars only, and a member that is
itself a sequence is refused (section 12.1). The two look like one rule and are two: one
describes data the model carries, the other describes what an author can write into a line.

The value rules come in two parts. **On the wire**, a `date` value is an ISO-8601 calendar
date string (`"2025-01-01"`, JSON Schema `format: date`) and a `datetime` value an ISO-8601
timestamp string (`format: date-time`) — wherever a value of that type appears: a sample, a
trace, an assumption payload, a column of a content-hashed frame. **For execution**, the
typing table states how a consumer with no date type of its own carries them.

**A date is among the scalar values an operation tree can hold.** A date literal is
written structurally as `{"op": "lit", "date": "2025-01-01"}`, with exactly one of
`value`, `values` and `date` present. Section 12.1 encodes it under scalar tag `0x16`
as the zigzag varint count of whole days from 1970-01-01 on the proleptic Gregorian
calendar. A date may also be a call attribute where an operation's signature declares
one, although no signature in this preview currently does; `projection_set`'s
`valuation_date` remains ISO-date text by its signature. A date is never a member of a
sequence literal, and `datetime` remains a column/payload type rather than a tree
literal: this preview mints no tree scalar tag `0x17`.

| Type | On the wire | For execution |
|---|---|---|
| `bool` | JSON boolean | a boolean |
| `i64` | JSON number | a signed 64-bit integer |
| `f64` | JSON number | a double-precision float |
| `str` | JSON string | a string |
| `date` | ISO-8601 calendar date string, `format: date` | a signed 32-bit integer count of days since 1970-01-01 |
| `datetime` | ISO-8601 timestamp string, `format: date-time` | a signed 64-bit integer count of microseconds since 1970-01-01T00:00:00Z; a column also carries its zone, a zone-naive one read as UTC, and the content grammar hashes the zone and the instant to the nanosecond (§12.3) |
| `list[T]` | JSON array of `T` | a sequence of `T` |

The wire form is for the reader; the typing table is for the engine.

The reference producer reads an integer narrower than 64 bits as `i64` where it enters the
frame — a book column, a column a join brings, and the `month`, `step` and `num_proj_months` a
projection stamps — so it computes in the type the record names. **It reads a float narrower
than 64 bits — a `Float16` or `Float32` column, or a list of one — as `f64` at the same doors**,
for the same reason: kept in its four bytes, `qx.list.sum()` over `[0.001, 0.0015, 0.002]` was
carried in single precision (0.0044999998062849045) while the record named `f64` and a reader
answered 0.00450000015553087. The widening is exact, so the book's digest and every fingerprint
are unchanged. **It reads an engine's fixed-point decimal — a `Decimal` column, or a list of
one, held to a fixed number of places, which this vocabulary does not name — as the number it
denotes at every door a value enters by**: a book column, a column a join brings, a table's
answer column, a column of values handed in whole and a decimal written into a formula. One with
places is read as the `f64` nearest each value, so `1000.00 / 12` answers the quotient's double
and not the decimal's two places, and a value past fifteen or sixteen significant figures
loses the digits a double does not hold (9007199254740993 is read as 9007199254740992); one with
no places is read as the whole number it is, by the rule below for a width wider than `i64`. No
operation meets a fixed-point decimal, the record names the column `f64` or `i64`, and the book's
digest reads the value the column entered as, as section 7.5 reads a category as its text.
**A width wider than `i64` —
`UInt64`, `Int128` or `UInt128`, or a list of one — is read by its values, by one rule at both
doors.** A column whose every value lies in `[-2^63, 2^63 - 1]` is read as `i64`, as a narrow
one is widened. A column holding any value outside that range keeps the width it arrived in:
`to_text` writes such a value by its digits and `to_integer` refuses it (11.1.39, 11.1.23), and
arithmetic on the column (11.1.25) — any operator, either side, per policy or per period — and
every other read that computes in its width, answers in its type or carries it into a double —
a sum, a running sum or product, a remaining sum (11.1.9, 11.1.14, 11.1.20), an absolute value,
significant figures and the maths calls that carry it into a double (11.1.12), a least or
greatest value, a bound, a rounding, a sign, a fill, a substitution (11.1.6), a conditional's
branch beside a narrower one (11.1.28), placing it in a band (11.1.4), a period's value or a
shift, and a rollforward's operands (16.1) — is refused by name rather than wrapped, the refusal naming
the column, `to_text()` for an identifier, and a narrower type of the author's choosing for a
quantity. A conversion keeps the rule its own entry states, a test of presence reads the value
as it stands, and a comparison or a membership test is outside the portable domain and
compared exactly (11.1.26). A producer handed the
book as a plan, with no values in hand where the frame is built, keeps such a column's width
there and applies the same rule when the plan runs: every read named above takes the column as
`i64` where its values fit, and refuses in the producer's own sentence where one does not, so
the two doors answer one type; and a column that arrived with the book and was not written over
is read by the same rule when the run's values are collected, so the results the two doors hand
back carry one type. A record written from such a plan names a column that arrived with the
book on its values too, read off the book as it arrived — as the book's digest is — so the two
doors write one document, and a value past `i64` in it is refused naming the value, from either
door; a calculated column of such a width, whose values the producer does not hold, is refused
on its width. Only the plan's own schema, before any value is read, still shows the width
the column arrived in. A run that cuts
the book into batches judges such a column over the book, not over each batch, so every batch
reads it in one width. A consumer handed the book reads it the same way at its own door — an
`Int8` through `UInt32` column, or a list of one, is the `i64` the record names, a `Float16` or
`Float32` one the `f64`, and so is a wider column whose values fit — so the two take one book; a consumer that carries every integer
as an `i64` refuses a column holding a value past that range, naming the value, rather than
wrapping it.

**A literal inside an operation tree is typed by its token and not by this table.** The table
above says what a value of a *declared* type looks like: a column says it is `i64`, so its
values are JSON numbers read as integers. A literal in an `expr` declares nothing — there is
no `dtype` beside it — and section 12.1 nevertheless has to choose between the whole-number
tag and the decimal one. **The token settles it**: a JSON number written without a decimal
point or an exponent is a whole number, one written with either is a decimal, and a producer
therefore writes `1` and `1.0` to mean two different things. Section 12.1 states both halves
of that rule, including the one a consumer gets wrong: read the tag off the token as written,
never off a value some parser has already turned into a single numeric type.

A whole-number literal, and a whole-number call attribute, lies in `[-2^63, 2^63 - 1]`: section
12.1 writes one as an `i64`, and no tag of this grammar carries a whole number outside that range.
A producer refuses such a literal where it is written, naming it — in a formula, or assigned
as a column on its own — except as the other operand of a comparison or a membership test
whose receiver is a column still wider than `i64`, which the producer compares exactly in that
column's width (11.1.26) and which no document carries, and a consumer refuses a document
carrying one, naming the line; an identifier past that range is compared through `to_text`
(11.1.39), or, while its column keeps the width it arrived in, directly (11.1.26), and a
quantity is written as a decimal. **A whole-number literal is an `i64`
operand wherever it stands**, and a column it alone types — a constant assigned as a column, a
conditional whose branches are whole numbers, a fill — is the `i64` the record names: a producer
computing in an engine whose integer literal carries no width of its own states each one as an
`i64` before the engine sees it, rather than let the engine settle on a narrower width that wraps
(`when(x > 2).then(70000).otherwise(0) * 70000` is 4,900,000,000, not 605,032,704). Beside a decimal
it widens to the decimal, as 11.1.25 states.

**A non-finite `f64` travels as a string naming itself** — `"NaN"`, `"Infinity"` or
`"-Infinity"` — wherever a value appears. JSON has no token for one: the bare words a
lenient writer emits are not in the grammar, and a strict parser refuses the whole document
rather than the one value, so a producer that emits them has written a file that reads as
valid until somebody tries to parse it. Null is not available to stand in, because null
already means *no value here* and a NaN is a value the column holds — section 12.3 hashes
the two differently, and collapsing them would move a digest. The column's declared `dtype`
stays `f64`, and that is what makes the string unambiguous: a `str` column holding the text
`"NaN"` holds that text, an `f64` column holding it holds the number. A consumer reads it
back to the float before doing anything numeric with it, section 13's re-hash included.

**`dtype` is also what says whether a column holds a selection rather than a quantity, and
the record carries no second field restating it.** A column whose `dtype` is `bool` or
`list[bool]` holds a selection — **and a selection may also arrive as a numeric 0/1 mask,
which this vocabulary cannot tell from a quantity.** The second clause is not decoration.
Every bare comparison a producer writes down as a column of its own can land as `f64`: the
reference implementation's `af.is_post_reform = af.entry_date > date(2020, 1, 1)` is `f64`,
and so is `af.plain_bool = af.sum_assured > 1.5`. A reader who takes `bool` to mean selection
and infers `f64` to mean quantity is right about the first half and wrong about every such
column. So `bool` implies a selection; `f64` implies nothing either way.

Integer widths collapse to `i64` and float widths to `f64`, so neither a producer nor a
consumer may rely on this field to recover storage width. The record does not carry it.
A width wider than `i64` — an unsigned 64-bit column, a 128-bit column — is judged on its
values and not on its width: a producer holding them writes `i64` where every value is
inside the signed 64-bit range and refuses, naming the value, where one is not, and a
producer with no values in reach refuses the width itself rather than guessing at it.

A node's `dtype` may also carry the string `unknown`. **`unknown` is not a type.** It
records that the producer never determined one — which legitimately happens on a column's
superseded definitions and on columns defined and then dropped, where the value is history
rather than the answer. A producer must never write `unknown` for a type it met and could
not map; that is a refusal, as above. A validator flags `unknown` on any node that is in
the final schema: the model's answers carry real types, only its history may go untyped.
(`shape` carries an `unknown` member under the same rule.)

**An input leaf for a column the model renamed or dropped is typed, and carries no sample.**
The graph names such a leaf for the field the data arrived under — `Sum Assured`, with
`sum_assured` reading it — and the finished frame holds no column under that name to read
either a type or a value from. A producer keeps the schema its data arrived with, so the type
is stated: this is the case where the **type** is known and the **values** are not, and the
leaf's `value_sample` is null for that second reason alone rather than because nothing about
the column could be determined. So is the leaf of an arriving column whose name a later line
took over — written over in place, or reused after a rename or a drop: the leaf states the type
the field arrived with, never the type of what holds its name now, and a wide integer is named
on the values read off the book. Such a leaf is `unknown` only where the type it arrived under
is one this vocabulary has no name for — a `Categorical` carried into the model by `to_text`
and then dropped, say. That is the one place `unknown` is permitted for a type the producer
did meet and could not map, and it is narrow on purpose: the refusal above exists to stop a
document stating a type it cannot name for a column the model **holds**, and taking a whole
export down over a column the model has already carried into the vocabulary and let go of
would be refusing history. **Such a column still counts towards the book** (section 7.5): the
book's digest names no type, and it reads a category as the text the category stands for
(section 12.3), so a model that reads a categorical column and drops it rests on those values
and its book says so.

The vocabulary deliberately has no time-delta type. A producer that meets one — an engine's
duration column, typically from subtracting two dates — must refuse, and the refusal names
the cast that carries the value as `i64` in an explicit unit, which is also what makes the
unit visible to a reader. If a time-delta type is ever added it will be added additively
under the name `timedelta`, never `duration` — in this document's domain that word already
means a policy's age or a rate sensitivity, and a type must not collide with it. **A call that
reads a number out of one is refused where it is written**, per policy and per period, naming
the same cast: the reference producer refuses `sign`, `sqrt`, `cbrt`, `exp`, `log`, `log10`,
`log1p`, `norm_cdf`, `round_sig_figs`, `round`, `floor`, `ceil`, `cum_prod` and
`cumulative_survival` over a duration, each of which its engine either refused in its own words
or answered by reading the duration as a count in the engine's own storage unit. `abs`, `sum`,
`cum_sum`, `remaining_sum`, `mean`, `min` and `max` of durations answer a duration on the
frame, as a duration scaled by a number does (section 11.1.25), and the export refuses it as
above, so no document carries one and no consumer reads one.

**All-null inputs need an explicit intended type.** A live scalar `Null` or
`list[Null]` column is a determined but unmapped type, including an unused
passenger or an empty list whose element type was never declared. It refuses
graph construction and both export profiles. Do not infer f64, discard the
column, or call its known type `unknown`. Construct it with an explicit dtype,
for example `pl.Series("passenger", [None], dtype=pl.Float64)` or
`pl.Series("history", [[]], dtype=pl.List(pl.Float64))`. A null scalar, null
outer list or null element with a supported declared type remains nullable data.
This rule adds no neutral null type and no implicit cast.

**Raw Struct values are outside portable output in this preview.** Section
16.3 states the rollforward escape-hatch disposition and named alternatives.

This section states the type vocabulary and the two forms a value takes. An operation's
explicit domain, null behavior and refusal rules in §11 or §16 take precedence for the
forms they name. Behavior those clauses do not specify remains engine-defined; this type
vocabulary does not supply a portable default.

## 11. Operation identifiers

An operation identifier is a dotted name. The prefix before the first dot is the domain:
`projection.cumulative_survival` is in the `projection` domain, `excel.yearfrac` in the
`excel` domain. An identifier with no dot is in the unnamed domain, which holds the binary
operators and the forty operations that take no domain.

**The core vocabulary is this specification's own: the unnamed domain together with the
domains this document names** — `curve`, `date`, `excel`, `finance`, `list`, `mortality`,
`projection`, `projection_frame`, `rollforward`, `schedule`, `str` — and its members are
listed in section 11.1. A domain is a grouping of related operations, not a statement
about how well they are accounted for; that is the tier (section 11.2), which is stated per
identifier and is independent of the domain it sits in. **Any domain this document does not
name is an extension domain**, and an artifact may carry one without a schema change: a
domain is a name rather than a reserved slot, and nothing about adding one obliges a consumer
that does not know it to fail. A consumer can answer "is this operation in the specification's
vocabulary?" with a lookup in section 11.1 and nothing else.

`injected` — a whole column of values handed to the model at a known line — **is not an
operation and is not in this vocabulary**. It is a node with `kind: "input"` and
`provenance: "injected"`, which is what it is. Putting it here would file a thing that computes
nothing in a vocabulary of things that compute.

The binary-operator vocabulary is closed: `add`, `sub`, `mul`, `div`, `floordiv`, `mod`,
`pow`, `lt`, `le`, `gt`, `ge`, `eq`, `ne`, `and`, `or`. It grows only additively, and every
addition takes a change-log entry (section 14) recording what was added and when.

### 11.1 The core vocabulary

Every identifier this specification owns, with the tier it carries in this preview. The
table is the whole vocabulary: an identifier not in it is either in an extension domain or
is not an operation.

| Identifier | Tier |
|---|---|
| `add` | `core` |
| `sub` | `core` |
| `mul` | `core` |
| `div` | `core` |
| `floordiv` | `core` |
| `mod` | `core` |
| `pow` | `core` |
| `lt` | `core` |
| `le` | `core` |
| `gt` | `core` |
| `ge` | `core` |
| `eq` | `core` |
| `ne` | `core` |
| `and` | `core` |
| `or` | `core` |
| `abs` | `core` |
| `cbrt` | `core` |
| `ceil` | `core` |
| `clip` | `core` |
| `cum_prod` | `core` |
| `cum_sum` | `core` |
| `curve.discount_factor` | `core` |
| `curve.spot_rate` | `core` |
| `cut` | `core` |
| `date.date_ranges` | `core` |
| `date.months_between` | `core` |
| `date.offset_by` | `core` |
| `date.to_period` | `core` |
| `excel.days` | `core` |
| `excel.edate` | `core` |
| `excel.eomonth` | `core` |
| `excel.from_excel_serial` | `core` |
| `excel.irr` | `core` |
| `excel.pv` | `core` |
| `excel.round` | `core` |
| `excel.yearfrac` | `core` |
| `exp` | `core` |
| `fill_nan` | `core` |
| `fill_null` | `core` |
| `finance.compound` | `core` |
| `finance.discount` | `core` |
| `finance.discount_factor` | `core` |
| `finance.present_value` | `core` |
| `finance.to_monthly` | `core` |
| `floor` | `core` |
| `is_finite` | `core` |
| `is_in` | `core` |
| `is_infinite` | `core` |
| `is_nan` | `core` |
| `is_not_nan` | `core` |
| `is_not_null` | `core` |
| `is_null` | `core` |
| `join` | `core` |
| `list.get` | `core` |
| `list.reverse` | `core` |
| `log` | `core` |
| `log10` | `core` |
| `log1p` | `core` |
| `lookup` | `core` |
| `max` | `core` |
| `mean` | `core` |
| `min` | `core` |
| `mortality.at` | `core` |
| `norm_cdf` | `core` |
| `not_` | `core` |
| `projection.accumulate` | `core` |
| `projection.at_period` | `core` |
| `projection.broadcast_to_periods` | `core` |
| `projection.cumulative_survival` | `core` |
| `projection.next_period` | `core` |
| `projection.previous_period` | `core` |
| `projection.prospective_value` | `core` |
| `projection.remaining_sum` | `core` |
| `projection.with_period` | `core` |
| `projection_frame.anniversary_mask` | `core` |
| `projection_frame.period_dates` | `core` |
| `projection_frame.t_years` | `core` |
| `projection_frame.year_fractions` | `core` |
| `projection_set` | `core` |
| `replace` | `core` |
| `rollforward` | `core` |
| `rollforward.increment` | `core` |
| `rollforward.state` | `core` |
| `rollforward.struct` | `core` |
| `round` | `core` |
| `round_sig_figs` | `core` |
| `schedule.anniversary_mask` | `core` |
| `schedule.contract_boundary` | `core` |
| `schedule.is_in_force` | `core` |
| `schedule.per_policy_period_count` | `core` |
| `schedule.per_policy_period_dates` | `core` |
| `schedule.period_dates` | `core` |
| `schedule.year_fractions` | `core` |
| `sign` | `core` |
| `sqrt` | `core` |
| `str.to_date` | `core` |
| `sum` | `core` |
| `to_float` | `core` |
| `to_integer` | `core` |
| `to_list` | `core` |
| `to_text` | `core` |

**The tier is not the whole of what an identifier needs to be reproducible, and 11.1.11 is
the rest of it.** A tier says how well this specification can account for an operation; it
says nothing about how a call to that operation is *shaped* — how many operands it takes, in
what order, which of its settings are attributes, and what each attribute is called. Two
producers agreeing on every word above and disagreeing about whether an offset is an operand
or an attribute publish different digests for the same model, which is exactly the false
positive section 12 exists to prevent. **11.1.11 is the signature of every identifier in the
table above**, and it is normative for that reason.

**In this preview every identifier in the vocabulary is `core`.** `engine_native` and
`opaque` are properties a node acquires from its *tree* — an escape-hatch fragment written in
an engine's own expression language, or an identifier this table does not list — and never
from this table. An identifier without a value clause must not be assumed to have
semantics this document has defined. **Ninety-nine are stated here**, in §§11.1.1–11.1.10,
§§11.1.12–11.1.41 and §§16.1–16.2, and a consumer may rely on those ninety-nine only
within each section's stated domain.

The first two are `projection_set` and `join`, and they were the last two operations a real
model reached that this table did not list. Both compute a column no formula in the model
derives — one lays the time axis, the other brings a column in from a second table — and
until this revision an artifact of an ordinary projected model reported them `opaque`,
which carried through the reads of nearly every node downstream of them. Listing them
without saying what they mean would have moved a tier and told a reader nothing more, so
the entry and the semantics land together: a second implementation can reproduce these
columns from what the record carries, and where it cannot, 11.1.1 and 11.1.2 say so by
name.

The other four arrive the other way round: not columns a door minted, but ordinary lines an
actuary writes. `clip` holds a duration at a table's last row or a credited rate between a
floor and a cap; `cut`, `is_in` and `replace` are the three ways a model sorts values into
named groups — an age band, a set of product codes sharing a basis, a table's own spelling
of a rider mapped onto the model's. Each reached an artifact as an engine fragment for want
of an entry here, which is the same defect the tier is built to make visible and a worse one
to leave standing, because the calculations those fragments hid are a sentence each.
11.1.3 to 11.1.6 are those sentences, and 11.1.7 is a fifth: `str.to_date`, the first line
of a projection whose model points carry their entry dates as text, which is the ordinary
shape of an administration-system extract rather than the awkward one.

The last five arrive the same way and are the plainest lines of all. `round`, `floor` and
`ceil` move a value to a whole step — a premium billed in pennies, the completed years a
duration has run — and 11.1.8 is their sentence. `cum_prod` and `cum_sum` fold along a
projection's period axis, and 11.1.9 is theirs: they are the closed forms this framework
reaches for instead of a state machine, so a model that never escalates still has an
account of its fund growth and its premium taken to date. Every one of the five was an
engine fragment until this revision, and a survival probability recorded as engine text
takes every column downstream of it with it.

The thirteenth is `mortality.at`, and it arrives for a third reason: not a column a door
minted, and not a line whose calculation was hiding in a fragment, but a *convention* that
reached the record nowhere at all. A select and ultimate basis holds a duration at its
select period before it reads, and until this revision that clamp reached an artifact as an
engine fragment while the structure, the select period and the age basis reached it not at
all — so two models reading one grid, one on rates built age last birthday and one age
nearest birthday, were the same document with the same digest. 11.1.10 states what the
three structures mean and what the clamp does; the structure, the select period and the age
basis are attributes, because each is one flat value and a consumer that has them can apply
the convention again.

The sixteen after it are the plainest lines in the vocabulary, and they arrive for the
second of those three reasons. Nine are the maths a projection is written with — `abs`,
`sign`, `sqrt`, `cbrt`, `exp`, `log`, `log10`, `log1p` and `round_sig_figs` — and seven are
what a model says about a value that is not there: `fill_null` and the six tests `is_null`,
`is_not_null`, `is_nan`, `is_not_nan`, `is_finite` and `is_infinite`. Each answers one value at a time, each was an
engine fragment until this revision for want of an entry here, and a force of mortality
written as a logarithm took every reserve downstream of it out of the portable subset with
it. 11.1.12 and 11.1.13 are their sentences, and each carries one rule about what its family
is *not*: a transcendental function is held to a stated tolerance rather than to a bitwise
contract nobody can keep, and a null and a NaN are two different absences rather than one
with a flag. `fill_nan`, the fill for the second of those absences, joined the family later
for the same reason: a NaN a lookup answered for a blank cell was zeroed in an engine
fragment, and that fragment took the table's identity out of the record with it.

A tenth plain function, `norm_cdf`, joined the first family later and for the same reason,
seen from the other side. A guarantee priced as an option — a GMDB valued as a
Black-Scholes put — needs N(d1) and N(d2), and with no entry here a model had nothing to
write them with: the engine has no error function to compose from, so the one model in
evidence hand-built a series and a continued fraction of some 190 operations inside an
extension, which reached the record as engine text and took the valuation with it. 11.1.12
states Φ beside `exp` and `log`, under their tolerance.

Four reductions are `sum`, `mean`, `min` and `max`, and they arrive for a reason none of the
others did: not an entry this table was missing, but a **shape** this document could not
state. 11.1.9 said so in its own words — the reduction of a per-period column to one number
"has a different shape from its operand, and this document has not yet said how an operation
states that" — so a present value, the plainest closed form in an actuarial model and the
number a supervisory reader asks for by name, reached the record as engine text with the
multiplication that built it hidden inside the fragment. 11.1.14 to 11.1.17 are their
sentences, and the shape change is stated in each, in prose, beside the operation it is a
fact about rather than in a field on the node record that a node's own two shape statements
would already contradict.

Seven projection operations now have the numerical forms stated below:
`projection.cumulative_survival`, the three period shifts, `projection.accumulate`,
`projection.remaining_sum` and `projection.prospective_value`. 11.1.18 states the shared
policy/period shape rule those operations rely on; 11.1.19 to 11.1.21 state their finite
numeric forms. Each entry names the forms it does not yet state. Vocabulary membership still
does not imply semantics for an excluded form.

**What identifies a banding is the values written into it**, and that is why these three
carry their breakpoints, labels, membership sets and substitutions as sequence literals in
the tree (section 12.1) rather than as attributes. An attribute is one flat typed value and
could hold none of them; an engine's rendering of a long argument list abbreviates its middle
away, so two bands differing only there were one document. The values are operands, so they
are in the node's digest, and a band that moved between two quarters is a change the identity
can see.

#### 11.1.1 `projection_set`

`projection_set` is the declaration of a model's projection time axis, standing as the
node behind every column that declaration mints. It is not a formula the model wrote: the
node's attributes carry the axis configuration, and the columns are functions of that
configuration, of the columns the node reads, and — for the horizons named at the end of
this section — of model-point values the record does not carry.

**The axis is a sequence of boundary dates.** An axis of `n` periods has `n + 1`
boundaries: boundary 0 is the start, boundary `t + 1` closes the period boundary `t`
opened, and the last boundary is the end. Every count this operation states is a count of
boundaries.

**The configuration** is written in the attributes, and which attributes are present says
which of four forms declared the axis. `frequency` is on all four, and on the first three
names one of six cadences — monthly, quarterly, semi-annual, annual, weekly or daily; on the
fourth, the fixed step, it is null, because that axis has no calendar cadence. **The token is the
producing engine's own spelling of that cadence, not a vocabulary this document fixes**:
an engine accepting both an English name and a period shorthand records whichever the
caller wrote, so `monthly` and `1M` are two spellings of one axis and both reach the wire
— and the `schedule=` form carries the shorthand wherever the schedule object holds its
cadence that way. A consumer matching one spelling alone misses the other.

- **Policy-anchored** — `valuation_date` (ISO date), `until`, `until_value`. The axis runs
  from the valuation date to a horizon that `until` names and `until_value` carries:
  `term_months` and `term_years` take a whole term, `fixed_date` an ISO date,
  and `maximum_age` an attained age measured against each policy's issue age. A term
  horizon and a `maximum_age` horizon require a month-aligned cadence — a term in months over a weekly or daily cadence makes
  the period count ambiguous, and a number of years from an issue age to an attained age is
  not a whole number of weeks or days — and a producer refuses either rather than picking a
  count. Where `until_value` is a
  column name rather than a number, or the horizon is `maximum_age`, the horizon is per-policy.
  A `maximum_age` declaration also states `issue_age_column`, the column each policy's issue
  age is read from, which the node reads wherever the axis is per-policy.
- **Synthetic** — `start` (ISO date) and `n_periods` (integer), and no horizon at all: a
  grid of exactly that many periods from that date. `until`, `until_value` and
  `valuation_date` are null, because this form has no such argument.
- **From a schedule** — `frequency`, `until` (the schedule's own horizon kind, and only
  where the schedule is per-policy), `start` where the schedule carries a start date, and
  `schedule_source_sha`, the schedule object's own content identity. `until_value` and
  `valuation_date` are null here for the same reason: this form passed neither.
- **Fixed step** — `n_periods` (integer) and exactly one of `step_years`, the length of one
  step in years as the model wrote it (a decimal: `0.1` is the double nearest a tenth), or
  `steps_per_year`, the whole number of steps one year makes (an integer of one or more).
  `frequency`, `until`, `until_value` and `valuation_date` are null, and there is no
  `start`: **the axis has no calendar under it**. It is `n_periods` steps of a fixed number
  of years — a teaching workbook's time axis, or a numerical solution of Thiele's or
  Kolmogorov's equations — and its boundaries are not dates. A producer records this form
  the same way whether the model passed the two numbers to the declaration itself or handed
  it a fixed-step schedule object (section 15's `fixed_step` recipe), because the two
  numbers state the whole axis and no digest stands in for anything they do not. **The two
  spellings are two axes**: `step_years` of a twelfth and `steps_per_year` of 12 time their
  boundaries differently in the last bits (below), and a producer never converts one into the
  other.

**A per-policy horizon is either jagged or collapsed, and the record says which.** Jagged
— each policy carrying only its own boundaries — applies to a term horizon named by a
column and to a `maximum_age` horizon, whether the age is a whole number, a column or an
expression, and is what a producer does there by default. A
`maximum_age` axis runs each policy `until_value − issue_age` whole years: the age as
written, less the issue age read from the column `issue_age_column` names, the difference
truncated toward zero. Every other case — `maximum_age` included, where a producer is asked
for one shared grid — lays one shared grid sized from the
policy needing the most periods, which on `maximum_age` is the youngest life. **Such a grid
is a read across rows**: its length is read from the rows the frame holds, so a producer
lays it only where the frame is the whole book, and refuses it where a run cuts the book
into more than one batch or carries a scenario axis, exactly as it refuses any other read
across rows (§13.2). **What the
node reads is what tells the two apart**: a shared grid names nothing in `reads`, while a
per-policy axis reads each policy's own horizon or anchor column — on `maximum_age`, the
issue-age column, after the age's own column where the age is one — and names it there.
**An empty `reads` is not a statement that no data was consulted.** A shared grid is laid
over the model points as much as a jagged one is: where a `maximum_age` horizon or a horizon
named by a column is collapsed onto one grid, its length is a function of the portfolio —
the youngest issue age, the longest term — taken from a column `reads` does not list.

**The boundary count follows from the attributes wherever the horizon is one they carry.**
Write `p` for the number of periods a year the cadence has — 12, 4, 2, 1, 52 and 365 for
monthly, quarterly, semi-annual, annual, weekly and daily — and `m` for the months in one
period, which the four month-aligned cadences have and the other two have not (section
11.1.37). Write `T` for the number of periods. Then:

- **`term_months` of `k` months** gives `T = k // m`, a whole-number floor toward negative
  infinity and not a rounding. At a weekly or daily cadence there is no `m`, and a producer
  takes `T = k` — a month count read as a period count, which it records as a fallback
  rather than as a rule; such an axis is outside what this entry states a count for.
- **`term_years` of `k` years** gives `T = k × p`, at every cadence.
- **`maximum_age` of age `A`**, where the node reads the column `issue_age_column` names,
  gives `T_i = max(0, trunc(A_i − x_i) × p)`. Here `x_i` is that policy's issue age, and `A_i`
  is the whole number `until_value` states, or that policy's value of the column `until_value`
  names and the node reads; `trunc` drops a fraction toward zero. An age the record carries
  only as an expression's rendering is outside what this entry states a count for, and so is
  a policy whose issue age is past its `A_i`, as a negative term is (11.1.37).
- **`fixed_date`** gives `T = months_between(valuation_date, until_value) // m`: the
  calendar months between the two dates with the days ignored, as 11.1.33 counts them, then
  the same floor.
- **The synthetic form** states `T` outright as `n_periods`.
- **The fixed-step form** states `T` outright as `n_periods`, and has no horizon form: no
  `until` of any kind is admitted beside a step.

The axis then has **`T + 1` boundaries** — which is what `num_proj_months` carries — and
`month` is one value per boundary.

**The floor at nought is the per-policy rule and not the shared one.** Where `until_value`
names a column the node reads, or the node reads the issue-age column of a `maximum_age`
horizon, the arithmetic above is applied to *that policy's own* horizon and 11.1.37's
`T_i = max(0, term_months // m)` applies with it, so a term shorter
than one period gives `T = 0`: one boundary, so a `month` of `[0]` and a count of one, and a
policy that projects nowhere. A shared grid's count is not floored: a horizon whose arithmetic
comes out below
nought yields a negative count, which is no boundary count at all and is outside this
entry. Where `until_value` names a column and the node reads nothing, the count was
measured against the whole portfolio and the first item at the foot of this section applies
instead.

**On a shared grid the start is normalised to the anchor** before the first boundary is
taken — a producer laying a calendar grid from the two kwargs forms anchors on month end,
so a valuation date of 15 January opens the axis at 31 January — and each later boundary
is the previous one advanced by one period of the cadence, re-normalised to the anchor. A
per-policy grid takes its shared start date exactly as given. Neither of the two kwargs
forms applies a holiday calendar or a business-day adjustment.

**The columns.** On the three calendar forms four, and this node is the account of each
(the fixed-step form's are below):

- `projection_start_date` — boundary 0 of that row's own timeline.
- `projection_end_date` — the last boundary of that row's own timeline.
- `num_proj_months` — the number of boundaries on that row's own timeline, which is one
  more than its number of periods. The name is a producer's own history and the value is
  a boundary count at every cadence, not a count of months: a five-boundary quarterly axis
  carries 5 here and not 12.
- `month` — elapsed whole months from that row's own first boundary, one value per
  boundary: `0, 1, 2, …` monthly, `0, 3, 6, …` quarterly, `0, 6, 12, …` semi-annual,
  `0, 12, 24, …` annual, of length `n + 1`. It is the calendar-month difference between
  each boundary and the first — `(year − year₀) × 12 + (month − month₀)` — and carries no
  day component.

**`month` is stamped only where that difference is honest**, and an artifact therefore
carries three of these columns rather than four in two cases. At a weekly or daily cadence
a calendar-month difference over-counts by up to a month (31 January plus one day reads as
month 1), so no index is stamped. On an axis anchored at each policy's own inception,
elapsed months are policy *duration* rather than projection time, and stamping them under
this name would conflate the two; that axis carries no index either.

**A fixed-step axis mints no dates.** This node is the account of two columns on it, and
of a third in one case:

- `num_proj_months` — the boundary count `T + 1`, as on every axis; the name is history
  here too.
- `step` — `0, 1, …, T`, one integer per boundary: the step index, a workbook's step
  column. **The name is reserved on this form as `month` is on the others**: a producer
  refuses a declaration over a frame that already carries a `step` column of its own, naming
  the rename and the drop, rather than overwriting it.
- `month` — only where one step is a whole number of calendar months, which is
  `steps_per_year` of 1, 2, 3, 4, 6 or 12: `k × 12 / steps_per_year` at boundary `k`. It is
  never stamped on a `step_years` axis, whatever the decimal: whether `0.25` years is meant
  as three months is a guess, and `steps_per_year = 4` is how a model says so.

There is no `projection_start_date` and no `projection_end_date`: the boundaries are steps,
not days. Time along the axis is section 11.1.37's `projection_frame.t_years`, which on this
form is `k × step_years` or `k ÷ steps_per_year` — one IEEE operation per boundary, never a
running sum — so a workbook's time column, written `x + A·h` or `x + A/12`, is the model's
`issue_age + t_years` to the bit in whichever spelling the workbook used. A model whose
data carries the step index instead, declaring no axis, has no timeline on its record at
all, and nothing in the artifact says that its rows are policies rather than periods.

**On a jagged axis all four columns are per-policy**, and the list-valued ones vary in
length: each row's `num_proj_months` is its own boundary count and each row's `month` its
own index, neither padded to the longest-lived policy. A row whose horizon is null carries
an empty index and a count of zero rather than a null — a policy that projects nowhere has
no boundaries, which is a length and not an absence.

**A frame with no rows lays an axis of no periods.** A selection that keeps no policy (§7.6) —
over the whole book, or in one batch of a run cut into several — leaves no horizon to read, and
a producer lays zero periods over the zero rows and answers no rows; it does not fail for want
of a longest horizon. So does a jagged axis whose every row's horizon is null, each row
projecting nowhere as above. One shared grid sized from rows whose horizon is null in every one
has no length to read, and is refused, naming the column. A jagged axis states no longest
horizon (11.1.37): each policy's boundaries are its own, so a policy's axis is the one
`collect()` over the book lays it, whatever else shares its batch.

**There is deliberately no projection-year column.** A year label depends on the model's
timing convention: with end-of-period rows "year 1" is `ceil(month / 12)`, with
beginning-of-period rows it is `month // 12 + 1`, and the two disagree at every
anniversary. A producer that stamped one would be choosing the model's convention for it,
so the axis states elapsed months and the model states the label it means. A `year` column
on a frame is the model's own calendar column and no part of this operation.

**What a conforming producer will add.** The synthetic form's boundaries follow from the
attributes with the anchoring rule above, and so do a policy-anchored form's wherever the
horizon is a whole term, a fixed date or a number of years the attributes carry as a
value of their own. Four things a second implementation needs beyond that are not on
today's record:

1. **A horizon the attributes do not fix is sized from the model points, and the sizing is
   nowhere on the record.** Where `until` is `maximum_age` and the node reads no issue-age
   column the boundary count is measured against the portfolio's issue ages, and where a
   horizon named by a column is collapsed onto one shared grid it is measured against the
   longest horizon in the portfolio; the count arrived at is no attribute — on `maximum_age`
   the issue-age column is named, as `issue_age_column`, and its youngest value is not — and
   `reads` is empty in both cases because no formula consumed that column. Two runs of one configuration over
   two sets of model points therefore carry the same attributes, the same empty `reads`
   and the same node identity, and lay axes of different lengths. What the reference
   producer holds fixed is that the model points it sizes such a grid from are the whole
   book: it refuses the grid in a run cut into batches and on a scenario axis (§13.2), so
   two runs of one model over one book lay one axis. **For these horizons the
   record alone does not determine the axis**, and a consumer must not lay one from the
   attributes and the anchoring rule as though it did. Whether the record fixes the axis is
   read from the attributes alone, so a consumer that inspects a document before it is handed
   a book refuses such an axis there, on the same nodes and under this clause, as its run
   would. For a shared grid, a conforming
   producer will record the column it was sized from and the boundary count it arrived at;
   a per-policy `maximum_age` axis already reads its issue-age column and states its count's
   rule above.
2. **The `schedule=` form's boundaries are behind a digest.** `schedule_source_sha`
   identifies the object exactly and changes whenever any of its parameters does, but a
   second implementation holding only the artifact cannot rebuild a boundary sequence
   from a digest. The schedule record of section 15 is where the object itself lands, and
   a `projection_set` node will read it rather than naming a digest of it.
3. **The day-count basis a schedule carries is not on the record** under any form.
4. **`frequency` is written in the producing engine's own spelling**, so a consumer
   reading it is choosing between an engine's dialects exactly as it is for a join's
   `how` (section 11.1.2). A conforming producer will state the cadence in a closed
   vocabulary of this specification's own.

All four are stated before they are frozen. The first is the one that bites silently: an
axis laid from the attributes alone is not an ill-formed reading of this document, only a
wrong one.

#### 11.1.2 `join`

`join` is the relational join, and a `join` node is the account of a column that **arrived**
on the frame from a second table rather than being computed from anything already on it.

**The semantics.** For each row of the left side, the join finds the rows of the right side
whose key values equal that row's; a column the right side brings that the left did not
already carry takes its value from the match. One output row per match, so a right side
with repeated key values multiplies rows. Under a left join a row with no match keeps its
own columns and takes null for every arriving one where the record keeps it (`on_missing`,
below), and is refused where it does not. Which rows survive is the join type's
business, and equality of key values is the whole matching rule — this operation has no
inexact, range or nearest form.

**The attributes state the join.**

- `on` — the key. One key is its own name; several are comma-separated in the order they
  were given; where the two sides name the key differently the attribute is the left side's
  keys, `=`, then the right side's, each side comma-separated within itself. Null where
  there is no key at all, which is a cross join. **A name is every character between the
  separators, spaces included**: a consumer splits on `=` once and on `,` within each side
  and trims nothing, because a column called `" code "` is not the column called `"code"`,
  and a reader that trimmed would bind a key the join never matched on.
- `how` — the join type.
- `right_fingerprint` — the content identity of the right-side table, taken under the
  content grammar of section 12.3 over the whole right side in canonical form: its columns
  ascending by name and its rows sorted by every column in that order. It answers "which version of that table did this run use?" and **is not
  comparable with an assumption table's own digest** over the same file, which hashes a
  different projection of it. It is null in two cases, both honest rather than convenient:
  a right side handed over lazily, where taking the hash would mean reading the very frame
  that was deferred; and a frame the sort or the encoding refuses.
- `on_missing` — present only on a left join, and only as `"null"`: the model keeps a policy
  whose key matches no row of the right side, with null in every column the join brings. A
  null key matches no row and is such a policy. **Absent, a left join refuses that policy**:
  the reference producer refuses the join where it is written, naming how many policies
  missed, the first of them and its key, and the line; a consumer refuses the record before
  it answers. What `"null"` does to a total is stated, not hidden: a fold that skips nulls
  (section 11.1.14) leaves the policy out unless the model fills the null first
  (`fill_null`), and a consumer that holds no null answers a run whose nulls are filled
  before any operation reads them and refuses one that reads an unfilled null. **A key column
  the model also reads as a value is held to section 11.1.13's rule wherever it is read as
  one**: its null is a miss to the join, but the comparison or arithmetic that reads it meets
  an unfilled null, so such a consumer refuses the book where the reference producer answers
  null for that policy. The other join
  types carry no `on_missing`: an inner join drops the unmatched policy, a semi or anti join
  selects by the key, and a full or right join keeps the right side's rows.

**A `join` node accounts for the arriving columns and for nothing else.** Every node it
mints is one column the frame did not have a line earlier; the columns the left side
already carried keep the account they already had. A join that brings no new column at all
mints no node, so no `join` node carries a type that brings nothing. **A semi or anti join is
recorded all the same, as the selection step it is** (section 7.6): it brings no column and
chooses which policies are valued, and its `join` call — key, type, `right_fingerprint` — is
that step's tree, its right side an assumptions entry exactly as here. A left join whose
right side's every column is a shared key brings nothing and chooses nothing, and is not
recorded at all.

**A `join` node reads its key.** Every column the join brings in holds whichever row of the
right side its key matched, so the key decides its value: a policy moved to another product
code holds another product's rate. `reads` names the **left side's** key columns — the
columns on this frame, in the order `on` lists them — bound by section 8's rule to the
definition each held when the join ran. Each read is `INDIRECT` / `JOIN` (section 9): the key
selects the row rather than producing the value, which is the reading a lookup's key already
takes. The right side's key names are not reads, because they name columns of the right-hand
table, which is not on this frame and travels as an entry of its own. A cross join states no
key, and what it brings in reads nothing. The key stays stated in `on` as well: that attribute
is where a consumer executing the join finds the right side's names, and `reads` is where a
consumer following lineage finds the left side's, so a question about what moves when a key is
restated reaches every arriving column and everything downstream of it.

**The right side itself travels with the record.** It is an entry of the assumptions
directory (section 15), kind `join`, carrying the whole right-hand frame inline the way a
lookup's table does — under the same size guard, and standing in for itself under section
6.1's `omitted` object where the guard refuses or the producer cannot vouch for the values.
The entry is named `join:` followed by the first eight hex digits of its fingerprint, which
is section 15's rule for a value object with no name of its own to state; that label is not
the identity, so a consumer resolves the entry by kind and by the **whole** digest and
refuses an ambiguous match rather than taking the first label that agrees. Section 15 states
the payload's form and section 13 the grammar a consumer re-hashes it under.

**The node names its entry through `right_fingerprint` and through nothing else.** There is
no second attribute, no path and no table name, and the omission is the position rather than
a gap in it: a path answers "which file?", and the measurement that put this section here
found a right side whose values matched no file in the model's own assumptions directory —
some selection, filter or computed column stood between the file on disk and the frame the
join was handed. A digest beside the values it was taken over answers the question a path
was being asked to answer and cannot: *is this the data the run used?* A consumer holding
the artifact and nothing else can now execute a joined model, which before this it could
not.

**A right side handed over lazily carries nothing, and the record says so rather than
guessing.** `right_fingerprint` is null, no entry is written, and what survives is the fact
that a join happened, its keys and its type. Collecting the frame to hash it would defeat
the very deferral the caller asked for, and a digest over a query plan would fail to move
when the data behind the plan did — which is worse than not claiming one. The same is true
of a frame the sort or the encoding refuses.

**What a conforming producer will add.** Three things a second implementation needs that
today's record does not carry:

1. **`how` is written in the producing engine's own spelling**, not in a vocabulary this
   document fixes. `full` and `outer` are two names for one join in circulation, and a
   consumer reading this attribute today is guessing between an engine's dialects. A
   conforming producer will state the join type in a closed vocabulary of this
   specification's own.
2. **The key is one flat string.** A call's attribute is a flat typed value (section 12.1),
   so several keys are comma-separated and the two sides are divided by `=` — which makes a
   key whose column name contains a comma or an equals sign ambiguous on the wire. Until a
   conforming producer carries the two key lists structurally, **the reference producer
   refuses such a key** — and an empty name, which would read back as no key at all — at the
   join, naming the column and asking for it to be renamed, so no document it writes holds
   an attribute that reads back as other keys.
3. **An arriving column keeps its right-side name.** The column a join brings is written
   under the name the right side gave it; a consumer reading a `join` node's `column` reads
   the right side's name. Nothing in the record says which of the two sides names an
   arriving column, and a consumer executing the join has to call it something; a conforming
   producer will state the rule it wrote under.

Row order is not recorded and is not part of these semantics: a join is a set operation,
and a model whose answers depend on the order rows come back in is depending on something
no artifact of it claims. **The book is another matter.** The book's digest (section 7.5) is
taken over the rows in the order the book holds them, so a model that joins its enrichment
data and then builds its frame from what the join returned is digested in whatever order the
join returned it in. The reference producer therefore keeps the calling frame's rows first
and where they were through a join unless its caller names another order, so the same file
gives the same book, and the same output, on every run; nothing about that is recorded
here, because nothing about the calculation depends on it.

#### 11.1.3 `clip`

`clip` holds a value between a lower and an upper bound. It is the operation behind a
duration capped at a select table's last row, a credited rate held between a floor and a
cap, a negative account value floored at zero.

**The semantics.** For each value: a value below the lower bound becomes the lower bound, a
value above the upper bound becomes the upper bound, and a value already between them is
returned unchanged. The bounds are inclusive — a value equal to a bound is already within
it — and a null value stays null, because a bound answers "how large may this be" and not
"what is this when it is missing".

**A lower bound above the upper bound is answered by testing the lower bound first.** No
value satisfies both, so the order the two are applied in is the whole of the answer, and
the order is this: a value below the lower bound becomes the lower bound, and a value at or
above the lower bound that is above the upper bound becomes the upper bound. Crossed, the
operation is a step at the lower bound rather than a constant — bounds of 8 and 2 over
`1, 5, 10` give `8, 8, 2` and not `2, 2, 2`. This document left the case unanswered while
its own reference implementation was giving two answers to it, one for a per-policy value
and another for a per-period one, and an operation that means two things depending on the
shape its value arrived in is not an operation a consumer can read. Stating the rule does
not make crossed bounds sound: a model whose bounds can cross is still depending on
something no artifact of it claims, and the defect is in whatever produced the bounds, not
in this operation.

**The operands are the value and its bounds, in that order.** The first operand is the
value being bounded. The operands after it are the bounds, and `bounds` says which:
`both` — the lower then the upper; `lower` — one operand, the lower bound, with nothing
excluded above; `upper` — one operand, the upper bound, with nothing excluded below. A
`clip` with no bound at all is not this operation and is never written.

**A bound is an operand, not a configuration.** It may be a literal, a column, or any
expression — a floor that varies by product is a column reference in the tree like any
other, and reads it declares reach `reads` the ordinary way. This is why the bounds are
operands rather than attributes: an attribute is a flat typed value (section 12.1) and
could not carry a column at all, and a vocabulary that could only state constant bounds
would push every varying one back into an engine fragment.

**One value at a time.** Where the value is a per-period column (section 10's list form),
the bounds apply to each period's own value: the operation has no view across periods and
never compares one period with another. A per-period value with per-policy bounds bounds
every period of that policy by the same pair.

**`clip()` keeps the column's own type, whatever its bound is.** The answer is the value or
one of its bounds, so a whole-number value answers whole numbers — `i64`, or `list[i64]` per
period — whether its bound is a literal, a per-policy column or a per-period one, and a
decimal value answers decimals: `[0, 5, 12]` capped at a column holding 10 is `[0, 5, 10]`,
never `[0.0, 5.0, 10.0]`. The reference producer holds a per-period value between bounds read
from columns in doubles, so it refuses by name a policy whose value or bound lies at or beyond
`2^53` in magnitude rather than compare it as its nearest double; a literal bound holds every
whole number exactly.

#### 11.1.4 `cut`

`cut` places each value in one of the intervals a set of breakpoints divides the line into.
It is the operation behind an age band, a duration band, a size band — the grouping a rate
table or an experience study is keyed on.

**The semantics.** `n` breakpoints, given in ascending order, make `n + 1` intervals: one
below the first breakpoint, one between each adjacent pair, one above the last. Each value
takes the interval it falls in. By default an interval is closed on the right — a value
equal to a breakpoint belongs to the interval *below* it — and `left_closed` reverses that,
so a value equal to a breakpoint belongs to the interval above. A null value takes no
interval and stays null. **A NaN takes no interval either and is null**, per policy and per
period: it is neither above a breakpoint nor below one, so no interval holds it, and the
answer is the null a value with no band already is — never the lowest band a reading of "not
above any breakpoint" would give, nor the highest an engine ordering NaN above every number
would. A consumer that carries no null refuses such a value by name rather than band it. That
null is then what every operation over it reads: a comparison of it is null, and a portfolio
fold that skips a null policy (a total, an average across the book) skips it as it skips any
other, so a total built over banded NaNs does not show them — test with `is_nan` before banding
where a NaN must be counted.

**The operands are the value, the breakpoints, and optionally the labels.** The second
operand is the sequence of breakpoints, written into the formula (section 12.1's sequence
literal). A third operand, where present, is the sequence of labels, one per interval and
therefore one longer than the breakpoints; where absent, each interval names itself after
its own bounds and the naming is the producing engine's, which two implementations may spell
differently.

**`include_breaks` changes what comes back**, from the interval alone to the interval
together with the breakpoint that closes it.

**What a conforming producer will add.** A banded value is an ordered category, and section
10's type vocabulary has no name for one — nor for the pair `include_breaks` returns. A
`cut` therefore reaches an artifact today only where something downstream has already turned
it into a type that vocabulary holds: a comparison against a label, a cast to text. The
operation is in this vocabulary because the calculation is statable; the type it produces is
a separate gap, in section 10 rather than here.

#### 11.1.5 `is_in`

`is_in` asks, of each value, whether it is one of a set the formula names. It is the
operation behind "these product codes share a basis", "these states are in the filing",
"this rider is one of the guaranteed ones".

**The semantics.** True where the value equals a member of the set, false where it equals
none. Equality is the whole matching rule; there is no ordering, no range, no pattern. A
null value is not equal to anything, so by default the answer for it is null rather than
false; `nulls_equal` set true makes a null value compare as a value, so a null against a set
holding no null is false.

**The operands are the value and the set.** The second operand is the set: a sequence
literal where the formula wrote the members out, and otherwise whatever expression produced
it, in the tree like any other operand.

**A collection with no order of its own is not a set written out.** Where the members arrive
in a form that fixes no order between them, the only order a producer could write them in is
whichever one its run happened to iterate, and two runs of one model would be two documents.
Such a line is not this operation at all: it is an engine fragment and the node says so —
not a membership test whose set operand is an escape, which is what an expression that
produced the members gives, but the whole line left where it was.

#### 11.1.6 `replace`

`replace` substitutes one value for another, one for one. It is the operation behind mapping
a table's own spelling of a code onto the model's, or collapsing several codes into one.

**The semantics.** Each value equal to one of the values being replaced takes the
replacement standing opposite it; every other value, the null included, is returned
unchanged. This is a substitution and not a lookup: a value with no replacement keeps
itself, rather than becoming missing.

**The operands are the value, the values replaced, and their replacements.** The second
operand is the sequence of values being replaced. The third is either a sequence of the same
length — replacement `i` for value `i` — or one value standing for all of them. A producer
that wrote the substitution as a mapping records it as those two sequences: the two
spellings are one calculation and are therefore one node.

**The pairs are recorded in one order, and the order they were written in is not it.** Every
value is replaced at once and no value twice, so which pair a formula named first changes
nothing about the answer — which makes the order a producer happened to receive a false
difference, the kind that puts drift in a change report where the calculation did not move.
The pairs are therefore ordered by the text of the value replaced, the type of that value
breaking a tie between two spellings of one text and the replacement breaking it after that,
so that the order is total. Ordering by the text and breaking the tie is the idiom section
12.1 already uses for a call's attributes; this is the one other place in the vocabulary
where a producer holds an order that nothing in the calculation fixes, and the operands are
written in it rather than the encoding sorting them afterwards, so that two records of one
substitution are the same document and not only the same digest.

#### 11.1.7 `str.to_date`

`str.to_date` reads text as a calendar date. A model point file that carries its entry dates
as text is the ordinary case rather than the awkward one — an extract arrives in whatever
the administration system printed — and this is the line that turns it into dates before a
projection can begin.

**The semantics.** Each string is read under the format the record carries, and the result
is a date with no time and no zone. `strict` says what a string the format does not fit
becomes: under `true` the parse refuses, under `false` that string becomes null and the rest
are read. `exact` says whether the format has to account for the whole string or may match
a date inside a longer one. A null string parses to null under either.

**The format is what identifies the parse, and it is on the record.** `"%Y/%m/%d"` and
`"%d/%m/%Y"` read the same characters into two different dates, so two models differing only
there are two models. The attribute is the format string in the `strftime` vocabulary — the
one an actuary already writes — and a producer that supports another must not write this
identifier for it.

**A hint about speed is not part of this operation and is not recorded.** An engine may take
an argument that only makes the parse faster — a cache of conversions already done over
repeated text is the common one — and no such argument can change a date. Section 12 takes a
node's canonical bytes over what the node computes and nothing else, so recording one would
make two identical parses two documents, and a change report would call drift on a line
nobody edited. A consumer meeting this operation may rely on the three attributes named
here; a producer that writes a fourth for a hint is writing something this section does not
describe.

**A null `format` means the producer inferred it.** The parse then depended on the text the
run happened to hold, and a second implementation reading the record cannot reproduce it:
what a consumer knows is that dates were read out of text and nothing about how. A producer
that can name the format should, and a reader meeting a null here should treat the operation
as `core` in vocabulary and unreproducible in fact.

**One string at a time.** Where the text is per-period (section 10's list form), each
period's own string is read; the operation has no view across periods.

**What a conforming producer will add.** The sibling parses -- text to a date *and a time*,
text to a time of day -- are not in this vocabulary. A datetime carries a time unit and a
zone, and this document names neither on an operation; adding the parse without them would
be a vocabulary entry a consumer could not act on. Until then those lines stay engine
fragments and say so.

#### 11.1.8 `round`, `floor` and `ceil`

These three move a value to a whole step. `round` goes to the nearest step of a size the
call names; `floor` goes down to the whole number below, and `ceil` up to the one above.
They are the operations behind a premium billed in whole pennies, the completed years a
duration has run, and the whole units a charge is levied in.

**The semantics.** `floor` returns the largest whole number not above the value, and `ceil`
the smallest not below it — so a negative value floors *away* from zero and ceilings
towards it, which is what makes the two different questions rather than one with a sign.
`round` moves a value to the nearest multiple of ten to the power of minus `decimals`, and
`decimals` is any whole number: `2` rounds to hundredths, `0` to whole numbers, and a negative
one to a multiple of a power of ten, as a spreadsheet's `ROUND(x, -n)` does — `-1` to tens,
`-3` to thousands, the step a sum assured is banded by. The attribute carries the count as
written, `decimals: -2` for hundreds. A null value stays null under all three. **A flag, or a
comparison, is read as its 0.0 or 1.0** (section 11.1.25): `floor`, `ceil` and `round` of one
answer `f64`, per policy and per period — `floor(True)` is 1.0 and `round(False, 2)` 0.0 —
never `bool`, so a consumer reads the stored flag's own type and answers the double.

**What `round` moves is the value a spreadsheet holds.** On an `f64` value it reads the
double as its fifteen-significant-digit decimal — the value's exact decimal expansion cut to
fifteen significant digits, a sixteenth digit of 5 or more going away from zero, a double that
is itself exactly a sixteen-digit tie included, as section 11.1.35 reads an operand of
`excel.round` and section 11.1.12 a value of `round_sig_figs` — and moves that decimal to the
nearest step under the tie rule below. The answer is the double nearest the result, with the
value's sign. 2.675 is the double 2.67499999999999982…, which reads as 2.67500000000000, a
half, so at two places it is 2.68 under either rule; 0.285 reads as a half too and is 0.28 to
the even neighbour and 0.29 away from zero; 1.005 away from zero is 1.01; a workbook's
`1.5 * 45366.20999999999`, the double 68049.31499999999…, is 68049.32 at two places under
either rule; and 0.30000000000000004 at sixteen places is 0.3, its fifteen-digit value. Two
routes answer differently and neither computes this operation: rounding the double's exact
value answers 2.67 for 2.675 to the even neighbour, and scaling it by a power of ten in
binary64 answers 0.28 for 0.285 and 1.0 for 1.005 away from zero. To the left of the point the
same reading is moved to a multiple of `10^n` by the same rule: 1234.5 to hundreds is 1200.0,
25.0 to tens is 20.0 to the even neighbour and 30.0 away from zero, −25.0 is −30.0 away from
zero, and a workbook's 68049.31499999999 to tens is 68050.0. A value under half a step answers
a nought with its own sign: −4.0 to tens is −0.0. So `round` under `half_away_from_zero`
answers what `excel.round` answers at the same places, on either side of the point, wherever
section 11.1.35's entry reaches (`num_digits` from -10 to 10), and the framework reads a double
one way wherever it rounds one. The two spellings part company on a whole number, in type
only: `excel.round` answers Float64 cells, as a spreadsheet does, and `round` keeps an `i64`
whole — 25 to tens away from zero is 30.0 under one and 30 under the other.

**A whole number is moved in whole numbers.** On an `i64` value `floor` and `ceil` answer
`i64`, the value itself, exactly: `floor` of `2^53 + 1` is 9007199254740993, never the
9007199254740992 a double would carry. On an `i64` value `round` answers `i64`. At or
after the point that is the value itself: a whole number is already on every such step. To
the left of it the value is moved to its nearest multiple of `10^n` exactly, in whole-number
arithmetic, by the same tie rule: 25 to tens is 20 to the even neighbour and 30 away from
zero, −25 is −20 and −30, and 35 is 40 under both. Never through a double: `2^53 + 13` to
tens away from zero is 9007199254741010, and through the double nearest it, 2^53 + 12, it
would be 9007199254741000. **An answer outside `i64` is refused by
name, never wrapped**: `2^63 − 1` to tens is 9223372036854775810 and the least `i64` to tens
is −9223372036854775810, neither of which an `i64` holds. From `10^19`, past the largest
power of ten an `i64` holds, every value is under half a step or rounds to one no `i64`
holds: to `10^19` a value of magnitude below `5 × 10^18` answers 0, one above it is refused,
and `5 × 10^18` itself answers 0 to the even neighbour and is refused away from zero; from
`10^20` every `i64` answers 0. A producer whose engine carries other whole-number types reads
each as the `i64` it holds — a narrower one exactly, a wider one where its values fit and
refused by name where one does not, as arithmetic reads it (section 11.1.25) — and answers
`i64`.

**Where a producer reads the value exactly, and what it does elsewhere.** In binary64 the
reading is moved exactly for every value below `10^37` in magnitude at up to 22 places either
side of the point — `decimals` from -22 to 22: there the reading can be taken exactly in
binary64 (section 11.1.12 gives one way, the scaling its figures are read by) and the step is a
double. Each bound is compared exactly. Zero, a NaN and an infinity are their own answers.
**Outside that range an engine may answer by its own native rounding**, and the
reference producer and the JAX engine both do, the same double on both: from `10^37` every
double is a whole number and, at up to 22 places either side, the answer is the double itself,
which sits within half a unit of the fifteenth figure of its reading; past 22 places the
native scaling — the value times ten to the places, rounded to a whole number by the mode and
scaled back — may sit a few units in the last place from the reading, or on the other side of
a half a few units from one; and past 22 places to the left of the point, to `10^308`, the
same scaling is written as three products, the value times the double nearest `10^−22`, times
the double nearest `10^(22−n)`, rounded by the mode, times the double nearest `10^n` — two
factors down because `10^−308` is below the least normal double, which an engine may read as
nought — an answer the scaling carries past the largest double being the value itself; it may
sit a few units in the last place from the reading, or a step away where the reading lies
within a few units of a half. **Past `10^308` no step is a double**, and every finite double
is less than half of one, so from `decimals = -309` every finite value answers a nought of its
own sign, exactly and on every producer; a NaN and an infinity are their own answers. The
reference reader moves the reading exactly at every magnitude and every count of places, and
refuses an answer past the largest double: 1.7976931348623157e308 to `10^308` reads as
2e308, which the reader refuses and an engine answers as the value itself.

**The tie rule is on the record because it moves the money.** A reading exactly halfway
between two steps has two answers, and `mode` says which one this operation takes:
`half_to_even` sends it to whichever neighbour is even, and `half_away_from_zero` sends it
to the neighbour further from zero. The two part company on the ties whose away-from-zero
neighbour is odd — half a penny is a penny under one rule and nothing under the other, while
1.5 and 3.5 go to 2 and 4 under both — and which one an engine applies when a formula
leaves it out is that engine's choice rather than the model's. So the attribute is always
present and always names the rule the calculation actually ran under; a producer that
omitted it would be publishing a premium whose last penny depends on which engine reads the
file back. `floor` and `ceil` have no tie to break and carry no configuration at all.

**The operand is the value, and there is only one.** Neither the places nor the tie rule may
vary by policy: they are one flat typed value each (section 12.1), which is what an
attribute is, and a model whose rounding rule varies by row is not writing this operation.

**One value at a time.** Where the value is a per-period column (section 10's list form),
each period's own value is moved; the operation has no view across periods and never
compares one period with another.

**Significant figures are another operation.** Rounding to a count of *significant figures*
has its own identifier,
`round_sig_figs` (§11.1.12). Its step depends on each value's magnitude;
it is not `round` with a different attribute.

#### 11.1.9 `cum_prod` and `cum_sum`

These two fold a per-period column along the projection's period axis. `cum_prod` is the
operation behind a fund's cumulative growth from the start of a projection and a survival
probability written as a running product of one-minus-the-decrement; `cum_sum` is the
premium taken to date, the claims paid so far, the reserve released cumulatively.

**The semantics.** For a value with `n` periods the result has `n` periods, and period `t`
of it is the product — or the sum — of periods `0` to `t` of the operand inclusive. So the
first period of the result is the first period of the operand, and the last is the fold over
the whole of it. Under `reverse` the fold runs the other way: period `t` of the result is
the product, or the sum, of periods `t` to `n - 1` inclusive, which is what a model writes
when it wants what is still to come rather than what has been.

**The direction is the calculation, so it is on the record.** The premium still to come and
the premium already taken are two different columns of one cashflow, and an engine's
rendering of either drops the flag that told them apart. `reverse` is therefore always
present and always names the direction the fold ran in.

**The fold is along the periods, and along nothing else.** The operand is one policy's own
sequence of periods, and the result is that policy's; no value of one policy reaches
another's answer. An engine's method of the same name applied to a per-policy column folds
down the rows of the model-point file instead — a different calculation, whose answer
depends on the order those rows happen to stand in, and one this vocabulary does not name.
A producer must not write these identifiers for it: such a line is an engine fragment and
the node says so, which is the tier doing exactly what it is for.

**A period carrying no value ends the fold's knowledge of its own total.** Period `t` of
the result is null when period `t` of the operand is null and whenever a null period stands
between period `t` and the end the fold started from — so `[1.0, null, 3.0, 4.0]` answers
`[1.0, null, null, null]`, and under `reverse`, where the fold starts at the last period, the
same operand answers `[null, null, 7.0, 4.0]`. The propagation runs in the fold's own
direction because that is the direction the missing value would have travelled: a running
total that has lost a period does not know its total from there on, and a fold that skipped
the null and carried on would answer `[1.0, null, 4.0, 8.0]` — a number with nothing wrong
on the face of it and a period missing from underneath it. The four reductions of 11.1.14
follow this rule and not a milder one: a total that lost a period is unknown, because nothing
in one number can say the period was not there. A running fold answers one number per period
and says which of them it no longer knows; a total has the one answer, and says it there.

**A null outer list answers null.** A policy whose whole column is null has no periods for
the fold to reach, and the result for that policy is null rather than an empty list: it is a
policy with no column, not a policy with no periods. This is distinct from an empty list,
which is a policy with a column of no periods and answers an empty list.

**Over whole numbers each period is a whole number, exact.** Over an `i64` run both folds answer
`list[i64]`, each period taken in whole-number arithmetic and never through a double:
`cum_sum` of `[2^53 + 1, 3]` is `[9007199254740993, 9007199254740996]`, where a fold in doubles
answers 9007199254740992 for the first period. A period whose answer is outside `i64` —
`cum_prod` of `[−2^63, −1]` at its second period, `cum_sum` of `[2^63 − 1, 1]` at its second —
is outside the portable domain, as an integer result is in section 11.1.25: a consumer claiming
only this domain must refuse the line, never wrap the period. The reference producer refuses it
by name, naming the column and the fold; a run of flags folds as the whole numbers it indicates,
`list[i64]`.

**Every period is in every later answer.** That is why a read into one of these is
`DIRECT`/`AGGREGATION` (section 9) rather than `DIRECT`/`TRANSFORMATION`: an impact cone
drawn through a cumulative product has to sweep in the whole period axis, and a reviewer
told it was a transformation of this period's value would be told the opposite of the truth.
The `DIRECT` is on the edge and the `AGGREGATION` beside it, in the narrowing facet section
9 describes — so a consumer that reads only the core edge sweeps the whole axis in, which is
the right answer, and one that reads the facet as well is told why.

**The reduction of a per-period column to one number is now in this vocabulary**, and
11.1.14 to 11.1.17 are where it is: `sum`, `mean`, `min` and `max`. This paragraph used to
say the opposite — that such a line stayed an engine fragment because this document had not
said how an operation states a result whose shape is not its operand's. It says it now, per
entry and in prose, and the present value that sums a whole discounted cashflow is a `call`
like any other.

#### 11.1.10 `mortality.at`

`mortality.at` reads one rate per row out of an assumption base under the mortality
convention that base is held on. It is the line behind a cost-of-insurance charge, a death
decrement, an expected-claims projection — the read an actuary describes not as "a lookup"
but as "the 2017 CSO male select rate at attained age and duration".

**The operands are the dimensions read, and `dimensions` names them.** The operands stand in
the order the read takes them, and `dimensions` is those names in that same order, joined by
commas — the rendering section 11.1.2 already gives a join's keys, and for the same reason:
an attribute is one flat typed value and cannot hold a list. The first names are the
structure's own (below); any names after them are the further dimensions the base is keyed
by — a table identifier, a gender, a smoker status — in the order the read was written.

**The structure says which dimensions the read takes, and what happens to them.** `structure`
carries one of three values.

- `aggregate` — one rate per attained age. The dimensions are `age` and whatever else the
  base is keyed by. There is no duration and no select period, and `select_period` is absent
  rather than null: a basis with no select period has none, which is different from one whose
  select period was not recorded.
- `select_ultimate` — the dimensions are `age` and `duration`, and **the duration is held at
  `select_period` before the read**. A duration at or below the select period reads its own
  row; every duration above it reads the select period's row, which is what a select table
  means by an ultimate rate. The clamp has an upper bound only: nothing is excluded below,
  because a duration below the first row of the base is a key the base does not carry and is
  answered by the miss policy, not by a floor this operation invents. `select_period` is
  present, and it is an integer number of durations in the base's own duration units.
- `joint` — the dimensions are `age_1` and `age_2`, one rate for a pair of lives. There is no
  clamp and no select period.

**The read itself is section 11.1's `lookup`, and its miss policy is the base's.** After the
clamp, the operation is an exact-match read of the base at those keys: a key the base does
not carry is answered the way the base answers a miss, and this operation neither widens nor
narrows that. A producer stating `mortality.at` is stating the convention around a lookup,
never a second kind of matching. **Where the node carries no `on_missing` attribute, that
policy is `"raise"`** — the default an assumption base takes where a model has set no other —
so a key the base does not carry refuses the invocation and names the key, rather than being
answered by a consumer's own choice between a zero, a null and a NaN; where the node does
carry one, it is read as 11.1.24 states it, in that clause's three values and under the same
`fill_value` pairing.

**`age_basis` is recorded and never converted.** `age_last_birthday` and
`age_nearest_birthday` are different definitions of the same integer, and a rate table built
on one and read with ages computed on the other is out by up to half a year of mortality —
a valuation error that no run reports, because both sides are integers and both look right.
The attribute says which definition the base is on. It does **not** say that anything was
converted: this operation performs no conversion at all, and a model whose ages are on the
other basis has to convert them itself, in a line of its own that the record can see. A
consumer must read this attribute as a declaration about the base, not as a transformation
applied to the ages.

**One row at a time.** Where the dimensions are per-period columns (section 10's list form),
each period's own keys are read, and the clamp holds each period's own duration; the
operation has no view across periods and never compares one period with another. A
per-period duration with a per-policy age reads that policy's age in every period.

**What a conforming producer will add.** Three things, all stated here rather than made
silently.

1. **The dimension names are one flat string.** A call's attribute is a flat typed value
   (section 12.1), so several names are comma-separated — which makes a dimension whose name
   contains a comma ambiguous on the wire, exactly as 11.1.2 says of a join's keys. A
   conforming producer will carry the name list structurally.
2. **A base whose miss policy is not the default will travel with it.** The paragraph above
   says what a consumer applies where the node states nothing, and that is a default rather
   than a reading of the base: a base registered to answer a miss with a NaN or with a fill
   is, on today's record, indistinguishable from one that refuses — and the two differ at
   exactly the keys a model with a guarded read was written around. A conforming producer
   will carry the base's own policy on the node, under `on_missing`, with the `fill_value`
   pairing 11.1.24 states.
3. **The wrapper has no assumptions entry of its own.** The base appears in the artifact's
   assumptions section under the *assumption table's* identity, which is what `table` and
   `table_fingerprint` name; the wrapper's identity travels as the `mortality` attribute and
   nothing else. A reader can therefore say which grid was read and under which convention,
   and cannot yet re-hash that convention against a published entry the way they can a
   table, a schedule or a curve. Giving the wrapper an entry is a change to section 6's
   assumption kinds.

#### 11.1.11 The signature schedule

This subsection is normative, and it is the one section 12.1 cannot be implemented without.
Section 12.1 says how a call encodes — the tag, the identifier as text, the counted run of
operands, the sorted run of attributes. It does not say, and cannot, **which values a given
identifier puts in which of those two places**. That is here, one row per identifier, for
every identifier the table at the top of section 11.1 lists.

**Why a schedule at all.** Reproducing `projection.at_period(-1)` needs the attribute's key
name and its scalar type; nothing else in this document carries either, and a producer that
chose `offset` where this one chose `relative_period` would publish a different digest for
an identical calculation. That is not a cosmetic disagreement — it is the false positive
section 12 exists to prevent, arriving through the one door the format had left open.

**Four rules hold across every row.**

- **Operand order is the calculation and is never sorted.** Section 12.1 sorts attributes by
  key text precisely so that a producer's build order cannot leak into a digest; it does
  **not** sort operands, because which operand is which is what the operation means.
  `excel.days(end, start)` and `date.months_between(start, end)` are the two rows where the
  order is easiest to get backwards, and both are stated below.
- **An attribute is one flat typed value** (section 12.1), so anything that can vary by
  policy or carry an expression is an operand instead. That is why `clip`'s bounds, `cut`'s
  breakpoints and `is_in`'s membership set are operands and not configuration.
- **A key listed as *always* is written even when its value is null**, and the null is
  encoded (section 12.1). A key listed as *conditional* is absent, not null, when its
  condition does not hold; the two spellings are different digests, so the distinction is
  stated per row rather than left to a producer's habit.
- **A scalar type in the rows below is the type of the value, not of the key.** Three
  attributes admit more than one — `excel.yearfrac`'s `basis`, `projection_set`'s
  `until_value`, `projection.with_period`'s `value` — and each is called out where it sits.
  Section 12.1 tags every scalar type differently, so an attribute written as `1` and one
  written as `1.0` or `"1"` are three records, and a producer must write the type the caller
  gave rather than normalising it.

**The fifteen binary operators take no part in this schedule.** `add`, `sub`, `mul`, `div`,
`floordiv`, `mod`, `pow`, `lt`, `le`, `gt`, `ge`, `eq`, `ne`, `and` and `or` are not calls:
they encode under the binary-operation tag `0x03` with two operands and no attributes at all
(section 12.1), and a producer that wrote one as a call has written a different node.

**The schedule.** "Receiver" means the column or expression the operation was reached on.
Where an operation has one it is **operand 0**, and `projection.accumulate` is the single
row where that does not hold. Several operations have no receiver at all — `join`,
`projection_set` and the bare `rollforward` are minted by a recording door rather than
written on a column, while `finance.present_value`, `finance.discount_factor`,
`date.date_ranges` and `date.offset_by` are written on the frame and take every operand
from the columns the call names.

| Identifier | Positional operands | Attributes |
|---|---|---|
| `abs` | 1 — the value | none |
| `cbrt` | 1 — the value | none |
| `ceil` | 1 — the value | none |
| `clip` | 2 or 3 — the value, then the bounds actually given, lower before upper | `bounds` (text) always: `both`, `lower` or `upper`, which is what says whether a single bound operand is the floor or the cap |
| `cum_prod` | 1 — the per-period value | `reverse` (flag) always |
| `cum_sum` | 1 — the per-period value | `reverse` (flag) always |
| `curve.discount_factor` | 1 — the times | `curve` (text) always: the curve object's own `source_sha` |
| `curve.spot_rate` | 1 — the times | `curve` (text) always |
| `cut` | 2 or 3 — the value, the breakpoints as a sequence literal, and the labels as a sequence literal where labels were given | `left_closed` (flag) always; `include_breaks` (flag) always |
| `date.date_ranges` | 2 — the start date, the end date | `interval` (text) always; `closed` (text) always |
| `date.months_between` | 2 — **the start date, then the end date** | none |
| `date.offset_by` | 1 — the date | `duration` (text) always |
| `date.to_period` | 1 — the date | `freq` (text) always |
| `excel.days` | 2 — **the end date, then the start date**, which is the receiver-first order EXCEL's own `DAYS(end, start)` takes | none |
| `excel.edate` | 2 — the start date, the whole months | none |
| `excel.eomonth` | 2 — the start date, the whole months | none |
| `excel.from_excel_serial` | 1 — the serial | `epoch` (text) always: `1900` or `1904` |
| `excel.irr` | **1 or 2** — the cashflows, and a starting guess only where one was given | `default_guess` (decimal, nullable) always. Arity is load-bearing for identity. Absence and a null per-row guess both use the recorded/default fallback (§11.1.36) |
| `excel.pv` | 3 — the rate, the number of periods, the payment | `fv` (decimal, nullable) always; `typ` (whole number, nullable) always |
| `excel.round` | 1 — the value | `num_digits` (whole number) always |
| `excel.yearfrac` | 2 — the start date, the end date | `basis` (text **or** whole number) always — Excel's own basis is written both ways, and section 12.1 tags the two differently, so a model written with `1` and one written with `"actual/actual"` are two documents |
| `exp` | 1 — the value | none |
| `fill_nan` | **2 — the value, then the fill**, as for `fill_null` and for the same reason | none |
| `fill_null` | **2 — the value, then the fill**. The fill is an operand and never an attribute, because what fills a gap is as often a column or an expression as a number | none |
| `finance.compound` | 1 — the period | `rate` (decimal) always; `periods_per_year` (whole number) always |
| `finance.discount` | 3 — the value, the rate, the number of periods | none |
| `finance.discount_factor` | **2 always** — the rate column, the periods column, both written whatever the method | `method` (text) always: `spot` or `forward`. Under `forward` the second operand is not read, and it is still written: the record states the call, not the evaluation |
| `finance.present_value` | 3 — the cashflow, the rate, the period | none |
| `finance.to_monthly` | 1 — the annual rate | `method` (text) always: `compound` or `simple` |
| `floor` | 1 — the value | none |
| `is_finite` | 1 — the value | none |
| `is_in` | 2 — the value, the membership set | `nulls_equal` (flag) always |
| `is_infinite` | 1 — the value | none |
| `is_nan` | 1 — the value | none |
| `is_not_nan` | 1 — the value | none |
| `is_not_null` | 1 — the value | none |
| `is_null` | 1 — the value | none |
| `join` | **none, always** — the key is stated in `on` rather than taken as an operand, and the node's `reads` bind it (11.1.2) | `on` (text, nullable) always; `how` (text) always; `right_fingerprint` (text, nullable) always; `on_missing` (text) only as `"null"` on a left join that keeps an unmatched policy |
| `list.get` | **2 — the list value, then the position**. The position is an operand because it may be one signed Int64 value per policy; a whole-number literal is the same operand form broadcast across policies | none |
| `list.reverse` | 1 — the list value | none |
| `log` | **1 always** — the value. The base is no part of this identifier: it is the natural logarithm, and a call naming any other base is not this operation (11.1.12) | none |
| `log10` | 1 — the value | none |
| `log1p` | 1 — the value | none |
| `lookup` | **one per key column of the processed table, in that table's own key-column order** — which is the payload's `columns` order with the `value` column removed, never its `dimensions`, which is a set of names rather than a sequence (11.1.24), and never the order the call's keywords were written — each a column reference, or a literal where a bare dimension value was written | `table` (text) always; `table_fingerprint` (text) always; `on_missing` (text) always: `raise`, `nan` or `fill`; `fill_value` (decimal, nullable) always — null under `raise` and `nan`, which makes a null here the ordinary case |
| `max` | 1 — the per-period value | none |
| `mean` | 1 — the per-period value | none |
| `min` | 1 — the per-period value | none |
| `mortality.at` | **one per dimension read, in the order the structure takes them**: `aggregate` → age then any further keys; `select_ultimate` → age, duration, then any further keys; `joint` → age_1, age_2, then any further keys | `mortality` (text) always: the wrapper's `source_sha`, over a recipe that carries the base's content hash beside the convention, so it moves when a rate does; `structure` (text) always; `age_basis` (text) always; `dimensions` (text) always, comma-joined **in operand order**, which is what lets this read bind by name where `lookup` above binds only by position; `table` (text) always; `table_fingerprint` (text) always; `select_period` (whole number) **conditional** — present only where the basis has one, absent otherwise (11.1.10); `on_missing` (text) **conditional** — the base's miss policy, in 11.1.24's three values, and **where it is absent a consumer applies `raise`** (11.1.10, which also says a producer carrying a base's non-default policy is what closes the gap) |
| `norm_cdf` | 1 — the value. Excel's `NORM.S.DIST(z, TRUE)` is the same call, never a second identifier (11.1.12) | none |
| `not_` | 1 — the predicate | none |
| `projection.accumulate` | **3 — the initial value, the multiplier, the addend. The receiver is not an operand at all**, and this is the one exception to receiver-first in the vocabulary: the accessor is reached on a column that supplies the axis rather than a value the fold consumes | `reverse` (flag) always: whether the recurrence runs back from each policy's own last period (11.1.20) |
| `projection.at_period` | **2 — the value, then the fill value** | `relative_period` (whole number) always |
| `projection.broadcast_to_periods` | 2 on current emission — the per-policy value, then the list supplying its length (explicit `like` or `col("month")`). Historical 1-operand records remain recognizable but outside §11.1.32's execution domain | none |
| `projection.cumulative_survival` | 1 — the decrement or survival column | `start_at` (decimal, nullable) always — **null is how end-of-period timing is recorded**, and 1.0 how beginning-of-period is; `from_survival` (flag) always |
| `projection.next_period` | **2 — the value, then the fill value** | none |
| `projection.previous_period` | **2 — the value, then the fill value** | none |
| `projection.prospective_value` | 2 — the cashflows, then the discount operand | `timing` (text) always; `discount_kind` (text) always: `rate` or `factor`, which is the **only** thing saying which of the two the second operand is |
| `projection.remaining_sum` | 1 — the value | none |
| `projection.with_period` | 1 — the list column | `period` (whole number) always; `value` (decimal or whole number) always. Several periods overridden at once are nested calls, one per period, not a second identifier |
| `projection_frame.anniversary_mask` | 0 or more — the frame columns the expression actually reads: none on a shared calendar grid, each policy's own anchor column on a per-policy axis | `schedule` (text) always |
| `projection_frame.period_dates` | 0 or more, by the same rule | `schedule` (text) always |
| `projection_frame.t_years` | 0 or more, by the same rule | `schedule` (text) always |
| `projection_frame.year_fractions` | 0 or more, by the same rule | `schedule` (text) always |
| `projection_set` | 0 or more, by the same rule — none on a shared grid, the per-policy anchor or horizon columns on a jagged axis | `frequency` (text), `until` (text), `valuation_date` (text, an ISO date) and `until_value` (**whole number or text** — a number, or the name of the column carrying a per-policy horizon) are all always present and all nullable, and 11.1.1 says which form nulls which; `start` (text) **conditional** — the synthetic and schedule forms only; `n_periods` (whole number) **conditional** — synthetic only; `schedule_source_sha` (text) **conditional** — schedule form only. **The key set differs by form**, so a producer must not assume a fixed one |
| `replace` | 3 — the value, the values replaced as a sequence literal, and either their replacements as a sequence literal of the same length or one scalar literal standing for all of them | none |
| `rollforward` | **none, always** | `fingerprint` (text) always: the compilation's own published identity, the machine alone (§16); `schedule` (text) always: the `source_sha` of the schedule the machine runs on |
| `rollforward.increment` | the compilation's own operand run — see the note below | `fingerprint` (text) always; `schedule` (text) always; `label` (text) always; `shared` (flag) always |
| `rollforward.state` | the compilation's own operand run | `fingerprint` (text) always; `schedule` (text) always; `state` (text) always; `point` (text) always; `shared` (flag) always |
| `rollforward.struct` | the compilation's own operand run | `fingerprint` (text) always and `schedule` (text) always, **and nothing else** |
| `round` | 1 — the value | `decimals` (whole number) always; `mode` (text) always: `half_to_even` or `half_away_from_zero` (11.1.8 says why it is never omitted) |
| `round_sig_figs` | 1 — the value | `digits` (whole number) always — significant figures, not decimal places, which is why this is its own identifier and not `round` carrying a second attribute (11.1.12) |
| `schedule.anniversary_mask` | 0 or more — the frame columns the expression reads | `schedule` (text) always: the schedule object's `source_sha` |
| `schedule.contract_boundary` | 0 or more | `schedule` (text) always; `end_date_column` (text, nullable) always — **written even where nobody passed one** |
| `schedule.is_in_force` | 0 or more | `schedule` (text) always; `end_date_column` (text, nullable) always |
| `schedule.per_policy_period_count` | 0 or more | `schedule` (text) always |
| `schedule.per_policy_period_dates` | 0 or more | `schedule` (text) always |
| `schedule.period_dates` | 0 or more | `schedule` (text) always |
| `schedule.year_fractions` | 0 or more | `schedule` (text) always |
| `sign` | 1 — the value | none |
| `sqrt` | 1 — the value | none |
| `sum` | 1 — the per-period value | none |
| `str.to_date` | 1 — the text | `format` (text, nullable) always — null says the producer inferred it and the parse is unreproducible (11.1.7); `strict` (flag) always; `exact` (flag) always |
| `to_float` | **1 — the value** | none |
| `to_integer` | **1 — the value** | none |
| `to_list` | **1 — the array** | none |
| `to_text` | **1 — the value** | none |

**The three rows whose operand run is not a call's argument list.** `rollforward.state`,
`rollforward.increment` and `rollforward.struct` all carry the same run: the compiled state
machine's own operands, walked out of the compilation in declaration order — each state's
initial value, then, per transition in order, every operand the transition reads, with a
state-reference node (§12.1's `0x06`) standing wherever the machine reads a running balance.
Duplicates are kept, because the run is the machine's own order and not a set of reads. The
three differ only in their attributes. That run is not something a consumer can shorten or
sort: it is why the compilation's `fingerprint` attribute is carried as well, and why §16
keeps the machine itself out of these bytes. **All four rollforward calls carry `schedule`
beside `fingerprint`**, because the fingerprint is the machine alone and leaves out the
schedule the machine runs on (§16): one machine run on two schedules is one fingerprint and
two runs, and the pair is what names the run.

**`fill_value` has two homes, and a producer must not unify them.** On
`projection.at_period`, `projection.previous_period` and `projection.next_period` it is a
**positional operand** — the second one — because a fill may be a column or an expression as
easily as a number. On `lookup` it is an **attribute**, because a miss policy is one flat
setting of the read. One concept, two homes, and the schedule states homes rather than names
for exactly this reason: an implementation that read "fill_value" as one thing everywhere
reproduces neither node.

**What a conforming producer will add.** Two things this schedule does not yet fix, both
stated rather than made silently.

1. **The schedule is a shape, not a semantics.** It says where each value sits and what
   scalar it is; what these operations *compute* is stated only for the ninety-nine
   of §§11.1.1–11.1.10, §§11.1.12–11.1.41 and §§16.1–16.2, and section 11.1 says a consumer
   must not rely on the rest
   having semantics this document has defined. Reproducing a digest and reproducing an answer
   are two different claims, and this section supports the first.
2. **Several attributes carry an engine's own spelling rather than a vocabulary of this
   document's** — a join's `how`, a projection's `frequency`, a schedule's cadence, a parse's
   `format`. Each is named where it arises (11.1.1, 11.1.2, 11.1.7); a conforming producer
   will state them in closed vocabularies, and until it does they are text a consumer matches
   rather than tokens it dispatches on.

#### 11.1.12 `abs`, `sign`, `sqrt`, `cbrt`, `exp`, `log`, `log10`, `log1p`, `norm_cdf` and `round_sig_figs`

These ten are the maths a projection is written with. They are the operations behind a
force of mortality taken as a logarithm, a continuous discount factor taken as an
exponential, a volatility taken as a square root, the N(d1) of a guarantee priced as an
option, and a headline figure kept to three significant digits.

**The semantics.** `abs` returns the value with its sign dropped and `sign` returns minus
one below zero, one above it, and zero at it; **the `sign` of a NaN is NaN**, since a NaN is
neither below zero nor above it nor at it, and the `sign` of an infinity is that of its
direction. `sqrt` and `cbrt` return the square and cube
roots; `exp` returns *e* raised to the value; `log` returns the natural logarithm, `log10`
the logarithm to base ten, and `log1p` the natural logarithm of one plus the value, which is
the form that keeps its accuracy for a value near zero. `norm_cdf` returns Φ, the standard
normal distribution function: the probability that a standard normal variable is at most
the value, a double whatever numeric type the value arrives in. `round_sig_figs` keeps the leading
`digits` significant figures of the value and zeroes the rest: three of them leave 1234.567
as 1230.0 and 0.001234567 as 0.00123, which is why it is its own identifier and not `round`
carrying a second attribute — significant figures are not decimal places, and a vocabulary
recording both under one name would publish one identity for two calculations. A null value
stays null under all ten. The logarithm of 0.0 is `−∞` under `log` and `log10`, and so is
`log1p` of −1.0, the value binary64 gives the pole.

**A flag is read as its 0.0 or 1.0.** A Boolean operand — a stored flag, a comparison written
as the operand (11.1.26), or a result of `and`, `or` or `not_` (11.1.27) — is the number section
11.1.25 reads it as in arithmetic, true 1.0 and false 0.0, and each of the ten answers `f64`, per
policy and per period alike: `abs`, `sign`, `sqrt`, `cbrt` and `round_sig_figs` of a true flag
are 1.0 and of a false one 0.0; `exp` of a false one is 1.0, `log1p` of a true one ln 2,
`norm_cdf` of a false one 0.5, and `log` and `log10` of a true one 0.0 and of a false one
`−∞`. A consumer types the answer `f64`, never `bool`. `log` of a flag is rarely what a model
means, and it answers what `log(0.0)` answers rather than being refused: one reading of a flag
holds wherever a number is read.

**A tie rounds half away from zero, for either sign.** Keeping the leading figures says
where to cut and not which way to go when the value sits exactly between the two answers,
and that is the one input the digits do not decide: 2.5 to one figure is 3.0 and −2.5 is
−3.0; 1245.0 to three figures is 1250.0 and 102.5 is 103.0. This is the rule every document
written under this format was produced under, and it is stated here rather than made an
attribute, because an attribute nobody would set to the other value would move every
`round_sig_figs` node's identity to carry a setting the model never made. The cost is
named: **a model wanting a tie taken to the even neighbour cannot say so through this
identifier** — `round` carries a `mode` (section 11.1.8) and is the operation for it. An
implementation that reaches for its host language's own rounding should check which way that
takes a tie before using it; several take it to the even neighbour and would answer 2.0
here.

**A whole number keeps its figures in whole-number arithmetic.** On an `i64` value
`round_sig_figs` answers `i64`, and the figures are counted and the rest cut off exactly, never
through a double: 781098 to one figure is 800000, `2^53 + 1` to two is 9000000000000000, and
`2^63 - 1` to two is 9200000000000000000. A scaling by a negative power of ten in binary64 lands
a hair under such an answer, and a cast back to an integer truncates it to 799999; an
implementation that rounds a whole number through a double does not compute this operation. An
answer that rounds up past `i64` — `2^63 - 1` to ten figures — is refused by name, never wrapped.

**A whole number keeps its type under `abs` and `sign`; the six held to a tolerance answer a
double.** On an `i64` value `abs` and `sign` answer `i64`, in whole-number arithmetic and never
through a double: `abs` of `−(2^53 + 1)` is 9007199254740993, where the double nearest it would
answer 9007199254740992, and `sign` of it is −1. The absolute value of the least `i64`, `−2^63`,
is `2^63`, which no `i64` holds: it is outside the portable domain, as an integer result is in
section 11.1.25, and a consumer claiming only this domain must refuse it, never wrap it. The
reference producer refuses it by name. `sqrt`, `cbrt`, `exp`,
`log`, `log10` and `log1p` answer `f64` over an `i64` as `norm_cdf` does, per policy and per
period: `sqrt` of 4 is 2.0 and `exp` of 1 is *e*, and a consumer types the answer `f64`, never
`i64`. **An `i64` value past `2^53` in magnitude under one of these seven is outside the portable
domain**, as the same value beside a double is in arithmetic (section 11.1.25): no double names
every such whole number, so a producer may answer the call of the double nearest it — the
reference producer and the reference reader answer `sqrt` of `2^62` as 2147483648.0 — and a
consumer may refuse the line by name, as the JAX engine does (`mixed.2p53`). `abs`, `sign` and
`round_sig_figs` keep the whole number exactly and have no such edge.

**A double is read as the fifteen significant figures a spreadsheet holds.** On an `f64`
value the figures kept are those of its fifteen-significant-digit decimal — the value's exact
decimal expansion cut to fifteen significant digits, a sixteenth digit of 5 or more going away
from zero, a double that is itself exactly a sixteen-digit tie included, as section 11.1.35
reads an operand of `excel.round` — and that decimal is rounded to `digits` figures, a half
going away from zero as above. The answer is the double nearest the result. 0.15 is the double
0.1499999999999999944…, which reads as 0.150000000000000, so to one figure it is 0.2; 0.285 to
two figures is 0.29, 2.675 to three is 2.68, 1.005 to three is 1.01, and 781098.0 to one is
800000.0. From fifteen figures up the answer is the fifteen-digit value itself, so
0.30000000000000004 to seventeen figures is 0.3. Two routes answer differently and neither
computes this operation: rounding the double's exact value answers 0.1 for 0.15 and 2.67 for
2.675, and scaling by a power of ten in binary64 rounds twice, so 781098.0 to one figure comes
back 799999.9999999999. The reading is a double's alone. A whole number keeps every digit it
has, as the paragraph above says, so `12345678901234567` to sixteen figures is
`12345678901234570` as an `i64` and `12345678901234600.0` as an `f64`.

**Where a producer keeps the figures exactly, and what it does elsewhere.** In binary64 the
figures are exact for a magnitude from `10^(digits − 23)` — `10^−8` at fifteen figures or more
— to below `10^37`: there the power of ten that scales the fifteen figures to a whole number is
a double or an exact product of doubles, and so is the one that hands the answer back. Each
bound is compared exactly. Zero, a NaN and an infinity are their own answers at any digits.
**Outside that range an engine may answer by its own native rounding** — the value scaled by
a power of ten in binary64, rounded to a whole number and scaled back — and the reference
producer and the JAX engine both do, the JAX engine taking the power of ten as the reference
producer's engine takes it, so the two answer the same double for every normal value (a
subnormal one, below `2^−1022`, is its own answer on the JAX engine). That answer may sit a few
units in the last place from the fifteen-digit reading: 1e-30 to three figures is
9.999999999999999e-31, and 1e300 to one figure 1.0000000000000006e300. Where the value lies
within a few units of a half of its kept figures it may land on the other side of the half, a
figure away from the reading. Neither is refused: a floating-point residue where nought was
meant — `3e-24` left by a cancellation — rounds, to `3e-24` at one figure, rather than stopping
a model on noise. The reference reader keeps the figures exactly at every magnitude, so outside
the range an engine's answer and the reader's may differ by those amounts, and that is this
clause, not a disagreement between them. An answer past the largest double is refused by the
reader; the engines answer the value itself there.

**`log` is the natural logarithm and this vocabulary names no other.** An engine whose
method takes a base is not writing this operation when a base is given, and a producer must
leave such a line an engine fragment rather than recording the base as an operand or the
default as a literal. The reason is that the default is not a number a document can carry:
written down it is a truncated double, so two producers agree only as far as they truncate
alike, and a consumer computing a change of base rather than calling its own natural
logarithm does not reproduce the column at all. `log10` is an identifier for the same
reason from the other side: it is a function an engine has, not a division by a written-down
constant.

**Three are exact and seven are held to a tolerance.** `abs`, `sign` and `round_sig_figs` are
decided by the value's digits — for `round_sig_figs` of a double, its fifteen-digit reading —
and, at a tie, by the rule above: two implementations
that agree on the input agree on the output bit for bit, and a consumer may check them
exactly — for `round_sig_figs` of a double, over the range above. `sqrt`, `cbrt`, `exp`, `log`,
`log10`, `log1p` and `norm_cdf` are transcendental functions of a binary float, and two
libraries computing one of them correctly may still part company in the last place. **The
contract for those seven is agreement to a relative tolerance of 1e-12, not bitwise
identity**, and a conforming consumer must not report a difference within it as a difference
in the model. `sqrt` alone could hold a bitwise contract — IEEE 754 requires it correctly
rounded — and it is stated with the family anyway, because a consumer checking a column of
numbers has no way to know which of the seven produced it.

**`norm_cdf` is held to the mathematical Φ, its lower tail included.** The 1e-12 is relative
to Φ itself wherever Φ is a normal double, which is every value from −37.5 up; there Φ is
4.6e-308. Below that the answer is subnormal, and from about −38.5 it is zero, so a relative
tolerance means nothing and the line rule below decides. Four values are exact: a null stays
null, a NaN stays a NaN, +∞ answers 1.0 and −∞ answers 0.0. The tail is where an
implementation is most easily wrong. The textbook form `0.5 · (1 + erf(x / √2))` subtracts two
nearly equal numbers there: it is right to about eight digits in the body, and at −8.36 it
answers 0.0 for a Φ of 3.1e-17. The complementary form `0.5 · erfc(−x / √2)` keeps every
digit; its error comes only from rounding `x / √2`, grows like x²·ε, and is about 1.8e-13 at
its worst near −37. **No agreement with Excel's own bits is claimed**: Excel's algorithm is
unpublished, and its cached values sit within about 1e-14 of Φ over the range workbooks use,
so a reconciliation against a workbook is held to that order and not to the last bit.

**One function, one identity.** Excel's `NORM.S.DIST(z, TRUE)`, its older `NORMSDIST(z)` and
a textbook's N(z) are this one call, so a model converted from a workbook and one written from
the formula publish one digest. A producer may offer an Excel spelling as a second door to
the call, but it must record `norm_cdf`, never a second identifier. `NORM.DIST(x, mean, sd,
TRUE)` is written standardised, as `norm_cdf` of `(x − mean) / sd`: the mean and the standard
deviation are arithmetic the record already states. The density, `NORM.S.DIST(z, FALSE)`, is
`exp(−z²/2) / √(2π)` in operations this section already holds, and is not an identifier of its
own.

**Two engines agree on a line to 1e-12 of its scale.** The tolerance above is one
operation's; this is the whole document's, and it is the rule a reader holding two result
files and this artifact applies to them. Two finite results agree when `|a − b| ≤ 1e-12 ·
scale`, where the scale is **the line's**: the largest magnitude among the node's own values
and the values of every node its `reads` names, over **that policy's** whole timeline, taken
over both results. Per policy before any maximum, so that no policy lends another its
allowance. A line whose scale is 0 is compared exactly. The number is 1e-12 — the number the
seven above already carry — and there is one of it: no new per-operation tolerance is
introduced, and the ones this section states stand.

**Why the scale is the line's and not the value's.** Floating error is proportional to the
magnitudes that were added and never to what is left after they cancel. A closing balance
struck from operands near 17,000 that cancels to nothing differs between two correct
implementations by about 7e-10 — a ten-thousandth of a trillionth of the operands, and the
whole of the answer if the remainder is what it is measured against. The node's own values
miss those operands, and the model's largest value would let a sum assured forgive a
mortality rate. What the node reads is the smallest scope that sees the cancelling operands
and the largest that sees no unrelated ones, and it is a scope this format already names on
the record.

**What is exact, and the one thing that is not compared.** Integers, Booleans, dates and
strings; the shape and length of every list; where the nulls are; whether a value is a NaN,
and which way an infinity points. The sign of a zero is not compared: which zero a model
produced is a value the model states — section 11.1.25's division observes it and section
12.1's byte grammar hashes the two apart — and a comparison of results is not where that
question is asked.

**The band is five decades wide, and it is stated rather than hidden.** Reassociation — the
same sum taken in another order, which a second implementation is free to do and a fused
multiply-add does by itself — moves a line by about 1e-13 of it. The rule forgives 1e-12 of
it. Inside that decade no comparator can tell an arithmetic-order difference from a wrong
answer, and a reader must not report a difference inside it as either. **A product the record
writes is rounded before anything reads it**: section 11.1.25 states `a + b * c` as two
operations, each rounded, and so does every entry that writes a product beside a sum inside
itself — the recurrence of section 11.1.20, a rollforward's growth or charge before its next
step, a curve's line between two knots. An implementation that fuses a product into the sum
reading it rounds once, and under a comparison, a `when`, a floor, `//` or `%` that place is
a whole step — `0.5 + 5 * 0.011 >= 0.555` is 0 by the record and 1 fused — so a fused answer
is not inside this band; it is a different calculation. **One residue is disclosed rather than
closed**: a call of this section answered inside its own tolerance may sit one place from
another implementation's, and a threshold set at that call's own value can then answer the
other way on the two (the normal distribution function and the cube root are the two seen to
do so).

**A conforming comparison states what it compared.** Its report is written in
`gaspatchio-graph-compare/v0-preview.2`, carrying the artifact's `graph_fingerprint` and
beside it the `document_digest` of the written document it was handed — null where that
document carries none — which section 13.1 records on every citation of a document and
never compares, the scope both result files were written under — the model's final schema, or every
value-bearing node — both sides' input digests and whether the two agree, whether rows were
matched by a policy identity or by position, and per node the largest ratio to the scale,
the scale itself, the verdict and the largest absolute difference. **That last is stated
for a line the band decided and is absent on a line the exact classes decided**, where the
class that parted them stands in its place: two integers one apart are not a distance
apart, and a zero written there would say they were identical. The fixed-floor reading
`|a − b| ≤ 1e-10 + 1e-12·|ref|` is printed beside every verdict, because a reader who has
been reading that number for a year is owed it.

**Rows are paired by the identity the results record, and by position only where the order
is shown.** A result manifest's `row_identity` names the columns that together name each row
once — the policy-id column, then the scenario column where a scenario axis crossed the book
— or is null where none does; a manifest written before it named more than one column states
one name, which is read as that one column. A comparison pairs two results' rows on the
columns the caller names, or else on the columns both manifests record. Where they record no
one identity between them, it pairs by position only where position is shown to be the
pairing: the columns one side records hold the same values in the same order on the other,
or both sides read one book — `inputs_digest` is taken over the rows in the book's order
(section 7), and both results are of one artifact. Otherwise it refuses, naming the columns a
caller would name. **A pairing by position that is wrong still produces a verdict** — the
same policies in another order disagree, and two books whose values happen to line up agree
— so it is never the fallback. The report states which it was and on which columns:
`rows_matched_by` (`identity` or `position`) and `rows_matched_on`, the columns paired on or
shown in one order, empty where one book showed it.

**Three verdicts, not two.** A result file carrying only the final schema does not carry
the reads the scale needs, and the scale taken from the values in hand can only be smaller
than the true one: a line that passes that reduced test would pass under any larger scale
and *agrees*; a line that fails it with a read absent is *indeterminate*, stated with the
scale those reads would have to supply, and never a disagreement; *disagree* is reserved
for the full rule. A result the scope requires and a file does not carry is recorded as
missing, and neither a missing result nor a comparison that compared nothing is agreement.

**Between two versions of a model the rule is a label.** Two runs of two artifacts do
not agree or disagree: one model was edited, and a reader asks what moved. Section
14.2's `values` member applies this rule to each moved line as `within_band`, each side's
scale taken from what its own document says the line reads, and lists the line as moved
whichever way it falls.

**The operand is the value, and for nine of them there is nothing else.**
`round_sig_figs` carries `digits`, which is one flat typed value and therefore may not vary
by policy; a model whose significant figures vary by row is not writing this operation.
`digits` is a whole number of at least one: a producer refuses a smaller count where it is
written, and a consumer refuses a document carrying one.

**One value at a time.** Where the value is a per-period column (section 10's list form),
each period's own value is answered; none of the ten has a view across periods.

**What a conforming producer will add.** The trigonometric and hyperbolic siblings, the
logarithm to a stated base, and the inverse of the normal distribution function are not in
this vocabulary. The first two and the inverse are absent because no actuarial line in
evidence has reached for them, and an entry nothing writes is one nobody can check; the name
`norm_inv` is reserved for the inverse, and a constant fixed before the projection — the
99.5% point of a capital shock — is a number a model computes once and writes down. The
logarithm to a stated base is absent for the reason given above. Until then those lines stay
engine fragments and say so.

#### 11.1.13 `fill_null`, `fill_nan`, `is_null`, `is_not_null`, `is_nan`, `is_not_nan`, `is_finite` and `is_infinite`

These eight are what a model says about a value that is not there. They are the operations
behind a model point that arrived with no smoker status, a lookup that answered a key its
base does not carry, and a discount factor that divided by something which turned out to be
zero.

**A null and a NaN are two different absences, and this vocabulary keeps them apart.** A
null is a value that was never present. A NaN is a value an arithmetic produced and cannot
name — zero over zero, the logarithm of a negative rate. `is_null` answers the first and
`is_nan` the second, and a model that tests one where it meant the other passes every row it
has data for. They are separate identifiers rather than one carrying a flag for exactly that
reason.

**The semantics.** `is_null` returns true where the value is missing and false where it is
present; `is_not_null` returns its complement, and neither ever answers null. `is_nan`
returns true where the value is NaN and false where it is a number; `is_not_nan` returns its
complement. **Both of the NaN tests answer null for a null value**, because a value that is
not there is neither a NaN nor a number, and answering false would assert something about a
value the model does not have. `is_finite` returns true for a value that is neither infinite
nor NaN, `is_infinite` true for an infinity of either sign, and both answer null for a null
by the same rule. `fill_null` returns the value where it is present and the fill where it is
missing; it does not touch a NaN, which is present. **A fill that reads a column fills each
period one value at a time**, as a fill that is a value does: over a per-period value a fill
that is one value per policy — a scheme's own default premium — reaches every missing period
of its policy, and a per-period fill reaches the same period; a policy with no run has no period
to fill and stays null. A per-period fill for a per-policy value would answer a list for one
number and is outside this entry; the reference producer refuses it by name, for `fill_nan` as
for `fill_null`. **`fill_null`'s bounded domain is a value
and a fill of one family** — two of `i64`, `f64` and `bool`, answering the type the two share
(`f64` where either is, an `i64` mixing only inside the exact integer range of section
11.1.25, and a `bool` fill standing as the 0 or 1 it indicates), or two `str`, two `date` or
two `datetime` — and a fill of another family than the value's, or an `i64` or `f64` fill
for a `bool` value, is outside it: the reference producer refuses either where the line is
written rather than converting one side into the other's type. **An `i64` value past `2^53` in
magnitude meeting an `f64` fill is outside the portable domain**, for `fill_null` and `fill_nan`
alike, as the same pair is in arithmetic: no double names every such whole number, so a producer
may answer the double nearest it — the reference producer fills `[2^53 + 1, null]` with 0.5 as
`[9007199254740992.0, 0.5]` — and a consumer may refuse the line by name, as the reference
reader does (`arithmetic-outside-exact-numeric-range`).

**`fill_nan` is the fill for the other absence, and it does not touch a null.** It returns the
fill where the value is NaN and the value everywhere else: a number, an infinity of either
sign and a null alike. An infinity is a value an arithmetic produced *and named*, so it is not
filled. **A null stays null**, because a value that is not there is not a NaN — the reason
the NaN tests answer null for it — and a model whose NaN and null both mean nought writes both
fills, so that the record says it assumed each. The fill is an operand under the rule below, so a
scheme's own default column fills as readily as a fixed zero. The answer keeps the value's
shape: over a per-period value, a fill that is one value per policy reaches every NaN period
of that policy and a per-period fill reaches the same period (section 11.1.18); a per-period
fill for a per-policy value would answer a list for one number and is outside this entry. A
NaN where the fill itself is null takes the null. The bounded domain is a value and a fill of
`i64` or `f64`, and the answer is the type the two share — `f64` where either is, with an
`i64` mixing only inside the exact integer range of section 11.1.25.

**The negations are their own identifiers and not the affirmatives under `not_`.** A
producer must not record `is_not_null` as `not_(is_null(x))`, or `is_not_nan` as
`not_(is_nan(x))`. Two reasons, and either is sufficient. The record is meant to say what
the model says, and a reader tracing a line an actuary wrote as one operation should not
meet two. And the composition is not the same calculation everywhere: a producer whose
negation over a per-period column is arithmetic over a numeric mask hands back a numeric
column where the direct test hands back a Boolean one, so a rewrite that looks like an
identity changes the type of the answer.

**The fill is an operand and never an attribute.** What fills a gap is as often a column as
a number — a scheme's own default premium, last quarter's rate — and an attribute is one
flat typed value (section 12.1) which could carry neither. A vocabulary that put the fill in
the configuration would record the constant fills correctly and drop every varying one,
which is worse than not recording the operation at all: it is a document reading as a
complete account of a calculation half of which it has lost.

**A fill from the neighbouring rows is not this operation.** An engine whose `fill_null`
also offers to carry the last present value forward, or to fill only so many gaps, is
offering a different calculation — one whose answer depends on the order the rows stand in,
or which leaves some gaps unfilled. A producer must leave such a line an engine fragment.

**These eight are where the vocabulary's silence about type is visible, and this is what a
consumer may rely on.** The operation tree carries no data type, so the identifier alone
does not say whether the value tested was a floating-point number or a whole one — and a
whole number cannot hold a NaN or an infinity at all. **Over a whole-number column `is_nan`
and `is_infinite` answer false, `is_not_nan` and `is_finite` answer true, and none of them
fails.** A producer that raised there would be refusing a line that is merely trivially
answered. **Over a whole-number value `fill_nan` replaces nothing and does not fail either**,
for the same reason: every value stands as it was, in the type it shares with the fill, so
`fill_nan(x, 0.0)` over an `i64` column answers its values as `f64` and `fill_nan(x, 0)`
answers them as `i64`.

**Past the whole numbers this specification states no answer, and a consumer must not read
one in.** A Boolean, a string, a date and a decimal cannot hold a NaN either, and the
reference producer refuses all four tests over each of those four types rather than
answering false: its engine has no kernel for the test over any of them, and that is as
true of the line recorded as this operation as it was of the same line recorded as an
engine fragment. An engine that
took the rule above as licence to answer `false` there would disagree with a producer that
raises, which is the opposite of what stating the rule is for. So the rule is stated for
the case where an answer is genuinely available and withheld where it is not: over any
other type a consumer must accept either an answer or a refusal, and a producer is
conforming whichever it does. `fill_nan` is held to the same rule over the same four types,
and the reference producer refuses it there for the same reason — its engine's NaN fill is
the NaN test and the fill, and the test has no kernel over any of them.

**What the artifact carries beside the tree closes part of this gap, and a consumer needs
to know which part.** Types are recorded per *column*, not per operation: every node
records the type it resolved to (section 8), the input columns among them. Where the test
reads a column directly, that column's own type is the type the test was applied to, and a
consumer can read it off the artifact. Where the test reads the result of an expression it
cannot: `is_nan(a / b)` over two `i64` columns records `i64`, `i64` and, on the node itself,
`bool` — the `f64` the division produced appears nowhere, because no node stands for the
division alone. A consumer that needs that type must re-derive it from the operand types
and the operations between them, under its own engine's promotion rules.

**One value at a time.** Where the value is a per-period column (section 10's list form),
each period's own value is tested or filled; none of the eight has a view across periods,
and neither fill ever carries a value from one period into another.

#### 11.1.14 `sum`

`sum` folds one policy's per-period column to one number: the present value of a whole
discounted cashflow, the total premium over a projection, the claims paid across a lifetime.
It is the operation behind the line an actuary writes as
`(cashflow * discount_factor).list.sum()` and reads as "the PV".

**The semantics.** For a value with `n` periods the result is the sum of periods `0` to
`n - 1` inclusive. There is no `reverse`: a fold over the whole axis reaches the same number
in either direction, and an attribute that could not change an answer would be a distinction
nothing is on either side of. There is no `start_at` and no seed: the sum of an empty run is
nought, and the sum of one period is that period. **An empty sum is +0.0**, and a sum of
doubles is taken from IEEE's additive identity, −0.0, so one period of −0.0 sums to −0.0: the
sign decides a division by the total (§11.1.25), and §11.1.12 compares which way an infinity
points. **The order is the period order**: a fold over one policy's run — `sum`, `mean`,
`cum_sum`, `cum_prod` and `remaining_sum` — is the binary64 fold from the first period to the
last, `remaining_sum` from the last back, each step rounded, and is exact to the bit on every
side rather than inside the band. `70000 // [0.2, -2.0, 0.2, 1.5].list.sum()` is −700000: the
total in period order is −0.10000000000000009, where an exactly rounded total would be
−0.09999999999999998 and the floor a whole step away. A fold across policies — a portfolio
total, `run_aggregated`, a batch door — is not ordered by this sentence and keeps §11.1.12's
band, since batching reorders it.

**The shape changes, and this entry is where that is stated.** This operation takes a `list` and answers `scalar`;
its siblings in §§11.1.15–11.1.17 make the same shape change.
11.1.9 left that open — an operation whose result has a different shape from its operand had
no way to say so — and it is said here, per entry, in prose, alongside the operation whose
shape it is a fact about. It is not a new field on the node record: a node already states the
shape of its own answer, and its operand's node states the shape of the operand, so a second
field would be a third copy free to disagree with the two that already exist.

**The fold is along the periods, and along nothing else.** 11.1.9's paragraph applies here
word for word: the operand is one policy's own sequence of periods, and no value of one
policy reaches another's answer. An engine's method of the same name applied to a per-policy
column folds down the rows of the model-point file — a different calculation, whose answer
depends on the order those rows happen to stand in, and one this vocabulary does not name. A
producer must not write this identifier for it; such a line is an engine fragment and the
node says so.

**A null period makes the total null**, and the four entries state it once, here. A period
carrying no value is not a period carrying nought, and a total is one number with no room to
say that a period went missing underneath it: `[10.0, null, 30.0, 40.0]` answers null through
all four. Reading the null as absent to the fold would answer `sum` 80.0, `mean`
26.666666666666668, `min` 10.0 and `max` 40.0 — the answers `[10.0, 30.0, 40.0]` gives, each
of them a number with nothing wrong on the face of it and a period missing from under it.
This is the rule 11.1.9 states for a running fold, reaching the place a total is taken, which
is the one number a supervisory reader signs.

**A run of nothing but nulls answers null, for all four.** A run whose every period is
missing is not a run of no periods, so it is not the empty run this entry sums to nought:
`mean`, `min` and `max` already answered null there, as §§11.1.15–11.1.17 state, and `sum`
answers null with them. The empty run itself is untouched and still sums to nought, because a
fold that reaches no period has lost none.

**A null outer list answers null, for all four.** A policy whose whole column is null has no
periods for the fold to reach at all, which is a different thing from a policy whose periods
are each missing; the answer is null either way, and the distinction is kept because a policy
with an empty list is the run of no periods and takes the answers above.

**A total of whole numbers is a whole number, exact.** Over an `i64` run `sum` answers `i64`,
taken in whole-number arithmetic and never through a double: `[2^53 + 1, 2^53 + 1]` sums to
18014398509481986, where a total in doubles answers 18014398509481984. A total outside `i64` —
`[2^63 − 1, 1]` — is outside the portable domain, as an integer result is in section 11.1.25: a
consumer claiming only this domain must refuse it, never wrap it. The answer is the total, so a
run whose running total passes the range and comes back — `[2^63 − 1, 1, −1]` — sums to
`2^63 − 1`. The reference producer takes the total exactly and refuses one outside `i64` by
name, naming the column; it totals a run of flags as the count it indicates, an `i64`.

**A modeller who means nought writes it**, and this is stated once, here, for the family and
for the folds of 11.1.9, 11.1.19, 11.1.20 and 11.1.21 that follow the same rule. A missing
period read as a nought is an assumption, and `fill_null` (11.1.13) is where this vocabulary
holds an assumption: `[10.0, null, 30.0, 40.0]` filled with nought before the total sums to
80.0, and the filling is a node of its own with its own digest, so a reviewer reads the
assumption rather than inferring it from a total that never mentioned the hole.

**An edge into `sum` is `DIRECT` / `AGGREGATION`** (section 9), by the same rule and for the
same reason as `cum_sum`: every period is in the answer, and an impact cone told this was a
transformation of one period's value would be told the opposite of the truth.

#### 11.1.15 `mean`

`mean` answers the average of the periods of one policy's own column: the average reserve
held over a projection, the average credited rate a contract earned.

**The semantics.** The sum of the periods, divided by their count. **The denominator is that
policy's own periods and never the grid's**, which is what
the period-axis paragraph above fixes: a per-policy timeline gives each policy its own number
of periods, and the two denominators differ for every policy but the longest. A level
timeline hides the difference, which is what makes choosing the wrong one a valuation error
that survives testing. A null period makes the answer null, by the rule 11.1.14 states for
the family: `[10.0, null, 30.0, 40.0]` answers null, and neither 26.666666666666668, the
average of the periods that carry a value, nor 20.0, the average a null read as nought would
give. A run of nothing but nulls answers null too, having no period to average either way.
**The answer is `f64` whatever numeric type the periods are**: `[100, 101, 101, 101]`
averages 100.75, and a consumer types it `f64`, never `i64`. **A run of `i64` holding a value past
`2^53` in magnitude is outside the portable domain** for `mean`, as it is for the maths calls of
11.1.12: the average is a double and no double names every such whole number, so a producer may
total the periods in doubles and answer the double nearest the average — the reference producer
and the reference reader answer `[2^53 + 1, 2^53 + 3]` as 9007199254740994.0 — and a consumer may
refuse the line by name, as the JAX engine does (`mixed.2p53`).

The shape change, the period-axis rule and the `DIRECT` / `AGGREGATION` edge are `sum`'s word
for word.

#### 11.1.16 `min`

`min` answers the least of the periods of one policy's own column: the lowest the account
value fell to over a projection, the worst funding level a contract reached.

**The semantics.** The least value among the periods. A null period makes the
answer null, by the rule 11.1.14 states for the family: a period carrying no value could have
been the least of them, so `[10.0, null, 30.0, 40.0]` answers null and neither the 10.0 a
missing period read as absent would give nor the 0.0 it would give read as a nought. A run of
nothing but nulls has no value to be least and answers null. **The answer is one of the
periods' own values, in their type**: a run of `i64` answers `i64`, and a run of flags answers
`bool` — whether every period was set, `[True, False, True, True]` answering `False` — and
never the 0 or 1 the totals of 11.1.14 count it as. **A NaN period makes the answer NaN**,
wherever in the run it stands: a NaN has no place in the run's order, so a run holding one has
no least value, and `[0.0, NaN, 0.2]` answers NaN — never the 0.0 a fold skipping the NaN gives,
and never an answer that depends on the NaN's position. It is the rule the folds across
policies already follow, carried along the periods. ±infinity is a value like any other:
`[1.0, -inf]` answers `-inf`.

The shape change, the period-axis rule and the `DIRECT` / `AGGREGATION` edge are `sum`'s word
for word.

#### 11.1.17 `max`

`max` answers the greatest of the periods of one policy's own column: the high-water mark a
fund reached, the largest claim a projection paid in any one period.

**The semantics.** The greatest value among the periods. A null period makes
the answer null, by the rule 11.1.14 states for the family: a period carrying no value could
have been the greatest of them, so `[10.0, null, 30.0, 40.0]` answers null and not the 40.0
either of the older readings would have given. A run of nothing but nulls has no value to be
greatest and answers null. A NaN period makes the answer NaN, as for `min`. The answer is one of the periods' own values, in their type, as for
`min`: a run of flags answers `bool`, whether any period was set — `[False, False]` answering
`False`.

The shape change, the period-axis rule and the `DIRECT` / `AGGREGATION` edge are `sum`'s word
for word.

**What these four are not, and what a conforming producer will add.** `first`, `last`, `len`,
`std` and `median` are folds of the same axis and are deliberately not here. `first` and
`last` are `projection.at_period` with a boundary offset, and minting a second spelling of an
operation the vocabulary already has is what 11.1.11's four rules exist to prevent; `len` is a
length rather than a fold of values, and it is the projection's own period count, which
`projection_set`'s record already carries. `std` and `median` each need a decision this entry
shape has no room for — a `ddof`, and a convention for an even period count — and an
identifier carrying a default the vocabulary never stated would be configuration hidden inside
a name. Each lands additively the day the decision is made, and until then such a line stays
an engine fragment and the node says so.

#### 11.1.18 Policy and period shapes

The outer axis of every column is the frame's model-point row: one row is one policy for the
purpose of the rules below. A `scalar` column has one value for each policy. A `list` column
has one ordered sequence for each policy, and position `t` in that sequence is that policy's
period `t`. A scalar literal has neither axis until an operation combines it with a column.

**Broadcasting never crosses the policy axis.** For a binary operation whose value semantics
are stated elsewhere, or a conditional branch combining a scalar and a list, policy `i`'s
scalar is repeated to the length of policy `i`'s list. The result is a list with that length.
Two lists must have equal lengths within each policy. Two scalars produce a scalar unless an
operation's own entry states a shape change. Empty lists obey the same rules and produce
empty list results. A null list is a policy with no periods, not a policy whose periods are
null: where either operand of a binary operation or a comparison is one, the result for that
policy is a null list on whichever side it stands, never a list of nulls. A null scalar is
another thing: it is repeated to the other operand's length as any scalar is, a null in each
period. This paragraph states shape only;
it does not define the value semantics of an otherwise unstated binary identifier.

The policies need not share one period count. If policy `i` has `T_i` periods, all the rules
above apply with that `T_i`; another policy may have a different count. A backend whose array
representation requires one rectangular `T` may refuse such an invocation as a backend
limitation. It must not report the artifact or the unequal per-policy lengths as invalid for
that reason.

**An operand held at a shape its entry does not state is refused by name.** A fold of one
policy's own periods (11.1.9, 11.1.14–11.1.17) or a period override (11.1.32) over one value per
policy, a broadcast onto an axis held once per policy (11.1.32), and a guess (11.1.36), an
initial value (11.1.20), or any operand of a scalar valuation (11.1.29) held per period are
each outside their entry. The reference producer refuses each where the line is
written, naming the operation, the operand and the move, and the JAX engine and the kit's
reader refuse one a document holds by name too (`fold-over-a-value-per-policy`,
`period-override-over-a-value-per-policy`, `explicit-broadcast-axis-required`,
`irr-guess-per-period`, `accumulate-initial-per-period`, `discount-scalar-domain`).

**A stored Float64 predicate has one deliberately narrow meaning.** Where a `when_then`
condition is a direct reference to a column declared `f64` or `list[f64]`, every value at
that evaluation boundary must be finite, non-null and exactly `0.0` or `1.0`; `1.0` selects
the then-branch and `0.0` the otherwise-branch. The check applies whether the referenced
column arrived as an input or was computed earlier. Any other numeric value is a refusal,
not truthiness. The same check, with the same refusals, applies where such a direct
reference is an operand of `and`, `or` or `not_` (11.1.27). This rule does not change the
column's declared type, admit another numeric predicate type, or state new semantics for
Boolean nulls.

#### 11.1.19 `projection.cumulative_survival` and period shifts

This entry states the per-period Float64 form of `projection.cumulative_survival` where
`from_survival` is false. For a policy with decrement sequence `q[0:T]`, let
`c[t] = product(1 - q[u], u=0..t)`. When `start_at` is null the result is `c`. When
`start_at` is a finite decimal `a`, the result has the same length and is
`[a, c[0], ..., c[T-2]]`: `a` is the value at the opening boundary, not an additional
factor in every later product. An empty sequence returns an empty sequence.

A null decrement ends the running survival's knowledge of itself, by the rule 11.1.9 states
for the two scans: `c[t]` is null when `q[t]` is null and whenever a null decrement stands at
or before period `t`, so `q = [0.1, null, 0.3]` gives `c = [0.9, null, null]`. The rule is
about the fold rather than about the shift, so it applies to `c` before `start_at` moves the
sequence along — the opening value `a` is the boundary the projection starts from and is
never the factor that went missing, and the same decrements with `start_at = 1.0` therefore
give `[1.0, 0.9, null]`. A missing decrement is not an absent decrement: a fold that read it
as no decrement would answer `[0.9, 0.9, 0.63]`, a survival curve a reviewer would check
against the periods it has and find correct.

`projection.previous_period(x, fill)` returns a sequence of the same length with `fill` at
position 0 and `x[t-1]` at every later position. `projection.next_period` returns `x[t+1]`
and fills the last position. `projection.at_period(x, fill)` with `relative_period=k`
returns `x[t+k]` where that position exists and `fill` elsewhere; negative `k` therefore
means a prior period. All three return an empty sequence for an empty input.

The stated shift form has a list Float64 value and a finite numeric literal fill. A scalar
value, an expression or column as fill, null and non-finite values in the shifts,
non-finite values in the survival fold, and the `from_survival=true` form remain outside
this entry. Their operation identifiers and signatures remain in 11.1.11; this subsection
makes no claim about their result. A shifted run of Booleans is among them, and the reference
producer meets one only where the run arrived as data, since a comparison it stores is
`list[f64]` (11.1.26): it shifts one under a Boolean fill or a null, and refuses a numeric
fill — the `0.0` default included — where the line is written rather than converting either
side into the other's type.

**A whole-number operand is widened on the record, as 11.1.20 states for `accumulate`.** Where a
model hands `projection.cumulative_survival` whole-number decrements, or shifts an `i64` run under
a decimal fill — the reference producer's `0.0` default among them — the reference producer
writes `to_float` (11.1.38) around the operand, so the record holds the stated Float64 form and a
reader replaying it meets the conversion; a whole number outside `[-2^53, 2^53]` is refused there
by name rather than rounded. A shift of an `i64` run under a whole-number fill makes no
conversion, writes none and keeps the run `i64`; that form is outside this entry.

#### 11.1.20 `projection.accumulate` and `projection.remaining_sum`

`projection.accumulate(initial, multiplier, addend)` evaluates one linear recurrence per
policy. The initial value is a finite Float64 literal or scalar column. At least one of
`multiplier` and `addend` is a finite Float64 list and supplies that policy's period count;
the other may be a list of the same length or a finite numeric literal. A literal is
broadcast by 11.1.18. Starting with `s[-1] = initial`, the result is

```text
s[t] = s[t - 1] * multiplier[t] + addend[t]
```

for `t=0..T-1`. Zero and negative multipliers are ordinary values in this recurrence; an
implementation must not replace it with a division by a cumulative product. `T=0` returns
an empty sequence. Two scalar step operands supply no period axis and are outside this entry.

**`reverse` names the direction, and it is always present.** The recurrence above is
`reverse = false`. Under `reverse = true` the same recurrence runs from that policy's own last
period back to its first. Starting with `s[T] = initial`, the result is

```text
s[t] = s[t + 1] * multiplier[t] + addend[t]
```

for `t=T-1..0`, so `initial` is the value after the policy's last period and position `t` of
the result is still the state at period `t`. This is a workbook's rollback, a reserve whose row
reads the row below it: with `initial = 0.0`, `multiplier = [0.9, 0.9, 0.9]` and
`addend = [1.0, 2.0, 3.0]` it gives `[5.23, 4.7, 3.0]`. Each policy starts at its own last
period, so on a book of unequal lengths no policy's run begins where another's does. The
result is the forward recurrence over each step operand reversed within the policy (11.1.41),
reversed back, and the two are the same doubles; the prohibition on a division by a
cumulative product binds either way. The direction is on the record for the reason 11.1.9
gives for its folds: an account value carried forward and a reserve rolled back are two
different columns of one cashflow, and an engine's rendering of a reversal wrapped round a
forward recurrence drops which of the two it was. A document written before this attribute
was stated carries no `reverse`, and its recurrence is the forward one, which was then the
only one.

A null multiplier or a null addend at position `t` makes `s[t]` and every later position
null, by the rule 11.1.9 states for a forward fold: at that period the recurrence has lost a
term of its own state and does not know the state from there on. With `initial = 10.0` and
`addend = [1.0, 1.0, 1.0, 1.0]`, a `multiplier` of `[2.0, null, 3.0, 4.0]` gives
`[21.0, null, null, null]`, where a fold that skipped the hole and carried on would give
`[21.0, null, 64.0, 257.0]`; with `multiplier = [2.0, 2.0, 2.0, 2.0]`, an `addend` of
`[1.0, 2.0, null, 4.0]` gives `[21.0, 44.0, null, null]`. Either way the periods reached
before the hole keep the states they had, and every position after it is an account value a
reader would otherwise check against the periods it has and find correct. A null `initial`
answers a run of nulls of the period count, because the recurrence has no state to open
with, and a run whose every step is null answers a run of nulls for the same reason at every
position. A modeller who means nought writes it, by 11.1.14's sentence for the family. The
rule is about a period carrying no value, and a non-finite operand is not one: it stays
outside this entry with the exclusions below.

Under `reverse` the run starts at the last period, so the positions it has lost run from the
hole back toward period zero, by the rule 11.1.9 states for a reverse fold. With
`initial = 10.0` and `addend = [1.0, 1.0, 1.0, 1.0]`, a `multiplier` of `[2.0, null, 3.0, 4.0]`
gives `[null, null, 124.0, 41.0]`; with `multiplier = [2.0, 2.0, 2.0, 2.0]`, an `addend` of
`[1.0, 2.0, null, 4.0]` gives `[null, null, null, 24.0]`. The periods the run reached before
the hole keep their states, and a null `initial` or a run whose every step is null answers a
run of nulls in either direction.

`projection.remaining_sum(x)` returns the inclusive suffix sum of one finite Float64 list:
result position `t` is `sum(x[s], s=t..T-1)`. It preserves the input length, and an empty
input returns an empty sequence. **Over an `i64` run `remaining_sum` answers `list[i64]`**, by
11.1.9's whole-number rule: each period exact, never through a double — `[2^53 + 1, 2]`
answers `[9007199254740995, 2]` — a period whose sum is outside `i64` outside the portable
domain and refused by name by the reference producer, and a run of flags summed as the whole
numbers it indicates.

A null period makes that position and every earlier position null, by the rule 11.1.9 states
for a reverse fold. This fold starts at the last period, so the periods it has lost run from
the hole back toward period zero, and `[10.0, null, 30.0, 40.0]` gives
`[null, null, 70.0, 40.0]` where a fold past the hole would give `[80.0, 70.0, null, 40.0]`.
A run of nothing but nulls answers a run of nulls; a null outer list answers null; and a
modeller who means nought writes it, by 11.1.14's sentence for the family.

Non-finite operands, a scalar column as multiplier or addend, mismatched list lengths within
a policy, non-Float64 forms, a generated non-finite result, and a null outer list to
`projection.accumulate` are outside the two stated forms. A consumer may refuse those
invocations without making either operation opaque.

**A producer that widens an operand says so on the record.** Where a model hands
`projection.accumulate` a whole-number column or expression — as the opening value, the
multiplier or the addend — the reference producer writes the widening it makes as a `to_float`
call (11.1.38) around that operand, so the recurrence the record states reads Float64 and stays
inside the stated form, and a reader replaying it meets the conversion rather than inferring
it. A whole-number literal needs no call: as the opening value it is written as the decimal
of the same value, which the stated form asks of an opening literal, and as a multiplier or an
addend it is written as it stands, a finite numeric literal of the stated form. A Boolean
operand is not widened: a run of flags is a selection rather than an amount, and the reference
producer refuses one where the line is written, naming the amount to write in its place —
`when(flag).then(1.0).otherwise(0.0)`, with the `otherwise` the model means for a missing flag.

#### 11.1.21 `projection.prospective_value`

This entry states `projection.prospective_value(cashflows, discount)` for
`discount_kind="rate"`. Cashflows are one finite Float64 list per policy. The rate
is a finite Float64 literal for `beginning_of_period`, a scalar column supplying one
policy-specific rate, or a list whose length equals that policy's cashflow length. Scalar
columns and literals broadcast by 11.1.18. Scalar-column and list rates admit both timings;
the literal-rate form stated here admits `beginning_of_period`. Every rate must be greater
than `-1`.

For one policy, write `v[t] = 1 / (1 + rate[t])`, `B[0] = 1`, and
`B[t] = product(v[u], u=0..t-1)` for `t>0`. The result at position `t` is

```text
beginning_of_period: sum(cashflows[s] * B[s],        s=t..T-1) / B[t]
end_of_period:       sum(cashflows[s] * B[s] * v[s], s=t..T-1) / B[t]
```

Thus the current cashflow is undiscounted under `beginning_of_period`; under
`end_of_period`, each cashflow carries its own period's rate. A scalar rate and a constant
list containing that rate are equivalent. An empty cashflow list with a matching empty list
rate, or with a literal or scalar rate, returns an empty list.

A null cashflow period makes that position and every earlier position null, by the rule
11.1.9 states for a reverse fold: this fold also starts at the last period, so under either
timing and any rate this entry admits, `[10.0, null, 30.0, 40.0]` answers null at positions 0
and 1 and leaves positions 2 and 3 the values the whole periods give. A run of nothing but
nulls answers a run of nulls; a null outer list answers null; and a modeller who means nought
writes it, by 11.1.14's sentence for the family. The rule is about the cashflows' own
periods: a null rate is one of the operands below and stays outside this entry.

`discount_kind="factor"`, an `end_of_period` literal rate, scalar cashflows, mismatched list
lengths, null rates, non-finite operands, rates at or below `-1`, and a generated non-finite
result remain outside this entry. Whole-number cashflows, or a whole-number rate column, reach
the record inside `to_float` (11.1.38), by the rule 11.1.20 states for `accumulate`. A consumer that implements only this entry must refuse
those forms rather than infer a factor convention or silently reshape an operand.

#### 11.1.22 `list.get`

`list.get(value, position)` selects one stored position from each policy's own ordered list.
It is positional selection, not a projection-period label, a calendar date or a relative
shift. `projection.at_period` remains the operation that shifts a whole timeline by a
relative offset and fills the positions exposed at its boundary.

For policy `i`, let its list have length `T_i` and let its signed Int64 position be `k_i`.
A whole-number literal supplies the same `k` to every policy; a scalar Int64 column supplies
one `k_i` per policy. Define `p_i = k_i` when `k_i >= 0` and `p_i = T_i + k_i` otherwise.
Where `0 <= p_i < T_i`, the result for that policy is `value_i[p_i]`: position `0` is the
first item and position `-1` is the last. The result has the selected element's type. A null
at the selected position is an ordinary selected value and remains null; a null at an
unselected position has no effect.

A null list, a null position, or a position outside `[-T_i, T_i - 1]` refuses the whole
invocation. An empty list therefore refuses. The position must be a whole-number literal or
a scalar `i64` value; a Boolean, decimal, text, date or list-shaped position is refused,
including a decimal whose value happens to be integral. No nullable or fill-on-bounds mode is
part of this identifier.

#### 11.1.23 `to_integer`

`to_integer(value)` is checked conversion to signed Int64. It accepts a scalar integer or
`f64` value, or a list of either, and preserves the scalar or list shape. An integer value is
returned unchanged where an `i64` carries it. A Float64 value `x` is converted only where it is finite, exactly integral, and
`-2^63 <= x < 2^63`; `-0.0` therefore becomes `0`. The result type is `i64` for a scalar and
`list[i64]` for a list. An empty list returns an empty `list[i64]`.

An integer stored in a width wider than `i64` — unsigned or 128-bit — is an integer for this
call and is judged on its value, the rule section 10 states for an integer width at export:
one inside `[-2^63, 2^63 - 1]` converts, and one outside it refuses the whole invocation
rather than wrapping. A value with no `i64` to convert to keeps its digits through
`to_text` (11.1.39) instead.

A null scalar, a null list, any null list item, a NaN, an infinity, a fractional value or a
value outside that half-open range refuses the whole invocation. Every other input type is
refused, including Boolean, text and date. There is no truncating, saturating, wrapping or
nullable form hidden behind this identifier.

#### 11.1.24 `lookup`

`lookup` selects one answer from the processed table named by its `table`
attribute and identified by its `table_fingerprint`. The ordered operands are
paired with the processed table's key columns in the order §11.1.11 states;
call-site keyword order is immaterial. The remaining processed-table column
is the answer column. A consumer must refuse if this does not identify exactly
one answer column or if the operand count does not equal the key-column count.

**That key-column order is read from the payload's `columns`** (§15), with the
`value` column removed: `columns` is an ordered run of objects and its order is
the processed table's own. The payload's `dimensions` is a **set** of names and
is not an operand order. It is commonly alphabetical, and a consumer binding
operands to it mis-keys any table whose columns stand in another order
**silently** — the key families still line up, the gather still answers, and
the answer is wrong. Nor is name-matching available as a fallback: an operand's
column name need not be its dimension's name. Only position works, and only
`columns` carries it. The reference producer's canonical form (§12.3) writes the key columns
in name order, so in its documents `columns` and a sorted `dimensions` coincide; a consumer
still binds to `columns`, because a document written before that rule, or by another
producer, need not agree. `mortality.at` takes the other rule, and the contrast is
deliberate: its `dimensions` attribute is written in operand order (§11.1.11),
so that read binds by name. One vocabulary, two binding rules — `lookup` by
position, `mortality.at` by name.

The bounded portable domain has at least one processed table row, at least one
key column and an `f64` answer column. The reference producer reads an answer column of whole
numbers, or of single-precision values, as the `f64` each value is exactly — an integer within
`[-2**53, 2**53]` — so the processed table, its payload `columns` and its fingerprint carry
`f64`, and a table spelled `3` and one spelled `3.0` are one content; an integer past that
interval, and an answer column that is not a number, are refused when the table is built.
Empty processed tables
have no portable value semantics from this clause. Each processed table key is either a present string with
a string query, or a present finite `f64` with an
`i64`/`f64` query. Cross-family pairs and other key types are outside this form.
Every numeric
table and query key is in
the closed interval `[-2**53, 2**53]`; finite fractional `f64` keys are valid
inside it. Strings compare by exact string equality. Numeric keys compare by
their exact mathematical value, including between signed `i64` and `f64`
inside this interval. Numeric keys outside that interval, null outer lists,
non-finite query keys,
non-finite or null **key** cells in the table, and other key types are outside
this bounded contract and a consumer claiming only this subset must refuse
them. Those are properties of the table or of the query's shape and are judged
table-wide, as written. The **answer** column's own cells are judged below,
where a query lands.

**A flag key is written as its number.** The reference producer reads a
Boolean key against a dimension the table holds as numbers as its `0` or `1`,
as a flag is read in arithmetic, and writes the reading into the operand —
`binop mul(key, 1.0)` — so the document is an `f64` query inside this form and
every engine and reader answers it alike; against a dimension whose keys are
not within `{0, 1}` it refuses the key by name, since a flag there would read
as a code. A date or a timestamp key is read by the reference producer
against a table dimension of its own kind and refused against any other, by
kind and whatever `on_missing` says — a day count never equals a date — and a
document carrying such a key is outside this form, as written above. A table
is never keyed on a duration or a time of day: the content grammar (§12.3)
names neither, so such a key would be fingerprinted as the bare count of its
unit, the same as a whole number's; the reference producer refuses the key
column by name when the table is built, extended, re-read or copied, and names
the move — key on a whole number of the unit meant, or on a date.

Each complete key tuple must match at most one processed-table row. Duplicate
key tuples make the table ambiguous and the invocation refuses before
selecting a value, whether or not their answer cells agree. With
`on_missing: "raise"`, any tuple matching no row refuses the invocation. With
`"nan"`, the result at that tuple is the canonical `f64` NaN. With `"fill"`,
it is the finite decimal in `fill_value`; `fill_value` must be non-null for
this mode and null for the other two. Miss handling does not turn an
ambiguous duplicate into a miss.

**The answer cell's condition is judged at the cells a query reaches, not over
the table.** A null or non-finite answer cell **at a key tuple some query
reaches** is a **miss**, and `on_missing` decides it exactly as it decides a
tuple matching no row: refused by name under `"raise"`, the canonical NaN under
`"nan"`, the finite decimal under a fill. An answer cell no query reaches is
never read and disqualifies nothing, so **a table may carry unreachable cells
and still be a portable basis.** That is the case this rule comes from: a
select basis whose ultimate block is padded at the age and duration pairs no
life can occupy carries blanks by construction, and it is a published table
rather than a defective one. The refusal a strict reading wants has not gone —
it has moved from the basis to the query, and under the default `"raise"` the
invocation still stops and names the key it could not answer.

**A null query key is a miss** on the same rule, not a domain violation, and
`on_missing` decides it the same three ways. It must not be allowed to select a
row. The shape this answers is the commonest one in a product-parameter table:
a key that exists only for the rows that use it — a surrender-charge identifier
carried by the plans that have a schedule and null on the plans that do not —
read behind the model's own condition. **§11.1.28 is unchanged and keeps its
force.** Every other invalidity still refuses behind a false condition: a key
of the wrong family, a key outside the closed interval above, an ambiguous
table, a checked conversion that cannot hold. There is no refusal left to
suppress here, because the branch is a valid expression under the claimed
domain and the node's own miss policy says what a miss means. A lowering
**selects** between branches and never blends them arithmetically, so a
discarded NaN cannot leak into the answer.

The policy/list rules of §11.1.18 apply per key. With scalar keys only, the
result is scalar `f64`. If any key is a list, scalar keys broadcast across
each policy's list axis and the result is `list[f64]`. All list keys on one
policy have equal lengths. An empty list produces an empty list; no-policy
input produces no rows while preserving the declared result dtype. Jagged
lengths between policies remain valid under §11.1.18 and may be refused by a
backend whose declared portable subset is rectangular.

Executable artifact replay resolves the exact
`(kind="table", table, table_fingerprint)` identity. Exactly one matching
assumption entry and a payload that verifies under §§12.3 and 13 are required.
A same-name entry or live registry value with another fingerprint is not the
table this call names and must not be read as a fallback. Two entries matching
the identity, or a name-only `reads_assumptions` link selecting more than one
entry, are ambiguous and refuse. This paragraph governs closed artifact
replay; it does not redefine the lifetime of a producer's live lazy plan.

#### 11.1.25 Arithmetic: `add`, `sub`, `mul`, `div`, `floordiv`, `mod`, `pow`

These are binary operations, with left and right operands in written order, not
calls. The policy/period broadcast rule in §11.1.18 applies, including empty
lists and different period counts between policies. List lengths must agree
within one policy; no list is truncated to its neighbour's length.

**The stated numeric domain.** Operands are `i64` or `f64`, scalar or list,
with finite present elements or nulls, and a Boolean, per policy or per period, read as the
paragraph below says. Text, date, datetime and nested lists are outside this
entry, and so is an engine's duration, which section 10 names no type for: the reference
producer refuses a number beside a duration where the line is written, naming the count in an
explicit unit to write instead, except where its engine scales the duration — times a number,
or over one, per policy, and a run of durations times or over a written number — which it
leaves to answer as the duration the export then refuses. An operand stored wider than `i64` is read as the `i64` its values fit, and refused by
name where one does not, on either side; it is never wrapped (section 10). Two `i64` operands retain `i64` for `add`, `sub`,
`mul`, `floordiv` and `mod`; an `f64` operand promotes the answer to `f64`.
`div` always returns `f64`. Mixed i64/f64 operands are stated only where the
integer's magnitude is at most `2^53`, so conversion loses no integer value.
A pure-i64 calculation need not take a float detour and remains exact at the
signed endpoints. An integer result outside `[-2^63, 2^63-1]` is outside this
portable domain: a consumer claiming only this domain must refuse it, never
silently promise an exact answer from wrapped arithmetic. The current producer
can wrap outside this domain; that is not a portable guarantee.

**A Boolean operand reads as the 0 or 1 it indicates**: true is 1, false is 0
and a null stays null, as a stored comparison already reads (11.1.26). **Per
period the answer is `list[f64]`** whatever the other operand is: the reference
producer reads a Boolean run as its `list[f64]` indicator before the operation,
on either side and under every operator here, and a consumer reads it the same
way. **Per policy the answer is `f64` too**, under every operator here and on
either side, whatever the other operand is: the reference producer reads a
per-policy Boolean as its 0.0/1.0 `f64` indicator before the operation, as it
reads a run, so `flag + 1` is `2.0`, `2 // flag` is infinity where the flag is
false, and `flag ** 2.0`, `flag ** x` and `2.0 ** flag` are in the entry; beside
a per-period operand the answer is `list[f64]`. A per-policy Boolean on both
sides of one operation is not admitted. A model that
needs a per-policy flag as an amount of a stated type writes the conversion —
`when(flag).then(1.0).otherwise(0.0)` — and the record carries it. **A conditional reads a
flag beside a whole number the same way** (11.1.28): `when(c).then(True).otherwise(n)` over an
`i64` column is `f64`, per policy as per period, `1.0` where the condition holds, and a
whole number stored wider than `i64` beside the flag is read as an operand here is. **The calls
that read a number read a flag the same way**: `abs`, `sign`, `sqrt`, `cbrt`, `exp`, `log`,
`log10`, `log1p`, `norm_cdf` and `round_sig_figs` (11.1.12), and `round`, `floor` and `ceil`
(11.1.8), over a Boolean — stored, a comparison written as the operand, or a result of `and`,
`or` or `not_` — read it as its 0.0 or 1.0, a null staying null, and answer `f64` per policy and
`list[f64]` per period, never `bool`: `sign` of a true flag is `1.0`, `exp` of a false one
`1.0`, `round` of either the flag's own 0.0 or 1.0, and `log` and `log10` of a false one `−∞`,
as of any 0.0. A producer reads the flag as that double before the call's own rule, and a
consumer reads it the same way; one rule, "a flag is its 0 or 1", holds in arithmetic and in
these thirteen alike.

| Identifier | Value at one policy/period position |
|---|---|
| `add` | left plus right |
| `sub` | left minus right |
| `mul` | left times right |
| `div` | real division after the stated float promotion |
| `floordiv` | integer operands: exact quotient rounded toward negative infinity; float operands: floor of the binary64 quotient, returned as f64 |
| `mod` | integer operands: `left - right * floor(left/right)` in exact integer arithmetic; float operands: `left - right * floor(left/right)`, with the quotient and subsequent operations evaluated in binary64 |
| `pow` | left raised to right, within the further domain below |

Floor is not truncation: `-7 // 3` is `-3`, and `-7 % 3` is `2`. With a
negative divisor, `7 % -3` is `-2`. The float clause is deliberately a rounded
quotient: `1.0 // 0.1` is `10.0`; it does not inherit a language's alternative
floating remainder algorithm. Finite float operands whose nonzero quotient or
intermediate overflows remain outside the bounded `floordiv`/`mod` domain.

**Zero and absence are explicit.** A null element on either side yields null
at that position; a null outer list yields a null result list. Integer
`floordiv` and `mod` with a zero divisor yield null. For `div`, a nonzero
finite numerator divided by signed zero yields the appropriately signed
infinity; zero divided by zero yields NaN. Float `floordiv` preserves that
infinity or NaN; float `mod` with a zero divisor yields NaN. These are stated
exceptional outputs from finite inputs, not permission to infer behavior for
arbitrary non-finite inputs. Signed zeros denote the same numeric value except
where their sign determines this division result. Other overflowing float
arithmetic is outside this bounded entry.

**Power has a narrower type/shape promise.** Two scalar i64 operands return i64
when the exponent is in `[0, 2^32-1]` and the exact result fits i64; a whole-number literal
written as the base is an `i64` operand like any other (section 10). **Where the exponent is
written as an integer literal outside that range — a negative one, or one past `2^32-1` — the
answer is `f64`**: the record holds the exponent, so the type is known where the line is
written, and the base is read as its double and raised by the binary64 power, held like every
power to the relative `1e-12` below: `a ** -1` lies within it of `1 / a`, not on its bits. An
exponent held in a column keeps the integer rule: the answer is `i64`, and a value of that
column outside `[0, 2^32-1]` is outside this entry when the run reaches it. The
reference producer then refuses the run, naming the floating-point power (`to_float()` on
either operand), and a consumer refuses it, naming the line. Every
list-shaped power, and a power with an f64 operand, returns f64; integer
operands converted along this path must lie within `[-2^53, 2^53]`.
A positive base accepts any finite exponent producing a finite result.
A zero base accepts nonnegative exponents, with `0**0 = 1`. A negative base
accepts integral exponents when the result is finite and **the base is list-shaped
or both operands are scalar**. A negative scalar base against a list exponent
is explicitly outside this contract, including when every exponent is integral:
the current producer's guarded logarithmic path returns a null list there.
Zero with a negative exponent, fractional powers of negative values, and
overflow/underflow-sensitive powers outside finite representable results remain
outside this entry. Nulls preserve the element/outer-list rule above.

Integer, mask and shape assertions are exact. Power's finite f64 values use
the same relative `1e-12` agreement as the transcendental family in §11.1.12;
this does not change any single-producer golden. The small basic-arithmetic
vectors in §11.3 state their own comparison budgets and do not establish a
whole-model error budget or authorize reassociation across arbitrary nodes. The
rule two engines' whole documents are held to is §11.1.12's, a line at a time.

#### 11.1.26 Comparisons: `lt`, `le`, `gt`, `ge`, `eq`, `ne`

These six compare their two operands in written order. The bounded domain is
finite i64/f64 numeric values, or matching Boolean/string/date/datetime types;
no ordering between different semantic families is inferred. Shape follows
§11.1.18. **A null outer list on either side yields a null result for the policy** (section 11.1.18):
`av < gmdb` and `gmdb > av` answer alike where one policy's `gmdb` run is absent, so a fill and
a total read after them do not move with the order the comparison is written in. **Two i64
operands compare exactly over the full signed-i64 range,
per policy and per period alike**: `2^53 + 1` is greater than `2^53` in every
period, `2^63 - 1` is greater than `2^63 - 2`, and `-2^63` is less than
`-2^63 + 1`. A producer whose list predicate reads its operands as doubles
decides such a pair by their exact value, never by the double nearest each
(the reference producer hands its kernel the two values' difference, taken in
128 bits, against nought, whose sign a double keeps). Such a producer needs
both operands' types to know which pairs those are — a sequence written into
the formula is typed as the run it is compared with — and refuses by name a
per-period comparison whose operand type it cannot read, rather than decide
it by the nearest doubles. Two f64 operands compare
as the doubles they are. A mixed i64/f64 comparison is stated only for i64
values within `[-2^53, 2^53]`, per policy and per period, where the integer
converts to f64 exactly. **±infinity is a number and is ordered as IEEE 754
orders it**: `inf > 1e308`, `-inf < x` for every other number, `inf == inf`.

**A NaN operand leaves a comparison with no truth value**, per policy and per
period, on every side. A NaN is no number, so it is neither greater than 1.0
nor less than it nor equal to anything, itself included; 0/0 is one (11.1.25),
and an in-the-money ratio over a nought guarantee is the ordinary way to meet
it. The comparison's indicator is **NaN** there — `NaN > 1.0` stores NaN, and
so does `NaN == NaN` — and its truth value as a predicate is the same unknown:
11.1.27 and 11.1.28 say what reads it. A null on either side is still a null,
and wins over a NaN on the other. Never the true of an engine that orders NaN
above every number, nor the false of a hardware comparison: each silently
selects one of two readings the vocabulary does not hold. A model that means
"no value" tests for the NaN with `is_nan` (11.1.13) and says what it means.
**Membership of a NaN is false, not unknown**: `is_in` (11.1.5) asks whether a
value equals a member of its set, and under IEEE 754 equality a NaN equals
none, so `is_in` of a NaN answers false, per policy and per period, on every
side — never the true of an engine whose hashing makes one NaN equal another,
and never null, which stays the answer for a null value.
A truth value of a per-policy test combined with `&`, `|` or `~` is a
Boolean (11.1.27), stored or inline, which holds no NaN: it is null there. A consumer that
carries no null refuses that cell by name rather than store a truth value.

**Two `datetime` operands compare as instants, exactly to the last unit they
are held in**, per policy and per period: a nanosecond after another is
later, and two values in one time zone or in two compare by the instant each
names. A zone-naive `datetime` against a zoned one names no instant to
compare, and a producer refuses the line by name where it is written. **A
pair held in two different time units compares in the finer unit**, per
policy and per period: a nanosecond after an instant held in microseconds is
later than it, never equal to it as it would be in the coarser unit. Every
value of the coarser unit has an exact count of the finer, taken wide enough
to hold it, so no value is refused for the unit it is held in — an
open-ended 9999-12-31 held in microseconds is later than any nanosecond
value. Two durations in different units compare the same way. A consumer
that carries no `datetime` refuses such a column by its type (section 10);
the wire holds a `datetime` in one unit, so a document never carries such a
pair.

**A column still wider than `i64`** — one section 10 leaves in the width it
arrived in, because a value in it is past `i64` — is outside the portable
domain, and a document carrying one is refused. A producer that keeps such a
column compares it exactly in its own width, against another whole number of
any width and against a literal past `i64` (`pid == 2**64 - 1`), and tests its
membership of a set written in the formula the same way (11.1.5). A literal
past `i64` is admitted there and nowhere else: a comparison reads a value by
its digits and cannot wrap it.

`lt`, `le`, `gt`, `ge`, `eq`, `ne` mean less than, less than or equal, greater
than, greater than or equal, equal and unequal. A null operand yields a null
comparison. Comparing nulls is not null-safe equality. Scalar text uses
lexicographic Unicode order and scalar dates chronological order. **List-shaped
text compares period by period under the same rule** — exact equality, order by
code point, a null element answering null — against a text value or another
text run of the same length, and its answer is the per-period indicator of the
paragraph below. **List-shaped dates compare period by period too**, in
chronological order with exact equality and a null element answering null,
against a date — a column or a literal, on either side — or another date run of
the same length; runs of different lengths within one policy are refused under
11.1.18. Date/datetime mixing is outside this entry. **An ordered category
compared with text for order is outside this vocabulary**, and the reference
producer refuses it by name, per policy and per period: a band from `cut`
(11.1.4) is ordered by its categories and text by its letters, and the two
disagree (`"under 30"` comes before `"30 to 59"` as a band and after it as
text), so `band < "30 to 59"` has two meanings and the record could hold only
the second. The band's order is written against the number it was cut from
(`issue_age < 30`), the letters' against its text (`to_text`, 11.1.39), and a
consumer refuses an ordering whose operand is a `cut`. `eq`, `ne` and `is_in`
(11.1.5) have one meaning and answer, the band read as its text: a label
outside its categories is unequal to every band and a member of no set.

**A predicate and a stored indicator have the same truth value but different
representations.** A comparison used directly as a `when_then` condition, or
as a logical operand, supplies a Boolean truth value. Assigned as a column or
used as an arithmetic operand, it supplies f64 `1.0` for true and `0.0` for
false, with null preserved; a per-period result is `list[f64]` — and so it does as the
operand of a call that reads a number (11.1.12, 11.1.8). **What it compares does not move
this**: a comparison of a table lookup (11.1.24), a mortality or a curve read, assigned as a
column, is the same indicator, `af.r = table.lookup(age=af.age) > 60` storing `1.0`/`0.0`
typed `f64` as `af.r = af.age > 60` does, and so is the same test stored through a batch door
under the name it was given, `af.with_columns((table.lookup(age=af.age) > 60).alias("r"))` or
the same in `select`. It does so on
either side of every operator of 11.1.25 and under a negation: `(age > 60) *
loading`, `loading * (age > 60)`, `1 - (age > 60)` and `-(age > 60)` are each
the one indicator in arithmetic, and a producer whose surface hands a
comparison back as a predicate accepts it there in either order. **A comparison compared is
a flag compared**: as an operand of one of these six it supplies its indicator too, per policy
as per period, so `(age > 60) == 1` is true where the age is over 60, `(age > 60) >= 0.5`
likewise, and `(age > 60) != (smoker == 1)` is true where exactly one of the two tests holds —
the way this vocabulary writes an exclusive or, which it holds as no operator of its own.
Against a Boolean, stored or written as `True`, it is compared as that Boolean's 0 or 1, as a
stored flag is. A producer whose surface hands a comparison back as a predicate accepts it on
either side of each comparison and records one `binop` over the other; it never answers the
line with its host language's own truth value. The tree
remains the same `binop`. A consumer must respect its position and the stored
column's declared dtype instead of letting its host language choose an integer
or Boolean output column. Truth values, null locations and indicators are exact.

#### 11.1.27 Logical operations: `and`, `or`, `not_`

These mean logical conjunction, disjunction and negation, never integer bit
operations. The stated operands are Boolean values, comparisons used as
predicates, and stored indicators. **A stored indicator is a direct reference
to a column declared `f64` or `list[f64]`, read under §11.1.18's stored
predicate rule**: every value is finite, non-null and exactly `0.0` or `1.0`, a
negative zero is zero, and any other value — a null among them — is a refusal
at evaluation rather than a truth value or a null. A per-policy stored
indicator stands for the Boolean it encodes; a per-period one is its own 0/1
indicator. Neither changes the column's declared type. Other list-shaped f64
indicators — a per-period logical result used as an operand of another — are
usable where each present value is exactly `0.0` or `1.0`, under the
per-position null rule below. An `i64` operand, a numeric literal, an
arithmetic result and every other numeric truthiness remain outside this
clause. `not_` takes one operand; the others take left and right operands
under §11.1.18's shape rules.

**This preview preserves the producer's explicit scalar/list distinction.**
When all operands are scalar, the result is Boolean and uses three-valued
logic: false AND anything is false, true OR anything is true, and otherwise
a null operand yields null. Negating null yields null. Thus false AND null
is false and true OR null is true. **An operand with no truth value — a
comparison a NaN reached (11.1.26) — makes the result have none**, on both
shapes, as the per-period arithmetic below already gives it (`NaN * 0.0` is
NaN): false AND unknown is unknown, a null beside it winning; a per-period
result is NaN there. **A scalar result is a Boolean wherever it is read,
stored or inline: null there.** A value does not change by being named, so
whatever reads it reads that null -- `is_in`, `is_null`, `fill_null`, a
comparison, arithmetic, an enclosing `&`, `|` or `~` under the three-valued
logic above (false AND it is false), and a `when` (11.1.28), which selects its
otherwise there as over any null scalar condition.

When any operand is a list, the result is `list[f64]` with `1.0`/`0.0`
representing true/false. At each position a null operand yields null, even
for false AND null or true OR null. For present indicators `a` and `b`, AND
is `a*b`, OR is `1-(1-a)*(1-b)`, and NOT is `1-a`. A null outer list remains
null. The distinction is documented existing behavior, not a Boolean-storage
migration. A consumer offering only the non-null common domain must say so and
refuse nullable inputs; it may not quietly apply one shape's null policy to both.
Either shape of result, as the operand of a call that reads a number (11.1.12,
11.1.8), is read as its 0.0 or 1.0, and the call answers `f64` (11.1.25).

`^` is not an operation of this vocabulary. A producer refuses it by name; the
test it usually stands for, one or the other but not both, is `ne` of the two
predicates (11.1.26).

#### 11.1.28 Conditional composition: `when_then`

`when_then` is a tree form, not an operation identifier of its own. It selects the
then value where the condition is true and the otherwise value where it is
false. A nested otherwise conditional is the next case in written priority
order. Branches obey §11.1.18, so a scalar branch repeats over the current
policy's list axis. **The bounded branch types are a matched pair of one type
this vocabulary carries** — two `i64`, two `f64`, two `bool`, two `str`, two
`date` or two `datetime` — with `i64`/`f64` mixing only within the exact
integer-conversion range, and a `bool` beside an `i64` answering `f64`, the flag read as the
0.0/1.0 indicator section 11.1.25 reads it as beside a number, under the same range — and a
`bool` beside an `f64` answering `f64` the same way, `when(c).then(False).otherwise(3.25)` being
`0.0` or `3.25`;
list-shaped branches with different lengths are not padded or truncated. Two branches of different families are not a matched pair and are
outside this entry: a producer that carries one of them into the other's type
is recording a conversion the model never wrote, and a consumer must refuse
rather than choose which of the two the answer is. **A `datetime` pair answers a
`datetime`**, per policy or per period alike; a producer whose engine carries a
unit and a time zone beside the value answers the pair in the zone the two share and **the
finer of their two units**, so neither branch loses a digit: a microsecond value beside a
millisecond one answers microseconds, and a literal written beside a nanosecond column
answers nanoseconds. A value the finer unit cannot hold — a nanosecond count reaches only the
years 1677 to 2262 — is refused by name when the run reaches it, never answered in the
coarser unit and never a null; the reference producer reads an engine's durations, outside
this vocabulary, the same way. **An `i64` past the exact range beside an `f64` is outside this entry**,
as it is in arithmetic (11.1.25): a consumer refuses the pair over every value of both
branches, since a false condition does not suppress a branch's domain, and the reference
producer rounds such a value to its double, as it rounds the same pair's sum. It refuses by
name, where the line is written, two whose types
have nothing in common — a zone-naive value opposite a zoned one — rather than carry
one into the other's. A consumer that carries no `datetime` refuses such a column by
its type where the book arrives, before anything is computed.

A direct stored f64 condition follows §11.1.18's checked non-null finite 0/1
rule, including when the column arrived as data. An inline comparison uses
§11.1.26's predicate meaning. **A condition with no truth value — a NaN reached
its comparison (11.1.26) — selects neither branch** (a per-policy `&`, `|` or
`~` over one is a null Boolean instead, 11.1.27): the answer is NaN where
it is a double, and null where it is a type that holds no NaN (text, a whole
number, a flag, a date), per policy and per period alike. A branch holding a
null at that cell does not change it: neither branch is selected there, so a
double answer is NaN whichever branch the null is written in. A guarded model,
`when(gtee > 0).then(av / gtee).otherwise(0.0)`, never reaches the unknown,
because its condition is a number; one that tests the quotient,
`when(av / gtee > 1.0)`, answers NaN for the policy whose quotient is 0/0. A
consumer that carries no null refuses the cells whose answer is one by name. For Boolean conditions, a null scalar selects
otherwise when the whole conditional is scalar. If the condition or either
branch is list-shaped, a null condition yields a null element instead. A null
selected branch stays null; a null unselected branch does not replace the
selected value. Empty lists remain empty. **A null outer list anywhere in the line makes the
policy null**: a policy with no run has no periods for the conditional to answer (11.1.18),
whether the run stands in the condition — a comparison with a null outer list on either side
is null for the policy (11.1.26), and so is a stored list condition — or in either branch,
selected or not, or in any case of a chain. `when(in_force).then(gmdb).otherwise(av)` with
one policy's `gmdb` run absent is null for that policy, never its `av` values in the periods
the condition is false and nulls in those it is true.

Selection does not promise lazy branch execution. A branch's own input-domain
or signature refusal is not suppressed by placing that branch behind a false
condition. Both branches must be valid expressions under the claimed domains.
In particular, a conditional is not an escape from an invalid lookup or checked
conversion. Output dtype is the shared branch type (f64 where an `i64` and an
`f64` branch meet, and where a `bool` and an `i64` do), with its scalar/list shape; the condition's storage type is
not the output type. A mortality table selected by sex — text either way — is
the ordinary case that makes this wider than a numeric pair, and it is a line
two of the shipped tutorials carry.

**A null branch carries no type of its own, so the output is the other branch's
type.** `when(month > 0).then(None).otherwise(k)` over an `i64` run is `list[i64]`,
and beside a `bool`, `str`, `date` or `datetime` branch a null is that type, so a
branch that holds no value carries neither a whole number, a flag nor a calendar
value into `f64`. **Two null branches carry no type at all**: the output is a null
of no type, per period as per policy, and section 10's all-null rule refuses it at
export rather than guess one. **A selection hands back the value it selected.** A
producer whose engine selects in doubles selects a whole number past `2^53` without
loss or not there: `when(month > 0).then(0).otherwise(k)` over a run holding
`2^53 + 1` answers `2^53 + 1`, a branch holding `2^63 - 1` answers it, and a
`datetime` keeps its last unit. (The reference producer selects each value as the
whole number its engine holds it as — a `date` as its day count, a `datetime` as its
count of units — in 32-bit pieces, each of which a double holds exactly, and joins
them; an engine's wider whole numbers, outside this vocabulary, are selected the
same way, so none is rounded at any width.) The tree has no null literal in this
preview: a producer writes a null branch as an engine-native fragment (§11.2), and a
consumer that runs only core calculations refuses such a document by name before
it reads a book.

#### 11.1.29 Finance conversions and scalar present values

The following domains use finite Float64 values and propagate a null operand to a
null result, unless the formula below selects null itself. Results are Float64.
`finance.to_monthly` and `finance.compound` operate independently per policy and
per period, preserving empty lists. Null outer lists remain null. The other two
operations in this entry state **scalar operands only**; a per-period cashflow
valuation is the separately specified `projection.prospective_value` (§11.1.21).

| Operation | Calculation and supported configuration |
|---|---|
| `finance.to_monthly(r)` | `method="simple"` gives `r/12`. `method="compound"` gives `(1+r)^(1/12)-1`, with `r >= -1`. Other method tokens are unsupported, not aliases for simple interest. |
| `finance.compound(t)` | `(1+rate)^(t/periods_per_year)`. `rate` is a finite decimal greater than -1 and `periods_per_year` is a positive whole number. Zero and negative periods are valid: 0 returns 1; a negative period discounts. The receiver is time, not an opening account value. |
| `finance.discount(value, r, t)` | `value/(1+r)^t`; a zero denominator returns null. The stated rate is `r > -1`, with arbitrary finite `t`, or `r=-1` with nonnegative integral `t`. At `r=-1,t=0`, the factor is 1. |
| `finance.present_value(cf, r, t)` | `cf/(1+r)^t` when `t >= 1`, otherwise null. Its rate domain is the same as `finance.discount`. Unlike that operation, a zero denominator uses §11.1.25's IEEE division rule: a positive cashflow at `r=-1,t=1` returns positive infinity. This is a per-row contribution, not a sum over periods. |

Exponents whose mathematical result or intermediate factor overflows or underflows
binary64 are outside this bounded domain. Powers allow relative error `1e-12`;
monthly compound conversion additionally allows absolute error `1e-15` because
subtracting 1 near zero loses relative precision. Exact null, shape and exceptional
value rules are not relaxed by a numerical tolerance.

#### 11.1.30 `finance.discount_factor`

Both operands are always recorded, including under `method="forward"`.

- **Spot:** for finite rates greater than -1 and finite periods, return
  `d[t]=(1+r[t])^(-p[t])`. A scalar rate broadcasts across a list of periods;
  a list rate accepts a scalar period or a same-length list. This entry states
  forms with at least one list. The output is `list[f64]`, with empty lists kept.
- **Forward:** the rate is a finite, non-null `list[f64]`, each rate greater than
  -1. For a list of length T, return exactly T factors: `d[0]=1` and
  `d[t]=product(1/(1+r[u]), u=0..t-1)` for `1 <= t < T`. An empty rate list
  returns an empty list. The period operand does not supply exponents, lengths
  or values under this method; it is retained as the caller's recorded operand.

The initial 1 belongs to the opening boundary. For rates `[0.1,0.2,0.3]` and
periods `[0,1,2]`, spot returns `[1,1/1.2,1/1.3^2]`; forward returns
`[1,1/1.1,1/(1.1*1.2)]`. These are distinct conventions even at the same horizon.
Nulls and non-finite inputs, rates at or below -1, and overflowing/underflowing
products are outside this entry. Finite results permit relative error `1e-12`.
It does not expand the excluded forms of `projection.prospective_value`.

#### 11.1.31 `curve.spot_rate` and `curve.discount_factor`

These operations resolve the **exact** `curve` source SHA to one curve recipe
(§15). A missing, inconsistent or ambiguous recipe is a refusal; a current curve
of the same display name is not a replacement. Identity verification is separate
from interpolation: matching a digest does not prove an evaluated rate.

The bounded evaluation domain here is a knot curve with `interpolation="linear"`
and flat extrapolation (the canonical recipe omits `extrapolation` for flat).
It has at least two strictly increasing finite tenors and finite rates greater
than -1. Times are nonnegative finite Float64 scalars or lists, without nulls.
For adjacent knots `(x0,r0),(x1,r1)` containing `t`, the spot rate is
`r0 + (t-x0)/(x1-x0)*(r1-r0)`. A knot returns its own rate; before the first
knot use the first rate and after the last use the last rate. There is no
calendar conversion of the time operand during either operation.

`curve.spot_rate(t)` returns that rate. `curve.discount_factor(t)` returns
`(1+spot_rate(t))^(-t)`, including 1 at time zero. Output has the same scalar/list
shape as time and Float64 cells; empty lists stay empty. Finite evaluations allow
relative error `1e-12` and absolute error `1e-15` for a spot rate near zero.
Nonlinear, forward-extrapolated and parametric recipes remain valid identities
but outside this evaluation entry. A reader must report its capability limit,
not replace their interpolation by linear. Non-finite/underflowing outputs are
outside the bounded domain.

#### 11.1.32 `projection.with_period` and `projection.broadcast_to_periods`

`with_period` takes a `list[f64]` and a finite Float64 replacement attribute.
`period=k >= 0` names position k; a negative k names position `T+k` for that
policy's length T. Replace precisely that cell when it exists. Otherwise return
the original list: an override never extends a shorter policy or adds a value
to an empty list. Null cells are kept except at the replaced position; a null
outer list stays null. The result is `list[f64]`. Multiple overrides compose
as nested calls in written order, so a later override of the same cell wins.
Other replacement/input dtype combinations are outside this entry.

`broadcast_to_periods` repeats each policy's scalar once per cell of its second,
list-shaped operand. Only that list's length matters, not its values. The
bounded scalar types are `i64`, `f64`, `bool` and `str`; output is a list of
that type. A null scalar repeats as null cells, an empty axis yields an empty
list, and a null outer axis yields a null outer result. Policies can have
different lengths; there is no repeat across policy rows.

A current producer records **both** operands. When the user omits `like`, the
second operand is `col("month")`, because its length is a real dependency. The
axis is read `INDIRECT` / `WINDOW` (section 9): its length reaches the answer
and its values do not.
The historical one-operand spelling is recognizable under the signature
schedule but lacks an explicit axis dependency; it is outside this portable
execution entry. A consumer must not manufacture a `month` read invisible to
the graph. Writing an explicit axis changes this expression's digest and the
affected graph identities; the existing two-operand grammar itself is unchanged.

#### 11.1.33 Date operations and Excel calendar arithmetic

This entry uses Gregorian `date` values, without times or time zones, in years
1–9999. An offset whose result leaves that range is outside the domain. Except
for `excel.yearfrac`, this entry states scalar operands only; the reference
producer refuses any other operation here whose operand is held per period by
name, where the line is written, and the JAX engine and the kit's reader refuse
one a document holds by name too (`calendar-operand-per-period`). Null operands
produce null results. The integer results below are `i64` in the neutral type
vocabulary, irrespective of a producer's narrower physical storage.

| Operation | Calculation and boundary |
|---|---|
| `date.months_between(start,end)` | `12*(end.year-start.year)+end.month-start.month`. Days are ignored: 31 January to 1 February is 1. Output `i64`. |
| `excel.days(end,start)` | Signed count of elapsed calendar days, **end first**. Output `i64`. |
| `date.to_period(d)` | `freq` Y/M/W/D (case-insensitive): start of year, month, Monday-starting week, or the same day. Output `date`. Other interval spellings remain outside this entry. |
| `date.offset_by(d)` | A signed integral count followed by `mo`, `y`, `w` or `d`. Months/years change the year/month and clamp the original day to the last valid day in the target month. Weeks/days add 7/1 calendar days per unit. Output `date`; compound durations are outside this entry. |
| `excel.edate(d,m)` | Move a signed whole number m of calendar months using the same clamp. Output `date`. An `f64` m that is a whole number is that number; one that is not is refused as a whole-number conversion refuses it (11.1.23), never truncated as the spreadsheet does, and text or a flag is refused by kind. |
| `excel.eomonth(d,m)` | Move m months, then return that target month's last day. Output `date`. m is read as `excel.edate` reads it: an `f64` m that is a whole number is that number, one that is not is refused as a whole-number conversion refuses it, and text or a flag is refused by kind. |
| `date.date_ranges(start,end)` | Output `list[date]`. `interval` is a **positive** integral count followed by `mo`, `y`, `w` or `d`. Candidate k is start plus k intervals, each offset from the **original start**, not from the previously clamped date. Keep candidates at or before end. `closed` both/left/right/none includes both/only start/only end/neither endpoint when it is a candidate. If end precedes start the list is empty. Null endpoints yield a null outer list. |

Thus a monthly range starting 31 January 2024 contains 29 February and then
31 March, not 29 March. A Monday week boundary can lie in the preceding year.
These are exact date/integer rules, with no numerical tolerance.

`excel.from_excel_serial` accepts finite scalar numeric serials or nulls and
returns `date`. Floor the serial to obtain its whole day; discard time-of-day.
Below 1 return null on **both** epoch systems. Under `epoch="1904"`, add the
whole days to 1 January 1904. Under `epoch="1900"`, serials 1–59 map to
1 January–28 February 1900; 60 also maps to 28 February (there is no real
29 February 1900); 61 maps to 1 March. Thereafter add the whole days to
30 December 1899. No other epoch token is defined here.

#### 11.1.34 `excel.yearfrac`

The two operands are dates, start then end. Scalar/scalar, list/scalar and
same-length list/list forms return Float64 in the corresponding shape.
Null date cells propagate. This entry excludes null outer lists. First put
start and end in chronological order: the answer does not depend on which was
written first, and is never negative. Equal dates yield zero. Let D be the actual elapsed day count.

| Basis | Rule |
|---|---|
| 2 | D/360 |
| 3 | D/365, including leap years |
| 4 | Replace a day-of-month 31 by 30 at either endpoint, then divide `360*year_difference + 30*month_difference + day_difference` by 360. |
| 0 | Before that 30/360 calculation apply the first of these that holds, and only it: both days are 31 — set both to 30; the start day is 31 — set it to 30; the start day is 30 and the end day 31 — set the end day to 30; both endpoints are February's last day — set both days to 30; the start is February's last day — set its day to 30. A start on February's last day therefore leaves an end day of 31 as 31: 29 February to 31 March 2024 is 31/360. |
| 1 | Same calendar year: D divided by that year's 365 or 366 days. The end in the year after the start and on or before the start's month and day: divide by 366 if the closed date interval contains a 29 February, and by 365 if it does not — 29 February 2024 to 28 February 2025 is 365/366. Otherwise — including 366 days that run past the anniversary, 25 September 2020 to 26 September 2021 — divide D by the arithmetic mean length of all calendar years from start.year through end.year, inclusive. |

These are the rules of D. A. Wheeler's reverse-engineered YEARFRAC, which OpenFormula and
Gnumeric follow, and this operation's; basis 1 must not be substituted with a
schedule's Actual/Actual ISDA year splitting. The text aliases, matched without
case, are: basis 0 `us_nasd_30_360`, `30/360`; basis 1 `act/act`,
`actual/actual`; basis 2 `actual/360`, `actual_360`, `act/360`; basis 3
`actual/365`, `actual_365`, `act/365`; basis 4 `european_30_360`, `30e/360`.
Aliases execute alike but remain differently typed/spelled identity attributes.
An unlisted basis is a refusal. Finite results allow absolute error `1e-12`.

#### 11.1.35 `excel.round` and `excel.pv`

`excel.round` takes finite Float64 scalar/list cells and a whole-number
`num_digits`, and answers what a spreadsheet's `ROUND` answers — which rounds
the value the spreadsheet holds, not the double beneath it. **Take the
operand's exact decimal expansion to fifteen significant digits, a sixteenth
digit of 5 or more going away from zero; round that decimal to `num_digits`
places, a half going away from zero; answer the double nearest the result,
with the operand's sign.** A double that is itself exactly a sixteen-digit tie
— `12345678901234.25` — goes away from zero at the first step too, and is
held as `12345678901234.3`. A negative operand that rounds to nothing answers
`-0.0`, and a whole-number operand answers a Float64 cell like any other. Where fifteen digits are no finer than the step — the operand's
magnitude times `10^num_digits` at `10^14` or above — the second rounding has
nothing left to move and the answer is the fifteen-digit value itself. The
double `68049.31499999999…` (a workbook's `1.5 * 45366.20999999999`) is
`68049.3150000000` at fifteen digits, a half, so it rounds to `68049.32` at two
places; a rounding of the double after binary scaling answers `68049.31`. This
entry bounds `num_digits` to -10..10 and the scaled magnitude below 2^52;
overflows and non-finite values are excluded. Nulls propagate and empty lists
remain empty. Output has the same shape and Float64 cells, and finite results
compare exactly.

`excel.pv` states three operands, a finite Float64 rate r, a nonnegative
integral period count n and a finite payment p (a whole-number operand is read
as its double), and two attributes of the call. `fv=null` means a future value
F of zero and `typ=null` means end-of-period payments (b=0); explicit typ 0 and
1 select end- and beginning-of-period payments respectively. With `r > -1`,
return `-(p*(1+r*b)*(1-(1+r)^(-n))/r + F*(1+r)^(-n))` when r is nonzero, and
`-(p*n+F)` at zero rate. Cash paid and value received have opposite signs;
zero periods return `-F`.

**Each of r, n and p may be held per policy or per period.** Where all three
are held per policy the output is one `f64` per policy. Where any is held per
period the output is `list[f64]`, answered cell by cell under 11.1.18's shape
rules: the operands held per period are paired period by period and must have
equal lengths within each policy, two that differ being refused by name; an
operand held per policy beside them reads as that policy's value in every
period; a policy's empty list answers an empty list and its null list a null
list. The formula, the zero-rate form and the tolerance below hold at each
cell as they hold per policy, so a nought rate in one period takes the
zero-rate form in that period alone. `fv` and `typ` are attributes, one value
for the whole call, never held per policy or per period. Other typ values,
negative periods, non-finite values and over/underflowing factors are outside
this entry. A null operand cell answers null in that cell, and a null operand
held per policy beside one held per period answers a null in each of that
policy's periods, however many operands are held per period. Finite results
allow relative error `1e-12`, **at every nonzero rate however near nought**: a
producer takes `(1+r)^(-n)` as `exp(-n·log1p(r))` and `1-(1+r)^(-n)` as
`-expm1(-n·log1p(r))`, never rounding `1+r` first, which at `r = 1e-12` loses
the rate's last digits (`8.9e-5` relative) and is why a producer that switched
to the zero-rate form below a threshold stepped there. The zero-rate form is
the answer at `r = 0` only.

#### 11.1.36 `excel.irr`

Cashflows are `list[f64]`, one regularly spaced stream per policy, with its
first cashflow at t=0. Output is one scalar `f64` per policy. A null outer
list, an empty list, a null cell, or a stream without both a positive and a
negative cashflow returns null. Null here is an unavailable result, never zero.

The bounded numerical domain for a non-null result has a negative initial
cashflow of magnitude at least 1, no later negative cashflows, at least one
later positive cashflow, at most 600 periods, finite cashflows of magnitude
at most 1e12, and its unique root in [-0.9,1]. Return r satisfying
`sum(cf[t]/(1+r)^t)=0`, with absolute rate error at most `1e-6`. This rate
budget is specific to this bounded solver domain; it is not a cashflow epsilon.
The vector reader uses bisection independently of the producer's Newton iteration.

A supplied guess is a scalar Float64 operand; a null guess cell falls back to
`default_guess`, whose null means 0.1. The absent guess operand uses that same
fallback. The bounded guess domain is [-0.9,1]. Arity still affects identity,
even when absence and a null guess execute alike. The producer attempts up to
50 Newton steps with an absolute NPV stop of 1e-7, then a bracket/bisection
fallback; derivative failure, an unbracketed root and exhausted iterations can
return null. A backend unable to meet the stated bounded value contract must
report that capability/failure, not call a solver's null a numerical agreement
with a known root.

Multiple sign changes can produce multiple roots: `[-100,230,-132]` has roots
0.1 and 0.2. Which root a guess selects, roots outside the bracket, non-finite
cashflows, and overflow/underflow in the solver remain **outside this entry**.
The identifier does not promise the smallest positive root or an Excel solver's
choice on those streams. The public vectors include that capability boundary;
none counts a producer result there as a portable value pass.

#### 11.1.37 Schedule and projection-frame operations

This bounded calendar family resolves the exact schedule source SHA (§15).
It admits `NullCalendar`, `Unadjusted`, `OneTwelfth`, and frequencies 1M/3M/6M/1Y,
with m=1/3/6/12 months per period. These are recipe values, not defaults a
consumer is free to fill in. Business-day adjustment, holiday calendars, other
day counts and weekly/daily cadence require separate evaluation capabilities;
a reader must not approximate them with this family. Beside it, the same identifiers
resolve a `fixed_step` recipe — 11.1.1's fourth form, which carries none of these
because it has no calendar — under the rules stated for that kind below.

**The cadence is written in one vocabulary here, and 11.1.1's `frequency` maps onto it.**
A schedule recipe carries the period shorthand — `1M`, `3M`, `6M`, `1Y`, and `1W` and `1D`
outside this bounded family — and 11.1.1 says outright that its own `frequency` is the
producing engine's spelling of a cadence rather than a vocabulary this document fixes. The
two are one axis written twice, and the mapping is: `monthly` is `1M`, `quarterly` is `3M`,
`semi-annual` is `6M`, `annual` is `1Y`, `weekly` is `1W`, `daily` is `1D`, and a token
already in the shorthand is itself. `m` — the months in one period — is 1, 3, 6 and 12 for the first
four and is not a whole number for the last two, whose periods are a week and a day. Every
boundary rule in this section is stated in months, so this bounded family covers the four
month-aligned cadences and not the other two; `p`, the periods a year, is defined for all
six and is what 11.1.1's year horizons are counted in. A consumer that answers only the
month-aligned cadences is reporting its own capability limit, which section 11.2 is where
it says so — this section states no refusal of its own. A consumer matching one spelling
alone misses the other, and this is the table that tells it which it is holding.

The four schedule kinds have distinct axes:

- `from_calendar_grid`: the recipe has a normalized start date, anchor and
  nonnegative n_periods=T. This entry states `anchor="exact_date"`; other
  anchors remain outside its boundary-date domain. The anchor is in the recipe, so
  a consumer that refuses another anchor refuses it from the payload alone, on
  inspection before any book is read as in a run.
- `from_inception`: the recipe names a non-null per-policy inception date and
  nonnegative T. Offset every boundary from that original inception date.
- `per_policy_grid`: a shared start date and a per-policy whole-number term in
  months or years. Convert years to months, then `T_i=max(0,term_months//m)`.
  **The recipe states no `n_periods`.** Its identity is its rule — `kind`, the
  cadence, the calendar, convention and day count, the start date, `until_kind`
  and the column or age each policy's horizon is read from — and no other
  policy's horizon is part of it, so a node that reads the schedule keeps its
  digest when another policy's term changes, when one policy runs alone and at
  every batch size. The longest horizon in a book is a fact of the run, the
  folded record's `run_metadata.n_periods` (§13.2), never of the recipe; a
  consumer that wants it reads it there or from the book. Null/negative terms have count zero, but are outside the boundary-date domain;
  there is no inferred expiry date for an unknown term. With `until_kind`
  `maximum_age` the recipe states `issue_age_column` and the age as exactly one of
  `maximum_age` (an integer), `until_value_column` (a column the call reads) or
  `until_value_expr` (an expression's rendering, outside this entry's count domain),
  and `T_i = max(0, trunc(A_i − x_i) × p)` in whole years, as 11.1.1 states.
  It states no `n_periods`, as for a term.
- `fixed_step`: the recipe is exactly `kind`, a nonnegative `n_periods=T` and one of
  `step_years` (a positive decimal) or `steps_per_year=n` (a positive integer), and no
  calendar, convention, day count, frequency, anchor or start. **It is outside the
  calendar family above and has no boundary dates at all**: every row's axis is the same
  `T + 1` boundaries, and the time at boundary `k` is `k × step_years` or `k ÷ n`,
  computed as one IEEE binary64 multiplication or division of the integer `k` (exact as a
  double) by the recipe's step, correctly rounded, and never as a running sum of the step
  or as `k` times a rounded reciprocal. The three differ in the last bits — `k ÷ 12` and
  `k × (1/12)` at 324 of 976 boundaries, `k × 0.1` and `k ÷ 10` at 1,002 of 2,948, a running
  sum of `0.1` and `k × 0.1` at 2,932 of 2,948 — and a workbook writes its time column one
  way, so the spelling is the recipe's and is exact.

For `from_inception` and `per_policy_grid`, boundary k is the original start
plus k*m calendar months, with the Gregorian day clamp of §11.1.33.
For a shared `from_calendar_grid` with `exact_date`, boundary zero is start,
and each next boundary is the previous boundary plus m months, clamped at
that step. The distinction matters: a quarterly shared grid from 31 January
2024 runs 30 April, 30 July; an inception grid runs 30 April, 31 July.
Neither rule silently re-anchors to month end. Boundaries have **T+1** cells, k=0..T.
Period values and masks have **T** cells, t=0..T-1. No extra terminal payment,
year fraction or in-force flag is implied by the final boundary.

| Operation | Output and applicable kind |
|---|---|
| `schedule.per_policy_period_count` | `i64` T_i, including zero for null/negative terms; per_policy_grid only. |
| `schedule.per_policy_period_dates` | `list[date]` boundaries, per_policy_grid only. A known zero term gives `[start]`. |
| `schedule.period_dates` | `list[date]` boundaries, from_inception only. |
| `schedule.year_fractions` | `list[f64]` of T copies of m/12, for all three kinds in the stated day-count domain. |
| `schedule.anniversary_mask` | `list[bool]` of T flags; true where `(t+1)*m` is divisible by 12. from_inception/per_policy_grid only. |
| `schedule.is_in_force` | `list[bool]` of T flags. For inception with an end-date column, true when that period's **end** boundary is <= the end date. Null end dates mean no known termination and yield true. Without an end-date column, or for either other kind, every period is true. |
| `schedule.contract_boundary` | Exact Boolean complement of is_in_force: true where the state machine must stop. It is not a one-cell marker for the first breach. |
| `projection_frame.period_dates` | Boundary dates for the schedule's kind, including a shared calendar grid; `list[date]`, T+1. |
| `projection_frame.year_fractions` | The same per-period fractions; `list[f64]`, T. |
| `projection_frame.t_years` | Zero followed by the cumulative sum of year fractions; `list[f64]`, T+1. |
| `projection_frame.anniversary_mask` | The same anniversary rule for any of the three calendar kinds; `list[bool]`, T. |

On a `fixed_step` recipe the same identifiers mean the following, and the time results are
**exact** rather than within the tolerance below:

| Operation | On `fixed_step` |
|---|---|
| `projection_frame.t_years` | `k × step_years` or `k ÷ steps_per_year` for `k = 0..T`, as stated above; `list[f64]`, T+1. Not the cumulative sum of `year_fractions`: the two differ in the last bits. |
| `projection_frame.year_fractions`, `schedule.year_fractions` | T copies of `step_years`, or of `1 ÷ steps_per_year`; `list[f64]`, T. |
| `projection_frame.anniversary_mask`, `schedule.anniversary_mask` | Under `steps_per_year=n`, true where `(t+1)` is divisible by `n`; `list[bool]`, T. Under `step_years` a refusal: whether a whole number of steps makes a year is not stated. |
| `schedule.is_in_force`, `schedule.contract_boundary` | Every period true, and its complement, every period false. An `end_date_column` is a refusal: there is no period end to compare a date with. |
| `projection_frame.period_dates`, `schedule.period_dates`, `schedule.per_policy_period_dates`, `schedule.per_policy_period_count` | Refusals: the axis has no dates and one shared count. |

The masks on a jagged grid describe the periods that exist on that grid; an
end-date column does not create more periods beyond its known horizon. At T=0,
all masks and fractions are empty, boundary dates contain the start, and
`t_years` is `[0]`. Date/Boolean/count results are exact. Fraction and cumulative
time results allow absolute error `1e-12`. Calendar recipes that lack a required
anchor/horizon operand, have inconsistent identities, or cannot be resolved are
refusals; a hidden frame column must not supply a missing recorded read.

#### 11.1.38 `to_float`

`to_float(value)` is checked widening to Float64. It accepts a scalar integer or
floating-point value, or a list of either, and preserves the scalar or list shape. A
floating-point value is returned unchanged, including a NaN and an infinity: every
floating-point width widens into a double exactly, so nothing is given up and nothing is
measured. An integer value `x` is converted where `-2^53 <= x <= 2^53`. The result type is
`f64` for a scalar and `list[f64]` for a list. An empty list returns an empty `list[f64]`.

A null is carried rather than refused, on a scalar, on a list item and on a whole list:
nothing about an absent value is too large for a double, so there is no loss to refuse.
An integer outside `[-2^53, 2^53]` refuses the whole invocation. That interval is where the
doubles stop being closer together than one: above it two neighbouring whole numbers share a
double, and a conversion that went through would make a later comparison read two
identifiers as one. Every other input type is refused, including Boolean, text and date. An
integer stored in a width wider than `i64` is an integer for this call and is judged on its
value like any other. There is no rounding, nearest-double or saturating form hidden behind
this identifier; a value past the interval that must travel as a number is rescaled in the
model, where the reader can see which unit it moved to.

#### 11.1.39 `to_text`

`to_text(value)` writes a value out as text without giving any of it up. It accepts a
scalar Boolean, integer, floating-point value, text, date, datetime or category, or a list
of any of those, and preserves the scalar or list shape. The result type is `str` for a
scalar and `list[str]` for a list. An empty list returns an empty `list[str]`. A null is
carried as null, on a scalar, on a list item and on a whole list.

The text is the value and not a rendering of it. An integer is written by its digits,
whatever width it is stored in and whether or not an `i64` could carry it — which is what
makes this the answer for an identifier section 10 has no exact numeric name for. A
floating-point value is written as the shortest decimal that reads back to the same number
at the width it is stored in, laid out by the convention below. A Boolean is `true` or
`false`. A date is its ISO calendar day, `YYYY-MM-DD`. A datetime is its calendar day and
time of day, `YYYY-MM-DD HH:MM:SS`, carrying the fractional digits its own time unit holds
and, where the column carries a zone, that zone's offset. Text and categories are carried
through unchanged: a category is a string with a dictionary in front of it, and the
dictionary was never content.

**The shortest decimal says which digits; this says how they are laid out.** The two are
separate questions and only the first is obvious, so a document that stated the first and
stopped left the second to whatever the engine's own printer did — and two conforming
implementations then wrote the same number two ways, which for an operation whose answers
are used as keys and tested in conditions is a difference in the model rather than in the
display. Write the digits of the shortest decimal as `d₁.d₂…dₙ × 10ᵉ`, with `d₁` not zero,
and then:

- **Fixed form when `-5 ≤ e ≤ 15`**, with the digits placed at the point and at least one
  digit after it: `0.00001`, `0.000015`, `0.1`, `100.0`, `1000000000000000.0`. A value whose
  decimal is whole still carries `.0`, which is what keeps it from reading back as an
  integer.
- **Exponent form outside those bounds**, mantissa then `e` then the exponent: `1e-6`,
  `1.5e-6`, `1e+16`, `1.2345678901234568e+16`, `5e-324`. **The exponent always carries its
  sign, `+` as well as `-`, and is never padded**: `1e-7`, not `1e-07`. The mantissa carries
  a point only where it has digits after it, so a power of ten is `1e+20` rather than
  `1.0e+20`.
- **A negative value carries one leading `-`** and is otherwise written as its magnitude is,
  **a zero included**: `-0.0` and `0.0` are two texts, which is the same sign this operation
  reads that section 12.1's identity now reads with it.
- **The three non-finite values are `NaN`, `inf` and `-inf`.** These are what this operation
  *computes*, and they are a `str` column's values like any other. Section 10's `"NaN"`,
  `"Infinity"` and `"-Infinity"` are a different rule about a different thing — how a
  non-finite value travels on the wire *in an `f64` column*, where JSON has no token for one
  — and the two never meet: once this operation has run, the column is `str` and holds the
  text this clause names. A consumer must not read `inf` in a `str` column back to a number,
  and must not write `Infinity` where this clause says `inf`.

Those two bounds are the bounds for a double, which is the one float width section 10's
vocabulary names. A value the producer holds in a narrower float is written by the same
construction at that width — its own shortest decimal, its own switch — and the record does
not carry the width (section 10), so a consumer replaying from the document alone reads the
double's convention. That is a real limit and it is named here rather than left to be
discovered.

Every other input type is refused by name, including a duration, a decimal, a time of day, a
binary value and a fixed-width array. Each would have to be written out under a convention
the model never stated, and a text no reader can read back is not a conversion. There is no
format, locale, padding or separator attribute: the wording a report wants is built from
this text rather than selected inside this call — and the convention above is not one of
those either. It is not a setting a model chose; it is what this operation means, and an
implementation that wrote the same double some other way has implemented a different
operation.

#### 11.1.40 `to_list`

`to_list(value)` converts a fixed-width array into a list of the same elements. It accepts a
column whose type is an array of a section 10 scalar element type, and answers `list[T]` for
an array of `T`: the same elements, in the same order, with the element type unchanged. The
fixed width is the only thing given up, and an artifact records no fixed width, so nothing
the record carries is lost. A null element stays null and a null array answers null. An
array of width zero answers an empty list.

A column that is already a list refuses rather than passing through. The operation would
leave such a column exactly as it found it, and a node that sometimes converts and sometimes
does nothing means two things to a reader of the trace. A scalar refuses for the same
reason in the other direction: it is not a run of elements. An array whose element type
section 10 has no name for refuses by that element type, because the list it would answer is
one this document could not describe. There is no padding, truncating or re-widthing form
hidden behind this identifier.

#### 11.1.41 `list.reverse`

`list.reverse(value)` turns each policy's own list end for end. For policy `i`, let its list
have length `T_i`: position `t` of the result is position `T_i - 1 - t` of the operand, for
`t = 0..T_i - 1`. The result has the operand's length and its element type, whatever type
that is (section 10), so `[10.0, 20.0, 30.0]` answers `[30.0, 20.0, 10.0]`. An empty list
answers an empty list, and a null outer list answers null: a policy with no column rather
than a policy with no periods, the distinction 11.1.9 draws.

**A reversal moves values and combines none of them**, so a period carrying no value moves
with its position and stays a period carrying no value: `[1.0, null, 3.0]` answers
`[3.0, null, 1.0]`. Nothing is lost by it and nothing beside the null becomes unknown. The
rule 11.1.9 states is about a running total that lost a term, and there is no running total
here.

**The length is the policy's own, never a shared one.** On a book whose policies have
different period counts, policy `i` is reversed within its own `T_i` periods, so its last
period becomes its first. A backend that holds the book in a rectangle padded to one width
reverses within each policy's own length and never across the padding, or a short policy's
first period would be a cell nobody projected.

**An edge into `list.reverse` is `DIRECT` / `AGGREGATION`** (section 9), although nothing is
folded. Period `t` of the answer is the operand's period `T_i - 1 - t`, which turns on the
policy's length, so no one distance describes the read and every period of the operand is in
some period of the answer. An impact cone drawn through a reversal has to sweep the whole
axis, and a reviewer told it was a transformation of this period's value would be told the
opposite of the truth.

**What it is for.** A rollback a workbook writes as a row reading the row below it is most
often linear, and a linear one is `projection.accumulate` under `reverse` (11.1.20).
Discounting alone is `projection.prospective_value` (11.1.21) and a suffix sum is
`projection.remaining_sum` (11.1.20). This identifier is what a rollback that is not linear is
written with: reverse, a forward calculation, and reverse back. Over the same operands,
`projection.accumulate` under `reverse` and the forward recurrence written between two
reversals give the same doubles.

The operand is one list per policy, of any element type. A per-policy value has no periods
to turn and is outside this entry; a consumer may refuse it.

### 11.2 Tiers

A tier says how much of a node this specification can account for.

| Tier | What it says |
|---|---|
| `core` | Every operation in the node's tree is in this specification's own vocabulary (§11.1) at tier `core`. |
| `engine_native` | Somewhere in the tree is a fragment written in one engine's own expression language, declared rather than hidden. |
| `opaque` | Somewhere in the tree is an identifier the producer carries but cannot classify. |

A fragment that reads across rows answers the book's figure only where the frame it runs over
is the book, or a window whose partition includes the scenario, within a scenario's whole copy
of it; §13.2 says where a producer refuses it and where it admits the partitioned form.

**A node's tier is the weakest tier reached anywhere in its operation tree.** `core` is
stronger than `engine_native`, which is stronger than `opaque`; one unclassifiable leaf makes
the whole node opaque. A tier reporting the strongest thing found would tell a reader the
node was more accountable than it is.

A `rollforward` node carries a tier like any other node with a tree, and its tree is the
single call `rollforward` (§16), which section 11.1 lists at `core`. **That is a statement
about the vocabulary and not about the payload.** The compiled state machine itself is what a
second implementation would need to *run* the node, it is no part of the `audit` profile, and
the profile is where that question is answered — the same separation as any other operation
whose data sits out of band, such as a lookup and its table.

The `audit` profile carries the tier without the operation tree it was computed from
(section 3), so a consumer holding only `audit` reads it as the producer's statement about
the node.
`tier` and `engines` (section 8.3) are related but are not the same claim: `engines` names
what a node's text needs and may be left out entirely, while `tier` is stated on every node
that has anything to execute. Section 6.2 says what an `engine_native` node may declare about
the core operation it is closest to.

### 11.3 Operation vectors

The reference distribution carries synthetic, machine-readable operation
vectors beside the schema, under `gaspatchio/schemas/vectors/`. Their envelope
is identified by `gaspatchio-operation-vectors/v0-preview.1`, independently of
the artifact schema and fingerprint tokens each envelope also names. A vector
document is an invocation test, not a sealed graph artifact. It does not
substitute for §12.5's identity corpus, or claim that an arbitrary model can run.

Each case names its id, the identifiers it exercises (`covers`), typed input
columns, and an `expr` using the executable artifact's existing tree grammar.
Input `values` are model-point rows; a `list[T]` input has one list per row.
An empty outer array means no policies, an empty inner array no periods for
that policy, and null is JSON null. Non-finite numeric cells are represented
by `{"nonfinite":"nan"}`, `{"nonfinite":"+inf"}` or
`{"nonfinite":"-inf"}`; these tagged objects are vector cells, never operation
literals or a change to the artifact's value encoding.

A `value` case gives the expected dtype/values and explicit `atol`/`rtol`.
Finite floating cells compare by
`abs(actual-expected) <= atol + rtol*abs(expected)`; integers, Booleans, shapes,
null locations and strings compare exactly. NaN must match NaN, and infinities
must match their sign. A zero budget is an exact-value check, not a promise
about sign-of-zero or NaN payload bits. A case budget belongs to that case;
it does not become a general whole-model tolerance.

A `portable-domain-refusal` case names the reason an invocation falls outside
the stated portable subset. `producer_check: false` expressly records that
the existing producer may execute such an invocation with behavior this subset
does not promise. Such a case is checked by the independent subset reader,
not counted as a producer refusal or a passing full-backend comparison.
`producer_check: true` on a refusal requires the producer to refuse as well.
`backend-capability-refusal` and `integrity-mutation` are separate case
classes; neither can be relabelled as a numerical pass. An
`artifact-type-refusal` can evaluate natively but refuses artifact export;
its producer check covers both audit and executable profiles. A
`recording-door-value` case supplies setup/join invocation data in
`producer_setup`, and names the output column. A join comparison may state
`sort_output_by` to compare model-point identity rather than streaming row
position. This does not add an ordering guarantee to the join contract.
A `selection-value` case states section 7.6's steps under `selection` — each
step's `kind` and predicate `expr` as a document's entry carries them, and a
semi or anti join's right side under `right` as columns of values — and its
`expr` is evaluated over the rows the steps keep, in the book's order.
`vectors/selection.json` carries filters (a null answer keeping nothing, a
compound predicate), a semi and an anti join, two steps in order and a
selection that keeps no policy; each join's `right_fingerprint` is the
producer's digest of its right side, which the producer check holds the
recorded step to.

Assumption-backed cases supply canonical recipes or typed table payloads in
`assumptions`. Rollforward cases carry the compilation facet in
`compilations`; `producer_build` is a public builder recipe for producer
replay, not the independent reader's calculation oracle. Literal, recipe
and payload encodings remain those of their respective artifact contracts.

**A perturbation vector holds an engine to the window an edge states** (§9). A
`value` case may carry `perturbation`: `of`, the id of the case it departs from,
which it equals except for one cell; `operand`, `policy` and `period`, the cell
moved; and `window`, the `periods` or `position` the answer's read of that
operand states. The relation is the contract: every period of the answer whose
window excludes the moved period, and every other policy's answer, equals the
base case's; and where some period's window includes it, at least one such
period differs. Each such case is still an ordinary value case, so a reader
that knows nothing of the member checks its numbers as it checks any other.
`vectors/windows.json` carries one base and at least one moved case for every
row of §9's table — both scan directions, the survival fold with and without an
opening value, the recurrence in both directions and on both step operands, a
compiled rollforward, the suffix sum, a prospective value's cashflows and list
rate under both timings, the four reductions, the internal rate, a reversal, a
forward discount factor, a literal position counted from either end, and one
composition — over two policies of unequal length, in halves and powers of two
so that every cell compares exactly.

The adjacent `gaspatchio/schemas/conformance/index.json` maps all 101
identifiers to clauses and case ids: 99 have bounded value examples, bare
`rollforward` has structural evidence, and `rollforward.struct` has an explicit
portable-output exclusion with a producer export-refusal fixture (§16.3). `when_then` has separate composition examples.
These are examples of the stated domains, not exhaustive coverage of every
boundary or a full-backend conformance certificate.

The kit carries `vector-envelope.schema.json`, a clause-by-clause
`boundary-review.json`, the §12.5 corpus and a standard-library `reader.pyz`.
The review links selected value/refusal cases, named exclusions and producer
checks for each clause. A zero-policy example covers every bounded value
identifier. This is a reviewed boundary checklist, not an exhaustive Cartesian
product of dtypes, shapes and configurations or a general backend certificate.
A case may use `producer_setup.table_storage="hash"` to register a synthetic
table with that storage mode; storage selection is not part of its value identity. Copy the kit and adjacent vectors together;
`python -I reader.pyz ../vectors/*.json` verifies invocation results and
`python -I reader.pyz --identity corpus.json` independently recomputes the
fixed corpus's current-token digests — every node's two, `graph_fingerprint`,
the formulas-only figure of §12.6 and the seal; `python -I reader.pyz --citation
citations.json` checks that a comparison report over the corpus cites it by
that seal as well as its fingerprint (§13.1). The archive's readable source and
deterministic builder live in `spec/graph-artifact/conformance/`, without
private `ref` dependencies. The value reader is an oracle for published
invocations, not a general artifact loader or a supported execution backend.
The independent identity reader transcribes §12.5's model; it does not claim
general compiler-fingerprint coverage or authenticity verification.

## 12. Identity and fingerprints

Every node carries two hashes.

`local_fingerprint` is SHA-256 over the canonical bytes of that node's operation tree: what
the node computes, and nothing else. `fingerprint` is SHA-256 over that node's
`local_fingerprint` followed by the fingerprints of everything the node reads, in the order
it reads them — which is the order `reads` states, and is part of the calculation rather
than an incidental ordering.

Two hashes rather than one, because a reviewer's question is never "did anything change?".
A node whose `local_fingerprint` moved between two artifacts was edited. A node whose
`local_fingerprint` held and whose `fingerprint` moved was **not** edited: its formula is
what it was, and its answer still cannot be, because something upstream of it changed. One
hash cannot tell those apart, and telling them apart is what turns a diff of two artifacts
into a report a reviewer can act on.

Both fields are stamped in the form section 8 gives — `sha256:` followed by sixty-four
lowercase hex digits. The digest that folds into a dependent node's `fingerprint` is the
raw thirty-two bytes, not the stamped string; the prefix is the stamped field's form only.
The digests are fixed width, which is why the fold needs no count in front of them.

**The fold takes `reads` and only `reads`.** `reads_assumptions` names things a node reads
too, and it does **not** enter this hash — a deliberate exclusion rather than an oversight,
and one worth saying because folding it in produces a well-formed digest that matches
nothing. An assumption base's identity is already inside the node's `local_fingerprint`: a
lookup carries its table's content hash as an attribute (section 12.1), so a base that moved
underneath the model moves the node's *local* digest, which is the reading a reviewer wants
— the calculation itself is now a different calculation. Folding the same hash in a second
time would move the node's `fingerprint` without moving its `local_fingerprint` on a base
change, which is the signature this format reserves for "not edited, but something upstream
was", and a base is not upstream in that sense. Section 12.4's second section is where the
fact is lifted out for a reader to point at.

**A producer folds its own recomputed digests; a consumer folds what the profile carries.**
Every fingerprint in a published artifact was taken over digests the producer computed in
the order the calculations ran, so the file is internally consistent by construction. A
consumer verifying one has a choice, and the profile settles it: in `audit` there is no
operation tree, so the only fold available is over the *published* upstream fingerprints,
and what that verifies is propagation. In `executable` a consumer recomputes from the tree
every `local_fingerprint` it has a tree for, and folds its **own** recomputed upstream values
— never the published ones — because a producer that erred is exactly the case verification
exists for, and a fold over published digests would agree with the error. Section 13 states
what each profile buys, and which node kind carries no tree to recompute from. A leaf needs
none: its bytes — its tag, its name and its type — are on the node in both profiles, so a
consumer of either may recompute a leaf's `local_fingerprint` and fold its own value.

The canonical bytes of a **computed** node deliberately exclude three things: **the source
location, any rendered expression text, and the node's own column name.** Reformatting a
model, moving a definition to another file, or renaming a computed column is therefore not a
model change. That is what lets a rename be reported as a rename rather than as one
calculation deleted and an identical one invented at the same moment.

**A leaf is the exception, and deliberately so.** A leaf is a node nothing on the model
defines — an arriving column, or a hole — and its bytes are its tag, its name and its type
(section 12.1). It has no calculation to be identified by, so its name and its type *are* its
identity: renaming an arriving column or a hole moves that leaf's `local_fingerprint`, and
every `fingerprint` downstream of it with it. That is the reading a reviewer needs. A column
the model was handed under one name last quarter and another this quarter is a change in what
the model was handed, and a column that stops being explained between two quarters must be
visible as a change rather than absorbed as a rename.

The consequence is worth stating outright rather than leaving to be discovered: **two
columns computed the same way share a `local_fingerprint` by design.** It is not a
collision and a consumer must not treat it as one. Section 12.4 says how the graph
fingerprint stays sensitive to which formula binds to which name in spite of it.

### 12.1 The canonical byte grammar

This subsection is normative. The canonical bytes of a node are its type tag followed by
that node's own fields in declaration order, with child nodes encoded in place. There is no
framing around the whole, no separator between fields, and no header: every piece is
self-delimiting, and a node's bytes are exactly the concatenation below.

**One tag byte per node type.** A node's bytes begin with its tag, so that two kinds of node
can never encode alike however similar their payloads look.

| Tag | Node type |
|---|---|
| `0x01` | column reference |
| `0x02` | literal |
| `0x03` | binary operation |
| `0x04` | call |
| `0x05` | conditional |
| `0x06` | state reference |
| `0x07` | engine-native |

**One tag byte per scalar type**, for a literal's payload and for a call attribute's value. A
term of thirty years, the text `"30"`, and a true/false flag are three different things to
every consumer that reads them back, so they are three different encodings here.

| Tag | Scalar type |
|---|---|
| `0x10` | absent |
| `0x11` | boolean |
| `0x12` | whole number |
| `0x13` | decimal |
| `0x14` | text |
| `0x15` | sequence |
| `0x16` | date |

**Three leaf tags**, for a node with no operation tree to hash — a column the data arrived
with, a column nothing in the model accounts for (section 7.1), and a running state of a
rollforward (section 8.1). Separate tags because the three make different claims about a
model: "the data supplied this", "nothing here can explain this", and "this is not a column
at all". A column that stops being explained between two quarters must be visible as a
change rather than as nothing.

| Tag | Leaf |
|---|---|
| `0x20` | arriving column |
| `0x21` | unaccounted column |
| `0x22` | running state |

**The primitive encodings.**

- **Counts and byte lengths** are unsigned base-128 varints, low group first: seven bits per
  byte, the high bit set on every byte but the last.
- **Whole numbers** are zigzag-encoded and then written as a varint: `-1` becomes `1`, `1`
  becomes `2`, `-2` becomes `3`. Two's complement would spell every negative number at full
  width, and a period offset of `-1` is routine enough to deserve its one byte.
- **Decimals** are their eight IEEE-754 bytes, most significant first — **a negative zero
  included, which therefore hashes apart from a positive one**. The two are one number in
  the arithmetic, and this grammar wrote them alike until `gspv0-preview-3` for that reason;
  but the vocabulary this identity is published beside can tell them apart. `to_text`
  spells them differently (section 11.1.39), `sign` and section 11.1.25's division observe
  the sign, and `round_sig_figs` carries it through — so a model whose one edit was a minus
  sign printed `0.0` one quarter and `100.0` the next under identical node, closure and
  graph fingerprints, and the change report said there had been no drift. **An identity must
  not equate what an admitted operation can distinguish**, and where the two rules disagree
  it is the identity that gives way, because the alternative is a document whose silence is
  wrong. The one document in the world this reaches is one carrying a negative-zero literal:
  every other digest ever taken is the digest this grammar takes.
  **Every NaN is still written as the single quiet payload `7ff8000000000000`**, and that
  rule is untouched. Two runs that both produced a NaN have not drifted, and reading their
  differing bit patterns as two different models would be a false positive in the one report
  whose value is its silence — which is not the signed zero's case, where one bit is what an
  author wrote and an operation reads back. The infinities keep their own distinct bits.
- **Text** is UTF-8 behind its byte length.
- **A true/false flag** is one byte behind its tag: `0x01` for true, `0x00` for false — the
  same byte and the same two values the content grammar of section 12.3 writes for a `bool`
  column. Two grammars spelling one flag two ways would be a distinction nothing is on
  either side of. **The tag is live rather than reserved**, and a producer whose host
  language makes a boolean a kind of whole number has one thing to get right: test for the
  flag *before* the number, or `true` encodes as the whole number `1`, `0x11` is never
  emitted at all, and a flag and a count collide in the digest whose whole job is to keep
  them apart.
- **A sequence** is its own count followed by each element encoded behind its own scalar tag.
  **A sequence is flat and its members are narrower than a scalar**: text, a whole number, a
  decimal, a flag, or absent. A member that is itself a sequence is refused rather than
  nested, on the way in and on the way back — and so is a date, which is a literal's whole
  payload in this grammar and never a member of one. This is the one place section 10's vocabulary and this grammar
  part company, and deliberately: `list[T]` is a *column* type and nests three deep there,
  while a literal sequence is what an author wrote into one formula — a band's breakpoints,
  a set of product codes, a schedule of loadings — and no formula in this vocabulary writes
  a band of bands.
- **Every variable-length run** — a call's arguments, a call's attributes, an engine-native
  fragment's declared reads, a sequence's elements — is written behind its own count. Every
  other piece of the encoding is already self-delimiting, so the count is belt as well as
  braces; it means one argument named `ab` can never flatten to the same bytes as two named
  `a` and `b`, and it states a run's boundaries outright rather than leaving them to be
  inferred from an argument about which tag bytes happen not to look like which length bytes.
  That argument is how tree hashes end up accepting something they never hashed.

**An absent run is the empty run**, and it is a rule here rather than a description of one
producer. A call written without `args`, without `attrs`, or an engine-native fragment
written without its declared reads, encodes exactly as one written with an empty list would:
a count of zero and nothing behind it. "No arguments" is not an ambiguous sentence, and a
document that spelled the empty run two ways would hash one call two ways.

**A whole number and a decimal are told apart by the wire token, never by a parsed value.**
Sections 10 and the schema type a literal's payload and an attribute's value as a JSON
number, and JSON has one number type where this grammar has two tags. So the rule runs both
ways and both halves are normative:

- **A producer MUST write a `0x12` value as a JSON number token with no decimal point and no
  exponent** — `1`, `-1`, `30` — **and a `0x13` value as a token that carries one** — `1.0`,
  `0.00123`, `2e-3`. The distinction is in the characters on the wire, so a producer that
  renders every number the same way has published a document nobody can hash. A `0x12` value
  lies in `[-2^63, 2^63 - 1]`.
- **A verifier MUST take the tag from the token as written, before any parse that would
  destroy it.** `{"value": 1}` encodes as `021202` and `{"value": 1.0}` as
  `02133ff0000000000000`; they are two literals and two digests. In a language whose parser
  yields one numeric type — JavaScript, a Go `interface{}`, `jq` — reading the tag off the
  parsed value collapses the two, and every model carrying a whole-number offset reproduces
  the wrong digest with nothing to say why. Read the token, or read the document with a
  parser that keeps the two apart.

**A date is a scalar in this grammar, under tag `0x16`.** It is the number of whole days from
1970-01-01 to the date, counted forward, zigzag-encoded and then written as a varint by the
rules already given for a whole number. 1970-01-01 is `0` and encodes as the single byte
`0x00`; 1970-01-02 is `1` and encodes as `0x02`; 1969-12-31 is `-1` and encodes as `0x01`.
The count is of days and never of seconds, milliseconds or microseconds, and it is the same
count the content grammar of section 12.3 writes behind the same tag, deliberately: a reader
holding both grammars meets one number and one layout for a date.

**The day count runs on the proleptic Gregorian calendar**, which is the calendar every date
type in section 10's vocabulary is held on, extended backwards without limit. There is no
time zone in a date, no offset applied on the way in or out, and no leap second: a date is a
calendar day, and the count is a count of calendar days.

**This section used to refuse a date, and the refusal was justified by a sentence this one
withdraws.** It read that reaching for the content grammar's date tags here would have them
mean two things in two grammars — the opposite reading of the shared block section 12.3 calls
a feature, and both sentences were in this document at once. It is resolved in section 12.3's
favour, because that section is the one that made the block shared and already documented the
one place the sharing is a number without a layout (*"`0x15` shares the number and not the
layout"*): a grammar that borrows a byte **and its bytes** has not made the byte mean two
things, it has made it mean one. Under the old rule a producer handed a date refused to
produce the artifact — and the reference producer did not refuse, it reached for the escape
hatch, so a `date.months_between` whose second operand was a calendar date reached a reader
as engine text on a node declaring it needed one engine, when what it needed was a date.

**A date is not a text and a text is not a date, and JSON cannot tell a reader which it is
holding.** The wire form is therefore structural and not a spelling: a date literal is
written `{"op": "lit", "date": "2024-01-01"}`, under its own key, and **exactly one of
`value`, `values` and `date` is present on a literal**. This is the same discipline the
section already applies to whole numbers and decimals — the tag comes off the document as
written, before any parse that would destroy it — arriving through a key rather than through
a token because JSON has a number token and no date token. A producer that wrote a date under
`value` has written the text `"2024-01-01"`, which encodes as `0x14` and its eleven bytes; a
consumer that read `date` as `value` reproduces a well-formed digest matching nothing.

**A date is a literal's whole payload and never a member of a sequence.** `values` holds
flags, whole numbers, decimals and text, as it always has; a date under it is refused. The
two grammars share this block, and this is the second place where they agree on a number and
part below it — section 12.3 already says `0x15` shares the number and not the layout, and
here `0x16` shares both, in a literal and not in a member of one. A membership test against a
set of dates is therefore an engine fragment, and the node says so, which is what this
document says about every calculation it cannot yet spell. The sequence form is a grammar
change like any other, and it lands the day a producer holds one.

**The text under `date` is a calendar date in ISO 8601 extended form and nothing else** —
four digits, a hyphen, two digits, a hyphen, two digits, for a year in `0000`–`9999` — with
no time, no offset, no `Z`, and no compact form. A wider year range and the other forms are
refused rather than accommodated: the value hashed is the day count, so two spellings of one
day would be one digest under two documents, and a consumer checking one against the other
could not say which spelling the producer wrote.

**`0x17`, the content grammar's instant, is deliberately not minted here.** No shipped model
writes a datetime literal into a formula, and a tag nothing writes is an untested token in a
grammar whose whole value is that two implementations agree on it. A model comparing against
an instant writes the instant onto the frame in a line of its own and compares against the
column, which is what this section told every model to do about dates until now. **A producer
must test for the instant before the date**, in every host language where an instant is a
kind of date — Python is one — or a datetime encodes as its own calendar day, loses its time
without a word, and `0x17` is never reached. That is the same trap the flag-before-number
rule above is written against, one type down. When a producer holds an instant, `0x17` lands
additively with a change-log line, and it will already have the content grammar's layout to
copy.

**A worked example**, and it is the flagship's own first date line. The date `2024-01-01` is
19 723 days after 1970-01-01. Zigzagged that is 39 446, and as a varint, low group first,
`96 b4 02`. So the literal encodes as five bytes:

```text
02                                       literal
16                                       date
96 b4 02                                 19723 days, zigzagged, as a varint
```

```text
021696b402
```

**A date may be a call attribute's value as well as a literal's payload**, by the same
encoding, because the two share one scalar block. No identifier's signature in section
11.1.11 currently puts a date in an attribute — `projection_set`'s `valuation_date` is text,
an ISO date, and stays text, because the signature says so and moving it would move every
projection's digest to say something the schedule already says. A signature that wants a real
date can take one additively.

**A tree node carries the keys its own kind declares and no others.** The seven branches of
the published schema are closed, and the reason is that a node's keys are closed while its
identity is not. This grammar reads the kind off `op` and encodes what that kind carries, so
a node relabelled to a kind that carries less keeps every key it had and loses them from its
digest. A `call` relabelled to `state`, with its arguments and its configuration left in
place, hashes as `0x06` and the identifier alone: fifty-two bytes of operands and
configuration leave the digest, and before the closure the document was valid on the way out.
That is a file in which one node's whole calculation has been struck out passing validation
and carrying a digest that no longer covers what it dropped.

A refusal under `oneOf` reports itself as *"is not valid under any of the given schemas"*,
which names no key and leaves a producer comparing its document against seven branches by
eye. **The schema is what refuses; a validator is what says why**, naming the `op`, the key
and the JSON pointer. The envelope's stated openness (section 6) is untouched: the closure is
of the seven trees and of nothing above them, and a document carrying an unknown envelope
member or an unknown node member validates exactly as it did.

**The nodes.**

| Node type | Bytes |
|---|---|
| column reference | `0x01`, the column name as text |
| literal | `0x02`, the value as a scalar |
| binary operation | `0x03`, the operator identifier as text, the left operand, the right operand |
| call | `0x04`, the operation identifier as text, the counted run of its positional arguments, its attributes |
| conditional | `0x05`, the test, the then-branch, the otherwise-branch |
| state reference | `0x06`, the state name as text |
| engine-native | `0x07`, the engine name as text, the fragment as text, the counted run of the names it declares it reads |

**A call's attributes** are a counted run of key-then-value pairs — the key as text, the
value as a scalar — **sorted by the key text, with the encoded value breaking a tie.**
Sorted rather than left in the order the call happened to build them, so that two records
configured identically encode identically; the encoded value breaks ties so that the order
is total rather than merely stable. **By the key text, not by the key's encoded bytes**: a
key is encoded as its byte length in front of its UTF-8, so the two orderings disagree
whenever a shorter key would sort after a longer one — `content` before `origin` by the
text, `origin` before `content` by the bytes, on a pair section 12.5's own corpus carries.
An implementation that sorted the encodings would reproduce a different digest for that
node with nothing in this section telling it which of the two readings it had taken.

**Sorted means by Unicode code point**, here and in section 12.4's three sections. UTF-8
preserves code-point order, so for a key a reader can hold in their head the two answers
agree and the rule reads like a formality; it stops being one the moment a column or a
dimension is named in a language whose letters sit outside ASCII, which "meet you where you
are" invites rather than discourages. Code point, then — not a collation, not a locale, not
a case-folded or accent-stripped order, none of which two implementations agree on.

**A null attribute is written, and it is not the same claim as an absent one.** A key whose
value is null encodes as the key and the tag `0x10`, and it counts towards the run; a key
that is not there encodes as nothing and does not. `fill_value: null` on a lookup says the
call was configured with no fill and the producer looked; a missing `fill_value` says this
producer does not write that key at all. Those are two records and two digests — the count
byte moves as well as the payload — and a consumer must neither drop a null on the way in
nor add one on the way out. **This is the common case rather than the corner**: a lookup left
on its default miss policy writes `on_missing: "raise"` and `fill_value: null` together, so
the ordinary assumption-table read in an ordinary model already carries a null attribute. A
producer writes the keys the operation's schedule (section 11.1) says it writes, and writes
them whether or not the value each holds is null.

**A digest carried as an attribute value is hashed in its stamped form** — the whole string
`sha256:` and sixty-four lowercase hex digits, as text, behind `0x14` and its length: two tag
and length bytes and seventy-one of payload. That is the opposite of the fold's rule in
section 12, and the two are not in tension: the fold concatenates fixed-width raw digests
because nothing there is text, while an attribute value is a scalar and the scalar it is is
the string the record carries. `table_fingerprint` on a lookup and `fingerprint` on a
compiled rollforward are both hashed as the seventy-one characters they are written as,
prefix included.

**A leaf's bytes** are its tag, its name as text, and its type as text, the type being one
from section 10's vocabulary. A leaf has no formula, so these bytes are what its
`local_fingerprint` is taken over.

**A leaf's name is the leaf's own, and for a running state that is the state reference rather
than the id built around it** — `account_value@eop`, exactly the string a state-reference node
inside any operation tree carries, and not `state:account_value@eop`. What identifies a state
is what its compilation calls it; the `state:` namespace is how one artifact keeps its ids
apart, and section 8.1 says an id is positional within one artifact and means nothing across
two. A producer that hashed the id would put an artifact-local convention inside a digest
whose whole purpose is to compare two artifacts.

**Which field the name comes off, for each of the three leaves.** An arriving column and an
unaccounted column are accounts of a column, so the name is the node record's `column` — the
field section 8 calls authoritative, and never the `id`, which a column containing an `@`
would make unrecoverable anyway. The two coincide on most models, and that is precisely why
the rule has to be stated: an implementation that reached for the `id` would agree with this
one everywhere except where it mattered. A running state is not an account of a column,
carries `column: null`, and takes its name from the state reference as the paragraph above
says.

**A leaf may carry `unknown` for its type, and `unknown` is then what is hashed** — the seven
characters, as text, exactly as a named type would be. Section 10 says `unknown` is not a
type, and that stands: it records that the producer never determined one. But a leaf's bytes
are its name and its type, so a leaf that carries `unknown` has to encode something, and the
answer is the string the record carries rather than an empty text or a refusal. This is not
a corner: **a running state always carries it.** A compilation's carried value is not a
column of the frame, nothing probes it for a type, and a producer that invented one would be
putting a guess inside an identity. An unaccounted column minted for a name no frame ever
held carries it for the same reason. What section 10 forbids is writing `unknown` for a type
a producer *met* and could not map — that is a refusal — and what its validator flags is
`unknown` on a node in the final schema, which no leaf of either kind is.

**A compiled rollforward is not a leaf.** Its bytes are a call (§16): the identifier
`rollforward`, no arguments, and two attributes — `fingerprint`, carrying the compilation's
own published identity as text, and `schedule`, the `source_sha` of the schedule the machine
runs on. That identity is already a hash over the whole state machine — every state, every
operation, in order — so restating the machine here would hash one structure twice under two
grammars. **The identity is defined, and a consumer recomputes it.** It is the section 12.3
recipe-grammar hash, `sha256:` and sixty-four lowercase hex digits, of the compilation body
exactly as the `gaspatchio_rollforward_ir` facet publishes it under that identity (section 16)
— `points`, `states`, `increments`, `track_increments`, `lapse_when_all_non_positive`,
`contract_boundary`, `engine_binding` and `batch_axes`, every operand as the operation tree the
body carries and every setting as written — with the body's `schedule` member left out. It is
taken over what the file holds and over no engine's rendering of an expression, so a reader
holding the facet takes it again with the standard library, and a second producer compiling
the same machine reaches the same string. A consumer that reads a body **must** take its
identity again and refuse a body that does not hash to the key it is published under: such a
body is a machine nobody compiled under that name, whatever the seal says. It also holds the
node's `increments` summary to the body (section 16), and refuses a summary that names an
operation, label, target, running-balance read or ordinal the body does not apply. A
compilation the file does not carry — every one, in the `audit` profile — has its identity read
as published (section 13). **It is
taken over the machine and not over its schedule**, which is why the schedule is stated
beside it: a schedule is data the machine runs over, as a table is data a lookup reads, and
it reaches the node's digests through its own digest exactly as a table does through
`table_fingerprint`.

**An injected column is not a leaf either, and this is the fourth kind of bytes.** A whole
column of values handed to the model at a line carries `kind: "input"`,
`provenance: "injected"` and a version, which makes it neither a node nothing on the model defines nor a formula the
model wrote — and it still carries a `local_fingerprint`, because a reviewer's question about
it is the same question. **Its bytes are a call**: the identifier `injected`, **no
arguments**, and **two attributes**, encoded by the ordinary rules above.

| Attribute | Scalar | What it holds |
|---|---|---|
| `content` | text | The stamp — `sha256:` and sixty-four hex digits — over the values, taken under the content grammar of section 12.3 |
| `origin` | text | Which container the values arrived in: `series` for a column object, `array` for a numeric array |

**What the content stamp is taken over is a frame of one column**, in the shape section
12.3's grammar states: a count of one column, then that column's name as text, then its
type tag, its row count, and every value's bytes in the order they arrived. **The column is
named `injected`** — a fixed placeholder, not the model's name for the column and not
whatever the object the values arrived in happened to call itself. The values are what was
injected; the name they land under is the assignment, which is already the node's own `column`
and its `id`. Hashing the assignment name here would make one set of values two identities
depending on which line took them, and hashing the arriving object's name would make them two
depending on how a simulation happened to label its output.

**The values are hashed in the order they arrived, and section 12.3 says why**: an injected
column lands on the rows by position, so for an injection the order *is* the content and
sorting it before hashing would hide exactly the change the stamp exists to catch.

**A column that arrives by cross-join is stamped over what was handed over, not over the
product.** A scenario axis is a handful of identifiers joined onto every row of the book, so the
column on the frame is those identifiers repeated once per policy. The stamp is over the
identifiers as the run declared them, in that order: hashing the expanded column would give one
axis a different identity on every book it was run over, which is the same mistake this section
refuses when it forbids hashing the name the values landed under. The row count in the content
bytes is therefore the axis's, and a consumer re-deriving the stamp hashes the distinct
identifiers in declaration order rather than the column as the results file holds it. The
identifier `injected` is not in section 11's operation vocabulary and is not becoming one:
it is not an operation, it computes nothing, and section 11 says so outright. What it is, is
the tag under which this grammar spells a node whose identity is its data.

**`origin` is part of the identity, and the values are not enough on their own.** Two runs
handing the same numbers over in two different containers are two records — the attribute
names the container the data arrived in, `series` or `array`, and a change of container is a
change a reviewer is entitled to see even where the numbers held. It is the only thing in
this document that field names, and the node record beside it says where the values came from
under `provenance` (§8).

**A worked example**, and it is `simulated_shock@1` of section 12.5's own corpus: the three
values `0.01, -0.02, 0.03`, handed over as a column object. The content bytes are
thirty-nine:

```text
01                                       one column
08 69 6e 6a 65 63 74 65 64               "injected"
13                                       f64
03                                       three rows
02 3f 84 7a e1 47 ae 14 7b               present, 0.01
02 bf 94 7a e1 47 ae 14 7b               present, -0.02
02 3f 9e b8 51 eb 85 1e b8               present, 0.03
```

Concatenated:

```text
0108696e6a65637465641303023f847ae147ae147b02bf947ae147ae147b023f9eb851eb851eb8
```

giving the content stamp

```text
sha256:6103a3a7d560f2d5efc89e7822a8520aeda0062eaf4a44ba9632d872d819ed23
```

which the node's own bytes then carry as the `content` attribute, sorted ahead of `origin` by
the key text:

```text
04                                       call
08 69 6e 6a 65 63 74 65 64               "injected"
00                                       no arguments
02                                       two attributes
07 63 6f 6e 74 65 6e 74                  "content"
14 47 <the seventy-one characters above> the stamp, as text
06 6f 72 69 67 69 6e                     "origin"
14 06 73 65 72 69 65 73                  "series"
```

Concatenated — one hundred and eight bytes, in four lines of thirty-two that join end to end
with nothing between them:

```text
0408696e6a6563746564000207636f6e74656e7414477368613235363a363130
3361336137643536306632643565666338396537383232613835323061656461
3030363265616634613434626139363332643837326438313965643233066f72
6967696e1406736572696573
```

and the `local_fingerprint` section 12.5 publishes for that node:

```text
sha256:89ca8ced673d17ff6d5e87916397cf9bb5483658021e6ac0ff08be1d6f96dc03
```

**An injected column reads nothing**, so its `fingerprint` is the fold of that local digest
over an empty run of dependencies — which is what makes the values load-bearing. Nothing
upstream of an injection can move on its behalf, so if the data changed and the stamp did
not, nothing in the artifact would say so.

**A worked example.** The operation tree `BinOp("mul", Col("sum_assured"),
Col("death_rate"))` — the formula `sum_assured * death_rate` — encodes as thirty bytes:

```text
03                                       binary operation
03 6d 75 6c                              "mul"
01 0b 73 75 6d 5f 61 73 73 75 72 65 64   column reference "sum_assured"
01 0a 64 65 61 74 68 5f 72 61 74 65      column reference "death_rate"
```

Concatenated:

```text
03036d756c010b73756d5f61737375726564010a64656174685f72617465
```

and its `local_fingerprint`:

```text
sha256:521b0d6fbdde0541fed0a75b82b2699fa87d09c1dc097f1650fcddc5a3b9de3d
```

An implementation that reproduces those thirty bytes and that digest has the grammar right
for the commonest node in any model. Section 12.5 is where it proves the rest of it.

### 12.2 `fingerprint_algorithm`

The envelope's `fingerprint_algorithm` is an **opaque token** naming the byte grammar every
digest in the artifact was taken under. **Equality is the only operation defined on it.** It
is not parsed, not ordered, not resolved over a network, and carries no version arithmetic —
the reasoning section 5 gives for the `schema` identifier, applied to the grammar.

**The token changes whenever the byte grammar changes, for any reason**, including a change
a reader would call cosmetic. There is no such thing as a small change here: a tag byte
moved, a run given a count it did not have, a normalisation added or dropped, and every
digest in every artifact ever written under the old grammar is a digest of something else.

**Two artifacts carrying different tokens must not be compared.** Not "compared with care" —
not compared. A consumer that wants to compare them re-derives the fingerprints from the
model source under one grammar, rather than translating digests between grammars, which is
not a thing that can be done. A change report handed two artifacts with different tokens
**refuses rather than reporting**: an empty change report and an unreadable one look
identical to a reader, and only one of them is true.

The token in this preview is `gspv0-preview-3`.

**`gspv0-preview-2`.** The token moved first on the date-literal tag of section 12.1, and
everything that landed beside it — the node record's collapse, the edge's relationship, the
list reductions, the closed tree branches, the increments summary, the seal becoming
required — landed in the same document so that the format's users read one change rather
than several. Section 14.1 carries a line for each. Every digest published under
`gspv0-preview-1` is a digest under a different grammar and must not be compared with one
published under this token; the change report refuses the comparison rather than reporting
on it, and a consumer that wants an answer re-derives the fingerprints from the model source
under one grammar.

**`gspv0-preview-3`.** The token moved a second time on the signed zero of section 12.1: a
negative zero is no longer written as a positive one, because `to_text` and the sign-reading
operations tell the two apart and an identity that equates what an operation distinguishes
reports no drift on a model that changed. That is the whole of the grammar change, and it
is narrow on purpose — **only a document carrying a negative-zero literal has different
bytes under this token**. Narrow is not small: section 12.2's rule admits no "cosmetic"
change, so every digest taken under `gspv0-preview-2` is a digest under a different grammar
and the refusal above applies to it exactly as it applies to `gspv0-preview-1`, whether or
not the document in hand holds such a literal. A consumer cannot tell from the outside which
documents the change reached, and a rule that asked it to would be a rule about content
rather than about grammar. The corpus of section 12.5 is regenerated and reprinted, and it
grows a column holding a negative-zero literal so that the one new thing in the grammar is
exercised by the artifact whose whole job is to let a second implementation prove agreement.

**The token took its history from the corpus.** During this preview the content grammar of
section 12.3 joined what the token covers, and the token did not move with it: no artifact
had ever been published carrying a content digest, so there was no digest in the world for a
consumer to read under the wrong grammar, and a new token would have named a distinction
nothing could be on either side of. That was settled once, against the conformance corpus of
section 12.5 — the first digests this format has published — and the change log (section 14.1)
records both the exception and the settling, because the rule above admits no exception a
reader is left to discover for themselves. **`gspv0-preview-1` is the token the corpus was
first taken under, and from that corpus onward the rule applies without this footnote** —
including to the moves to `gspv0-preview-2` and `gspv0-preview-3`, each of which took it
without an exception and regenerated and reprinted the corpus in the same document.

**The selection section did not move it, by ruling** (section 14.1). Section 12.4's and
section 12.6's fourth section is taken only over a document carrying section 7.6's
`selection`, and is absent from every other, so no byte of any document that chooses no rows
moved — the corpus included — and a document that does carry one is new to this edition, with
no digest of it in the world to be read under the wrong rule. The token is unreleased, and the
ruling kept it rather than spend a move on a grammar change no existing digest is on the other
side of. It is the same reasoning section 12.6 gives for masking an attribute no earlier
document carries, stated here because this rule is where a reader looks for it.

**The published schema pins the token, and that is a preview decision rather than a
contradiction of this section.** `schemas/gaspatchio-graph-v0.schema.json` admits
`gspv0-preview-3` and refuses every other value, so an artifact carrying an unknown grammar
is rejected by shape before a consumer has to reason about it — which is the tightest
validation available in a world where exactly one token is emitted, and the preview is that
world. It does mean that a grammar change cannot be expressed without reissuing the schema —
both token moves reissued it — and that coupling is real. **Reissuing the schema document is
not moving the schema identifier**, and the second move is where the difference is visible:
`gaspatchio-graph/v0-preview.3` names what a document may carry, which the signed zero did
not touch, so the identifier holds while the pin inside it moves. A `gspv0-preview-2`
document is then refused by a `.3` schema on that pin, which is the refusal section 12.2
wants and states. It also means the
`v0-preview.1` row of section 5's table places an older document without validating it,
which that section states where a reader meets the row. **At `/v0` final the pin relaxes to
a pattern**, and the two
identities decouple as section 5 and this section intend: a new grammar token will then be
readable under an unchanged schema, and a consumer will refuse the comparison on the token
rather than on the document. Recorded here so a reader meeting the pin knows it is a floor
that is coming up, not a ceiling that was overlooked.

### 12.3 The content grammar, and the recipe grammar beside it

Two more content-hash grammars sit alongside section 12.1's, and this specification names
them plainly rather than leaving a reader to trip over them. The first is normative here.

**The content grammar** is what an assumption table's content hash, a join's right-hand-side
fingerprint and an injected column's stamp are taken under: a SHA-256 over the values
themselves, encoded as below. It is deliberately **not an engine's serialisation.** A digest
taken over a writer's file layout moves the moment that writer is upgraded, with no data
behind the movement, and a drift alarm that fires on a dependency upgrade is an alarm a
reader learns to ignore. It is also what lets a consumer holding an inline payload and no
library in common with the producer re-derive the digest from this document alone.

The bytes are the frame's columns, in the order the frame holds them:

- **a count of columns**, as a varint;
- then, for each column: **its name** as text, **the tag** for the type it carries, **a
  count of rows** as a varint, and **every value's bytes** in row order.

The primitive encodings are section 12.1's, unchanged: counts and byte lengths are unsigned
base-128 varints, low group first; text is UTF-8 behind its byte length; a whole number is
zigzag-encoded and then written as a varint.

**One tag byte per type**, taken from the same block section 12.1's scalar tags occupy, so
that a reader holding both grammars meets one number per type rather than two. For the four
scalar types the two grammars share — `0x11` to `0x14` — the bytes behind the tag are the
same bytes as well. **`0x15` shares the number and not the layout**, and a reader holding
both has to be told so: section 12.1 writes a sequence as a count followed by each element
behind its own scalar tag, and marks an absent value with `0x10`; here the element's tag is
written once, hoisted into the column's own header, and each member carries the
present-or-missing marker below instead. One column of values is not one literal, and the
two are counted differently for that reason.

| Tag | Type | The value's bytes |
|---|---|---|
| `0x11` | `bool` | one byte, `0x00` or `0x01` |
| `0x12` | `i64` | a zigzag varint |
| `0x13` | `f64` | eight IEEE-754 bytes, most significant first |
| `0x14` | `str` | UTF-8 behind a varint byte length |
| `0x15` | `list[T]` | the tag is this byte followed by `T`'s own tag; each value is a varint count of members and then those members |
| `0x16` | `date` | a zigzag varint of days since 1970-01-01 |
| `0x17` | `datetime` | the tag is this byte followed by the column's zone as text, empty for a zone-naive or a UTC column; each value is a zigzag varint of microseconds since 1970-01-01T00:00:00Z and then a varint of the nanoseconds past that microsecond, `0` to `999` |

**A `datetime` carries the whole instant and its zone**, because the vocabulary reads both:
two instants compare to the last unit they are held in (§11.1.26), and a calendar is read in
the column's zone. A count kept in milliseconds or microseconds is put on microseconds, a count
kept in nanoseconds is divided towards the earlier microsecond and the remainder written after
it — `-1` ns is microsecond `-1` and `999` past it — so one instant kept in any unit has one
encoding, and two a nanosecond apart have two. **A count whose microseconds an `i64` does not
hold is refused, by name**: a millisecond count beyond about 292,000 years either side of 1970
would otherwise wrap onto another instant's microseconds and share its digest, so neither a
producer nor a reader writes it (the kit carries the refusal). The zone is written once, in the
column's header behind the tag, and behind the element's tag for a `list[datetime]`; a zone-naive column
is read as UTC (§10), so the two write an empty zone and digest alike, and one instant shown in
another zone is another column. A column `v` holding the instant one millisecond past the epoch
is `01 0176 17 00 01 02d00f 00` zone-naive, and `01 0176 17 10 50…64 01 02d00f 00` — the zone's
sixteen bytes `Pacific/Auckland` behind their length — in that zone.

`f64` normalises **every NaN to the single quiet payload `7ff8000000000000`**, as section
12.1 does and for the same reason: a NaN in a column of data is a value the column holds,
not a configuration mistake, and two runs that both produced one have not drifted. **A
negative zero is written as zero here**, which since `gspv0-preview-3` is where this grammar
and section 12.1's part company, and the divergence is deliberate rather than an oversight
of the move. Section 12.1 hashes a *literal an author wrote into a formula*, and the
vocabulary reads that sign back; this grammar hashes a *column of data*, where a zero's sign
is whatever the arithmetic that produced it left behind, and a basis republished with the
same rates would announce a change nobody made. The two grammars already take opposite
positions on a NaN against the recipe grammar below, and this is the second place they are
told apart rather than assumed to agree. **The hole section 12.1 closed for literals is closed
for data at the door, not by this grammar**: a producer writes a negative zero as zero where
data enters — an assumption table's source and a column injected into a frame — before it is
hashed or read, so one identity has one answer and `fingerprint_algorithm` does not move. **The
cost is named and it is real**: an operation that reads a sign (`sign`, `to_text`) over a
negative zero in such data sees `+0.0`, whatever the arithmetic that produced the data left
behind. A compiled machine's settings are under the recipe grammar below, not this one, and
keep their sign: `floor(value=-0.0)` is its own machine with its own identity. So do the tables the
framework builds for itself — a scenario plan's per-scenario factors, and the shocked copies
of tables it has already read — because they are the plan's recipe, not data entering: a
multiply is written `x * f + -0.0` so that a shocked negative zero keeps its sign and the
batch equals the direct recipe bit for bit. **A second engine cannot tell those tables from
data**, and reads every table's negative zero as `+0.0`, so a column shock that multiplies a
negative zero in the book answers `-0.0` on the producer and `+0.0` on the JAX engine and the
independent reader. That is the one disagreement this section names; it is a sign, never a
magnitude. A model-point column is not normalised at the door: the door is a table's source
and an injected column, nothing else.

**Every value carries a marker in front of it saying whether it is there.** A present value
is the byte `0x02` and then the bytes above; a missing one is the byte `0x01` and then the
single placeholder byte `0x00`. A rate nobody supplied and a rate of nought are two
different assumptions — one propagates a null, the other multiplies a reserve to zero — and
the marker is what keeps them from encoding alike. A member of a `list[T]` carries its own
marker under the same rule. **An assumption table's answer column is where a reader meets
the absent marker in practice**, and the worked example below has no cell that takes it: a
blank rate in a published basis is hashed as absent rather than as zero and rather than
stopping the hash, and §11.1.24 says what a query reaching one gets.

**A column whose type the vocabulary cannot name stops the hash**, naming the column and the
type, by section 10's rule. A fixed-width array is one type carried rather than refused,
and it is not a guess: an array is the `list[...]` the vocabulary already has with its
length fixed, and a fixed length is storage rather than content, so it is hashed as the list
of values it holds.

**A book reads a category as its text.** Where the grammar digests a book — the envelope's
`book` (section 7.5), and the `inputs_digest` a result manifest records — a `Categorical` or
an `Enum` column, or a list or array of either, is read as the text it holds: tagged `str`,
each value its string, a missing value missing. The dictionary in front of the strings is how
an engine kept the column, which is storage as a width is, and the strings are the content,
so a book held as categories and the same book held as text share a digest. The reading is
the book's alone. A table, a join's right side and an injected column hash values a node or a
payload names the type of, and section 10 has no name for a category, so there the rule above
stands and the hash stops; a book's values never travel and no type is claimed for them, so
nothing is named that could not be.

**Width collapses to the neutral type.** A column's tag is the name section 10 gives it, and
section 10 collapses every integer width to `i64` and every float width to `f64`. Two frames
equal in value and different in storage width therefore **share a content hash** —
deliberately: the values are the content, and how many bytes an engine chose to keep them in
is not something a producer ever promised. Where narrowing actually changed a number, the
number itself moves and the hash moves with it, which is the movement a reader needs to see.

**Row order is the caller's, and the three callers order differently.** The grammar hashes
the frame exactly as it is handed over, so a caller that wants two loads of the same data to
agree imposes an order first: **an assumption table puts itself in canonical form** — its
key columns, which are every column but the one it answers with, ascending by name in
Unicode code point order; the answer column last; and the rows ascending by those keys, in
that column order, a number by its value, a text key in code point order and `false` before
`true`. **A table's date or timestamp key is written as the date or the instant it is**,
under `0x16` or `0x17` with its zone, whatever count a lookup kernel keys it by: one instant
kept in milliseconds, microseconds or nanoseconds is one table, and a count of days, of
milliseconds or a plain whole number is never another kind's table. **A join's right-hand side puts its columns in name order and sorts its rows
by every column**, having no answer column to put last and no key it can trust. **An injected column imposes no order at all**, and
that is the rule rather than an omission: a column of values handed over wholesale lands on
the rows by position, so the second value belongs to the second policy and for an injection
the order *is* the content. Sorting it before hashing it would hide exactly the change the
stamp is there to catch. A consumer re-deriving an injected column's stamp hashes the values
in the order it received them. The first two also project differently — **a table hands over
its whole processed frame**, in that canonical order, a join its whole right side in its
own canonical order — so **a table's content hash and a join's are never comparable**, even over the
same file.
Each answers "is this the same table as last quarter's run?"; neither answers "are these two
tables the same?".

**A table's content hash is one string, and it depends on the values alone.** Because the
canonical form fixes the column order as well as the row order, the order a source happened
to list its columns in, the order its rows arrived in and the file format it was read from
reach no byte; a changed cell moves it. That one string is what a lookup node carries as
`table_fingerprint`, what the `assumptions` section writes as an entry's `fingerprint`, what
the reference producer returns from `Table.fingerprint()`, and the `content_sha` field inside
the table's recipe below. The recipe's own digest — the table's `source_sha` — is a different
string over the recipe grammar, and moves for more reasons: when the values move, and also
when anything else about the table does, its name included. A consumer re-deriving an
entry's fingerprint from an inline payload wants the content hash, and section 13 states the
form it hashes.

**A worked example.** The three-row mortality basis `{"age": [45, 46, 47], "rate": [0.001,
0.0012, 0.0015]}` — one dimension `age`, value column `rate`, in canonical form as a table
orders itself — encodes as forty-seven bytes:

```text
02                                       two columns
03 61 67 65                              "age"
12                                       i64
03                                       three rows
02 5a                                    present, 45
02 5c                                    present, 46
02 5e                                    present, 47
04 72 61 74 65                           "rate"
13                                       f64
03                                       three rows
02 3f 50 62 4d d2 f1 a9 fc               present, 0.001
02 3f 53 a9 2a 30 55 32 61               present, 0.0012
02 3f 58 93 74 bc 6a 7e fa               present, 0.0015
```

Concatenated:

```text
02036167651203025a025c025e04726174651303023f50624dd2f1a9fc023f53a92a30553261023f589374bc6a7efa
```

and its content hash:

```text
sha256:5267aed7a08b589310c079677eddd6128fb44af9f9fbfbb1dc3d58e2b6dcd277
```

An implementation that reproduces those bytes and that digest has the content grammar right
for the commonest frame in any model.

**The recipe grammar.** The *source* stamp of an assumption table, a projection schedule and
a yield curve — what a `source_sha` carries — is a SHA-256 over a canonical JSON encoding of
the object's own recipe: keys sorted at every level, no insignificant whitespace,
ASCII-escaped so the bytes are stable across platforms, and an unknown type refused rather
than coerced to a string. It is neither the tree grammar of section 12.1 nor the content
grammar above; it *contains* the content grammar's answer, because a table's recipe carries
its content hash as one of its fields.

The recipe grammar and section 12.1 take **opposite positions on NaN**, deliberately.
Section 12.1 normalises every NaN to one payload, because a NaN reaching a call attribute
means two runs both produced a NaN and have not drifted. The recipe grammar **refuses** one,
because a NaN reaching the recipe of an assumption table is a data problem the caller should
be told about rather than a difference to be normalised away.

**A third digest in the artifact is under neither grammar, and it is named here so that a
reader meeting it does not go looking for one.** `model.source_sha`, `model.model_points`'s and
`results`' fingerprints, and a `sources` entry's fingerprint (§7.3) are each a plain SHA-256
**over the file's own bytes**. There is nothing to encode: a model file is text somebody wrote
and a Parquet is a file somebody holds, neither is a frame of values or a canonical recipe, and
a digest over a re-serialisation of either would move whenever the library that writes the
format changed — an identity nobody could compare across quarters. It follows that these
digests are comparable with `shasum` and with nothing else in this artifact: a table's content
hash over the same bytes would be a different string answering a different question.

**`fingerprint_algorithm` covers section 12.1 and the content grammar — one token for
both.** Splitting them would leave a reader holding a digest whose grammar nothing in the
file names, and there is no artifact in which one of the two moves and the other may be
trusted: a content hash rides inside the canonical bytes of every node that reads a table,
so a change to either grammar moves the same digests. The recipe grammar moves with them,
because a table's recipe carries its content hash inside it. Every digest an artifact holds
carries the `sha256:` prefix that every content hash in this framework takes, and which
grammar produced it follows from where it sits in the artifact and from the artifact's own
published identity (section 5).

### 12.4 The graph fingerprint

The envelope's `graph_fingerprint` is SHA-256 over three counted sections, in this order,
each sorted:

1. **every (node id, node fingerprint) pair**, sorted by node id, each pair encoded as the id
   as text followed by that node's raw `fingerprint` digest;
2. **every assumption table content hash the model reads**, sorted, each as text;
3. **every unaccounted column**, once each and sorted by name: the names section 7.1's holes
   section lists, each as text, followed in the same entry by that hole's `content` as text
   where the section gives it one;

and, **where the model chose which rows it values, a fourth**:

4. **every selection step's raw `fingerprint`** (section 7.6), in the order the list holds the
   steps — **not sorted**, because the order is the model's own — each as its thirty-two
   bytes and nothing else, since they are fixed width.

Each section is a variable-length run and carries its own count, by section 12.1's rule.
**The fourth section is absent rather than empty where the model selects nothing**: a model
that never selects is hashed over the three sections it always was, so its digest did not move
when the selection entered the record, and a document carrying no `selection` member is read
under the three. A step's tables reach the second section as any formula's do — a selection
step's tree is read for the assumption tables it names — and a semi or anti join's right side
reaches the digest through the step's own bytes, as a join node's does.

**There is no framing beyond those counts.** Section 12.1's opening sentence applies
here in full and is restated rather than borrowed, because a reader who took "SHA-256 over
three counted sections" and reached for a length prefix, a version byte or the algorithm
token would produce a well-formed digest that matches nothing: **no framing around the whole,
no separator between sections, no header, and the token is not folded in.** The runs are
concatenated and hashed once. The grammar the digest was taken under is named in the
envelope beside it (section 12.2), which is where a consumer reads it and not something the
bytes restate.

**Sorted means by Unicode code point**, in the three sorted sections, exactly as section 12.1's
attribute keys are sorted and for the same reason: it is the one order two implementations
agree on without agreeing on a locale first.

**A digest inside a section is hashed as text in its stamped form** — `sha256:` and
sixty-four hex digits, behind its own byte length, seventy-one characters in all. That is
section 2's content hashes. It is not the fold's rule, and the difference is the same one
section 12 draws: the fold concatenates fixed-width *raw* digests because nothing there is
text, while a section here is a run of strings the artifact carries. Section 1 is the mixed
case and says so in its own line — the id **as text**, then that node's **raw** digest — so
one pair is a length-prefixed string followed by exactly thirty-two bytes.

**A section's entry carries no scalar tag**, and this is the one place a reader holding
section 12.1 in their head will over-encode. A call's attributes are a run of *scalars*, so
each value carries the tag that says which scalar it is; the three sections here are runs of
*text*, and text behind a length needs nothing to say so. The same content hash is therefore
seventy-three bytes as an attribute value — `0x14`, the length `0x47`, then the string — and
seventy-two as a section-2 entry, which is the length and the string alone.

**Every node of the artifact enters section 1, and "every" is literal.** A column's
superseded definitions are in it: `net_cashflow@1` and `net_cashflow@2` are two nodes and
two pairs, and section 12.5's corpus proves it arithmetically — its published
`graph_fingerprint` is over twelve pairs for eleven columns, and drops out of the reader's
own recomputation only when both definitions are counted. Reserved namespaces are in it too: a
compiled rollforward's node and each running state's node are nodes, and they enter under
the ids they carry. The reading to avoid is the natural one — that "the model" means the
final schema — because a model that rewrote a column and one that never did must not share
this digest, and the history is the difference.

**Section 2 lists each distinct content hash once.** Two nodes reading one table put one
entry in it, not two: the section answers "which assumption bases was this model run
against?", and a base read twice is one base. Take the distinct hashes and then sort them —
de-duplicate first, sort second. Doing it the other way round and sorting a list with
repeats gives a different byte string, and both readings look like "sorted, each as text".

**Section 3 lists each name once**, as the holes section does: a column with two hole
nodes, two of its definitions written past the producer's interfaces, is one name there.
De-duplicate first, sort second, as for section 2. **A stamp is the one value of a hole it
carries.** A hole the frame arrived holding enters as its name and then its `content` — two
strings, each behind its own length, in one entry, so the section's count is of holes and not
of strings — and every other hole as its name alone, exactly as every hole entered before the
stamp existed: a document whose holes carry no stamp keeps the digest it had. Two runs whose
arriving holes held different values therefore differ here, and two runs whose overwritten
holes held different values do not; either way a verifier never reads an agreeing digest as
agreement about a hole (section 13).

**Pairs rather than a bag of fingerprints.** Two columns computed the same way share a
fingerprint by design (section 12), so swapping which formula binds to which column name
leaves a bag of fingerprints byte-for-byte identical — and that swap is a model change, of
exactly the kind a reviewer is looking for. Binding the id to the fingerprint is what makes
the digest move.

The second section restates something the first already covers, since an assumption table's
content hash rides on the lookup node that reads it. The restatement is the point: "which
assumption bases was this model run against?" becomes a section of the digest a reader can
point at, rather than a fact buried inside one node's bytes.

**Tables only, and the other two kinds lose nothing by it.** A schedule and a curve reach the
digest already, through the canonical bytes of the node whose formula reads them (section
12.1), so a model that swaps either for a different one moves this digest through the first
section. That includes the schedule a compiled rollforward runs on: the compilation's node
and every line reading it carry it as their `schedule` attribute, so a re-sourced schedule
under a state machine moves those nodes' digests and this one. The second section exists to lift one fact out of those bytes and put it where a
reader can point at it, and the fact worth lifting is the assumption table — the thing a
reviewer asks about by name across two quarters. Listing a value object beside it would restate
a hash without making it any easier to ask a question about.

The third section does the same for section 7.1's holes. A model that can account for every
column it holds and one that cannot must not share a digest, and an empty third section is
the claim that it can. Nor must a model whose setup joined a file share one with the same model
over an edited copy of that file, which is what the stamps beside the names are for.

**This digest is the model as run, data included**, and that is deliberate: a lookup against a
re-sourced basis is a different calculation. Section 12.6 takes the same fold a second time
with the data left out, for the reviewer whose question is whether any formula moved.

### 12.5 The conformance corpus

A small artifact is published alongside this specification, together with every one of its
nodes' `local_fingerprint` and `fingerprint` and its `graph_fingerprint`, all reprinted below.
It exists so that **a second implementation can prove agreement before claiming it**:
reproducing those digests from the corpus's own operation trees is the check, and matching
them is the claim. An implementation that has not run it has an untested reading of section
12.1, however carefully it was read, and section 14 makes reproducing these digests one of the
conditions for closing the preview.

The artifact itself travels with the reference implementation, at
`bindings/python/tests/graph/goldens/conformance_corpus.json`, for the reason the schema
document does: one copy, kept where the thing that produces it lives, rather than a second
copy beside this document to drift out of step with it. Everything needed to check an
implementation against it is reprinted below, so a reader holding only this document is not
missing anything.

The corpus is regenerated and reprinted whenever `fingerprint_algorithm` changes. A grammar
change that left the corpus behind would leave a second implementer proving agreement with a
grammar nobody emits any more, which is worse than having no corpus at all.

**The model.** Eleven columns, between them carrying one of each thing section 12.1 has to
get right: a column that arrived with the data, an arithmetic formula, a conditional, a
formula holding a sequence literal, an accessor call carrying a typed offset, a whole column
of values injected at a line, a column the model wrote twice, a leaf whose type is a date, a
date literal under the tag this grammar mints for one, a reduction whose answer has a
different shape from its operand, and a decimal literal this grammar tells from its own
negation. **There is deliberately no rollforward
in it and no assumption table**, so that the digests below do not move when sections 15 and 16
land. A corpus that moved when a payload section arrived would be pinning the wrong thing.

Three of those columns arrived with `gspv0-preview-2` and one with `gspv0-preview-3`, and
the reason is what a corpus is for, twice. A grammar that grew a date tag, or that stopped
writing a negative zero as zero, published beside a corpus that holds neither, would leave
the one new thing in the grammar untested by the one artifact whose job is to let a second
implementation test it — and, since no other column holds a byte the change reaches, it
would publish two artifacts under two tokens carrying identical digests, which is the shape
section 12.2 forbids comparing and which a careless consumer would compare.

`.list.sum()` and not `.sum()`, and the difference is the whole of what that line is for.
`select_loaded_claims` is a per-period column, and this is the fold along its periods. The
bare spelling is the engine's fold down the *rows* of the model-point file — a different
calculation, whose answer depends on the order those rows stand in — and section 11.1.12
forbids writing this identifier for it.

```python
import datetime

import polars as pl

from gaspatchio import ActuarialFrame, when


def _the_corpus_model() -> ActuarialFrame:
    """Return the model the published corpus is an account of.

    Eleven columns, between them carrying one of each thing the byte grammar
    of section 12.1 has to get right: a column that arrived with the data, an
    arithmetic formula, a conditional, a formula holding a sequence literal,
    an accessor call carrying a typed offset, a whole column of values
    injected at a line, a column the model wrote twice, a leaf whose type is
    a date, a date literal under the tag the grammar mints for one, a
    reduction whose answer has a different shape from its operand, and a
    decimal literal the grammar now tells from its own negation.

    The date three arrived with ``gspv0-preview-2`` and the signed zero with
    ``gspv0-preview-3``, for the same reason both times. A grammar that grew
    a date tag, or that stopped writing a negative zero as zero, published
    beside a corpus carrying neither would leave the one new thing in the
    grammar untested by the one artifact whose job is to let a second
    implementation test it -- and would publish two artifacts under two
    tokens carrying identical digests, which is the shape section 12.2
    forbids comparing.

    ``.list.sum()`` and not ``.sum()``: ``select_loaded_claims`` is a
    per-period column, and this is the fold along its periods. The bare
    spelling is the engine's fold down the *rows* of the model-point file,
    a different calculation whose answer depends on the order the rows stand
    in, and section 11.1.12 forbids writing this identifier for it.

    Deliberately no rollforward and no assumption table. The corpus is
    pinned, and one that moved when a payload section landed would be pinning
    the wrong thing.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "sum_assured": [100_000.0, 250_000.0, 500_000.0],
                "entry_date": [
                    datetime.date(2019, 3, 1),
                    datetime.date(2021, 7, 15),
                    datetime.date(2023, 11, 30),
                ],
            }
        )
    )
    af.death_claims = af.sum_assured * 0.001_23
    af.ceded_claims = (
        when(af.sum_assured > 200_000.0).then(af.death_claims).otherwise(0.0)
    )
    af.select_loaded_claims = af.death_claims * [1.5, 1.25, 1.0]
    af.prior_period_claims = af.select_loaded_claims.projection.at_period(-1)
    af.simulated_shock = pl.Series([0.01, -0.02, 0.03])
    af.net_cashflow = af.sum_assured * 0.02 - af.death_claims + af.ceded_claims
    af.net_cashflow = af.net_cashflow * (1.0 + af.simulated_shock)
    af.post_reform = (
        when(af.entry_date > datetime.date(2022, 1, 1)).then(1.0).otherwise(0.0)
    )
    af.total_claims = af.select_loaded_claims.list.sum()
    af.unceded_claims = (
        when(af.ceded_claims == 0.0).then(af.death_claims).otherwise(-0.0)
    )
    return af
```

**The trees, and they are what the digests were taken over.** The Python above is how the
model was written; it is **illustrative**, and the operation trees below are **normative for
this conformance check**. A reader deriving trees from source would be reproducing one
parser's associativity and one recorder's decisions about where a statement splits, neither
of which this document defines or intends to — `a * 0.02 - b + c` is printed below as the
producer folded it, and an implementation that read it the other way is not wrong about this
format, only about that parser. So the check is: hash these trees, reach these digests.

The trees are printed in the shape the `executable` profile writes them (section 8's `expr`),
one per node, in the order the model defined them. A node with no tree is printed as what its
bytes *are* instead.

```json
sum_assured
  a leaf — an arriving column, tag 0x20 — so its bytes are the tag, its name
  "sum_assured" as text, and its type "f64" as text. It has no tree.

entry_date
  a leaf on the same terms, and the one whose type is the point: the tag, its
  name "entry_date" as text, and its type "date" as text. It has no tree.

death_claims@1
{"op": "binop", "kind": "mul",
 "left": {"op": "col", "name": "sum_assured"},
 "right": {"op": "lit", "value": 0.00123}}

ceded_claims@1
{"op": "when_then",
 "cond": {"op": "binop", "kind": "gt",
          "left": {"op": "col", "name": "sum_assured"},
          "right": {"op": "lit", "value": 200000.0}},
 "then": {"op": "col", "name": "death_claims"},
 "otherwise": {"op": "lit", "value": 0.0}}

select_loaded_claims@1
{"op": "binop", "kind": "mul",
 "left": {"op": "col", "name": "death_claims"},
 "right": {"op": "lit", "values": [1.5, 1.25, 1.0]}}

prior_period_claims@1
{"op": "call", "name": "projection.at_period",
 "args": [{"op": "col", "name": "select_loaded_claims"},
          {"op": "lit", "value": 0.0}],
 "attrs": {"relative_period": -1}}

simulated_shock@1
{"op": "call", "name": "injected", "args": [],
 "attrs": {"content": "sha256:6103a3a7d560f2d5efc89e7822a8520aeda0062eaf4a44ba9632d872d819ed23",
           "origin": "series"}}

net_cashflow@1
{"op": "binop", "kind": "add",
 "left": {"op": "binop", "kind": "sub",
          "left": {"op": "binop", "kind": "mul",
                   "left": {"op": "col", "name": "sum_assured"},
                   "right": {"op": "lit", "value": 0.02}},
          "right": {"op": "col", "name": "death_claims"}},
 "right": {"op": "col", "name": "ceded_claims"}}

net_cashflow@2
{"op": "binop", "kind": "mul",
 "left": {"op": "col", "name": "net_cashflow"},
 "right": {"op": "binop", "kind": "add",
           "left": {"op": "lit", "value": 1.0},
           "right": {"op": "col", "name": "simulated_shock"}}}

post_reform@1
{"op": "when_then",
 "cond": {"op": "binop", "kind": "gt",
          "left": {"op": "col", "name": "entry_date"},
          "right": {"op": "lit", "date": "2022-01-01"}},
 "then": {"op": "lit", "value": 1.0},
 "otherwise": {"op": "lit", "value": 0.0}}

total_claims@1
{"op": "call", "name": "sum",
 "args": [{"op": "col", "name": "select_loaded_claims"}],
 "attrs": {}}

unceded_claims@1
{"op": "when_then",
 "cond": {"op": "binop", "kind": "eq",
          "left": {"op": "col", "name": "ceded_claims"},
          "right": {"op": "lit", "value": 0.0}},
 "then": {"op": "col", "name": "death_claims"},
 "otherwise": {"op": "lit", "value": -0.0}}
```

Six things about that block a reader should not have to infer. **`simulated_shock@1` has no
tree on the wire** — the `executable` profile writes no `expr` for a node whose `kind` is
`input`, so the tree above is what its bytes are taken over rather than something the
artifact hands you; section 12.1's injected-column example prints those bytes in full,
together with the frame the `content` stamp was taken over. **`prior_period_claims@1` carries
`-1` as a whole-number attribute and `0.0` as a
decimal positional argument** — the offset is configuration and the fill value is an operand,
which is the signature section 11.1 schedules for that identifier and not a distinction a
reader could recover from the call as it was written. **`net_cashflow@2` reads
`net_cashflow@1`**, the definition it supersedes, which is section 8's binding rule doing the
one thing it exists to do. **`post_reform@1`'s literal carries its date under `date` and not
under `value`** — JSON has a number token and no date token, so the distinction whole numbers
and decimals draw with a token is drawn here with a key, and exactly one of `value`, `values`
and `date` is present on a literal. **`total_claims@1` carries no attributes and one
operand**, and its answer is a scalar where its operand is a per-period column: a reduction
is the one shape in this corpus where those two differ, which is what section 11.1.12 exists
to state. **`unceded_claims@1`'s two literals are a positive zero and a negative one**, and
under `gspv0-preview-2` they encoded alike and this node's digests were the ones a model
writing `0.0` in both places would have published; under this grammar they are eight bytes
apart, and that is the single difference the corpus is republished to carry.

**What the reads are, since the fold needs them in order.** `sum_assured`, `entry_date` and
`simulated_shock@1` read nothing. `death_claims@1` reads `sum_assured`; `ceded_claims@1`
reads `sum_assured` then `death_claims@1`; `select_loaded_claims@1` reads `death_claims@1`;
`prior_period_claims@1` reads `select_loaded_claims@1`; `net_cashflow@1` reads
`sum_assured`, `death_claims@1`, `ceded_claims@1`; `net_cashflow@2` reads `net_cashflow@1`
then `simulated_shock@1`; `post_reform@1` reads `entry_date`; `total_claims@1` reads
`select_loaded_claims@1`; `unceded_claims@1` reads `ceded_claims@1` then
`death_claims@1`. Every one of those follows from the trees above under section 8's
binding rule, and is printed here so an implementation can check its derivation rather than
having to trust it.

**What the artifact makes of it.** Twelve nodes over those eleven columns, because
`net_cashflow` is written twice and each writing is an account of its own (section 8). The
superseded first definition carries `unknown` for `dtype` and `shape`, which is the honest
answer rather than a gap: the frame's final schema holds the *second* definition, so there
is nothing left to read the first one's type off — unless a producer retained it (§8), in
which case it did read one and states it. It is a computed node, and a computed node's type is no
part of its canonical bytes, so the `unknown` moves no digest. A leaf's type *is* part of its
bytes (section 12.1), and no leaf in this corpus carries one — `sum_assured` is `f64` and
`entry_date` is `date`, and both are hashed.

Twelve edges, and two of them are `INDIRECT`: `sum_assured` is read inside `ceded_claims@1`'s
conditional test and nowhere else in that formula, and `entry_date` inside `post_reform@1`'s,
and deciding which value flows is not the
same as flowing. The narrowing that says which kind of indirect read it was — `CONDITIONAL` —
is on each of those two reading nodes, in the `gaspatchio_column_transformation` facet, beside
the `TRANSFORMATION` narrowing every other read in the corpus carries but one:
`total_claims@1`'s read of `select_loaded_claims@1` is `DIRECT`/`AGGREGATION`, because a fold
along the periods is not a transformation of them one for one.
`holes`, `boundaries` and `assumptions` are all empty, and each empty section
is the claim section 7 says it is.

`source_location` names a path inside the producer's own repository rather than a path on the
machine that ran the model. Section 12.1 keeps the source location out of the canonical bytes,
so that choice moves no digest, and a reader who rebuilds this model in a file of their own
will see their own locations beside these same digests. It is written that way by the producer
rather than edited into the file afterwards, because `document_digest` covers every byte: a
location rewritten after the export would leave this file carrying a seal over a document
nobody holds, which is section 13.1's fourth limit met from the inside.

- **`fingerprint_algorithm`:** `gspv0-preview-3`
- **`graph_fingerprint`:** `sha256:20882cdb67b31e9dd707eaa518b99cde4c5a51499bcc18dbd049dcf9e3e675ed`
- **`formulas_fingerprint`:** `sha256:d1a502e636f5b748fb899347915a41584eb5b2e0587adc05cbe2a109a76fa8fe`

| Node | `local_fingerprint` | `fingerprint` |
|---|---|---|
| `sum_assured` | `sha256:b643510e5bc2884efbc56ffc1b90fca82f7cc07abb692dd75abb3cf7d1f60b38` | `sha256:c7d944982f89b2858870c74491fff1c28758dbead932cdaa6ba90157ec2b3778` |
| `entry_date` | `sha256:680fe476f58e01f99da4b11dfb89138dd5df719e0eaa763a42c8cf33b8b63364` | `sha256:5e88b3fc7020a83b2efa2bee8ddd96c559b7eb4a4c65b5199946a9bb69367049` |
| `death_claims@1` | `sha256:b49aa4a4748ec6573286d9401d4adeae21cb8b154fc3f9ae49f9fbf7f363ce5b` | `sha256:9bc483fe29a43ab5d080d973ed916dfc622a92b9420e0791c793645220aa5619` |
| `ceded_claims@1` | `sha256:5c174ac4e152918c28d4b7eba56ce0ac8f69e5d1f274ae693f3437f665b5208f` | `sha256:83a1396aad170c59ca9aebe357a8e686a8e7d5233d1c31202c43bce8ab71e0e2` |
| `select_loaded_claims@1` | `sha256:e1bb14b04beeb8f13b4a054464cf7fe13d0aa30f5cd0490718edf8c0a1648eac` | `sha256:1e16bb8e7dbdac91fbab8445915a42252fe5865331d2c599b02971e05752bb3f` |
| `prior_period_claims@1` | `sha256:55364b07a9c09f8a1357b7b85e7575b66e13e7d5a7d03cda49985f69860d3795` | `sha256:93c1ba8ed1eb44a1d39dc6e7ab18c97d595b0548cb4a9a37b226014f507a2c2c` |
| `simulated_shock@1` | `sha256:89ca8ced673d17ff6d5e87916397cf9bb5483658021e6ac0ff08be1d6f96dc03` | `sha256:3f46ec6c4d8ca5cdb2d2dd0078d125cffb6f095c9d6505ddea3048bf4701bcd8` |
| `net_cashflow@1` | `sha256:e37e5f058300dcc00ace9d4a83a92a5d0afb395fbd7c1731a683fc2aeb600f5d` | `sha256:81f51cba1a85d7b6af7c4cba33dab979fcd04d48acd3847b756daf98e8f4e284` |
| `net_cashflow@2` | `sha256:63b0e83ed9c4d6c0ebd3ff5dba3978392217e5fbf8a2a06c4b27d97622f2fba3` | `sha256:e957038a0d0ffad8d9c43ffbabd60872ed8d80fe00315b7be9184f8f40f877d9` |
| `post_reform@1` | `sha256:ef85e9164e298e9a645f0d3bb9ee60188961d5a122d638a380cc0319e804280d` | `sha256:510149594f8d8111253bdd50a23e35eeaf9fce4fb1ae0ee84b489f1626fc4431` |
| `total_claims@1` | `sha256:53eb3fde2e217dd1d1edf7cef774d1106f079c8c8150826098623f06edaf9337` | `sha256:5fd1848b3f591685a2bc0a11b999da6ee66aff9abc45333d5489c3d3547f08d7` |
| `unceded_claims@1` | `sha256:a6c2ab21f3e726745876ab9adc7f88b8f013f5c3e06ffec25b771ebdd570f7c4` | `sha256:d97fed6e4fcebcf79fa18070448cdcb243bdf4c56f3460f8b0777aeb01afbe13` |

### 12.6 The formulas-only fingerprint

The envelope's `formulas_fingerprint` answers the one question `graph_fingerprint` cannot:
**did any formula change, or only the data the formulas read?** `graph_fingerprint` is the
model as run. A lookup carries its table's content hash as an attribute (section 12.1), so a
re-sourced basis moves it exactly as an edited formula does. Each node's own digests already
separate the two node by node — a formula edit moves one `local_fingerprint`, a table edit
moves the lookups that read it — but a reviewer signing off a quarter needs one figure to
quote, and a lookup whose digest moved alongside its table could also have been edited.

**It is section 12.4's fold, taken again over masked trees and over two of its three
sections.** This subsection is normative.

1. **A node's masked local digest** is SHA-256 over the canonical bytes (section 12.1) of its
   operation tree with the value of every *content attribute* below replaced by the text
   `masked` — the scalar `0x14`, the length `0x06`, and `6d61736b6564`. Nothing else in the
   tree moves: every node, every operand, every attribute key, and whether a conditional key is
   present at all stay as they were, and the value is replaced whatever it was, a null
   included. **A leaf's masked local digest is its `local_fingerprint`**, because a leaf's
   bytes are a name and a type and carry no content digest.
2. **A node's masked fingerprint** is section 12's fold over its masked local digest and the
   masked fingerprints of what it reads, in the order `reads` states.
3. **The digest** is SHA-256 over two counted sections, concatenated with nothing between
   them: every (node id, masked fingerprint) pair sorted by id, encoded as section 12.4's
   first section; then every unaccounted column name, once each and sorted, as its third —
   each name alone, with no hole's `content` beside it, since a stamp is data.
   **Section 12.4's second section, the tables, is left out rather than masked**: a run of
   masked entries would still count the bases a model reads, and how many tables a basis is
   split across is data too.
4. **Where the model chose which rows it values, section 12.4's fourth section follows**, over
   each step's masked fingerprint in list order: SHA-256 over the step's kind as text and the
   canonical bytes of its masked tree, folded over the masked fingerprints of what it reads.
   The content attributes below are masked in a step's tree exactly as in a node's, so a semi
   or anti join's `right_fingerprint` is masked and a re-sourced in-force list is data; and
   the section is absent where there is no step, as there.

**The content attributes** are the ones whose value names a value object's content, by the
identifier that carries them:

| Identifier | Attributes masked |
|---|---|
| `lookup` | `table_fingerprint` |
| `join` | `right_fingerprint` |
| `mortality.at` | `mortality`, `table_fingerprint` |
| every `curve.*` | `curve` |
| every `schedule.*` and every `projection_frame.*` | `schedule` |
| `rollforward` and every `rollforward.*` | `schedule` |
| `projection_set` | `schedule_source_sha`; and, on a call carrying it, `start` and `frequency` |
| `injected` | `content`, `origin` |

**Everything a modeller types stays in**: literals, a table's name, a lookup's keys,
`on_missing` and `fill_value`, a join's `on` and `how`, and a projection's `valuation_date`,
which is written in the model, so a quarter roll that edits it is an edit to the model. So
**pointing a lookup at a different table moves both figures**, because the name it reads by
moved; **swapping the contents of two tables of one shape between their names moves
`graph_fingerprint` only**, because which values each name holds is data.

**A schedule's restated parameters are masked with it.** A projection set from a schedule
object writes, beside the schedule's digest, the `start` and `frequency` it read off that
schedule — the schedule's own content written out a second time, which would otherwise move
this digest on a re-sourced schedule with the digest masked. On a projection set from a start
and a frequency handed to the projection itself there is no schedule digest, and there they
are what the model typed and stay in. **A fixed-step axis declared on the projection is the
second case**: it carries no schedule digest, because its two numbers state the whole axis and
are what the model typed (section 11.1.1), so re-stepping it moves both figures through
`projection_set`.

**A compiled rollforward's machine stays in and its schedule is masked.** The rollforward
calls' `fingerprint` is the compiler's identity for the state machine (section 16) — logic,
and the only account of the machine's operations this format carries — and it is kept. It is
taken over the machine alone: every state and its opening value, every operation in order
with its operands, its label, its rounding and its timing, and the stopping conditions, the
batch axes, the increment tracking and the engine binding. The schedule the machine runs on is
left out of it and stated beside it as `schedule`, which the table above masks. **So under a
rollforward a re-sourced schedule moves `graph_fingerprint` and leaves this digest where it
was, and an edit to the machine moves both** — and the rollforward node's id, which is built
from the fingerprint, moves only with the machine.

**One position keeps data inside this digest, and it is stated rather than hidden: an
engine-native fragment's text is hashed as written.** The reference producer's fragments carry
no content digest, with one exception a model reaches only by wrapping a rollforward
extraction in an expression the record keeps as engine text (prepending an opening period,
concatenating two states): the fragment then names the scratch column the producer runs the
machine into, and the reference producer names that column for the run — machine and schedule
— so that two runs never share one. Under such a line a schedule change moves this digest too.
It errs in one direction — towards reporting a formula change that did not happen, never
towards hiding one that did.

**A column of values handed over at a line is data by construction**, its container included.
The `executable` profile writes no tree for an injected or continued column (section 13), so a
digest keeping `origin` could not be recomputed by any reader; with both attributes masked
every such node shares one masked local digest, taken over these forty-three bytes:

```text
04                                       call
08 69 6e 6a 65 63 74 65 64               "injected"
00                                       no arguments
02                                       two attributes
07 63 6f 6e 74 65 6e 74                  "content"
14 06 6d 61 73 6b 65 64                  "masked"
06 6f 72 69 67 69 6e                     "origin"
14 06 6d 61 73 6b 65 64                  "masked"
```

```text
0408696e6a6563746564000207636f6e74656e7414066d61736b6564066f726967696e14066d61736b6564
```

giving

```text
sha256:db5ec4947abbb3c7f8d7b5a32334f3aa070e62eb182321b859fe29d79448e863
```

**A consumer of an `executable` artifact recomputes it**: each tree masked and hashed, each
leaf's published `local_fingerprint`, the constant above for each node whose `provenance` is
`injected` or `continuation`, then the fold and the two sections. **In the `audit` profile it
is read as written**, as a computed node's `local_fingerprint` is, because the trees it is
taken over are not in the file (section 13).

**The corpus of section 12.5 carries one**, printed beside its `graph_fingerprint`. It reads no
table, curve or schedule, so its only content attribute is `simulated_shock@1`'s: every other
node's masked local digest is the `local_fingerprint` its table publishes, and a second
implementation reaches the figure from that table, the constant above and the reads section
12.5 states.

**The mask is part of the grammar `fingerprint_algorithm` names.** Adding an attribute to the
table above or taking one away changes this digest for models nobody touched, and moves the
token by section 12.2's rule. The rollforward row is the case that rule does not reach, for the
reason the digest's own arrival did not move the token: it masks an attribute no earlier
document carries, so no digest written before it changes under it. The digest's arrival did not: no artifact had carried a
`formulas_fingerprint`, so there was no digest in the world to read under the wrong rule —
the reasoning section 12.2 gives for the content grammar's arrival.

**It is optional.** A document written before it carries none, and a comparison holding one
such document says nothing about formulas rather than inferring an answer from the node
digests (section 14.2).

## 13. Verification

**Every artifact carries stamped fingerprints. There is no unstamped form.** A producer that
emits a node emits both of that node's hashes, so a consumer never has to ask whether this
particular artifact is one of the ones that can be checked.

**In the `audit` profile a consumer verifies propagation.** It recomputes each node's
`fingerprint` from that node's published `local_fingerprint` and its dependencies' published
fingerprints, taken in the order `reads` states, and it recomputes `graph_fingerprint` from
the published pairs, the published assumption hashes and the published hole columns. Both
recomputations need section 12's rules and nothing else — no operation tree, no engine, and
nothing the producer did not put in the file.

**It cannot verify the `local_fingerprint` of a node that computes.** Such a node's
canonical bytes are its operation tree, and the `audit` profile does not carry the operation
tree. This is worth saying plainly rather than leaving in the gap between two sections: **an
`audit` artifact verifies its structure, its propagation and its leaves, not the local
fingerprints of its calculations.** Full self-authentication is a property of the
`executable` profile, which carries the trees the local fingerprints were taken over; a
consumer holding one recomputes every `local_fingerprint` it has a tree for under section
12.1 — section 12's bound, stated there in the same words — and is then checking the whole
chain rather than the joins between its links.

**A leaf's `local_fingerprint` is recomputable from either profile.** A leaf — a column the
data arrived with, a column nothing accounts for, a running state — has no tree in either
profile and needs none: section 12.1 takes its bytes over its tag, its name and its type, and
each is on the node in both profiles — the tag from `kind`, the name from `column` (for a
running state, its `id` less the `state:` prefix) and the type from `dtype`. A consumer
holding either profile may therefore recompute every leaf's `local_fingerprint` and check it,
and one that does reports a leaf whose digest does not follow from its own name and type as it
would a tree that does not. What no profile lets a consumer recompute is the injected column,
and, beside it, a compiled rollforward whose machine the file does not carry.

**The injected column is a node kind rather than a corner case, and it is the one worth
stating.** The `executable` profile writes no
`expr` for a node whose `kind` is `input` (section 12.5), and such a node's canonical bytes are
a call carrying the content stamp over the injected values and the container they arrived
in — neither of which the artifact holds. A producer *builds* those bytes from section 12.1's
rule while the values are still in front of it; a consumer cannot *recompute* them from the
file. So an injected column's `local_fingerprint` is reproducible by its producer and not
recomputable by its reader, and a consumer meeting one reads that stamp as published rather
than checking it. **A compilation the file does not carry is read the same way.** A compiled
rollforward's identity is the hash of its published machine (section 12.1), so where the
`gaspatchio_rollforward_ir` facet carries the body a consumer recomputes it, and where it does
not — every compilation in the `audit` profile, or one the exporting process could not reach —
the identity is read as published, and a deep reading names each such node. **And the chain
being checked is the identity chain and nothing wider**:
`formula` is no part of any node's canonical bytes (section 8.2), so a quotation edited after
the artifact was written recomputes clean, and what a full recomputation establishes is that
this is the same calculation — never that this is the file the producer wrote.

**`formulas_fingerprint` follows the same line between the profiles** (section 12.6). In
`executable` a consumer recomputes it from the trees, and the injected column is no obstacle
there: with both of its attributes masked its bytes are one constant a reader can take from
the node's `provenance`. In `audit` it is read as written.

**A selection step is verifiable from either profile** (section 7.6). Its tree travels in both,
so a consumer recomputes its `local_fingerprint` from the kind and the tree, folds its
`fingerprint` over the published fingerprints of what it reads, and takes `graph_fingerprint`
again with section 12.4's fourth section; `formulas_fingerprint` is recomputed from it where the
nodes' trees allow, as above. A holder of the book checks the columns the steps read with the
rest of `book.columns`, which is what makes a book in which an in-force flag moved another book
even where the model dropped the flag.

**An inline assumption payload (section 15) is the exception**, and it is verifiable from the
`audit` profile: a consumer re-hashes the inlined values and compares the result against the
declared fingerprint. The rule holds today for each of the four kinds the section carries,
and section 12.3 already states both grammars it needs. A **table**'s payload declares its
columns, their types and their rows, and re-hashes under the content grammar over exactly
what it declares: **those columns in the payload's own order, those rows in the payload's
own order, no projection and no re-sort.** The payload is the frame the producer hashed, not
a view of it, so a consumer that tidied it first — sorting by the dimensions, on the
reasonable-looking theory that a table is keyed, or dropping to the dimensions and the value
column — would hash a different frame and reach a digest that matches nothing. **A
non-finite float arrives as the string sentinel section 10 defines, and is read back to the
float before hashing**: `"NaN"`, `"Infinity"` and `"-Infinity"` in a column declared `f64`,
or as an element of a `list[f64]` at any depth, are that column's numbers, and the grammar's own NaN normalisation then applies to them as
it does to any other. A **join**'s payload re-hashes the same way and under the same
grammar, over the columns and the rows exactly as carried. It declares no roles, so there is
nothing to project away and nothing to check beyond the digest: the sort that put its rows
in this order was the producer's, taken before the hash by section 12.3's rule for a right
side, and a reader who sorted again would be re-deriving an order rather than checking the
one published. A **schedule**'s and a **curve**'s payload is the canonical form that
entry's own source stamp was taken over, and re-hashes under the recipe grammar. Note which
digest a table's entry publishes: its content hash, not its `source_sha` — section 12.3 says
which string is which. No kind is re-described on the wire for this purpose: each
entry carries the very form its declared fingerprint was taken over, so what a consumer
hashes is what the producer hashed. Section 15 defines the entry; this section defines
its verification. Where the payload was not inlined there is nothing to re-hash, and section 6.1's
`omitted` object is how a producer says which of two things happened: under `size`, the
declared fingerprint is a claim about data the producer held and weighed and left out, and
the reader is being told what fetching it would cost; under `unavailable`, it is a claim
about data the producer named and could not vouch for, and the reader is being told the
producer's own account of this base is short.

**The model's own source (section 7.3) is verifiable the same way and under no grammar at
all.** An entry's payload carries the file's text; a consumer encodes that text as UTF-8,
takes SHA-256 over the bytes, and reaches the entry's `fingerprint` — which for the model file
is `model.source_sha`, the digest the envelope already published beside it. That is the check
that turns "here is some code" into "here is the code this run was made from", and it is the
one a page showing a line of the model rests on. UTF-8 is a round trip on valid text, so there
is no normalisation step to get wrong and no rule about line endings: the bytes the producer
hashed are the bytes the consumer re-encodes. Where the text was not carried, section 6.1's
three reasons say which of three things happened, and only one of them — `withheld` — means
the producer could have carried it.

**The obligation that makes all of that work sits on the producer, and it is stated here as
a requirement rather than left as an assumption.** Section 12.3 says a table puts itself in canonical
form before hashing; this section says re-hash the payload's own order with no re-sort.
Those two sentences agree only if the frame that was inlined *is* the frame that was hashed,
so: **a producer inlining a payload MUST inline exactly the frame its declared fingerprint
was taken over** — the same columns, in the same order, the same rows, in the same order,
already sorted if sorting is what that kind does. A producer that hashed a sorted frame and
then inlined the file's original order has published a payload that verifies against nothing,
and no field in the document would say so: the digest is well formed, the payload is well
formed, and they are accounts of two different frames. A consumer meeting a mismatch reports
the entry as failing verification and must not attempt to recover it by sorting — a payload
that only verifies after the consumer rearranges it is a payload whose order was never
pinned, and re-deriving the digest is the whole point.

**The book (section 7.5) is verifiable by whoever holds it, and by nobody else.** The document
carries no value of the book, only its digest, so a consumer holding the file alone reads the
digest as published. A consumer holding the policy data takes section 12.3's content grammar
over the columns `book.columns` names, in that order, with the rows as the data holds them,
and reaches the published `digest` exactly when this document is an account of that data. A
mismatch says the document was built over other policy data, or the data has moved since; a
consumer must not reorder rows or retype columns to make it match, for the reason a payload
must not be re-sorted above. (Reading a category as its text is section 12.3's own rule for a
book, taken by producer and consumer alike, and not a retyping.) Holding the data is the whole
request: a verifier handed the book checks it, and needs no further setting to be asked.

**A table's entry is verifiable against a file by whoever holds the file.** The entry's
payload is the processed frame, and a reader holding the file the table was read from re-reads
it as that table: the payload's `columns` less its `value` as the keys, and the `value`, taken
from the file — a key the payload carries as `str` read as text, as a table rebuilt from its
processed frame keeps it — through the steps a table's construction takes and section 12.3's
canonical form, to the content hash the entry's `fingerprint` carries. It is the same digest
however the file is laid out or encoded, and a moved value moves it. A payload omitted for its
size states the same three members as `roles` in its stand-in (§15), so such a table is read the
same way. A table entry's `source_file` (§15) says where to look: the file it was read from, or
null where the model handed the table a frame rather than a file's path, which has no file to
be held against — that is reported as such, and is not a failure.

**A difference decides only for a plain read of a named file.** Where `shaped_by` (§15) lists
any step — a column renamed, cast, melted, set or computed — the processed frame is not a plain
read of any file, and a reader does not read one back as the table: a reshaped table must never
read as an edited one, and naming a file for it names the file, not the recipe. Where
`source_file` is null, or absent, the model handed the table a frame and nothing records what
that frame was: rows filtered or values derived in code before the table was built, and an edit
to the file since, read alike, so a file that reads as the fingerprint agrees and one that does
not leaves the question open. Only where `source_file` names a file and `shaped_by` is empty is
a different fingerprint a disagreement. A file that does not hold the recorded columns, an
entry stating no roles at all, and the two cases above are checks that could not be made rather
than differences. A reader looks for the file only among the files and directories it was
handed: `source_file` names where the file sat when the record was written, and a check that
opened it there would be checking whatever sits there now.

**A local module is verifiable as the model file is.** Each `model.modules` entry's
fingerprint is SHA-256 over a file's bytes, and the file is the one beside the model file the
reader holds, at the entry's path taken relative to the directory of `source_path` — which is
where running that model would import it from. A module that differs is a model that differs,
whatever `source_sha` says; one the reader's copy of the model does not have beside it is a
check that could not be made. **So is a model that loads code by its path** — a helper
reached through `importlib`, `runpy` or `exec` rather than an import statement, which
`model.modules` does not list (§7): a verifier holding the model names each such call and
reports the modules check as one that could not be made, never as agreement over the modules
it did hold, since an edit to the helper it cannot see would move figures with nothing on the
record moving.

**So is a document whose holes section is not empty** (section 7.1). A hole is carried by name
only: its values reach no digest, so whatever they were read or computed from — a file joined
to the policy data after the frame collected it, a write past the producer's doors, a
calculation on another frame — is held by no check, and an edit to it would move figures with
every file the verifier holds still agreeing. A verifier asked about the inputs a document's
numbers rest on — its model, its policy data or its assumption files — names each hole, its
reason and the columns that rest on it, and reports the holes check as one that could not be
made, whatever the reason the hole carries; an empty section agrees. A results file held alone
is asked only whether it is the file the run wrote, which no hole touches. A document recording
no assumption table and no join has nothing to hold assumption files against, and that check
agrees rather than staying open: nothing recorded is nothing to check.

**A model is decided by the graph its files rebuild.** A file's digest says whether the file
moved, not whether the numbers did: a model reads values from places no stamp holds — a scalar
taken out of a parameter file, a configuration file, an environment variable, a module imported
from outside the model's directory, a scenario plan's shock factor — and each moves a formula
while every file the document stamps still agrees. A verifier holding the model and the policy
data it was run over therefore rebuilds the graph: it imports the model and runs it over that
data — or, for a document whose `model.scenarios` names a plan, composes the plan over it — as
the producer built the frame it exported, computing no value, and takes `graph_fingerprint`
again under section 12. **A rebuilt fingerprint that differs is a model that differs**, whatever
the stamps above say, and the verifier names each node whose `local_fingerprint` moved, with its
`formula` and `source_location`: that is the line a moved input entered at. The stamps keep
deciding beside it, and one that differs still differs. **The rebuild runs the model's own code,
so its answer holds in the environment it ran in** — the verifier's interpreter, its installed
packages and its environment variables, and the files the model reads where it reads them —
and a verifier says so; the reference verifier runs it in a process of its own, so that nothing
an earlier import left behind is read in place of the files. A model that cannot be rebuilt
there, or a verifier not handed the policy data it was run over, or a scenario plan's document
not handed the plan, is a check that could not be made, naming why. **A node whose calculation
hands the engine a host-language function or a compiled extension function** (`map_batches`, a
plugin; section 11.2's `engine_native`) is fingerprinted by what it calls and not by what the
function computes, so a value read inside one moves figures with the graph unmoved: a verifier
names such a node and reports the check as one that could not be made, never as agreement, even
where the fingerprint agrees. **A compiled rollforward enters the graph only by its identity**,
so a body its facet publishes that was edited after export and resealed rebuilds the same
graph: before the rebuild decides, the verifier takes each published body's identity again
under section 12.1 and holds the node's movement summary to it, and a body that is not the
machine its identity names is a model that differs, naming the compilation, whatever the
rebuild says. This check departs from the rest of this section, which reads only
the document and the files it was handed: it runs the model, needs what the model reads, and its
agreement is agreement here.

What propagation verification actually buys the reader is the pair of questions a
quarter-over-quarter review asks: **which node changed on its own, and which inherited a
change from upstream.** A node whose `local_fingerprint` matches last quarter's and whose
`fingerprint` does not was not edited — something it reads was, and the artifact says which.
Verifying the propagation is what makes that reading a fact the reader checked rather than a
story the producer told about its own file.

### 13.1 The document seal

Everything above verifies the **calculation**, and the paragraph on the identity chain says
where that stops: `formula` is no part of any node's canonical bytes (§8.2), so a quotation
edited after the artifact was written recomputes clean through every check in this section,
under both profiles. The exclusion is deliberate and stays — an identity moves when the
computation moves and at no other time — and it leaves a second question unanswered. **Is
this the file the producer wrote?** `document_digest` (§7) is the answer to that one, and
this is the contract for taking it again.

**The byte stream.** The seal is a SHA-256 over the document's own canonical serialization,
under the **recipe grammar of §12.3** — the same encoding a `source_sha` is taken under,
applied to the document instead of to a recipe. There is no second canon:

1. Take the document as the JSON value a parser produces.
2. Remove the top-level member `document_digest` if it is present. **Nothing else is
   removed.** `created_at`, `producer`, `model`, every node, every edge, every facet and
   every inlined payload are inside the seal, because its subject is the record and not the
   calculation.
3. Encode what is left under §12.3's recipe grammar: object members sorted by key at every
   level, by Unicode code point, exactly as §12.1's attribute keys and §12.4's sections are
   sorted; array order preserved as the document states it; `,` and `:` as separators with
   no insignificant whitespace; every non-ASCII character escaped, so the bytes are stable
   across platforms; and the non-finite tokens `NaN`, `Infinity` and `-Infinity` refused
   rather than written — §10's string sentinels are how such a value travels, and a document
   holding a bare one is outside the JSON grammar as well as outside this one.
4. Stamp the digest as §2's content hashes are stamped: `sha256:` and sixty-four lowercase
   hex digits.

A consumer holding this document and the standard library of its language recomputes the
seal in five lines: parse, drop that one member, re-encode under the rules above, hash,
stamp. Nothing from the producer's software is needed and nothing is fetched.

**The one residual, stated rather than left to be met.** A number is written in the shortest
decimal form that reads back to the same value, and two implementations that spell one such
number differently reach two digests. That is the recipe grammar's own property, carried by
every `source_sha` this framework has published, and not something this member introduces;
the alternative — a second canon over the document's own number lexemes — is exactly the
duplication §12.3 exists to avoid.

**It reaches the document a supervisor reads, and the example that shows it is one this
format ships.** An `audit` artifact carrying no value samples and no inlined assumption
payload is the narrowest document written here, and it is not thereby a document of whole
numbers: §17's `state_graph` payload states each transition's intensity as an operation
tree, and a `lit` node inside one carries whatever number the product was quoted with.
`state_graph_example.json` — the artifact §17 stands behind, declaring `"profile":
"audit"` — carries no value sample anywhere in the file, and with its two inlined table
payloads removed it still holds the literal `3.4`, a loading on a mortality intensity,
inside the bytes this seal is taken over. `nested_valuation` (§17) will carry numbers the
same way. So what bounds the residual is the numbers a document holds rather than the
profile it declares: two implementations reach one digest for a document whose every number
is whole, because a whole number has one spelling, and for any other document they agree
exactly as far as they spell a float alike.

**What a deep verification does with it.** Four readings, and the grades are the two §6.1's
`omitted` remark already established rather than a third:

| What the reader meets | Grade | What it says |
|---|---|---|
| No `document_digest` | **remark**, and the schema refuses the document | The document is unsealed, and the remark says which reading a consumer does not get. The refusal comes from the schema rather than from here, because the member is required under this identifier (§7): the two voices answer different questions — what shape is missing, and what could not be checked — and a reader wants both. |
| Present and not a stamped digest | **refusal** | A seal nobody can parse is a seal nobody can check. |
| Present, well formed, and not equal to the digest taken again | **refusal** | **This is not the file the producer wrote.** |
| Present, and the grammar refuses a value in the document | **refusal** | The seal cannot be recomputed, and the reader is told which reading they did not get. |

The third of those is the one the section exists for, and what it does *not* say is as
important as what it does. A disagreement need not be a calculation: the fingerprints cover
what would run and the seal covers the record, so an edited quotation, a rewritten
`source_location` or a re-dated envelope reaches the seal and reaches no fingerprint. It is
that asymmetry — clean fingerprints, a broken seal — that names the edit for what it was.

**Every citation of one document by another carries the cited document's seal beside the
identity it already carries.** A change report naming the two artifacts it compared names
each one's `graph_fingerprint` and each one's `document_digest`; so does any other record
that points at an artifact it does not enclose. The seal is *recorded* there and never
compared: two exports of an untouched model carry two seals and one `graph_fingerprint`,
which is the difference between the two questions written in the two fields, and a report
that read a moved seal as drift would fire on every pair of exports ever taken.

**The limits, and they are the point of the paragraph above.** This is **tamper-evidence and
not tamper-proofing.** A seal a document carries is a digest whoever edits that document can
take again, so a forgery that re-seals itself is internally consistent and no reading of the
standalone file will catch it. What catches it is the citation web: a document whose seal
disagrees with every record that ever cited it is a document somebody rewrote, and that is
why the recording rule above is normative rather than a convenience. **Non-repudiation is
producer signing** — a digest the producer alone could have produced, checkable by a reader
who trusts a key rather than a file — and it is named here as future work and is not built.

**A payload kept outside the document is not a document, and takes no seal of its own.** A
producer may hold an entry's values beside the artifact rather than inside it — §6.1's
`omitted` vocabulary is how the entry says so, and §13 is what a reader does with those
values once they have them. Whether the stored bytes should carry a `document_digest` too is
the question a reader will ask here, and the answer is that they must not. `document_digest`
is an envelope member (§7) and a payload has no envelope; more to the point, **the identity
of those bytes is already recorded**, in the `fingerprint` of the entry that names them, and
already re-derivable from the bytes themselves under §13's rule. A second digest over the
same bytes says nothing the first does not, and one written *into* the payload would make the
file weigh more than the value its entry measured: §6.1's `bytes` is the size of that value,
carried so a reader can tell what obtaining it as a file would cost, and against a payload
holding a seal the entry would go on stating a weight that file no longer has. So there is
one mechanism and it is §13's: hash the values under the grammar that entry's kind is
stamped by, and compare against the `fingerprint` the artifact declares. How a store spells
that identity as a location is the store's business and no part of this format. Nothing in a
deep verification changes with where the values were kept: an entry that stands in for its
values reaches the `omitted` remark, saying that this one fingerprint was read rather than
checked, and it becomes the check the moment the values are in front of the reader.

**A holder who legitimately transforms a sealed document breaks its seal, and this is what
they do about the member.** The transformations are ones this format provides for: dropping
an inlined payload and saying so in §6.1's `omitted` vocabulary, redacting a
`source_location`, deriving an `audit` view of a document written under the `executable`
profile. Each rewrites bytes the seal was taken over, so the derived file meets the third
reading above and its holder is told it is not the file the producer wrote — which is true
of it, and is the mechanism working rather than a false alarm. Three moves are available and
this format allows two. **Leaving the old seal in place is the one it refuses**: the derived
record would carry a claim to be a file it is not, and the next reader spends their attention
on an edit nobody made. **Dropping the member** leaves the derived record unsealed and reaches the
first reading's remark — and under this identifier the schema refuses it, since §7 requires
the member, so what this buys is a record that says plainly it is nobody's published file
rather than a conforming one. A holder who needs the derived record to validate takes the
third move. **Taking the seal again** is the honest one, and it says what it implies: the digest now
states that the derived record is the file *this* holder wrote, so §7's `producer` names them
rather than the original producer. Either way the original's seal stands wherever it was
recorded, which is what keeps a transformation something a reader can follow back rather than
something that quietly replaces its subject.

### 13.2 The run record

A run that folds a model's results into reported numbers — a scenario plan over the scenario
axis, an aggregation over a policy book — writes a second record of itself beside its output:
the **run record**, which the reference producer calls the audit sidecar. Section 4 says why
it is a document of its own: this one grows with the model, that one with the run. The artifact
says how each number was made; the run record carries the numbers the run reported, the plan
that produced them, the calculation each scenario folded and the data it read. This
subsection is normative for the record written under `schema_version` `"2.1"`. **There is no
machine-readable schema for it in this preview** — this subsection is the account of it — and
its `schema_version` does not move with this document's own identifier.

It is one JSON object, outside the artifact's schema identifier and envelope, and every member
below is always present:

| Member | Type | Meaning |
|---|---|---|
| `schema_version` | string | `"2.1"`. |
| `source_sha` | `"sha256:<64 hex>"` | SHA-256 under section 12.3's recipe grammar over `plan_canonical_form`, so a reader recomputes it from the member beside it. |
| `plan_canonical_form` | object | What the run was asked to do. `kind` names the axis: `"ScenarioRun"`, beside `shocks`, `base_tables`, `aggregations` and `master_seed`; or `"run_aggregated"`, beside `aggregations` alone. Below those keys the forms are the producer's account of its own plan and no clause here fixes them: a reader takes `source_sha` over them and reads them as the producer's words. |
| `aggregator_identity` | object | Keyed by alias, what each reported number *is*: the same object `plan_canonical_form.aggregations` carries under that alias, written beside the numbers so that "what is this number?" is answered where the number is. |
| `aggregator_outputs` | object | Keyed by alias, the numbers (below). |
| `run_metadata` | object | What the run cost and what it ran under (below). |
| `graph_fingerprint` | `"sha256:<64 hex>"` or null | The one calculation the whole run folded, or null where no one calculation is true of it (below). |
| `graph_fingerprint_by_scenario` | object or null | The calculation each scenario folded, keyed by the scenario's own name written as text; null on the policy axis. |
| `input_data_fingerprint` | object | A content stamp of the policy data the run read, under the key `model_points` (below). |
| `bases` | object or null | Per table a shock moved, the content the shock was applied to and the file it came from; null on the policy axis (below). |

**The numbers.** A total is a JSON number — or, for an aggregator answering which scenario
reached it, that scenario's name. A per-period aggregator answers one value per projection
boundary — `T + 1` of them over `T` periods — as an array. A quantile family's levels are an
object of such runs. An aggregator partitioned with `.over(...)` answers an array of row
objects, one per group and period. A non-finite value is section 10's string sentinel, and no type travels beside
a value, so a consumer must not turn a `"NaN"` back into a float where the member could hold a
scenario's name. On the scenario axis, an aggregator not partitioned by the scenario folds every
row the run folded — all scenarios together. **A total of whole numbers is the book's exact
total.** A sum of an `i64` column — over the policies, within a scenario, or across scenarios —
is taken exactly whatever the batches were, and written as the double nearest it; a total
outside `[-2^63, 2^63 - 1]` is refused by name, with its exact value, never wrapped and never
moved by the batch size. A per-period total is such a total at each period: each period's sum
of an `i64` column, and on the scenario axis each scenario's sum at a period that a per-period
statistic then reads, is taken exactly and refused so, naming the period — the run's index
from 0 — and, within a scenario, the scenario. **So is every statistic of whole numbers read
from totals.** A mean, a variance or a standard deviation of an `i64` column — per policy or
per period, over the policies or across scenarios — is read once from the exact count, total
and, for a spread, total of squares: a mean is written as the double nearest the exact total
over the count, a sample variance as the double nearest `(n·Σx² − (Σx)²) / (n(n − 1))`, and
a standard deviation as that exact ratio's square root rounded once. None moves with the batch
size, and none is refused, since each lies within the reach of a double. A whole number folded
beside a decimal is read as a double from then on, as a decimal column is throughout. A
quantile, a median or a tail expectation reads each value as the double nearest it — `-2^63`
is `-9.223372036854775808e18` — and answers within its sketch's stated relative accuracy. A
scenario's mean of its own policies (`within="mean"`) is such a mean, read from the scenario's
exact total and count — `2^63 − 1`, `−2^63` and `5` average `4/3` — and each other reduction
of a scenario's policies is its exact total (`within="sum"`, refused past `i64` as above), its
count, or a value the column holds (`max`, `min`, `first`, `last`), carried exactly into the
statistic across scenarios.

**A run's figures are the book's.** A producer refuses a calculation that reads across rows —
an aggregation, a window, a cumulative operation or a count of the rows, written in an
engine's own expression language (§11.2 `engine_native`) — on the policy axis wherever the run
cuts the book into more than one batch, and on the scenario axis at any batch size; outside a
run, a frame crossed with a scenario axis refuses such a read made after the cross-join. There,
the rows such a read answers from are a batch, or every scenario's copy of the book. **One
partition is admitted on the scenario axis**: where the policies are not cut into batches —
every scenario plan, which batches scenarios and never policies, and a frame crossed with the
axis outside a batch runner — a read inside a window whose partition includes the scenario
column, `pl.col("sa").sum().over("scenario_id")` or `.over(["scenario_id", "product"])`, answers
from rows of one scenario's whole copy of the book, which is that scenario's figure or a part of
it, and is not refused; a further partition key that itself reads across rows is refused as such
a read. A read taken across rows outside the window, or a window that maps its answer other than
back onto its rows, is refused there as an unpartitioned read is, at any number of scenarios per
batch; where the policies are cut into batches the partitioned read answers from the batch's
copy and is refused with the rest. **A
shared projection grid sized from the rows** (§11.1.1) is a read across rows too — its length is
the youngest issue age or the longest horizon among the rows in the frame — and is refused
wherever such a read is, with no partition admitted, since one grid serves every row. **So is
a selection's condition** (§7.6): a filter keeping the policies above the mean sum assured
chooses from the rows in the frame, and is refused wherever an assignment reading that mean
would be, the scenario partition admitted as there. **So is a function a producer cannot
read**: a function written in the host language and handed to the engine (`map_batches`,
`map_elements`, `rolling_map`) carries no body a producer can read, so it is refused wherever a
read across rows is, whatever it declares; a compiled extension function is taken at its own
declaration, and one not declared elementwise is a read across rows. **So is a column
injected wholesale** (§12.3): it lands on the rows by position, so where a run cuts the book its
values would be paired with whichever policies share a batch, and an injection of more than one
value is refused there; anywhere, a producer refuses one whose length is not the row count of
the frame it lands on. **A run of one policy taken from the book is such a cut**: the
reference producer's single-policy run runs the policy alone under this rule, and where it
refuses a read across rows runs the whole book instead, selects the policy from it and says so,
naming the read; the result's manifest then records the whole book's `inputs_digest`, and a
policy the model's own selection drops from the book is refused by name. Every
per-policy figure a run record folds is therefore a function of that policy's inputs and the
model, and does not move with `batch_size`. **So is a frame the model builds over values
that left it.** Where a run cuts the book into more than one batch, a frame the model builds
from a table of values — `ActuarialFrame(df)`, with or without `continue_from=` — is refused
unless the table is the batch's own: no column the batch did not hold, every column equal to
the batch's row for row, and the batch's rows. A table holds values and not the expressions
that made them, so a producer cannot tell a read across rows among them from a per-row join,
and refuses both; the reference producer names four ways out — the join made through the
frame (`af.join`), which the record follows; the column computed on the book before the run;
the book run in one batch; and an engine that runs the setup over the whole book before it
cuts the batches (`engine="jax"`). A frame built from a plan rather than a table is judged on
the plan: built over the batch's own values, with no step or expression in it reading across
rows. A table in memory such a plan joins is read as a side table, and values the model
computed from the batch's rows before it handed them over as one are not seen. A rebuild that
chose its rows outside the frame is refused with the rest, and stands wherever the run's one
batch holds every policy (section 7.6). Whole policies do not excuse a batch that crosses
scenarios: a scenario plan whose batch holds more than one scenario hands the model every
scenario's copy of the book, crossed, so a rebuild there is judged against that crossed frame
as a rebuild in a batch of policies is judged against the batch, and refused by name; a
scenario plan running one scenario a batch hands the model that scenario's whole book, and
judges none of this. `with_scenarios` crossing the book with more than one scenario hands back
such a frame with no plan around the model, and is held to the same rule: a frame built over a
table carrying the crossing's axis and columns, or over a plan scanning its book and its axis,
is judged against the crossed frame and refused by name, naming the column computed on the book
before it is crossed and the join made through the frame; a crossing of one scenario judges
nothing. **Nor does the type a run writes a column at.** A
column shock that makes a whole-number column a double in one scenario makes it a double in
the rows of every scenario composed beside it; the reference producer reads such a column as a
double in every batch, so each batch file it writes carries one type for the column whatever
scenarios share the batch, and the files read as one dataset.

**`graph_fingerprint` and `graph_fingerprint_by_scenario` are calculation identities, not
citations of documents.** Each is section 12.4's graph fingerprint of a calculation the run
composed, taken in memory. No document was written for any of them, so there is no seal to
record beside them, and section 13.1's citation rule — which binds a record pointing at a
*document* — does not reach them. On the scenario axis each scenario is composed alone, so a
scenario with no shocks, BASE in the ordinary plan, carries the standalone model's own
`graph_fingerprint`: that equality is the proof that BASE is the model that was reconciled.
**A model whose own records read `scenario_id` is composed alone over a one-scenario axis
instead** — a model that picks its discount curve per row on the axis, say. Composed with no
axis it would be a different calculation, and every scenario would carry BASE's figure, a
false identity; composed over the book crossed with that scenario's name alone, its shocked
bases in place, each scenario carries a figure of its own — an unshocked scenario's equals the
model's own export over the book crossed with that one scenario — and none claims to equal an
export with no axis, which such a model cannot make. For every model that does not read the
axis, BASE equals the standalone export. A
table shock reaches its scenario's figure through the table's content (§12.4) and a column
shock through the assignment it writes at the plan's line (§8), so a shocked scenario's figure
is not BASE's. **The shocked table is read under the name the model gave it.** A producer that
holds a scenario's shocked copy under a name of its own — the reference producer registers it as
`<name>_shocked`, so the base stays registered under its own name — takes the scenario's figure
with every read of the copy naming the model's table, a mortality wrapper's recipe (§11.1.10)
taken again over that name: the name is the registry's convenience, not the model's. So a shock
that leaves every rate as it was (`× 1.0`, `+ 0.0`) leaves BASE's figure, and a shocked
scenario's figure is the one the model gives exported over the shocked rates under the table's
own name; section 12.6's formulas digest of that composition, which keeps the name and masks
the content, is BASE's. `graph_fingerprint` is the one figure every scenario agreed on — on the policy
axis, every batch — and null where they differ, as they do wherever a shock reached the
calculation; a value inside the map is null where the producer could not take a stamp. **Each
figure is taken told the book's columns**, as `gspio calc-graph` is told them, so a record a
batch runner or a scenario plan writes names the holes an export of the same model names, each
stamped (section 7.1). A stamp is of the values the frame held, so on the policy axis batches
that hold different rows of an arriving hole fold different figures, and `graph_fingerprint`
is null there, as it is wherever they differ. An export of the run is one
document over the cross-joined frame, and its own `graph_fingerprint` is that composition's,
equal to none of the per-scenario figures.

**`bases` names what each table shock was applied to.** A plan names a table by its name, not
its content, so this member is where the record says which rates a shock moved. Each entry,
keyed by the table's name, is `{fingerprint, source_file}`: `fingerprint` is the content hash
(§12.3) of the table the model read, before any shock — the string the artifact writes as that
table's entry `fingerprint` (§15); `source_file` is the file it was read from, written relative
to the working directory the run was made in, or as its name in angle brackets where it lies
outside that directory, or null for a table built in memory. That is not section 7's rule,
and a reader holds the two apart: an artifact's paths are relative to the model's root,
keep a sibling directory's `..` climb and name any other file outside the root under
`<outside the model's root>`, where this member is relative to the working directory, never
climbs, and names a file outside that directory by its name alone — `<mortality.parquet>`.
Neither writes an absolute path. The member is an empty object
where the plan shocks no table, and null on the policy axis.

**`input_data_fingerprint` stamps the data the run was handed.** Its one member,
`model_points`, is a digest under section 12.3's content grammar over that frame — every column
in the frame's own order, the rows in the order the run read them — wherever the grammar could
name every column. Where it could not, it is an object, `content_sha` beside
`columns_not_stamped`: the digest over the rest, null where no column could be stamped, and
each column left out as `{column, dtype}`, the type in the engine's own spelling. A partial
stamp never arrives in a whole one's shape: a digest string covers every column, and an object
names what it does not cover.

**Three identities of the policy data, and none is derived from another.** The artifact's
`model.model_points.fingerprint` is SHA-256 over the bytes of the file a run read (§7, §12.3).
The artifact's `book.digest` is the content grammar over the columns the model's answers rest
on, in name order, a category read as its text (§7.5). This record's `model_points` is the
content grammar over every column of the frame the run was handed, in that frame's order, with
a column the grammar cannot name — a category among them — left out and listed. Two share a
grammar and differ in their columns and their order, and the third is a file hash, so the three
agree only by coincidence: a reader matches each against what it stamps — the file, the book,
the frame — and never against another.

**`run_metadata` is what the run cost and what it ran under.** Its measurements are
`wall_time_s` and `batch_size`; on the scenario axis `n_scenarios`, `batch_size_resolution`,
`selection_engine`, `selection_reason`, `selection_probed` (each probe's `batch`, `engine`,
`per_sc_s`, `peak_mb` and `fits`) and `master_seed`; on the policy axis `n_policies`, the
number of policies the model valued (the rows the totals were folded over, which is fewer than
the book holds where the model chose its policies, section 7.6), and
`n_periods`, the length of the per-period runs folded, which counts boundaries, `T + 1`, and
not periods. They move on every run, so the record's bytes, and the fingerprint an artifact
names it by, move with them. Beside them stand **the six library keys** a results file's manifest and an artifact's
`producer.versions` state — `core_version`, `extension_version`, `extension_sha256`,
`polars_version`, `python_version` and `platform`, spelled as those spell them — and
`ddsketch_version`, `"unavailable"` where it is not installed; and, where a second engine folded
the book on the policy axis, `engine`, `engine_versions`, `inputs_digest` and `engine_notes`. A
record committed as a golden writes section 6.1's `withheld` form, `{"omitted": "withheld"}`,
under each library key and under `engine_versions`. **The record carries the library keys and
not `producer.versions.imports`, and no git**: those are the artifact's (§7), so the two records
of one run are held against each other key for key on the library and on nothing else. A
version difference is evidence, as everywhere in this format, and never a failed check.

**The artifact names the record, and the record cannot name the artifact.** An export of a run
that wrote one carries `model.audit`, `{path, fingerprint}`, the fingerprint SHA-256 over the
record's bytes as written (§7). The reverse citation is impossible by construction: the
artifact's seal covers that fingerprint, so a record carrying the seal would have to be written
after the document whose seal depends on it. The record carries no seal of its own and needs
none: the citation pins its bytes, and a reader holding both checks one against the other with
`shasum`.

**Where it is written is the producer's business.** The reference producer writes
`<run_id>.audit.json` — the UTC time to the second, and the first eight hex digits of
`source_sha` — into the run's output directory, or into `./gaspatchio_audit/` under the working
directory where the run has none, or exactly at a path the caller names; `gspio calc-graph …
--scenarios` writes it beside the export as `<name>.run.audit.json`. It is written whole, so a
reader never finds half a record under the name. A record under a default name is never written
over — two runs of one plan in one second share that name, and the second run's record is
refused, naming the move — while a record at a path the caller named is replaced, the caller
having named it.

**`"2.1"` is the record this document defines.** It differs from the `"2.0"` record the
reference producer's 0.9.0 wrote: `run_metadata.library_version` is gone, and the library is
stated by the six keys above, of which `polars_version` and `python_version` were already
there; `input_data_fingerprint`, written empty there, is filled; `aggregator_identity`,
`graph_fingerprint`, `graph_fingerprint_by_scenario` and `bases` are added; and the forms inside
`plan_canonical_form` are the plan's own, which changed with it.

## 14. Versioning and change log

**The `schema` string carries status.** `gaspatchio-graph/v0-preview.2` is not
`gaspatchio-graph/v0`, and a tool whose table (section 5) holds only a final `/v0` therefore
fails loudly on a preview artifact rather than resolving it to the wrong schema and
misreading it. Status belongs in the identifier because the identifier is the one thing
every consumer looks at first, and a status carried anywhere else is a status a consumer can
reach the nodes without having read.

**Preview strings carry a monotone counter** — `v0-preview.1`, `v0-preview.2`, `v0-preview.3`
and so on —
so that a consumer holding two preview artifacts can tell which is the older without parsing
dates, comparing timestamps, or fetching anything. That is the only fact the string is
allowed to carry to a reader. It is not a compatibility ordering: a later counter promises
nothing whatever about being able to read an earlier one. And it is not a resolution
mechanism — section 5's rule stands, and the identifier is still resolved through a table
rather than parsed. Nor does it separate anything *within* one value: section 14.1 records a
required field added inside `v0-preview.1`, so documents written before that line and
documents written after it carry the same string, and a consumer holding one of each tells
them apart by validating them against the schema rather than by reading the counter.

**Within a stamped `v0` the schema is additive only.** A field may be added, a closed
vocabulary may grow — section 9's narrowing vocabulary, section 11's binary operators — and
nothing already defined is removed, renamed, or given a new meaning. `fingerprint_algorithm`
(section 12.2) is the escape valve for the one change that cannot be made additively: the
byte grammar, where any change at all changes every digest in every artifact, and where a
new token is the only honest way to say so.

The preview closes — and the format becomes one a consumer may hold still — when all of the
following hold:

1. the rollforward, state-graph and nested-valuation payload sections have each been
   exercised — the first against a live emission, the other two against a hand-built example
   the published validator accepts;
2. artifacts from real models have been read end to end through the viewer, the validator
   and the change report;
3. an independent implementation has reproduced the conformance corpus digests of section
   12.5;
4. the core operation vocabulary of section 11.1 carries stated semantics;
5. no open defect against this specification.

### 14.1 Change log

Every change to the format takes one line here, against the version it landed in, newest
last. Section 1 says why: for a preview the change policy is documentation rather than
compatibility work, and this is the document a consumer reads instead of being carried
across a change by a shim that was never written.

- `v0-preview.1` — first published preview.
- `v0-preview.1` — the content grammar of section 12.3 stated normatively, joining what
  `fingerprint_algorithm` covers. The token did not move: nothing had been published carrying
  a content digest, so no digest existed to be read under the wrong grammar. Section 12.2
  says the same thing where a reader of the rule will meet it.
- `v0-preview.1` — section 8.2's rule for `formula` stated at the width it is produced at: the
  recording door earns the null rather than the number of columns behind it, a `date`
  derivation joins the doors that earn one, and the text is declared free-form so that a
  consumer parsing it as a bare expression is told what it will meet. No field, value or
  encoding changed, and no artifact valid before this line is invalid after it.
- `v0-preview.1` — section 7.2 states that a hole's `materialized_at` is always null. A producer
  cannot see when a column it cannot account for acquired its value, so the ordinal such a node
  used to carry was the order the producer happened to seed it in rather than anything observed.
  No field, value or encoding moved; a value the producer could not substantiate is no longer
  claimed.
- `v0-preview.1` — the conformance corpus of section 12.5 published: the model it is an account
  of, its `graph_fingerprint`, and both of every node's digests. `fingerprint_algorithm` keeps
  the value `gspv0-preview-1` rather than moving with it. No byte grammar changed here, and the
  one earlier change that did — the content grammar joining what the token covers, recorded
  above — reached no published digest, so there has never been an artifact a new token could
  have told this one apart from. Bumping would have said that digests under the old token were
  digests of something else, which was true of nothing. The corpus is where the token begins to
  mean something, and every grammar change after it moves the token.
- `v0-preview.1` — sections 7.1 and 8 state a hole at the width it is minted: a column on the
  frame with no account of itself, or a name a record reads that no frame ever held. Both have
  always been produced, and only the account of them was narrower than the thing it described.
  Section 8's leaf sentence gains the injected column in the same pass — it carries a null
  `tier` and a stated `origin`, and neither half of that sentence reached it. No field, value
  or encoding changed.
- `v0-preview.1` — `reads_assumptions` added to the node record (section 8): required, usually
  empty, and naming the entries of the `assumptions` section a node's own formula reads.
  Section 15 notes where the two meet, and Annex A's reading of Article 244(g) is re-pointed at
  it, since the join it recorded as missing is the one this field makes. Being required, this
  is the first line here after which an artifact valid before it is not: a document written
  without the field is refused by the schema. No digest moved — the field is no part of any
  node's canonical bytes (section 12.1) — and the corpus of section 12.5 was regenerated
  carrying it, with every digest in its table unchanged.
- `v0-preview.1` — section 12.4's second digest section named at what it counts: every
  assumption **table** content hash, rather than every assumption content hash. A schedule
  and a curve reach the digest through the canonical bytes of the node whose formula reads
  them and were never in that section; an implementation that had read the sentence as
  written would have hashed a section nothing produces. No digest moved, none could have,
  and `fingerprint_algorithm` therefore keeps its value: the corpus of section 12.5 carries
  no schedule and no curve, and its table is unchanged.
- `v0-preview.1` — section 13's re-hash of an inlined assumption payload stated as a check a
  consumer can run rather than a commitment waiting on section 15. The rule holds for all
  three kinds the section carries, under the two grammars section 12.3 already states: the
  content grammar for a table's declared columns and rows, the recipe grammar for the
  canonical form a schedule or a curve hands over. No field, value or encoding changed —
  what moved is that the document now names the rule the payloads are already published
  under.
- `v0-preview.1` — section 12.3's account of how an assumption table orders and projects the
  frame it hashes corrected to the digest the format actually publishes: the whole processed
  frame, columns in the frame's own order, rows sorted by its key columns. The sentence as
  written — dimensions and value column, sorted by the dimension columns — describes the
  content hash carried *inside* a table's recipe, which is a different string from the one a
  lookup node carries and the `assumptions` section publishes as an entry's `fingerprint`. An
  implementation following it would have derived a digest matching nothing whenever a table's
  frame does not happen to hold its dimensions first and in name order. Section 12.3 now
  states that a table takes this hash twice and which of the two is published, and section 13
  states the form a consumer hashes an inline payload under. No digest moved: what the
  producer emits is unchanged, and the corpus of section 12.5 carries no assumption entry.
- `v0-preview.1` — section 6.1's `omitted` reason becomes a closed pair rather than a single
  word. `size` keeps its meaning and its required `bytes`; `unavailable` joins it, for a value
  the producer named the identity of and cannot vouch for now, and carries no `bytes` because
  none was taken. The schema states that conditionally: `bytes` required and an integer under
  `size`, absent or null under `unavailable`. **No artifact valid before this line is invalid
  after it** — every omission a producer could previously write was `{"omitted": "size",
  "bytes": N}` for a non-negative integer `N`, and every one of those still validates; this is
  a closed vocabulary growing, which section 14 allows within a stamped `v0`. The same pass
  states what `bytes` measures: the serialisation the enclosing document is written in, rather
  than the tightest one a writer could manage, so the number is a cost in a file. No digest
  moved and none could — a payload is no part of any node's canonical bytes (section 12.1) —
  and the corpus of section 12.5 carries no assumption entry at all, so its table is
  unchanged.
- `v0-preview.1` — section 10 states how a non-finite `f64` travels: the string sentinels
  `"NaN"`, `"Infinity"` and `"-Infinity"`, read back to the float by any consumer doing
  arithmetic or a section 13 re-hash. The bare tokens a lenient JSON writer emits for these
  are outside the JSON grammar and a strict parser refuses the whole document over one, so a
  producer emitting them writes a file that is not readable rather than a value that is not
  understood. Section 12.3's own position on NaN is untouched, and no digest moved: the
  content grammar already normalised every NaN to one payload, and it is that same float the
  sentinel resolves to.
- `v0-preview.1` — section 16 written: a compiled rollforward is one node, its running states
  are nodes of their own, and every extraction from it reads the compilation rather than the
  columns the compilation consumes. Nothing here is new to the format — the `rollforward` and
  `state` kinds, the two reserved namespaces, the `rollforward` recording door, the `states`
  field and the running-state leaf tag `0x22` were all defined already and none of them was
  produced. What lands is the first live emission of them, together with the three sentences
  the sections around it owed: section 9 says the state-read rule fires on the `rollforward`
  node and only there, section 12.1 says a running state's bytes are taken over the state
  reference rather than the reserved id, and section 11.1 gains the identifier `rollforward`
  for the compilation's own node. **No digest of any artifact without a rollforward in it
  moved, and none could:** every byte named here is a byte no model produced before, the
  conformance corpus of section 12.5 carries no rollforward by construction, and its table is
  unchanged. A model *with* a rollforward in it does move, because what such a model's
  extractions read is now the compilation rather than a list of columns — which is the
  correction, not a side effect of it. `fingerprint_algorithm` therefore keeps its value: no
  digest published under it is a digest of something else.
- `v0-preview.1` — section 8.1's reserved-namespace rule states the refusal it always implied,
  and sections 9 and 16 are corrected where they claimed more than they could. A column named
  into `state:` or `rollforward:` is refused by name whether or not anything contends for the
  id: a rule enforced on collision alone leaves a node in a reserved namespace giving an
  account of a column, which is the one thing a node there is defined not to be, and the
  ordinary model is exactly the one it lets through. Section 9's "every other node in a
  rollforward model" narrows to every other node *that reads it* — a false universal as
  written, since such a model's arriving columns and timeline columns read no compilation.
  Section 16 gains a second degraded-producer carve-out beside the one `states` already had,
  for a wrapping line whose only reference to a compilation is a truncation of its identity,
  and one sentence saying an extraction carries no `trace` and why. **No digest moved and no
  artifact valid before this line is invalid after it**: an artifact with a column in a
  reserved namespace was already a document section 8.1 said could not exist, every other
  artifact is written byte for byte as before, and the corpus of section 12.5 carries neither
  a rollforward nor a reserved namespace, so its table is unchanged.
- `v0-preview.1` — `projection_set` and `join` join the vocabulary of section 11.1, each with
  its semantics stated: 11.1.1 says what a projection axis's columns are and how the
  configuration on the record determines them — together with the model points, for the
  horizons its own gap list names — and 11.1.2 states the relational join over the keys,
  type and right-side identity a node already carries. They were the last two
  operations an ordinary model reached that the table did not list, so an artifact of a
  projected model reported them `opaque` and carried that through the reads of nearly
  everything downstream. Both sections name what a conforming producer will still add — the
  model-point data a shared axis is sized from, the schedule object behind a
  `schedule_source_sha`, a cadence and a join type in vocabularies this document fixes
  rather than an engine's spellings, and the two key lists carried structurally rather than
  comma-separated in one string. **No digest moved and none could: a tier is no part of any
  node's canonical bytes (section 12.1)**, so every node's canonical bytes and every
  fingerprint in every model stand as before; what moves on the wire is the `tier` these two
  operations' own nodes report, and with it what a reader folding tiers through `reads` can
  say about everything downstream of them. The corpus of section 12.5 carries neither a
  timeline nor a join, so its table is unchanged, and `fingerprint_algorithm` therefore
  keeps its value. Section 11's count of the operations in the unnamed domain moves from
  three to five with them. This is a closed vocabulary growing, which section 14 allows
  within a stamped `v0`, and no artifact valid before this line is invalid after it — the
  tier vocabulary is unchanged, and an artifact written before it carrying `opaque` on one
  of these nodes is still a valid document, now saying less about it than a producer would
  say today.
- `v0-preview.1` — `clip` joins the vocabulary of section 11.1 with its semantics stated in
  11.1.3: a value held between a lower and an upper bound, the bounds carried as operands
  rather than as configuration so that a floor which varies by product is a column reference
  in the tree like any other. Unlike the two before it this is not a column a door minted
  but an ordinary line — a duration capped at a select table's last row — that reached an
  artifact as an engine fragment for want of an entry. **Digests move, and only where a
  producer's record of such a line genuinely changes**: a node that carried an engine
  fragment now carries a `call`, which is different canonical bytes for a different
  document, and every other node in every model is written byte for byte as before.
  `fingerprint_algorithm` keeps its value — the byte grammar of section 12.1 is unchanged
  and a `call` has been hashable under it since it was written; what changed is which of the
  grammar's node kinds a producer writes for this line. The corpus of section 12.5 carries
  no bound, so its table is unchanged. Section 11's count of the operations in the unnamed
  domain moves from five to six.
- `v0-preview.1` — `cut`, `is_in` and `replace` join the vocabulary of section 11.1, with
  their semantics stated in 11.1.4 to 11.1.6: the three ways a model sorts values into named
  groups — placement in one of a band's intervals, membership of a named set, substitution
  one for one. **What identifies a banding is the values written into it**, so the
  breakpoints, the labels, the membership set and the substitution's two sides are operands
  carried as sequence literals rather than attributes: an attribute is one flat typed value
  and could hold none of them, and an engine's rendering of a long argument list abbreviates
  its middle away, which made two bands differing only there one document. 11.1.4 names the
  one thing a conforming producer still needs and this revision does not give it: a banded
  value is an ordered category, and section 10's type vocabulary has no name for one, so a
  `cut` reaches an artifact only where something downstream has already turned it into a
  type that vocabulary holds. **Digests move where a producer's record of such a line
  genuinely changes** — an engine fragment becomes a `call`, which is different canonical
  bytes for a different document — and every other node is written byte for byte as before.
  Two of the three carry a rule about what is *not* in the identity, for the same reason:
  11.1.6 orders a substitution's pairs rather than leaving them as the formula happened to
  spell them, since every value is replaced at once and no value twice, so the written order
  is a difference between two records of one calculation; and 11.1.5 says that a collection
  fixing no order between its members is not a set written out at all, because the only
  order to write would be the one a run happened to iterate.
  `fingerprint_algorithm` keeps its value: the byte grammar of section 12.1 is unchanged,
  and both a `call` and a sequence literal have been hashable under it since it was written.
  The corpus of section 12.5 carries no banding, so its table is unchanged. Section 11's
  count of the operations in the unnamed domain moves from six to nine.
- `v0-preview.1` — `str.to_date` joins the vocabulary of section 11.1 with its semantics
  stated in 11.1.7, and brings the `str` domain with it. It is the first line of a projection
  whose model points carry their entry dates as text, and the format string is the whole of
  what makes one parse different from another: `"%Y/%m/%d"` and `"%d/%m/%Y"` read the same
  characters into two different dates. A producing engine's rendering of the expression drops
  the format entirely, so two models parsing the same column under different formats were one
  document with one digest — a false identity, not merely an unhelpful one, and the reason
  this entry carries its format as an attribute. 11.1.7 states what `strict` and `exact`
  change, that a null `format` means the producer inferred it and a second implementation
  cannot reproduce the parse, that an engine's hint about how fast the parse runs is no part
  of the operation and is not recorded — the same false difference in the other direction,
  since a hint that cannot change a date would otherwise give one parse two digests — and
  why the datetime and time-of-day parses are not here: a datetime carries a time unit and a
  zone that no operation in this document names.
  **Digests move where a producer's record of such a line genuinely changes**, and through
  every node that reads it, since a node's `fingerprint` folds in the identity of what it
  read. `fingerprint_algorithm` keeps its value: the byte grammar of section 12.1 is
  unchanged. The corpus of section 12.5 parses no text, so its table is unchanged. Section
  11's list of named domains gains `str`; the count of operations in the unnamed domain is
  unchanged.
- `v0-preview.1` — `round`, `floor`, `ceil`, `cum_prod` and `cum_sum` join the vocabulary of
  section 11.1, with their semantics stated in 11.1.8 and 11.1.9. The first three move a
  value to a whole step and the last two fold a per-period column along the projection's
  period axis; all five are lines an actuary writes on an ordinary projection, and all five
  reached an artifact as engine fragments for want of an entry. The accumulations are the
  costlier gap of the two: **a survival probability or a cumulative growth factor recorded
  as engine text takes every column downstream of it with it**, since a node is only as
  portable as the least portable thing in its tree, and it also loses the
  `DIRECT`/`AGGREGATION` reading of what it folded, so a model doing its accumulating in the
  closed form this framework prefers had no aggregation edges at all. Both entries carry a
  rule about what is *not* the operation. 11.1.8 says the tie rule is always recorded and
  never left to an engine's default, because half a penny is a penny under one rule and
  nothing under the other; 11.1.9 says the fold is along the periods and along nothing else,
  so the same engine method name applied down the model points is not this operation, and a
  producer must not write these identifiers for it. 11.1.9 also names what a conforming
  producer still needs and this revision does not give it: the reduction of a per-period
  column to one number per policy has a result of a different shape from its operand, and
  this document has not said how an operation states that, so a present value written that
  way is still an engine fragment. **Digests move where a producer's record of such a line
  genuinely changes** — an engine fragment becomes a `call`, which is different canonical
  bytes for a different document — and through every node that reads it, since a node's
  `fingerprint` folds in the identity of what it read. `fingerprint_algorithm` keeps its
  value: the byte grammar of section 12.1 is unchanged and a `call` has been hashable under
  it since it was written. The corpus of section 12.5 rounds nothing and accumulates
  nothing, so its table is unchanged. Section 11's count of the operations in the unnamed
  domain moves from nine to fourteen.
- `v0-preview.1` — `mortality.at` joins the vocabulary of section 11.1 with its semantics
  stated in 11.1.10, and brings the `mortality` domain with it. It is the first entry whose
  gap was a *convention* rather than a calculation: a select and ultimate basis holds a
  duration at its select period before it reads, and that clamp reached an artifact as an
  engine fragment while the structure, the select period and the age basis reached it
  nowhere at all — so two models reading one grid, one on rates built age last birthday and
  one age nearest birthday, were one document with one digest. 11.1.10 states the three
  structures, what the clamp does and what it deliberately does not do (it bounds above
  only; a duration below the base's first row is a miss and is answered by the miss
  policy), and that `age_basis` is a declaration
  about the base and never a conversion applied to the ages — a rate table on one age
  definition read with ages computed on the other is out by up to half a year of mortality,
  and both sides are integers, so nothing reports it. The section names two things a
  conforming producer will add: the dimension names travel as one comma-separated string,
  which is ambiguous for a name containing a comma exactly as 11.1.2 says of a join's keys;
  and the wrapper has no entry in the assumptions section of its own, so the convention is
  readable and not yet re-hashable. **Digests move where a producer's record of such a line
  genuinely changes** — an engine fragment becomes a `call` carrying the convention, which is
  different canonical bytes for a different document — and through every node that reads it.
  `fingerprint_algorithm` keeps its value: the byte grammar of section 12.1 is unchanged and
  a `call` has been hashable under it since it was written. The corpus of section 12.5 reads
  no mortality basis, so its table is unchanged. Section 11's list of named domains gains
  `mortality`; the count of operations in the unnamed domain is unchanged.
- `v0-preview.1` — the document closed to the width an independent producer needs. An
  isolated second implementation, holding this document, the schema and one artifact and
  nothing else, reproduced every digest on the *verification* path first-run and could not
  complete the *production* path: two of the corpus's own nodes were unreproducible from the
  prose, and twenty-two further readings were open — each one a place where two implementers
  could both read carefully and publish different digests for the same model. Section 12.5
  claimed a reader holding only this document was not missing anything, and that claim was
  false. This line is where it becomes true. **The closures.** 12.1 gains the bytes of an
  injected column — a `call` carrying `content` and `origin`, with the content stamp taken
  over a one-column frame under the fixed placeholder name `injected` — which is the one node
  class the section had no entry for; the rule mapping a JSON number token to the whole-number
  or decimal tag, in both directions, which single-numeric-type languages destroy; the
  boolean payload; the refusal of a date in a tree, stated as the position it is; sequences
  declared flat; an absent run declared the empty run; a null attribute declared a different
  claim from an absent one; the stamped form of a digest carried as an attribute; the field a
  leaf's name comes off for each of its three kinds; and what a leaf carries when its type is
  `unknown`, which a running state always is. 11.1.11 states the **signature of every
  identifier in the vocabulary** — operands with their order and meaning, attributes with
  their scalar types, and which of the two homes each value sits in — without which two
  producers mint different digests for identical models, the false positive section 12 exists
  to prevent. 12.4 states that its three sections carry no framing, that "sorted" is Unicode
  code point, that superseded definitions and reserved namespaces are in section 1, and that
  section 2 de-duplicates before it sorts. 12 states that the fold takes `reads` and not
  `reads_assumptions`, and which digests each profile folds. 8 states how an unversioned
  `col` name in a tree binds to a versioned node id, the reassignment idiom included. 10 is
  corrected where it said a date appears in a literal, and separates a column's `list[T]`
  from a formula's flat sequence. 13 puts the obligation to inline the frame that was hashed
  on the producer, where it belongs. 12.5 **prints the corpus's operation trees** and declares
  them normative for the conformance check, with the Python above them illustrative — a
  parser's associativity is not part of this document, and asking a second implementer to
  recover trees from source was asking them to reproduce one. 12.2 records that the schema's
  single-token pin is a preview decision that relaxes to a pattern at `/v0` final. **Nothing
  moved that a digest can see.** No field, value, encoding, tag or grammar changed; no
  identifier joined or left the vocabulary; the corpus of section 12.5 is unchanged and
  `fingerprint_algorithm` keeps its value. Every artifact valid before this line is valid
  after it and carries the same digests. What changed is that a second engine can now be
  built from the document, which is the only test of it that matters.
- `v0-preview.1` — section 13 names the one node its self-authentication claim does not reach:
  a `kind: "input"` column, whose canonical bytes a producer builds from section 12.1's rule
  and a consumer cannot recompute from a file carrying neither the values nor the container
  they arrived in. The same paragraph points at section 8.2's bound on `formula`, and section
  12.1 states the collision between the injected bytes' `origin` attribute and the node
  record's `origin` field. No field, value, encoding or grammar moved; what changed is that a
  verifier built from this document no longer fails on a node the document had told it to
  check.
- `v0-preview.1` — `continuation` joins the `origin` vocabulary of section 8, for a column that
  came back through an explicit re-entry holding values the model's own calculations do not
  account for. Section 7.2 states that re-entry: the boundary it emits, the comparison of values
  that decides which columns keep their definitions, and the row order that comparison is read
  in — so a frame reordered or filtered outside arrives whole, deliberately. **No artifact valid
  before this line is invalid after it**: this is a closed vocabulary growing, which section 14
  allows within a stamped `v0`. The break runs the other way, and saying so is what this line is
  for — an artifact carrying the ninth value is refused by the schema as it stood at the line
  above this one, which knows eight, and under section 1's preview policy this log is the whole
  of the warning a consumer pinned there gets. In the same pass section 12's account of what an
  `executable` consumer recomputes gains an explicit bound — every `local_fingerprint` it has
  a tree for — so that paragraph, quoted on its own, no longer reads as an instruction to
  recompute the one node the document says cannot be recomputed. (Section 13's own bound was
  worded differently until the line below brought the two into one phrasing.) No digest
  moved and none could: the node record's `origin` field is no part of any node's canonical
  bytes — the `origin` an injected column's bytes carry is the different thing section 12.1
  names — and the corpus of section 12.5 carries no re-entry, so its table is unchanged and
  `fingerprint_algorithm` keeps its value.
- `v0-preview.1` — `document_digest` defined: an envelope member (section 7) sealing the
  document as a written record, and section 13.1 stating the byte stream it is taken over, what
  a deep verification does with it, the rule that a citing document records it, and the limits
  — tamper-evidence rather than tamper-proofing, the citation web rather than the standalone
  file as what catches a re-seal, and producer signing named as future work and not built. It
  answers the question section 13 already said the identity chain does not: whether this is the
  file the producer wrote, as against whether this is the same calculation. **No artifact valid
  before this line is invalid after it** — the member is not required, so a document written
  without it validates exactly as it did. That is the contrast with `reads_assumptions` above,
  which is required and therefore did make a document written before it invalid; neither line
  moved the identifier, and section 14 says what a consumer holding one document from each side
  of such a line does instead — validate them against the schema rather than read the counter.
  It is taken under the recipe grammar section 12.3 already states rather than under a grammar
  of its own, and it is no part of any canonical byte stream a digest in this format is taken
  over: no node digest moved, no `graph_fingerprint` moved,
  the corpus of section 12.5 is unchanged and `fingerprint_algorithm` keeps its value.
- `v0-preview.1` — two sentences narrowed to what a producer does. Section 7.2's re-entry
  paragraph said a reordered frame comes back with **every** column recorded as arriving
  data; a column a permutation cannot change — a flat loading, a level rate, an all-true
  indicator — compares equal row for row and keeps its definition, which is what the rule
  immediately above it already says, so a conformance test written from the wider sentence
  would have marked a correct producer non-conforming. And section 13's bound on what an
  `executable` consumer recomputes is stated in section 12's words — every `local_fingerprint`
  it has a tree for — rather than as "every one but the injected columns", which licensed
  recomputing the leaves, whose bytes carry no tree either; the injected column is still named
  as the case worth stating. No field, value or encoding changed, no digest moved, and the
  corpus of section 12.5 carries no re-entry, so its table is unchanged.
- `v0-preview.1` — an `assumptions[]` entry that states no name of its own is named after its
  contents instead of carrying `name: null`: the entry's kind and the first eight digits of the
  `fingerprint` written beside it, as in `curve:5c1f0a3d`. That is a label and not an identity
  — the fingerprint remains the identity — and the field's type is unchanged: a null is still
  valid, stored documents carry one, and a consumer must read one. What it buys is the join of
  section 8's `reads_assumptions` to this section, which names entries by name and so could
  reach no schedule and no curve; Annex A.2 records that as the case it closes. Nothing here is
  in a canonical byte stream: the name enters no node's bytes, section 12.4's second section
  lists tables, no node digest and no `graph_fingerprint` moved, the corpus of section 12.5 is
  unchanged and `fingerprint_algorithm` keeps its value.
- `v0-preview.1` — section 13.1 answers the question a producer holding an entry's values
  outside the document raises: those bytes take no `document_digest` of their own, because the
  entry's `fingerprint` already records their identity and section 13 already re-derives it
  from the bytes. One mechanism rather than two, and a payload carrying a second digest would
  weigh more than the value its entry measured. Nothing is added, removed or renamed: no field,
  value or encoding moved, the `omitted` reading of a deep verification is the one section 6.1
  already defines, no digest moved, and the corpus of section 12.5 is unchanged.
- `v0-preview.1` — 11.1.3 states what a `clip` answers when its bounds cross, replacing the
  sentence that declared the case unanswered. The lower bound is tested first, so bounds of
  8 and 2 over `1, 5, 10` give `8, 8, 2`; the rule is the one this document's reference
  engine already kept for a per-policy value, and its own list-shaped path, which had been
  giving `2, 2, 2`, follows it now. Section 14's fourth closing condition wants the core
  vocabulary's semantics stated, and this was the one operation carrying a hole in its own.
  Nothing is added, removed or renamed: no field, value or encoding moved, no digest moved,
  and the corpus of section 12.5 carries no bound and is unchanged.
- `v0-preview.1` — sixteen identifiers added to the vocabulary of section 11.1, with their
  signatures in 11.1.11 and their semantics in 11.1.12 and 11.1.13: the nine plain maths
  `abs`, `sign`, `sqrt`, `cbrt`, `exp`, `log`, `log10`, `log1p` and `round_sig_figs`, and the
  seven of the missing-value family `fill_null`, `is_null`, `is_not_null`, `is_nan`,
  `is_not_nan`, `is_finite` and `is_infinite`. Every one of them was an engine fragment for
  want of an entry here, and a node is only as portable as the least portable thing in its
  tree, so a force of mortality written as a logarithm took every reserve downstream of it
  with it. Two rules land beside the entries because neither could be left to a reader's
  assumption: a transcendental answer is held to a stated relative tolerance rather than to a
  bitwise contract no implementation can keep, and the two negated tests are their own
  identifiers rather than the affirmatives under `not_`. The vocabulary grows additively,
  which section 14 allows within a stamped version; no field, value or encoding moved, no
  existing identifier changed, and the corpus of section 12.5 reaches none of the sixteen and
  is unchanged.

- `v0-preview.2` — **the node record's six axes collapse to three.** `source` and `origin`
  merge into `provenance`, keeping both vocabularies whole: the recording doors — `join`,
  `rename`, `batch`, `assignment`, `projection`, `date`, `rollforward`, `continuation` —
  stand beside the arrival places `model_points`, `assumptions` and `injected`, and every
  node has exactly one answer to where its definition came from. `value_kind` is removed:
  it was a restatement of `dtype` on every record ever produced, and section 10 now states
  the rule where a reader looking up the type vocabulary meets it — with the clause a
  reader needs beside it, that a selection may also arrive as a numeric 0/1 mask the type
  vocabulary cannot tell from a quantity, which is what every bare comparison in the
  reference producer writes. `engines` and `tier` gain the consistency rules they always had
  in practice — naming an engine says something in the tree reaches into one, which
  contradicts `core` and contradicts a null tier and stops there; a positive engine-free
  claim and an engine-native claim are contradictories; a node with nothing to execute names
  no engines — with the `executable` profile requiring the list on a `core` or
  `engine_native` node, because that is the profile whose file holds the operation tree the
  list is a walk of and on those two tiers the walk is exhaustive over it, and requiring it
  of an `opaque` node only where that walk reaches an engine, because an opaque node's
  silence is a leaf nobody could classify and not a fact about engines. The `audit` profile
  leaves the field optional throughout, exactly as section 8.3 intends. **A node whose tree
  reaches both an engine fragment and an identifier nothing has classified is `opaque` and
  names its engine**, because section 11.2's ladder takes the weakest tier in the tree: the
  rules narrow what a record may claim without making that record unwritable, and an artifact
  valid under the old shape in that respect stays valid.
  The old shape admitted 252 combinations of `kind`, `source` and `origin`; ten occurred.
  The new shape admits thirteen `(kind, provenance)` pairs across the five kinds anything
  emits, and fifteen across all seven: `state_graph` and `nested_valuation` are constrained
  to null now rather than left open until a producer emits one, which is what both
  hand-built examples already carry, and a later producer widens the constraint additively.
  **A document written before this line is refused after it, and the reverse**, which is why
  the identifier moves. No digest moved: none of the three fields was ever inside a node's
  canonical bytes. Section 12.1's stated collision between an injected column's `origin`
  attribute and the node record's `origin` field is closed by the rename rather than
  restated.

- `v0-preview.2` — **the edge carries the relationship; the narrowing travels beside it.**
  An edge is `source`, `target` and `relationship` — `DIRECT` or `INDIRECT` — which is the
  distinction section 9 exists for: what a reserve depends on and what selected the row are
  different questions. `subtype` moves whole into the `gaspatchio_column_transformation`
  facet on the reading node, carrying OpenLineage's own `transformations` array with its
  own `type` and `subtype` keys and its own enum spellings, unaltered. The facet is
  announced in `facets_used` and never in `facets_required`: a consumer that has never met
  it reads the same graph and loses only a narrowing. Promotion back to the core edge stays
  additive. No digest moved — an edge enters none.

- `v0-preview.2` — **the `audit` profile states a compiled rollforward's working.** A
  `rollforward` node carries `increments`: one entry per movement, in the order the machine
  applies them, with the ordinal, the label the model's author gave it, the operation, the
  running balance it lands on, and whether its amount depends on that balance. It is present
  wherever it can be derived and absent otherwise, exactly as `states` is — a producer that
  cannot reach the compiled artefact, or that meets an operation the vocabulary does not
  name, or whose labels collide within the one array, or that meets a label written as the
  empty string, omits the field rather than writing something it cannot stand behind.
  **`operation` is a closed enum of ten names, listed in
  section 16 by this line** — `Add`, `Subtract`, `Charge`, `Grow`, `GrowCapped`,
  `DeductNAR`, `Ratchet`, `Floor`, `Round`, `Apply` — and publishing the framework's own
  operation identifiers on the wire is a deliberate coupling: renaming one becomes a format
  change with a line here, which is what a second name for one operation would cost anyway
  and without a translation table free to drift. **No label may appear twice within one
  `increments` array**, because the summary is what a reader cites and a matching hint is
  what a change report falls back on; nothing is required of a compilation that produces no
  summary, so no model that compiles today stops compiling. An operation with no label
  carries null, which is the claim it is everywhere else in section 8.
  `reads_running_balance` is a fact about the operation for seven of the ten — those whose
  shape puts the balance in the amount however the operand is written — and for `Add`,
  `Subtract` and `Apply`, whose expression *is* the amount, it is read off that expression,
  which the compiler has already reduced to a single column reference and classified as
  either a declared state at a declared point or an input column: it is **true where that
  classification reads the same state the increment's `target` names, at either point**.
  The reference producer has since stopped writing an `Apply` at all (the `v0-preview.3`
  entry on it, below); a reader still reads one this way.
  Where a producer cannot classify one it writes null rather than guessing, with the meaning
  null carries throughout section 8. An
  increment's identity is its position in its compilation — the compilation's `fingerprint`
  and the increment's ordinal — and no per-increment digest is minted, for the reason
  section 12.1 gives for not restating the machine inside the node's bytes. **The
  non-promise is explicit: this is the movements and their order and nothing else.** The
  amounts, the expressions, the rounding, the stopping conditions, the schedule and the
  states' opening values are the machine, they travel in the `gaspatchio_rollforward_ir`
  facet, and that facet is unstable and will change without a compatibility path while this
  preview is open. No digest moved: the compiled fingerprint already covers every label and
  the order, which is why this record can promise to be stable.

- `v0-preview.2` — **`sum`, `mean`, `min` and `max` join the vocabulary**: the reduction of
  one policy's per-period column to one number, which is what a present value is. Section
  11.1.9 named this gap and said an operation whose answer has a different shape from its
  operand had no way to state that; 11.1.12 states it, per entry, where the fact belongs,
  and 11.1.13 to 11.1.15 do the same for the three siblings. One operand, no attributes, no
  `reverse` — a fold over a whole axis reaches the same number either way. The fold is along
  the periods and along nothing else: an engine method of the same name applied to a
  per-policy column folds down the rows of the model-point file, a different calculation
  whose answer depends on the order those rows stand in, and a producer must not write this
  identifier for it. **Digests move wherever a producer's record of such a line genuinely
  changes** — an engine fragment becomes a `call` — and through every node downstream of one.
  `fingerprint_algorithm` did not move for this: a `call` has been hashable under section
  12.1 since it was written. Only `sum` moves a digest in any shipped model: the three
  siblings occur zero times in the package, the tutorials and the tests, and they ride now
  so that a later addition does not move the same digests a second time. Section 11's count
  of the operations in the unnamed domain moves from fourteen to eighteen. The reductions that
  did not ride are named and so is what each waits for: `std` waits on a `ddof` the vocabulary
  never stated, which an identifier carrying a default would hide inside a name, and `median`
  on a convention for an even period count, which is a question no denominator of its own
  asks; `first` and `last` are `projection.at_period` at a boundary and a second spelling is
  what 11.1.11's rules exist to prevent; `len` is a length and not a fold of values.

- `v0-preview.2` — **a date is a scalar in the tree grammar, and the refusal is withdrawn
  for a literal on its own.** Tag `0x16`, a zigzag varint of days since 1970-01-01 on the
  proleptic Gregorian calendar — the same number and the same layout the content grammar of
  section 12.3 has always written behind that byte, so a reader holding both grammars still
  meets one encoding per type. Section 12.1 and section 12.3 disagreed about whether sharing
  that block made a tag mean two things or one; this line settles it in section 12.3's
  favour, which is the section that made the block shared. On
  the wire a date literal is `{"op": "lit", "date": "..."}` under its own key, and exactly one
  of `value`, `values` and `date` is present: JSON has a number token and no date token, so
  the distinction that whole numbers and decimals draw with a token is drawn here with a key.
  **The withdrawal is for a literal and not for a member of one.** `values` still holds
  flags, whole numbers, decimals and text, and a date under it is refused: a date written
  there is text, encodes as `0x14` and its eleven bytes, and reaches a well-formed digest
  matching nothing — the failure this section warns about for a scalar, one level down. So a
  membership test against a set of dates stays an engine fragment and the node says so, as
  every calculation this document cannot yet spell does. `0x17` is likewise not minted for
  the tree — nothing writes a datetime literal, and an untested token in a grammar whose
  value is agreement is worse than a stated absence. Both forms land additively, with a line
  here, the day a producer holds one.
  **`fingerprint_algorithm` moves to `gspv0-preview-2`, and it is this line that moves it.**
  Every digest in every artifact written under `gspv0-preview-1` is a digest under a different
  grammar; section 12.2's rule applies without exception, and two artifacts carrying different
  tokens must not be compared. The corpus of section 12.5 is regenerated and reprinted, and it
  grows a date column and a date literal so that the new tag is exercised by the artifact whose
  whole job is to let a second implementation prove agreement.

- `v0-preview.2` — **the seven operation-tree branches close.** Each carries
  `unevaluatedProperties: false`, so a node claiming to be one kind and carrying another
  kind's fields is refused rather than validated and then hashed as the kind it claims. The
  case this closes was live: a `call` relabelled `state`, keeping its arguments and its
  configuration, validated clean and hashed as a state reference — a document with one node's
  whole configuration struck out, carrying a digest that no longer covered what it dropped.
  **The envelope's stated openness is untouched**: the top level and the node record still
  admit keys this document does not define, and section 6's round-trip promise for an unknown
  facet rests on that and is unchanged. No conforming document was refused by the closure: it
  was checked against every operation tree in every artifact the reference implementation
  produces. No digest moved.

- `v0-preview.2` — **`document_digest` becomes required on emission.** The member itself was
  defined under `v0-preview.1`, where section 7 states it, section 13.1 states the byte stream
  it is taken over and the limits, and section 14.1 carries its line; what changes here is that
  a document written without one stops validating. **That is a break in validity and this line
  is where a consumer is told of it** — which is what this log is for under section 1's preview
  policy, rather than a claim that required-ness by itself moved the counter: the
  `reads_assumptions` line above added a required field inside `v0-preview.1` with the counter
  unmoved, and section 14 says what a reader does about two documents on either side of such a
  line. The identifier moves at this release for the byte grammar of section 12.1 and for the
  shape changes landing beside it, and this member becomes required in the same document.
  It seals a written record rather than an identity — the digest field excluded,
  `created_at` included — which is the question section 8.2's bound left open and the
  fingerprint chain deliberately does not answer. Deep validation recomputes it and
  names the mismatch. Every citation of one document by another carries the cited document's
  digest beside its identity, which is what makes an edit-and-reseal detectable at all. The
  limits are stated in section 13.1: this is tamper-evidence and not tamper-proofing, a
  determined re-sealer beats the standalone file and is caught only by the citation web, and
  producer signing is future work and is not built. No node digest moved.

- `v0-preview.2` — **`list.get` and `to_integer` join the vocabulary**, with their signatures
  in 11.1.11 and their semantics in 11.1.22 and 11.1.23. `list.get` selects an absolute,
  zero-based position from each policy's own list, admits negative positions from the end and
  refuses a missing or out-of-bounds position; it is distinct from
  `projection.at_period`, which shifts a whole timeline by a relative offset.
  `to_integer` preserves a scalar or list shape while converting only finite, integral,
  in-range signed numeric values to `i64`, and refuses nulls and every lossy form. Both are
  ordinary calls using the existing argument run and no attributes. The vocabulary grows
  additively, which section 14 allows within a stamped version: no field, scalar type, tag or
  byte encoding changes, and no existing identifier changes meaning. A `call` has been
  hashable under section 12.1 since that grammar was written, so `fingerprint_algorithm`
  remains `gspv0-preview-2` and the schema is unchanged. The corpus of section 12.5 reaches
  neither identifier and is preserved byte for byte; no regeneration or reprinting is
  warranted. The unnamed domain gains `to_integer`, moving its non-operator count from
  thirty-four to thirty-five, and the named domains gain `list`.

- `v0-preview.2` — value semantics were added for bounded exact `lookup` and for
  the bounded portable BOP/EOP result of `rollforward.state`. The existing call
  identifiers, signatures, facet body, typed attributes and operation-tree
  grammar are unchanged. No artifact fingerprint and no §12.5 corpus digest
  changes solely because of this prose addition. The bare `rollforward` call
  remains bookkeeping identity; `rollforward.increment` and
  `rollforward.struct` remain structurally recorded without portable value
  semantics.

- `v0-preview.2` — value semantics were added for the projection family, and for the shape
  algebra every other entry rests on. 11.1.18 states the policy and period axes: one row is
  one policy, position `t` of a list column is that policy's period `t`, a scalar broadcasts
  along one policy's periods and never across policies, two lists match in length within a
  policy, and per-policy period counts may differ — a backend needing one rectangular count
  may refuse such an invocation as its own limitation, but not report the artifact invalid
  for that reason. It also states the stored Float64 predicate: a `when_then` condition that
  directly references an `f64` or `list[f64]` column is exactly `0.0` or `1.0` at that
  boundary, and any other numeric value is a refusal rather than truthiness. 11.1.19 states
  `projection.cumulative_survival` where `from_survival` is false, with `start_at` as the
  opening-boundary value rather than an extra factor in every later product, and the three
  period shifts. 11.1.20 states the `projection.accumulate` recurrence and
  `projection.remaining_sum`. 11.1.21 states `projection.prospective_value` under
  `discount_kind="rate"`, both timings written out. Each names the forms it leaves outside
  itself, so a consumer implementing only the stated one knows where to refuse. These four
  landed out of the same commit as the two lines above and were left out of this log; this
  is the line they were owed, and it sits where they landed rather than at the end. Call
  identifiers, signatures, attributes and the operation-tree grammar are unchanged, no field
  or scalar tag is added, `fingerprint_algorithm` remains `gspv0-preview-2`, the schema
  identifier does not move, and the corpus of section 12.5 is preserved byte for byte.

- `v0-preview.2` — **a table payload's column grammar widens from `f64` and `str` to `f64`,
  `i64` or `str`.** Every numeric key of a processed assumption table used to be cast to
  Float64 before it was hashed, published or looked up. A key column whose values do not all
  fall inside the range a double carries every integer of exactly — `[-2^53, 2^53]` — now
  keeps its source type instead, so `i64` joins `f64` and `str` on the wire and a key past
  that range publishes with every digit. Section 15 states the resulting grammar; this is the
  line saying it moved and when. **A table with such a key stamps differently, and that is
  the one movement to expect.** The `table_fingerprint` a `lookup` node carries is the
  content digest of the *processed* frame under section 12.3, and that grammar writes a tag
  for the type each column carries, so a key column that stops being cast tags `i64` where it
  tagged `f64` and carries its exact values where it carried rounded ones. Nothing moves for
  a table whose keys all fit: those are still cast and stamp exactly as before. No stamp
  moves with the same values behind it — every one that moves does so because the keys it is
  taken over stopped being folded into their neighbours. The neutral type vocabulary of
  section 10 is unchanged and gains no name, no tag, field or byte encoding of section 12.1
  changes, `fingerprint_algorithm` remains `gspv0-preview-2`, and the schema identifier does
  not move. The change rode in under a commit titled `fix(assumptions)` that named neither
  the grammar nor the stamp, and section 15's sentence followed three commits later; this is
  the line both were owed.

- `v0-preview.2` — bounded value clauses added for the base, finance, curve,
  date/Excel and schedule families, plus tracked `rollforward.increment`:
  93 stated value contracts, one structural identity and one unresolved raw
  Struct output. Sections 14.2 and 15 consolidate the implemented change
  report and assumption contracts. Section 11.3 adds a separately versioned
  synthetic invocation kit and an independent current-token identity reader.
  Newly emitted default `projection.broadcast_to_periods` trees explicitly
  record the `month` operand, using the existing two-operand call form;
  historical one-operand trees remain readable but outside that portable
  subset. Their different dependency trees correctly have different digests.
  No tag, byte grammar or schema/fingerprint token changes. The final §14
  gate, historical-retention work and all-null/Struct type decisions remain
  open; this is candidate evidence, not a final stamp.

- `v0-preview.2` — raw Struct output explicitly excluded under §16.3; all-null
  inputs require a declared supported dtype under §10. The operation vocabulary
  remains 95 identifiers: 93 bounded value contracts, one structural identity
  and one excluded output. The invocation kit gains artifact-type refusal and
  reviewed boundary evidence. The calendar clause distinguishes successive
  shared-grid steps from original-start inception/per-policy offsets, matching
  existing producer behavior. The native list-power kernel retains its declared
  Float64 element type on zero-policy output. No tree grammar, neutral type,
  schema token or fingerprint token changes. Retention, viewer evidence and the
  final release conditions remain separate.

- `v0-preview.2` — **a superseded definition may carry its own values, and must say so.**
  The node record gains the optional boolean `retained`, meaningful only where
  `in_final_schema` is false and stating that the producer held that definition's own output
  to the export and read `value_sample` and `trace` off it rather than off the column the
  frame ended up holding. Section 8 states both halves: without the declaration, enrichment on
  a superseded definition stays refused, for the reason it always was — the value would be the
  number that replaced it, the wrong number against the right formula — and `retained: true`
  on a node whose `in_final_schema` is true is refused too, since the definition a column holds
  has nothing to retain. `in_final_schema` is unchanged in meaning, and so is the type
  permission of section 10: a retained definition states the `dtype` and `shape` the producer
  read, and a definition nothing retained keeps `unknown`. **This is a field growing and a
  refusal narrowing, both of which section 14 allows within a stamped version**: the field is
  optional, so every artifact valid before this line is valid after it, and the documents the
  relaxation newly admits are documents no producer could previously write. No digest moved and
  none could — enrichment is no part of any node's canonical bytes (section 12.1) — so
  `fingerprint_algorithm` remains `gspv0-preview-2` and the schema identifier does not move.
  The corpus of section 12.5 carries no values on any node and is preserved byte for byte; its
  own `net_cashflow@1` is the superseded definition a producer exporting that model with values
  now retains, and every digest it publishes is the same under retention on, retention off, and
  the valueless export the file itself is.

- `v0-preview.2` — **an integer width wider than `i64` is judged on its values.** Section 10
  states it beside the collapse it qualifies: a producer holding a column's values writes
  `i64` where every one of them is inside the signed 64-bit range, and refuses naming the
  value where one is not; a producer with no values in reach refuses the width, as it always
  did. **This is a refusal narrowing, which section 14 allows within a stamped version**, and
  the documents it newly admits are documents no producer could previously write — a column
  under an unsigned or 128-bit width stopped the export, so no artifact carrying one exists to
  be read differently. No field, tag, value or byte encoding changes: such a column's leaf is
  written with the `i64` its own `.cast(pl.Int64)` would have written, which is the same
  canonical bytes under section 12.1 and therefore the same digest a reader would have got by
  casting in the model. `fingerprint_algorithm` remains `gspv0-preview-2`, the schema
  identifier does not move, and the corpus of section 12.5 carries no integer wider than
  `i64`, so its table is unchanged.
- `v0-preview.2` — **a running fold answers null from the first period it does not have
  onward.** Sections 11.1.9 and 11.1.19 state it for `cum_sum`, `cum_prod` and
  `projection.cumulative_survival`: a null period makes its own position null and every later
  position in the direction the fold runs, so under `reverse` the nulls run toward period
  zero. **This changes a value a conformant engine already answers**, and is therefore a
  stronger disclosure than the refusal narrowings above: `cum_sum([1.0, null, 3.0, 4.0])`
  answered `[1.0, null, 4.0, 8.0]` before this line and answers `[1.0, null, null, null]`
  after it, reversed it answered `[8.0, null, 7.0, 4.0]` and answers `[null, null, 7.0, 4.0]`,
  and a survival built on a decrement sequence with a null period no longer folds past it. A
  consumer that had implemented the unstated behaviour is wrong against the clause from this
  line, and no shim carries it across. The two closures stated beside them — an all-null run
  sums to nought, as an empty run does, and a null outer list answers null for all six of
  11.1.9's and 11.1.14's identifiers — describe answers both published engines already gave.
  No field, tag, attribute, value or byte encoding moves, no signature changes, and
  `fingerprint_algorithm` remains `gspv0-preview-2`: the identifiers, their operands and their
  attributes are what they were, and only the answer at a null period is different. The corpus
  of section 12.5 writes none of these three identifiers, so its table and its
  `graph_fingerprint` are unchanged; the published vectors gain the cases these clauses now
  state and no existing expected value moves. The
  four reductions of §§11.1.14–11.1.17 keep the rule that a null period is absent to the fold,
  and `projection.remaining_sum` and `projection.prospective_value` keep their stated non-null
  domains, so a total taken over a run this rule has nulled still folds past the null tail.
- `v0-preview.2` — **a total over a period it does not have is null**, which is the line above
  this one reaching the last place its rule was not applied. Sections 11.1.14 to 11.1.17 state
  it for `sum`, `mean`, `min` and `max`; 11.1.20 and 11.1.21 state it for
  `projection.remaining_sum` and `projection.prospective_value`, which fold from the last
  period and therefore null from the hole back toward period zero. 11.1.9's sentence that a
  reduction "can say the period was not there" comes out, because nothing in one number can.
  **This changes values a conformant engine already answers**, as that line did:
  `[10.0, null, 30.0, 40.0]` answered `sum` 80.0, `mean` 26.666666666666668, `min` 10.0 and
  `max` 40.0 and now answers null through all four; a run of nothing but nulls answered `sum`
  0.0 and answers null, so `sum` no longer parts company with its siblings and the sentence
  qualifying that nought for a typed run goes with it; `projection.remaining_sum` answered
  `[80.0, 70.0, null, 40.0]` over that run and answers `[null, null, 70.0, 40.0]`, and
  `projection.prospective_value` nulls the same two positions under either timing. The empty
  run still sums to nought, and a null outer list still answers null for all four. **A nought
  is now declared rather than inferred**: a modeller who means that a missing period is a zero
  writes `fill_null` before the total, 11.1.14 says so once for the family, and the filling is
  a node carrying its own digest where a reviewer can read it. `projection.accumulate` is not
  covered — a null step stays outside 11.1.20's stated form, and 11.1.20 now says so with the
  other exclusions rather than leaving it to the older non-null domain. Seven published
  expected values change with the clauses: `null-sum-period`, `null-mean-period`,
  `null-min-period`, `null-max-period` and `null-sum-all-null`, and with them
  `null-min-is-not-a-nought` and `null-max-is-not-a-nought`, the two runs published to
  separate a null read as absent from a null read as nought — a distinction this rule removes,
  since neither reading survives it. The vectors gain cases for the two reverse folds. A
  consumer that had implemented the published answers is wrong against the clauses from this
  line, and no shim carries it across. No field, tag, attribute or byte encoding moves, no
  signature changes, and `fingerprint_algorithm` remains `gspv0-preview-2`: the identifiers,
  their operands and their attributes are what they were, and only the answer over a null
  period is different. The corpus of section 12.5 writes none of these six identifiers, so its
  table and its `graph_fingerprint` are unchanged.
- `v0-preview.2` — **`to_float`, `to_text` and `to_list` join the vocabulary**, with their
  signatures in 11.1.11 and their semantics in 11.1.38, 11.1.39 and 11.1.40. Each is one pair
  of meanings rather than a cast taking a type: `to_float` widens an integer to a double and
  refuses one outside `[-2^53, 2^53]`, where two whole numbers would share a double;
  `to_text` writes a value out losing nothing, which is the exact numeric name section 10
  does not have for an integer past 2^63; `to_list` gives up an array's fixed width and keeps
  its elements. With `to_integer` and `str.to_date`, every type section 10 names now has a
  declared door, and no generic `cast` is added. 11.1.23 widens with them: an integer stored
  in a width wider than `i64` is an integer for that call and is judged on its value — the
  rule section 10 already states for an integer width at export — where its previous sentence
  refused an unsigned engine value on its type. That is a **widening of an accepted domain**,
  so an input a conformant consumer refused before this line is one it must now convert or
  refuse by value; nothing that converted before converts differently. All three are ordinary
  calls using the existing argument run and no attributes. The vocabulary grows additively,
  which section 14 allows within a stamped version: no field, scalar type, tag or byte
  encoding changes, and no existing identifier changes meaning. A `call` has been hashable
  under section 12.1 since that grammar was written, so `fingerprint_algorithm` remains
  `gspv0-preview-2` and the artifact schema is unchanged. The corpus of section 12.5 reaches
  none of the three and is preserved byte for byte. The unnamed domain gains all three,
  moving its non-operator count from thirty-five to thirty-eight. The published vector
  envelope `gaspatchio-operation-vectors/v0-preview.1` gains five names on **inputs only** —
  `u64`, `i128`, `u128`, `categorical` and `array[<element>,<n>]` — because three of these
  clauses exist to convert a column out of a storage type section 10 cannot name, and a case
  could not otherwise state one. Its `$id` does not move, a result is still named from
  section 10's closed vocabulary, and every bundle published before this line is unchanged
  byte for byte.
- `v0-preview.2` — **an input leaf's `dtype` no longer goes `unknown` on a renamed arrival.**
  Section 8.1 names an input leaf for the field the data arrived under rather than for what
  the model renamed it to, and a producer reading its type off the finished frame found no
  such column and wrote `unknown` — for a type it had met at the door, which section 10
  forbids. A producer keeps the schema its data arrived with, and section 10 now
  states that case and the one absence it leaves: the type is stated, the `value_sample`
  stays null because the values are gone from the finished frame, and `unknown` survives
  only where the arrival type is one this vocabulary has no name for. `shape` follows the
  type under the rule it already shared. **No field, tag or byte grammar moves**, so
  `fingerprint_algorithm` keeps its value and the artifact schema is unchanged. A document
  carrying such a leaf does change its digests — a leaf's canonical bytes are its tag, its
  name and its type (section 12.1), so a leaf hashed over `unknown` and one hashed over
  `f64` are different bytes — and that is the correction rather than a side effect of it: the
  renamed arrival's leaf is now byte-identical to the one a model that kept the vendor name
  writes. **No published digest can move, because no published document carries such a
  leaf**: the corpus of section 12.5 renames nothing and drops nothing, and its table is
  unchanged. No artifact valid before this line is invalid after it — `unknown` is still a
  member section 10 permits on a node outside the final schema, and an artifact written
  before it carrying one on a renamed arrival is still a valid document, saying less about
  that field than a producer would say today.
- `v0-preview.2` — **`projection.accumulate` joins the rule the rest of its family already
  has**: a null multiplier or addend at position `t` makes `s[t]` and every later position
  null, by 11.1.9's rule for a forward fold, and a null `initial` answers a run of nulls.
  11.1.20 states it, where that entry used to place a null step outside its stated form
  because the recurrence was the one member of the family this document could not say an
  answer for. It is the last member of the family to take the rule, so the family is one rule
  throughout. **This states an answer where none was stated**, rather than changing a
  published one: no clause said what a null step gave, so a consumer implementing only the
  stated form had nothing here to implement, and 11.1.20's exclusion list keeps non-finite
  operands and a null outer list to the recurrence outside the entry exactly as it did.
  A modeller who means nought writes `fill_null` before the recurrence, by 11.1.14's
  sentence for the family. No field, tag, attribute or byte encoding moves, no signature
  changes, and `fingerprint_algorithm` remains `gspv0-preview-2`: the identifier, its
  operands and its attributes are what they were, and only the answer at a null step is
  stated. **No published expected value moves**: `nulls.json` carried no
  `projection.accumulate` case before this line, and the recurrence's cases elsewhere carry
  no null. The bundle gains five cases for the rule, every expected value hand-derived from
  this clause. The corpus of section 12.5 writes the identifier nowhere, so its table and its
  `graph_fingerprint` are unchanged.
- `v0-preview.2` — **a column that materialises a compilation's running balance says which
  balance**, in the optional `extracts` of section 8, with section 16 stating the field and
  the forward query rule that rests on it: the two forward questions asked of such a column
  are asked of its running state as well, because an edge walk from the column alone stops at
  the column — what the compilation reads is the state. Until this line the only thing tying
  the two together was the extraction's own formula text, which section 8.2 declares free-form
  and no consumer may parse. The field is additive and optional, so no artifact valid before
  this line is invalid after it, and one written without it says less about such a column than
  a producer would say today. **No digest moves**: a running state's canonical bytes are taken
  over its reference and a column's over its operation tree (section 12.1), and neither reads
  a node's fields, so `fingerprint_algorithm` remains `gspv0-preview-2`. No published digest
  could have moved in any case — the corpus of section 12.5 carries no state node, no
  compilation and no column that extracts one — and its table and its `graph_fingerprint` are
  unchanged. Annex A.2 gains nothing and needs nothing: the column's own account is what
  answers the question, and no reading is inferred from a name.
- `v0-preview.2` — **a join's right side travels in the artifact.** Section 11.1.2 used to put
  it out of band by design: the node carried `on`, `how` and `right_fingerprint`, and the table
  the columns arrived from was somewhere else. A fresh consumer measured against level 4 and
  level 5 lowered **3 of 114 nodes** and **3 of 111** from the file alone — twenty-three columns
  arrive by join in each model, and everything else is one of those or downstream of one — and
  it reached the rest only by being handed the columns from a reference. The fingerprint answers
  *which version?* and cannot answer *which table?*: the one file in each model's own assumptions
  directory with the right shape hashed differently, so the frame joined was not the file on
  disk. Section 15 gains a fourth kind for it, `join`, named after its contents like a schedule
  and a curve, carrying `columns` and `rows` and **no `dimensions` and no `value`** — a join
  declares no key and answer roles, so section 15's role-consistency clause does not reach this
  kind and the schema refuses an entry of it that states either. The inline budget, section 6.1's
  `omitted` pair and the sidecar are the table's, unchanged. A right side handed over lazily
  still records nothing, and 11.1.2's honest sentence about it stands. Section 13 says the payload
  re-hashes under the content grammar over the columns and rows as carried. **No digest moved.**
  A payload is no part of any node's canonical bytes (section 12.1) and `graph_fingerprint` folds
  the content hashes of assumption *tables* only, so on both tutorial models every node
  fingerprint and the graph fingerprint are byte for byte what they were, and so is every node's
  `reads_assumptions` — a joined node's stays empty, because that field names what a node's own
  formula read and an arriving column's formula read nothing. The corpus of section 12.5 carries
  no join, so its table and its `graph_fingerprint` are unchanged, and `fingerprint_algorithm`
  remains `gspv0-preview-2`. What does move is `document_digest`, on any model with a join in it,
  because the file genuinely gained bytes: two entries and about 4.9 KB on a 1.7 MB artifact,
  against 302 KB of mortality table already inlined in the same file. No artifact valid before
  this line is invalid after it — this is a closed vocabulary growing, which section 14 allows
  within a stamped `v0`, and an artifact written before it says less about a joined column than a
  producer would say today. Annex A.2's fourth case half closes with it: the directory now names
  the table an arriving column came from, and the per-node field still does not, so the join from
  that figure to its base runs through the node's own `right_fingerprint`.
- `v0-preview.2` — **a lookup's answer-cell condition is judged at the cells a query
  reaches, not over the table.** Section 11.1.24 stated the bounded portable domain as
  having a "present, finite `f64` answer column", read over the whole table, so a single
  blank cell anywhere put the basis outside the subset and a consumer claiming only that
  subset had to refuse it. A shipped select basis carries **164 blanks in 47,112 cells** —
  the ultimate block at the age and duration pairs no life can occupy — and **0 of 83,000
  gathered key tuples reach one**, measured across both tutorial models by a consumer written
  fresh from section 11.1 on 2026-09-17. A null or non-finite answer cell
  **at a reached key is now a miss** and `on_missing`
  decides it, exactly as for a key matching no row; the other members of the bounded domain
  — key types and families, the closed `[-2^53, 2^53]` interval, duplicate key tuples, the
  empty table — stay table-wide as written, and a table's own **key** cells with them.
  Section 15's role sentence says the same thing about a payload, and section 12.3 says where
  a blank cell's absent marker sits. **This widens what a conforming consumer accepts**: no
  artifact valid before this line is invalid after it, and a basis a consumer had to refuse
  before it may now be read. **No digest moves.** The content grammar already encoded a
  blank cell as absent (`0x01` and one placeholder byte), the producer already answered a
  reached blank by the model's own miss policy, and neither a payload's bytes nor
  `fingerprint_algorithm` changes; it remains `gspv0-preview-2`. The independent reader of
  section 12.5 is brought to the rule and re-derives the shipped basis's
  `sha256:33a5cc9a8152552d1425992bb64a1049e4d06b9b4ee4391af6974bc7ab226616` from that
  payload, which it previously refused to hash at all. Four vectors pin the rule across the
  three miss modes and over a blank no key reaches. Decided 2026-09-18.
- `v0-preview.2` — **a null query key is a miss, not a domain violation.** Section 11.1.24
  put a null key outside the bounded domain, and section 11.1.28 says a conditional is not
  an escape from an invalid lookup, so a model reading a product-parameter key that exists
  only for the rows that use it refused on the specification's own words — and took the
  model's bottom line with it. Measured over the shipped level-4 model points
  (`tutorial/level-4-lifelib/base/`): of **10,000 policies, 4,980 carry a blank
  surrender-charge identifier, 4,980 have the condition false, the two sets are identical,
  and 0 policies carry a blank where the condition is on** — the null is the condition's
  complement by construction of the product table. The same measurement raised it.
  `on_missing` now decides a null key the same three ways: refused by name under `"raise"`,
  the canonical NaN under `"nan"`, the finite decimal under a fill; a null key never selects
  a row, and a lowering selects between branches rather than blending them, so a discarded
  NaN cannot leak. **Section 11.1.28 is left exactly as written and keeps its force** — a key
  of the wrong family, a key outside the closed interval, an ambiguous table and a checked
  conversion that cannot hold all still refuse behind a false condition; what has gone is the
  refusal there was to suppress, because the branch is now a valid expression under the
  claimed domain and the node's own miss policy says what a miss means. **This widens what a
  conforming consumer accepts**: no artifact valid before this line is invalid after it, and
  an artifact refused before it may now be read. **No digest moves** — the identifier, its
  operands and its attributes are what they were, `fingerprint_algorithm` remains
  `gspv0-preview-2`, and the producer already behaved this way. Three vectors pin a
  conditional lookup whose key is null exactly where its condition is false, one per miss
  mode, with the downstream product shown to be `0.0` rather than NaN. Decided 2026-09-18.
- `v0-preview.2` — **sections 11.1.11 and 11.1.24 say where a lookup's operand order is read
  from.** Both said the operands stand "in that table's own key-column order" and neither
  said where on the record that order is found. An inline payload carries two candidates and
  only one is an order: **the key-column order is the payload's `columns` order with the
  `value` column removed; `dimensions` is a set and is not an operand order.** A fresh
  consumer reading `dimensions` — alphabetical in every shipped table — mis-keys two of
  level 4's four lookups **silently**, because the key families still line up, the gather
  still answers, and the answer is wrong; the operand column names are not the dimension
  names either, so name-matching is not available as a fallback. Only section 15 settled it,
  in two separate clauses about two different fields. The contrast with `mortality.at`, whose
  `dimensions` attribute **is** written in operand order and binds by name, is now stated in
  both places rather than left to be discovered. The same fresh-consumer measurement found it.
  **Nothing on the wire moves**: no field, tag, attribute or byte encoding changes, and this
  states where to read an order that was already the only correct one, so no artifact valid
  before this line is invalid after it and none becomes readable that was not. One of the
  vectors the null-key line above added carries a table whose `dimensions` and `columns`
  disagree, so the
  distinction is now exercised rather than only described.
- `v0-preview.2` — **the model's own source travels in the artifact.** The file named the model
  and stamped it, and every node carried the line its calculation was written on; it carried no
  line of the file. So a consumer could be told which line computed a figure and could not show
  it, and a second reader holding the artifact had the formulas without the code around them.
  Section 7.3 is the new section: a top-level `sources` array, one entry per distinct path any
  node's `source_location` names, ordered by path, each `{path, fingerprint, payload}` with the
  payload either `{"text": …}` or section 6.1's `omitted` object. The path is the string the
  nodes already carry, so following a location arrives; the fingerprint is SHA-256 over the
  file's own bytes, which section 12.3 now names as the third digest an artifact holds and as
  neither of its two grammars; and **the entry for `model.source_path` carries exactly
  `model.source_sha`**, which is what lets a page say the source it shows is the source that
  ran. Section 13 states the reading — encode the text as UTF-8, hash the bytes, reach the
  digest — and section 8's `source_location` row points at the section, since that is where a
  reader meets a location and wonders what to do with it. It is **not** an `assumptions[]`
  entry: section 15's directory is an account of the bases a model *read*, and a model's own
  text is not one of those. Section 6.1 gains a third reason, **`withheld`**, for a producer
  that held the text and was asked not to disclose it — `size` would state a reason that is
  false and a weight nobody measured, and a silence would leave a reader unable to tell a
  decision from an oversight. The guard, the stand-in and the sidecar are a table's, unchanged:
  above the inline budget an entry reads `{"omitted": "size", "bytes": N}`, and a path outside
  the model root or a file the producer could not read reads `unavailable` with a null
  fingerprint. **Carrying the text is the default**; leaving it out is the act the file records.
  **This widens what a file carries and changes what nothing already in it means.** No node
  fingerprint moves and no `graph_fingerprint` moves — a payload is no part of any node's
  canonical bytes (section 12.1), and `graph_fingerprint` folds the content hashes of assumption
  tables only — so `fingerprint_algorithm` remains `gspv0-preview-2`; measured on both tutorial
  models under both profiles, every node fingerprint and each graph fingerprint are byte for
  byte what they were. What does move is `document_digest`, on any model whose source travels,
  because the file genuinely gained those bytes: **39,964 bytes of `model.py` on level 4's
  1.67 MB document and 33,967 on level 5's 1.70 MB, about 2 %**, beside the 264 KB of one
  mortality table already inlined in the same file. **No artifact valid before this line is
  invalid after it**: `sources` is optional in the envelope for exactly that reason, and the
  `omitted` vocabulary is a closed one growing additively, which section 14 allows within a
  stamped `v0`. An artifact written before it says less about where its calculations were
  written than a producer would say today. The corpus of section 12.5 carries a `sources` entry
  whose one payload is `withheld` — its model is a fixture inside a test module and that
  module's text is not what the corpus is an account of — so its table, its node digests and its
  `graph_fingerprint` are unchanged.
- `v0-preview.3` — **the artifact carries a policy axis.** The envelope gains `policies`
  (section 7.4), one entry per policy the artifact carries values for, in the order the producer
  selected them: `enrichment`'s four members and a fifth, `why`, a plain sentence recording the
  row the policy sits at and the id it carries. `value_sample`, `trace` and `branches` are read
  along it, the axis being the outermost container of each. Until this line the file held one
  model point, so *how does this policy differ from that one?* had no answer in the document at
  all, and *which of these is the one I was shown?* had no answer either — a single policy with
  no account of how it was chosen reads as a policy somebody chose, and on the overwhelmingly
  common export nobody did: it is the first row of the file.
  **The schema identifier moves and `fingerprint_algorithm` does not.** No digest input
  changes: a policy is no part of any node's canonical bytes, and `graph_fingerprint` folds node
  digests and assumption content hashes. Measured on level 4 over `model_points_1k.parquet`,
  every one of 128 node fingerprints and the graph fingerprint are byte for byte what they were
  between a one-policy export and a two-policy one, and the token remains `gspv0-preview-2`.
  **A document carrying one policy is byte for byte what it was**, apart from the three strings
  this edition moves: `schema`, the `_producer` each facet carries (which names the edition the
  producer wrote the facet under, and would otherwise have a `v0-preview.2` facet inside a
  `v0-preview.3` document), and a hole's `closes_with`. Each enrichment field on such a document
  is the value itself and never an array of one, which is the rule that makes this additive: a
  consumer written against `v0-preview.2` reads a single-policy document exactly as it always
  did, and reads a multi-policy one as its first policy, `enrichment` being `policies[0]` with
  `why` left off. The only enrichment it cannot read is enrichment no producer could previously
  write. **No artifact valid before this line is invalid after it** in anything it says about a
  calculation; `policies` is required, so as with `reads_assumptions` and `document_digest`
  before it, a document written without the member is refused by the schema, and section 5 keeps
  the earlier rows so a reader meeting one is told which edition it is under.
  **What does move is `document_digest`**, on every document, because every document gains the
  member — `[]` on one carrying no values, which is what an artifact with `enrichment: null`
  now writes and the claim that it states no context rather than an axis it forgot to fill in.
  The corpus of section 12.5 is such a document: its table, its node digests and its
  `graph_fingerprint` are unchanged, and its seal and its `_producer` strings are not.
  **A selection says what was sampled and never what was computed.** A producer does not
  narrow the model run to the policies it carries: a model with a cross-row step would then
  give a policy one value in a narrow export and another in the run that was performed, and
  every value in this format is a quotation of a run that was performed. The narrowing a
  producer was asked for keeps the member it always had, `filter`, now on every entry of the
  axis. The three strings that move with the schema identifier — `schema`, each facet's
  `_producer` and a hole's `closes_with` — move because each names the edition of this
  specification the producer wrote under, and a `v0-preview.2` facet inside a `v0-preview.3`
  document would have a producer claiming an edition it is not writing.
  **Nothing on the axis is chosen for the reader.** This edition defines no automatic selection
  — no inferred ranking column, no cohorts, no anomaly rule — and section 7.4 says why: a rule
  that picks badly is worse than a visibly arbitrary one, because it looks authoritative. The
  evidence is that no rule survives contact with the shipped models: a "last computed column"
  rule lands on a two-valued string on one of them and on a per-period column on another, and a
  sign-anomaly rule flags 20 of 1,000 policies on one output column and 0 of 1,000 on another
  of the same model. The published operation-vector bundles keep the `artifact_schema` they were
  derived against: no operation, signature, attribute or byte encoding changes here, so
  re-stamping them would claim a re-derivation that did not happen. Decided 2026-09-19.
- `v0-preview.3` — **the book's own fold is written, and `aggregation` widens to a name.** The
  member section 7 defined as `"sum" | "mean" | null` when the format was drafted had never been
  written by anything: an artifact carried one policy, and a fold of the book had nowhere to sit.
  Section 7.4's axis gave it a home in the line above, and this is the line that fills it — a
  producer folds the book with the accumulators the model declares and puts the result on that
  axis as its own entry, `policy_id` null, ahead of the policies. A fold partitioned by a column
  is one entry per cut, each stating its cut in `filter`, which is the member this format already
  defines for *the cut the sampled rows had been narrowed by*; **no member is added**, because a
  second way of saying which rows are behind a number is a second thing that can disagree with
  the first. A column no accumulator covers carries null at that entry's position and `trace` is
  null there throughout, there being no row for a walk-through to be of.
  **The vocabulary widens and the schema identifier does not.** `aggregation` becomes a name —
  `sum`, `period_sum`, `mean`, `count`, `min`, `max`, `variance`, `std` — rather than the two
  words, which were chosen before there was an aggregator set to name and would refuse a document
  stating a fold that had genuinely been taken. **No artifact valid before this line is invalid
  after it**: an enum widening to a name refuses nothing it used to accept, and every document
  written before it states `aggregation: null` on every entry, which the widened member still
  reads. The identifier stays at `v0-preview.3` because this is the half of that edition section
  7.4 already described — *"the book's own fold is an entry on this axis"* was written into that
  section by the line above, with the two-word enum the only thing standing between the sentence
  and a producer that could write it — and because the edition is not one any artifact has been
  published under. `fingerprint_algorithm` remains `gspv0-preview-2`: an entry on the axis is no
  part of any node's canonical bytes, and `graph_fingerprint` folds node digests and assumption
  content hashes. What moves is `document_digest`, and only on a document that carries a fold,
  because only such a document gains anything.
  **A fold is a quotation like every other value here.** It is the producer's own aggregation over
  the whole book and never a re-summation of the policies the document happens to carry: those are
  the handful a reader asked for, and their total is nobody's number. Measured on the reference
  producer over a thousand-policy book, the folded `pv_net_cf` and the sum of that column in the
  results file the same run wrote agree to one unit in the last place, and each cut of a
  scenario-grouped fold equals that cut's own sum exactly. Decided 2026-09-19.
- `v0-preview.3` — **a scenario run is a run this format can be an account of.** Three statements,
  none of them a new member and none of them refusing a document that was valid before.
  **A cross-joined scenario axis is `injected`, not `model_points`.** Section 8 defines
  `model_points` as *the policy data the model was run over*, and the file never carried the
  column: the framework put it there, at the line the run's plan was declared or called at, which
  is exactly the arrival `injected` was defined for. Section 8's own table gains the sentence and
  its vocabulary does not — `injected` has been a legal `provenance` on an `input` since the
  format was drafted — so a consumer written against this edition reads such a node without
  changing anything. **The stamp such a node carries is over the identifiers the run declared**,
  not over the column the join produced, and section 12.1 now says so: an axis hashed after the
  cross-join would have a different identity on every book it ran over.
  Left open by name, and not decided here: whether the other columns this framework adds to a
  model's frame — a projection timeline stamped by `projection.set` is the case that was raised —
  want the same word.
  **Every entry of the policy axis on such a frame states its scenario in `filter`**, the policies
  as well as the folds. A row of a cross-joined frame is one policy under one scenario, and the
  member section 7 already defines for *the cut the sampled rows had been narrowed by* is where
  that belongs; where an export was narrowed as well, both cuts are written and joined. Again no
  member is added.
  **And the version block may name the run's own record.** `model.audit`, `{path, fingerprint}` on
  exactly the shape `model_points` and `results` carry, absent rather than null where the run wrote
  none — the reading `results` already has, and for the same reason. A scenario run keeps two
  records of itself: this document, which says how each number was made, and the run's sidecar,
  which says which plan was run and what each scenario folded. Naming one in the other by content
  is what makes them one chain rather than two files in a directory.
  **The schema identifier does not move**, on the test the fold's line above used: nothing here
  refuses a document this edition used to accept. `injected` on an input and the `filter` on an
  entry are values this edition already defines, and `audit` is an added optional member of a block
  every other member of which is already optional to carry — a consumer written against
  `v0-preview.3` reads a document with it exactly as it reads one without, which is section 14's
  additive rule applied where it was written for. `fingerprint_algorithm` remains
  `gspv0-preview-2`: an envelope member is no part of any node's canonical bytes. What moves is
  `document_digest`, and only on a document that carries one of these. Decided 2026-09-19.
- `v0-preview.3` — **every step of a tracked rollforward is a movement, and a structural step is
  identified by a reserved label.** Section 16.2 already returned `after - before` for the
  operation a `rollforward.increment` names; what it did not say is which operations can be
  named, and the answer was only the ones the model's author had labelled. `Floor` and `Round`
  carry no label field — deliberately, since a floor is a constraint on the balance rather than a
  movement anyone booked — so a chain ending in a floor put the floor's own amount off the file,
  in exactly the model class that needs it: the account value that would have gone negative and
  did not. 16.2 now states the synthetic label `{kind}@{ordinal}`, the ordinal the same 1-based
  position section 16's `increments` array already numbers the step at, and reserves `@` in a
  label a producer will accept. With no step untracked, the section states the identity a
  consumer may read off a document without inventing a residual line: **a period's increments sum
  to that period's change in the state, to floating point.**
  **No member is added and the schema identifier does not move**, on the test the two lines above
  used: nothing here refuses a document this edition used to accept. `label` on a
  `rollforward.increment` node is a text attribute this edition already requires, and a document
  written before this line — one whose producer named only labelled steps — is read by a consumer
  written against it exactly as before. Nor does `increments` move: that array is the summary of
  what a compilation applies, its `label` is the *author's* name for a step and stays null on a
  structural one, and the synthetic key is the kernel's name for the movement rather than a second
  label on the summary. `fingerprint_algorithm` remains `gspv0-preview-2`, and no node's canonical
  bytes move: the two structural operations gain no field, so no compiled rollforward's
  `fingerprint`, no node digest and no `graph_fingerprint` is different before and after. What a
  tracked model's document gains is a `rollforward.increment` node where a floor had none, so
  `document_digest` moves on such a document and on no other. The conformance corpus of section
  12.5 carries no tracked structural step, so its table is unchanged. Decided 2026-09-19.
- `v0-preview.3` — **a compiled rollforward's movements travel, and its running state carries
  the balance they move.** The line above put every step of a tracked chain within a consumer's
  reach; this is the artifact carrying what each of them came to, so that the one question a
  rollforward is audited by — *walk me from opening to closing for this period* — is answered by
  the document rather than by re-running the model. One member is added and one value moves.
  **`movements` on a `rollforward` node** is enrichment like `value_sample` beside it, keyed by
  the kernel's own name for the step — the author's label, or the reserved `{kind}@{ordinal}` on
  a structural one — with every step of the chain a key, and each key holding the signed
  per-period amount in the shape `value_sample` takes, the axis inside the member rather than
  around it. **A running state's `shape` states `list`** where it stated `unknown`, because the
  state node now carries that balance per period in its own `value_sample`; its `dtype` does not
  move, since a leaf's type is inside its canonical bytes and naming one would move every digest
  downstream of every compiled rollforward for a reading that changes no calculation. Nothing
  carries an opening balance: section 16 states it as an address — the period before's close,
  with the state's initial value in front of the series and off this profile — so the identity
  section 16.2 gives is stated from period 1, where every term of it is on the file.
  **The schema identifier does not move**, on the test the three lines above used: nothing here
  refuses a document this edition used to accept. `movements` is an added optional member, a
  `shape` of `list` is a value section 10 already defines, and a consumer written against
  `v0-preview.3` reads a document carrying neither exactly as it did. `fingerprint_algorithm`
  remains `gspv0-preview-2` and **no node digest and no `graph_fingerprint` moves on any
  document** — measured on every fixture this repository carries that holds a rollforward, before
  and after. What moves is `document_digest`, and only on a document carrying a compilation. The
  conformance corpus of section 12.5 carries no rollforward at all, so its table is unchanged.
  One refusal is relaxed and one is added, and both are about the same pair of nodes: a running
  state may carry a value while `in_final_schema` is false without declaring `retained`, because
  that rule is about a column the frame no longer holds and a running state was never a column;
  and a document whose `movements` are not exactly the steps its `increments` declare is
  refused, because a member short of one step would let a reader close the identity on a number
  nobody accounted for. Decided 2026-09-19.
- `v0-preview.3` — **the portable executable subset reaches the operations the shipped patterns
  are built from.** Section 16.1 admitted `Add`, `Subtract` and `Charge`, and refused every other
  operation tree by name. This framework's own two teaching rollforwards are `Grow → Charge →
  Floor` and a `Grow` with a cross-state `Ratchet` at the anniversary, so an independent
  implementation reading the format could not replay the models the format is taught with — which
  is the one thing *No vendor lock-in* asks of a published execution subset. 16.1 now admits
  `Grow`, `Floor` and `Ratchet` in the exact forms a compilation writes them: `Grow` on
  `Charge`'s own shape with the sign of the factor reversed; `Floor` with its bound in
  `settings` rather than as an operand, because a lower bound is a constraint on the balance and
  not an amount applied to it; `Ratchet` with three operands — the state it lifts to, the gate,
  the running balance — and no settings. One operand type is added with the gate and with
  nothing else: a `bool` column, scalar or `list[bool]`, which no other operand admits and which
  the gate admits alone, so a mask and a rate cannot change places unnoticed. `GrowCapped`,
  `DeductNAR`, `Round` and `Apply` stay outside and refuse by name, as do a rounded `Grow`, a
  `Floor` without a finite bound, and a `Ratchet` that was never gated.
  **This is a widening of what a conforming reader must execute and not of what a document may
  carry**, which is why the schema identifier does not move on the test the four lines above
  used: no member is added, no value is added to any closed vocabulary, and nothing here refuses
  a document this edition used to accept. The three operations have been legal in `increments`
  and in the `gaspatchio_rollforward_ir` facet since section 16 was drafted — that facet's own
  identifier does not move either, since what it may carry is unchanged — and what changes is
  that a reader meeting one of them now has a stated answer where it previously had a stated
  refusal. `fingerprint_algorithm` remains `gspv0-preview-2`, no node's canonical bytes are
  touched, and no node digest, compiled `fingerprint` or `graph_fingerprint` moves on any
  document — measured across every fixture and golden this repository carries. `document_digest`
  moves only on the conformance vector files this line rewrote. The conformance corpus of
  section 12.5 carries no rollforward at all, so its table is unchanged; the vectors of section
  11.3 gain two replays of the shipped chains and four refusals holding the new boundary.
  Decided 2026-09-20.

- `v0-preview.3` — **an entry's values are the row it names, or the producer refuses.** Section
  7.4 said which policy a document carries values for and left the producer to reach it.
  An external review of 2026-09-20 found what that left open: a producer that reads row *n* of the
  finished frame because it counted row *n* of the model points publishes another policy's
  numbers under the selected policy's name the moment the model sorts, filters or duplicates its
  rows, and the document passes every other reading in this specification. 7.4 now states the
  property — a selected row is found again after the run and never counted to — and the reading
  that catches a producer that did not: where an entry names a policy and the document carries
  the model points' own values at that entry, some value it carries there must be that policy.
  It states the other half of the same order too: **a refusal's named way through is one the
  producer will accept**, which means the cut is made before the selection rather than after it.
  **Nothing on the wire moves.** No member is added — the reference producer's row stamp is a
  column it puts on the book and takes off before the document is written — no value joins any
  closed vocabulary, and the reading above refuses only documents that were already making a
  false statement, so nothing this edition used to accept and that was true is refused now.
  `fingerprint_algorithm` remains `gspv0-preview-2`; no node's canonical bytes are touched and no
  node digest, compiled `fingerprint` or `graph_fingerprint` moves on any fixture or golden —
  measured. A `why` sentence gains a clause naming where the model left the row, on the documents
  where the two differ and on no other. This answers two of that review's findings.

- `v0-preview.3` — **a compilation's movements are the run its balance came from, or it carries
  none.** Section 16 said what `movements` is and left the producer to reach it. The same
  review found what that left open: a producer re-tracks the compiled machine to read
  the amounts, the machine names its operands by column name, and a model that writes over one
  of those columns after pulling its state back out therefore gets a whole waterfall — amounts,
  closing balance and the check line over them — computed against values the machine never saw,
  with every other reading in this specification passing the result. 16 now states the property
  — the amounts are bound to the versions the compilation read, which section 8's `reads`
  already records, one node id per column — and what a producer does when a bound version is
  out of reach: it omits `movements`, reads the state's balance off the column the model
  materialised it into, and a consumer must not derive the schedule from the balances, which is
  the identity solved for the terms nobody quoted. And the reading that catches a producer that
  did neither: **where a compilation carries `movements` and its state carries a balance, that
  balance and the samples of a column whose whole tree is the extraction must be the same
  numbers, to the six decimals the wire writes.** That reading is asked where the trees are on
  the file, since `extracts` records which compilation a formula reached and a formula that
  wrapped the extraction reached it too — the `executable` profile earns it and the `audit`
  profile does not, which is stated as a limit rather than guessed at.
  **Nothing on the wire moves.** No member is added, no value joins any closed vocabulary, and
  the reading refuses only documents that were already stating a run that did not happen, so
  nothing this edition used to accept and that was true is refused now. A compilation whose
  amounts a producer declines gains a warning saying so and no error. `fingerprint_algorithm`
  remains `gspv0-preview-2`; no node's canonical bytes are touched and no node digest, compiled
  `fingerprint` or `graph_fingerprint` moves on any fixture or golden — measured, and every
  movement and every sampled balance of the shipped patterns is equal before and after. This
  answers a finding of the external review of 2026-09-20.

- `v0-preview.3` — **a negative zero keeps its own bytes, and `fingerprint_algorithm` moves to
  `gspv0-preview-3`; it is this line that moves it.** Section 12.1 wrote a negative zero as a
  positive one, on the ground that the two are one number in every arithmetic an actuary cares
  about — and that ground is where the rule was wrong, because the vocabulary published beside
  this identity does not treat them as one number. `to_text` spells them apart (11.1.39),
  `sign` and 11.1.25's division observe the sign. The same review that found the two
  clauses below exported one model twice, changing `0.0` to `-0.0` and nothing else, and got
  `0.0` from one run and `100.0` from the other under identical node, closure and graph
  fingerprints, with the change report reporting no drift and both documents validating. An
  identity may not equate what an admitted operation can distinguish, so the normalisation
  goes; the NaN normalisation beside it stays, because two runs that both produced a NaN have
  not drifted and no operation in this vocabulary reads a NaN's payload bits.
  **What has different bytes under the new token is a document carrying a negative-zero
  literal, and nothing else** — every other digest this grammar takes is the digest the old one
  took, which section 12.5's reprinted table shows node by node. But the token moves for every
  document regardless, because 12.2 admits no cosmetic grammar change and a consumer cannot
  tell from the outside which documents a change reached: two artifacts carrying different
  tokens must not be compared, and the change report refuses rather than reporting. The corpus
  of section 12.5 is regenerated and reprinted, and it grows an eleventh column holding a
  negative-zero literal so the one new thing in the grammar is exercised by the artifact whose
  job is to let a second implementation prove agreement.
  **The content grammar of section 12.3 does not follow, and that is stated rather than
  implied.** It hashes a column of data, where a zero's sign is what an arithmetic left
  behind rather than what an author wrote, and a basis republished with the same rates would
  otherwise announce a change nobody made; 12.3 now states its own position instead of
  pointing at 12.1's, and names what that leaves open. **The schema document is reissued** —
  its `fingerprint_algorithm` pin is the new token — and **the schema identifier does not
  move**: `gaspatchio-graph/v0-preview.3` names what a document may carry, which is unchanged.
  This answers a finding of the external review of 2026-09-20.

- `v0-preview.3` — **`round_sig_figs` states its tie rule: half away from zero, either sign.**
  Section 11.1.12 named it among the three operations decided by the value's own digits and
  checkable bit for bit, and a tie is exactly where the digits do not decide. The external
  review found the producer answering 3.0 and −3.0 for 2.5 and −2.5 at one figure while an
  independent reader written from these words answered 2.0 and −2.0, because its host
  language takes a tie to the even neighbour. The rule stated is the producer's, which every
  document written under this format was produced under, so **no value and no digest moves**;
  it is a sentence rather than a `mode` attribute like 11.1.8's, because an attribute nobody
  would set to the other value would move every `round_sig_figs` node's identity to carry a
  setting no model made. Cost named in the clause: a model wanting the even neighbour uses
  `round`. The same pass corrects that clause's own worked example, which printed
  `0.001234567` to three significant figures as `0.001234` — four figures, and not what the
  operation answers. Two vectors join the published corpus, at two magnitudes and both signs.
  This answers a finding of the same review.

- `v0-preview.3` — **`to_text` states how a float is laid out, not only which digits it has.**
  Section 11.1.39 said "the shortest decimal that reads back to the same number" and stopped,
  leaving the fixed/exponent switch, the exponent's padding and sign, and the non-finite
  spellings to whatever an engine's own printer did: the producer writes `1e-7` and `0.00001`
  and `NaN` where a reader written from these words wrote `1e-07`, `1e-05` and `nan`. Since
  this operation's answers are used as keys and tested in conditions, that is a difference in
  the model and not in a display. The convention stated is the producer's, measured across
  every boundary — **fixed form for a decimal exponent from −5 to 15 inclusive and exponent
  form outside it, the exponent always signed and never padded, a whole decimal keeping its
  `.0`, a negative zero keeping its `-`, and `NaN`, `inf` and `-inf` for the three non-finite
  values** — so **every text any model ever computed from a float is the text it was**. The
  clause also says where section 10's `"NaN"`/`"Infinity"`/`"-Infinity"` sentinels stop and
  this convention starts: those are how a non-finite value travels in an `f64` column on the
  wire, and these are what this operation computes into a `str` column, which never meet.
  Six vectors join the published corpus, one per boundary and both sides of each. This
  answers a finding of the same review.

- `v0-preview.3` — **Two engines agree on a line to 1e-12 of its scale.** Section 11.1.12 held
  six transcendental operations to a relative tolerance and said nothing about the whole
  document, so a reader holding two result files had no rule of this format's to apply and the
  cross-engine comparison that prompted these words used a fixed floor of
  `1e-10 + 1e-12·|ref|`. That floor called eleven closing balances of an IFRS 17 run-off year
  a difference in the model: they differ by 7.3e-10 between two correct implementations
  against operands near 17,000, which is 4e-14 of the operands and the whole of what is left
  after they cancel. Floating error is proportional to the magnitudes that were added and
  never to the remainder, so the scale is the line's — the node's own values and the values of
  everything its `reads` names, over that policy's timeline, on both sides — and the number is
  the one the six already carry, so the document keeps one. The exact classes are the ones
  that comparison used, the sign of a zero excepted, which section 12.1's grammar already
  hashes apart. The new words also state the five-decade band between reassociation and the
  rule, and the comparison grammar `gaspatchio-graph-compare/v0-preview.1` with its three
  verdicts, because a file carrying only the final schema does not carry the reads the scale
  needs and a comparison that cannot tell must say so rather than choose. **No value and no
  digest moves**: this states how two documents are compared, not what either of them says.
  The schema identifier does not move, on the test the lines above used.

- `v0-preview.3` — **A processed table cell may be a Boolean.** Section 15's account of the
  payload listed `i64`, `f64` and `str` and stopped, while section 12.3's content grammar has
  carried a `bool` under its own tag `0x11` for as long as that grammar has been normative.
  So a base whose answer column is a flag — a select table's "select applies", a rider's "in
  force" — had a cell type the digest hashes and the prose beside it did not admit, and a
  consumer written from these words would have refused a payload the grammar accepts. The
  fourth name joins both places the list is written, for a table and for a join's right side.
  **No value and no digest moves**: the bytes were always these, and the sentence widens what
  is described rather than what is accepted. The schema identifier does not move, on the test
  the lines above used.

- `v0-preview.3` — **An arriving column keeps its right-side name.** Section 11.1.2 said
  which keys a join matches on, that the whole right-hand frame travels with the record, and
  what `reads` does and does not carry — and never said what the columns the join brings are
  called. A consumer executing one therefore had to choose between the two sides' spellings
  wherever they differ, and a node's `column` was the one field it could not read without
  having made that choice. The rule stated is the producer's: the right side's name. It joins
  the list of what a conforming producer will add rather than becoming an attribute, because
  a name the record already carries does not need a second place to disagree with itself.
  **No value and no digest moves.** The schema identifier does not move, on the test the
  lines above used.
- `v0-preview.3` — **An engine's coverage table has three statuses, and two of them carry a
  condition.** Section 8.3 said what a node claims about the engines its own text needs and
  never said what an engine may claim about the vocabulary. The design walk's portability
  reading is computable per node, and the table it produces was being written in three words
  nothing defined: *lowered*, *lowered off the trace*, *refused by name*. The words are now
  stated, with the rule that makes them worth anything — the second and third travel with the
  condition they hold under, and a status is a statement about an invocation's form rather than
  about an identifier's name, so a table cannot say *lowered* of a form its engine refuses.
  Nothing in an artifact changes: a coverage table is an engine's publication and no part of a
  document, and this paragraph adds no member, no field and no value to any closed vocabulary.
  **No value and no digest moves.** The schema identifier does not move, on the test the
  lines above used.
- `v0-preview.3` — **A `mortality.at` that states no miss policy means `raise`.** Section
  11.1.10 said the read's miss policy is the base's and stopped, and the base's policy is on
  no part of the record: the wrapper emits the convention, the table's name and its content
  hash, and never the `on_missing` the base was registered with. A consumer holding the
  artifact therefore had to choose between refusing every `mortality.at` ever written and
  inventing an answer for a key the base does not carry — and the second is the choice
  between a zero, a null and a NaN, which are three different valuations. The default is now
  stated, in the same three values 11.1.24 already spells, and a base whose policy is not the
  default joins the list of what a conforming producer will add rather than becoming a second
  attribute nobody writes. **No value and no digest moves**: no member, field or value is
  added to any closed vocabulary, and a document this edition accepted is accepted still. The
  schema identifier does not move, on the test the lines above used.
- `v0-preview.3` — **Section 11.1.1 states the boundary count its own attributes yield.**
  The axis is a sequence of boundary dates and every count it states is a count of
  boundaries, and the section said so without ever saying how many. A second implementation
  holding the artifact had to infer the arithmetic from the four columns' sample values —
  which is an inference, and one that is off by exactly one wherever a reader takes the
  period count for the boundary count. The rule is now written out per horizon kind, in
  whole months over the cadence's own `m` where the cadence has one and in periods a year
  where it has not, with `T + 1` boundaries after it, the floor at nought named as the
  per-policy rule it is, and the portfolio-sized horizons still pointed at the item that
  says the record does not determine them. **No value and no digest moves**: no member, field or value is added to any closed
  vocabulary, the four columns are the four columns, and a document this edition accepted is
  accepted still. The schema identifier does not move, on the test the lines above used.
- `v0-preview.3` — **The cadence has one vocabulary, and section 11.1.37 carries the
  mapping onto it.** 11.1.1's `frequency` is the producing engine's own spelling and says so;
  11.1.37's recipes carry the period shorthand; and nothing said that `monthly` and `1M` are
  two spellings of one axis, so a consumer reading a `projection_set` beside the schedule it
  was laid from was matching two vocabularies without being told they were the same one. The
  six cadences are now mapped to the six tokens where the bounded family states its own, with
  the months a period of each is, the periods a year all six have, and the reason this
  bounded family covers four of them. **No value and no
  digest moves**: both spellings already reached the wire and both still do, no member is
  added to any closed vocabulary — 11.1.1's `frequency` is deliberately not closed — and a
  document this edition accepted is accepted still. The schema identifier does not move, on
  the test the lines above used.

- `v0-preview.3` — **Section 11.1.28's branches are a matched pair of any type this
  vocabulary carries, not of a number.** The entry bounded them to "matching i64 values or
  f64 values" and closed with "Output dtype is the shared numeric branch type", and the
  format's own producer has always emitted more than that: a conditional over two text
  columns, over two calendar dates and over two Boolean columns each runs and each is
  recorded with the shared branch type, and a mortality table selected by sex is such a line
  in two shipped tutorials. So the entry stated a bound its own producer did not keep, and a
  second implementation reading it would have refused an ordinary model — or, worse, read
  the artifact as ill-formed, which it is not: the validator accepted those nodes then and
  accepts them now. The pair rule is what was always true and is now what is written, with
  the crossed case named as outside rather than left to a reader to infer from a bound that
  did not hold. **No value and no digest moves**: no member, field or value is added to any
  closed vocabulary — section 10's type names are the five that were already there — and a
  document this edition accepted is accepted still, since what changes is the set of
  documents the entry *describes* rather than the set it admits. The schema identifier does
  not move, on the test the lines above used.
- `v0-preview.3` — **A `join` node reads its key.** Section 11.1.2 said a `join` node reads
  nothing, on the ground that the key selects the row rather than producing the value — while
  section 9's own rules had always listed "a join key" beside a lookup key as an `INDIRECT` /
  `JOIN` read. The first sentence won, and cost what it could not afford: a key column had no
  reader in the graph, so a consumer asked what depends on a policy's product code answered
  nothing, and asked what moves if the code is restated answered the code alone — while every
  column the join brought in, and everything computed from them, moves with it. A lineage
  question answered "nothing" is the comfortable answer, and a reviewer bounding a
  restatement with it under-scopes the re-run. Every column a join brings in now reads the
  left side's key columns, in the order `on` lists them, bound by section 8's rule and
  classified `INDIRECT` / `JOIN`; a cross join states no key and reads nothing, as before. The
  key stays in `on` as well, and the right side's names are not reads. Every reader of `on`
  reads it exactly as written, trimming nothing, and the reference producer refuses a key
  whose name holds `,` or `=`, since the attribute could not carry it. **No local digest
  moves** — the operation tree is unchanged, and so are the canonical bytes of section 12.1 —
  but **every Merkle digest downstream of a join does, and so does `graph_fingerprint`**,
  because each joined node now folds its key's digest in. Measured on the two tutorial
  models, each with 23 joined columns: 37 key reads added on each (level 4's 184 edges become
  221, level 5's 180 become 217), 85 of level 4's 128 node fingerprints and 85 of level 5's
  125 moved, and not one `local_fingerprint`. `fingerprint_algorithm` remains
  `gspv0-preview-3`, since no byte grammar changed, and the corpus of section 12.5 carries no
  join, so its table is unchanged. The schema identifier does not move: the edition is not one
  any artifact has been published under. **A document written before this line does not
  validate.** It was also written before the book line below, whose member the schema
  requires, so the schema refuses it; and what it lacks of this line is the key read, so even
  with a book added its executable reading no longer binds — `inspect_execution` reports the
  join's tree and `reads` as naming different sources, and a consumer executing it is told
  the join's node does not read its key. Export it again.
- `v0-preview.3` — **Every document records the book it was built over.** The envelope gains
  `book` (section 7.5): the input columns the model's answers rest on, in name order, and a content digest
  of them under section 12.3's grammar — the digest a result manifest records as
  `inputs_digest` when the engine was handed the book itself. Until this line a document said which policy data it was
  an account of only where its caller had filled in `model.model_points`, so two exports of one
  model over two entirely different in-force files compared as no drift, with nothing under
  `calculations` and nothing under `data`: the model never reads a model point by name, so
  nothing in the graph moves when the policies do. The comparison of section 14.2 now reports
  a changed book from these digests with no argument, and a book revised only in a column the
  model does not read is no change. `model.model_points` keeps its meaning — the file the run
  read, where the run named it — and is what a comparison falls back to where either document
  states no book digest; where neither decides, the comparison writes the policy data as an
  entry whose `reason` says the books could not be compared, and why, and that is drift.
  Section 6.1's `omitted` form gains a third position, the book's `digest`, which admits
  `unavailable` alone, for a producer that held no book or could not read the one it held,
  and there carries `detail` saying which; a column held as categories is read as the text it
  holds (section 12.3), so it is not one of those. A `data` entry of section 14.2 gains
  `reason`. **The member is required**, so as with
  `reads_assumptions`, `document_digest` and `policies` before it, a document written without
  it is refused by the schema. The schema identifier does not move, because the edition is not
  one any artifact has been published under, and `fingerprint_algorithm` remains
  `gspv0-preview-3`: the book's digest is no part of any node's canonical bytes and no section
  of `graph_fingerprint`, so not one node digest and not one graph fingerprint moves. **What
  moves is `document_digest`, on every document**, because every document gains the member.
  The corpus of section 12.5 is exported again carrying it: its table, its node digests and
  its `graph_fingerprint` are unchanged, and its seal is not. Decided 2026-09-25.
- `v0-preview.3` — **A location in the producer's temporary directory names the file, not the
  machine.** Section 7 writes a path outside the root with `..` segments on purpose: a helper
  module in a sibling directory of the same checkout, `../shared/helpers.py:12`, resolves for
  anybody with that layout. A notebook kernel keeps each cell's source in a file under the
  machine's temporary directory, and written the same way a cell's location became
  `../../../../../var/folders/…` — an absolute path spelled relatively, which names the
  exporting machine and resolves for nobody. A `source_location` in a file under the
  producer's temporary directory, where the root is not, is now written by the file's name in
  angle brackets, `<cell.py>:7`, the spelling Python uses for code with no file a reader can
  open, and its `sources` entry is `unavailable`, as any file outside the root is. Every other
  path outside the root keeps its `..` segments, and a location that names no file, such as a
  notebook cell's `Jupyter Cell 3`, is written as it was recorded. **No identifier moves**,
  `fingerprint_algorithm` remains `gspv0-preview-3`, and no fingerprint moves: a location is
  no part of any node's canonical bytes. A document exported again with such a location spells
  it anew, so its `document_digest` moves; the corpus of section 12.5 carries none, and its
  seals are unchanged. Decided 2026-09-30.
- `v0-preview.3` — **The comparison reads the results file each run recorded.** Section 7's
  `model.results` names the output file a run wrote, with the SHA-256 of its bytes, and until
  this line the comparison of section 14.2 never read it: two documents of one model over one
  book compared as no drift over two different results files. A column the model recorded and
  then overwrote straight in the query plan produces exactly that, since the overwrite moves
  the numbers in the file and no digest in the graph. A `data` entry gains a sixth kind,
  `results`, written where both documents record a results file's fingerprint and the two
  differ: `before` and `after` are the fingerprints, the name is the later run's
  `model.results.path`, else the earlier one's, else null, `reason` is null, and the entry is
  drift. It follows every other kind. A file's bytes move with whatever wrote it as well as with
  its numbers, so the entry says the file moved, and the comparison of two results that section
  11.1.12 states says whether the two results agree. Where one document records a results
  file's fingerprint, or neither does, no entry is written. **No identifier moves**: the report
  grammar `gaspatchio-graph-diff/v0-preview.1` has had no report published under it, the schema
  identifier and `fingerprint_algorithm` are unchanged, and no document, digest or seal moves,
  because nothing a producer writes changes. Decided 2026-09-30.
- `v0-preview.3` — **The reference producer writes no `Apply`.** Section 16 states it: the
  producer's kernel has no evaluation for a step that sets a balance to an expression
  outright, so its compiler now refuses a rollforward carrying one before there is a
  compilation to describe, where it used to compile one and fail at every run of it. `Apply`
  stays among the ten operations section 16 lists, and a reader that meets one reads it as
  before. **No identifier moves**, `fingerprint_algorithm` remains `gspv0-preview-3`, and no
  document, digest or seal moves: the corpus of section 12.5 holds no `Apply`. Decided
  2026-10-03.
- `v0-preview.3` — **A hole says what the producer saw.** `reason` in the holes section
  (section 7.1) grows from one value to three. `unrecorded` keeps its meaning. `overwritten`
  is a column the producer had accounted for — a calculation it logged, or a column the data
  arrived with — that a write past its interfaces then replaced: the producer sees the write
  and reads off the plan which names it defined, so the hole is one definition it can place
  and cannot read, versioned (`column@k`, sections 8 and 8.1), located at the line of the
  write, and read by the calculations written after it. Until this line such a column kept the
  formula it had been written over: a document stated a calculation the frame's values no
  longer came from, and the comparison of section 14.2 found no calculation moved, so that
  only a results file, where both runs named one, said otherwise. `rebuilt` is a column the
  frame arrived with whose memory was, when the frame was built, a calculated column of values
  another frame's collect in the same process produced, still held by that frame or its
  caller; until this line it was an input of the policy data. Section 7.1 states what each
  reason cannot see. The holes section is one entry per name, as it always said, and section
  12.4's third section takes each name once: a name can now have two hole nodes, so a producer
  de-duplicates before it sorts. Two different rules carry this line. The vocabulary growing
  is the additive change section 14 allows even within a stamped `v0` — "a closed vocabulary
  may grow" — and a document whose holes are all `unrecorded` means what it meant. The
  versioned hole is not additive: until this line a hole was never a definition and never
  carried a version, and an `overwritten` hole gives `kind: hole` and `version` a meaning they
  did not have, which section 14 does not allow within a stamped `v0`. It is made under the
  preview's own policy (section 1): written down here for a consumer to read, so a consumer
  that took every hole to be unversioned will meet one that is not. The schema accepts after
  this line every document it accepted before it. The published validator does not: it now
  holds the section to the nodes it restates — one entry for each name a hole node stands
  for, carrying a reason that fits the first such node's version — so a hand-built document
  whose section and nodes disagree, which section 7.1 never described, is refused where it
  used to be accepted. Every document this producer has written agrees. **No identifier
  moves**: no release has published a document under `v0-preview.3`, which 1.0.0 is the first
  to write, and 0.9.0 wrote an unversioned graph and reads no document of this format, so no
  released reader meets a hole at all. `fingerprint_algorithm` remains `gspv0-preview-3`,
  because a hole's canonical bytes are its kind, name and type, as before. On a model with
  such a column the graph moves — a hole node, the digests downstream of it and
  `graph_fingerprint` — and on every other model nothing does. Decided 2026-10-03.
- `v0-preview.3` — **A broadcast's axis is read for its length.** Section 9 gains an emission
  rule: the second operand of `projection.broadcast_to_periods` — `like`, or the `month` a
  producer records where `like` was omitted — is `INDIRECT` / `WINDOW`, the weakest of the
  indirect narrowings. Until this line the reference producer claimed it `DIRECT` /
  `TRANSFORMATION`, which section 9 defines as a value that flows into the result, and section
  11.1.32 says it does not: a column broadcast along `policy_year` sat in the impact cone of
  `policy_year` as though restating a policy year moved the rate. The read and its edge are
  kept, only their relationship and narrowing move. **No identifier moves** and no digest or
  seal does: an edge's relationship and the narrowing facet are no part of any canonical bytes
  (sections 12.1 and 12.4). A document written before this line states a relationship the
  section now defines otherwise; the schema accepts both. Decided 2026-10-10.
- `v0-preview.3` — **`and`, `or` and `not_` read a stored indicator.** Section 11.1.18's
  checked 0/1 rule for a stored `f64` or `list[f64]` column was stated for a `when_then`
  condition alone, and section 11.1.27 put a per-policy stored `f64` operand outside itself,
  so a flag a model had stored could select a branch but could not be combined with another
  or negated: the reference producer refused `af.flag & other` and `~af.flag` while the
  formula was being written. Section 11.1.27 now takes a direct reference to such a column
  as an operand under the same rule: exactly `0.0` or `1.0`, a negative zero is zero, and a
  null, a NaN, an infinity or any other number is a refusal at evaluation. A per-policy one
  reads as the Boolean it encodes, so an all-scalar result is Boolean; a per-period one is
  its own 0/1 indicator, so the result is `list[f64]`, as every per-period logical result
  already was. One reading narrows: a direct `list[f64]` column reference holding a null,
  which the entry's per-position rule answered with a null, now refuses, as the same column
  standing as a `when_then` condition does. No document the reference producer has written
  holds such a node — it refused every `f64` logical operand — and no published vector did.
  **No identifier moves**: no member, field or value is added to any closed vocabulary, the
  operation is the same `binop` or `not_` call over the same column reference, and the schema
  accepts exactly the documents it accepted. `fingerprint_algorithm` remains
  `gspv0-preview-3` and no digest or seal moves, since an operand's declared type is no part
  of any canonical bytes and no tree changed shape; the corpus of section 12.5 holds no
  logical operation. The kit's reader follows the entry, and `vectors/logical.json` carries
  its cases. Decided 2026-10-10.
- `v0-preview.3` — **A table's identity is its content, whatever order its source was laid
  out in.** Section 12.3 states the canonical form a table puts itself in before it is hashed:
  key columns ascending by name, the answer column last, rows ascending by the keys. Until this
  line the reference producer hashed the processed frame with its columns in the order the
  source listed them, so the same rates published with two columns swapped carried two
  `table_fingerprint`s, two graph fingerprints and a registry warning that the table had been
  re-registered with different data, and the content hash inside the table's own recipe — taken
  over the canonical order already — was a second string beside the one the record carried.
  There is now one: the entry's `fingerprint`, every lookup node's `table_fingerprint`, the
  recipe's `content_sha` and the reference producer's public `Table.fingerprint()` are the
  same digest, and `source_sha` stays the recipe's (sections 12.3 and 15 say which is which).
  **A table whose source held its key columns out of name order, or its answer anywhere but
  last, stamps differently, once, and that is the one movement to expect**: its entry, the
  lookup nodes that read it — whose operands now stand in the canonical key order, which is the
  order the payload carries — the digests downstream of them and `graph_fingerprint`. A table
  already in that order stamps exactly as before, and no stamp moves with different values
  behind it. One source read under two different answer columns is now two contents rather than
  one content with two conflicting roles, so neither payload is withheld as ambiguous. No byte
  grammar moves — section 12.1's tree grammar and section 12.3's content grammar write the
  same bytes for the frame they are handed; what changed is the frame — so
  `fingerprint_algorithm` remains `gspv0-preview-3`, as it did when the key-type widening above
  moved a stamp the same way, and the schema identifier does not move. No reader changes: a
  consumer re-hashes a payload in the order carried (section 13), and a document written before
  this line still verifies against its own payload; compared across the line, such a table
  reads as moved once. The corpus of section 12.5 carries no assumption entry and is unchanged.
  The conformance kit's three `lookup-guarded-null-key` vectors carried a table outside the
  canonical order and are rewritten in it, with their fingerprint re-derived by the kit's own
  reader and the index regenerated. Decided 2026-10-10.
- `v0-preview.3` — **A join's right side and a mortality wrapper take the same content
  identity a table does.** Section 12.3 puts a join's right side in canonical form before it is
  hashed — its columns ascending by name, its rows sorted by every column in that order — where
  until this line the columns stood in the order the caller's frame listed them, so the same
  expense table handed over with two columns swapped carried two `right_fingerprint`s. Sections
  11.1.2 and 15 say the same, and section 15's inline join payload now carries its columns in
  name order. And the `mortality` attribute of `mortality.at` (11.1.10) is the wrapper's
  `source_sha` over a recipe that now carries the base's content hash: until this line that
  recipe held the table's name, its dimensions and the convention and none of the rates, so two
  mortality bases under one name with different rates stamped the same `mortality`. Section 15
  also states what the table's canonical form already implied, that the content hash fixes which
  column answers. **What moves, once**: a join whose right side was not already in name order,
  with its entry and the digests downstream of it, and every `mortality.at` node's `mortality`
  attribute, its digest and those downstream of it; no stamp moves with the same values and the
  same convention behind it. No byte grammar moves, so `fingerprint_algorithm` remains
  `gspv0-preview-3` and the schema identifier does not move, on the same ground as the table
  line above. No reader changes: a payload is re-hashed in the order carried, and the
  `mortality` attribute is read as published (section 13). The corpus of section 12.5 holds
  neither operation and is unchanged. The conformance kit's two join vectors carried their
  right side outside name order and two `mortality.at` vectors carried the earlier wrapper
  digest; all four are rewritten, the join fingerprint re-derived by the kit's own reader, and
  the index regenerated. Decided 2026-10-10.
- `v0-preview.3` — **A sampled number is the full double the run held.** Section 8 states it:
  every floating-point value in `value_sample`, `branches` and `movements`, on every entry of
  the axis, and every number a `trace` step carries as a JSON number, is the binary64 value
  the column held, written as the shortest decimal that reads back to it; a `trace`'s prose
  still prints six significant figures and is stated to be a reading aid. Until this line the
  reference producer rounded every such value to six decimal places, a rule this document
  never stated for `value_sample` and named only in section 16's balance reading, and a reader
  who rebuilt a timeline from the artifact against the results file `model.results` pins
  matched some of its cells and not others. Section 16's reading now says the two readings of
  one series are equal to the bit and keeps its `1e-6` tolerance, so nothing it accepted is
  refused. **No identifier moves**: no member is added and none changes type or meaning — a
  sample was always what the column held — the schema leaves the enrichment fields
  unconstrained as before, and no release has published a document under `v0-preview.3`.
  `fingerprint_algorithm` remains `gspv0-preview-3` and no fingerprint moves, because no
  enrichment field is part of any node's canonical bytes (section 12.1). A document carrying
  values is written with more digits, so its bytes and its `document_digest` move; one
  carrying none, which is every document of the corpus of section 12.5, moves nothing. On the
  level-4 tutorial's one-policy export the document grows from 1,729,777 to 1,757,373 bytes,
  and section 8's byte guard is unchanged. Decided 2026-10-10.
- `v0-preview.3` — **An engine-native fragment keeps a decimal receiver's digits.** The
  reference producer takes the library path out of a fragment's text before the fragment is
  hashed, and that scrub could start inside a decimal written immediately before a plugin call:
  `dyn float: 1.01.<library>:list_pow(…)` was written `dyn float: 1.<plugin>:list_pow(…)`, so two
  fragments differing only in the digits after the point carried one text and one digest. The
  scrub now never starts at a digit. **No identifier moves** and no rule of this document
  changes: a fragment's text is the producer's rendering, which section 12.1 hashes as written.
  A node holding such a fragment, its dependants and `graph_fingerprint` move, on a model that
  has one and on no other; the corpus of section 12.5 holds none. Decided 2026-10-10.
- `v0-preview.3` — **A record names what a model rests on beside its own file.** Section
  7's version block gains `modules`: every local module the model imports — each file beside the
  model, or in a package beside it, that its import statements resolve to, followed through
  those files' own — with the SHA-256 of its bytes, taken as `source_sha` is. Until this line
  `source_sha` covered the model file alone, so an edited helper the model imported moved figures
  and no stamp. Section 15's table entry gains `source_file`, the file a table was read from, or
  null where the model built it from a frame in its own code; `shaped_by`, each step of its
  recipe that reshaped what it read; and section 6.1's stand-in for a table payload omitted
  for its size gains `roles`, the payload's dimensions, value and typed columns without the
  rows. Section 13 states both
  checks: a module against the file beside the model a reader holds, and a table's file re-read
  as that table, through its roles, to its content hash — a difference deciding only where the
  record names the file the table was a plain read of. **No identifier moves.** Every member
  is optional, so the schema accepts every document it accepted before, and the identifier is
  `v0-preview.3`, which no release has published a document under. `fingerprint_algorithm`
  remains `gspv0-preview-3` and no fingerprint moves: no member is part of any canonical
  bytes or of `graph_fingerprint`. A document exported again carries the new members wherever
  its model block names a source or it reads a table, so its `document_digest` moves; the corpus
  of section 12.5 names no model source and reads no table, and its seal is unchanged. Decided
  2026-10-10.
- `v0-preview.3` — **`excel.round` rounds the value a spreadsheet holds.** Section 11.1.35
  said a decimal tie is determined after the binary64 scaling, not by reading the operand as a
  decimal, and a spreadsheet does the opposite: its `ROUND` rounds the operand's
  fifteen-significant-digit decimal. A workbook conversion found the difference in the
  workbook's own cached cells — `ROUND(1.5 * K19, 2)` with `K19 = 45366.20999999999` caches
  `68049.32` and the clause answered `68049.31`, because the product is the double
  `68049.31499999999…` and its fifteen digits are a half; a cent of interest went missing the
  same way inside a rollforward. The clause now states the spreadsheet's rule — fifteen
  digits, a sixteenth of 5 or more away from zero, then `num_digits` places half away from
  zero, then the nearest double — and its worked value. **Values move; no identifier and no
  digest does**: the operation, its attribute and their canonical bytes are unchanged, so a
  document written before this line reads exactly as it did, and an evaluation of it after
  this line answers a different last place wherever an operand's fifteen digits are a half its
  double is not, or are coarser than the step. `fingerprint_algorithm` remains
  `gspv0-preview-3` and the schema identifier does not move, on the test the lines above use.
  Vectors at the workbook's values, the decimal ties a double sits just under, both signs, a
  negative `num_digits` and the magnitudes where fifteen digits are coarser than the step join
  the published corpus. The reference producer's rollforward rounds — `round_charge` and
  `Round` — follow the same rule in the same code; section 16.1 gives neither portable value
  semantics, so no clause of section 16 moves. Decided 2026-10-10.
- `v0-preview.3` — **A comparison pairs rows by the identity its results record.** Section
  11.1.12 said a comparison states whether rows were matched by a policy identity or by
  position, and said nothing of when position may be used: a result manifest's
  `row_identity` was null unless a command was told a column, so two results of one artifact
  whose policies stood in another order were compared policy against wrong policy and still
  given a verdict. The clause now states the rule: `row_identity` names the columns that
  together name each row once — the policy-id column, and the scenario column on a scenario
  run — rows are paired on them, and position is a pairing only where the same order is shown
  by those columns or by one book's `inputs_digest`; otherwise the comparison refuses. The
  report gains `rows_matched_on`. A manifest's one-name form is still read. **No identifier
  moves**: no member of the document, no canonical bytes and no fingerprint is touched, the
  report keeps `gaspatchio-graph-compare/v0-preview.1`, and `fingerprint_algorithm` remains
  `gspv0-preview-3`. A comparison that used to answer over an unshown order is refused where
  it would have paired the wrong policies. Landed 2026-10-11.
- `v0-preview.3` — **The record says what produced its values, and why a revision is
  missing.** Section 7's `producer` gains the optional `versions`: the six keys a result
  manifest states — core and extension versions, the extension's sha256, Polars, Python and the
  platform — and `imports`, each installed distribution the model imports with its version, so
  a reviewer holding only the document can say whether this library would give the same number,
  and a document and the results file of one run state one set. A document committed as a
  golden writes §6.1's `withheld` form in its place. `model.git: null` now has one meaning, no
  working tree beside the model; every other failure is §6.1's `unavailable` form with `detail`,
  and §6.1 gains both positions. **Additive, and no identifier moves**: both members are
  optional and outside every fingerprint and canonical byte, so a document written before this
  line validates and reads as it did; `fingerprint_algorithm` remains `gspv0-preview-3` and the
  schema identifier does not move. Landed 2026-10-11.
- `v0-preview.3` — **One figure says whether any formula moved.** The envelope gains the
  optional `formulas_fingerprint` (section 12.6): section 12.4's fold taken again over trees in
  which every attribute naming a value object's content — a table's, a join's right side's, a
  mortality basis's, a curve's, a schedule's and its restated start and frequency, and both
  attributes of a column of values handed over at a line — is replaced by the text `masked`,
  over the pairs and the unaccounted names, the tables section left out. A re-sourced table,
  curve or schedule moves `graph_fingerprint` and leaves it where it was; an edited formula, a
  literal, a table name, a key or a typed valuation date moves both. A compiled rollforward's
  identity is kept, and it includes the schedule it was compiled on, so under a rollforward a
  schedule change moves both — until the line headed *a compiled rollforward's identity is its
  machine* below takes the schedule out of that identity. Recomputable from an `executable` document and read as written
  from an `audit` one. Section 14.2's `compared` records gain the member, null where a document
  carries none, and `gspio diff` prints whether the two agree. **Additive, and no identifier
  moves**: the member is optional and outside every canonical byte, so a document written
  before this line validates and reads as it did; no node digest and no `graph_fingerprint`
  moves; `fingerprint_algorithm` remains `gspv0-preview-3`, because no artifact had carried the
  digest and there was none to read under the wrong rule — section 12.2's reasoning for the
  content grammar. The corpus of section 12.5 is exported again carrying it, with its library
  versions withheld; its seal and its creation time move and none of its digests does. Landed
  2026-10-11.
- `v0-preview.3` — **A recurrence can roll back, and a list can be turned end for end.**
  `projection.accumulate` gains the attribute `reverse` (11.1.11, 11.1.20), a flag written on
  every call: under `true` the same linear recurrence runs from each policy's own last period
  back to its first, `s[t] = s[t + 1] * multiplier[t] + addend[t]` opening at
  `s[T] = initial`, and a null step loses every earlier position by 11.1.9's rule for a
  reverse fold. `list.reverse` joins the vocabulary (11.1.41): position `t` of the answer is
  the operand's position `T_i - 1 - t` within each policy's own length, a null moving with
  its position, and its operand is `DIRECT` / `AGGREGATION` (section 9). Until this line a
  workbook's rollback reached the record as three engine fragments around a forward
  recurrence — reverse, accumulate, reverse back through an escape hatch — so the line and
  every column it fed refused a second engine. **What moves, once**: every
  `projection.accumulate` node now carries `reverse: false` where it carried no attribute,
  so its digest, the digests downstream of it and `graph_fingerprint` move with the same
  calculation behind them. No byte grammar moves — section 12.1 writes the attribute by the
  rule it always had; what changed is the signature schedule — so `fingerprint_algorithm`
  remains `gspv0-preview-3` and the schema identifier does not move, on the ground the
  table-identity line above states. A document written before this line carries no
  `reverse` and reads as the forward recurrence it was written as; compared across the line,
  each accumulation reads as moved once. The vocabulary grows additively to ninety-nine
  identifiers, ninety-seven with stated values. The corpus of section 12.5 holds no
  accumulation and is unchanged. The kit's eight earlier accumulation cases carry
  `reverse: false`, `vectors/reversal.json` carries the backward recurrence and the
  reversal over jagged books, nulls and empty runs, the kit's reader implements both, and
  the index is regenerated. Landed 2026-10-11.
- `v0-preview.3` — **A table read inside an engine fragment is refused.** Annex A.2's second
  case is closed. A lookup continued by a method the vocabulary does not hold, handed to one of
  the engine's own functions, or opened through the escape used to reach the record as one
  engine-native fragment whose text names the lookup and not the table, so two models reading
  two different tables exported one `graph_fingerprint`. A value-object read — table, mortality
  basis, curve, schedule — is now its own node, and the producer refuses a statement that would
  inline one into a fragment, naming the base, the declared operation that keeps it a node and
  the two-line form; section 8.2 states the consequence for `formula`. A renamed read keeps its
  node, and a compiled rollforward's fragment, which reads the rollforward by name, is not
  touched. **No identifier moves**: no member, canonical byte or fold changes, so a document
  written before this line validates and reads as it did, `fingerprint_algorithm` remains
  `gspv0-preview-3` and the schema identifier does not move. What changes is which statements a
  producer records: one that used to export a fragment hiding its base is refused, and one that
  renamed a read now records the read, whose digests move. The corpus of section 12.5 holds no
  such node and is unchanged. Landed 2026-10-13.
- `v0-preview.3` — **A projection axis of fixed steps in years, with no calendar under it.**
  Section 11.1.1 gains a fourth declaration form, *fixed step*: `n_periods` and exactly one of
  `step_years` (the decimal as written) or `steps_per_year` (an integer), `frequency` null, no
  start and no horizon. It mints `step` (`0..T`, reserved as `month` is), `num_proj_months`
  and, only where a step is whole months, `month`; it mints no dates. Section 11.1.37 states
  the fourth schedule kind, `fixed_step`, whose time is `k × step_years` or
  `k ÷ steps_per_year` — one IEEE operation per boundary, exact, never a running sum — and
  whose dated readings, and an anniversary under `step_years`, are refusals. Section 15 states
  the `fixed_step` recipe, section 16.1's executable subset admits it as a schedule supplying
  only `T`, and section 17's `time_axis` gains the step form, `frequency` null and the step
  written as declared. The schema admits that form of `time_axis` and nothing else moves in
  it. **No identifier moves**: no operation, member, canonical byte or fold changes, so a
  document written before this line validates and reads as it did, `fingerprint_algorithm`
  remains `gspv0-preview-3` and the schema identifier does not move; a calendar axis records
  exactly what it did, and its `t_years` remains the running sum. The corpus of section 12.5
  holds no projection and is unchanged. The kit gains `vectors/fixed-step.json` — the step and
  month a declaration mints, and `t_years` in both spellings at zero tolerance, chosen so the
  other spelling and a running sum both fail — its reader implements the form, and the index
  is regenerated. Landed 2026-10-19.
- `v0-preview.3` — **The normal distribution function is an operation.** `norm_cdf` joins the
  vocabulary (11.1.11, 11.1.12): Φ of one value, a double whatever numeric type the value
  arrives in, held with the transcendental family to 1e-12 relative to the mathematical Φ
  wherever Φ is a normal double (from −37.5 up), exact at a null, a NaN and the two
  infinities, and decided by the line rule below the normal range. Excel's
  `NORM.S.DIST(z, TRUE)` and `NORMSDIST(z)` are this call, and a producer's Excel spelling
  records it rather than a second identifier; `NORM.DIST` is the call on the standardised
  value; the density is written in operations 11.1.12 already holds; no agreement with
  Excel's own bits is claimed; and `norm_inv` is reserved for the inverse, which is not in
  this vocabulary. Until this line a guarantee priced as an option reached the record as
  engine text, because there was nothing to write N(d1) with. **Additive, and no identifier
  moves**: a `call` has been hashable under section 12.1 since that grammar was written, no
  member, canonical byte or fold changes, and no existing identifier changes meaning, so a
  document written before this line validates and reads as it did, `fingerprint_algorithm`
  remains `gspv0-preview-3` and the schema identifier does not move. The vocabulary grows to
  one hundred identifiers, ninety-eight with stated values, and the unnamed domain's
  non-operator count from thirty-eight to thirty-nine. The corpus of section 12.5 holds no
  such node and is unchanged. `vectors/normal-cdf.json` carries the body, both tails to the end
  of the normal range, the subnormal and underflowed answers under the line rule, the exact
  values, nulls on both shapes and an empty portfolio, each against Φ worked to 60 digits; the
  kit's reader implements it and the index is regenerated. Landed 2026-10-19.
- `v0-preview.3` — **A NaN has a fill of its own.** `fill_nan` joins the vocabulary (11.1,
  11.1.11, 11.1.13): the fill where the value is NaN and the value everywhere else, an
  infinity and a null included, with the fill an operand as `fill_null`'s is. Over a whole
  number it replaces nothing and does not fail; over a Boolean, text, a date or a decimal this
  document states no answer for it, as it states none for the NaN tests. Until this line the
  commonest clean-up of a table read, `lookup(...).fill_nan(0.0)`, was refused under the
  2026-10-13 line above for hiding the table inside an engine fragment, and the same fill on a
  stored column was refused as a name the vocabulary did not hold; it is now one core node
  over the read, and its digest moves with the table. **No identifier moves**: no member,
  canonical byte or fold changes, so a document written before this line validates and reads
  as it did, `fingerprint_algorithm` remains `gspv0-preview-3` and the schema identifier does
  not move. A NaN fill with a value written through the escape is now refused, naming this
  operation, as every declared form is; the escape keeps the forms the operation does not
  hold. The vocabulary grows additively to one hundred and one identifiers, ninety-nine with
  stated values, and the unnamed domain's non-operator count from thirty-nine to forty. The
  corpus of section 12.5 holds no such node and is unchanged; `vectors/nan-fill.json` carries
  the fill over policies and periods, nulls, infinities, column and expression fills and
  whole numbers, the kit's reader implements it, and the index is regenerated. Landed
  2026-10-19.
- `v0-preview.3` — **An aggregation's edge says which periods it read.** Section 9's narrowing
  facet gains two members of this document's own beside `offset`: `periods: {from, to}` on an
  `AGGREGATION` read, each bound a whole number of periods from the period being computed or
  `"first"` / `"last"`, and `position: k` on a direct read a literal `list.get` made. Each is
  quoted from the identifier's own attributes by the table §9 prints — `{first, 0}` for a
  forward scan, survival fold, recurrence or rollforward operand, `{first, -1}` for a survival
  fold with an opening value and a forward discount factor's rate, `{0, last}` for a reverse
  scan or recurrence, a remaining sum and a prospective value's cashflows and list rate,
  `{first, last}` for the four reductions, the internal rate and a reversal — and never from
  lowered text. A composition the members can write states its composed window, one they
  cannot states none, and a column holding one value per policy states none. A name read
  through two windows in one formula writes one entry per window, strongest narrowing first;
  every other read writes the one entry it wrote before. Until this line five of seven
  workbook reconciliations recovered an aggregation's timing with regular expressions over
  `formula`. **Additive, and no identifier moves**: §7 has a consumer accept members it does
  not define and the `transformations` entries stay open, the schema declares both members and
  the pairings, the validator refuses a window that runs backwards, and a facet is outside every
  canonical byte, so no node digest, `graph_fingerprint` or `formulas_fingerprint` moves and
  `fingerprint_algorithm` remains `gspv0-preview-3`. A document written before this line
  carries no window and reads as it did. The corpus of section 12.5 is exported again, its
  `total_claims@1` read gaining `{"from": "first", "to": "last"}`: its seal and its creation
  time move and none of its digests does. The kit's envelope gains the optional
  `perturbation` member (§11.3), `vectors/windows.json` carries forty-eight cases, the kit's
  reader is unchanged, and the index is regenerated. Landed 2026-10-19.
- `v0-preview.3` — **A compiled rollforward's identity is its machine; its schedule is data.**
  The compilation's published `fingerprint` (section 16) is taken over the machine alone —
  states and opening values, every operation in order with its operands, label, rounding and
  timing, the stopping conditions, the batch axes, the increment tracking and the engine
  binding — and no longer over the schedule the machine runs on. Every rollforward call gains
  the attribute `schedule`, the `source_sha` of that schedule (11.1, 12.1, 16), and section
  12.6 masks it. A re-sourced schedule under a state machine therefore moves
  `graph_fingerprint`, through the compilation's node and every line reading it, and leaves
  `formulas_fingerprint` and the `rollforward:` id where they were; an edited machine moves
  both figures and the id. One model holding one machine on two schedules is refused by name,
  since the two runs would claim one id (section 16), and a document whose compilation node
  and IR facet body name two schedules is refused by the execution reading. **What moves,
  once**: every compiled fingerprint, every `rollforward:` id, and so the digests of every
  rollforward node, every line reading one and every `graph_fingerprint` of a model holding
  one, with the same calculation behind them; two machines that differed only in their
  schedule now share a fingerprint. No byte grammar moves — section 12.1 writes the new
  attribute by the rule it always had, and the compiled fingerprint is an identity section
  12.1 carries as text and does not define — so `fingerprint_algorithm` remains
  `gspv0-preview-3` and the schema identifier does not move, on the ground the
  accumulation line above states. The new mask row reaches an attribute no earlier document
  carries, so no `formulas_fingerprint` written before this line changes under it. A
  document written before this line carries no `schedule` on its rollforward calls and reads
  as it did; compared across the line, each compilation reads as renamed once. The corpus of
  section 12.5 holds no rollforward and is unchanged. The kit's rollforward cases carry the
  new identity and the attribute, and the index is regenerated. Landed 2026-10-20.
- `v0-preview.3` — **A scenario plan's column shock is an `assignment` at the plan's line.**
  Section 8's provenance table gains the sentence and its vocabulary does not. A plan runs the
  model unchanged and shocks a model-point column -- a valuation rate, a solved premium -- by
  rewriting it per scenario before the model runs. The record states that rewrite as what it is:
  an assignment superseding the book's column, located at the plan's line, its formula the
  shock's recipe. A read of a table a shock names is the lookup a model handed the stacked table
  would write, with the injected axis as an operand, and a seeded plan's per-scenario seed is an
  `injected` column, as the axis is. **No identifier moves**: no member, canonical byte or fold
  changes, `fingerprint_algorithm` remains `gspv0-preview-3` and the schema identifier does not
  move. The corpus of section 12.5 holds no scenario run and is unchanged. Landed 2026-10-20.
- `v0-preview.3` — **The change report measures what moved, and by how much.** Section 14.2's
  report reads the two runs' results files beside the two documents, where both documents
  record one whose checksum still matches or a caller names two, and writes a seventh member,
  `values`: per paired line whether its numbers moved, in how many policies, from which period,
  the largest absolute and relative move and the cell that ranks it, the policies only one book
  holds, and what the record states moved under a line whose definition did not. A value has
  moved when it is unequal; section 11.1.12's rule labels a moved line `within_band` and never
  hides one. `drift` is also true where a line under an unmoved definition moved beyond the
  band. The report grammar moves to `gaspatchio-graph-diff/v0-preview.2`, and `values` is null
  on a report written without results. **The schema identifier does not move**,
  `fingerprint_algorithm` remains `gspv0-preview-3`, and no document, digest or seal moves:
  nothing a producer writes changes. Landed 2026-10-20.
- `v0-preview.3` — **`fill_null` states its bounded domain.** Section 11.1.13 stated
  `fill_nan`'s domain and not `fill_null`'s, so the type a fill of another kind answered was
  whatever an engine's promotion chose: text, where a number met a string. The domain is now
  a value and a fill of one family, the numbers sharing a type as `fill_nan`'s do, and a fill
  of another family, or a number filling a `bool`, is outside it — the reference producer
  refuses both at the line, as it now refuses a comparison or an `is_in` member across the
  families section 11.1.26 keeps apart. **No identifier moves**: no member, canonical byte or
  digest changes, `fingerprint_algorithm` remains `gspv0-preview-3`, and a document written
  before this line reads as it did. The corpus of section 12.5 holds no cross-family fill and
  is unchanged. Landed 2026-10-20.
- `v0-preview.3` — **The run record is defined.** Section 13.2 states the record a scenario run
  or an aggregation writes beside its output, under `schema_version` `"2.1"`: its ten members,
  the shapes its numbers take, the six library keys it shares with `producer.versions` beside
  `ddsketch_version` and the two things it does not carry (`imports`, git), `bases`, the whole
  or partial stamp of the data the run read, and the three identities of the policy data, none
  derived from another. It says `graph_fingerprint` and `graph_fingerprint_by_scenario` are
  calculation identities rather than citations of documents, so section 13.1's seal rule does
  not reach them, and it records how 2.1 differs from the 2.0 record the reference producer
  wrote before. Section 4 and the `model` row point at it, and there is no machine-readable
  schema for the record. **No identifier moves**: nothing a producer writes changes,
  `fingerprint_algorithm` remains `gspv0-preview-3` and the schema identifier does not move.
  Landed 2026-10-20.
- `v0-preview.3` — **The stated domains reach what the reference producer already does.**
  Section 11.1.25 reads a per-period Boolean operand as its `list[f64]` indicator, under every
  operator and on either side, and leaves the type of a per-policy one's answer outside the
  entry; 11.1.26 states list-shaped text comparison — exact equality, code-point order, a null
  element answering null; 11.1.20 says a producer writes a whole-number operand's widening as
  `to_float` and refuses a Boolean one, and 11.1.19 how it meets a shifted run of Booleans; and
  section 15 says a key column declared as text stays text. Each was the producer's behaviour
  already and is held by its tests; no vector is added, and the kit's boundary review names
  those tests. **No identifier moves**: no member, canonical byte or fold changes, and a
  document written before this line reads as it did. Landed 2026-10-20.
- `v0-preview.3` — **Sentences that said more, or less, than the format does.** Section 8 no
  longer says the two timing conventions agree at constant rates — they differ even at flat
  rates, and what flat rates hide is a wrong conversion between them — and its every-policy
  fence names the reader's own `all` and the byte guard that bounds it. Sections 1 and 4 name
  the enrichment of sections 7.4 and 8 as the one exception to carrying no per-policy values.
  Section 11.1.1's zero term is one boundary and a `month` of `[0]`, as its own column rule
  says; 11.1.25 points at 11.1.12's line rule as the whole document's; 11.1.28 stops counting
  identifiers; 12.1 says a compiled rollforward's identity is the compiler's and opaque to a
  consumer; and Annex A.2 states what an engine-native fragment still does not answer — values
  its engine's rendering does not print, and a meaning that is the engine's. **No identifier
  moves** and nothing a producer writes changes. Landed 2026-10-20.
- `v0-preview.3` — **The kit's identity reader recomputes the formulas-only figure.** It folds
  section 12.6's masked trees over the corpus and reports a `formulas_fingerprint` that moved,
  where it used to read the figure as written; the kit's README states what a null does to a
  total and to a running fold as the clauses do, names the fixed-step bundle, and states the
  invocation reader's narrow edges — no Boolean table cell, one plainly named join key, no
  Parquet reader, and recipes found by the envelope's `source_sha`. The boundary review lists
  the producer tests behind the clauses above, and the index and the archive are regenerated.
  **No vector, digest or corpus byte moves.** Landed 2026-10-20.
- `v0-preview.3` — **Which policies a model values enters the record**, by ruling.
  Section 7.6 adds the optional envelope member `selection`: one entry per filter, semi join or
  anti join the model took, carrying its kind, its predicate's tree in both profiles, its
  reads, both its digests and, on a join kind, the right side's `right_fingerprint`.
  Section 12.4's `graph_fingerprint` and section 12.6's `formulas_fingerprint` gain a fourth
  section over the steps, **absent where there are none**; section 7.5's book columns gain the
  columns a step reads; section 8.1 reserves `selection:`; a replay applies the steps to the
  book before it projects, and the `executable` profile carries only steps a replay can make —
  a `core` predicate over book columns. Section 14.2's change report lists a step's movement
  among its calculations and gains `source`, the model file's own digests where they moved.
  The kit gains `vectors/selection.json` and the `selection-value` case class. **The token
  stays `gspv0-preview-3`**, as the ruling says: it is unreleased, and for every model that
  selects nothing — every shipped model — no digest moves, because the new section is absent;
  a document carrying `selection` is new and was never read under another rule. Before this
  line a selection moved no identity, and a replay valued the policies the model left out.
  Landed 2026-10-21.
- `v0-preview.3` — **A policy's figure is its own, whatever shares its run**, by ruling.
  Section 11.1.1 states the `maximum_age` horizon per policy: each policy runs
  `until_value − issue_age` whole years at a month-aligned cadence, the declaration states
  `issue_age_column` and a per-policy axis reads it, and the boundary list gains the count
  `T_i = max(0, trunc(A_i − x_i) × p)`; a shared grid, where one is asked for or the cadence is
  weekly or daily, is still sized from the youngest life. Section 11.1.37's `per_policy_grid`
  recipe states the age in one of three forms beside the issue-age column. Section 13.2 states
  that a producer refuses a read across rows wherever a run cuts the book into batches or
  carries a scenario axis, so a run record's per-policy figures do not move with `batch_size`,
  and section 11.2 points at it. **The token stays `gspv0-preview-3`** and the schema identifier
  does not move; a `maximum_age` model's projection node now reads its issue-age column, so its
  digests and values move once, to the values each policy has alone. The corpus of section
  12.5 holds no such horizon and is unchanged. Landed 2026-10-22.
- `v0-preview.3` — **Four smaller rulings, stated where they land.** Section 7 writes a file
  outside the root that shares no directory with it below the filesystem's root, or sits on
  another drive, as its name under `<outside the model's root>`, keeping a sibling directory's
  `..` climb, and section 7.3 says such an entry is `unavailable`; the schema's four path
  descriptions say the same. Section 10 says the reference producer reads an integer narrower
  than 64 bits as `i64` where it enters the frame. Section 11.1.25 answers `f64` for a
  per-policy Boolean under every operator, as it already did for a run. Section 11.1.34 is
  Excel's YEARFRAC: the answer does not depend on the order of the dates and is never
  negative, basis 0 applies the first of five adjustments that holds and only it, and basis 1
  divides a span inside one calendar year by that year's days, one ending within a year of the
  start by 365 or 366, and every other span by the mean year. Each is a behaviour change of
  the reference producer; **none moves `fingerprint_algorithm` or the schema identifier**. The
  kit's yearfrac vectors moved and one case was added. Landed 2026-10-22.
- `v0-preview.3` — **A leaf is checked from either profile, and the sentences around the
  record say what ships.** Section 13 lets a consumer of the `audit` profile recompute a
  leaf's `local_fingerprint` from its tag, name and type, as section 12.1 takes it, and the
  three hand-built examples — the supervisory annex's and section 17's two — are regenerated by
  their own generator, `bindings/python/tests/graph/test_hand_built_goldens.py`, so their
  thirteen leaves now carry those digests and every fingerprint, `graph_fingerprint` and seal
  in them follows from the file. Section 11.1.26 states list-shaped date comparisons, and the kit gains
  `vectors/list-dates.json`, three cases. Section 7 and section 13 say that a helper loaded by
  its path is on no `modules` list and that a verifier reports such a model's modules as a check
  that could not be made. Section 13.2 states that a model whose own records read
  `scenario_id` is composed alone over a one-scenario axis, and that `bases.source_file` is
  relative to the working directory rather than the model's root. **No identifier of the
  format moves**: nothing a producer writes changes, and the corpus of section 12.5 is
  unchanged; the three examples' own digests move, because they are now taken. Landed
  2026-10-22.
- `v0-preview.3` — **What the reference producer now does at five edges, stated where each
  lands.** Section 7.6 says a model whose only step is a selection is a document like any other,
  that a step may read a compiled rollforward's state and is then refused from the `executable`
  profile, and that a `filter` predicate answers once per policy — one with an answer per period
  is refused where it is written and records no step. Section 10 says a consumer reads a book's
  narrow integers as the `i64` the record names, as the producer does. Section 11.1.24 says an
  answer column of whole numbers or single-precision values is read as `f64`, so such a table
  and its `f64` twin are one content. Section 11.1.25 says a power whose exponent is written as
  an integer outside `[0, 2^32-1]` answers `f64`, and that a column exponent past that range is
  refused naming `to_float()`. Section 13.2 says `n_policies` counts the policies the model
  valued. Each is a behaviour change of the reference producer or its JAX engine; a filtered
  model's run record now states fewer policies, and **no identifier of the format moves**: the
  token stays `gspv0-preview-3`, the schema identifier is unmoved and the corpus of section 12.5
  is unchanged. Landed 2026-10-22.
- `v0-preview.3` — **The kit publishes an ordering over text.** Section 11.1.26 already ordered
  text by code point, per policy and per period; the kit gains `vectors/text-order.json`, five
  cases worked by hand that tell code-point order from a case-folded or collated one, a null on
  either shape among them. The JAX engine, which refused the four orderings over text, now
  answers them as the producer does. **No clause, digest or corpus byte moves.** Landed
  2026-10-22.
- `v0-preview.3` — **The supervisory annex's bases carry the digests their values hash to.** The
  annex example declared its curve under a placeholder digest its inlined values did not hash
  to, and named it after that digest; its generator now takes the curve's identity over the
  payload under the recipe grammar, `sha256:0483acfa…`, and the entry and the node reading it
  call it `curve:0483acfa`. Its mortality table was inlined in a form section 15 does not state,
  so no reader could check its digest; it is now written as the producer writes it — the
  processed frame's `columns` and `rows` — under its content hash. The example's graph
  fingerprint and seal move with them, and its deep reading finds no error. The label
  `curve:5c1f0a3d` in this log and in Annex A.2 is an instance of the naming form and stands.
  **No identifier of the format moves.** Landed 2026-10-22.
- `v0-preview.3` — **A shared grid sized from the rows is a read across rows, a window
  partitioned by the scenario is each scenario's own, and a maximum age needs a calendar
  cadence**, by ruling. Section 11.1.1 refuses a `maximum_age` horizon at a weekly or daily
  cadence, as it already refused a term there, and states that a shared grid whose length is
  read from the rows — `maximum_age` on one grid, a horizon named by a column or an expression
  collapsed onto one — is laid only where the frame is the whole book; its foot item 1 says what
  that holds fixed. Section 13.2 adds the grid to what a producer refuses wherever a run cuts the
  book into batches or carries a scenario axis, and admits, on a scenario axis whose policies are
  not cut into batches, a read inside a window partitioned exactly by the scenario column; section
  11.2 points at both. The line above for the per-policy `maximum_age` horizon described the shared
  grid and the weekly or daily cadence as still laid from the youngest life; that is superseded
  here. Each is a behaviour change of the reference producer: a model that ran now refuses, or
  one that refused now runs, and nothing it writes moves. **No identifier of the format moves**:
  the token stays `gspv0-preview-3`, the schema identifier is unmoved and the corpus of section
  12.5 is unchanged. Landed 2026-10-27.
- `v0-preview.3` — **Section 17's state-graph example carries the digests its values hash to.**
  Its two inlined tables, `di_incidence` and `di_occ_loading`, were row objects with no
  `columns` — not the inline payload section 15 states — under typed-in digests no reader could
  check. Each is now written as the producer writes it, the processed frame's `columns` and
  `rows`, under its content hash (`sha256:d39ce174…` and `sha256:bd877d7a…`), and the
  `table_fingerprint` each intensity inside the `state_graph` payload carries follows it. The
  example's graph fingerprint and seal move with them; every digest the file declares now
  recomputes, the two tables whose values the file leaves out apart. **No identifier of the
  format moves.** Landed 2026-10-27.
- `v0-preview.3` — **A book integer wider than `i64` is read by its values, by one rule at both
  doors, and a window whose partition includes the scenario is admitted**, by ruling. Section 10
  states that a `UInt64`, `Int128` or `UInt128` column whose every value fits is read as `i64` by
  the producer and by a consumer, as a narrow one is widened, and that one holding a value past
  that range keeps its width — `to_text` and `to_integer` treat it as sections 11.1.39 and
  11.1.23 publish — while arithmetic on it is refused by name, never wrapped; a book handed over
  as a plan is judged when it runs, and a batched run judges the book once. This replaces section
  10's permission to refuse such a column by its width alone; the earlier line saying a consumer
  reads a book's narrow integers as the producer does stands, and now covers the wide ones that
  fit. Section 11.1.25 points at the rule. Section 13.2 admits, on a scenario axis whose policies
  are not cut into batches, a read inside a window whose partition includes the scenario column
  with further keys, where the line above admitted one partitioned exactly by it; that wording is
  superseded. Each is a behaviour change of the reference producer and its JAX engine: a model
  whose arithmetic wrapped on such a column now refuses, a book whose wide column fits now runs
  on the JAX engine and digests as the `i64` book it is read as, a results file carries `Int64`
  where it carried `UInt64`, and a window over the scenario and another key that refused now
  runs. The five wide-integer conversion vectors of `vectors/conversions.json` are unchanged.
  **No identifier of the format moves**: the token stays `gspv0-preview-3`, the schema identifier
  is unmoved and the corpus of section 12.5 is unchanged. Landed 2026-10-28.
- `v0-preview.3` — **A whole-number literal past `i64` is refused, and every read that computes
  in a wide column's width is refused as arithmetic on it is.** Sections 10 and 12.1 state the
  literal range; section 10 extends the wide-integer refusal to the sums, running folds, signed
  absolute value and rollforward operands, and states that a plan's arriving wide column is
  judged when collected. Behaviour changes of the reference producer: a literal past `i64` that
  answered null now refuses where written; `2 ** af.n` answers `i64`; those folds refuse where
  they wrapped; a lazily handed fitting wide column comes back `Int64`. The JAX engine's literal
  refusal names section 10 and the two moves. **No identifier of the format moves.** Landed
  2026-10-28.
- `v0-preview.3` — **A whole-number literal is an `i64` wherever it stands, a total of whole
  numbers is exact, a Float64 period operation widens a whole-number run on the record, a whole
  number keeps its significant figures exactly, and every read that answers in a wide column's
  type takes it as `i64` from both doors.** Section 10 states that a column a whole-number
  literal alone types is the `i64` the record names, and widens the wide-integer rule from the
  folds to every read that answers in the column's type — a least or greatest value, a bound, a
  rounding, a sign, a fill, a period's value or a shift, an absolute value of either signedness,
  significant figures — so a book handed over as a plan answers the type a DataFrame does, and
  a column past `i64` is refused by any of them on both doors.
  Section 11.1.12 states that `round_sig_figs` keeps a whole number's figures in whole-number
  arithmetic; sections 11.1.19 and 11.1.21 state that a whole-number operand reaches the record
  inside `to_float`, as 11.1.20 already stated for `accumulate`; section 13.2 states that a sum of
  an `i64` column is the book's exact total and refuses one past `i64`. Behaviour changes of the
  reference producer: `af.c = 5` and a conditional of whole-number branches are `Int64` where they
  were `Int32`, and arithmetic on them no longer wraps at 2,147,483,647; `run_aggregated`'s `Sum`
  of an integer column is exact at every batch size and refuses a total past `i64`;
  `previous_period()`, `next_period()` and `at_period()` under the `0.0` default record their
  widening, so their record states `list[f64]` where it stated `list[i64]` over doubles, and the
  JAX engine runs them; `round_sig_figs` of a whole number answers 800000 for 781098 at one
  figure where it answered 799999, on both engines and in the reference reader; a least or
  greatest value, a fill or another such read of a column past `i64` refuses where it answered in
  the wide type. **No identifier of the format moves**: the token stays `gspv0-preview-3`, the
  schema identifier is unmoved and the corpus of section 12.5 is unchanged. Landed 2026-10-29.
- `v0-preview.3` — **A per-period total of whole numbers is exact, and a double keeps the
  figures of its exact value.** Section 13.2 extends the exact total to every period of a
  per-period total, and to a scenario's total at a period that a per-period statistic reads; a
  refusal there names the period and, within a scenario, the scenario. Section 11.1.12 states
  that a double's significant figures are those of the number it is, the answer the double
  nearest the decimal they leave, and that at seventeen figures or more a double is its own
  answer. Behaviour changes of the reference producer and its JAX engine: `PeriodSum` of an
  integer column is exact at every batch size and refuses a period's total past `i64` where it
  wrapped; on the scenario axis a scenario's per-period total past `i64` is refused under every
  per-period kind; `round_sig_figs` of a double answers 800000.0 for 781098.0 at one figure where
  it answered 799999.9999999999, and 0.1 for 0.15 where it answered 0.2, for up to fifteen
  figures wherever the power of ten is a double. The reference reader answers so at every
  magnitude, and its archive is rebuilt. **No identifier of the format moves**: the token stays
  `gspv0-preview-3`, the schema identifier is unmoved, no published vector's expected value
  changes and the corpus of section 12.5 is unchanged. Landed 2026-10-29.
- `v0-preview.3` — **Every statistic of whole numbers is read from exact totals.** Section 13.2
  extends the exact total to a mean, a variance and a standard deviation of an `i64` column,
  per policy and per period, on both axes: each is read once from the exact count, total and
  total of squares, and none moves with the batch size; and it states that a quantile, a median
  or a tail expectation reads each value as the double nearest it. Behaviour changes of the
  reference producer and its JAX engine: `PeriodMean` of 2**62 and 2**62 answers 4.6e18 at
  every batch size where it answered -4.6e18 two a batch; `Mean` of 2**63 − 1, −2**63 and 5
  answers 4/3 where it answered 1.67, or 0.0 under `"auto"`; `Variance`, `Std`,
  `PeriodVariance` and `PeriodStd` of 2**53 + 1, + 2, + 3 and + 5 answer 35/12 and its root
  where they answered 5.22, 6.67 or 3.67 by batch; and `PeriodMedian`, `PeriodQuantile` and
  `PeriodCTE` of −2**63 answer −9.2e18 where they answered +9.2e18. **No identifier of the
  format moves**: the token stays `gspv0-preview-3`, the schema identifier is unmoved, no
  published vector's expected value changes and the corpus of section 12.5 is unchanged.
  Landed 2026-10-29.
- `v0-preview.3` — **A null branch takes the other branch's type, a selection keeps the
  value it selects, and a scenario's mean of whole numbers is exact.** Section 11.1.28 states
  that a null branch carries no type, so a conditional's output is the other branch's type;
  that a producer selecting in doubles selects a whole number past `2^53` without loss; and
  that a null branch, having no literal in this preview's tree, is an engine-native fragment a
  core-only consumer refuses by name. Section 13.2 states that a scenario's `within="mean"` of
  an `i64` column is read from its exact total and count, and that its other reductions are
  exact. Behaviour changes of the reference producer: `when(month > 0).then(None).otherwise(k)`
  over a `list[i64]` run answers `list[i64]` where it answered `list[f64]`, and beside a flag,
  date or text run the run's own type where it answered 0.0/1.0, day counts or a refusal; a
  per-period conditional of 64-bit whole numbers holds `2^53 + 1` where it held `2^53`, and
  `2^63 - 1` where it failed to collect, so it now answers what the JAX engine answers; two
  per-period date branches answer dates where they answered day counts; and a scenario's
  `within="mean"` of `2^63 − 1`, `−2^63` and `5` is `4/3` where it was `5/3`. **No identifier
  of the format moves**: the token stays `gspv0-preview-3`, the schema identifier is unmoved,
  no published vector's expected value changes and the corpus of section 12.5 is unchanged.
  Landed 2026-10-29.
- `v0-preview.3` — **A `datetime` pair answers a `datetime`, two null branches carry no
  type, and a selection keeps every bit at every width.** Section 11.1.28 adds two `datetime`
  to its bounded branch pairs, answered in the unit and zone the two share, with a pair of no
  shared type (a zone-naive value opposite a zoned one) refused by name where the line is
  written, and a consumer carrying no `datetime` refusing the column by its type; states that
  two null branches carry no type, which section 10 refuses at export; and states that a
  `datetime` keeps its last unit through a selection. Behaviour changes of the reference
  producer: two per-period `datetime` branches answer `list[datetime]` in their unit and zone
  where they answered `list[f64]` counts, which lost a nanosecond count's last digits, and
  the record says `list[datetime]` where it said `list[f64]`; a `None` beside a `datetime`
  run takes its type; `when(month > 0).then(None).otherwise(None)` answers a run of nulls of
  no type, refused at export as the per-policy form is, where it answered and recorded
  `list[f64]`; a 128-bit whole number is selected exactly past `2^85`, where it lost its low
  bits, and an unsigned one where the kernel panicked; a duration, a time of day, a decimal
  and a Categorical or Enum pair answer their own type where they answered doubles or text;
  a zone-naive and a zoned `datetime`, or a Categorical and an Enum, are refused by name on
  both routes where the per-policy route failed when the frame ran and the per-period route
  answered; and an unsigned value past `i64` beside an `i64` run fails by its value where it
  answered a null. The JAX engine refuses a `datetime` book column as one it does not carry,
  where it told the author to cast the column to the type it already was. **No identifier of
  the format moves**: the token stays `gspv0-preview-3`, the schema identifier is unmoved, no
  published vector's expected value changes and the corpus of section 12.5 is unchanged.
  Landed 2026-10-29.
- `v0-preview.3` — **A pair of two time units answers the finer, and a flag beside a whole
  number answers a double.** Section 11.1.28 states that a `datetime` pair answers in the zone
  the two share and the finer of their two units, a value the finer unit cannot hold refused
  by name at the run; adds a `bool` beside an `i64` to its bounded branch pairs, answering
  `f64` with the flag read as its 0.0/1.0 indicator; and names that pair in its output-type
  sentence. Section 11.1.25 states that a conditional reads a flag beside a whole number as
  arithmetic does. Behaviour changes of the reference producer: `when(x > 2).then(us)
  .otherwise(ms)` over a microsecond and a millisecond `datetime` answers microseconds where it
  answered milliseconds and dropped the microsecond branch's last three digits, and a literal
  beside a nanosecond column answers nanoseconds where it answered microseconds, per policy
  and per period; two durations likewise; a value outside the finer unit's range (9999-12-31
  beside a nanosecond column) is refused by name where it was answered in the coarser unit;
  and `when(x > 2).then(True).otherwise(n)` answers and records `f64` per policy where it
  answered and recorded `i64`, as it already did per period, a column stored wider than `i64`
  beside the flag read as arithmetic reads one (refused by name past `i64`, where the per-policy
  form kept its width and the per-period form rounded it). The JAX engine answers the flag
  pair as `f64` inside its own arithmetic, where it computed it in `i64` and settled it to the
  record only at the node, so a whole number past `2^53` beside a flag is refused there by
  name, as under `flag + n`. **No identifier of the format moves**: the token stays
  `gspv0-preview-3`, the schema identifier is unmoved, no published vector's expected value
  changes and the corpus of section 12.5 is unchanged. Landed 2026-10-29.
- `v0-preview.3` — **A double's significant figures are the fifteen a spreadsheet holds.**
  Section 11.1.12 states that `round_sig_figs` reads an `f64` value as its
  fifteen-significant-digit decimal, a sixteenth digit of 5 or more going away from zero, as
  section 11.1.35 reads an operand of `excel.round`, rounds that decimal to its figures with a
  half away from zero, and answers the double nearest the result, so that from fifteen figures
  up the answer is the fifteen-digit value; that a whole number keeps every digit it has; and
  that the figures are exact from `10^(digits − 23)` (`10^−8` at fifteen figures or more) to
  below `10^37`, where a finite value outside is refused by name on both engines while the
  reference reader answers it. The exact-value reading that a 2026-10-29 line above records
  is withdrawn. Behaviour changes of the reference producer, its JAX engine and the reference
  reader: 0.15 to one figure answers 0.2 where it answered 0.1; 0.285 to two answers 0.29,
  2.675 to three 2.68 and 1.005 to three 1.01, where they answered 0.28, 2.67 and 1.0;
  0.30000000000000004 to seventeen figures answers 0.3 where it answered itself; and a value
  outside the range is refused by name where it was rounded through binary64 scaling. The
  reference reader's archive is rebuilt. **No identifier of the format moves**: the token stays
  `gspv0-preview-3`, the schema identifier is unmoved, no published vector's expected value
  changes and the corpus of section 12.5 is unchanged. Landed 2026-10-29.
- `v0-preview.3` — **Per-period comparisons are exact.** Section 11.1.26 withdraws its exclusion
  of list comparisons past `2^53`: two `i64` operands compare exactly over the full signed-i64
  range per period as per policy, and two `datetime` operands compare as instants to their last
  unit; a mixed `i64`/`f64` comparison keeps its stated range. It states that a zone-naive
  `datetime` against a zoned one is refused by name, and that a column still wider than `i64`
  is outside the portable domain and compared exactly by a producer that keeps one, a literal
  past `i64` admitted against it and nowhere else. Behaviour changes of the reference producer:
  `k > 2^53` over a run holding `2^53 + 1` answers 1.0 in every period where it answered 0.0,
  `2^63 - 1 == 2^63 - 2` per period answers 0.0 where it answered 1.0, and a nanosecond date and
  time or duration one unit after another compares later where it compared equal; a per-period
  `datetime` against one in another unit is compared in the finer unit where the two counts were
  compared as raw numbers; a zoned `datetime` against a zone-naive one is refused where the line
  is written where it failed when the frame ran; `pid == 2**64 - 1` against a `UInt64` column
  past `i64` answers where it was refused, and `pid > 7` there answers 1.0 where it answered
  null; and `replace` and `cut` over such a column read it as `Int64` where it fits, from either
  door, and refuse by name past it. The JAX engine compares a per-period `i64` run past `2^53`
  where it refused it. **One published vector's expected answer moves**:
  `comparison-large-integer-list` (`[2^53 + 1] == 2^53` per period) is a value case answering
  `[[0.0]]` where it was a portable-domain refusal, and the reference reader answers it so. The
  token stays `gspv0-preview-3`, the schema identifier is unmoved and the corpus of section 12.5
  is unchanged. Landed 2026-10-29.
- `v0-preview.3` — **Two time units compare in the finer, and a comparison is never decided by
  an unread type.** Section 11.1.26 states that a pair of `datetime` (or duration) operands in
  two units compares in the finer unit, per policy as per period, refusing no value for its
  unit; that a producer refuses by name a per-period comparison whose operand type it cannot
  read; and that a decimal held to fixed places, outside the vocabulary, is compared exactly
  by a producer that keeps one. Section 10 states where a literal past `i64` is admitted (the
  other operand of a comparison or membership test on a column still wider than `i64`), that
  a substitution and a band refuse such a column, and that a record written from a plan names
  a column the book arrived with on its values. Behaviour changes of the reference producer:
  a nanosecond `datetime` one unit after a microsecond one compares later per policy where it
  compared equal; two zoned `datetime` columns in different zones compare per policy where
  Polars refused them; two decimals a double cannot tell apart compare exactly per period
  where they compared equal, and per policy answer where one common decimal type could not
  hold both and answered null; `af.k > (2^53, 2^53)` answers 1.0 for a run holding `2^53 + 1`
  where it answered 0.0, and a formula built with no frame is decided by the frame it is
  assigned to; `af.c = 2**64` is refused in the literal's sentence; a book handed over as a
  plan whose `UInt64` column fits exports its leaf as `i64` where it was refused on its width,
  and a value past `i64` in a book column is refused naming the value from either door. **No
  identifier of the format moves**: the token stays `gspv0-preview-3`, the schema identifier
  is unmoved, no published vector's expected value changes, and the corpus of section 12.5 is
  unchanged. Landed 2026-10-29.
- `v0-preview.3` — **`round` reads a double as its fifteen figures, and outside the exact range
  both rounding operations answer by the engine's native route.** Section 11.1.8 states that
  `round` reads an `f64` value as its fifteen-significant-digit decimal, a sixteenth digit of 5
  or more going away from zero, moves that decimal to its places under its tie rule and answers
  the double nearest the result, an `i64` value answering itself; that this is exact for every
  value below `10^37` at up to 22 places; and that outside that range an engine may answer by
  its native rounding while the reference reader stays exact and refuses an answer past the
  largest double. Section 11.1.12 replaces its refusal outside the exact range with the native
  route, and states how far that route may sit from the reading. Section 11.1.28 states that the
  reference producer reads a flag beside an engine's fixed-point decimal as a double. Behaviour
  changes of the reference producer, its JAX engine and the reference reader: `round` of 0.285
  and 1.005 to two places away from zero answers 0.29 and 1.01 where it answered 0.28 and 1.0,
  68049.31499999999 answers 68049.32 under either rule where it answered 68049.31, and the
  reader's 2.675 to the even neighbour answers 2.68 where it answered 2.67; `round_sig_figs`
  of a value outside its exact range — 3e-24 to one figure — is answered where it was refused;
  the JAX engine's `round` of a value whose scaling overflows answers the value where it
  answered infinity; the reference reader types a flag beside an `i64` in a conditional `f64`
  where it took the then branch's type, and refuses the pair past `2^53`; and the reference
  producer answers a flag beside a fixed-point decimal per policy where its engine refused the
  pair. The reference reader's archive is rebuilt. **No identifier of the format moves**: the
  token stays `gspv0-preview-3`, the schema identifier is unmoved, no published vector's
  expected value changes and the corpus of section 12.5 is unchanged. Landed 2026-10-29.
- `v0-preview.3` — **A selection between decimals keeps them, an `i64` past the exact range
  beside an `f64` is refused by the reference reader, and a comparison is an indicator on either
  side of arithmetic.** Section 11.1.28 states that two of an engine's fixed-point decimals, or
  one beside a whole number, answer in the decimal type the engine gives the pair, each value
  selected exactly, and a value that type cannot hold is refused by name; and that an `i64` past
  the exact range beside an `f64` is outside the entry, refused by a consumer over every value
  of both branches. Section 11.1.26 states that a comparison in arithmetic is its indicator on
  either side of the operator. Behaviour changes of the reference producer: a per-period
  selection between decimals held to `s` places answers the decimals where a value with
  `38 - 2s` whole digits or more answered null (from 0.01 at twenty places), and a value the pair's
  decimal type cannot hold is refused in the framework's sentence where Polars refused it in its
  own; `(age > 60) * 1.0`, `1 - (age > 60)` and `-(age > 60)` answer the indicator where they
  raised a type error at the line; an input leaf whose name a later line took over, or whose
  column was renamed or dropped, is typed as the data arrived, a book handed over as a plan
  naming such a column on its values. The reference reader refuses
  `when(c).then(k).otherwise(x)` with `k` past `2^53` where it answered the rounded double, and
  its archive is rebuilt. **No identifier of the format moves**: the token stays
  `gspv0-preview-3`, the schema identifier is unmoved, no published vector's expected value
  changes, and the corpus of section 12.5 is unchanged. Landed 2026-10-29.
- `v0-preview.3` — **A comparison compared is a flag compared, and `abs` of a flag is refused.**
  Section 11.1.26 states that a comparison which is an operand of a comparison supplies its
  indicator, per policy and per period, and is compared against a Boolean as that Boolean's 0
  or 1; section 11.1.25 states that `abs` is not among its operators and is refused over a
  Boolean or a comparison; section 10 states that the leaf of an arriving column whose name a
  later line took over is typed as the field arrived. Behaviour changes of the reference
  producer: `(age > 60) == 1` and the other comparisons on a comparison answer the comparison
  where they answered the host language's own `False` or `True`, or raised its type error, and
  per period answer the indicator where the frame failed when it ran; `abs` of a flag or a
  comparison, and `round_sig_figs` keeping fewer than one figure, are refused where they are
  written. The reference reader reads a stored Boolean operand of arithmetic as its 0 or 1
  where it refused it, refuses a per-policy Boolean on both sides of one operation, and refuses
  `abs` of a Boolean and `round_sig_figs` keeping fewer than one figure where it answered them;
  its archive is rebuilt. **No identifier of the format moves**: the token stays
  `gspv0-preview-3`, the schema identifier is unmoved, no published vector's expected value
  changes, and the corpus of section 12.5 is unchanged. Landed 2026-10-29.
- `v0-preview.3` — **`round` with a negative `decimals` rounds to tens, hundreds and coarser.**
  Section 11.1.8 defines `round(decimals=-n)`, which it had left undefined, as rounding to a
  multiple of `10^n` under both tie rules, the record carrying the negative count as written: a
  double read as its fifteen-significant-digit decimal and moved to the step, a whole number
  moved exactly in whole numbers and refused by name where the answer is outside `i64`; it
  states the exact range (`decimals` from -22 to 22, below `10^37`), the native scaling past 22
  places to the left, written as three products, the type limits (from `10^19` for an `i64`,
  from `10^309` for a double, where every finite value answers a nought of its sign), and that
  `round` under `half_away_from_zero` answers what `excel.round` answers inside section 11.1.35's
  entry, a whole number differing only in type. Behaviour changes: the reference producer
  rounds a whole number to tens where it raised its host language's `OverflowError` at the
  line, refuses an answer past `i64` and an engine's fixed-point decimal by name, answers the
  native scaling past 22 places to the left where it answered the reading below `10^37` and the
  value itself from it, and answers a nought past `10^308` where it answered the value, or
  raised a division by zero to the even neighbour; its JAX
  engine answers the operation where it refused the record by name, and keeps the sign of a
  value below the least normal double, which it answered as `+0.0`; the reference reader rounds
  a whole number to tens where it answered it unmoved, and refuses one past `i64`. The
  conformance kit gains nine cases in `boundaries.json` (eight values, one refusal), 710
  published; `index.json`, `boundary-review.json` and the reference reader's archive are
  rebuilt. **No identifier of the format moves**: the token stays `gspv0-preview-3`, the schema
  identifier is unmoved, no published vector's expected value changes, and the corpus of
  section 12.5 is unchanged. Landed 2026-10-29.
- `v0-preview.3` — **The calls that read a number read a flag as its 0.0 or 1.0.** Section
  11.1.25 states that `abs`, `sign`, `sqrt`, `cbrt`, `exp`, `log`, `log10`, `log1p`, `norm_cdf`,
  `round_sig_figs`, `round`, `floor` and `ceil` over a Boolean or a comparison read it as its
  0.0/1.0 and answer `f64`, per policy and per period, withdrawing the sentence that put `abs`
  outside the reading; section 11.1.12 states the reading for its ten, that `log` and `log10` of
  0.0 are `−∞`, and that `digits` is at least one; section 11.1.27 states that a logical result
  is read so by those calls, and that `^` is no operation of the vocabulary. Behaviour changes:
  the reference producer answers `sign`, `floor`, `ceil`, `round`, `round_sig_figs` and
  `norm_cdf` of a flag where they failed when the frame ran, `abs` of one where it was refused,
  and all thirteen over a per-period comparison where they failed, and a comparison carries
  those thirteen methods; its JAX engine answers them over a Boolean where it refused the
  record by name; the reference reader types the answer `f64` where it typed nine of them
  `bool`, answers `abs` where it refused it, and answers `−∞` for the logarithm of 0.0 where
  it raised. The conformance kit gains 26 cases in `boundaries.json`, 736 published;
  `index.json`, `boundary-review.json` and the reference reader's archive are rebuilt. **No
  identifier of the format moves**: the token stays `gspv0-preview-3`, the schema identifier is
  unmoved, no published vector's expected value changes, and the corpus of section 12.5 is
  unchanged. Landed 2026-10-29.
- `v0-preview.3` — **A whole number is answered in whole numbers, and in the type the record
  names.** Section 11.1.12 states that `abs` and `sign` keep an `i64` exactly, that the
  absolute value of `−2^63` is outside the portable domain, and that `sqrt`, `cbrt`, `exp`, `log`,
  `log10` and `log1p` answer `f64` over an `i64`; sections 11.1.9 and 11.1.14 state that
  `cum_sum`, `cum_prod` and `sum` over an `i64` run are exact and that a period or a total
  outside `i64` is outside the portable domain; section 11.1.15 states that `mean` answers
  `f64`. Behaviour changes: the reference reader types those six maths calls and `mean` over a
  whole number `f64` where it typed them `i64`, answers `fill_null` of a whole number with a
  double as `f64` where it typed it `i64`, takes `floor`, `ceil`, `abs`, `sign`, `sum`,
  `cum_sum`, `cum_prod` and `remaining_sum` over an `i64` in whole numbers where it went through
  doubles and lost digits past `2^53`, keeps `round_sig_figs`' sign in whole numbers, so `2^62`
  to seventeen figures is rounded and `2^63 − 1` to seventeen figures answered where it was
  refused, refuses a whole-number answer past `i64` by name where it answered a double, refuses
  a whole number past `2^53` meeting a double fill, holds every value as the type its label
  names, and fails a case whose answer is held as another type than its label. The reference
  producer and the JAX engine are unchanged. The conformance kit publishes no new case, 736
  published; the reference reader's archive is rebuilt. **No identifier of the format moves**:
  the token stays `gspv0-preview-3`, the schema identifier is unmoved, no published vector's
  expected value changes, and the corpus of section 12.5 is unchanged. Landed 2026-10-29.
- `v0-preview.3` — **A verifier holds a hole open, and the reference producer's batch doors
  answer as one run over the book.** Section 13 states that a verifier asked about a
  document's inputs reports a non-empty holes section as a check that could not be made,
  naming each hole, and that a document recording no assumption table agrees under an
  assumption check; section 12.4 states that a hole reaches the graph fingerprint by name
  only. Section 11.1.1 states that a frame with no rows lays an axis of no periods, that a
  jagged axis whose every horizon is null does too, that a shared grid sized from rows all
  null is refused, and that a consumer inspecting a document refuses an axis the record does
  not fix before any book is read; section 11.1.37 states the same of an anchor outside its
  domain. Section 13.2 states that a filter's condition reading across rows is refused where
  an assignment's read is, that a column a shock widens is written at one type in every
  batch, and that a scenario's shocked table is read under the name the model gave it, so an
  identity shock leaves BASE's figure. Section 11.1.19's sentence on `to_float` names the
  interval it refuses outside. Behaviour changes: the reference producer's verifier holds a
  holed document open (exit 4) where it agreed, and agrees under `--assumptions` over a
  document with no table where it held the check open; the reference producer runs a frame
  a filter emptied, in collect and in every batch door, where it failed with a host-language
  type error, refuses a cross-row filter condition in a batch of several and on a scenario
  axis where it answered from the batch's rows, writes a widened column at one type in
  every batch file, and stamps a scenario that reads a shocked table by the table's own
  name; its JAX engine's inspection refuses the month-end anchor and the unfixed axis it
  refused only when run. **No identifier of the format moves**: the token stays
  `gspv0-preview-3`, the schema identifier is unmoved, no published vector's expected value
  changes, and the corpus of section 12.5 is unchanged. Landed 2026-10-29.
- `v0-preview.3` — **The producer computes in the type the record names, a policy with no run is
  null on either side, and a per-period fold or clip of whole numbers keeps them.** Section 10
  states that the reference producer reads a `Float16` or `Float32` column as `f64` where it
  enters the frame, and lists the maths calls and a conditional's branch among the reads that
  refuse a column still wider than `i64`; section 11.1.18 states that a null list is a policy
  with no periods on either side of a binary operation or a comparison, and sections 11.1.26
  and 11.1.28 that a comparison, and a conditional on it, with a null outer list on either side
  is null; section 11.1.3 states that `clip` keeps the value's own type whatever its bound;
  section 11.1.13 that a fill that reads a column fills each period one value at a time;
  sections 11.1.9, 11.1.12 and 11.1.14 that the producer refuses a fold or an absolute value
  past `i64` by name; section 11.1.28 that a flag beside a double answers `f64`. Behaviour
  changes, in the reference producer: a single-precision column is computed in doubles; a
  per-period comparison with a null run on its right answers null for the policy where it
  answered a run of nulls; a per-period `sum`, `cum_sum`, `cum_prod` or `remaining_sum` past
  `i64` and the absolute value of `−2^63` are refused by name where they wrapped; a run of
  flags totals to `i64` where it answered an unsigned type; a per-period clip of whole numbers
  by a column's bound answers `list[i64]` where it answered `list[f64]`, and refuses a value
  past `2^53`; `fill_null` by a column fills each missing period where it filled only a policy
  with no run; the numeric calls refuse text, dates and times by name; a flag beside a double
  is typed `f64` before the run; and an executable record of a plan whose schema cannot be
  resolved is refused where it was written untyped. The JAX engine reads a narrow float book
  column as `f64` where it refused the book. The reference reader is unchanged. The conformance
  kit publishes no new case. **No identifier of the format moves**: the token stays
  `gspv0-preview-3`, the schema identifier is unmoved, no published vector's expected value
  changes, and the corpus of section 12.5 is unchanged. Landed 2026-10-30.
- `v0-preview.3` — **A stored comparison is its indicator whatever it compares, a null run anywhere
  in a conditional nulls the policy, and a whole number keeps its digits at the edges.** Section
  11.1.26 states that a comparison read by a call that reads a number supplies its indicator, and
  that a comparison of a table lookup, a mortality or a curve read, stored, is the `f64` indicator
  a comparison of a column is; section 11.1.28 that a null outer list anywhere in a conditional —
  its condition, either branch, selected or not, any case of a chain — makes the policy null;
  section 11.1.8 that `floor`, `ceil` and `round` of a flag answer `f64`, and `floor` and `ceil`
  of an `i64` the `i64` itself; section 11.1.13 that an `i64` past `2^53` meeting an `f64` fill
  is outside the portable domain, where a producer may answer its nearest double and a
  consumer may refuse it; section 11.1.20 that `remaining_sum` over an `i64` run answers `list[i64]`.
  Behaviour changes, in the reference producer: a per-policy lookup comparison is stored as
  `f64` where it was stored `bool`; a conditional with a null run in a branch answers null for
  the policy where it answered the other branch's values; arithmetic between a number and text,
  a date or a run of an engine's decimals is refused where it is written, where it failed in the
  engine's words when the frame ran. The JAX engine's disclosures say that a comparison, `sign`
  and `cbrt` of a value below the least normal double can differ from the producer's, and that
  it refuses a whole-number total whose running total passes `i64`. The reference reader is
  unchanged. The conformance kit publishes 28 more cases (764). **No identifier of the format
  moves**: the token stays `gspv0-preview-3`, the schema identifier is unmoved, no published
  vector's expected value changes, and the corpus of section 12.5 is unchanged. Landed
  2026-10-30.
- `v0-preview.3` — **A hole the frame arrived holding carries the stamp of its values, and a
  run cut into batches judges a frame the model rebuilt.** Section 7.1 adds the holes
  section's `content` member: on a `rebuilt` hole and an `unrecorded` name the policy data
  never had, the content hash of that column as it arrived; on no other hole. Section 12.4's
  third section folds each hole's name followed, in the same entry, by its `content` where it
  has one; section 12.6 keeps names alone. Section 13.2 states that a run cutting the book into
  more than one batch refuses a frame the model builds from a table that is not the batch's
  own, judges one built from a plan on the plan, and takes each record told the book's columns.
  Behaviour changes, in the reference producer: `run_aggregated` and `run_to_parquet` refuse,
  in a batch of several, a frame built from a DataFrame holding a column the batch did not
  hold, a changed batch column or other rows, and a plan that reads across rows, where they
  answered from the batch; the batch runners and scenario plans tell the record the book's
  columns, so a column a setup step made is a hole in their records as on the command line;
  and every document with an arriving hole moves its `graph_fingerprint` once. The schema
  admits `content` on a hole. **No identifier of the format moves**: the token stays
  `gspv0-preview-3`, the schema identifier is unmoved, no published vector's expected value
  changes — none carries a hole — and the corpus of section 12.5, which has no holes, is
  unchanged. Landed 2026-10-30.
- `v0-preview.3` — **The change report names a hole whose stamp moved, the book's fold is taken
  whole, and the edges past `2^53` are stated.** Section 14.2's `data` gains a seventh kind,
  `hole`: a hole both documents list whose `content` stamp differs is an entry with the two
  stamps, and one stamped on one side only is written with a `reason`, each drift, so an edit to
  a file the setup joined is no longer reported as nothing moved over two different
  `graph_fingerprint`s. Section 7.4 states that the reference producer takes the book's own fold
  as one batch. Section 11.1.12 states that the maths calls over an `i64` past `2^53`, and
  section 11.1.15 that `mean` over a run holding one, are outside the portable domain, where a
  producer may answer the nearest double and a consumer may refuse; section 11.1.25 that a
  number beside a duration is refused where the line is written, except where the engine scales
  the duration; section 11.1.26 that a lookup's comparison stored through a batch door under its
  name is the same indicator. Behaviour changes, in the reference producer: `gspio diff` reports
  a moved hole stamp as drift where it said nothing moved; `gspio calc-graph --portfolio` folds a
  setup that rebuilt its frame, where it was refused on any book the memory budget cut; a line
  after a fragment Polars cannot type is typed by what the model wrote, where it read the
  schema from before the fragment; duration arithmetic Polars refused is refused at the line;
  a lookup comparison named with `alias` in `with_columns` or `select` is stored. The JAX engine
  answers `sum`, `mean`, `cum_sum`, `cum_prod` and `remaining_sum` over a run of flags, and
  `remaining_sum` over a run of whole numbers in whole numbers, where it refused them. The
  report grammar stays `gaspatchio-graph-diff/v0-preview.2`, no report having been published
  under it. **No identifier of the format moves**: the token stays `gspv0-preview-3`, the schema
  identifier is unmoved, no published vector's expected value changes, and the corpus of section
  12.5 is unchanged. Landed 2026-10-30.
- `v0-preview.3` — **The change report states the helper modules that moved and names the hole
  under a moved line, and a run of flags has a least and a greatest.** Section 14.2's `source`
  gains `modules`: each helper module whose `model.modules` fingerprint differs, or which only
  one document lists, paired by its path relative to its own document's model file, as
  `{path, before, after}`; `source` is written where the model file or a helper moved, its
  `before` and `after` equal where only a helper did, and it stays stated and never counted.
  A `values` line gains `holes`, and `cause` gains `hole`: a line whose definition held and whose
  numbers moved, reading a hole whose stamp the `data` entries show moved, names the hole, the
  book still outranking it. Sections 11.1.16 and 11.1.17 state that `min` and `max` answer one of
  the periods' own values in their type, a run of flags answering `bool`; section 10 that a call
  reading a number out of a duration is refused where it is written. Behaviour changes, in the
  reference producer: `gspio diff` prints a line per helper module that moved, and a hole cause
  where it printed `unexplained`; `projection.set`, `select`, `rename` and `drop` after a fragment
  Polars cannot type raise that fragment's break naming its line, with a note that the door was
  not run, where they raised it in Polars' words naming none; the maths calls but `abs`,
  `cum_prod` and `cumulative_survival` over a duration are refused at the line. The JAX engine
  answers `min` and `max` over a run of flags where it refused them. The comparison page gains
  the `hole` kind, the hole cause and the model's own files. The report grammar stays
  `gaspatchio-graph-diff/v0-preview.2`, no report having been published under it. **No
  identifier of the format moves**: the token stays `gspv0-preview-3`, the schema identifier is
  unmoved, no published vector's expected value changes, and the corpus of section 12.5 is
  unchanged. Landed 2026-10-30.
- `v0-preview.3` — **A run's figures are the book's on three more paths.** Section 13.2 states
  that a function written in the host language and handed to the engine is refused wherever a
  read across rows is, whatever it declares, and a compiled extension function not declared
  elementwise is such a read; that a column injected wholesale is refused where a run cuts the
  book, and anywhere its length is not the row count of the frame it lands on; and that a run
  of one policy taken from the book is such a cut, which the reference producer answers by
  running the whole book, selecting the policy and saying so. Behaviour changes, in the
  reference producer: `map_batches`, `map_elements`, `rolling_map` and a plugin registered
  with `is_elementwise=False` are refused in a batch of several and on a scenario axis where
  they answered from the batch's rows; an injected `Series`, array, `lit(Series)` or fixed
  `int_range` is refused there and wherever its length is not the frame's, where a batch of
  one paired it with every policy and a one-row frame was repeated to its length;
  `gspio run-single-policy` and `runner.run_single_policy` run the policy alone under that
  rule and, where it refuses, the whole book with the policy selected, where they ran one row
  and answered a cross-row model's figure over that row; the exact roundings hold their
  operand once, so a rounding of a rounding answers. **No identifier of the format moves**:
  the token stays `gspv0-preview-3`, the schema identifier is unmoved, no published vector's
  expected value changes, and the corpus of section 12.5 is unchanged. Landed 2026-10-31.
- `v0-preview.3` — **An engine's fixed-point decimal is read as the number it denotes where it
  enters.** Section 10 states that the reference producer reads a `Decimal` column, or a list of
  one, as the `f64` nearest each value where it has places and as the whole number it is where
  it has none, at the book, a join, a table's answer column, a column handed in whole and a
  literal, and that the book's digest reads that value. The fixed-point sentences of sections
  11.1.8, 11.1.26 and 11.1.28 are struck: no operation meets such a decimal. Behaviour changes
  of the reference producer and its JAX engine: a `Decimal` book is exported, run and verified
  where it was refused at export; `1000.00 / 12` answers 83.33333333333333 where it answered
  83.33, and `round_sig_figs` of 0.05 to two figures 0.05 where it answered 0.06; results
  store `Float64` where they stored a decimal type; two decimals a double cannot tell apart
  compare and select as their doubles where they compared exactly. **No identifier of the
  format moves**: the token stays `gspv0-preview-3`, the schema identifier is unmoved, no
  published vector's expected value changes, and the corpus of section 12.5 is unchanged.
  Landed 2026-10-31.
- `v0-preview.3` — **A per-policy grid's identity is its rule.** Section 11.1.37 states that a
  `per_policy_grid` recipe carries no `n_periods`: its identity is its kind, cadence, calendar,
  convention, day count, start date, horizon kind and the column or age each policy's horizon is
  read from, so no other policy's horizon reaches the digest of a line reading the schedule.
  Section 11.1.1 states that a jagged axis states no longest horizon; the longest horizon in a
  run stays `run_metadata.n_periods` (§13.2). **What moves, once**: the digest of every
  per-policy grid, and with it the local digest of every line reading one, those lines'
  downstream digests and the `graph_fingerprint` of every model on such an axis, with the same
  calculation behind them; a model's figure is then one across books, samples and batch sizes,
  and a batched audit record of a model with no hole carries it where it carried null. No byte
  grammar moves, so the token stays `gspv0-preview-3` and the schema identifier is unmoved; no
  published vector's expected value changes, and the corpus of section 12.5 is unchanged (it
  holds no per-policy grid). Landed 2026-10-31.
- `v0-preview.3` — **A compiled rollforward's identity is its published machine.** Section 12.1
  defines the compiled fingerprint as the section 12.3 recipe-grammar hash of the compilation
  body the `gaspatchio_rollforward_ir` facet publishes, less its `schedule` member, where it
  was the compiler's own string taken over engine renderings the file did not hold. A consumer
  reading a body takes its identity again and refuses a body that does not hash to its key, and
  holds the node's `increments` summary to the body (sections 12.1, 16); a compilation the file
  does not carry is read as published and named, beside the injected column (section 13). The
  facet writes `lapse_when_all_non_positive` in sorted order, a set having no order of its own.
  Behaviour changes, in the reference producer: `validate --deep` reports an edited machine, or
  a summary that disagrees with it, as an error, and names each compilation it read on trust;
  `run-artifact` refuses both through that reading, where a floor edited to a billion and a
  charge read as a growth replayed. **What moves, once**: every compiled fingerprint, every
  `rollforward:` id, and so the digests of every rollforward node, every line reading one and
  the `graph_fingerprint` and `formulas_fingerprint` of every model holding one, with the same
  calculation behind them. No byte grammar moves, so the token stays `gspv0-preview-3` and the
  schema identifier is unmoved; no published vector's expected value changes, and the corpus of
  section 12.5 is unchanged (it holds no rollforward). Landed 2026-10-31.
- `v0-preview.3` — **A comparison of results cites the document it was handed by its seal.**
  Section 11.1.12's comparison report carried the artifact's `graph_fingerprint` alone, though
  it is handed a written document and section 13.1 has every record that points at a document
  it does not enclose carry that document's `document_digest` beside its identity. The report
  gains `document_digest`, beside `artifact_fingerprint` and null where the document carries
  no seal; it is recorded and never compared, so two exports of one model compared over the
  same results give one verdict and two reports that differ in that member alone. The report
  grammar moves to `gaspatchio-graph-compare/v0-preview.2`. **No identifier of the format
  moves**: the token stays `gspv0-preview-3`, the schema identifier is unmoved, no published
  vector's expected value changes, and the corpus of section 12.5 is unchanged. Landed
  2026-11-01.

### 14.2 The change report

The implemented report grammar is `gaspatchio-graph-diff/v0-preview.2`.
Its JSON members are `report_version`, `fingerprint_algorithm`, `compared`,
`drift`, `calculations`, `data`, `values` and `source`. `compared` is an object with `before` and
`after` document records, each with `graph_fingerprint`, `document_digest`,
`created_at`, `producer` and `formulas_fingerprint`; unavailable descriptive values are null,
and `formulas_fingerprint` is null where a document carries none. Two records agreeing on it
changed no formula between them (section 12.6); the command's text output says so in one line
under its headline, naming the `data` entries that moved, or says a formula changed, and says
nothing where either side has no figure. Like the rest of the record it is not compared as a
model change: `calculations` is still read node by node. The
Boolean `drift` is true when either change array is
nonempty. Document metadata and seals are recorded, not compared as model
changes. A seal is evidence against an independently retained copy/report,
not an authentication mechanism by itself (§13.1).

Both input artifacts must state the same `fingerprint_algorithm`; different
grammars refuse rather than comparing incomparable digests. Validation and
numerical execution are separate from comparison: a change report is not a
schema validator, a proof of payload availability, or a valuation comparison.
Callers making those claims must perform those checks too.

Each `calculations` entry writes all seven fields, including nulls:
`node`, `column`, `kind`, `change_origin`, `renamed_from`,
`fingerprint_equal_to`, `values_equal_to`.

- Nodes are paired by artifact node id. A paired node with both fingerprints
  unchanged produces no entry. A moving local fingerprint is ordinarily
  `kind="changed", change_origin="self"`; only the upstream fingerprint
  moving is `change_origin="inherited"`.
- Data attribution also classifies a changed injected/continued input as
  inherited, and can classify a re-sourced assumption read as inherited when
  both artifacts retain equal formula text, equal `reads`, equal
  `reads_assumptions`, and a named assumption in that read set moved. This is
  a bounded attribution heuristic: equal absent formula text is not proof
  that an unrecorded formula edit did not coincide with the data change.
  The join uses assumption names and cannot disambiguate two kinds sharing
  a name. Consumers must retain these limits when presenting the label.
- A new node carrying recorded `provenance="rename"` and exactly one source
  read present in the earlier artifact is `kind="renamed"`, naming that
  source in `renamed_from`. Merely editing a variable name in source code
  supplies no recorded rename. A copy is not a rename either.
- Other arrivals/departures are `added`/`removed`, with null change_origin.
  A unique one-to-one equal-fingerprint pair across arrivals/departures may
  set `fingerprint_equal_to` on the added node. Where either endpoint is an
  injected/continued input, the weaker `values_equal_to` label is used.
  These are hints, never inferred renames. Multiple matching candidates
  receive no unique-pair hint.

Entries follow the later artifact's node order, then departures in the earlier
artifact's order. Compilation nodes obey the same id rule. A changed compiled
identity that appears under a new id is add/remove; there is no stable business
role in this report with which to pair it automatically. Two unrelated state
machines are not matched merely because they occupy the same ordinal. Adding
a stable role or a new matching rule remains a deliberate format decision.

Each `data` entry writes all five fields, including nulls: `kind`, `name`, `before`,
`after`, `reason`. Kind is table, schedule, curve, model_points, hole, injection or results. Missing
sides are null, and `reason` is null on every entry that reports a movement. Named assumptions
pair by (kind,name). Unnamed assumptions are compared as digest sets per kind;
an unchanged digest crossing the named/unnamed representation is reconciled
before emitting changes. Schedule/curve labels synthesized from content change
when content changes, so these ordinarily produce a removal and an addition.
Model points are reported from the book digests of section 7.5 where both documents state one:
the entry's `before` and `after` are those digests and its name is the file the later run
recorded in `model.model_points`, or the earlier one's, or null. A book revised only in a
column the model does not read is therefore no change. Where either document states no book
digest, model points are reported from the file stamps `model.model_points` records. **Where
neither can decide** — a document states no book digest and the two runs do not both name a
file — the entry is written anyway: `before` and `after` carry whichever digest each side
stated, or null, and `reason` says the two books could not be compared, in each document's
own words where it gave any (the `detail` of section 6.1's form) and naming the run that named
no file. Such an entry is drift. An empty `data` would read as "the same policies", which is
the one answer a report that could not tell must not give.
**A hole is reported from the stamp of what it held.** Section 7.1 gives a hole the frame
arrived holding a `content` stamp in the holes section and none in its node, and section 12.4
folds that stamp beside the hole's name, so an edit to a file the model's setup joined moves
`graph_fingerprint` and no node digest: read node by node, the two documents differ in nothing,
which is the one answer a report over two different fingerprints must not give. So every hole
name both documents' holes sections list is compared on its `content`. Where the two stamps
differ, the entry's `before` and `after` are those stamps, its name is the hole's column, and
its `reason` is null; where one document gives the hole a stamp and the other gives it none —
one written before holes carried one, a hole whose values its producer could not read, or an
`overwritten` hole, which carries none — `before` or `after` is null and `reason` says the two
could not be compared and why. Either entry is drift. A hole only one document lists is a node
only one document holds, which `calculations` already reports, and it writes no `data` entry.
Injected/continued inputs are reported from their recorded content stamps. **Results are
reported only where both documents record a results file's fingerprint** in `model.results`
(section 7): where the two fingerprints differ, the entry's `before` and `after` are those
fingerprints, its name is the file the later run recorded in `model.results.path`, or the
earlier one's, or null, and its `reason` is null. Such an entry is drift. The fingerprint is a
SHA-256 over the file's bytes, and a file's bytes move with whatever wrote it — its encoding,
its metadata, what a result manifest says produced it, the platform included — as well as
with the numbers it holds, so the entry says the file moved and not that any number did:
whether the two results agree is the comparison that section 11.1.12 states. Where one
document records a results file's fingerprint, or neither does, no entry is written, because
nothing was compared, and an empty `data` says nothing about the results either way.
Assumption changes precede model points, which precede holes, which precede injections,
which precede results.

**`values` is what the two runs' numbers did, and it is null where no results
file was read.** A change report over two documents alone says what *can* have moved;
whether a row of a table is reached depends on the book, so no identity can say what
*did*. Where the two runs' results files are read beside the documents — each file the
one its document records in `model.results`, found where that path resolves with the
checksum recorded, or two files the caller names — the report carries:

- `results`: `before` and `after`, each `{path, fingerprint, read, scope, producer}`,
  `read` being `recorded` or `named`. Each file must be a result of **its own**
  document: a result manifest whose `graph_fingerprint` is not that document's is
  refused, naming the side, as section 11.1.12's comparison refuses it.
- `rows`: `{matched_by, on, paired, joined, left}`. Rows pair on the identity
  columns the caller names, else those both result manifests record, else those one
  records where both files carry them; by position only where both files were run over
  one book (equal `inputs_digest`, equal row counts); otherwise the report is not
  written. A policy only one file holds is never a refusal: `joined` (later only) and
  `left` (earlier only) each carry a `count` and the first policies by name.
- `periods`: `{aligned, reason}`. Period `t` of one run is period `t` of the other only
  where every paired policy's `projection_start_date` is equal in the two files, or
  neither document has a dated timeline. Otherwise no line holding one value per
  period is compared, and `reason` says why. Where the starts agree and one timeline is
  longer, the periods both hold are compared and the difference in length is stated.
- `lines`: one entry per line the report pairs and both files carry, in the later
  document's order. Lines pair as `calculations` pairs nodes: by node id; a recorded
  rename's new node with `renamed_from`; an added node with the node its
  `fingerprint_equal_to` or `values_equal_to` hint names, compared and labelled
  `paired_by: "hint"`, never a claim of a rename. An added or removed node has no
  values. Each entry writes `node`, `before_node`, `column`, `paired_by` (`id`,
  `rename`, `hint`), `change` (the definition's movement: `self`, `inherited`,
  `renamed`, `added`, or null where it did not move), `compared`, `moved`,
  `cells_compared`, `cells_moved`, `policies_compared`, `policies_moved`,
  `first_period_moved`, `max_abs`, `max_relative`, `from_zero`, `worst`,
  `length_moved`, `within_band`, `cause` and `holes`, nulls included.
- `cause`: what the record states moved under a line whose definition did not —
  `book` (a `model_points` entry, or one whose books could not be compared over two
  results files of different `inputs_digest`), else `hole` where the line reads a hole
  whose stamp moved — it is that hole's node, or reads it through the lines it reads, as
  the later document's `reads` record them, and the hole has a `data` entry with two
  stamps and a null `reason` — else `producer` (the result manifests' `producer` or
  `versions` differ), else `unexplained`. The book and the producer are the comparison's
  and a hole is the line's: a line that reads no moved hole keeps the comparison's cause,
  so a column written over around the frame stays `unexplained` beside an edited side
  file. `holes` names, on a line whose cause is `hole`, the holes it reads whose stamps
  moved, by column, in the later document's node order; it is null on every other line.
  The `values` member's own `cause` is the comparison's, and is never `hole`.
- `headline`: the counts a reviewer reads, as node lists — `edited` lines that moved
  and that moved no number; `inherited` lines that moved and that moved only in
  identity; lines that moved under unmoved definitions by `cause`; the moved lines
  `within_band`, counted apart; `not_carried`, the lines `calculations` lists that one
  file does not carry; and the `joined` and `left` counts.
- `declared`: the policy the later document's first policy entry names, read from the
  two files as a comparison page reads the two documents' own values, so that the two
  readings can be held against each other; null where the entry names no single policy
  or no paired row answers to it.

**A value has moved when it is unequal.** Integers, Booleans, text, dates, where the
nulls are, whether a value is a NaN, which way an infinity points and a timeline's
length are compared exactly; two numbers are compared as numbers; the sign of a zero is
not compared. `max_relative` is `|after − before| / |before|` over two finite numbers
with a non-zero `before`; a move out of a zero `before` sets `from_zero` and is never
divided, and it outranks every finite ratio in choosing `worst`, the cell that ranks the
line — `{policy, row, period, before, after}`, a non-finite value in section 10's
sentinel text. **`within_band` is a label and never a filter**: on a moved line it says
whether section 11.1.12's rule holds, each side's scale taken from what **its own**
document says the line reads; false on a moved line of exact values; null on a moved
float line beyond the band where a read is absent from its own file, and on a line that
did not move. A moved line inside the band is listed as moved, and a reader decides what
it means.

**`drift` gains one case.** It is also true where a line whose definition did not move
moved beyond the band or where the band cannot be decided. A line whose definition moved
is drift already, through `calculations`; a move inside the band, under an unmoved
definition, is not drift, because no comparison can tell it from the order arithmetic
was done in.

**A selection step is a calculation entry.** A change to which policies the model values is a
change to the model, so each step section 7.6 lists is paired by its `id` and reported in
`calculations` as a node is: `changed` with `change_origin: "self"` where its own digest moved
(the in-force definition changed), `"inherited"` where only its fingerprint did (a column it
reads was redefined), and `added` or `removed` where only one document carries it. `column` is
null on every such entry, and the entries follow the nodes'. They make `drift` true as any
calculation entry does.

**`source` is the model's own files' bytes, on a line of its own.** Where the two documents'
`model.source_sha` values differ, or a helper module moved, the report carries
`{path, before, after, modules}` — the later document's `source_path`, or the earlier one's,
the two `source_sha` digests, each null where its document states none, and the helper
modules that moved — and is null otherwise. `before` and `after` are equal where only a
helper moved. `modules` is read where both documents list `model.modules` (section 7), and is
empty otherwise: each module is paired by its path relative to its own document's model file,
so a model copied to another directory of one repository pairs its helpers with the copy's,
and one entry `{path, before, after}` is written, ordered by that relative path, for each whose
fingerprint differs or which only one document lists — `path` as the later document writes it,
or the earlier one's, and `before` or `after` null on the side that does not list it or could
not read it. **It is stated and never counted**: a reformatted model, or a comment in a helper,
moves a file and no calculation, and `drift` is the fingerprints' to decide; a helper edit that
does move a calculation is reported in `calculations` as well, and this names the file it came
from. What it tells a reviewer is that a file they would open is not the file the earlier run
recorded. The command's text output prints the model file's line where its digests differ, and
one line per helper module, under its headline.

This subsection documents the existing grammar and its limits. It adds no
closed-key rule above the expression/increment branches already closed by
§§6 and 12.1, and does not alter unknown-extension handling.

## 15. Assumptions

Every directory entry has `kind`, `name`, `fingerprint` and `payload`. Kinds
are table, join, schedule and curve. Name is a label or null on older/other-producer
records. Tables ordinarily retain their declared name; a value object with no
name receives `kind:` followed by the first eight hex digits of its fingerprint.
That short label is **not** an identity. Resolution uses kind and the full
digest; it must refuse an ambiguous match rather than select the first label.
The directory is an account of bases actually read, including a schedule read
by a compiled rollforward. Configuring an otherwise unused schedule does not
by itself assert an assumption dependency.

For a table, `fingerprint` is the processed table's **content** hash (§12.3) —
what the reference producer's `Table.fingerprint()` returns — and not `Table.source_sha()`,
which hashes its recipe, name included. It is taken over the table's canonical form, so it
is the same string however the source ordered its rows or columns and whatever format it was
read from. An inline table payload has:

- `dimensions`: the named dimension set;
- `value`: the column supplying the lookup answer;
- `columns`: ordered objects containing `name` and neutral `dtype`;
- `rows`: ordered rows, cells aligned with those columns.

The payload is the processed registered frame, in the canonical form of §12.3: the key
columns ascending by name, the `value` column last, the rows ascending by the keys. Input
reshaping, melting, computed dimensions, overflow extension and that ordering have already
occurred.
A reader must not rerun those transformations or sort/project the payload before
verifying it. Hash its declared columns and rows in the order carried, using
§12.3. Bind lookup operands in the processed table's key-column order — **the
`columns` order above with `value` removed** — and not in `dimensions` order,
which is a set of names rather than a sequence, nor in the original Python
keyword order (§11.1.24). In canonical form the answer is
the last column and every other column a key, so the content hash fixes the roles as well as
the values: one source read with another column as its answer is another content, and two
readings of one file under two answer columns never share a digest. The declared
`dimensions` and `value` must still agree with that layout, and role consistency is still
checked before lookup — a document written before the canonical form, or by another
producer, need not hold its answer last. A payload with missing roles or multiple
conflicting role assignments is not an executable base merely because its rows hash
correctly. Roles are about
which column is which: a table whose answer column carries a blank cell has
declared its roles, and §11.1.24 judges that cell where a query reaches it
rather than over the table.

Processed table cells travel as i64, f64, bool or str — scalar types §12.3's content
grammar writes, a Boolean under its own tag `0x11` — and **a key the table holds as a date
or a timestamp travels as `date` or `datetime`**, each value section 10's ISO-8601 text,
because that is the kind its fingerprint is taken in (§12.3): a lookup kernel may key it by
a count of days or of its unit, and the count is not what travels. A timestamp key in a zone
other than UTC has no payload form that keeps its zone — a column declares `datetime` and
nothing more — so such a table's payload is §6.1's `unavailable` omission rather than values
that would re-hash under another zone. So is the payload of a table or a join holding a date
or a timestamp outside the years 1 to 9999, which §10's ISO-8601 text — a four-digit year —
cannot write (§11.1.33 puts such a date outside the domain), and of a join holding a list of
timestamps in such a zone. A `list[date]` or `list[datetime]` column, at any depth §10
allows, carries each element as that text, and a consumer reads each element back as the
date or instant it names before re-hashing (§13).
Wide signed integer keys retain i64 identity; the bounded lookup value domain
of §11.1.24 is not expanded by this account of the payload. An undeclared str
key column whose cells all spell whole numbers is judged on those integers,
against the same closed interval §11.1.24 states, as an i64 column of those
values is, so one set of key values carries one processed type and one content
hash whichever type the source held. Above that interval the two part, and the
asymmetry is known: an i64 key column retains i64 identity while the same
digits written as text travel as str. **A key column the table declares as text
stays text** — the reference producer's `DataDimension(dtype=pl.String)` —
whatever its cells spell: it travels as str, its content hash is the text
column's, and a number queried against it is a key of the wrong family, which
§11.1.24 refuses as it refuses text against a numeric key. Non-finite f64 cells use the string sentinels of §10 and
are decoded before content hashing. These are different from the
operation-vector envelope's explicit nonfinite markers.

For a join, `fingerprint` is the `right_fingerprint` of the `join` nodes that
read it: the content hash (§12.3) of the whole right side in canonical form, its
columns ascending by name and its rows sorted by every column. An inline join payload has:

- `columns`: ordered objects containing `name` and neutral `dtype`;
- `rows`: ordered rows, cells aligned with those columns.

It has **no `dimensions` and no `value`**, and an entry of this kind carrying
either is invalid. A join has no roles to declare: equality of key values is the
whole matching rule (§11.1.2), the key is named on the node rather than in the
payload, and every column the right side holds is either that key or a value
the join brings over. The role-consistency sentence above is therefore about a
table and does not reach this kind — there are no roles here to be missing or to
conflict, and an entry whose rows hash correctly is an executable right side.
The columns are in name order and the rows in the sorted order
the fingerprint was taken over, which is the order §12.3 requires of a join's
right side and the same order a reader re-hashes in. The cell grammar is the
table's: i64, f64, bool or str (§12.3's `0x11`), non-finite f64 through §10's string
sentinels.

A join entry is named after its contents — `join:` and the first eight hex
digits of the fingerprint — because a right side is a frame a model handed to
one call and not a base anybody named. Its `fingerprint` is not comparable with
a table's over the same file (§12.3): the two project and order differently, so
one file read both ways publishes two digests, neither wrong. The directory is
still an account of bases actually read: a join that brings no column mints no
node (§11.1.2) and therefore contributes no entry, and a right side handed over
lazily has no identity to file one under.

Schedule and curve payloads are their canonical recipes, hashed under the
recipe grammar (§12.3). A schedule identifies its kind, frequency, period count,
calendar, business-day convention and day count, plus the anchor/start or
inception/horizon fields its kind requires — except a `fixed_step` schedule, which has
no calendar and whose recipe is exactly `kind: "fixed_step"`, `n_periods` and one of
`step_years` (the decimal the model wrote) or `steps_per_year` (an integer). A recipe of
that kind carrying a frequency, a calendar, a convention, a day count, an anchor or a
start is not one this document states, and the two spellings of one step are two recipes
with two digests: a step of a twelfth of a year and twelve steps a year time their
boundaries differently in the last bits (§11.1.37). A curve identifies knots, rates,
day count and interpolation; non-default extrapolation and parametric fields
travel when present in its canonical form. Missing fields cannot be repaired
by assuming the current runtime's defaults. A compiled rollforward's schedule
must be discoverable and resolve to its recorded identity even if no ordinary
column reads that schedule (§16.1).

A table entry may carry `source_file`: the file the table was read from, written against
the model's root as every path is (§7), or by its name alone where the document has no root;
**null where the model handed the table a frame rather than a file's path**, so it named no file.
A table built from another table — shocked with `with_shock`, or shocked and stacked per scenario
by a plan — names the file that table was read from, and is never a plain read of it.
The member is absent where the producer cannot say which of the two it was — a table built in
another process, or one that has moved off the identity its formula read — and on every entry
of another kind. A table extended after it was read from a file holds rows the file does not,
and names none. Beside it, `shaped_by` lists each step of the table's own recipe that
reshaped what it read, in the order its dimensions were declared — `{step, column}` with
`from`, the column or columns it was made from, or `to`, the type a cast produced; the steps
are `renamed`, `cast`, `melted`, `set` and `computed` — and is empty where the processed frame
is a plain read of its source. A table built from another lists that table's steps first, then
`shocked`, with `by` saying the shock or each scenario's shocks in words, and, for a copy
stacked per scenario, `stacked` under `scenario_id`. A key declared as text is not a step: the payload carries it as
`str`, and a reader reads it so. A table payload omitted for its size carries `roles` in its
section 6.1 stand-in: the payload's `dimensions`, `value` and `columns`, everything but the
rows, so the table can still be read from its file. The roles go with the stand-in, so a holder
putting the values back in its place (§13.1) has exactly the entry the inline export writes. A
producer conforming to this edition writes all three wherever it can answer; they are optional,
so a document written before them stays valid. They
say where a reviewer holding the file finds it and how to read it, and §13 states what they do
with it; none is part of any fingerprint.

`payload` is either inline content or §6.1's omission object. An omission states
why content is absent, including unavailable values and a declined inline-size
budget. A sidecar reference is resolved under the established omission rules;
it is not permission to substitute a same-named live table. Moved source objects,
missing registry entries and ambiguous table roles can leave a valid audit
record with no executable payload. A consumer reports that availability limit
separately from identity validity and numerical conformance. Historical value
retention and a new stable assumption-role identity remain outside this clause;
it does not silently implement either pending work order.

## 16. Rollforward

Most accumulations in an actuarial model have a closed form: a survival probability is a
cumulative product, a discount factor is a power, an account value with pre-computable charges
is a linear recurrence. A model escalates to a state machine when — and only when — a
within-period charge depends on the running balance: a cost of insurance struck on the net
amount at risk, a credited rate held between a floor and a cap, a benefit base that ratchets to
a fund's high-water mark. **That escalation is the whole justification for the machinery, so
the artifact shows it as structure rather than flattening it back into the columns that read
it.**

**One compiled rollforward is one node.** Its id is in the reserved `rollforward:` namespace
(§8.1) and its `kind` is `rollforward`. It is not an account of a column, so `column`,
`version` and `formula` are null and `source_location` is null: no statement in the model's
source defines it, and the lines that *read* it carry their own locations. Its `provenance`
is `rollforward`, the recording door §8 reserves for a compilation's own within-period
bookkeeping and the only value §8 admits on this kind. Its operation tree is one call — the identifier `rollforward`, no arguments, and
two attributes: `fingerprint`, carrying the compilation's own published identity as text, and
`schedule`, the `source_sha` of the schedule the machine runs on — and §12.1 says why the
machine is not restated inside those bytes.

**The compiled identity is the machine, and the schedule is data.** The fingerprint is taken
over every state and its opening value, every operation in declared order with its operands,
its label, its rounding and its timing, the stopping conditions, the batch axes, the increment
tracking and the engine binding — and **not over the schedule**. A schedule is the axis the
machine runs over: how many periods, on what calendar or fixed step. Re-sourcing it is a data
change, as re-sourcing a table is, so it leaves the fingerprint and the node's id where they
were; it moves `graph_fingerprint` through the `schedule` attribute the compilation's node and
every line reading it carry, and leaves `formulas_fingerprint` where it was (§12.6). An edit to
the machine moves the fingerprint, the id and both figures. The `gaspatchio_rollforward_ir`
facet's body states the same schedule as its own `schedule`, and a document whose node and
body name two schedules has no single period count; the execution reading refuses it.

**One model runs one machine on one schedule.** Two runs of one machine on two schedules are
one fingerprint and two kernel runs, and the `rollforward:` namespace names a compilation by
its fingerprint, so both would claim one id and the artifact could not say whose reads and
movements were whose. A producer meeting that **must refuse to produce the artifact**, naming
the machine and both schedules — the refusal two compilations sharing a running state get,
below, and for the same reason. A model reaches it only by compiling a machine on a schedule
other than its own projection's.

**A line that reads a compilation reads the node, and never the columns behind it.** A line
whose whole right-hand side pulls one state's per-period values out of a compilation is an
ordinary `computed` node whose `reads` is exactly that one compilation, `DIRECT` /
`TRANSFORMATION` (§9). A line that wraps the extraction in arithmetic of its own reads the
compilation **and** whatever else it names, in the order it names them; what it must never read
is the columns *inside* the compilation, which belong to the compilation's own node. A model
extracting a fund and a benefit base from one compilation has two such nodes and one parent
between them, which is what a reader needs: it is one kernel run and one state machine, not
two.

**Such a line says which balance it materialises, and a forward question asked of it is asked
of that balance too.** A `computed` node whose formula extracts a state carries `extracts`,
naming the compilation and the state reference it pulls out —
`{"compilation": "rollforward:7be2aa108f31", "state": "av@eop"}`, the reference and not the
`state:` id built around it, by the rule `target` already follows — in both profiles, and a
line materialising two balances, which may come from two compilations, carries one such object
per balance as an array in the order its formula names them. It is the *column* that carries
this and never the state: a running state is not a column, and one balance may be materialised
by no column at all or by two, so a field on the state naming its column would have a
cardinality the state cannot hold. The compilation named is one of that node's `reads` and the
state named is one the compilation's `states` declares, and a document disagreeing with itself
on either is refused. The rule this exists for is the forward one: a column assigned an
extraction **is** that running balance, written onto the frame, so "if this fund moves, what
moves with it?" must reach the benefit base that ratchets to it — and an edge walk from the
column alone cannot, because what the compilation reads is the *state* and nothing reads the
column. A consumer answering that question opens the walk at the running state `extracts`
names as well as at the column, and answers the union. It is stated here rather than left to
the edges because the edges do not carry it; the two backward questions need no such rule,
since a column reads its compilation and the compilation reads its states, and a derivation
walk therefore already arrives. The other two doors carry no such field: `rollforward.increment`
reads back a signed movement rather than a balance and names no state on the call, and
`rollforward.struct` has no portable output at all (§16.3).

**What the compilation consumes hangs off the compilation.** Its `reads` are the columns it
takes — opening balances, rates, masks — together with the running states it reads, in the
order the compilation names them and each stated once. The two are interleaved rather than
grouped, because that order is the compilation's own: a state read belongs where the operation
that consults it sits. Stating them here rather than on every extraction is what stops one
growth rate being reported twice in a model reading two states, and it is what lets a reader
ask what the state machine rests on without first working out which of its outputs to ask.

**A running state is a node of its own**, in the reserved `state:` namespace, with `kind`
`state`. It is not a column: nothing on the model holds it, nothing can be asked to supply it,
and it reads nothing — it is where a compilation's account of its own balance begins. Before
it, an artifact had nowhere to point when a charge read the balance it was about to change: a
cost of insurance on the net amount at risk said it read a rate and a death benefit and nothing
else, which is true of the arguments and false of the calculation. A state's `local_fingerprint`
is a leaf's (§12.1), taken under the running-state tag `0x22` and over the state reference
rather than the id built around it.

**`states` names the running states the compilation declares, in declaration order.** It is
carried by `rollforward` nodes and no others. It is not the same list as the state reads in
`reads`: a compilation declares every state it carries, and reads only those whose balance an
operation actually consults. A producer that cannot reach the compiled artefact — a graph
folded where the compiler never ran — **omits the field** rather than writing an empty array,
which would say a state machine with no states in it.

**The same producer may lose a wrapping line's reference to the compilation altogether.** A
line reaches a compilation through one of two doors, and only one of them survives being read
where the compiled artefact is out of reach. A line whose whole right-hand side is the
extraction carries the compilation's identity in the expression itself. A line that *wrapped*
the extraction may keep no more than the name of the scratch column the producer's kernel
works in, and such a name carries a truncation of that identity — sixteen hex characters of
sixty-four, in this framework's spelling — which is enough to recognise the door and not
enough to stand for what came through it. A producer in that state **emits neither the
`rollforward` node nor the reference to it**, so the rule earlier in this section — a wrapping
line reads the compilation **and** whatever else it names — is read with this exception: such
a line's `reads` names whatever else it names, and not the compilation. It is
the same absence `states` carries, taken for the same reason and with the same alternative
rejected — the artifact says less rather than inventing an identity it does not hold, and a
producer that instead minted a `hole` for the scratch column would put a column no statement
of the model's author ever wrote in front of a reviewer as one the model cannot account for.

**An extraction carries no `trace`.** A value trace is a substitution: each name in the
rendered formula replaced by the value the finished model held for it. A line reading a
compilation reads a node that is not a column, and no column of the finished model holds the
compilation's per-period values, so the substitution has nothing to put there. The line still
carries its own `value_sample` — the number it produced is a column of the model like any
other — and a reader noticing the walk-through absent beside a sample that is present is
seeing a decision rather than a producer that gave up: the numbers a trace would have to show
are numbers that would have to be invented. Both fields are enrichment (§8) and neither is
required, so this constrains no producer; it says what the absence means where the enrichment
context is present.

**Two compilations in one model may not carry a running state of the same reference.** The
`state:` namespace names the state and has no room for the compilation that owns it, so two
such compilations would share one node and the artifact would say they carry one running
balance. Namespacing the state id by its compilation was considered and rejected: it would
disambiguate, but a running state is named by the state, and inventing a wider name to hold
an account the format cannot otherwise give is the move this document declines everywhere
else. A producer meeting that **must refuse to produce the artifact**, and must name both
compilations and the state in its refusal — the state as the model's author declared it,
since that is the name they can rename.

**`increments` names the movements the compilation applies, in the order they apply.** It is
carried by `rollforward` nodes and no others. Each entry says which movement it is, the name
the model's author gave it, what kind of movement it is, which running balance it lands on,
and whether its amount depended on the balance it was changing:

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

**`ordinal`** counts from 1 in the order the increments apply, which is the order the array
holds them in. The array order is what is normative and the ordinal restates it, so that a
reader can cite one movement; a restatement is only worth carrying if it is checked, and a
producer's ordinals disagreeing with its array's positions is refused. The order gets no
integrity claim of its own, because it already has two: swapping two increments moves the
compiled fingerprint, the node's id, both of its digests and the artifact's
`graph_fingerprint`, and a JSON array is ordered inside the document seal (§13.1). A third
claim over one fact would be free to disagree with the two that already cover it.

**An increment's identity is its position in its compilation** — the pair (the compilation's
`fingerprint`, its `ordinal`) — and no per-increment digest is minted. §12.1 declines to
restate the machine inside the node's own bytes because its identity already hashes it once,
and a digest minted here would be a second identity over one structure, free to disagree with
the first. Matching an increment across two artifacts is
done on (compilation fingerprint, ordinal) where the fingerprints agree, and on the label
where they do not, with the honesty §14.2 already applies to a rename: a label match is a
hint and never an assertion.

**`label` is a name and not a caption.** A model reads an increment back by name, and a label
is inside the compilation's own identity — renaming one moves the compiled fingerprint, the
node's id, both of its digests and every digest downstream. Two compilations differing only
in a label are two compilations, and the artifact reports the change. This is not the
treatment §8.2 gives `formula`, and the difference is deliberate: the quotation of an author
sits outside identity because editing it changes no calculation, while a name a model can
dereference is part of what the model is. A label is non-empty where it is present, and
**within one `increments` array no label appears twice** — a shared label is a citation
resolving to two movements. That requirement is on the document rather than on the compiler:
a model whose labels collide still compiles and still runs, and what it does not get is a
summary. An operation carrying no field for a name carries `label: null`, which is a claim
like every other null here — the producer looked, and the movement has no name.

**`operation` is the compiler's own vocabulary, closed at ten:** `Add`, `Subtract`, `Charge`,
`Grow`, `GrowCapped`, `DeductNAR`, `Ratchet`, `Floor`, `Round`, `Apply`. Publishing a
compiler's own identifiers as a wire enum couples this format to them, so renaming one is a
format change with a change-log line rather than a refactor. That is accepted: any second
vocabulary would be a translation table between two names for one operation, free to drift
from the thing it translates, which is the argument §12.1 makes for not restating the machine
under a second grammar. The names are already load-bearing — a class name is inside the
compiled fingerprint — so publishing them adds a change-log obligation to a rename that was
never free.

**`target` is the state reference the movement lands on** — `av@eop` — and not the `state:`
id built around it, by §12.1's rule for a running state's name and for the same reason.

**`reads_running_balance` is where the escalation is shown per movement.** A model escalates
to a state machine when a within-period charge depends on the running balance; this section
opens by saying that is the whole justification for the machinery, and this member is the
artifact answering it one movement at a time rather than as a claim about the whole. Seven of
the ten answer from the operation alone: `Charge`, `Grow`, `GrowCapped`, `DeductNAR`,
`Ratchet`, `Round` and `Floor` each take the running balance as an operand of the amount they
apply — a charge struck on the balance, a growth of it, a cost of insurance on the net amount
at risk, a ratchet or a floor comparing against it, a rounding of it — whatever expression
they were handed, because it is the shape of the operation and not the shape of its operand
that puts the balance in the amount.

`Add`, `Subtract` and `Apply` are the three whose expression **is** the amount, and for those
the answer is a reading and not a constant: it is `true` where the expression names the same
**state** the `target` names, at either point, and `false` where it names an input column.
The comparison is between two states and never between two state references — an amount read
off the opening balance of the balance being changed is an amount that depends on it, so
comparing the references would write a false negative on exactly the movement the member
exists to show. There is no property of `Add` that makes its amount computed without the
balance; that is a statement about how people usually write one, and a producer built on it
would answer `false` on the movement that most plainly justifies the escalation.

**The reference producer writes no `Apply`.** Its kernel has no evaluation for a step that
sets a balance to an expression outright, so the compiler refuses a rollforward carrying one
before there is a compilation to describe, and no document it writes holds one. The name stays
in the list because the format names it: a reader still accepts an `Apply` from any producer
that writes one, and reads its `reads_running_balance` exactly as for `Add` and `Subtract`,
off the expression that is its amount.

**The member is nullable**, for the day a producer cannot make that reading. A producer that
cannot classify an expression writes `null`, which carries the meaning null carries
everywhere else in §8 — the producer looked and cannot say — rather than guessing `true` and
telling a reviewer a state machine was justified when nothing checked. Omission is not the
answer there: omission is for an operation the vocabulary does not name, and all three of
these are in the list.

**A producer omits `increments` in four cases, and writes no empty array in any of them** —
the same conditional presence `states` has, one field above. The compiled artefact is out of
reach, which is `states`' own case. Or an operation is not one of the ten, where inventing an
entry would put a movement in front of a reader under a name this document never promised.
Or two movements carry one label, where the array would not be citable. Or one movement's
label is the empty string, which `label` refuses: a label is a name a model reads an
increment back by, and `""` is not one. A producer never writes a document its own validator
refuses, and an empty array would claim a compilation that moves nothing.

**The fourth case is its own and not the third's other half**, which is a distinction a
second producer needs rather than a nicety. A compiler is free to refuse a *missing* label
and say nothing about an empty one — the reference implementation does exactly that — so a
compilation carrying `label: ""` is a compilation that ran. A producer omitting only on the
other three would write that empty string onto the wire, where `label`'s own non-empty rule
refuses it: the document would be refused by the validator of the producer that wrote it.
Stated as four so that no one has to discover the fourth by having a document rejected.

**This is a summary and not the machine.** What it carries is the movements, in order, with
the name each was given and which balance each lands on. What it deliberately does **not**
carry is the expression behind a movement, its rounding, its stopping conditions, its
schedule, or the opening value of any state. Those are the compiled state machine; they travel
in the `gaspatchio_rollforward_ir` facet, which the `executable` profile carries and this one
does not, **that facet is unstable and will change without a compatibility path while this
preview is open**, and a consumer must not read this summary as a stable projection of it. A
reader who wants to re-run the machine asks for the `executable` profile, fetches the facet,
takes the body's identity again under section 12.1 and holds it to the key the body is
published under, and holds this summary to the body's operations; a disagreement in either is
refused rather than run. A reader who wants to know what moved, in what
order, and under what name reads this, and this is what the `audit` profile promises. So what
the `audit` profile carries of a compilation is its identity, what it reads, what it declares,
the movements it applies, what each of them came to, and every line that read it; §11.2 says
why the node's `tier` is a statement about the vocabulary rather than about the payload the
profile does not carry.

**`movements` is what each of those steps actually moved**, and it is the one thing a
rollforward is audited by. It is enrichment (§8) — read only under the envelope's evaluation
context, absent from a document that states none — and it is carried by `rollforward` nodes and
no others. It is an object keyed by the step, and **the key is the kernel's name for the
movement rather than a second copy of the summary's `label`**: the author's label where the
step carries one, and the reserved `{kind}@{ordinal}` (§16.2) where it does not. §16.2 says why
`Floor` and `Round` have no label to give and why that form is reserved; what matters here is
that the join between a row of `increments` and the amount beside it is the ordinal they both
carry, and that **every step of the chain is a key**. A document whose movements name a step
its `increments` do not, or omit one they do, is refused — a reader closing the identity below
without a residual is relying on that and on nothing else.

Each key holds the signed per-period amount, on the policy axis exactly as `value_sample` is
(§7.4): the timeline itself where the axis carries one entry, an array of those in the axis's
order where it carries several, and a null at an entry the amount has no meaning under — which
is a fold taken under an aggregation the identity does not survive, and never a policy. **The
axis goes inside the member and not around it.** Which steps a chain has is a fact about the
compilation and not about any policy, so a mapping per entry would let two entries of one axis
disagree about it, and would make a reader index a policy before they could name a movement.

**A movement on the file is a movement of the run the state came from.** A producer reaches
these amounts by asking the compiled machine what each step moved, and a machine names its
operands by *column name*. A column name is not a value: a model that pulls a balance out of a
compilation and then writes over one of the columns that compilation read —

```python
af.av = compiled.expr_for("av")
af.fund_return = af.fund_return * 2.0   # a stress, a units fix, a second pass
```

— leaves the finished frame holding a `fund_return` the machine never saw. A producer that
reads the amounts against *that* publishes a movement schedule, a closing balance and a check
line that all agree with each other and none of which happened. **Every other reading in this
specification passes such a document**: the fingerprints hold, the axis is as long as the
enrichment, and `closing = opening + Σ movements` closes exactly, because both sides were
computed together on the wrong values. It is the worst failure this format has — not a value
missing, which a reader sees, but a whole waterfall present, arithmetically perfect, and about
a run nobody performed.

So **the amounts are bound to the versions the compilation read.** §8's `reads` already carries
them: a node id is a version — `fund_return` is the column as it arrived, `fund_return@1` the
first definition the model wrote of that name — and a compilation's `reads` is therefore the
record of which definition of each column the machine was handed. A producer evaluates against
those and against nothing else.

**Where a bound version is not in reach, the amounts are declined.** A definition a later
definition replaced may still be reachable — the reference producer carries it aside at the
assignment door — and a column's *arriving* values, written over by the model's first assignment
to that name, are carried nowhere, because what is retained is a definition and an arrival was
never one. A producer that cannot reach what a compilation bound omits `movements` rather than
quoting the replacement, and the state's closing balance is then read off the column the model
materialised it into, which is that balance written onto the frame by the run that happened. A
consumer meeting a compilation that states `increments` and carries no `movements` in a document
that carries values is meeting exactly this, and **must not derive the schedule from the
balances**: that is the identity solved for the terms nobody quoted, and it is true by
construction whatever the machine did.

**The reading that catches a producer that did neither.** A line whose whole calculation is the
extraction **is** that running balance on the frame, so the state's closing balance and that
column are one series read twice: **where a compilation carries `movements` and its state
carries a balance, that balance and the samples of a column extracting it must be the same
numbers.** The wire carries each as the full double the run held (§8), so one series read
twice is equal to the bit — as it is on every pattern this producer ships. A reader holds the
two to within `1e-6` absolute, the tolerance this reading carried while the wire rounded to
six decimals, so that a document written then reads as it did. A document where they differ
by more is quoting two runs, and it is refused. The reading is asked only of a column whose operation tree is the state
call and nothing else: `extracts` records which compilation a formula *reached*, which a formula
that wrapped the extraction in arithmetic reached just as honestly, and those columns are a
different quantity. A document carrying no trees carries nothing that separates the two, so this
is a reading the `executable` profile earns and the `audit` profile does not — the honest limit,
rather than a reading that guessed.

**The state node carries the closing balance, and nothing carries an opening one.** A
compilation's running-state node holds that balance per period per axis entry in its own
`value_sample`, and its `shape` therefore states `list` rather than `unknown`. Its `dtype` does
not move with it, and that is a decision rather than an oversight: a running state is a leaf and
a leaf's type is inside its canonical bytes (§12.1), so naming one would move that state's two
digests, the compilation's, and the `graph_fingerprint` of every model that ever compiled a
rollforward — for a reading that changes no calculation and that §10 already permits `unknown`
for. A running state is also the one node that may carry a value while `in_final_schema` is
false: that rule is about a *column* the frame no longer holds, and a running state was never a
column, so it is not asked to declare `retained`.

**The opening balance is an address and not a member.** What a period opened at is what the
period before it closed at, and the first period's opening is the state's own initial value,
which this profile does not carry. So a consumer states the identity §16.2 gives it — a
period's movements sum to that period's change in the state — from period 1, where every term
of it is on the file, and says at period 0 that the opening is the initial state rather than
deriving a number for it. Deriving one is always available and is always wrong: it would be
the identity solved for the term nobody quoted, which makes the identity true by construction
and tells a reader nothing.

**This section and §17 are siblings and are easily confused.** A compilation here is *one
running balance* accumulating through a sequence of movements within each period. §17's
`state_graph` is a *product whose states are the product* — an income benefit that runs while
a life is disabled, a long-term-care benefit stepping between levels of care — where the
calculation is a solve over transitions. The structural difference decides the shape of each
record: a compilation's increments are **ordered and applied**, so increment 2 lands on the
balance increment 1 left, which is why swapping two moves every digest; a state graph's
transitions are **declared and simultaneous**, and no transition is applied after another. So
an ordinal here and a state pair there, a `target` here and a `from`/`to` there, an intensity
there and no amount here. Neither record is the other's shape and neither should grow into it.

### 16.1 Bounded portable BOP/EOP execution

This subsection states one executable subset of the unstable
`gaspatchio_rollforward_ir` facet. It applies only where the facet's `_schemaURL` is
`https://gaspatchio.dev/schemas/facets/gaspatchio_rollforward_ir-v0-preview.1.json`,
its `compilations` member contains exactly one body for
the fingerprint on the compilation node, and that body has
`points: ["bop", "eop"]`, `engine_binding: "portable"`,
`batch_axes: ["policy"]`, `track_increments: false`,
`lapse_when_all_non_positive: []`, and `contract_boundary: null`. Unknown or
missing fields, another schema identifier, another point or batch-axis form,
tracking, lapse, a contract boundary, or a non-portable binding are outside
this subset and refuse by name.

The body's `schedule` identifies exactly one schedule assumption entry whose
payload verifies under §§12.3 and 13. This form uses `from_calendar_grid`,
`frequency: "1M"`, `calendar: "NullCalendar"`, `convention: "Unadjusted"`,
`day_count: "OneTwelfth"` and `anchor: "month_end"`, with a month-end
`start_date` — or a `fixed_step` recipe (§15), exactly `kind`, `n_periods` and one of
`step_years` or `steps_per_year`, which supplies `T` and nothing else: the machine reads
no date, year fraction or calendar from its schedule under either form, so a step axis
runs the same increments over the same `T` periods. Other schedule forms are outside this
subset. The payload supplies
the nonnegative whole period count `T`; no model source, sidecar period count
or list operand may supply a fallback. Schedule boundary arrays have `T + 1`
entries. Rollforward operands
and extracted state arrays have `T` entries.

State names are non-empty and unique. Every state initializer is one `Col`
operand bound by the compilation node's versioned reads to a scalar finite,
non-null `f64` column. Every ordinary `Col` operation operand is bound through
those same versioned reads and is either scalar finite `f64`, broadcast for
every period, or `list[f64]` with exactly `T` finite, non-null elements for
every policy. One operand of one operation is a test rather than an amount —
the `Ratchet`'s gate, below — and it binds the same way to a `bool` column:
scalar, broadcast for every period, or `list[bool]` with exactly `T` non-null
elements for every policy. No other operand admits that type and the gate
admits no other, so a mask and a rate cannot change places unnoticed.
This portable subset is rectangular. Every `State` operand and
operation target names one declared state and one declared point. Missing,
duplicate or inconsistent bindings, list lengths, state references or point
references refuse before execution.

Every increment operand is either such a bound `Col` or a `State`; every other
operation-tree form is outside this subset and refuses.

For period zero, set each state's BOP to its initializer. For period `t > 0`,
set BOP to that state's EOP at `t - 1`. At each period seed every state's EOP
from its BOP, then apply `increments` in serialized array order. A `State`
operand at `@bop` reads the value fixed at the start of the period. A `State`
operand at `@eop` reads the value left by earlier serialized increments in the
same period. `reads_running_balance` is audit description and never changes
execution.

This subset admits only the following increment records, all targeting
`state@eop`:

* `Add` has one operand and empty `settings`; update the target as
  `target = target + operand`.
* `Subtract` has one operand and empty `settings`; update the target as
  `target = target - operand`.
* `Charge` has two operands: its rate and then a `State` read naming the same
  target at `@eop`. Its settings are exactly
  `{ "round_charge": null }`. Update in this operator order as
  `target = target * (1 - rate)`. The state operand documents and binds the
  running balance; it is not a second charge operand.
* `Grow` has two operands and one setting on exactly `Charge`'s shape: its
  rate and then a `State` read naming the same target at `@eop`, with settings
  exactly `{ "round_charge": null }`. Update in this operator order as
  `target = target * (1 + rate)`. The rate is applied as quoted for the
  period; no schedule fraction scales it, so an annual rate on a monthly grid
  is the model's error and not this subsection's to correct.
* `Floor` has one operand, a `State` read naming the same target at `@eop`,
  and its lower bound is configuration rather than an amount: its settings are
  exactly `{ "value": v }` with `v` a finite `f64`. Update as
  `target = max(target, v)`. A floor is a constraint on the balance rather
  than a movement anyone booked, so it carries no label and §16.2 names what
  it moved by the reserved `{kind}@{ordinal}` instead.
* `Ratchet` has three operands: the value it lifts to, then the test that
  gates it, then a `State` read naming the same target at `@eop`. Its settings
  are exactly `{}`. The first operand is a `State` naming one declared state
  at either declared point — at `@eop` it reads that balance as earlier
  increments of this period left it, which is what a benefit base ratcheting
  to a fund's within-period high-water mark is, and the cross-state read is
  the whole reason the operation exists. The second operand is the gate.
  Update as `target = max(target, lift)` at every period the gate is true and
  leave the target unchanged at every period it is false.

The list is closed. An unrecognized operation, an allowed operation with
another arity, setting or target point, a rounded `Charge` or `Grow`, a
`Floor` whose bound is absent or not a finite number, a `Ratchet` lifting to
anything but a declared state, or an ungated `Ratchet` — which carries
`{ "when": null }` in its settings and two operands — refuses. Every
intermediate and output
state must remain finite and non-null; generated non-finite values refuse and
must name the compilation. This subsection fixes operator order. It does not
state a numerical conformance tolerance; an execution contract must declare
any tolerance separately.

A `rollforward.state` call in this subset selects a declared state with
`point: "eop"` from the machine identified by its
fingerprint and returns one
`list[f64]` of length `T` per policy. The `shared` attribute controls reuse of
one compilation result and does not alter values. With `T = 0`, each policy
receives an empty list without applying increments; with no policies, the
result has no rows and retains its `list[f64]` dtype. The compilation is evaluated
once as a state map; the bare `rollforward` node remains its structural
identity rather than an ordinary data column. `rollforward.increment` and
`rollforward.struct`, extraction at `bop` or another point, the other four
operation names — `GrowCapped`, `DeductNAR`, `Round` and `Apply` — jagged
schedules, non-scalar initializers, rounding, tracking,
lapse and contract boundaries do
not acquire portable value semantics from this subsection.

### 16.2 Bounded tracked increment extraction

`rollforward.increment` extends §16.1's stated machine domain in one respect:
`track_increments` is true, and the requested label identifies exactly one
serialized increment — by the name its author gave it, or by the reserved
name below where the step carries none, which is the only way a chain
holding two structural steps names either. All other §16.1 restrictions on
points, schedule,
initializers, operands, operation names/settings, bindings and finite values
still apply. An absent/ambiguous label or tracking disabled is a refusal.

Run the same operations in the same order. For the identified operation, let
`before` be the target's binary64 value immediately before applying it and
`after` the value immediately after. Return **`after - before`**, with one
Float64 delta per period per policy. This is a signed movement: a charge
usually gives a negative value. It is not the original operand, a notional
charge recomputed later, or the final period balance minus BOP after all
operations. Floating cancellation is observable: adding 1 to a balance of
2^53 leaves the rounded balance unchanged and its tracked delta is 0.

**Every operation of the chain is tracked, and a structural one is identified
by a reserved label.** `Floor` and `Round` carry no label field — a floor is a
constraint on the balance rather than a movement anyone booked — so the label
that identifies such an operation is the synthetic `{kind}@{ordinal}`:
`floor@3` for a `Floor` declared third, `kind` the operation name lowercased
and `ordinal` the same 1-based position §16's `increments` array numbers it
at. **`@` is reserved for this form**: a producer refuses a model whose author
wrote a label carrying it, before any run, because a label free to spell
`floor@3` is two movements under one name. A `Floor`'s delta is the amount it
put back, positive where it bit and zero in every period it did not; a
`Round`'s is the rounding delta, signed the same way as every other. Because
no operation goes untracked, **the sum of a period's increments is that
period's change in the state to floating point** — closing at *t* minus
closing at *t−1*, with the initial state standing as the opening of the
first — and a consumer may state that identity without deriving a residual
term for the steps the chain did not name.

The result is `list[f64]` with length T; T=0 yields an empty list and zero
policies yields zero rows. `shared` changes reuse, not values. Numerical
comparison must account for the stated update/subtraction order; the fixture's
budget is explicit and is not a new universal rollforward tolerance.

### 16.3 Raw Struct output is excluded

`rollforward.struct` remains a core vocabulary identifier and a recorded
native-kernel escape hatch. It has **no portable output contract in this
preview**. The live result is a Struct of named list fields, and §10 has no
Struct type: graph construction and both artifact export profiles refuse it,
naming the column, the unsupported type and the alternative.

Assign `compiled.expr_for("fund")` to a named state column, or
`compiled.increment_for("credit")` to a named tracked movement column,
within §§16.1–16.2's respective domains. Keep the raw Struct off the exported
frame. Do not silently flatten it, drop its fields, change its tier, or count
this exclusion as a 94th bounded value contract. A dropped raw column may
remain a historical node with unknown dtype; that does not make its former
Struct value portable. A future Struct type needs explicit field naming/order,
nested typing, value encoding and validation rules before it can be emitted.

## 17. Reserved payload sections

Two of the accounts a node may give (§8) are ones this preview does not produce. Both are
**designed and not emitted**: the schema defines the payload each carries, and nothing in the
reference implementation writes one. A seat that has never been filled is a claim rather than
a fact, so each section has one hand-built example artifact standing behind it — travelling
with the reference implementation, at
`bindings/python/tests/graph/goldens/state_graph_example.json` and
`bindings/python/tests/graph/goldens/nested_valuation_example.json` — which the published
schema accepts whole. **That is the evidence, and it is what these sections cost**: two
example artifacts, in exchange for knowing that the payload each is written for can be
carried the day a producer holds one, without a change that breaks anything already written.

What that acceptance is, and what it is not. The schema holds the *shape* of a payload: which
fields are there, what type each takes, that a state is named once, that a product declares at
least two states, and that at least one transition runs between them — a set of states nothing
moves between is a list rather than a product. It does not hold that a transition names a state
the same payload declared, and this document does not claim it does: reference within one
document is outside what a schema of this kind reaches. That check is held by a test over the
example beside the section, and, the day either section is emitted, by the producer that writes
it — which is where the schema's own field descriptions say it lives.

Neither section belongs to a conformance profile (§3). A profile says what a producer must
write and what a consumer may rely on, and nothing writes either of these; which profile
carries them is settled by the producer that first does. Neither kind has an id namespace
reserved for it either: §8.1 reserves `state:` and `rollforward:` and nothing else. The two
example artifacts write ids prefixed by the kind's own name, following the shape of the two
that are reserved, and **a consumer must not read either prefix as reserved today** —
reserving them is part of emitting these sections rather than of designing them. That gap has a
second consequence a reader should not have to find for themselves: both example artifacts
carry a null `column` and a null `version` on those ids, because neither node is a column of the
model — and §8's row for `column` says null *only* in a reserved id namespace, leaving room for
this section to add its own, which this section has not done. So **a null `column` is not by
itself a reserved prefix today**, and it is a node that is not a column of the model rather than
a node whose prefix a consumer may trust. Reserving the prefixes closes both halves at once.

**`state_graph`.** Section 16 is about a model that escalates to a state machine for one
running balance, and its `increments` record the movements that balance takes, in order, one
landing on what the last one left. This is the case where the *product* is the states, whose
transitions are declared and simultaneous rather than ordered and applied — the sibling
distinction §16 draws, read from this side: an income benefit that
runs while a life is disabled and stops when it recovers, a long-term-care benefit that steps
between levels of care, a joint-life annuity that changes on the first death. The calculation
is then a solve over the transitions rather than a recurrence written column by column, and
flattening it into the columns that read it would lose the one thing a reviewer wants to see.
The payload carries the states in declaration order, one entry per declared transition — the
state left, the state entered, and the intensity governing the move as an operation tree —
the axis a rate is quoted against, and the columns the intensities were fitted on. Two things
it deliberately does not carry are both derivable, and written down twice would be free to
disagree with what they were derived from: a state's chance of staying put, which is what is
left after the exits it declares, and the absorbing set, which is the states no transition
leaves. The axis carries the length of a
period **and** the period an intensity is quoted per, because with a constant intensity an
annual rate and a per-period one reach the same answer, so an axis left unsaid is a valuation
error that survives testing and appears the first time the rates vary. **The length of a
period is written in 11.1.1's own vocabulary, including its fixed step**: on a calendar axis
`frequency` names the cadence; on a fixed-step axis — the teaching workbooks and numerical
solutions of Thiele's and Kolmogorov's equations a product of states is most often checked
against — `frequency` is null and exactly one of `step_years` or `steps_per_year` states the
step, written as the axis was declared, so an annual intensity is converted on the step the
model laid and not on a calendar month it does not have. A `state_graph` node
has no `formula` — no statement in the model's source defines the product, and the lines that
*read* it carry their own locations — so the bases its intensities look up are named in the
node's `reads_assumptions`: the payload is where that node's reading happens, and an empty
array beside a payload that plainly reads a table would be a positive claim (§8) that is
false.

**What a `state_graph` payload can and cannot be read for.** The two omissions above are
derivable, and naming them is a courtesy. Three that are **not** derivable are a boundary, and
a reader who took the courtesy for the whole story would take the wrong inference from it. What
a reader can reconstruct from this payload is the product's topology and the rate governing
every move in it: the states, the transitions between them, each intensity as something a
second implementation evaluates rather than reads, the axis those rates are quoted against, and
the columns they vary over. What a reader **cannot** reconstruct from it is a reserve. What the
product *pays* is not in this section — the benefits and the premiums, the amount of each, the
pattern it follows over time, and whether it attaches to a sojourn in a state or to a move
between two. The state a reserve is **struck from** is not in it either, and the same graph
gives one answer conditioned on a life that is active and a different one conditioned on a life
that is disabled. Nor is the **discount input** the resulting payment stream is valued at. Each
of the three has more than one defensible shape, and a shape published before anything holds
one would be a guess a reader could not tell apart from a decision; each arrives with the
producer that first emits this section, which is the same moment the profile question above is
settled. Until then a `state_graph` node is a record of a product's transitions, and **a
consumer must not read it as a record of a valuation.**

**`nested_valuation`.** A valuation evaluated inside the projection — a guarantee reserve
struck period by period by an inner stochastic model, each of the outer model's periods
standing as a state the inner one is launched from. It is one node rather than an inlining
because the inner model is a model: it has its own graph, its own identity, and its own
artifact. The payload carries that identity as the inner graph's fingerprint (§12.4), the
interface across the boundary — what goes in, what comes back — and the context the returned
values mean something under: the measure they were struck under, the number of paths they
were reduced over, and whatever else the producer holds. The context is key and value rather
than a fixed field list, so a producer that later holds the seed and the generator carries them
without a schema change; an inner valuation is a Monte Carlo answer, and one that does not
say what generated its paths cannot be reproduced. What the section does **not** do is put
the inner model's own bases in front of the reader. The fingerprint is the identity of a
record held elsewhere, and a reader who wants the calculation behind that figure fetches that
artifact — which is the honest account of where this artifact's reach ends, and the reason
the interface is named at all: a dependency drawn through this node reaches the interface and
no further.

## Annex A. Solvency II

This annex reads the specification against a supervisory documentation regime that already
exists, and reports what it found. It is an exercise in **assembly**: for each obligation the
question is whether a reader holding one conforming artifact and nothing else can reach the
answer by a named path through the fields sections 6 to 14 define. Where the path exists it is
given. Where it does not, the annex says so and names nothing — a field invented to fill a cell
in the table below would be a field this specification does not have.

Nothing here is a compliance claim. An artifact is a record of how a model's columns were
computed; the documentation of an internal model is a much larger thing, and most of what
Articles 243 to 246 of Commission Delegated Regulation (EU) 2015/35 ask for — the inventory of
documents, the policy for changing the model, the responsibilities assigned to staff, the
results of validation — is not a property of a calculation and is not what this format carries.
The obligations below are the ones that are: three the table assembles from named fields, and a
fourth that is demonstrated by recomputing rather than by looking anything up.

The standard all four sit under is Article 243(1), and it is restated here at its own length
rather than at the length this annex can answer. The documentation must be sufficient for any
independent knowledgeable third party to understand the design and operational details of the
model **and to form a sound judgement as to its compliance with the Directive provisions that
same clause goes on to name.** Section 1's engine-free claim is the first half of that standard
restated as a property of a file — a consumer that can read JSON can read the record without the
software that produced it being installed, licensed, or still in existence. It is not the second
half and cannot be: a judgement about compliance is a conclusion a person reaches, resting on
material an artifact does not carry and this annex does not claim. Restating the standard at
half its strength would make the distance between it and the rows below look shorter than it is.

The proof that each path below resolves is
`bindings/python/tests/graph/test_supervisory_annex.py`, which walks a conforming artifact and
asserts the path rather than the value. A test that pinned a number would pass for one fixture
and say nothing about the format.

### A.1 The three questions, and a fourth

| Obligation | Assembled from |
|---|---|
| **Article 244** — minimum content of the documentation: what each figure is, what it was computed from, and which data and which assumption bases it rests on. | `nodes[].formula` and `nodes[].reads` for the calculation and the operands it names, `edges` for the dependency structure between them, and `nodes[].source_location` for where in the model author's own source it was written (§8, §9); `model.model_points` for the policy data and `assumptions[]` for the assumption bases, each carrying a content hash, with `nodes[].reads_assumptions` naming which of those bases each figure's own formula read (§7, §8, §12). |
| **Article 245** — the circumstances under which the model does not work effectively. | `holes[]`, one entry per column the model holds that nothing in the model accounts for, and every node carrying a non-empty `engines` (§7.1, §8.3). |
| **Article 246** — the record of changes to the model. | Two artifacts of the same model, compared: each node's `local_fingerprint` against its `fingerprint`, which separates a node that was edited from one that inherited a change from upstream, `graph_fingerprint` for the whole, `formulas_fingerprint` for whether any formula moved at all (§12.6), and the superseded definitions each artifact keeps as history (§8, §12, §12.4). |

Four readings of that table are worth stating outright.

**The first row names `formula` first, and `formula` is a quotation.** It is the calculation
as the model author wrote it, and it is what makes the record legible to the reader Article
243(1) has in mind. It is not, on its own, evidence that the figure beside it was computed
that way: no producer is required to check the text against the operation that ran (§8.2).
What ties the documentation to the run is the rest of the row — `reads` for the operands the
recorded operation actually took, and the identity fields of §12, which are computed from
that operation rather than from the text. A reviewer reads the formula to understand the
calculation and the identity fields to know what was calculated.

Which means the identity fields are not a check on the quotation either, and a reader must not
credit this row's Article 244 answer with a verification the format does not make. `formula` is
no part of a node's canonical bytes, so a quotation altered after the artifact was written
leaves every fingerprint in the file valid and every deep check on them clean (§8.2). That is
deliberate — an identity moves when the computation moves and at no other time — and it means
the question the chain answers is whether this is the same calculation, never whether this is
the file the producer wrote. The second question is a document-level one, and §13.1's
`document_digest` is what answers it: a seal over the document's own canonical serialization,
`created_at` included, that a deep verification recomputes and that every document citing this
one records — so an edited quotation is caught by the seal, and a re-sealed forgery by the
record that cited the original. It is tamper-evidence rather than proof of authorship, and a
supervisor reading it as more than that is reading in a guarantee this format does not make.
It is required under this identifier, so a document filed under Article 244 that carries no
seal is a document the validator refuses; a reader holding one written under an earlier
identifier, where the member was optional, is back at the paragraph above and reads the row
exactly as it is written there.

**The `audit` profile carries all of it.** Every field named above is an `audit` field, so none
of the three answers depends on the operation tree or on the compiled-rollforward payload, and
none of them depends on the part of this format that is unstable in the preview (section 3).
That is the same reason the profile split exists: what a supervisor reads is what a third-party
exporter can emit cheaply.

**`tier` belongs in the second row as well.** `engines` names *which* engine a node's
escape-hatch text needs; `tier` says *how much* of the node this specification can account for
(section 11.2). A node at `engine_native` or `opaque` is a place the record's own account is
partial, which is a limitation in the modelling in the same sense a non-empty `engines` is. The
row names `engines` because that is the field the artifact's honest account of engine lock-in
lives in; a reader working the second question reads both.

**An empty array is an answer, not the absence of one.** An empty `holes` is the producer
stating that the model can account for every column it holds (section 7.1), and an `engines`
present and empty is the node stating that it is engine-free (section 8.3) — which is why
neither may be conflated with the field being missing. Section 12.4 puts the first of those
claims inside `graph_fingerprint` as its own counted section, so a model that stops accounting
for a column cannot keep the digest it had.

**The fourth obligation is Article 243(3), and it is not a row of that table.** The article asks
that a model's outputs be capable of being reproduced using the internal model documentation and
all of the inputs. Reproducibility is not something a reader establishes by finding a field; it
is a property that has to be exercised before it can be claimed, which is why it sits here
rather than in a cell above. It has been exercised in the narrower sense the paragraph below
states, over the account of the calculation rather than over the figures a run produces. An
implementation written from this document and the standard library of its language — nothing
from the software that produced the artifact, and no library in common with it — reproduced
every digest the conformance corpus publishes: eight of eight `local_fingerprint`s under
section 12.1's byte grammar, eight of eight `fingerprint`s under section 12's fold, and the
`graph_fingerprint` of section 12.4, with each node's `reads` derived from section 8's binding
rule rather than transcribed. Section 12.5 is where the corpus and its digests are printed, and
section 13's propagation check is that same arithmetic performed by a reader against an
artifact in hand.

**What that reproduces is the calculation's identity and structure, and not its figures.** The
distinction is the one section 4 draws and A.2 keeps: an artifact is a record of how the columns
were computed, and the numbers are in the Parquet the model wrote. Reproducing an output in
Article 243(3)'s own sense needs the inputs and something that will run the model, and this
format is neither. What has been shown is the narrower thing, and it is the thing a file can
carry: the account of *what would run* can be rebuilt digest for digest by a stranger holding
this document alone, so a reader who recomputes these fingerprints has established that the
account of the calculation in front of them is the account the producer published, and not a
story told about a file nobody can check.

### A.2 What the artifact does not answer

**Why an assumption was chosen.** Article 244(e) and (f) ask for the assumptions the model rests
on together with their justification, and for the methodology by which they were set — the
inputs to the choice, its objectives, the criteria for appropriateness, and its limitations. An
`assumptions[]` entry carries a kind, a name, a content hash, and the values where the producer
inlined them. It carries no justification, and no field this specification defines carries one.
That is not an oversight: section 4 records the decision not to define governance metadata in
the base record, and section 6 is the mechanism by which one organisation's justification
vocabulary is carried without being frozen into the format for everyone.

**Which base an assumption column arrived from.** Article 244(g) asks for a directory of the
data used, specifying its source, its characteristics and its **usage**. The usage is stated
in `nodes[].reads_assumptions` (section 8): it names the `assumptions[]` entries that node's
own formula reads, and the join from one figure to the bases it rests on is that field read
against that section. The field is written on every node and is empty where the producer has
nothing to name — and two cases leave it with nothing to name, where a third, now closed, used
to. The first is an arriving column. Where assumption data arrives as an input column rather
than through a formula that reads a base, nothing in the record says which entry it came from: a
leaf has no operation tree in any profile, its canonical bytes are its tag, its name and its type
and nothing more (section 12.1), and a producer that named an entry there would be inventing the
answer rather than reporting it.

**And a base read inside an engine-native fragment — closed, by refusal.** The second case was
larger than the first, and it reached the `assumptions[]` section itself rather than only the
field. The section and the field are both taken off a node's own operation tree, and where an
expression reached the producer already collapsed into a single engine-native fragment — a
lookup continued by a method the vocabulary does not hold, handed to one of the engine's own
functions, or opened through the escape — the read was inside the fragment's text, in the
engine's own spelling, carrying neither the base's name nor its content hash. The base appeared
in no node's `reads_assumptions` and in no `assumptions[]` entry. And because a fragment is
identified by its text (section 12.1), two models reading two different tables carried one
digest for that node and one `graph_fingerprint`. The `engine_native` tier said the account was
partial; it could not say the identity was false, and an identity that does not move when the
table does is false rather than partial.

A producer therefore never writes such a node. **A value-object read — a table, a mortality
basis, a curve or a schedule, whether the frame's own or one built apart from it — is its own
node**, and a formula that would put one inside an engine-native fragment is refused where it is
written. The refusal names the base, the declared operation that keeps the read a node where
there is one (a conversion such as `to_float`; a conditional for a fill), and the two-line form:
store the read as a column of its own, then continue from that column. The fragment then reads
the column through `reads`, the fold of section 12 reaches the read's node, and the base is in
the directory and named by the node that read it. Renaming a read is not a calculation (section
12 leaves a computed column's name out of its bytes), so a renamed read is still the read. A
compiled rollforward's fragment is not this case: it reads the rollforward's own node by name,
and its identity was never hidden. What `engine_native` marks after this line is a fragment an
author wrote over columns of the model — a partial account of the calculation, whose inputs the
fold still reaches through `reads`. The rule binds an assignment to a model's frame; an engine
expression evaluated on a plain engine frame, outside any model, is no record's business.

**What such a fragment still does not answer — stated for this preview rather than closed.** Two
things, both about a fragment an author wrote over the model's own columns. **Its identity is
its text** (section 12.1), and an engine's rendering does not print every value written into
it: a membership set or a set of breaks written in the engine's own spelling is printed with a
long middle abbreviated and its decimals cut to the digits the rendering shows, so two such
fragments differing only there carry one digest, and a band whose values moved between two
quarters can leave `graph_fingerprint` where it was. The declared banding operations (sections
11.1.4–11.1.6) carry their values as operands and see that move; a fragment does not. **And its
meaning is the engine's**, conversions included that the declared operations refuse: a date
tested through the escape for lying between two whole numbers answers false on the reference
engine, where the same test written as two comparisons is refused at the line as a comparison
across families (section 11.1.26). Neither is hidden from a reader: the node's tier says it
holds a fragment (section 11.2), and a reader listing a model's fragment-bearing nodes has
listed every place either can occur.

**And a column the projection door materialised.** A third case, and one most projection models
carry. `projection.set()` builds the timeline off a schedule and writes the columns that *are*
it — `month`, the number of periods, the projection dates — and section 8.2 is why none of them
names the schedule: a timeline configuration writes no expression against the column, so
`formula` is null and the node carries no tree to take a read off. A sibling with one names it,
`projection.t_years()` being the formula that reads the schedule, so the entry is in the section
and named by the node that read it while the nodes the schedule materialised name nothing. Where
a model never calls it — `month // 12` counts years off a column the door already wrote — no
formula reads the schedule at all and the section carries no entry for it, so the directory of
bases is empty for a model whose entire time axis rests on one. The reason is the first case's
reason: `reads_assumptions` names what a node's own tree names, and a node with no tree names
nothing rather than being credited with a read the producer worked out from the column's origin.
What is unlike the second case as it stood is that no tier marks it — every one of these nodes is accounted
for in full and reports `core` — so a reader following the join from a schedule entry reaches
the formulas that read it and not the columns that are it.

**And a base that arrived through a join.** A fourth case, and the narrowest — half of it now
closed. An arriving column is a node the format accounts for in full: section 11.1.2 states
the join, such a node reports `core`, and since the right side became an entry of its own the
table it arrived from **is** in `assumptions[]`, with its values inline where the guard
allowed. What is still short is the field rather than the directory. The node's
`reads_assumptions` stays empty: an arriving column's `reads` name the key it was matched on,
which is a column of this frame (11.1.2), and the right side it was matched against is data the
join was handed rather than an entry its formula read. So the join from one figure to the base
behind it runs through the node's own `right_fingerprint` read against the directory, rather
than through the field the other three kinds are followed by. A reader reconciling an arriving column to the table it came from
matches that digest against the `join` entry carrying it; a reader who follows only
`reads_assumptions` will not arrive.

**And a base with no name to join on — closed, by naming it.** A fifth case,
recorded because the shape it took is worth recognising and because the answer to it was not
another limit. A schedule and a curve are value objects: neither carries a name a model author
gave it, and an `assumptions[]` entry for one used to state `name: null`. Since
`nodes[].reads_assumptions` names entries **by their name**, an entry with no name could be
named by no node — so a yield curve sat in the directory with nothing tying it to the figures
discounted off it, and the join Article 244(g) asks for was broken for two of the three kinds of
basis a model reads.

The first, third and fourth cases above are the record reaching the edge of what it can see: a
leaf has no tree, a timeline configuration writes no expression to take a read off, a join's
right side is data rather than a basis. Two of the three say so where a reader meets them,
through the node the limit sits on; the projection door's says so only here, because the nodes
it wrote are accounted for in full and report `core`. The second was closed by refusing the
shape that hid the read. This one was not that. The reading node's own tree carried the curve's
identity, the node reported `core`, and every other field was complete — what was missing was
a string to join by.
A producer therefore names every entry it writes: where the base states a name, that name; where
it states none, the entry's kind and the first eight digits of the identity written beside it,
as in `curve:5c1f0a3d`. Such a name is a **label and not an identity** — the `fingerprint` is
the identity, and two entries of one kind whose digests agreed in eight digits would share a
label — and it claims nothing about the model, which is why it wears its derivation on its face:
a reader wondering whether somebody actually called a curve that reads the fingerprint beside it
and sees where the name came from. A null name remains valid for a stored document and a
consumer must still read one; what a consumer can now rely on for an artifact this producer
wrote is that every entry is named and every read resolves.

The consequence for a change report is worth stating, because it is not the one a reader would
guess. A table keeps its own name when it is re-sourced, so the entry is one entry with a moved
digest. A base named after its contents is renamed by the re-sourcing, so it reports as one
entry gone and another arrived — which is the honest reading of a model that no longer reads
what it read, and a reader can now say which curve went and which came in place of it.

So a reader can say which bases the model's own trees name, which columns came from assumption
data, and which formulas read which base — for every kind of base a formula names, table and
schedule and curve alike — and cannot say which base an assumption column arrived from, which
schedule the columns the projection door materialised were cut from, nor anything about a table a join brought in beyond
the fingerprint identifying it.

**Most of Article 245.** The article asks an undertaking to take seven things into account.
`holes[]` and `engines` speak to one of them — the limitations in the risk modelling used — and
to the deficiencies in data only in the narrow sense that a column nothing accounts for is the
point at which the record of the calculation stops. The risks not covered by the model, the
nature, degree and sources of uncertainty in its results and their sensitivity to key
assumptions, the risks arising from external models and external data, the limitations of the
information technology, and the limitations of governance are none of them properties of a
record of how columns were computed, and no field here carries any of them. Section 4 is what
puts the sensitivity of results out of reach in particular: a sensitivity is a statement about
outputs, and this format carries none.

**The rest of Article 246.** The record that article asks for has three parts. The artifact
carries one of them outright — what changed, and what the change reached — and toward a second
it carries raw material rather than the answer. That second part asks for a description of what
a major change implies for the model's continued appropriateness, and a description of
implications is an interpretive statement about a model. What two artifacts compared give is the
mechanical fact underneath it: which nodes were edited, which inherited a change from upstream,
and how far the change reached. That fact is what a reviewer would form the judgement from, and
it is not the judgement; nothing here turns one into the other, and an annex counting it as a
second part delivered would be claiming an author's conclusion as a property of a file. The
third part is a quantitative and qualitative comparison of the outputs before and after a
change, at the same valuation date, which is a comparison of results, and section 4 records the
decision that this format carries none — the artifact says the calculation moved and where the
move propagated to, and the results it moved are in the Parquet the model wrote. The rationale
for a change is governance metadata wherever the article asks for it, and section 4 applies to
that too. There is also a naming point worth stating rather than
leaving to be tripped over: sections 8.1 and 12.2 call the comparison of two artifacts a change
report, whose implemented contract is now consolidated in §14.2. Section 14.1
is the format's own change log; it records changes to the format rather than
changes to a model. Sections 8, 12 and 12.4 define the report's inputs, and
§14.2 states how the report classifies them and where attribution is limited.

**The assumption entry has a stated contract.** Section 15 defines
`assumptions[]`, including each kind's identity, payload or explicit omission,
and resolution rules. Section 12.3 supplies the hash grammars and section 13
the verification rules. This supports the data-and-assumptions half of the
first row; it does not establish why an author chose a base, or make an
omitted payload available to a reader who does not have it.

### A.3 The two registers

A calculation can be written down twice and mean the same thing both times, and the two writings
are not read by the same person. The as-written `formula` of section 8.2 is the model author's
own right-hand side: it is in the language the calculation was specified in, it survives a
change of engine, and comparing it across two quarters compares the model rather than the
software underneath it. That is a reviewer's reading. An engine's rendering of the same
calculation — carried, when it is carried at all, by the `gaspatchio_lowered` facet of section 6
— says what the engine was actually asked to do, which is the question worth asking when a
number is wrong rather than when a calculation is being reviewed. That is a debugger's reading.
This specification makes the first normative and leaves the second an opt-in convenience for
exactly that reason. A base record whose audit surface was an engine's rendering would churn
whenever a dependency changed how it prints an expression, which makes quarter-over-quarter
comparison unreadable; and it would be legible only to a reader who knew that engine at that
version, which is the opposite of the independent knowledgeable third party Article 243(1) asks
the documentation to satisfy. Where the two disagree, the reviewer's reading wins, and section
8.2 says so.

This annex is a draft. It is published as a claim about this specification only when the preview
closes.
