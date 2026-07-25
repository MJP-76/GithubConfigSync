"""Constants for Cross Battery Charge Guard."""

DOMAIN = "cross_battery_charge_guard"
PLATFORMS: list[str] = ["sensor"]
CONF_CREATE_DASHBOARD = "create_dashboard"
CONF_DASHBOARD_TITLE = "dashboard_title"
CONF_DASHBOARD_URL_PATH = "dashboard_url_path"
CONF_BATTERY_A_NAME = "battery_a_name"
CONF_BATTERY_A_SOC = "battery_a_soc"
CONF_BATTERY_A_POWER = "battery_a_power"
CONF_BATTERY_A_CURRENT_LIMIT = "battery_a_current_limit"
CONF_BATTERY_A_HOUSE_LOAD = "battery_a_house_load"
CONF_BATTERY_B_NAME = "battery_b_name"
CONF_BATTERY_B_SOC = "battery_b_soc"
CONF_BATTERY_B_POWER = "battery_b_power"
CONF_BATTERY_B_CURRENT_LIMIT = "battery_b_current_limit"
CONF_BATTERY_B_HOUSE_LOAD = "battery_b_house_load"
DEFAULT_RESERVE_SOC = 10.0
DEFAULT_DEADBAND = 0.2
DEFAULT_MAX_CROSS_CHARGE_WATTS = 100.0
DEFAULT_MAX_SOC_DIFFERENCE = 30.0
DEFAULT_LOOP_DURATION = 300
DEFAULT_MAX_BATTERY_TEMP = 50.0
DEFAULT_CREATE_DASHBOARD = True
DEFAULT_DASHBOARD_TITLE = "Cross Battery Charge Guard"
DEFAULT_DASHBOARD_URL_PATH = "crossbatterychargeguard"
