// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The integers a double cannot carry, from the parse to the page.
 *
 * The case is one an external review found, and its artifact is the smallest one
 * that shows it: a model adding `1` to the Int64 input `9007199254740992`,
 * whose `result` is `9007199254740993` with an `i64` dtype. §11.1.25 admits
 * that arithmetic across the signed range and §10 makes the format's integers
 * exact, so it is a value a conforming document carries — and `JSON.parse`
 * rounded it away before the reader could look at the dtype.
 *
 * Built here rather than committed as a fixture: what is under test is the
 * reader's arithmetic on a literal, and a whole level-4 export would put a
 * megabyte between the assertion and the thing it asserts.
 */

import { readFileSync, readdirSync } from "node:fs";

import { describe, expect, it } from "vitest";

import {
  ExactInteger,
  approximately,
  comparedAs,
  isExactInteger,
  parseExactly,
} from "../src/reader/exact";
import { formatValue } from "../src/reader/format";

/**
 * Every committed document the page is packed from, so the shortcut is held to
 * all of them. `refusal-*` and `written-*` are not among them: the end-to-end
 * specs write those into the same directory and git ignores them, so counting
 * them made the check below pass only where the end-to-end run had left them
 * behind. A fresh checkout holds the committed twenty.
 */
const FIXTURES = readdirSync(new URL("../fixtures/", import.meta.url))
  .filter((name) => name.endsWith(".json") && !/^(refusal|written)-/.test(name))
  .map((name) => name.replace(/\.json$/, ""));

/** A literal a double rounds, and the one below it that a double does carry. */
const PAST = "9007199254740993";
const SAFE = "9007199254740991";

describe("parsing a document that carries a wide integer", () => {
  it("keeps the digits of an integer a double would round", () => {
    const parsed = parseExactly(`{"result": ${PAST}}`) as { result: unknown };
    expect(isExactInteger(parsed.result)).toBe(true);
    expect((parsed.result as ExactInteger).digits).toBe(PAST);
    // And the thing that went wrong: the double is not the file's number.
    expect(String((parsed.result as ExactInteger).rounded)).toBe("9007199254740992");
  });

  it("leaves every number a double carries exactly where it was", () => {
    const parsed = parseExactly(
      `{"safe": ${SAFE}, "rate": 0.00408163, "zero": 0, "negative": -0, "money": 24065746.88}`,
    ) as Record<string, unknown>;
    expect(parsed["safe"]).toBe(9007199254740991);
    expect(parsed["rate"]).toBe(0.00408163);
    expect(parsed["zero"]).toBe(0);
    // A negative zero is a safe integer and is left as the number it is. What
    // identity makes of `-0.0` is the format's question (§12.1 writes it apart
    // from zero), not this page's about a literal it was handed.
    expect(Object.is(parsed["negative"], -0)).toBe(true);
    expect(parsed["money"]).toBe(24065746.88);
    expect(Object.values(parsed).some(isExactInteger)).toBe(false);
  });

  it("leaves a string of digits a string", () => {
    // A policy number, a scheme identifier, a date the producer rendered. The
    // reason the token is not kept as a bare string: these must not be grouped
    // and written as money.
    const parsed = parseExactly(`{"id": "${PAST}"}`) as { id: unknown };
    expect(parsed.id).toBe(PAST);
    expect(isExactInteger(parsed.id)).toBe(false);
  });

  it("leaves a float past the safe range a float", () => {
    // `1e300` is not an integer literal, so there are no digits to keep and
    // nothing has been lost by the parse.
    const parsed = parseExactly(`{"huge": 1e300}`) as { huge: unknown };
    expect(parsed.huge).toBe(1e300);
  });

  it("keeps them inside a timeline, which is where a projection puts them", () => {
    const parsed = parseExactly(`{"value_sample": [1, ${PAST}, 3]}`) as {
      value_sample: unknown[];
    };
    expect(formatValue(parsed.value_sample[1])).toBe("9,007,199,254,740,993");
    expect(parsed.value_sample[0]).toBe(1);
  });

  it("serialises as its digits, so a harness reading the reader reads the file", () => {
    const parsed = parseExactly(`{"result": ${PAST}}`);
    expect(JSON.stringify(parsed)).toBe(`{"result":"${PAST}"}`);
  });

  it("takes the plain parse where no number position could hold one", () => {
    // The 36 ms the reviver costs on a level-4 export is not paid by a
    // document that cannot carry the value. What is asserted is the property
    // that makes the shortcut sound: the two parses agree, for every document
    // the shortcut is taken on.
    const ordinary = `{"a": [0.08333333333333333, 1e300, -0, 9007199254740991], "b": "${PAST}"}`;
    expect(parseExactly(ordinary)).toEqual(JSON.parse(ordinary));
  });

  it("takes the reviver wherever a wide integer can stand in JSON", () => {
    // Every position a value occupies: after a colon, after a comma, first in
    // an array. A false negative here is a rounded number shown as exact.
    for (const text of [
      `{"a": ${PAST}}`,
      `{"a": [1, ${PAST}]}`,
      `{"a": [${PAST}]}`,
      `{"a": [-${PAST}]}`,
      `{"a":${PAST}}`,
    ]) {
      const parsed = parseExactly(text) as { a: unknown };
      const held = Array.isArray(parsed.a) ? parsed.a[parsed.a.length - 1] : parsed.a;
      expect(isExactInteger(held)).toBe(true);
    }
  });

  it("holds the shortcut to every committed fixture", () => {
    // The property, over the documents the page actually opens: a fixture the
    // shortcut skips the reviver on parses to exactly what the reviver would
    // have built, and the one fixture that carries a wide integer does not
    // take the shortcut.
    let checked = 0;
    for (const name of FIXTURES) {
      const text = readFileSync(new URL(`../fixtures/${name}.json`, import.meta.url), "utf8");
      // `refusal-malformed` is not JSON on purpose, and both parses throw the
      // same way on it — which is the refusal `parseArtifacts` prints.
      let plain: unknown;
      try {
        plain = JSON.parse(text);
      } catch {
        expect(() => parseExactly(text)).toThrow();
        continue;
      }
      const kept = parseExactly(text);
      if (name === "wide-integer") expect(kept).not.toEqual(plain);
      else expect(kept).toEqual(plain);
      checked += 1;
    }
    expect(checked).toBe(FIXTURES.length);
    expect(checked).toBeGreaterThanOrEqual(20);
  });
});

