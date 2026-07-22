---
name: test-iteration-discipline
description: >-
  Pick the right test invocation when iterating on failures, fixing a bug, or
  finishing a unit of work. Use whenever you're tempted to run a broad suite
  (`npm test`, `npm run verify`, `pytest`, `cargo test`, `go test ./...`, full
  e2e, etc.) to "see what's broken" — that's the failure mode this skill exists
  to prevent. Triggers: running tests during development, debugging a failing
  test, choosing how to validate a refactor, deciding whether a slice/PR is
  ready to land, working on a resource-constrained host where concurrent broad
  suites OOM.
---

# Test iteration discipline

Broad test suites are gates, not probes. The full verify run is the closer, not the iteration loop.

## The kernel

Three modes, in this order:

1. **Targeted (predictive).** When you make a code change, you have a theory of what it impacts. Before anything else, run the tests your theory predicts are affected — narrowly, by name or by file. This is verification of your model, not discovery. You expect them to pass after the change; if they don't, you immediately have a tight signal to iterate on.

2. **Discovery (broad).** Once your targeted runs are clean and you *believe* you should be green everywhere, you run a broader suite to surface anything your theory missed. This is the right job for a broad invocation — enumerate unexpected failures. Discovery is a check against your theory, not a first pass.

3. **Iteration (narrow again).** When discovery surfaces an unexpected failing test, you switch instruments. You don't re-run the broad suite to see if your next fix worked — you invoke that one failing test by grep/filter/pattern, iterate against it until it passes, then climb back up the ladder one rung at a time, each rung confirming the prior stays green. Only at the top do you re-run discovery to confirm nothing else regressed.

Two supporting rules:

- **As iteration depth increases, invocation breadth decreases.** Once you're in iteration mode on a known failure, the broad suite is the wrong instrument for the fix/verify loop. Running the same `npm run verify` three times to see if your one-line fix worked is using a $20 instrument to answer a $0.50 question.

- **As prior confidence increases, invocation breadth increases.** The broader the suite, the higher the confidence required before paying for it. The full verify run at the end is a final gate where failure should be a *genuine surprise* — because all three modes above have already done the upfront work.

The shape this produces: many targeted runs at the narrowest rung → one or two broad runs for discovery → if anything surfaces, drop to the narrowest rung and climb → one final broad gate.

## The ladder

Language-agnostic rungs, narrowest to broadest:

1. **Single test case.** A named test, addressed by grep/filter/pattern. (`vitest -t 'rejects empty path'`, `pytest -k rejects_empty_path`, `cargo test rejects_empty_path`, `go test -run TestRejectsEmptyPath`, `mvn test -Dtest=...#rejectsEmptyPath`, `rspec -e 'rejects empty path'`.)
2. **Single test file or describe block.** One file's worth, or one nested group. (`vitest run path/to/file.test.ts`, `pytest path/to/test_file.py`, `cargo test --test file_name`, `go test ./pkg -run TestGroup`, `mvn test -Dtest=ClassName`, `rspec spec/path/file_spec.rb`.)
3. **Module or package suite.** Everything in one package/module/workspace member. (`vitest --project @scope/pkg`, `pytest path/to/module/`, `cargo test -p crate_name`, `go test ./pkg/...`, `mvn -pl module test`, `rspec spec/module/`.)
4. **Whole workspace unit-test run.** (`npm test`, `pytest`, `cargo test`, `go test ./...`, `mvn test`, `rspec`.)
5. **Verify / full gate.** Lint + type-check + every test surface, often including expensive end-to-end. (`npm run verify`, `tox`, `cargo test --all-features`, `make ci`, `nox`, `bundle exec rake`.)

Rung 5 is the closer. It runs once per coherent unit of work — typically at the end of a slice, before pushing, before opening a PR. Not three times. Not "let me just check one more thing." Once.

## E2E is a special case of rung 5

End-to-end tests are usually the largest single cost in the verify suite. They get their own internal ladder, parallel to unit tests:

1. **Single e2e test.** (`playwright test -g 'pattern'`, `cypress run --spec file.cy.ts -e grep='...'`.)
2. **Single e2e spec file.** (`playwright test test/e2e-browser/foo.spec.ts`.)
3. **E2E for a single area.** (Directory-scoped invocation: `playwright test test/e2e-browser/auth/`.)
4. **All e2e in one shape** (browser, node, electron).
5. **Full e2e suite.** Final gate, same status as full verify.

Never use the full e2e suite as the iteration trampoline. If you're debugging an e2e regression, run the one failing spec by file or by `-g <pattern>`. When that's green, expand by one rung. The full suite is the closer, not the probe.

## The three modes, in practice

**Targeted mode (predictive).** You just made a code change. Before running anything, ask: *what tests does my theory of this change predict should still pass — and which ones does it predict should now pass that didn't before?* Run those, narrowly:

