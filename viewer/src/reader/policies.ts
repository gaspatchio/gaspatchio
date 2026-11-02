// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * Reading one policy's values off a document that may carry several.
 *
 * §7.4 puts a policy axis in the envelope and §8 aligns `value_sample`, `trace`
 * and `branches` to it: **the axis is the outermost container**, so a node's
 * enrichment is that one policy's value where the axis carries one entry, and
 * an array of those — exactly as long as `policies`, in its order — where it
 * carries several.
 *
 * The whole of that reading is here, in one function, for a reason worth
 * stating. The two shapes cannot be told apart by looking at the value: a
 * scalar column of two policies and a per-period column of one policy are both
 * an array of two numbers, and only the envelope says which is which. So the
 * axis's own length decides, once, in the reader — and no view indexes a
 * policy. A view that did would be a second place the page could be wrong
 * about whose numbers are on the screen, and the first one a reader would find
 * is the one that disagreed.
 */

import { foldLabel, isFold } from "./fold";
import type { Artifact, Policy } from "./types";

/**
 * What one entry of the axis is called, decided in one place.
 *
 * The id the file carries; the fold's own name where the entry is the book
 * rather than a policy; and **null where the file gives it neither** — an
 * export selecting by row position over a book with no identifier column has a
 * policy and no name for it, and inventing one here would be a name a reader
 * could not find anywhere else in the document.
 *
 * It is here rather than in the strip that draws it because two things need the
 * same string now: the switcher, and the entry a shared link names. A link that
 * spelled an entry one way while the strip spelled it another would point at a
 * policy nobody could see it pointing at.
 *
 * @param entry - One entry of `policies`.
 * @returns The fold's name, the id, or null where the file names it neither.
 */
export function policyName(entry: Policy): string | null {
  return foldLabel(entry) ?? entry.policy_id;
}

/** Count the declared kinds of entries without inferring them from names or filters. */
export function axisSummary(axis: Policy[]): string {
  if (axis.length === 0) return "no entries — this file carries no values";
  const folds = axis.filter(isFold).length;
  const policies = axis.length - folds;
  return [
    policies === 0 ? null : `${String(policies)} ${policies === 1 ? "policy" : "policies"}`,
    folds === 0 ? null : `${String(folds)} portfolio ${folds === 1 ? "fold" : "folds"}`,
  ].filter((part) => part !== null).join(" and ");
}

/**
 * The axis the values are read along, as the envelope declares it.
 *
 * Read off `policies` and off nothing else. `enrichment` is the same context
 * written twice — `policies[0]` with `why` left off — so a reader that mixed
 * the two would be choosing which of two statements of one fact to believe.
 *
 * @param artifact - The parsed file.
 * @returns The entries, in the producer's own order. Empty where the file
 *   carries no values, which is the case `enrichment: null` states beside it.
 */
export function axisOf(artifact: Artifact): Policy[] {
  return Array.isArray(artifact.policies) ? artifact.policies : [];
}

/**
 * One policy's share of a node's enrichment.
 *
 * @param field - The member as the file carries it: `value_sample`, `trace` or
 *   `branches`, in whichever of the two shapes the axis puts it in.
 * @param at - Which entry of the axis to read, 0-based.
 * @param carried - How many entries the axis carries.
 * @returns That policy's value, or undefined where the node states none for it.
 *
 * Three things are refused rather than read past, and each would put a number
 * under the wrong policy's name:
 *
 * - An axis of one carrying an array. **The value itself is what a
 *   single-policy document writes** (§8) — never an array of one — so the
 *   member is returned whole and a per-period column's timeline stays a
 *   timeline. That is also what makes this edition additive.
 * - An array whose length is not the axis's. §8: a consumer meeting one
 *   refuses the node's enrichment rather than reading past it, because every
 *   value after the first mismatch would sit under some other policy's name.
 * - A position past the end. The caller has asked for a policy the file does
 *   not carry values for, and a null is what the file says about it.
 */
export function atPolicy(field: unknown, at: number, carried: number): unknown {
  if (field === undefined || field === null) return undefined;
  if (carried <= 1) return field;
  if (!Array.isArray(field) || field.length !== carried) return undefined;
  const mine = field[at];
  return mine === null ? undefined : mine;
}
