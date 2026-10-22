"""Point catalog: friendly names, units, enum labels and default visibility.

Pure Python (no Home Assistant imports) so it can be unit-tested on its own.
Sources: NIBE's MODBUS S-SERIES manual and S1155PC installer manual, the register
library, the firmware's own point descriptions, and the whatsinabyte/nibe-smo-mqtt-bridge
project (menu structure, value mappings, unit/entity-type overrides), loaded from
data.json. Unknown values fall back to the raw number.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .api import (
    bounds, clean_title, divisor, firmware_description, flag_mismatch, is_live,
    is_writable, raw_value, reported_bounds, scale_factor, unit_of,
)
from .const import HEATER_STEPS_POINT


def load_data(path: str) -> dict:
    """Read data.json (call from an executor thread)."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@dataclass
class PointInfo:
    point_id: int
    title: str
    name: str
    kind: str  # sensor | binary_sensor | number | switch | select | button | time | skip
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    category: str | None = None  # None | diagnostic | config
    enabled: bool = False
    live: bool = False
    integer: bool = True
    description: str = ""
    fw_description: str = ""
    options: dict[int, str] | None = None
    reason: str = ""
    menu_path: str = ""
    menu_range: str = ""
    menu_note: str = ""
    menu_warning: str = ""
    mapping_status: str = ""
    min_raw: int = 0  # raw range a setting accepts (see api.bounds)
    max_raw: int = 0
    range_note: str = ""


UNITS = {
    "°C": ("°C", "temperature"),
    "kW": ("kW", "power"),
    "W": ("W", "power"),
    "kWh": ("kWh", "energy"),
    "Hz": ("Hz", "frequency"),
    "A": ("A", "current"),
    "mA": ("mA", "current"),
    "bar": ("bar", "pressure"),
    "h": ("h", "duration"),
    "min": ("min", "duration"),
    "s": ("s", "duration"),
    "days": ("d", "duration"),
    "d": ("d", "duration"),
    "l/min": ("L/min", "volume_flow_rate"),
    "rpm": ("rpm", None),
    "%": ("%", None),
    "DM": ("DM", None),
}

PRIORITY = {10: "Off", 20: "Hot water", 30: "Heating", 40: "Pool", 60: "Cooling"}
HW_DEMAND = {0: "Small", 1: "Medium", 2: "Large", 4: "Smart control"}
OP_MODE = {0: "Auto", 1: "Manual", 2: "Additional heat only"}
BRINE_MODE = {10: "Intermittent", 20: "Continuous", 30: "10 days continuous"}
HM_PUMP_SETTING = {10: "Intermittent", 40: "Auto"}
SHUNT = {10: "Off", 20: "Opening", 30: "Closing"}
COMPRESSOR_STATE = {20: "Stopped", 40: "Starting", 60: "Running", 100: "Stopping"}

# Own enum tables, used only when neither the bridge project nor the firmware's own
# point description provides labels.
ENUMS = {
    1758: PRIORITY,
    3697: HW_DEMAND,
    3751: OP_MODE,
    3753: BRINE_MODE,
    3752: HM_PUMP_SETTING,
    2556: COMPRESSOR_STATE,
    1965: COMPRESSOR_STATE,
}
SHUNT_RE = re.compile(r"oper(ating|\.)? ?\.? ?mode,? shunt", re.I)
# Firmware reports a degenerate range for these on/off points, so range detection fails.
# 3930 (high brine in alarm active) is a safety setting and stays disabled by default.
SWITCH_IDS = {3754, 8982, 12392, 12393, 3930}
BUTTON_IDS = {3478}
# Never expose as writable (spot prices etc.)
READ_ONLY_IDS = {55749, 55884} | set(range(26817, 26841))
# Writable, but only some values are verified: created disabled.
# 4564 "More hot water": writing 2 over REST starts a one-time increase (confirmed on an S1155: the pump then
# sets 4030 to 120 and counts it down). 4030 itself is read-only over REST (HTTP 400), so it stays a sensor.
EXPERIMENTAL_IDS = {4564}
# Read-only diagnostics that are still worth having enabled out of the box.
# 1942: "More hot water status" (menu 2.1), 1 while a temporary increase is running.
# 2509: software version (menu 3.1.15), decoded by the sensor.
ENABLED_DIAGNOSTICS = {1942, 2509}
NO_EFFECT_RE = re.compile(r"has no effect|no effect", re.I)
# Counters that are not time-based: point_id -> unit label
STEP_POINTS = {HEATER_STEPS_POINT: "steps"}

