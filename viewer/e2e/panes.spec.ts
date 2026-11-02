// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The window management, in the page it was built for.
 *
 * The panes' controls, rails, layouts, keys and memory, on the page an actuary
 * opens from a disk. What is asserted here is what only a browser can answer — that the
 * controls are not drawn until a pointer or a key arrives, that a collapse
 * leaves a strip carrying a live figure, that Escape puts back what was there,
 * that a letter typed into the search box stays a letter. The state machine
 * underneath is `test/layout.test.ts`'s and is not re-asserted through a
 * browser: one place per claim.
 *
 * Two pages are used and they are two different files. The level-4 export is a
 * model with values, where the rails carry numbers. The holes fixture is a file
 * that admits two columns it does not account for and carries no values at all,
 * which is where a rail's amber admission has something to be true about.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { formatValue, isIntegerDtype } from "../src/reader/format";
import { buildIndex } from "../src/reader/index";
import type { Artifact } from "../src/reader/types";

/** One committed fixture, indexed, so a figure is derived rather than typed in. */
function fixture(name: string) {
  return buildIndex(
    JSON.parse(readFileSync(resolve(`fixtures/${name}.json`), "utf8")) as Artifact,
  );
}

const level4 = fixture("level4");
const holes = fixture("holes");

/** The page packed from one fixture, as a file on a disk, which is how it is opened. */
function pageFor(name: string): string {
  return pathToFileURL(resolve(`dist/${name}.html`)).href;
}

/**
 * Take focus out of the search box, which has it on every fresh page.
 *
 * The keyboard is suppressed while somebody is typing, so a test that pressed a
 * layout letter straight after loading would be asserting the suppression and
 * calling it the layout. Clicking the strip is what a reader does.
 */
async function stopTyping(page: Page): Promise<void> {
  await page.locator(".strip").click({ position: { x: 2, y: 2 } });
}

/** Open a page and put the selection on one column at one period. */
async function reading(page: Page, model: string, column: string, period: number): Promise<void> {
  await page.goto(pageFor(model));
  await expect(page.getByTestId("grid")).toBeVisible();
  await page.getByTestId("cursor").fill(String(period));
  await page.getByTestId("search").fill(column);
  await page.getByTestId("search").press("Enter");
  await expect(page.getByTestId("cone-count")).toBeVisible();
}

test("the two controls are not in the page at rest, and appear on a pointer", async ({ page }) => {
  await page.goto(pageFor("level4"));
  await expect(page.getByTestId("grid")).toBeVisible();

  // The reason for hiding them is that they must never turn up in a
  // screenshot by accident, so "hidden" here has to mean not drawn rather than
  // drawn at zero opacity.
  await expect(page.getByTestId("expand-cone")).toBeHidden();
  await expect(page.getByTestId("collapse-cone")).toBeHidden();

  await page.locator('[data-pane="cone"]').hover();
  await expect(page.getByTestId("expand-cone")).toBeVisible();
  await expect(page.getByTestId("collapse-cone")).toBeVisible();
});

test("the controls appear on keyboard focus as well as on a pointer", async ({ page }) => {
  await page.goto(pageFor("level4"));
  await expect(page.getByTestId("grid")).toBeVisible();
  await stopTyping(page);

  await page.keyboard.press("Digit2");
  await expect(page.getByTestId("expand-cone")).toBeVisible();
});

test("collapsing a pane leaves a rail carrying its live figure", async ({ page }) => {
  await reading(page, "level4", "maint_fee_pp", 62);

  await page.locator('[data-pane="cone"]').hover();
  await page.getByTestId("collapse-cone").click();

  // The pane is gone and the rail is not, which is the whole of what
  // separates a collapse from a hidden pane.
  await expect(page.getByTestId("proof")).toHaveCount(0);
  const rail = page.getByTestId("rail-cone");
  await expect(rail).toBeVisible();
  // Named in the documentation's words, not by the id the code keys it by.
  await expect(rail.locator(".rail-name")).toHaveText("derivation and proof");
  await expect(page.getByTestId("rail-figure-cone")).toContainText("arithmetic · maint_fee_pp");

  // And the figure is live: the result at the cursor's period, as the file
  // holds it, not a label saying the pane is closed.
  const node = level4.nodes.get("maint_fee_pp@1");
  const sample = level4.timeline("maint_fee_pp@1");
  const value = formatValue(sample?.[62], {
    integer: node !== undefined && isIntegerDtype(node.dtype),
  });
  await expect(page.getByTestId("rail-figure-cone")).toContainText(value);
});

