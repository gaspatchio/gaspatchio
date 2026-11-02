// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The bounded window the cone draws.
 *
 * Every count below is walked from the fixture in this file rather than typed
 * in from a screen, for the reason the grid's cases give: a number somebody
 * read once stops being evidence the moment the fixture is regenerated. What
 * is held to here is the shape of the walk — that it stops where it is told to
 * stop, that it reaches the centre from either direction, and that it never
 * draws an edge to a node it did not bring with it.
 */

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { buildIndex } from "../src/reader/index";
import type { Artifact } from "../src/reader/types";
import { coneWindow } from "../src/reader/window";

const artifact = JSON.parse(
  readFileSync(new URL("../fixtures/level4.json", import.meta.url), "utf8"),
) as Artifact;
const index = buildIndex(artifact);

/**
 * The same walk, done here by hand over the file's own `edges`.
 *
 * The test computes its expectation the long way round so that the assertion
 * is about the file rather than about `coneWindow` agreeing with itself.
 *
 * @param start - The node walked from.
 * @param direction - `up` over the edges into a node, `down` over the edges out of it.
 * @param depth - How many steps to take.
 * @returns Every node reached, the start among them.
 */
function reached(start: string, direction: "up" | "down", depth: number): Set<string> {
  const seen = new Set([start]);
  let frontier = [start];
  for (let step = 0; step < depth && frontier.length > 0; step += 1) {
    const next: string[] = [];
    for (const id of frontier) {
      for (const edge of artifact.edges) {
        const from = direction === "up" ? edge.target : edge.source;
        const to = direction === "up" ? edge.source : edge.target;
        if (from !== id || seen.has(to)) continue;
        seen.add(to);
        next.push(to);
      }
    }
    frontier = next;
  }
  return seen;
}

describe("coneWindow", () => {
  it("reaches what the selected node reads, and what reads it", () => {
    const window = coneWindow(index, "net_cf@1", 2, 2);
    const nodes = new Set(window.nodes);

    // The six columns `net_cf` is written from, one step up.
    for (const read of index.readsOf.get("net_cf@1") ?? []) expect(nodes.has(read)).toBe(true);
    // And what those six are written from, two steps up.
    for (const read of index.readsOf.get("premiums@1") ?? []) expect(nodes.has(read)).toBe(true);

    // `net_cf` is the last column this model writes, so its cone downwards is
    // itself. A column with readers shows them: `premiums` feeds three.
    const below = new Set(coneWindow(index, "premiums@1", 0, 1).nodes);
    for (const reader of index.readBy.get("premiums@1") ?? []) expect(below.has(reader)).toBe(true);
    expect(below.size).toBe((index.readBy.get("premiums@1") ?? []).length + 1);
  });

  it("draws the node alone when it is told to reach nowhere", () => {
    expect(coneWindow(index, "net_cf@1", 0, 0).nodes).toEqual(["net_cf@1"]);
  });

  it("reaches the whole ancestor cone when the bound is past its depth", () => {
    const window = coneWindow(index, "net_cf@1", 99, 0);
    expect(window.nodes.length).toBe(reached("net_cf@1", "up", 99).size);
    // The walk over this fixture: 100 columns feed `net_cf`, 101 with itself.
    expect(window.nodes.length).toBe(101);
  });

  it("stops one step short when the bound is one step shorter", () => {
    for (const depth of [1, 2, 3]) {
      expect(new Set(coneWindow(index, "net_cf@1", depth, 0).nodes)).toEqual(
        reached("net_cf@1", "up", depth),
      );
    }
  });

  it("carries only the edges joining two of its own nodes", () => {
    const window = coneWindow(index, "net_cf@1", 2, 2);
    const nodes = new Set(window.nodes);
    for (const edge of window.edges) {
      expect(nodes.has(edge.source)).toBe(true);
      expect(nodes.has(edge.target)).toBe(true);
    }
    // And every such edge the file carries, not merely some of them.
    const joining = artifact.edges.filter((e) => nodes.has(e.source) && nodes.has(e.target));
    expect(window.edges.length).toBe(joining.length);
  });

  it("says what it was asked for, so a control can read it back", () => {
    const window = coneWindow(index, "net_cf@1", 2, 3);
    expect(window.center).toBe("net_cf@1");
    expect(window.up).toBe(2);
    expect(window.down).toBe(3);
  });
});
