#!/usr/bin/env node
import {
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  buildPayload,
  changedFileInventory,
  compareInventories,
  git,
  parseArgs,
  readJSON,
  requireOptions,
  resolveRepository,
  run,
  validateScope,
} from "./review-lib.mjs";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const defaultTemplate = path.resolve(scriptDirectory, "../assets/review-template.html");
const payloadMarker = "__REVIEW_DATA__";

function usage() {
  return `Usage:
  node build-review.mjs --scope <scope.json> --content <content.json> --output <review.html> [--repo <path>] [--template <template.html>]

Builds one self-contained review file. The bundled renderer is used unless a
custom template is supplied. A custom template must contain __REVIEW_DATA__
exactly once in an inert <script id="review-data" type="application/json"> block.`;
}

try {
  if (process.argv.includes("--help") || process.argv.includes("-h")) {
    console.log(usage());
    process.exit(0);
  }
  const options = parseArgs(process.argv.slice(2));
  requireOptions(options, ["scope", "content", "output"]);
  const scopePath = path.resolve(options.scope);
  const contentPath = path.resolve(options.content);
  const outputPath = path.resolve(options.output);
  const templatePath = path.resolve(options.template ?? defaultTemplate);
  const scope = readJSON(scopePath, "frozen scope");
  const content = readJSON(contentPath, "review content");
  const repo = resolveRepository(options.repo ?? scope.repository);

  validateScope(scope, repo, { reconcileRefs: true });
  const { payload, warnings } = buildPayload(repo, scope, content);
  const template = readFileSync(templatePath, "utf8");
  if (template.split(payloadMarker).length !== 2) {
    throw new Error(`${templatePath} must contain ${payloadMarker} exactly once`);
  }
  const serialized = JSON.stringify(payload).replaceAll("<", "\\u003c");
  const html = template.replace(payloadMarker, serialized);
  mkdirSync(path.dirname(outputPath), { recursive: true });
  writeFileSync(outputPath, html);

  verifyArtifact({ html, payload, repo, scope, outputPath });
  validateScope(scope, repo, { reconcileRefs: true });

  for (const warning of warnings) console.error(`warning: ${warning}`);
  const counts = payload.meta.statusCounts;
  console.log(`Built ${outputPath}`);
  console.log(
    `${payload.meta.fileCount} files (A ${counts.A}, M ${counts.M}, D ${counts.D}); `
    + `${payload.meta.hierarchyNodeCount} shared nodes; ${payload.meta.hierarchyPathCount} paths; `
    + `depth ${payload.meta.hierarchyDepth}; ${statSync(outputPath).size} bytes`,
  );
  console.log(`${payload.meta.mergeBase}..${payload.meta.analyzedHead}`);
  console.log(`Renderer: ${templatePath === defaultTemplate ? "bundled template" : templatePath}`);
  console.log("Mechanical verification passed");
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  console.error(usage());
  process.exitCode = 1;
}

function verifyArtifact({ html, payload, repo, scope, outputPath }) {
  const payloadMatch = html.match(/<script\s+id=["']review-data["']\s+type=["']application\/json["']>([\s\S]*?)<\/script>/i);
  if (!payloadMatch) throw new Error("Generated HTML does not contain the inert review-data script block");
  let embedded;
  try {
    embedded = JSON.parse(payloadMatch[1]);
  } catch (error) {
    throw new Error(`Embedded review JSON does not parse: ${error instanceof Error ? error.message : String(error)}`);
  }
  if (JSON.stringify(embedded) !== JSON.stringify(payload)) throw new Error("Embedded review JSON differs from the built payload");

  const freshInventory = changedFileInventory(repo, scope.mergeBase, scope.analyzedHead, scope.excludedPaths);
  if (!compareInventories(scope.files, freshInventory)) throw new Error("Generated artifact inventory differs from frozen Git scope");
  for (const file of embedded.files) {
    const freshDiff = git(repo, ["diff", "--no-renames", scope.mergeBase, scope.analyzedHead, "--", file.path]);
    if (file.diff !== freshDiff) throw new Error(`Embedded diff differs from Git for ${file.path}`);
  }

  if (embedded.meta.fileCount !== embedded.files.length) throw new Error("Embedded file count is inconsistent");
  if (embedded.meta.hierarchyNodeCount !== embedded.nodes.length) throw new Error("Embedded node count is inconsistent");
  if (embedded.meta.hierarchyPathCount !== embedded.paths.length) throw new Error("Embedded path count is inconsistent");
  const expectedDepth = Math.max(...embedded.paths.map((occurrence) => occurrence.ancestorIds.length + 1));
  if (embedded.meta.hierarchyDepth !== expectedDepth) throw new Error("Embedded hierarchy depth is inconsistent");
  for (const status of ["A", "M", "D"]) {
    const expected = embedded.files.filter((file) => file.status === status).length;
    if (embedded.meta.statusCounts[status] !== expected) throw new Error(`Embedded ${status} count is inconsistent`);
  }

  const shell = html.slice(0, payloadMatch.index) + html.slice(payloadMatch.index + payloadMatch[0].length);
  if (/<script\b[^>]*\bsrc\s*=/i.test(shell)) throw new Error("HTML shell contains a script src reference");
  if (/<link\b[^>]*\brel\s*=\s*["']?stylesheet/i.test(shell)) throw new Error("HTML shell contains an external stylesheet link");
  if (/<(?:img|video|audio|iframe|source)\b[^>]*\bsrc\s*=\s*["']?https?:/i.test(shell)) {
    throw new Error("HTML shell contains network media");
  }
  if (/\bfetch\s*\(/.test(shell)) throw new Error("HTML shell calls fetch; the review must work offline");

  const scripts = [...shell.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)]
    .filter((match) => !/type\s*=\s*["']application\/json["']/i.test(match[1]));
  const tempRoot = mkdtempSync(path.join(os.tmpdir(), "topical-review-check-"));
  try {
    scripts.forEach((match, index) => {
      const scriptPath = path.join(tempRoot, `inline-${index}.js`);
      writeFileSync(scriptPath, match[2]);
      run(process.execPath, ["--check", scriptPath]);
    });
  } finally {
    rmSync(tempRoot, { recursive: true, force: true });
  }

  if (!readFileSync(outputPath, "utf8").includes(payload.meta.analyzedHead)) {
    throw new Error("Written output does not contain the analyzed head hash");
  }
}
