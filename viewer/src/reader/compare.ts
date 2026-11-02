// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * What moved between two artifacts of one model, derived here rather than read.
 *
 * The comparison lives in one page carrying both documents, and the
 * difference is derived **in the page**. Nothing about `gspio diff`'s report
 * travels with the two files — this module is a second implementation of the
 * definition `bindings/python/gaspatchio/frame/graph/diff.py` implements, and
 * the two are checked against each other over the same pair of fixtures. That
 * is §12.5's own discipline: one definition, two readings, and a disagreement
 * is a finding about one of them rather than something to reconcile.
 *
 * ## Three kinds of change, and the fields that tell them apart
 *
 * **The model changed.** Somebody edited a formula, added a column, stopped
 * computing one. It is exact: there is no magnitude in "this is not the
 * calculation it was".
 *
 * **The numbers changed.** The formula stands and its answer cannot be what it
 * was, because something under it moved — a basis re-sourced, an input edited
 * upstream. It is ranked, by how far it moved.
 *
 * **The book changed.** Nothing moved in the model at all — every fingerprint
 * this column carries is the fingerprint it carried — and the values are not
 * the values they were, because the run was over a different set of model
 * points. That third kind came later, and it exists because the page was
 * silent on the case it is most often opened for: an external review moved
 * one input amount from 100 to 150, and the page showed `before 200`,
 * `after 300` and an empty changes list. A reader told "nothing changed"
 * beside two different numbers has been told something false. The mark is
 * *data*, it is ranked with the numbers, and it is derived here — §14.2's
 * report has no such kind, because a report of definitions cannot have one.
 *
 * The field that separates them is §14.2's `change_origin`, and it is not the
 * same question as "did this node's digest move". **An assumption base's own
 * digest is inside the node that looks it up**, deliberately, because a lookup
 * against a different table is a different calculation — so re-sourcing a
 * mortality basis moves the local fingerprint of every node that reads it.
 * Marking those as edits would tell a committee the model changed in a quarter
 * when nobody touched it, which is exactly what §14.2 refuses to say. So a
 * node's own digest moving is a model change only where the data does not
 * account for it, and that rule is reproduced here from the same evidence the
 * report reads: the formula text, the reads, the assumption names and which
 * bases moved.
 *
 * ## The magnitude, and the one case that is never divided
 *
 * `|after − before| / |before|`, at the period where it is largest. A `before`
 * of zero is stated as *from 0* and never divided: a ratio against nothing is
 * not a bigger number, it is not a number. Those entries sort above every
 * finite ratio, because arriving from nothing is the largest relative move
 * there is, and the page says which they are rather than printing an infinity.
 *
 * **There is no tolerance.** A value has changed when it is unequal, and the
 * reader sets the floor. A tolerance in here would be a number
 * somebody has to defend, applied to every model the page ever opens.
 *
 * **Equality is exact even where the ratio cannot be.** An integer the file
 * spells past what a double carries arrives as its own digits
 * (`reader/exact.ts`), and "did this value move" is answered on those digits.
 * The *magnitude* is a quotient and is taken on the doubles, which loses
 * nothing: a ratio has no exact decimal, and the two figures the page prints
 * either side of it are still the file's.
 *
 * ## A hole whose stamp moved, and the model's own files
 *
 * A column the model's setup joined from a file in plain Polars is a hole that
 * carries a stamp of what it held, and an edit to that file moves no node's
 * digest. `bases` carries §14.2's `hole` entry for it, and each line marked
 * *data* that reads the hole — is it, or reads it through what it reads —
 * names it in `holes`, which is the cause the record states for that line, as
 * `gspio diff` gives it `cause: "hole"`. The model file's own digest, and each
 * helper module's (`model.modules`), are `source`: stated beside the list and
 * never counted, as the report states them.
 *
 * ## The results file, which marks no column
 *
 * Where both documents record the results file their run wrote and the two
 * differ, `bases` carries §14.2's `results` entry, last. Where only one of them
 * records one, `resultsNote` says the two were not compared. Neither marks a
 * column: a file's digest moves with the writer as well as with the numbers,
 * so it says the file moved and nothing about which number did.
 */

import { approximately, comparedAs } from "./exact";
import { isIntegerDtype } from "./format";
import { buildIndex } from "./index";
import type { Index } from "./index";
import { disagreements } from "./movement";
import type { BookLine, BookMovement } from "./movement";
import { axisOf } from "./policies";
import type { Artifact, ArtifactNode, Policy } from "./types";

/** Which of the three kinds of change one entry is. */
export type ChangeMark = "model" | "numbers" | "data";

/**
 * What the record says about a column whose values moved under definitions that did not.
 *
 * The *data* mark is an observation — every digest the column carries held, and
 * its numbers did not — and its cause is a second claim, made only where the
 * record makes it. **Only the book can be a cause here.** An assumption base's
 * digest is inside every fingerprint that reads it, so a re-sourced base moves
 * those fingerprints and their lines are marked *numbers*, never *data*.
 *
 * - `book`: §14.2's report carries a `model_points` entry with both digests and
 *   no `reason` — the two books differ.
 * - `uncompared`: it carries one with a `reason`, and the two books could not
 *   be compared.
 * - `unnamed`: neither document names the policy its values were read from, so
 *   the two may have sampled two rows of the book.
 * - `producer`: the two documents name different producers, or one producer on
 *   two libraries. A release can move a computed value with no definition
 *   moving, and so can the library under one release — another Polars, another
 *   build of the extension — which `producer.versions` states. The record holds
 *   either as a candidate, and the page does not claim it as the cause. A
 *   library one side withholds or does not state is not a move the record
 *   shows, as `gspio diff` prints no library line for that pair.
 * - `unexplained`: none of those, so nothing in the record explains the move,
 *   and the page says so and names the check that finds the line.
 *
 * A line whose values moved by no more than §11.1.12 allows is none of these:
 * see `Change.agrees`.
 */
export type DataCause = "book" | "uncompared" | "unnamed" | "producer" | "unexplained";

/** What happened to one node — §14.2's own vocabulary, spelled its way. */
export type ChangeKind = "added" | "removed" | "changed" | "renamed";

/** Which of the two moved, on a node both documents hold. §14.2's `change_origin`. */
export type ChangeOrigin = "self" | "inherited";

/** What a node's `provenance` says when the column was handed over whole rather than computed. */
const HANDED_OVER = new Set(["injected", "continuation"]);

/** What the frame writes on a node it minted for a name-move. */
const RENAME = "rename";

/** The assumption kinds a node's `reads_assumptions` can name. */
const ASSUMPTION_KINDS = new Set(["table", "schedule", "curve"]);

/** How far the values moved, and where. */
export interface Movement {
  /** Whether any sampled value is unequal: what a change is here, with no tolerance in it. */
  moved: boolean;
  /** The largest `|after − before| / |before|`, or null where none could be taken. */
  magnitude: number | null;
  /** The period that magnitude was measured at, or null on a column holding one value. */
  period: number | null;
  /** Whether the move this entry is ranked by is out of a `before` of zero. */
  fromZero: boolean;
}

/** One thing that moved, and everything the list needs to rank and print it. */
export interface Change extends Movement {
  /** The node id — the later document's, and the earlier one's for a departure. */
  node: string;
  /** The column it defines, or its id where it defines none. */
  column: string;
  mark: ChangeMark;
  kind: ChangeKind;
  /**
   * §14.2's `change_origin`, or null where the report states none.
   *
   * Null on a node only one document holds, because the question is about a
   * pair — and null on a *data* entry, because the report has no such kind at
   * all: nothing in the definitions moved, so there is no origin for the
   * change to have.
   */
  origin: ChangeOrigin | null;
  /** The node a recorded name-move came from, on a `renamed` entry and nowhere else. */
  renamedFrom: string | null;
  /**
   * Whether the two samples agree under §11.1.12's rule, on a *data* entry, and
   * false on every other. Such a line moved, and no more than two runs of one
   * model are allowed to — the tolerance `gspio compare` applies — so it is not
   * a move the record has to explain.
   */
  agrees: boolean;
  /**
   * On a *data* entry, the holes it reads whose stamps moved — itself, or
   * through the lines it reads — by column, in the later document's order;
   * empty on every other entry. Non-empty is §14.2's `cause: "hole"`: the
   * record names what moved under the line, so it owes no note.
   */
  holes: string[];
}

