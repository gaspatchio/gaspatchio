// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * Write `fixtures/no-values.json`, the artifact with no enrichment context.
 *
 * The page has a refusal for a file that carries no values: the cone and
 * the inspector still render, and the grid and the proof each say one line. To
 * test it there has to be such a file, and the command line has no door that
 * writes one — `calc-graph`'s options are `--policy-id`,
 * `--policy-id-column`, `--period`, `--filter`, `--branches`, `--profile`,
 * `--retain-superseded`, `--output`, `--output-file` and `--html`, and every
 * one of them runs the model and samples the frame it produced.
 *
 * The published conformance corpus **is** such an artifact. It is the format's
 * own worked example, written to show the members and not a run:
 * `enrichment` is `null`, and not one of its nodes carries a `value_sample`
 * or a `trace`. So this fixture is that file, copied byte for
 * byte rather than edited into shape — an artifact a producer published, not
 * one a test dismantled. Nothing is added and nothing is taken away, which is
 * why this script is four lines of copying and no lines of editing.
 *
 * Usage, from `viewer/`:
 *
 *     node no-values-fixture.mjs
 *
 * The copy is committed, because the end-to-end run packs a page from it and a
 * fixture regenerated on the way into a test is a fixture nobody reviewed. It
 * is a viewer fixture and nothing else: the corpus under
 * `bindings/python/gaspatchio/schemas/` does not move, and this is not a golden.
 */

import { readFileSync, writeFileSync } from "node:fs";

const CORPUS = "../bindings/python/gaspatchio/schemas/conformance/corpus.json";
const OUT = "fixtures/no-values.json";

const text = readFileSync(new URL(CORPUS, import.meta.url), "utf8");
writeFileSync(new URL(OUT, import.meta.url), text);

const artifact = JSON.parse(text);

console.log(
  JSON.stringify(
    {
      fixture: OUT,
      nodes: artifact.nodes.length,
      enrichment: artifact.enrichment,
      valued: artifact.nodes.filter((node) => node.value_sample !== undefined).length,
      traced: artifact.nodes.filter((node) => node.trace !== undefined).length,
      document_digest: artifact.document_digest,
    },
    null,
    2,
  ),
);
