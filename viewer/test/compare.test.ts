// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The comparison, against the report `gspio diff` wrote over the same two files.
 *
 * `fixtures/compare-before.json` and `fixtures/compare-after.json` are two
 * exports of level 4 with two changes made between them and no others, and
 * both changes are known before the page is asked: one formula edited in
 * place — `maint_fee_pp`, `/ 12.0` became `/ 12.0 * 1.10` — and one assumption
 * table re-sourced, `lapse_rates` at duration 0 on `L001`, 0.03 to 0.05.
 * `fixtures/compare-report.json` is `gspio diff`'s own report between them,
 * committed so the agreement check has a fixed reference rather than a
 * reference it computes.
 *
 * **The agreement is over `model` and `numbers`, and it is stated that way on
 * purpose.** The page later gained a third mark, *data*, for a column
 * whose sampled values moved under an unmoved fingerprint — and `gspio diff`
 * carries no such kind, because a report of definitions cannot have one. So
 * the two readings are held to each other over the two kinds they both
 * express, and *data* is held separately against the fixtures' own
 * `value_sample` arrays. A page that asserted *data* against the report would
 * be asserting that a report says something it does not.
 *
 * `fixtures/compare-book-before.json` and `fixtures/compare-book-after.json`
 * are the third state: one model, two books — level 4 over
 * `model_points.parquet` and over `model_points_2022Q4IF.parquet` — so that
 * *data* has a pair it is the only thing in.
 *
 * `fixtures/compare-results-report.json` is the fourth: `gspio diff`'s report
 * over `compare-before` compared with itself, each side as though its run had
 * named a different results file, so the results file is the only thing that
 * moved. The two documents are derived here rather than committed, the way the
 * other edits of a committed export are.
 */

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import {
  RESULTS_FILE_MOVED,
  RESULTS_OF_TWO_CALCULATIONS,
  RESULTS_OVER_TWO_BOOKS,
  RESULTS_READ,
  baseChanges,
  compare,
  locateEntry,
  matchingEntry,
  moved,
  movementOf,
  refusedComparison,
  sourceMoved,
} from "../src/reader/compare";
import { ExactInteger } from "../src/reader/exact";
import { bookSaid, disagreements, drillIn, identityOnly, readMovement } from "../src/reader/movement";
import type { BookMovement } from "../src/reader/movement";
import { parseArtifacts } from "../src/reader/parse";
import type { Artifact, ArtifactNode, Policy } from "../src/reader/types";

function load(name: string): Artifact {
  const parsed = parseArtifacts([readFileSync(new URL(`../fixtures/${name}.json`, import.meta.url), "utf8")]);
  if (parsed.refused) throw new Error(parsed.sentence);
  return parsed.artifacts[0]!;
}

/** The committed `gspio diff` report, as JSON. */
interface Report {
  calculations: {
    node: string;
    column: string | null;
    kind: string;
    change_origin: string | null;
  }[];
  data: { kind: string; name: string | null; before: string | null; after: string | null; reason?: string | null }[];
  /** The two documents the report names, each as §14.2's `compared` writes one. */
  compared?: { before: ComparedDocument; after: ComparedDocument };
}

/** One of the two documents a report names. */
interface ComparedDocument {
  graph_fingerprint: string | null;
  document_digest: string | null;
  created_at: string | null;
  producer: string | null;
  /** Null where the document was written before the member. */
  formulas_fingerprint: string | null;
}

const after = load("compare-after");
const before = load("compare-before");
const bookAfter = load("compare-book-after");
const bookBefore = load("compare-book-before");
const report = JSON.parse(
  readFileSync(new URL("../fixtures/compare-report.json", import.meta.url), "utf8"),
) as Report;

/**
 * `gspio diff`'s own report over `compare-before` compared with itself, as
 * though the earlier run had named `results_q1.parquet` and the later
 * `results_q2.parquet` — the two `withResults` below makes, and the two
 * `tests/graph/test_diff_results.py` makes on the Python side.
 */
const resultsReport = JSON.parse(
  readFileSync(new URL("../fixtures/compare-results-report.json", import.meta.url), "utf8"),
) as Report;

describe("the page's derivation and gspio diff's report", () => {
  const comparison = compare(after, before);

  it("marks as a model change exactly the nodes the report calls self, added, removed or renamed", () => {
    const page = comparison.changes.filter((one) => one.mark === "model").map((one) => one.node);
    const said = report.calculations
      .filter((one) => one.kind !== "changed" || one.change_origin === "self")
      .map((one) => one.node);
    expect([...page].sort()).toEqual([...said].sort());
  });

  it("marks as a numbers change exactly the nodes the report calls inherited", () => {
    const page = comparison.changes.filter((one) => one.mark === "numbers").map((one) => one.node);
    const said = report.calculations
      .filter((one) => one.kind === "changed" && one.change_origin === "inherited")
      .map((one) => one.node);
    expect([...page].sort()).toEqual([...said].sort());
  });

  it("finds neither more nor fewer changed definitions than the report does", () => {
    // Both directions in one sentence: the two sets are equal, so neither
    // implementation marks a node the other does not. Over the two marks the
    // report expresses — a *data* entry is not a changed definition and the
    // report has no kind for it.
    const definitions = comparison.changes.filter((one) => one.mark !== "data");
    expect([...definitions.map((one) => one.node)].sort()).toEqual(
      [...report.calculations.map((one) => one.node)].sort(),
    );
  });

  it("marks nothing as the book on two runs over one book", () => {
    // The two fixtures were exported over the same `model_points_1k.parquet`,
    // so there is no book move in them at all — which is what makes the two
    // sets above comparable to the report in the first place.
    expect(comparison.changes.filter((one) => one.mark === "data")).toEqual([]);
    expect(after.model.model_points?.fingerprint).toBe(before.model.model_points?.fingerprint);
  });

  it("finds the same bases moved underneath the model, in the same order", () => {
    expect(comparison.bases).toEqual(
      report.data.map((one) => ({
        kind: one.kind,
        name: one.name,
        before: one.before,
        after: one.after,
        reason: one.reason ?? null,
      })),
    );
  });

  it("is the two changes that were made and nothing else", () => {
    const edited = comparison.changes.filter((one) => one.mark === "model");
    expect(edited.map((one) => one.node)).toEqual(["maint_fee_pp@1"]);
    expect(comparison.bases).toEqual([
      {
        kind: "table",
        name: "lapse_rates",
        before: expect.stringMatching(/^sha256:/) as unknown as string,
        after: expect.stringMatching(/^sha256:/) as unknown as string,
        reason: null,
      },
    ]);
  });
});

