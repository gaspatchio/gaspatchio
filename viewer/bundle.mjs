// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * What the page is built from, and whose it is.
 *
 * `build.mjs` bundles the reader with esbuild and writes the assets the wheel
 * ships. Those assets carry other people's code -- React, the cone's layout and
 * its virtualisation, d3's pan and zoom -- and three font faces that are not
 * this repository's work either. Each was licensed on the condition that its
 * notice travels with it. So the build does not keep a list of what it bundled:
 * it asks esbuild, through the metafile, and writes every package's own licence
 * file into `third-party-notices.txt` beside the assets.
 *
 * One package can carry another inside its own distributed file, where the
 * metafile sees only the outer one: `@dagrejs/dagre` ships graphlib inside
 * `dagre.esm.js`. A bundled file's source map names what went into it, so the
 * map is read as well, and a package found there is listed as carried by the
 * package that ships it.
 *
 * A bundled file can also point at a notice of its own. esbuild keeps the
 * legal comment `@dagrejs/dagre`'s file opens with -- "For license information
 * please see dagre.esm.js.LEGAL.txt" -- in the bundle, so the text it names is
 * carried into that package's section under its own file name.
 *
 * A bundled package with no licence file of its own is refused by name rather
 * than listed without one. A notices file that quietly skipped it would say the
 * page carries less than it does.
 *
 * Kept apart from `build.mjs` so that `test/notices.test.ts` can bundle with
 * exactly these options and hold the committed notices to what the bundle
 * holds, without writing a file.
 */

import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";

/** The esbuild options `build.mjs` bundles the page with. */
export const bundleOptions = {
  entryPoints: { viewer: "src/main.tsx" },
  bundle: true,
  minify: true,
  format: "iife",
  target: "es2020",
  jsx: "automatic",
  define: { "process.env.NODE_ENV": '"production"' },
  loader: { ".woff2": "dataurl" },
  outdir: "dist",
};

/**
 * The faces `fonts.css` inlines, by family, with the copyright lines the SIL
 * Open Font License asks to travel with them. They are the documentation site's
 * identity, which the viewer shares, and REUSE.toml annotates the files under
 * `fonts/` the same way.
 */
export const FONT_FAMILIES = [
  {
    family: "iA Writer Quattro S",
    copyright: ["Copyright (c) 2018 iA Inc., with Reserved Font Name iA Writer"],
    faces: [
      { weight: 400, file: "iAWriterQuattroS-Regular.woff2" },
      { weight: 700, file: "iAWriterQuattroS-Bold.woff2" },
    ],
  },
  {
    family: "Zed Plex Mono",
    copyright: [
      "Copyright (c) 2017 IBM Corp., with Reserved Font Name Plex",
      "Copyright (c) 2022 Zed Industries, Inc.",
    ],
    faces: [{ weight: 400, file: "ZedPlexMono-Regular.woff2" }],
  },
];

/** The built files, in the order a notice names them. */
const OUTPUT_ORDER = ["viewer.js", "viewer.css"];