/**
 * One base, data set or handed-over column that moved underneath the model, or
 * the results file the run wrote.
 */
export interface BaseChange {
  kind: "table" | "schedule" | "curve" | "model_points" | "hole" | "injection" | "results";
  /**
   * What it is called, or null where the thing has no name of its own. Policy
   * data and a results file are named by the path their run recorded.
   */
  name: string | null;
  before: string | null;
  after: string | null;
  /**
   * Why the two could not be compared, on an entry that says so; null on
   * every entry that reports a movement. The policy data and a hole stamped
   * on one side only carry one: `diff_artifacts`'s `reason`, written in the
   * same words (§14.2).
   */
  reason: string | null;
}

/** The whole comparison: two documents, and what moved between them. */
export interface Comparison {
  /** The later document, indexed at the entry the reader is standing on. */
  after: Index;
  /** The earlier document, indexed at the entry that answers to the same policy. */
  before: Index;
  /** Every change, ranked. Model changes first, then the numbers by how far they moved. */
  changes: Change[];
  /** The same entries by node id, for the grid and the cone to ask one at a time. */
  byNode: Map<string, Change>;
  /** What moved underneath the model — §14.2's `data`, derived the same way. */
  bases: BaseChange[];
  /**
   * The sentence for a policy axis the two documents do not share, or null.
   *
   * Where the entry the reader is standing on has no answering entry in the
   * earlier document, the model comparison still holds — fingerprints are not
   * a function of which policy was sampled — and no value comparison does.
   * The page says so rather than comparing one policy's numbers with another's.
   */
  policyNote: string | null;
  /**
   * The sentence for a results file only one of the two runs recorded, or null.
   *
   * No entry is written for it, because there is nothing to hold the other
   * side against; the page says so, in the line `gspio diff` prints, so that
   * an empty list is not read as "the same results".
   */
  resultsNote: string | null;
  /**
   * The sentence written beside a results entry: the step that works for
   * these two runs, chosen as `gspio diff` chooses it (`resultsFileMoved`).
   */
  resultsMoved: string;
  /** What the record says moved under the columns marked *data*. */
  dataCause: DataCause;
  /**
   * The sentence for columns marked *data* that nothing in the record explains,
   * or null: it names the check that finds the line, and is written only where
   * such a column is in the list.
   */
  dataNote: string | null;
  /**
   * How far each line moved over the whole book, where `gspio diff` read the
   * two runs' results files and wrote its measurement into the page; null
   * where it did not. Shown beside the marks, never instead of them.
   */
  book: BookMovement | null;
  /** The book's lines by node, for the list to read one entry at a time. */
  bookByNode: Map<string, BookLine>;
  /**
   * The sentence for the policy the page reads differently from the results
   * files, or null where the two readings agree or cannot both be taken.
   */
  crossCheck: string | null;
  /** Each version's model file and book, as its document names them, to export it again. */
  sides: { before: RunFiles; after: RunFiles };
  /**
   * The model's own files, where the model file or a helper module moved:
   * §14.2's `source`. Stated, never counted — `moved` does not read it — so a
   * comment in a helper shows without the page saying the model changed.
   */
  source: SourceMoved | null;
}

/** One helper module whose bytes moved: §14.2's `source.modules` entry. */
export interface ModuleMoved {
  /** The later document's path for it, or the earlier one's where only that lists it. */
  path: string;
  /** The earlier run's fingerprint, or null where it did not list it or could not read it. */
  before: string | null;
  after: string | null;
}

/** §14.2's `source`: the model file's two digests and the helper modules that moved. */
export interface SourceMoved {
  path: string | null;
  /** The earlier run's `source_sha`; equal to `after` where only a helper moved. */
  before: string | null;
  after: string | null;
  modules: ModuleMoved[];
}

/** A run's model file and book, as its document names them. */
export interface RunFiles {
  model: string | null;
  book: string | null;
}

/** The model file and the book one document names. */
function runFiles(artifact: Artifact): RunFiles {
  return { model: artifact.model.source_path, book: artifact.model.model_points?.path ?? null };
}

/** Whether this comparison found anything at all. */
export function moved(comparison: Comparison): boolean {
  return comparison.changes.length > 0 || comparison.bases.length > 0;
}

/**
 * The sentence for two documents this page will not compare, or null.
 *
 * **The page refuses what `gspio diff` refuses, and nothing else**, because
 * the page and the change report are two readings of one comparison and a
 * page that refused a pair the report compares would be the two disagreeing
 * at the first question. `gspio diff` refuses one pair and only one (§14.2):
 * digests taken under two fingerprint algorithms, between which there is no
 * translation.
 *
 * It does not refuse two documents whose `model.source_path` differs, and
 * neither does this page. That path is written relative to the model's root
 * — the model file's directory, or the repository's root where `git` is set
 * (§7) — so it moves when last quarter's model is copied into a new folder of
 * one repository, which is the comparison the page exists for, and it holds
 * when two unrelated models each sit at their own root as `model.py`. A path
 * is not an identity, and the graph fingerprint is not one either: it moves on
 * every edit. Two different models compared here read as what the report says
 * they are — lines added, removed and changed — on the page and in the report
 * alike.
 *
 * @param after - The later document.
 * @param before - The earlier document.
 * @returns The one sentence, or null where the two can be compared.
 */
export function refusedComparison(after: Artifact, before: Artifact): string | null {
  if (after.fingerprint_algorithm !== before.fingerprint_algorithm) {
    return (
      `These two artifacts cannot be compared: their digests were taken under ` +
      `${before.fingerprint_algorithm} and ${after.fingerprint_algorithm}, and a digest under ` +
      `one says nothing about a digest under the other. Re-export both models under one ` +
      `fingerprint algorithm and compare those.`
    );
  }
  return null;
}

/**
 * Compare two documents, along one entry of the later one's policy axis.
 *
 * @param after - The later document, which every view is drawn from.
 * @param before - The earlier document.
 * @param at - Which entry of the later document's axis the reader is standing on.
 * @returns The comparison, ranked.
 */
export function compare(
  after: Artifact,
  before: Artifact,
  at = 0,
  book: BookMovement | null = null,
): Comparison {
  const later = buildIndex(after, at);
  const found = locateEntry(axisOf(before), later.policy);
  const answering = typeof found === "number" ? found : null;
  const earlier = buildIndex(before, answering ?? 0);

  const bases = baseChanges(before, after);
  const reSourced = new Set(
    bases
      .filter(
        (base) =>
          ASSUMPTION_KINDS.has(base.kind) &&
          base.name !== null &&
          base.before !== null &&
          base.after !== null,
      )
      .map((base) => base.name),
  );

  const comparable = later.policy === null || answering !== null;
  const dataCause = causeOfData(before, after, bases, later.policy);
  // The book outranks a hole, as it does in `gspio diff`: it moves every line.
  const holes = dataCause === "book" ? new Map<string, string[]>() : holesRead(later, movedHoles(bases));
  const changes = ranked(
    calculationChanges(earlier, later, reSourced, holes, comparable ? undefined : "no values"),
  );
  // A note is owed only where a line moved further than §11.1.12 allows and
  // the record names nothing under it: a line that agrees within the rule, or
  // reads a hole whose stamp moved, is not a move the record leaves unexplained.
  const unaccounted = changes.some(
    (change) => change.mark === "data" && !change.agrees && change.holes.length === 0,
  );
  const byNode = new Map(changes.map((change) => [change.node, change]));

  return {
    after: later,
    before: earlier,
    changes,
    byNode,
    bases,
    policyNote: comparable ? null : policySentence(later.policy, found === "ambiguous"),
    resultsNote: resultsNotCompared(before, after),
    resultsMoved: book === null ? resultsFileMoved(before, after) : RESULTS_READ,
    dataCause,
    dataNote: unaccounted ? dataNoteFor(dataCause, before, after) : null,
    book,
    bookByNode: new Map((book?.lines ?? []).map((line) => [line.node, line])),
    crossCheck: comparable ? crossChecked(book, later.policy, byNode) : null,
    sides: { before: runFiles(before), after: runFiles(after) },
    source: sourceMoved(before, after),
  };
}

