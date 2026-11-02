// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The two pure parts the shell rests on: how a value is written down, and how
 * the one selection moves.
 *
 * Both are tested here rather than in the page because both are decisions
 * about meaning, not about pixels. A number written one way in the grid and
 * another way in the proof would be two claims about one value, so the
 * convention is one function with one set of cases; and a selection that moved
 * differently depending on which view asked would make a click in the grid and
 * a click in the cone two different things, so the move is one reducer.
 */

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { ExactInteger } from "../src/reader/exact";
import { exactly, formatFormula, formatValue } from "../src/reader/format";
import { initialSelection, reduceSelection } from "../src/state/selection";

describe("formatValue", () => {
  it("writes a number with thousands and two decimals", () => {
    expect(formatValue(1234.5678)).toBe("1,234.57");
  });

  it("abbreviates a million and above so a row stays one line", () => {
    expect(formatValue(24065746.88)).toBe("24.07m");
  });

  it("says nothing with a mark rather than a zero", () => {
    expect(formatValue(null)).toBe("·");
  });

  it("leaves a string exactly as the file wrote it", () => {
    expect(formatValue("Yes")).toBe("Yes");
  });

  it("writes an integer column without decimals", () => {
    expect(formatValue(100, { integer: true })).toBe("100");
  });

  /*
   * Decided from the page rather than from this file. At two decimals every
   * monthly rate in the level-4 export printed as `0.00`, and a column of
   * `0.00` where the file holds 0.00408163 is not quoting the file. Below one
   * the digits are the whole of the value, so below one the digits are shown.
   */
  it("writes a rate below one to the digits the file holds", () => {
    expect(formatValue(0.05)).toBe("0.05");
    expect(formatValue(0.0041)).toBe("0.0041");
    expect(formatValue(0.00408163)).toBe("0.00408163");
    expect(formatValue(-0.0625)).toBe("-0.0625");
  });

  it("stops a rate at six significant digits, which is what a rate is quoted to", () => {
    expect(formatValue(0.004081632653061225)).toBe("0.00408163");
  });

  it("leaves everything else where it was", () => {
    expect(formatValue(1.005)).toBe("1.01");
    expect(formatValue(0)).toBe("0.00");
    expect(formatValue(0.5, { integer: true })).toBe("1");
  });
});

/**
 * Every number token in one document's own text, strings skipped.
 *
 * A scanner and not a pattern, because a formula's text carries numbers too —
 * `[1, 0.994058, ‥]` inside a trace's `expr` — and those are the producer's
 * rounded prose about a value, not a value.
 */
function numberTokens(text: string): string[] {
  const found: string[] = [];
  let at = 0;
  while (at < text.length) {
    const here = text[at];
    if (here === '"') {
      at += 1;
      while (at < text.length && text[at] !== '"') at += text[at] === "\\" ? 2 : 1;
      at += 1;
    } else if (here !== undefined && /[-\d]/.test(here)) {
      const token = /^-?\d+(\.\d+)?([eE][+-]?\d+)?/.exec(text.slice(at, at + 40))?.[0] ?? here;
      found.push(token);
      at += token.length;
    } else {
      at += 1;
    }
  }
  return found;
}

describe("exactly", () => {
  it("writes every digit the double holds, where formatValue rounds", () => {
    expect(formatValue(0.004081632653061224)).toBe("0.00408163");
    expect(exactly(0.004081632653061224)).toBe("0.004081632653061224");
    expect(formatValue(11.916666666666666)).toBe("11.92");
    expect(exactly(11.916666666666666)).toBe("11.916666666666666");
  });

  it("spells a float the way the producer's shortest repr does", () => {
    // A whole float keeps its point; the exponent turns on where repr turns
    // it on, with a sign and two digits; a negative zero is not zero.
    expect(exactly(12)).toBe("12.0");
    expect(exactly(0)).toBe("0.0");
    expect(exactly(-0)).toBe("-0.0");
    expect(exactly(0.0001)).toBe("0.0001");
    expect(exactly(0.00001)).toBe("1e-05");
    expect(exactly(1.5e-7)).toBe("1.5e-07");
    expect(exactly(1e15)).toBe("1000000000000000.0");
    expect(exactly(1e16)).toBe("1e+16");
    expect(exactly(-24065746.88)).toBe("-24065746.88");
    expect(exactly(0.1 + 0.2)).toBe("0.30000000000000004");
    expect(exactly(5e-324)).toBe("5e-324");
    expect(exactly(1.7976931348623157e308)).toBe("1.7976931348623157e+308");
  });

  it("writes an integer column as the integers the file wrote", () => {
    expect(exactly(12, { integer: true })).toBe("12");
    expect(exactly(new ExactInteger("9007199254740993", 9007199254740992))).toBe("9007199254740993");
    expect(exactly(new ExactInteger(null, 9007199254740992))).toBe("≈9007199254740992");
  });

  it("leaves a string itself and says there is no value where there is none", () => {
    expect(exactly("NaN")).toBe("NaN");
    expect(exactly("2027-01-31")).toBe("2027-01-31");
    expect(exactly(true)).toBe("true");
    expect(exactly(null)).toBeNull();
    expect(exactly(undefined)).toBeNull();
  });

  /*
   * The claim the page makes is "the file holds", so it is held to the files.
   * Both documents are the producer's own exports, written by its JSON
   * encoder, so every number in them is a token in the producer's spelling:
   * read back and written by `exactly`, each must come out character for
   * character. The level-4 export carries tens of thousands of them.
   */
  it.each(["level4", "record"])(
    "writes back every number in %s.json as the token the file holds",
    (name) => {
      const text = readFileSync(new URL(`../fixtures/${name}.json`, import.meta.url), "utf8");
      const tokens = numberTokens(text);
      const floats = tokens.filter((token) => /[.eE]/.test(token));
      expect(floats.length).toBeGreaterThan(name === "level4" ? 10_000 : 50);
      const moved = floats.filter((token) => exactly(Number(token)) !== token);
      expect(moved).toEqual([]);
      const integers = tokens.filter((token) => !/[.eE]/.test(token) && Number.isSafeInteger(Number(token)));
      expect(integers.filter((token) => exactly(Number(token), { integer: true }) !== token)).toEqual([]);
    },
  );
});

describe("formatFormula", () => {
  it("collapses a formula written over three lines onto one", () => {
    expect(formatFormula("when(af.a > 0)\n  .then(1)\n  .otherwise(0)")).toBe(
      "when(af.a > 0) .then(1) .otherwise(0)",
    );
  });
});

describe("reduceSelection", () => {
  it("keeps the period when the selected column changes", () => {
    const at12 = reduceSelection(initialSelection, { period: 12 });
    expect(reduceSelection(at12, { select: "net_cf@1" })).toEqual({
      ...initialSelection,
      nodeId: "net_cf@1",
      period: 12,
    });
  });

  it("never widens the cone above the selected node to less than nothing", () => {
    expect(reduceSelection(initialSelection, { up: -1 }).up).toBe(0);
  });
});
