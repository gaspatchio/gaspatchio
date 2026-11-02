// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The position a reader sends, over the page somebody was sent.
 *
 * `test/position.test.ts` holds the grammar to its own arithmetic without a
 * browser. What is under test here is the part only a browser can answer: that
 * a link opens the page **on** that policy, column and period, that a stale one
 * opens the page anyway and says what has moved, and that a reader clicking
 * their way across a model leaves a back button they can still use.
 *
 * **The back button is the assertion worth writing.** `replaceState` and
 * `pushState` produce a URL that looks identical and a page that behaves
 * completely differently: one of them turns every cell a reviewer clicked into
 * a step they have to press their way back out through. `history.length` is
 * the only thing that tells them apart, so it is read before and after.
 *
 * Every expectation about what a fragment should contain is built from the
 * fixture the page was packed from, not typed: a policy id and a column name
 * typed into a test stop being evidence the moment a fixture is regenerated.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { formatValue, isIntegerDtype } from "../src/reader/format";
import { buildIndex } from "../src/reader/index";
import { policyName } from "../src/reader/policies";
import type { Artifact } from "../src/reader/types";

/** The two fixtures the acceptance asks for: a multi-policy file and a single one. */
const axis = JSON.parse(readFileSync(resolve("fixtures/policy-axis.json"), "utf8")) as Artifact;
const only = JSON.parse(readFileSync(resolve("fixtures/level4.json"), "utf8")) as Artifact;

/** The page packed from one fixture, as a file on a disk, which is how it is opened. */
function pageFor(name: string): string {
  return pathToFileURL(resolve(`dist/${name}.html`)).href;
}

/** What the address bar holds, read from the page rather than from the harness. */
async function hash(page: Page): Promise<string> {
  return page.evaluate(() => window.location.hash);
}

/**
 * Open a page and select a column the way a reader selects one.
 *
 * Through the search box, which is also what scrolls the grid sideways to the
 * column: a cell of a column nobody has asked for is not drawn, because the
 * grid draws the columns it can see.
 */
async function reading(page: Page, model: string, column: string): Promise<void> {
  await page.goto(pageFor(model));
  await expect(page.getByTestId("grid")).toBeVisible();
  await page.getByTestId("search").fill(column);
  await page.getByTestId("search").press("Enter");
  await expect(page.locator("th.sel[data-column]")).toHaveText(column);
}

test("a link lands on the policy, the column and the period it names", async ({ page }) => {
  // The third entry of the awkward axis: a policy whose id is `3:40`, which is
  // the one a link would mangle if anything on the way encoded it by hand.
  const at = 2;
  const entry = axis.policies[at];
  const name = policyName(entry!) ?? "";
  const params = new URLSearchParams({ policy: name, column: "net_claims", period: "6" });

  await page.goto(`${pageFor("policy-axis")}#${params.toString()}`);
  await expect(page.getByTestId("grid")).toBeVisible();

  await expect(page.getByTestId("policy-switcher")).toHaveValue(String(at));
  await expect(page.locator("th.sel[data-column]")).toHaveText("net_claims");
  await expect(page.getByTestId("period")).toHaveText("6");
  await expect(page.locator('tr[data-period="6"]')).toHaveClass(/\bcursor\b/);

  // And the number under the cursor is **that** entry's, which is the whole
  // point of naming the policy in the link. Read out of the fixture through
  // the reader's own axis-aware index, which is the one place §8's positional
  // read happens.
  const index = buildIndex(axis, at);
  const sample = index.sampleOf("net_claims@1");
  await expect(
    page.locator('td[data-column="net_claims"][data-period="6"]'),
  ).toHaveText(
    formatValue(Array.isArray(sample) ? sample[6] : sample, {
      integer: isIntegerDtype(String(index.nodes.get("net_claims@1")?.dtype)),
    }),
  );
  // Nothing was asked for that this file does not carry, so nothing is said.
  await expect(page.getByTestId("link-note")).toHaveCount(0);
});

