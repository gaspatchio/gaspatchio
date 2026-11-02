// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * What the record says a model rests on beyond its own file, in the page's words.
 *
 * Four members an export now writes and a reviewer needs to read: the local
 * modules the model imports (`model.modules`), the library that produced the
 * values (`producer.versions`), why a document states no git revision
 * (`model.git`), and where each table was read from (`source_file`,
 * `shaped_by`). They are what `gspio verify --model` and `--assumptions` hold
 * against the files beside the model, so a page that left them out would show
 * a reviewer less than the verifier checks.
 *
 * The rule is the Model tab's: **every member is stated, and every absence is
 * a sentence.** A document written before a member existed says nothing about
 * it, and that reads differently from a producer that stated an empty list or
 * withheld the member on purpose; each of those is its own sentence, and
 * none of them is a blank. Nothing here is decided by the page: each sentence
 * is the reading the format gives the member, kept in one place so that the
 * drawer and its tests read the same words.
 */

import { shortFingerprint } from "./format";

/** One fact the drawer prints: the name it is filed under, its label, and its value. */
export interface Said {
  /** The member's path in the file, which the row is found by. */
  name: string;
  label: string;
  value: string;
  /** The whole value, where the row shows a shortened one. */
  title?: string;
}

/** What `model.git` is, read without assuming which of its three shapes it took. */
type Git = { commit?: unknown; dirty?: unknown; omitted?: unknown; detail?: unknown };

/**
 * The two git rows, saying why where the file records no revision.
 *
 * §7 gives `model.git` three shapes and each is a different sentence. A
 * revision is its commit and whether the working tree was dirty. `null` is the
 * one thing it means: git ran beside the model and found no working tree. The
 * unavailable form is git that could not answer — no git on `PATH`, a refusal,
 * no answer in time — with the producer's sentence saying which, and that
 * sentence is printed as the file writes it. A document written before the
 * member carries none, which is the fourth sentence.
 *
 * The dirty row is never "undefined". Where there is no revision there is no
 * working-tree state to report, and the row says so and why.
 *
 * @param git - The model block's `git` member, or undefined where it has none.
 * @returns The commit row's value and the dirty row's.
 */
export function gitSaid(git: unknown): { commit: string; dirty: string } {
  if (git === undefined) {
    return { commit: "no git commit recorded", dirty: "no git state recorded" };
  }
  if (git === null) {
    return {
      commit: "exported outside a git working tree",
      dirty: "no working tree, so no state to record",
    };
  }
  const read = git as Git;
  if (read.omitted === "unavailable") {
    const why = typeof read.detail === "string" && read.detail !== "" ? read.detail : "no reason was given";
    return {
      commit: `git could not answer: ${why}`,
      dirty: "not recorded, because git could not answer",
    };
  }
  return {
    commit: typeof read.commit === "string" ? read.commit : "no git commit recorded",
    dirty: typeof read.dirty === "boolean" ? String(read.dirty) : "no git state recorded",
  };
}

/** One entry of `model.modules`. */
interface ModuleEntry {
  path?: unknown;
  fingerprint?: unknown;
}

/**
 * The model's own files beside it: each local module it imports, with its stamp.
 *
 * `model.modules` is every file beside the model that its import statements
 * resolve to, path and the hash of its bytes. An empty list is a claim — the
 * model imports nothing from beside itself — and is said as one; a document
 * that carries no list says it records none. A module whose bytes the producer
 * could not read has a null fingerprint, and the row says that rather than
 * printing a blank where a stamp belongs.
 *
 * @param modules - The model block's `modules` member.
 * @returns One fact per module, or the one fact saying there are none.
 */
export function modulesSaid(modules: unknown): Said[] {
  if (!Array.isArray(modules)) {
    return [{ name: "model.modules", label: "modules", value: "no modules recorded" }];
  }
  if (modules.length === 0) {
    return [{ name: "model.modules", label: "modules", value: "imports nothing from beside itself" }];
  }
  return modules.map((entry: ModuleEntry, at) => {
    const path = typeof entry.path === "string" ? entry.path : "unnamed module";
    const name = `model.modules[${String(at)}]`;
    if (typeof entry.fingerprint !== "string") {
      return { name, label: path, value: "the producer could not read it" };
    }
    return { name, label: path, value: shortFingerprint(entry.fingerprint), title: entry.fingerprint };
  });
}

/** A whole sha-256, prefixed or bare: the one value this tab shortens. */
const DIGEST = /^(sha256:)?[0-9a-f]{64}$/;

