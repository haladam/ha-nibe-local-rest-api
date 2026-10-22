DOMAIN = "nibe_local_api"
CONF_HTTPS = "https"
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_PORT = 8443
DEFAULT_SCAN_INTERVAL = 30

# Optional fast polling: a few chosen points are re-read with one small request each
# between the regular full-table updates.
CONF_FAST_POINTS = "fast_points"
CONF_FAST_INTERVAL = "fast_interval"
DEFAULT_FAST_INTERVAL = 10
MIN_FAST_INTERVAL = 5
MAX_FAST_INTERVAL = 300
MAX_FAST_POINTS = 10
FAST_POLL_TIMEOUT = 30  # seconds for one whole fast round

# "Sensor not connected" markers by variable size
SENTINELS = {"s16": -32768, "u16": 65535, "s32": -2147483648, "u32": 4294967295}

# Known firmware quirks: point_id -> corrected divisor
# 29258: PV power divisor (also overridden by the whatsinabyte bridge).
# 259: register export says factor 100 but the value (raw 90) is the 90 Hz limit.
DIVISOR_OVERRIDES = {29258: 100, 259: 1}
# point_id -> factor applied to the raw value (shown value = raw x factor; writes
# divide by it). 14314: PV surplus power sent to the heat pump over Modbus TCP. The
# register holds units of 10 W (the owner's Home Assistant automation writes W / 10).
# Each entity exposes raw_value and divisor attributes to verify this.
MULTIPLIERS = {14314: 10}
# point_id -> (min_raw or None, max_raw or None).
# 3702: firmware minimum is 10x too low (installer manual: 55-70 C).
# 4564 "More hot water": the firmware reports no range (min = max = 0); s8 limits used.
RANGE_OVERRIDES = {3702: (550, None), 4564: (0, 127)}

# Internal electric heater: point 1760 counts active steps of 0.5 kW each (confirmed
# by the owner; the Modbus manual calls register 1029 "Add. heat steps"). The maximum
# number of steps follows the "Max. internal additional heat" setting (point 3823, kW).
# "Version (EB100)": raw = major x 256 + minor (1037 = 4.13, 1038 = 4.14, confirmed on
# software 4.13.12 and 4.14.6). The patch level is not reported over REST.
VERSION_POINT = 2509
ALARM_NUMBER_POINT = 3375  # 0 means no alarm
HEATER_STEPS_POINT = 1760
HEATER_MAX_POINT = 3823
HEATER_STEP_KW = 0.5

# Derived "running" sensors: key -> (speed point, name)
PUMP_POINTS = {
    "gp1": (1975, "Heating medium pump running (GP1)"),
    "gp2": (1977, "Brine pump running (GP2)"),
}