test("a link to a single-policy file names no policy and still lands", async ({ page }) => {
  expect(only.policies).toHaveLength(1);
  await page.goto(`${pageFor("level4")}#column=maint_fee_pp&period=62`);
  await expect(page.getByTestId("grid")).toBeVisible();

  await expect(page.locator("th.sel[data-column]")).toHaveText("maint_fee_pp");
  await expect(page.getByTestId("period")).toHaveText("62");
  await expect(page.getByTestId("policy-switcher")).toHaveCount(0);
  // The page wrote the fragment back and left the policy out of it: there is
  // nothing to choose between on this file.
  await expect.poll(() => hash(page)).toBe("#column=maint_fee_pp&period=62");
});

test("a link naming a column this file lacks opens the page and says so", async ({ page }) => {
  await page.goto(`${pageFor("level4")}#column=shortfall&period=4`);
  await expect(page.getByTestId("grid")).toBeVisible();

  // Opened normally — on the column the page opens on when nothing names one,
  // which is the last column this model computed and nothing else reads. It is
  // a scalar, so the drawer's record is where its name is, not the grid's
  // heading row.
  await expect(
    page.getByTestId("inspector").locator('[data-member="column"] .member-value'),
  ).toHaveText("pv_net_cf");
  // The period it could honour, it honoured: a link that has gone half stale
  // is not thrown away whole.
  await expect(page.getByTestId("period")).toHaveText("4");
  await expect(page.getByTestId("link-note")).toHaveText(
    "This link asked for column shortfall, which this file does not carry. " +
      "The page opened where it opens.",
  );
});

test("selecting a cell rewrites the fragment and leaves the back button alone", async ({
  page,
}) => {
  await reading(page, "level4", "maint_fee_pp");
  // Settled: the page writes the position once the reader's hand has stopped,
  // and the count below has to be taken after that write rather than before.
  await expect.poll(() => hash(page)).toBe("#column=maint_fee_pp&period=0");
  const before = await page.evaluate(() => history.length);

  await page.locator('td[data-column="maint_fee_pp"][data-period="12"]').click();
  await expect(page.getByTestId("period")).toHaveText("12");
  await expect.poll(() => hash(page)).toBe("#column=maint_fee_pp&period=12");

  // `replaceState`, not `pushState`. A reviewer who has clicked their way
  // across forty cells has one back button press between them and whatever
  // they were doing before they opened this file.
  expect(await page.evaluate(() => history.length)).toBe(before);

  // And a second cell replaces it again rather than stacking.
  await page.locator('td[data-column="maint_fee_pp"][data-period="13"]').click();
  await expect.poll(() => hash(page)).toBe("#column=maint_fee_pp&period=13");
  expect(await page.evaluate(() => history.length)).toBe(before);
});

test("the link control copies the link to where the reader is standing", async ({
  page,
  context,
  browserName,
}) => {
  // Reading the clipboard back is the assertion worth making, and only one of
  // the two engines will grant it from a file on a disk — the same split the
  // fingerprint's control is held to in `e2e/shell.spec.ts`. In the other, the
  // control's own word for what it did is what there is, and it says either
  // way rather than always saying "copied".
  if (browserName === "chromium") {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  }
  await reading(page, "level4", "maint_fee_pp");
  await page.locator('td[data-column="maint_fee_pp"][data-period="12"]').click();
  await expect.poll(() => hash(page)).toBe("#column=maint_fee_pp&period=12");

  await page.getByTestId("copy-link").click();
  await expect(page.getByTestId("copy-link")).toHaveText("link copied");

  if (browserName === "chromium") {
    const pasted = await page.evaluate(() => navigator.clipboard.readText());
    // The file's own path with the fragment on the end, which is exactly what
    // a colleague holding the same file needs.
    expect(pasted).toBe(`${pageFor("level4")}#column=maint_fee_pp&period=12`);
  }

  // For a second and then nothing: this is a gesture, and nothing about the
  // page has changed because somebody took a copy of where they were standing.
  await expect(page.getByTestId("copy-link")).toHaveText("copy link");
});
