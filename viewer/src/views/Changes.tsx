// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * What moved, ranked, with the floor in the reader's hand.
 *
 * The changes list. Three kinds of entry, never blurred, each marked in a
 * word rather than in a colour: **the model moved** — a formula edited, a
 * column added, one stopped being computed — **the numbers moved**, which is a
 * formula standing still over an answer that cannot be what it was, and **the
 * book moved**, the kind added last: every digest this column
 * carries is the digest it carried and the values are not the values they
 * were, because the run was over different model points. The first is exact.
 * The other two are ranked together by how far they moved, and the page never
 * says how far is far enough.
 *
 * The three answer the three questions apart, which is the addendum's own
 * reason for a third mark rather than a wider second one: did the model
 * change, did an upstream definition change, did the book change. An actuary
 * asks the last of those first.
 *
 * **The *data* mark names the book only where the record does.** The mark is an
 * observation — the digests held and the numbers did not — and "the book
 * moved" is a second claim, made only where the two books differ. An
 * assumption cannot be the cause: its digest is inside every fingerprint that
 * reads it, so a re-sourced base marks its lines *numbers*. Where the books
 * could not be compared, where neither document names the policy, or where the
 * producer changed between the runs, the mark says that and claims nothing
 * more. Where none of those holds — a column recorded and then rewritten
 * straight in the query plan, for one — it says that nothing in the record
 * explains the move, and the panel names the check that finds the line. And a
 * line that moved by no more than §11.1.12 allows two runs of one model agrees
 * within the specification's tolerance, and says that instead.
 *
 * Selecting an entry selects that column, which is what makes the list a way
 * into the page rather than a report printed on it.
 *
 * **The results file is listed apart from the bases.** It is what the run
 * wrote rather than what the model rests on, so it has a heading of its own,
 * and its entry says what its digest is evidence of: the file moved, and
 * whether the two results agree is `gspio compare`'s to say. Where only one run
 * recorded a results file's checksum, that heading carries the line `gspio diff`
 * prints saying the two were not compared.
 *
 * **The panel is memoised, and its rows were already.** A comparison page
 * opens on this tab, so the whole of it — head, floor control and list —
 * re-rendered on every frame of a scrub, for three props a period step moves
 * none of. The inner memo covers the fifty rows; this one covers the panel
 * around them.
 */

import { memo, useMemo, useState } from "react";
import type { JSX } from "react";

import type { BaseChange, Change, Comparison, DataCause, SourceMoved } from "../reader/compare";
import { shortFingerprint } from "../reader/format";
import { bookSaid, drillIn, identityOnly } from "../reader/movement";
import type { BookLine } from "../reader/movement";
import type { SelectionAction } from "../state/selection";

import "./Changes.css";

/** What the *model* and *numbers* marks say, in the words the list prints beside the column. */
export const MARKS = {
  model: "the model moved",
  numbers: "the numbers moved",
} as const;

/**
 * What the *data* mark says, by what the record says moved under it.
 *
 * **the book moved** rather than "the data moved" where the book moved,
 * because the word a reviewer uses for a new quarter's model points is the
 * book. The mark itself stays *data*.
 */
export const DATA_SAID: Record<DataCause, string> = {
  book: "the book moved",
  uncompared: "the books could not be compared",
  unnamed: "neither document names this policy, so these may be two rows",
  producer: "the producer changed between the runs, which may explain this",
  unexplained: "nothing in the record explains this move",
};

/** What a *data* mark says where the line agrees within §11.1.12's tolerance. */
export const AGREES = "agrees within the specification's tolerance";

/** What a *data* mark says where a hole the line reads changed its stamp. */
export function holeSaid(holes: string[]): string {
  return `the ${holes.length === 1 ? "hole" : "holes"} ${holes.join(", ")} it reads moved`;
}

/** The sentence a mark's title carries on this comparison — the grid's and the cone's too. */
export function markSaid(change: Change, comparison: Comparison): string {
  if (change.mark !== "data") return MARKS[change.mark];
  if (change.agrees) return AGREES;
  return change.holes.length > 0 ? holeSaid(change.holes) : DATA_SAID[comparison.dataCause];
}