# "<number> = <label>" pairs. A pair starts at the beginning of the text or after a
# separator; its label runs up to the next pair or separator, so labels that contain a
# comma ("1 = Heating, cooling") stay whole.
_FWD = re.compile(
    r"(?:^|[,;\n])\s*(-?\d+)\s*[=:]\s*(.*?)(?=[,;\n]\s*-?\d+\s*[=:]|[;\n]|$)", re.S
)
# "<label> = <number>" (for example "Auto = 0, Manual = 1"). Only "=" is accepted:
# "Offset: 5, Limit: 10" is a list of settings, not an enumeration.
_REV = re.compile(r"^\s*(.+?)\s*=\s*(-?\d+)\s*$")
_REV_NOT_LABELS = {
    "min", "minimum", "max", "maximum", "default", "offset", "limit", "range", "step",
    "factor", "value", "from", "to",
}
_HAS_LETTER = re.compile(r"[^\W\d_]")


def _cap(label: str) -> str:
    return label[:1].upper() + label[1:] if label else label


def parse_description_mapping(text: str | None) -> dict[int, str]:
    """Parse '0 = Off, 1 = Active', '0: Zones, 1: Profile' or 'Auto = 0, Manual = 1'.

    Returns {} unless the whole text reads as an enumeration: at least two entries,
    unique values, and labels that contain letters.
    """
    if not text:
        return {}
    out: dict[int, str] = {}
    duplicate = False
    for m in _FWD.finditer(text):
        label = m.group(2).strip()
        if len(label) > 40:  # trailing prose after the label: keep the first clause
            label = re.split(r"[,.]\s", label, maxsplit=1)[0]
        label = label.rstrip(".").strip()
        if not label or len(label) > 40 or not _HAS_LETTER.search(label):
            continue
        key = int(m.group(1))
        duplicate = duplicate or key in out
        out[key] = _cap(label)
    if len(out) >= 2 and not duplicate:
        return out

    segments = [s for s in re.split(r"[,;\n]", text) if s.strip()]
    out = {}
    for segment in segments:
        m = _REV.match(segment)
        if not m:
            return {}  # every segment must be a pair, or this is not an enumeration
        label = m.group(1).strip()
        key = int(m.group(2))
        if label.lower().rstrip(".") in _REV_NOT_LABELS or not _HAS_LETTER.search(label) or key in out:
            return {}
        out[key] = _cap(label)
    return out if len(out) >= 2 else {}