const LICENCE_FILE = /^(licen[cs]e|copying)([-._].*)?$/i;
const SOURCE_MAP_URL = /^\s*(?:\/\/|\/\*)[#@]\s*sourceMappingURL=([^\s*]+)/gm;

/** Compare by UTF-16 code unit, which no locale can reorder. */
function byCodeUnit(a, b) {
  if (a < b) return -1;
  return a > b ? 1 : 0;
}

/** The package a path under node_modules belongs to, and that package's directory. */
function packageOf(path) {
  const at = path.lastIndexOf("node_modules/");
  if (at < 0) return null;
  const parts = path.slice(at + "node_modules/".length).split("/");
  const name = parts[0].startsWith("@") ? `${parts[0]}/${parts[1]}` : parts[0];
  return { name, root: `${path.slice(0, at)}node_modules/${name}` };
}

/** The packages a bundled file's own source map says went into it. */
function carriedBy(file) {
  const text = readFileSync(file, "utf8");
  const url = [...text.matchAll(SOURCE_MAP_URL)].map((match) => match[1]).at(-1);
  let map;
  if (url?.startsWith("data:")) {
    map = Buffer.from(url.slice(url.indexOf(",") + 1), "base64").toString("utf8");
  } else {
    const path = url === undefined ? `${file}.map` : join(dirname(file), url);
    if (!existsSync(path)) return [];
    map = readFileSync(path, "utf8");
  }
  const sources = JSON.parse(map).sources ?? [];
  return [...new Set(sources.map((source) => packageOf(source)?.name).filter(Boolean))];
}

/** Where `name` is installed, looked for the way Node looks for it from `from`. */
function installed(name, from, top) {
  const stop = resolve(top);
  for (let at = resolve(from); ; at = dirname(at)) {
    const candidate = join(at, "node_modules", name);
    if (existsSync(join(candidate, "package.json"))) return candidate;
    if (at === stop || at === dirname(at)) return null;
  }
}

/** One package, read from its own directory: version, licence, licence files. */
function describe(name, root, cwd) {
  const manifest = JSON.parse(readFileSync(join(cwd, root, "package.json"), "utf8"));
  const files = readdirSync(join(cwd, root))
    .filter((file) => LICENCE_FILE.test(file))
    .sort(byCodeUnit);
  if (files.length === 0) {
    throw new Error(
      `${name}@${manifest.version} is in the page's bundle and ships no licence file, so ` +
        "third-party-notices.txt cannot carry its notice. Take it out of the bundle, or " +
        "teach viewer/bundle.mjs where its licence text is.",
    );
  }
  if (typeof manifest.license !== "string" || manifest.license === "") {
    throw new Error(
      `${name}@${manifest.version} is in the page's bundle and its package.json names no ` +
        "licence, so the built files' SPDX headers cannot say what they carry.",
    );
  }
  return {
    name,
    version: manifest.version,
    licence: manifest.license,
    licenceFiles: files.map((file) => ({
      name: file,
      text: readFileSync(join(cwd, root, file), "utf8").replaceAll("\r\n", "\n"),
    })),
  };
}

/**
 * Every third-party package the bundle holds, and the built files it lands in.
 *
 * Read from esbuild's metafile. An input counts when it contributed bytes to an
 * output, so a module the bundler shook out is not listed. A package carried
 * inside another package's distributed file is found through that file's
 * source map, and `via` names the package that carries it -- unless it is also
 * bundled in its own right, when `via` is null.
 *
 * @param metafile - esbuild's metafile for the build.
 * @param cwd - The directory esbuild resolved the metafile's paths against.
 * @returns The packages, sorted by name.
 */
export function bundledPackages(metafile, cwd = process.cwd()) {
  const found = new Map();
  const note = (name, root, output, carrier) => {
    const entry = found.get(name) ?? {
      ...describe(name, root, cwd),
      outputs: new Set(),
      carriers: new Set(),
      direct: false,
    };
    entry.outputs.add(output);
    if (carrier === null) entry.direct = true;
    else entry.carriers.add(carrier);
    found.set(name, entry);
  };
  // A notice a bundled file points at, filed with the package that ships it.
  const legal = (name, root, file) => {
    const entry = found.get(name);
    const own = relative(join(cwd, root), file).split(sep).join("/");
    if (!entry.licenceFiles.some((existing) => existing.name === own)) {
      const text = readFileSync(file, "utf8").replaceAll("\r\n", "\n");
      entry.licenceFiles.push({ name: own, text });
    }
  };
  for (const [outputPath, output] of Object.entries(metafile.outputs)) {
    const outputName = outputPath.split("/").at(-1);
    for (const [input, { bytesInOutput }] of Object.entries(output.inputs)) {
      const owner = packageOf(input);
      if (owner === null || bytesInOutput === 0) continue;
      note(owner.name, owner.root, outputName, null);
      const pointedAt = `${join(cwd, input)}.LEGAL.txt`;
      if (existsSync(pointedAt)) legal(owner.name, owner.root, pointedAt);
      for (const name of carriedBy(join(cwd, input))) {
        if (name === owner.name) continue;
        const root = installed(name, join(cwd, owner.root), cwd);
        if (root === null) {
          throw new Error(
            `${owner.name} carries ${name} inside ${input}, and ${name} is not installed, ` +
              "so third-party-notices.txt cannot read its licence file.",
          );
        }
        note(name, relative(cwd, root), outputName, owner.name);
      }
    }
  }
  return [...found.values()]
    .map(({ outputs, carriers, direct, ...pkg }) => ({
      ...pkg,
      outputs: OUTPUT_ORDER.filter((name) => outputs.has(name)).concat(
        [...outputs].filter((name) => !OUTPUT_ORDER.includes(name)).sort(byCodeUnit),
      ),
      via: direct ? null : [...carriers].sort(byCodeUnit).join(", "),
    }))
    .sort((a, b) => byCodeUnit(a.name, b.name));
}

/**
 * The SPDX expression for one built file: this repository's Apache-2.0 and the
 * licence of every package bundled into it.
 *
 * @param packages - What `bundledPackages()` returned.
 * @param output - The built file's name, `viewer.js` or `viewer.css`.
 * @returns For example `Apache-2.0 AND ISC AND MIT`.
 */
export function licenceExpression(packages, output) {
  const licences = new Set(
    packages
      .filter((pkg) => pkg.outputs.includes(output))
      .map((pkg) => (/\s(OR|WITH)\s/.test(pkg.licence) ? `(${pkg.licence})` : pkg.licence)),
  );
  licences.delete("Apache-2.0");
  return ["Apache-2.0", ...[...licences].sort(byCodeUnit)].join(" AND ");
}

/**
 * The third-party notices for the built page, as one text file.
 *
 * Each package gets its name, the version bundled, its licence, the built file
 * that carries it, and its own licence file verbatim. The font faces follow,
 * with their copyright lines and the text of the SIL Open Font License.
 *
 * @param packages - What `bundledPackages()` returned.
 * @param families - `FONT_FAMILIES`.
 * @param oflText - The text of LICENSES/OFL-1.1.txt.
 * @returns The file's contents.
 */
export function thirdPartyNotices(packages, families, oflText) {
  const rule = "=".repeat(78);
  const thin = "-".repeat(78);
  const sections = packages.map((pkg) => {
    const carried = pkg.via === null ? "" : `, inside ${pkg.via}'s own distributed file`;
    const files = pkg.licenceFiles.map((file) => `${thin}\n${file.name}\n\n${file.text.trimEnd()}\n`);
    return (
      `${rule}\n${pkg.name} ${pkg.version}\nLicence: ${pkg.licence}\n` +
      `In: ${pkg.outputs.join(" and ")}${carried}\n${files.join("")}`
    );
  });
  const fonts = families.map((family) => {
    const files = family.faces.map((face) => face.file).join(", ");
    return (
      `${rule}\n${family.family}\nLicence: OFL-1.1\nIn: fonts.css (${files})\n${thin}\n` +
      `${family.copyright.join("\n")}\n`
    );
  });
  return (
    "Third-party software in gaspatchio-viewer's built page\n\n" +
    "viewer.js, viewer.css and fonts.css carry the packages and font faces below,\n" +
    "which are not Opio Inc.'s work. Each package is listed at the version bundled,\n" +
    "with the built file it is in and its own licence file, verbatim. Written by\n" +
    "viewer/build.mjs from esbuild's metafile on every build; edits here are lost.\n\n" +
    `${sections.join("\n")}\n${fonts.join("\n")}\n${rule}\n` +
    "SIL Open Font License 1.1, under which each face above is distributed\n" +
    `${thin}\n\n${oflText.trimEnd()}\n`
  );
}
