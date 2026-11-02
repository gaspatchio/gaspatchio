// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * Where every node sits, decided once for the whole graph.
 *
 * The alternative is laying out each window as it is drawn, and it is worse in
 * the way that matters: widening the cone by one step would move every node
 * already on the screen, and a node that moves when nothing about it changed
 * is a node the reader has to find again. One layout means a node is in the
 * same place whichever window it is seen through, and the overview can draw
 * the whole graph and the window in one coordinate system.
 *
 * Left to right, because that is the direction a calculation reads: a column's
 * inputs are to its left, the same order the file's nodes arrive in and the
 * same order the grid puts them in.
 */

import dagre from "@dagrejs/dagre";

import type { Index } from "../reader/index";
import type { Edge } from "../reader/types";

/**
 * The node body's own size, the one `MAX_LAYOUT_NODES` was measured at. The
 * layout and the overview share it.
 */
export const NODE_SIZE = { w: 220, h: 78 } as const;

/** Between two nodes in one rank, and between two ranks. */
export const NODE_SEPARATION = 24;
export const RANK_SEPARATION = 80;

/**
 * The graph size above which the whole-graph layout is not attempted.
 *
 * A fixed count, because a number a reviewer can read beats a behaviour that
 * varies by laptop. A time budget would make the page's own behaviour depend on
 * the machine it was opened on, and two reviewers looking at one file would see
 * two different pages.
 *
 * The number is measured, not a guess. On 2026-09-16, before this page was
 * built, the frame-time harness ran a prototype of it over k disjoint copies
 * of the level-4 shape until it failed, and the ×4 row — 512 nodes, 736
 * edges — is where it first does: the cold layout takes 610 ms against 179 ms
 * at 128, the scrub's p95 reaches 33.2 ms, and five of eighty-three frames
 * cross the 30 fps budget. Above that row the curve is super-linear and it is
 * dagre and not React Flow that fails: 1.76 s at 1,024 and 24.1 s at 4,096,
 * the last of those about 94% of a twenty-six-second cold open.
 *
 * So 512 is the last size measured to open in about a second, and the page
 * draws the selected window at its own layout above it rather than making a
 * reader wait on a layout of a graph they cannot read at that zoom anyway.
 */
export const MAX_LAYOUT_NODES = 512;

/** Where one node's top-left corner goes. */
export interface Placement {
  x: number;
  y: number;
}

/**
 * Lay out one set of nodes and the edges between them.
 *
 * @param ids - The nodes to place, in the order they should be fed to dagre,
 *   which is the file's order and so the model's own.
 * @param edges - Candidate edges. One naming a node not in `ids` is dropped
 *   rather than drawn: dagre would invent the missing node, and an invented
 *   node is a node the file does not hold.
 * @param size - The node body's size. Positions are the body's top-left corner,
 *   which is what React Flow places a node by; dagre works in centres, so the
 *   half-sizes come off here rather than at each call site.
 * @returns Every id's position.
 */
export function layoutOf(
  ids: readonly string[],
  edges: readonly Edge[],
  size: { w: number; h: number },
): Map<string, Placement> {
  const graph = new dagre.graphlib.Graph({ directed: true });
  graph.setGraph({
    rankdir: "LR",
    nodesep: NODE_SEPARATION,
    ranksep: RANK_SEPARATION,
  });
  graph.setDefaultEdgeLabel(() => ({}));

  const held = new Set(ids);
  for (const id of ids) graph.setNode(id, { width: size.w, height: size.h });
  for (const edge of edges) {
    if (!held.has(edge.source) || !held.has(edge.target)) continue;
    graph.setEdge(edge.source, edge.target);
  }

  dagre.layout(graph);

  const placed = new Map<string, Placement>();
  for (const id of ids) {
    const node = graph.node(id) as { x?: number; y?: number } | undefined;
    placed.set(id, {
      x: (node?.x ?? 0) - size.w / 2,
      y: (node?.y ?? 0) - size.h / 2,
    });
  }
  return placed;
}

/**
 * Lay the whole graph out once.
 *
 * @param index - The one index. Every node it carries is placed, including the
 *   ones no edge touches: a column nothing reads and that reads nothing is
 *   still a column the model holds.
 * @param size - The node body's size.
 * @returns Every node's id to its position, or nothing at all where the graph
 *   is larger than `MAX_LAYOUT_NODES`. Nothing, rather than a partial layout:
 *   half a graph laid out is a picture of a model that does not exist, and the
 *   page says the layout was skipped instead of drawing one.
 */
export function layoutAll(index: Index, size: { w: number; h: number }): Map<string, Placement> {
  if (index.order.length > MAX_LAYOUT_NODES) return new Map();
  return layoutOf(index.order, index.artifact.edges, size);
}
