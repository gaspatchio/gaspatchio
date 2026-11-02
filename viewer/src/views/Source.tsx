// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The model's own text, at the line that computed the number.
 *
 * Read from the file's sources section (§7.3). Until that section the
 * page could tell a reader that `maint_fee_pp` was written at `model.py:520`
 * and could not show them line 520; now the file carries the file, and this is
 * the tab that reads it. Nothing is fetched, ever — the page opens from a disk
 * and reads the document it is part of, and a source view that reached for a
 * path on the reader's machine would be showing a file nothing in the document
 * identifies.
 *
 * **It reads both ways, which is the point of it.** From a number to its line:
 * the proof's footer is a control and it opens this tab at that file and line,
 * with the line marked and the file's own path and digest above it. And from a
 * line back to a column: a line the export accounted for carries that column's
 * name in the margin and selects it when clicked, so the model's text is a way
 * into the graph and not only a thing to look at.
 *
 * **A line no node claims stays plain, and that is worth seeing.** It is code
 * the record does not account for — a helper, a comment, an import, or a
 * calculation the export missed — and a page that marked every line, or that
 * drew something hopeful in the margin, would have taken away the one reading
 * this view offers that a text editor does not.
 *
 * **Where the file carries no text, the tab says which of the three reasons it
 * is** (§6.1), in the form every refusal takes: what the file claimed, what is missing,
 * and the one move. The three are three sentences and not one with three
 * spellings — `size` says what fetching it would cost, `unavailable` says the
 * producer's own account is short, `withheld` says the account is complete and
 * was not given — so this tab says the one the file said and never a summary of
 * all three.
 *
 * **The text can be taken out whole**, from a control beside the digest in the
 * head. What it copies is the payload exactly as the document carries it —
 * every byte, no line numbers, no margin — because that is the only thing that
 * can be checked against the digest sitting next to the control, and that
 * adjacency is why the control stands where it does: what is copied is beside
 * what it is stamped with.
 */

import { useEffect, useMemo, useRef } from "react";
import type { JSX } from "react";

import { useVirtualizer } from "@tanstack/react-virtual";

import { shortFingerprint } from "../reader/format";
import type { Index, SourceAt } from "../reader/index";
import type { SourceEntry } from "../reader/types";
import type { SelectionAction } from "../state/selection";
import { Copy } from "./Copy";
import { highlight } from "./python";

import "./Source.css";

/** One line's height, in pixels. The grid's row height, so code and values scan alike. */
const LINE_HEIGHT = 18;

/** The file's own bytes, counted off the text the document carries. */
function bytesOf(text: string): number {
  // The format states that an inlined payload is the file's bytes decoded as
  // UTF-8 and that it re-encodes to those same bytes exactly — which is the
  // property the digest beside it is checked with. So this is the size of the
  // file, not an estimate of it.
  return new TextEncoder().encode(text).length;
}

/** A number with the thousands separators a reader reads it with. */
function grouped(count: number): string {
  return count.toLocaleString("en-US");
}

/** One sentence, said where the file would have been. */
function Missing({ which, sentence }: { which: string; sentence: string }): JSX.Element {
  return (
    <div className="panel" data-panel="source">
      <p className="refusal-sentence source-missing" data-testid="source-missing" data-missing={which}>
        {sentence}
      </p>
    </div>
  );
}

/**
 * What the tab says about a payload that carries no text.
 *
 * @param entry - The §7.3 entry, whose payload said why.
 * @returns The reason's own name, and the sentence for it.
 */
