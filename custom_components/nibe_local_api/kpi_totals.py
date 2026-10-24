"""Running totals of heat and compressor electricity per mode, for seasonal and lifetime COP.

Pure Python (no Home Assistant imports), like kpi.py.

Unlike the steady-state COP in kpi.py, nothing is left out here except readings that cannot be
trusted: the compressor's whole energy is counted, start-ups and mode changes included, because
that is what the electricity meter would have seen. Every reading is a point on a curve; the
energy of an interval is the trapezoid between two readings, and each end goes to the mode it was
measured in (priority and reversing valve agree, otherwise "other"). Intervals with a missing
reading or a longer pause than `max_gap_s` count for neither heat nor electricity, so the ratio
of the two stays honest; what was not seen is reported as coverage.

The totals are kept per local day (for "today", the season and the previous season) and as one
running lifetime sum, and they are saved and restored through to_dict() / from_dict().
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .kpi import HEATING, HOT_WATER, KJ_PER_LITRE_KELVIN, Sample, operating_mode

OTHER = "other"        # compressor running while priority and valve disagree, pool, cooling
TOTAL = "total"        # all three buckets together (only used for results)
BUCKETS = (HEATING, HOT_WATER, OTHER)
PUMP_KEYS = ("heating", "hot_water", "total_heat", "total_el")
FORMAT = 1


@dataclass(frozen=True)
class TotalsSettings:
    max_gap_s: float = 150.0        # longer pauses between two readings are not integrated
    idle_below_w: float = 20.0      # the compressor draws less than this: nothing is running
    max_heat_kw: float = 30.0       # more than this from one reading is a sensor glitch
    max_start_step: int = 20        # starts counted between two readings at most
    keep_days: int = 800            # days of history kept for seasons
    min_energy_kwh: float = 0.25    # electricity needed before a COP is shown (about an hour at minimum speed)
    min_pump_energy_kwh: float = 1.0  # the pump's own counters have 0.1 kWh steps: needs more


def season_start(day: date, month: int) -> date:
    """First day of the season `day` belongs to: the 1st of `month`, this year or the year before."""
    return date(day.year if day.month >= month else day.year - 1, month, 1)


def _endpoint(s: Sample, cfg: TotalsSettings):
    """(bucket, kW electric, kW heat) of one reading; (None, 0, 0) when idle; None when unknown."""
    p = s.power_w
    if p is None:
        return None
    if p < cfg.idle_below_w:
        return (None, 0.0, 0.0)
    if s.flow_lpm is None or s.supply_c is None or s.return_c is None:
        return None
    q = max(0.0, s.flow_lpm / 60.0 * KJ_PER_LITRE_KELVIN * (s.supply_c - s.return_c))
    if q > cfg.max_heat_kw:
        return None
    return (operating_mode(s) or OTHER, p / 1000.0, q)


def _new_day() -> dict:
    return {HEATING: [0.0, 0.0], HOT_WATER: [0.0, 0.0], OTHER: [0.0, 0.0], "run_s": 0.0, "starts": 0}


class EnergyTotals:
    def __init__(self, settings: TotalsSettings | None = None, season_month: int = 10) -> None:
        self.cfg = settings or TotalsSettings()
        self.season_month = min(max(int(season_month), 1), 12)
        self.since: str | None = None                       # first day that was counted
        self.lifetime = {b: [0.0, 0.0] for b in BUCKETS}    # per bucket: [kWh heat, kWh electricity]
        self.days: dict[str, dict] = {}
        self.counted_s = self.skipped_s = self.gap_s = 0.0
        self.pump_base: dict[str, float] = {}               # the pump's own counters at the first reading
        self.pump_now: dict[str, float] = {}
        self.season: str | None = None                      # start of the season the baseline belongs to
        self.season_base: dict[str, float] = {}
        self.season_from: str | None = None
        self._prev: tuple | None = None                     # time, endpoint, starts counter

    # ------------------------------------------------------------------ feeding
    def update(self, s: Sample, day: str, counters: dict | None = None) -> None:
        cfg = self.cfg
        counters = counters or {}
        t, ep, starts = s.time, _endpoint(s, cfg), counters.get("starts")
        prev, self._prev = self._prev, (t, ep, starts)
        if self.since is None:
            self.since = day
        self._follow_counters(day, counters)
        if prev is None or t <= prev[0]:
            return
        dt = t - prev[0]
        rec = self.days.get(day)
        if rec is None:
            rec = self.days[day] = _new_day()
            self._prune(day)
        if dt > cfg.max_gap_s:
            self.gap_s += dt
            return
        if prev[1] is None or ep is None:
            self.skipped_s += dt
        else:
            self.counted_s += dt
            half_hour = dt / 2.0 / 3600.0
            for bucket, p_kw, q_kw in (prev[1], ep):
                if bucket is None:
                    continue
                for total in (self.lifetime[bucket], rec[bucket]):
                    total[0] += q_kw * half_hour
                    total[1] += p_kw * half_hour
                rec["run_s"] += dt / 2.0
        if starts is not None and prev[2] is not None and 0 <= starts - prev[2] <= cfg.max_start_step:
            rec["starts"] += int(round(starts - prev[2]))

    def _follow_counters(self, day: str, counters: dict) -> None:
        for key in PUMP_KEYS:
            value = counters.get(key)
            if value is not None:
                self.pump_now[key] = value
                self.pump_base.setdefault(key, value)
        start = season_start(date.fromisoformat(day), self.season_month).isoformat()
        if start != self.season:
            self.season, self.season_base, self.season_from = start, {}, None
        for key in ("total_heat", "total_el"):
            value = counters.get(key)
            if value is not None and key not in self.season_base:
                self.season_base[key] = value
                self.season_from = self.season_from or day

    def _prune(self, day: str) -> None:
        limit = (date.fromisoformat(day) - timedelta(days=self.cfg.keep_days)).isoformat()
        for old in [k for k in self.days if k < limit]:
            del self.days[old]

    # ------------------------------------------------------------------ results
    @staticmethod
    def _buckets(bucket: str) -> tuple[str, ...]:
        return BUCKETS if bucket == TOTAL else (bucket,)

    def lifetime_sums(self, bucket: str) -> tuple[float, float]:
        """kWh of heat and of electricity since the counting began."""
        parts = [self.lifetime[b] for b in self._buckets(bucket)]
        return sum(p[0] for p in parts), sum(p[1] for p in parts)

    def season_sums(self, bucket: str, today: str, previous: bool = False) -> tuple[float, float]:
        """kWh of heat and of electricity in the current (or the previous) season."""
        start = season_start(date.fromisoformat(today), self.season_month)
        if previous:
            first, last = date(start.year - 1, start.month, 1).isoformat(), start.isoformat()   # [first, last)
        else:
            first, last = start.isoformat(), None
        heat = electricity = 0.0
        for key, rec in self.days.items():
            if key < first or (key >= last if last else key > today):
                continue
            for b in self._buckets(bucket):
                heat, electricity = heat + rec[b][0], electricity + rec[b][1]
        return heat, electricity

    def cop(self, heat: float, electricity: float, minimum: float | None = None) -> float | None:
        minimum = self.cfg.min_energy_kwh if minimum is None else minimum
        return heat / electricity if electricity >= max(minimum, 1e-9) else None

    def collecting(self, electricity: float, minimum: float | None = None) -> str:
        """Status text for a COP that is not shown yet because there is too little data."""
        minimum = self.cfg.min_energy_kwh if minimum is None else minimum
        return "ok" if electricity >= minimum else f"collecting data: {electricity:.2f} of {minimum:g} kWh of electricity"

    def season_since(self, today: str) -> str:
        """Where the season figures really start: the season's first day or when counting began."""
        start = season_start(date.fromisoformat(today), self.season_month).isoformat()
        return max(start, self.since) if self.since else start

    def pump_delta(self, key: str, season: bool = False) -> float | None:
        base = (self.season_base if season else self.pump_base).get(key)
        now = self.pump_now.get(key)
        return None if base is None or now is None else max(0.0, now - base)

    def coverage(self) -> float | None:
        total = self.counted_s + self.skipped_s + self.gap_s
        return self.counted_s / total if total > 0 else None

    def today(self, day: str) -> dict:
        return self.days.get(day) or _new_day()

    # ------------------------------------------------------------------ saving
    def to_dict(self) -> dict:
        r = lambda v: round(v, 4)
        return {
            "format": FORMAT,
            "since": self.since,
            "lifetime": {b: [r(v) for v in self.lifetime[b]] for b in BUCKETS},
            "days": {
                k: {**{b: [r(v) for v in rec[b]] for b in BUCKETS}, "run_s": round(rec["run_s"], 1), "starts": rec["starts"]}
                for k, rec in sorted(self.days.items())
            },
            "seconds": [round(self.counted_s), round(self.skipped_s), round(self.gap_s)],
            "pump_base": self.pump_base,
            "season": {"start": self.season, "from": self.season_from, "base": self.season_base},
        }

    @classmethod
    def from_dict(cls, data, settings: TotalsSettings | None = None, season_month: int = 10) -> EnergyTotals:
        """Rebuild from saved data; anything unexpected gives a fresh instance."""
        obj = cls(settings, season_month)
        try:
            if not isinstance(data, dict) or data.get("format") != FORMAT:
                return obj
            pair = lambda v: [float(v[0]), float(v[1])]
            lifetime = {b: pair(data["lifetime"][b]) for b in BUCKETS}
            days = {}
            for key, rec in data["days"].items():
                date.fromisoformat(key)
                days[key] = {**{b: pair(rec[b]) for b in BUCKETS}, "run_s": float(rec["run_s"]), "starts": int(rec["starts"])}
            counted, skipped, gap = (float(v) for v in data["seconds"])
            pump_base = {k: float(v) for k, v in data["pump_base"].items()}
            season = data["season"]
            season_base = {k: float(v) for k, v in season["base"].items()}
            since = data["since"]
            if since is not None:
                date.fromisoformat(since)
            season_start_saved, season_from = season["start"], season["from"]
        except (KeyError, TypeError, ValueError, IndexError, AttributeError):
            return cls(settings, season_month)
        obj.since, obj.lifetime, obj.days = since, lifetime, days
        obj.counted_s, obj.skipped_s, obj.gap_s = counted, skipped, gap
        obj.pump_base, obj.season, obj.season_base, obj.season_from = pump_base, season_start_saved, season_base, season_from
        return obj
