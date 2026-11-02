// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * A control that puts one string on the clipboard and says what it did.
 *
 * Two places need exactly this and they are at opposite ends of the page — the
 * link to where the reader is standing, in the identity strip, and the model
 * file's own text, in the source tab's head — so the behaviour is written once.
 * What is **not** shared is the face: each site passes its own class, because
 * one of them sits among the file's facts and the other sits in a panel head
 * beside a digest.
 *
 * **It says which way the write went**, for the reason the fingerprint's
 * control says it: a control that always reports success is a control nobody
 * can trust the one time it mattered. Browsers refuse this write for reasons
 * that have nothing to do with the page — a file opened from a disk, a window
 * without focus — and a silent failure there is a reviewer pasting the last
 * thing they copied into an email about this one.
 *
 * It says it for a second and then goes back to its name. Both of these are
 * gestures rather than states: nothing about the page has changed because
 * somebody took a copy of something out of it.
 */

import { useEffect, useRef, useState } from "react";
import type { JSX } from "react";

/** How long the control says what it did, in milliseconds. */
const SAID_MS = 1000;

/** A control that copies one string. */
export function Copy({
  what,
  name,
  title,
  className,
  testid,
}: {
  /**
   * The string to copy, read when the control is pressed.
   *
   * A function and not a string, because the link is `location.href` and that
   * is a fact about the moment of the press rather than about the render that
   * drew the button.
   */
  what: () => string;
  /** What is being copied, one word: the label and both messages are built on it. */
  name: string;
  /** What the control does, for the reader who hovers it. */
  title: string;
  className: string;
  testid: string;
}): JSX.Element {
  const [said, setSaid] = useState<string | null>(null);
  const clearing = useRef<number | null>(null);

  // The timer is restarted on every press rather than left running, so a
  // second press says its own thing for a whole second rather than for
  // whatever was left of the first one's.
  function flash(text: string): void {
    setSaid(text);
    if (clearing.current !== null) window.clearTimeout(clearing.current);
    clearing.current = window.setTimeout(() => {
      setSaid(null);
      clearing.current = null;
    }, SAID_MS);
  }

  useEffect(
    () => () => {
      if (clearing.current !== null) window.clearTimeout(clearing.current);
    },
    [],
  );

  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(what());
      flash(`${name} copied`);
    } catch {
      flash(`${name} not copied`);
    }
  }

  return (
    <button
      type="button"
      className={className}
      data-testid={testid}
      title={title}
      onClick={() => {
        void copy();
      }}
    >
      {said ?? `copy ${name}`}
    </button>
  );
}
