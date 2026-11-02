// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The window a read states, written the way a reviewer writes it.
 *
 * An offset says which period a shifted value came from; `periods` says which
 * run an aggregation read and `position` which stored period a literal
 * `list.get` took (§9). Both are read off the facet and never off the
 * formula's text, exactly as the offset is, and both are drawn the same way:
 * a label on the reading node's loop in the cone, and an outline on every cell
 * of the window in the grid.
 *
 * A window is a bound, not a promise that every period inside it moved the
 * answer — a reversal states the whole run because no single period would be
 * true of every row. The grid outlines the bound the file states and nothing
 * narrower.
 */

import type { Narrowing, PeriodBound } from "./types";

/** Whether a narrowing states a window at all. */
export function statesWindow(narrowing: Narrowing): boolean {
  return narrowing.periods !== undefined || narrowing.position !== undefined;
}

/**
 * One end of a window, as a row label.
 *
 * The minus is U+2212, as the cone's offset label writes it.
 *
 * @param bound - The facet's bound.
 * @returns `first`, `last`, `t`, `t−1`, `t+2`, and so on.
 */
function boundLabel(bound: PeriodBound): string {
  if (bound === "first" || bound === "last") return bound;
  if (bound === 0) return "t";
  return bound < 0 ? `t−${String(Math.abs(bound))}` : `t+${String(bound)}`;
}

/**
 * The window one narrowing states, as a short label, or null where it states none.
 *
 * @param narrowing - One transformation from the facet.
 * @returns `first…t`, `t…last`, `first…last`, `[0]`, `[−1]`, or null.
 */
export function windowLabel(narrowing: Narrowing): string | null {
  if (narrowing.position !== undefined) {
    const at = narrowing.position;
    return at < 0 ? `[−${String(Math.abs(at))}]` : `[${String(at)}]`;
  }
  if (narrowing.periods === undefined) return null;
  return `${boundLabel(narrowing.periods.from)}…${boundLabel(narrowing.periods.to)}`;
}

/**
 * The rows a window covers when the answer is read at `period`, clipped to the run.
 *
 * @param narrowing - One transformation that states a window.
 * @param period - The period of the answer being shown.
 * @param length - How many periods the run has.
 * @returns The covered rows, in order; empty where the window holds none here,
 *   which a read of `{first, −1}` does at the first period.
 */
export function windowRows(narrowing: Narrowing, period: number, length: number): number[] {
  if (narrowing.position !== undefined) {
    const at = narrowing.position < 0 ? length + narrowing.position : narrowing.position;
    return at >= 0 && at < length ? [at] : [];
  }
  if (narrowing.periods === undefined) return [];
  const row = (bound: PeriodBound): number =>
    bound === "first" ? 0 : bound === "last" ? length - 1 : period + bound;
  const low = Math.max(row(narrowing.periods.from), 0);
  const high = Math.min(row(narrowing.periods.to), length - 1);
  const rows: number[] = [];
  for (let at = low; at <= high; at += 1) rows.push(at);
  return rows;
}