function omission(entry: SourceEntry): { which: string; sentence: string } {
  const payload = entry.payload as { omitted?: string; bytes?: number };
  const reason = payload.omitted ?? "unrecorded";
  if (reason === "withheld") {
    return {
      which: "withheld",
      sentence:
        `The file names ${entry.path} and stamps it, and records its text as withheld: the ` +
        `producer held the text and was asked not to disclose it, which is a decision this ` +
        `document records rather than a silence. Nothing on this page can recover it. Export ` +
        `again with gspio calc-graph --source, which is the default, and the text travels; the ` +
        `digest above is what a copy you already hold can be checked against.`,
    };
  }
  if (reason === "size") {
    const weight = typeof payload.bytes === "number" ? `${grouped(payload.bytes)} bytes` : "a size it did not state";
    return {
      which: "size",
      sentence:
        `The file names ${entry.path} and stamps it, and records its text as omitted for size ` +
        `at ${weight} — weighed, and above the inline budget this export was written under. ` +
        `Open that file where it sits and check it against the digest above, which is the one ` +
        `this document published for it.`,
    };
  }
  if (reason === "unavailable") {
    return {
      which: "unavailable",
      sentence:
        `The file names ${entry.path} and records its text as unavailable: the producer could ` +
        `not read it from where it was standing — a file that had moved, bytes that are not ` +
        `text, or a path leaving the model root this document speaks for — so it took no digest ` +
        `either. Export again from the tree that holds that file and the text travels with it.`,
    };
  }
  return {
    which: "unrecorded",
    sentence:
      `The file names ${entry.path} and its payload carries neither text nor one of the three ` +
      `reasons this format defines for leaving text out, so this page has nothing to show and ` +
      `nothing to say about why. Run gspio validate over the file, which is where a payload ` +
      `that does not match the schema is reported.`,
  };
}

