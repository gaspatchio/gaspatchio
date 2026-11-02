// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * Which of these terms is most of the answer.
 *
 * "Materiality" in general is not something this artifact can answer. It
 * carries the graph and the value samples and not the derivatives, so how much
 * `lapse_rate` moves `pv_net_cf` is a question about a model that was not run,
 * and a page that put a number on it would be inventing one.
 *
 * There is exactly one case where the question has an arithmetic answer rather
 * than an inferred one, and this is it: **where a column is a signed sum of
 * other columns, each term's value is its contribution.** No attribution, no
 * derivative, no assumption — `pv_net_cf` is its six present values added up,
 * so saying that claims are three fifths of the gross movement is reading the
 * addition the model wrote. That is the case an actuary asks about most, since
 * it is the shape every headline result on these models has.
 *
 * **It fails closed, and the test is exact rather than clever.** Take the
 * formula, take out every column reference it makes, and look at what is left.
 * If that is nothing but `+`, `-` and whitespace, the expression was a signed
 * sum of those columns and nothing else — no product, no power, no conditional,
 * no literal. Anything else and this returns null and the panel says nothing.
 * `1 - (1 - af.mort_rate) ** (1 / 12)` leaves digits and brackets behind and is
 * refused; `af.av_pp * af.pols_maturity` leaves a `*` and is refused. A column
 * named twice is refused too, because its share would then be split across two
 * terms that this cannot tell apart.
 *
 * The share is of the **gross**: the sum of the absolute values. Two terms that
 * nearly cancel are both large, and dividing by the net would report each of
 * them as many times the answer — which is true arithmetic and useless
 * reporting. The label says gross for that reason.
 */

import { approximately } from "./exact";
import type { Index } from "./index";
import type { Artifact } from "./types";

/** One term of a sum, and how much of the gross movement it is. */
export interface Share {
  /** The operand's node id. */
  id: string;
  /** Its value at the period asked for. */
  value: number;
  /** Its share of the sum of the absolute values, between 0 and 1. */
  share: number;
}

/** Every `af.name` the formula mentions, in the order it mentions them. */
function referenced(formula: string): string[] {
  return [...formula.matchAll(/\baf\.([A-Za-z_][A-Za-z0-9_]*)/g)].map((m) => m[1] ?? "");
}

/**
 * One column's value at a period, where the file carries one.
 *
 * `approximately`, so a term whose value is an integer too wide for a double
 * still counts towards the gross rather than silently withdrawing the whole
 * panel. A share is a quotient and is rounded to a whole per cent before it
 * is printed, so nothing exact is claimed about it and nothing exact is lost:
 * the terms themselves are written from the file by `formatValue`.
 */
function valueAt(index: Index, id: string, period: number): number | null {
  const sample = index.sampleOf(id);
  const value = Array.isArray(sample) ? sample[period] : sample;
  const number = approximately(value);
  return number !== null && Number.isFinite(number) ? number : null;
}

/**
 * The terms of a column that is a signed sum of other columns, and their shares.
 *
 * @param index - The one index.
 * @param nodeId - The column being explained.
 * @param period - The row cursor.
 * @returns The terms, largest share first, or null where the formula is not a
 *   signed sum of columns or where any term's value is missing at that period.
 */
/**
 * Whether a column is a signed sum, and of which operands — cached per file.
 *
 * The shape is a property of the formula and the formula does not change under
 * the row cursor, so this is decided once per column and read from there. It is
 * not a micro-optimisation: the panel is rebuilt on every period a reader
 * scrubs through, and running the shape test there put the 95th-percentile
 * frame at 33.3 ms against a 33 ms budget. The values still come from the
 * period, which is the only part that depends on it.
 *
 * Keyed on the **artifact** and not on the index, and for the same reason the
 * cost above is worth avoiding: a formula does not change when the reader
 * moves along the policy axis either, so a cache keyed on the index would be
 * thrown away and rebuilt by a switch that cannot have changed a single answer
 * in it.
 */
const shapes = new WeakMap<Artifact, Map<string, string[] | null>>();

/** The operand ids of a signed sum, or null where the formula is not one. */
function termsOf(index: Index, nodeId: string): string[] | null {
  let known = shapes.get(index.artifact);
  if (known === undefined) {
    known = new Map<string, string[] | null>();
    shapes.set(index.artifact, known);
  }
  const already = known.get(nodeId);
  if (already !== undefined) return already;

  const decided = decide(index, nodeId);
  known.set(nodeId, decided);
  return decided;
}

/** The shape test itself, run once per column. */
function decide(index: Index, nodeId: string): string[] | null {
  const node = index.nodes.get(nodeId);
  const formula = typeof node?.formula === "string" ? node.formula : "";
  if (formula === "") return null;

  const names = referenced(formula);
  if (names.length < 2) return null;
  if (new Set(names).size !== names.length) return null;

  // The exact test: with the column references taken out, a signed sum has
  // nothing left but its signs.
  const rest = formula.replace(/\baf\.[A-Za-z_][A-Za-z0-9_]*/g, "");
  if (!/^[\s+-]*$/.test(rest)) return null;

  // The operands the file says this node reads, matched to the names by column.
  const byColumn = new Map<string, string>();
  for (const id of index.readsOf.get(nodeId) ?? []) {
    const column = index.nodes.get(id)?.column;
    if (typeof column === "string") byColumn.set(column, id);
  }

  const ids: string[] = [];
  for (const name of names) {
    const id = byColumn.get(name);
    if (id === undefined) return null;
    ids.push(id);
  }
  return ids;
}

export function sharesOf(index: Index, nodeId: string, period: number): Share[] | null {
  const ids = termsOf(index, nodeId);
  if (ids === null) return null;

  const terms: Share[] = [];
  let gross = 0;
  for (const id of ids) {
    const value = valueAt(index, id, period);
    if (value === null) return null;
    gross += Math.abs(value);
    terms.push({ id, value, share: 0 });
  }
  if (gross === 0) return null;

  for (const term of terms) term.share = Math.abs(term.value) / gross;
  return terms.sort((a, b) => b.share - a.share);
}