/**
 * The sentence for the one policy the page and the results files read apart, or null.
 *
 * Taken only on the policy the block names, and only where the reader is
 * standing on it: the page holds one policy's values at a time, and any other
 * entry has nothing in the block to be held against.
 */
function crossChecked(
  book: BookMovement | null,
  entry: Policy | null,
  byNode: Map<string, Change>,
): string | null {
  const declared = book?.declared ?? null;
  if (book === null || declared === null || entry === null) return null;
  if (entry.policy_id !== declared.policy || entry.aggregation !== null || entry.filter !== null) {
    return null;
  }
  const parted = disagreements(declared, book.lines, byNode);
  if (parted.length === 0) return null;
  return (
    `This page and gspio diff read policy ${declared.policy} differently on ` +
    `${parted.join(", ")}: the page from the two documents' own values, the report from ` +
    "the two results files. Two readings of one definition that disagree are a finding " +
    "about one of them, so neither is preferred here."
  );
}

/**
 * The check that finds a line written past the record.
 *
 * A second engine recomputes every line from the audit file's own formulas,
 * so a column rewritten after the frame recorded it disagrees there, and
 * `gspio compare` names it; a release's arithmetic agrees there, within the
 * rule both apply.
 */
const RECOMPUTE =
  "To find a line whose own operands do not give its result, recompute the model from its " +
  "audit file on a second engine with gspio run-artifact … --every-node, and compare that " +
  "with the model's own run, also written with --every-node, using gspio compare.";

/**
 * The sentence over the lines marked *data* that the rule does not account for, or null.
 *
 * Where the book moved or could not be compared, the bases underneath the list
 * already say so, and nothing is added here.
 *
 * @param cause - What the record says moved under those lines.
 * @param before - The earlier document.
 * @param after - The later document.
 * @returns The sentence, or null where the bases say it.
 */
function dataNoteFor(cause: DataCause, before: Artifact, after: Artifact): string | null {
  switch (cause) {
    case "book":
    case "uncompared":
      return null;
    case "unnamed":
      return (
        "Neither document names the policy its values were read from, so the moves marked " +
        "data may be two different rows of the book rather than one policy moving."
      );
    case "producer": {
      // Name what moved. Where the release did, the sentence is about the
      // release, with the library beside it where that moved too; where only
      // the library did, it is about the library, in `gspio diff`'s own words,
      // and never one release printed as though it had changed into itself.
      const library = libraryMoved(before, after);
      const was = producerSaid(before);
      const now = producerSaid(after);
      const what =
        was === now
          ? `The library changed between the runs (${library ?? "library: not stated"}), and a ` +
            "new library can move"
          : `The producer changed between the runs, from ${was} to ${now}` +
            `${library === null ? "" : ` (${library})`}, and a new release can move`;
      return (
        `${what} a computed value with no definition moving: that may explain the moves ` +
        `marked data, and the record does not say that it does. ${RECOMPUTE}`
      );
    }
    case "unexplained":
      return (
        "Nothing in the record explains the moves marked data beyond the specification's " +
        "tolerance: those lines' fingerprints, the book and the producer are the ones they " +
        `were. ${RECOMPUTE}`
      );
  }
}

/** `gspio diff`'s word for each library key it names a move in, in its order. */
const LIBRARY_WORDS: [string, string][] = [
  ["core_version", "core"],
  ["extension_version", "extension"],
  ["polars_version", "polars"],
  ["python_version", "python"],
  ["platform", "platform"],
];

/** The library a document states produced it, or null where it states none. */
function libraryOf(artifact: Artifact): Record<string, unknown> | null {
  const producer: unknown = artifact.producer;
  if (typeof producer !== "object" || producer === null) return null;
  const versions = (producer as { versions?: unknown }).versions;
  if (typeof versions !== "object" || versions === null || "omitted" in versions) return null;
  return versions as Record<string, unknown>;
}

/** The installed distributions a library says the model imports. */
function importsOf(library: Record<string, unknown>): Record<string, string> {
  const imports = library["imports"];
  if (typeof imports !== "object" || imports === null) return {};
  return Object.fromEntries(
    Object.entries(imports as Record<string, unknown>).map(([name, version]) => [name, String(version)]),
  );
}

/**
 * The line `gspio diff` prints where the library moved between two documents, or null.
 *
 * `diff._library_moved`, word for word: each named key that differs as
 * `word was → now`, "extension sha differs" where the digests do, and each
 * imported distribution that moved, by name. Null where either document
 * withholds its versions or states none — the record then shows no move —
 * and where the two state the same library.
 *
 * @param before - The earlier document.
 * @param after - The later document.
 * @returns `library: …`, or null.
 */
export function libraryMoved(before: Artifact, after: Artifact): string | null {
  const was = libraryOf(before);
  const now = libraryOf(after);
  if (was === null || now === null) return null;
  const said = (value: unknown): string => (value === undefined ? "-" : String(value));
  const moved = LIBRARY_WORDS.filter(([key]) => was[key] !== now[key]).map(
    ([key, word]) => `${word} ${said(was[key])} → ${said(now[key])}`,
  );
  if (was["extension_sha256"] !== now["extension_sha256"]) moved.push("extension sha differs");
  const wasImports = importsOf(was);
  const nowImports = importsOf(now);
  // Sorted as Python sorts strings, by code point, which is what diff does.
  const names = [...new Set([...Object.keys(wasImports), ...Object.keys(nowImports)])].sort((a, b) =>
    a < b ? -1 : a > b ? 1 : 0,
  );
  for (const name of names) {
    if (wasImports[name] !== nowImports[name]) {
      moved.push(`${name} ${said(wasImports[name])} → ${said(nowImports[name])}`);
    }
  }
  return moved.length === 0 ? null : `library: ${moved.join("; ")}`;
}

/** A document's producer by its name and version, the way `diff_artifacts` names it. */
function producerSaid(artifact: Artifact): string {
  const producer: unknown = artifact.producer;
  if (typeof producer === "object" && producer !== null) {
    const { name, version } = producer as { name?: unknown; version?: unknown };
    const said = [name, version].filter((part): part is string => typeof part === "string").join(" ");
    if (said !== "") return said;
  }
  return "a producer it does not name";
}

/**
 * What the record says moved under the columns whose values moved and whose definitions did not.
 *
 * See {@link DataCause}. The bases are §14.2's `data`, so the book is read
 * exactly as `gspio diff` reads it; an assumption or injection entry moves the
 * fingerprints that read it and explains no *data* line, and a results file is
 * what the run wrote, which explains none of its own numbers.
 *
 * @param before - The earlier document.
 * @param after - The later document.
 * @param bases - What moved underneath the model between the two.
 * @param entry - The entry of the later document's axis the reader is standing on.
 * @returns The cause the record supports, or that it supports none.
 */