/** The Source tab: one file of the model, at one line of it. */
export function Source({
  index,
  at,
  dispatch,
}: {
  index: Index;
  /** The file and line to open at, or null where nothing has named one. */
  at: SourceAt | null;
  dispatch: (action: SelectionAction) => void;
}): JSX.Element {
  const scroll = useRef<HTMLDivElement>(null);
  const path = at?.path ?? null;
  const entry = path === null ? undefined : index.sources.get(path);
  const text =
    entry !== undefined && "text" in entry.payload ? entry.payload.text : null;

  // Split once per file rather than once per render of a row. A trailing
  // newline would otherwise show as a final empty line the file does not have.
  const lines = useMemo(() => {
    if (text === null) return [];
    const all = text.split("\n");
    if (all.length > 1 && all[all.length - 1] === "") all.pop();
    return all;
  }, [text]);

  // Coloured once per file, not once per row: the tokeniser reads the whole
  // file because a docstring's colour depends on a line above it. Python only —
  // a file this tokeniser does not claim to read is drawn in one ink rather
  // than coloured by a grammar that is not its own.
  const coloured = useMemo(() => {
    if (text === null || path === null || !path.endsWith(".py")) return null;
    const all = highlight(text);
    all.length = Math.min(all.length, lines.length);
    return all;
  }, [text, path, lines.length]);

  const claims = path === null ? undefined : index.accountedLines.get(path);

  const virtual = useVirtualizer({
    count: lines.length,
    getScrollElement: () => scroll.current,
    estimateSize: () => LINE_HEIGHT,
    overscan: 20,
  });

  // Open on the line the reader came for. A file scrolled to the top is a file
  // with the answer in it and no way to see the answer; any scrolling after
  // this is theirs.
  const line = at?.line ?? null;
  useEffect(() => {
    if (line !== null && line >= 1 && line <= lines.length) {
      virtual.scrollToIndex(line - 1, { align: "center" });
    }
  }, [line, lines.length, virtual]);

  if (path === null) {
    return (
      <div className="panel" data-panel="source">
        <p className="prompt">
          Select a column and open its source location from the proof panel&apos;s footer to read
          the line it was written on.
        </p>
      </div>
    );
  }

  if (!index.carriesSources) {
    return (
      <Missing
        which="no-section"
        sentence={
          `This file carries no sources section at all: it names ${path} on its nodes and ` +
          `carries no line of it, so there is nothing here to show. The section is the one ` +
          `optional array in the envelope — a document written before it existed has none, ` +
          `and a producer may leave it out — so export again with a gaspatchio that writes ` +
          `gaspatchio-graph/v0-preview.2 or later, where the text travels by default.`
        }
      />
    );
  }

  if (entry === undefined) {
    return (
      <Missing
        which="no-entry"
        sentence={
          `The file's sources section has no entry for ${path}, though a node names it as where ` +
          `its calculation was written. The section is built from those same locations, so a ` +
          `path present on a node and absent here is a file this document does not account for. ` +
          `Run gspio validate over it, which is where that disagreement is reported.`
        }
      />
    );
  }

  if (text === null) {
    const said = omission(entry);
    return <Missing which={said.which} sentence={said.sentence} />;
  }

  const drawn = virtual.getVirtualItems();
  const first = drawn[0];
  const last = drawn[drawn.length - 1];
  const above = first === undefined ? 0 : first.start;
  const below = last === undefined ? 0 : virtual.getTotalSize() - last.end;
  // The one guarantee §7.3 states on its own: the entry whose path is the
  // model's carries exactly the digest the envelope publishes beside it. Said
  // here because it is the difference between showing a model and showing the
  // model that ran, and it is a comparison of two strings in the file rather
  // than anything this page computed.
  const ran =
    path === index.artifact.model.source_path &&
    entry.fingerprint !== null &&
    entry.fingerprint === index.artifact.model.source_sha;

  return (
    <div className="panel source-panel" data-panel="source">
      <div className="source-head">
        <span className="source-path mono" data-testid="source-path">
          {path}
        </span>
        <span className="source-size mono" data-testid="source-bytes">
          {grouped(bytesOf(text))} bytes
        </span>
        <span
          className="chip fingerprint-chip mono"
          title={entry.fingerprint ?? "no fingerprint recorded"}
        >
          <span data-testid="source-fingerprint">{shortFingerprint(entry.fingerprint ?? "")}</span>
        </span>
        {/* The payload as the document carries it, not the split lines: a
            trailing newline is a byte of the file, and the one thing the
            digest beside this control can be checked against is the file. */}
        <Copy
          what={() => text}
          name="file"
          title="copy this file's text, exactly as the document carries it"
          className="copy-file"
          testid="copy-source"
        />
        {ran ? (
          <span className="source-ran" data-testid="source-ran">
            the source that ran
          </span>
        ) : null}
      </div>
      <div className="source-scroll" ref={scroll}>
        <div className="source-lines" style={{ paddingTop: above, paddingBottom: below }}>
          {drawn.map((item) => {
            const number = item.index + 1;
            const accounting = claims?.get(number) ?? [];
            // A line the export accounted for is itself the way into the graph
            // at that column, because that is what the line is: clicking it does
            // what clicking the column's own heading in the grid does. Where a
            // line defines more than one, the whole line takes the first and the
            // chips in the margin pick between them. The chips stay buttons —
            // they are the control a keyboard reaches, and the row is the target
            // a pointer already wants to hit.
            const first = accounting[0];
            return (
              <div
                key={number}
                className={
                  `source-row${number === line ? " hit" : ""}` +
                  (first === undefined ? "" : " claimed")
                }
                data-line={number}
                style={{ height: LINE_HEIGHT }}
                {...(number === line ? { "data-hit": "true" } : {})}
                {...(first === undefined
                  ? {}
                  : {
                      onClick: () => {
                        dispatch({ select: first });
                      },
                    })}
              >
                <span className="source-ln">{number}</span>
                <code className="source-code">
                  {coloured === null
                    ? lines[item.index]
                    : // Keyed by position, which is stable here because the file
                      // cannot change under the page: the tokens of one line of
                      // an immutable document, in the order they appear in it.
                      (coloured[item.index] ?? []).map((token, i) => (
                        <span key={i} className={`t-${token.kind}`}>
                          {token.text}
                        </span>
                      ))}
                </code>
                <span className="source-accounts">
                  {accounting.map((id) => (
                    <button
                      key={id}
                      type="button"
                      className="source-account"
                      data-accounts={index.nodes.get(id)?.column ?? id}
                      title={`select ${index.nodes.get(id)?.column ?? id}`}
                      onClick={(event) => {
                        // The row behind it would otherwise take the first
                        // column, which on a line defining two is not the one
                        // the reader just pointed at.
                        event.stopPropagation();
                        dispatch({ select: id });
                      }}
                    >
                      {index.nodes.get(id)?.column ?? id}
                    </button>
                  ))}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
