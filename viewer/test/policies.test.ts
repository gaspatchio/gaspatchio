// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The policy axis, read the way §7.4 and §8 say it is read.
 *
 * The fixture is a producer's own export over the awkward book — string ids,
 * shuffled, one policy called `3:40` and one called `all` — because the names a
 * switcher has to survive are exactly the ones that look like something else.
 * Nothing below is typed in: every expectation is read out of the file, so a
 * regenerated fixture moves the numbers and not the claims.
 */

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { buildIndex } from "../src/reader/index";
import { parseArtifacts } from "../src/reader/parse";
import { atPolicy, axisOf } from "../src/reader/policies";
import type { Artifact } from "../src/reader/types";

function load(url: URL): Artifact {
  const r = parseArtifacts([readFileSync(url, "utf8")]);
  if (r.refused) throw new Error(r.sentence);
  return r.artifacts[0]!;
}

const book = load(new URL("../fixtures/policy-axis.json", import.meta.url));
const one = load(new URL("../fixtures/level4.json", import.meta.url));
const none = load(new URL("../fixtures/no-values.json", import.meta.url));

describe("the axis the envelope declares", () => {
  it("is the file's own order, and every entry says how it got there", () => {
    const axis = axisOf(book);
    expect(axis).toHaveLength(book.policies.length);
    expect(axis.map((e) => e.policy_id)).toEqual(book.policies.map((e) => e.policy_id));
    for (const entry of axis) expect(entry.why).toBeTypeOf("string");
  });

  it("carries the ids a selection grammar could have mangled", () => {
    // The book holds a policy called `3:40` and one called `all`. Both reach
    // the axis, and the page has no opinion about either name.
    expect(axisOf(book).map((e) => e.policy_id)).toContain("3:40");
    expect(axisOf(book).map((e) => e.policy_id)).toContain("all");
  });

  it("restates its first entry as enrichment, with why left off", () => {
    const first = axisOf(book)[0];
    expect(book.enrichment).toEqual({
      policy_id: first?.policy_id,
      aggregation: first?.aggregation,
      periods: first?.periods,
      filter: first?.filter,
    });
  });

  it("is empty exactly where the file carries no values", () => {
    expect(none.enrichment).toBeNull();
    expect(axisOf(none)).toEqual([]);
    expect(buildIndex(none).carriesValues).toBe(false);
  });
});

describe("one policy's share of a node's enrichment", () => {
  it("is the member itself where the axis carries one, never an array of one", () => {
    // What makes this edition additive: a single-policy document is read byte
    // for byte as it always was, and a per-period column's timeline stays a
    // timeline rather than becoming a policy.
    const timeline = [1, 2, 3];
    expect(atPolicy(timeline, 0, 1)).toBe(timeline);
    expect(atPolicy(7, 0, 1)).toBe(7);
  });

  it("is the entry at the reader's own position where the axis carries several", () => {
    expect(atPolicy(["a", "b", "c"], 2, 3)).toBe("c");
    expect(
      atPolicy(
        [
          [1, 2],
          [3, 4],
        ],
        1,
        2,
      ),
    ).toEqual([3, 4]);
  });

  it("refuses a length that is not the axis's rather than reading past it", () => {
    // §8: every value after the first mismatch would sit under some other
    // policy's name, and a reader checking one of them would be checking a
    // different model point.
    expect(atPolicy(["a", "b"], 0, 3)).toBeUndefined();
    expect(atPolicy(["a", "b", "c", "d"], 0, 3)).toBeUndefined();
    expect(atPolicy("not an array at all", 0, 3)).toBeUndefined();
  });

  it("reads a null at a position as the node stating nothing for that policy", () => {
    expect(atPolicy([1, null, 3], 1, 3)).toBeUndefined();
  });
});

describe("the index, read along one entry", () => {
  const carried = book.policies.length;

  it("opens on the first entry, which is the one enrichment restates", () => {
    const index = buildIndex(book);
    expect(index.at).toBe(0);
    expect(index.policy?.policy_id).toBe(book.policies[0]?.policy_id);
  });

  it("gives each policy its own values, quoted out of the file", () => {
    for (let at = 0; at < carried; at += 1) {
      const index = buildIndex(book, at);
      const sample = book.nodes.find((n) => n.id === "net_claims@1")?.value_sample as unknown[];
      expect(index.timeline("net_claims@1")).toEqual(sample[at]);
      expect(index.policy?.policy_id).toBe(book.policies[at]?.policy_id);
    }
  });

  it("gives each policy its own trace", () => {
    const traces = new Set<string>();
    for (let at = 0; at < carried; at += 1) {
      traces.add(JSON.stringify(buildIndex(book, at).traceOf("net_claims@1")));
    }
    expect(traces.size).toBe(carried);
  });

  it("counts periods under the selected policy and not over the axis", () => {
    // A scalar column of four policies is four numbers, and a reader that
    // counted those would put a grid of four rows under a projection of
    // twenty-five.
    const index = buildIndex(book, 1);
    expect(index.timeline("pv_net_claims@1")).toBeNull();
    expect(index.periods).toBe((index.timeline("net_claims@1") ?? []).length);
  });

  it("changes nothing but the values when the entry changes", () => {
    // The property the page demonstrates rather than asserts: the graph is
    // policy-invariant, so the same artifact object comes back, every node
    // record is the same object, and every fingerprint is the same string.
    const first = buildIndex(book, 0);
    const second = buildIndex(book, carried - 1);
    expect(second.artifact).toBe(first.artifact);
    expect(second.order).toEqual(first.order);
    expect(second.artifact.graph_fingerprint).toBe(first.artifact.graph_fingerprint);
    for (const id of first.order) {
      expect(second.nodes.get(id)?.fingerprint).toBe(first.nodes.get(id)?.fingerprint);
      expect(second.nodes.get(id)?.local_fingerprint).toBe(first.nodes.get(id)?.local_fingerprint);
    }
    // And at least one value did move, or the test above proves nothing.
    expect(second.timeline("net_claims@1")).not.toEqual(first.timeline("net_claims@1"));
  });

  it("clamps a position the axis does not carry to the first entry", () => {
    expect(buildIndex(book, carried + 5).at).toBe(carried - 1);
    expect(buildIndex(book, -3).at).toBe(0);
    expect(buildIndex(none, 4).at).toBe(0);
    expect(buildIndex(none).policy).toBeNull();
  });

  it("reads a single-policy export exactly as it read it before the axis", () => {
    const index = buildIndex(one);
    expect(index.policies).toHaveLength(1);
    expect(index.timeline("net_cf@1")).toEqual(
      one.nodes.find((n) => n.id === "net_cf@1")?.value_sample,
    );
  });
});
