---
name: pr-writing
description: Write or revise pull request descriptions for squash-merge review, focusing on the final net change against the merge base rather than branch history.
---

Write the PR for a squash-merge review. Describe the final net change against
the merge base (`main`) only.

A pull request description should explain the system change, not just enumerate
file changes. It must give a reviewer enough context to understand the
architecture, runtime behavior, key technologies, and integration boundaries
without already knowing the branch history. Name the primary mechanisms and
tools involved, explain how data flows through the feature, and describe what
existing behavior changed. A reviewer should be able to answer "what is this?",
"how does it work?", "what are the important moving parts?", and "why was it
built this way?" from the PR itself.

Assume the reviewer sees only the final squashed delta and has no
knowledge of the development timeline. Focus on what exists in the final
code/spec/test changes, grouped by shipped behavior, architecture, validation,
and important decisions. Do not frame the PR around the latest incremental
changes or the sequence of development work.

Or in short: write PRs for a capable reviewer who has not lived inside the
branch.

## Apply cold-reader policy

A PR reviewer is a cold reader. They see the squash diff against `main` and
the current state of `main`. They do not see your intermediate commits, the
design conversation that produced the change, abandoned implementations,
renames you reverted, or alternatives you considered along the way.

Apply the cold-reader policy (`cold-reader/SKILL.md`) when writing the PR.
The policy and its self-audit grep apply directly. In the PR context, the
practical rules are:

- **Comparisons against `main` are valid.** "Removed flag `--foo`" works when
  `--foo` exists in `main` — the reviewer sees both sides in the diff.
- **Comparisons against unshipped alternatives are not.** "Library X is used
  instead of library W" is invalid if W never landed in the branch or in
  `main`. The reviewer has nothing to compare against.
- **Forward-looking rationale is fine.** "Library X is used because it gives
  us Y" describes the chosen design without pulling in the closet.

Run the cold-reader self-audit grep before publishing.

## Anti-patterns specific to PR writing

- a list of changed files masquerading as an explanation for what changed
- cursory descriptions of "implements new feature X" that do not actually
  enumerate what was modified or added to the system architecture, the
  design of affected modules, new tooling/dependencies, why things were done
  this way, etc.
- history-oriented PR narration / archaeological branch-work summaries
- focusing on the most recent incremental changes instead of the full final
  delta against `main`
- describing replacements of code that is not present in the squashed diff
  (covered by cold-reader policy — the reviewer cannot see what was replaced
  if the replacement isn't in the diff)

## Useful inclusions

- **Why** a design decision was made, framed forward-looking. Include only when
  the reviewer will plausibly wonder.
- Cross-file architectural notes the diff alone would not make obvious — how
  data flows, what invariants hold across modules, where the integration
  boundaries are.

If a design rationale only makes sense by contrasting against an alternative
that lived during development but is not in the final diff, the rationale
belongs in commit messages or design docs, not the PR body.

## Writing correctly to GitHub APIs

When updating long-form PR text, treat the PR body as publication content, not
shell content and not patch content. Draft it in a plain temporary markdown
file exactly as you want reviewers to read it, with no diff markers, no patch
prefixes, and no shell interpolation. Then send that file to GitHub through a
file-based API path, and verify the stored PR body afterward. Never compose PR
prose inline inside shell commands, and never reuse patch-formatted text as PR
content.