CURATED = {
    4: ("Outdoor temperature (BT1)", "Current outdoor temperature."),
    54: ("Outdoor temperature, average (BT1)", "Filtered outdoor temperature used by auto mode."),
    8: ("Supply temperature (BT2)", "Heating medium temperature leaving the heat pump."),
    10: ("Return temperature (BT3)", "Heating medium temperature returning to the heat pump."),
    11: ("Hot water top (BT7)", "Temperature at the top of the hot water cylinder."),
    12: ("Hot water charging (BT6)", "Hot water charging sensor, controls hot water production."),
    13: ("Brine in (BT10)", "Brine temperature entering the heat pump from the ground loop."),
    14: ("Brine out (BT11)", "Brine temperature leaving the heat pump to the ground loop."),
    15: ("Condenser outlet (BT12)", "Condenser supply line temperature."),
    16: ("Discharge / hot gas (BT14)", "Compressor discharge temperature."),
    17: ("Liquid line (BT15)", "Refrigerant liquid line temperature."),
    19: ("Suction gas (BT17)", "Refrigerant suction gas temperature."),
    58: ("Flow sensor (BF1)", "Heating medium flow."),
    781: ("Degree minutes", "Heating demand integrator. Compressor starts at the start value, additional heat at the add-heat value."),
    1704: ("Degree minutes limit", "Limit value for degree minutes."),
    2691: ("Cooling degree minutes", "Cooling demand integrator."),
    1708: ("Calculated supply temperature, climate system 1", "Target supply temperature from the heating curve."),
    2695: ("Calculated cooling supply temperature, climate system 1", "Target supply temperature for cooling."),
    1758: ("Operating priority", "What the heat pump is currently producing."),
    1799: ("Compressor frequency", "Current compressor frequency."),
    1831: ("Compressor frequency (alt.)", "Duplicate of the current compressor frequency."),
    258: ("Requested compressor frequency", "Frequency requested by the control system."),
    1788: ("Compressor minimum frequency", ""),
    1789: ("Compressor maximum frequency", ""),
    1800: ("Inverter temperature", ""),
    1801: ("Compressor power input", "Electrical power drawn by the compressor."),
    1932: ("Compressor power input, average", ""),
    1806: ("Compressor current", ""),
    1961: ("Compressor total run time", ""),
    1963: ("Compressor run time, hot water", ""),
    1959: ("Compressor starts", "Number of compressor starts (matches the official NIBE integration's counter)."),
    1755: ("Additional heat total run time", ""),
    1865: ("Additional heat run time, hot water", ""),
    1756: ("Internal additional heat power", "Firmware value; see also the calculated power from the step count."),
    1760: ("Internal additional heat, steps", "Active steps of the internal electric heater (the Modbus manual calls register 1029 'Add. heat steps'), 0.5 kW per step. The highest possible step follows the 'Max. internal additional heat' setting (for example 6.5 kW = 13 steps)."),
    1975: ("Heating medium pump speed (GP1)", ""),
    1977: ("Brine pump speed (GP2)", ""),
    1969: ("Heating medium pump operating mode (current)", "Firmware labels: Off, Starting, On, 10-day mode, Calibration."),
    1971: ("Brine pump operating mode (current)", "Firmware labels: Off, Starting, On, 10-day mode, Calibration."),
    2556: ("Compressor state", ""),
    1965: ("Compressor operating state", ""),
    3375: ("Alarm number", "0 means no alarm."),
    2509: ("Software version", "Version of the heat pump software, for example 4.14 (menu 3.1.15). The register holds major x 256 + minor, so the patch level (the 6 in 4.14.6) is not available over REST. The raw_value attribute shows the register."),
    4030: ("More hot water, minutes remaining", "Remaining time of the temporary hot water increase, counted down by the pump one minute at a time. Read-only over REST (the pump refuses writes to it); start an increase with More hot water instead."),
    4064: ("Operating mode (readback)", "Read-only mirror of the operating mode setting (Auto, Manual, Add. heat)."),
    4564: ("More hot water", "Temporary hot water increase. Write 2 to start a one-time increase: the pump then counts 120 minutes down in More hot water, minutes remaining. 0 is Off. The firmware reports no value range and the other values are not verified (menu 2.1 offers 3, 6 and 12 hours, Off and One-time increase). Created disabled; enable it to use it."),
    6139: ("Solar PV total energy", "Energy reported by the EME PV accessory."),
    6002: ("Solar PV current power", ""),
    6138: ("Solar PV total average power", ""),
    3667: ("Heating curve, climate system 1", "Heating curve slope (0-15). Curve 0 means the own curve is used."),
    3671: ("Heating offset, climate system 1", "Parallel shift of the heating curve (-10..10)."),
    3675: ("Minimum supply temperature, climate system 1", ""),
    3679: ("Maximum supply temperature, climate system 1", ""),
    3692: ("External adjustment, climate system 1", ""),
    3696: ("External adjustment with room sensor, climate system 1", ""),
    3697: ("Hot water demand", "Small / Medium / Large / Smart control."),
    3699: ("Hot water start temperature, high", ""),
    3700: ("Hot water start temperature, normal", ""),
    3701: ("Hot water start temperature, low", ""),
    3702: ("Hot water stop temperature, periodic increase", "Firmware minimum is corrected to 55 C."),
    3703: ("Hot water stop temperature, high", ""),
    3704: ("Hot water stop temperature, normal", ""),
    3705: ("Hot water stop temperature, low", ""),
    3706: ("Periodic hot water increase", "Legionella protection increase."),
    3707: ("Periodic hot water interval", ""),
    3708: ("Periodic hot water start time", "Time of day when the periodic increase starts (menu 2.4)."),
    3709: ("Hot water circulation", ""),
    3751: ("Operating mode", "Auto, Manual or Additional heat only."),
    3752: ("Heating medium pump operating mode", "Auto or Intermittent."),
    3753: ("Brine pump operating mode", ""),
    3818: ("Degree minutes: start compressor", "Compressor starts when degree minutes fall below this value."),
    3821: ("Degree minutes between additional heat steps", ""),
    3823: ("Maximum internal additional heat", "Upper limit for the internal electric heater; 0.5 kW per step."),
    3825: ("Fuse size", ""),
    3919: ("Permit additional heat, heating", ""),
    3920: ("Permit heating", ""),
    3921: ("Permit cooling", ""),
    3923: ("Auto mode: heating stop temperature", ""),
    3924: ("Auto mode: additional heat stop temperature", ""),
    3941: ("Use room sensor, climate system 1", ""),
    3949: ("Room sensor factor, climate system 1", ""),
    4527: ("Degree minutes: start additional heat (relative)", "Additional heat starts this many degree minutes below the compressor start value."),
    5025: ("Cooling curve, climate system 1", ""),
    5033: ("Cooling offset, climate system 1", ""),
    10613: ("Activate SG Ready via API", ""),
    3172: ("Requested compressor frequency (alt. source)", ""),
    32341: ("Desired room temperature, zone 1", "Room temperature setpoint for zone 1."),
    22130: ("Electrical power, current", "Instantaneous electrical power used (compressor and additional heat)."),
    27378: ("Heat produced, heating (compressor only)", "Flow-measured heat output, lifetime counter, suitable for the Energy dashboard."),
    27379: ("Heat produced, hot water (compressor only)", "Flow-measured heat output, lifetime counter."),
    27382: ("Heat produced, heating (incl. additional heat)", "Flow-measured heat output, lifetime counter."),
    27383: ("Heat produced, hot water (incl. additional heat)", "Flow-measured heat output, lifetime counter."),
    28392: ("Total heat produced", "Lifetime heat output."),
    28393: ("Total electricity consumption (estimated)", "Lifetime electrical energy estimate."),
    15753: ("Passive cooling energy", "Lifetime counter."),
    14314: ("Modbus TCP/IP Ext. Available power (Solar PV)", "PV surplus power sent to the heat pump over Modbus TCP, shown in W. The register holds units of 10 W, so the value is shown and written x10 (see the raw_value attribute). Normally written by a Home Assistant automation: write real watts to this entity and it sends value / 10; do not write the same register from two integrations. The heat pump only uses it while 'Modbus TCP/IP external Solar PV activated' is on (menu 7.5.12)."),
    14312: ("Modbus TCP/IP external Solar PV activated", "Switches on the PV surplus function (menu 7.5.12). Needed before the heat pump uses the value of 'Ext. Available power (Solar PV)'."),
    14313: ("Modbus TCP/IP PV inverter: Include own consumption", "When on, the heat pump subtracts its own consumption from the PV power it is given (menu 7.5.12). Leave off if the value you send is already the surplus."),
    22070: ("AUX via Modbus: function ID", "Use the nibe_local_api.set_aux service instead of writing this directly."),
    24483: ("External calculated supply: use Modbus value", "When on, the heat pump uses the supply setpoints below instead of its own heating curve."),
    24484: ("External calculated supply setpoint, heating, system 1", "Used only when 'use Modbus value' is on."),
    24492: ("External calculated supply setpoint, cooling, system 1", "Used only when 'use Modbus value' is on."),
    3680: ("Own curve, heating P7", "Supply temperature at the warmest outdoor point. Only used when the heating curve is 0."),
    3681: ("Own curve, heating P6", "Only used when the heating curve is 0."),
    3682: ("Own curve, heating P5", "Only used when the heating curve is 0."),
    3683: ("Own curve, heating P4", "Only used when the heating curve is 0."),
    3684: ("Own curve, heating P3", "Only used when the heating curve is 0."),
    3685: ("Own curve, heating P2", "Only used when the heating curve is 0."),
    3686: ("Own curve, heating P1", "Supply temperature at the coldest outdoor point. Only used when the heating curve is 0."),
    3748: ("Operating prioritisation time, hot water", "Likely menu 7.1.10.1: minutes spent on hot water when several demands exist (0-180)."),
    3749: ("Operating prioritisation time, heating", "Likely menu 7.1.10.1: minutes spent on heating when several demands exist (0-180)."),
    55084: ("Emergency mode: immersion heater output", "Menu 7.1.8.2."),
    3292: ("Smart Price Adaption: status", "Read-only status of Smart Price Adaption."),
    3754: ("Forced control", "Activates menu 7.5.3 forced control. For troubleshooting only."),
    3930: ("High brine in alarm active", "Safety setting, created disabled. The firmware reports a fixed range of 1."),
    8982: ("Away mode status", ""),
    3478: ("Reset alarm (point)", "Prefer the 'Reset alarms' button."),
    5482: ("Brine pump speed mode", "Labels are partially confirmed: 0 manual, 1 auto, 2 fixed delta. The Modbus manual lists register 1319 as 0 auto, 1 manual, so check before writing."),
}
USER_FACING = {
    3667, 3671, 3675, 3679, 3692, 3696, 3697, 3699, 3700, 3701, 3702, 3703,
    3704, 3705, 3706, 3707, 3708, 3709, 3751, 3919, 3920, 3921, 3923, 3924, 3941,
    3949, 5025, 5033, 10613, 32341, 14312, 14313, 14314, 3823,
    3680, 3681, 3682, 3683, 3684, 3685, 3686,
}