- `vitest run path/to/the.test.ts -t 'specific case'`
- `pytest path/to/test_file.py::TestClass::test_specific_case`
- `cargo test path::to::specific_case`
- `go test ./pkg -run TestSpecificCase`
- `rspec spec/path/file_spec.rb -e 'specific case'`

The win condition: the tests your theory said would pass do pass. If they don't, you have a tight, immediate signal — your change interacts with the code under test differently than you predicted, and you iterate against that single failure.

This is *not* discovery — you already have a theory. You're testing the theory against reality at the narrowest granularity that proves it.

**Discovery mode (broad).** Only after your targeted runs are clean do you run a broader suite. The purpose is to surface what your theory missed — collateral damage you didn't predict, distant tests that depended on something you changed, integration points you forgot. Read the failure list. Stop. Do not re-run the broad suite as your next action.

**Iteration mode (narrow again).** Discovery surfaced an unexpected failing test. You know its name. Switch instruments. The very first thing you do is invoke that one test by name/grep/filter, in isolation, using the same forms as targeted mode. Read the failure output. Make a change. Re-run *the same single-test invocation*. Repeat until that test passes. Then expand: file, module, package, workspace, one rung at a time, each confirming the prior is still green.

The transition from discovery to iteration is the moment most worker agents fumble — they keep using the broad suite to check whether their fix worked, paying full price for partial signal. Don't. The instant you have a failing test name, the next invocation should target only that test.

## Anti-patterns to recognize and stop

- **The verify trampoline.** Running `npm run verify` (or equivalent), reading the failure, making a one-line change, running `npm run verify` again to see if it worked. Each cycle is minutes-to-tens-of-minutes of CPU. The narrowest invocation gets you the same signal in seconds.
- **The "let me just be sure" extra full run.** You've already passed the narrower rungs; you've already passed the broader one once; now you're running it again for vibes. Stop.
- **Background-spawning broad suites.** Running `npm test &` or `npm run verify &` while continuing to work. On any resource-constrained host this is how OOMs happen — a second invocation lands while the first is still consuming RAM. Always foreground; always one at a time.
- **Running broad and narrow concurrently.** "I'll start the verify in window 2 while I keep iterating in window 1." Same OOM failure mode. Pick one.
- **Treating coverage gaps as a reason to run the broad suite.** If you suspect uncovered code, *add tests*. Don't run the full suite hoping something incidental catches it.
- **"It only fails when the whole suite runs."** That's a test-order or shared-state bug, not evidence for running the whole suite. Pin the failure to the minimal pair/triple of tests that reproduces it, then debug at *that* granularity. The broad run isn't the diagnostic — the minimal reproducer is.

## When to deviate (legitimately)

The ladder is a default, not a religion. Some signals genuinely need the broader rung:

- **You suspect cross-module coupling.** If a refactor crosses package boundaries and you've finished the local rungs, jumping straight to rung 3 or 4 is sometimes correct. Skipping to rung 5 still isn't — type-check + lint are not test signal.
- **Final pre-push gate.** Always rung 5, exactly once, before pushing the work or opening the PR. This is what rung 5 exists for.
- **CI is the only place a flake reproduces.** Run the broader scope locally to chase the flake, but pin it to a reproducer at the lowest rung you can, then stop.
- **Tooling forces it.** Some frameworks make narrow invocation awkward (Maven historically, some Bazel setups). Where the tooling fights you, file the friction as a finding and use the narrowest path the tooling supports — don't surrender to "just run the whole thing."

## How to budget a slice / PR / unit of work

A coherent unit of work — a slice in an implementation plan, a fix-and-test cycle, a PR — should produce roughly this shape of test execution:

- Many invocations at rung 1 (during iteration).
- Several at rungs 2–3 (as each layer comes clean).
- One or two at rung 4 (when you think you're done).
- Exactly one at rung 5 (the final gate before push).

If you find yourself running rung 4 or rung 5 more than once or twice for the same unit of work, that's a smell — either the work wasn't actually ready or you were using the broad suite as a probe. Step back and figure out which.

## Tool-agnostic reminders

- **Watch mode is iteration, not verification.** Vitest/jest watch, pytest-watch, etc., are fine for rung-1/rung-2 iteration. They are not a substitute for running the rungs above explicitly at decision points.
- **`--bail` on broad runs.** When you do run a broad suite, bail on first failure (`--bail 1`, `-x` in pytest, `--fail-fast` in cargo/go). You're not collecting a failure inventory; you're verifying a hypothesis.
- **Parallel test execution is fine. Concurrent broad-suite *invocations* are not.** A single `vitest run` may use all cores. Two simultaneous `vitest run` invocations use two times all cores and double the RAM. Different problem.

## One-line summary to give a worker agent

> When you change code, run the narrow tests your theory says should be affected, *then* run a broad suite to surface what your theory missed. To fix any failure that surfaces, switch instruments: grep the exact failing test by name and iterate against that single invocation until it passes, then climb back up the ladder one rung at a time. The full verify suite is the final gate, not the iteration loop — run it once per unit of work, never backgrounded, never concurrent.
