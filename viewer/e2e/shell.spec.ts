// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The header strip: which file this is, and which policy the values are.
 *
 * Three facts and a control, and all three facts come out of the envelope
 * rather than out of this test. The fingerprint is the one a reviewer quotes
 * back in an email, so it is worth knowing both that the eight hex on screen
 * are the file's own and that the control puts the whole of it somewhere the
 * reviewer can paste from.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { expect, test } from "@playwright/test";

import type { Artifact } from "../src/reader/types";

const PAGE = resolve("dist/level4.html");

const level4 = JSON.parse(readFileSync(resolve("fixtures/level4.json"), "utf8")) as Artifact;
const fingerprint = level4.graph_fingerprint;
const eightHex = (fingerprint.split(":").pop() ?? "").slice(0, 8);

test("the strip names the model file, the policy and the graph", async ({ page }) => {
  await page.goto(pathToFileURL(PAGE).href);

  const strip = page.locator(".identity");
  await expect(strip).toContainText((level4.model.source_path ?? "").split("/").pop() ?? "");
  await expect(strip).toContainText(`policy ${level4.enrichment?.policy_id ?? ""}`);
  await expect(page.getByTestId("fingerprint")).toHaveText(eightHex);
  await expect(page.getByTestId("fingerprint")).toHaveAttribute("title", fingerprint);
});

test("the fingerprint control puts the whole fingerprint where it can be pasted", async ({
  page,
  context,
  browserName,
}) => {
  // Reading the clipboard back is the assertion worth making, and only one of
  // the two engines will grant it from a file on a disk. In the other the
  // control's own state is what there is to hold to: it says `data-copied` only
  // after the browser reported the write, and says so either way, which is why
  // a failed write is visible rather than silent.
  if (browserName === "chromium") {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  }
  await page.goto(pathToFileURL(PAGE).href);

  await page.getByTestId("fingerprint").click();
  await expect(page.getByTestId("fingerprint")).toHaveAttribute("data-copied", "true");

  if (browserName === "chromium") {
    const pasted = await page.evaluate(() => navigator.clipboard.readText());
    expect(pasted).toBe(fingerprint);
  }
});

test("the row cursor moves on the slider and is printed once", async ({ page }) => {
  await page.goto(pathToFileURL(PAGE).href);

  await page.getByTestId("cursor").fill("40");
  await expect(page.getByTestId("period")).toHaveText("40");
  await expect(page.locator('tr[data-period="40"]')).toHaveClass(/\bcursor\b/);
  await expect(page.locator("tr.cursor")).toHaveCount(1);
});

test("the four regions are laid out, and all four are drawn", async ({ page }) => {
  await page.goto(pathToFileURL(PAGE).href);

  await expect(page.getByTestId("grid")).toBeVisible();
  await expect(page.getByTestId("cone")).toBeVisible();
  await expect(page.getByTestId("proof")).toBeVisible();
  // The fourth region said its own name and nothing else until the drawer was
  // built; it is built, so it is held to being the drawer.
  await expect(page.locator('[data-region="inspector"]').getByTestId("inspector")).toBeVisible();
});

test("the page remembers where the dividers were, and stores nothing else", async ({ page }) => {
  await page.goto(pathToFileURL(PAGE).href);
  await expect(page.getByTestId("grid")).toBeVisible();

  const stored = await page.evaluate(() =>
    Object.fromEntries(
      Array.from({ length: localStorage.length }, (_, at) => {
        const key = localStorage.key(at) ?? "";
        return [key, localStorage.getItem(key)];
      }),
    ),
  );
  expect(Object.keys(stored)).toEqual(["gaspatchio-viewer.panes"]);
  expect(JSON.parse(stored["gaspatchio-viewer.panes"] ?? "{}")).toMatchObject({
    top: expect.any(Number),
    cone: expect.any(Number),
    drawer: expect.any(Number),
  });
});

/**
 * Where the page puts a reader who has just opened it.
 *
 * It used to put them in front of three empty panes and a box saying "search
 * for a column", which asks somebody who did not write this model to type a
 * name they do not know. It opens on the model's last result now, and the box
 * offers the rest of them when it is empty.
 */
test("the page opens on the model's last result, not on nothing", async ({ page }) => {
  await page.goto(pathToFileURL(PAGE).href);
  await expect(page.getByTestId("grid")).toBeVisible();

  // Nothing typed and nothing clicked: the proof is already working something
  // out, the cone is already drawn around it, and the drawer holds its record.
  await expect(page.getByTestId("proof")).toContainText("pv_net_cf");
  await expect(page.getByTestId("cone-count")).toBeVisible();
  await expect(page.getByTestId("inspector")).toContainText("pv_net_cf");
});

test("an empty search box offers the columns nothing else reads", async ({ page }) => {
  await page.goto(pathToFileURL(PAGE).href);
  await expect(page.getByTestId("grid")).toBeVisible();

  // Not offered until it is asked for.
  await expect(page.getByTestId("search-ends")).toHaveCount(0);

  await page.getByTestId("search").click();
  const offered = page.getByTestId("search-ends");
  await expect(offered).toBeVisible();

  // Headed with what was measured rather than with "results": one of these is a
  // date label on every model in this corpus, and the file carries nothing that
  // separates a result from a leftover.
  await expect(offered).toContainText("nothing else reads these");
  await expect(offered.locator(".ends-name")).toContainText(["projection_date"]);

  // And one is a way in: clicking a name selects that column.
  await offered.locator('[data-end="pv_claims_death"]').click();
  await expect(page.getByTestId("proof")).toContainText("pv_claims_death");

  // Typing puts it away — a reader who is narrowing does not want a list of
  // somewhere else to go sitting over the grid.
  await page.getByTestId("search").click();
  await expect(page.getByTestId("search-ends")).toBeVisible();
  await page.getByTestId("search").fill("mort");
  await expect(page.getByTestId("search-ends")).toHaveCount(0);
});
