// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * Playwright, over a file on a disk.
 *
 * There is no server here and there will not be one: the thing under test is
 * an HTML file somebody was sent, opened by double-clicking it. `webServer` is
 * left undefined deliberately rather than by omission — a page served over
 * HTTP is a different page, with a different origin and different rules about
 * what it may read, and it is not the one this repository ships.
 *
 * Two engines, because the page is opened by whoever was sent it: Chromium for
 * Chrome and Edge, WebKit for Safari. Firefox joins when someone asks.
 */

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  // A page that took a retry to open is a page that did not open.
  retries: 0,
  reporter: [["list"]],
  webServer: undefined,
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
});
