"""AUX via Modbus: activate NIBE control functions through two writable points.

Per NIBE's Modbus S-series manual, the function ID is written to register 2740 and
0/1 to register 2741 (software 2.4.3 or later). On the REST API these should be
points 22070 and 22077. The service refuses to write unless the points' reported
modbusRegisterID matches, so a wrong mapping cannot touch other settings.
"""
from __future__ import annotations

from .api import NibeApiError
from .exceptions import translated_error

FUNCTION_POINT, STATE_POINT = 22070, 22077
FUNCTION_REGISTER, STATE_REGISTER = 2740, 2741

AUX_FUNCTIONS = {
    "hot_water_large": 1,
    "external_adjustment": 2,
    "block_additional_heat": 3,
    "block_compressor": 4,
    "block_heating": 6,
    "block_cooling": 7,
    "tariff_blocking": 19,
    "sg_ready_a": 20,
    "sg_ready_b": 21,
    "block_external_additional_heat": 33,
    "block_hot_water": 34,
    "hot_water_small": 41,
    "activate_heating": 58,
    "activate_cooling": 59,
}


def _check_point(points: dict, pid: int, register: int) -> None:
    meta = (points.get(pid) or {}).get("metadata", {})
    if meta.get("modbusRegisterID") != register:
        raise translated_error(
            "aux_unavailable", point_id=pid, found=meta.get("modbusRegisterID"), expected=register
        )


def _check_status(result, pid: int) -> None:
    if isinstance(result, dict):
        status = result.get(str(pid))
        if isinstance(status, str) and status.startswith("error"):
            raise translated_error("write_rejected", point_id=pid, status=status)


async def async_set_aux(coordinator, function: str, state: bool) -> None:
    function_id = AUX_FUNCTIONS[function]
    _check_point(coordinator.data, FUNCTION_POINT, FUNCTION_REGISTER)
    _check_point(coordinator.data, STATE_POINT, STATE_REGISTER)
    # The function register and the on/off register are a pair: the on/off value acts on
    # whichever function was written last. Without the lock, two overlapping calls could
    # interleave and switch the wrong function.
    async with coordinator.aux_lock:
        try:
            result = await coordinator.api.patch_points({FUNCTION_POINT: function_id})
            _check_status(result, FUNCTION_POINT)
            result = await coordinator.api.patch_points({STATE_POINT: 1 if state else 0})
            _check_status(result, STATE_POINT)
        except NibeApiError as err:
            raise translated_error("aux_write_failed", error=err) from err
    await coordinator.async_request_refresh()
