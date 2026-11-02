// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The name the command gave each document, on the page it was given to.
 *
 * `render()` takes a label for each side and carries it on that side's block;
 * a comparison page shows the two where it names its two sides, before each
 * side's date and seal. The pages here are packed with `pack.mjs`'s own two
 * options, which the Python suite holds byte for byte to `render()`, under
 * names of their own in `dist/`, which git ignores.
 */

import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { expect, test } from "@playwright/test";

/** A path at a revision, which is what `gspio diff` names a side by. */
const AFTER = "model.audit.json at v2026.Q2 (3f2a91c)";

/** Every character that could end an attribute, open an element or close a block. */
const BEFORE = "q1 \"<b>\" & 'quoted' </script><script>alert(1)</script>";

/**
 * A path two hundred characters long, ending in the revision it names, which
 * is the part of a label that tells one side from the other.
 */
function long(revision: string): string {
  const tail = `/model.audit.json at ${revision}`;
  return `/srv/valuation/${"quarter-end-reviews/".repeat(12)}`.slice(0, 200 - tail.length) + tail;
}

/** Pack one page with `pack.mjs`, under a name of its own. */
function packed(as: string, ...args: string[]): string {
  execFileSync("node", ["pack.mjs", ...args, "--as", as], { cwd: resolve("."), stdio: "pipe" });
  return pathToFileURL(resolve(`dist/${as}.html`)).href;
}

test.use({ viewport: { width: 1440, height: 900 } });

test("a comparison names each side by its label, before its date and seal", async ({ page }) => {
  await page.goto(
    packed(
      "labelled-compare",
      "compare-after",
      "--second",
      "compare-before",
      "--label",
      AFTER,
      "--second-label",
      BEFORE,
    ),
  );
  await expect(page.getByTestId("changes")).toBeVisible();

  const compared = page.getByTestId("compared");
  await expect(compared.getByTestId("label-before")).toHaveText(BEFORE);
  await expect(compared.getByTestId("label-after")).toHaveText(AFTER);
  // Earlier first, each before its own date: label, date, seal, arrow, label,
  // date, seal.
  const order = await compared.evaluate((strip) =>
    [...strip.children].map((one) => one.getAttribute("data-testid") ?? one.className),
  );
  expect(order).toEqual([
    "label-before",
    "against",
    "seal-before",
    "to",
    "label-after",
    "against",
    "seal-after",
  ]);

  // The label was text: no script it held was ever an element.
  const scripts = await page.evaluate(() => document.querySelectorAll("script").length);
  expect(scripts).toBe(3);
  await expect(page.locator("script#artifact")).toHaveCount(2);
});

test("a label reads back exactly, carriage returns included", async ({ page }) => {
  // An HTML parser reads a carriage return in an attribute, and a carriage
  // return and line feed together, back as a line feed. The label travels with
  // each one written as its reference, so the page holds the label it was
  // given, character for character.
  const before = "cr\r\nlf\rlone cr";
  const after = "tab\tline\nfeed";
  await page.goto(
    packed(
      "labelled-returns",
      "compare-after",
      "--second",
      "compare-before",
      "--label",
      after,
      "--second-label",
      before,
    ),
  );
  await expect(page.getByTestId("changes")).toBeVisible();
  const read = await page.evaluate(() =>
    [...document.querySelectorAll("script#artifact")].map((block) => block.getAttribute("data-label")),
  );
  expect(read).toEqual([after, before]);
  await expect(page.getByTestId("label-before")).toHaveAttribute("title", before);
  expect(await page.getByTestId("label-before").evaluate((named) => named.textContent)).toBe(before);
});

test("a comparison given no labels names its sides as it always did", async ({ page }) => {
  await page.goto(packed("unlabelled-compare", "compare-after", "--second", "compare-before"));
  await expect(page.getByTestId("changes")).toBeVisible();
  await expect(page.getByTestId("label-before")).toHaveCount(0);
  await expect(page.getByTestId("label-after")).toHaveCount(0);
});

test("a page carrying one document carries its label and shows none", async ({ page }) => {
  await page.goto(packed("labelled-one", "level4", "--label", AFTER));
  await expect(page.getByTestId("grid")).toBeVisible();
  await expect(page.locator("script#artifact")).toHaveAttribute("data-label", AFTER);
  await expect(page.getByTestId("label-after")).toHaveCount(0);
  expect(await page.locator(".identity").innerText()).not.toContain(AFTER);
});

for (const width of [1440, 1100]) {
  test(`a label too long for the strip at ${String(width)} px is cut from its start, and the strip stays in the window`, async ({
    browser,
  }) => {
    const after = long("v2026.Q2 (3f2a91c)");
    const before = long("v2026.Q1 (9b1c2d3)");
    expect([after.length, before.length]).toEqual([200, 200]);
    const context = await browser.newContext({ viewport: { width, height: 900 } });
    const page = await context.newPage();
    await page.goto(
      packed(
        `long-labels-${String(width)}`,
        "compare-after",
        "--second",
        "compare-before",
        "--label",
        after,
        "--second-label",
        before,
      ),
    );
    await expect(page.getByTestId("changes")).toBeVisible();

    const seen = await page.evaluate(() => {
      const box = (selector: string) => {
        const found = document.querySelector(selector);
        return found === null ? null : found.getBoundingClientRect();
      };
      const named = (testid: string) => {
        const outer = document.querySelector(`[data-testid="${testid}"]`);
        const inner = outer?.firstElementChild;
        if (!(outer instanceof HTMLElement) || !(inner instanceof HTMLElement)) return null;
        const shown = outer.getBoundingClientRect();
        const text = inner.getBoundingClientRect();
        return {
          title: outer.title,
          text: outer.textContent,
          // Within a pixel's rounding: WebKit sets the end of a run cut from its
          // start a pixel past the box that cuts it.
          endInSight: text.right <= shown.right + 1.5,
          startCut: text.left < shown.left - 1,
          right: shown.right,
        };
      };
      const facts = [...document.querySelectorAll(".identity > .fact:not(.compared)")];
      return {
        window: window.innerWidth,
        page: document.documentElement.scrollWidth,
        // Every other fact in the identity on one line of its own height:
        // "policy 1" squeezed onto two lines is a fact giving way that should
        // not have.
        wrapped: facts.filter((fact) => fact.getBoundingClientRect().height > 30).length,
        sealAfter: box('[data-testid="seal-after"]')?.right ?? Number.POSITIVE_INFINITY,
        fingerprint: box('[data-testid="fingerprint"]')?.right ?? Number.POSITIVE_INFINITY,
        before: named("label-before"),
        after: named("label-after"),
      };
    });
    await context.close();

    // Nothing pushed past the window's right edge, and no page to scroll
    // sideways to find the seals on.
    expect(seen.page).toBeLessThanOrEqual(seen.window);
    expect(seen.sealAfter).toBeLessThanOrEqual(seen.window);
    expect(seen.fingerprint).toBeLessThanOrEqual(seen.window);
    expect(seen.wrapped).toBe(0);
    // Each label is the whole label, in the document and on its title; what
    // gives way on the screen is its start, so the revision stays in sight.
    for (const [side, label] of [
      [seen.before, before],
      [seen.after, after],
    ] as const) {
      expect(side?.text).toBe(label);
      expect(side?.title).toBe(label);
      expect(side?.endInSight).toBe(true);
      expect(side?.startCut).toBe(true);
      expect(side?.right ?? Number.POSITIVE_INFINITY).toBeLessThanOrEqual(seen.window);
    }
  });
}
