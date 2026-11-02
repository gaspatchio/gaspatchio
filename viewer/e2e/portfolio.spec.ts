// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The book's own fold, read off the page the exporter writes.
 *
 * The policy axis's other half: `--portfolio` puts the fold on §7.4's axis as its own
 * entry, and this is the control that opens it. Three things are held to.
 *
 * **The page opens on the fold.** The producer puts the folds at the head of
 * the axis and the page opens on the entry the producer put first, so a
 * document carrying a portfolio total opens on the portfolio total. Nothing in
 * the page chooses that — it is the ordering, asserted here so that a change
 * to either half is caught by the half it breaks.
 *
 * **A column the fold did not cover says so, in words, in all three places a
 * value is drawn.** The grid cell, the proof and the cone's foot. This is the
 * one that matters: `·` is what a value the file does not carry looks like, and
 * a reviewer scanning a column of money reads it as a zero. There is no
 * portfolio value of a monthly mortality rate, and the page has to say that
 * rather than draw a mark that could be one.
 *
 * **A column the fold did cover carries the fold's own number**, read out of
 * the fixture by the reader the page draws with, so what is asserted is that
 * the figure on the screen is the element of that entry's `value_sample` it
 * claims to be.
 *
 * The fixture is a producer's own export of level 4 over a thousand policies:
 * two folds — one across the book, one down each month of it — and one policy
 * beneath them.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { DID_NOT_FOLD, NOT_FOLDED } from "../src/reader/fold";
import { formatValue, isIntegerDtype } from "../src/reader/format";
import { buildIndex } from "../src/reader/index";
import type { Artifact } from "../src/reader/types";

const MODEL = "portfolio";

/** The fixture the packed page carries, read back to work out what to expect. */
const file = JSON.parse(readFileSync(resolve(`fixtures/${MODEL}.json`), "utf8")) as Artifact;

/** The scalar column the whole-book fold covers, and the one it does not. */
const FOLDED = "pv_net_cf";
const FOLDED_NODE = "pv_net_cf@1";
const UNFOLDED = "mort_rate_mth";
const UNFOLDED_NODE = "mort_rate_mth@1";

/** The entry that folds the book down each period, which is the one with a grid. */
const PER_PERIOD = file.policies.findIndex(
  (entry) => entry.aggregation !== null && entry.aggregation.startsWith("period"),
);

/** The page packed from one fixture, as a file on a disk. */
function pageFor(name: string): string {
  return pathToFileURL(resolve(`dist/${name}.html`)).href;
}

/** What one entry holds for one column, written as the page writes it. */
function held(at: number, id: string, period: number): string {
  const index = buildIndex(file, at);
  const sample = index.sampleOf(id);
  return formatValue(Array.isArray(sample) ? sample[period] : sample, {
    integer: isIntegerDtype(String(index.nodes.get(id)?.dtype)),
  });
}

/** Move to one entry of the axis and select one column. */
async function reading(page: Page, at: number, column: string): Promise<void> {
  await page.goto(pageFor(MODEL));
  await expect(page.getByTestId("policy-switcher")).toBeVisible();
  await page.getByTestId("policy-switcher").selectOption(String(at));
  await expect(page.locator('label[for="policy"]')).toHaveText(
    file.policies[at]?.aggregation === null ? "policy" : "portfolio",
  );
  await page.getByTestId("search").fill(column);
  await page.getByTestId("search").press("Enter");
  await expect(page.getByTestId("cone-count")).toBeVisible();
}

test("opens on the book's own fold, with its total in the proof", async ({ page }) => {
  // The producer puts the folds first and the page opens on the first entry,
  // so a document carrying a portfolio total opens on one.
  expect(file.policies[0]?.aggregation).not.toBeNull();
  expect(file.policies[0]?.policy_id).toBeNull();

  await page.goto(pageFor(MODEL));
  const switcher = page.getByTestId("policy-switcher");
  await expect(switcher).toBeVisible();
  await expect(switcher).toHaveValue("0");
  await expect(switcher.locator("option").first()).toHaveText(
    `fold · ${String(file.policies[0]?.aggregation)} — ${String(file.policies[0]?.why)}`,
  );

  // And the fold's own total is the number in the proof, read out of the file.
  await page.getByTestId("search").fill(FOLDED);
  await page.getByTestId("search").press("Enter");
  await expect(page.getByTestId("proof")).toContainText(held(0, FOLDED_NODE, 0));
  await expect(page.getByTestId("proof").locator('[data-kind="fold"]')).toContainText(
    String(file.policies[0]?.why),
  );
});