describe("the ranking", () => {
  const comparison = compare(after, before);

  it("puts the model changes first, in the model's own order", () => {
    const first = comparison.changes[0];
    expect(first?.mark).toBe("model");
    const model = comparison.changes.filter((one) => one.mark === "model").length;
    expect(comparison.changes.slice(0, model).every((one) => one.mark === "model")).toBe(true);
    // The edited line's numbers moved by the factor it was edited by, and the
    // entry carries that measurement. What it is not is *ranked* by it: a
    // model change is exact, and the ordering question is only ever asked of
    // the numbers.
    expect(first?.magnitude).toBeCloseTo(0.1, 6);
  });

  it("orders the numbers by the magnitude computed from the fixtures' own value_sample", () => {
    // Computed here from the two documents' arrays, not from the module under
    // test: the order the list draws has to equal the order these numbers put
    // the columns in.
    const sampleOf = (artifact: Artifact, id: string): unknown =>
      artifact.nodes.find((node: ArtifactNode) => node.id === id)?.value_sample;
    const largest = (id: string): number | null => {
      const was = sampleOf(before, id);
      const now = sampleOf(after, id);
      // A column holding one value per policy is one comparison and a
      // per-period column is one per period; both are recomputed here from the
      // arrays the two files carry.
      const wasRun = Array.isArray(was) ? was : [was];
      const nowRun = Array.isArray(now) ? now : [now];
      let best: number | null = null;
      for (let at = 0; at < Math.min(wasRun.length, nowRun.length); at += 1) {
        const b = wasRun[at];
        const a = nowRun[at];
        if (typeof a !== "number" || typeof b !== "number" || b === 0 || a === b) continue;
        const ratio = Math.abs(a - b) / Math.abs(b);
        if (best === null || ratio > best) best = ratio;
      }
      return best;
    };
    const numbers = comparison.changes.filter((one) => one.mark === "numbers");
    for (const change of numbers) {
      if (change.fromZero || !change.moved) continue;
      expect(change.magnitude).toBeCloseTo(largest(change.node) ?? Number.NaN, 12);
    }
    const measured = numbers.filter((one) => one.moved && !one.fromZero && one.magnitude !== null);
    const descending = [...measured].sort((a, b) => (b.magnitude ?? 0) - (a.magnitude ?? 0));
    expect(measured.map((one) => one.node)).toEqual(descending.map((one) => one.node));
  });

  it("ranks the nodes whose digests moved and whose sampled numbers did not, last", () => {
    const numbers = comparison.changes.filter((one) => one.mark === "numbers");
    const still = numbers.filter((one) => !one.moved).map((one) => one.node);
    // The lapse basis moved and this policy never reaches the cell that moved,
    // so its own rate is the number it was. The page says the change is there
    // and measures no move on it, which is the honest pair of statements.
    expect(still).toContain("base_lapse_rate@1");
    expect(numbers.slice(numbers.length - still.length).every((one) => !one.moved)).toBe(true);
  });
});

describe("the magnitude", () => {
  it("is the relative move at the period where it is largest", () => {
    expect(movementOf([1, 2, 4], [1, 3, 5])).toEqual({
      moved: true,
      magnitude: 0.5,
      period: 1,
      fromZero: false,
    });
  });

  it("never divides by a before of zero, and says so instead", () => {
    expect(movementOf([0], [7])).toEqual({
      moved: true,
      magnitude: null,
      period: 0,
      fromZero: true,
    });
  });

  it("puts a move out of zero above every finite ratio", () => {
    expect(movementOf([1, 0], [1000, 1])).toMatchObject({ fromZero: true, period: 1 });
  });

  it("calls a value unequal without a tolerance anywhere near it", () => {
    expect(movementOf([1], [1 + 1e-15]).moved).toBe(true);
    expect(movementOf([1], [1]).moved).toBe(false);
  });

  it("reports a move it cannot put a ratio on rather than inventing one", () => {
    expect(movementOf(["a"], ["b"])).toEqual({
      moved: true,
      magnitude: null,
      period: 0,
      fromZero: false,
    });
  });

  it("counts two timelines of different lengths as a move", () => {
    expect(movementOf([1, 2], [1, 2, 3]).moved).toBe(true);
  });
});

describe("only the book moved", () => {
  const comparison = compare(bookAfter, bookBefore);

  it("marks nothing in the model, because nothing in the model moved", () => {
    // Every digest on every node is the digest it was: one model, two books.
    // This is the pair's whole reason for existing — it isolates the mark.
    expect(comparison.changes.filter((one) => one.mark !== "data")).toEqual([]);
    expect(bookAfter.graph_fingerprint).toBe(bookBefore.graph_fingerprint);
  });

  it("lists exactly the columns whose sampled values differ", () => {
    // Recomputed here from the two files' own arrays rather than from the
    // module under test, so the list is held to the documents and not to
    // itself.
    const sampleOf = (artifact: Artifact, id: string): unknown =>
      artifact.nodes.find((node: ArtifactNode) => node.id === id)?.value_sample;
    const unequal = bookAfter.nodes
      .filter(
        (node) =>
          JSON.stringify(sampleOf(bookBefore, node.id)) !== JSON.stringify(sampleOf(bookAfter, node.id)),
      )
      .map((node) => node.id);
    expect(unequal.length).toBeGreaterThan(0);
    expect([...comparison.changes.map((one) => one.node)].sort()).toEqual([...unequal].sort());
    expect(comparison.changes.every((one) => one.moved)).toBe(true);
  });

  it("names the book underneath, which is the thing that moved", () => {
    // Both documents state their book, so the two book digests are what moved,
    // named by the file the later run said it read.
    expect(typeof bookBefore.book?.digest).toBe("string");
    expect(bookBefore.book?.digest).not.toBe(bookAfter.book?.digest);
    expect(comparison.bases).toEqual([
      {
        kind: "model_points",
        name: "model_points_2022Q4IF.parquet",
        before: bookBefore.book?.digest ?? null,
        after: bookAfter.book?.digest ?? null,
        reason: null,
      },
    ]);
  });

  it("ranks the book's moves by the magnitude the two files give, largest first", () => {
    const measured = comparison.changes.filter(
      (one) => one.moved && !one.fromZero && one.magnitude !== null,
    );
    expect(measured.length).toBeGreaterThan(10);
    const descending = [...measured].sort((a, b) => (b.magnitude ?? 0) - (a.magnitude ?? 0));
    expect(measured.map((one) => one.node)).toEqual(descending.map((one) => one.node));
  });

  it("says nothing about a book that moved where no values can be compared", () => {
    // The entry the earlier file does not answer to. The model comparison
    // stands and no number does, so there is no *data* entry to be had.
    const elsewhere = { ...bookBefore, policies: [{ ...bookBefore.policies[0]!, policy_id: "999" }] };
    const apart = compare(bookAfter, elsewhere);
    expect(apart.policyNote).not.toBeNull();
    expect(apart.changes).toEqual([]);
  });
});

describe("a value too wide for a double", () => {
  const wide = (digits: string): ExactInteger => new ExactInteger(digits, Number(digits));

  it("has not moved where the digits are the digits", () => {
    expect(movementOf([wide("9007199254740993")], [wide("9007199254740993")]).moved).toBe(false);
  });

  it("has moved where one double would call the two equal", () => {
    // A wide integer in one line: these two round to the same number, and
    // the file spells them apart.
    const moved = movementOf([wide("9007199254740993")], [wide("9007199254740992")]);
    expect(moved.moved).toBe(true);
    expect(moved.period).toBe(0);
  });

  it("is ranked on the double, because a ratio has no exact decimal", () => {
    expect(movementOf([wide("10000000000000000")], [wide("20000000000000000")])).toEqual({
      moved: true,
      magnitude: 1,
      period: 0,
      fromZero: false,
    });
  });
});

