---
name: cargo-cult-review-audit
description: Audit a system for accreted complexity — machinery that exists because each change was reasoned about locally and carried forward rather than questioned. Runs two fresh agents of different model families in parallel against the same brief, then synthesizes their independent findings into ranked options. Use after a substantial body of work lands, when a system feels heavier than its purpose, or when a series of individually-reasonable changes has produced something nobody would draw on a blank page. Produces proposals only, never changes.
---

# Cargo Cult Review Audit

**Depends on:** agent-supervision.

## What this is for

Software accretes. Someone writes a sentence in a spec; a requirement is inferred from it; a schema grows to satisfy the requirement; a validator grows to enforce the schema; tests grow to pin the validator — and by the end there is a substantial apparatus whose original justification nobody would defend if asked plainly. Every step was locally defensible. The person making each change was reasoning correctly about the change in front of them. Nobody stood back to ask whether the thing being elaborated should exist at all.

That is the cargo cult: not stupidity, but forward motion in the absence of anyone looking at the whole. It is invisible from inside the sequence of changes and obvious from outside it.

This skill puts people outside it. It runs two auditors who did not participate in building the thing, gives them permission to question its foundations rather than its conformance, and asks them what they would delete.

Use it when:

- a substantial body of work has landed and you want a sanity read before it becomes load-bearing;
- a system feels heavier than the job it does, without a specific complaint you can name;
- a series of reasonable-looking changes has produced something that would not be drawn this way from scratch;
- you notice yourself defending a mechanism by explaining its history rather than its purpose.

## How to run it

**1. Create two fresh agents.** Different model families, so their blind spots differ. Default to one pi running GPT-5.6 Sol and one Claude running Fable; override when a particular invocation calls for something else. Follow the `agent-supervision` skill for launching, registering, observing, and messaging them.

Fresh context is a requirement, not a nicety. Do not reuse an agent that participated in building the system, reviewed it earlier, or has already read findings about it. An auditor carrying prior framing will cargo-cult that framing, which is the same failure one level up. If a suitable agent already exists but has history, retire it and create a new one.

**2. Give both the same brief, and let them work independently.** They must not see each other's reports. Two independent passes that converge is a strong signal; two passes that were allowed to influence each other are one pass.

[audit-brief.md](audit-brief.md) is a template. Copy it, fill the three fields at the top — what system to audit and where it lives, its purpose in a sentence or two, and where that auditor writes its report — and send each agent its own filled copy as a single file. One agent, one complete document. Do not send the brief and then the details as a second message: an auditor reads what it has, and a document that promises context it does not contain will stop and ask for it.

Do not add a checklist of things to look for. A checklist bounds the auditor to what the person writing it already thought of, which is precisely the knowledge the audit exists to supplement. State the target, state the purpose, ask what is wrong.

**3. Synthesize, do not relay.** Read both reports in full. Then:

- **Filter against decisions the owner has already made.** An auditor coming in cold will flag settled decisions as defects, because nothing in the system records that someone chose them deliberately. Recognizing those and dropping them is the synthesizer's job, not the owner's. Passing them through as open findings wastes the owner's time and erodes trust in the rest of the report.
- **Verify claims that drive recommendations.** Auditors reason from reading; some conclusions will be wrong in ways a two-minute check would reveal. Check the load-bearing ones yourself before repeating them.
- **Note convergence explicitly.** When two independent auditors of different model families name the same thing first, say so — that is the strongest signal the exercise produces.
- **Rank by what you would do first**, and for each item say what it deletes and what it costs.

**4. Nothing is acted on without owner approval.** The output is options. Some findings will contradict decisions the owner made deliberately, and the owner is entitled to say "that is not a flaw, that is my call" — which is information about the system's intent, not a failure of the audit.

## The principles the audit applies

Stated in full, with worked examples, in [audit-brief.md](audit-brief.md). In brief:

- **Fix the instance, not the class.** A mechanism should earn its existence by a multiplicity of instances that already exist, not by one instance plus imagination.
- **Size the solution to the problem.** When the ratio is absurd, the design is wrong even if every line is correct.
- **Prior text is evidence, not law.** In a system that has not shipped, every existing artifact is a draft. If a rule is generating work, question the rule before doing the work.
- **Cascade is a smell.** If satisfying X requires adding Y, which requires constraint Z, which forces a new failure case — the chain is evidence that X was wrong.
- **Deletion is the first move to consider.** The gradient runs the other way naturally: adding feels productive and its cost is invisible; deleting feels risky and its benefit is invisible.
- **The one-sentence test.** Describe the mechanism aloud in one sentence and predict the owner's response. If the sentence sounds absurd, the mechanism is wrong regardless of whether the code is correct.

## What this skill is not

It is not a code review, a correctness audit, or a conformance check. Those ask "is this right?" This asks "should this exist?" An auditor who spends the pass verifying that the implementation matches the spec has misunderstood the assignment — the spec is one of the things under suspicion.

It is also not a license to rewrite. The deliverable is a report a human can act on, ranked and honest, including "this is basically sound" when that is the answer. An audit that manufactures findings to justify itself is worse than no audit.