test("every rail is named in the documentation's words, and so is the way back", async ({
  page,
}) => {
  await reading(page, "level4", "maint_fee_pp", 62);

  // Each pane put away by its own control, so all three rails are on the page
  // at once — and each control says, before it is pressed, what it puts away.
  const named = { grid: "worksheet", cone: "derivation and proof", inspector: "record" };
  for (const [pane, label] of Object.entries(named)) {
    await page.locator(`[data-pane="${pane}"]`).hover();
    const collapse = page.getByTestId(`collapse-${pane}`);
    await expect(collapse).toHaveAttribute("aria-label", `collapse the ${label} to a rail`);
    await collapse.click();
  }

  for (const [pane, label] of Object.entries(named)) {
    await expect(page.getByTestId(`rail-${pane}`).locator(".rail-name")).toHaveText(label);
    await expect(page.getByTestId(`rail-${pane}`)).toHaveAttribute("title", `open the ${label}`);
    await expect(page.getByTestId(`rail-${pane}`)).not.toContainText(pane);
  }
});

test("clicking a rail opens the pane it stands for", async ({ page }) => {
  await reading(page, "level4", "maint_fee_pp", 62);
  await page.locator('[data-pane="cone"]').hover();
  await page.getByTestId("collapse-cone").click();
  await expect(page.getByTestId("rail-cone")).toBeVisible();

  await page.getByTestId("rail-cone").click();
  await expect(page.getByTestId("cone")).toBeVisible();
  await expect(page.getByTestId("rail-cone")).toHaveCount(0);
});

test("the grid's rail says the period and the selected value", async ({ page }) => {
  await reading(page, "level4", "maint_fee_pp", 62);
  await page.locator('[data-pane="grid"]').hover();
  await page.getByTestId("collapse-grid").click();

  const figure = page.getByTestId("rail-figure-grid");
  await expect(figure).toContainText("period 62");
  await expect(figure).toContainText("maint_fee_pp");
});

test("the cone's rail says the window's size and its centre", async ({ page }) => {
  await reading(page, "level4", "maint_fee_pp", 62);
  const counted = await page.getByTestId("cone-count").textContent();

  await page.locator('[data-pane="cone"]').hover();
  await page.getByTestId("collapse-cone").click();

  const figure = page.getByTestId("rail-figure-cone");
  // The same count the cone bar was showing a moment ago: a rail that quoted a
  // second number would be a second answer to one question.
  await expect(figure).toContainText(`${String(counted)} of ${String(level4.order.length)}`);
  await expect(figure).toContainText("centre maint_fee_pp");
});

test("expanding a pane gives it the page and rails the other two", async ({ page }) => {
  await reading(page, "level4", "maint_fee_pp", 62);

  await page.locator('[data-pane="cone"]').hover();
  await page.getByTestId("expand-cone").click();

  await expect(page.getByTestId("cone")).toBeVisible();
  for (const pane of ["grid", "inspector"]) {
    await expect(page.getByTestId(`rail-${pane}`)).toBeVisible();
  }
  // The identity strip never hides, including under an expanded pane:
  // a screenshot of a maximised pane with no identity above it is a screenshot
  // of nothing, and these pages end up in records.
  await expect(page.getByTestId("fingerprint")).toBeVisible();
  await expect(page.locator(".identity")).toContainText("policy");
});

test("the same corner restores, and so does Escape", async ({ page }) => {
  await reading(page, "level4", "maint_fee_pp", 62);

  await page.locator('[data-pane="cone"]').hover();
  await page.getByTestId("expand-cone").click();
  await expect(page.getByTestId("rail-grid")).toBeVisible();

  await page.locator('[data-pane="cone"]').hover();
  await page.getByTestId("expand-cone").click();
  await expect(page.getByTestId("grid")).toBeVisible();
  await expect(page.getByTestId("rail-grid")).toHaveCount(0);

  await page.locator('[data-pane="cone"]').hover();
  await page.getByTestId("expand-cone").click();
  await expect(page.getByTestId("rail-grid")).toBeVisible();
  await stopTyping(page);
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("grid")).toBeVisible();
});

