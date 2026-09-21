# Changelog

The full 71-release history lives in
[CHANGELOG.md](https://github.com/MJP-76/GithubConfigSync/blob/main/CHANGELOG.md)
(and on
[GitHub Releases](https://github.com/MJP-76/GithubConfigSync/releases)).
The last 5 releases are kept at the top, per the project's changelog rules.

## Unreleased

- **Fix**: Sync no longer fails with "Path escapes allowed sync roots" when the
  `www` mount point is excluded — `www` files are resolved from the config root
  instead of the container's `/www` path (regression from the mount-point
  controls)
- **Fix**: `.gitignore` patterns in the config root are now honored during
  scanning, so UI-managed defaults (e.g. HACS `www/community/`) are excluded
- **Fix**: Removed the vestigial `sync_interval_minutes` option — scheduled
  sync still uses day-of-week + time selection
- **Fix**: Options pushed to Supervisor are filtered to the add-on schema,
  fixing `Failed to sync options to Supervisor: HTTP Error 400`
- **Fix**: Scheduled-sync timer can no longer double-schedule when settings are
  saved while a poll is in flight
- **Chore**: `include_www` now defaults consistently to off across the schema,
  UI and engine

## 1.6.0

- **Feature**: Reset to Defaults button for ignore patterns in web UI
- **Fix**: Reset to Defaults button was missing its event handler (Uncaught TypeError)
- **Fix**: Add-on rebuild via Supervisor API now works correctly

## 1.5.22

- **Fix**: "Token missing" badge no longer appears when the token is actually
  fine — transient GitHub check failures now show as an amber "Token check
  failed" badge instead of a red "Token missing"
- **Fix**: One slow/timed-out GitHub call no longer poisons the token badge —
  transient `error` health results cache for 30s (stable states keep 5m)
- **Fix**: Device Flow completion no longer reports "request timed out"
  mid-authorization — UI waits up to 130s (server polls GitHub up to 120s)
- **Fix**: Live token health check uses a bounded 20s GitHub call with a 30s
  client timeout
- **Fix**: `_save_state()` is now lock-serialized so concurrent status
  polls/sync writes can no longer drop the token-health cache entry

## 1.5.21

- **Fix**: Options now persist across restarts — Supervisor sync POSTs to
  `/addons/self/options` (works for any `hassio_role`)
- **Fix**: `hassio_api: true` added so `SUPERVISOR_TOKEN` is injected into the
  container (without it, the Supervisor sync silently skipped and the token was
  lost on reboot)
- **Fix**: Settings save can never overwrite the real token with the `********`
  mask placeholder

## 1.5.20

- **Fix**: `/api/status` is now fully cached — no live GitHub call on the 2s
  status poll
- **Fix**: Added dedicated public `/api/token/health` endpoint for the live
  GitHub token check, called on a 60s throttle
- **Fix**: `fetchJson` aborts hung requests after 10s

## 1.5.19

- **Fix**: `_via_ingress_proxy()` checks `X-Hass-Source: core.ingress` +
  private IP first, with Supervisor IP fallback (works regardless of Docker
  networking changes)
- **Fix**: Version fetches from `/api/health` before auth, so it shows instantly
- **Fix**: IPv6 support in `_is_private_ip()` (ULA, link-local, loopback)