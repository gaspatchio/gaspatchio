// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The tier census: how many of a document's calculations sit at each tier.
 *
 * Every node that computes states a `tier` (§11.2): `core` where the format's
 * own vocabulary accounts for all of it, `engine_native` where it reaches a
 * fragment of one engine's own expression language, `opaque` where it reaches
 * an operation nothing has classified. The page draws each node's tier on its
 * box; this adds them up, because a file with no holes reads as more than it
 * says. "Every column is accounted for" is a statement about where each column
 * came from, and a line written in an engine's own language is accounted for
 * and is still a line only that engine can run.
 *
 * It is the census `af.graph.tiers()` and `gspio calc-graph` state, read off
 * the document the page shows, and it counts what they count: every node that
 * has something to execute, each at its tier, in the order the file writes
 * them. That is every kind §8 does not call a leaf -- `computed` and
 * `rollforward`, which an export of this package writes, and `state_graph`
 * and `nested_valuation`, the two payload sections the specification reserves,
 * which a document may carry. A leaf -- a column the data arrived with, a hole,
 * a running state -- computes nothing and carries no tier, so it is not
 * counted. Every tier is stated, a zero included, because `0 opaque` is a claim
 * about the model.
 *
 * Two files state no census, and they say different things. A file in which
 * no node carries the member at all has been edited by hand: the format has
 * required it on every node since its first preview, and this page reads no
 * other edition. It has no census to give, and a count of nothing there would
 * be a false zero. A file in which a calculation carries no tier the format
 * defines cannot be counted either: counting that line nowhere would
 * understate the model, and counting it anywhere would be a guess. The page
 * names the line instead, and what it carries.
 */

import type { Artifact } from "./types";

/** The three tiers, strongest claim first: the order a census states them in. */
export const TIERS = ["core", "engine_native", "opaque"] as const;

/** One of the three. */
export type Tier = (typeof TIERS)[number];

/** The calculations at each tier, by node id, in the order the file writes them. */
export type TierCensus = Record<Tier, string[]>;

/**
 * What a document says about its tiers: a census, or the line that stops one,
 * with what that line carries where a tier should be -- null, nothing at all,
 * or a value the format does not define.
 */
export type TiersRead = { census: TierCensus } | { untiered: string; tier: unknown };

/** The kinds of node that compute, and so state a tier: every kind but a leaf's. */
const COMPUTES = new Set(["computed", "rollforward", "state_graph", "nested_valuation"]);

/**
 * How many calculations the page names at a tier before saying how many more.
 *
 * The command line's number, so the strip and the line `gspio calc-graph`
 * prints name the same ones. The drawer's Model tab names every one.
 */
export const NAMED_AT_A_TIER = 5;

/**
 * Read a document's tier census.
 *
 * @param artifact - The document the page shows.
 * @returns The census; the first calculation that carries no tier the format
 *   defines, and what it carries instead, where one does; or null where no
 *   node carries a tier at all.
 */
export function tiersOf(artifact: Artifact): TiersRead | null {
  if (!artifact.nodes.some((node) => "tier" in node)) return null;
  const census: TierCensus = { core: [], engine_native: [], opaque: [] };
  for (const node of artifact.nodes) {
    if (!COMPUTES.has(node.kind)) continue;
    const at = (TIERS as readonly unknown[]).includes(node.tier) ? (node.tier as Tier) : null;
    if (at === null) return { untiered: node.id, tier: node.tier };
    census[at].push(node.id);
  }
  return { census };
}
