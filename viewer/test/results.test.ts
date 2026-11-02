// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * Where a model ends, read off the file and not off a naming convention.
 *
 * The page opens on the last of these and the search box offers all of them, so
 * what this picks is the first thing an actuary sees. Held to the two things
 * that make it honest: it is a fact about the edges — a column with a formula
 * that nothing else reads — and it never becomes a claim that these are the
 * results. `projection_date` qualifies on every model in this corpus and is a
 * date label; a rule that excluded it would be reading names, which is the
 * inference this file exists to avoid.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { buildIndex } from "../src/reader/index";
import type { Artifact } from "../src/reader/types";
import { endsOf, openingColumn } from "../src/reader/results";

function fixture(name: string) {
  return buildIndex(
    JSON.parse(readFileSync(resolve(`fixtures/${name}.json`), "utf8")) as Artifact,
  );
}

describe("where the model ends", () => {
  it.each([
    ["level3", "pv_net_cf"],
    ["level4", "pv_net_cf"],
    ["level5", "pv_net_cf"],
    ["rollforward", "av_growth"],
    ["level1", "is_profitable"],
  ])("opens %s on %s", (name, column) => {
    const index = fixture(name);
    const opening = openingColumn(index);
    expect(opening).not.toBeNull();
    expect(index.nodes.get(opening ?? "")?.column).toBe(column);
  });

  it("takes only columns nothing else reads", () => {
    const index = fixture("level4");
    for (const id of endsOf(index)) {
      expect(index.readBy.get(id) ?? []).toEqual([]);
    }
  });

  it("takes only columns the model computed, never one that arrived", () => {
    const index = fixture("level4");
    for (const id of endsOf(index)) {
      expect(typeof index.nodes.get(id)?.formula).toBe("string");
    }
    // `sum_assured` arrives with the model point and nothing reads it on this
    // model either — it is a sink and it is not an end, which is the whole of
    // the difference the formula makes here.
    expect(endsOf(index)).not.toContain("sum_assured@1");
  });

  it("ends on the last of them, which is the model's own order", () => {
    const index = fixture("level4");
    const ends = endsOf(index);
    expect(openingColumn(index)).toBe(ends[ends.length - 1]);
  });

  it("offers a small enough set to read at a glance", () => {
    for (const name of ["level1", "level3", "level4", "level5", "rollforward", "holes"]) {
      expect(endsOf(fixture(name)).length).toBeLessThanOrEqual(8);
    }
  });
});