BINARY = {
    1973: ("Compressor running", "running"),
    2859: ("Compressor running (EP14)", "running"),
    2002: ("Reversing valve (QN10): hot water", None),
    1829: ("Hot water circulation pump (GP11)", "running"),
    1709: ("Class 1 alarm", "problem"),
    3126: ("Defrosting (EB100-EP14)", None),
    1820: ("External blocking", None),
}
COUNTERS = {1959, 2561}
DUPLICATE_OF = {
    2547: 10, 2548: 13, 2549: 14, 2550: 15, 2551: 16, 2552: 17, 2553: 19,
    2855: 12, 2856: 11, 2857: 8, 2559: 1975, 2560: 1977, 2562: 1961,
    2563: 1963, 2561: 1959, 1831: 1799, 3153: 3375, 3154: 3375, 25165: 22130,
    55000: 1758,
}
NOISE_IDS = {3171, 3172, 29291, 25166, 259, 3122, 3123, 3129, 3258, 3478} | set(range(26817, 26841))

UNUSED_RE = re.compile(
    r"EB10[1-8]|EP15|heat pump [1-8]\b|^heat pump [1-8] requested|"
    r"climate systems? [2-8]\b|\bFLM\b|\bERS\b|\bAZ\d\d|\bSAM\b|\bpool\b|EQ1|"
    r"\bACS\b|\(RMU\)|\bHTS\b|wood boiler|charge pump [2-8]|collector|EP10|"
    r"\bCL12\b|^fan mode|zone (?:[2-9]|[1-4]\d)\b|\bECS[1-8]?\b|input on ECS|"
    r"filter replacement|return time fan|set point (heating|cooling) [2-8]|"
    r"^min\. vent|^blocking actions|^ers |"
    r"\(EP4[4-7]|\(EP2[1-3]\)|clim\. system [2-8]", re.I)