describe("what the page will not compare", () => {
  it("refuses two documents whose digests were taken under different grammars", () => {
    const other = { ...after, fingerprint_algorithm: "gspv0-preview-1" };
    expect(refusedComparison(other, before)).toContain("gspv0-preview-1");
  });

  it("compares two documents whose model files are named differently, as gspio diff does", () => {
    // The page refuses what `gspio diff` refuses and nothing else. The diff
    // report compares this pair -- last quarter's model copied into a new
    // folder of one repository -- so the page compares it too, and the two
    // readings mark the same lines.
    const moved = { ...after, model: { ...after.model, source_path: "q4/model.py" } };
    expect(refusedComparison(moved, before)).toBeNull();
    const comparison = compare(moved, before);
    expect(comparison.changes.map((change) => change.node).sort()).toEqual(
      compare(after, before)
        .changes.map((change) => change.node)
        .sort(),
    );
  });

  it("refuses exactly one pair: two fingerprint algorithms", () => {
    const other = {
      ...after,
      fingerprint_algorithm: "gspv0-preview-2",
      model: { ...after.model, source_path: "q4/model.py" },
    };
    expect(refusedComparison(other, before)).toContain("gspv0-preview-2");
    expect(refusedComparison(other, before)).not.toContain("q4/model.py");
  });

  it("compares two states of one model however far the graph moved", () => {
    expect(refusedComparison(after, before)).toBeNull();
    expect(after.graph_fingerprint).not.toBe(before.graph_fingerprint);
  });
});

describe("the policy axis", () => {
  const entry = (policy_id: string | null, aggregation: string | null = null): Policy => ({
    policy_id,
    aggregation,
    periods: null,
    filter: null,
    why: "",
  });

  it("answers to the same policy id and never to the same position", () => {
    const axis = [entry("7"), entry("1")];
    expect(matchingEntry(axis, entry("1"))).toBe(1);
  });

  it("answers to the same fold by its own cut", () => {
    const axis = [entry(null, "sum"), entry("1")];
    expect(matchingEntry(axis, entry(null, "sum"))).toBe(0);
  });

  it("tells two scenario rows of one policy apart on the cut the file wrote", () => {
    // Every entry's `filter` is in the file, and the defect pinned here is the reader
    // dropping it: policy 1 under UP answered to policy 1 under BASE, and the
    // page put one scenario's proof beside another's without an admission.
    const cut = (policy_id: string | null, aggregation: string | null, filter: string): Policy => ({
      policy_id,
      aggregation,
      periods: null,
      filter,
      why: "",
    });
    const axis = [
      cut("1", null, 'scenario_id == "BASE"'),
      cut("1", null, 'scenario_id == "UP"'),
      cut("1", null, 'scenario_id == "DOWN"'),
    ];
    for (const [at, entry] of axis.entries()) expect(matchingEntry(axis, entry)).toBe(at);
    // And a fold is separated by its own cut in exactly the same way.
    const folds = [
      cut(null, "sum", 'scenario_id == "BASE"'),
      cut(null, "sum", 'scenario_id == "UP"'),
    ];
    for (const [at, entry] of folds.entries()) expect(matchingEntry(folds, entry)).toBe(at);
  });

  it("refuses a match two entries answer to rather than taking the first", () => {
    const twice = [entry("1"), entry("1")];
    expect(locateEntry(twice, entry("1"))).toBe("ambiguous");
    expect(matchingEntry(twice, entry("1"))).toBeNull();
    const doubled = { ...before, policies: [before.policies[0]!, before.policies[0]!] };
    const comparison = compare(after, doubled);
    expect(comparison.policyNote).toContain("more than one entry");
    // The model comparison still stands; only the numbers are withheld.
    expect(comparison.changes.filter((one) => one.mark === "model").map((one) => one.node)).toEqual([
      "maint_fee_pp@1",
    ]);
    expect(comparison.changes.every((one) => !one.moved)).toBe(true);
  });

  it("says nothing rather than comparing a policy the earlier file does not carry", () => {
    expect(matchingEntry([entry("1")], entry("42"))).toBeNull();
    const only = { ...before, policies: [{ ...before.policies[0]!, policy_id: "999" }] };
    const comparison = compare(after, only);
    expect(comparison.policyNote).toContain("1");
    // The model comparison still stands: a fingerprint is not a function of
    // which policy was sampled.
    expect(comparison.changes.filter((one) => one.mark === "model").map((one) => one.node)).toEqual([
      "maint_fee_pp@1",
    ]);
    expect(comparison.changes.every((one) => !one.moved)).toBe(true);
  });
});

describe("a node only one of the two documents holds", () => {
  const withoutOne = (artifact: Artifact, id: string): Artifact => ({
    ...artifact,
    nodes: artifact.nodes.filter((node) => node.id !== id),
  });

  it("is an addition where the later document holds it", () => {
    const comparison = compare(after, withoutOne(before, "maint_fee_pp@1"));
    const one = comparison.changes.find((change) => change.node === "maint_fee_pp@1");
    expect(one?.kind).toBe("added");
    expect(one?.mark).toBe("model");
    expect(one?.origin).toBeNull();
  });

  it("is a removal where only the earlier one does", () => {
    const comparison = compare(withoutOne(after, "maint_fee_pp@1"), before);
    const one = comparison.changes.find((change) => change.node === "maint_fee_pp@1");
    expect(one?.kind).toBe("removed");
    expect(one?.mark).toBe("model");
  });

  it("is a name-move only where the framework recorded one", () => {
    const renamed: ArtifactNode = {
      ...after.nodes.find((node) => node.id === "net_cf@1")!,
      id: "cashflow@1",
      column: "cashflow",
      provenance: "rename",
      reads: ["net_cf@1"],
    };
    const comparison = compare({ ...after, nodes: [...after.nodes, renamed] }, before);
    const one = comparison.changes.find((change) => change.node === "cashflow@1");
    expect(one?.kind).toBe("renamed");
    expect(one?.renamedFrom).toBe("net_cf@1");
  });
});

describe("the bases", () => {
  /** The same document as one written before documents recorded their book. */
  function withoutBook(artifact: Artifact): Artifact {
    const { book: _book, ...rest } = artifact;
    return rest;
  }

  it("reports the policy data on its digest and never on its path", () => {
    // Written before the book member, so the files the runs named decide.
    const moved = {
      ...withoutBook(after),
      model: { ...after.model, model_points: { path: "q2.parquet", fingerprint: "sha256:bb" } },
    };
    expect(baseChanges(withoutBook(before), moved)).toContainEqual({
      kind: "model_points",
      name: "q2.parquet",
      before: before.model.model_points?.fingerprint ?? null,
      after: "sha256:bb",
      reason: null,
    });
  });

  it("says nothing about the same data read from a new location", () => {
    const renamed = {
      ...after,
      model: {
        ...after.model,
        model_points: {
          path: "elsewhere/model_points_1k.parquet",
          fingerprint: after.model.model_points!.fingerprint,
        },
      },
    };
    expect(baseChanges(before, renamed).filter((one) => one.kind === "model_points")).toEqual([]);
  });
});