test("shows no worked example on a fold, because nothing ran once for the book", async ({
  page,
}) => {
  await reading(page, 0, FOLDED);
  // Absent, not empty: `trace` is null at a fold entry, so the "expression
  // that ran" disclosure the panel folds a walk-through into is not there at
  // all.
  await expect(page.getByTestId("proof").locator("details.lowered")).toHaveCount(0);

  // The operands are still named — they are the definition, and the definition
  // is not a fact about a policy — and each says plainly that the fold did not
  // cover it. A blank beside a term a reader is about to check is the one
  // thing this panel must not print.
  const operands = page.getByTestId("proof").locator('[data-kind="substitution"]');
  expect(await operands.count()).toBeGreaterThan(0);
  for (const text of await operands.allInnerTexts()) {
    expect(text).toContain(NOT_FOLDED);
  }
});

test("says the model did not fold a column, in the grid, the proof and the cone", async ({
  page,
}) => {
  // The file says it first: null at that entry's position, which is a claim
  // and not an omission.
  const node = file.nodes.find((n) => n.id === UNFOLDED_NODE);
  expect((node?.value_sample as unknown[])[PER_PERIOD]).toBeNull();

  await reading(page, PER_PERIOD, UNFOLDED);

  // The grid cell: the words, and the sentence on the cell itself.
  const cell = page.locator(`td[data-column="${UNFOLDED}"][data-period="0"]`).first();
  await expect(cell).toHaveText(NOT_FOLDED);
  await expect(cell).toHaveAttribute("title", DID_NOT_FOLD);
  await expect(cell).toHaveAttribute("data-unfolded", "true");

  // The proof: the sentence itself, in place of a result.
  await expect(page.getByTestId("proof").locator('[data-kind="fold"]')).toContainText(
    DID_NOT_FOLD,
  );
  await expect(page.getByTestId("proof").locator('[data-kind="result"]')).toHaveCount(0);

  // The cone's foot, on the box for that column.
  const box = page.locator(`.react-flow__node[data-id="${UNFOLDED_NODE}"] .cone-value`);
  await expect(box).toHaveText(NOT_FOLDED);
  await expect(box).toHaveAttribute("title", DID_NOT_FOLD);
});

test("draws the fold's own numbers for the column it did cover", async ({ page }) => {
  await reading(page, PER_PERIOD, "net_cf");

  // The cell on the screen is the element of that entry's value_sample it
  // claims to be — a quotation, checked, rather than a number somebody saw.
  const cell = page.locator('td[data-column="net_cf"][data-period="3"]').first();
  await expect(cell).toHaveText(held(PER_PERIOD, "net_cf@1", 3));
  await expect(cell).not.toHaveAttribute("data-unfolded", "true");
});

test("a fold with no timeline says so instead of drawing an empty grid", async ({ page }) => {
  // The whole-book fold of a column holding one value per policy is one number
  // rather than a run of them, so this entry has no periods at all. An empty
  // table under a selected entry reads as a projection of nothing.
  await page.goto(pageFor(MODEL));
  await page.getByTestId("policy-switcher").selectOption("0");
  await expect(page.getByTestId("grid")).toContainText("no column it covers holds one value");
  await expect(page.getByTestId("grid").locator("[data-unfolded]")).toBeVisible();
});

test("says nothing about folding once the reader moves to the policy", async ({ page }) => {
  const policy = file.policies.findIndex((entry) => entry.aggregation === null);
  await reading(page, policy, UNFOLDED);

  const cell = page.locator(`td[data-column="${UNFOLDED}"][data-period="0"]`).first();
  await expect(cell).toHaveText(held(policy, UNFOLDED_NODE, 0));
  await expect(cell).not.toHaveAttribute("data-unfolded", "true");
  await expect(page.getByTestId("proof").locator('[data-kind="fold"]')).toHaveCount(0);
  await expect(page.getByTestId("proof").locator('[data-kind="result"]')).toHaveCount(1);
});