function causeOfData(before: Artifact, after: Artifact, bases: BaseChange[], entry: Policy | null): DataCause {
  const book = bases.find((base) => base.kind === "model_points");
  if (book !== undefined && book.reason === null && book.before !== null && book.after !== null) {
    return "book";
  }
  if (book !== undefined && book.reason !== null) return "uncompared";
  if (entry === null || (entry.policy_id === null && entry.aggregation === null)) return "unnamed";
  if (producerSaid(before) !== producerSaid(after)) return "producer";
  if (libraryMoved(before, after) !== null) return "producer";
  return "unexplained";
}

/** How a policy entry is named in a sentence about it. */
function named(entry: Policy | null): string {
  if (entry === null) return "this entry";
  return entry.policy_id ?? entry.aggregation ?? "this entry";
}

/**
 * The sentence for an entry the earlier document does not answer to.
 *
 * Two reasons and two sentences, because they call for different moves. The
 * earlier file may carry no such entry at all — nothing to do about that but
 * say so. Or it may carry **more than one**, which is the scenario case: a
 * cross-joined export has policy 1 under BASE, UP and DOWN, and if the entry
 * in front of the reader does not say which cut it is in, then neither can
 * this. Picking the first would put one scenario's proof beside another's
 * without an admission, which is what an external review found it doing.
 */
function policySentence(entry: Policy | null, ambiguous: boolean): string {
  if (ambiguous) {
    return (
      `The earlier artifact carries more than one entry answering to ${named(entry)}, and ` +
      `nothing on this entry says which of them it is, so what moved in the model is shown ` +
      `and no number is compared.`
    );
  }
  return (
    `The earlier artifact carries no values for ${named(entry)}, so what moved in the model is ` +
    `shown and no number is compared.`
  );
}

/**
 * What the earlier axis has to say about the entry the reader is standing on.
 *
 * **An entry's identity is `policy_id`, `aggregation` and `filter`**, as the
 * file writes all three. The `filter` is on the entry for exactly this reason: a
 * cross-joined scenario run gives one policy one row per scenario, and every
 * entry states its own cut. Matching on the id and the fold alone made policy
 * 1 under `UP` answer to policy 1 under `BASE` — the file carried the
 * distinction and the reader dropped it.
 *
 * Position is never used either: an export selecting `:2` and one selecting
 * `3,7` put different policies at index 0, and comparing by position would put
 * one policy's numbers under another's name.
 *
 * A match that is still ambiguous is **refused**, not resolved to the first.
 * The changes list says so in its own words and the model comparison still
 * stands, because a fingerprint is not a function of which policy was sampled.
 *
 * @param axis - The earlier document's axis.
 * @param entry - The entry the later document is being read at.
 * @returns Its position on that axis; `"absent"` where the earlier document
 *   has no such entry, `"ambiguous"` where it has more than one.
 */
export function locateEntry(axis: Policy[], entry: Policy | null): number | "absent" | "ambiguous" {
  if (entry === null) return "absent";
  // A fold of the book has no id to be matched on: §7.4 writes `policy_id`
  // null on one, and its own cut is what separates one fold from another.
  const folded = entry.policy_id === null && entry.aggregation !== null;
  const answering: number[] = [];
  for (const [at, other] of axis.entries()) {
    if (other.aggregation !== entry.aggregation) continue;
    if (other.filter !== entry.filter) continue;
    if (!folded && other.policy_id !== entry.policy_id) continue;
    answering.push(at);
  }
  if (answering.length === 0) return "absent";
  if (answering.length > 1) return "ambiguous";
  return answering[0]!;
}

/**
 * The one entry of the earlier axis that answers, or null.
 *
 * `locateEntry` narrowed for a caller that only wants the position — the two
 * ways of having no answer are one answer here. The page itself uses
 * `locateEntry`, because the sentence it prints differs between them.
 *
 * @param axis - The earlier document's axis.
 * @param entry - The entry the later document is being read at.
 * @returns Its position, or null where no single entry answers to it.
 */
export function matchingEntry(axis: Policy[], entry: Policy | null): number | null {
  const found = locateEntry(axis, entry);
  return typeof found === "number" ? found : null;
}

/** The name a change is listed under: the column, or the id where there is none. */
function columnOf(node: ArtifactNode): string {
  return node.column ?? node.id;
}

/**
 * Every node the two documents do not hold identically, classified.
 *
 * The later document's own order first — which is the order the model was
 * written in — then whatever the earlier one held and this one does not.
 *
 * **One pass, at load, over every column**, for the *data* mark. A node
 * whose digests both held is not skipped any more: its sampled values are
 * compared here, and a column whose numbers moved under an unmoved fingerprint
 * is a *data* entry. The cost of that mark is this loop — about 128
 * columns by 83 periods on level 4 — and it is paid once when the page opens,
 * never on a scrub: `shell/App.tsx` memoises the comparison on the two
 * documents and the axis position, and a period step moves none of the three.
 */
function calculationChanges(
  earlier: Index,
  later: Index,
  reSourced: Set<string | null>,
  holes: Map<string, string[]>,
  withoutValues?: "no values",
): Change[] {
  const found: Change[] = [];

  for (const id of later.order) {
    const now = later.nodes.get(id);
    if (now === undefined) continue;
    const was = earlier.nodes.get(id);
    if (was === undefined) {
      const from = nameMoveSource(now);
      found.push({
        node: id,
        column: columnOf(now),
        mark: "model",
        kind: from !== null && earlier.nodes.has(from) ? "renamed" : "added",
        origin: null,
        renamedFrom: from !== null && earlier.nodes.has(from) ? from : null,
        agrees: false,
        holes: [],
        ...stillness(),
      });
      continue;
    }
    const localMoved = was.local_fingerprint !== now.local_fingerprint;
    const merkleMoved = was.fingerprint !== now.fingerprint;
    if (!localMoved && !merkleMoved) {
      // Every digest this column carries is the digest it carried, so nothing
      // about the calculation moved. If its values moved anyway, that is a
      // change this list owes the reader — and what, if anything, the record
      // says moved under it is the comparison's `dataCause`.
      if (withoutValues !== undefined) continue;
      const movement = movementOf(earlier.sampleOf(id), later.sampleOf(id));
      if (!movement.moved) continue;
      found.push({
        node: id,
        column: columnOf(now),
        mark: "data",
        kind: "changed",
        origin: null,
        renamedFrom: null,
        agrees: agreesUnderTheRule(earlier, later, now),
        holes: holes.get(id) ?? [],
        ...movement,
      });
      continue;
    }
    const inherited = !localMoved || dataAccountsForIt(was, now, reSourced);
    found.push({
      node: id,
      column: columnOf(now),
      mark: inherited ? "numbers" : "model",
      kind: "changed",
      origin: inherited ? "inherited" : "self",
      renamedFrom: null,
      agrees: false,
      holes: [],
      ...(withoutValues === undefined
        ? movementOf(earlier.sampleOf(id), later.sampleOf(id))
        : stillness()),
    });
  }

  for (const id of earlier.order) {
    if (later.nodes.has(id)) continue;
    const was = earlier.nodes.get(id);
    if (was === undefined) continue;
    found.push({
      node: id,
      column: columnOf(was),
      mark: "model",
      kind: "removed",
      origin: null,
      renamedFrom: null,
      agrees: false,
      holes: [],
      ...stillness(),
    });
  }

  return found;
}

/** No movement measured, because there was no pair of values to measure one over. */
function stillness(): Movement {
  return { moved: false, magnitude: null, period: null, fromZero: false };
}

/**
 * §11.1.12's agreement rule: the tolerance two runs of one model are held to,
 * and the one `gspio compare` applies. Two finite results agree when
 * `|a − b| ≤ 1e-12 · scale`.
 */
const AGREEMENT = 1e-12;

