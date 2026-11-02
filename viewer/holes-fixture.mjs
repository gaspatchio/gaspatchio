// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * Write `fixtures/holes.json`, the one fixture no model run produces.
 *
 * Every other fixture under `fixtures/` is an export: a tutorial model run and
 * `calc-graph` asked for the artifact. None of them holds a hole, because the
 * tutorials account for every column they build, and a page that has never
 * shown its amber chip has never been tested.
 *
 * So this one is made by hand, from the published conformance corpus, by
 * adding what the corpus does not carry: two entries in `holes`, the three
 * nodes of kind `hole` that stand behind them, and the two calculations one of
 * those columns had before it was written over. The two counts differ
 * deliberately — the section holds one entry per column however many holes
 * stand for it, and the chip reads the `holes` array, which is the section a
 * reviewer reads to learn whether the model accounts for every column it holds.
 * A fixture where both counts happened to agree could not tell a chip reading
 * one from a chip reading the other.
 *
 * Usage, from `viewer/`:
 *
 *     node holes-fixture.mjs
 *
 * The output is committed, because the end-to-end run packs a page from it and
 * a fixture regenerated on the way into a test is a fixture nobody reviewed.
 * It is a viewer fixture and nothing else: no file under
 * `bindings/python/gaspatchio/schemas/` moves, and this is not a golden.
 *
 * Two digests come through the edit untouched: `graph_fingerprint` and
 * `document_digest` are the corpus's, and after the edit neither describes the
 * file that carries it. That is on purpose. The page quotes what a file says
 * about itself and never recomputes it — recomputing is `gspio validate`'s
 * answer, from the producer's own implementation — so a fixture whose stated
 * digests do not match its bytes is exactly the case worth being able to open.
 */

import { readFileSync, writeFileSync } from "node:fs";

const CORPUS = "../bindings/python/gaspatchio/schemas/conformance/corpus.json";
const OUT = "fixtures/holes.json";

/**
 * Where a reader who meets a hole is sent, as the format's own section: the
 * address the producer writes on every hole today, which names the edition of
 * the specification the corpus is under.
 */
const CLOSES_WITH = "https://gaspatchio.dev/spec/graph-artifact/v0-preview.3#holes";

const artifact = JSON.parse(readFileSync(new URL(CORPUS, import.meta.url), "utf8"));

// The two columns nothing in this model accounts for, each for the reason the
// producer gives it. `reserve_override` was written straight into the query
// plan under a name of its own: nothing accounted for it, and the producer
// cannot see why. `experience_adjustment` was calculated, written over in the
// plan, calculated again and written over again: the producer saw each write
// replace a definition it had logged, and stands a hole for each of them. The
// section carries the reason of the first.
artifact.holes = [
  { column: "reserve_override", reason: "unrecorded", closes_with: CLOSES_WITH },
  { column: "experience_adjustment", reason: "overwritten", closes_with: CLOSES_WITH },
];

// Every node and edge added below is exactly what the producer writes for it,
// copied rather than invented, because a digest made up to fill a field is the
// one thing a fixture about unaccounted columns must not carry. They are taken
// from an export of the corpus model with these lines run after it:
//
//     af._df = af._df.with_columns(
//         (pl.col("select_loaded_claims") * 1.1).alias("reserve_override")
//     )
//     af.experience_adjustment = af.death_claims * 0.05
//     af._df = af._df.with_columns(pl.lit(0.0).alias("experience_adjustment"))
//     af.experience_adjustment = af.death_claims * 0.04
//     af._df = af._df.with_columns(
//         (pl.col("experience_adjustment") * 1.1).alias("experience_adjustment")
//     )
//
// They were run from a string, which the producer can read no line back from,
// so it wrote every `source_location` and `formula` among them as null — as it
// does for any code it cannot read back. A calculation the plan has since
// replaced states no type, because no values of it survive to be typed; a hole
// states the type its write left.