test("an expansion puts back exactly the rails that were there before it", async ({ page }) => {
  await reading(page, "level4", "maint_fee_pp", 62);

  await page.locator('[data-pane="cone"]').hover();
  await page.getByTestId("collapse-cone").click();
  await expect(page.getByTestId("rail-cone")).toBeVisible();

  await page.locator('[data-pane="grid"]').hover();
  await page.getByTestId("expand-grid").click();
  await stopTyping(page);
  await page.keyboard.press("Escape");

  // The cone stays away and everything else comes back: an expansion is a
  // gesture over the reader's own arrangement, not a replacement for it.
  await expect(page.getByTestId("rail-cone")).toBeVisible();
  await expect(page.getByTestId("grid")).toBeVisible();
  // Not the proof: it rides under the cone now, so a railed cone takes it too,
  // which is exactly why that rail has to speak for both.
  await expect(page.getByTestId("inspector")).toBeVisible();
});

test("an amber admission travels to the rail in words", async ({ page }) => {
  await page.goto(pageFor("holes"));
  await expect(page.getByTestId("cone")).toBeVisible();
  await page.getByTestId("search").fill("reserve_override");
  await page.getByTestId("search").press("Enter");
  await stopTyping(page);

  // Railed one at a time rather than by a layout: the two panes that have
  // something to own up to on this file are the grid and the cone, and a
  // layout that expanded either would leave only one rail to read.
  await page.locator('[data-pane="grid"]').hover();
  await page.getByTestId("collapse-grid").click();
  await page.locator('[data-pane="cone"]').hover();
  await page.getByTestId("collapse-cone").click();
  await page.locator('[data-pane="inspector"]').hover();
  await page.getByTestId("collapse-inspector").click();

  const grid = page.getByTestId("rail-figure-grid");
  await expect(grid).toHaveText("this file carries no values");
  await expect(grid).toHaveAttribute("data-admits", "true");

  // The cone's rail speaks for the strip beneath it too, which is what keeps a
  // collapse safe now that the proof is not a pane of its own.
  const cone = page.getByTestId("rail-figure-cone");
  await expect(cone).toContainText("reserve_override unaccounted for");
  await expect(cone).toHaveAttribute("data-admits", "true");

  const drawer = page.getByTestId("rail-figure-inspector");
  await expect(drawer).toContainText(`${String(holes.artifact.holes.length)} holes`);
  await expect(drawer).toHaveAttribute("data-admits", "true");

  // Amber, and the page's amber: a hole and a disagreement and nothing else.
  const colour = await grid.evaluate((element) => getComputedStyle(element).color);
  const amber = await page
    .getByTestId("holes-chip")
    .evaluate((element) => getComputedStyle(element).color);
  expect(colour).toBe(amber);
});

test("the four layouts are reachable from the strip and from the keyboard", async ({ page }) => {
  await reading(page, "level4", "maint_fee_pp", 62);
  await stopTyping(page);

  await page.getByTestId("layout-table").click();
  await expect(page.getByTestId("grid")).toBeVisible();
  await expect(page.getByTestId("rail-cone")).toBeVisible();
  await expect(page.getByTestId("rail-cone")).toBeVisible();

  await page.keyboard.press("KeyL");
  await expect(page.getByTestId("cone")).toBeVisible();
  await expect(page.getByTestId("rail-grid")).toBeVisible();
  await expect(page.getByTestId("rail-inspector")).toBeVisible();

  // The source layout rails the grid and leaves the cone — and with it the
  // worked example under it — beside the model file.
  await page.keyboard.press("KeyS");
  await expect(page.getByTestId("proof")).toBeVisible();
  await expect(page.getByTestId("inspector").locator('[data-tab="source"]')).toHaveAttribute(
    "aria-selected",
    "true",
  );

  await page.keyboard.press("KeyG");
  for (const pane of ["grid", "cone", "proof"]) {
    await expect(page.getByTestId(pane)).toBeVisible();
  }
  await expect(page.locator("[data-rail]")).toHaveCount(0);
  await expect(page.getByTestId("layout-read")).toHaveAttribute("aria-pressed", "true");
});

