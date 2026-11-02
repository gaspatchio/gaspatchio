// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * What the window controls do, read without a browser.
 *
 * The window management's rules are mostly claims about states rather than about pixels,
 * and the states live in `state/layout.ts`. What is asserted here is the part a
 * screenshot cannot show: that a collapse always leaves a rail, that an
 * expansion is a gesture the railed set survives, that Escape puts back exactly
 * what was there, and that the `read` layout is the absence of everything — the
 * clause the four scripted reads depend on.
 */

import { describe, expect, it } from "vitest";

import {
  initialPaneState,
  LAYOUTS,
  LAYOUT_NAMES,
  layoutOf,
  PANE_LABELS,
  PANES,
  railed,
  reducePanes,
} from "../src/state/layout";
import type { PaneState } from "../src/state/layout";

describe("what a pane is called on the page", () => {
  it("is the Audit View documentation's word for it, never the id the code keys it by", () => {
    // The four words the documentation teaches, and the pane that carries each:
    // the proof rides under the derivation, so one pane answers to both.
    expect(PANE_LABELS).toEqual({
      grid: "worksheet",
      cone: "derivation and proof",
      inspector: "record",
    });
    for (const pane of PANES) expect(PANE_LABELS[pane]).not.toContain(pane);
  });
});

describe("the default", () => {
  it("rails nothing and expands nothing, which is the read layout", () => {
    expect(initialPaneState).toEqual({ railed: [], expanded: null });
    expect(layoutOf(initialPaneState)).toBe("read");
    for (const pane of PANES) expect(railed(initialPaneState, pane)).toBe(false);
  });
});

describe("collapse and open", () => {
  it("rails the pane it is given and leaves the others alone", () => {
    const after = reducePanes(initialPaneState, { collapse: "cone" });
    expect(after.railed).toEqual(["cone"]);
    expect(railed(after, "cone")).toBe(true);
    expect(railed(after, "grid")).toBe(false);
  });

  it("keeps the railed set in one order however it was reached", () => {
    const one = reducePanes(reducePanes(initialPaneState, { collapse: "inspector" }), {
      collapse: "cone",
    });
    const other = reducePanes(reducePanes(initialPaneState, { collapse: "cone" }), {
      collapse: "inspector",
    });
    expect(one.railed).toEqual(other.railed);
  });

  it("opens a railed pane and rails it again on a toggle", () => {
    const away = reducePanes(initialPaneState, { toggle: "inspector" });
    expect(away.railed).toEqual(["inspector"]);
    expect(reducePanes(away, { toggle: "inspector" }).railed).toEqual([]);
  });

  it("hands back the same state where the move changes nothing", () => {
    const away = reducePanes(initialPaneState, { collapse: "grid" });
    expect(reducePanes(away, { collapse: "grid" })).toBe(away);
    expect(reducePanes(initialPaneState, { open: "grid" })).toBe(initialPaneState);
    expect(reducePanes(initialPaneState, { restore: true })).toBe(initialPaneState);
  });
});

describe("expansion", () => {
  it("rails every other pane while it stands, and none of them in the stored set", () => {
    const wide = reducePanes(initialPaneState, { expand: "cone" });
    expect(wide.expanded).toBe("cone");
    // The set a reader chose is still empty: an expansion is a gesture, and
    // it is never remembered. `railed()` is what makes the other three
    // rails for as long as it lasts.
    expect(wide.railed).toEqual([]);
    expect(railed(wide, "cone")).toBe(false);
    for (const pane of ["grid", "inspector"] as const) {
      expect(railed(wide, pane)).toBe(true);
    }
  });

  it("puts back exactly the rails that were there before it", () => {
    const chosen = reducePanes(initialPaneState, { collapse: "inspector" });
    const wide = reducePanes(chosen, { expand: "grid" });
    const back = reducePanes(wide, { restore: true });
    expect(back.railed).toEqual(["inspector"]);
    expect(back.expanded).toBeNull();
    expect(railed(back, "grid")).toBe(false);
    expect(railed(back, "inspector")).toBe(true);
  });

  it("takes a pane off its rail when that pane is the one expanded", () => {
    const chosen = reducePanes(initialPaneState, { collapse: "cone" });
    const wide = reducePanes(chosen, { expand: "cone" });
    expect(wide.railed).toEqual([]);
    expect(wide.expanded).toBe("cone");
  });

  it("ends when a railed pane is opened, because opening it asks to see it", () => {
    const wide = reducePanes(initialPaneState, { expand: "grid" });
    const after = reducePanes(wide, { open: "cone" });
    expect(after.expanded).toBeNull();
    expect(railed(after, "cone")).toBe(false);
  });

  it("collapses the expanded pane into a rail rather than into nothing", () => {
    const wide = reducePanes(initialPaneState, { expand: "cone" });
    const after = reducePanes(wide, { collapse: "cone" });
    expect(after.expanded).toBeNull();
    expect(railed(after, "cone")).toBe(true);
  });
});

describe("no state hides a pane", () => {
  it("leaves every pane either drawn or railed, after any move", () => {
    const moves = [
      { collapse: "grid" },
      { expand: "cone" },
      { collapse: "cone" },
      { open: "grid" },
      { toggle: "inspector" },
      { layout: "table" },
      { layout: "source" },
      { restore: true },
      { layout: "lineage" },
    ] as const;
    let state: PaneState = initialPaneState;
    for (const move of moves) {
      state = reducePanes(state, move);
      // No control hides a pane, as an assertion: a pane is a region
      // or it is a rail, and there is no third answer this reducer can give.
      for (const pane of PANES) expect(typeof railed(state, pane)).toBe("boolean");
      expect(PANES.filter((pane) => !railed(state, pane)).length).toBeGreaterThan(0);
    }
  });
});

describe("the four layouts", () => {
  it("each names itself back from the states it sets", () => {
    for (const name of LAYOUT_NAMES) {
      expect(layoutOf(reducePanes(initialPaneState, { layout: name }))).toBe(name);
    }
  });

  it("gives every layout its own letter", () => {
    const letters = LAYOUT_NAMES.map((name) => LAYOUTS[name].key);
    expect(new Set(letters).size).toBe(letters.length);
  });

  it("stops naming a layout the moment the reader leaves it", () => {
    const table = reducePanes(initialPaneState, { layout: "table" });
    expect(layoutOf(table)).toBe("table");

    // Railing one more pane than the layout asks for is leaving it. (Opening
    // the cone instead would land on `read`, which is a layout too — the point
    // here is that a state no layout describes is named by none of them.)
    expect(layoutOf(reducePanes(table, { collapse: "inspector" }))).toBeNull();
  });

  it("puts the drawer on the source tab for the source layout alone", () => {
    expect(LAYOUTS.source.tab).toBe("source");
    for (const name of ["read", "table", "lineage"] as const) {
      expect(LAYOUTS[name].tab).toBeUndefined();
    }
  });

  it("leaves the read layout as the absence of everything", () => {
    expect(LAYOUTS.read.railed).toEqual([]);
    expect(LAYOUTS.read.expanded).toBeNull();
  });
});
