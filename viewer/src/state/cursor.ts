// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The row cursor, published where a memoised box can subscribe to it.
 *
 * This is **not** a second piece of page state. `Selection.period` in
 * `state/selection.ts` is the cursor and remains the only thing that decides
 * where the reader is looking; this module republishes that one number, and
 * the cone publishes it in a layout effect whenever the selection's changes.
 * One writer, one value, and it is the reducer's.
 *
 * **Why it exists at all.** The cone's node array is built in a memo and handed
 * to React Flow. When the cursor's period was one of that memo's dependencies
 * every period step rebuilt all 101 node objects of the level-4 window, which
 * gave React Flow a new array with new `data` on every box, which made `memo`
 * on the body useless: every box re-rendered, laid out and had its style
 * recalculated, for a change to one line of text in each. Measured on
 * 2026-09-17 over that window, a scrub cost p50 33.3 / p95 50.1 ms with 234 of
 * 249 frames over 33 ms and ~35.6 ms of main-thread work a frame, against a
 * budget of 33 ms at the 95th percentile — the one interaction of the three
 * outside it, at every window size the page draws.
 *
 * So the period comes out of the node data and out of the memo's dependencies.
 * The boxes carry the timeline the file sampled, which is the same array object
 * for the life of the page, and each box reads the period from here through
 * `useSyncExternalStore`. Stepping the cursor now re-renders the value line in
 * each visible box and nothing else: the node array React Flow holds is the
 * same array, so it diffs nothing and lays out nothing.
 *
 * **A box subscribes to what it draws, not to the period** (2026-09-29). Most
 * of a cone's boxes read the same line from one period to the next — a scalar
 * input never changes, and a timeline often holds still for a stretch — so a
 * subscription to the period re-rendered every visible box to write out what
 * most of them already showed. Measured over the level-4 window `perf/measure.mjs`
 * scrubs: 14 of the 46 boxes drawn change their line on an average step, and 26
 * at most. `useAtCursor` hands React the line itself, which it compares with the
 * last one, and a box whose line would not change is not rendered at all — 0.2 ms
 * of script a frame of the scrub, and 0.3 on the comparison page. Since
 * 2026-10-30 the subscriber is the box's value line rather than the box
 * (`views/ConeNode.tsx`), so a box whose line does change redraws that line and
 * not its head, its chips, its formula and React Flow's handles.
 *
 * **One page, one cursor.** The store is a module value rather than something
 * handed down a context because the exported page mounts one `App` over one
 * artifact and there is no second cursor for a second one to be confused with.
 * A context would carry the same single value through every box's props for the
 * sake of a case this document cannot be in.
 */

import { useSyncExternalStore } from "react";

/** The period the boxes are drawing. Written only by `publishCursorPeriod`. */
let period = 0;

/** Who wants to hear about it. */
const listeners = new Set<() => void>();

/**
 * Say which period the boxes should draw.
 *
 * @param next - The selection's period. Publishing the period it already holds
 *   notifies nobody, so a render that changed something else costs nothing here.
 */
export function publishCursorPeriod(next: number): void {
  if (next === period) return;
  period = next;
  for (const listener of listeners) listener();
}

/** Subscribe, and unsubscribe. `useSyncExternalStore`'s first argument. */
function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/**
 * Something drawn at the row cursor, subscribed to.
 *
 * `read` is called with the cursor's period whenever the cursor moves, and the
 * component re-renders only when what it returns is not what it returned last
 * time — which is why it must return something React compares by value, as the
 * string on a box's value line is. It must be a function of the period and of
 * things that re-render the component when they change, and nothing else.
 *
 * @param read - What the component draws, at a period.
 * @returns What it draws at the cursor's period now.
 */
export function useAtCursor<T>(read: (period: number) => T): T {
  // The third argument is the server snapshot, which this page has no server
  // for; it is the same value, so a hydration that never happens agrees anyway.
  return useSyncExternalStore(
    subscribe,
    () => read(period),
    () => read(period),
  );
}