NOISE_RE = re.compile(
    r"unprocessed|version|wizard|bit register|test guide|^current status$|"
    r"^functionality|^permit|hw (type|version)|inverter (pic|8051|alarm|fault|run|limit|min|max)|"
    r"initiate inverter|force initiated|eev-|evi pressure|fan (speed|rpm|status)|"
    r"^compressor, requested|prot\. status|seconds of blank|available compressors|"
    r"docked compressors|used compressors|blocked compressors|compressor restrictions|"
    r"^heat pump functionality|relay status|external guide|is the compressor|"
    r"more hot water status|eme lux|temp\. lux|smart energy source|^blocked$|"
    r"external reading of|energy storage|^status$|block new compressor|all sub units|"
    r"^reset alarm|non module-specific|^frost protection status|"
    r"^oper\. mode$|auxiliary operation|^priority$", re.I)
PRESSURE_SENSOR_RE = re.compile(r"\bBP[48]\b|low press|high press|pressure sensor", re.IGNORECASE)
ADVANCED_RE = re.compile(
    r"accessor|^climate system \d$|^installed \(|^eme20$|^ers \d|^hts \d|^flm \d|^acs$|"
    r"\(rmu\)|phase order|^fuse$|current transformer|^language$|^time format$|"
    r"audio signal|sound when|start guide|changes have been made|blockfreq|"
    r"mode, energy meter|^input aux|^output aux|smart energy source|own curve|"
    r"floor drying|\bflm\b|^eb10\d|^k4 relay|^activate forced control|"
    r"^step controlled|^shunted brine|^period$|^number of years|^months$|"
    r"^active days|^start time|^stop time|^factor$|^show (outdoor|indoor)|"
    r"\bSES\b|production \(pv power\)|\(spa\)|^heating \(sg ready\)|^ground water pump|"
    r"^blocking actions|^cooling with room sensors|^preset flow|"
    r"^external adjustment climate system [2-8]|^ers|\bsam\b|phase|^ext\.|"
    r"external reading of|modbus|^aux from|energiepreis|^supply line set point|"
    r"freeze protection|use lp|silent mode|power limitation|^disable offset|"
    r"cooling with solar|^immersion heater power, emergency|^brine pump auto mode|"
    r"high brine in alarm active", re.I)
