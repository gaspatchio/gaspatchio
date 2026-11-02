// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * What the drawer says about the members the record carries beyond the model's file.
 *
 * Each member has more than one shape, and each shape is its own sentence: a
 * revision, no working tree, git unable to answer, nothing recorded at all.
 * They are tested here, off the reader, because which sentence a shape earns
 * is a decision about meaning; `e2e/record.spec.ts` holds the drawer to these
 * same words on the page.
 */

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import {
  gitSaid,
  modulesSaid,
  tableShapedSaid,
  tableSourceSaid,
  versionsSaid,
} from "../src/reader/record";
import type { Artifact } from "../src/reader/types";

/** The record fixture: a real export whose model rests on a helper and three tables. */
const record = JSON.parse(
  readFileSync(new URL("../fixtures/record.json", import.meta.url), "utf8"),
) as Artifact;

/** One of its tables, by name. */
function table(name: string): unknown {
  return (record.assumptions as { name: string }[]).find((entry) => entry.name === name);
}

describe("gitSaid", () => {
  it("states a revision as its commit and whether the tree was dirty", () => {
    expect(gitSaid({ commit: "3f2a91c", dirty: false })).toEqual({ commit: "3f2a91c", dirty: "false" });
  });

  it("says a null git is an export outside a working tree", () => {
    expect(record.model.git).toBeNull();
    expect(gitSaid(record.model.git).commit).toBe("exported outside a git working tree");
  });

  it("prints why git could not answer, and never a dirty row of undefined", () => {
    const detail = "fatal: detected dubious ownership in repository at '..'";
    const said = gitSaid({ omitted: "unavailable", detail });
    expect(said.commit).toBe(`git could not answer: ${detail}`);
    expect(said.dirty).toBe("not recorded, because git could not answer");
    for (const shape of [null, undefined, { omitted: "unavailable" }, { commit: "abc" }]) {
      expect(gitSaid(shape).dirty).not.toContain("undefined");
      expect(gitSaid(shape).commit).not.toContain("undefined");
    }
  });

  it("says a document written before the member records none", () => {
    expect(gitSaid(undefined)).toEqual({ commit: "no git commit recorded", dirty: "no git state recorded" });
  });
});

describe("modulesSaid", () => {
  it("names each module beside the model with its short stamp, the whole of it on the title", () => {
    const modules = record.model.modules ?? [];
    expect(modules.map((entry) => entry.path)).toEqual(["loadings.py"]);
    const [said] = modulesSaid(modules);
    expect(said?.label).toBe("loadings.py");
    expect(said?.value).toBe(modules[0]?.fingerprint?.slice("sha256:".length, "sha256:".length + 8));
    expect(said?.title).toBe(modules[0]?.fingerprint);
  });

  it("says an empty list is a model importing nothing from beside itself", () => {
    expect(modulesSaid([])).toEqual([
      { name: "model.modules", label: "modules", value: "imports nothing from beside itself" },
    ]);
  });

  it("says a document with no list records none, and an unread module could not be read", () => {
    expect(modulesSaid(undefined)[0]?.value).toBe("no modules recorded");
    expect(modulesSaid([{ path: "helpers.py", fingerprint: null }])[0]?.value).toBe(
      "the producer could not read it",
    );
  });
});

describe("versionsSaid", () => {
  const stated = {
    name: "gaspatchio",
    version: "1.0.0",
    versions: {
      core_version: "1.0.0",
      extension_version: "1.0.0",
      extension_sha256: "sha256:a81975366bb2bf50a97601ea363dafe7f1595c7fc1b5754e8f1dda2e0b57ebde",
      polars_version: "1.42.1",
      python_version: "3.13.0",
      platform: "macOS-15.7.9-x86_64-i386-64bit-Mach-O",
      imports: { numpy: "2.3.1", polars: "1.42.1" },
    },
  };

  it("states one fact per key, under the file's own spelling and in its order", () => {
    const said = versionsSaid(stated);
    expect(said.map((fact) => fact.label)).toEqual(Object.keys(stated.versions));
    expect(said.find((fact) => fact.label === "polars_version")?.value).toBe("1.42.1");
    expect(said.find((fact) => fact.label === "imports")?.value).toBe("numpy 2.3.1, polars 1.42.1");
  });

  it("shortens the extension's digest and keeps the whole of it on the title", () => {
    const sha = versionsSaid(stated).find((fact) => fact.label === "extension_sha256");
    expect(sha?.value).toBe("a8197536");
    expect(sha?.title).toBe(stated.versions.extension_sha256);
  });

  it("prints a sentence where the file states one in place of the digest", () => {
    const moved = { versions: { extension_sha256: "unavailable: the file on disk is not the one loaded" } };
    expect(versionsSaid(moved)[0]?.value).toBe("unavailable: the file on disk is not the one loaded");
  });

  it("says withheld versions were withheld, and absent ones were not recorded", () => {
    expect(record.producer).toMatchObject({ versions: { omitted: "withheld" } });
    expect(versionsSaid(record.producer)).toEqual([
      { name: "producer.versions", label: "versions", value: "withheld: the exporter was asked not to state them" },
    ]);
    expect(versionsSaid({ name: "gaspatchio", version: "1.0.0" })[0]?.value).toBe("no library versions recorded");
  });

  it("says an empty imports is a model importing nothing installed", () => {
    const said = versionsSaid({ versions: { imports: {} } });
    expect(said[0]?.value).toBe("none: the model imports nothing installed but the standard library");
  });
});

describe("tableSourceSaid and tableShapedSaid", () => {
  it("names the file a plain read came from, and says nothing more", () => {
    expect(tableSourceSaid(table("record_lapse"))).toBe("read from lapse.csv");
    expect(tableShapedSaid(table("record_lapse"))).toBeNull();
  });

  it("says a reshaped table cannot be held against its file, in verify's words", () => {
    expect(tableSourceSaid(table("record_mortality"))).toBe("read from mortality.csv");
    expect(tableShapedSaid(table("record_mortality"))).toBe(
      "age renamed from Age: verify cannot hold this table against its file.",
    );
  });

  it("says a table built from a frame was built in code", () => {
    expect(tableSourceSaid(table("record_expense"))).toBe("built from a frame in code");
  });

  it("says the file does not say where an entry records nothing", () => {
    expect(tableSourceSaid({ kind: "table", name: "old" })).toBe(
      "the file does not say what this table was read from",
    );
  });

  it("words every step the way verify does", () => {
    const steps = [
      { step: "cast", column: "age", to: "Int64" },
      { step: "melted", column: "rate", from: ["Male", "Female"] },
      { step: "set", column: "table_id", from: null },
      { step: "computed", column: "band", from: null },
    ];
    expect(tableShapedSaid({ shaped_by: steps })).toBe(
      "age cast to Int64; rate melted from the columns Male, Female; table_id set to a constant " +
        "in code; band computed in code: verify cannot hold this table against its file.",
    );
  });
});
