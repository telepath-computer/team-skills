#!/usr/bin/env node
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import {
  parseArgs,
  readJSON,
  renderContentOutline,
  requireOptions,
} from "./review-lib.mjs";

function usage() {
  return `Usage:
  node render-content-outline.mjs --scope <scope.json> --content <content.json> [--output <content.md>] [--structure-only true]

Renders the authored hierarchy as plain Markdown. Without --output, writes it
to stdout. --structure-only true omits file-impact paragraphs.`;
}

try {
  if (process.argv.includes("--help") || process.argv.includes("-h")) {
    console.log(usage());
    process.exit(0);
  }
  const options = parseArgs(process.argv.slice(2));
  requireOptions(options, ["scope", "content"]);
  const scope = readJSON(path.resolve(options.scope), "frozen scope");
  const content = readJSON(path.resolve(options.content), "review content");
  const { markdown, warnings } = renderContentOutline(scope, content, {
    structureOnly: options["structure-only"] === "true",
  });
  if (options.output) {
    const output = path.resolve(options.output);
    mkdirSync(path.dirname(output), { recursive: true });
    writeFileSync(output, markdown);
    console.log(output);
  } else {
    process.stdout.write(markdown);
  }
  for (const warning of warnings) console.error(`warning: ${warning}`);
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  console.error(usage());
  process.exitCode = 1;
}
