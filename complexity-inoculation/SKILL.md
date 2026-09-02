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

## Instructions are themselves a source of complexity

The same accretion happens in what you write *to* a capable reader, not only in what you build. Over-specification is complexity, and it compounds the same way.

**Let the highest statement the reader can work from be the boundary of the communication.** If a competent agent or engineer can act correctly from a general statement, that statement is the instruction. Enumerating the cases it covers does not add rigor — it moves judgment out of the reader and into a list that will be wrong the first time reality presents a case the list did not anticipate.

**Enumeration implies litigation.** A list of examples stops being illustration and becomes the definition. The reader then reasons about whether their situation is *on the list* rather than about what was meant, and edge cases become disputes about the boundary of the enumeration instead of ordinary judgment calls. The list has quietly replaced the intent it was meant to illustrate.

**Prefer soft statements where soft statements suffice.** A rule with strong, far-reaching teeth forecloses the gray areas where intelligence is most valuable. Reach for that force only when crossing the line is genuinely unacceptable — not to signal that you mean it.

**Hard lines propagate.** Once one is drawn, the environment changes: readers begin expecting hard lines, hesitate where they should exercise judgment, and infer that other lines must exist and should be drawn. One unnecessary prohibition teaches everyone downstream to ask for prohibitions. That cost never appears in the document that caused it.

The test before writing a constraint: *could this reader do the right thing without it?* If yes, the constraint is not protection, it is noise with authority.

## A positive statement is not a negative rule

The most common way toothy limitations get volunteered into existence: read a statement of what something *is* or *does*, notice the space around it that the statement does not cover, and treat that space as a gap that a rule must fill. "The spec says we buy cherries at the store — but it doesn't say what we *cannot* buy! Can we buy lemons? It's a flawed spec!" No. It is fine. A spec describes what a thing has and does. It does not, by default, define the total, logically derivable landscape of everything it does not cover and does not allow, and it is not defective for leaving that landscape open. The open space is where judgment lives.

So: when a statement says where something lives, that is not a statement that it may live nowhere else. When a statement says what a hook exposes, that is not a request to enumerate what may not be read from it. When a policy is positive about one thing, do not infer the negative about its neighbors and then promote the inference into a global rule. Nobody asked for the rule; you volunteered it.

Negative rules — limitations with teeth — remain available. They are the rare exception, chosen deliberately when extreme emphasis or strict procedure is worth what it costs: every hard line removes a case from agent judgment, and unasked-for ones create a litigious, fearful status quo in which every small new thing has to be raised for human approval against a limitation nobody actually wanted. Write one only when that cost is being paid on purpose.

## The asymmetry: following rules versus writing them

An agent is highly efficient at following litigious rules and extremely inefficient at authoring them unsupervised. Given a precise rule, it applies the rule faithfully, to the letter, in every case the rule reaches — including the cases the author never imagined. Asked to write one, it produces a sentence that reads confidently and has not been traced against the cases it will govern. The two skills do not come as a pair, and the gap is invisible from the inside: writing a rule feels like the same activity as understanding one.

The downstream reader of an agent-authored rule is usually another litigious agent — often the author itself a few turns later — which will apply it exactly as written. So the cost of a rule authored with too little thought is not a vague one; it is a specific wrong action, taken confidently, the first time reality presents a case the author did not consider. A numeric cap on review rounds, invented to make a loop terminate, ends a review that genuinely needed another round. A stopping test phrased as "if the next check could not change anything, stop" halts supervision of any task long enough to outlast one check interval. Both were written to sound like principles; neither survived its first real case.

So treat authoring a rule as the higher-risk act, the opposite of how it feels. When a situation seems to call for a rule that the governing document does not contain, the default is to ask the owner, not to supply one. Where a rule genuinely must be written, walk it against the concrete cases it will meet — especially the long, the slow, the iterative, and the ones where the reader is an agent that will not second-guess it — before it becomes text with authority.

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

## Guardrails

This defense is not reflexive minimalism. Some problems deserve substantial systems. It is not permission to ignore relevant failures, weaken acceptance criteria, or label disliked requirements “complexity.” Deliberate owner decisions remain decisions.

It is also not a reason to hold an elaborate anti-complexity review at every step. Use judgment. The skill succeeds when the work stays proportionate to its purpose, not when it produces more procedure about simplicity.

## Compact reminder

**Step outside the chain. Recover the purpose. Question the earliest premise. Compare value with the machinery it creates. Delete before adding.**
