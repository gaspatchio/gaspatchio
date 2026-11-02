// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * Two balances, one kernel run, and the row a ratchet leaves on the waterfall.
 *
 * The rollforward patterns' second model, exported by this repository's own
 * producer: a separate-account fund growing every month, and a GMDB benefit
 * base that ratchets to it at each anniversary and moves by nothing at all in
 * between. It is here because it is the shape the single-state fixture cannot
 * show — a chain landing on **two** balances, so the panel draws two
 * waterfalls rather than adding two states together, and a step whose amount
 * is zero for eleven months and a number on the twelfth.
 *
 * The eleven zeros are the point. A movement schedule that only listed the
 * periods something happened in would leave a reader working out whether the
 * ratchet was absent or had not fired; the file states 0.00 and the page draws
 * it, so *nothing happened here* is a quotation rather than an inference. The
 * same is true one fixture over, where a floor that cannot bite reads zero all
 * the way down.
 *
 * Every figure below is read out of the fixture by the same functions the page
 * writes with, for `walk.ts`'s reason: a number typed into a test stops being
 * evidence the moment the fixture is regenerated.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { expect, test } from "@playwright/test";

import { formatValue } from "../src/reader/format";
import { buildIndex } from "../src/reader/index";
import type { Artifact } from "../src/reader/types";

const MODEL = "rollforward-ratchet";
const artifact = JSON.parse(
  readFileSync(resolve(`fixtures/${MODEL}.json`), "utf8"),
) as Artifact;
const index = buildIndex(artifact);
const page_ = pathToFileURL(resolve(`dist/${MODEL}.html`)).href;

/** The compilation, as the file names it. */
const COMPILED =
  artifact.nodes.find((node) => node.kind === "rollforward")?.id ?? "no compilation";

/** The anniversary the ratchet fires at, and the month either side of it. */
const FIRES = 11;
const QUIET = 12;

/** One movement's amount at one period, out of the fixture's own array. */
function moved(key: string, period: number): number {
  return (index.movementsOf(COMPILED).get(key) as number[])[period];
}

/** One balance's closing value at one period, out of the state node's own array. */
function closing(state: string, period: number): number {
  return (index.sampleOf(`state:${state}@eop`) as number[])[period];
}

/** Put the cursor on a period and open the compilation's panel. */
async function atPeriod(page: import("@playwright/test").Page, period: number) {
  await page.goto(page_);
  await expect(page.getByTestId("grid")).toBeVisible();
  await page.locator(`td[data-column="fund"][data-period="${String(period)}"]`).click();
  await page.locator(`.react-flow__node[data-id="${COMPILED}"]`).click();
  await expect(page.getByTestId("proof-idiom")).toHaveText("rollforward");
  return page.getByTestId("proof");
}

test("two balances are two waterfalls, not one sum of both", async ({ page }) => {
  const proof = await atPeriod(page, FIRES);

  // The file declares two states and two steps, one landing on each.
  expect(index.nodes.get(COMPILED)?.states).toEqual(["fund", "gmdb"]);
  const increments = index.nodes.get(COMPILED)?.increments ?? [];
  expect(increments.map((one) => one.target)).toEqual(["fund@eop", "gmdb@eop"]);

  // So the panel heads two of them, in the order the chain reaches them.
  const heads = proof.locator('[data-kind="fold"] .text');
  await expect(heads).toHaveCount(2);
  await expect(heads.nth(0)).toHaveText(`fund@eop, period ${String(FIRES)}`);
  await expect(heads.nth(1)).toHaveText(`gmdb@eop, period ${String(FIRES)}`);

  // And two check lines, one per balance, each closing on its own numbers.
  await expect(proof.locator('[data-kind="check"] .text')).toHaveCount(2);
  await expect(proof.locator('[data-kind="check"][data-flagged]')).toHaveCount(0);
});

test("the ratchet at the anniversary it bites", async ({ page }) => {
  const proof = await atPeriod(page, FIRES);
  const amount = moved("GMDB_ratchet", FIRES);
  const opening = closing("gmdb", FIRES - 1);

  expect(amount).toBeGreaterThan(0);
  const rows = proof.locator('[data-kind="substitution"] .text');
  // The second waterfall: opening, the one step that lands on this balance.
  await expect(rows.nth(2)).toHaveText(`opening   ${formatValue(opening)}`);
  await expect(rows.nth(3)).toHaveText(`GMDB_ratchet   ${formatValue(amount)}`);
  await expect(proof.locator('[data-kind="result"] .text').nth(1)).toHaveText(
    `closing   ${formatValue(closing("gmdb", FIRES))}`,
  );
  // The benefit base stepped up to the fund, which is what a ratchet is.
  expect(closing("gmdb", FIRES)).toBeCloseTo(closing("fund", FIRES), 6);
});

test("and the month after it, where nothing happened", async ({ page }) => {
  const proof = await atPeriod(page, QUIET);
  const amount = moved("GMDB_ratchet", QUIET);

  // Zero, and written as zero: the row is the file saying the ratchet did not
  // fire, not the file leaving the period out.
  expect(amount).toBe(0);
  await expect(proof.locator('[data-kind="substitution"] .text').nth(3)).toHaveText(
    `GMDB_ratchet   ${formatValue(0)}`,
  );
  // The balance held what the anniversary gave it.
  expect(closing("gmdb", QUIET)).toBe(closing("gmdb", FIRES));
  await expect(proof.locator('[data-kind="check"][data-flagged]')).toHaveCount(0);
});

test("the box says how many steps it folds", async ({ page }) => {
  await page.goto(page_);
  await expect(page.getByTestId("grid")).toBeVisible();
  await page.locator(`td[data-column="fund"][data-period="1"]`).click();
  const increments = index.nodes.get(COMPILED)?.increments ?? [];
  await expect(
    page.locator(`.react-flow__node[data-id="${COMPILED}"] [data-testid="steps-chip"]`),
  ).toHaveText(`${String(increments.length)} steps`);
});
