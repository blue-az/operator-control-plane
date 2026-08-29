#!/usr/bin/env bash
# A worked example that does real work and then tries to lie about it.
#
# Everything here runs for real: a real module, a real pytest run, a real gate.
# Nothing is stubbed. Four scenarios, each printing what `doctor` actually says:
#
#   1. Real work, evidence attached, unverified   -> consistent
#   2. Same-UID verification in single_user mode  -> Warning, recorded as advisory
#   3. Evidence file edited after attachment      -> Error, SHA-256 mismatch
#   4. Builder verifies itself in enforced mode   -> refused before it is written
#
# Run it anywhere; it works in a temp dir and cleans up after itself.
#   ./examples/verified-work/run.sh
set -euo pipefail

OP="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/operator"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
run() { printf '\033[2m$ %s\033[0m\n' "$*"; eval "$@"; }

"$OP" init >/dev/null
say "The work: a real module and a real test"
cat > netcfg.py <<'PY'
def parse_port(spec: str) -> int:
    """Return the port from a "host:port" string."""
    return int(spec.split(":")[1])
PY
cat > test_netcfg.py <<'PY'
from netcfg import parse_port

def test_extracts_port():
    assert parse_port("host:8080") == 8080
PY
run "python3 -m pytest -q test_netcfg.py" | tee result.log

say "1. Record the claim, bind it to the gate, attach the real output"
"$OP" task-create --objective "parse_port extracts the port from host:port" --id netcfg >/dev/null
run "\"\$OP\" claim-add --task netcfg --type test_passes \
    --text 'parse_port(\"host:8080\") returns 8080' --gate test_netcfg.py --by builder" >/dev/null
run "\"\$OP\" evidence-attach result.log --task netcfg --claim claim-0001 --type test_output \
    --verify-cmd 'python3 -m pytest -q test_netcfg.py' --by builder" >/dev/null
echo "-> doctor:"; "$OP" doctor | grep -E '^\[|consistent' || true
echo "   The claim is unverified and doctor says so by staying quiet about trust."

say "2. Verify it as the same Unix user (default single_user mode)"
run "\"\$OP\" evidence-attach result.log --task netcfg --claim claim-0001 --type test_output \
    --status verified --verified-by reviewer" >/dev/null
echo "-> doctor:"; "$OP" doctor | grep -E '^\[|consistent' || true
echo "   Accepted, but recorded as ADVISORY. One Unix user is one identity, whatever"
echo "   name was passed to --verified-by. No self-grading is silently upgraded."

say "3. Now edit the evidence to say something it never said"
echo '2 passed in 0.01s' > result.log
echo "-> doctor:"; "$OP" doctor | grep -E '^\[Error\]' | head -2 || true
echo "   The bytes were fingerprinted at attach time. Editing them afterwards is"
echo "   an Error, and doctor exits non-zero. This is the check you cannot talk past."
echo '1 passed in 0.01s' > result.log   # put the honest bytes back

say "4. Turn on enforced identity and let the builder try to verify itself"
# The uid must be this machine's real one -- the registry keys on the executing
# OS uid, not on a name. Hardcoding 1000 works on a laptop and fails on a CI
# runner, which is the gate behaving correctly.
cat > .operator/identity.yaml <<YML
mode: enforced
uids:
  $(id -u):
    name: builder-seat
    roles:
      - builder
YML
"$OP" claim-add --task netcfg --type test_passes --text "a second claim" \
    --gate test_netcfg.py --by builder-seat >/dev/null
echo "-> attempting self-verification:"
# expected to fail: that refusal is the point of the scenario
("$OP" evidence-attach result.log --task netcfg --claim claim-0002 --type test_output \
    --status verified --verified-by builder-seat 2>&1 || true) | tail -1
echo "   Refused before anything was written. Trusted verification needs a registered"
echo "   verifier whose OS uid differs from the claim author's -- a different harness"
echo "   name is not enough. See docs/specs/EXECUTOR_IDENTITY_SPEC.md."

say "Done"
echo "Nothing above was stubbed: pytest really ran, the hash mismatch is a real"
echo "SHA-256 comparison, and the refusal is the identity gate, not a printed message."
