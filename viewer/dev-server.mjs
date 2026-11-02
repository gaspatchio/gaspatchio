// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The page, over a wire, rebuilt on every save.
 *
 * `pack.mjs` writes a page once; this serves the same page and writes it again
 * every time a source file changes, then tells the browsers holding it to
 * reload. It exists for the one loop that a self-contained file makes slow:
 * change a colour, see the colour. Without it that loop is build, copy-assets,
 * pack, find the file, reload — which is long enough that a formatting pass
 * stops being worth doing.
 *
 * **What is served is what ships, and the difference is stated.** The document
 * is composed by the same function `pack.mjs` uses and
 * `gaspatchio_viewer.render()` mirrors line for line, over the same fonts and
 * the same favicon, with the bundle esbuild has just built under the settings
 * `build.mjs` builds under — minified, same target, same defines. Two things
 * differ from the bytes of a rendered page, both of them comments or close to
 * it, and neither of them anything a reader could see:
 *
 * - the two built assets arrive without the SPDX licence headers `build.mjs`
 *   prepends, because that build writes them and this one holds its output in
 *   memory. A block comment each, at the top of a minified file.
 * - one `<script>` at the end that listens for a reload, appended after the
 *   document rather than inside it, so a diff against a rendered page is one
 *   hunk at the bottom and two at the top.
 *
 * `--check` prints exactly that diff against a page the Python renderer wrote,
 * so the claim is measured rather than asserted. A page saved from this server
 * is a page with a dev script in it; the file an actuary opens still comes from
 * `gspio calc-graph --html`.
 *
 * Nothing here writes into the repository. The build is held in memory, the
 * committed assets under `python/gaspatchio_viewer/assets/` are read and never
 * written, and the artifacts are read from wherever `--artifacts` points.
 *
 * Usage, from `viewer/`:
 *
 *     node dev-server.mjs --artifacts /path/to/dir            # every .json in it
 *     node dev-server.mjs --artifacts DIR --host 100.x.y.z    # bind elsewhere
 *     node dev-server.mjs --artifacts DIR --port 8817
 *
 * The host defaults to the loopback address, because a server that binds to
 * every interface by default is a server that ends up on a café network. Pass
 * the Tailscale address to reach it from another machine on the tailnet.
 */

import { readFileSync, readdirSync, statSync, watch } from "node:fs";
import { createServer } from "node:http";
import { basename, extname, join } from "node:path";

import { context } from "esbuild";

const assets = "python/gaspatchio_viewer/assets";

/** One committed asset's text. The fonts, the favicon and the notices, not the bundle. */
function asset(name) {
  return readFileSync(`${assets}/${name}`, "utf8");
}

