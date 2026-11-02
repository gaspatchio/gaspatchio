// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * What moves if this changes.
 *
 * The question a reviewer actually asks, and the one the cone answers only a
 * step at a time: change the lapse basis, and what moves? Walking down two
 * boxes at a time answers it eventually and never tells you that you have
 * finished. This answers it once — everything reachable over the edges out of a
 * column — and then says the part an actuary cares about: which of the model's
 * own answers are among them.
 *
 * **Structural, and it says so.** This is reach and not influence. A column
 * that feeds `pv_net_cf` is in its chain; whether it moves the number by a
 * basis point or by a third is not something this file can tell you, because
 * the artifact carries the graph and the values and not the derivatives. Saying
 * "42 columns depend on this" is a fact about the edges. Saying "this drives
 * the result" would be a claim about magnitudes nobody measured, and *sharp
 * knives, no magic* is the rule against making it.
 *
 * The walk is over `readBy`, the same map the cone widens downwards with, so
 * what this reports and what the cone draws can never disagree.
 */

import type { Index } from "./index";
import { endsOf } from "./results";

/**
 * Every column that reads this one, directly or through any chain of others.
 *
 * Breadth-first over `readBy`, on a `seen` set rather than a depth bound, so a
 * graph with a cycle in it terminates. The column itself is not included: it is
 * what changed, not what moved.
 *
 * @param index - The one index.
 * @param id - The column that would change.
 * @returns The ids downstream of it, in the file's order.
 */
export function descendantsOf(index: Index, id: string): string[] {
  const seen = new Set<string>();
  let front = [id];
  while (front.length > 0) {
    const next: string[] = [];
    for (const one of front) {
      for (const reader of index.readBy.get(one) ?? []) {
        if (seen.has(reader) || reader === id) continue;
        seen.add(reader);
        next.push(reader);
      }
    }
    front = next;
  }
  return index.order.filter((one) => seen.has(one));
}

/**
 * The model's own ends that this column reaches.
 *
 * `endsOf` is where the model stopped; these are the ones a change here would
 * travel to. The answer an actuary wants from "what depends on this" is rarely
 * the whole list of forty columns — it is whether the result is among them, and
 * which results.
 *
 * @param index - The one index.
 * @param id - The column that would change.
 * @returns The ends downstream of it, in the file's order, empty where a change
 *   here reaches none of them.
 */
export function endsReached(index: Index, id: string): string[] {
  const downstream = new Set(descendantsOf(index, id));
  return endsOf(index).filter((end) => downstream.has(end));
}
