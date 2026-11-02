// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The tier census, in the strip beside the file's identity.
 *
 * Three counts, every tier stated and a zero included: how many of the model's
 * calculations the format's own vocabulary accounts for, how many reach into
 * one engine's own expression language, and how many reach an operation
 * nothing has classified. It sits beside the identity, after the holes chip,
 * because the two answer neighbouring questions and the first is easily read
 * as the second: a file with no holes accounts for every column, and that
 * says nothing about whether every line is in the format's own vocabulary.
 *
 * Where a calculation sits below core, the census opens to name them, the
 * first five at each tier as `gspio calc-graph` names them, each one a way to
 * select its node; past five, "and N more" opens the drawer's Model tab, which
 * names every one. A census of core lines alone has nothing to name and is
 * not a control.
 *
 * **Not on a comparison page.** The strip there names two documents, and a
 * census beside them would be one document's account standing beside two;
 * there is also no room for it on the strip's one line. The drawer's Model tab
 * states the later document's census with the rest of its envelope.
 *
 * A file that records no tier says nothing here rather than three zeros, and
 * so does one that leaves a calculation without a tier the format defines:
 * there is no census to state, and the Model tab says which.
 */

import { Fragment, useMemo, useRef, useState } from "react";
import type { JSX, MouseEvent } from "react";

import { NAMED_AT_A_TIER, TIERS, tiersOf } from "../reader/tiers";
import type { Artifact } from "../reader/types";
import type { SelectionAction } from "../state/selection";

/** What the three counts are of, said on the census itself. */
const MEANING = "the calculations in this file, by tier";

/** How near the window's edge the list of names may come, in pixels. */
const MARGIN = 12;

/** Close the census's list, so a choice made from it leaves the page as it found it. */
function closing(event: MouseEvent<HTMLButtonElement>): void {
  event.currentTarget.closest("details")?.removeAttribute("open");
}

/** The census. */
export function Census({
  artifact,
  dispatch,
  showModel,
}: {
  artifact: Artifact;
  dispatch: (action: SelectionAction) => void;
  /** Open the drawer on the Model tab, which names every calculation counted here. */
  showModel: () => void;
}): JSX.Element | null {
  const read = useMemo(() => tiersOf(artifact), [artifact]);
  const list = useRef<HTMLDivElement>(null);
  // How far right the list is moved to keep it inside the window: nothing on a
  // strip of one line, where the census stands at the right; on a narrow
  // window, where the census starts a line, as much as the list would run off.
  const [shift, setShift] = useState(0);

  /** Keep the list inside the window when it opens. */
  function place(open: boolean): void {
    const box = list.current?.getBoundingClientRect();
    if (!open || box === undefined) {
      setShift(0);
      return;
    }
    setShift((was) => Math.max(0, MARGIN - (box.left - was)));
  }

  if (read === null || !("census" in read)) return null;
  const { census } = read;
  const counts = TIERS.map((tier) => `${String(census[tier].length)} ${tier}`).join(", ");
  const below = TIERS.filter((tier) => tier !== "core" && census[tier].length > 0);

  if (below.length === 0) {
    return (
      <span className="census" data-testid="census" title={`${MEANING}: ${counts}`}>
        {counts}
      </span>
    );
  }
  return (
    <div className="census" data-testid="census">
      <details
        onToggle={(event) => {
          place(event.currentTarget.open);
        }}
      >
        <summary title={`${MEANING}: ${counts}`}>{counts}</summary>
        <div
          className="census-names"
          ref={list}
          {...(shift === 0 ? {} : { style: { right: -shift } })}
        >
          {below.map((tier) => {
            const ids = census[tier];
            return (
              <Fragment key={tier}>
                <span className="ends-head">{tier}</span>
                {ids.slice(0, NAMED_AT_A_TIER).map((id) => (
                  <button
                    key={id}
                    type="button"
                    className="census-name"
                    data-tier={tier}
                    data-node={id}
                    onClick={(event) => {
                      closing(event);
                      dispatch({ select: id });
                    }}
                  >
                    {id}
                  </button>
                ))}
                {ids.length > NAMED_AT_A_TIER ? (
                  <button
                    type="button"
                    className="copy-link"
                    data-testid="census-more"
                    onClick={(event) => {
                      closing(event);
                      showModel();
                    }}
                  >
                    and {String(ids.length - NAMED_AT_A_TIER)} more
                  </button>
                ) : null}
              </Fragment>
            );
          })}
        </div>
      </details>
    </div>
  );
}