/** `text` with the three characters that would end an element. `_escaped()`. */
function escaped(text) {
  return text.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

/** What the notices' comment says first, before a blank line. `_NOTICES_HEAD`. */
const NOTICES_HEAD =
  "Third-party notices: the software and fonts this page carries that are\n" +
  "not Opio Inc.'s work, each with its licence. This is gaspatchio-viewer's\n" +
  "third-party-notices.txt, escaped for a comment, which two hyphens\n" +
  "together could close: each backslash is written as two, and each hyphen\n" +
  "that follows a hyphen has a backslash written before it. The text starts\n" +
  "after the blank line below and ends at the line break before the comment\n" +
  "closes. To read it back, replace each backslash and the character after\n" +
  "it with that character, from left to right.";

/**
 * The comment every page ends with: the head, then the notices, under the
 * escape the head states. `_notices_comment()`. The committed notices, as the
 * fonts are: this server's bundle is built in memory, and a dependency added
 * since the last `npm run copy-assets` is in neither the notices nor the
 * wheel until that is run.
 */
function noticesComment() {
  const escapedNotices = asset("third-party-notices.txt")
    .replaceAll("\\", "\\\\")
    .replace(/(?<=-)-/g, "\\-");
  return `<!--\n${NOTICES_HEAD}\n\n${escapedNotices}\n-->\n`;
}

/** One artifact, as the document carries it: one block, escaped the one way. */
function block(artifactJson) {
  return (
    '<script type="application/json" id="artifact">' +
    artifactJson.replaceAll("<", "\\u003c") +
    "</script>\n"
  );
}

/**
 * One self-contained HTML document around one artifact.
 *
 * Line for line, `pack.mjs`'s `render()` and `gaspatchio_viewer.render()`,
 * except that the bundle and the styles arrive as arguments rather than off the
 * disk — which is the whole reason this file can serve a build that has not
 * been written anywhere.
 */
function render(artifactJson, title, built) {
  const faviconHref = `data:image/svg+xml;base64,${Buffer.from(asset("favicon.svg").trim(), "utf8").toString("base64")}`;
  return (
    "<!doctype html>\n" +
    '<html lang="en">\n' +
    "<head>\n" +
    '<meta charset="utf-8">\n' +
    '<meta name="viewport" content="width=device-width, initial-scale=1">\n' +
    `<title>${escaped(title)}</title>\n` +
    `<link rel="icon" href="${faviconHref}">\n` +
    `<style>\n${built.css}\n${asset("fonts.css")}\n</style>\n` +
    "</head>\n" +
    "<body>\n" +
    block(artifactJson) +
    '<div id="root"></div>\n' +
    `<script>\n${built.js}\n</script>\n` +
    "</body>\n" +
    "</html>\n" +
    noticesComment()
  );
}

/**
 * The one line that makes this a dev server rather than a file server.
 *
 * An EventSource on a stream that emits a build number. A number higher than
 * the one this page was served with means the page is stale, so it reloads.
 * The scroll position and the period the reader was on are not kept: a reload
 * is a reload, and pretending otherwise would hide a state bug behind a state
 * restore.
 */
function reloadScript(build) {
  return (
    "<script>\n" +
    `(() => { const mine = ${String(build)};\n` +
    '  const source = new EventSource("/__reload");\n' +
    '  source.onmessage = (event) => { if (Number(event.data) > mine) location.reload(); };\n' +
    "})();\n" +
    "</script>\n"
  );
}

/** `--name value` from the command line, or the fallback. */
function option(name, fallback) {
  const at = process.argv.indexOf(`--${name}`);
  return at < 0 ? fallback : (process.argv[at + 1] ?? fallback);
}

const artifactsDir = option("artifacts", "fixtures");
const host = option("host", "127.0.0.1");
const port = Number(option("port", "8817"));

/** Every artifact in the directory, by the name its file carries. */
function artifacts() {
  return readdirSync(artifactsDir)
    .filter((file) => extname(file) === ".json")
    .map((file) => ({
      name: basename(file, ".json"),
      path: join(artifactsDir, file),
      bytes: statSync(join(artifactsDir, file)).size,
    }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

/** What the browser is told about, and what it is told to reload against. */
const state = { js: "", css: "", build: 0, listeners: new Set() };

/**
 * The parity claim in this file's own header, measured.
 *
 * Composes the page this server would serve for one artifact, asks the Python
 * renderer for the page it would write over the same artifact, and prints the
 * lines that differ. The expected answer is the two licence headers and nothing
 * else — the reload script is not in the comparison, because it is appended
 * after the document and this compares documents.
 *
 * @param name - The artifact to compare over.
 * @returns Nothing; prints, and exits non-zero if the difference is not the
 *   two headers.
 */
async function check(name) {
  const file = artifacts().find((one) => one.name === name);
  if (file === undefined) throw new Error(`no artifact called ${name} in ${artifactsDir}`);

  const mine = render(readFileSync(file.path, "utf8"), name, state);
  const python = option("python", "../bindings/python/.venv/bin/python");
  // UTF-8 both ways, whatever the platform's own encoding: the page ends
  // with the notices, which are not ASCII, and it is read back as UTF-8 below.
  const script =
    "import sys, gaspatchio_viewer;" +
    "page = gaspatchio_viewer.render(open(sys.argv[1], encoding='utf-8').read(), title=sys.argv[2]);" +
    "sys.stdout.buffer.write(page.encode('utf-8'))";
  const { execFileSync } = await import("node:child_process");
  const theirs = execFileSync(python, ["-c", script, file.path, name], {
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
  });

  // A licence header is inserted lines, so comparing by line number would call
  // every line after the first one different. Take the headers out of both and
  // the rest has to be equal byte for byte — which is the claim, stated as a
  // comparison that can only pass one way.
  const withoutHeaders = (page) => page.replaceAll(/\/\*![\s\S]*?\*\/\n?/g, "");
  const strippedMine = withoutHeaders(mine);
  const strippedTheirs = withoutHeaders(theirs);

  console.log(`served   ${String(Buffer.byteLength(mine))} bytes`);
  console.log(`rendered ${String(Buffer.byteLength(theirs))} bytes`);
  console.log(
    `licence headers account for ${String(Buffer.byteLength(theirs) - Buffer.byteLength(mine))} bytes`,
  );

  if (strippedMine === strippedTheirs) {
    console.log("identical with the licence headers removed — the page served is the page written");
    return;
  }

  const a = strippedMine.split("\n");
  const b = strippedTheirs.split("\n");
  const at = a.findIndex((line, i) => line !== b[i]);
  console.error("the pages have drifted — first difference:");
  console.error(`  served ${JSON.stringify((a[at] ?? "").slice(0, 90))}`);
  console.error(`  file   ${JSON.stringify((b[at] ?? "").slice(0, 90))}`);
  process.exitCode = 1;
}

/** Everything holding a page is told the build number moved. */
function announce() {
  state.build += 1;
  for (const listener of state.listeners) listener(state.build);
}

// The same settings build.mjs builds under, so what is served is the bundle
// that would ship rather than a friendlier one. Minified: an unminified bundle
// would rebuild a little faster and read nothing like the file an actuary opens
// if a rendering difference ever turned on it.
const ctx = await context({
  entryPoints: { viewer: "src/main.tsx" },
  bundle: true,
  minify: true,
  format: "iife",
  target: "es2020",
  jsx: "automatic",
  define: { "process.env.NODE_ENV": '"production"' },
  loader: { ".woff2": "dataurl" },
  outdir: "dist",
  write: false,
  plugins: [
    {
      name: "hold-the-build",
      setup(build) {
        build.onEnd((result) => {
          if (result.errors.length > 0) {
            console.error(`build failed with ${String(result.errors.length)} error(s)`);
            for (const error of result.errors) console.error(`  ${error.text}`);
            return;
          }
          for (const file of result.outputFiles ?? []) {
            if (file.path.endsWith(".js")) state.js = file.text;
            if (file.path.endsWith(".css")) state.css = file.text;
          }
          announce();
          console.log(`build ${String(state.build)} — ${new Date().toLocaleTimeString()}`);
        });
      },
    },
  ],
});
await ctx.rebuild();

const checkName = option("check", undefined);
if (checkName !== undefined) {
  await check(checkName);
  await ctx.dispose();
  process.exit(process.exitCode ?? 0);
}

await ctx.watch();

// An artifact changing is the other thing worth a reload: re-export a model and
// the page holding it is stale in exactly the way a source change makes it.
watch(artifactsDir, { persistent: false }, () => {
  announce();
});

/** The launcher. Deliberately plain: it is a list of doors, not a page to review. */
function index() {
  const rows = artifacts()
    .map(
      (file) =>
        `<li><a href="/${file.name}">${escaped(file.name)}</a>` +
        `<span>${(file.bytes / 1_000_000).toFixed(2)} MB</span></li>`,
    )
    .join("\n");
  return (
    "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">" +
    '<meta name="viewport" content="width=device-width, initial-scale=1">' +
    "<title>gaspatchio viewer — dev</title><style>" +
    "body{font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;margin:0;padding:3rem 2rem;" +
    "background:#fbfaf8;color:#1b1a17}" +
    "@media(prefers-color-scheme:dark){body{background:#171614;color:#e8e6e1}a{color:#9fc7ff}}" +
    "h1{font-size:1.1rem;font-weight:600;margin:0 0 .25rem}" +
    "p{margin:0 0 2rem;opacity:.65}" +
    "ul{list-style:none;margin:0;padding:0;max-width:34rem}" +
    "li{display:flex;justify-content:space-between;gap:2rem;padding:.7rem 0;" +
    "border-bottom:1px solid rgba(128,128,128,.22)}" +
    "li span{opacity:.5;font-variant-numeric:tabular-nums}" +
    "a{color:#1a4fa0;text-decoration:none}a:hover{text-decoration:underline}" +
    "</style></head><body><h1>gaspatchio viewer</h1>" +
    `<p>build ${String(state.build)} · reloads on save</p><ul>\n${rows}\n</ul></body></html>\n`
  );
}

createServer((request, response) => {
  const path = (request.url ?? "/").split("?")[0];

  if (path === "/__reload") {
    response.writeHead(200, {
      "content-type": "text/event-stream",
      "cache-control": "no-cache",
      connection: "keep-alive",
    });
    response.write(`data: ${String(state.build)}\n\n`);
    const listener = (build) => response.write(`data: ${String(build)}\n\n`);
    state.listeners.add(listener);
    request.on("close", () => state.listeners.delete(listener));
    return;
  }

  if (path === "/" || path === "/index.html") {
    response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    response.end(index());
    return;
  }

  const name = decodeURIComponent(path.slice(1)).replace(/\.html$/, "");
  const file = artifacts().find((one) => one.name === name);
  if (file === undefined) {
    response.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    response.end(`no artifact called ${name} in ${artifactsDir}\n`);
    return;
  }

  const page = render(readFileSync(file.path, "utf8"), name, state);
  response.writeHead(200, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" });
  // The one line that is not in the shipped page, appended after the document
  // rather than inside it, so a diff against a rendered page is one hunk.
  response.end(page + reloadScript(state.build));
}).listen(port, host, () => {
  console.log(`serving ${String(artifacts().length)} artifacts from ${artifactsDir}`);
  console.log(`  http://${host}:${String(port)}/`);
});
