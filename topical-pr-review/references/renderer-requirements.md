# Topical review renderer requirements

This document records the product and interaction requirements behind the bundled topical pull-request review renderer. It exists so the review experience is explained independently of its HTML, CSS, and JavaScript implementation.

The bundled renderer is a useful default, not a mandatory presentation for every task. An artifact author may copy and adapt the template, or replace it, when the user or the material calls for a different experience. Use these requirements to understand what the default provides and to decide which behavior a customized artifact should retain.

## Purpose

A large pull request is difficult to understand as one flat file list. The renderer lets a reviewer move among three complementary views:

1. the complete changed source tree;
2. the outcomes and themes that explain why those files changed;
3. the explanation and exact diff for the selected subject.

The hierarchy is a directed acyclic graph. A file may appear under several topics when it has a different effect in each one. Those repeated leaves are intentional.

## Default page structure

The standard renderer has three columns.

### Files

The left column contains every changed path in a collapsible folder tree.

- Folders start expanded.
- Folder state persists for the frozen revision pair.
- A path search filters the tree.
- Added, modified, and deleted files use both a letter and color.
- A legend explains the status treatment.
- Selecting a shared hierarchy node filters the tree to files below that node.
- Selecting a hierarchy file leaf filters the tree to that file.
- Selecting a file directly does not discard folder state.

### Change hierarchy

The middle column renders this shape:

```text
change → theme → optional subtheme → file
```

- Top-level changes start expanded.
- Lower levels start folded unless a selection needs to reveal them.
- Fold state persists for the frozen revision pair.
- Shared nodes render once per applicable hierarchy occurrence.
- Files render once under every path to which they were assigned.
- Selecting a shared node shows its common explanation.
- Selecting a file occurrence records that exact hierarchy path.

### Explanation and diff

The right column shows either a shared-node explanation or a selected file.

For a shared node it shows:

- the node name;
- its shared explanation;
- the number of changed files below it;
- useful links to child nodes and files.

For a file it shows:

- full path and A/M/D status;
- one card for every hierarchy path containing the file;
- the complete path-specific explanation in each card;
- the exact embedded unified diff.

Each card shows a clickable breadcrumb. Selecting a breadcrumb ancestor behaves like selecting the same shared node in the middle column.

The diff starts open. The reviewer can collapse it, and that preference persists across files and reloads. A collapsed diff may be formatted lazily when reopened.

## Selection synchronization

The renderer keeps these states separate:

- selected file path;
- selected shared node ID;
- selected exact hierarchy-path ID;
- path search query;
- folder folds;
- hierarchy folds;
- diff visibility preference.

The distinction between a file and an exact path matters.

### File selected from the left column

The renderer:

- reveals every hierarchy path containing the file;
- highlights every matching file leaf;
- highlights the union of ancestors from all matching paths;
- shows every path-specific explanation card;
- does not mark one card as the exact selection.

### File selected from the hierarchy

The renderer:

- records the selected path occurrence;
- reveals that occurrence;
- filters the file tree to the file;
- shows all explanation cards for the file;
- marks only the corresponding card as exact.

Exact selection and multi-lineage matching must be visually different.

### Shared node selected

The renderer:

- reveals the node in the hierarchy;
- filters the file tree to descendant files;
- shows the node's shared explanation and child links;
- clears file and exact-path selection.

URL fragments such as `#file:`, `#node:`, and `#path:` make direct links and reload restoration possible. Values must be encoded before they enter a fragment.

## Review data expected by the default renderer

The build script supplies one payload with four sections:

```json
{
  "meta": {
    "title": "Pull request title",
    "pullRequest": 123,
    "summary": "Short overview",
    "mergeBase": "full hash",
    "analyzedHead": "full hash",
    "fileCount": 0,
    "hierarchyDepth": 0,
    "hierarchyNodeCount": 0,
    "hierarchyPathCount": 0,
    "statusCounts": { "A": 0, "M": 0, "D": 0 }
  },
  "nodes": [],
  "paths": [],
  "files": []
}
```

A node contains an ID, kind, name, shared explanation, and derived parent IDs. A path contains its ordered ancestor IDs, file path, status, stable ID, and path-specific explanation. A file contains its path, status, and exact raw diff.

