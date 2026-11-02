// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * Which panes are open, which are rails, and which one has the page.
 *
 * The page's window management, as data. The four pane names, the four layouts, and
 * the two questions every region asks before it draws itself, in a module with
 * no React in it — so what the page does when you press `t` can be read, and
 * tested, without a browser. The same reason `state/selection.ts` sits here.
 *
 * **Two states, and they are not the same kind of thing.** Which panes are
 * *railed* is a setting: the reader put a pane away and expects to find it away
 * tomorrow, so it is remembered. Which pane is *expanded* is a gesture: a hand
 * reaching for one thing for a moment, restored by Escape and by the same
 * corner, and it is never remembered — so a file you send someone opens
 * the way your page opens rather than the way you happened to leave it.
 *
 * **A rail is not a hidden pane**, which is why the two are kept apart
 * here rather than collapsed into one "visible" flag. A railed pane is still on
 * the screen, still saying its name and its one live figure; what changed is
 * how much room it has. Nothing in this module can put a pane in a state where
 * it is neither drawn nor railed, and `Panes.tsx` has no other way to ask.
 */

/** The four regions, as the page names them. */
export type PaneName = "grid" | "cone" | "inspector";

/** All four, in the order the keyboard's 1–4 take them. */
export const PANES: PaneName[] = ["grid", "cone", "inspector"];

/**
 * What each pane is called on the page, wherever the page names one.
 *
 * The ids above are the code's: they key the remembered layout, the regions'
 * `data-pane` attributes and every test id, and they stay what they are. What a
 * reader sees is these words instead — the ones the Audit View documentation
 * teaches: the worksheet, the derivation, the proof and the record. The cone's
 * pane carries the proof as a strip under the derivation, so its one name says
 * both, as its rail's figure does. A pane put away to a rail says one of these;
 * a rail reading "cone" or "inspector" would be a word no page of the
 * documentation ever taught the person holding the file.
 */
export const PANE_LABELS: Record<PaneName, string> = {
  grid: "worksheet",
  cone: "derivation and proof",
  inspector: "record",
};

/** Which tab of the drawer is open. */
export type InspectorTab = "node" | "table" | "model" | "source" | "changes";

/**
 * The four, in the order the drawer shows them.
 *
 * `source` is fourth because it is the one a reader arrives at from somewhere
 * else — the proof's footer — rather than one they go looking through the tabs
 * for, and putting it first would have moved the three that were there.
 */
export const TABS: InspectorTab[] = ["node", "table", "model", "source"];

/**
 * The five a comparison page shows, `changes` first.
 *
 * First because it is the question the page was opened to ask — a reader who
 * has just been handed two quarters wants the list before they want a record —
 * and it is the one tab whose entries take the reader to the other four.
 *
 * A page carrying one document draws **four**, not five with one inert. That is
 * the policy switcher's rule, applied where it applies again: a
 * control that looks operable and is not is worse than no control, and "there
 * is nothing to compare this with" is not a thing a tab can say usefully. It is
 * also what keeps the four scripted reads asserting against exactly the drawer
 * they assert against today.
 */
export const COMPARISON_TABS: InspectorTab[] = ["changes", ...TABS];

/** The four saved sets of pane states. */
export type LayoutName = "read" | "table" | "lineage" | "source";

/** One layout: what it rails, what it expands, and where it leaves the drawer. */
export interface Layout {
  /** The letter that reaches it from the keyboard. */
  key: string;
  /** What a reader would call it, for the control in the strip. */
  says: string;
  railed: PaneName[];
  expanded: PaneName | null;
  /** The tab the drawer opens on, where the layout is about one. */
  tab?: InspectorTab;
}

/**
 * The four layouts, which cost nothing beyond the controls they are made of.
 *
 * Each is one set of the states above and nothing else: no layout knows a
 * pixel, a fraction or a divider position, so choosing one leaves the reader's
 * own dividers exactly where they dragged them.
 *
 * `read` is today's default and is defined as the absence of everything — no
 * rail, no expansion — which is what makes it the layout the four scripted
 * reads still assert against, byte for byte.
 */
export const LAYOUTS: Record<LayoutName, Layout> = {
  read: { key: "g", says: "read", railed: [], expanded: null },
  table: { key: "t", says: "table", railed: ["cone"], expanded: "grid" },
  lineage: { key: "l", says: "lineage", railed: ["grid"], expanded: "cone" },
  source: { key: "s", says: "source", railed: ["grid"], expanded: null, tab: "source" },
};

