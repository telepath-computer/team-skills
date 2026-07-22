---
name: cold-reader
description: Write documents — user guides, READMEs, PR descriptions, specs, proposals, commit bodies, code comments — for a reader who has no history. Use when authoring or editing any text a future reader will encounter cold, with no memory of prior versions, abandoned alternatives, or the conversation that produced the text. Triggers include user requests to apply "cold-reader policy", make a document "forward-looking", remove references to "old" / "previous" / "deprecated" / "removed" behavior the reader has no context for, or scrub a document of iteration-history framing.
---

# Cold-reader policy

The reader has no priors.

A document — user guide, README, PR description, spec, proposal, commit body, code comment — is published into a world where the reader sees only what is in front of them. They did not sit through the design conversation. They did not watch the implementation iterate. They do not know what was tried and abandoned, what was renamed, what used to exist, or which alternatives were rejected.

Write for that reader. Describe what exists, not what was.

## The cold reader, by context

The reader who sees no history takes a different concrete shape per document type. The rule is the same; the visible surface differs.

- **User docs, guides, READMEs.** Cold reader = a user who installed the software today, never saw any prior version, has no memory of last week's release.
- **PR descriptions.** Cold reader = a code reviewer who sees the squash diff against `main` and the current state of `main`. They did not live inside the branch.
- **Specs / proposals.** Cold reader = a future implementer or reviewer who reads the document in isolation, without the chat transcripts that produced it.
- **Commit messages.** Cold reader = a git archaeologist running `git log -p` or `git blame`. They see this commit's diff and message and nothing of the surrounding work.
- **Code comments.** Cold reader = a future maintainer reading the function in isolation, possibly years later, possibly in a refactored file.

For each context, the operating question is: **can the reader open the document and find every thing it references?** If a referenced thing is not in the document, not in the diff, not in the current state of the code or system, the reference is invisible — and worse than invisible, because it tells the reader they are missing the answer to a question they should not be expected to hold.

## The hard rule

Describe what is. Do not describe what was, what was considered, or what was removed, unless the thing being referenced is visible to the reader.

If you find yourself writing "Y not X", "X is removed", "X is no longer supported", "in place of X", "instead of X", "rather than X" — **stop**. Check whether X is visible. If not, delete the reference and rewrite as a forward statement of what currently exists.

## Analogy

You are going to dinner and chose a black shirt over a blue shirt you tried on first. You say "I'm wearing my black shirt." You do not say "I'm wearing my black shirt, NOT the blue one." The blue shirt is irrelevant to anyone who did not help you pick. Mentioning it doesn't reassure them; it tells them they are missing important context about the blue shirt, when in fact the blue shirt was only ever live in your closet during dressing.

## Comparisons that are allowed

A comparison is fine when both sides are visible to the reader of this document:

- A PR description can say "removed flag `--foo`" because `--foo` exists in `main` and the reviewer can see its deletion in the diff.
- A migration guide, or change log, can say "the export name changed from X to Y" because the document's explicit purpose is to help readers who DO have the priors bridge to the new state — the document is for warm readers and cold readers who are explicitly looking to understand history.
- A code comment can say "this differs from `frobnicate()` because we need to skip Z" if `frobnicate()` is real current code.
- A spec can reference an earlier section of itself.

A comparison is not fine when the other side is only in your head, in your chat history, in an abandoned branch, or was abandoned during the scope a task's complex journey.

## Forward-looking rationale

It is fine — sometimes essential — to explain *why* the current design is the way it is. Frame the rationale forward: "library X is used because it gives us Y." Do not frame as a contrast against unshipped alternatives: "library X is used instead of library W" when W never lived in either the current state or any state the reader can see.

If a rationale only makes sense by contrasting against an alternative that lived during development but did not land, the rationale belongs in design docs, internal notes, or commit messages on the specific commits that introduced the choice — not in user-facing docs or PR descriptions. Such design and architectural decision records, internal notes, and incremental commit messages, by definition do not follow "cold reader" policy.

## Self-audit before publishing

Search the draft mechanically for these markers:

- `not`, `no longer`, `not yet`, `not currently`
- `instead of`, `rather than`, `in place of`, `as opposed to`
- `previously`, `formerly`, `used to`, `was`, `had been`
- `new`, `now`, `this change`, `this update`, `we now`
- `removed`, `deprecated`, `replaced`, `dropped`
- `we considered`, `we explored`, `we tried`, `we chose`
- `instead`, `however`

For each hit, ask: **is the thing being referenced visible to the reader of this document?** If no, rewrite the sentence to describe what exists.

The grep is mechanical and catches the easy violations. The harder ones are framings the grep won't catch: implicit assumptions of a baseline the reader doesn't share, references to "the old way" without saying old-relative-to-what, sentences that only make sense to someone who watched the iteration. Re-read end-to-end with the cold-reader question in mind: "If I were reading this for the first time today, with no prior knowledge of this project, would this sentence confuse me or make me wonder about something I cannot see?"

## When the rule is hardest

- **Migration sections in release notes.** These genuinely reference both old and new state because they're written FOR readers who have priors. Comparisons are valid here. But everything else in the doc — feature descriptions, API references, conceptual overviews — should still describe what is, not what was.
- **PR descriptions for branches with long iteration history.** The reviewer reads the squash diff; they see `main` and your branch's final state. They do NOT see intermediate commits, abandoned implementations, or alternatives you considered. Forward-only.
- **Docs that have lived through several rewrites.** Hardest of all. Old "the new system does X" framings calcify in. The doc passes through multiple authors, each leaving a layer of "the new behavior" framing that becomes stale relative to whichever rewrite is current. Re-read end-to-end with the cold-reader question.
- **Replacing a paragraph that itself violates the rule.** When editing, do not just patch the surface phrasing — read the surrounding context and check whether the paragraph's structure assumes a baseline the reader doesn't have.

## Operating principle

Write for someone who has no history.
Describe what is, not what was.
Comparisons are allowed only when both sides are visible.
