// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * How a value the file carries is written on the page.
 *
 * One convention, in one place, so that a number read in the grid and the same
 * number read in the proof are the same number written the same way. The page
 * never computes a value; formatting is the only thing it does to one, and
 * doing it in two places would be two claims about one figure.
 *
 * The locale is fixed rather than the reader's. A file that showed `1,234.57`
 * on one desk and `1.234,57` on another would be two documents, and this one is
 * meant to be quotable.
 *
 * **An integer past what a double carries is written from its own digits.**
 * `reader/exact.ts` keeps the token through the parse and `Intl` groups a
 * decimal string at any width, so a valid `9007199254740993` reads as itself
 * rather than as the `…992` this page used to print. The one case the digits
 * are not there — an engine that would not hand them over — is written with a
 * `≈` in front of it, because a rounded integer shown as though it were the
 * file's is the thing the whole of that module exists to stop.
 */

import { isExactInteger } from "./exact";
import type { Index } from "./index";

/** Below this the number is written out; at or above it, abbreviated. */
const MILLION = 1_000_000;

const PLAIN = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const WHOLE = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

/**
 * The same formatter, grouping a decimal string of any width.
 *
 * ES2023 widened `Intl.NumberFormat.format` to take a string, and that is the
 * whole reason an integer past 2⁵³ can be written here at all — a double
 * handed to the formatter would have lost the digits before it arrived. This
 * project's `lib` is `es2020` and carries the narrower declaration, so the
 * wider one is stated here. It is not a claim about the runtime: the three
 * engines this page is built and measured in — Node, Chromium and WebKit —
 * were each asked directly, and each groups `9007199254740993` exactly.
 */
const groupedDigits = WHOLE.format as unknown as (value: string) => string;

/**
 * How a value below one is written.
 *
 * Decided from the page rather than from a principle. At two decimals every
 * monthly rate in the level-4 export read `0.00`, and a column of `0.00` where
 * the file holds 0.00408163 is the page rounding a number away rather than
 * quoting it. Below one there is no integer part carrying the magnitude, so
 * the significant digits are the whole of the value and the significant digits
 * are what is shown. Six of them is where a rate is quoted in practice — a
 * monthly qx, a discount factor, a lapse rate — and `Intl` drops the trailing
 * zeros, so `0.05` stays `0.05` rather than becoming `0.0500000`.
 */
const RATE = new Intl.NumberFormat("en-US", { maximumSignificantDigits: 6 });

/** What a value the file did not carry looks like: a mark, never a zero. */
const ABSENT = "·";

/** What stands in front of a whole number this page could not keep exactly. */
const APPROXIMATELY = "≈";

/**
 * Write one value.
 *
 * @param v - The value as the file carries it: a number, an integer too wide
 *   for one (`reader/exact.ts`), a string the producer already rendered (a
 *   date, a code), a boolean, or nothing at all.
 * @param opts - `integer` when the node's `dtype` says the column holds whole
 *   numbers, so a month reads `12` rather than `12.00`. An integer is never
 *   abbreviated: a policy count or a period index abbreviated to `1.23m` has
 *   lost the thing it was counting.
 * @returns The value, written for a tabular column.
 */
export function formatValue(v: unknown, opts?: { integer?: boolean }): string {
  if (v === null || v === undefined) return ABSENT;
  // Whole by construction, and never abbreviated for the same reason no other
  // integer is: a scheme identifier written `9.01m` has lost what it names.
  // `opts.integer` is not consulted — the file spelled an integer literal, and
  // that is a stronger statement about this value than the column's `dtype`.
  if (isExactInteger(v)) {
    return v.digits === null
      ? `${APPROXIMATELY}${WHOLE.format(v.rounded)}`
      : groupedDigits(v.digits);
  }
  if (typeof v === "string") return v;
  if (typeof v !== "number") return String(v);
  if (!Number.isFinite(v)) return String(v);
  if (opts?.integer === true) return WHOLE.format(v);
  if (Math.abs(v) >= MILLION) return `${PLAIN.format(v / MILLION)}m`;
  // A whole number below one is zero, and a column of zeroes reads straighter
  // at the same two decimals as everything else around it.
  if (Math.abs(v) < 1 && !Number.isInteger(v)) return RATE.format(v);
  return PLAIN.format(v);
}