COUNTER_RE = re.compile(r"run time|operating time|oper\. time|op\. time|total", re.I)

ABBR = {
    "oper": "operating", "op": "operating", "temp": "temperature", "add": "additional",
    "imm": "immersion", "compr": "compressor", "ext": "external", "int": "internal",
    "outd": "outdoor", "supp": "supply", "prim": "primary", "el": "electrical",
    "clim": "climate", "diff": "difference",
}
ABBR_RE = re.compile(r"\b(" + "|".join(ABBR) + r")\.", re.I)
GLOSSARY = {
    "BT1": "outdoor sensor", "BT2": "supply line sensor", "BT3": "return line sensor",
    "BT6": "hot water charging sensor", "BT7": "hot water top sensor",
    "BT10": "brine in sensor", "BT11": "brine out sensor", "BT12": "condenser supply sensor",
    "BT14": "discharge (hot gas) sensor", "BT15": "liquid line sensor",
    "BT17": "suction gas sensor", "BT25": "external supply line sensor",
    "BT50": "room sensor", "BT64": "cooling supply sensor", "BP4": "high pressure sensor",
    "BP8": "low pressure sensor", "BF1": "flow sensor", "GP1": "heating medium pump",
    "GP2": "brine pump", "GP10": "external heating medium pump",
    "GP11": "hot water circulation pump", "QN10": "reversing valve heating/hot water",
    "EB100": "heat pump unit 1", "EP14": "compressor module 1", "EP15": "compressor module 2",
}
DES_RE = re.compile(r"\b(B[TPF]\d+|G[PQ]\d+|QN\d+|EP1[45]|EB100)\b")


def _expand(match: re.Match) -> str:
    word = ABBR[match.group(1).lower()]
    return word.capitalize() if match.group(1)[0].isupper() else word


def prettify(title: str) -> str:
    t = ABBR_RE.sub(_expand, title)
    t = re.sub(r"\bHW\b", "hot water", t)
    t = re.sub(r"^hot water", "Hot water", t)
    t = t.replace("Electrical price", "Electricity price").replace("--", "-")
    t = t.replace("Operating. ", "Operating ")
    t = re.sub(r"\s+,", ",", t)
    t = re.sub(r"\s{2,}", " ", t).strip().rstrip(".")
    return t[:1].upper() + t[1:] if t else t


def describe_designators(title: str) -> str:
    seen = []
    for code in DES_RE.findall(title):
        if code in GLOSSARY and code not in seen:
            seen.append(code)
    return "; ".join(f"{c} = {GLOSSARY[c]}" for c in seen)


def _shown(value: float) -> str:
    return f"{round(value, 6):g}"


def options_in_range(
    options: dict[int, str], mn: int, mx: int, div: int, current_raw: int | None = None
) -> dict[int, str]:
    """Drop labels whose raw value the pump would refuse to take.

    The label sources (bridge project, firmware text, own tables) sometimes list more
    values than the pump accepts: the external adjustment inputs list three modes but
    accept 0-1. Nothing is dropped when the pump reports no usable range, when fewer
    than two options would remain, or for the value the pump holds right now.
    """
    if mx <= mn:
        return options
    kept = {
        k: v for k, v in options.items()
        if mn <= k * div <= mx or k * div == current_raw
    }
    return kept if len(kept) >= 2 else options


