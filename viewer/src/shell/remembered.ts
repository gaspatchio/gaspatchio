// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The one thing this page writes anywhere, and the reading of it.
 *
 * Where the three dividers sit and which panes the reader has railed, under one
 * key in one browser. It lives in a file of its own because two parts of the
 * page need it and they need different halves: `Panes.tsx` owns the dividers
 * and is the only writer, and `App.tsx` reads the railed set once to start the
 * pane reducer from where the reader left it.
 *
 * **Expansion is not here, and its absence is the design.** A rail is a
 * setting and an expansion is a gesture; a file you send someone opens the way
 * your page opens, not the way you happened to leave it. There is no field for
 * it to be stored in and no line that could store it.
 *
 * Every read and every write is wrapped. A browser with storage turned off, a
 * private window, a quota already full — none of those is a reason a page
 * cannot be opened, so a refusal to remember is caught and the defaults stand.
 * And what comes back is checked before it is used: a stored value is the only
 * thing on this page written by something other than this page's own run of it.
 */

import { PANES } from "../state/layout";
import type { PaneName } from "../state/layout";

/** The one key this page writes. Nothing else is stored, here or anywhere. */
const KEY = "gaspatchio-viewer.panes";

/** What is remembered: where the dividers sit, and which panes are away. */
export interface Remembered {
  /** The grid's share of the height. */
  top: number;
  /** The cone's share of the width below it. */
  cone: number;
  /** The inspector drawer's width, in pixels. */
  drawer: number;
  /**
   * The panes standing as rails.
   *
   * Added to the shape rather than replacing anything in it, so a value stored
   * by a page built before this field existed still loads and simply has no
   * rails — which is the state it was stored in.
   */
  railed: PaneName[];
}

export const DEFAULTS: Remembered = { top: 0.62, cone: 0.5, drawer: 320, railed: [] };

/**
 * How narrow and how wide the reader may drag the drawer.
 *
 * Declared here rather than at the divider because two places clamp it — the
 * drag, and the read of a stored value — and a stored width outside the drag's
 * bounds would be a drawer the reader could not put back where they found it.
 *
 * The wide end is 960 rather than the 640 this page shipped with, and the
 * number is the model file's. Code in this repository is formatted to 100
 * columns; at the mono face's 13px that is about 780 pixels, and the drawer
 * also spends a line-number gutter, its padding, and the margin that carries
 * the columns a line accounts for. Under 640 a reader sent to `model.py:520`
 * met a line cut off mid-identifier with the margin sitting over the rest of
 * it, and had to scroll sideways to read one line of the model they had been
 * told computed their number. The default is unchanged at 320: a drawer that
 * opened wide would be a page that opens differently, and the four scripted
 * reads assert against the one that opens today.
 */
export const DRAWER_MIN = 180;
export const DRAWER_MAX = 960;

/** Keep a remembered size inside the bounds the layout can actually draw. */
export function within(value: unknown, low: number, high: number, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value)
    ? Math.min(high, Math.max(low, value))
    : fallback;
}

/**
 * The pane names in a stored value, and nothing that is not one.
 *
 * A name this page does not have is dropped rather than carried: the stored
 * value is the only thing on this page written by something other than this
 * page's own run of it, and a rail drawn from a string nobody recognises would
 * be a rail with no pane behind it.
 */
function panesIn(value: unknown): PaneName[] {
  if (!Array.isArray(value)) return [];
  return PANES.filter((name) => value.includes(name));
}

/** The remembered shape, or the defaults where nothing usable comes back. */
export function remembered(): Remembered {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (raw === null) return DEFAULTS;
    const stored = JSON.parse(raw) as Partial<Remembered>;
    return {
      top: within(stored.top, 0.2, 0.9, DEFAULTS.top),
      cone: within(stored.cone, 0.15, 0.85, DEFAULTS.cone),
      drawer: within(stored.drawer, DRAWER_MIN, DRAWER_MAX, DEFAULTS.drawer),
      railed: panesIn(stored.railed),
    };
  } catch {
    return DEFAULTS;
  }
}

/** Remember the shape, or carry on without remembering it. */
export function remember(shape: Remembered): void {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(shape));
  } catch {
    // A page that cannot remember where the dividers were is still the page.
  }
}
