# GitHub Config Sync — Project Plan & Tracker

Use this as the single source of truth for **where we are**, **what is next**, and **what is done**.

---

## Status Snapshot

- **Last updated:** 2026-07-07
- **Current milestone:** `v0.1.2 — Sync Engine Hardening`
- **Track:** Home Assistant Integration + Home Assistant Add-on (Ingress Web UI)
- **Latest shipped improvements:** Add-on Device Flow auth + ingress path fix + repo picker/create flow
- **Version state:** See auto-managed tracker below.

<!-- VERSION:START -->
- Integration version: `0.0.23`
- Add-on version: `0.1.6`
- Channel: `stable`
- Release tag: `v0.0.23`
<!-- VERSION:END -->

---

## Cross-device handoff (use this first on another machine)

1. Open this file (`PROJECT_PLAN.md`) and read **Status Snapshot** + **Active Sprint Tracker**.
2. Verify the latest tag/release in GitHub (`v0.0.23` at time of writing).
3. Continue from the top unchecked item in **In Progress**.
4. After finishing work, update this file and ship via: version bump → tag → GitHub release.

**Current repo context**

- Integration path: `custom_components/github_config_sync/`
- Add-on path: `addons/github-config-sync/`
- Add-on web app: `addons/github-config-sync/rootfs/app/`
- Version sync script: `scripts/sync_versions.py`

---

## Milestone Roadmap

## v0.1.0 — Foundation

- [x] Custom integration scaffold in `custom_components/github_config_sync`
- [x] Config flow + token handling foundations
- [x] HACS metadata and validation workflow
- [x] GitHub release/tag pipeline established

## v0.1.1 — Compliance Fixes

- [x] Config flow schema/runtime stability fixes
- [x] OAuth/device-flow parsing corrections
- [x] Home Assistant-compatible auth flow iteration
- [x] Dev release line advanced through `v0.0.18-dev`

## v0.1.2 — Sync Engine Hardening (IN PROGRESS)

- [x] Add-on scaffold with ingress UI (`addons/github-config-sync`)
- [x] Add-on repository metadata (`repository.yaml`)
- [x] Add-on API endpoints (`/api/health`, `/api/options`, `/api/status`, `/api/sync`)
- [x] Hash-based changed-file detection (added/changed/removed)
- [x] Real GitHub upsert/delete sync path integrated in runtime endpoint
- [x] Structured sync module boundaries (`github_client`, `sync_engine`, models, errors)
- [x] Tests for hash diff + sync planning + API happy path/error path
- [ ] End-to-end dry-run and live-run verification notes in docs

## v0.1.3 — Security + Auth

- [ ] Token never persisted/logged in plaintext beyond required runtime paths
- [ ] OAuth path hardened with clear fallback/error handling
- [ ] Startup scope checks and actionable auth diagnostics
- [ ] Security notes in docs (`SECURITY.md` or equivalent section)

## v0.1.4 — Integration ↔ Add-on Contract

- [ ] Define stable local API contract between integration and add-on
- [ ] Expose add-on health/sync status in HA entities
- [ ] Diagnostics export bundle (config + status + sanitized logs)

## v0.1.5 — Quality Gate

- [ ] Unit tests for sync engine + API + config validation
- [ ] CI includes integration checks + add-on checks + tests
- [ ] Release checklist enforced for each tag
- [ ] Migration notes template for every milestone release

---

## Active Sprint Tracker (Now)

## In Progress

- [ ] Add end-to-end dry-run and live-run verification notes in docs (close `v0.1.2`)
- [ ] Add runbook section for add-on auth/repo-picker workflow and common recovery steps
- [ ] Validate HACS metadata requirements tied to GitHub repo settings (description/topics/brands)

## Next Up

- [ ] Complete `v0.1.2` and publish next stable/dev release as needed
- [ ] Start `v0.1.3` auth/security hardening

## Blockers / Decisions Needed

- [ ] Decide whether add-on sync should use **GitHub Contents API only** or support **git-native engine** later
- [ ] Decide minimum supported Home Assistant version for add-on/integration pairing policy

---

## Release Checklist (Per Tag)

- [ ] Version bumped (integration/add-on as applicable)
- [ ] Run `python3 scripts/sync_versions.py ...` for stable/dev channel
- [ ] Validation/CI green
- [ ] Docs updated (features + migration notes)
- [ ] Tag created and pushed
- [ ] GitHub Release created (pre-release or stable)
- [ ] Tracker updated in this file