/**
 * Whether a column's `dtype` says it holds whole numbers.
 *
 * Read off the file's own type string rather than guessed from the values: a
 * float column whose sampled policy happens to hold round numbers is still a
 * float column, and writing it as one is the difference between reporting and
 * inferring.
 *
 * @param dtype - The node's `dtype`, `i64` or `list[i64]` or anything else.
 * @returns True for an integer column, list or scalar.
 */
export function isIntegerDtype(dtype: string): boolean {
  const inner = /^list\[(.*)\]$/.exec(dtype)?.[1] ?? dtype;
  return /^[iu](8|16|32|64)$/.test(inner);
}

/**
 * Write one formula on one line.
 *
 * The string is the node's `formula` as the producer recorded it, which is the
 * source line as the actuary wrote it — often wrapped over three or four lines
 * by a formatter. A header row is one line tall, so the wrapping is collapsed
 * and nothing else is touched: no re-rendering from a tree, no pretty-printing,
 * no shortening. What is shown is what is in the file, minus the newlines the
 * page has no room for.
 *
 * @param f - The node's `formula`, or null where the file records none.
 * @returns The formula on one line; the empty string when there is no formula.
 */
export function formatFormula(f: string | null): string {
  if (f === null) return "";
  return f.replace(/\s+/g, " ").trim();
}

/** How much of a fingerprint a reader actually compares. */
const SHOWN = 8;

/**
 * The first eight hex of a fingerprint, past whatever algorithm prefix it carries.
 *
 * Eight is what somebody checking two stamps against each other reads, and the
 * whole of it is always one hover or one click away. It lives here with the
 * other conventions because the header's truncation and the proof panel's chip
 * are the same truncation, and two of them would be two claims about one stamp.
 *
 * @param fingerprint - A `sha256:…` stamp, or bare hex.
 * @returns Its first eight hex characters.
 */
export function shortFingerprint(fingerprint: string): string {
  const hex = fingerprint.includes(":") ? (fingerprint.split(":").pop() ?? "") : fingerprint;
  return hex.slice(0, SHOWN);
}

/**
 * The convention a node's `settings` states, in the words an actuary uses.
 *
 * `cumulative_survival` records its convention as `start_at`: a number means
 * the series opens at that value before any decrement has been applied, which
 * is beginning-of-period; `null` means it does not, which is end-of-period.
 * Anything spelled `timing` is already the convention's name and is shown as
 * the file spells it, with the underscores that make it an identifier taken
 * out. A settings block saying neither gets no words rather than a guess.
 *
 * It is a formatting rule and it lives with the formatting rules. The cone's
 * chip and the proof panel's convention line are the same sentence about the
 * same member, two of them would be two claims about one convention, and the
 * reader they would both have to read it from may not import React.
 *
 * @param settings - The node's `settings`, as the file carries it.
 * @returns The convention in words, or nothing where the file states none.
 */
export function settingsInWords(settings: Record<string, unknown> | undefined): string | undefined {
  if (settings === undefined) return undefined;
  const timing = settings["timing"];
  if (typeof timing === "string") return timing.replace(/_/g, " ");
  if (!("start_at" in settings)) return undefined;
  const startAt = settings["start_at"];
  if (startAt === null) return "end of period";
  if (typeof startAt === "number") return "beginning of period";
  return undefined;
}

/**
 * Where a double's own spelling turns to an exponent, as the producer's `repr` decides it.
 *
 * Written as the decimal point's position against the first significant digit:
 * `0.0001` has it at −3 and is written out, `0.00001` at −4 and is not;
 * `1e15` has it at 16 and is written out, `1e16` at 17 and is not. Those are
 * the two bounds Python's shortest `repr` takes, and the producer writes every
 * float in the file through it.
 */
