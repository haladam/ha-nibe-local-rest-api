from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import aiohttp

from .const import (
    DIVISOR_OVERRIDES, HEATER_STEP_KW, MULTIPLIERS, RANGE_OVERRIDES, SENTINELS,
    VERSION_POINT,
)


class NibeApiError(Exception):
    """Communication error."""


class NibeAuthError(NibeApiError):
    """Bad credentials."""


class NibeLocalApi:
    def __init__(self, session: aiohttp.ClientSession, host: str, port: int, https: bool) -> None:
        scheme = "https" if https else "http"
        self._base = f"{scheme}://{host}:{port}/api/v1"
        self._session = session

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            async with asyncio.timeout(45):
                async with self._session.request(method, f"{self._base}{path}", **kwargs) as resp:
                    if resp.status in (401, 403):
                        raise NibeAuthError(f"HTTP {resp.status}")
                    resp.raise_for_status()
                    text = await resp.text()
                    try:
                        return json.loads(text) if text else None
                    except ValueError:
                        return text
        except NibeApiError:
            raise
        except (aiohttp.ClientError, TimeoutError) as err:
            raise NibeApiError(str(err)) from err

    async def get_devices(self) -> Any:
        return await self._request("GET", "/devices")

    async def get_device(self, device: int = 0) -> Any:
        return await self._request("GET", f"/devices/{device}")

    async def get_points(self, device: int = 0) -> dict[int, dict]:
        data = await self._request("GET", f"/devices/{device}/points")
        if not isinstance(data, dict):
            raise NibeApiError("Unexpected points response")
        return {int(k): v for k, v in data.items()}

    async def patch_points(self, values: dict[int, int], device: int = 0) -> Any:
        body = [
            {"type": "datavalue", "isOk": True, "variableId": pid,
             "integerValue": raw, "stringValue": ""}
            for pid, raw in values.items()
        ]
        return await self._request("PATCH", f"/devices/{device}/points", json=body)

    async def get_point(self, point_id: int, device: int = 0) -> dict | None:
        """Read a single point (one small request instead of the whole table)."""
        data = await self._request("GET", f"/devices/{device}/points/{point_id}")
        return data if isinstance(data, dict) else None

    async def set_mode(self, endpoint: str, key: str, value: str, device: int = 0) -> dict | None:
        """Set aid/smart mode and verify it.

        Tries the lowercase body key first (confirmed on firmware 4.12.6 by the bridge
        project), then the spec's camelCase key. After each attempt the device state is
        read back: a 200 response alone does not prove the pump applied the value.
        Returns the device state read back, or None when it could not be read.
        """
        path = f"/devices/{device}/{endpoint}"
        for body_key in (endpoint, key):
            try:
                await self._request("POST", path, json={body_key: value})
            except NibeAuthError:
                raise
            except NibeApiError:
                continue
            try:
                state = await self.get_device(device)
            except NibeApiError:
                return None  # written, but could not be verified
            if isinstance(state, dict) and state.get(key, state.get(endpoint)) == value:
                return state
        raise NibeApiError(f"{endpoint} did not change to {value!r}")

    async def get_notifications(self, device: int = 0) -> list[dict]:
        data = await self._request("GET", f"/devices/{device}/notifications")
        if isinstance(data, dict):
            data = data.get("alarms", [])
        return data if isinstance(data, list) else []

    async def reset_notifications(self, device: int = 0) -> Any:
        return await self._request("DELETE", f"/devices/{device}/notifications")


def parse_device(payload: Any) -> dict[str, str]:
    """Extract serial/name/firmware defensively from /devices output."""
    dev = payload
    if isinstance(payload, dict) and "devices" in payload:
        dev = payload["devices"]
    if isinstance(dev, list):
        dev = dev[0] if dev else {}
    prod = (dev or {}).get("product", {}) or {}
    return {
        "serial": str(prod.get("serialNumber") or "nibe"),
        "name": prod.get("name") or "NIBE S1155",
        "manufacturer": prod.get("manufacturer") or "NIBE",
        "firmware": prod.get("firmwareId") or "",
    }


def version_label(firmware: str | None) -> str | None:
    """Firmware text worth showing as a software version, otherwise None.

    /devices reports firmwareId "nibe-n": the product line, not a version number.
    """
    if firmware and re.search(r"\d+\.\d+", firmware):
        return firmware
    return None


def decode_version(raw: int | None) -> str | None:
    """'major.minor' from the heat pump's version register (high byte, low byte)."""
    if not isinstance(raw, int) or isinstance(raw, bool):
        return None
    if raw < 256 or raw >= 0xFFFF:  # major 0, or the "not connected" marker
        return None
    return f"{raw >> 8}.{raw & 0xFF}"


def firmware_version(points: dict[int, dict]) -> str | None:
    """The heat pump's own software version ('4.14'), read from its version point."""
    point = points.get(VERSION_POINT)
    if not point:
        return None
    value = point.get("value") or point.get("datavalue") or {}
    if not value.get("isOk", False):
        return None
    return decode_version(value.get("integerValue"))


def fix_text(text: str | None) -> str:
    if not text:
        return ""
    try:
        text = text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return text.replace("\u00ad", "").strip()


