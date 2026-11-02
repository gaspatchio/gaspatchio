// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * Reading an entry of the axis that is the book rather than a policy.
 *
 * §7.4's axis carries the book's own fold as one of its entries: `policy_id`
 * null, because no policy is what it is an account of, and `aggregation`
 * naming the fold — `sum`, `period_sum`, `mean`. Everything else about such an
 * entry reads exactly as a policy's does, which is the point of putting it on
 * the same axis, so the only thing this file adds is the one predicate that
 * tells the two apart and the sentences the page says because of it.
 *
 * **The sentence matters more than the predicate.** A column no accumulator
 * covered carries null at the fold's position, and `atPolicy` turns that into
 * `undefined` — the same `undefined` a value the file simply does not carry
 * produces, which the page writes as `·`. Those are not the same statement. A
 * reader who meets `·` in a row of numbers reads it as nothing, and nothing in
 * a column of money reads as zero. So where the file says a column was not
 * folded, the page says that in words.
 *
 * It is **not an admission**, and it is not drawn like one. An amber mark on
 * this page means a hole or a disagreement — something the file owns up to.
 * There is no portfolio value of a monthly mortality rate, and a file that
 * declines to invent one is not confessing to anything; it is being asked a
 * question that has no answer. The dead branch of a conditional is grey for
 * the same reason and this follows it.
 */

import type { Index } from "./index";
import type { Policy } from "./types";

/**
 * What the page says where a fold covers no such column.
 *
 * Read against `·`, which is what a value the file does not carry looks like.
 * The difference is the whole of it: `·` says the file is silent, and this
 * says the file was asked and there is no such number.
 */
export const DID_NOT_FOLD = "the model did not fold this column";

/** The same thing in the width of a grid cell, with the sentence on its title. */
export const NOT_FOLDED = "not folded";

/**
 * A fold entry whose every covered column holds one value per policy, said
 * where the timeline would be.
 *
 * The grid draws per-period columns, and a fold across the book of a column
 * holding one value per policy produces one number rather than a run of them.
 * So the grid has no rows — and an empty grid under a selected entry reads as
 * a projection of nothing, which is exactly the misreading this page exists to
 * prevent.
 *
 * @param aggregation - The fold's own name, as the entry states it.
 * @returns The sentence, naming the fold and the one move available.
 */
export function noTimelineInThisFold(aggregation: string): string {
  return (
    `This entry is the book folded by ${aggregation}, and no column it covers holds one value ` +
    "per period, so there is no timeline for the grid to draw. Choose a policy on the identity " +
    "strip for a timeline, or select a folded column to read its total in the proof."
  );
}

/**
 * Whether an entry of the axis is a fold of the book rather than one policy.
 *
 * Decided on `aggregation` and on nothing else. A null `policy_id` is not the
 * test: a book that names no policy column is walked by row position and its
 * entries carry no id either, and those are policies (§7.4).
 *
 * @param entry - The selected entry, or null where the file carries no values.
 * @returns True where the entry states a fold.
 */
export function isFold(entry: Policy | null | undefined): boolean {
  return entry !== null && entry !== undefined && entry.aggregation !== null;
}

/**
 * Whether the selected entry is a fold that did not cover this node's column.
 *
 * The one predicate the grid, the proof, the cone and the rails all ask, so
 * that the four say the same thing about one column rather than four things
 * that usually agree.
 *
 * @param index - The document, read at the selected entry.
 * @param id - The node.
 * @returns True where the page should say the sentence instead of a value.
 */
export function unfolded(index: Index, id: string): boolean {
  return isFold(index.policy) && index.sampleOf(id) === undefined;
}

/**
 * The line saying a number is the book folded rather than one policy's arithmetic.
 *
 * The entry's own `why`, which already records the fold and how many policies
 * went into it, so that the panel and the switcher say one thing rather than
 * two that usually agree. The qualifier after it is the part a reader of a
 * worked example needs: the formula above is the definition of a column, and
 * the number below is not that formula evaluated once.
 *
 * @param entry - The selected entry, which is a fold.
 * @returns The sentence.
 */
export function foldNote(entry: Policy): string {
  return `${entry.why} — a fold, not one policy's arithmetic`;
}

/**
 * How a fold entry is named where a policy would be named by its id.
 *
 * The name of the fold, because that is what distinguishes one fold entry from
 * another on an axis that may carry several: the whole book summed, the same
 * book summed per scenario. The cut itself is in the entry's `why`, which is
 * what the switcher shows beside this.
 *
 * @param entry - The entry to name.
 * @returns The fold's name, or null where the entry is a policy.
 */
export function foldLabel(entry: Policy): string | null {
  return entry.aggregation === null ? null : `fold · ${entry.aggregation}`;
}