describe("the book each document was built over", () => {
  /** One fixture, stating the book the producer now writes into every document. */
  function withBook(artifact: Artifact, digest: string): Artifact {
    return { ...artifact, book: { columns: ["policy_id", "sum_assured"], digest } };
  }

  const q1 = `sha256:${"a".repeat(64)}`;
  const q2 = `sha256:${"b".repeat(64)}`;

  it("reports a changed book from its digests, with no file named by either run", () => {
    const earlier = withBook({ ...before, model: { ...before.model, model_points: null } }, q1);
    const later = withBook({ ...after, model: { ...after.model, model_points: null } }, q2);
    expect(baseChanges(earlier, later).filter((one) => one.kind === "model_points")).toEqual([
      { kind: "model_points", name: null, before: q1, after: q2, reason: null },
    ]);
  });

  it("names the change by the file the later run said it read", () => {
    const later = withBook(
      { ...after, model: { ...after.model, model_points: { path: "q2.parquet", fingerprint: "sha256:bb" } } },
      q2,
    );
    expect(baseChanges(withBook(before, q1), later).filter((one) => one.kind === "model_points")).toEqual([
      { kind: "model_points", name: "q2.parquet", before: q1, after: q2, reason: null },
    ]);
  });

  it("says nothing where the book is the same, whatever the two runs said of their files", () => {
    // One book written out twice: two file stamps, one content digest. The
    // content decides, as diff_artifacts decides it.
    const later = withBook(
      { ...after, model: { ...after.model, model_points: { path: "copy.parquet", fingerprint: "sha256:bb" } } },
      q1,
    );
    expect(baseChanges(withBook(before, q1), later).filter((one) => one.kind === "model_points")).toEqual([]);
  });

  it("falls back to the files the runs named where either document states no digest", () => {
    const unvouched = { ...after, book: { columns: [], digest: { omitted: "unavailable" } } };
    const moved = {
      ...unvouched,
      model: { ...after.model, model_points: { path: "q2.parquet", fingerprint: "sha256:bb" } },
    };
    expect(baseChanges(withBook(before, q1), moved)).toContainEqual({
      kind: "model_points",
      name: "q2.parquet",
      before: before.model.model_points?.fingerprint ?? null,
      after: "sha256:bb",
      reason: null,
    });
  });

  /** A document whose producer could not vouch for its book, and names no file. */
  function unvouched(artifact: Artifact, detail: string): Artifact {
    return {
      ...artifact,
      model: { ...artifact.model, model_points: null },
      book: { columns: ["policy_id"], digest: { omitted: "unavailable", detail } },
    };
  }

  it("writes a book nothing can compare as not compared, with the reason diff_artifacts gives", () => {
    const noBook =
      "No book was handed to the export: the graph was written from its calculations alone, with no policy data beside it.";
    const moved = baseChanges(unvouched(before, noBook), unvouched(after, noBook));
    expect(moved.filter((one) => one.kind === "model_points")).toEqual([
      {
        kind: "model_points",
        name: null,
        before: null,
        after: null,
        reason:
          "The two books could not be compared: neither document states a digest of its book " +
          "(No book was handed to the export: the graph was written from its calculations alone, " +
          "with no policy data beside it), and neither run named a file for its policy data to " +
          "compare instead. To compare them, export each model from the frame built over its book, " +
          "with every column the model reads in a type the format names, or name each run's file " +
          'with ModelIdentity.of("model.py", model_points="points.parquet"), passed to the export ' +
          "as GraphExportConfig(model=...).",
      },
    ]);
  });

  it("names each side's own account where only one could not vouch for its book", () => {
    const earlier = { ...withBook(before, q1), model: { ...before.model, model_points: null } };
    const later = unvouched(after, "The book could not be digested: Column 'term' has type Duration.");
    const [moved] = baseChanges(earlier, later).filter((one) => one.kind === "model_points");
    expect(moved?.before).toBe(q1);
    expect(moved?.after).toBeNull();
    expect(moved?.reason).toContain(
      "the later document states no digest of its book (The book could not be digested: Column 'term' has type Duration)",
    );
    expect(moved?.reason).toContain("neither run named a file");
  });
});