/**
 * The model's own files, where they moved: §14.2's `source`, one line each.
 *
 * Stated and never counted, as `gspio diff` prints it under its headline: the
 * model file where its two digests differ, and each helper module that moved.
 */
function SourceLines({ source }: { source: SourceMoved }): JSX.Element {
  const short = (digest: string | null): string => (digest === null ? "no stamp" : shortFingerprint(digest));
  return (
    <ol className="bases" data-testid="source">
      {source.before !== source.after ? (
        <li className="base" data-base="source" data-name={source.path ?? ""}>
          <span className="base-kind">model file</span>
          <span className="base-name mono">{source.path ?? "no path recorded"}</span>
          <span className="base-digests mono">
            {short(source.before)}
            {" → "}
            {short(source.after)}
          </span>
        </li>
      ) : null}
      {source.modules.map((module) => (
        <li className="base" data-base="module" data-name={module.path} key={module.path}>
          <span className="base-kind">helper module</span>
          <span className="base-name mono">{module.path}</span>
          <span className="base-digests mono">
            {short(module.before)}
            {" → "}
            {short(module.after)}
          </span>
        </li>
      ))}
    </ol>
  );
}

/** The short form of each mark, which is what the grid and the cone wear. */
export const SHORT_MARKS = {
  model: "model",
  numbers: "numbers",
  data: "data",
} as const;

/** What one `kind` says in words, for the entries that are not a plain edit. */
const KINDS: Record<Change["kind"], string> = {
  added: "added",
  removed: "removed",
  changed: "edited",
  renamed: "renamed",
};

/**
 * How far one entry moved, written for a reader.
 *
 * A percentage where there is a ratio, *from 0* where the earlier value was
 * zero and was never divided, *moved* where the two values are unequal and no
 * ratio describes the difference, and *no move here* where the digests say
 * something moved and this policy's sampled numbers are the numbers they were.
 * The last is not a contradiction and is not hidden: the basis under a column
 * can move without reaching the one policy on the page.
 */
export function magnitudeSaid(change: Change): string {
  if (!change.moved) return "no move here";
  if (change.fromZero) return "from 0";
  if (change.magnitude === null) return "moved";
  return `${(change.magnitude * 100).toPrecision(3)}%`;
}

/**
 * One moved base, written as the directory names it.
 *
 * A book the two documents give nothing to compare on is written too, with
 * the reason in place of the two digests: "arrived" and "gone" would say the
 * data came and went, when what happened is that nobody can tell. A results
 * file's two digests are followed by what they are evidence of, because two
 * digests of a file of numbers read as two sets of numbers.
 */
function BaseRow({ base, resultsMoved }: { base: BaseChange; resultsMoved?: string }): JSX.Element {
  return (
    <li className="base" data-base={base.kind} data-name={base.name ?? ""}>
      <span className="base-kind">{base.kind.replace("_", " ")}</span>
      <span className="base-name mono">{base.name ?? "no name recorded"}</span>
      {base.reason === null ? (
        <span className="base-digests mono">
          {base.before === null ? "arrived" : shortFingerprint(base.before)}
          {" → "}
          {base.after === null ? "gone" : shortFingerprint(base.after)}
        </span>
      ) : (
        <span className="base-digests" data-testid="base-reason">
          {base.reason}
        </span>
      )}
      {base.kind === "results" ? (
        <span className="base-digests" data-testid="base-results">
          {resultsMoved}
        </span>
      ) : null}
    </li>
  );
}


/** What a moved line inside §11.1.12's band is called, in its chip's title. */
export const WITHIN_BAND = "inside the specification's band: indistinguishable from arithmetic (§11.1.12)";

/** What a line whose definition moved and whose numbers all held is called. */
export const IDENTITY_ONLY = "identity only: the definition moved and no number did, in any policy";

