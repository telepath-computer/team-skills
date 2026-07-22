#!/usr/bin/env node
import path from "node:path";
import {
  changedFileInventory,
  git,
  parseArgs,
  requireOptions,
  resolveRepository,
  writeJSON,
} from "./review-lib.mjs";

function usage() {
  return `Usage:
  node freeze-scope.mjs --repo <path> --base <ref> --head <ref> --output <scope.json> [--exclude <path>]...

Resolves the merge base and analyzed head to full hashes and records the exact
A/M/D inventory produced by git diff --no-renames.`;
}

try {
  if (process.argv.includes("--help") || process.argv.includes("-h")) {
    console.log(usage());
    process.exit(0);
  }
  const options = parseArgs(process.argv.slice(2), { repeatable: ["exclude"] });
  requireOptions(options, ["repo", "base", "head", "output"]);
  const repo = resolveRepository(options.repo);
  const mergeBase = git(repo, ["merge-base", options.base, options.head]).trim();
  const analyzedHead = git(repo, ["rev-parse", options.head]).trim();
  const excludedPaths = options.exclude ?? [];
  if (new Set(excludedPaths).size !== excludedPaths.length) throw new Error("--exclude contains a duplicate path");
  const completeInventory = changedFileInventory(repo, mergeBase, analyzedHead);
  const changedPaths = new Set(completeInventory.map((file) => file.path));
  const unknownExclusions = excludedPaths.filter((filePath) => !changedPaths.has(filePath));
  if (unknownExclusions.length > 0) {
    throw new Error(`Excluded paths are not in the frozen change set: ${unknownExclusions.join(", ")}`);
  }
  const files = completeInventory.filter((file) => !excludedPaths.includes(file.path));
  if (files.length === 0) throw new Error("The frozen review scope contains no changed files");
  const scope = {
    repository: repo,
    baseRef: options.base,
    headRef: options.head,
    mergeBase,
    analyzedHead,
    excludedPaths,
    files,
  };
  writeJSON(path.resolve(options.output), scope);
  const counts = Object.fromEntries(["A", "M", "D"].map(
    (status) => [status, files.filter((file) => file.status === status).length],
  ));
  console.log(`Frozen ${files.length} files at ${mergeBase.slice(0, 9)}..${analyzedHead.slice(0, 9)} (A ${counts.A}, M ${counts.M}, D ${counts.D})`);
  console.log(path.resolve(options.output));
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  console.error(usage());
  process.exitCode = 1;
}
