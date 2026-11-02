// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { parseArtifacts } from "../src/reader/parse";
import { READS_SCHEMA } from "../src/reader/types";

const level4 = readFileSync(new URL("../fixtures/level4.json", import.meta.url), "utf8");
const corpus = readFileSync(
  new URL("../../bindings/python/gaspatchio/schemas/conformance/corpus.json", import.meta.url),
  "utf8",
);

describe("parseArtifacts", () => {
  it("reads an audit artifact of the edition it says it reads", () => {
    const r = parseArtifacts([level4]);
    expect(r.refused).toBe(false);
    if (!r.refused) expect(r.artifacts[0].nodes.length).toBe(128);
  });

  it("reads the published corpus", () => {
    expect(parseArtifacts([corpus]).refused).toBe(false);
  });

  it("refuses a schema it does not read, naming both", () => {
    const r = parseArtifacts([level4.replace(READS_SCHEMA, "gaspatchio-graph/v0-preview.9")]);
    expect(r.refused).toBe(true);
    if (r.refused) {
      expect(r.sentence).toContain("gaspatchio-graph/v0-preview.9");
      expect(r.sentence).toContain(`reads ${READS_SCHEMA}`);
    }
  });

  it("accepts the executable profile and says so", () => {
    const r = parseArtifacts([level4.replace('"profile": "audit"', '"profile": "executable"')]);
    expect(r.refused).toBe(false);
    if (!r.refused) expect(r.artifacts[0].profile).toBe("executable");
  });

  it("refuses malformed JSON in one sentence", () => {
    const r = parseArtifacts(["{ not json"]);
    expect(r.refused).toBe(true);
    if (r.refused) expect(r.sentence).toMatch(/could not be read as JSON/);
  });

  it("keeps a second artifact whose model file is named differently, as gspio diff compares it", () => {
    // A differing `model.source_path` is not a refusal: `gspio diff` compares
    // the pair, and the page refuses what the report refuses and nothing else.
    const other = level4.replace('"source_path": "model.py"', '"source_path": "other_model.py"');
    const r = parseArtifacts([level4, other]);
    expect(r.refused).toBe(false);
    if (r.refused) return;
    expect(r.artifacts).toHaveLength(2);
    expect(r.notice).toBeUndefined();
  });

  it("shows the first artifact and refuses a second under another fingerprint algorithm", () => {
    const algorithm = /"fingerprint_algorithm": "([^"]+)"/.exec(level4)?.[1] ?? "";
    const other = level4.replace(
      `"fingerprint_algorithm": "${algorithm}"`,
      '"fingerprint_algorithm": "gspv0-preview-2"',
    );
    const r = parseArtifacts([level4, other]);
    // The first is shown, the second refused, and no comparison offered
    // between them -- the one pair `gspio diff` refuses too.
    expect(r.refused).toBe(false);
    if (r.refused) return;
    expect(r.artifacts).toHaveLength(1);
    expect(r.notice).toContain("gspv0-preview-2");
    expect(r.notice).toContain(algorithm);
  });

  it("keeps a second artifact of the same model however far its graph moved", () => {
    const edited = level4.replace(
      /"graph_fingerprint": "sha256:[0-9a-f]{64}"/,
      '"graph_fingerprint": "sha256:' + "0".repeat(64) + '"',
    );
    const r = parseArtifacts([level4, edited]);
    expect(r.refused).toBe(false);
    if (r.refused) return;
    expect(r.artifacts).toHaveLength(2);
    expect(r.notice).toBeUndefined();
  });
});
