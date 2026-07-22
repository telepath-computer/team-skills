import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

export function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    ...options,
    encoding: options.encoding ?? "utf8",
    maxBuffer: options.maxBuffer ?? 128 * 1024 * 1024,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    const stderr = typeof result.stderr === "string" ? result.stderr.trim() : "";
    throw new Error(`${command} ${args.join(" ")} failed with exit ${result.status}${stderr ? `:\n${stderr}` : ""}`);
  }
  return result.stdout;
}

export function git(repo, args) {
  return run("git", args, { cwd: repo });
}

export function readJSON(filePath, description = filePath) {
  let source;
  try {
    source = readFileSync(filePath, "utf8");
  } catch (error) {
    throw new Error(`Could not read ${description} at ${filePath}: ${errorMessage(error)}`);
  }
  try {
    return JSON.parse(source);
  } catch (error) {
    throw new Error(`Could not parse ${description} at ${filePath}: ${errorMessage(error)}`);
  }
}

export function writeJSON(filePath, value) {
  mkdirSync(path.dirname(path.resolve(filePath)), { recursive: true });
  writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`);
}

export function parseArgs(argv, { repeatable = [] } = {}) {
  const repeatableNames = new Set(repeatable);
  const result = { _: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (!argument.startsWith("--")) {
      result._.push(argument);
      continue;
    }
    const name = argument.slice(2);
    const value = argv[index + 1];
    if (value === undefined || value.startsWith("--")) throw new Error(`${argument} requires a value`);
    if (repeatableNames.has(name)) {
      result[name] ??= [];
      result[name].push(value);
    } else {
      if (result[name] !== undefined) throw new Error(`Duplicate option ${argument}`);
      result[name] = value;
    }
    index += 1;
  }
  return result;
}

export function requireOptions(options, names) {
  for (const name of names) {
    if (typeof options[name] !== "string" || options[name].length === 0) {
      throw new Error(`--${name} is required`);
    }
  }
}

export function resolveRepository(repo) {
  const resolved = path.resolve(repo);
  return path.resolve(git(resolved, ["rev-parse", "--show-toplevel"]).trim());
}

export function changedFileInventory(repo, mergeBase, analyzedHead, excludedPaths = []) {
  const excluded = new Set(excludedPaths);
  const output = git(repo, [
    "diff",
    "--name-status",
    "-z",
    "--no-renames",
    mergeBase,
    analyzedHead,
  ]);
  const fields = output.split("\0");
  if (fields.at(-1) === "") fields.pop();
  if (fields.length % 2 !== 0) throw new Error("Git returned an incomplete name-status inventory");
  const files = [];
  for (let index = 0; index < fields.length; index += 2) {
    const status = fields[index];
    const filePath = fields[index + 1];
    if (!new Set(["A", "M", "D"]).has(status)) {
      throw new Error(`Unsupported Git status ${JSON.stringify(status)} for ${filePath}; use --no-renames A/M/D scope`);
    }
    if (!excluded.has(filePath)) files.push({ path: filePath, status });
  }
  return files;
}

export function validateScope(scope, repo, { reconcileRefs = false } = {}) {
  assertObject(scope, "scope");
  for (const key of ["baseRef", "headRef", "mergeBase", "analyzedHead"]) {
    nonemptyString(scope[key], `scope.${key}`);
  }
  if (!Array.isArray(scope.excludedPaths)) throw new Error("scope.excludedPaths must be an array");
  const excluded = new Set();
  for (const [index, filePath] of scope.excludedPaths.entries()) {
    nonemptyString(filePath, `scope.excludedPaths[${index}]`);
    if (excluded.has(filePath)) throw new Error(`scope.excludedPaths contains duplicate path ${filePath}`);
    excluded.add(filePath);
  }
  if (!Array.isArray(scope.files)) throw new Error("scope.files must be an array");
  const seen = new Set();
  for (const [index, file] of scope.files.entries()) {
    assertObject(file, `scope.files[${index}]`);
    nonemptyString(file.path, `scope.files[${index}].path`);
    if (!new Set(["A", "M", "D"]).has(file.status)) {
      throw new Error(`scope.files[${index}].status must be A, M, or D`);
    }
    if (seen.has(file.path)) throw new Error(`scope.files contains duplicate path ${file.path}`);
    if (excluded.has(file.path)) throw new Error(`scope path ${file.path} is both included and excluded`);
    seen.add(file.path);
  }

  const frozenBase = git(repo, ["rev-parse", scope.mergeBase]).trim();
  const frozenHead = git(repo, ["rev-parse", scope.analyzedHead]).trim();
  if (frozenBase !== scope.mergeBase || frozenHead !== scope.analyzedHead) {
    throw new Error("scope mergeBase and analyzedHead must be full commit hashes");
  }

  if (reconcileRefs) {
    const currentHead = git(repo, ["rev-parse", scope.headRef]).trim();
    const currentBase = git(repo, ["merge-base", scope.baseRef, scope.headRef]).trim();
    if (currentHead !== scope.analyzedHead || currentBase !== scope.mergeBase) {
      throw new Error(
        `The review refs moved after scope freeze. Frozen ${scope.mergeBase.slice(0, 9)}..${scope.analyzedHead.slice(0, 9)}, `
        + `current ${currentBase.slice(0, 9)}..${currentHead.slice(0, 9)}. Freeze and review the scope again.`,
      );
    }
  }

  const fresh = changedFileInventory(repo, scope.mergeBase, scope.analyzedHead, scope.excludedPaths);
  if (JSON.stringify(fresh) !== JSON.stringify(scope.files)) {
    throw new Error("scope.files no longer equals Git's frozen A/M/D inventory");
  }
  return scope;
}

export function validateContent(scope, content) {
  assertObject(content, "content");
  nonemptyString(content.title, "content.title");
  if (content.summary !== undefined) nonemptyString(content.summary, "content.summary");
  if (content.pullRequest !== undefined && !["string", "number"].includes(typeof content.pullRequest)) {
    throw new Error("content.pullRequest must be a string or number when present");
  }
  if (!Array.isArray(content.nodes) || content.nodes.length === 0) {
    throw new Error("content.nodes must be a nonempty array");
  }
  if (!Array.isArray(content.paths) || content.paths.length === 0) {
    throw new Error("content.paths must be a nonempty array");
  }

  const nodeById = new Map();
  for (const [index, node] of content.nodes.entries()) {
    const location = `content.nodes[${index}]`;
    assertObject(node, location);
    const id = nonemptyString(node.id, `${location}.id`);
    if (nodeById.has(id)) throw new Error(`content.nodes contains duplicate id ${id}`);
    if (!new Set(["change", "theme", "subtheme"]).has(node.kind)) {
      throw new Error(`${location}.kind must be change, theme, or subtheme`);
    }
    nonemptyString(node.name, `${location}.name`);
    nonemptyString(node.explanation, `${location}.explanation`);
    nodeById.set(id, node);
  }

  const scopeByPath = new Map(scope.files.map((file) => [file.path, file]));
  const usedNodes = new Set();
  const coveredFiles = new Set();
  const assignmentKeys = new Set();
  const textByFile = new Map();
  const expectedKinds = ["change", "theme", "subtheme"];
  const parentIds = new Map(content.nodes.map((node) => [node.id, new Set()]));
  const paths = [];

  for (const [index, occurrence] of content.paths.entries()) {
    const location = `content.paths[${index}]`;
    assertObject(occurrence, location);
    if (!Array.isArray(occurrence.ancestorIds) || occurrence.ancestorIds.length === 0 || occurrence.ancestorIds.length > 3) {
      throw new Error(`${location}.ancestorIds must contain a change, optional theme, and optional subtheme`);
    }
    occurrence.ancestorIds.forEach((id, ancestorIndex) => {
      nonemptyString(id, `${location}.ancestorIds[${ancestorIndex}]`);
      const node = nodeById.get(id);
      if (!node) throw new Error(`${location} references unknown node ${id}`);
      if (node.kind !== expectedKinds[ancestorIndex]) {
        throw new Error(`${location} expects a ${expectedKinds[ancestorIndex]} at depth ${ancestorIndex + 1}; ${id} is ${node.kind}`);
      }
      usedNodes.add(id);
      if (ancestorIndex > 0) parentIds.get(id).add(occurrence.ancestorIds[ancestorIndex - 1]);
    });
    const filePath = nonemptyString(occurrence.filePath, `${location}.filePath`);
    const scopeFile = scopeByPath.get(filePath);
    if (!scopeFile) throw new Error(`${location} references path outside the frozen scope: ${filePath}`);
    const leafExplanation = nonemptyString(occurrence.leafExplanation, `${location}.leafExplanation`);
    const assignmentKey = `${occurrence.ancestorIds.join("\0")}\0${filePath}`;
    if (assignmentKeys.has(assignmentKey)) throw new Error(`${location} duplicates an existing hierarchy path for ${filePath}`);
    assignmentKeys.add(assignmentKey);
    coveredFiles.add(filePath);
    const existingTexts = textByFile.get(filePath) ?? new Set();
    if (existingTexts.has(leafExplanation)) {
      throw new Error(`${filePath} reuses the same explanation on more than one hierarchy path`);
    }
    existingTexts.add(leafExplanation);
    textByFile.set(filePath, existingTexts);
    const id = `path:${createHash("sha256").update(assignmentKey).digest("hex").slice(0, 16)}`;
    paths.push({
      id,
      ancestorIds: [...occurrence.ancestorIds],
      filePath,
      status: scopeFile.status,
      leafExplanation,
    });
  }

  const missingFiles = scope.files.map((file) => file.path).filter((filePath) => !coveredFiles.has(filePath));
  if (missingFiles.length > 0) {
    throw new Error(`Changed files missing from the hierarchy:\n${missingFiles.map((filePath) => `- ${filePath}`).join("\n")}`);
  }
  const unusedNodes = content.nodes.map((node) => node.id).filter((id) => !usedNodes.has(id));
  if (unusedNodes.length > 0) throw new Error(`Hierarchy nodes have no file path: ${unusedNodes.join(", ")}`);

  const nodes = content.nodes.map((node) => ({
    id: node.id,
    kind: node.kind,
    name: node.name,
    explanation: node.explanation,
    parentIds: [...parentIds.get(node.id)],
  }));
  const warnings = [];
  for (const node of nodes) {
    if (sentenceCount(node.explanation) > 2) warnings.push(`${node.id} shared explanation is longer than two sentences`);
  }
  for (const occurrence of paths) {
    if (sentenceCount(occurrence.leafExplanation) > 2) warnings.push(`${occurrence.id} file explanation is longer than two sentences`);
  }
  return { nodes, paths, warnings };
}

export function renderContentOutline(scope, content, { structureOnly = false } = {}) {
  const validated = validateContent(scope, content);
  const nodeById = new Map(validated.nodes.map((node) => [node.id, node]));
  const nodeOrder = new Map(validated.nodes.map((node, index) => [node.id, index]));
  const root = { children: new Map(), leaves: [] };
  for (const occurrence of validated.paths) {
    let cursor = root;
    for (const nodeId of occurrence.ancestorIds) {
      if (!cursor.children.has(nodeId)) cursor.children.set(nodeId, { nodeId, children: new Map(), leaves: [] });
      cursor = cursor.children.get(nodeId);
    }
    cursor.leaves.push(occurrence);
  }

  const lines = [
    `# ${content.title}`,
    "",
    `${scope.mergeBase.slice(0, 9)} → ${scope.analyzedHead.slice(0, 9)} · ${scope.files.length} changed files · ${validated.paths.length} explanation paths`,
    "",
  ];
  if (content.summary) lines.push(content.summary, "");

  function walk(occurrence, depth) {
    const node = nodeById.get(occurrence.nodeId);
    const indent = "  ".repeat(depth);
    const label = node.kind === "change" ? "Change" : node.kind === "theme" ? "Theme" : "Subtheme";
    lines.push(`${indent}- **${label}: ${node.name}**`);
    lines.push(`${indent}  - ${node.explanation}`);
    const children = [...occurrence.children.values()].sort(
      (left, right) => nodeOrder.get(left.nodeId) - nodeOrder.get(right.nodeId),
    );
    for (const child of children) walk(child, depth + 1);
    for (const leaf of occurrence.leaves.slice().sort((left, right) => left.filePath.localeCompare(right.filePath))) {
      lines.push(`${indent}  - \`${leaf.status} ${escapeInlineCode(leaf.filePath)}\``);
      if (!structureOnly) lines.push(`${indent}    - ${leaf.leafExplanation}`);
    }
  }

  const roots = [...root.children.values()].sort(
    (left, right) => nodeOrder.get(left.nodeId) - nodeOrder.get(right.nodeId),
  );
  for (const occurrence of roots) walk(occurrence, 0);
  return { markdown: `${lines.join("\n")}\n`, warnings: validated.warnings };
}

