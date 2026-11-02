// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The comparison page with `gspio diff`'s book-wide reading beside its marks.
 *
 * Packed from the values vector: `fixtures/values-{before,after}.json`, one
 * model a fee rate apart over a revised book, with the `values` member of
 * `gspio diff`'s report over the two runs' results files carried as the page's
 * movement block (`fixtures/values-movement.json`, written by
 * `fixtures/values/export.py`). The page still derives every mark from the two
 * documents; beside each entry it states how far the line moved over the whole
 * book, greys a line the identity flags and whose numbers held -- labelled,
 * never hidden -- and holds its own reading of the one policy it carries to the
 * block's.
 */

import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { expect, test } from "@playwright/test";

/** The page `pack.mjs` wrote from the vector, the movement block carried. */
const PAGE = pathToFileURL(resolve("dist/values-after.html")).href;

test("each entry says how far it moved over the book, and the identity-only line is greyed", async ({
  page,
}) => {
  await page.goto(PAGE);
  await expect(page.getByTestId("changes")).toBeVisible();

  await expect(page.getByTestId("book-note")).toHaveText(
    "Over the whole book, as gspio diff read the two results files: 2 policies compared, " +
      "1 (P4) joined, 1 (P3) left. Moved in the book and not for this policy, so in no entry " +
      "here: premium, reserve@1.",
  );
  const fee = page.locator('[data-testid="changes"] li[data-node="fee@1"]');
  await expect(fee.getByTestId("change-book")).toHaveText("moved in 2 of 2 policies, worst 28.7% at P2");

  const waived = page.locator('[data-testid="changes"] li[data-node="waived@1"]');
  await expect(waived).toHaveClass(/identity-only/);
  await expect(waived.getByTestId("change-book")).toHaveText("identity onlyno number moved in 2 policies");

  const overBase = page.locator('[data-testid="changes"] li[data-node="fee_over_base@1"]');
  await expect(overBase.getByTestId("change-book")).toHaveText("moved in 2 of 2 policies, from 0 at P1");
});

test("the page's own reading of its policy agrees with the book's, so no finding is printed", async ({
  page,
}) => {
  await page.goto(PAGE);
  await expect(page.getByTestId("changes")).toBeVisible();
  await expect(page.getByTestId("cross-check")).toHaveCount(0);
});

test("a selected entry prints the commands that open its worst policy in both versions", async ({
  page,
}) => {
  await page.goto(PAGE);
  await page.locator('[data-testid="changes"] li[data-node="fee@1"] button').click();

  await expect(page.getByTestId("drill")).toHaveText(
    [
      "gspio calc-graph model.py model_points.csv --policies id:P2 -o before.audit.json",
      "gspio calc-graph model.py model_points.csv --policies id:P2 -o after.audit.json",
      "gspio diff before.audit.json after.audit.json --html policy.html",
    ].join("\n"),
  );
});