test("shift and a digit expands that pane, and the backslash toggles the drawer", async ({
  page,
}) => {
  await reading(page, "level4", "maint_fee_pp", 62);
  await stopTyping(page);

  await page.keyboard.press("Shift+Digit2");
  await expect(page.getByTestId("cone")).toBeVisible();
  await expect(page.getByTestId("rail-grid")).toBeVisible();

  await page.keyboard.press("Escape");
  await page.keyboard.press("Backslash");
  await expect(page.getByTestId("rail-inspector")).toBeVisible();
  await page.keyboard.press("Backslash");
  await expect(page.getByTestId("inspector")).toBeVisible();
});

test("typing in the search box stays typing", async ({ page }) => {
  await page.goto(pageFor("level4"));
  await expect(page.getByTestId("grid")).toBeVisible();

  // The box has focus on a fresh page. Every one of these is a shortcut
  // somewhere else on this page, and every one of them has to be a character
  // here — `total_claims` alone would have reached three layouts.
  await page.getByTestId("search").fill("");
  await page.getByTestId("search").type("gtls");
  await expect(page.getByTestId("search")).toHaveValue("gtls");
  await expect(page.locator("[data-rail]")).toHaveCount(0);
  await expect(page.getByTestId("grid")).toBeVisible();
});

test("the grid keeps its own arrow keys after a digit puts focus in it", async ({ page }) => {
  await page.goto(pageFor("level4"));
  await expect(page.getByTestId("grid")).toBeVisible();
  await stopTyping(page);

  await page.keyboard.press("Digit1");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  await expect(page.locator('tr[data-period="2"]')).toHaveClass(/\bcursor\b/);
  await expect(page.getByTestId("period")).toHaveText("2");
});

test("which panes are railed is remembered, and an expansion never is", async ({ page }) => {
  await reading(page, "level4", "maint_fee_pp", 62);

  await page.locator('[data-pane="cone"]').hover();
  await page.getByTestId("collapse-cone").click();
  await page.locator('[data-pane="grid"]').hover();
  await page.getByTestId("expand-grid").click();
  await expect(page.getByTestId("rail-cone")).toBeVisible();

  // Still one key, and the shape gained a field rather than changing one.
  const stored = await page.evaluate(() =>
    Object.fromEntries(
      Array.from({ length: localStorage.length }, (_, at) => {
        const key = localStorage.key(at) ?? "";
        return [key, localStorage.getItem(key)];
      }),
    ),
  );
  expect(Object.keys(stored)).toEqual(["gaspatchio-viewer.panes"]);
  const shape = JSON.parse(stored["gaspatchio-viewer.panes"] ?? "{}") as Record<string, unknown>;
  expect(shape).toMatchObject({
    top: expect.any(Number),
    cone: expect.any(Number),
    drawer: expect.any(Number),
    railed: ["cone"],
  });
  expect(Object.keys(shape)).not.toContain("expanded");

  // A file you send someone opens the way your page opens. The cone was
  // put away and stays away; the expansion was a gesture and is gone.
  await page.reload();
  await expect(page.getByTestId("rail-cone")).toBeVisible();
  await expect(page.getByTestId("grid")).toBeVisible();
  // Not the proof: it rides under the cone now, so a railed cone takes it too,
  // which is exactly why that rail has to speak for both.
  await expect(page.getByTestId("inspector")).toBeVisible();
  await expect(page.getByTestId("inspector")).toBeVisible();
});

test("a value stored before there were rails still opens the page", async ({ page }) => {
  await page.goto(pageFor("level4"));
  await expect(page.getByTestId("grid")).toBeVisible();
  await page.evaluate(() => {
    // Exactly what a page wrote before panes could be railed: three numbers and no rails.
    localStorage.setItem(
      "gaspatchio-viewer.panes",
      JSON.stringify({ top: 0.62, cone: 0.5, drawer: 320 }),
    );
  });

  await page.reload();
  await expect(page.getByTestId("grid")).toBeVisible();
  await expect(page.locator("[data-rail]")).toHaveCount(0);
});
