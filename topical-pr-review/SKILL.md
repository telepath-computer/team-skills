---
name: topical-pr-review
description: Build a single-file offline HTML review site for a large pull request, organized by topic with path-specific explanations, embedded diffs, and synchronized file and hierarchy navigation.
---

# Topical PR review

Use this skill when a pull request is too broad to understand comfortably from a flat file list. The work has five phases: establish the review, freeze its source scope, understand and organize the change, revise the hierarchy and language for a human reviewer, then build the site with the bundled renderer or a task-specific adaptation.

The final deliverable is one self-contained HTML file. The bundled renderer provides a three-column file tree, topical hierarchy, and explanation-plus-diff view. Its detailed behavior and design requirements live in [references/renderer-requirements.md](references/renderer-requirements.md). Read that document when modifying or replacing the renderer; it is not necessary when using the bundled template unchanged.

Set `SKILL_DIR` to the directory containing this `SKILL.md` before running the helper commands below.

## Phase 0 — Establish context and requirements

Confirm:

- repository path;
- pull request or change being reviewed;
- base and head refs;
- requested output path;
- any review-process files the user explicitly excludes;
- intended reader and any requested visual or interaction changes.

Read the repository's agent instructions. Identify its architecture overview and which specifications or documentation are authoritative for the changed areas.

The standard result is one offline HTML file containing every changed path, every explanation, and every exact raw diff. A user request may change the presentation. The bundled renderer is a strong default, not a restriction on task-specific design.

## Phase 1 — Freeze the source scope

Create an immutable inventory before classifying files:

```bash
node "$SKILL_DIR/scripts/freeze-scope.mjs" \
  --repo "$REPO" \
  --base "$BASE_REF" \
  --head "$HEAD_REF" \
  --output "$WORK_DIR/scope.json"
```

Use `--exclude <path>` only for a review-process file the user explicitly placed outside the source change being reviewed. The command may be repeated for several exclusions.

The helper resolves and records:

- the full merge-base hash;
- the full analyzed-head hash;
- the exact `git diff --name-status --no-renames` A/M/D inventory;
- any explicit exclusions.

Treat `scope.json` as authoritative. Do not derive completeness from directory scans, theme assignments, or the generated site. A rename is represented as a deleted path and an added path.

## Phase 2 — Analyze the change and draft the content hierarchy

Understand the pull request before polishing its prose:

1. Read the complete frozen diff.
2. Read architecture and authoritative specs for the changed areas; use current documentation where no spec exists.
3. Read commit subjects between the frozen revisions as supporting evidence.
4. Resolve final meaning against the net diff and current authoritative documents.
5. Identify a small set of broad outcomes that answer: “What does this pull request deliver?”
6. Divide each outcome into themes that answer: “What coherent part of that outcome is implemented here?”
7. Add a subtheme only when it helps a reviewer distinguish material that would otherwise be crowded together.
8. Map every changed file to one or more complete hierarchy paths.
9. Draft one shared explanation for every node and one file-impact explanation for every path.

Prefer outcomes and behavior over directory or implementation taxonomies. A specs folder is not automatically a “specs” topic, and tests are usually most useful beside the behavior they prove. Give an unrelated ride-along its own change rather than hiding it under an adjacent topic.

The hierarchy is a directed acyclic graph. A central file may appear under several topics when the diff has a genuinely different effect through each one. Do not force one primary topic, and do not duplicate a file merely because duplication is possible.

### Content file

Author `content.json` separately from the renderer:

```json
{
  "title": "Pull request title",
  "pullRequest": 123,
  "summary": "A short overview of the complete change.",
  "nodes": [
    {
      "id": "change:example",
      "kind": "change",
      "name": "Deliver the broad outcome",
      "explanation": "What this outcome does and why it matters."
    },
    {
      "id": "theme:example",
      "kind": "theme",
      "name": "Implement one coherent part",
      "explanation": "The intent shared by the files below it."
    }
  ],
  "paths": [
    {
      "ancestorIds": ["change:example", "theme:example"],
      "filePath": "src/example.ts",
      "leafExplanation": "This file performs the concrete work and explains why that matters through this topic."
    }
  ]
}
```

Use ordered paths of:

```text
change → optional theme → optional subtheme → file
```

The helpers derive statuses, parent relationships, stable path IDs, counts, and raw diffs. Do not hand-maintain data that comes from Git or the hierarchy itself.

Each shared node has one explanation. Treat `(ordered ancestor IDs, file path)` as the unit of file-impact authorship:

- write against that file's exact diff through that path's topic;
- name the concrete behavior and why it matters to this topic;
- keep it to one or two complete sentences when possible;
- give each path its own text;
- make a multi-path file's distinctions explicit.

Render a structure-focused manuscript:

```bash
node "$SKILL_DIR/scripts/render-content-outline.mjs" \
  --scope "$WORK_DIR/scope.json" \
  --content "$WORK_DIR/content.json" \
  --structure-only true \
  --output "$WORK_DIR/content-structure.md"
```

Read it as one document. Revise the hierarchy until the roots and themes tell the technical story without help from the HTML interface.

## Phase 3 — Review and revise the hierarchy and language

This phase is mandatory. Its goal is maximum clarity: the artifact should read like one experienced developer walking another developer through the pull request.

Render the complete manuscript:

```bash
node "$SKILL_DIR/scripts/render-content-outline.mjs" \
  --scope "$WORK_DIR/scope.json" \
  --content "$WORK_DIR/content.json" \
  --output "$WORK_DIR/content.md"
```

