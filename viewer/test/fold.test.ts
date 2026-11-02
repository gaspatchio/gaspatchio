// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The entry of the axis that is the book rather than a policy.
 *
 * The fixture is a producer's own export of level 4 over a thousand policies
 * with `--portfolio`: two folds at the head of the axis and one policy under
 * them. Nothing below is typed in — every expectation is read out of the file
 * — so a regenerated fixture moves the numbers and not the claims.
 *
 * The one claim worth stating twice: a column the fold did not cover is null
 * at that entry's position, and the page has to say so in words. `·` is what a
 * value the file does not carry looks like, and a reviewer scanning a column
 * of money reads it as a zero. The tests below hold the reader to telling the
 * two apart.
 */

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { DID_NOT_FOLD, foldLabel, foldNote, isFold, unfolded } from "../src/reader/fold";
import { buildIndex } from "../src/reader/index";
import { parseArtifacts } from "../src/reader/parse";
import { proofOf } from "../src/reader/proof";
import type { Artifact } from "../src/reader/types";

function load(url: URL): Artifact {
  const r = parseArtifacts([readFileSync(url, "utf8")]);
  if (r.refused) throw new Error(r.sentence);
  return r.artifacts[0]!;
}

const folded = load(new URL("../fixtures/portfolio.json", import.meta.url));
const plain = load(new URL("../fixtures/level4.json", import.meta.url));

/** The first entry that states a fold, which is the one the page opens on. */
const firstFold = folded.policies.findIndex((entry) => entry.aggregation !== null);
/** The first entry that states a policy, wherever the producer put it. */
const firstPolicy = folded.policies.findIndex((entry) => entry.aggregation === null);

/** The node id of one column the fold covers, read off the file. */
function covered(at: number): string {
  const node = folded.nodes.find(
    (n) =>
      n.in_final_schema &&
      Array.isArray(n.value_sample) &&
      n.value_sample.length === folded.policies.length &&
      n.value_sample[at] !== null,
  );
  if (node === undefined) throw new Error(`no column is folded at entry ${String(at)}`);
  return node.id;
}

describe("telling a fold from a policy", () => {
  it("opens on the fold, because the producer puts the folds first", () => {
    expect(firstFold).toBe(0);
    expect(buildIndex(folded).at).toBe(0);
    expect(isFold(buildIndex(folded).policy)).toBe(true);
  });

  it("is decided on the aggregation and never on a missing id", () => {
    // A book that names no policy column is walked by row position, and its
    // entries carry no id either. Those are policies.
    expect(isFold({ policy_id: null, aggregation: null, periods: null, filter: null, why: "x" })).toBe(
      false,
    );
    expect(isFold(null)).toBe(false);
  });

  it("names a fold entry by its fold and a policy entry by its id", () => {
    expect(foldLabel(folded.policies[firstFold]!)).toBe(
      `fold · ${String(folded.policies[firstFold]?.aggregation)}`,
    );
    expect(foldLabel(folded.policies[firstPolicy]!)).toBeNull();
  });

  it("restates the fold as the envelope's enrichment, aggregation and all", () => {
    // The member §7 defined when the format was drafted and nothing wrote.
    expect(folded.enrichment?.aggregation).toBe(folded.policies[0]?.aggregation);
    expect(folded.enrichment?.aggregation).not.toBeNull();
    expect(folded.enrichment?.policy_id).toBeNull();
    expect(plain.enrichment?.aggregation).toBeNull();
  });
});

describe("a column the fold did not cover", () => {
  it("is null in the file and nothing at all in the reader", () => {
    const index = buildIndex(folded, firstFold);
    const rate = index.nodes.get("mort_rate_mth@1");
    expect(rate).toBeDefined();
    expect((rate?.value_sample as unknown[])[firstFold]).toBeNull();
    expect(index.sampleOf("mort_rate_mth@1")).toBeUndefined();
    expect(unfolded(index, "mort_rate_mth@1")).toBe(true);
  });

  it("says so in the proof, in place of a result", () => {
    const index = buildIndex(folded, firstFold);
    const proof = proofOf(index, "mort_rate_mth@1", 0);
    expect(proof.lines.some((line) => line.kind === "fold" && line.text === DID_NOT_FOLD)).toBe(
      true,
    );
    expect(proof.lines.some((line) => line.kind === "result")).toBe(false);
  });

  it("is a policy's own value again the moment the reader moves off the fold", () => {
    const index = buildIndex(folded, firstPolicy);
    expect(unfolded(index, "mort_rate_mth@1")).toBe(false);
    expect(index.sampleOf("mort_rate_mth@1")).toBeDefined();
  });

  it("never claims a policy's values were not folded", () => {
    // The predicate has to be false on every column of a policy entry,
    // including the ones that carry nothing: a page saying "not folded" about
    // a policy would be inventing a fold that is not on the axis.
    const index = buildIndex(folded, firstPolicy);
    for (const node of folded.nodes) expect(unfolded(index, node.id)).toBe(false);
  });
});

describe("a column the fold did cover", () => {
  it("carries the fold's own number and says it is a fold", () => {
    const index = buildIndex(folded, firstFold);
    const id = covered(firstFold);
    expect(index.sampleOf(id)).toBeDefined();
    const proof = proofOf(index, id, 0);
    expect(proof.lines.some((line) => line.kind === "result")).toBe(true);
    expect(
      proof.lines.some(
        (line) => line.kind === "fold" && line.text === foldNote(folded.policies[firstFold]!),
      ),
    ).toBe(true);
  });

  it("shows no worked example, because nothing ran once for the book", () => {
    const index = buildIndex(folded, firstFold);
    expect(index.traceOf(covered(firstFold))).toBeUndefined();
    for (const node of folded.nodes) expect(index.traceOf(node.id)).toBeUndefined();
  });

  it("leaves every walk-through intact on the policy beneath it", () => {
    const index = buildIndex(folded, firstPolicy);
    expect(index.traceOf("pv_net_cf@1")).toBeDefined();
  });
});

describe("what the fold does not disturb", () => {
  it("moves nothing but the values between the fold and the policy", () => {
    const one = buildIndex(folded, firstFold);
    const two = buildIndex(folded, firstPolicy);
    expect(one.order).toEqual(two.order);
    for (const id of one.order) {
      expect(one.nodes.get(id)?.fingerprint).toBe(two.nodes.get(id)?.fingerprint);
    }
    expect(one.artifact.graph_fingerprint).toBe(two.artifact.graph_fingerprint);
  });

  it("reads a document with no fold exactly as it always did", () => {
    const index = buildIndex(plain);
    expect(isFold(index.policy)).toBe(false);
    for (const node of plain.nodes) expect(unfolded(index, node.id)).toBe(false);
  });
});