describe("writing one down", () => {
  it("writes the digits the file spelled, grouped like every other integer", () => {
    const value = new ExactInteger(PAST, 9007199254740992);
    expect(formatValue(value)).toBe("9,007,199,254,740,993");
    expect(formatValue(value, { integer: true })).toBe("9,007,199,254,740,993");
  });

  it("never abbreviates one, for the reason no integer is abbreviated", () => {
    expect(formatValue(new ExactInteger("123456789012345678", 0))).toBe(
      "123,456,789,012,345,678",
    );
  });

  it("says approximately where the digits could not be had", () => {
    // The engine did not hand the literal's source text over. The page shows
    // the double it has and marks it, rather than printing a rounded integer
    // as though it were the file's.
    expect(formatValue(new ExactInteger(null, 9007199254740992))).toBe(
      "≈9,007,199,254,740,992",
    );
  });
});

describe("comparing one", () => {
  it("is equal to itself on the digits and not on the object", () => {
    const a = new ExactInteger(PAST, 9007199254740992);
    const b = new ExactInteger(PAST, 9007199254740992);
    expect(a === b).toBe(false);
    expect(comparedAs(a) === comparedAs(b)).toBe(true);
  });

  it("tells apart two integers one double would call equal", () => {
    const a = new ExactInteger("9007199254740993", 9007199254740992);
    const b = new ExactInteger("9007199254740992", 9007199254740992);
    expect(a.rounded === b.rounded).toBe(true);
    expect(comparedAs(a) === comparedAs(b)).toBe(false);
  });

  it("is not equal to a string of the same digits", () => {
    // A column that stopped being `i64` and started being text has changed,
    // and a comparison that called the two equal would say it had not.
    expect(comparedAs(new ExactInteger(PAST, 0)) === comparedAs(PAST)).toBe(false);
  });

  it("hands a ratio the double and nothing else", () => {
    expect(approximately(new ExactInteger(PAST, 9007199254740992))).toBe(9007199254740992);
    expect(approximately(1.5)).toBe(1.5);
    expect(approximately("a word")).toBeNull();
  });
});
