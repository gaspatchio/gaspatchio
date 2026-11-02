// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * Moving along the policy axis, read off the page the exporter writes.
 *
 * A document can carry several model points, and this is the control that
 * walks them. Two things are held to here, and the second is the one worth
 * writing a test for.
 *
 * **The values a switch shows are the file's.** Every expectation below is read
 * out of the fixture by the function the page draws with, so what is asserted
 * is that the cell on the screen is the element of *that policy's*
 * `value_sample` it claims to be — a quotation, checked, rather than a number
 * somebody once saw.
 *
 * **A switch re-reads values and moves nothing else.** The graph is
 * policy-invariant: two exports of one model differing only in which policy
 * they carry differ in the three enrichment members and in nothing at all
 * besides. A page can assert that or it can demonstrate it, and the case below
 * demonstrates it — the selected column, the period cursor, the cone's window
 * and all three fingerprints in the drawer are compared before and against
 * after, while at least one value in the grid is required to have moved, so
 * that "nothing changed" cannot be passed by a switch that did nothing.
 *
 * The fixture is a producer's own export over the awkward book: string ids,
 * shuffled, one policy called `3:40` and one called `all`. A switcher that
 * mangled a name would mangle one of those.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { formatValue, isIntegerDtype } from "../src/reader/format";
import { buildIndex } from "../src/reader/index";
import type { Artifact } from "../src/reader/types";

const MODEL = "policy-axis";

/** The fixture the packed page carries, read back to work out what to expect. */
const file = JSON.parse(readFileSync(resolve(`fixtures/${MODEL}.json`), "utf8")) as Artifact;

/** The column every case below reads, and the period it reads it at. */
const COLUMN = "net_claims";
const NODE = "net_claims@1";
const CURSOR = 6;

/** The page packed from one fixture, as a file on a disk. */
function pageFor(name: string): string {
  return pathToFileURL(resolve(`dist/${name}.html`)).href;
}

/**
 * What one policy's timeline holds at one period, written as the grid writes it.
 *
 * Read off the fixture through the reader's own axis-aware index, which is the
 * one place §8's positional read happens — a test that indexed the policy
 * itself would be asserting its own arithmetic against the page's.
 */
function held(at: number, id: string, period: number): string {
  const index = buildIndex(file, at);
  const sample = index.sampleOf(id);
  return formatValue(Array.isArray(sample) ? sample[period] : sample, {
    integer: isIntegerDtype(String(index.nodes.get(id)?.dtype)),
  });
}

/** Open the page, put the cursor on a period and select the column. */
async function reading(page: Page): Promise<void> {
  await page.goto(pageFor(MODEL));
  await expect(page.getByTestId("grid")).toBeVisible();
  await page.getByTestId("grid").focus();
  for (let step = 0; step < CURSOR; step += 1) await page.keyboard.press("ArrowDown");
  await expect(page.locator(`tr[data-period="${String(CURSOR)}"]`)).toHaveClass(/\bcursor\b/);
  await page.getByTestId("search").fill(COLUMN);
  await page.getByTestId("search").press("Enter");
  await expect(page.getByTestId("cone-count")).toBeVisible();
}

/**
 * Where every box on the cone's canvas is standing.
 *
 * Read off the transforms React Flow writes rather than off the node count,
 * because a count is the same number after a relayout that moved every box.
 * The layout is dagre's and dagre is deterministic, so a cone that was laid out
 * again would very likely come back identical — which is the point: this is
 * the assertion that catches the one arrangement it would not, the reader's
 * own, and it is cheap enough to hold on every switch.
 */
async function boxes(page: Page): Promise<string[]> {
  return page.locator(".react-flow__node").evaluateAll((nodes) =>
    nodes.map((node) => `${node.getAttribute("data-id") ?? ""}@${(node as HTMLElement).style.transform}`),
  );
}

/** The three digests a reviewer quotes, as the drawer prints them. */
async function digests(page: Page): Promise<string[]> {
  const drawer = page.getByTestId("inspector");
  await drawer.locator('[data-tab="node"]').click();
  const local = await drawer.locator('[data-member="local_fingerprint"] .member-value').innerText();
  const whole = await drawer.locator('[data-member="fingerprint"] .member-value').innerText();
  await drawer.locator('[data-tab="model"]').click();
  const graph = await drawer.locator('[data-fact="graph_fingerprint"] .fact-value').innerText();
  return [local, whole, graph];
}

test("the switcher names every entry and says why each one is in the file", async ({ page }) => {
  await page.goto(pageFor(MODEL));
  const switcher = page.getByTestId("policy-switcher");
  await expect(switcher).toBeVisible();

  // One option per entry, in the file's own order, each reading as the id and
  // then the producer's sentence. The `why` is the whole point: a list of ids
  // would throw away the reason the file carries.
  const options = await switcher.locator("option").allInnerTexts();
  expect(options).toEqual(
    file.policies.map((entry) => `${String(entry.policy_id)} — ${entry.why}`),
  );
  // Including the two names a selection grammar could have mangled.
  expect(options.some((text) => text.startsWith("3:40 — "))).toBe(true);
  expect(options.some((text) => text.startsWith("all — "))).toBe(true);

  // The page opens on the entry the producer put first, which is the one the
  // envelope restates as `enrichment`.
  await expect(switcher).toHaveValue("0");
  expect(file.policies[0]?.policy_id).toBe(file.enrichment?.policy_id);
});