/** The four layout names, in the order the strip offers them. */
export const LAYOUT_NAMES: LayoutName[] = ["read", "table", "lineage", "source"];

/** Where the panes stand: what is railed, and what has the page. */
export interface PaneState {
  railed: PaneName[];
  expanded: PaneName | null;
}

/** Nothing railed and nothing expanded: the default, and the `read` layout. */
export const initialPaneState: PaneState = { railed: [], expanded: null };

/** The moves the panes' controls and keys can make. */
export type PaneAction =
  | { collapse: PaneName }
  | { open: PaneName }
  | { expand: PaneName }
  | { restore: true }
  | { toggle: PaneName }
  | { layout: LayoutName };

/** `name` with `pane` in it exactly once, in the order `PANES` gives. */
function withPane(railed: PaneName[], pane: PaneName): PaneName[] {
  return PANES.filter((name) => name === pane || railed.includes(name));
}

/**
 * Apply one move to the pane states.
 *
 * Opening a railed pane also ends an expansion that was hiding it, because a
 * reader who clicks a rail is asking to see that pane and an expansion still
 * standing over it would answer by doing nothing visible.
 *
 * @param state - Where the panes stand now.
 * @param action - The move.
 * @returns Where they stand next.
 */
export function reducePanes(state: PaneState, action: PaneAction): PaneState {
  // Every branch returns the state it was handed where the move changes
  // nothing. A reducer that returned a fresh object for a move with no effect
  // would re-render four panes to say that nothing happened, and one of those
  // panes is a graph.
  if ("collapse" in action) {
    if (state.railed.includes(action.collapse) && state.expanded !== action.collapse) return state;
    return {
      railed: withPane(state.railed, action.collapse),
      // A pane cannot be both expanded and a rail; collapsing the expanded one
      // is a restore that also puts it away.
      expanded: state.expanded === action.collapse ? null : state.expanded,
    };
  }
  if ("open" in action) {
    const hidden = state.expanded !== null && state.expanded !== action.open;
    if (!state.railed.includes(action.open) && !hidden) return state;
    return {
      railed: state.railed.filter((name) => name !== action.open),
      // Opening a railed pane ends an expansion that was standing over it: a
      // reader clicking a rail is asking to see that pane, and an expansion
      // left in place would answer by doing nothing visible.
      expanded: hidden ? null : state.expanded,
    };
  }
  if ("expand" in action) {
    if (state.expanded === action.expand) return state;
    // Expanding a railed pane takes it off its rail: an expanded pane fills
    // the page area, which a rail is not a way of doing.
    return {
      railed: state.railed.filter((name) => name !== action.expand),
      expanded: action.expand,
    };
  }
  if ("restore" in action) return state.expanded === null ? state : { ...state, expanded: null };
  if ("toggle" in action) {
    return state.railed.includes(action.toggle)
      ? reducePanes(state, { open: action.toggle })
      : reducePanes(state, { collapse: action.toggle });
  }
  const layout = LAYOUTS[action.layout];
  if (layoutOf(state) === action.layout) return state;
  return { railed: [...layout.railed], expanded: layout.expanded };
}

/**
 * Is this pane drawn as a rail right now?
 *
 * The one question `Panes.tsx` asks, and the reason an expansion does not have
 * to be written into the railed set to take effect: under an expansion every
 * other pane is a rail for as long as it lasts, and the set the reader chose
 * comes back untouched the moment Escape is pressed.
 *
 * @param state - Where the panes stand.
 * @param pane - The pane asking.
 * @returns Whether it draws itself as a rail rather than as a region.
 */
export function railed(state: PaneState, pane: PaneName): boolean {
  if (state.expanded !== null) return pane !== state.expanded;
  return state.railed.includes(pane);
}

/**
 * Which layout the panes are standing in, where they are standing in one.
 *
 * Derived rather than remembered, deliberately. A layout is a set of pane
 * states and nothing more, so a reader who picks `table` and then opens the
 * cone is no longer in `table` — and a page that kept saying so would be
 * naming a state it was not in. Nothing is stored for this.
 *
 * @param state - Where the panes stand.
 * @returns The layout whose states these are, or null for any other set.
 */
export function layoutOf(state: PaneState): LayoutName | null {
  for (const name of LAYOUT_NAMES) {
    const layout = LAYOUTS[name];
    if (layout.expanded !== state.expanded) continue;
    if (layout.railed.length !== state.railed.length) continue;
    if (layout.railed.every((pane) => state.railed.includes(pane))) return name;
  }
  return null;
}
