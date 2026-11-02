// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The integers a JavaScript number cannot carry, kept as the file spelled them.
 *
 * A portable integer is exact in the format: a model's own `UInt64` is judged
 * on its values and named `i64` (§10), and §11.1.25 admits pure-i64 arithmetic
 * across the signed range. So `9007199254740993` is a value a conforming
 * document may carry — and `JSON.parse` turns it into `9007199254740992`
 * before any reader can look at the node's `dtype`. The page then displayed a
 * number the file does not hold, in the grid, in the trace and in a comparison,
 * with nothing on the screen admitting it. An external review found it.
 *
 * **What is kept is the token.** The reviver below is handed the literal's own
 * source text (`JSON.parse`'s third reviver argument), and where a double
 * cannot be trusted to carry the integer it spells, the digits travel beside
 * the double this page will never do arithmetic on.
 *
 * Three shapes were available and the token is the one taken:
 *
 * - **A `BigInt`** is exact and native, and it cannot leave the page: it has no
 *   `JSON.stringify`, so every harness that reads this reader's answers through
 *   JSON — the external review's own among them — stops working, and every
 *   `typeof` in the reader gains a fourth answer that mixes with a double only
 *   under an explicit conversion at each site.
 * - **A second parse** of the raw text — tokenise it, find the wide literals,
 *   parse it again — is what the page rules out: parse once,
 *   index once, draw. It is also unnecessary, since the reviver is handed the
 *   same characters during the one parse. (There *is* a cheap test over the
 *   text below, `MIGHT_HOLD_ONE`, and it is not a parse: it reads no
 *   structure, builds nothing, and decides only which single parse runs.)
 * - **The token beside the number**, which is this. The digits are what the
 *   file says; the double is what the page falls back to where an engine will
 *   not hand the digits over, and it is never shown as though it were exact.
 *
 * A bare digit string was refused: a file carries real strings — a product
 * code, a policy number, a date the producer already rendered — and a page
 * that could not tell `"9007199254740993"` from the integer would group the
 * digits of a scheme identifier and call it money.
 *
 * **Nothing here computes.** An exact integer never enters arithmetic as
 * itself. Equality and ranking are taken on the digits, which is exact; where
 * a *ratio* is wanted — the changes list's relative magnitude, a term's share
 * of a gross sum — the caller asks for `approximately` and gets the double,
 * because a ratio is not an integer and no exactness is lost by a number that
 * was never going to be exact. The values printed on the page stay the file's.
 */

/**
 * An integer the file spells that a JavaScript number cannot be trusted with.
 *
 * `digits` is the literal exactly as the document wrote it, sign and all.
 * `rounded` is what `JSON.parse` made of it — the nearest double, which is the
 * number the page displayed before this existed.
 *
 * `digits` is **null** where the engine would not hand the source text over.
 * That is not a shape the two engines this page is tested in produce; it is
 * what an older one does, and the page says *approximately* in that case
 * rather than printing a rounded integer as though it were the file's.
 */
export class ExactInteger {
  /** The literal as the file spelled it, or null where it could not be read. */
  readonly digits: string | null;

  /** The double `JSON.parse` produced, which is what those digits round to. */
  readonly rounded: number;

  constructor(digits: string | null, rounded: number) {
    this.digits = digits;
    this.rounded = rounded;
  }

  /**
   * The digits, for anything that serialises this — a harness, a test.
   *
   * The string rather than the number, because the number is the thing that
   * cannot hold it. Where there are no digits the double is all there is, and
   * a reader of that output meets the same value the page marks as
   * approximate.
   */
  toJSON(): string | number {
    return this.digits ?? this.rounded;
  }

  /** The same, for anything that interpolates it. */
  toString(): string {
    return this.digits ?? String(this.rounded);
  }
}

/** Whether a value the file carried is one of those. */
export function isExactInteger(value: unknown): value is ExactInteger {
  return value instanceof ExactInteger;
}

/**
 * One value as the term its equality is taken on.
 *
 * Two exact integers built from one document are two objects and are never the
 * same object, so every equality in the reader would say they moved. This
 * reduces each to something comparable — the digits, or the double where there
 * are none — and leaves the comparison itself to the caller, because the
 * callers do not agree about it: the changes list counts a NaN that stayed a
 * NaN as a move (`===`) and the trace's disagreement flag does not
 * (`Object.is`), and neither of those rules is this module's to change.
 *
 * The digits are prefixed. A column that stopped being `i64` and started being
 * text would otherwise compare equal to itself across the change, and "the
 * integer 42" and "the characters 4 and 2" are two different things for a page
 * whose whole job is to quote the file.
 *
 * @param value - Any value read off the document.
 * @returns The term to compare, which for everything else is the value itself.
 */
export function comparedAs(value: unknown): unknown {
  if (!isExactInteger(value)) return value;
  return value.digits === null ? value.rounded : `i64:${value.digits}`;
}

/**
 * The double behind a number, for the one kind of answer that is a ratio.
 *
 * Never for a value the page prints. A relative magnitude and a share of a
 * gross sum are both quotients and neither has an exact decimal, so taking
 * them on the double loses nothing that was ever available; the figures either
 * side of them are still written from the digits.
 *
 * @param value - Any value read off the document.
 * @returns The number, or null where the value is not one.
 */
export function approximately(value: unknown): number | null {
  if (typeof value === "number") return value;
  return isExactInteger(value) ? value.rounded : null;
}

/**
 * One value back in the file's own notation, with a wide integer left bare.
 *
 * `JSON.stringify` would quote it. It has to: the only thing an exact integer
 * can offer `toJSON` is a string, because the number is what cannot hold it.
 * But the drawer prints a node's record as the file writes it, and
 * `["9007199254740993"]` there would say the document carries a *string* where
 * it carries a number — the page inventing a dtype, which is the same class of
 * wrong answer as rounding the digits away.
 *
 * So the notation is written here, and only where it has to be: everything
 * that is not one of these goes straight through `JSON.stringify`.
 *
 * @param value - Any value read off the document.
 * @returns Compact JSON, with every exact integer written as its own digits.
 */
export function asWritten(value: unknown): string {
  if (isExactInteger(value)) return value.digits ?? String(value.rounded);
  if (Array.isArray(value)) return `[${value.map(asWritten).join(",")}]`;
  if (typeof value === "object" && value !== null) {
    const members = Object.entries(value)
      .filter(([, member]) => member !== undefined)
      .map(([name, member]) => `${JSON.stringify(name)}:${asWritten(member)}`);
    return `{${members.join(",")}}`;
  }
  return JSON.stringify(value) ?? "undefined";
}

/** An integer literal, which is the only token whose digits are worth keeping. */
const INTEGER_LITERAL = /^-?\d+$/;

/**
 * Whether a document's text could hold an integer literal a double would round.
 *
 * **A reviver is not free**, and the cost is the reason this exists. Measured
 * on the committed level-4 export, 1.70 MB: `JSON.parse` takes 6.2 ms and
 * `JSON.parse` with a reviver takes 41.9 ms, because a reviver is called for
 * every value in the document and there are tens of thousands of them. That is
 * 36 ms on the cold open of every page the viewer writes, paid for a value
 * almost none of them carries. This test takes 0.1 ms.
 *
 * The test is an over-approximation and is sound in the direction that
 * matters. `Number.isSafeInteger` is false only at 2⁵³ and above, and every
 * integer from there up is written with **at least sixteen digits** — so a
 * document with no run of sixteen digits in a number position cannot hold one,
 * and a plain parse of it is the same document the reviver would have built.
 * A run that is really inside a string, or inside a formula's text, is a false
 * positive: the reviver runs, every value goes through it unchanged, and the
 * page is slower by 36 ms and wrong about nothing.
 *
 * A number position is the start of the text or a `:`, `,` or `[` before it,
 * which is everywhere JSON puts a value; the lookahead excludes a float, whose
 * digits are not an integer's however many of them there are.
 *
 * One consequence, stated rather than left to be found: on an engine that does
 * not hand a literal's source text over, a *float* past the safe range —
 * `1e300` — is marked approximate in a document that also carries a wide
 * integer and is not in one that does not. The page cannot tell the two apart
 * without the token, and neither case was ever an exact integer to lose.
 */
const MIGHT_HOLD_ONE = /(^|[:,[])\s*-?\d{16,}(?![\d.eE])/;

/**
 * What `JSON.parse` hands a reviver about the literal it just read.
 *
 * Declared here rather than taken from the library because the page is built
 * against a `JSON.parse` whose reviver is two arguments. `source` is absent on
 * an object or an array — there is no one literal behind either — and on an
 * engine that does not implement the third argument at all, which is the case
 * `digits: null` above exists for.
 */
interface LiteralSource {
  source?: string;
}

/**
 * Read one artifact's text, keeping every integer a double would round.
 *
 * One `JSON.parse`, with a reviver where one can make a difference. The
 * page's order — parse, index, draw, once each — is the reason this is a reviver and not a
 * pass over the characters: the page reads the document once, whichever branch
 * it takes. `MIGHT_HOLD_ONE` is a test over the text and not a parse of it,
 * and it decides only which single parse runs.
 *
 * The rule is the narrowest one that is true: an integer **literal** whose
 * value is not a safe integer is kept. `Number.isSafeInteger` is exactly the
 * question "can a double be trusted with this whole number", so a rate, a
 * discount factor and every ordinary money figure go through untouched and
 * nothing about them moves. `-0` is a safe integer and stays the number it
 * was; `1e300` is not an integer literal and stays a float.
 *
 * @param text - One artifact block, as the exporter wrote it into the page.
 * @returns The parsed document, with `ExactInteger` wherever a literal needed one.
 * @throws SyntaxError - Where the text is not JSON, which is the caller's refusal.
 */
export function parseExactly(text: string): unknown {
  if (!MIGHT_HOLD_ONE.test(text)) return JSON.parse(text);
  const keepingIntegers = (
    _key: string,
    value: unknown,
    context?: LiteralSource,
  ): unknown => {
    if (typeof value !== "number") return value;
    if (Number.isSafeInteger(value)) return value;
    const source = context?.source;
    // No source text: the engine is older than this reviver's third argument,
    // and a whole number past the safe range is one the page cannot promise.
    if (source === undefined) {
      return Number.isInteger(value) ? new ExactInteger(null, value) : value;
    }
    if (!INTEGER_LITERAL.test(source)) return value;
    return new ExactInteger(source, value);
  };
  return JSON.parse(text, keepingIntegers as (key: string, value: unknown) => unknown);
}