export function buildPayload(repo, scope, content) {
  const validated = validateContent(scope, content);
  const files = scope.files.map((file) => ({
    ...file,
    diff: git(repo, ["diff", "--no-renames", scope.mergeBase, scope.analyzedHead, "--", file.path]),
  }));
  const statusCounts = Object.fromEntries(
    ["A", "M", "D"].map((status) => [status, files.filter((file) => file.status === status).length]),
  );
  const meta = {
    title: content.title,
    pullRequest: content.pullRequest ?? null,
    summary: content.summary ?? null,
    mergeBase: scope.mergeBase,
    analyzedHead: scope.analyzedHead,
    fileCount: files.length,
    hierarchyDepth: Math.max(...validated.paths.map((occurrence) => occurrence.ancestorIds.length + 1)),
    hierarchyNodeCount: validated.nodes.length,
    hierarchyPathCount: validated.paths.length,
    statusCounts,
  };
  return {
    payload: { meta, nodes: validated.nodes, paths: validated.paths, files },
    warnings: validated.warnings,
  };
}

export function compareInventories(expected, actual) {
  return JSON.stringify(expected) === JSON.stringify(actual);
}

function sentenceCount(text) {
  return (text.trim().match(/[.!?](?:\s|$)/g) ?? []).length;
}

function escapeInlineCode(value) {
  return value.replaceAll("`", "\\`");
}

function assertObject(value, location) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${location} must be an object`);
  }
}

function nonemptyString(value, location) {
  if (typeof value !== "string" || value.trim().length === 0) throw new Error(`${location} must be a nonempty string`);
  return value;
}

function errorMessage(error) {
  return error instanceof Error ? error.message : String(error);
}
