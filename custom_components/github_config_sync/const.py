DOMAIN = "github_config_sync"

CONF_GITHUB_TOKEN = "github_token"
CONF_REPOSITORY = "repository"
CONF_BACKUP_INTERVAL_MINUTES = "backup_interval_minutes"
CONF_IGNORE_PATTERNS = "ignore_patterns"
CONF_EXTRA_IGNORE_PATTERNS = "extra_ignore_patterns"

DEFAULT_BACKUP_INTERVAL_MINUTES = 60
DEFAULT_REMOTE_PATH = "."
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
