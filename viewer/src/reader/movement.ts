// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * How far each line moved over the whole book, as `gspio diff` measured it.
 *
 * The page derives what moved from the two documents, and the two documents
 * carry the values of one policy. Where `gspio diff` read the two runs' results
 * files it also measured every line over every policy both books hold, and
 * `--html` carries that measurement into the page as a block of its own: the
 * report's `values` member (§14.2). The page shows it **beside** the marks it
 * derives and never in place of them — a mark is still the page's own reading
 * of the two documents.
 *
 * **Two readings of one policy, held against each other.** The block names
 * the one policy the documents carry and says what moved for it, read from
 * the results files. The page reads the same policy from the documents. Where
 * the two disagree, that is a finding about one of them, and the page says so
 * rather than choosing — §12.5's discipline, applied to values.
 */

import type { Change } from "./compare";

/** One line's movement over the book, as `values.lines` writes it. */
export interface BookLine {
  node: string;
  before_node: string;
  paired_by: "id" | "rename" | "hint";
  /** What the change report says happened to the definition, or null where it held. */
  change: string | null;
  /** False where the line holds one value per period and the two timelines do not start together. */
  compared: boolean;
  moved: boolean;
  policies_compared: number;
  policies_moved: number;
  first_period_moved: number | null;
  max_relative: number | string | null;
  from_zero: boolean;
  worst: { policy: string | null; row: number; period: number | null; before: unknown; after: unknown } | null;
  /** Whether every move is inside §11.1.12's band; null where undecided or nothing moved. */
  within_band: boolean | null;
  /**
   * What the record says moved under a line whose definition did not: `book`,
   * `hole`, `producer` or `unexplained` (§14.2); null elsewhere.
   */
  cause: string | null;
  /**
   * On a line whose cause is `hole`, the holes it reads whose stamps moved;
   * null elsewhere, and absent from a block written before the member.
   */
  holes?: string[] | null;
}

/** The one policy the documents carry, as the results files read it. */
export interface Declared {
  policy: string;
  lines: { node: string; magnitude: number | string | null; from_zero: boolean; period: number | null }[];
}

/** The part of the report's `values` member the page reads. */
export interface BookMovement {
  rows: {
    matched_by: string;
    on: string[];
    paired: number;
    joined: { count: number; policies: string[] };
    left: { count: number; policies: string[] };
  };
  periods: { aligned: boolean; reason: string | null };
  cause: string;
  lines: BookLine[];
  declared: Declared | null;
}

/**
 * The block, parsed, or null where the page carries none or it is not one.
 *
 * Read defensively: the page must open whatever the block holds, and a block
 * it cannot read is a page without the book's reading rather than no page.
 *
 * @param text - The block's text, or null where the page carries none.
 * @returns The movement, or null.
 */
export function readMovement(text: string | null): BookMovement | null {
  if (text === null || text.trim() === "") return null;
  try {
    const parsed: unknown = JSON.parse(text);
    if (typeof parsed !== "object" || parsed === null) return null;
    const { lines, rows } = parsed as { lines?: unknown; rows?: unknown };
    if (!Array.isArray(lines) || typeof rows !== "object" || rows === null) return null;
    return parsed as BookMovement;
  } catch {
    return null;
  }
}

/** A relative move as the page writes one: three figures, as a percentage. */
function percent(ratio: number): string {
  return `${(ratio * 100).toPrecision(3)}%`;
}

/** Where a cell is, as a sentence names it. */
function where(line: BookLine): string {
  const worst = line.worst;
  if (worst === null) return "";
  const policy = worst.policy ?? `row ${String(worst.row)}`;
  return worst.period === null ? policy : `${policy}, period ${String(worst.period)}`;
}

/**
 * What one line did over the book, in one phrase.
 *
 * *moved in k of n policies* and how far at its worst, *under the hole h*
 * where a hole the line reads changed its stamp; *no number moved in n
 * policies* where the definition moved and every value held; *not compared*
 * where the two timelines do not start together.
 *
 * @param line - The line, as the block measured it.
 * @returns The phrase the changes list prints beside the entry.
 */
export function bookSaid(line: BookLine): string {
  if (!line.compared) return "not compared over the book: the timelines start apart";
  if (!line.moved) return `no number moved in ${String(line.policies_compared)} policies`;
  const under =
    line.cause === "hole" && Array.isArray(line.holes) && line.holes.length > 0
      ? ` under the hole ${line.holes.join(", ")}`
      : "";
  const moved = `moved${under} in ${String(line.policies_moved)} of ${String(line.policies_compared)} policies`;
  if (line.from_zero) return `${moved}, from 0 at ${where(line)}`;
  if (typeof line.max_relative === "number") {
    return `${moved}, worst ${percent(line.max_relative)} at ${where(line)}`;
  }
  return line.worst === null ? moved : `${moved}, first at ${where(line)}`;
}

/** Whether a line's definition moved and none of its numbers did. */
export function identityOnly(line: BookLine): boolean {
  return line.compared && !line.moved && line.change !== null;
}

/**
 * The commands that export both versions again at one policy, to open it here.
 *
 * Each version's own model file and book, as its document names them, with
 * `--policies id:` so a policy whose id looks like a range is reached; then
 * the comparison of the two. The paths are the documents' own, written against
 * each model's root.
 *
 * @param policy - The policy to drill into.
 * @param before - The earlier document's model file and book.
 * @param after - The later document's model file and book.
 * @returns The three command lines.
 */
export function drillIn(
  policy: string,
  before: { model: string | null; book: string | null },
  after: { model: string | null; book: string | null },
): string[] {
  const exported = (side: { model: string | null; book: string | null }, name: string): string =>
    `gspio calc-graph ${side.model ?? "model.py"} ${side.book ?? "book.parquet"} ` +
    `--policies id:${policy} -o ${name}.audit.json`;
  return [
    exported(before, "before"),
    exported(after, "after"),
    "gspio diff before.audit.json after.audit.json --html policy.html",
  ];
}

/** Two magnitudes read two ways: equal numbers, or both absent. */
function sameMagnitude(page: number | null, book: number | string | null): boolean {
  if (page === null || book === null) return page === null && book === null;
  return typeof book === "number" && page === book;
}

/**
 * The lines the page and the results files read differently for one policy.
 *
 * Over every line the block compared and paired by node id: whether it
 * moved, and where it did, how far — the largest relative move, whether it is
 * out of zero, and the period it is at.
 *
 * @param declared - The block's reading of the policy.
 * @param lines - Every line the block measured.
 * @param byNode - The page's own changes, by node.
 * @returns The nodes the two readings part on, in the block's order.
 */
export function disagreements(declared: Declared, lines: BookLine[], byNode: Map<string, Change>): string[] {
  const said = new Map(declared.lines.map((line) => [line.node, line]));
  const parted: string[] = [];
  for (const line of lines) {
    if (line.paired_by !== "id" || !line.compared) continue;
    const page = byNode.get(line.node);
    const pageMoved = page?.moved ?? false;
    const book = said.get(line.node);
    if (pageMoved !== (book !== undefined)) {
      parted.push(line.node);
      continue;
    }
    if (page === undefined || book === undefined) continue;
    const alike =
      sameMagnitude(page.magnitude, book.magnitude) &&
      page.fromZero === book.from_zero &&
      page.period === book.period;
    if (!alike) parted.push(line.node);
  }
  return parted;
}
