// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The bounded piece of the graph the cone draws.
 *
 * Two questions, asked of one node: what fed this, and what does this feed.
 * Each is answered by a breadth-first walk over the file's own `edges`,
 * stopped at a depth the reader sets — never by the whole graph, which is
 * unreadable at the zoom it takes to fit a real model on a screen and answers
 * neither question. Widening is one step at a time and the step is the
 * reader's, so what is on the screen is always something they asked for.
 *
 * Nothing here is drawing. The window is a set of ids and the edges between
 * them, and it is a function of the index and three numbers, which is what
 * lets the counts in `test/window.test.ts` be walked from the file rather than
 * read off a canvas.
 */

import type { Index } from "./index";
import type { Edge } from "./types";

/** One reader's view of the graph: a centre, a reach each way, and what that reaches. */
export interface Window {
  /** The selected node, which is always in `nodes`. */
  center: string;
  /** Every node reached, the centre among them. */
  nodes: string[];
  /** Exactly the file's edges whose two ends are both in `nodes`. */
  edges: Edge[];
  /** How many steps were walked over the edges into a node. */
  up: number;
  /** How many steps were walked over the edges out of it. */
  down: number;
}

/**
 * Walk `steps` steps from `start`, following one map of the edges.
 *
 * Breadth-first, so a node reached by two routes is kept at the shorter one
 * and the bound means depth rather than path length. The walk visits each node
 * once; a graph with a cycle in it terminates on the `seen` set rather than on
 * the bound.
 *
 * @param start - The node walked from.
 * @param edges - `readsOf` to walk upwards, `readBy` to walk downwards.
 * @param steps - How far. Zero reaches only `start`.
 * @param seen - Collected into; `start` is added here.
 */
function walk(
  start: string,
  edges: Map<string, string[]>,
  steps: number,
  seen: Set<string>,
): void {
  seen.add(start);
  let frontier = [start];
  for (let step = 0; step < steps && frontier.length > 0; step += 1) {
    const next: string[] = [];
    for (const id of frontier) {
      for (const neighbour of edges.get(id) ?? []) {
        if (seen.has(neighbour)) continue;
        seen.add(neighbour);
        next.push(neighbour);
      }
    }
    frontier = next;
  }
}

/**
 * The window around one node.
 *
 * @param index - The one index.
 * @param center - The selected node's id, as the file spells it.
 * @param up - How many steps of ancestors to reach: what `center` reads, what
 *   those read, and so on.
 * @param down - How many steps of descendants: what reads `center`, and so on.
 * @returns The window. Its `nodes` are in the file's order, which is
 *   topological, so a node's inputs come before it here as they do in the grid.
 */
/**
 * The window a set of nodes makes, with the file's own edges between them.
 *
 * What the cone draws once a reader has started opening it up. `coneWindow`
 * answers "everything within N steps of here", which is the right question for
 * a column just chosen and the wrong one for a graph somebody is exploring: it
 * moves every box on the screen each time the centre changes. This answers
 * "these nodes, and the edges the file carries between them", so a set that
 * grew by two nodes is a drawing that gained two boxes.
 *
 * The order is `index.order`, which is the file's, so a node added anywhere is
 * inserted where the model wrote it rather than appended.
 *
 * @param index - The one index.
 * @param center - The focused node, which is put in the set if it is missing.
 * @param ids - The nodes to draw.
 * @returns The window, with `up` and `down` zero: the set is no longer a
 *   distance from anywhere, and reporting one would be inventing it.
 */
export function windowOf(index: Index, center: string, ids: ReadonlySet<string>): Window {
  const reached = new Set(ids);
  reached.add(center);
  const nodes = index.order.filter((id) => reached.has(id));
  if (!reached.has(center)) nodes.unshift(center);
  const edges = index.artifact.edges.filter(
    (edge) => reached.has(edge.source) && reached.has(edge.target),
  );
  return { center, nodes, edges, up: 0, down: 0 };
}

export function coneWindow(index: Index, center: string, up: number, down: number): Window {
  const reached = new Set<string>();
  walk(center, index.readsOf, up, reached);
  walk(center, index.readBy, down, reached);

  const nodes = index.order.filter((id) => reached.has(id));
  // A centre the file does not carry still gets a window of its own, because a
  // page that answered "no such node" by drawing the graph around some other
  // node would be answering a question nobody asked.
  if (!reached.has(center)) nodes.unshift(center);

  const edges = index.artifact.edges.filter(
    (edge) => reached.has(edge.source) && reached.has(edge.target),
  );

  return { center, nodes, edges, up, down };
}
