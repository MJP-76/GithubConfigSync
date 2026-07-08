# Multi-device workflow

Use this repo as the shared source of truth across devices.

## Central paths

- Central repo: `E:\NextCloud\_Projects\GitHub\GithubConfigSync`
- Shared handoff: `SESSION_HANDOVER.md`
- Shared shortcuts: `SESSION_SHORTCUTS.md`

## On the current device

1. Make changes in the central repo.
2. Commit them locally.
3. Push to the shared remote branch.

## On another device

1. Clone or open the same central repo path if available.
2. Fetch the remote branches.
3. Check out the branch you need.
4. Pull the latest commits.
5. Rebuild any local worktree from that branch if needed.

## Worktree guidance

- Treat worktrees as disposable local views of the shared repo state.
- Do not expect worktrees themselves to sync; sync the underlying branch instead.
- If a worktree is stale, delete and recreate it from the updated branch.

## Handoff order

1. Read `PROJECT_PLAN.md`.
2. Read `SESSION_HANDOVER.md`.
3. Read `SESSION_SHORTCUTS.md`.
4. Pull the branch and continue.