describe("the results file each run wrote", () => {
  /** The two results files the committed report was taken over. */
  const q1 = { path: "results_q1.parquet", fingerprint: `sha256:${"1".repeat(64)}` };
  const q2 = { path: "results_q2.parquet", fingerprint: `sha256:${"2".repeat(64)}` };

  /** One document, as though its run had named `results` when it was exported. */
  function withResults(artifact: Artifact, results: { path: string; fingerprint: string }): Artifact {
    return { ...artifact, model: { ...artifact.model, results } };
  }

  /** The same, for a block missing a member the format writes, which a reader still meets. */
  function withBlock(artifact: Artifact, results: Record<string, unknown>): Artifact {
    return withResults(artifact, results as unknown as { path: string; fingerprint: string });
  }

  /** The sentence for a comparison where the `side` run recorded no results file's checksum. */
  const notCompared = (side: string): string =>
    `The results files were not compared: the ${side} run recorded no checksum of a results ` +
    "file. If a results file from each run is to hand, run gspio compare on the later audit " +
    "file and both of them to see whether the two results agree.";

  it("finds what gspio diff found over the same two documents", () => {
    const comparison = compare(withResults(before, q2), withResults(before, q1));
    expect(comparison.bases).toEqual(
      resultsReport.data.map((one) => ({
        kind: one.kind,
        name: one.name,
        before: one.before,
        after: one.after,
        reason: one.reason ?? null,
      })),
    );
    expect(comparison.bases.map((one) => one.kind)).toEqual(["results"]);
    // The model and the book are one document compared with itself, so
    // nothing but the file moved — on the page as in the report.
    expect(comparison.changes).toEqual([]);
    expect(resultsReport.calculations).toEqual([]);
    expect(moved(comparison)).toBe(true);
    expect(comparison.resultsNote).toBeNull();
  });

  it("names the entry by the later run's file, else by the earlier one's", () => {
    const laterUnnamed = baseChanges(withResults(before, q1), withBlock(before, { fingerprint: q2.fingerprint }));
    const neither = baseChanges(
      withBlock(before, { fingerprint: q1.fingerprint }),
      withBlock(before, { fingerprint: q2.fingerprint }),
    );
    expect(laterUnnamed.map((one) => one.name)).toEqual(["results_q1.parquet"]);
    expect(neither.map((one) => one.name)).toEqual([null]);
  });

  it("says nothing where the same file was moved to another path", () => {
    const elsewhere = { path: "archive/results_q1.parquet", fingerprint: q1.fingerprint };
    const comparison = compare(withResults(before, elsewhere), withResults(before, q1));
    expect(comparison.bases).toEqual([]);
    expect(moved(comparison)).toBe(false);
    expect(comparison.resultsNote).toBeNull();
  });

  it("reads the results file after every other kind of data", () => {
    const bases = baseChanges(withResults(bookBefore, q1), withResults(bookAfter, q2));
    expect(bases.map((one) => one.kind)).toEqual(["model_points", "results"]);
  });

  it("compares nothing where only one run named a results file, and says which named none", () => {
    const earlierUnnamed = compare(withResults(before, q2), before);
    const laterUnnamed = compare(before, withResults(before, q1));
    expect(earlierUnnamed.bases).toEqual([]);
    expect(moved(earlierUnnamed)).toBe(false);
    expect(earlierUnnamed.resultsNote).toBe(notCompared("earlier"));
    expect(laterUnnamed.bases).toEqual([]);
    expect(laterUnnamed.resultsNote).toBe(notCompared("later"));
  });

  it("says nothing at all where neither run named a results file", () => {
    expect(before.model.results).toBeUndefined();
    expect(compare(after, before).resultsNote).toBeNull();
  });

  it("reads a block that states no checksum as recording none, whatever path it names", () => {
    for (const block of [{ path: "results_q2.parquet" }, { path: "results_q2.parquet", fingerprint: null }]) {
      const comparison = compare(withBlock(before, block), withResults(before, q1));
      expect(comparison.bases).toEqual([]);
      expect(comparison.resultsNote).toBe(notCompared("later"));
    }
  });

  it("names the fixture it was taken over, so a fixture written again without it fails here", () => {
    // Both sides are `compare-before`, so both carry its seal, its stamp and
    // its producer. A fixture restamped or exported again without the report
    // being written again would leave the report naming a seal no fixture
    // carries; tests/graph/test_diff_results.py names the command that writes
    // it again.
    const producer = before.producer as { name: string; version: string };
    const named: ComparedDocument = {
      graph_fingerprint: before.graph_fingerprint,
      document_digest: before.document_digest ?? null,
      created_at: before.created_at,
      producer: `${producer.name} ${producer.version}`,
      formulas_fingerprint: before.formulas_fingerprint ?? null,
    };
    expect(resultsReport.compared).toEqual({ before: named, after: named });
  });

  it("never points at gspio compare after an edit, because compare refuses that pair", () => {
    // compare-after and compare-before are two calculations (their graph
    // fingerprints differ), so compare binds neither results file to the
    // other's artifact. The entry says so and points at what works.
    expect(after.graph_fingerprint).not.toBe(before.graph_fingerprint);
    const comparison = compare(withResults(after, q2), withResults(before, q1));
    expect(comparison.bases.map((one) => one.kind)).toContain("results");
    expect(comparison.resultsMoved).toBe(RESULTS_OF_TWO_CALCULATIONS);
    expect(comparison.resultsMoved).not.toContain("run gspio compare on");
  });

  it("says what compare will and will not do where only the book moved", () => {
    expect(bookAfter.graph_fingerprint).toBe(bookBefore.graph_fingerprint);
    const comparison = compare(withResults(bookAfter, q2), withResults(bookBefore, q1));
    expect(comparison.resultsMoved).toBe(RESULTS_OVER_TWO_BOOKS);
  });

  it("still points at compare where only the file moved", () => {
    expect(compare(withResults(before, q2), withResults(before, q1)).resultsMoved).toBe(RESULTS_FILE_MOVED);
  });

  it("does not point the not-compared line at compare after an edit", () => {
    const note = compare(after, withResults(before, q1)).resultsNote;
    expect(note).toContain("gspio diff on the two audit files with --results");
    expect(note).not.toContain("run gspio compare on");
  });

  it("writes the two newer sentences in the words gspio diff prints", () => {
    // tests/graph/test_diff_results.py holds diff.py to these exact sentences.
    expect(RESULTS_OF_TWO_CALCULATIONS).toBe(
      "The results file differs between the two runs, and so does the model: the two audit " +
        "files state different graph fingerprints, so the files hold the numbers of two " +
        "different calculations. The calculations listed above are the ones whose numbers can " +
        "have moved. To see which did, and by how much, run gspio diff on the two audit files " +
        "with --results and the two results files, earlier first.",
    );
    expect(RESULTS_OVER_TWO_BOOKS).toBe(
      "The results file differs between the two runs, and so does the book the model ran over, " +
        "so the numbers can have moved with the data. To see which did, and by how much, run " +
        "gspio diff on the two audit files with --results and the two results files, earlier " +
        "first: it pairs the two books' policies and counts those only one of them holds.",
    );
    expect(RESULTS_READ).toBe(
      "The results file differs between the two runs. Both files were read, and the values " +
        "reported here compare them line by line and policy by policy.",
    );
  });

  it("says the file moved in the words gspio diff prints under the entry", () => {
    // tests/graph/test_diff_results.py holds diff.py to this exact sentence.
    expect(RESULTS_FILE_MOVED).toBe(
      "The results file differs between the two runs. A results file also records the " +
        "library versions and platform that wrote it, so this says the file moved, not that " +
        "any number did. To see whether the two results agree, run gspio compare on the later " +
        "audit file and the two results files.",
    );
  });
});