/** One node of kind `hole`: a column there is, and no account of. */
function hole(id, version, dtype, shape, inFinalSchema, localFingerprint, fingerprint) {
  return {
    id,
    column: id.split("@")[0],
    version,
    kind: "hole",
    dtype,
    shape,
    provenance: null,
    formula: null,
    reads: [],
    reads_assumptions: [],
    tier: null,
    local_fingerprint: localFingerprint,
    fingerprint,
    in_final_schema: inFinalSchema,
    materialized_at: null,
    source_location: null,
    facets: {},
  };
}

/** One of the calculations of `experience_adjustment` a write then replaced. */
function replacedCalculation(id, version, localFingerprint, fingerprint) {
  return {
    id,
    column: "experience_adjustment",
    version,
    kind: "computed",
    dtype: "unknown",
    shape: "unknown",
    provenance: "assignment",
    formula: null,
    reads: ["death_claims@1"],
    reads_assumptions: [],
    engines: [],
    tier: "core",
    local_fingerprint: localFingerprint,
    fingerprint,
    in_final_schema: false,
    materialized_at: null,
    source_location: null,
    facets: {
      gaspatchio_column_transformation: {
        _producer: "https://gaspatchio.dev/spec/graph-artifact/v0-preview.3",
        _schemaURL:
          "https://gaspatchio.dev/schemas/facets/gaspatchio_column_transformation-v0-preview.1.json",
        reads: [
          {
            source: "death_claims@1",
            transformations: [{ type: "DIRECT", subtype: "TRANSFORMATION" }],
          },
        ],
      },
    },
  };
}

// The written-over holes carry the same digests: a hole's bytes are its kind,
// its column's name and its type, and these two share all three.
const WRITTEN_OVER = [
  "sha256:12dd1c783c8dfea3ce3014c06e3b22c847078b9c4b8016128500e45323576267",
  "sha256:20f56427f8f833075c6b0ee1f7561e3acce119396a213afe411e6be182ab3ccd",
];

artifact.nodes.push(
  hole(
    "reserve_override",
    null,
    "list[f64]",
    "list",
    true,
    "sha256:12339f1632fd446659844906c4cfbf0f9600406dee4904e8603a6cc25d855f06",
    "sha256:9e71f53fd7f6d31406ec12fa44e357d6c393d24513b5a4ace781953a8757d5e9",
  ),
  replacedCalculation(
    "experience_adjustment@1",
    1,
    "sha256:d155316bf4a292b05d46b1841ea636e330285b446bc20c439c786cc1ca91d6ce",
    "sha256:fbea00a87d142b9b025a6c2479b07b29495bae39271af8aba43f53e476757638",
  ),
  hole("experience_adjustment@2", 2, "f64", "scalar", false, ...WRITTEN_OVER),
  replacedCalculation(
    "experience_adjustment@3",
    3,
    "sha256:e188446f69a979d10d3aaa89282a38fdfcbd33091fdae3a6718aa815ffc663ad",
    "sha256:78268c416ed0271661411eec72dde161f6a68cdb84274bc58f06af3dc84bd944",
  ),
  hole("experience_adjustment@4", 4, "f64", "scalar", true, ...WRITTEN_OVER),
);
artifact.edges.push(
  { source: "death_claims@1", target: "experience_adjustment@1", relationship: "DIRECT" },
  { source: "death_claims@1", target: "experience_adjustment@3", relationship: "DIRECT" },
);

writeFileSync(new URL(OUT, import.meta.url), `${JSON.stringify(artifact, null, 2)}\n`);

console.log(
  JSON.stringify(
    {
      fixture: OUT,
      holes: artifact.holes.length,
      hole_nodes: artifact.nodes.filter((node) => node.kind === "hole").length,
      nodes: artifact.nodes.length,
      graph_fingerprint: artifact.graph_fingerprint,
      document_digest: artifact.document_digest,
    },
    null,
    2,
  ),
);
