// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The proof panel, read off the page the exporter writes.
 *
 * Every expected string below is read out of the fixture the page was packed
 * from, for the reason the grid's and the cone's cases give. What is held to
 * here is the property the panel exists for: the line on the screen is the
 * producer's own sentence, the row in the excerpt is the payload's own row, and
 * the stamps at the foot are the node's own. A panel that had recomputed any of
 * it would pass a test written against a number somebody typed in, and fail
 * this one.
 *
 * Two pages, because one of the six idioms is only complete on a file the
 * exporter was asked for twice over: `level4.html` is the plain export and its
 * conditional says the dead branch was not carried, `level4-branches.html` is
 * the same model exported with `--branches` and its conditional prices it.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { formatValue, isIntegerDtype, shortFingerprint } from "../src/reader/format";
import { buildIndex } from "../src/reader/index";
import type { Artifact, ArtifactNode } from "../src/reader/types";

/** One fixture, indexed, read back here to work out what to expect. */
function fixture(name: string) {
  const artifact = JSON.parse(readFileSync(resolve(`fixtures/${name}.json`), "utf8")) as Artifact;
  return buildIndex(artifact);
}

const level4 = fixture("level4");
const branches = fixture("level4-branches");

/** The cursor every case below stands at. */
const CURSOR = 12;

/** One node of the plain level-4 fixture. */
function node(id: string): ArtifactNode {
  const found = level4.nodes.get(id);
  if (found === undefined) throw new Error(`the level-4 fixture carries no node ${id}`);
  return found;
}

/** The page packed from one fixture, as a file on a disk. */
function pageFor(name: string): string {
  return pathToFileURL(resolve(`dist/${name}.html`)).href;
}

/**
 * Open a packed page, select one column and put the row cursor on `CURSOR`.
 *
 * The cursor is moved with the grid's own arrow keys rather than by any door
 * the test opened for itself, so what is under test is the page a reader gets.
 */
async function at(page: Page, name: string, column: string): Promise<void> {
  await page.goto(pageFor(name));
  await expect(page.getByTestId("grid")).toBeVisible();
  await page.getByTestId("grid").focus();
  for (let step = 0; step < CURSOR; step += 1) await page.keyboard.press("ArrowDown");
  await expect(page.locator(`tr[data-period="${CURSOR}"]`)).toHaveClass(/\bcursor\b/);
  await page.getByTestId("search").fill(column);
  await page.getByTestId("search").press("Enter");
  await expect(page.getByTestId("proof")).toBeVisible();
}

test("the lowered line is the producer's own step 2, character for character", async ({
  page,
}) => {
  await at(page, "level4", "net_cf");
  const stepTwo = level4.traceOf("net_cf@1")?.find((s) => s.step === 2)?.expr;
  expect(typeof stepTwo).toBe("string");
  // The operand lines are the hoverable terms and carry `.term`; the producer's
  // own sentence is the panel's one lowered line, folded behind its own summary.
  await expect(
    page.getByTestId("proof").locator('[data-kind="lowered"] .text').first(),
  ).toHaveText(String(stepTwo));
});

test("hovering an operand term lights that operand's cell in the grid", async ({ page }) => {
  await at(page, "level4", "net_cf");
  const claims = page.locator('td[data-column="claims"][data-period="12"]');
  await expect(claims).not.toHaveClass(/\bhover\b/);

  await page.getByTestId("proof").locator('[data-operand="claims@1"]').hover();
  await expect(claims).toHaveClass(/\bhover\b/);

  // And the light goes out. A mark that stayed would be the page remembering
  // where a pointer had been, which is not a thing the file says.
  await page.getByTestId("proof-footer").hover();
  await expect(claims).not.toHaveClass(/\bhover\b/);
});

