"""Repository-relative locations shared by the integration test suites."""
import os

TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
SRC = os.path.join(REPO, "custom_components", "nibe_local_api")
FIXTURES = os.path.join(TESTS, "fixtures")
CARD_BUILD = os.path.join(REPO, "card", "nibe-plant-card.js")

# REST exports of the points table: S1155, firmware 4.13.12 (English titles) and 4.14.6 (some German titles)
REST_413 = os.path.join(FIXTURES, "rest_4.13.12.json")
REST_414 = os.path.join(FIXTURES, "rest_4.14.6.json")

# Optional: unpacked earlier releases (the folder that contains data.json) for the one-off
# "only the intended points changed" comparisons in test_083 and test_084. Skipped when unset.
PREV_082 = os.environ.get("NIBE_TEST_PREV_082", "")
PREV_083 = os.environ.get("NIBE_TEST_PREV_083", "")


def version_at_least(version, minimum):
    """True when dotted version string `version` is `minimum` or later (numeric compare)."""
    parse = lambda v: tuple(int(p) for p in v.split("."))
    return parse(version) >= parse(minimum)