test("a file carrying one policy draws no switcher, and still says why", async ({ page }) => {
  // There is nothing to switch to, and a select with one option is a control
  // that looks operable and is not. The policy is still named in the strip and
  // the producer's sentence is still shown — in the drawer, where the rest of
  // the envelope is. That sentence is the one §7.4 was written for: a reader
  // who meets a single policy and no account of how it was chosen assumes
  // somebody chose it, and on the ordinary export nobody did.
  const only = JSON.parse(readFileSync(resolve("fixtures/level4.json"), "utf8")) as Artifact;
  expect(only.policies).toHaveLength(1);

  await page.goto(pageFor("level4"));
  await expect(page.getByTestId("grid")).toBeVisible();
  await expect(page.getByTestId("policy-switcher")).toHaveCount(0);
  await expect(page.locator(".identity")).toContainText(
    `policy ${String(only.policies[0]?.policy_id)}`,
  );

  const drawer = page.getByTestId("inspector");
  await drawer.locator('[data-tab="model"]').click();
  await expect(drawer.locator('[data-fact="policies"] .fact-value')).toHaveText("1 policy");
  await expect(drawer.locator('[data-fact="policies[0].why"] .fact-value')).toHaveText(
    String(only.policies[0]?.why),
  );
});

test("the values a switch shows are the file's, for every entry on the axis", async ({ page }) => {
  await reading(page);
  const cell = page.locator(`td[data-column="${COLUMN}"][data-period="${String(CURSOR)}"]`);

  for (let at = 0; at < file.policies.length; at += 1) {
    await page.getByTestId("policy-switcher").selectOption(String(at));
    await expect(cell).toHaveText(held(at, NODE, CURSOR));
    // And the strip is showing the entry whose numbers those are.
    await expect(page.getByTestId("policy-switcher")).toHaveValue(String(at));
  }
});

test("switching is a value change and nothing more", async ({ page }) => {
  await reading(page);
  const cell = page.locator(`td[data-column="${COLUMN}"][data-period="${String(CURSOR)}"]`);

  const before = {
    digests: await digests(page),
    cone: await page.getByTestId("cone-count").innerText(),
    boxes: await boxes(page),
    period: await page.getByTestId("period").innerText(),
    column: await page.locator("th.sel[data-column]").innerText(),
    value: await cell.innerText(),
  };

  const last = String(file.policies.length - 1);
  await page.getByTestId("policy-switcher").selectOption(last);
  await expect(page.getByTestId("policy-switcher")).toHaveValue(last);
  await expect(cell).toHaveText(held(file.policies.length - 1, NODE, CURSOR));

  // The graph did not move: the same three digests, the same window, the same
  // column under the same period cursor.
  expect(await digests(page)).toEqual(before.digests);
  expect(await page.getByTestId("cone-count").innerText()).toBe(before.cone);
  // Not just the same number of boxes: the same boxes, in the same places. The
  // cone's layout is memoised on the artifact and not on the index, so dagre
  // does not run again and the drawing the reader had arranged is the drawing
  // they still have.
  expect(await boxes(page)).toEqual(before.boxes);
  expect(before.boxes.length).toBeGreaterThan(1);
  expect(await page.getByTestId("period").innerText()).toBe(before.period);
  expect(await page.locator("th.sel[data-column]").innerText()).toBe(before.column);

  // And a value did move, or the four equalities above prove nothing.
  expect(await cell.innerText()).not.toBe(before.value);
});

test("the drawer's context is the entry the strip is showing", async ({ page }) => {
  await reading(page);
  const drawer = page.getByTestId("inspector");
  const last = file.policies.length - 1;

  await page.getByTestId("policy-switcher").selectOption(String(last));
  await drawer.locator('[data-tab="model"]').click();
  await expect(drawer.locator(`[data-fact="policies[${String(last)}].policy_id"] .fact-value`)).toHaveText(
    String(file.policies[last]?.policy_id),
  );
  await expect(drawer.locator(`[data-fact="policies[${String(last)}].why"] .fact-value`)).toHaveText(
    String(file.policies[last]?.why),
  );
  await expect(drawer.locator('[data-fact="policies"] .fact-value')).toHaveText(
    `${String(file.policies.length)} policies`,
  );
});

test("nothing about the choice is remembered", async ({ page }) => {
  // The panes' reason, unchanged: **the file** you send someone opens the way your
  // page opens. The reader's move is theirs and lasts as long as the page does.
  //
  // The one thing that carries a choice between openings is a link, and that is
  // the opposite case rather than an exception to this one: somebody pointed at
  // an entry on purpose and sent the pointing. Opening the file itself — which
  // is what a colleague does with the attachment — is what this holds to, and
  // the check below is that nothing was written anywhere to make it otherwise.
  const last = String(file.policies.length - 1);
  await page.goto(pageFor(MODEL));
  await page.getByTestId("policy-switcher").selectOption(last);
  await expect(page.getByTestId("policy-switcher")).toHaveValue(last);

  const stored = await page.evaluate(() =>
    Array.from({ length: localStorage.length }, (_, at) => localStorage.key(at) ?? ""),
  );
  expect(stored).not.toContain("gaspatchio-viewer.policy");

  await page.goto(pageFor(MODEL));
  await expect(page.getByTestId("policy-switcher")).toHaveValue("0");
});

test("a link carries the choice, because somebody pointed at it", async ({ page }) => {
  // The switch is a gesture on one page; a link is a reader pointing. So the
  // fragment follows the switcher, and reopening that fragment lands there —
  // which is not the same claim as the one above, and is the reason the page
  // may write the URL while writing nothing to the browser.
  const last = file.policies.length - 1;
  const name = String(file.policies[last]?.policy_id);
  await page.goto(pageFor(MODEL));
  await page.getByTestId("policy-switcher").selectOption(String(last));
  await expect
    .poll(() => page.evaluate(() => window.location.hash))
    .toContain(`policy=${encodeURIComponent(name)}`);

  await page.goto(await page.evaluate(() => window.location.href));
  await expect(page.getByTestId("policy-switcher")).toHaveValue(String(last));
});
