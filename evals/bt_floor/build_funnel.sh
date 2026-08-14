#!/usr/bin/env bash
# build_funnel.sh — assemble the BT cold-start documentation funnel, reproducibly.
#
# The BT local-LLM floor benchmark feeds a model five repo documents and asks
# five boundary probes. Its input was never pinned, so the corpus moved
# underneath it: measured 23,736 tokens on 2026-07-18 and 37,002 on 2026-08-13,
# a 63% growth that pushed it past the 24,576-token window the original run was
# built around. `granite4` dropped 4/5 -> 3/5 from corpus growth alone, with
# the model and probes unchanged.
#
# Usage:
#   ./build_funnel.sh july     > funnel.txt   # the 2026-07-18 pinned epoch
#   ./build_funnel.sh current  > funnel.txt   # today's HEAD
#   ./build_funnel.sh capped   > funnel.txt   # today's HEAD, BOTTLENECKS truncated
#
# Always record which epoch a run used. Results from different epochs are not
# comparable, in the same way results from different harness revisions are not.
set -uo pipefail
EPOCH="${1:?usage: build_funnel.sh july|current|capped}"
PHX="${PHX:-$HOME/Python}"
OCP="${OCP:-$HOME/operator-control-plane}"

# Pinned heads, taken verbatim from BT_FLOOR_ANSWER_2026-07-18.md. project-phoenix
# is a subdirectory of the ~/Python repo, not its own -- paths need the prefix, and
# omitting it makes `git show` emit an error that looks like a short file.
JULY_PHX=c25e8c3d
JULY_OCP=79fd91b

case "$EPOCH" in
  july)
    git -C "$PHX" show "$JULY_PHX:project-phoenix/AGENTS.md"
    git -C "$PHX" show "$JULY_PHX:project-phoenix/BOTTLENECKS.md"
    git -C "$PHX" show "$JULY_PHX:project-phoenix/docs/BULKHEAD_TAU_BOUNDARIES.md"
    git -C "$OCP" show "$JULY_OCP:AGENTS.md"
    git -C "$OCP" show "$JULY_OCP:CRYSTAL_LEDGER_INTEROP_SPEC.md"
    ;;
  current)
    cat "$PHX/project-phoenix/AGENTS.md" \
        "$PHX/project-phoenix/BOTTLENECKS.md" \
        "$PHX/project-phoenix/docs/BULKHEAD_TAU_BOUNDARIES.md" \
        "$OCP/AGENTS.md" "$OCP/CRYSTAL_LEDGER_INTEROP_SPEC.md"
    ;;
  capped)
    # BOTTLENECKS.md is 68% of the funnel and grows monotonically by design, so it
    # is the whole reason the benchmark outgrew its window. The probes ask about
    # boundaries and vocabulary, which live in its header and glossary -- the
    # open-work entries below "## Self-Blocked" carry none of the answers. Cutting
    # there keeps the benchmark answerable while bounding its growth.
    cat "$PHX/project-phoenix/AGENTS.md"
    sed '/^## Self-Blocked/,$d' "$PHX/project-phoenix/BOTTLENECKS.md"
    cat "$PHX/project-phoenix/docs/BULKHEAD_TAU_BOUNDARIES.md" \
        "$OCP/AGENTS.md" "$OCP/CRYSTAL_LEDGER_INTEROP_SPEC.md"
    ;;
  *) echo "unknown epoch: $EPOCH" >&2; exit 2;;
esac
