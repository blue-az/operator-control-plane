"""Live Pi harness identity at documentation / crystal capture time.

GitHub #16 / docs/ISSUE_REQUEST_pi-model-provenance-autocheck.md.

Environment fields are provenance metadata for *this capture*, not evidence
that the same model authored every prior turn. Missing values are ``unknown``.
Secrets never belong in the returned dict.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any, Mapping

SAFE_ENV_KEYS = ("PI_PROVIDER", "PI_MODEL", "PI_SESSION_ID", "PI_CODING_AGENT_VERSION")
SECRET_NAME_RE = re.compile(
    r"(api[_-]?key|token|secret|password|passwd|authorization|cookie|bearer|credential)",
    re.IGNORECASE,
)
SECRET_VALUE_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,}|Bearer\s+\S+|gh[pousr]_[A-Za-z0-9]{8,}"
    r"|xox[baprs]-[A-Za-z0-9-]{8,}|eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,})",
    re.IGNORECASE,
)


def _utc_now(now: datetime | None = None) -> str:
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def redact_value(value: str) -> str:
    if not value:
        return value
    if SECRET_VALUE_RE.search(value):
        return "redacted"
    if len(value) > 200:
        return "redacted"
    return value


def _read_safe(env: Mapping[str, str], key: str) -> str:
    if SECRET_NAME_RE.search(key):
        return "redacted"
    raw = env.get(key)
    if raw is None or not str(raw).strip():
        return "unknown"
    return redact_value(str(raw).strip())


def capture_live_pi_identity(
    *,
    claimed_provider: str | None = None,
    claimed_model: str | None = None,
    environ: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return additive provenance. Never copies the full environment."""
    env = os.environ if environ is None else environ
    observed_provider = _read_safe(env, "PI_PROVIDER")
    observed_model = _read_safe(env, "PI_MODEL")
    observed_session = _read_safe(env, "PI_SESSION_ID")
    harness_version = _read_safe(env, "PI_CODING_AGENT_VERSION")

    claimed: dict[str, str] = {}
    if claimed_provider:
        claimed["provider"] = redact_value(claimed_provider.strip())
    if claimed_model:
        claimed["model"] = redact_value(claimed_model.strip())

    mismatches: list[dict[str, str]] = []
    if claimed_provider and observed_provider != "unknown":
        if claimed["provider"] != observed_provider:
            mismatches.append(
                {
                    "field": "provider",
                    "claimed": claimed["provider"],
                    "observed": observed_provider,
                }
            )
    if claimed_model and observed_model != "unknown":
        if claimed["model"] != observed_model:
            mismatches.append(
                {
                    "field": "model",
                    "claimed": claimed["model"],
                    "observed": observed_model,
                }
            )

    payload: dict[str, Any] = {
        "captured_at": _utc_now(now),
        "harness": "pi",
        "harness_version": harness_version,
        "observed": {
            "provider": observed_provider,
            "model": observed_model,
            "session_id": observed_session,
        },
        "note": (
            "Provenance at capture time only; not evidence that this identity "
            "authored every prior turn."
        ),
    }
    if claimed:
        payload["claimed"] = claimed
    if mismatches:
        payload["mismatch"] = mismatches
    return payload


def format_mismatch_warning(identity: Mapping[str, Any]) -> str | None:
    mismatches = identity.get("mismatch") or []
    if not mismatches:
        return None
    parts = [
        f"{row['field']}: claimed {row['claimed']!r} observed {row['observed']!r}"
        for row in mismatches
        if isinstance(row, dict)
    ]
    if not parts:
        return None
    return (
        "live Pi identity differs from claimed label ("
        + "; ".join(parts)
        + "); both recorded, capture-time only"
    )


def contains_secret_material(payload: Mapping[str, Any] | str) -> bool:
    blob = payload if isinstance(payload, str) else repr(payload)
    return bool(SECRET_VALUE_RE.search(blob))