describe("a column whose values moved under definitions that did not", () => {
  /** The columns the overwrite route moves here: one line, and a line that reads it. */
  const OVERWRITTEN = ["claims@1", "net_cf@1"];

  /** A sample as a column rewritten to nine tenths of itself holds it. */
  function scaled(sample: unknown): unknown {
    if (Array.isArray(sample)) return sample.map(scaled);
    return typeof sample === "number" ? sample * 0.9 : sample;
  }

  /**
   * `artifact` as the overwrite route leaves its record: a recorded column
   * rewritten straight in the query plan moves the values the export sampled,
   * and nothing a fingerprint, the book or an assumption entry covers.
   */
  function overwritten(artifact: Artifact, ids: string[] = OVERWRITTEN): Artifact {
    return {
      ...artifact,
      nodes: artifact.nodes.map((node) =>
        ids.includes(node.id) ? { ...node, value_sample: scaled(node.value_sample) } : node,
      ),
    };
  }

  /** One document, as though its run had named `results` when it was exported. */
  function withResults(artifact: Artifact, results: { path: string; fingerprint: string }): Artifact {
    return { ...artifact, model: { ...artifact.model, results } };
  }

  const q1 = { path: "results_q1.parquet", fingerprint: `sha256:${"1".repeat(64)}` };
  const q2 = { path: "results_q2.parquet", fingerprint: `sha256:${"2".repeat(64)}` };

  const RECOMPUTE =
    "To find a line whose own operands do not give its result, recompute the model from its " +
    "audit file on a second engine with gspio run-artifact … --every-node, and compare that " +
    "with the model's own run, also written with --every-node, using gspio compare.";

  const UNEXPLAINED =
    "Nothing in the record explains the moves marked data beyond the specification's " +
    "tolerance: those lines' fingerprints, the book and the producer are the ones they were. " +
    RECOMPUTE;

  /** The node ids the page marks as data, sorted. */
  const dataMarked = (comparison: ReturnType<typeof compare>): string[] =>
    comparison.changes
      .filter((one) => one.mark === "data")
      .map((one) => one.node)
      .sort();

  it("says nothing in the record explains it, where both runs named their results files", () => {
    const comparison = compare(withResults(overwritten(before), q2), withResults(before, q1));
    expect(dataMarked(comparison)).toEqual([...OVERWRITTEN].sort());
    expect(comparison.changes.every((one) => one.mark === "data" && !one.agrees)).toBe(true);
    expect(comparison.dataCause).toBe("unexplained");
    expect(comparison.dataNote).toBe(UNEXPLAINED);
    expect(comparison.bases.map((one) => one.kind)).toEqual(["results"]);
  });

  it("says the same where only the later run named one", () => {
    const comparison = compare(withResults(overwritten(before), q2), before);
    expect(dataMarked(comparison)).toEqual([...OVERWRITTEN].sort());
    expect(comparison.dataCause).toBe("unexplained");
    expect(comparison.dataNote).toBe(UNEXPLAINED);
    expect(comparison.bases).toEqual([]);
    expect(comparison.resultsNote).not.toBeNull();
  });

  it("says the book moved where the report's policy data moved, and adds nothing", () => {
    const comparison = compare(bookAfter, bookBefore);
    const book = comparison.bases.find((one) => one.kind === "model_points");
    expect(book?.reason).toBeNull();
    expect(dataMarked(comparison).length).toBeGreaterThan(0);
    expect(comparison.dataCause).toBe("book");
    expect(comparison.dataNote).toBeNull();
  });

  it("does not say the book moved where a basis was re-sourced and a line was overwritten", () => {
    // `compare-after` re-sourced `lapse_rates`: the lines reading it moved
    // their fingerprints and are marked numbers. These two read no lapse, kept
    // their fingerprints, and are overwritten here: the basis explains nothing
    // about them.
    const untouched = ["mort_rate@1", "mort_rate_mth@1"];
    const comparison = compare(overwritten(after, untouched), before);
    expect(comparison.bases.map((one) => one.kind)).toEqual(["table"]);
    expect(dataMarked(comparison)).toEqual([...untouched].sort());
    expect(comparison.changes.some((one) => one.mark === "numbers")).toBe(true);
    expect(comparison.dataCause).toBe("unexplained");
    expect(comparison.dataNote).toBe(UNEXPLAINED);
  });

  it("says the books could not be compared where the report says so, and adds nothing", () => {
    const unvouched = (artifact: Artifact): Artifact => ({
      ...artifact,
      model: { ...artifact.model, model_points: null },
      book: { columns: ["point_id"], digest: { omitted: "unavailable", detail: "No book was handed to the export." } },
    });
    const comparison = compare(unvouched(overwritten(before)), unvouched(before));
    expect(dataMarked(comparison)).toEqual([...OVERWRITTEN].sort());
    expect(comparison.dataCause).toBe("uncompared");
    expect(comparison.dataNote).toBeNull();
  });

  it("says the producer changed between the runs, as a candidate and not as the cause", () => {
    const later = { ...overwritten(before), producer: { name: "gaspatchio", version: "1.0.1" } };
    const comparison = compare(later, before);
    expect(dataMarked(comparison)).toEqual([...OVERWRITTEN].sort());
    expect(comparison.dataCause).toBe("producer");
    expect(comparison.dataNote).toBe(
      "The producer changed between the runs, from gaspatchio 1.0.0 to gaspatchio 1.0.1, and " +
        "a new release can move a computed value with no definition moving: that may explain " +
        "the moves marked data, and the record does not say that it does. " +
        RECOMPUTE,
    );
  });

  /** The library one run states it ran under: the manifest's six keys and an import. */
  function onLibrary(artifact: Artifact, polars: string, sha: string, numpy = "2.3.1"): Artifact {
    return {
      ...artifact,
      producer: {
        name: "gaspatchio",
        version: "1.0.0",
        versions: {
          core_version: "1.0.0",
          extension_version: "1.0.0",
          extension_sha256: `sha256:${sha.repeat(64)}`,
          polars_version: polars,
          python_version: "3.13.0",
          platform: "macOS-15.7.9-x86_64-i386-64bit-Mach-O",
          imports: { numpy },
        },
      },
    };
  }

  it("names what moved in the library when the release did not, in diff's own words", () => {
    // One release on both sides, a different library under it: the record's
    // candidate is the library, and the sentence says which parts of it moved
    // rather than printing the one release twice.
    const later = onLibrary(overwritten(before), "1.43.0", "b", "2.4.0");
    const comparison = compare(later, onLibrary(before, "1.42.1", "a"));
    expect(dataMarked(comparison)).toEqual([...OVERWRITTEN].sort());
    expect(comparison.dataCause).toBe("producer");
    expect(comparison.dataNote).toBe(
      "The library changed between the runs (library: polars 1.42.1 → 1.43.0; extension sha " +
        "differs; numpy 2.3.1 → 2.4.0), and a new library can move a computed value with no " +
        "definition moving: that may explain the moves marked data, and the record does not " +
        "say that it does. " +
        RECOMPUTE,
    );
    expect(comparison.dataNote).not.toContain("from gaspatchio 1.0.0 to gaspatchio 1.0.0");
  });

  it("names the library beside a new release, where both moved", () => {
    const earlier = onLibrary(before, "1.42.1", "a");
    const later = onLibrary(overwritten(before), "1.43.0", "a");
    (later.producer as { version: string }).version = "1.0.1";
    const comparison = compare(later, earlier);
    expect(comparison.dataCause).toBe("producer");
    expect(comparison.dataNote).toContain(
      "from gaspatchio 1.0.0 to gaspatchio 1.0.1 (library: polars 1.42.1 → 1.43.0), and a new " +
        "release can move",
    );
  });

  it("does not offer the library where the record cannot say it moved", () => {
    // Withheld on one side, stated on the other: diff prints no library line
    // for that pair, and the page names no library as a candidate either.
    const later = { ...onLibrary(overwritten(before), "1.43.0", "b") };
    const earlier = {
      ...before,
      producer: { name: "gaspatchio", version: "1.0.0", versions: { omitted: "withheld" } },
    };
    const comparison = compare(later, earlier);
    expect(comparison.dataCause).toBe("unexplained");
  });

  it("says neither document names the policy, where neither does", () => {
    const unnamed = (artifact: Artifact): Artifact => ({
      ...artifact,
      policies: artifact.policies.map((entry) => ({ ...entry, policy_id: null })),
    });
    const comparison = compare(unnamed(overwritten(before)), unnamed(before));
    expect(dataMarked(comparison)).toEqual([...OVERWRITTEN].sort());
    expect(comparison.dataCause).toBe("unnamed");
    expect(comparison.dataNote).toBe(
      "Neither document names the policy its values were read from, so the moves marked data " +
        "may be two different rows of the book rather than one policy moving.",
    );
  });

  it("compares no values, and so claims nothing, where the earlier file carries another policy", () => {
    const elsewhere = { ...before, policies: [{ ...before.policies[0]!, policy_id: "999" }] };
    const comparison = compare(overwritten(before), elsewhere);
    expect(comparison.policyNote).not.toBeNull();
    expect(dataMarked(comparison)).toEqual([]);
    expect(comparison.dataNote).toBeNull();
  });

  it("writes no note where no column's values moved under unmoved definitions", () => {
    const comparison = compare(after, before);
    expect(dataMarked(comparison)).toEqual([]);
    expect(comparison.dataNote).toBeNull();
  });

  describe("the tolerance two runs of one model are held to (§11.1.12)", () => {
    const LINE = "claims@1";

    /**
     * The line's scale under the rule, taken here from the two documents
     * rather than from the module under test: the largest magnitude among its
     * own values and those of every node it reads, over both documents.
     */
    function scaleOf(documents: Artifact[]): number {
      const reads = before.nodes.find((node) => node.id === LINE)!.reads;
      let scale = 0;
      const visit = (value: unknown): void => {
        if (Array.isArray(value)) value.forEach(visit);
        else if (typeof value === "number" && Number.isFinite(value)) scale = Math.max(scale, Math.abs(value));
      };
      for (const document of documents) {
        for (const id of [LINE, ...reads]) visit(document.nodes.find((node) => node.id === id)?.value_sample);
      }
      return scale;
    }

    /** `before` with the line moved by `times` the rule's allowance at one period. */
    function nudged(times: number): Artifact {
      const scale = scaleOf([before]);
      const sample = before.nodes.find((node) => node.id === LINE)!.value_sample as number[];
      // A period whose value is not the largest, so the nudge leaves the scale where it was.
      const at = sample.findIndex((value) => value !== 0 && Math.abs(value) < scale);
      const moved = sample.map((value, period) => (period === at ? value + times * 1e-12 * scale : value));
      return { ...before, nodes: before.nodes.map((node) => (node.id === LINE ? { ...node, value_sample: moved } : node)) };
    }

    it("agrees just inside the rule, and no note claims the record has to explain it", () => {
      const later = nudged(0.9);
      expect(scaleOf([before, later])).toBe(scaleOf([before]));
      const comparison = compare(later, before);
      const line = comparison.byNode.get(LINE);
      expect(line?.mark).toBe("data");
      expect(line?.moved).toBe(true);
      expect(line?.agrees).toBe(true);
      expect(comparison.dataCause).toBe("unexplained");
      expect(comparison.dataNote).toBeNull();
    });

    it("does not agree just outside it, and the record has nothing to explain it with", () => {
      const comparison = compare(nudged(1.1), before);
      const line = comparison.byNode.get(LINE);
      expect(line?.mark).toBe("data");
      expect(line?.agrees).toBe(false);
      expect(comparison.dataNote).toBe(UNEXPLAINED);
    });
  });
});