Read `content.md` in full, independently of the diffs and renderer. Revise `content.json`, regenerate the manuscript, and repeat until it passes the review below. Do not begin the HTML build before this pass is complete.

### Review the hierarchy progressively

1. Read only the top-level changes. Can a developer summarize the pull request from them?
2. Read the changes and themes. Does each child make a useful distinction its parent does not?
3. Read the complete file paths and explanations. Does the detailed account still support the story promised at the top?

The language review may rename, merge, split, move, or remove hierarchy nodes. Structural awkwardness is not solved by polishing the same labels.

### Developer-walks-a-developer-through-it test

For every heading and explanation, ask:

- Would a developer naturally say this during a pull request walkthrough?
- Does the heading name behavior or an outcome rather than an abstract category?
- Can a change heading naturally complete “This pull request…”?
- Does the explanation add purpose, or merely restate the heading?
- Does it say why the reviewer should care rather than only listing machinery?

Prefer:

- “Generate notices from the packages included in each bundle.”
- “Check LICENSE and notice files inside published npm tarballs.”
- “Save each build's package list for the later license check.”

Question phrases such as “validated cross-process inventory handoff,” “packed-artifact defense,” or “governed repository contract.” They may be technically compressive while making the reader decode language no developer would normally use.

### Plain language for a cold reviewer

Assume the reader understands software development and can see the frozen diff, but has no history of the branch or the conversation that produced it.

- Name behavior before implementation details.
- Use a project-specific term only if the reader already shares it, or define it in the same sentence where it first appears.
- Prefer direct verbs over nouns made from processes.
- Avoid private shorthand, decorative aliases, workstream names, temporary codenames, and unexplained abbreviations.
- Describe the net change. Do not narrate abandoned approaches or intermediate branch history that the reviewer cannot see.
- Do not strip legitimate technical vocabulary the project actually uses.
- Do not talk down to the reader or define obvious software terms.

Flag terms such as *surface*, *inventory*, *aggregate*, *election*, *handoff*, *topology*, *provenance*, *authority*, and *spine* when they first appear. They are not banned; they must either be shared vocabulary or introduced in ordinary language.

### Explanation quality

- A shared explanation states the common intent once.
- A file explanation names what the diff changes and why it matters through this path.
- A “why” sentence must add information rather than paraphrase the “what.”
- Repeated boilerplate should not bury the files that carry the important behavior.
- Tests should say what behavior or boundary they prove.
- Specs should say what decision or contract they establish.
- Multiple explanations for one file must remain technically and linguistically distinct.
- Claims such as “safe,” “deterministic,” “authoritative,” “exact,” or “validated” should be supported by a concrete mechanism or consequence, not used as ornamental praise.

For a large review, give the generated manuscript to a fresh language reviewer when another agent is available. Ask it to identify phrases it would not naturally use, undefined terms, repeated ideas, and hierarchy distinctions that do not help. Recheck any rewritten technical claim against the exact diff afterward.

Phase 3 is complete when:

- every frozen file has at least one useful path;
- the roots explain the pull request without the UI;
- every node earns its place;
- the complete manuscript reads naturally end to end;
- edited claims remain accurate against the source.

## Phase 4 — Build the HTML artifact

Use the bundled renderer by default:

```bash
node "$SKILL_DIR/scripts/build-review.mjs" \
  --repo "$REPO" \
  --scope "$WORK_DIR/scope.json" \
  --content "$WORK_DIR/content.json" \
  --output "$OUTPUT_HTML"
```

The builder:

- verifies that the refs and frozen inventory have not moved;
- validates complete hierarchy coverage and path-specific text;
- derives path IDs, parent relationships, statuses, and metadata;
- captures every raw per-file diff with argument-safe Git calls;
- safely embeds the data in the template;
- writes one offline HTML file;
- parses the payload back out;
- compares every embedded diff and status with Git;
- checks metadata counts, offline resources, and inline JavaScript syntax;
- reconciles the frozen scope again immediately before completion.

### Customize when the task benefits

The bundled renderer is an implementation shortcut, not a locked format. If the user or material calls for a different presentation, read [references/renderer-requirements.md](references/renderer-requirements.md), copy the template into task-local scratch space, and change the copy:

```bash
cp "$SKILL_DIR/assets/review-template.html" "$WORK_DIR/custom-template.html"

node "$SKILL_DIR/scripts/build-review.mjs" \
  --repo "$REPO" \
  --scope "$WORK_DIR/scope.json" \
  --content "$WORK_DIR/content.json" \
  --template "$WORK_DIR/custom-template.html" \
  --output "$OUTPUT_HTML"
```

Do not edit the installed shared template for a one-off artifact. A custom renderer may add, remove, or change behavior to serve the task. Verify custom layout or interaction work in proportion to what changed. The bundled renderer's full interaction behavior is maintained against the renderer requirements and does not need to be manually re-proven for every unchanged use.

## Completion report

Report:

- output path;
- merge base and analyzed head;
- file and A/M/D counts;
- hierarchy depth, shared-node count, and path count;
- final HTML size;
- whether the bundled or a customized renderer was used;
- mechanical verification result;
- any additional checks performed for renderer customizations.

The content is complete when every frozen source path is represented, every hierarchy path has its own accurate explanation, the standalone manuscript reads like a clear developer walkthrough, and the final file contains the exact diffs in one offline artifact.