/**
 * Whether one line's two samples agree under §11.1.12's rule, read on the values the page holds.
 *
 * The scale is the line's: the largest magnitude among the node's own values
 * and the values of every node its `reads` names, over the policy's whole
 * timeline, taken over both documents — and the page holds one policy at a
 * time, so it is that policy's. A line whose scale is 0 is compared exactly,
 * and so is everything the rule compares exactly: an integer, a word, a date,
 * where the nulls are, and the length of every run. The sign of a zero is not
 * compared.
 *
 * @param earlier - The earlier document, at the entry that answers.
 * @param later - The later document, at the entry the reader stands on.
 * @param node - The line, as the later document records it.
 * @returns Whether every value agrees within the rule.
 */
function agreesUnderTheRule(earlier: Index, later: Index, node: ArtifactNode): boolean {
  let scale = 0;
  const measure = (sample: unknown): void => {
    if (Array.isArray(sample)) {
      for (const value of sample) measure(value);
      return;
    }
    const value = approximately(sample);
    if (value !== null && Number.isFinite(value)) scale = Math.max(scale, Math.abs(value));
  };
  for (const id of [node.id, ...node.reads]) {
    measure(earlier.sampleOf(id));
    measure(later.sampleOf(id));
  }
  return agreesWithin(earlier.sampleOf(node.id), later.sampleOf(node.id), AGREEMENT * scale, isIntegerDtype(node.dtype));
}

/** Whether two samples agree, exactly where the rule is exact and within `allowed` elsewhere. */
function agreesWithin(before: unknown, after: unknown, allowed: number, integer: boolean): boolean {
  if (Array.isArray(before) || Array.isArray(after)) {
    if (!Array.isArray(before) || !Array.isArray(after) || before.length !== after.length) return false;
    return before.every((value, at) => agreesWithin(value, after[at], allowed, integer));
  }
  if (comparedAs(before) === comparedAs(after)) return true;
  if (integer) return false;
  const was = approximately(before);
  const now = approximately(after);
  if (was === null || now === null || !Number.isFinite(was) || !Number.isFinite(now)) return false;
  return Math.abs(now - was) <= allowed;
}

/**
 * Whether a node's own digest moved because the data under it moved.
 *
 * `diff.py`'s `_the_data_accounts_for_it`, over the same evidence. A column
 * handed over whole has no formula at all — its identity is its contents — so
 * nothing else can have moved. A computed node qualifies where it is the
 * calculation it was, in the text it was written in, reading what it read, and
 * one of the bases it names has been re-sourced.
 */
function dataAccountsForIt(
  was: ArtifactNode,
  now: ArtifactNode,
  reSourced: Set<string | null>,
): boolean {
  if (HANDED_OVER.has(was.provenance ?? "") && HANDED_OVER.has(now.provenance ?? "")) return true;
  const names = now.reads_assumptions;
  if (!same(names, was.reads_assumptions)) return false;
  if (!names.some((name) => reSourced.has(name))) return false;
  return was.formula === now.formula && same(was.reads, now.reads);
}

/** The node a recorded name-move came from, where the framework recorded one. */
function nameMoveSource(node: ArtifactNode): string | null {
  if (node.provenance !== RENAME) return null;
  return node.reads.length === 1 ? (node.reads[0] ?? null) : null;
}

/** Two string lists holding the same names in the same order. */
function same(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((name, at) => name === b[at]);
}

/**
 * How far one column's sampled values moved.
 *
 * A column holding one value per policy is one comparison and has no period. A
 * per-period column is compared period by period and reports the largest move;
 * where the two timelines are different lengths, the periods they share are
 * compared and the difference in length is itself a move.
 *
 * A pair that is not two finite numbers — a string, a null, a value on one
 * side and nothing on the other — is unequal or it is not, and never carries a
 * magnitude: there is no ratio between a number and a word.
 *
 * **An integer too wide for a double is compared on its digits and ranked on
 * the double it rounds to.** Equality is the question the page answers with "a
 * value has changed when it is unequal", and on such a value the digits are
 * the only honest answer to it. The magnitude is `|after − before| / |before|`,
 * which has no exact decimal at any width, so taking it on the doubles loses
 * nothing that was ever there — and the two figures the page prints either
 * side of the ratio are still the ones the file spelled.
 */
export function movementOf(before: unknown, after: unknown): Movement {
  if (Array.isArray(before) || Array.isArray(after)) {
    const was = Array.isArray(before) ? before : [];
    const now = Array.isArray(after) ? after : [];
    let out: Movement = { moved: was.length !== now.length, magnitude: null, period: null, fromZero: false };
    for (let at = 0; at < Math.max(was.length, now.length); at += 1) {
      const step = movementOf(was[at], now[at]);
      if (!step.moved) continue;
      out = larger(out, { ...step, period: at });
    }
    return out;
  }
  if (comparedAs(before) === comparedAs(after)) return stillness();
  const was = approximately(before);
  const now = approximately(after);
  if (was === null || now === null) {
    return { moved: true, magnitude: null, period: null, fromZero: false };
  }
  if (!Number.isFinite(was) || !Number.isFinite(now)) {
    return { moved: true, magnitude: null, period: null, fromZero: false };
  }
  if (was === 0) return { moved: true, magnitude: null, period: null, fromZero: true };
  return {
    moved: true,
    magnitude: Math.abs(now - was) / Math.abs(was),
    period: null,
    fromZero: false,
  };
}

/**
 * The larger of two moves, under the order the changes list is ranked in.
 *
 * A move out of zero beats every finite ratio, because a ratio against nothing
 * is not a number and arriving from nothing is the largest relative move
 * there is. Among finite ratios the larger wins; a move with no ratio at all —
 * a word for a number — stands only where nothing measurable moved.
 */
function larger(a: Movement, b: Movement): Movement {
  if (!a.moved) return b;
  if (!b.moved) return a;
  if (a.fromZero !== b.fromZero) return a.fromZero ? a : b;
  if (a.magnitude === null) return b.magnitude === null ? a : b;
  if (b.magnitude === null) return a;
  const keep = b.magnitude > a.magnitude ? b : a;
  return { ...keep, moved: true };
}

/**
 * The changes, in the order the list prints them.
 *
 * Model changes first, in the later document's own order, which is the order
 * the model was written in — they are exact, there is no magnitude to rank
 * them by, and they are usually why the rest of the list moved. Then
 * everything that has a magnitude, by how far it moved: the moves out of zero,
 * then the finite ratios largest first, then whatever moved in a way no ratio
 * describes, then the nodes the digests say moved and this policy's numbers
 * did not.
 *
 * **The numbers and the data are ranked together**, which is the second
 * addendum's own word — *ranked by relative magnitude with the rest*. They
 * answer different questions about one column and neither is the larger kind
 * of change; separating them into two blocks would make the order a statement
 * about which sort of change matters more, and the page does not have one.
 */
function ranked(changes: Change[]): Change[] {
  const rank = (change: Change): number => {
    if (!change.moved) return 3;
    if (change.fromZero) return 0;
    return change.magnitude === null ? 2 : 1;
  };
  const model = changes.filter((change) => change.mark === "model");
  const measured = changes
    .filter((change) => change.mark !== "model")
    .sort((a, b) => {
      const order = rank(a) - rank(b);
      if (order !== 0) return order;
      return (b.magnitude ?? 0) - (a.magnitude ?? 0);
    });
  return [...model, ...measured];
}

// --- what moved underneath the model ----------------------------------------

/**
 * Every base, data set, handed-over column and results file that moved.
 *
 * `diff.py`'s `_data_changes`, in the order a reviewer asks about them: the
 * assumption bases the model rests on, then the policy data it was run over,
 * then the holes its setup filled from elsewhere, then the columns of values
 * it was handed at a line — what went into the run — and last the results
 * file it wrote.
 */
export function baseChanges(before: Artifact, after: Artifact): BaseChange[] {
  return [
    ...assumptionChanges(before, after),
    ...modelPointChanges(before, after),
    ...holeChanges(before, after),
    ...injectionChanges(before, after),
    ...resultsChanges(before, after),
  ];
}