describe("the book-wide reading gspio diff carries into the page", () => {
  /**
   * The values vector: one model a fee rate apart, over a revised book, with
   * `gspio diff`'s report taken over the two runs' results files
   * (`fixtures/values/export.py`). `tests/graph/test_diff_values.py` holds the
   * committed report to the code; this holds the page to the report.
   */
  const valuesBefore = load("values-before");
  const valuesAfter = load("values-after");
  const valuesReport = JSON.parse(
    readFileSync(new URL("../fixtures/values-report.json", import.meta.url), "utf8"),
  ) as Report & { values: BookMovement };
  const book = readMovement(JSON.stringify(valuesReport.values));
  const comparison = compare(valuesAfter, valuesBefore, 0, book);

  it("reads the block the command writes", () => {
    expect(book).not.toBeNull();
    expect(readMovement(null)).toBeNull();
    expect(readMovement("not json")).toBeNull();
  });

  it("reads the declared policy as the results files read it, line for line", () => {
    // Two readings of one definition: the page's, from the two documents' own
    // values, and the report's, from the two results files. Every line the
    // report paired by id, both ways: what moved, and by how much.
    expect(comparison.crossCheck).toBeNull();
    expect(disagreements(book!.declared!, book!.lines, comparison.byNode)).toEqual([]);
    const pageMoved = book!.lines
      .filter((line) => line.paired_by === "id" && comparison.byNode.get(line.node)?.moved === true)
      .map((line) => line.node);
    expect(pageMoved).toEqual(book!.declared!.lines.map((line) => line.node));
  });

  it("says so where the two readings part, and prefers neither", () => {
    // The mutation control: one magnitude off in the block, and the page names it.
    const off: BookMovement = {
      ...book!,
      declared: {
        ...book!.declared!,
        lines: book!.declared!.lines.map((line) =>
          line.node === "fee@1" ? { ...line, magnitude: 0.5 } : line,
        ),
      },
    };
    const parted = compare(valuesAfter, valuesBefore, 0, off).crossCheck;
    expect(parted).toContain("read policy P1 differently on fee@1");
    // And a line the block says moved that the page does not.
    const extra: BookMovement = {
      ...book!,
      declared: {
        ...book!.declared!,
        lines: [...book!.declared!.lines, { node: "waived@1", magnitude: 1, from_zero: false, period: null }],
      },
    };
    expect(compare(valuesAfter, valuesBefore, 0, extra).crossCheck).toContain("waived@1");
  });

  it("states each entry's movement over the book, worst first, and greys the identity-only", () => {
    const fee = comparison.bookByNode.get("fee@1")!;
    const waived = comparison.bookByNode.get("waived@1")!;
    const overBase = comparison.bookByNode.get("fee_over_base@1")!;
    // P2's premium was revised as well as the rate, so its fee moved furthest.
    expect(bookSaid(fee)).toBe("moved in 2 of 2 policies, worst 28.7% at P2");
    expect(bookSaid(overBase)).toBe("moved in 2 of 2 policies, from 0 at P1");
    expect(bookSaid(waived)).toBe("no number moved in 2 policies");
    expect(identityOnly(waived)).toBe(true);
    expect(identityOnly(fee)).toBe(false);
  });

  it("names the step that drills into the worst policy, for each version", () => {
    expect(drillIn("P1", comparison.sides.before, comparison.sides.after)).toEqual([
      "gspio calc-graph model.py model_points.csv --policies id:P1 -o before.audit.json",
      "gspio calc-graph model.py model_points.csv --policies id:P1 -o after.audit.json",
      "gspio diff before.audit.json after.audit.json --html policy.html",
    ]);
  });

  it("says the results files were read, in the words gspio diff prints", () => {
    expect(comparison.resultsMoved).toBe(RESULTS_READ);
    expect(compare(valuesAfter, valuesBefore).resultsMoved).toBe(RESULTS_OF_TWO_CALCULATIONS);
  });

  it("marks the same definitions the report does, with the block beside them", () => {
    const definitions = comparison.changes.filter((one) => one.mark !== "data").map((one) => one.node);
    expect([...definitions].sort()).toEqual([...valuesReport.calculations.map((one) => one.node)].sort());
  });
});

