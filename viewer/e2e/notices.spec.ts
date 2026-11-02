// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The page carries its notices, and a browser reads them back whole.
 *
 * Every page ends, after `</html>`, with the third-party notices of what it
 * bundles, in a comment whose first paragraph says how its text is escaped.
 * The Python tests read that comment out of the file. This reads it out of the
 * document a browser built from the file, in both engines: the comment is the
 * document's last node, its text undoes to `third-party-notices.txt` byte for
 * byte by the rule the comment states, and none of it reaches the screen. A
 * comment the parser had closed early would fail the first two, and one it had
 * never opened would fail the third.
 *
 * Both shapes of page, because both are what the command writes: one artifact
 * (`calc-graph --html`) and two (`diff --html`).
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { expect, test } from "@playwright/test";

const NOTICES = readFileSync(
  resolve("python/gaspatchio_viewer/assets/third-party-notices.txt"),
  "utf8",
);

/** The notices, read back by what the comment's own head says, and nothing else. */
function undo(comment: string): string {
  const blank = comment.indexOf("\n\n");
  expect(blank, "the comment has no blank line after its head").toBeGreaterThan(0);
  const body = comment.slice(blank + 2);
  expect(body.endsWith("\n"), "the notices end at a line break before the close").toBe(true);
  return body.slice(0, -1).replace(/\\([\s\S])/g, "$1");
}

for (const name of ["level4", "compare-after"]) {
  test(`the ${name} page ends with its notices, whole`, async ({ page }) => {
    await page.goto(pathToFileURL(resolve(`dist/${name}.html`)).href);
    await expect(page.locator("#root > *")).not.toHaveCount(0, { timeout: 1000 });

    const last = await page.evaluate(() => {
      const node = document.lastChild;
      return node?.nodeType === Node.COMMENT_NODE ? (node as Comment).data : null;
    });
    expect(last, "the document's last node is not a comment").not.toBeNull();
    const comment = last ?? "";

    expect(comment.startsWith("\nThird-party notices:")).toBe(true);
    expect(comment).not.toContain("--");
    expect(undo(comment)).toBe(NOTICES);

    // Carried, not shown.
    const shown = await page.evaluate(() => document.body.innerText);
    expect(shown).not.toContain("Third-party notices");
    expect(shown).not.toContain("Permission is hereby granted");
  });
}
