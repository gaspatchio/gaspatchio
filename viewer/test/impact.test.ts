// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * What moves if this changes, held to being a fact about the edges.
 *
 * The block this feeds is the one a reviewer will quote when they ask whether a
 * change to an assumption reaches the result, so the two properties that matter
 * are that it is complete — a chain of any length, not two steps — and that it
 * is closed under the file's own edges rather than under a naming convention.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { descendantsOf, endsReached } from "../src/reader/impact";
import { buildIndex } from "../src/reader/index";
import { endsOf } from "../src/reader/results";
import type { Artifact } from "../src/reader/types";
import { coneWindow } from "../src/reader/window";

function fixture(name: string) {
  return buildIndex(
    JSON.parse(readFileSync(resolve(`fixtures/${name}.json`), "utf8")) as Artifact,
  );
}

const level4 = fixture("level4");

describe("what moves if this changes", () => {
  it("reaches further than the cone's two steps", () => {
    const near = new Set(coneWindow(level4, "lapse_rate@1", 0, 2).nodes);
    const all = descendantsOf(level4, "lapse_rate@1");
    expect(all.length).toBeGreaterThan(near.size);
    // Everything two steps down is in it, and it does not stop there.
    for (const id of near) {
      if (id !== "lapse_rate@1") expect(all).toContain(id);
    }
  });

  it("is closed: every reader of something downstream is downstream", () => {
    const all = new Set(descendantsOf(level4, "lapse_rate@1"));
    for (const id of all) {
      for (const reader of level4.readBy.get(id) ?? []) {
        expect(all.has(reader)).toBe(true);
      }
    }
  });

  it("does not include the column that changed", () => {
    expect(descendantsOf(level4, "lapse_rate@1")).not.toContain("lapse_rate@1");
  });

  it("names the model's own ends among them, and nothing that is not one", () => {
    const ends = new Set(endsOf(level4));
    const reached = endsReached(level4, "lapse_rate@1");
    expect(reached.length).toBeGreaterThan(0);
    for (const id of reached) expect(ends.has(id)).toBe(true);

    // The one an actuary is asking about: a change to the lapse basis reaches
    // the model's bottom line.
    expect(reached.map((id) => level4.nodes.get(id)?.column)).toContain("pv_net_cf");
  });

  it("says nothing moves where a column is the end of its own chain", () => {
    const last = endsOf(level4).at(-1) ?? "";
    expect(descendantsOf(level4, last)).toEqual([]);
    expect(endsReached(level4, last)).toEqual([]);
  });

  it("terminates on a graph that reads itself", () => {
    // The rollforward's state is read by the node that writes it; a walk bounded
    // by depth would be fine and a walk bounded by `seen` is what makes this
    // safe, so it is asserted rather than assumed.
    const rollforward = fixture("rollforward");
    for (const id of rollforward.order) {
      expect(Array.isArray(descendantsOf(rollforward, id))).toBe(true);
    }
  });
});