/**
 * One entry's key: its kind and its name together.
 *
 * The pair, because that is what identifies an entry of the assumptions
 * section — a name alone identified one only while tables were the only kind
 * that carried a name. Through JSON rather than by joining on a separator: a
 * table may be called anything, including something holding a space, and a key
 * that could be read back two ways would put two bases under one entry.
 */
function keyOf(kind: string, name: string): string {
  return JSON.stringify([kind, name]);
}

/** That key read back, as the two strings it was made of. */
function fromKey(key: string): { kind: string; name: string } {
  const [kind, name] = JSON.parse(key) as [string, string];
  return { kind, name };
}

/** One document's named assumption entries, keyed by kind and name. */
function namedAssumptions(artifact: Artifact): Map<string, string> {
  const found = new Map<string, string>();
  for (const entry of assumptionEntries(artifact)) {
    if (typeof entry.name === "string") found.set(keyOf(entry.kind, entry.name), entry.fingerprint);
  }
  return found;
}

/** The digests of the entries carrying no name at all, by kind. */
function unnamedAssumptions(artifact: Artifact): Map<string, Set<string>> {
  const found = new Map<string, Set<string>>();
  for (const entry of assumptionEntries(artifact)) {
    if (entry.name !== null && entry.name !== undefined) continue;
    const held = found.get(entry.kind) ?? new Set<string>();
    held.add(entry.fingerprint);
    found.set(entry.kind, held);
  }
  return found;
}

/** The assumption entries that state both a kind and a digest. */
function assumptionEntries(
  artifact: Artifact,
): { kind: string; name?: string | null; fingerprint: string }[] {
  const entries = Array.isArray(artifact.assumptions) ? artifact.assumptions : [];
  return entries.filter(
    (entry): entry is { kind: string; name?: string | null; fingerprint: string } =>
      typeof entry === "object" &&
      entry !== null &&
      "kind" in entry &&
      "fingerprint" in entry &&
      typeof (entry as { kind: unknown }).kind === "string" &&
      typeof (entry as { fingerprint: unknown }).fingerprint === "string",
  );
}

/**
 * The digests one document names and the other leaves unnamed, by kind.
 *
 * A base that gained or lost a label between two producers is one base, and
 * the label is not its identity — the digest beside it is. Reporting it as a
 * base gone and another arrived would accuse a model that did not move.
 */
function bridged(before: Artifact, after: Artifact): Map<string, Set<string>> {
  const namedDigests = (artifact: Artifact): Map<string, Set<string>> => {
    const byKind = new Map<string, Set<string>>();
    for (const entry of assumptionEntries(artifact)) {
      if (typeof entry.name !== "string") continue;
      const held = byKind.get(entry.kind) ?? new Set<string>();
      held.add(entry.fingerprint);
      byKind.set(entry.kind, held);
    }
    return byKind;
  };
  const wasNamed = namedDigests(before);
  const nowNamed = namedDigests(after);
  const anonymous = unnamedAssumptions(before);
  const later = unnamedAssumptions(after);
  const out = new Map<string, Set<string>>();
  for (const kind of new Set([...anonymous.keys(), ...later.keys()])) {
    const carried = new Set<string>();
    for (const digest of anonymous.get(kind) ?? []) {
      if (nowNamed.get(kind)?.has(digest) === true) carried.add(digest);
    }
    for (const digest of later.get(kind) ?? []) {
      if (wasNamed.get(kind)?.has(digest) === true) carried.add(digest);
    }
    out.set(kind, carried);
  }
  return out;
}

/** The assumption entries whose digests moved between the two documents. */
function assumptionChanges(before: Artifact, after: Artifact): BaseChange[] {
  const was = namedAssumptions(before);
  const now = namedAssumptions(after);
  const carried = bridged(before, after);
  const out: BaseChange[] = [];

  for (const key of [...new Set([...was.keys(), ...now.keys()])].sort()) {
    const { kind, name } = fromKey(key);
    const stood = was.get(key);
    const stands = now.get(key);
    const bridge = carried.get(kind);
    if (stood === undefined && stands !== undefined && bridge?.has(stands) === true) continue;
    if (stands === undefined && stood !== undefined && bridge?.has(stood) === true) continue;
    if (stood === stands) continue;
    out.push({ kind: kind as BaseChange["kind"], name, before: stood ?? null, after: stands ?? null, reason: null });
  }

  const anonymous = unnamedAssumptions(before);
  const later = unnamedAssumptions(after);
  for (const kind of [...new Set([...anonymous.keys(), ...later.keys()])].sort()) {
    const bridge = carried.get(kind) ?? new Set<string>();
    const held = [...(anonymous.get(kind) ?? [])].filter((digest) => !bridge.has(digest));
    const holds = [...(later.get(kind) ?? [])].filter((digest) => !bridge.has(digest));
    for (const digest of held.filter((one) => !holds.includes(one)).sort()) {
      out.push({ kind: kind as BaseChange["kind"], name: null, before: digest, after: null, reason: null });
    }
    for (const digest of holds.filter((one) => !held.includes(one)).sort()) {
      out.push({ kind: kind as BaseChange["kind"], name: null, before: null, after: digest, reason: null });
    }
  }

  return out;
}

/** The content digest of the book one document was built over, where it states one. */
function bookDigest(artifact: Artifact): string | null {
  const digest = artifact.book?.digest;
  return typeof digest === "string" ? digest : null;
}

/**
 * The policy data the two runs consumed, where it is not the same data.
 *
 * `diff_artifacts`'s rule, read the same way here (§14.2). The book's own
 * digest decides where both documents state one: it is taken over the data the
 * model reads, so a replaced in-force file is a changed book and the same data
 * written out again — or revised only where no line reads — is not. Where
 * either states none, the file each run said it read decides, on its
 * fingerprint and never on the path: the same data read from a new location is
 * the same policies, and calling that a change would be reporting on
 * somebody's filesystem. Where neither can decide — no digest on one side and
 * no file named by both runs — the entry is written anyway, with a `reason`,
 * because saying nothing would read as "nothing moved".
 */
function modelPointChanges(before: Artifact, after: Artifact): BaseChange[] {
  const was = before.model.model_points ?? null;
  const now = after.model.model_points ?? null;
  const name = now?.path ?? was?.path ?? null;
  const wasBook = bookDigest(before);
  const nowBook = bookDigest(after);
  if (wasBook !== null && nowBook !== null) {
    return wasBook === nowBook ? [] : [{ kind: "model_points", name, before: wasBook, after: nowBook, reason: null }];
  }
  const wasFile = was?.fingerprint ?? null;
  const nowFile = now?.fingerprint ?? null;
  if (wasFile !== null && nowFile !== null) {
    return wasFile === nowFile ? [] : [{ kind: "model_points", name, before: wasFile, after: nowFile, reason: null }];
  }
  return [
    {
      kind: "model_points",
      name,
      before: wasBook ?? wasFile,
      after: nowBook ?? nowFile,
      reason: whyTheBooksWereNotCompared(before, after),
    },
  ];
}

/** What one document said about a book it states no digest of, or null. */
function noDigestBecause(artifact: Artifact): string | null {
  const book = artifact.book;
  if (book === undefined || book === null) return "it records no book, having been written before documents did";
  if (typeof book.digest === "string") return null;
  const detail = book.digest.detail;
  if (typeof detail !== "string" || detail === "") return "it gave no reason";
  // Carried inside a sentence, so the document's own full stop goes.
  return detail.endsWith(".") ? detail.slice(0, -1) : detail;
}

