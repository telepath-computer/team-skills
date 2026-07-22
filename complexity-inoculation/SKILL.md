---
name: complexity-inoculation
description: Maintain active skepticism toward accreted complexity while writing specs and plans, designing systems, implementing changes, and reviewing work. Use when local decisions are cascading into machinery, when a solution feels larger than its purpose, when inherited text or precedent is driving work, during long autonomous plans, or whenever the user asks to use "complexity inoculation."
---

# Complexity Inoculation

## Purpose

Cargo cult complexity emerges when a sequence of individually reasonable decisions produces a whole that nobody would choose from scratch. A sentence becomes a requirement; the requirement creates a mechanism; the mechanism creates constraints and edge cases; tests and process preserve all of it. Each step makes sense locally. The accumulation does not.

This skill is a preventive posture used while work is still taking shape. It asks the agent to step outside the chain, recover the actual purpose, and question whether the thing being elaborated should exist at all.

It applies broadly: to requirements, architecture, schemas, abstractions, compatibility layers, automation, test policy, operational process, review demands, and implementation plans. No particular symptom defines the problem.

## An ambient lens, not a workstream

Complexity Inoculation is context carried through the ordinary work. It influences planning, implementation, testing, and review decisions as they happen; it is not a separate task to dispatch or a phase to complete.

Do not create an audit, agent team, scheduled loop, checklist, report, deliverable, approval gate, or review ceremony merely to “apply” Complexity Inoculation. Do not turn the posture into a compliance system. If it identifies a concrete simplification, handle that simplification within the existing work and use the normal review process. The lens should remove or prevent machinery, never manufacture more process around simplicity.

## The posture

Keep these ideas active without turning them into another compliance system:

- **Fix the instance before inventing the class.** General machinery must be earned by multiple real cases, not one case plus imagined futures.
- **Size the solution to the problem.** Correctness does not redeem an absurd ratio between machinery and value.
- **Treat prior text as evidence, not law.** Specs and plans can be the source of accidental complexity, even when implementation conforms perfectly.
- **Treat cascade as a smell.** When X requires Y, which forces Z and its own failure policy, question X before polishing Z.
- **Consider deletion first.** The natural bias is to add because adding looks productive. Deliberately ask what requirement, layer, field, rule, or mechanism can disappear.
- **Prefer a simple rule plus judgment over elaborate universal handling.** Not every irregular case needs to be absorbed automatically.
- **Explain mechanisms by purpose, not history.** “We have it because the previous layer required it” is evidence of accretion, not justification.

## While writing specs and plans

A short sentence can cast a long implementation shadow: code, state, validation, migrations, failure behavior, tests, operations, and future compatibility. Think about that shadow before making the sentence authoritative.

Pay particular attention when a statement has high implementation impact but low strategic value. Ask, in substance:

- What valuable outcome does this statement protect?
- What will literal compliance cause us to build and maintain?
- Would a narrower statement preserve the outcome?

Do not add requirements merely because they sound complete, symmetric, rigorous, or future-proof. Distinguish outcomes that must hold from implementation ideas that may change. If an exact mechanism is not itself part of the product, describe the result it should achieve rather than turning the mechanism into law.

Before declaring a document ready, look at it from a blank page: knowing only the project's purpose, would you introduce these concepts and constraints? If not, simplify the document before implementation gives them weight.

## While designing, implementing, or reviewing

When work begins to expand, stop reasoning only from the most recent local decision. Restate the original problem and inspect the entire chain that led to the proposed machinery.

Use three questions:

1. **What concrete problem exists now?**
2. **Would we choose this solution from scratch for that problem?**
3. **What can be removed or narrowed while preserving the valuable outcome?**

Apply the same skepticism to the source material. Conformance is not enough when the requirement itself is low-value or the plan has mistaken one possible method for the goal.

When a small, reversible correction clearly restores alignment with the stated purpose, make it and continue—especially during explicitly autonomous work. Escalate when simplification would alter a deliberate product decision, weaken a real safety or compatibility guarantee, incur meaningful irreversible cost, or choose between genuinely different owner intentions.

## Scenarios for calibration

These scenarios are **dots on a large map**, not the territory and not a checklist of patterns to hunt for. Cargo cult complexity can emerge anywhere local reasoning accumulates without reconsidering the whole. Use the scenarios to recognize the feeling of that accumulation, then apply judgment to the system in front of you.

### A sentence that manufactured a data model

A specification said every generated entry should identify where it came from. Nobody had asked for provenance, and readers already had the useful content. Literal implementation required a canonical registry URL, which required an exact version, which required new schema coupling between name and version, validation failures, and tests. One low-value sentence generated an entire chain of obligations. Deleting or narrowing the sentence would have preserved the product's value and removed the chain.

### A list that became a schema

An owner needed a list of items to skip. The implementation required every item to include a nonempty `reason`, added load-time validation, and added tests enforcing the reasons—even though the reasons changed no behavior. A simple list became structured policy machinery because explanatory prose was mistaken for required runtime data. A comment or plain list would have served the actual purpose.

### A missing identity that became a prohibition

A file originally described one component, so the file's name also served as the component's name. Later the file could contain several components. Instead of giving each component its own identity, a rule prohibited more than one unnamed component, followed by validation and error cases. The system constrained valid use to preserve an old modeling shortcut. Fixing the earlier identity mistake made the prohibition unnecessary.

### A verification command that became the goal

A feature plan required a broad server-test command. The command included an unsupported experimental subsystem unrelated to the feature, and that subsystem leaked a process even on the unchanged baseline. The feature's own tests passed, but work stopped because the written command was treated as the requirement. The valuable goal was confidence in the feature, not health of every experiment selected by one command. Correcting test ownership or narrowing the evidence preserved rigor without expanding the feature into unrelated repair work.

Other shapes will look entirely different: an abstraction that makes every concrete case harder, a compatibility layer outliving its obligation, automation that exists to satisfy unused process evidence, or a general framework built for one exception. The common signal is not any specific pattern. It is a whole whose complexity no longer earns its keep.

## Required local work journal

Any change to a spec or plan made because of this defense **must be recorded in a dedicated local journal** so the user can review where written instructions were challenged or refined.

Use this file in the project or worktree root:

```text
.complexity-inoculation-journal.md
```

Keep it local and uncommitted unless the user explicitly asks to preserve it in the repository. Its visibility in the working directory and `git status` is intentional: the journal should be easy for the user to find and review.

Keep each entry brief:

```markdown
## <timestamp> — <document and section>
**Changed:** <what changed>
**Why:** <the purpose, the unnecessary complexity, and why the revision preserves the purpose>
**Effect:** <what is avoided or simplified, plus any risk or owner decision>
```

Record the entry before or immediately after changing the document. At the next progress update, give the user the journal path and summarize new entries.

The journal is visibility, not permission. Do not silently override an explicit owner requirement and explain it afterward. Escalate genuine conflicts.

## Guardrails

This defense is not reflexive minimalism. Some problems deserve substantial systems. It is not permission to ignore relevant failures, weaken acceptance criteria, or label disliked requirements “complexity.” Deliberate owner decisions remain decisions.

It is also not a reason to hold an elaborate anti-complexity review at every step. Use judgment. The skill succeeds when the work stays proportionate to its purpose, not when it produces more procedure about simplicity.

## Compact reminder

**Step outside the chain. Recover the purpose. Question the earliest premise. Compare value with the machinery it creates. Delete before adding. Record any resulting spec or plan change in the local journal.**
