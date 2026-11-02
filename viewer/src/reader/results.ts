// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * Where the model ends, and therefore where a reader starts.
 *
 * The page used to open on nothing: three empty panes and a box saying "search
 * for a column". An actuary opening a model somebody else wrote has no idea
 * what to type into it — they know what they want (the answer, and then what
 * drove it) and not what the model called it. So the page opens on the model's
 * last result and the search box offers the rest.
 *
 * **What this is allowed to know.** A column in the final schema that carries a
 * formula and that nothing else in the graph reads is the end of a chain: the
 * model computed it and then stopped. That is a fact about the edges, and this
 * file states nothing beyond it. It is deliberately **not** a claim that these
 * are "the results" — `projection_date` qualifies on every one of these models
 * and is a label, not an answer, and the file carries nothing that tells the
 * two apart. Inferring which of them matters is meaning, and *sharp knives, no
 * magic* is the rule against inferring it; so the page heads the list with what
 * was measured — nothing else reads these — and lets the reader read it.
 *
 * **Why the last one.** Models are written building up to their answer, so file
 * order ends on it. Measured over the corpus this repository ships: `pv_net_cf`
 * for levels 3, 4 and 5, `av_growth` for the rollforward patterns (its only
 * one), `is_profitable` for level 1, `total_claims` for the holes fixture. That
 * is a camera position and not a claim — the reader moves it with one click,
 * and where a file has no such column the page opens as it always did.
 */

import type { Index } from "./index";

/**
 * Every column the model computed and then stopped at, in the file's order.
 *
 * @param index - The one index.
 * @returns The ids, in file order; empty where the file has none.
 */
export function endsOf(index: Index): string[] {
  return index.finalColumns.filter((id) => {
    const node = index.nodes.get(id);
    if (node === undefined || typeof node.formula !== "string" || node.formula === "") return false;
    return (index.readBy.get(id) ?? []).length === 0;
  });
}

/**
 * The column the page opens on, or null where it opens on nothing.
 *
 * @param index - The one index.
 * @returns The last of `endsOf`, which is where the model's own order ends.
 */
export function openingColumn(index: Index): string | null {
  const ends = endsOf(index);
  return ends.length === 0 ? null : (ends[ends.length - 1] ?? null);
}
