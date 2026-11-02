// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The tier census, against the census the core takes of the same documents.
 *
 * `fixtures/tier-census.json` is the core's census of every committed
 * fixture, read the way `gspio calc-graph` reads a document, written by
 * `tests/graph/test_tier_census.py` and held there to the core. Here the
 * page's own reading of each fixture is held to it: the counts at all three
 * tiers and the calculations named below core, in the file's order. One
 * fixture, `tiers`, was exported by the core from a model with a line at each
 * tier, so none of the three is compared only as a zero.
 *
 * Two more documents are held to it: the hand-built examples of the two
 * payload sections the specification reserves, a state graph and a nested
 * valuation, which no export of this package carries and which compute and
 * state a tier like any other calculation.
 */

import { readFileSync, readdirSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { TIERS, tiersOf } from "../src/reader/tiers";
import type { Artifact } from "../src/reader/types";

/** The core's census of one fixture, as the committed file states it. */
interface CoreCensus {
  counts: Record<string, number>;
  engine_native: string[];
  opaque: string[];
}

const core = JSON.parse(
  readFileSync(new URL("../fixtures/tier-census.json", import.meta.url), "utf8"),
) as Record<string, CoreCensus>;

/**
 * Every committed document the page is tested against: the fixtures that carry
 * a schema, less the ones the end-to-end run writes for itself.
 */
const documents = readdirSync(new URL("../fixtures/", import.meta.url))
  .filter((name) => name.endsWith(".json") && !/^(refusal|written)-/.test(name))
  .map((name) => ({
    name: name.replace(/\.json$/, ""),
    artifact: JSON.parse(
      readFileSync(new URL(`../fixtures/${name}`, import.meta.url), "utf8"),
    ) as Artifact,
  }))
  .filter(({ artifact }) => typeof artifact.schema === "string");

/** The two payload examples, under the name the core's census files them by. */
const PAYLOAD_EXAMPLES = ["goldens/state_graph_example", "goldens/nested_valuation_example"];

/** Where the core keeps its hand-built examples. */
const GOLDENS = "../../bindings/python/tests/graph/";

for (const name of PAYLOAD_EXAMPLES) {
  documents.push({
    name,
    artifact: JSON.parse(
      readFileSync(new URL(`${GOLDENS}${name}.json`, import.meta.url), "utf8"),
    ) as Artifact,
  });
}

/** A fixture, read fresh, so a test may edit it. */
function fixture(name: string): Artifact {
  return JSON.parse(
    readFileSync(new URL(`../fixtures/${name}.json`, import.meta.url), "utf8"),
  ) as Artifact;
}

/** One of the core's hand-built examples, read fresh. */
function golden(name: string): Artifact {
  return JSON.parse(
    readFileSync(new URL(`${GOLDENS}${name}.json`, import.meta.url), "utf8"),
  ) as Artifact;
}

describe("the page's census and the core's", () => {
  it("is taken of every committed document, and the core's file names each one", () => {
    expect(documents.length).toBeGreaterThanOrEqual(21);
    expect(Object.keys(core).sort()).toEqual(documents.map(({ name }) => name).sort());
  });

  it("counts every tier as the core does, and names the same calculations below core", () => {
    for (const { name, artifact } of documents) {
      const read = tiersOf(artifact);
      const said = core[name];
      if (said === undefined || read === null || !("census" in read)) {
        throw new Error(`${name}: the page states no census where the core states one`);
      }
      const counts = Object.fromEntries(TIERS.map((tier) => [tier, read.census[tier].length]));
      expect(counts, name).toEqual(said.counts);
      expect(read.census.engine_native, name).toEqual(said.engine_native);
      expect(read.census.opaque, name).toEqual(said.opaque);
    }
  });

  it("reaches all three tiers on the fixture the core exported for it", () => {
    expect(core["tiers"]?.counts).toEqual({ core: 8, engine_native: 2, opaque: 1 });
  });
});

describe("what the census counts, and when it states none", () => {
  it("counts a state graph and a nested valuation, each at the tier it states", () => {
    for (const [name, kind] of [
      ["goldens/state_graph_example", "state_graph"],
      ["goldens/nested_valuation_example", "nested_valuation"],
    ]) {
      const artifact = golden(String(name));
      const payload = artifact.nodes.find((node) => node.kind === kind);
      if (payload === undefined) throw new Error(`${String(name)} carries no ${String(kind)}`);
      payload.tier = "opaque";
      const read = tiersOf(artifact);
      if (read === null || !("census" in read)) throw new Error(`${String(name)}: no census`);
      expect(read.census.opaque, String(name)).toEqual([payload.id]);
    }
  });

  it("counts no input, hole or running state, which compute nothing", () => {
    for (const name of ["holes", "rollforward"]) {
      const artifact = fixture(name);
      const read = tiersOf(artifact);
      if (read === null || !("census" in read)) throw new Error(`${name}: no census`);
      const counted = TIERS.flatMap((tier) => read.census[tier]);
      const computing = artifact.nodes
        .filter((node) => node.kind === "computed" || node.kind === "rollforward")
        .map((node) => node.id);
      expect(counted.sort()).toEqual(computing.sort());
      expect(artifact.nodes.some((node) => node.kind !== "computed" && node.kind !== "rollforward"))
        .toBe(true);
    }
  });

  it("states no census, rather than three zeros, for a file that records no tier", () => {
    const artifact = fixture("level4");
    for (const node of artifact.nodes) delete (node as Partial<typeof node>).tier;
    expect(tiersOf(artifact)).toBeNull();
  });

  it("names the calculation that carries no tier the format defines, and what it carries", () => {
    for (const written of [null, "fast"]) {
      const artifact = fixture("tiers");
      const node = artifact.nodes.find((one) => one.id === "loaded_claims@1");
      if (node === undefined) throw new Error("the tiers fixture lost loaded_claims@1");
      node.tier = written;
      expect(tiersOf(artifact)).toEqual({ untiered: "loaded_claims@1", tier: written });
    }
  });
});
