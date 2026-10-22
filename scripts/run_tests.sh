#!/usr/bin/env bash
# Run every test suite: the integration suites always, the card's browser tests unless --no-card.
#   ./scripts/run_tests.sh            everything (needs node, and python playwright with chromium)
#   ./scripts/run_tests.sh --no-card  integration suites only
set -u
cd "$(dirname "$0")/.."
status=0

run() {  # run <label> <command...>: print the last line of the output, or the failures
  local label=$1; shift
  local out
  if out=$("$@" 2>&1); then
    printf '%-45s %s\n' "$label" "$(printf '%s\n' "$out" | tail -n 1)"
  else
    printf '%-45s FAILED\n' "$label"
    printf '%s\n' "$out" | grep -E '^FAIL|Traceback|Error|problems' | head -n 20
    status=1
  fi
}

echo "== integration suites"
for t in tests/test_*.py; do run "$t" python3 -I -B "$t"; done

if [ "${1:-}" != "--no-card" ]; then
  echo "== card"
  run "build card/src" ./card/build.sh
  if cmp -s card/nibe-plant-card.js custom_components/nibe_local_api/frontend/nibe-plant-card.js; then
    echo "bundled card matches card/src"
  else
    echo "FAILED: the bundled card differs from the build of card/src (run ./scripts/sync_card.sh)"; status=1
  fi
  run "card/test/test_card.py" python3 -I -B card/test/test_card.py
  run "card/test/overlaps.py" python3 -I -B card/test/overlaps.py
fi

if [ "$status" -eq 0 ]; then echo "ALL GREEN"; else echo "SOMETHING FAILED"; fi
exit $status
