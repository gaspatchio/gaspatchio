// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The page opens.
 *
 * One assertion, made in two engines: a file packed the way the exporter packs
 * it, opened from a disk with no server anywhere, gets as far as putting
 * something on the screen. Everything the page is for — the grid, the cone,
 * the proof, the inspector — is asserted in the specs that add them. What is
 * asserted here is the thing all of those rest on and none of them would
 * notice breaking: that a bundle inlined into one file, read back out of a
 * `file://` origin, still runs.
 *
 * The page is `dist/level4.html`, written by `pack.mjs` from the committed
 * assets — the same bytes the wheel carries and `render()` assembles.
 */

import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { expect, test } from "@playwright/test";

const PAGE = resolve("dist/level4.html");

test("the exported page opens from a disk and mounts", async ({ page }) => {
  expect(existsSync(PAGE), `run "npm run e2e", which packs ${PAGE} first`).toBe(true);

  await page.goto(pathToFileURL(PAGE).href);

  // The title is the name the exporter was given — the model file's stem,
  // which `pack.mjs` takes from the fixture's.
  await expect(page).toHaveTitle("level4");

  // Something is on the screen, and it is the reader that put it there.
  await expect(page.locator("#root > *")).not.toHaveCount(0, { timeout: 1000 });
});