const SPELLED_OUT = { above: -4, through: 16 } as const;

/**
 * One value exactly as the file holds it: every digit, in the file's own spelling.
 *
 * `formatValue` is for reading — two decimals, or six significant figures
 * below one — and says so on the page. This is the other answer, the one a
 * reader who selected a cell or copied it is asking for: the shortest decimal
 * that reads back as the very double the file carries, written the way the
 * producer wrote it. JavaScript and the producer agree on the digits (both
 * take the shortest that round-trips) and differ only in the notation around
 * them, so the digits are taken from `toExponential()` and set in the
 * producer's notation: `0.004081632653061224`, `12.0` for a whole float,
 * `1e-05` rather than `0.00001`, and `-0.0` for the negative zero a plain
 * `String` would write as `0`. So what is shown and copied is the token in the
 * document, character for character, and reads back as the value the results
 * file holds.
 *
 * An integer column's value is written as an integer, because the file wrote
 * it as one: `12`, not `12.0`. An integer past what a double carries is its
 * own digits (`reader/exact.ts`), or marked approximate where the engine
 * would not hand them over, exactly as `formatValue` marks it. A string — a
 * date, a code, a non-finite float the file spells as `"NaN"` — is itself.
 *
 * @param v - The value as the file carries it.
 * @param opts - `integer` when the node's `dtype` says the column holds whole numbers.
 * @returns The value's every digit, or null where the file holds no value.
 */
export function exactly(v: unknown, opts?: { integer?: boolean }): string | null {
  if (v === null || v === undefined) return null;
  if (isExactInteger(v)) {
    return v.digits ?? `${APPROXIMATELY}${String(v.rounded)}`;
  }
  if (typeof v === "string") return v;
  if (typeof v !== "number") return String(v);
  if (!Number.isFinite(v)) return Number.isNaN(v) ? "NaN" : v > 0 ? "Infinity" : "-Infinity";
  if (opts?.integer === true && Number.isInteger(v)) return Object.is(v, -0) ? "0" : String(v);
  const sign = v < 0 || Object.is(v, -0) ? "-" : "";
  if (v === 0) return `${sign}0.0`;
  const [mantissa = "", power = "0"] = Math.abs(v).toExponential().split("e");
  const digits = mantissa.replace(".", "");
  const point = Number(power) + 1;
  if (point <= SPELLED_OUT.above || point > SPELLED_OUT.through) {
    const exponent = point - 1;
    const magnitude = String(Math.abs(exponent)).padStart(2, "0");
    const lead = digits.length > 1 ? `${digits[0] ?? ""}.${digits.slice(1)}` : digits;
    return `${sign}${lead}e${exponent < 0 ? "-" : "+"}${magnitude}`;
  }
  if (point <= 0) return `${sign}0.${"0".repeat(-point)}${digits}`;
  if (point < digits.length) return `${sign}${digits.slice(0, point)}.${digits.slice(point)}`;
  return `${sign}${digits}${"0".repeat(point - digits.length)}.0`;
}

/**
 * What the file holds at one cell, every digit of it: a column at a period.
 *
 * The grid's cell and the drawer's line are the same value, so they are read
 * here once, by the rule the proof reads a value by: the selected policy's
 * sample, and that sample's entry at the period where it is a timeline.
 *
 * @param index - The file, indexed.
 * @param nodeId - The column's node.
 * @param period - The row.
 * @returns The value as `exactly` writes it, or null where the file holds none.
 */
export function cellExactly(index: Index, nodeId: string, period: number): string | null {
  const node = index.nodes.get(nodeId);
  if (node === undefined) return null;
  const sample = index.sampleOf(nodeId);
  const value = Array.isArray(sample) ? sample[period] : sample;
  return exactly(value, { integer: isIntegerDtype(node.dtype) });
}