describe("a hole whose stamp moved, and the model's own files", () => {
  /**
   * The 0.9 setup's join, as the record leaves it: `sum_assured` arrived from a
   * file the model joined in plain Polars, so it is a hole carrying a stamp of
   * what it held, and an edit to that file moves its stamp and its values and
   * no node's digest. `gspio diff` names the hole as data that moved and gives
   * each line under it `cause: "hole"` (§14.2); the page says the same.
   */
  const HOLE = "sum_assured";
  /** The hole and the three lines that read it directly, whose samples move with it. */
  const UNDER = [HOLE, "itm@1", "claim_pp_death@1", "claim_pp_maturity@1"];
  const stamp = (digit: string): string => `sha256:${digit.repeat(64)}`;

  function doubled(sample: unknown): unknown {
    if (Array.isArray(sample)) return sample.map(doubled);
    return typeof sample === "number" ? sample * 2 : sample;
  }

  /** `artifact` with `sum_assured` a hole stamped `content`, and `moved` lines' samples doubled. */
  function holed(artifact: Artifact, content: string | null, moved: string[] = []): Artifact {
    return {
      ...artifact,
      holes: [{ column: HOLE, reason: "unrecorded", ...(content === null ? {} : { content }) }],
      nodes: artifact.nodes.map((node) => {
        const kind = node.id === HOLE ? "hole" : node.kind;
        const value_sample = moved.includes(node.id) ? doubled(node.value_sample) : node.value_sample;
        return { ...node, kind, provenance: node.id === HOLE ? null : node.provenance, value_sample };
      }),
    };
  }

  const dataMarked = (comparison: ReturnType<typeof compare>): [string, string[]][] =>
    comparison.changes
      .filter((one) => one.mark === "data")
      .map((one): [string, string[]] => [one.node, one.holes])
      .sort((a, b) => (a[0] < b[0] ? -1 : 1));

  it("names the hole underneath the model, between the book and the results", () => {
    const bases = baseChanges(holed(before, stamp("a")), holed(before, stamp("b")));
    expect(bases).toEqual([{ kind: "hole", name: HOLE, before: stamp("a"), after: stamp("b"), reason: null }]);
    expect(baseChanges(holed(before, stamp("a")), holed(before, stamp("a")))).toEqual([]);
  });

  it("says a hole stamped on one side could not be compared, in diff_artifacts's words", () => {
    const [entry] = baseChanges(holed(before, null), holed(before, stamp("b")));
    expect(entry).toEqual({
      kind: "hole",
      name: HOLE,
      before: null,
      after: stamp("b"),
      reason:
        "The hole sum_assured could not be compared: the earlier document records no stamp of " +
        "what the column held (it was written before holes carried one, or its producer could " +
        "not read the values), so nothing says whether it held the same values. A hole the frame " +
        "arrived holding is stamped by a producer that read it; export both runs from one that " +
        "does to compare them.",
    });
  });

  it("gives every line under the moved hole the hole as its cause, and owes no note", () => {
    const comparison = compare(holed(before, stamp("b"), UNDER), holed(before, stamp("a")));
    expect(dataMarked(comparison)).toEqual([...UNDER].sort().map((node): [string, string[]] => [node, [HOLE]]));
    expect(comparison.dataNote).toBeNull();
    expect(moved(comparison)).toBe(true);
  });

  it("keeps the comparison's own cause on a line that reads no moved hole", () => {
    const comparison = compare(
      holed(before, stamp("b"), [...UNDER, "inv_return_mth@1"]),
      holed(before, stamp("a")),
    );
    const marked = new Map(dataMarked(comparison));
    expect(marked.get("inv_return_mth@1")).toEqual([]);
    expect(marked.get("itm@1")).toEqual([HOLE]);
    expect(comparison.dataCause).toBe("unexplained");
    expect(comparison.dataNote).not.toBeNull();
  });

  it("lets a moved book outrank the hole, as gspio diff does", () => {
    const later = holed(before, stamp("b"), UNDER);
    const rebooked: Artifact = { ...later, book: { ...later.book!, digest: stamp("c") } };
    const comparison = compare(rebooked, holed(before, stamp("a")));
    expect(comparison.dataCause).toBe("book");
    expect(comparison.changes.every((one) => one.holes.length === 0)).toBe(true);
    expect(comparison.bases.map((one) => one.kind)).toEqual(["model_points", "hole"]);
  });

  it("reads the hole cause the report writes into the book-wide block", () => {
    const line = {
      node: "pv_prem@1",
      before_node: "pv_prem@1",
      paired_by: "id" as const,
      change: null,
      compared: true,
      moved: true,
      policies_compared: 3,
      policies_moved: 2,
      first_period_moved: null,
      max_relative: 0.1,
      from_zero: false,
      worst: { policy: "1", row: 0, period: null, before: 400, after: 440.00000000000006 },
      within_band: false,
      cause: "hole",
      holes: ["load"],
    };
    expect(bookSaid(line)).toBe("moved under the hole load in 2 of 3 policies, worst 10.0% at 1");
    expect(bookSaid({ ...line, cause: "unexplained", holes: null })).toBe(
      "moved in 2 of 3 policies, worst 10.0% at 1",
    );
  });

  /** One document as a run of `model` importing `modules`, in a directory of one repository. */
  function run(model: string, sha: string, modules?: { path: string; fingerprint: string | null }[]): Artifact {
    return {
      ...before,
      model: { ...before.model, source_path: model, source_sha: sha, ...(modules === undefined ? {} : { modules }) },
    };
  }

  it("states a helper module that moved beside an unmoved model file", () => {
    const was = run("model.py", stamp("m"), [{ path: "helper.py", fingerprint: stamp("h") }]);
    const now = run("model.py", stamp("m"), [{ path: "helper.py", fingerprint: stamp("k") }]);
    expect(sourceMoved(was, now)).toEqual({
      path: "model.py",
      before: stamp("m"),
      after: stamp("m"),
      modules: [{ path: "helper.py", before: stamp("h"), after: stamp("k") }],
    });
    // Stated, never counted: nothing else moved, so nothing moved.
    expect(moved(compare(now, was))).toBe(false);
    expect(compare(now, was).source).not.toBeNull();
  });

  it("pairs a copied model's helpers by their place beside it", () => {
    const helpers = (home: string, helper: string): { path: string; fingerprint: string }[] => [
      { path: `${home}/helper.py`, fingerprint: helper },
      { path: "shared/curves.py", fingerprint: stamp("c") },
    ];
    const was = run("q1/model.py", stamp("m"), helpers("q1", stamp("h")));
    expect(sourceMoved(was, run("q2/model.py", stamp("m"), helpers("q2", stamp("h"))))).toBeNull();
    expect(sourceMoved(was, run("q2/model.py", stamp("m"), helpers("q2", stamp("k"))))?.modules).toEqual([
      { path: "q2/helper.py", before: stamp("h"), after: stamp("k") },
    ]);
  });

  it("names a helper only one run imports with its missing side, and compares none it does not list", () => {
    const was = run("m/model.py", stamp("m"), []);
    const now = run("m/model.py", stamp("m"), [{ path: "m/rates.py", fingerprint: stamp("r") }]);
    expect(sourceMoved(was, now)?.modules).toEqual([{ path: "m/rates.py", before: null, after: stamp("r") }]);
    expect(sourceMoved(now, was)?.modules).toEqual([{ path: "m/rates.py", before: stamp("r"), after: null }]);
    expect(sourceMoved(run("m/model.py", stamp("m")), now)).toBeNull();
    expect(sourceMoved(run("model.py", stamp("m")), run("model.py", stamp("n")))).toEqual({
      path: "model.py",
      before: stamp("m"),
      after: stamp("n"),
      modules: [],
    });
  });
});
