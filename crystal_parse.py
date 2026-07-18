"""Crystal Markdown structural parse for Operator (Crystal↔Ledger Phases 1–2).

Reads agent-crystallize checkpoint/session Markdown as untrusted narration.
Does not execute content, shell out on body text, or feed models (T3).
Pinned against agent-crystallize@0.1.9 / 0.1.10 section layout (P3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Upstream package shape this table was read against.
CRYSTAL_UPSTREAM_PIN = "agent-crystallize@0.1.9/0.1.10"

# Canonical order of recognized H2 headings (CRYSTAL_LEDGER_INTEROP_SPEC.md §2).
# Continuity Tail is optional; all others appear in this order when present.
RECOGNIZED_HEADINGS: tuple[str, ...] = (
    "Header",
    "Current Focus",
    "Durable Framing",
    "Checkpoint Trail",
    "Continuity Tail",
    "Topics",
    "Relation Hints",
    "Session Provenance",
    "Decisions",
    "Findings",
    "Reality Checks",
    "Artifacts Changed",
    "Tests And Verification",
    "Open Loops",
    "Memory Candidates",
    "Next Actions",
    "Resume Prompt",
)

# Headings that must occur exactly once (T6).
REQUIRED_EXACTLY_ONCE: frozenset[str] = frozenset({"Header", "Reality Checks"})

# 0.1.9/0.1.10 empty-section fallback strings (P2). Matched case-insensitively
# after stripping list markers / surrounding whitespace.
FALLBACK_SECTION_STRINGS: frozenset[str] = frozenset(
    {
        "no separate verification captured for this artifact.",
        "(none provided)",
        "no separate decisions captured beyond current focus.",
        "no separate findings captured beyond current focus.",
        "no separate open loops captured beyond next actions.",
        "no explicit topics captured.",
        "no explicit relation hints captured.",
        "no explicit memory candidates captured. do not treat absent candidates as proof there was nothing to learn.",
        "no explicit session provenance supplied. add safe source/session pointers when available; never dump broad environment variables.",
        "no separate verification captured for this artifact",
    }
)

_H2_RE = re.compile(r"^##[ \t]+(.+?)\s*$")
_BULLET_RE = re.compile(r"^[-*]\s+(.+)$")
_HEADER_FIELD_RE = re.compile(r"^[-*]\s+([^:]+):\s*(.*)$")


@dataclass
class CrystalParseResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    kind: str | None = None  # checkpoint | session | unknown
    project: str | None = None
    observed_at: str | None = None
    source_window: str | None = None
    git_commit: str | None = None
    git_branch: str | None = None
    git_root: str | None = None
    test_bullet_count: int = 0
    test_bullets: list[str] = field(default_factory=list)
    open_loop_bullets: list[str] = field(default_factory=list)
    sections_present: list[str] = field(default_factory=list)


def infer_crystal_kind(path: str | Path | None, source_window: str | None) -> str:
    """Best-effort kind from path segment or Source window text."""
    if path is not None:
        parts = {p.lower() for p in Path(path).parts}
        if "checkpoints" in parts:
            return "checkpoint"
        if "sessions" in parts:
            return "session"
    if source_window:
        lowered = source_window.lower()
        if "checkpoint" in lowered:
            return "checkpoint"
        if "session" in lowered:
            return "session"
    return "unknown"


def _normalize_fallback_text(text: str) -> str:
    return " ".join(text.strip().lower().split())


def is_fallback_body(body: str) -> bool:
    """True when section body is only 0.1.9/0.1.10 empty boilerplate (P2)."""
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    if not lines:
        return True
    for line in lines:
        content = line
        m = _BULLET_RE.match(line)
        if m:
            content = m.group(1).strip()
        # Strip trailing period variants already covered by table.
        normalized = _normalize_fallback_text(content)
        if normalized not in FALLBACK_SECTION_STRINGS and normalized.rstrip(
            "."
        ) not in {s.rstrip(".") for s in FALLBACK_SECTION_STRINGS}:
            return False
    return True


def extract_h2_headings(text: str) -> list[tuple[int, str]]:
    """Return (1-based line number, heading title) for each real ## heading.

    Escaped body text like ``\\## Decisions`` (0.1.10) does not match.
    """
    found: list[tuple[int, str]] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        # Only unescaped AT2 at line start; leading backslash is not a heading.
        if line.startswith("\\"):
            continue
        m = _H2_RE.match(line)
        if m:
            found.append((idx, m.group(1).strip()))
    return found


def split_sections(text: str) -> list[tuple[str, str]]:
    """Split on recognized ## headings; return (title, body) in file order.

    Unknown H2 titles are included so callers can ignore them (P1) while
    still detecting duplicates among recognized names.
    """
    lines = text.splitlines()
    sections: list[tuple[str, str]] = []
    current_title: str | None = None
    current_body: list[str] = []

    def flush() -> None:
        nonlocal current_title, current_body
        if current_title is not None:
            sections.append((current_title, "\n".join(current_body).strip("\n")))
        current_title = None
        current_body = []

    for line in lines:
        if line.startswith("\\"):
            if current_title is not None:
                current_body.append(line)
            continue
        m = _H2_RE.match(line)
        if m:
            flush()
            current_title = m.group(1).strip()
            current_body = []
            continue
        if current_title is not None:
            current_body.append(line)
    flush()
    return sections


def validate_heading_structure(text: str) -> tuple[list[str], list[str], list[str]]:
    """T6 + P1 structural validation.

    Returns (errors, warnings, recognized_present_in_order).
    """
    errors: list[str] = []
    warnings: list[str] = []
    headings = extract_h2_headings(text)
    recognized_index = {name: i for i, name in enumerate(RECOGNIZED_HEADINGS)}

    counts: dict[str, int] = {}
    recognized_order: list[str] = []
    for _lineno, title in headings:
        if title in recognized_index:
            counts[title] = counts.get(title, 0) + 1
            recognized_order.append(title)

    for required in sorted(REQUIRED_EXACTLY_ONCE):
        n = counts.get(required, 0)
        if n == 0:
            errors.append(f"missing required heading '## {required}' (must occur exactly once)")
        elif n > 1:
            errors.append(
                f"duplicate required heading '## {required}' (found {n}; must occur exactly once)"
            )

    for title, n in counts.items():
        if title in REQUIRED_EXACTLY_ONCE:
            continue
        if n > 1:
            errors.append(
                f"duplicate recognized heading '## {title}' (found {n}; at most once allowed)"
            )

    # Canonical order among recognized headings that appear (each first occurrence).
    last_index = -1
    present_in_order: list[str] = []
    seen_for_order: set[str] = set()
    for title in recognized_order:
        if title in seen_for_order:
            continue  # duplicates already errored
        seen_for_order.add(title)
        present_in_order.append(title)
        idx = recognized_index[title]
        if idx < last_index:
            errors.append(
                f"recognized heading '## {title}' is out of canonical order "
                f"(expected order: {', '.join(RECOGNIZED_HEADINGS)})"
            )
            break
        last_index = idx

    # Missing non-critical recognized sections → warnings only (P1).
    for name in RECOGNIZED_HEADINGS:
        if name in REQUIRED_EXACTLY_ONCE:
            continue
        if name == "Continuity Tail":
            continue  # optional by design
        if name not in counts:
            warnings.append(f"missing optional section '## {name}'")

    return errors, warnings, present_in_order


def _parse_header_bullets(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in body.splitlines():
        m = _HEADER_FIELD_RE.match(line.strip())
        if not m:
            continue
        key = m.group(1).strip().lower()
        value = m.group(2).strip()
        fields[key] = value
    return fields


def _parse_reality_checks(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in body.splitlines():
        m = _HEADER_FIELD_RE.match(line.strip())
        if not m:
            continue
        key = m.group(1).strip().lower()
        value = m.group(2).strip()
        fields[key] = value
    return fields


def _is_fallback_line(content: str) -> bool:
    normalized = _normalize_fallback_text(content)
    fallback_norm = {_normalize_fallback_text(s) for s in FALLBACK_SECTION_STRINGS}
    fallback_norm |= {s.rstrip(".") for s in fallback_norm}
    return normalized in fallback_norm or normalized.rstrip(".") in fallback_norm


def extract_real_bullets(body: str) -> list[str]:
    """Non-fallback ``-`` / ``*`` bullets from a section body (P2).

    Numbered lists and free prose are ignored — crystals use list bullets for
    Tests And Verification / Open Loops. Never used for Resume Prompt (T3).
    """
    if is_fallback_body(body):
        return []
    bullets: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        m = _BULLET_RE.match(stripped)
        if not m:
            continue
        content = m.group(1).strip()
        if not content or _is_fallback_line(content):
            continue
        bullets.append(content)
    return bullets


def count_real_test_bullets(body: str) -> int:
    """Count non-fallback bullets under Tests And Verification (P2)."""
    return len(extract_real_bullets(body))


def parse_crystal(text: str, path: str | Path | None = None) -> CrystalParseResult:
    """Validate structure and extract Header / Reality Checks metadata.

    On structural corruption (T6), ``ok`` is False and no ledger write should
    proceed. Metadata fields may still be partially filled for diagnostics.
    """
    result = CrystalParseResult(ok=True)
    errors, warnings, present = validate_heading_structure(text)
    result.errors = errors
    result.warnings = warnings
    result.sections_present = present
    if errors:
        result.ok = False

    sections = {title: body for title, body in split_sections(text)}

    header_body = sections.get("Header", "")
    header_fields = _parse_header_bullets(header_body)
    result.project = header_fields.get("project") or None
    result.observed_at = header_fields.get("observed at") or None
    result.source_window = header_fields.get("source window") or None

    reality_body = sections.get("Reality Checks", "")
    reality = _parse_reality_checks(reality_body)
    result.git_commit = reality.get("git commit") or None
    result.git_branch = reality.get("git branch") or None
    result.git_root = reality.get("git root") or None

    tests_body = sections.get("Tests And Verification", "")
    result.test_bullets = extract_real_bullets(tests_body)
    result.test_bullet_count = len(result.test_bullets)

    open_loops_body = sections.get("Open Loops", "")
    result.open_loop_bullets = extract_real_bullets(open_loops_body)

    result.kind = infer_crystal_kind(path, result.source_window)
    return result


def load_and_parse_crystal(path: str | Path) -> CrystalParseResult:
    """Read a local crystal file as UTF-8 text and parse (no execution)."""
    path = Path(path)
    try:
        # utf-8-sig tolerates BOM; errors=strict rejects binary garbage.
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return CrystalParseResult(ok=False, errors=[f"crystal file not found: {path}"])
    except OSError as exc:
        return CrystalParseResult(ok=False, errors=[f"could not read crystal file: {exc}"])
    except UnicodeDecodeError as exc:
        return CrystalParseResult(
            ok=False, errors=[f"crystal file is not valid UTF-8 text: {exc}"]
        )
    return parse_crystal(text, path=path)