test("an accumulation prints the convention its settings state, in words", async ({ page }) => {
  await at(page, "level4", "survival_prob");
  await expect(page.getByTestId("proof").locator('[data-kind="convention"] .text')).toHaveText(
    "beginning of period",
  );
  // And the step it took to get here, with the two numbers the timelines hold.
  const self = level4.timeline("survival_prob@1") ?? [];
  const rate = level4.timeline("combined_decrement@1") ?? [];
  await expect(
    page
      .getByTestId("proof")
      .locator('[data-kind="substitution"] .text', { hasText: "survival_prob[12]" }),
  ).toHaveText(
    `survival_prob[12] = survival_prob[11] × (1 − combined_decrement[11]) = ` +
      `${formatValue(self[11])} × (1 − ${formatValue(rate[11])})`,
  );
});

test("a lookup quotes the row its keys name, marked, with the table's stamp", async ({ page }) => {
  await at(page, "level4", "base_mort_rate");
  const entry = level4.tables.get("mortality_select") as {
    fingerprint: string;
    payload: { columns: { name: string }[]; rows: unknown[][] };
  };

  const rows = page.getByTestId("proof").locator(".excerpt-rows tbody tr");
  await expect(rows).toHaveCount(5);
  const hit = page.getByTestId("proof").locator(".excerpt-rows tbody tr[data-hit]");
  await expect(hit).toHaveCount(1);
  // The hit is the third of the five: two rows of the payload either side of it.
  await expect(rows.nth(2)).toHaveAttribute("data-hit", "true");
  await expect(hit).toHaveText(
    new RegExp(String(level4.timeline("base_mort_rate@1")?.[CURSOR] ?? "").replace(".", "\\.")),
  );

  await expect(page.getByTestId("table-chip")).toHaveText(shortFingerprint(entry.fingerprint));
  await expect(page.getByTestId("table-chip")).toHaveAttribute("title", entry.fingerprint);
});

test("the footer carries the source location and both fingerprints, whole", async ({ page }) => {
  await at(page, "level4", "net_cf");
  const netCf = node("net_cf@1");
  const footer = page.getByTestId("proof-footer");
  await expect(footer).toContainText(String(netCf.source_location));
  await expect(footer).toContainText(netCf.local_fingerprint);
  await expect(footer).toContainText(netCf.fingerprint);
});

test("a file whose traces agree with its samples wears no flag", async ({ page }) => {
  await at(page, "level4", "net_cf");
  await expect(page.getByTestId("disagreement")).toHaveCount(0);
});

test("without --branches the panel says the dead branch was not carried", async ({ page }) => {
  await at(page, "level4", "pols_maturity");
  expect(level4.branchesOf("pols_maturity@1")).toBeUndefined();
  await expect(page.getByTestId("proof").locator('[data-kind="dead"]')).toHaveCount(0);
  await expect(page.getByTestId("proof").locator('[data-kind="note"] .text')).toContainText(
    "--branches",
  );
});

test("with --branches the dead branch is greyed and priced", async ({ page }) => {
  await at(page, "level4-branches", "pols_maturity");
  const carried = branches.branchesOf("pols_maturity@1");
  if (carried === undefined) throw new Error("the branches fixture carries no branches");
  const fired = (carried.fired as string[])[CURSOR];
  const dead = fired === "then" ? "otherwise" : "then";
  const integer = isIntegerDtype(String(branches.nodes.get("pols_maturity@1")?.dtype));

  await expect(page.getByTestId("proof").locator('[data-kind="fired"] .text')).toHaveText(
    `${fired} = ${formatValue((carried[fired as "then"] as unknown[])[CURSOR], { integer })}`,
  );
  const line = page.getByTestId("proof").locator('[data-kind="dead"]');
  await expect(line.locator(".text")).toHaveText(
    `${dead} = ${formatValue((carried[dead as "then"] as unknown[])[CURSOR], { integer })}`,
  );
  // Greyed, and said to be so by the class the stylesheet greys.
  await expect(line).toHaveClass(/\bdead\b/);
});
