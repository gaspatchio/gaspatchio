// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";

import { buildIndex } from "../src/reader/index";
import { parseArtifacts } from "../src/reader/parse";
import { axisSummary, policyName } from "../src/reader/policies";
import { Header } from "../src/shell/Header";
import { initialSelection } from "../src/state/selection";
import { Inspector } from "../src/views/Inspector";

function fixture(name: string) {
  const result = parseArtifacts([readFileSync(new URL(`../fixtures/${name}.json`, import.meta.url), "utf8")]);
  if (result.refused) throw new Error(result.sentence);
  return result.artifacts[0]!;
}

const portfolio = fixture("portfolio");
const plain = fixture("level4");
const noop = () => {};

function header(at: number) {
  return renderToStaticMarkup(createElement(Header, {
    index: buildIndex(portfolio, at), note: null, choosePolicy: noop, showHoles: noop,
  }));
}

function inspector(file = plain, tab: "model" | "node" = "model", nodeId = "net_cf@1") {
  return renderToStaticMarkup(createElement(Inspector, {
    index: buildIndex(file), selection: { ...initialSelection, nodeId }, dispatch: noop,
    tab, setTab: noop, sourceAt: null,
  }));
}

it("names the selected context without changing canonical entry names", () => {
  expect(header(0)).toContain('<label for="policy">portfolio</label>');
  const at = portfolio.policies.findIndex((entry) => entry.aggregation === null);
  expect(header(at)).toContain('<label for="policy">policy</label>');
  expect(policyName(portfolio.policies[0]!)).toBe(`fold · ${portfolio.policies[0]!.aggregation}`);
  expect(axisSummary(portfolio.policies)).toBe("1 policy and 2 portfolio folds");
  expect(inspector(portfolio)).toContain("portfolio fold");
});

it("distinguishes an unnamed policy from a file carrying no values", () => {
  const unnamed = { ...plain, policies: plain.policies.map((entry) => ({ ...entry, policy_id: null })) };
  expect(inspector(unnamed)).toContain("no id recorded");
  expect(inspector(unnamed)).not.toContain("this file carries no values");
  expect(inspector(fixture("no-values"))).toContain("this file carries no values");
});

it("exposes exact direct-input versions and retains the complete record order", () => {
  const markup = inspector(plain, "node");
  const node = plain.nodes.find((entry) => entry.id === "net_cf@1")!;
  expect([...markup.matchAll(/data-input="([^"]+)"/g)].map((match) => match[1])).toEqual(node.reads);
  expect([...markup.matchAll(/data-member="([^"]+)"/g)].map((match) => match[1])).toEqual(Object.keys(node));
  expect(markup.match(/aria-expanded="false"/g)).toHaveLength(2);
});
