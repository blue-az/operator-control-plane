#!/usr/bin/env bash
#
# gate_no_test_regression.sh — required_gate for the "no test regression" claim on
# task opr-continuation-loop-audit.
#
# Asserts that 890d595 (continuation loop) and d5eea34 (configurable dispatch timeout)
# introduce no test regression relative to their parent 81682a8, by comparing the SET OF
# FAILING TEST NAMES — not merely the failure count. Three commits can share a count
# while failing different tests; counts alone do not establish the claim.
#
# Uses `git worktree` rather than checking commits out in place. An earlier run of this
# comparison left the repository in detached HEAD and its restore assumed the branch was
# 'main' when it is 'master'. Nothing here touches the working tree or HEAD.
#
# Exit 0 = gate passes (identical failing-test sets at all three commits).
# Exit 1 = gate fails (sets differ, i.e. a regression or a fix changed which tests fail).
# Exit 2 = gate could not be evaluated.
#
set -uo pipefail

COMMITS=(81682a8 890d595 d5eea34)
REPO_ROOT=$(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel 2>/dev/null) \
    || { echo "gate: not inside a git repository" >&2; exit 2; }

WORKROOT=$(mktemp -d "${TMPDIR:-/tmp}/gate-notestreg-XXXXXX") || exit 2
cleanup() {
    for c in "${COMMITS[@]}"; do
        git -C "$REPO_ROOT" worktree remove --force "$WORKROOT/$c" 2>/dev/null
    done
    rm -rf "$WORKROOT"
    git -C "$REPO_ROOT" worktree prune 2>/dev/null
}
trap cleanup EXIT

declare -A DIGEST COUNT
STATUS=0

for c in "${COMMITS[@]}"; do
    if ! git -C "$REPO_ROOT" rev-parse --verify --quiet "${c}^{commit}" >/dev/null; then
        echo "gate: unknown commit $c" >&2; exit 2
    fi
    if ! git -C "$REPO_ROOT" worktree add --detach --quiet "$WORKROOT/$c" "$c" 2>/dev/null; then
        echo "gate: could not create worktree for $c" >&2; exit 2
    fi

    raw="$WORKROOT/$c.raw"
    ( cd "$WORKROOT/$c" && python3 -m unittest discover -s tests ) > "$raw" 2>&1

    # unittest prints "FAIL: test_name (module.Class)" / "ERROR: ..." per failure.
    names=$(grep -hE '^(FAIL|ERROR): ' "$raw" | sed -E 's/^(FAIL|ERROR): //' \
            | LC_ALL=C sort -u)
    COUNT["$c"]=$(printf '%s\n' "$names" | grep -c . )
    DIGEST["$c"]=$(printf '%s\n' "$names" | md5sum | cut -d' ' -f1)

    printf 'gate: %-9s failing=%-4s digest=%s\n' "$c" "${COUNT[$c]}" "${DIGEST[$c]}"
    printf '%s\n' "$names" > "$WORKROOT/$c.names"
done

BASE="${COMMITS[0]}"
for c in "${COMMITS[@]:1}"; do
    if [ "${DIGEST[$c]}" != "${DIGEST[$BASE]}" ]; then
        STATUS=1
        echo "gate: FAIL — failing-test set at $c differs from $BASE:"
        diff "$WORKROOT/$BASE.names" "$WORKROOT/$c.names" | sed 's/^/    /'
    fi
done

if [ "$STATUS" -eq 0 ]; then
    echo "gate: PASS — identical failing-test sets (${COUNT[$BASE]} tests, digest ${DIGEST[$BASE]}) across ${COMMITS[*]}"
fi
exit "$STATUS"
