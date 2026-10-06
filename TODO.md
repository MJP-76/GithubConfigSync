# GitHub Config Sync — TODO

Our own list of things we want to do. GitHub Issues stay the source of truth
for bugs; this file is for work that is not a bug report. An item may name an
issue as the target of the work, but must not restate or mirror what the issue
says.

---

## Planned

- [ ] **Follow `!include` references so a selection is self-contained**

      Picking a file that `!include`s another should imply the included one —
      shown as *implied* in the tree rather than as a separate tick.

      Today, removing an included file from the selection deletes it from the
      repository even though something still references it.

      Constraints: must not bypass the runtime floor, the security checks, or
      the user's `.gitignore`.

      Surfaced in the #44 thread and committed to there as "looking at adding".