The renderer treats ordered `ancestorIds` as the authoritative breadcrumb lineage. The same node may have several parents when that sharing is meaningful.

## Offline and source-safety requirements

The final deliverable is one self-contained HTML file.

- Styles, scripts, JSON, and diffs are inline.
- The page does not need a server.
- The page does not fetch data or load a CDN.
- The standard renderer uses no external scripts, stylesheets, fonts, or media.
- It works when opened through a `file://` URL.
- Source text is inserted into the DOM through `textContent`, not interpreted as markup.
- JSON embedded in the inert data script escapes literal `<` characters, so a diff containing HTML or `</script>` cannot terminate the payload.
- Raw diff text never appears inside executable JavaScript.

A customized artifact may embed self-contained media, such as a data URL, if the task benefits. It must still honor the user's offline expectations.

## Diff presentation

The renderer embeds the complete per-file output of:

```bash
git diff --no-renames <merge-base> <analyzed-head> -- <path>
```

It does not summarize, truncate, or reconstruct the diff. Formatting adds line numbers and classes for metadata, hunks, additions, and deletions while preserving every source line in the payload.

Long source lines scroll inside the diff container. They must not make the page itself scroll horizontally.

## Responsive layout

On a desktop viewport:

- the three columns use proportional widths;
- each column has zero intrinsic minimum width;
- each column owns its vertical scrolling;
- prose and breadcrumb labels wrap;
- paths can break anywhere when needed;
- only genuinely wide diff content scrolls horizontally.

The default proportions are approximately 26% files, 28% hierarchy, and 46% detail.

At a narrow breakpoint:

- the columns stack vertically;
- no column exceeds the viewport width;
- the document remains free of horizontal overflow;
- the diff container continues to own long-line scrolling.

Any flex or grid child containing paths or prose needs `min-width: 0`. Header metadata, legends, filters, cards, and breadcrumbs also need to stay within the viewport.

## Default visual behavior

The default renderer favors a dense code-review presentation:

- dark neutral surfaces;
- a monospace treatment for paths, revisions, statuses, and diffs;
- distinct colors for added, modified, and deleted files;
- a separate treatment for selected nodes, matching lineages, and exact path selection;
- no network font dependency;
- buttons that look like review controls rather than marketing-site calls to action.

These choices are replaceable. A task-specific renderer may use a project theme or a different information density while preserving the underlying review relationships.

## Reference behavior checks

Use these checks when maintaining the bundled renderer or when a customization changes the corresponding behavior.

1. The initial view shows the exact file, node, path, and status counts.
2. Folder and hierarchy folds survive reload.
3. Selecting a shared node filters the file tree and shows its explanation.
4. Selecting one hierarchy occurrence of a multi-path file marks exactly one explanation card.
5. Selecting a breadcrumb ancestor has the same effect as selecting that node in the hierarchy.
6. Selecting a multi-path file in the left tree reveals every matching leaf and the full union of ancestors.
7. Every distinct path explanation for that file appears in the detail column.
8. Diff visibility starts open, persists across files and reloads, and renders after reopening.
9. Desktop columns follow their proportions, prose wraps, columns scroll vertically, and the document does not overflow horizontally.
10. Narrow columns stack without document overflow.
11. A long diff line scrolls inside the diff container only.
12. Opening the file produces no HTTP or HTTPS requests.
13. Source containing markup, Unicode, quotes, backticks, and `</script>` remains inert text.

The bundled renderer should be tested against representative and adversarial payloads when it changes. An artifact that uses the bundled renderer unchanged normally needs only the build script's data and offline checks. A customized renderer should be checked in proportion to what changed.

## Customizing the renderer

Do not edit the installed shared template for one task. Copy it into task-local scratch space and pass that copy to the builder.

Reasonable customizations include:

- a project-specific visual style;
- another column or an overview diagram;
- custom rendering for images or generated assets;
- different navigation for a small hierarchy;
- hiding raw diffs when the user explicitly does not want them;
- additional metadata or review instructions.

The requirements in this document are a description of the standard experience and a checklist for informed deviation. They are not a prohibition on task-specific design.
