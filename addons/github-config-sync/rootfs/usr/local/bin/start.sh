#!/usr/bin/with-contenv bashio
set -euo pipefail

bashio::log.info "Starting Github Config Sync app service"
exec python3 /app/github_sync_app/server.py
