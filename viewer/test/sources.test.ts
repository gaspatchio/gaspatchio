// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * §7.3, read: the model's own text, and which line accounts for which column.
 *
 * The section's one stated guarantee is the one worth checking first — the
 * entry whose path is `model.source_path` carries exactly `model.source_sha` —
 * because it is what lets the page say the source it is showing is the source
 * that ran. The rest is the index the source view is drawn from: the entries by
 * the path the *nodes* spell, so a reader who followed `model.py:520` looks the
 * file up under the string the node gave them, and the lines a node accounts
 * for, read off `source_location` and off nothing else.
 *
 * Three files are read, and they are three different claims. The level-4 export
 * carries the text. The holes fixture carries the section with a payload that
 * says `withheld`, which is a decision recorded rather than a silence. The
 * level-3 export was written before the section existed and carries none of it,
 * which is not the same claim as carrying it empty.
 */

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { buildIndex, locationOf } from "../src/reader/index";
import type { Index } from "../src/reader/index";
import type { Artifact } from "../src/reader/types";

/** One committed fixture, indexed. */
function fixture(name: string): Index {
  return buildIndex(
    JSON.parse(readFileSync(new URL(`../fixtures/${name}.json`, import.meta.url), "utf8")) as Artifact,
  );
}

const level4 = fixture("level4");
const holes = fixture("holes");
const level3 = fixture("level3");

describe("the section", () => {
  it("is keyed by the same path the nodes carry", () => {
    for (const id of level4.order) {
      const where = locationOf(level4.nodes.get(id)?.source_location);
      if (where === null) continue;
      expect(level4.sources.has(where.path)).toBe(true);
    }
  });

  it("carries the model's text under the path the envelope stamps", () => {
    const only = level4.artifact.model.source_path ?? "";
    const entry = level4.sources.get(only);
    expect(entry).toBeDefined();
    expect(entry?.payload).toHaveProperty("text");
  });

  it("carries, for the model's own path, exactly the digest the envelope publishes", () => {
    const only = level4.artifact.model.source_path ?? "";
    expect(level4.sources.get(only)?.fingerprint).toBe(level4.artifact.model.source_sha);
  });

  it("tells a file with no section from a file with an empty one", () => {
    expect(level4.carriesSources).toBe(true);
    expect(holes.carriesSources).toBe(true);
    // `sources` is the one optional array in the envelope (§7), so a conforming
    // document may carry none — a file written before the section existed, or a
    // producer that left it out. Absent is a claim this reader has to be able to
    // make, because the sentence it prints for it is a different sentence from
    // the one for a producer that accounted for no file. Every export this
    // repository writes carries the section, so the case is made here rather
    // than kept as a fixture: level 3 with its one member taken away.
    const without = JSON.parse(
      readFileSync(new URL("../fixtures/level3.json", import.meta.url), "utf8"),
    ) as Artifact;
    delete without.sources;
    const index = buildIndex(without);
    expect(index.carriesSources).toBe(false);
    expect(index.sources.size).toBe(0);
    // And the file it was made from does carry one, which is what makes the
    // two sentences different sentences rather than one.
    expect(level3.carriesSources).toBe(true);
  });

  it("keeps a payload that says why it carries no text", () => {
    const entry = [...holes.sources.values()][0];
    expect(entry?.payload).toEqual({ omitted: "withheld" });
    // The path and the digest still travel, which is what lets a reader check a
    // copy of their own against what was left out.
    expect(entry?.fingerprint).toMatch(/^sha256:[0-9a-f]{64}$/);
  });
});

describe("the lines a node accounts for", () => {
  it("reads them off source_location and off nothing else", () => {
    const byLine = level4.accountedLines.get("model.py");
    expect(byLine).toBeDefined();
    let counted = 0;
    for (const id of level4.order) {
      const where = locationOf(level4.nodes.get(id)?.source_location);
      if (where === null || where.line === null) continue;
      counted += 1;
      expect(byLine?.get(where.line)).toContain(id);
    }
    // Every claim in the map came from a node, and every node with a location
    // is in the map: the two directions together are what make "a line no node
    // claims stays plain" a fact about the file rather than about this index.
    const claimed = [...(byLine?.values() ?? [])].reduce((all, ids) => all + ids.length, 0);
    expect(claimed).toBe(counted);
  });

  it("finds the line the level-4 maintenance fee was written on", () => {
    const node = level4.nodes.get("maint_fee_pp@1");
    const where = locationOf(node?.source_location);
    expect(where).toEqual({ path: "model.py", line: 520 });
    expect(level4.accountedLines.get("model.py")?.get(520)).toContain("maint_fee_pp@1");
  });

  it("leaves a line nothing was written on out of the map rather than empty in it", () => {
    // 519 is the comment above the maintenance fee. A page that answered
    // "nothing accounts for this" with an empty list and "nothing claims it"
    // with a missing key would have two spellings of one answer.
    expect(level4.accountedLines.get("model.py")?.has(519)).toBe(false);
  });
});

describe("splitting a location", () => {
  it("splits at the last colon, because a path may carry one of its own", () => {
    expect(locationOf("model.py:520")).toEqual({ path: "model.py", line: 520 });
    expect(locationOf("C:/work/model.py:12")).toEqual({ path: "C:/work/model.py", line: 12 });
  });

  it("says there is nowhere to go where the file records nothing", () => {
    expect(locationOf(null)).toBeNull();
    expect(locationOf(undefined)).toBeNull();
  });

  it("keeps a path with no line as a path", () => {
    expect(locationOf("model.py")).toEqual({ path: "model.py", line: null });
  });
});
