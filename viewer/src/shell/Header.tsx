// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * Which file this is: the identity strip, top right.
 *
 * Five facts, all of them the envelope's own — the model file the graph was
 * taken from, the policy whose timeline the values are, the profile the file
 * claims, the graph fingerprint a reviewer quotes back, and whether the file
 * admits to holes. Nothing here is derived and nothing is recomputed; the
 * fingerprint in particular is the one the producer wrote, shown truncated
 * because that is the part anybody reads aloud, with the whole of it on the
 * clipboard and in the control's own title.
 *
 * The holes chip is a control and not a label. It opens the
 * drawer on the Model tab, where the holes are listed with their reasons, so
 * that the count and the account of it are one click apart rather than one
 * search apart.
 *
 * **The policy is a control too, where the file carries more than one.**
 * It is here and not a fifth drawer tab because "whose numbers am I looking
 * at" already lives here, next to the file's name and its fingerprint. Each
 * entry reads as its id followed by the producer's own sentence saying how it
 * came to be in the file — §7.4's `why`, verbatim, because a list of ids would
 * throw away the one thing the axis carries that a reader cannot work out for
 * themselves. A file carrying one policy draws no control: there is nothing to
 * switch to, and a select with a single option is a thing that looks operable
 * and is not. That policy's `why` is still in the file and still shown — the
 * drawer's Model tab prints it, where the rest of the envelope is.
 *
 * Nothing about the choice is remembered. A file you send someone
 * opens the way your page opens, on the entry the producer put first — unless
 * the link they followed named an entry, which is somebody pointing at one on
 * purpose.
 *
 * **The link control sits beside this strip and not in it**, in `App.tsx`. The
 * two are the pair somebody pastes into one message — the fingerprint is what
 * this file *is*, the link is where the reader is *standing* in it — so they
 * stand side by side on the screen. What keeps them apart in the markup is
 * that everything drawn here is a fact, and a verb among the facts reads as
 * one of them. The four scripted reads read this strip back as a sentence,
 * which is the check on that.
 *
 * **One line here is not the envelope's**, and on a page of one document it is
 * the only one: where a link asked for a column, a policy or a period this file
 * does not carry, it says so. It belongs beside the facts because it is a
 * statement about which page this is, and it is a note rather than a refusal —
 * a link is often a quarter old by the time it is followed, and a page that
 * would not open is worse to its reader than a page that opens and says what
 * has moved.
 *
 * **A comparison page names both documents here**, and it names them
 * before anything on the page says what changed. The two `created_at`s and the
 * two seals, in that order, earlier first: a page that told a committee what
 * moved without saying which two files it read would be a finding with no
 * subject, which is the same reason §14.2's report carries `compared`. The
 * later document's own fingerprint stays where it was — it is what this page
 * *is* — and the earlier one sits beside it as what it is being read against.
 *
 * **Where the command named the two sides, the names come first.** A side read
 * from a revision of a repository is told apart by that revision, which neither
 * its date nor its seal says, so `gspio diff` hands each document a label and
 * the page shows it before that side's date, as the command wrote it. Like the
 * link note it is not the document's own statement about itself, and it is
 * text: it is never read as markup. Where the strip has no room for the whole
 * of it, it gives way from its start and keeps its end in sight, because the
 * end of a path at a revision is the revision; the whole of it is on its
 * title. A page carrying one document names its model and its graph rather
 * than the file it was read from, so it has no place for a label and shows
 * none.
 */

import { useState } from "react";
import type { JSX } from "react";

import type { Comparison } from "../reader/compare";
import { isFold } from "../reader/fold";
import { shortFingerprint } from "../reader/format";
import type { Index } from "../reader/index";
import { policyName } from "../reader/policies";
import type { Policy } from "../reader/types";

/**
 * The model file's name, as the artifact states it.
 *
 * The envelope's path is written against the model's root, so its last segment
 * is the file name and the rest is where the model sat. A file that names no
 * source says so: the page does not invent one.
 */
export function modelFileName(index: Index): string {
  const path = index.artifact.model.source_path;
  if (path === null) return "no model file named";
  return path.split("/").pop() ?? path;
}

/**
 * What one entry of the axis is called.
 *
 * The id the file carries, and the sentence saying nothing where it carries
 * none: an export selecting by row position over a book with no identifier
 * column has a policy and no name for it, and "no id recorded" is what the
 * file says about that. The `why` beside it carries the row either way.
 *
 * A fold of the book is named by its fold. Its `policy_id` is null too, and
 * "no id recorded" would be the wrong sentence about it twice over: nothing
 * failed to be identified, and there is no policy there to identify.
 *
 * @param entry - One entry of `policies`.
 * @returns The fold's name, the id, or the sentence standing in for one.
 */
function policyLabel(entry: Policy): string {
  return policyName(entry) ?? "no id recorded";
}

