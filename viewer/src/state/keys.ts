// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * What a key press means, decided away from the browser that sent it.
 *
 * The keys: 1–4 focus a pane, shift and a digit expands it, Escape restores, `\`
 * toggles the drawer, and one letter reaches each of the four layouts. The
 * whole of that decision is the function below, over a description of an event
 * rather than an event, so the answer to "what does `t` do here?" is a test and
 * not a browser session.
 *
 * **Everything is suppressed while focus is in a text field**, which is the
 * clause that makes the rest of it safe. A page whose search box swallowed the
 * letters it was given would be a page a reader could not type `total_claims`
 * into, and the search box is the page's front door. `inATextField` is
 * deliberately strict about what counts: a range input is not somewhere anybody
 * types, so the period slider does not disable the layouts, and a checkbox is
 * not either. What counts is a field where a character would land.
 *
 * **The digits are read off `code` and not off `key`.** Shift and `1` is `!` on
 * a US keyboard, `"` on a British one and something else again elsewhere, and a
 * page that read the character would have four shortcuts that worked on one
 * layout. `Digit1` is the key under the finger whatever the keyboard prints on
 * it.
 *
 * **A modified press is never ours.** Anything held with control, meta or alt
 * belongs to the browser or the desktop — ⌘1 is a tab, ⌥\ is a character — so
 * this returns nothing rather than taking one of them away.
 */

import { LAYOUT_NAMES, LAYOUTS, PANES } from "./layout";
import type { LayoutName, PaneName } from "./layout";

/** What a press asks the page to do. */
export type KeyAction =
  | { focus: PaneName }
  | { expand: PaneName }
  | { restore: true }
  | { drawer: true }
  | { layout: LayoutName };

/** The parts of a key event this decision is made from, and nothing else. */
export interface Press {
  key: string;
  code: string;
  shiftKey: boolean;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
}

/**
 * The input types a character lands in.
 *
 * Listed rather than excluded, so an input type this page never uses is treated
 * as a place somebody might type rather than as a shortcut it can steal.
 */
const TYPING = new Set(["text", "search", "email", "url", "tel", "password", "number"]);

/** What has focus, as much of it as this decision needs. */
export interface Focused {
  tag: string;
  /** The input's `type`, where it is an input at all. */
  type: string | null;
  editable: boolean;
}

/**
 * Is a character pressed now going to land in a field?
 *
 * The rule, away from the document that would answer it, so that "does `t`
 * reach the layouts while the search box has focus?" is a case in a file rather
 * than a browser somebody has to open. `inATextField` below is the two lines
 * that read a real element into this.
 *
 * @param focused - What has focus, or nothing at all.
 * @returns Whether the press belongs to whatever has focus.
 */
export function typingInto(focused: Focused | null): boolean {
  if (focused === null) return false;
  const tag = focused.tag.toLowerCase();
  if (tag === "textarea") return true;
  if (focused.editable) return true;
  if (tag !== "input") return false;
  // An input with no type attribute is a text input, which is why the default
  // here is "text" rather than nothing.
  return TYPING.has((focused.type ?? "text").toLowerCase());
}

/**
 * The same question, of a real element.
 *
 * @param element - Whatever has focus, which may be nothing at all.
 * @returns Whether a character pressed now would land in a field.
 */
export function inATextField(element: Element | null): boolean {
  if (element === null) return false;
  return typingInto({
    tag: element.tagName,
    type: element.getAttribute("type"),
    editable: element instanceof HTMLElement && element.isContentEditable,
  });
}

/** Digit1 … Digit4 → the pane that digit stands for. */
function paneFor(code: string): PaneName | undefined {
  const at = ["Digit1", "Digit2", "Digit3", "Digit4"].indexOf(code);
  return at < 0 ? undefined : PANES[at];
}

/** The letter a layout answers to → the layout. */
function layoutFor(key: string): LayoutName | undefined {
  return LAYOUT_NAMES.find((name) => LAYOUTS[name].key === key.toLowerCase());
}

/**
 * What this press means, or nothing where it means nothing here.
 *
 * @param press - The event's own description of itself.
 * @returns The move to make, or null to leave the press alone.
 */
export function actionFor(press: Press): KeyAction | null {
  if (press.ctrlKey || press.metaKey || press.altKey) return null;

  if (press.key === "Escape") return { restore: true };
  if (press.code === "Backslash" || press.key === "\\") return { drawer: true };

  const pane = paneFor(press.code);
  if (pane !== undefined) return press.shiftKey ? { expand: pane } : { focus: pane };

  // Shift and a letter is not a layout: `T` is a capital letter somebody meant
  // to type, and the four layouts are the unshifted keys the mocks print.
  if (press.shiftKey) return null;
  const layout = layoutFor(press.key);
  return layout === undefined ? null : { layout };
}
