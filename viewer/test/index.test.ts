// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { buildIndex } from "../src/reader/index";
import { parseArtifacts } from "../src/reader/parse";
import type { Artifact, Narrowing } from "../src/reader/types";

function load(url: URL): Artifact {
  const r = parseArtifacts([readFileSync(url, "utf8")]);
  if (r.refused) throw new Error(r.sentence);
  return r.artifacts[0]!;
}

const level4 = load(new URL("../fixtures/level4.json", import.meta.url));
const corpus = load(
  new URL("../../bindings/python/gaspatchio/schemas/conformance/corpus.json", import.meta.url),
);

describe("buildIndex over level 4", () => {
  const index = buildIndex(level4);

  it("puts every edge in both directions", () => {
    for (const edge of level4.edges) {
      expect(index.readsOf.get(edge.target) ?? []).toContain(edge.source);
      expect(index.readBy.get(edge.source) ?? []).toContain(edge.target);
    }
  });

  it("reads the period a formula looked at from the facet, not the trace", () => {
    expect(index.readsOf.get("shifted_growth@1")).toContain("combined_growth_factor@1");
    expect(index.offsetOf("shifted_growth@1", "combined_growth_factor@1")).toBe(-1);
  });

  it("carries three offsets and 181 narrowings without one", () => {
    const narrowings: Narrowing[] = [];
    for (const bySource of index.narrowing.values()) {
      for (const narrowing of bySource.values()) narrowings.push(narrowing);
    }
    expect(narrowings.filter((n) => n.offset !== undefined)).toHaveLength(3);
    expect(narrowings.filter((n) => n.offset === undefined)).toHaveLength(181);
  });

  it("keeps an accumulation's convention as the file states it", () => {
    expect(index.nodes.get("survival_prob@1")?.settings).toEqual({
      start_at: 1.0,
      from_survival: false,
    });
  });

  it("gives a list node its whole timeline, and the period count is its length", () => {
    expect(index.timeline("net_cf@1")).toHaveLength(83);
    expect(index.periods).toBe(83);
  });

  it("returns no timeline for a scalar node", () => {
    expect(index.timeline("policy_term@1")).toBeNull();
  });

  it("counts 70 per-period columns and 58 scalar ones", () => {
    expect(index.perPeriodColumns).toHaveLength(70);
    expect(index.scalarColumns).toHaveLength(58);
  });

  it("keeps the file's node order", () => {
    expect(index.order).toEqual(level4.nodes.map((n) => n.id));
  });

  it("names no id the file does not carry", () => {
    for (const node of level4.nodes) {
      for (const read of node.reads) expect(index.nodes.has(read)).toBe(true);
    }
  });

  it("keys the assumption tables by the name the file gives them", () => {
    expect(index.tables.size).toBe(level4.assumptions.length);
    expect(index.tables.has("mortality_select")).toBe(true);
  });
});

describe("buildIndex over the published corpus", () => {
  const index = buildIndex(corpus);

  it("puts every edge in both directions", () => {
    for (const edge of corpus.edges) {
      expect(index.readsOf.get(edge.target) ?? []).toContain(edge.source);
      expect(index.readBy.get(edge.source) ?? []).toContain(edge.target);
    }
  });

  it("says a file with no values has no periods", () => {
    const longest = Math.max(
      0,
      ...corpus.nodes.map((n) => (Array.isArray(n.value_sample) ? n.value_sample.length : 0)),
    );
    expect(index.periods).toBe(longest);
    expect(index.periods).toBe(0);
  });

  it("keeps the file's node order", () => {
    expect(index.order).toEqual(corpus.nodes.map((n) => n.id));
  });

  it("names no id the file does not carry", () => {
    for (const node of corpus.nodes) {
      for (const read of node.reads) expect(index.nodes.has(read)).toBe(true);
    }
  });

  it("reads the window the published total states, and none where it states none", () => {
    // `.list.sum()` over the per-period claims: the whole run (§9).
    expect(index.windowsOf("total_claims@1", "select_loaded_claims@1")).toEqual([
      { type: "DIRECT", subtype: "AGGREGATION", periods: { from: "first", to: "last" } },
    ]);
    expect(index.windowsOf("prior_period_claims@1", "select_loaded_claims@1")).toEqual([]);
    expect(index.offsetOf("prior_period_claims@1", "select_loaded_claims@1")).toBe(-1);
  });
});

describe("buildIndex over the rollforward export", () => {
  const rollforward = load(new URL("../fixtures/rollforward.json", import.meta.url));
  const index = buildIndex(rollforward);

  it("carries the compiled node's states beside the columns", () => {
    expect(index.nodes.get("state:av@eop")?.kind).toBe("state");
    expect([...index.nodes.values()].some((n) => n.kind === "rollforward")).toBe(true);
  });

  it("puts every edge in both directions", () => {
    for (const edge of rollforward.edges) {
      expect(index.readsOf.get(edge.target) ?? []).toContain(edge.source);
      expect(index.readBy.get(edge.source) ?? []).toContain(edge.target);
    }
  });
});