/** The sentence an uncompared book's entry carries, in `diff_artifacts`'s words. */
function whyTheBooksWereNotCompared(before: Artifact, after: Artifact): string {
  const sides: [string, Artifact][] = [
    ["earlier", before],
    ["later", after],
  ];
  const accounts = sides.flatMap(([side, artifact]): [string, string][] => {
    const account = noDigestBecause(artifact);
    return account === null ? [] : [[side, account]];
  });
  const said =
    accounts.length === sides.length && accounts[0]![1] === accounts[1]![1]
      ? `neither document states a digest of its book (${accounts[1]![1]})`
      : accounts.map(([side, account]) => `the ${side} document states no digest of its book (${account})`).join(" and ");
  const unnamed = sides
    .filter(([, artifact]) => (artifact.model.model_points?.fingerprint ?? null) === null)
    .map(([side]) => side);
  const files =
    unnamed.length === sides.length
      ? "neither run named a file for its policy data"
      : `the ${unnamed[0]} run named no file for its policy data`;
  return (
    `The two books could not be compared: ${said}, and ${files} to compare ` +
    "instead. To compare them, export each model from the frame built over " +
    "its book, with every column the model reads in a type the format " +
    "names, or name each run's file with " +
    'ModelIdentity.of("model.py", model_points="points.parquet"), passed ' +
    "to the export as GraphExportConfig(model=...)."
  );
}

/** Each hole's column, with its stamp and its reason, or null for either. */
function holeStamps(artifact: Artifact): Map<string, { content: string | null; reason: string | null }> {
  const found = new Map<string, { content: string | null; reason: string | null }>();
  for (const entry of Array.isArray(artifact.holes) ? artifact.holes : []) {
    if (typeof entry !== "object" || entry === null) continue;
    const { column, content, reason } = entry as { column?: unknown; content?: unknown; reason?: unknown };
    if (typeof column !== "string") continue;
    found.set(column, {
      content: typeof content === "string" ? content : null,
      reason: typeof reason === "string" ? reason : null,
    });
  }
  return found;
}

/** Why a hole carries no stamp, from the reason its entry gives: `diff._why_unstamped`. */
function whyUnstamped(reason: string | null): string {
  if (reason === "overwritten") {
    return "its hole is an overwritten definition, which holds no arriving values";
  }
  return "it was written before holes carried one, or its producer could not read the values";
}

/**
 * Every hole both documents list whose stamp of what it held moved.
 *
 * `diff.py`'s `_hole_changes`, read the same way (§14.2). A hole's node carries
 * no stamp, so an edit to a file the model's setup joined moves no node
 * digest, and only the holes section shows it. Where one side has no stamp the
 * two could not be compared, and the entry says why in the report's words. A
 * hole only one document lists is a node only one holds, and the changes list
 * already shows it.
 */
function holeChanges(before: Artifact, after: Artifact): BaseChange[] {
  const was = holeStamps(before);
  const now = holeStamps(after);
  const out: BaseChange[] = [];
  const columns = [...was.keys()].filter((column) => now.has(column));
  for (const column of columns.sort((a, b) => (a < b ? -1 : a > b ? 1 : 0))) {
    const stood = was.get(column)!;
    const stands = now.get(column)!;
    if (stood.content === stands.content) continue;
    let reason: string | null = null;
    if (stood.content === null || stands.content === null) {
      const [side, why]: [string, string | null] =
        stood.content === null ? ["earlier", stood.reason] : ["later", stands.reason];
      reason =
        `The hole ${column} could not be compared: the ${side} document ` +
        `records no stamp of what the column held (${whyUnstamped(why)}), ` +
        "so nothing says whether it held the same values. A hole the " +
        "frame arrived holding is stamped by a producer that read it; " +
        "export both runs from one that does to compare them.";
    }
    out.push({ kind: "hole", name: column, before: stood.content, after: stands.content, reason });
  }
  return out;
}

/** The holes whose two stamps the comparison holds and found apart, by column. */
function movedHoles(bases: BaseChange[]): Set<string> {
  return new Set(
    bases
      .filter((base) => base.kind === "hole" && base.reason === null && base.name !== null)
      .map((base) => base.name as string),
  );
}

/**
 * Per node of the later document, the moved holes it reads, in that document's order.
 *
 * A node reads a hole where it is that hole's node, or reads it through any
 * node it reads, as the later document's `reads` record them —
 * `diff_results._holes_read`, over the same evidence.
 */
function holesRead(later: Index, moved: Set<string>): Map<string, string[]> {
  const out = new Map<string, string[]>();
  if (moved.size === 0) return out;
  const found = new Map<string, Set<string>>();
  const reached = (id: string): Set<string> => {
    const known = found.get(id);
    if (known !== undefined) return known;
    found.set(id, new Set()); // a cycle in a malformed record reads nothing
    const node = later.nodes.get(id);
    const own = new Set<string>();
    if (node !== undefined && node.kind === "hole" && moved.has(node.column ?? "")) own.add(id);
    for (const read of node?.reads ?? []) for (const hole of reached(read)) own.add(hole);
    found.set(id, own);
    return own;
  };
  for (const id of later.order) {
    const holes = reached(id);
    if (holes.size === 0) continue;
    out.set(
      id,
      later.order.filter((one) => holes.has(one)).map((one) => later.nodes.get(one)?.column ?? one),
    );
  }
  return out;
}

/** A path's parts with `.` dropped and `..` taken back where it can be: `posixpath.normpath`. */
function normalParts(path: string): string[] {
  const out: string[] = [];
  for (const part of path.split("/")) {
    if (part === "" || part === ".") continue;
    if (part === ".." && out.length > 0 && out[out.length - 1] !== "..") {
      out.pop();
      continue;
    }
    out.push(part);
  }
  return out;
}

/** A module's path relative to the model file's directory, lexically: `diff._beside`. */
function beside(path: string, home: string[] | null): string {
  if (home === null) return path;
  const parts = normalParts(path);
  let shared = 0;
  while (shared < Math.min(parts.length, home.length) && parts[shared] === home[shared]) shared += 1;
  return [...Array<string>(home.length - shared).fill(".."), ...parts.slice(shared)].join("/");
}

/** A run's modules by their place beside the model file, or null where it lists none. */
function modulesOf(artifact: Artifact): Map<string, { path: string; fingerprint: string | null }> | null {
  const modules: unknown = artifact.model.modules;
  if (!Array.isArray(modules)) return null;
  const source = artifact.model.source_path;
  const home = typeof source === "string" && source !== "" ? normalParts(source).slice(0, -1) : null;
  const out = new Map<string, { path: string; fingerprint: string | null }>();
  for (const entry of modules) {
    if (typeof entry !== "object" || entry === null) continue;
    const { path, fingerprint } = entry as { path?: unknown; fingerprint?: unknown };
    if (typeof path !== "string") continue;
    out.set(beside(path, home), { path, fingerprint: typeof fingerprint === "string" ? fingerprint : null });
  }
  return out;
}

/**
 * The model's own files, where they moved: §14.2's `source`, `diff.py`'s `_source_change`.
 *
 * The model file's two `source_sha` digests, and each helper module whose
 * fingerprint moved or which only one run lists, paired by its place beside
 * the model file so a model copied to another directory of one repository
 * pairs its helpers with the copy's. Null where neither moved. Stated, never
 * counted: a comment moves a file and no calculation.
 *
 * @param before - The earlier document.
 * @param after - The later document.
 * @returns The line, or null.
 */
export function sourceMoved(before: Artifact, after: Artifact): SourceMoved | null {
  const stated = (value: unknown): string | null => (typeof value === "string" && value !== "" ? value : null);
  const was = stated(before.model.source_sha);
  const now = stated(after.model.source_sha);
  const fileMoved = was !== null && now !== null && was !== now;
  const earlier = modulesOf(before);
  const later = modulesOf(after);
  const modules: ModuleMoved[] = [];
  if (earlier !== null && later !== null) {
    const places = [...new Set([...earlier.keys(), ...later.keys()])].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
    for (const place of places) {
      const stood = earlier.get(place);
      const stands = later.get(place);
      if (stood !== undefined && stands !== undefined && stood.fingerprint === stands.fingerprint) continue;
      modules.push({
        path: stands?.path ?? stood?.path ?? place,
        before: stood?.fingerprint ?? null,
        after: stands?.fingerprint ?? null,
      });
    }
  }
  if (!fileMoved && modules.length === 0) return null;
  return {
    path: stated(after.model.source_path) ?? stated(before.model.source_path),
    before: was,
    after: now,
    modules,
  };
}