def info_for(pid: int, point: dict, data: dict | None = None, menu_name: str | None = None) -> PointInfo:
    data = data or {}
    key = str(pid)
    meta = point.get("metadata", {}) or {}
    vtype = meta.get("variableType")
    menu = (data.get("menu") or {}).get(key)
    bridge_map = (data.get("mappings") or {}).get(key)
    pump_title = clean_title(point)
    # The rules below were written against NIBE's English titles. Firmware 4.14.6 sends
    # some titles in the display language (German here), so classification and naming
    # use the English title recorded in data.json and fall back to what the pump sends.
    title = (data.get("english_titles") or {}).get(key) or pump_title
    fw_desc = firmware_description(point)
    raw_unit = unit_of(meta)
    unit_over = data.get("unit_overrides") or {}
    if key in unit_over:
        raw_unit = unit_over[key] or None
    if raw_unit in UNITS:
        unit, dclass = UNITS[raw_unit]
    else:
        unit, dclass = (raw_unit if raw_unit and raw_unit != "°" else None), None
    if "(RH)" in title:
        dclass = "humidity"
    ro_ids = READ_ONLY_IDS | set(data.get("read_only") or [])
    etypes = data.get("entity_types") or {}
    etype = etypes.get(key)
    switch_ids = SWITCH_IDS | {int(k) for k, v in etypes.items() if v == "switch"}
    button_ids = BUTTON_IDS | {int(k) for k, v in etypes.items() if v == "button"}
    mn, mx = bounds(pid, meta, data.get("register_ranges"))
    reported_mn, reported_mx = reported_bounds(pid, meta)
    div = divisor(pid, point)
    # A holding register the firmware flags read-only and that reports no range is a
    # status display (for example "More hot water, minutes remaining"), not a setting.
    status_only = (
        flag_mismatch(meta) and mx <= mn and pid not in switch_ids and pid not in button_ids
        and vtype == "integer"
    )
    writable = is_writable(meta) and pid not in ro_ids and not status_only
    mismatch = writable and flag_mismatch(meta)
    live = is_live(pid, point)
    if live and raw_unit == "bar" and raw_value(point) == 0 and PRESSURE_SENSOR_RE.search(title):
        # A fitted refrigerant-circuit sensor never reads exactly 0 bar, not even at standstill;
        # since 4.14 the pump sends 0 (earlier: no value) for sensors this model does not have.
        live = False
    cur = CURATED.get(pid)
    bin_cfg = BINARY.get(pid)
    if bin_cfg:
        name = bin_cfg[0]
    elif cur:
        name = cur[0]
    elif menu_name:
        name = menu_name
    else:
        name = prettify(title)

    # Label precedence: bridge project > firmware's own description > own tables.
    options, from_manual, mapping_status = None, False, ""
    fw_map = parse_description_mapping(fw_desc)
    if bridge_map:
        options = {int(k): v for k, v in bridge_map["labels"].items()}
        mapping_status = bridge_map.get("status", "")
    elif fw_map:
        options = fw_map
    elif pid in ENUMS:
        options, from_manual = ENUMS[pid], True
    elif SHUNT_RE.search(title):
        options, from_manual = SHUNT, True

    if vtype == "time":
        kind = "time" if writable else "skip"
    elif vtype != "integer" or etype == "time":
        kind = "skip"
    elif writable:
        if options:
            kind = "select"
            options = options_in_range(options, mn, mx, div, raw_value(point))
        elif pid in button_ids:
            kind = "button"
        elif pid in switch_ids or (mn, mx) == (0, 1):
            kind = "switch"
        elif mx <= mn:
            kind = "skip"
        else:
            kind = "number"
    elif bin_cfg:
        kind = "binary_sensor"
        dclass = bin_cfg[1]
    elif pid == 22077:
        kind = "binary_sensor"
    else:
        kind = "sensor"
    if kind in ("select", "switch", "binary_sensor", "button", "time") or options:
        unit = None
        if kind != "binary_sensor":
            dclass = None

    total_inc = set(data.get("total_increasing") or [])
    state_class = None
    if kind == "sensor" and not options:
        if title.lower().startswith("energy log"):
            if unit == "kWh":
                dclass = None  # rolling 1 h window, not a lifetime counter
            state_class = "measurement"
        elif pid in COUNTERS:
            unit = "starts"
            state_class = "total_increasing"
        elif pid in STEP_POINTS:
            unit = STEP_POINTS[pid]
            state_class = "measurement"
        elif unit:
            if pid in total_inc or raw_unit == "kWh" or (raw_unit == "h" and COUNTER_RE.search(title)):
                state_class = "total_increasing"
            else:
                state_class = "measurement"

    unused = bool(UNUSED_RE.search(title))
    other_family = bool(menu and menu.get("family") not in (None, "water_water"))
    if other_family:
        unused = True
    dup = pid in DUPLICATE_OF
    no_effect = bool(writable and menu and NO_EFFECT_RE.search(menu.get("note", "")))
    reason = "live" if live else "no value (sensor/accessory not present)"
    if writable:
        advanced = bool(ADVANCED_RE.search(title)) and pid not in USER_FACING
        category = None if pid in USER_FACING else "config"
        enabled = live and not unused and not advanced
        if live and unused:
            reason = "other heat pump family" if other_family else "likely unused hardware"
        elif live and advanced:
            reason = "advanced installer setting"
        if mismatch:
            enabled, category = False, "config"
            reason = "writable per register type (firmware flag says read-only)"
        if no_effect:
            enabled, category = False, "config"
            reason = "no effect on current firmware (menu notes)"
        if pid in button_ids or pid in SWITCH_IDS:
            enabled = False
        if pid in EXPERIMENTAL_IDS:
            enabled, category = False, "config"
            reason = "firmware reports no range; meaning of values unverified"
    else:
        forced = pid in NOISE_IDS
        noise = (bool(NOISE_RE.search(title)) or dup or forced) and not bin_cfg
        if (cur and not dup and not forced) or bin_cfg:
            noise = False
            unused = False
        category = "diagnostic" if (noise or pid in ENABLED_DIAGNOSTICS) else None
        enabled = live and not unused and not noise
        if live and unused:
            reason = "other heat pump family" if other_family else "likely unused hardware"
        elif live and dup:
            reason = f"duplicate of point {DUPLICATE_OF[pid]}"
        elif live and noise:
            reason = "diagnostic/internal value"
    if pid in ENABLED_DIAGNOSTICS and live and kind != "skip":
        enabled = True
        reason = "diagnostic, enabled for troubleshooting"
    if kind == "skip":
        enabled = False
        reason = "unsupported type or no usable range"

    range_note = ""
    if kind == "number" and (mn, mx) != (reported_mn, reported_mx):
        factor = scale_factor(pid, point)
        suffix = f" {unit}" if unit else ""
        range_note = (
            f"Range limited to {_shown(mn * factor)}-{_shown(mx * factor)}{suffix} using "
            f"NIBE's register list; the pump reports "
            f"{_shown(reported_mn * factor)}-{_shown(reported_mx * factor)}{suffix}."
        )

    menu_text = f"Menu {menu['path']}." if menu else ""
    status_text = f"Value labels are {mapping_status}." if mapping_status and mapping_status != "confirmed" else ""
    desc = " ".join(
        p for p in (cur[1] if cur else "", menu_text, status_text, range_note,
                    describe_designators(title)) if p
    )
    return PointInfo(
        point_id=pid, title=pump_title, name=name, kind=kind, unit=unit, device_class=dclass,
        state_class=state_class, category=category, enabled=enabled, live=live,
        integer=(div == 1), description=desc, fw_description=fw_desc,
        options=options or None, reason=reason,
        menu_path=(menu or {}).get("path", ""), menu_range=(menu or {}).get("range", ""),
        menu_note=(menu or {}).get("note", ""), menu_warning=(menu or {}).get("warn", ""),
        mapping_status=mapping_status, min_raw=mn, max_raw=mx, range_note=range_note,
    )