/**
 * The library that produced the values: one fact per key the file states.
 *
 * `producer.versions` is the results manifest's own keys under its own
 * spelling, so each is printed under that spelling, in the file's order, and
 * nothing is renamed. The extension's digest is shortened to the eight a
 * reader compares, with the whole of it on the row's title; where the file
 * states a sentence instead of a digest — the extension on disk was no longer
 * the one loaded — the sentence is printed whole. `imports` is each installed
 * distribution the model imports, written `name version`, and an empty one is
 * said as a claim.
 *
 * The withheld form is a document committed as a golden, whose exporter was
 * asked not to state the machine it ran on; that is a decision the file
 * records, and the row says it was taken rather than that nothing is known.
 *
 * @param producer - The envelope's `producer` member.
 * @returns The facts, or the one fact saying why there are none.
 */
export function versionsSaid(producer: unknown): Said[] {
  const versions =
    typeof producer === "object" && producer !== null
      ? (producer as { versions?: unknown }).versions
      : undefined;
  const name = "producer.versions";
  if (typeof versions !== "object" || versions === null) {
    return [{ name, label: "versions", value: "no library versions recorded" }];
  }
  const stated = versions as Record<string, unknown>;
  if ("omitted" in stated) {
    return [
      {
        name,
        label: "versions",
        value:
          stated["omitted"] === "withheld"
            ? "withheld: the exporter was asked not to state them"
            : `not stated: ${String(stated["omitted"])}`,
      },
    ];
  }
  return Object.entries(stated).map(([key, value]): Said => {
    const at = `${name}.${key}`;
    if (key === "imports") return { name: at, label: key, value: importsSaid(value) };
    const text = typeof value === "string" ? value : JSON.stringify(value);
    if (DIGEST.test(text)) return { name: at, label: key, value: shortFingerprint(text), title: text };
    return { name: at, label: key, value: text };
  });
}

/** The installed distributions the model imports, as `name version`. */
function importsSaid(imports: unknown): string {
  if (typeof imports !== "object" || imports === null) return "no imports recorded";
  const entries = Object.entries(imports as Record<string, unknown>);
  if (entries.length === 0) return "none: the model imports nothing installed but the standard library";
  return entries.map(([distribution, version]) => `${distribution} ${String(version)}`).join(", ");
}

/**
 * Where a table was read from, as its entry records it.
 *
 * A path is the file the table was read from, relative to the model's root.
 * `null` is a table the model built from a frame in its own code, so no file
 * was named — an answer, not a gap. A table entry with no `source_file` at all
 * is a producer that could not say which, or a document written before the
 * member, and the sentence says the file does not say.
 *
 * @param entry - One assumption entry.
 * @returns The sentence for the Table panel's header.
 */
export function tableSourceSaid(entry: unknown): string {
  const read = typeof entry === "object" && entry !== null ? (entry as Record<string, unknown>) : {};
  if (!("source_file" in read)) return "the file does not say what this table was read from";
  const file = read["source_file"];
  if (file === null) return "built from a frame in code";
  return `read from ${String(file)}`;
}

/** One step of a table's recipe, as `shaped_by` records it. */
interface Step {
  step?: unknown;
  column?: unknown;
  from?: unknown;
  to?: unknown;
}

/**
 * One reshaping step in the words `gspio verify` uses for it.
 *
 * The same phrases, so the line a reviewer reads on the page and the line the
 * verifier prints about the same table are one sentence.
 */
function stepSaid(step: Step): string {
  const column = String(step.column);
  switch (step.step) {
    case "renamed":
      return `${column} renamed from ${String(step.from)}`;
    case "cast":
      return `${column} cast to ${String(step.to)}`;
    case "melted":
      return `${column} melted from the columns ${Array.isArray(step.from) ? step.from.map(String).join(", ") : String(step.from)}`;
    case "set":
      return `${column} set to a constant in code`;
    case "computed":
      return `${column} computed in code`;
    default:
      return `${column} built by ${String(step.step)}`;
  }
}

/**
 * What a table's recipe did to what it read, in one sentence, or nothing.
 *
 * A table whose recipe reshaped its file is not a plain read of that file, so
 * `gspio verify --assumptions` cannot hold it against the file: naming the
 * file names the file and not the recipe. That is what a reviewer holding
 * the file needs to know before they try, and it is said beside the file's
 * name. An empty or absent `shaped_by` is a plain read and gets no sentence.
 *
 * @param entry - One assumption entry.
 * @returns The sentence, or null where the recipe reshaped nothing.
 */
export function tableShapedSaid(entry: unknown): string | null {
  const read = typeof entry === "object" && entry !== null ? (entry as Record<string, unknown>) : {};
  const steps = read["shaped_by"];
  if (!Array.isArray(steps) || steps.length === 0) return null;
  const said = steps
    .filter((step): step is Step => typeof step === "object" && step !== null)
    .map(stepSaid)
    .join("; ");
  return `${said}: verify cannot hold this table against its file.`;
}
