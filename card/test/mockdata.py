"""Build a mock Home Assistant `hass` object from a live CSV export of the integration (fixtures/points_live.csv)."""
import csv, json, os, re

CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "points_live.csv")

def slug(name):
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s

def build(overrides=None, only_enabled=True, include=()):
    """Return (states, entities). overrides: {point_id: raw_scaled_value or (value, label)}."""
    overrides = overrides or {}
    states, entities = {}, {}
    for r in csv.DictReader(open(CSV, encoding="utf-8")):
        if r["live"] != "True" or r["platform"] not in ("sensor", "binary_sensor", "number", "select", "switch"):
            continue
        pid = int(r["point_id"])
        if only_enabled and r["enabled_by_default"] != "True" and pid not in include:
            continue
        value = float(r["value"]) if r["value"] not in ("", None) else None
        if value is None:
            continue
        if pid in overrides:
            value = overrides[pid]
        plat = r["platform"]
        eid = f"{plat}.nibe_s1155_{slug(r['name'])}"
        labels = {}
        for part in (r["enum_labels"] or "").split(";"):
            if "=" in part:
                k, v = part.split("=", 1)
                labels[k.strip()] = v.strip()
        attrs = {"point_id": pid, "nibe_title": r["nibe_title"], "raw_value": value, "friendly_name": "NIBE S1155 " + r["name"]}
        if r["unit"]:
            attrs["unit_of_measurement"] = r["unit"]
        if plat == "binary_sensor":
            state = "on" if value else "off"
        elif labels and plat in ("sensor", "select"):
            state = labels.get(str(int(value)), str(int(value)))
        else:
            state = ("%g" % value)
        states[eid] = {"entity_id": eid, "state": state, "attributes": attrs}
        entities[eid] = {"entity_id": eid, "device_id": "dev_nibe"}
    return states, entities

def scenario(name):
    """Named situations as {point_id: value} overrides."""
    base = {}
    if name == "idle":
        return base
    if name == "heating":
        return {1758: 30, 1973: 1, 1799: 52, 1801: 1180, 22130: 1240, 8: 31.4, 10: 27.2, 1708: 30.5, 1975: 58, 1977: 70,
                2002: 0, 2556: 60, 13: 8.1, 14: 4.2, 4: 3.4, 25154: 0.9, 25158: 0.22}
    if name == "hotwater":
        return {1758: 20, 1973: 1, 1799: 74, 1801: 1650, 22130: 1710, 8: 52.3, 10: 44.1, 1975: 100, 1977: 85, 2002: 1,
                2556: 60, 11: 51.0, 12: 47.9, 13: 6.2, 14: 2.9, 4: 8.9, 25155: 1.4, 25159: 0.33, 1829: 1}
    if name == "cooling":
        return {1758: 60, 1973: 0, 1799: 0, 22130: 80, 3149: 1, 1977: 75, 8: 19.2, 10: 22.4, 13: 12.8, 14: 14.9, 4: 29.1, 1716: 1, 2695: 18.5, 25157: 0.0, 25161: 0.3}
    if name == "boost":
        return {1758: 20, 1973: 1, 1799: 90, 1801: 2900, 22130: 3010, 8: 55.0, 10: 47.0, 1975: 100, 1977: 90, 2002: 1, 2556: 60,
                11: 58.5, 12: 54.2, 4030: 142, 1942: 1, 1756: 1.5, 4: 12.0, 25155: 2.4, 25159: 0.55}
    if name == "alarm":
        return {3375: 163, 1709: 1}
    raise KeyError(name)

if __name__ == "__main__":
    s, e = build(scenario("idle"))
    print(len(s), "entities")
    for k in list(s)[:5]:
        print(k, s[k]["state"], s[k]["attributes"].get("point_id"))