def clean_title(point: dict) -> str:
    return fix_text(point.get("title")) or "Unknown"


def firmware_description(point: dict) -> str:
    return fix_text(point.get("description"))


def unit_of(meta: dict) -> str | None:
    return fix_text(meta.get("unit")) or fix_text(meta.get("shortUnit")) or None


def divisor(point_id: int, point: dict) -> int:
    meta = point.get("metadata", {})
    return DIVISOR_OVERRIDES.get(point_id) or meta.get("divisor") or 1


def scale_factor(point_id: int, point: dict) -> float:
    """Multiply a raw value by this to get the displayed value."""
    if point_id in MULTIPLIERS:
        return MULTIPLIERS[point_id]
    return 1 / divisor(point_id, point)


def to_raw(point_id: int, point: dict, value: float) -> int:
    """Convert a displayed value back to the raw integer to write."""
    if point_id in MULTIPLIERS:
        return round(value / MULTIPLIERS[point_id])
    return round(value * divisor(point_id, point))


def register_key(meta: dict) -> str | None:
    """Key into data.json 'register_ranges': H<register> (holding) or I<register> (input)."""
    prefix = {"MODBUS_HOLDING_REGISTER": "H", "MODBUS_INPUT_REGISTER": "I"}.get(
        meta.get("modbusRegisterType")
    )
    register = meta.get("modbusRegisterID")
    if prefix is None or not isinstance(register, int):
        return None
    return f"{prefix}{register}"


def reported_bounds(point_id: int, meta: dict) -> tuple[int, int]:
    """Raw (min, max) as the pump reports them, with the known firmware corrections."""
    mn, mx = meta.get("minValue", 0), meta.get("maxValue", 0)
    o_min, o_max = RANGE_OVERRIDES.get(point_id, (None, None))
    return (mn if o_min is None else o_min), (mx if o_max is None else o_max)


def bounds(point_id: int, meta: dict, register_ranges: dict | None = None) -> tuple[int, int]:
    """Raw (min, max) a setting accepts.

    The pump's own range is often a generic one (every hot water temperature reports
    5-70 C). NIBE's register list gives the real limit per register, so when both
    ranges are usable the narrower of the two wins. A range the pump reports as empty
    (min == max) is left alone: the register list cannot widen it.
    """
    mn, mx = reported_bounds(point_id, meta)
    if register_ranges and mx > mn:
        known = register_ranges.get(register_key(meta) or "")
        if known:
            lo, hi = max(mn, known[0]), min(mx, known[1])
            if hi > lo:
                return lo, hi
    return mn, mx


def is_writable(meta: dict) -> bool:
    """Writable per firmware flag or holding register (the flag is wrong for ~17 points)."""
    return bool(meta.get("isWritable")) or meta.get("modbusRegisterType") == "MODBUS_HOLDING_REGISTER"


def flag_mismatch(meta: dict) -> bool:
    return not meta.get("isWritable") and meta.get("modbusRegisterType") == "MODBUS_HOLDING_REGISTER"


def raw_value(point: dict) -> int | None:
    val = point.get("value") or point.get("datavalue") or {}
    return val.get("integerValue")


def scaled_value(point_id: int, point: dict) -> float | None:
    meta = point.get("metadata", {})
    val = point.get("value") or point.get("datavalue") or {}
    if meta.get("variableType") != "integer" or not val.get("isOk", False):
        return None
    raw = val.get("integerValue")
    if raw is None or raw == SENTINELS.get(meta.get("variableSize")):
        return None
    if point_id in MULTIPLIERS:
        return raw * MULTIPLIERS[point_id]
    return raw / divisor(point_id, point)


def time_seconds(point: dict) -> int | None:
    """Seconds since midnight for 'time' points (raw 5400 = 01:30), else None."""
    meta = point.get("metadata", {})
    val = point.get("value") or point.get("datavalue") or {}
    if meta.get("variableType") != "time" or not val.get("isOk", False):
        return None
    raw = val.get("integerValue")
    if raw is None or raw < 0 or raw >= 86400:
        return None
    return int(raw)


def is_live(point_id: int, point: dict) -> bool:
    return scaled_value(point_id, point) is not None or time_seconds(point) is not None


def pump_running(speed: float | None) -> bool | None:
    """A pump counts as running when its speed is above zero."""
    if speed is None:
        return None
    return speed > 0


def heater_power_kw(steps: float | None) -> float | None:
    """Internal electric heater power from its step count (0.5 kW per step)."""
    if steps is None:
        return None
    return round(steps * HEATER_STEP_KW, 3)


def heater_max_steps(max_kw: float | None) -> int | None:
    """Highest step count allowed by the 'Max. internal additional heat' setting."""
    if max_kw is None or max_kw <= 0:
        return None
    return int(max_kw / HEATER_STEP_KW + 1e-9)


def heater_load_percent(steps: float | None, max_kw: float | None) -> float | None:
    power = heater_power_kw(steps)
    if power is None or not max_kw or max_kw <= 0:
        return None
    return round(min(100.0, power / max_kw * 100), 1)