/** One entry of the list: the column, its mark, how far it moved. */
function Row({
  change,
  said,
  selected,
  dispatch,
  book,
  drill,
}: {
  change: Change;
  /** What the mark's title says, which for a *data* mark depends on the record. */
  said: string;
  selected: boolean;
  dispatch: (action: SelectionAction) => void;
  /** How far this line moved over the whole book, where `gspio diff` measured it. */
  book: BookLine | undefined;
  /** The commands that open this line's worst policy, on the selected entry only. */
  drill: string[] | null;
}): JSX.Element {
  // Greyed and labelled, never hidden: a line the identity flags and the book
  // shows unmoved is the finding a reviewer reads this list for.
  const idle = book !== undefined && identityOnly(book);
  return (
    <li
      className={`change${selected ? " sel" : ""}${idle ? " identity-only" : ""}`}
      data-node={change.node}
      data-mark={change.mark}
      data-kind={change.kind}
    >
      <button
        type="button"
        className="change-open"
        onClick={() => {
          dispatch({ select: change.node });
        }}
      >
        <span className="change-column mono">{change.column}</span>
        <span className={`chip mark ${change.mark}`} title={said}>
          {SHORT_MARKS[change.mark]}
        </span>
        {change.kind === "changed" ? null : <span className="chip what">{KINDS[change.kind]}</span>}
        <span className="change-size mono" data-magnitude={change.magnitude ?? ""}>
          {magnitudeSaid(change)}
        </span>
        {change.period === null || !change.moved ? null : (
          <span className="change-where mono">period {change.period}</span>
        )}
      </button>
      {change.renamedFrom === null ? null : (
        <span className="change-from mono">from {change.renamedFrom}</span>
      )}
      {book === undefined ? null : (
        <span className="change-book" data-testid="change-book">
          {idle ? (
            <span className="chip what" title={IDENTITY_ONLY}>
              identity only
            </span>
          ) : null}
          {book.moved && book.within_band === true ? (
            <span className="chip what" title={WITHIN_BAND}>
              within band
            </span>
          ) : null}
          <span className="mono">{bookSaid(book)}</span>
        </span>
      )}
      {drill === null ? null : (
        <pre className="change-drill mono" data-testid="drill">
          {drill.join("\n")}
        </pre>
      )}
    </li>
  );
}

/**
 * What the book-wide reading covers, in one sentence above the list.
 *
 * How many policies both books hold, and the ones only one does; and, where
 * the two timelines start apart, that only the lines of one value per policy
 * were measured.
 */
function bookNote(comparison: Comparison): string {
  const book = comparison.book;
  if (book === null) return "";
  const { paired, joined, left } = book.rows;
  const named = (count: number, policies: string[]): string =>
    count === 0 ? "0" : `${String(count)} (${policies.join(", ")}${count > policies.length ? ", …" : ""})`;
  const periods = book.periods.reason === null ? "" : ` ${book.periods.reason}`;
  // A line that moved in the book and not for the policy this page carries is
  // in no entry above, because every entry is the page's own reading; it is
  // named here rather than left for the reader to infer from its absence.
  const elsewhere = book.lines
    .filter((line) => line.moved && !comparison.byNode.has(line.node))
    .map((line) => line.node);
  const others =
    elsewhere.length === 0
      ? ""
      : ` Moved in the book and not for this policy, so in no entry here: ${elsewhere.join(", ")}.`;
  return (
    `Over the whole book, as gspio diff read the two results files: ${String(paired)} ` +
    `policies compared, ${named(joined.count, joined.policies)} joined, ` +
    `${named(left.count, left.policies)} left.${periods}${others}`
  );
}

