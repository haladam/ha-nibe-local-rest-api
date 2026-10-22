"""Helpers for the optional fast polling of a few chosen points.

Pure Python (no Home Assistant imports) so it can be unit-tested on its own.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from .const import CONF_FAST_POINTS, MAX_FAST_POINTS

# Entity kinds that make sense to poll fast (buttons and skipped points do not).
FAST_KINDS = frozenset({"sensor", "binary_sensor", "number", "switch", "select", "time"})


def selected_point_ids(options: Mapping[str, Any], known_points: Iterable[int]) -> list[int]:
    """Point ids from the saved options: unique, still on the pump, at most the maximum."""
    known = set(known_points)
    out: list[int] = []
    for item in options.get(CONF_FAST_POINTS) or []:
        try:
            pid = int(item)
        except (TypeError, ValueError):
            continue
        if pid in known and pid not in out:
            out.append(pid)
    return out[:MAX_FAST_POINTS]


def is_point_payload(payload: Any, point_id: int) -> bool:
    """True when a single-point response has the same shape as a points-table entry."""
    if not isinstance(payload, dict):
        return False
    meta = payload.get("metadata")
    if not isinstance(meta, dict) or meta.get("variableId", point_id) != point_id:
        return False
    return "value" in payload or "datavalue" in payload


def choice_pairs(infos: Mapping[int, Any], usable_ids: Iterable[int], selected: Iterable[int]) -> list[tuple[int, str]]:
    """(point id, label) pairs for the options form, sorted by label.

    usable_ids are the points that currently have an enabled entity. Points that are
    already selected stay in the list even when their entity is disabled now, so the
    saved choice does not make the form invalid.
    """
    wanted = set(usable_ids) | set(selected)
    pairs = [
        (pid, f"{info.name} [{pid}]")
        for pid, info in infos.items()
        if pid in wanted and info.kind in FAST_KINDS
    ]
    return sorted(pairs, key=lambda pair: pair[1].lower())
