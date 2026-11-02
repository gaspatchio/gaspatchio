// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * Where the cone puts a node.
 *
 * One layout of the whole graph, computed once and read from wherever a window
 * happens to fall. The alternative — laying out each window as it is drawn —
 * would move a node every time the reader widened the cone, and a node that
 * moves when nothing about it has changed is a node the reader has to find
 * again. Left to right, so that a column's inputs are to its left, the same
 * direction the grid's file order reads in.
 */

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { buildIndex } from "../src/reader/index";
import type { Artifact } from "../src/reader/types";
import { layoutAll, layoutOf, MAX_LAYOUT_NODES, NODE_SIZE } from "../src/layout/dagre";

const artifact = JSON.parse(
  readFileSync(new URL("../fixtures/level4.json", import.meta.url), "utf8"),
) as Artifact;
const index = buildIndex(artifact);
const placed = layoutAll(index, NODE_SIZE);

describe("layoutAll", () => {
  it("places every node the file carries", () => {
    expect(placed.size).toBe(index.order.length);
    for (const id of index.order) expect(placed.get(id)).toBeDefined();
  });

  it("puts no two nodes in one place", () => {
    const seen = new Set([...placed.values()].map(({ x, y }) => `${x},${y}`));
    expect(seen.size).toBe(placed.size);
  });

  it("puts what a column reads to its left", () => {
    for (const edge of artifact.edges) {
      const source = placed.get(edge.source);
      const target = placed.get(edge.target);
      expect(source).toBeDefined();
      expect(target).toBeDefined();
      expect(source!.x).toBeLessThan(target!.x);
    }
  });

  it("is the body's own size, so the drawing and the overview agree", () => {
    expect(NODE_SIZE).toEqual({ w: 220, h: 78 });
  });
});

describe("MAX_LAYOUT_NODES", () => {
  it("is four copies of the level-4 shape, where dagre's cold layout first costs a second", () => {
    expect(MAX_LAYOUT_NODES).toBe(512);
  });

  it("leaves the level-4 export well inside the whole-graph layout", () => {
    expect(index.order.length).toBe(128);
    expect(index.order.length).toBeLessThanOrEqual(MAX_LAYOUT_NODES);
    expect(placed.size).toBe(index.order.length);
  });

  it("lays out nothing at all above the count, rather than half a graph", () => {
    // Half a graph laid out is a picture of a model that does not exist. The
    // page says the layout was skipped and draws the window on its own.
    const grown = {
      ...artifact,
      nodes: Array.from({ length: MAX_LAYOUT_NODES + 1 }, (_node, at) => ({
        ...artifact.nodes[0]!,
        id: `grown-${String(at)}`,
        column: `grown_${String(at)}`,
      })),
      edges: [],
    };
    expect(layoutAll(buildIndex(grown), NODE_SIZE).size).toBe(0);
  });

  it("still lays out a window of any size, which is what the cone then draws", () => {
    const window = index.order.slice(0, 8);
    const only = layoutOf(window, artifact.edges, NODE_SIZE);
    expect(only.size).toBe(window.length);
    // And an edge naming a node outside the window is dropped, not invented.
    expect([...only.keys()].sort()).toEqual([...window].sort());
  });
});