def build_infos(points: dict[int, dict], data: dict | None = None) -> dict[int, PointInfo]:
    data = data or {}
    menu = data.get("menu") or {}

    def candidate(pid: int) -> str | None:
        m = menu.get(str(pid))
        if not m:
            return None
        label = m["label"].replace(" (read-only)", "").strip()
        mt = (m.get("mt") or "").strip()
        if len(label) < 24 and mt and mt.lower() not in label.lower():
            return f"{mt}: {label}"
        return label

    cand = {pid: candidate(pid) for pid in points}
    cand_counts: dict[str, int] = {}
    for v in cand.values():
        if v:
            cand_counts[v] = cand_counts.get(v, 0) + 1

    def menu_name(pid: int) -> str | None:
        v = cand.get(pid)
        if v and cand_counts[v] == 1:
            return v
        m = menu.get(str(pid))
        if v and m and m.get("mt"):
            alt = f"{v} ({m['mt']})"
            if alt not in cand_counts:
                return alt
        return None

    infos = {pid: info_for(pid, p, data, menu_name(pid)) for pid, p in points.items()}
    counts: dict[str, int] = {}
    for i in infos.values():
        counts[i.name] = counts.get(i.name, 0) + 1
    for i in infos.values():
        if counts[i.name] > 1 and i.point_id not in CURATED and i.point_id not in BINARY:
            i.name = f"{i.name} [{i.point_id}]"
    return infos
