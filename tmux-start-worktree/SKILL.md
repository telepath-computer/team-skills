---
name: tmux-start-worktree
description: "Set up a dedicated Git worktree for a repository task under the parent workspace's wt/ directory, using a thopter/{task} branch, while keeping the canonical repo clean on main; setup does not imply starting implementation. The tmux/superv variant, homing agent shells in the worktrees' parent folder for tmux-window launches; for worktrees under herdr use herdr-start-worktree."
---

# Start Worktree

**Depends on:** none.

Use this skill when setting up a new coding task in an existing Git repository and the user wants the task isolated in a Git worktree.

## Goal

Keep canonical repository checkouts stable and easy to find, while doing all task work in predictable task-specific worktrees.

Canonical repos usually live directly under a parent repos directory such as:

- `~/workspace`
- `~/repos`
- another user-designated parent repos directory

Task worktrees should live under that same parent directory at:

```text
$repo_parent/wt/{canonical-repo-dir-name}/{task-slug}
```

Branches should be named:

```text
thopter/{task-slug}
```

Example:

```text
canonical repo:  ~/workspace/carryall
worktree:        ~/workspace/wt/carryall/top-k-refactor
branch:          thopter/top-k-refactor
```

After creating the worktree, treat it as the primary working **target** for future task work — the place repo commands operate on, named explicitly in task briefs. It is not where agent shells live: agents launch in the worktrees' parent folder (`$repo_parent/wt/{repo-name}/`), because worktrees are often shorter-lived than the agent sessions that operate over them. Creating the worktree is setup only; it is not permission to begin implementation.

## Starting-directory rule

Before doing anything in an operator/supervisor session, check the current working directory.

The operator/supervisor agent session should start in the parent repos directory, not inside an individual repo, worktree, home directory, or random subdirectory. Task agents launched by the `triad` CLI follow the same spirit one level down: they start in the worktrees' parent folder (`$repo_parent/wt/{repo-name}/`), not inside their task worktree — an agent must not be stuck inside a worktree folder, because worktrees are often shorter-lived than the agent sessions that operate over them. The task brief names the worktree; the agent cds into it explicitly. (Codex-kind agents are the one exception and start inside the worktree; see tmux-agent-triad.)

Good:

```text
~/workspace
~/repos
```

Bad:

```text
~/workspace/carryall
~/workspace/wt/carryall/top-k-refactor
~/Downloads
```

If the operator/supervisor starting directory is not the parent repos directory, complain clearly before proceeding. Explain that the user prefers operator sessions to be anchored in the parent repos directory so sessions are easy to find and resume later. Ask whether to continue anyway or restart from the parent directory.

## Inputs to determine

Identify or ask for:

1. The parent repos directory.
2. The canonical repo directory.
3. The task name or task slug.
4. The default branch, usually `main`.

If the user gives a prose task name and you are creating the worktree manually, convert it to a short lowercase slug suitable for both a path and a branch name. Note: the `triad` CLI slugifies `--task` mechanically (`refactor top-k query logic` -> `refactor-top-k-query-logic`), so pass an explicit short slug such as `top-k-refactor` as `--task` if that is the intended branch/worktree name.

Examples:

```text
"refactor top-k query logic" -> top-k-refactor
"fix auth callback retries" -> auth-callback-retries
```

Use only simple slug characters: lowercase letters, numbers, and hyphens.

## Canonical repo expectations

The canonical repo is the normal checkout directly under the parent repos directory, for example:

```text
~/workspace/carryall
```

Do not do task work directly in the canonical repo unless the user explicitly asks.

Before creating the worktree:

1. Check that the canonical repo exists.
2. Check that it is a Git repository.
3. Check its current branch.
4. Prefer it to be on `main` or the repo's default branch.
5. Check for uncommitted changes.

If the canonical repo is not on the default branch or has uncommitted changes, warn the user and ask before proceeding unless the correct next step is obvious and safe.

## Worktree creation procedure

From the canonical repo, create the worktree at:

```text
$repo_parent/wt/{repo-name}/{task-slug}
```

using branch:

```text
thopter/{task-slug}
```

**Default base ref:** the **remote** default branch (`origin/main`, or `origin/master` / the actual remote default), not the local default branch. The local default may be behind, ahead, or diverged from the remote — basing on `origin/{default}` ensures the task starts from the latest published state.

The user may override the base ref — e.g., "branch off `feature/x`", "branch off the current local main", "branch off tag `v1.2.0`", "branch off commit `abc123`". Honor explicit overrides as given. Absent any direction, use `origin/{default}`.

Typical command shape:

```bash
mkdir -p "$repo_parent/wt/$repo_name"
git -C "$canonical_repo" fetch --all --prune
git -C "$canonical_repo" worktree add -b "thopter/$task_slug" "$repo_parent/wt/$repo_name/$task_slug" origin/main
```

The `fetch` must come first so `origin/main` reflects the current remote tip. Do not substitute local `main` as the base ref even if it appears up to date — the explicit `origin/{default}` form makes the freshness guarantee independent of local state.

If the branch already exists, do not blindly overwrite it. Inspect existing branches and worktrees:

```bash
git -C "$canonical_repo" worktree list
git -C "$canonical_repo" branch --list "thopter/$task_slug"
```

If an existing matching worktree is present, prefer reusing it after confirming it is the intended task workspace.

If the branch exists without a worktree, create a worktree from the existing branch:

```bash
git -C "$canonical_repo" worktree add "$repo_parent/wt/$repo_name/$task_slug" "thopter/$task_slug"
```

## After creation

After the worktree exists:

1. Report the worktree path and branch.
2. Treat the worktree as the primary target for future work on this task (agent shells stay homed in the worktrees' parent folder).
3. Do not begin implementation merely because the worktree exists.
4. Run future repo commands against the worktree once work has been explicitly requested — cd in explicitly or use absolute paths — unless there is a specific reason to inspect the canonical repo.
5. Remind the user if needed that the canonical repo remains the clean main-branch checkout.

## Do not

- Start task work directly in the canonical repo by default.
- Create worktrees in ad-hoc locations.
- Use branch names without the `thopter/` prefix unless the user asks.
- Ignore a mismatched starting directory.
- Assume the repo or task slug when multiple interpretations are plausible.