/**
 * When a document says it was written, cut to the day.
 *
 * The strip is a row of short facts and a full ISO stamp is nineteen
 * characters of which eight are the answer; the whole of it is on the title,
 * where the reader who needs the minute finds it.
 */
function dayOf(createdAt: string): string {
  return createdAt.slice(0, 10);
}

/** The identity strip. */
export function Header({
  index,
  note,
  choosePolicy,
  showHoles,
  comparison,
  label,
  earlierLabel,
}: {
  index: Index;
  /** What the link this page was opened from asked for and this file lacks. */
  note: string | null;
  /** Read the values along another entry of the axis. */
  choosePolicy: (at: number) => void;
  /** Open the drawer on the Model tab, which is where the holes are accounted for. */
  showHoles: () => void;
  /** The two documents and what moved between them, on a comparison page. */
  comparison?: Comparison | undefined;
  /** The name the command gave the later document, shown on a comparison page. */
  label?: string | undefined;
  /** The name it gave the earlier one. */
  earlierLabel?: string | undefined;
}): JSX.Element {
  const [copied, setCopied] = useState<boolean | null>(null);
  const fingerprint = index.artifact.graph_fingerprint;
  const axis = index.policies;
  const holes = index.artifact.holes.length;
  // `audit` is what an export is unless somebody asked for the other one, so
  // the ordinary case says nothing and the other one says what it claims.
  const profile = index.artifact.profile === "executable" ? index.artifact.profile : null;

  /**
   * Put the whole fingerprint on the clipboard, and say which way it went.
   *
   * A browser that refuses the write — some do, from a file on a disk — is
   * told so rather than quietly told nothing, because a control that always
   * says "copied" is a control a reviewer cannot trust the one time it mattered.
   */
  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(fingerprint);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="identity">
      {note === null ? null : (
        <span className="fact link-note" data-testid="link-note" title={note}>
          {note}
        </span>
      )}
      {axis.length === 0 ? null : axis.length === 1 ? (
        <span className="fact" title={axis[0]?.why}>
          {isFold(index.policy) ? "portfolio" : "policy"} <b className="mono">{policyLabel(axis[0]!)}</b>
        </span>
      ) : (
        <span className="fact policies">
          <label htmlFor="policy">{isFold(index.policy) ? "portfolio" : "policy"}</label>
          <select
            id="policy"
            className="policy-switcher mono"
            data-testid="policy-switcher"
            value={index.at}
            title={axis[index.at]?.why}
            onChange={(event) => {
              choosePolicy(Number(event.target.value));
            }}
          >
            {axis.map((entry, at) => (
              <option key={`${String(at)}:${policyLabel(entry)}`} value={at}>
                {policyLabel(entry)} — {entry.why}
              </option>
            ))}
          </select>
        </span>
      )}
      <span className="fact model">{modelFileName(index)}</span>
      {comparison === undefined ? null : (
        <span className="fact compared" data-testid="compared">
          {earlierLabel === undefined ? null : (
            <span className="named" data-testid="label-before" title={earlierLabel}>
              <span dir="ltr">{earlierLabel}</span>
            </span>
          )}
          <span className="against" title={comparison.before.artifact.created_at}>
            {dayOf(comparison.before.artifact.created_at)}
          </span>
          <b
            className="mono seal"
            data-testid="seal-before"
            title={comparison.before.artifact.document_digest ?? "this document carries no seal"}
          >
            {comparison.before.artifact.document_digest === undefined
              ? "unsealed"
              : shortFingerprint(comparison.before.artifact.document_digest)}
          </b>
          <span className="to">→</span>
          {label === undefined ? null : (
            <span className="named" data-testid="label-after" title={label}>
              <span dir="ltr">{label}</span>
            </span>
          )}
          <span className="against" title={index.artifact.created_at}>
            {dayOf(index.artifact.created_at)}
          </span>
          <b
            className="mono seal"
            data-testid="seal-after"
            title={index.artifact.document_digest ?? "this document carries no seal"}
          >
            {index.artifact.document_digest === undefined
              ? "unsealed"
              : shortFingerprint(index.artifact.document_digest)}
          </b>
        </span>
      )}
      {profile === null ? null : (
        <span className="fact profile" data-testid="profile">
          {profile}
        </span>
      )}
      <button
        type="button"
        className="fingerprint mono"
        data-testid="fingerprint"
        {...(copied === null ? {} : { "data-copied": String(copied) })}
        title={fingerprint}
        onClick={() => {
          void copy();
        }}
      >
        {shortFingerprint(fingerprint)}
      </button>
      {holes === 0 ? null : (
        <button
          type="button"
          className="chip holes"
          data-testid="holes-chip"
          title="the columns this model does not account for"
          onClick={showHoles}
        >
          {holes} {holes === 1 ? "hole" : "holes"}
        </button>
      )}
    </div>
  );
}
