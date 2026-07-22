---
name: plain-english
description: Write so the reader never has to decode private shorthand. Use when composing any text a reader will parse — chat replies, summaries, PR/commit messages, docs, comments — to avoid inventing one-off jargon, nominalizing a process into an undefined label, or compressing meaning into terms only the writer holds the key to. The reader usually has full conversational and project context; what they lack is the writer's internal naming and compression decisions. Triggers include a reader asking "what do you mean by X", a request to apply "plain-english policy", or the writer catching themselves coining a term mid-conversation and reusing it as if it were shared.
---

# Plain english

The reader is sharp and shares the writer's context: the conversation, the project, the decision at hand. What they do **not** have is the inside of the writer's head — the labels coined a moment ago, the noun made out of a verb, the meaning crushed into a short token because it felt efficient. When a competent reader has to stop and ask "what do you mean by that?", the writing handed them a cipher. That is the failure this skill prevents.

This is not about simplifying. The reader does not need smaller words or a gentler pace. They need the writer to stop encrypting.

## The core rule

**Use a term only if the reader already shares it, or define it in the same breath it is introduced.** Any term they would have to ask about is a defect in the writing, not a gap in their knowledge. The burden is on the writer.

The test, before using any term: *could the reader define this without asking?* If not, define it inline or drop the label and just say the thing.

## What is fine — and what is not

The problem is the **in-line, one-off encoding of new jargon without context.** It is not the use of real terminology.

**Fine — established, shared, or genuinely meaningful vocabulary.** Within a project, real shared terms need no gloss: module and file names, architectural concepts the team uses daily, standard technical words (idempotent, race condition, cache invalidation). The reader holds the key already, and paraphrasing these only adds noise. (Writing for a reader *outside* that project, the same terms may need a gloss — calibrate to who is actually reading.)

**Fine — a coined label, introduced with its definition, then reused.** When a short label genuinely earns its keep because an idea recurs, define it before the first reuse:

> Two stored records predate the new format: one missing its version field, one with a null timestamp. Call these *legacy records*. The migration test writes both legacy records and asserts they still load.

The label is safe because the definition came first; from that point on it is shared.

**Not fine — private compressions invented mid-conversation and used as if agreed.** Coining a phrase from one's own reasoning and deploying it like a defined term. Reaching for a short token because it is faster to *type*, when the plain description would cost the reader nothing to read.

## Examples

These are real failures (lightly generalized) with the fix beside each.

**Bad — nominalizing a process into an undefined noun.** This is the trap that named the skill. A writer described a code comment that "papered over" a known-wrong test result — a clear verb phrase. Ten lines later they wrote:

> The fix removes the paper.

The reader has no dictionary entry for "the paper" as a thing. It was minted mid-paragraph from the earlier verb and then reused as if shared. The verb form ("the comment papers over the bug") was fine; turning it into a noun broke it.

> **Fix:** The fix deletes that misleading comment and asserts the correct result instead.

**Bad — a pipeline crushed into an arrow chain.** Describing how a page assembles its text:

> served HTML → JS bundle → host message → DOM

Even when each step means something to the writer, the arrow form makes the reader rebuild the sentence the arrows replaced. Arrow chains optimize the writer's keystrokes at the reader's expense.

> **Fix:** The served HTML loads a script, which requests the text from the host and writes it into the page.

**Bad — a concept compressed into a hyphenated adjective.** 

> the identical define-based path a production build uses

"define-based" silently packs a build-tool mechanism into one adjective; a reader who does not already hold that mechanism cannot unpack it.

> **Fix:** the same path resolution a production build uses, where the directory is baked in as a build-time constant.

**Bad — an ordinary noun phrase compressed into a coined compound.**

> ran all the shared-harness consumers

"shared-harness consumers" stacks a compound adjective ("shared-harness") onto an invented collective noun ("consumers") to name a thing that has a plain, ready description. The reader has to unpack two compressions at once to recover a phrase that was never hard to say. There is no efficiency here for anyone but the writer's keystrokes.

> **Fix:** ran all the other tests that use the same harness.

**Good — a real domain term, used directly, no gloss.** Assuming the reader works on the project:

> The migration runs inside `applyPendingMigrations`, so a half-applied batch rolls back as one transaction.

`applyPendingMigrations`, batch, transaction, roll back are genuine shared vocabulary. Glossing them would be the opposite mistake (see anti-patterns).

## Anti-patterns

- **ELI5 / talking down.** Over-correcting into baby talk, stripping all technical vocabulary, over-explaining what the reader plainly knows. This is its own failure — it wastes the reader's time and is faintly insulting. Plainness is about *decodability*, not *simplicity*; use real terms, just do not invent private ones.
- **Stripping legitimate domain terms.** Replacing `idempotent` with a clumsy paraphrase, or spelling out a module name the reader uses daily. If the term is shared, use it.
- **Defining the obvious.** Glossing terms the reader clearly holds is the mirror image of cryptic shorthand — both ignore what the reader actually knows. Calibrate to this reader.
- **Defending the shorthand when asked.** When a reader asks "what do you mean by X", fix the writing and own that it was unclear — do not explain the cipher as though they had merely missed it.
- **Compression for the writer's benefit.** Arrow chains, cryptic abbreviations, and coined tokens that are shorter to type but slower to read. Optimize for the reader's parse, not the writer's keystrokes.

## The through-line

Clarity is measured at the reader's end, not the writer's. A sentence that only parses for someone who watched the writer think has failed — no matter how precise and efficient it feels from where the writer sits. Speak the reader's vocabulary; when adding to it, hand over the definition in the same breath.