/** Every column of values handed over at a line whose contents moved. */
function injectionChanges(before: Artifact, after: Artifact): BaseChange[] {
  const injections = (artifact: Artifact): Map<string, ArtifactNode> =>
    new Map(
      artifact.nodes
        .filter((node) => HANDED_OVER.has(node.provenance ?? ""))
        .map((node) => [node.id, node]),
    );
  const was = injections(before);
  const now = injections(after);
  const out: BaseChange[] = [];
  for (const id of [...was.keys()].filter((one) => now.has(one)).sort()) {
    const stood = was.get(id);
    const stands = now.get(id);
    if (stood === undefined || stands === undefined) continue;
    if (stood.local_fingerprint === stands.local_fingerprint) continue;
    out.push({
      kind: "injection",
      name: stands.column,
      before: stood.local_fingerprint,
      after: stands.local_fingerprint,
      reason: null,
    });
  }
  return out;
}

// --- the results file each run wrote ----------------------------------------

/**
 * What the page writes beside a results entry: `gspio diff`'s line under one,
 * in the same words. A results file's digest is taken over its bytes, which
 * move with the writer as well as with the values, so the sentence says the
 * file moved and names the step that says whether the two results agree, to a
 * stated tolerance. The entry's `reason` stays null, as the report's does —
 * this says how to read an entry that was compared, not why one could not be.
 */
export const RESULTS_FILE_MOVED =
  "The results file differs between the two runs. A results file also records the " +
  "library versions and platform that wrote it, so this says the file moved, not that any " +
  "number did. To see whether the two results agree, run gspio compare on the later audit " +
  "file and the two results files.";

/**
 * The same entry where the two runs are of two different calculations —
 * `diff.py`'s `_RESULTS_OF_TWO_CALCULATIONS`, word for word. gspio compare
 * asks whether two runs of one calculation agree, and refuses these; what
 * moved between two versions is `gspio diff` with the two results files.
 */
export const RESULTS_OF_TWO_CALCULATIONS =
  "The results file differs between the two runs, and so does the model: the two audit " +
  "files state different graph fingerprints, so the files hold the numbers of two different " +
  "calculations. The calculations listed above are the ones whose numbers can have moved. To " +
  "see which did, and by how much, run gspio diff on the two audit files with --results and " +
  "the two results files, earlier first.";

/**
 * The same entry where the calculation held and the book under it moved —
 * `diff.py`'s `_RESULTS_OVER_TWO_BOOKS`, word for word. The same command pairs
 * the two books' policies, so new business and lapses are counted, not refused.
 */
export const RESULTS_OVER_TWO_BOOKS =
  "The results file differs between the two runs, and so does the book the model ran over, " +
  "so the numbers can have moved with the data. To see which did, and by how much, run gspio " +
  "diff on the two audit files with --results and the two results files, earlier first: it " +
  "pairs the two books' policies and counts those only one of them holds.";

/**
 * The entry where `gspio diff` read the two results files and wrote what it
 * measured into the page — `diff.py`'s `_RESULTS_READ`, word for word.
 */
export const RESULTS_READ =
  "The results file differs between the two runs. Both files were read, and the values " +
  "reported here compare them line by line and policy by policy.";

/**
 * Whether two documents state one graph fingerprint, or cannot tell —
 * `diff.py`'s `_one_calculation`. The fingerprint gspio compare binds a
 * results file to; a document stating none says nothing either way.
 */
function oneCalculation(before: Artifact, after: Artifact): boolean {
  const was = typeof before.graph_fingerprint === "string" ? before.graph_fingerprint : null;
  const now = typeof after.graph_fingerprint === "string" ? after.graph_fingerprint : null;
  return was === null || now === null || was === now;
}

/** Whether two documents state one book digest, or cannot tell — `diff.py`'s `_one_book`. */
function oneBook(before: Artifact, after: Artifact): boolean {
  const was = bookDigest(before);
  const now = bookDigest(after);
  return was === null || now === null || was === now;
}

/**
 * The sentence beside a results entry: the next step that works for these
 * two runs, and never one that refuses them. `diff.py`'s
 * `_results_file_moved`, on the same evidence and in the same words.
 */
export function resultsFileMoved(before: Artifact, after: Artifact): string {
  if (!oneCalculation(before, after)) return RESULTS_OF_TWO_CALCULATIONS;
  if (!oneBook(before, after)) return RESULTS_OVER_TWO_BOOKS;
  return RESULTS_FILE_MOVED;
}

/**
 * Where a run's results file was written and its digest, or null where the
 * document records none.
 *
 * A block stating no digest records no file a comparison could read, so it is
 * read as no file at all — `diff.py`'s `_results_file`, on the same evidence.
 */
function resultsFile(artifact: Artifact): { path: string | null; fingerprint: string } | null {
  const results: unknown = artifact.model.results;
  if (typeof results !== "object" || results === null) return null;
  const { path, fingerprint } = results as { path?: unknown; fingerprint?: unknown };
  if (typeof fingerprint !== "string") return null;
  return { path: typeof path === "string" ? path : null, fingerprint };
}

/**
 * The results file the two runs wrote, where both recorded its digest and they differ.
 *
 * `diff_artifacts`'s rule, read the same way here (§14.2). Only where both
 * documents record a results file's digest: a run exported without one makes
 * no claim about its results, so there is nothing to hold the other side against.
 * Where both do, the two digests are the whole comparison, and the same bytes
 * under a new path are the same file. Named by the later run's path, else the
 * earlier one's.
 */
function resultsChanges(before: Artifact, after: Artifact): BaseChange[] {
  const was = resultsFile(before);
  const now = resultsFile(after);
  if (was === null || now === null || was.fingerprint === now.fingerprint) return [];
  return [
    { kind: "results", name: now.path ?? was.path, before: was.fingerprint, after: now.fingerprint, reason: null },
  ];
}

/**
 * The sentence for a results file only one of the two runs recorded, or null.
 *
 * `diff.py`'s `_results_not_compared`, in its words: which run recorded no
 * checksum — it may still have named a path — and the step that says whether
 * the two results agree, for a reader holding a results file from each run.
 * Where both recorded one, the entry says what there is to say; where neither
 * did, there is nothing to say, and a line over every such comparison would be
 * a line a reader learns to skip.
 */
function resultsNotCompared(before: Artifact, after: Artifact): string | null {
  const was = resultsFile(before) !== null;
  const now = resultsFile(after) !== null;
  if (was === now) return null;
  const opening =
    `The results files were not compared: the ${was ? "later" : "earlier"} run recorded no ` +
    "checksum of a results file.";
  if (!oneCalculation(before, after)) {
    return (
      `${opening} The two runs are of different calculations -- their graph fingerprints ` +
      "differ. If a results file from each run is to hand, gspio diff on the two audit files " +
      "with --results and the two files, earlier first, says which numbers moved and by how much."
    );
  }
  if (!oneBook(before, after)) {
    return (
      `${opening} The two runs are over different books. If a results file from each run is ` +
      "to hand, gspio diff on the two audit files with --results and the two files, earlier " +
      "first, pairs the two books' policies and says how far each line moved."
    );
  }
  return (
    `${opening} If a results file from each run is to hand, run gspio compare on the later ` +
    "audit file and both of them to see whether the two results agree."
  );
}
