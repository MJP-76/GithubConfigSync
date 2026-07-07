# Security Notes

## Authentication and token handling

- GitHub tokens are required for repository access and device-flow completion.
- The web UI masks stored tokens in API responses.
- Do not log tokens in plaintext.
- Prefer a private repository when syncing Home Assistant config data.

## Authorization diagnostics

- If repository probing fails with an auth error, confirm the token has `repo` access.
- If probing fails with a not-found error, confirm the repository name, visibility, and account access.
- If device-flow login fails, restart authorization from the add-on UI and complete the browser step again.

## Operational guidance

- Keep `dry_run` enabled until the repository, token, and sync plan look correct.
- Review the add-on status panel and logs before enabling live syncs.
