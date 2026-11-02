// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * What a railed pane says about itself, over the files it would say it about.
 *
 * A rail's two claims, checked against real exports rather than against a
 * fixture written to make them true: a rail carries the pane's one live figure,
 * and an amber admission travels to it in words. The second is the one worth
 * testing, because it is the clause that stops a collapse turning a hole into a
 * blank strip, and the holes fixture and the no-values fixture are the two
 * files that have something to admit.
 */

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { formatValue, isIntegerDtype } from "../src/reader/format";
import { buildIndex } from "../src/reader/index";
import type { Index } from "../src/reader/index";
import type { Artifact } from "../src/reader/types";
import { railFigure } from "../src/shell/rails";
import type { Selection } from "../src/state/selection";

/** One committed fixture, indexed. */
function fixture(name: string): Index {
  return buildIndex(
    JSON.parse(readFileSync(new URL(`../fixtures/${name}.json`, import.meta.url), "utf8")) as Artifact,
  );
}

const level4 = fixture("level4");
const holes = fixture("holes");
const noValues = fixture("no-values");

/** Where the reader is looking, with only what a case cares about spelled out. */
function at(part: Partial<Selection>): Selection {
  return { nodeId: null, period: 0, up: 2, down: 2, revealed: null, ...part };
}

describe("the grid's rail", () => {
  it("says which period the cursor is on and what is under it", () => {
    const figure = railFigure(level4, at({ nodeId: "maint_fee_pp@1", period: 62 }), "node", "grid");
    expect(figure.says).toContain("period 62");
    expect(figure.says).toContain("maint_fee_pp");
    expect(figure.admits).toBe(false);
  });

  it("quotes the value the grid would have drawn in that cell", () => {
    // Not a number typed into this test: the fixture's own value at that
    // period, put through the same two functions the grid's cells go through,
    // so a figure that stopped agreeing with the cell behind it fails here.
    const node = level4.nodes.get("maint_fee_pp@1");
    const sample = level4.timeline("maint_fee_pp@1");
    const expected = formatValue(sample?.[62], {
      integer: node !== undefined && isIntegerDtype(node.dtype),
    });
    const figure = railFigure(level4, at({ nodeId: "maint_fee_pp@1", period: 62 }), "node", "grid");
    expect(figure.says).toBe(`period 62 · maint_fee_pp ${expected}`);
  });

  it("carries a file with no values to the rail, in amber", () => {
    const figure = railFigure(noValues, at({}), "node", "grid");
    expect(figure.says).toBe("this file carries no values");
    expect(figure.admits).toBe(true);
  });
});

describe("the cone's rail", () => {
  it("says how much of the graph is in the window and what it is centred on", () => {
    const figure = railFigure(level4, at({ nodeId: "maint_fee_pp@1" }), "node", "cone");
    expect(figure.says).toContain(`of ${String(level4.order.length)}`);
    expect(figure.says).toContain("centre maint_fee_pp");
    expect(figure.admits).toBe(false);
  });

  it("says so in amber when the centre is a column nothing accounts for", () => {
    const figure = railFigure(holes, at({ nodeId: "reserve_override" }), "node", "cone");
    expect(figure.says).toContain("reserve_override unaccounted for");
    expect(figure.admits).toBe(true);
  });
});

describe("the cone's rail, which speaks for the worked example under it", () => {
  it("says the idiom, the column and what it came to", () => {
    const figure = railFigure(level4, at({ nodeId: "maint_fee_pp@1", period: 62 }), "node", "cone");
    expect(figure.says).toContain("arithmetic · maint_fee_pp · ");
    expect(figure.admits).toBe(false);
  });

  it("carries a hole's own admission to the rail, in amber", () => {
    const figure = railFigure(holes, at({ nodeId: "reserve_override" }), "node", "cone");
    expect(figure.says).toContain("hole · reserve_override unaccounted for");
    expect(figure.admits).toBe(true);
  });

  it("says a file carries no values rather than a worked example it has not got", () => {
    const first = noValues.order[0] ?? "";
    const figure = railFigure(noValues, at({ nodeId: first }), "node", "cone");
    expect(figure.says).toContain("this file carries no values");
    expect(figure.admits).toBe(true);
  });
});

describe("the drawer's rail", () => {
  it("says which tab is open", () => {
    expect(railFigure(level4, at({}), "table", "inspector")).toEqual({
      says: "table",
      admits: false,
    });
    expect(railFigure(level4, at({}), "source", "inspector").says).toBe("source");
  });

  it("counts the file's holes on it, in amber, and reads the envelope for the count", () => {
    const figure = railFigure(holes, at({}), "model", "inspector");
    expect(figure.says).toBe(`model · ${String(holes.artifact.holes.length)} holes`);
    expect(figure.admits).toBe(true);
  });
});

describe("every rail", () => {
  it("says something on every pane, whatever is selected", () => {
    for (const index of [level4, holes, noValues]) {
      for (const pane of ["grid", "cone", "inspector"] as const) {
        const figure = railFigure(index, at({}), "node", pane);
        expect(figure.says.length).toBeGreaterThan(0);
      }
    }
  });
});
