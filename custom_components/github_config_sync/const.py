DOMAIN = "github_config_sync"

CONF_GITHUB_TOKEN = "github_token"
CONF_REPOSITORY = "repository"
CONF_BACKUP_INTERVAL_MINUTES = "backup_interval_minutes"
CONF_LOCAL_FOLDER = "local_folder"
CONF_REMOTE_PATH = "remote_path"
CONF_IGNORE_PATTERNS = "ignore_patterns"

DEFAULT_BACKUP_INTERVAL_MINUTES = 60
DEFAULT_REMOTE_PATH = "."
DEFAULT_IGNORE_PATTERNS = [
    "home-assistant_v2.db",
    "home-assistant.log",
    "home-assistant.log.*",
    "*.log",
    "*.log.*",
]
