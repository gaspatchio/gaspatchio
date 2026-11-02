// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The window a read states (§9) is drawn the way its offset is.
 *
 * An offset is a loop on the reading node in the cone and an outline one row
 * away in the grid. A window — the run an aggregation read — is the same loop
 * labelled with the run, and an outline on every cell of it. Both come off
 * the narrowing facet and never off the formula's text.
 *
 * The committed level-4 fixture was exported before the producer stated
 * windows, so this file writes, under a name git ignores, that fixture with
 * the one member the producer now writes for its survival fold: the read of
 * `combined_decrement` by `survival_prob`, a cumulative survival under the
 * default opening of 1.0, is `{"from": "first", "to": -1}` —
 * `bindings/python/tests/graph/test_period_windows.py` holds the producer to
 * that. Nothing else in the file moves.
 */

import { execFileSync } from "node:child_process";
import { readFileSync, renameSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const CURSOR = 12;
const PAGE = "written-windows";

test.beforeAll(() => {
  const artifact = JSON.parse(readFileSync(resolve("fixtures/level4.json"), "utf8")) as {
    nodes: {
      id: string;
      facets: {
        gaspatchio_column_transformation?: {
          reads: { source: string; transformations: object[] }[];
        };
      };
    }[];
  };
  const fold = artifact.nodes.find((node) => node.id === "survival_prob@1");
  const read = fold?.facets.gaspatchio_column_transformation?.reads.find(
    (one) => one.source === "combined_decrement@1",
  );
  if (read === undefined) throw new Error("level 4's survival fold reads no decrement");
  read.transformations = [
    { type: "DIRECT", subtype: "AGGREGATION", periods: { from: "first", to: -1 } },
  ];
  const out = resolve(`fixtures/${PAGE}.json`);
  const partial = `${out}.${String(process.pid)}.part`;
  writeFileSync(partial, JSON.stringify(artifact));
  renameSync(partial, out);
  execFileSync("node", ["pack.mjs", PAGE], { cwd: resolve("."), stdio: "pipe" });
});

/** Open the page, put the cursor on CURSOR, and select the survival fold. */
async function atTheFold(page: Page): Promise<void> {
  await page.goto(pathToFileURL(resolve(`dist/${PAGE}.html`)).href);
  await expect(page.getByTestId("grid")).toBeVisible();
  await page.getByTestId("grid").focus();
  for (let step = 0; step < CURSOR; step += 1) await page.keyboard.press("ArrowDown");
  await page.getByTestId("search").fill("survival_prob");
  await page.getByTestId("search").press("Enter");
  await expect(page.getByTestId("cone-count")).toBeVisible();
}

test("a read that states a window wears the loop, labelled with the run", async ({ page }) => {
  await atTheFold(page);
  await expect(page.locator('.edge-offset[data-label="first…t−1"]')).toHaveCount(1);
});

test("a window outlines every cell of the run it read, and only those", async ({ page }) => {
  await atTheFold(page);
  // {first, −1} at period 12 is periods 0 to 11 of the decrement.
  for (const period of [0, 5, CURSOR - 1]) {
    const cell = page.locator(`td[data-column="combined_decrement"][data-period="${String(period)}"]`);
    await expect(cell).toHaveClass(/\boperand\b/);
    await expect(cell).toHaveAttribute("data-window", "first…t−1");
  }
  await expect(
    page.locator(`td[data-column="combined_decrement"][data-period="${String(CURSOR)}"]`),
  ).not.toHaveClass(/\boperand\b/);
});

test("the proof panel names the run on the operand's line", async ({ page }) => {
  await atTheFold(page);
  const term = page.locator('.proof .term[data-operand="combined_decrement@1"]');
  await expect(term).toHaveAttribute("data-window", "first…t−1");
  await expect(term).toContainText("reads first…t−1");
});
