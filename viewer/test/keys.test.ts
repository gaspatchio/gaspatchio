// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * What a key press means here, and — more to the point — what it does not.
 *
 * The key list is short and its one dangerous clause is the suppression: a page
 * that took a letter while the search box had focus would be a page nobody
 * could type a column name into. So the cases below spend as much effort on the
 * presses this page must leave alone as on the ones it answers.
 */

import { describe, expect, it } from "vitest";

import { actionFor, typingInto } from "../src/state/keys";
import type { Focused, Press } from "../src/state/keys";

/** One press, with nothing held unless the case says so. */
function press(part: Partial<Press>): Press {
  return {
    key: "",
    code: "",
    shiftKey: false,
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    ...part,
  };
}

describe("the panes", () => {
  it("focuses one of the three on a digit, and the fourth digit now reaches nothing", () => {
    expect(actionFor(press({ key: "1", code: "Digit1" }))).toEqual({ focus: "grid" });
    expect(actionFor(press({ key: "2", code: "Digit2" }))).toEqual({ focus: "cone" });
    expect(actionFor(press({ key: "3", code: "Digit3" }))).toEqual({ focus: "inspector" });

    // The proof stopped being a pane and became a strip under the cone, so
    // there is no fourth pane for a fourth digit to focus.
    expect(actionFor(press({ key: "4", code: "Digit4" }))).toBeNull();
  });

  it("expands it when shift is held, whatever the keyboard prints", () => {
    // `!` is what a US keyboard sends for shift and 1, and `"` is what a
    // British one sends. Reading `code` is why both reach the same pane.
    expect(actionFor(press({ key: "!", code: "Digit1", shiftKey: true }))).toEqual({
      expand: "grid",
    });
    expect(actionFor(press({ key: '"', code: "Digit2", shiftKey: true }))).toEqual({
      expand: "cone",
    });
  });

  it("has nothing for a fifth digit", () => {
    expect(actionFor(press({ key: "5", code: "Digit5" }))).toBeNull();
    expect(actionFor(press({ key: "0", code: "Digit0" }))).toBeNull();
  });
});

describe("the rest of the list", () => {
  it("restores on Escape", () => {
    expect(actionFor(press({ key: "Escape", code: "Escape" }))).toEqual({ restore: true });
  });

  it("toggles the drawer on a backslash", () => {
    expect(actionFor(press({ key: "\\", code: "Backslash" }))).toEqual({ drawer: true });
  });

  it("reaches each layout by its own letter", () => {
    expect(actionFor(press({ key: "g", code: "KeyG" }))).toEqual({ layout: "read" });
    expect(actionFor(press({ key: "t", code: "KeyT" }))).toEqual({ layout: "table" });
    expect(actionFor(press({ key: "l", code: "KeyL" }))).toEqual({ layout: "lineage" });
    expect(actionFor(press({ key: "s", code: "KeyS" }))).toEqual({ layout: "source" });
  });

  it("leaves a letter nothing is bound to alone", () => {
    expect(actionFor(press({ key: "q", code: "KeyQ" }))).toBeNull();
  });

  it("leaves a capital letter alone, because it is a letter somebody meant to type", () => {
    expect(actionFor(press({ key: "T", code: "KeyT", shiftKey: true }))).toBeNull();
  });
});

describe("what belongs to the browser", () => {
  it("takes nothing held with control, meta or alt", () => {
    expect(actionFor(press({ key: "1", code: "Digit1", metaKey: true }))).toBeNull();
    expect(actionFor(press({ key: "t", code: "KeyT", ctrlKey: true }))).toBeNull();
    expect(actionFor(press({ key: "\\", code: "Backslash", altKey: true }))).toBeNull();
    expect(actionFor(press({ key: "Escape", code: "Escape", metaKey: true }))).toBeNull();
  });
});

describe("typing stays typing", () => {
  /** What a focused element looks like to this decision. */
  function focused(part: Partial<Focused>): Focused {
    return { tag: "div", type: null, editable: false, ...part };
  }

  it("suppresses everything while focus is in a field a character lands in", () => {
    expect(typingInto(focused({ tag: "INPUT", type: "search" }))).toBe(true);
    expect(typingInto(focused({ tag: "INPUT", type: "text" }))).toBe(true);
    // An input with no type attribute is a text input, which is why the
    // default matters: the page's own search box is `type="search"`, but a
    // field somebody adds later may carry no type at all.
    expect(typingInto(focused({ tag: "INPUT", type: null }))).toBe(true);
    expect(typingInto(focused({ tag: "TEXTAREA" }))).toBe(true);
    expect(typingInto(focused({ tag: "DIV", editable: true }))).toBe(true);
  });

  it("does not suppress on a control nobody types into", () => {
    // The period cursor is a range input. Suppressing there would take the
    // layouts away from a reader who had just moved the row cursor.
    expect(typingInto(focused({ tag: "INPUT", type: "range" }))).toBe(false);
    expect(typingInto(focused({ tag: "INPUT", type: "checkbox" }))).toBe(false);
    expect(typingInto(focused({ tag: "BUTTON" }))).toBe(false);
    expect(typingInto(focused({ tag: "DIV" }))).toBe(false);
  });

  it("does not suppress when nothing has focus at all", () => {
    expect(typingInto(null)).toBe(false);
  });
});

describe("the grid's own keys", () => {
  it("claims none of them", () => {
    for (const key of ["ArrowDown", "ArrowUp", "PageDown", "PageUp", "Home", "End"]) {
      expect(actionFor(press({ key, code: key }))).toBeNull();
    }
  });
});
