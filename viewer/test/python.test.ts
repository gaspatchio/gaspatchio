// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The tokeniser colours characters and never changes one.
 *
 * The first test is the one that matters: over the tutorial's own model file,
 * the tokens put back together are the file. The text under the source tab is
 * under a digest, and a highlighter that dropped a character would be showing a
 * reader something other than the line that ran while still claiming the digest
 * above it. The rest are the cases where a hand-written tokeniser goes wrong.
 */

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { highlight, tokenize } from "../src/views/python";

/** The tokens, back together. What the file must equal. */
function rejoin(text: string): string {
  return tokenize(text)
    .map((token) => token.text)
    .join("");
}

/** The kinds a snippet produces, in order, with their text. */
function kinds(text: string): [string, string][] {
  return tokenize(text).map((token) => [token.kind, token.text]);
}

describe("the invariant", () => {
  it("puts the tutorial's whole model file back together, byte for byte", () => {
    const model = readFileSync(
      "../bindings/python/gaspatchio/tutorials/level-4-lifelib/base/model.py",
      "utf8",
    );
    expect(model.length).toBeGreaterThan(30_000);
    expect(rejoin(model)).toBe(model);
  });

  it("puts every line back together, and loses no line", () => {
    const model = readFileSync(
      "../bindings/python/gaspatchio/tutorials/level-4-lifelib/base/model.py",
      "utf8",
    );
    const lines = highlight(model);
    expect(lines.length).toBe(model.split("\n").length);
    expect(lines.map((line) => line.map((token) => token.text).join("")).join("\n")).toBe(model);
  });

  it.each([
    'x = "a # not a comment"',
    "# a comment with a \" quote and a ' quote",
    'f"a {b} c"',
    'rb"\\x00"',
    "'''triple\nacross\nlines'''",
    '"""doc"""',
    '"unterminated\nnext_line = 1',
    "x = 100_000.0",
    "y = 0x1f + 0b1010 + 1e-9 + 3j",
    "z = .5",
    "@decorator\ndef f(a: int = 1) -> None: ...",
    "af.pols_death = af.pols_if * af.mort_rate_mth",
    "",
    "\n\n",
    "   ",
  ])("puts %j back together", (snippet) => {
    expect(rejoin(snippet)).toBe(snippet);
  });
});

describe("what gets which colour", () => {
  it("colours a keyword, a name and a string the three different ways", () => {
    expect(kinds('from gaspatchio import ActuarialFrame  # the frame')).toEqual([
      ["keyword", "from"],
      ["plain", " "],
      ["name", "gaspatchio"],
      ["plain", " "],
      ["keyword", "import"],
      ["plain", " "],
      ["name", "ActuarialFrame"],
      ["plain", "  "],
      ["comment", "# the frame"],
    ]);
  });

  it("keeps a string's prefix inside the string", () => {
    expect(kinds('f"{x}"')).toEqual([["string", 'f"{x}"']]);
  });

  it("does not colour a soft keyword, because a variable may be called one", () => {
    expect(kinds("case = 1")).toEqual([
      ["name", "case"],
      ["plain", " "],
      ["punct", "="],
      ["plain", " "],
      ["number", "1"],
    ]);
  });

  it("ends an unterminated string at the line rather than eating the file", () => {
    const lines = highlight('x = "oops\ny = 1');
    expect(lines[0]?.map((token) => token.kind)).toContain("string");
    expect(lines[1]?.map((token) => token.kind)).not.toContain("string");
  });

  it("colours a whole triple-quoted docstring, on every line of it", () => {
    const lines = highlight('"""one\ntwo"""\nx = 1');
    expect(lines[0]?.every((token) => token.kind === "string")).toBe(true);
    expect(lines[1]?.every((token) => token.kind === "string")).toBe(true);
    expect(lines[2]?.map((token) => token.kind)).toContain("number");
  });

  it("reads a number with underscores and an exponent as one number", () => {
    expect(kinds("100_000.0")).toEqual([["number", "100_000.0"]]);
    expect(kinds("1e-9")).toEqual([
      ["number", "1e-9"],
    ]);
  });
});
