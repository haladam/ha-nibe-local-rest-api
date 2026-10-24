"""COP and heat output calculated from the heat pump's own readings.

Pure Python (no Home Assistant imports) so it can be unit-tested on its own.

Heat output is the flow through the condenser times its temperature rise (supply line BT12 minus
return line BT3); the electrical side is the compressor's power input. The condenser sensor sits
before the internal electric heater, so this is the compressor's heat and its COP, whether or not
additional heat is running.

A reading only counts towards a COP when the heat pump is in a settled state:

* the compressor is running and has been for a few minutes in the same mode (no start-up),
* the operating priority and the hot water reversing valve agree (no mode change under way),
* no defrost, and no sudden step in compressor frequency, power, flow or temperature difference
  (those are transitions: the heat measured at the condenser lags the power for a while),
* flow, temperature difference and power are in a sensible range, and the COP of that single
  reading is plausible (a spike in a sensor is dropped, not averaged in).

COP is always energy over energy (the sum of heat divided by the sum of electricity over the
counted readings), never an average of ratios, so one odd reading cannot swing it.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from .const import KPI_POINTS

# Heat carried by one litre of heating medium per kelvin, in kJ (water: about 0.99 kg x 4.18 kJ/kg/K)
KJ_PER_LITRE_KELVIN = 4.15

PRIORITY_HOT_WATER = 20
PRIORITY_HEATING = 30
COMPRESSOR_RUNNING = 60

HEATING = "heating"
HOT_WATER = "hot_water"
MODES = (HEATING, HOT_WATER)

STATUS_OK = "ok"


@dataclass(frozen=True)
class Settings:
    settle_s: float = 300.0          # after a compressor start, a defrost or a change of mode
    step_settle_s: float = 120.0     # after a sudden step in one of the readings
    max_freq_step_hz: float = 20.0   # between two readings
    max_power_step: float = 0.4      # relative change of the power input between two readings ...
    min_power_step_w: float = 300.0  # ... and at least this many watts
    max_flow_step: float = 0.3       # relative change of the flow
    max_delta_t_step: float = 3.0    # K between two readings
    min_power_w: float = 250.0       # below this the compressor is not really producing
    min_flow_lpm: float = 2.0
    max_flow_lpm: float = 60.0
    min_delta_t: float = 1.0         # K across the condenser: smaller is within the sensor error
    max_delta_t: float = 25.0
    min_cop: float = 0.8             # a single reading outside this is a sensor spike
    max_cop: float = 9.0
    max_gap_s: float = 150.0         # a longer pause between two readings is not integrated
    live_window_s: float = 900.0
    min_live_valid_s: float = 120.0  # counted seconds in the live window before a value is shown
    long_window_s: float = 86400.0
    min_long_energy_kwh: float = 0.2  # electricity in the long window before a value is shown


@dataclass
class Sample:
    """One set of readings; None means the point is missing or not connected."""

    time: float                             # seconds, any steady clock
    priority: float | None = None           # 10 off, 20 hot water, 30 heating, 40 pool, 60 cooling
    valve_hot_water: float | None = None    # reversing valve QN10: 1 = hot water position
    compressor_state: float | None = None   # 20 stopped, 40 starting, 60 running, 100 stopping
    compressor_on: float | None = None      # "compressor running" flag, used without the state
    frequency_hz: float | None = None
    power_w: float | None = None            # compressor power input
    flow_lpm: float | None = None           # heating medium flow (BF1)
    supply_c: float | None = None           # condenser supply line (BT12)
    return_c: float | None = None           # return line (BT3)
    defrost: float | None = None


@dataclass(frozen=True)
class Reading:
    status: str                  # "ok", or the reason this reading does not count
    mode: str | None             # heating or hot_water for a counted reading
    heat_kw: float | None        # heat output of this reading; 0 when the compressor is stopped
    cop: float | None            # COP of this single reading (counted readings only)
    settle_left_s: float = 0.0


class CopTracker:
    def __init__(self, settings: Settings | None = None) -> None:
        self.cfg = settings or Settings()
        self.last: Reading | None = None
        self._now: float | None = None
        self._prev: tuple | None = None   # frequency, power, flow, delta T of the previous reading
        self._stable_mode: str | None = None
        self._stable_since: float | None = None
        self._quiet_until = 0.0
        # per mode: (time, seconds, kWh of heat, kWh of electricity) of each counted reading
        self._entries: dict[str, deque] = {m: deque() for m in MODES}
        self.rejected: dict[str, int] = {m: 0 for m in MODES}

    # ------------------------------------------------------------------ feeding
    def update(self, s: Sample) -> Reading:
        cfg = self.cfg
        t = s.time
        gap = self._now is None or t <= self._now or t - self._now > cfg.max_gap_s
        dt = 0.0 if gap else t - self._now
        prev, self._prev = self._prev, None
        self._now = t
        if gap:  # nothing is known about what happened in between
            prev = None
            self._stable_mode, self._stable_since, self._quiet_until = None, None, 0.0

        running = self._running(s)
        delta_t = None
        q_kw = None
        if s.supply_c is not None and s.return_c is not None:
            delta_t = s.supply_c - s.return_c
            if s.flow_lpm is not None:
                q_kw = max(0.0, s.flow_lpm / 60.0 * KJ_PER_LITRE_KELVIN * delta_t)
        heat_kw = 0.0 if running is False else (q_kw if running else None)
        self._prev = (s.frequency_hz, s.power_w, s.flow_lpm, delta_t)

        mode = self._mode(s)
        status: str | None = None
        key: str | None = None
        if running is None:
            status = "no data"
        elif not running:
            status = "idle"
        elif None in (s.priority, s.power_w, s.flow_lpm, delta_t):
            status = "no data"
        elif s.defrost == 1:  # 0 = no, 1 = active, 2 = passive (no heat reversal)
            status = "defrost"
        elif mode is None:
            status = "other operation"  # off, pool, cooling, or priority and valve disagree (valve moving)
        else:
            key = mode

        if key != self._stable_mode:
            self._stable_mode, self._stable_since = key, (t if key else None)
        if key and prev and self._step(prev, s, delta_t):
            self._quiet_until = t + cfg.step_settle_s

        settle_left = 0.0
        cop = None
        if key:
            settle_left = max(0.0, self._stable_since + cfg.settle_s - t)
            if settle_left > 0:
                status = "settling"
            elif t < self._quiet_until:
                status = "unsteady"
                settle_left = self._quiet_until - t
            elif not (cfg.min_power_w <= s.power_w
                      and cfg.min_flow_lpm <= s.flow_lpm <= cfg.max_flow_lpm
                      and cfg.min_delta_t <= delta_t <= cfg.max_delta_t):
                status = "out of range"
            else:
                cop = q_kw * 1000.0 / s.power_w
                if not cfg.min_cop <= cop <= cfg.max_cop:
                    status, cop = "implausible", None
                    self.rejected[key] += 1
                else:
                    status = STATUS_OK
        if status == STATUS_OK and dt > 0:
            self._entries[key].append((t, dt, q_kw * dt / 3600.0, s.power_w / 1000.0 * dt / 3600.0))

        for entries in self._entries.values():
            while entries and entries[0][0] < t - cfg.long_window_s:
                entries.popleft()
        self.last = Reading(status, key if status == STATUS_OK else None, heat_kw, cop, settle_left)
        return self.last

    def _step(self, prev: tuple, s: Sample, delta_t: float) -> bool:
        """True when a reading jumped compared with the previous one (a transition, not a trend)."""
        cfg = self.cfg
        freq, power, flow, d_t = prev
        if freq is not None and s.frequency_hz is not None \
                and abs(s.frequency_hz - freq) > cfg.max_freq_step_hz:
            return True
        if power is not None and abs(s.power_w - power) > max(cfg.min_power_step_w, cfg.max_power_step * power):
            return True
        if flow and abs(s.flow_lpm - flow) > cfg.max_flow_step * flow:
            return True
        return d_t is not None and abs(delta_t - d_t) > cfg.max_delta_t_step

    # ------------------------------------------------------------------ results
    def window(self, mode: str, seconds: float) -> tuple[float, float, float]:
        """Counted seconds, kWh of heat and kWh of electricity of the last `seconds`."""
        if self._now is None:
            return 0.0, 0.0, 0.0
        start = self._now - seconds
        valid = heat = power = 0.0
        for t, dt, q, e in reversed(self._entries[mode]):
            if t <= start:
                break
            valid, heat, power = valid + dt, heat + q, power + e
        return valid, heat, power

    def live_cop(self, mode: str) -> float | None:
        """COP of the last 15 minutes, only while the pump is in this mode and settled."""
        if self.last is None or self.last.mode != mode:
            return None
        valid, heat, power = self.window(mode, self.cfg.live_window_s)
        if valid < self.cfg.min_live_valid_s or power <= 0:
            return None
        return heat / power

    def long_cop(self, mode: str) -> float | None:
        """COP over the last 24 hours of counted readings (stays after a run ends)."""
        valid, heat, power = self.window(mode, self.cfg.long_window_s)
        if power < self.cfg.min_long_energy_kwh:
            return None
        return heat / power

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _running(s: Sample) -> bool | None:
        running = None
        if s.compressor_state is not None:
            running = s.compressor_state == COMPRESSOR_RUNNING
        elif s.compressor_on is not None:
            running = s.compressor_on >= 0.5
        if running and s.frequency_hz is not None and s.frequency_hz <= 0:
            running = False
        return running

    @staticmethod
    def _mode(s: Sample) -> str | None:
        if s.priority is None:
            return None
        valve = None if s.valve_hot_water is None else s.valve_hot_water >= 0.5
        if s.priority == PRIORITY_HOT_WATER and valve is not False:
            return HOT_WATER
        if s.priority == PRIORITY_HEATING and valve is not True:
            return HEATING
        return None


def available(points: dict) -> bool:
    """True when the pump reports what the calculation needs."""
    ids = KPI_POINTS
    return (
        all(ids[k] in points for k in ("priority", "flow", "supply", "return"))
        and (ids["power"] in points or ids["power_avg"] in points)
        and (ids["state"] in points or ids["running"] in points)
    )


def build_sample(now: float, value: Callable[[int], float | None]) -> Sample:
    """Collect one Sample; `value(point_id)` returns the scaled reading or None."""
    ids = KPI_POINTS
    power = value(ids["power"])
    if power is None:
        power = value(ids["power_avg"])
    return Sample(
        time=now,
        priority=value(ids["priority"]),
        valve_hot_water=value(ids["valve"]),
        compressor_state=value(ids["state"]),
        compressor_on=value(ids["running"]),
        frequency_hz=value(ids["freq"]),
        power_w=power,
        flow_lpm=value(ids["flow"]),
        supply_c=value(ids["supply"]),
        return_c=value(ids["return"]),
        defrost=value(ids["defrost"]),
    )
