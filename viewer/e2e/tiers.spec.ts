// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The tier census, in the strip and on the drawer's Model tab.
 *
 * Every figure expected here is read out of `fixtures/tier-census.json`, the
 * census the core takes of each committed fixture, which the Python suite
 * holds to the core and `test/tiers.test.ts` holds the page's own reading to.
 * What is held here is that the page draws that census: all three tiers
 * stated, the calculations below core named and each one a way to its node,
 * and nothing stated where the file states no census.
 *
 * `tiers.html` is packed from the one fixture with a line at each tier, which
 * the core exports from the model and points in `fixtures/tiers/`. The pages
 * a few cases need and no export produces are written beside the committed
 * fixtures under names git ignores, edited from one of them, and packed the
 * same way.
 */

import { execFileSync } from "node:child_process";
import { readFileSync, renameSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import type { Artifact } from "../src/reader/types";

/**
 * The width the strip is laid out for: one line at 1,440 px, which is the
 * screen the page's own reads are taken at. Narrower, the census gives way
 * before anything else on the strip does, and is clipped with the whole of it
 * on its title; what is held here is that at this width it is whole.
 */
test.use({ viewport: { width: 1440, height: 900 } });

/** The core's census of one fixture, as the committed file states it. */
interface CoreCensus {
  counts: Record<string, number>;
  engine_native: string[];
  opaque: string[];
}

const core = JSON.parse(readFileSync(resolve("fixtures/tier-census.json"), "utf8")) as Record<
  string,
  CoreCensus
>;

/** One fixture, as the file says it, read fresh so a case may edit it. */
function fixture(name: string): Artifact {
  return JSON.parse(readFileSync(resolve(`fixtures/${name}.json`), "utf8")) as Artifact;
}

/** The three counts, in the order the census states them. */
function counts(said: Record<string, number>): string {
  return ["core", "engine_native", "opaque"]
    .map((tier) => `${String(said[tier])} ${tier}`)
    .join(", ");
}

/** The core's census of a committed fixture. */
function census(name: string): CoreCensus {
  const said = core[name];
  if (said === undefined) throw new Error(`the core's census names no fixture ${name}`);
  return said;
}

/** Open one packed page. */
async function open(page: Page, name: string): Promise<void> {
  await page.goto(pathToFileURL(resolve(`dist/${name}.html`)).href);
  await expect(page.getByTestId("inspector")).toBeVisible();
}

/** Write an edited document beside the committed fixtures, and pack its page. */
function written(name: string, artifact: Artifact): string {
  const out = resolve(`fixtures/${name}.json`);
  const partial = `${out}.${String(process.pid)}.part`;
  writeFileSync(partial, JSON.stringify(artifact));
  renameSync(partial, out);
  execFileSync("node", ["pack.mjs", name], { cwd: resolve("."), stdio: "pipe" });
  return name;
}

/** The drawer's Model tab, opened by its own tab. */
async function modelTab(page: Page) {
  await page.getByTestId("inspector").locator('[data-tab="model"]').click();
  const panel = page.getByTestId("inspector").locator('[data-panel="model"]');
  await expect(panel).toBeVisible();
  return panel;
}

test("a model written all in core states its census in the strip, as a fact and not a control", async ({
  page,
}) => {
  await open(page, "level4");
  const strip = page.getByTestId("census");
  await expect(strip).toHaveText(counts(census("level4").counts));
  await expect(strip.locator("summary")).toHaveCount(0);

  // Beside the identity, on the strip's one line, and whole.
  const placed = await page.evaluate(() => {
    const said = document.querySelector('[data-testid="census"]');
    const identity = document.querySelector(".identity");
    if (!(said instanceof HTMLElement) || !(identity instanceof HTMLElement)) return null;
    const one = said.getBoundingClientRect();
    const two = identity.getBoundingClientRect();
    return {
      after: identity.nextElementSibling === said,
      level: Math.abs(one.top + one.height / 2 - (two.top + two.height / 2)),
      whole: said.scrollWidth <= said.clientWidth,
    };
  });
  expect(placed).toEqual({ after: true, level: expect.any(Number), whole: true });
  expect(placed?.level ?? 99).toBeLessThan(3);
});

test("a model with lines below core names them, and each one selects its node", async ({ page }) => {
  const said = census("tiers");
  await open(page, "tiers");
  const strip = page.getByTestId("census");
  await expect(strip.locator("summary")).toHaveText(counts(said.counts));
  const names = strip.locator(".census-names");
  await expect(names).toBeHidden();

  await strip.locator("summary").click();
  await expect(names).toBeVisible();
  for (const tier of ["engine_native", "opaque"] as const) {
    await expect(names.locator(`[data-tier="${tier}"][data-node]`)).toHaveText(said[tier]);
  }
  await expect(page.getByTestId("census-more")).toHaveCount(0);

  // A name selects its node, and the list it was chosen from closes.
  const chosen = said.engine_native[1] ?? "";
  await names.locator(`[data-node="${chosen}"]`).click();
  await expect(names).toBeHidden();
  const record = page.getByTestId("inspector").locator('[data-panel="node"]');
  await expect(record.locator('[data-member="id"] .member-value')).toHaveText(chosen);
});

test("the Model tab states the census under the holes, naming every line below core", async ({
  page,
}) => {
  const said = census("tiers");
  await open(page, "tiers");
  const panel = await modelTab(page);
  await expect(panel.locator('[data-fact="holes"] .fact-value')).toHaveText(
    "no holes — every column is accounted for",
  );
  const row = panel.locator('[data-fact="tiers"]');
  await expect(row.locator(".fact-value")).toHaveText(
    `${String(said.counts["core"])} core, ` +
      `${String(said.counts["engine_native"])} engine_native (${said.engine_native.join(", ")}), ` +
      `${String(said.counts["opaque"])} opaque (${said.opaque.join(", ")})`,
  );

  // Each name selects its node; the tab stays where the reader is reading.
  const chosen = said.opaque[0] ?? "";
  await row.locator(`[data-node="${chosen}"]`).click();
  await expect(page.getByTestId("proof")).toContainText(chosen.replace(/@\d+$/, ""));
  await expect(panel).toBeVisible();

  await open(page, "level4");
  const allCore = await modelTab(page);
  await expect(allCore.locator('[data-fact="tiers"] .fact-value')).toHaveText(
    counts(census("level4").counts),
  );
});

test("past five at a tier, the strip names five, and the rest are on the Model tab", async ({
  page,
}) => {
  // Six of the core lines written as opaque, so the opaque tier holds seven:
  // an edit the format allows and no export of this model would make.
  const artifact = fixture("tiers");
  for (const node of artifact.nodes.filter((one) => one.tier === "core").slice(0, 6)) {
    node.tier = "opaque";
  }
  const opaque = artifact.nodes.filter((node) => node.tier === "opaque").map((node) => node.id);
  expect(opaque).toHaveLength(7);
  await open(page, written("written-tiers-many", artifact));

  const strip = page.getByTestId("census");
  await expect(strip.locator("summary")).toHaveText("2 core, 2 engine_native, 7 opaque");
  await strip.locator("summary").click();
  await expect(strip.locator('[data-tier="opaque"][data-node]')).toHaveText(opaque.slice(0, 5));
  await expect(page.getByTestId("census-more")).toHaveText("and 2 more");

  await page.getByTestId("census-more").click();
  const panel = page.getByTestId("inspector").locator('[data-panel="model"]');
  await expect(panel).toBeVisible();
  await expect(panel.locator('[data-fact="tiers"] [data-tier="opaque"] [data-node]')).toHaveText(opaque);
});

test("a file that records no tier states no census, rather than three zeros", async ({ page }) => {
  const artifact = fixture("level4");
  for (const node of artifact.nodes) delete (node as Partial<typeof node>).tier;
  await open(page, written("written-no-tiers", artifact));

  await expect(page.getByTestId("census")).toHaveCount(0);
  const panel = await modelTab(page);
  await expect(panel.locator('[data-fact="tiers"] .fact-value')).toHaveText("no tiers recorded");
});

for (const [carried, said] of [
  [null, "no census — loaded_claims@1 computes and carries no tier"],
  ["fast", 'no census — loaded_claims@1 carries the tier "fast", which this page does not know'],
] as const) {
  test(`a calculation the file gives ${carried === null ? "no tier" : "a tier the format does not define"} stops the census, and is named`, async ({
    page,
  }) => {
    const artifact = fixture("tiers");
    const untiered = artifact.nodes.find((node) => node.id === "loaded_claims@1");
    if (untiered === undefined) throw new Error("the tiers fixture lost loaded_claims@1");
    untiered.tier = carried;
    await open(page, written(`written-untiered-${String(carried)}`, artifact));

    await expect(page.getByTestId("census")).toHaveCount(0);
    const panel = await modelTab(page);
    await expect(panel.locator('[data-fact="tiers"] .fact-value')).toHaveText(said);
  });
}

test("a comparison states no census in its strip, and the later document's on the Model tab", async ({
  page,
}) => {
  await open(page, "compare-after");
  await expect(page.getByTestId("census")).toHaveCount(0);
  const panel = await modelTab(page);
  await expect(panel.locator('[data-fact="tiers"] .fact-value')).toHaveText(
    counts(census("compare-after").counts),
  );
});

test("on a page carrying several policies the census is whole on the strip's one line", async ({
  page,
}) => {
  await open(page, "policy-axis");
  const whole = await page
    .getByTestId("census")
    .evaluate((said) => said.scrollWidth <= said.clientWidth);
  expect(whole).toBe(true);
  await expect(page.getByTestId("census")).toHaveText(counts(census("policy-axis").counts));
});

/** The census's own box: how wide it is drawn, and how wide its counts are. */
async function censusBox(page: Page) {
  return page.getByTestId("census").evaluate((said) => {
    const counts = said.querySelector("summary") ?? said;
    return {
      width: said.getBoundingClientRect().width,
      whole: counts.scrollWidth <= counts.clientWidth + 1,
      right: said.getBoundingClientRect().right,
      window: window.innerWidth,
    };
  });
}

for (const width of [1100, 700]) {
  test(`at ${String(width)} px the census's counts stay whole, on every kind of strip`, async ({
    browser,
  }) => {
    const context = await browser.newContext({ viewport: { width, height: 900 } });
    // A page of one policy, a page of several, and a page whose link asked for
    // what the file does not carry, which puts a note in the strip beside it.
    // A page each, because the page reads its link once, when it opens.
    for (const [name, link] of [
      ["level4", ""],
      ["policy-axis", ""],
      ["tiers", ""],
      ["tiers", "#column=no_such_column&period=999"],
    ] as const) {
      const page = await context.newPage();
      await page.goto(pathToFileURL(resolve(`dist/${name}.html`)).href + link);
      await expect(page.getByTestId("census")).toBeVisible();
      if (link !== "") await expect(page.getByTestId("link-note")).toBeVisible();
      const box = await censusBox(page);
      expect(box.whole, name + link).toBe(true);
      expect(box.width, name + link).toBeGreaterThan(200);
      expect(box.right, name + link).toBeLessThanOrEqual(box.window);
      await page.close();
    }
    await context.close();
  });

  test(`at ${String(width)} px the census's list of names opens inside the window`, async ({
    browser,
  }) => {
    const context = await browser.newContext({ viewport: { width, height: 900 } });
    const page = await context.newPage();
    await page.goto(pathToFileURL(resolve("dist/tiers.html")).href);
    await page.getByTestId("census").locator("summary").click();
    const names = page.getByTestId("census").locator(".census-names");
    await expect(names).toBeVisible();
    const box = await names.evaluate((list) => {
      const rect = list.getBoundingClientRect();
      return { left: rect.left, right: rect.right, window: window.innerWidth };
    });
    await context.close();
    expect(box.left).toBeGreaterThanOrEqual(0);
    expect(box.right).toBeLessThanOrEqual(box.window);
  });
}

// The census is as wide as its counts, so whether the strip's first line has
// room for it depends on everything else on that line -- and the period the
// cursor prints is on it. A period passing from one digit to two moved every
// fact after it along, and on a line with no room to spare it put the census
// on a line of its own mid-scrub and the panes 38 px further down the window,
// under a grid that had just scrolled its row to an edge that then moved. So
// the strip is held to one height from the first period to the last: on a page
// of one policy and on one of several, at the width the reads are taken at and
// at the width the browser suite opens pages at.
for (const width of [1440, 1280]) {
  test(`at ${String(width)} px the strip keeps its height while the period counts up`, async ({
    browser,
  }) => {
    const context = await browser.newContext({ viewport: { width, height: 800 } });
    for (const name of ["level4", "policy-axis", "tiers", "rollforward"]) {
      const page = await context.newPage();
      await page.goto(pathToFileURL(resolve(`dist/${name}.html`)).href);
      await expect(page.getByTestId("census")).toBeVisible();
      const heights: number[] = [];
      for (const period of [0, 9, 10, 99, 100]) {
        await page.getByTestId("cursor").evaluate((slider, at) => {
          const input = slider as HTMLInputElement;
          const write = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
          write?.call(input, String(Math.min(at, Number(input.max))));
          input.dispatchEvent(new Event("input", { bubbles: true }));
        }, period);
        heights.push(
          await page.locator(".strip").evaluate((strip) => strip.getBoundingClientRect().height),
        );
      }
      expect(new Set(heights).size, `${name}: ${heights.join(", ")}`).toBe(1);
      await page.close();
    }
    await context.close();
  });
}