/** The changes list, its floor, and the bases underneath it. */
function List({
  comparison,
  selected,
  dispatch,
}: {
  comparison: Comparison;
  /** The node the rest of the page is looking at, so the list can mark it. */
  selected: string | null;
  dispatch: (action: SelectionAction) => void;
}): JSX.Element {
  // Held here and nowhere else. The floor is a reading aid, not a position:
  // it is not in the link (a link is where somebody is standing, not how much
  // of the list they had hidden) and it is not remembered, so a file you send
  // someone opens showing everything.
  const [floor, setFloor] = useState(0);

  // The list, memoised on the three things it is a function of — and the row
  // cursor is not one of them. **This is load-bearing rather than tidy**: a
  // comparison page opens on this tab, so without it a reader scrubbing
  // through eighty-three periods rebuilt fifty rows on every frame to say that
  // none of them had changed. A period step moves neither the two documents,
  // nor the floor, nor which column is selected.
  const rows = useMemo(() => {
    const cut = floor / 100;
    // The floor cuts only what it can be compared against. A model change has
    // no magnitude to be below a floor, a move out of zero was never divided
    // and has no ratio, and a move a ratio cannot describe is not a small move.
    const shown = comparison.changes.filter(
      (change) =>
        change.mark === "model" ||
        !change.moved ||
        change.fromZero ||
        change.magnitude === null ||
        change.magnitude >= cut,
    );
    return {
      hidden: comparison.changes.length - shown.length,
      list: (
        <ol className="changes" data-testid="changes">
          {shown.map((change) => {
            const book = comparison.bookByNode.get(change.node);
            const worst = book?.moved === true ? book.worst?.policy ?? null : null;
            return (
              <Row
                key={change.node}
                change={change}
                said={markSaid(change, comparison)}
                selected={change.node === selected}
                dispatch={dispatch}
                book={book}
                drill={
                  change.node === selected && worst !== null
                    ? drillIn(worst, comparison.sides.before, comparison.sides.after)
                    : null
                }
              />
            );
          })}
        </ol>
      ),
    };
  }, [comparison, floor, selected, dispatch]);

  // What the model rests on, and what the run wrote, each under its own
  // heading. §14.2 writes at most one results entry, and it is the last.
  const underneath = comparison.bases.filter((base) => base.kind !== "results");
  const wrote = comparison.bases.find((base) => base.kind === "results");

  return (
    <div className="panel changes-panel" data-panel="changes">
      <div className="changes-head">
        <span className="counted" data-testid="changes-count">
          {comparison.changes.length} {comparison.changes.length === 1 ? "change" : "changes"}
        </span>
        <label className="floor" htmlFor="floor">
          hide moves under
          <input
            id="floor"
            className="mono"
            data-testid="floor"
            type="number"
            min={0}
            step={0.1}
            value={floor}
            onChange={(event) => {
              const said = Number(event.target.value);
              setFloor(Number.isFinite(said) && said >= 0 ? said : 0);
            }}
          />
          %
        </label>
        {rows.hidden === 0 ? null : (
          <span className="cut" data-testid="floor-cut">
            {rows.hidden} below the floor
          </span>
        )}
      </div>

      {comparison.book === null ? null : (
        <p className="says" data-testid="book-note">
          {bookNote(comparison)}
        </p>
      )}

      {comparison.crossCheck === null ? null : (
        <p className="says finding" data-testid="cross-check">
          {comparison.crossCheck}
        </p>
      )}

      {comparison.dataNote === null ? null : (
        <p className="says" data-testid="data-note">
          {comparison.dataNote}
        </p>
      )}

      {comparison.policyNote === null ? null : (
        <p className="says" data-testid="policy-note">
          {comparison.policyNote}
        </p>
      )}

      {comparison.changes.length === 0 ? (
        <p className="says">
          Nothing in the model moved between these two documents: every node holds the
          fingerprint it held.
        </p>
      ) : (
        rows.list
      )}

      {underneath.length === 0 ? null : (
        <>
          <h2 className="changes-sub">underneath the model</h2>
          <ol className="bases" data-testid="bases">
            {underneath.map((base) => (
              <BaseRow key={`${base.kind}:${base.name ?? ""}:${base.after ?? ""}`} base={base} />
            ))}
          </ol>
        </>
      )}

      {comparison.source === null ? null : (
        <>
          <h2 className="changes-sub">the model's own files</h2>
          <p className="says">
            Stated, not counted: a file's bytes move with a comment as well as a formula, and the
            list above says whether any calculation moved with them.
          </p>
          <SourceLines source={comparison.source} />
        </>
      )}

      {wrote === undefined && comparison.resultsNote === null ? null : (
        <>
          <h2 className="changes-sub">the results file</h2>
          {wrote === undefined ? null : (
            <ol className="bases" data-testid="results">
              <BaseRow base={wrote} resultsMoved={comparison.resultsMoved} />
            </ol>
          )}
          {comparison.resultsNote === null ? null : (
            <p className="says" data-testid="results-note">
              {comparison.resultsNote}
            </p>
          )}
        </>
      )}
    </div>
  );
}

export const Changes = memo(List);
