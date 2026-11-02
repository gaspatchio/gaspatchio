// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The window a read states (§9), read off the facet and written for a reviewer.
 *
 * `periods` and `position` are the producer's to state, quoted from each
 * operation's own attributes; this page labels them and outlines them, and
 * never works one out from a formula. The level-4 fixture predates the two
 * members, so the cases below hand it the window the producer now writes for
 * its survival fold — `{first, −1}`, the fold under the default opening of 1.0
 * — and read it back through the index and the proof panel.
 */

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { buildIndex } from "../src/reader/index";
import { parseArtifacts } from "../src/reader/parse";
import { statesWindow, windowLabel, windowRows } from "../src/reader/periods";
import { proofOf } from "../src/reader/proof";
import type { Artifact, Narrowing } from "../src/reader/types";

function load(url: URL): Artifact {
  const r = parseArtifacts([readFileSync(url, "utf8")]);
  if (r.refused) throw new Error(r.sentence);
  return r.artifacts[0]!;
}

const FOLD = "survival_prob@1";
const DECREMENT = "combined_decrement@1";
const BEFORE_NOW: Narrowing = {
  type: "DIRECT",
  subtype: "AGGREGATION",
  periods: { from: "first", to: -1 },
};

/** Level 4 with its survival fold's read stating the window the producer writes. */
function level4WithTheFoldsWindow(): Artifact {
  const artifact = load(new URL("../fixtures/level4.json", import.meta.url));
  const fold = artifact.nodes.find((node) => node.id === FOLD);
  const read = fold?.facets.gaspatchio_column_transformation?.reads.find(
    (one) => one.source === DECREMENT,
  );
  if (read === undefined) throw new Error("the fixture's fold reads no decrement");
  read.transformations = [BEFORE_NOW];
  return artifact;
}

describe("windowLabel", () => {
  it.each([
    [{ from: "first", to: 0 }, "first…t"],
    [{ from: 0, to: "last" }, "t…last"],
    [{ from: "first", to: "last" }, "first…last"],
    [{ from: "first", to: -1 }, "first…t−1"],
    [{ from: -2, to: 3 }, "t−2…t+3"],
  ] as const)("writes %j as %s", (periods, label) => {
    expect(windowLabel({ type: "DIRECT", subtype: "AGGREGATION", periods })).toBe(label);
  });

  it("writes a position as the index the call named", () => {
    expect(windowLabel({ type: "DIRECT", subtype: "TRANSFORMATION", position: 0 })).toBe("[0]");
    expect(windowLabel({ type: "DIRECT", subtype: "TRANSFORMATION", position: -1 })).toBe("[−1]");
  });

  it("says nothing where the facet states nothing", () => {
    const plain: Narrowing = { type: "DIRECT", subtype: "TRANSFORMATION", offset: -1 };
    expect(windowLabel(plain)).toBeNull();
    expect(statesWindow(plain)).toBe(false);
  });
});

describe("windowRows", () => {
  it("covers the run to date, and nothing before the first period", () => {
    expect(windowRows(BEFORE_NOW, 3, 6)).toEqual([0, 1, 2]);
    expect(windowRows(BEFORE_NOW, 0, 6)).toEqual([]);
  });

  it("stops at the policy's own last period", () => {
    const rest: Narrowing = { type: "DIRECT", subtype: "AGGREGATION", periods: { from: 0, to: "last" } };
    expect(windowRows(rest, 4, 6)).toEqual([4, 5]);
  });

  it("counts a negative position back from the run's own length", () => {
    const last: Narrowing = { type: "DIRECT", subtype: "TRANSFORMATION", position: -1 };
    expect(windowRows(last, 0, 3)).toEqual([2]);
    expect(windowRows({ ...last, position: 7 }, 0, 3)).toEqual([]);
  });
});

describe("the index and the proof panel read the window off the facet", () => {
  const index = buildIndex(level4WithTheFoldsWindow());

  it("keeps every window a read states", () => {
    expect(index.windowsOf(FOLD, DECREMENT)).toEqual([BEFORE_NOW]);
    expect(index.windowsOf(FOLD, "nothing@1")).toEqual([]);
    expect(index.offsetOf(FOLD, DECREMENT)).toBeUndefined();
  });

  it("names the window on the operand's line", () => {
    const line = proofOf(index, FOLD, 12).lines.find((l) => l.operand === DECREMENT);
    expect(line?.window).toBe("first…t−1");
  });

  it("states no window on a file written before the members existed", () => {
    const untouched = buildIndex(load(new URL("../fixtures/level4.json", import.meta.url)));
    expect(untouched.windowsOf(FOLD, DECREMENT)).toEqual([]);
    const line = proofOf(untouched, FOLD, 12).lines.find((l) => l.operand === DECREMENT);
    expect(line?.window).toBeUndefined();
  });
});
