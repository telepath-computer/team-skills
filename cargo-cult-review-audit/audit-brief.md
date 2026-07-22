# Audit brief

<!-- TEMPLATE. Copy this file, fill the three fields below, and send the filled copy.
     Do not send this file with the placeholders still in it, and do not send the
     fields as a separate message — the auditor should receive one complete document. -->

**The system:** _what to audit and where it lives — specs, implementation, tests._

**Its purpose:** _one or two sentences. You are evaluated against this, not against the specification._

**Your report:** _the path to write it to._

---

You are auditing a system you did not build. You have no history with it, and that is the point.

Evaluate it top-down against its stated purpose. The question is not whether the implementation matches the specification — assume both are suspect. The question is: **if you designed this from scratch, knowing only the purpose, what would it look like, and how does what exists differ?** Where the difference is unjustified, say so.

Treat the specification as an artifact under examination, not as authority. Its core assumptions are in scope for proposed change. A rule written down is not thereby correct; it is evidence that someone once thought it was.

## The failure you are looking for

Software accretes. A sentence appears in a document; a requirement is inferred from it; a schema grows to satisfy the requirement; a validator grows to enforce the schema; tests grow to pin the validator. By the end there is substantial machinery whose original justification nobody would defend if asked plainly — and yet every individual step was defensible, and the person making it was reasoning correctly about the change in front of them.

Nobody was wrong. Nobody stood outside and looked at the whole. That is what you are here to do.

The damage is invisible from inside the sequence of changes and obvious from outside it. You are the outside.

## Principles to apply

**Fix the instance, not the class.** When something concrete and bounded goes wrong, the cheap answer is usually to handle that specific thing. The expensive answer is to build a mechanism that handles it and everything like it — which must then anticipate cases that do not exist, and generates its own maintenance forever. A mechanism should earn its existence by a multiplicity of instances that already exist, not by one instance plus imagination.

**Size the solution to the problem.** Look at the ratio between how much machinery something takes and how much it accomplishes. When that ratio is absurd, the design is wrong even if every line of it is correct. Correctness at the wrong scale is still wrong.

**Prior text is evidence, not law.** A sentence written in an unshipped document is a draft, not a requirement. If a rule is generating work — schemas, validators, failure cases, tests — question whether the rule should exist before doing the work it demands. The question "why do we need this?" is always in scope, and it is asked least often about the things that generate the most.

**Cascade is a smell.** If satisfying X requires adding Y, which requires constraint Z, which forces a new failure case that needs its own handling — stop and look at X. The chain is evidence that X was wrong, not that Y and Z are needed. Every step in such a chain is a place where someone could have turned around, and the earliest one is nearly always the right one.

**Deletion is the first move to consider, not the last resort.** When something is wrong, ask what can come out before asking what should go in. The natural gradient runs the other way: adding feels productive and its cost is invisible; deleting feels risky and its benefit is invisible. Correcting for that bias is most of this job.

**The one-sentence test.** Describe a mechanism aloud, in one plain sentence, and predict how the system's owner would react. "We have a function that converts HTML escape sequences in text we copied out of a file." "We have a rule preventing a record from declaring two unnamed components." "We maintain a list of which directories the build produces." If the sentence itself sounds absurd, the mechanism is wrong — regardless of whether the code implementing it is correct. This test is cheap and catches more than any amount of careful reading.

**Prefer a simple rule plus a human over an elaborate rule alone.** Most systems process a messy world: dependencies that do not conform, inputs that arrive in unexpected shapes, cases nobody anticipated. The instinct is to grow the rules until they absorb every case. That produces logic nobody can predict or review, and each new oddity grows it further. The better shape is a simple rule set covering the ordinary path, with anything nonconforming failing loudly and being handled by a person — a configured exception, a written-down answer, a deliberate carve-out. Where you find logic that exists to automatically absorb a nonconforming case, ask whether a configuration entry and a loud failure would have done the job with none of the code.

## Three examples, for calibration only

These are real cases, drawn from different systems and described without their original domains so they read as shapes rather than as things to go looking for. All three were fixed.

They are **not a list of patterns to search for.** These exact shapes are unlikely to recur, and hunting for repeats of them is the wrong use of them. Read them to calibrate what this kind of wrongness feels like from the outside, then look wherever your own judgment leads.

**A chapter that inherited the book's title.** A configuration file tracked files that had been copied into a project from outside it — a font, some artwork. Each record described one file and carried a `description` naming what it was. Later the project needed to record files that contained *several* distinct copied-in items, so records grew a list of components underneath them. But the name stayed on the parent: a component with no other identity took its name from the file it lived in. That worked while every record had exactly one such component. When someone noticed that two components in one file would render as two identically-named entries, a rule was added forbidding a record from declaring a second unnamed component. Book grew chapters, chapters never got titles, then a rule forbade a second chapter. The fix was to give components their own names, at which point the rule had nothing left to prevent.

**A requirement nobody asked for, and the machinery that grew to serve it.** A sentence appeared in a specification saying each entry in a generated document should state "where it came from." Nobody had asked for that, and nobody reading the document needed it — an entry already carried what the item was and the text that had to accompany it. But once written, the sentence became a requirement that every entry carry a canonical registry URL for that item's exact version. That demanded an exact version on every entry, which forced a schema rule that a record declares its name and version "both or neither," which added load-time rejection cases and test assertions, which produced a contradiction with an optional version field elsewhere — consuming a full review round to resolve. Substantial machinery, built to control a data point nobody had requested. Deleting the sentence deleted all of it.

**A list that became a schema.** The owner asked for an ignore list: a list of items the system skips. What was built was a list of records with a required `reason` field, a configuration-load validator rejecting any entry whose reason was missing or empty, a test asserting every real entry carried one, and a second test asserting that changing a reason changed nothing — a test proving that a comment is a comment. Meanwhile the specification said an entry "needs no justification beyond being recorded," so the document declared the field unnecessary while the loader refused to start without it. A list became a schema, the schema grew a validator, the validator grew tests, and the tests contradicted the document. The entire apparatus existed to hold a note a human could have written as a comment.

What these share is worth more than what each one is: in every case each individual step was defensible, and the accumulation was not.

## What to produce

A report containing proposals and recommendations. **Make no changes** — no code, no specifications, no configuration.

- Rank by what you would actually do first.
- For each item, say what it deletes and what it costs.
- Distinguish a defect from a judgment call, and say which you think it is.
- Say plainly when something is fine. A short honest report beats a padded one, and if the system is basically sound, that is the finding.
- If you are uncertain whether something is deliberate, say so rather than assuming it is a mistake — some of what looks wrong is a decision somebody made for reasons not visible in the code.
