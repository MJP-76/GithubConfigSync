DOMAIN = "github_config_sync"

CONF_GITHUB_CLIENT_ID = "github_client_id"
CONF_GITHUB_TOKEN = "github_token"
CONF_REPOSITORY = "repository"
CONF_BACKUP_INTERVAL_HOURS = "backup_interval_hours"
CONF_SYNC_START_TIME = "sync_start_time"
CONF_IGNORE_PATTERNS = "ignore_patterns"
CONF_EXTRA_IGNORE_PATTERNS = "extra_ignore_patterns"

DEFAULT_BACKUP_INTERVAL_HOURS = 24
DEFAULT_SYNC_START_TIME = "03:00"
DEFAULT_REMOTE_PATH = "."
# Optional fixed OAuth app client ID for GitHub Device Flow.
# Leave empty to prompt for client ID in the config flow.
GITHUB_OAUTH_CLIENT_ID = ""
DEFAULT_IGNORE_PATTERNS = [
    "home-assistant_v2.db",
    "home-assistant.log",
    "home-assistant.log.*",
    "*.log",
    "*.log.*",
    ".storage/",
    ".cloud/",
    "tts/",
    "automations.yaml",
    "scripts.yaml",
    "scenes.yaml",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "*.tmp",
    "*.swp",
]
