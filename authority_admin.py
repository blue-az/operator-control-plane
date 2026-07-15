#!/usr/bin/python3 -I
"""Root-managed installation and policy lifecycle for the authority broker."""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import errno
import fcntl
import grp
import hashlib
import json
import os
import pwd
import re
import sqlite3
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator

import authority_broker as broker

POLICY_SCHEMA_VERSION = 1
INSTALL_SCHEMA_VERSION = 1
ACTIVE_INDEX_SCHEMA_VERSION = 1
MAX_ADMIN_FILE_BYTES = 1024 * 1024
MAX_CHILD_RESULT_BYTES = 4 * 1024 * 1024
DEFAULT_BROKER_USER = "operator-broker"
DEFAULT_SOCKET_GROUP = "operator-clients"
REGISTRY_PATH = Path("/etc/operator-control-plane-registry.json")
SYSTEM_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,63}")
POLICY_FIELDS = {
    "policy_schema_version",
    "policy_id",
    "ledger_id",
    "policy_generation",
    "previous_policy_sha256",
    "mode",
    "uid_names",
    "roles",
}
INSTALLED_SOURCE_ASSETS = {
    "authority_broker.py": 0o644,
    "authority_admin.py": 0o644,
    "operator-admin": 0o755,
    "socket_permission_helper.py": 0o644,
}
PREFLIGHT_CHECK_IDS = (
    "identity.admin_root",
    "identity.broker_binding",
    "identity.broker_account_properties",
    "identity.agent_uids_distinct",
    "identity.agents_outside_broker_group",
    "identity.socket_group_membership",
    "assets.protected_paths",
    "assets.extended_acl_visibility",
    "sudo.authorization",
    "sudo.cached_credentials",
    "polkit.authorization",
    "container.management_groups",
    "container.privileged_sockets",
    "service.delegated_control",
    "service.unit_writability",
    "mount.redirection",
    "capabilities.setuid_helpers",
    "process.control",
    "credentials.delegation",
    "broker.live_process",
)
RISKY_GROUPS = frozenset(
    {"adm", "docker", "incus-admin", "libvirt", "lxd", "podman", "root", "sudo", "wheel"}
)
PRIVILEGED_SOCKETS = (
    Path("/run/docker.sock"),
    Path("/var/run/docker.sock"),
    Path("/run/podman/podman.sock"),
    Path("/run/libvirt/libvirt-sock"),
    Path("/var/lib/lxd/unix.socket"),
    Path("/var/lib/incus/unix.socket"),
    Path("/run/containerd/containerd.sock"),
    Path("/run/crio/crio.sock"),
)
EVIDENCE_SCHEMA_VERSION = 1
EVIDENCE_MAX_AGE_SECONDS = 24 * 60 * 60
EVIDENCE_CHECK_IDS = (
    "identity.broker_account_properties",
    "assets.extended_acl_visibility",
    "sudo.cached_credentials",
    "polkit.authorization",
    "service.delegated_control",
    "service.unit_writability",
    "mount.redirection",
    "capabilities.setuid_helpers",
    "process.control",
    "credentials.delegation",
)
EVIDENCE_UNKNOWN_MESSAGES = {
    "identity.broker_account_properties": (
        "locked credentials, login shell, supplementary privileges, sudo, and polkit "
        "require issue #7 host evidence"
    ),
    "assets.extended_acl_visibility": (
        "mode, owner, link, inode, and traversal checks passed; ACL and mount "
        "evidence remains issue #7"
    ),
    "sudo.cached_credentials": "cached and delegated credentials require issue #7 observation",
    "polkit.authorization": "polkit rules and active agents require issue #7 observation",
    "service.delegated_control": (
        "sudo, polkit, D-Bus, and service delegation require issue #7 adjudication"
    ),
    "service.unit_writability": "drop-ins, generators, and alternate service-control paths",
    "mount.redirection": "bind mounts, namespaces, FUSE, and mount capabilities require issue #7",
    "capabilities.setuid_helpers": "system capabilities and setuid helpers require issue #7",
    "process.control": "ptrace and live process control require issue #7",
    "credentials.delegation": "delegated credentials and authentication agents require issue #7",
}
NOLOGIN_SHELLS = frozenset({"/usr/sbin/nologin", "/sbin/nologin", "/bin/false", "/usr/bin/false"})
SHADOW_PATH = Path("/etc/shadow")
SUDO_TIMESTAMP_DIRS = (
    Path("/run/sudo/ts"),
    Path("/var/run/sudo/ts"),
    Path("/var/db/sudo/ts"),
)
POLKIT_RULE_DIRS = (Path("/etc/polkit-1/rules.d"), Path("/usr/share/polkit-1/rules.d"))
DBUS_SYSTEM_POLICY_DIRS = (Path("/etc/dbus-1/system.d"), Path("/usr/share/dbus-1/system.d"))
CAPABILITY_SCAN_ROOTS = (Path("/usr/local/bin"), Path("/usr/local/sbin"), Path("/opt"))
KNOWN_SAFE_SETUID_HELPERS = frozenset(
    {
        "/opt/google/chrome/chrome-sandbox",
    }
)
DANGEROUS_CAPABILITIES = (
    "cap_setuid",
    "cap_setgid",
    "cap_sys_admin",
    "cap_dac_override",
    "cap_sys_ptrace",
    "cap_net_admin",
    "cap_chown",
    "cap_fowner",
)
RENAME_NOREPLACE = 1
LIBC = ctypes.CDLL(None, use_errno=True)


class AdminError(Exception):
    def __init__(self, code: str, message: str, **details: object) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def as_dict(self) -> dict:
        result = {"code": self.code, "message": self.message}
        if self.details:
            result["details"] = self.details
        return result


@dataclass(frozen=True)
class InstallLayout:
    anchor: Path
    install_root: Path
    config_root: Path
    state_root: Path
    runtime_root: Path
    unit_path: Path
    tmpfiles_path: Path

    @classmethod
    def production(cls) -> InstallLayout:
        return cls(
            anchor=Path("/"),
            install_root=Path("/usr/libexec/operator-control-plane"),
            config_root=Path("/etc/operator-control-plane"),
            state_root=Path("/var/lib/operator-control-plane"),
            runtime_root=Path("/run/operator-control-plane"),
            unit_path=Path("/etc/systemd/system/operator-control-plane-broker.service"),
            tmpfiles_path=Path("/etc/tmpfiles.d/operator-control-plane.conf"),
        )

    @classmethod
    def under(cls, root: Path) -> InstallLayout:
        root = root.resolve()
        return cls(
            anchor=root,
            install_root=root / "usr/libexec/operator-control-plane",
            config_root=root / "etc/operator-control-plane",
            state_root=root / "var/lib/operator-control-plane",
            runtime_root=root / "run/operator-control-plane",
            unit_path=root / "etc/systemd/system/operator-control-plane-broker.service",
            tmpfiles_path=root / "etc/tmpfiles.d/operator-control-plane.conf",
        )

    @property
    def database_path(self) -> Path:
        return self.state_root / "authority.sqlite3"

    @property
    def content_root(self) -> Path:
        return self.state_root / "content"

    @property
    def socket_path(self) -> Path:
        return self.runtime_root / "broker.sock"

    @property
    def manifest_path(self) -> Path:
        return self.config_root / "install.json"

    @property
    def active_path(self) -> Path:
        return self.config_root / "active.json"

    @property
    def lock_path(self) -> Path:
        return self.config_root / ".admin.lock"

    @property
    def policies_root(self) -> Path:
        return self.config_root / "policies"

    @property
    def revocations_root(self) -> Path:
        return self.config_root / "revocations"

    @property
    def evidence_path(self) -> Path:
        return self.config_root / "privilege-evidence.json"


@dataclass(frozen=True)
class DeploymentIdentity:
    admin_uid: int
    admin_gid: int
    broker_user: str
    broker_uid: int
    broker_gid: int
    socket_group: str
    socket_gid: int


@dataclass(frozen=True)
class PolicyDocument:
    policy_id: str
    ledger_id: str
    generation: int
    previous_sha256: str | None
    uid_names: dict[int, str]
    roles: dict[int, frozenset[str]]
    canonical_json: str
    sha256: str

    def as_object(self) -> dict:
        return broker.decode_json(self.canonical_json.encode("ascii"))


def require_root() -> None:
    if os.getuid() != 0 or os.geteuid() != 0:
        raise AdminError("root_required", "operator-admin requires real and effective UID 0")


def require_exact_keys(value: dict, expected: set[str], context: str) -> None:
    missing = expected - set(value)
    unknown = set(value) - expected
    if missing:
        raise AdminError("missing_field", f"{context} is missing: {', '.join(sorted(missing))}")
    if unknown:
        raise AdminError("unknown_field", f"{context} has unknown: {', '.join(sorted(unknown))}")


def require_token(value: object, field: str) -> str:
    try:
        return broker.require_token(value, field)
    except broker.BrokerError as exc:
        raise AdminError("invalid_policy", exc.message) from exc


def require_sha256(value: object, field: str) -> str:
    try:
        return broker.require_sha256(value, field)
    except broker.BrokerError as exc:
        raise AdminError("invalid_policy", exc.message) from exc


def parse_policy_object(raw: object) -> PolicyDocument:
    if not isinstance(raw, dict):
        raise AdminError("invalid_policy", "policy must be a JSON object")
    require_exact_keys(raw, POLICY_FIELDS, "policy")
    if raw["policy_schema_version"] != POLICY_SCHEMA_VERSION:
        raise AdminError("unsupported_policy_schema", "unsupported policy schema")
    policy_id = require_token(raw["policy_id"], "policy_id")
    ledger_id = require_token(raw["ledger_id"], "ledger_id")
    generation = raw["policy_generation"]
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
        raise AdminError("invalid_policy", "policy_generation must be a positive integer")
    previous = raw["previous_policy_sha256"]
    if generation == 1:
        if previous is not None:
            raise AdminError("invalid_policy", "generation 1 requires a null previous digest")
    else:
        previous = require_sha256(previous, "previous_policy_sha256")
    if raw["mode"] != "enforced":
        raise AdminError("invalid_policy", "external policy mode must be enforced")
    names = raw["uid_names"]
    role_map = raw["roles"]
    if not isinstance(names, dict) or not names or not isinstance(role_map, dict):
        raise AdminError("invalid_policy", "uid_names and roles must be non-empty mappings")
    if set(names) != set(role_map):
        raise AdminError("invalid_policy", "uid_names and roles must contain identical UIDs")
    normalized_names: dict[int, str] = {}
    normalized_roles: dict[int, frozenset[str]] = {}
    for raw_uid, name in names.items():
        if not isinstance(raw_uid, str) or not raw_uid.isdigit() or str(int(raw_uid)) != raw_uid:
            raise AdminError("invalid_policy", "policy UIDs must be canonical numeric strings")
        uid = int(raw_uid)
        if uid <= 0 or not isinstance(name, str) or not SYSTEM_NAME.fullmatch(name):
            raise AdminError("invalid_policy", f"invalid UID/name entry: {raw_uid}")
        roles = role_map[raw_uid]
        if (
            not isinstance(roles, list)
            or not roles
            or any(not isinstance(role, str) for role in roles)
            or len(roles) != len(set(roles))
        ):
            raise AdminError("invalid_policy", f"invalid roles for UID {uid}")
        role_set = frozenset(roles)
        if role_set - broker.VALID_ROLES:
            raise AdminError("invalid_policy", f"unknown role for UID {uid}")
        normalized_names[uid] = name
        normalized_roles[uid] = role_set
    builders = {uid for uid, roles in normalized_roles.items() if "builder" in roles}
    verifiers = {uid for uid, roles in normalized_roles.items() if "verifier" in roles}
    if not builders or not verifiers or not any(a != b for a in builders for b in verifiers):
        raise AdminError("invalid_policy", "policy requires distinct builder and verifier UIDs")
    normalized = {
        "policy_schema_version": POLICY_SCHEMA_VERSION,
        "policy_id": policy_id,
        "ledger_id": ledger_id,
        "policy_generation": generation,
        "previous_policy_sha256": previous,
        "mode": "enforced",
        "uid_names": {str(uid): normalized_names[uid] for uid in sorted(normalized_names)},
        "roles": {str(uid): sorted(normalized_roles[uid]) for uid in sorted(normalized_roles)},
    }
    canonical = broker.canonical_json(normalized)
    return PolicyDocument(
        policy_id,
        ledger_id,
        generation,
        previous,
        normalized_names,
        normalized_roles,
        canonical,
        broker.sha256_text(canonical),
    )


def read_limited_fd(fd: int, limit: int = MAX_ADMIN_FILE_BYTES) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(fd, min(65536, limit + 1 - total))
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        total += len(chunk)
        if total > limit:
            raise AdminError("file_too_large", f"file exceeds {limit} bytes")


def read_input_file(path: Path, owner_uid: int, context: str, limit: int) -> bytes:
    if not path.is_absolute():
        raise AdminError("invalid_path", f"{context} path must be absolute")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise AdminError("input_unavailable", f"could not open {context}: {exc}") from exc
    try:
        metadata = os.fstat(fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != owner_uid
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            raise AdminError("unsafe_input", f"{context} is not administrator-controlled")
        return read_limited_fd(fd, limit)
    finally:
        os.close(fd)


def read_policy_file(path: Path, owner_uid: int) -> PolicyDocument:
    data = read_input_file(path, owner_uid, "policy", MAX_ADMIN_FILE_BYTES)
    try:
        return parse_policy_object(broker.decode_json(data))
    except broker.BrokerError as exc:
        raise AdminError("invalid_policy", exc.message) from exc


def relative_parts(path: Path, anchor: Path) -> tuple[str, ...]:
    if not path.is_absolute() or not anchor.is_absolute():
        raise AdminError("invalid_path", "protected paths must be absolute")
    try:
        return path.relative_to(anchor).parts
    except ValueError as exc:
        raise AdminError("invalid_path", f"path escapes installation anchor: {path}") from exc


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def expected_directory_owner(
    path: Path, layout: InstallLayout, identity: DeploymentIdentity
) -> int:
    if is_within(path, layout.state_root) or is_within(path, layout.runtime_root):
        return identity.broker_uid
    return identity.admin_uid


def validate_directory(metadata: os.stat_result, path: Path, expected_uid: int) -> None:
    if not stat.S_ISDIR(metadata.st_mode):
        raise AdminError("unsafe_path_type", f"expected directory: {path}")
    if metadata.st_uid != expected_uid:
        raise AdminError("unsafe_path_owner", f"wrong directory owner: {path}")
    if stat.S_IMODE(metadata.st_mode) & 0o022:
        raise AdminError("unsafe_path_permissions", f"writable directory ancestor: {path}")


@contextlib.contextmanager
def open_layout_directory(
    path: Path, layout: InstallLayout, identity: DeploymentIdentity
) -> Iterator[int]:
    parts = relative_parts(path, layout.anchor)
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(layout.anchor, flags)
    current = layout.anchor
    try:
        validate_directory(
            os.fstat(fd), current, expected_directory_owner(current, layout, identity)
        )
        for part in parts:
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
            current /= part
            validate_directory(
                os.fstat(fd), current, expected_directory_owner(current, layout, identity)
            )
        yield fd
    except OSError as exc:
        raise AdminError("unsafe_path", f"could not traverse {path}: {exc}") from exc
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


@contextlib.contextmanager
def open_admin_directory(path: Path, anchor: Path, admin_uid: int) -> Iterator[int]:
    parts = relative_parts(path, anchor)
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(anchor, flags)
    current = anchor
    try:
        validate_directory(os.fstat(fd), current, admin_uid)
        for part in parts:
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
            current /= part
            validate_directory(os.fstat(fd), current, admin_uid)
        yield fd
    except OSError as exc:
        raise AdminError("unsafe_path", f"could not traverse {path}: {exc}") from exc
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def expected_directory_gid(path: Path, layout: InstallLayout, identity: DeploymentIdentity) -> int:
    if is_within(path, layout.runtime_root):
        return identity.socket_gid
    if is_within(path, layout.state_root):
        return identity.broker_gid
    return identity.admin_gid


def ensure_parent_tree(path: Path, layout: InstallLayout, identity: DeploymentIdentity) -> None:
    parts = relative_parts(path, layout.anchor)
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(layout.anchor, flags)
    current = layout.anchor
    try:
        validate_directory(
            os.fstat(fd), current, expected_directory_owner(current, layout, identity)
        )
        for part in parts:
            next_path = current / part
            try:
                next_fd = os.open(part, flags, dir_fd=fd)
            except FileNotFoundError:
                os.mkdir(part, 0o700, dir_fd=fd)
                next_fd = os.open(part, flags, dir_fd=fd)
                os.fchown(
                    next_fd,
                    expected_directory_owner(next_path, layout, identity),
                    expected_directory_gid(next_path, layout, identity),
                )
                os.fchmod(next_fd, 0o700)
                linked = os.stat(part, dir_fd=fd, follow_symlinks=False)
                opened = os.fstat(next_fd)
                if (linked.st_dev, linked.st_ino) != (opened.st_dev, opened.st_ino):
                    raise AdminError("path_race", f"directory changed during creation: {next_path}")
                os.fsync(next_fd)
                os.fsync(fd)
            os.close(fd)
            fd = next_fd
            current = next_path
            validate_directory(
                os.fstat(fd), current, expected_directory_owner(current, layout, identity)
            )
    except OSError as exc:
        raise AdminError("unsafe_path", f"could not prepare {path}: {exc}") from exc
    finally:
        os.close(fd)


def ensure_directory(
    path: Path,
    mode: int,
    uid: int,
    gid: int,
    layout: InstallLayout,
    identity: DeploymentIdentity,
) -> None:
    ensure_parent_tree(path.parent, layout, identity)
    with open_layout_directory(path.parent, layout, identity) as parent_fd:
        flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            child_fd = os.open(path.name, flags, dir_fd=parent_fd)
        except FileNotFoundError:
            os.mkdir(path.name, mode, dir_fd=parent_fd)
            child_fd = os.open(path.name, flags, dir_fd=parent_fd)
            os.fchown(child_fd, uid, gid)
            os.fchmod(child_fd, mode)
            os.fsync(child_fd)
            os.fsync(parent_fd)
        try:
            metadata = os.fstat(child_fd)
            linked = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
            if (
                (metadata.st_dev, metadata.st_ino) != (linked.st_dev, linked.st_ino)
                or metadata.st_uid != uid
                or metadata.st_gid != gid
                or stat.S_IMODE(metadata.st_mode) != mode
            ):
                raise AdminError("unsafe_path_metadata", f"directory metadata differs: {path}")
        finally:
            os.close(child_fd)


def write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        count = os.write(fd, view)
        if count <= 0:
            raise AdminError("short_write", "could not write complete file")
        view = view[count:]


def open_regular_at(parent_fd: int, name: str, limit: int) -> tuple[int, bytes, os.stat_result]:
    before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise AdminError("unsafe_path_type", f"unsafe protected file: {name}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(name, flags, dir_fd=parent_fd)
    try:
        metadata = os.fstat(fd)
        if (
            (before.st_dev, before.st_ino) != (metadata.st_dev, metadata.st_ino)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
        ):
            raise AdminError("unsafe_path_type", f"unsafe protected file: {name}")
        data = read_limited_fd(fd, limit)
    except Exception:
        os.close(fd)
        raise
    return fd, data, metadata


def rename_noreplace(parent_fd: int, source: str, destination: str) -> None:
    function = getattr(LIBC, "renameat2", None)
    if function is None:
        raise AdminError("atomic_publish_unavailable", "renameat2 is required")
    result = function(
        ctypes.c_int(parent_fd),
        ctypes.c_char_p(os.fsencode(source)),
        ctypes.c_int(parent_fd),
        ctypes.c_char_p(os.fsencode(destination)),
        ctypes.c_uint(RENAME_NOREPLACE),
    )
    if result != 0:
        error = ctypes.get_errno()
        if error == errno.EEXIST:
            raise FileExistsError(destination)
        raise OSError(error, os.strerror(error))


def remove_stale_pending(
    parent_fd: int, name: str, expected: bytes, uid: int, gid: int, mode: int
) -> None:
    try:
        fd, existing, metadata = open_regular_at(parent_fd, name, len(expected) + 1)
    except FileNotFoundError:
        return
    try:
        if (
            existing != expected
            or metadata.st_uid != uid
            or metadata.st_gid != gid
            or stat.S_IMODE(metadata.st_mode) != mode
        ):
            raise AdminError("unsafe_pending_file", f"pending file metadata differs: {name}")
    finally:
        os.close(fd)
    os.unlink(name, dir_fd=parent_fd)
    os.fsync(parent_fd)


def write_protected_file(
    path: Path,
    data: bytes,
    mode: int,
    uid: int,
    gid: int,
    layout: InstallLayout,
    identity: DeploymentIdentity,
    *,
    replace: bool = False,
    fault: Callable[[str, Path], None] | None = None,
) -> None:
    with open_layout_directory(path.parent, layout, identity) as parent_fd:
        try:
            fd, existing, metadata = open_regular_at(parent_fd, path.name, len(data) + 1)
        except FileNotFoundError:
            fd = -1
            existing = None
            metadata = None
        if existing is not None and not replace:
            try:
                if (
                    existing != data
                    or metadata is None
                    or metadata.st_uid != uid
                    or metadata.st_gid != gid
                    or stat.S_IMODE(metadata.st_mode) != mode
                ):
                    raise AdminError("protected_file_conflict", f"protected file differs: {path}")
                os.fsync(fd)
                os.fsync(parent_fd)
            finally:
                os.close(fd)
            return
        if fd >= 0:
            os.close(fd)

        pending = f".{path.name}.pending"
        remove_stale_pending(parent_fd, pending, data, uid, gid, mode)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        temp_fd = os.open(pending, flags, mode, dir_fd=parent_fd)
        try:
            os.fchown(temp_fd, uid, gid)
            os.fchmod(temp_fd, mode)
            write_all(temp_fd, data)
            os.fsync(temp_fd)
            if fault:
                fault("after_file_fsync", path)
        finally:
            os.close(temp_fd)
        try:
            if replace:
                os.replace(pending, path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            else:
                rename_noreplace(parent_fd, pending, path.name)
            if fault:
                fault("after_publish", path)
            os.fsync(parent_fd)
        except FileExistsError:
            os.unlink(pending, dir_fd=parent_fd)
            os.fsync(parent_fd)
            fd, existing, metadata = open_regular_at(parent_fd, path.name, len(data) + 1)
            try:
                if (
                    existing != data
                    or metadata.st_uid != uid
                    or metadata.st_gid != gid
                    or stat.S_IMODE(metadata.st_mode) != mode
                ):
                    raise AdminError("protected_file_conflict", f"protected file differs: {path}")
                os.fsync(fd)
                os.fsync(parent_fd)
            finally:
                os.close(fd)
        except Exception:
            # A simulated process crash intentionally leaves the validated pending file.
            if not isinstance(sys.exc_info()[1], RuntimeError):
                try:
                    os.unlink(pending, dir_fd=parent_fd)
                    os.fsync(parent_fd)
                except OSError:
                    pass
            raise


def read_protected_file(
    path: Path,
    mode: int,
    uid: int,
    gid: int,
    layout: InstallLayout,
    identity: DeploymentIdentity,
) -> bytes:
    with open_layout_directory(path.parent, layout, identity) as parent_fd:
        try:
            fd, data, metadata = open_regular_at(parent_fd, path.name, MAX_ADMIN_FILE_BYTES)
        except FileNotFoundError as exc:
            raise AdminError("protected_file_missing", f"protected file missing: {path}") from exc
        try:
            if (
                metadata.st_uid != uid
                or metadata.st_gid != gid
                or stat.S_IMODE(metadata.st_mode) != mode
            ):
                raise AdminError("unsafe_path_metadata", f"file metadata differs: {path}")
            return data
        finally:
            os.close(fd)


def json_bytes(value: object) -> bytes:
    return (broker.canonical_json(value) + "\n").encode("ascii")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode_canonical(data: bytes, context: str) -> dict:
    try:
        value = broker.decode_json(data)
    except broker.BrokerError as exc:
        raise AdminError("invalid_admin_state", f"{context}: {exc.message}") from exc
    if not isinstance(value, dict) or data != json_bytes(value):
        raise AdminError("invalid_admin_state", f"{context} is not canonical JSON")
    return value


def policy_path(layout: InstallLayout, policy: PolicyDocument) -> Path:
    return (
        layout.policies_root / policy.ledger_id / f"{policy.generation:020d}-{policy.sha256}.json"
    )


def revoke_path(layout: InstallLayout, ledger_id: str, digest: str) -> Path:
    return layout.revocations_root / ledger_id / f"revoke-{digest}.json"


def active_index(event: dict) -> dict:
    return {
        "active_index_schema_version": ACTIVE_INDEX_SCHEMA_VERSION,
        "authority": "ledger_policy_events",
        "ledger_id": event["ledger_id"],
        "state": "revoked" if event["event_type"] == "revoke" else "active",
        "policy_id": event["policy_id"],
        "policy_generation": event["generation"],
        "policy_sha256": event["policy_sha256"],
        "policy_event_hash": event["event_hash"],
    }


def group_ids(account: pwd.struct_passwd) -> set[int]:
    try:
        return set(os.getgrouplist(account.pw_name, account.pw_gid))
    except OSError as exc:
        raise AdminError(
            "identity_lookup_failed",
            f"could not enumerate groups for {account.pw_name}: {exc}",
        ) from exc


def validate_identity_binding(identity: DeploymentIdentity) -> None:
    try:
        account = pwd.getpwnam(identity.broker_user)
        socket_group = grp.getgrnam(identity.socket_group)
    except KeyError as exc:
        raise AdminError("identity_binding_changed", f"broker account/group is missing: {exc}")
    if (
        account.pw_uid != identity.broker_uid
        or account.pw_gid != identity.broker_gid
        or socket_group.gr_gid != identity.socket_gid
    ):
        raise AdminError("identity_binding_changed", "broker account/group numeric binding changed")
    if identity.broker_uid == 0:
        raise AdminError("unsafe_broker_identity", "broker UID must not be root")
    if identity.broker_gid == identity.socket_gid:
        raise AdminError(
            "unsafe_socket_group", "socket group must differ from broker primary group"
        )
    validate_privileged_runtime()


def validate_root_owned_path(path: Path, *, executable: bool) -> None:
    if not path.is_absolute():
        raise AdminError("unsafe_privileged_runtime", "privileged runtime path is not absolute")
    resolved = Path(os.path.realpath(path))
    for candidate in (path, resolved):
        current = Path("/")
        for part in candidate.parts[1:]:
            current /= part
            metadata = current.lstat()
            if metadata.st_uid != 0:
                raise AdminError(
                    "unsafe_privileged_runtime",
                    f"privileged path is not root-owned: {current}",
                )
            if not stat.S_ISLNK(metadata.st_mode) and stat.S_IMODE(metadata.st_mode) & 0o022:
                raise AdminError(
                    "unsafe_privileged_runtime",
                    f"privileged path is group/other writable: {current}",
                )
    metadata = resolved.stat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink < 1
        or metadata.st_uid != 0
        or stat.S_IMODE(metadata.st_mode) & 0o022
        or (executable and not stat.S_IMODE(metadata.st_mode) & 0o111)
    ):
        raise AdminError(
            "unsafe_privileged_runtime",
            f"privileged executable metadata differs: {resolved}",
        )


def validate_privileged_runtime() -> None:
    validate_root_owned_path(Path("/usr/bin/python3"), executable=True)


def validate_host_accounts(policy: PolicyDocument, identity: DeploymentIdentity) -> None:
    validate_identity_binding(identity)
    for uid, expected_name in policy.uid_names.items():
        if uid in {0, identity.broker_uid}:
            raise AdminError("unsafe_agent_identity", f"unsafe agent UID: {uid}")
        try:
            account = pwd.getpwuid(uid)
        except KeyError as exc:
            raise AdminError("missing_account", f"policy UID does not exist: {uid}") from exc
        if account.pw_name != expected_name:
            raise AdminError("identity_binding_changed", f"policy UID/name binding changed: {uid}")
        memberships = group_ids(account)
        if identity.broker_gid in memberships:
            raise AdminError("unsafe_agent_identity", f"agent UID {uid} belongs to broker group")
        if identity.socket_gid not in memberships:
            raise AdminError("socket_access_missing", f"agent UID {uid} lacks socket access")


def resolve_identity(
    policy: PolicyDocument, broker_user: str, socket_group: str
) -> DeploymentIdentity:
    if not SYSTEM_NAME.fullmatch(broker_user) or not SYSTEM_NAME.fullmatch(socket_group):
        raise AdminError("invalid_account", "invalid broker account or socket group name")
    try:
        account = pwd.getpwnam(broker_user)
        group = grp.getgrnam(socket_group)
    except KeyError as exc:
        raise AdminError("missing_account", f"required account/group is missing: {exc}") from exc
    identity = DeploymentIdentity(
        0,
        0,
        account.pw_name,
        account.pw_uid,
        account.pw_gid,
        group.gr_name,
        group.gr_gid,
    )
    validate_host_accounts(policy, identity)
    return identity


def render_service(layout: InstallLayout, identity: DeploymentIdentity) -> bytes:
    helper = layout.install_root / "socket_permission_helper.py"
    lines = [
        "[Unit]",
        "Description=Operator Control Plane authority broker",
        "After=local-fs.target",
        "",
        "[Service]",
        "Type=simple",
        f"User={identity.broker_uid}",
        f"Group={identity.broker_gid}",
        f"SupplementaryGroups={identity.socket_gid}",
        "WorkingDirectory=/",
        "Environment=LANG=C",
        "UnsetEnvironment=PYTHONPATH PYTHONHOME PYTHONUSERBASE",
        "UMask=0077",
        (
            f"ExecStartPre=/usr/bin/python3 -I {helper} --remove-stale "
            f"--socket {layout.socket_path} --expected-gid {identity.socket_gid}"
        ),
        (
            f"ExecStart=/usr/bin/python3 -I {layout.install_root / 'authority_broker.py'} serve "
            f"--store {layout.database_path} --content-dir {layout.content_root} "
            f"--socket {layout.socket_path}"
        ),
        (
            f"ExecStartPost=/usr/bin/python3 -I {helper} --socket {layout.socket_path} "
            f"--expected-gid {identity.socket_gid}"
        ),
        "NoNewPrivileges=yes",
        "PrivateTmp=yes",
        "ProtectSystem=strict",
        "ProtectHome=yes",
        "ProtectKernelTunables=yes",
        "ProtectKernelModules=yes",
        "ProtectControlGroups=yes",
        "RestrictAddressFamilies=AF_UNIX",
        f"ReadWritePaths={layout.state_root} {layout.runtime_root}",
        "Restart=on-failure",
        "RestartSec=1s",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
        "",
    ]
    return "\n".join(lines).encode("ascii")


def render_tmpfiles(layout: InstallLayout, identity: DeploymentIdentity) -> bytes:
    return (f"d {layout.runtime_root} 2750 {identity.broker_uid} {identity.socket_gid} -\n").encode(
        "ascii"
    )


def ensure_layout(layout: InstallLayout, identity: DeploymentIdentity) -> None:
    directories = (
        (layout.install_root, 0o755, identity.admin_uid, identity.admin_gid),
        (layout.config_root, 0o700, identity.admin_uid, identity.admin_gid),
        (layout.policies_root, 0o700, identity.admin_uid, identity.admin_gid),
        (layout.revocations_root, 0o700, identity.admin_uid, identity.admin_gid),
        (layout.state_root, 0o700, identity.broker_uid, identity.broker_gid),
        (layout.content_root, 0o700, identity.broker_uid, identity.broker_gid),
        (layout.content_root / "sha256", 0o700, identity.broker_uid, identity.broker_gid),
        (layout.runtime_root, 0o2750, identity.broker_uid, identity.socket_gid),
    )
    for path, mode, uid, gid in directories:
        ensure_directory(path, mode, uid, gid, layout, identity)
    ensure_parent_tree(layout.unit_path.parent, layout, identity)
    ensure_parent_tree(layout.tmpfiles_path.parent, layout, identity)


def serialize_child_error(exc: Exception) -> dict:
    if isinstance(exc, AdminError):
        return {"ok": False, "error": exc.as_dict()}
    if isinstance(exc, broker.BrokerError):
        return {"ok": False, "error": {"code": exc.code, "message": exc.message}}
    return {"ok": False, "error": {"code": "broker_child_failed", "message": str(exc)}}


def run_as_broker(identity: DeploymentIdentity, callback: Callable[[], dict]) -> dict:
    if os.geteuid() == identity.broker_uid:
        old_umask = os.umask(0o077)
        try:
            return callback()
        finally:
            os.umask(old_umask)
    if os.geteuid() != 0:
        raise AdminError("root_required", "only root may enter the broker identity")
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(read_fd)
        try:
            os.setgroups([])
            os.setgid(identity.broker_gid)
            os.setuid(identity.broker_uid)
            os.umask(0o077)
            payload = {"ok": True, "result": callback()}
        except Exception as exc:
            payload = serialize_child_error(exc)
        data = broker.canonical_json(payload).encode("ascii")
        try:
            write_all(write_fd, data)
        finally:
            os.close(write_fd)
        os._exit(0 if payload["ok"] else 1)
    os.close(write_fd)
    data = b""
    status = None
    read_error: Exception | None = None
    try:
        data = read_limited_fd(read_fd, MAX_CHILD_RESULT_BYTES)
    except Exception as exc:
        read_error = exc
    finally:
        os.close(read_fd)
        _, status = os.waitpid(pid, 0)
    if read_error:
        raise read_error
    try:
        payload = broker.decode_json(data)
    except broker.BrokerError as exc:
        raise AdminError("broker_child_failed", "broker child returned invalid JSON") from exc
    if not isinstance(payload, dict) or not payload.get("ok"):
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        raise AdminError(
            str(error.get("code", "broker_child_failed")),
            str(error.get("message", "broker child failed")),
        )
    if status is None or not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
        raise AdminError("broker_child_failed", "broker child exited unexpectedly")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise AdminError("broker_child_failed", "broker child returned no result")
    return result


def validate_exact_directory(
    path: Path,
    mode: int,
    uid: int,
    gid: int,
    layout: InstallLayout,
    identity: DeploymentIdentity,
) -> None:
    with open_layout_directory(path, layout, identity) as fd:
        metadata = os.fstat(fd)
        if (
            metadata.st_uid != uid
            or metadata.st_gid != gid
            or stat.S_IMODE(metadata.st_mode) != mode
        ):
            raise AdminError("unsafe_path_metadata", f"directory metadata differs: {path}")


def validate_store_boundary(
    layout: InstallLayout,
    identity: DeploymentIdentity,
    *,
    require_database: bool,
) -> dict[str, tuple[int, int] | None]:
    validate_exact_directory(
        layout.state_root, 0o700, identity.broker_uid, identity.broker_gid, layout, identity
    )
    validate_exact_directory(
        layout.content_root, 0o700, identity.broker_uid, identity.broker_gid, layout, identity
    )
    validate_exact_directory(
        layout.content_root / "sha256",
        0o700,
        identity.broker_uid,
        identity.broker_gid,
        layout,
        identity,
    )
    identities: dict[str, tuple[int, int] | None] = {}
    with open_layout_directory(layout.state_root, layout, identity) as state_fd:
        for name, required in (
            (layout.database_path.name, require_database),
            (layout.database_path.name + "-wal", False),
            (layout.database_path.name + "-shm", False),
            (layout.database_path.name + "-journal", False),
        ):
            try:
                before = os.stat(name, dir_fd=state_fd, follow_symlinks=False)
            except FileNotFoundError:
                if required:
                    raise AdminError("store_unavailable", "authority database is missing")
                identities[name] = None
                continue
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise AdminError("unsafe_store_path", f"unsafe authority store file: {name}")
            if name.endswith("-journal"):
                raise AdminError(
                    "unsafe_store_path", "rollback journal is forbidden for the WAL authority store"
                )
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(name, flags, dir_fd=state_fd)
            try:
                metadata = os.fstat(fd)
                if (
                    (before.st_dev, before.st_ino) != (metadata.st_dev, metadata.st_ino)
                    or not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_nlink != 1
                    or metadata.st_uid != identity.broker_uid
                    or metadata.st_gid != identity.broker_gid
                    or stat.S_IMODE(metadata.st_mode) != 0o600
                ):
                    raise AdminError("unsafe_store_path", f"unsafe authority store file: {name}")
                identities[name] = (metadata.st_dev, metadata.st_ino)
            finally:
                os.close(fd)
    return identities


def initialize_store_as_broker(layout: InstallLayout, identity: DeploymentIdentity) -> dict:
    validate_store_boundary(layout, identity, require_database=False)

    def initialize() -> dict:
        before = validate_store_boundary(layout, identity, require_database=False)
        store = broker.AuthorityStore(layout.database_path, layout.content_root)
        conn = store.connect()
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            application = conn.execute("PRAGMA application_id").fetchone()[0]
            if version not in {0, broker.STORE_SCHEMA_VERSION}:
                raise AdminError("unsupported_store_schema", "unsupported authority schema")
            if application not in {0, broker.STORE_APPLICATION_ID}:
                raise AdminError("unsupported_store", "foreign authority database")
            store._create_schema(conn)
        finally:
            conn.close()
        with open_layout_directory(layout.state_root, layout, identity) as state_fd:
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(layout.database_path.name, flags, dir_fd=state_fd)
            try:
                os.fchmod(fd, 0o600)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.fsync(state_fd)
        after = validate_store_boundary(layout, identity, require_database=True)
        database_name = layout.database_path.name
        if before[database_name] is not None and before[database_name] != after[database_name]:
            raise AdminError("store_inode_changed", "database inode changed during initialization")
        return {
            "created_by_uid": os.geteuid(),
            "database_inode": list(after[database_name] or ()),
        }

    return run_as_broker(identity, initialize)


def store_transition_is_safe(
    before: dict[str, tuple[int, int] | None],
    after: dict[str, tuple[int, int] | None],
    database_name: str,
) -> bool:
    if before[database_name] != after[database_name]:
        return False
    return all(
        old is None or new is None or new == old
        for name, old in before.items()
        if name != database_name
        for new in (after[name],)
    )


def serialize_store_identity(
    identity: dict[str, tuple[int, int] | None],
) -> dict[str, list[int] | None]:
    return {name: list(value) if value is not None else None for name, value in identity.items()}


def deserialize_store_identity(identity: dict) -> dict[str, tuple[int, int] | None]:
    return {
        str(name): tuple(value) if isinstance(value, list) else None
        for name, value in identity.items()
    }


def run_store_action(
    layout: InstallLayout, identity: DeploymentIdentity, callback: Callable[[], dict]
) -> dict:
    root_inode = validate_store_boundary(layout, identity, require_database=True)

    def guarded() -> dict:
        guard_store = broker.AuthorityStore(layout.database_path, layout.content_root)
        guard_connection = guard_store.connect()
        try:
            before = validate_store_boundary(layout, identity, require_database=True)
            database_name = layout.database_path.name
            if root_inode[database_name] != before[database_name]:
                raise AdminError(
                    "store_inode_changed", "database changed or sidecar changed before operation"
                )
            result = callback()
            after = validate_store_boundary(layout, identity, require_database=True)
            if before != after:
                raise AdminError(
                    "store_inode_changed", "database changed or sidecar changed during operation"
                )
            return {
                "callback_result": result,
                "store_identity": serialize_store_identity(after),
            }
        finally:
            guard_connection.close()

    guarded_result = run_as_broker(identity, guarded)
    child_identity = deserialize_store_identity(guarded_result["store_identity"])
    root_after = validate_store_boundary(layout, identity, require_database=True)
    if not store_transition_is_safe(child_identity, root_after, layout.database_path.name):
        raise AdminError(
            "store_inode_changed", "database changed or sidecar changed after operation"
        )
    return guarded_result["callback_result"]


def policy_event(row: sqlite3.Row) -> dict:
    return {
        "policy_event_sequence": row["policy_event_sequence"],
        "ledger_id": row["ledger_id"],
        "event_type": row["event_type"],
        "policy_id": row["policy_id"],
        "generation": row["generation"],
        "policy_sha256": row["policy_sha256"],
        "previous_event_hash": row["previous_event_hash"],
        "event_hash": row["event_hash"],
    }


def inspect_store(layout: InstallLayout) -> dict:
    store = broker.AuthorityStore(layout.database_path, layout.content_root)
    authority_audit = broker.audit_store(store)
    conn = store.connect(read_only=True)
    conn.execute("BEGIN")
    try:
        policies = [
            dict(row)
            for row in conn.execute(
                "SELECT policy_id, generation, policy_sha256, policy_json "
                "FROM policy_snapshots ORDER BY policy_id, generation"
            )
        ]
        events = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM ledger_policy_events ORDER BY policy_event_sequence"
            )
        ]
        commits = [
            dict(row)
            for row in conn.execute(
                "SELECT commit_sequence, ledger_id, policy_id, policy_generation, "
                "policy_sha256, receipt_hash FROM authority_commits ORDER BY commit_sequence"
            )
        ]
    finally:
        conn.rollback()
        conn.close()
    return {
        "authority_audit": authority_audit,
        "policies": policies,
        "policy_events": events,
        "commits": commits,
    }


def activate_policy(layout: InstallLayout, policy: PolicyDocument, event_type: str) -> dict:
    store = broker.AuthorityStore(layout.database_path, layout.content_root)
    store.validate()
    conn = store.connect()
    conn.execute("BEGIN IMMEDIATE")
    try:
        current = store._current_policy_event(conn, policy.ledger_id)
        if current and (
            current["event_type"] == event_type
            and current["policy_id"] == policy.policy_id
            and current["generation"] == policy.generation
            and current["policy_sha256"] == policy.sha256
        ):
            conn.rollback()
            return {**policy_event(current), "idempotent_replay": True}
        if event_type == "enroll":
            if current:
                raise AdminError("ledger_already_enrolled", "ledger already enrolled")
            if policy.generation != 1 or policy.previous_sha256 is not None:
                raise AdminError("invalid_policy_chain", "enrollment requires generation 1")
        elif event_type == "rotate":
            if not current:
                raise AdminError("ledger_not_enrolled", "ledger is not enrolled")
            if current["event_type"] == "revoke":
                raise AdminError("policy_revoked", "revocation is terminal")
            if (
                current["policy_id"] != policy.policy_id
                or policy.generation != current["generation"] + 1
                or policy.previous_sha256 != current["policy_sha256"]
            ):
                raise AdminError("policy_history_fork", "policy rotation does not extend head")
        else:
            raise AdminError("invalid_event", "unsupported policy event")
        existing = conn.execute(
            "SELECT policy_sha256, policy_json FROM policy_snapshots "
            "WHERE policy_id = ? AND generation = ?",
            (policy.policy_id, policy.generation),
        ).fetchone()
        if existing and (
            existing["policy_sha256"] != policy.sha256
            or existing["policy_json"] != policy.canonical_json
        ):
            raise AdminError("policy_replacement", "stored policy generation differs")
        if not existing:
            conn.execute(
                "INSERT INTO policy_snapshots(policy_id,generation,policy_sha256,policy_json,created_at) "
                "VALUES (?,?,?,?,?)",
                (
                    policy.policy_id,
                    policy.generation,
                    policy.sha256,
                    policy.canonical_json,
                    broker.utc_now(),
                ),
            )
            for uid, roles in sorted(policy.roles.items()):
                for role in sorted(roles):
                    conn.execute(
                        "INSERT INTO policy_roles(policy_id,generation,uid,role) VALUES (?,?,?,?)",
                        (policy.policy_id, policy.generation, uid, role),
                    )
        previous_event_hash = current["event_hash"] if current else None
        body = {
            "ledger_id": policy.ledger_id,
            "event_type": event_type,
            "policy_id": policy.policy_id,
            "generation": policy.generation,
            "policy_sha256": policy.sha256,
            "previous_event_hash": previous_event_hash,
        }
        body_json = broker.canonical_json(body)
        event_hash = broker.sha256_text(body_json)
        conn.execute(
            "INSERT INTO ledger_policy_events(ledger_id,event_type,policy_id,generation,"
            "policy_sha256,previous_event_hash,event_body_json,event_hash,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                policy.ledger_id,
                event_type,
                policy.policy_id,
                policy.generation,
                policy.sha256,
                previous_event_hash,
                body_json,
                event_hash,
                broker.utc_now(),
            ),
        )
        conn.commit()
        head = store._current_policy_event(conn, policy.ledger_id)
        if not head:
            raise AdminError("policy_activation_failed", "policy event was not retained")
        return {**policy_event(head), "idempotent_replay": False}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def revoke_policy(layout: InstallLayout, ledger_id: str, expected_digest: str) -> dict:
    store = broker.AuthorityStore(layout.database_path, layout.content_root)
    store.validate()
    conn = store.connect()
    conn.execute("BEGIN IMMEDIATE")
    try:
        current = store._current_policy_event(conn, ledger_id)
        if not current:
            raise AdminError("ledger_not_enrolled", "ledger is not enrolled")
        if current["event_type"] == "revoke":
            if current["policy_sha256"] != expected_digest:
                raise AdminError("policy_digest_mismatch", "revoked digest differs")
            conn.rollback()
            return {**policy_event(current), "idempotent_replay": True}
        if current["policy_sha256"] != expected_digest:
            raise AdminError("policy_digest_mismatch", "current policy digest differs")
        body = {
            "ledger_id": ledger_id,
            "event_type": "revoke",
            "policy_id": current["policy_id"],
            "generation": current["generation"],
            "policy_sha256": current["policy_sha256"],
            "previous_event_hash": current["event_hash"],
        }
        body_json = broker.canonical_json(body)
        event_hash = broker.sha256_text(body_json)
        conn.execute(
            "INSERT INTO ledger_policy_events(ledger_id,event_type,policy_id,generation,"
            "policy_sha256,previous_event_hash,event_body_json,event_hash,created_at) "
            "VALUES (?,'revoke',?,?,?,?,?,?,?)",
            (
                ledger_id,
                current["policy_id"],
                current["generation"],
                current["policy_sha256"],
                current["event_hash"],
                body_json,
                event_hash,
                broker.utc_now(),
            ),
        )
        conn.commit()
        head = store._current_policy_event(conn, ledger_id)
        return {**policy_event(head), "idempotent_replay": False}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def install_manifest(
    layout: InstallLayout,
    identity: DeploymentIdentity,
    policy: PolicyDocument,
    assets: dict[str, dict],
) -> dict:
    return {
        "install_schema_version": INSTALL_SCHEMA_VERSION,
        "broker_user": identity.broker_user,
        "broker_uid": identity.broker_uid,
        "broker_gid": identity.broker_gid,
        "socket_group": identity.socket_group,
        "socket_gid": identity.socket_gid,
        "ledger_id": policy.ledger_id,
        "policy_id": policy.policy_id,
        "paths": {
            "install_root": str(layout.install_root),
            "config_root": str(layout.config_root),
            "state_root": str(layout.state_root),
            "runtime_root": str(layout.runtime_root),
            "database": str(layout.database_path),
            "content_root": str(layout.content_root),
            "socket": str(layout.socket_path),
            "unit": str(layout.unit_path),
            "tmpfiles": str(layout.tmpfiles_path),
        },
        "assets": assets,
    }


def identity_from_manifest(manifest: dict, admin_uid: int, admin_gid: int) -> DeploymentIdentity:
    return DeploymentIdentity(
        admin_uid,
        admin_gid,
        str(manifest["broker_user"]),
        int(manifest["broker_uid"]),
        int(manifest["broker_gid"]),
        str(manifest["socket_group"]),
        int(manifest["socket_gid"]),
    )


def load_manifest(
    layout: InstallLayout,
    admin_uid: int,
    admin_gid: int,
    *,
    validate_binding: bool,
) -> tuple[dict, DeploymentIdentity]:
    provisional = DeploymentIdentity(
        admin_uid, admin_gid, "unknown", admin_uid, admin_gid, "unknown", admin_gid
    )
    data = read_protected_file(
        layout.manifest_path, 0o600, admin_uid, admin_gid, layout, provisional
    )
    manifest = decode_canonical(data, "install manifest")
    fields = {
        "install_schema_version",
        "broker_user",
        "broker_uid",
        "broker_gid",
        "socket_group",
        "socket_gid",
        "ledger_id",
        "policy_id",
        "paths",
        "assets",
    }
    require_exact_keys(manifest, fields, "install manifest")
    if manifest["install_schema_version"] != INSTALL_SCHEMA_VERSION:
        raise AdminError("unsupported_install_schema", "unsupported install manifest")
    if (
        not isinstance(manifest["broker_user"], str)
        or not SYSTEM_NAME.fullmatch(manifest["broker_user"])
        or not isinstance(manifest["socket_group"], str)
        or not SYSTEM_NAME.fullmatch(manifest["socket_group"])
    ):
        raise AdminError("invalid_admin_state", "manifest account name is invalid")
    for field in ("broker_uid", "broker_gid", "socket_gid"):
        value = manifest[field]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise AdminError("invalid_admin_state", f"manifest {field} is invalid")
    require_token(manifest["ledger_id"], "ledger_id")
    require_token(manifest["policy_id"], "policy_id")
    identity = identity_from_manifest(manifest, admin_uid, admin_gid)
    stub = PolicyDocument(
        manifest["policy_id"],
        manifest["ledger_id"],
        1,
        None,
        {},
        {},
        "{}",
        "0" * 64,
    )
    expected_paths = install_manifest(layout, identity, stub, {})["paths"]
    if manifest["paths"] != expected_paths:
        raise AdminError("installation_redirected", "manifest paths differ from fixed layout")
    expected_assets = {str(layout.install_root / name) for name in INSTALLED_SOURCE_ASSETS}
    expected_assets |= {str(layout.unit_path), str(layout.tmpfiles_path)}
    if not isinstance(manifest["assets"], dict) or set(manifest["assets"]) != expected_assets:
        raise AdminError("install_manifest_mismatch", "manifest asset set differs")
    for raw_path, entry in manifest["assets"].items():
        if not isinstance(entry, dict):
            raise AdminError("invalid_admin_state", f"invalid asset entry: {raw_path}")
        require_exact_keys(entry, {"sha256", "mode", "uid", "gid"}, f"asset {raw_path}")
        require_sha256(entry["sha256"], "asset sha256")
        for field in ("mode", "uid", "gid"):
            if not isinstance(entry[field], int) or isinstance(entry[field], bool):
                raise AdminError("invalid_admin_state", f"invalid asset {field}: {raw_path}")
    if validate_binding:
        validate_identity_binding(identity)
    return manifest, identity


def entry_metadata_if_present(
    path: Path, layout: InstallLayout, identity: DeploymentIdentity
) -> os.stat_result | None:
    parts = relative_parts(path.parent, layout.anchor)
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(layout.anchor, flags)
    current = layout.anchor
    try:
        validate_directory(
            os.fstat(fd), current, expected_directory_owner(current, layout, identity)
        )
        for part in parts:
            try:
                next_fd = os.open(part, flags, dir_fd=fd)
            except FileNotFoundError:
                return None
            os.close(fd)
            fd = next_fd
            current /= part
            validate_directory(
                os.fstat(fd), current, expected_directory_owner(current, layout, identity)
            )
        try:
            return os.stat(path.name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            return None
    except OSError as exc:
        raise AdminError("unsafe_path", f"could not inspect {path}: {exc}") from exc
    finally:
        os.close(fd)


def validate_input_parent(path: Path, layout: InstallLayout, identity: DeploymentIdentity) -> None:
    with open_admin_directory(path.parent, layout.anchor, identity.admin_uid):
        pass


def read_source_assets(
    source_dir: Path, layout: InstallLayout, identity: DeploymentIdentity
) -> dict[str, bytes]:
    with open_admin_directory(source_dir, layout.anchor, identity.admin_uid):
        pass
    return {
        name: read_input_file(
            source_dir / name,
            identity.admin_uid,
            f"source asset {name}",
            8 * MAX_ADMIN_FILE_BYTES,
        )
        for name in INSTALLED_SOURCE_ASSETS
    }


def expected_asset_payloads(
    layout: InstallLayout,
    identity: DeploymentIdentity,
    source_assets: dict[str, bytes],
) -> dict[Path, tuple[bytes, int]]:
    result = {
        layout.install_root / name: (source_assets[name], mode)
        for name, mode in INSTALLED_SOURCE_ASSETS.items()
    }
    result[layout.unit_path] = (render_service(layout, identity), 0o644)
    result[layout.tmpfiles_path] = (render_tmpfiles(layout, identity), 0o644)
    return result


def preflight_existing_file(
    path: Path,
    expected_data: bytes,
    mode: int,
    uid: int,
    gid: int,
    layout: InstallLayout,
    identity: DeploymentIdentity,
) -> None:
    metadata = entry_metadata_if_present(path, layout, identity)
    if metadata is None:
        return
    data = read_protected_file(path, mode, uid, gid, layout, identity)
    if data != expected_data:
        raise AdminError("installation_conflict", f"existing protected file differs: {path}")


def reject_pending_protected_files(
    targets: Iterable[Path],
    layout: InstallLayout,
    identity: DeploymentIdentity,
    *,
    allowed: dict[Path, bytes] | None = None,
) -> None:
    allowed = allowed or {}
    for target in targets:
        pending = target.parent / f".{target.name}.pending"
        if target in allowed:
            preflight_existing_file(
                pending,
                allowed[target],
                0o600,
                identity.admin_uid,
                identity.admin_gid,
                layout,
                identity,
            )
        elif entry_metadata_if_present(pending, layout, identity) is not None:
            raise AdminError(
                "installation_conflict", f"completed installation has pending file: {pending}"
            )


def verify_admin_lock(layout: InstallLayout, identity: DeploymentIdentity) -> None:
    data = read_protected_file(
        layout.lock_path,
        0o600,
        identity.admin_uid,
        identity.admin_gid,
        layout,
        identity,
    )
    if data:
        raise AdminError("installation_conflict", "administration lock content differs")


def verify_socket_path(layout: InstallLayout, identity: DeploymentIdentity) -> None:
    metadata = entry_metadata_if_present(layout.socket_path, layout, identity)
    if metadata is not None and (
        not stat.S_ISSOCK(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid != identity.broker_uid
        or metadata.st_gid != identity.socket_gid
        or stat.S_IMODE(metadata.st_mode) != 0o660
    ):
        raise AdminError("unsafe_socket_path", "broker socket metadata differs")


def current_event(state: dict, ledger_id: str) -> dict:
    events = [event for event in state["policy_events"] if event["ledger_id"] == ledger_id]
    if not events:
        raise AdminError("ledger_not_enrolled", "ledger has no policy event")
    return events[-1]


def archive_matches_policy(
    layout: InstallLayout, identity: DeploymentIdentity, policy: PolicyDocument
) -> bool:
    metadata = entry_metadata_if_present(policy_path(layout, policy), layout, identity)
    if metadata is None:
        return False
    data = read_protected_file(
        policy_path(layout, policy),
        0o600,
        identity.admin_uid,
        identity.admin_gid,
        layout,
        identity,
    )
    return data == (policy.canonical_json + "\n").encode("ascii")


def validate_interrupted_install_state(
    layout: InstallLayout, identity: DeploymentIdentity, policy: PolicyDocument
) -> dict | None:
    if not archive_matches_policy(layout, identity, policy):
        raise AdminError(
            "foreign_store",
            "pre-existing store lacks the exact root-owned interrupted-install archive",
        )
    state = run_store_action(layout, identity, lambda: inspect_store(layout))
    if not state["authority_audit"]["ok"] or state["commits"]:
        raise AdminError("foreign_store", "pre-existing authority store is not install recovery")
    if not state["policies"] and not state["policy_events"]:
        if entry_metadata_if_present(layout.active_path, layout, identity) is not None:
            raise AdminError(
                "installation_conflict",
                "empty interrupted installation has an active index",
            )
        return None
    if len(state["policies"]) != 1 or len(state["policy_events"]) != 1:
        raise AdminError("foreign_store", "pre-existing authority history is not install recovery")
    stored = state["policies"][0]
    event = state["policy_events"][0]
    if (
        stored["policy_id"] != policy.policy_id
        or stored["generation"] != 1
        or stored["policy_sha256"] != policy.sha256
        or stored["policy_json"] != policy.canonical_json
        or event["event_type"] != "enroll"
        or event["ledger_id"] != policy.ledger_id
        or event["policy_id"] != policy.policy_id
        or event["generation"] != 1
        or event["policy_sha256"] != policy.sha256
    ):
        raise AdminError("foreign_store", "pre-existing authority history differs")
    active_metadata = entry_metadata_if_present(layout.active_path, layout, identity)
    if active_metadata is not None:
        expected_active = json_bytes(active_index(event))
        actual_active = read_protected_file(
            layout.active_path,
            0o600,
            identity.admin_uid,
            identity.admin_gid,
            layout,
            identity,
        )
        if actual_active != expected_active:
            raise AdminError(
                "installation_conflict", "interrupted installation active index differs"
            )
    return event


def validate_install_preflight(
    layout: InstallLayout,
    identity: DeploymentIdentity,
    policy: PolicyDocument,
    asset_payloads: dict[Path, tuple[bytes, int]],
    *,
    validate_binding: bool,
) -> tuple[dict, DeploymentIdentity] | None:
    if validate_binding:
        validate_host_accounts(policy, identity)
    exact_directories = (
        (layout.install_root, 0o755, identity.admin_uid, identity.admin_gid),
        (layout.config_root, 0o700, identity.admin_uid, identity.admin_gid),
        (layout.policies_root, 0o700, identity.admin_uid, identity.admin_gid),
        (
            layout.policies_root / policy.ledger_id,
            0o700,
            identity.admin_uid,
            identity.admin_gid,
        ),
        (layout.revocations_root, 0o700, identity.admin_uid, identity.admin_gid),
        (
            layout.revocations_root / policy.ledger_id,
            0o700,
            identity.admin_uid,
            identity.admin_gid,
        ),
        (layout.state_root, 0o700, identity.broker_uid, identity.broker_gid),
        (layout.content_root, 0o700, identity.broker_uid, identity.broker_gid),
        (layout.content_root / "sha256", 0o700, identity.broker_uid, identity.broker_gid),
        (layout.runtime_root, 0o2750, identity.broker_uid, identity.socket_gid),
    )
    for path, mode, uid, gid in exact_directories:
        if entry_metadata_if_present(path, layout, identity) is not None:
            validate_exact_directory(path, mode, uid, gid, layout, identity)
    manifest_metadata = entry_metadata_if_present(layout.manifest_path, layout, identity)
    if manifest_metadata is not None:
        manifest, installed_identity = load_manifest(
            layout,
            identity.admin_uid,
            identity.admin_gid,
            validate_binding=validate_binding,
        )
        if (
            installed_identity != identity
            or manifest["ledger_id"] != policy.ledger_id
            or manifest["policy_id"] != policy.policy_id
        ):
            raise AdminError("installation_conflict", "existing installation identity differs")
        return manifest, installed_identity
    for root in (layout.policies_root, layout.revocations_root):
        metadata = entry_metadata_if_present(root, layout, identity)
        if metadata is None:
            continue
        with open_layout_directory(root, layout, identity) as root_fd:
            ledger_directories = set(os.listdir(root_fd))
        if ledger_directories not in (set(), {policy.ledger_id}):
            raise AdminError(
                "installation_conflict",
                f"foreign ledger archive exists under {root}",
            )
    for path, (data, mode) in asset_payloads.items():
        pending_path = path.parent / f".{path.name}.pending"
        target_exists = entry_metadata_if_present(path, layout, identity) is not None
        pending_exists = entry_metadata_if_present(pending_path, layout, identity) is not None
        if target_exists and pending_exists:
            raise AdminError(
                "installation_conflict", f"asset has both final and pending files: {path}"
            )
        preflight_existing_file(
            path,
            data,
            mode,
            identity.admin_uid,
            identity.admin_gid,
            layout,
            identity,
        )
        preflight_existing_file(
            pending_path,
            data,
            mode,
            identity.admin_uid,
            identity.admin_gid,
            layout,
            identity,
        )
    preflight_existing_file(
        policy_path(layout, policy),
        (policy.canonical_json + "\n").encode("ascii"),
        0o600,
        identity.admin_uid,
        identity.admin_gid,
        layout,
        identity,
    )
    policy_pending = policy_path(layout, policy).parent / (
        f".{policy_path(layout, policy).name}.pending"
    )
    preflight_existing_file(
        policy_pending,
        (policy.canonical_json + "\n").encode("ascii"),
        0o600,
        identity.admin_uid,
        identity.admin_gid,
        layout,
        identity,
    )
    policy_ledger_root = layout.policies_root / policy.ledger_id
    if entry_metadata_if_present(policy_ledger_root, layout, identity) is not None:
        with open_layout_directory(policy_ledger_root, layout, identity) as policy_fd:
            expected = {policy_path(layout, policy).name}
            pending = {policy_pending.name}
            if set(os.listdir(policy_fd)) not in (set(), expected, pending):
                raise AdminError("installation_conflict", "policy archive contains foreign files")
    revocation_ledger_root = layout.revocations_root / policy.ledger_id
    if entry_metadata_if_present(revocation_ledger_root, layout, identity) is not None:
        with open_layout_directory(revocation_ledger_root, layout, identity) as revocation_fd:
            if os.listdir(revocation_fd):
                raise AdminError("installation_conflict", "revocation archive is not empty")
    preflight_existing_file(
        layout.lock_path,
        b"",
        0o600,
        identity.admin_uid,
        identity.admin_gid,
        layout,
        identity,
    )
    verify_socket_path(layout, identity)
    recovery_event = None
    database = entry_metadata_if_present(layout.database_path, layout, identity)
    if database is not None:
        recovery_event = validate_interrupted_install_state(layout, identity, policy)
    else:
        for suffix in ("-wal", "-shm", "-journal"):
            if (
                entry_metadata_if_present(
                    Path(str(layout.database_path) + suffix), layout, identity
                )
                is not None
            ):
                raise AdminError(
                    "installation_conflict", "database sidecar exists without authority database"
                )
        if entry_metadata_if_present(layout.active_path, layout, identity) is not None:
            raise AdminError(
                "installation_conflict", "active index exists without an authority database"
            )
    asset_entries = {
        str(path): {
            "sha256": sha256_bytes(data),
            "mode": mode,
            "uid": identity.admin_uid,
            "gid": identity.admin_gid,
        }
        for path, (data, mode) in asset_payloads.items()
    }
    pending_payloads = {
        layout.active_path: (
            json_bytes(active_index(recovery_event)) if recovery_event is not None else None
        ),
        layout.manifest_path: (
            json_bytes(install_manifest(layout, identity, policy, asset_entries))
            if recovery_event is not None
            else None
        ),
    }
    for target, expected in pending_payloads.items():
        pending_path = target.parent / f".{target.name}.pending"
        if expected is None:
            if entry_metadata_if_present(pending_path, layout, identity) is not None:
                raise AdminError(
                    "installation_conflict", f"unexpected pending protected file: {pending_path}"
                )
        else:
            preflight_existing_file(
                pending_path,
                expected,
                0o600,
                identity.admin_uid,
                identity.admin_gid,
                layout,
                identity,
            )
    return None


@contextlib.contextmanager
def administration_lock(layout: InstallLayout, identity: DeploymentIdentity) -> Iterator[None]:
    with open_layout_directory(layout.config_root, layout, identity) as parent_fd:
        create_flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        create_flags |= getattr(os, "O_NOFOLLOW", 0)
        created = False
        try:
            fd = os.open(layout.lock_path.name, create_flags, 0o600, dir_fd=parent_fd)
            created = True
        except FileExistsError:
            flags = os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(layout.lock_path.name, flags, dir_fd=parent_fd)
        try:
            if created:
                os.fchown(fd, identity.admin_uid, identity.admin_gid)
                os.fchmod(fd, 0o600)
                os.fsync(fd)
                os.fsync(parent_fd)
            metadata = os.fstat(fd)
            linked = os.stat(layout.lock_path.name, dir_fd=parent_fd, follow_symlinks=False)
            if (
                (metadata.st_dev, metadata.st_ino) != (linked.st_dev, linked.st_ino)
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or metadata.st_uid != identity.admin_uid
                or metadata.st_gid != identity.admin_gid
                or stat.S_IMODE(metadata.st_mode) != 0o600
            ):
                raise AdminError("unsafe_admin_lock", "administration lock metadata differs")
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)


def verify_asset(
    path: Path,
    expected: dict,
    layout: InstallLayout,
    identity: DeploymentIdentity,
) -> None:
    data = read_protected_file(
        path,
        int(expected["mode"]),
        int(expected["uid"]),
        int(expected["gid"]),
        layout,
        identity,
    )
    if sha256_bytes(data) != expected["sha256"]:
        raise AdminError("installed_asset_changed", f"asset digest differs: {path}")


def verify_deployment(
    layout: InstallLayout,
    manifest: dict,
    identity: DeploymentIdentity,
    *,
    state: dict | None = None,
    allowed_staged_policy: PolicyDocument | None = None,
    allowed_pending_policy: PolicyDocument | None = None,
    allowed_revocation: dict | None = None,
    allowed_stale_active: dict | None = None,
    allowed_pending_active: bytes | None = None,
    validate_binding: bool,
) -> dict:
    if validate_binding:
        validate_identity_binding(identity)
    for raw_path, expected in manifest["assets"].items():
        verify_asset(Path(raw_path), expected, layout, identity)
    reject_pending_protected_files(
        [Path(raw_path) for raw_path in manifest["assets"]]
        + [layout.active_path, layout.manifest_path],
        layout,
        identity,
        allowed=(
            {layout.active_path: allowed_pending_active}
            if allowed_pending_active is not None
            else None
        ),
    )
    verify_admin_lock(layout, identity)
    exact_directories = (
        (layout.install_root, 0o755, identity.admin_uid, identity.admin_gid),
        (layout.config_root, 0o700, identity.admin_uid, identity.admin_gid),
        (layout.policies_root, 0o700, identity.admin_uid, identity.admin_gid),
        (
            layout.policies_root / manifest["ledger_id"],
            0o700,
            identity.admin_uid,
            identity.admin_gid,
        ),
        (layout.revocations_root, 0o700, identity.admin_uid, identity.admin_gid),
        (
            layout.revocations_root / manifest["ledger_id"],
            0o700,
            identity.admin_uid,
            identity.admin_gid,
        ),
        (layout.state_root, 0o700, identity.broker_uid, identity.broker_gid),
        (layout.content_root, 0o700, identity.broker_uid, identity.broker_gid),
        (layout.content_root / "sha256", 0o700, identity.broker_uid, identity.broker_gid),
        (layout.runtime_root, 0o2750, identity.broker_uid, identity.socket_gid),
    )
    for values in exact_directories:
        validate_exact_directory(*values, layout, identity)
    verify_socket_path(layout, identity)
    if state is None:
        state = run_store_action(layout, identity, lambda: inspect_store(layout))
    if not state["authority_audit"]["ok"]:
        raise AdminError("store_corrupt", "; ".join(state["authority_audit"]["issues"]))
    policy_by_key: dict[tuple[str, int], PolicyDocument] = {}
    for row in state["policies"]:
        try:
            raw = broker.decode_json(row["policy_json"].encode("ascii"))
        except broker.BrokerError as exc:
            raise AdminError("store_corrupt", exc.message) from exc
        policy = parse_policy_object(raw)
        if (
            policy.ledger_id != manifest["ledger_id"]
            or policy.policy_id != manifest["policy_id"]
            or policy.sha256 != row["policy_sha256"]
        ):
            raise AdminError("wrong_ledger_policy", "stored policy differs from enrollment")
        archived = read_protected_file(
            policy_path(layout, policy),
            0o600,
            identity.admin_uid,
            identity.admin_gid,
            layout,
            identity,
        )
        if archived != (policy.canonical_json + "\n").encode("ascii"):
            raise AdminError("policy_archive_mismatch", "policy archive content differs")
        policy_by_key[(policy.policy_id, policy.generation)] = policy
    events = state["policy_events"]
    if not events:
        raise AdminError("ledger_not_enrolled", "policy event history is empty")
    previous_hash = None
    previous_policy = None
    revoked = False
    for index, event in enumerate(events):
        policy = policy_by_key.get((event["policy_id"], event["generation"]))
        if (
            event["ledger_id"] != manifest["ledger_id"]
            or policy is None
            or policy.sha256 != event["policy_sha256"]
            or event["previous_event_hash"] != previous_hash
        ):
            raise AdminError("policy_event_mismatch", "policy event history differs")
        if index == 0:
            if event["event_type"] != "enroll" or policy.generation != 1:
                raise AdminError("policy_event_mismatch", "history must begin with generation 1")
        elif event["event_type"] == "rotate":
            if (
                revoked
                or previous_policy is None
                or policy.generation != previous_policy.generation + 1
                or policy.previous_sha256 != previous_policy.sha256
            ):
                raise AdminError("policy_event_mismatch", "rotation history is forked")
        elif event["event_type"] == "revoke":
            if revoked or previous_policy is None or policy.sha256 != previous_policy.sha256:
                raise AdminError("policy_event_mismatch", "invalid revocation history")
            revoked = True
        else:
            raise AdminError("policy_event_mismatch", "unsupported event type")
        previous_hash = event["event_hash"]
        previous_policy = policy
    event_policy_keys = {(event["policy_id"], event["generation"]) for event in events}
    if event_policy_keys != set(policy_by_key):
        raise AdminError("policy_event_mismatch", "unreferenced policy snapshot exists")
    for commit in state["commits"]:
        key = (commit["policy_id"], commit["policy_generation"])
        if (
            commit["ledger_id"] != manifest["ledger_id"]
            or key not in policy_by_key
            or policy_by_key[key].sha256 != commit["policy_sha256"]
        ):
            raise AdminError("policy_event_mismatch", "commit policy binding differs")
    expected_policy_files = {policy_path(layout, item).name for item in policy_by_key.values()}
    if allowed_staged_policy is not None:
        expected_policy_files.add(policy_path(layout, allowed_staged_policy).name)
    if allowed_pending_policy is not None:
        pending_name = f".{policy_path(layout, allowed_pending_policy).name}.pending"
        expected_policy_files.add(pending_name)
        with open_layout_directory(
            layout.policies_root / manifest["ledger_id"], layout, identity
        ) as pending_parent_fd:
            expected_pending = (allowed_pending_policy.canonical_json + "\n").encode("ascii")
            pending_fd, pending_data, pending_metadata = open_regular_at(
                pending_parent_fd, pending_name, len(expected_pending) + 1
            )
            try:
                if (
                    pending_data != expected_pending
                    or pending_metadata.st_uid != identity.admin_uid
                    or pending_metadata.st_gid != identity.admin_gid
                    or stat.S_IMODE(pending_metadata.st_mode) != 0o600
                ):
                    raise AdminError("unsafe_pending_file", "pending policy metadata differs")
            finally:
                os.close(pending_fd)
    with open_layout_directory(
        layout.policies_root / manifest["ledger_id"], layout, identity
    ) as policies_fd:
        if set(os.listdir(policies_fd)) != expected_policy_files:
            raise AdminError("policy_archive_mismatch", "policy archive file set differs")
    with open_layout_directory(layout.policies_root, layout, identity) as policies_root_fd:
        if set(os.listdir(policies_root_fd)) != {manifest["ledger_id"]}:
            raise AdminError("policy_archive_mismatch", "policy ledger directory set differs")
    head = events[-1]
    active = decode_canonical(
        read_protected_file(
            layout.active_path,
            0o600,
            identity.admin_uid,
            identity.admin_gid,
            layout,
            identity,
        ),
        "active index",
    )
    if active != active_index(head) and active != allowed_stale_active:
        raise AdminError("active_index_mismatch", "active index differs from event head")
    expected_revocations: set[str] = set()
    if head["event_type"] == "revoke":
        expected_revocations.add(revoke_path(layout, head["ledger_id"], head["policy_sha256"]).name)
    elif allowed_revocation is not None:
        expected_revocations.add(revoke_path(layout, head["ledger_id"], head["policy_sha256"]).name)
    with open_layout_directory(
        layout.revocations_root / manifest["ledger_id"], layout, identity
    ) as revocations_fd:
        if set(os.listdir(revocations_fd)) != expected_revocations:
            raise AdminError("revocation_archive_mismatch", "revocation archive differs")
    with open_layout_directory(layout.revocations_root, layout, identity) as revocations_root_fd:
        if set(os.listdir(revocations_root_fd)) != {manifest["ledger_id"]}:
            raise AdminError(
                "revocation_archive_mismatch", "revocation ledger directory set differs"
            )
    if expected_revocations:
        intent = decode_canonical(
            read_protected_file(
                revoke_path(layout, head["ledger_id"], head["policy_sha256"]),
                0o600,
                identity.admin_uid,
                identity.admin_gid,
                layout,
                identity,
            ),
            "revocation intent",
        )
        expected_intent = {
            "action": "revoke",
            "ledger_id": head["ledger_id"],
            "policy_id": head["policy_id"],
            "policy_generation": head["generation"],
            "policy_sha256": head["policy_sha256"],
        }
        if intent != expected_intent or (
            allowed_revocation is not None and intent != allowed_revocation
        ):
            raise AdminError("revocation_intent_mismatch", "revocation intent differs")
    return {
        "ok": True,
        "ledger_id": manifest["ledger_id"],
        "policy_generations": len(policy_by_key),
        "policy_events": len(events),
        "current": active,
        "authority": state["authority_audit"],
        "boundary_operational": False,
    }


def audit_deployment(
    layout: InstallLayout,
    admin_uid: int,
    admin_gid: int,
    *,
    validate_binding: bool = True,
) -> dict:
    manifest, identity = load_manifest(
        layout, admin_uid, admin_gid, validate_binding=validate_binding
    )
    return verify_deployment(layout, manifest, identity, validate_binding=validate_binding)


def install_deployment(
    layout: InstallLayout,
    source_dir: Path,
    policy_file: Path,
    identity: DeploymentIdentity,
    *,
    validate_accounts: bool,
    after_activation: Callable[[dict], None] | None = None,
) -> dict:
    validate_input_parent(policy_file, layout, identity)
    policy = read_policy_file(policy_file, identity.admin_uid)
    if policy.generation != 1:
        raise AdminError("invalid_policy_chain", "installation requires generation 1")
    source_assets = read_source_assets(source_dir, layout, identity)
    payloads = expected_asset_payloads(layout, identity, source_assets)
    existing = validate_install_preflight(
        layout,
        identity,
        policy,
        payloads,
        validate_binding=validate_accounts,
    )
    if existing is not None:
        manifest, installed_identity = existing
        for path, (data, mode) in payloads.items():
            entry = manifest["assets"].get(str(path))
            if (
                entry is None
                or entry["sha256"] != sha256_bytes(data)
                or entry["mode"] != mode
                or entry["uid"] != identity.admin_uid
                or entry["gid"] != identity.admin_gid
            ):
                raise AdminError("installation_conflict", "reinstall asset set differs")
        if not archive_matches_policy(layout, identity, policy):
            raise AdminError("installation_conflict", "reinstall policy generation differs")
        audit = verify_deployment(
            layout,
            manifest,
            installed_identity,
            validate_binding=validate_accounts,
        )
        return {
            "ok": True,
            "action": "install",
            "idempotent_replay": True,
            "policy": {
                "id": policy.policy_id,
                "ledger_id": policy.ledger_id,
                "generation": 1,
                "sha256": policy.sha256,
            },
            "audit": audit,
            "service_started": False,
            "boundary_operational": False,
        }

    ensure_layout(layout, identity)
    with administration_lock(layout, identity):
        existing = validate_install_preflight(
            layout,
            identity,
            policy,
            payloads,
            validate_binding=validate_accounts,
        )
        if existing is not None:
            raise AdminError("installation_conflict", "installation appeared concurrently")
        ensure_directory(
            layout.policies_root / policy.ledger_id,
            0o700,
            identity.admin_uid,
            identity.admin_gid,
            layout,
            identity,
        )
        ensure_directory(
            layout.revocations_root / policy.ledger_id,
            0o700,
            identity.admin_uid,
            identity.admin_gid,
            layout,
            identity,
        )
        asset_entries: dict[str, dict] = {}
        for destination, (data, mode) in payloads.items():
            write_protected_file(
                destination,
                data,
                mode,
                identity.admin_uid,
                identity.admin_gid,
                layout,
                identity,
            )
            asset_entries[str(destination)] = {
                "sha256": sha256_bytes(data),
                "mode": mode,
                "uid": identity.admin_uid,
                "gid": identity.admin_gid,
            }
        write_protected_file(
            policy_path(layout, policy),
            (policy.canonical_json + "\n").encode("ascii"),
            0o600,
            identity.admin_uid,
            identity.admin_gid,
            layout,
            identity,
        )
        initialize_store_as_broker(layout, identity)
        event = run_store_action(
            layout, identity, lambda: activate_policy(layout, policy, "enroll")
        )
        if after_activation:
            after_activation(event)
        write_protected_file(
            layout.active_path,
            json_bytes(active_index(event)),
            0o600,
            identity.admin_uid,
            identity.admin_gid,
            layout,
            identity,
            replace=True,
        )
        manifest = install_manifest(layout, identity, policy, asset_entries)
        write_protected_file(
            layout.manifest_path,
            json_bytes(manifest),
            0o600,
            identity.admin_uid,
            identity.admin_gid,
            layout,
            identity,
        )
        final_state = run_store_action(layout, identity, lambda: inspect_store(layout))
        audit = verify_deployment(
            layout,
            manifest,
            identity,
            state=final_state,
            validate_binding=validate_accounts,
        )
    return {
        "ok": True,
        "action": "install",
        "idempotent_replay": False,
        "policy": {
            "id": policy.policy_id,
            "ledger_id": policy.ledger_id,
            "generation": 1,
            "sha256": policy.sha256,
        },
        "event": event,
        "audit": audit,
        "store_created_by_uid": identity.broker_uid,
        "service_started": False,
        "boundary_operational": False,
    }


def rotate_deployment(
    layout: InstallLayout,
    policy_file: Path,
    admin_uid: int,
    admin_gid: int,
    *,
    validate_accounts: bool,
    archive_fault: Callable[[str, Path], None] | None = None,
    after_activation: Callable[[dict], None] | None = None,
) -> dict:
    manifest, identity = load_manifest(
        layout, admin_uid, admin_gid, validate_binding=validate_accounts
    )
    validate_input_parent(policy_file, layout, identity)
    policy = read_policy_file(policy_file, admin_uid)
    if policy.ledger_id != manifest["ledger_id"] or policy.policy_id != manifest["policy_id"]:
        raise AdminError("wrong_ledger_policy", "policy does not match enrollment")
    if validate_accounts:
        validate_host_accounts(policy, identity)
    with administration_lock(layout, identity):
        state = run_store_action(layout, identity, lambda: inspect_store(layout))
        head = current_event(state, policy.ledger_id)
        already_active = (
            head["event_type"] == "rotate"
            and head["generation"] == policy.generation
            and head["policy_sha256"] == policy.sha256
        )
        if not already_active:
            if head["event_type"] == "revoke":
                raise AdminError("policy_revoked", "revocation is terminal")
            if (
                policy.generation != head["generation"] + 1
                or policy.previous_sha256 != head["policy_sha256"]
            ):
                raise AdminError("policy_history_fork", "rotation does not extend current head")
        target = policy_path(layout, policy)
        pending = target.parent / f".{target.name}.pending"
        target_exists = entry_metadata_if_present(target, layout, identity) is not None
        pending_exists = entry_metadata_if_present(pending, layout, identity) is not None
        stale_active = active_index(state["policy_events"][-2]) if already_active else None
        verify_deployment(
            layout,
            manifest,
            identity,
            state=state,
            allowed_staged_policy=policy if target_exists and not already_active else None,
            allowed_pending_policy=(
                policy if pending_exists and not target_exists and not already_active else None
            ),
            allowed_stale_active=stale_active,
            allowed_pending_active=(json_bytes(active_index(head)) if already_active else None),
            validate_binding=validate_accounts,
        )
        write_protected_file(
            target,
            (policy.canonical_json + "\n").encode("ascii"),
            0o600,
            identity.admin_uid,
            identity.admin_gid,
            layout,
            identity,
            fault=archive_fault,
        )
        if not already_active:
            verify_deployment(
                layout,
                manifest,
                identity,
                state=state,
                allowed_staged_policy=policy,
                validate_binding=validate_accounts,
            )
        event = run_store_action(
            layout, identity, lambda: activate_policy(layout, policy, "rotate")
        )
        if after_activation:
            after_activation(event)
        write_protected_file(
            layout.active_path,
            json_bytes(active_index(event)),
            0o600,
            identity.admin_uid,
            identity.admin_gid,
            layout,
            identity,
            replace=True,
        )
        final_state = run_store_action(layout, identity, lambda: inspect_store(layout))
        audit = verify_deployment(
            layout,
            manifest,
            identity,
            state=final_state,
            validate_binding=validate_accounts,
        )
    return {
        "ok": True,
        "action": "rotate",
        "policy": {
            "id": policy.policy_id,
            "ledger_id": policy.ledger_id,
            "generation": policy.generation,
            "sha256": policy.sha256,
        },
        "event": event,
        "audit": audit,
        "boundary_operational": False,
    }


def revoke_deployment(
    layout: InstallLayout,
    ledger_id: str,
    expected_digest: str,
    admin_uid: int,
    admin_gid: int,
    *,
    after_intent: Callable[[dict], None] | None = None,
    after_activation: Callable[[dict], None] | None = None,
    validate_binding: bool = True,
) -> dict:
    ledger_id = require_token(ledger_id, "ledger_id")
    expected_digest = require_sha256(expected_digest, "expected_policy_sha256")
    manifest, identity = load_manifest(
        layout, admin_uid, admin_gid, validate_binding=validate_binding
    )
    if manifest["ledger_id"] != ledger_id:
        raise AdminError("wrong_ledger_policy", "ledger does not match enrollment")
    with administration_lock(layout, identity):
        state = run_store_action(layout, identity, lambda: inspect_store(layout))
        head = current_event(state, ledger_id)
        if head["policy_sha256"] != expected_digest:
            raise AdminError("policy_digest_mismatch", "current policy digest differs")
        intent = {
            "action": "revoke",
            "ledger_id": ledger_id,
            "policy_id": head["policy_id"],
            "policy_generation": head["generation"],
            "policy_sha256": expected_digest,
        }
        already_revoked = head["event_type"] == "revoke"
        verify_deployment(
            layout,
            manifest,
            identity,
            state=state,
            allowed_revocation=(
                intent
                if not already_revoked
                and entry_metadata_if_present(
                    revoke_path(layout, ledger_id, expected_digest), layout, identity
                )
                is not None
                else None
            ),
            allowed_stale_active=(
                active_index(state["policy_events"][-2]) if already_revoked else None
            ),
            allowed_pending_active=(json_bytes(active_index(head)) if already_revoked else None),
            validate_binding=validate_binding,
        )
        write_protected_file(
            revoke_path(layout, ledger_id, expected_digest),
            json_bytes(intent),
            0o600,
            identity.admin_uid,
            identity.admin_gid,
            layout,
            identity,
        )
        if after_intent:
            after_intent(intent)
        event = run_store_action(
            layout, identity, lambda: revoke_policy(layout, ledger_id, expected_digest)
        )
        if after_activation:
            after_activation(event)
        write_protected_file(
            layout.active_path,
            json_bytes(active_index(event)),
            0o600,
            identity.admin_uid,
            identity.admin_gid,
            layout,
            identity,
            replace=True,
        )
        final_state = run_store_action(layout, identity, lambda: inspect_store(layout))
        audit = verify_deployment(
            layout,
            manifest,
            identity,
            state=final_state,
            validate_binding=validate_binding,
        )
    return {
        "ok": True,
        "action": "revoke",
        "event": event,
        "audit": audit,
        "boundary_operational": False,
    }


def check_result(check_id: str, status: str, evidence: object) -> dict:
    if status not in {"pass", "fail", "unknown", "not_applicable"}:
        raise ValueError(f"invalid preflight status: {status}")
    return {"id": check_id, "status": status, "evidence": evidence}


def failed_preflight_report(admin_uid: int, error: object, failed_check_id: str) -> dict:
    checks = []
    for check_id in PREFLIGHT_CHECK_IDS:
        if check_id == "identity.admin_root":
            checks.append(check_result(check_id, "pass" if admin_uid == 0 else "fail", admin_uid))
        elif check_id == failed_check_id:
            checks.append(check_result(check_id, "fail", error))
        elif check_id == "broker.live_process":
            checks.append(
                check_result(
                    check_id,
                    "not_applicable",
                    "issue #5 does not start or enable the service",
                )
            )
        else:
            checks.append(
                check_result(
                    check_id,
                    "unknown",
                    {"blocked_by": "deployment_state", "error": error},
                )
            )
    return {
        "ok": True,
        "boundary_ready": False,
        "checks": checks,
        "stop_condition": "issue #7 real-host privilege proof is required",
    }


def run_sudo_listing(user: str) -> tuple[str, str]:
    try:
        completed = subprocess.run(
            ["/usr/bin/sudo", "-n", "-l", "-U", user],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"},
            cwd="/",
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return "unknown", str(exc)
    output = (completed.stdout + completed.stderr).strip()
    lowered = output.lower()
    if "not allowed to run sudo" in lowered or "may not run sudo" in lowered:
        return "pass", output
    if completed.returncode == 0:
        return "fail", output
    return "unknown", output


def run_probe(args: list[str], timeout: float = 5.0) -> tuple[int | None, str]:
    try:
        completed = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"},
            cwd="/",
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, str(exc)
    return completed.returncode, (completed.stdout + completed.stderr).strip()


def read_shadow_password_field(user: str) -> str | None:
    with open(SHADOW_PATH, encoding="ascii", errors="replace") as handle:
        for line in handle:
            fields = line.rstrip("\n").split(":")
            if fields and fields[0] == user:
                return fields[1] if len(fields) > 1 else ""
    return None


def collect_broker_account_properties(identity: DeploymentIdentity) -> dict:
    lock_status = "unknown"
    try:
        password_field = read_shadow_password_field(identity.broker_user)
        if password_field is None:
            shadow_error = "account not present in /etc/shadow"
        elif password_field == "":
            shadow_error = "account has an empty shadow password field"
        else:
            lock_status = "pass" if password_field.startswith(("!", "*")) else "fail"
            shadow_error = None
    except OSError as exc:
        shadow_error = str(exc)
    try:
        shell = pwd.getpwnam(identity.broker_user).pw_shell
    except KeyError as exc:
        return check_result("identity.broker_account_properties", "unknown", {"error": str(exc)})
    shell_status = "pass" if shell in NOLOGIN_SHELLS else "fail"
    statuses = {lock_status, shell_status}
    status = "fail" if "fail" in statuses else ("unknown" if "unknown" in statuses else "pass")
    return check_result(
        "identity.broker_account_properties",
        status,
        {
            "locked_status": lock_status,
            "shadow_error": shadow_error,
            "shell": shell,
            "shell_status": shell_status,
        },
    )


def collect_extended_acl_visibility(layout: InstallLayout) -> dict:
    paths = [
        layout.install_root,
        layout.config_root,
        layout.state_root,
        layout.runtime_root,
        layout.database_path,
        layout.socket_path,
    ]
    findings: dict[str, object] = {}
    saw_error = False
    for path in paths:
        if not path.exists():
            continue
        code, output = run_probe(["/usr/bin/getfacl", "-p", "--omit-header", str(path)])
        if code is None:
            saw_error = True
            findings[str(path)] = {"status": "unknown", "output": output}
            continue
        extra = [
            line
            for line in output.splitlines()
            if line and not line.startswith(("user::", "group::", "other::", "mask::", "flags:"))
        ]
        findings[str(path)] = {"status": "fail" if extra else "pass", "entries": extra}
    statuses = {entry["status"] for entry in findings.values()}
    status = "fail" if "fail" in statuses else ("unknown" if saw_error or not findings else "pass")
    return check_result("assets.extended_acl_visibility", status, findings)


def collect_sudo_cached_credentials(uid_names: dict[int, str]) -> dict:
    findings: dict[str, object] = {}
    for uid, name in uid_names.items():
        try:
            account_name = pwd.getpwuid(uid).pw_name
        except KeyError:
            findings[name] = {"status": "unknown", "reason": "account lookup failed"}
            continue
        cached = []
        for ts_dir in SUDO_TIMESTAMP_DIRS:
            candidate = ts_dir / account_name
            try:
                metadata = candidate.stat()
            except FileNotFoundError:
                continue
            except OSError as exc:
                cached.append({"path": str(candidate), "error": str(exc)})
                continue
            cached.append({"path": str(candidate), "mtime": metadata.st_mtime})
        findings[name] = {"status": "fail" if cached else "pass", "cached": cached}
    statuses = {entry["status"] for entry in findings.values()}
    status = "fail" if "fail" in statuses else ("unknown" if "unknown" in statuses else "pass")
    return check_result("sudo.cached_credentials", status, findings)


def collect_polkit_authorization(uid_names: dict[int, str]) -> dict:
    if not any(directory.is_dir() for directory in POLKIT_RULE_DIRS):
        return check_result(
            "polkit.authorization", "not_applicable", "no polkit rules.d directory present"
        )
    names = set(uid_names.values())
    matches = []
    for directory in POLKIT_RULE_DIRS:
        if not directory.is_dir():
            continue
        try:
            entries = sorted(directory.iterdir())
        except OSError as exc:
            return check_result(
                "polkit.authorization",
                "unknown",
                {"error": str(exc), "directory": str(directory)},
            )
        for entry in entries:
            try:
                text = entry.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                matches.append({"file": str(entry), "error": str(exc)})
                continue
            if "unix-user:*" in text:
                matches.append({"file": str(entry), "reason": "broad grant pattern"})
                continue
            for name in names:
                if name in text:
                    matches.append({"file": str(entry), "reason": f"references {name}"})
    return check_result("polkit.authorization", "fail" if matches else "pass", {"matches": matches})


def collect_service_delegated_control(layout: InstallLayout, uid_names: dict[int, str]) -> dict:
    names = set(uid_names.values())
    matches = []
    for directory in DBUS_SYSTEM_POLICY_DIRS:
        if not directory.is_dir():
            continue
        try:
            entries = sorted(directory.iterdir())
        except OSError as exc:
            return check_result(
                "service.delegated_control",
                "unknown",
                {"error": str(exc), "directory": str(directory)},
            )
        for entry in entries:
            try:
                text = entry.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                matches.append({"file": str(entry), "error": str(exc)})
                continue
            if "org.freedesktop.systemd1" not in text:
                continue
            for name in names:
                if f'user="{name}"' in text or f"user='{name}'" in text:
                    matches.append(
                        {"file": str(entry), "reason": f"grants systemd1 access to {name}"}
                    )
    return check_result(
        "service.delegated_control",
        "fail" if matches else "pass",
        {"unit": layout.unit_path.name, "matches": matches},
    )


def collect_service_unit_writability(layout: InstallLayout) -> dict:
    dropin_dirs = [
        Path(f"/etc/systemd/system/{layout.unit_path.name}.d"),
        Path(f"/run/systemd/system/{layout.unit_path.name}.d"),
        Path(f"/run/systemd/generator/{layout.unit_path.name}.d"),
        Path(f"/run/systemd/generator.late/{layout.unit_path.name}.d"),
    ]
    findings: dict[str, object] = {}
    for directory in dropin_dirs:
        try:
            metadata = directory.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            findings[str(directory)] = {"status": "unknown", "error": str(exc)}
            continue
        unsafe = (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != 0
            or stat.S_IMODE(metadata.st_mode) & 0o022
        )
        findings[str(directory)] = {
            "status": "fail" if unsafe else "pass",
            "mode": oct(stat.S_IMODE(metadata.st_mode)),
            "uid": metadata.st_uid,
        }
    statuses = {entry["status"] for entry in findings.values()}
    status = "fail" if "fail" in statuses else ("unknown" if "unknown" in statuses else "pass")
    return check_result("service.unit_writability", status, findings)


def collect_mount_redirection(layout: InstallLayout) -> dict:
    protected_roots = [
        layout.install_root,
        layout.config_root,
        layout.state_root,
        layout.runtime_root,
    ]
    try:
        with open("/proc/mounts", encoding="utf-8", errors="replace") as handle:
            mount_lines = handle.readlines()
    except OSError as exc:
        return check_result("mount.redirection", "unknown", {"error": str(exc)})
    mount_points = [fields[1] for line in mount_lines if len(fields := line.split()) > 1]
    overlaps = []
    for root in protected_roots:
        root_text = str(root)
        for point in mount_points:
            if point == root_text or point.startswith(root_text + "/"):
                overlaps.append({"protected_root": root_text, "mount_point": point})
    return check_result("mount.redirection", "fail" if overlaps else "pass", {"overlaps": overlaps})


def collect_capabilities_setuid_helpers(layout: InstallLayout) -> dict:
    scan_roots = [layout.install_root, *CAPABILITY_SCAN_ROOTS]
    setuid_files = []
    capability_findings = []
    allowlisted = []
    saw_error = False
    for root in scan_roots:
        if not root.is_dir():
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for filename in filenames:
                candidate = Path(dirpath) / filename
                try:
                    metadata = candidate.lstat()
                except OSError:
                    continue
                if stat.S_ISREG(metadata.st_mode) and metadata.st_mode & (
                    stat.S_ISUID | stat.S_ISGID
                ):
                    if str(candidate) in KNOWN_SAFE_SETUID_HELPERS:
                        allowlisted.append(str(candidate))
                    else:
                        setuid_files.append(str(candidate))
        code, output = run_probe(["/usr/sbin/getcap", "-r", str(root)])
        if code is None:
            saw_error = True
            continue
        for line in output.splitlines():
            if not any(capability in line.lower() for capability in DANGEROUS_CAPABILITIES):
                continue
            path = line.split("=", 1)[0].strip()
            if path in KNOWN_SAFE_SETUID_HELPERS:
                allowlisted.append(line)
            else:
                capability_findings.append(line)
    status = "fail" if setuid_files or capability_findings else ("unknown" if saw_error else "pass")
    return check_result(
        "capabilities.setuid_helpers",
        status,
        {
            "setuid_or_setgid_files": setuid_files,
            "capabilities": capability_findings,
            "allowlisted": allowlisted,
            "scanned": [str(root) for root in scan_roots],
        },
    )


def collect_process_control(identity: DeploymentIdentity) -> dict:
    try:
        scope = int(Path("/proc/sys/kernel/yama/ptrace_scope").read_text().strip())
        scope_status = "pass" if scope >= 1 else "fail"
    except (OSError, ValueError):
        scope, scope_status = None, "unknown"
    tracers = []
    try:
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                status_text = (entry / "status").read_text(encoding="ascii", errors="replace")
            except OSError:
                continue
            owner_uid = None
            tracer_pid = None
            for line in status_text.splitlines():
                if line.startswith("Uid:"):
                    owner_uid = int(line.split()[1])
                elif line.startswith("TracerPid:"):
                    tracer_pid = int(line.split()[1])
            if owner_uid in (0, identity.broker_uid) and tracer_pid:
                tracers.append(
                    {"pid": entry.name, "tracer_pid": tracer_pid, "owner_uid": owner_uid}
                )
    except OSError as exc:
        return check_result(
            "process.control", "unknown", {"error": str(exc), "ptrace_scope": scope}
        )
    status = "fail" if tracers else scope_status
    return check_result(
        "process.control", status, {"ptrace_scope": scope, "traced_privileged_processes": tracers}
    )


def collect_credentials_delegation(uid_names: dict[int, str]) -> dict:
    findings: dict[str, object] = {}
    for uid, name in uid_names.items():
        artifacts = []
        for candidate in (Path(f"/tmp/krb5cc_{uid}"), Path(f"/run/user/{uid}/krb5cc")):
            try:
                candidate.lstat()
            except FileNotFoundError:
                continue
            except OSError as exc:
                artifacts.append({"path": str(candidate), "error": str(exc)})
                continue
            artifacts.append({"path": str(candidate)})
        findings[name] = {"status": "fail" if artifacts else "pass", "artifacts": artifacts}
    statuses = {entry["status"] for entry in findings.values()}
    status = "fail" if "fail" in statuses else "pass"
    return check_result("credentials.delegation", status, findings)


def collect_privilege_evidence(
    layout: InstallLayout,
    identity: DeploymentIdentity,
    policy: PolicyDocument,
    *,
    now: int | None = None,
) -> dict:
    checks = [
        collect_broker_account_properties(identity),
        collect_extended_acl_visibility(layout),
        collect_sudo_cached_credentials(policy.uid_names),
        collect_polkit_authorization(policy.uid_names),
        collect_service_delegated_control(layout, policy.uid_names),
        collect_service_unit_writability(layout),
        collect_mount_redirection(layout),
        collect_capabilities_setuid_helpers(layout),
        collect_process_control(identity),
        collect_credentials_delegation(policy.uid_names),
    ]
    if tuple(check["id"] for check in checks) != EVIDENCE_CHECK_IDS:
        raise AdminError("evidence_catalog_error", "evidence catalog is incomplete")
    return {
        "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "ledger_id": policy.ledger_id,
        "policy_id": policy.policy_id,
        "policy_generation": policy.generation,
        "policy_sha256": policy.sha256,
        "collected_at": now if now is not None else int(time.time()),
        "checks": {
            check["id"]: {"status": check["status"], "evidence": check["evidence"]}
            for check in checks
        },
    }


def load_privilege_evidence(
    layout: InstallLayout,
    identity: DeploymentIdentity,
    policy: PolicyDocument,
    *,
    now: float | None = None,
) -> dict | None:
    try:
        data = read_protected_file(
            layout.evidence_path,
            0o600,
            identity.admin_uid,
            identity.admin_gid,
            layout,
            identity,
        )
    except AdminError as exc:
        if exc.code == "protected_file_missing":
            return None
        raise
    evidence = decode_canonical(data, "privilege evidence")
    require_exact_keys(
        evidence,
        {
            "evidence_schema_version",
            "ledger_id",
            "policy_id",
            "policy_generation",
            "policy_sha256",
            "collected_at",
            "checks",
        },
        "privilege evidence",
    )
    if evidence["evidence_schema_version"] != EVIDENCE_SCHEMA_VERSION:
        raise AdminError("unsupported_evidence_schema", "unsupported privilege evidence schema")
    if not isinstance(evidence["checks"], dict) or set(evidence["checks"]) != set(
        EVIDENCE_CHECK_IDS
    ):
        raise AdminError("evidence_catalog_error", "privilege evidence catalog is incomplete")
    for check_id, entry in evidence["checks"].items():
        if not isinstance(entry, dict) or set(entry) != {"status", "evidence"}:
            raise AdminError("evidence_catalog_error", f"malformed evidence entry: {check_id}")
        if entry["status"] not in {"pass", "fail", "unknown", "not_applicable"}:
            raise AdminError("evidence_catalog_error", f"invalid evidence status: {check_id}")
    current_time = now if now is not None else time.time()
    bound = (
        evidence["ledger_id"] == policy.ledger_id
        and evidence["policy_id"] == policy.policy_id
        and evidence["policy_generation"] == policy.generation
        and evidence["policy_sha256"] == policy.sha256
    )
    collected_at = evidence["collected_at"]
    fresh = (
        isinstance(collected_at, (int, float))
        and not isinstance(collected_at, bool)
        and 0 <= current_time - collected_at <= EVIDENCE_MAX_AGE_SECONDS
    )
    evidence["trusted"] = bool(bound and fresh)
    return evidence


def mode_allows_write(metadata: os.stat_result, uid: int, groups: set[int]) -> bool:
    mode = stat.S_IMODE(metadata.st_mode)
    if uid == metadata.st_uid:
        return bool(mode & stat.S_IWUSR)
    if metadata.st_gid in groups:
        return bool(mode & stat.S_IWGRP)
    return bool(mode & stat.S_IWOTH)


def preflight_filesystem_deployment(
    layout: InstallLayout,
    manifest: dict,
    identity: DeploymentIdentity,
) -> tuple[dict, PolicyDocument]:
    for raw_path, expected in manifest["assets"].items():
        verify_asset(Path(raw_path), expected, layout, identity)
    reject_pending_protected_files(
        [Path(raw_path) for raw_path in manifest["assets"]]
        + [layout.active_path, layout.manifest_path],
        layout,
        identity,
    )
    verify_admin_lock(layout, identity)
    exact_directories = (
        (layout.install_root, 0o755, identity.admin_uid, identity.admin_gid),
        (layout.config_root, 0o700, identity.admin_uid, identity.admin_gid),
        (layout.policies_root, 0o700, identity.admin_uid, identity.admin_gid),
        (
            layout.policies_root / manifest["ledger_id"],
            0o700,
            identity.admin_uid,
            identity.admin_gid,
        ),
        (layout.revocations_root, 0o700, identity.admin_uid, identity.admin_gid),
        (
            layout.revocations_root / manifest["ledger_id"],
            0o700,
            identity.admin_uid,
            identity.admin_gid,
        ),
        (layout.state_root, 0o700, identity.broker_uid, identity.broker_gid),
        (layout.content_root, 0o700, identity.broker_uid, identity.broker_gid),
        (layout.content_root / "sha256", 0o700, identity.broker_uid, identity.broker_gid),
        (layout.runtime_root, 0o2750, identity.broker_uid, identity.socket_gid),
    )
    for values in exact_directories:
        validate_exact_directory(*values, layout, identity)
    validate_store_boundary(layout, identity, require_database=True)
    with open_layout_directory(layout.policies_root, layout, identity) as root_fd:
        if set(os.listdir(root_fd)) != {manifest["ledger_id"]}:
            raise AdminError("policy_archive_mismatch", "policy ledger directory set differs")
    policies: list[PolicyDocument] = []
    policy_root = layout.policies_root / manifest["ledger_id"]
    with open_layout_directory(policy_root, layout, identity) as policy_fd:
        names = sorted(os.listdir(policy_fd))
    if not names:
        raise AdminError("policy_archive_mismatch", "policy archive is empty")
    for name in names:
        match = re.fullmatch(r"([0-9]{20})-([0-9a-f]{64})\.json", name)
        if not match:
            raise AdminError("policy_archive_mismatch", "policy archive has an unsafe entry")
        data = read_protected_file(
            policy_root / name,
            0o600,
            identity.admin_uid,
            identity.admin_gid,
            layout,
            identity,
        )
        try:
            policy = parse_policy_object(broker.decode_json(data))
        except broker.BrokerError as exc:
            raise AdminError("policy_archive_mismatch", exc.message) from exc
        if (
            policy.ledger_id != manifest["ledger_id"]
            or policy.policy_id != manifest["policy_id"]
            or policy.generation != int(match.group(1))
            or policy.sha256 != match.group(2)
            or data != (policy.canonical_json + "\n").encode("ascii")
        ):
            raise AdminError("policy_archive_mismatch", "policy archive entry differs")
        policies.append(policy)
    for index, policy in enumerate(policies):
        if policy.generation != index + 1:
            raise AdminError("policy_archive_mismatch", "policy generations are not contiguous")
        if index == 0:
            if policy.previous_sha256 is not None:
                raise AdminError("policy_archive_mismatch", "generation one predecessor differs")
        elif policy.previous_sha256 != policies[index - 1].sha256:
            raise AdminError("policy_archive_mismatch", "policy archive history is forked")
    active = decode_canonical(
        read_protected_file(
            layout.active_path,
            0o600,
            identity.admin_uid,
            identity.admin_gid,
            layout,
            identity,
        ),
        "active index",
    )
    require_exact_keys(
        active,
        {
            "active_index_schema_version",
            "authority",
            "ledger_id",
            "state",
            "policy_id",
            "policy_generation",
            "policy_sha256",
            "policy_event_hash",
        },
        "active index",
    )
    current = policies[-1]
    if (
        active["active_index_schema_version"] != ACTIVE_INDEX_SCHEMA_VERSION
        or active["authority"] != "ledger_policy_events"
        or active["ledger_id"] != current.ledger_id
        or active["policy_id"] != current.policy_id
        or active["policy_generation"] != current.generation
        or active["policy_sha256"] != current.sha256
        or active["state"] not in {"active", "revoked"}
    ):
        raise AdminError("active_index_mismatch", "active index differs from policy archive")
    require_sha256(active["policy_event_hash"], "policy_event_hash")
    with open_layout_directory(layout.revocations_root, layout, identity) as root_fd:
        if set(os.listdir(root_fd)) != {manifest["ledger_id"]}:
            raise AdminError(
                "revocation_archive_mismatch", "revocation ledger directory set differs"
            )
    expected_revocations = (
        {revoke_path(layout, current.ledger_id, current.sha256).name}
        if active["state"] == "revoked"
        else set()
    )
    with open_layout_directory(
        layout.revocations_root / manifest["ledger_id"], layout, identity
    ) as revocation_fd:
        if set(os.listdir(revocation_fd)) != expected_revocations:
            raise AdminError("revocation_archive_mismatch", "revocation archive differs")
    if expected_revocations:
        intent = decode_canonical(
            read_protected_file(
                revoke_path(layout, current.ledger_id, current.sha256),
                0o600,
                identity.admin_uid,
                identity.admin_gid,
                layout,
                identity,
            ),
            "revocation intent",
        )
        expected_intent = {
            "action": "revoke",
            "ledger_id": current.ledger_id,
            "policy_id": current.policy_id,
            "policy_generation": current.generation,
            "policy_sha256": current.sha256,
        }
        if intent != expected_intent:
            raise AdminError("revocation_intent_mismatch", "revocation intent differs")
    verify_socket_path(layout, identity)
    return (
        {
            "filesystem_only": True,
            "ledger_id": manifest["ledger_id"],
            "policy_generations": len(policies),
            "current": active,
            "database_metadata_checked": True,
        },
        current,
    )


def collect_structural_preflight_violations(
    layout: InstallLayout,
    manifest: dict,
    identity: DeploymentIdentity,
) -> list[dict]:
    violations: list[dict] = []

    def probe(subject: str, callback: Callable[[], object]) -> None:
        try:
            callback()
        except (AdminError, broker.BrokerError, OSError) as exc:
            if isinstance(exc, AdminError):
                error = exc.as_dict()
            elif isinstance(exc, broker.BrokerError):
                error = {"code": exc.code, "message": exc.message}
            else:
                error = {"code": "preflight_state_error", "message": str(exc)}
            record = {"subject": subject, "error": error}
            if record not in violations:
                violations.append(record)

    for raw_path, expected in manifest["assets"].items():
        probe(
            raw_path,
            lambda raw_path=raw_path, expected=expected: verify_asset(
                Path(raw_path), expected, layout, identity
            ),
        )
    pending_targets = [Path(raw_path) for raw_path in manifest["assets"]]
    pending_targets += [layout.active_path, layout.manifest_path]
    for target in pending_targets:
        probe(
            f"pending:{target}",
            lambda target=target: reject_pending_protected_files([target], layout, identity),
        )
    probe("administration_lock", lambda: verify_admin_lock(layout, identity))
    probe("broker_socket", lambda: verify_socket_path(layout, identity))
    exact_directories = (
        (layout.install_root, 0o755, identity.admin_uid, identity.admin_gid),
        (layout.config_root, 0o700, identity.admin_uid, identity.admin_gid),
        (layout.policies_root, 0o700, identity.admin_uid, identity.admin_gid),
        (
            layout.policies_root / manifest["ledger_id"],
            0o700,
            identity.admin_uid,
            identity.admin_gid,
        ),
        (layout.revocations_root, 0o700, identity.admin_uid, identity.admin_gid),
        (
            layout.revocations_root / manifest["ledger_id"],
            0o700,
            identity.admin_uid,
            identity.admin_gid,
        ),
        (layout.state_root, 0o700, identity.broker_uid, identity.broker_gid),
        (layout.content_root, 0o700, identity.broker_uid, identity.broker_gid),
        (layout.content_root / "sha256", 0o700, identity.broker_uid, identity.broker_gid),
        (layout.runtime_root, 0o2750, identity.broker_uid, identity.socket_gid),
    )
    for values in exact_directories:
        probe(
            str(values[0]),
            lambda values=values: validate_exact_directory(*values, layout, identity),
        )
    probe(
        str(layout.database_path),
        lambda: validate_store_boundary(layout, identity, require_database=True),
    )
    probe(
        "policy_and_revocation_archives",
        lambda: preflight_filesystem_deployment(layout, manifest, identity),
    )
    return violations


def privilege_preflight(
    layout: InstallLayout,
    admin_uid: int,
    admin_gid: int,
    *,
    sudo_probe: Callable[[str], tuple[str, str]] = run_sudo_listing,
    validate_binding: bool = True,
    now: float | None = None,
) -> dict:
    try:
        manifest, identity = load_manifest(
            layout, admin_uid, admin_gid, validate_binding=validate_binding
        )
        violations = collect_structural_preflight_violations(layout, manifest, identity)
        if violations:
            return failed_preflight_report(
                admin_uid,
                {"code": "boundary_violations", "violations": violations},
                "assets.protected_paths",
            )
        structural, policy = preflight_filesystem_deployment(layout, manifest, identity)
        evidence = load_privilege_evidence(layout, identity, policy, now=now)
    except (AdminError, broker.BrokerError, OSError, sqlite3.Error) as exc:
        if isinstance(exc, AdminError):
            error = exc.as_dict()
            identity_codes = {
                "identity_binding_changed",
                "identity_lookup_failed",
                "missing_account",
                "unsafe_broker_identity",
                "unsafe_socket_group",
                "unsafe_privileged_runtime",
            }
            failed_check_id = (
                "identity.broker_binding"
                if exc.code in identity_codes
                else "assets.protected_paths"
            )
        elif isinstance(exc, broker.BrokerError):
            error = {"code": exc.code, "message": exc.message}
            failed_check_id = "assets.protected_paths"
        else:
            error = {"code": "preflight_state_error", "message": str(exc)}
            failed_check_id = "assets.protected_paths"
        return failed_preflight_report(admin_uid, error, failed_check_id)

    def evidence_check(check_id: str) -> dict:
        if evidence is not None and evidence["trusted"]:
            entry = evidence["checks"][check_id]
            return check_result(check_id, entry["status"], entry["evidence"])
        return check_result(check_id, "unknown", EVIDENCE_UNKNOWN_MESSAGES[check_id])

    checks = [
        check_result("identity.admin_root", "pass" if admin_uid == 0 else "fail", admin_uid),
        check_result(
            "identity.broker_binding",
            "pass" if validate_binding else "unknown",
            {
                "user": identity.broker_user,
                "uid": identity.broker_uid,
                "gid": identity.broker_gid,
                "socket_group": identity.socket_group,
                "socket_gid": identity.socket_gid,
            },
        ),
        evidence_check("identity.broker_account_properties"),
    ]
    unsafe_uids = sorted(set(policy.uid_names) & {0, identity.broker_uid})
    checks.append(
        check_result(
            "identity.agent_uids_distinct",
            "pass" if not unsafe_uids else "fail",
            {"unsafe_uids": unsafe_uids},
        )
    )
    broker_members = []
    socket_missing = []
    risky_memberships: dict[str, list[str]] = {}
    sudo_evidence: dict[str, dict] = {}
    privileged_socket_evidence: dict[str, object] = {}
    lookup_unknown = False
    for uid, name in policy.uid_names.items():
        try:
            account = pwd.getpwuid(uid)
            memberships = group_ids(account)
            group_names = {grp.getgrgid(group_id).gr_name for group_id in memberships}
        except (KeyError, AdminError) as exc:
            lookup_unknown = True
            broker_members.append(uid)
            socket_missing.append(uid)
            risky_memberships[name] = ["identity-lookup-failed"]
            sudo_evidence[name] = {"status": "unknown", "output": str(exc)}
            privileged_socket_evidence[name] = {"status": "unknown", "paths": []}
            continue
        if identity.broker_gid in memberships:
            broker_members.append(uid)
        if identity.socket_gid not in memberships:
            socket_missing.append(uid)
        risky_memberships[name] = sorted(group_names & RISKY_GROUPS)
        sudo_status, sudo_output = sudo_probe(account.pw_name)
        sudo_evidence[name] = {"status": sudo_status, "output": sudo_output}
        writable = []
        errors = []
        for socket_path in PRIVILEGED_SOCKETS:
            try:
                metadata = socket_path.stat()
            except FileNotFoundError:
                continue
            except OSError as exc:
                errors.append({"path": str(socket_path), "error": str(exc)})
                continue
            if mode_allows_write(metadata, uid, memberships):
                writable.append(str(socket_path))
        privileged_socket_evidence[name] = {
            "status": "unknown" if errors else ("fail" if writable else "pass"),
            "paths": writable,
            "errors": errors,
        }
    checks.append(
        check_result(
            "identity.agents_outside_broker_group",
            "unknown" if lookup_unknown else ("pass" if not broker_members else "fail"),
            {"uids": broker_members},
        )
    )
    checks.append(
        check_result(
            "identity.socket_group_membership",
            "unknown" if lookup_unknown else ("pass" if not socket_missing else "fail"),
            {"missing_uids": socket_missing},
        )
    )
    checks.extend(
        [
            check_result("assets.protected_paths", "pass", structural),
            evidence_check("assets.extended_acl_visibility"),
        ]
    )
    sudo_statuses = {entry["status"] for entry in sudo_evidence.values()}
    sudo_status = (
        "fail" if "fail" in sudo_statuses else ("unknown" if "unknown" in sudo_statuses else "pass")
    )
    checks.append(check_result("sudo.authorization", sudo_status, sudo_evidence))
    checks.extend(
        [
            evidence_check("sudo.cached_credentials"),
            evidence_check("polkit.authorization"),
        ]
    )
    risky = any(groups for groups in risky_memberships.values())
    checks.append(
        check_result(
            "container.management_groups",
            "unknown" if lookup_unknown else ("fail" if risky else "pass"),
            risky_memberships,
        )
    )
    socket_statuses = {value["status"] for value in privileged_socket_evidence.values()}
    socket_status = (
        "fail"
        if "fail" in socket_statuses
        else ("unknown" if "unknown" in socket_statuses else "pass")
    )
    checks.append(
        check_result(
            "container.privileged_sockets",
            socket_status,
            privileged_socket_evidence,
        )
    )
    checks.extend(
        [
            evidence_check("service.delegated_control"),
            evidence_check("service.unit_writability"),
            evidence_check("mount.redirection"),
            evidence_check("capabilities.setuid_helpers"),
            evidence_check("process.control"),
            evidence_check("credentials.delegation"),
            check_result(
                "broker.live_process",
                "not_applicable",
                "issue #5 does not start or enable the service",
            ),
        ]
    )
    if tuple(check["id"] for check in checks) != PREFLIGHT_CHECK_IDS:
        raise AdminError("preflight_catalog_error", "preflight catalog is incomplete")
    return {
        "ok": True,
        "boundary_ready": all(check["status"] in {"pass", "not_applicable"} for check in checks),
        "checks": checks,
        "stop_condition": "issue #7 real-host privilege proof is required",
    }


def collect_evidence_deployment(
    layout: InstallLayout,
    admin_uid: int,
    admin_gid: int,
    *,
    validate_binding: bool = True,
    collector: Callable[
        [InstallLayout, DeploymentIdentity, PolicyDocument], dict
    ] = collect_privilege_evidence,
) -> dict:
    manifest, identity = load_manifest(
        layout, admin_uid, admin_gid, validate_binding=validate_binding
    )
    violations = collect_structural_preflight_violations(layout, manifest, identity)
    if violations:
        raise AdminError(
            "boundary_violations",
            "cannot collect privilege evidence over a broken deployment",
            violations=violations,
        )
    _structural, policy = preflight_filesystem_deployment(layout, manifest, identity)
    evidence = collector(layout, identity, policy)
    write_protected_file(
        layout.evidence_path,
        json_bytes(evidence),
        0o600,
        identity.admin_uid,
        identity.admin_gid,
        layout,
        identity,
        replace=True,
    )
    return {
        "ok": True,
        "action": "collect-evidence",
        "evidence_path": str(layout.evidence_path),
        "policy_sha256": policy.sha256,
        "checks": evidence["checks"],
    }


def validate_local_ledger(repo_path: Path) -> dict:
    import yaml

    op_dir = repo_path / ".operator"
    if not op_dir.is_dir():
        raise AdminError("unsafe_enrollment", f"Operator ledger is missing: {op_dir}")

    ledger_db = op_dir / "ledger.sqlite3"
    if not ledger_db.exists():
        raise AdminError("unsafe_enrollment", f"Durable ledger store is missing: {ledger_db}")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory_flags = flags | os.O_DIRECTORY
    try:
        with contextlib.ExitStack() as stack:
            repo_fd = os.open(repo_path, directory_flags)
            stack.callback(os.close, repo_fd)
            op_fd = os.open(".operator", directory_flags, dir_fd=repo_fd)
            stack.callback(os.close, op_fd)
            db_fd = os.open("ledger.sqlite3", flags, dir_fd=op_fd)
            stack.callback(os.close, db_fd)
            identities = {
                "repository": os.fstat(repo_fd),
                "operator": os.fstat(op_fd),
                "ledger": os.fstat(db_fd),
            }
            if identities["repository"].st_mode & 0o022:
                raise AdminError("unsafe_enrollment", "repository path is group/other writable")
            if identities["operator"].st_mode & 0o022:
                raise AdminError("unsafe_enrollment", "operator path is group/other writable")
            if identities["ledger"].st_mode & 0o022 or identities["ledger"].st_nlink != 1:
                raise AdminError("unsafe_enrollment", "ledger database metadata is unsafe")
            if identities["operator"].st_uid != identities["repository"].st_uid:
                raise AdminError(
                    "unsafe_enrollment", "operator directory owner differs from repository"
                )
            if identities["ledger"].st_uid != identities["repository"].st_uid:
                raise AdminError(
                    "unsafe_enrollment", "ledger database owner differs from repository"
                )
            for suffix in ("-wal", "-shm", "-journal"):
                try:
                    os.stat(f"ledger.sqlite3{suffix}", dir_fd=op_fd, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                raise AdminError("unsafe_enrollment", "ledger has active SQLite sidecar state")

            conn = sqlite3.connect(f"file:/proc/self/fd/{db_fd}?mode=ro&immutable=1", uri=True)
            conn.row_factory = sqlite3.Row
            try:
                schema_version = conn.execute("PRAGMA user_version").fetchone()[0]
                if schema_version != 1:
                    raise AdminError(
                        "unsafe_enrollment",
                        f"Durable ledger schema version {schema_version} is unsupported",
                    )

                triggers = {
                    row["name"]: " ".join(row["sql"].lower().split())
                    for row in conn.execute(
                        "SELECT name, sql FROM sqlite_master WHERE type = 'trigger' "
                        "AND name IN ('ledger_events_no_update', 'ledger_events_no_delete')"
                    )
                }
                expected_triggers = {
                    "ledger_events_no_update": "create trigger ledger_events_no_update before update on ledger_events begin select raise(abort, 'ledger_events is append-only'); end",
                    "ledger_events_no_delete": "create trigger ledger_events_no_delete before delete on ledger_events begin select raise(abort, 'ledger_events is append-only'); end",
                }
                if triggers != expected_triggers:
                    raise AdminError(
                        "unsafe_enrollment", "Durable ledger append-only triggers differ"
                    )

                rows = conn.execute(
                    """
                    SELECT event_id, record_type, record_id, version, event_type, payload_json,
                           actor_uid, actor_name, created_at, source_command, previous_event_hash,
                           event_hash
                    FROM ledger_events
                    ORDER BY record_type, record_id, version
                    """
                ).fetchall()
            finally:
                conn.close()
    except sqlite3.Error as exc:
        raise AdminError("unsafe_enrollment", f"Durable ledger cannot be read: {exc}")
    except OSError as exc:
        raise AdminError("unsafe_enrollment", f"Durable ledger path cannot be opened: {exc}")

    chain_state = {}
    latest_events = {}
    for row in rows:
        key = (row["record_type"], row["record_id"])
        previous = chain_state.get(key)
        expected_version = previous[0] + 1 if previous else 1
        expected_previous_hash = previous[1] if previous else None

        if row["version"] != expected_version:
            raise AdminError(
                "unsafe_enrollment",
                f"Durable ledger version gap for {key[0]} {key[1]}: expected {expected_version}, got {row['version']}",
            )
        if row["previous_event_hash"] != expected_previous_hash:
            raise AdminError(
                "unsafe_enrollment",
                f"Durable ledger hash chain is broken for {key[0]} {key[1]} at version {row['version']}",
            )

        try:
            decoded_payload = json.loads(row["payload_json"])
            if broker.canonical_json(decoded_payload) != row["payload_json"]:
                raise AdminError(
                    "unsafe_enrollment",
                    f"Durable ledger payload is not canonical for {key[0]} {key[1]} version {row['version']}",
                )
        except (TypeError, ValueError, json.JSONDecodeError):
            raise AdminError(
                "unsafe_enrollment",
                f"Durable ledger payload is invalid JSON for {key[0]} {key[1]} version {row['version']}",
            )

        hash_fields = {
            "hash_format": "operator-ledger-event-v1",
            "record_type": row["record_type"],
            "record_id": row["record_id"],
            "version": row["version"],
            "event_type": row["event_type"],
            "payload_json": row["payload_json"],
            "actor_uid": row["actor_uid"],
            "actor_name": row["actor_name"],
            "created_at": row["created_at"],
            "source_command": row["source_command"],
            "previous_event_hash": row["previous_event_hash"],
        }
        computed_hash = hashlib.sha256(
            broker.canonical_json(hash_fields).encode("utf-8")
        ).hexdigest()
        if row["event_hash"] != computed_hash or row["event_id"] != row["event_hash"]:
            raise AdminError(
                "unsafe_enrollment",
                f"Durable ledger event hash mismatch for {key[0]} {key[1]} version {row['version']}",
            )

        chain_state[key] = (row["version"], row["event_hash"])
        latest_events[key] = decoded_payload

    for key, expected_fields in latest_events.items():
        rtype, rid = key
        if rtype == "task":
            filepath = op_dir / "tasks" / f"{rid}.yaml"
        elif rtype == "claim":
            filepath = op_dir / "claims" / f"{rid}.yaml"
        elif rtype == "evidence":
            task_id = expected_fields.get("task_id")
            if not task_id:
                raise AdminError(
                    "unsafe_enrollment", f"Evidence {rid} is missing task_id in database payload"
                )
            leaf_id = rid.split("/", 1)[-1]
            filepath = op_dir / "evidence" / task_id / f"{leaf_id}.yaml"
        elif rtype == "handoff":
            task_id = expected_fields.get("task_id")
            if not task_id:
                raise AdminError(
                    "unsafe_enrollment", f"Handoff {rid} is missing task_id in database payload"
                )
            leaf_id = rid.split("/", 1)[-1]
            filepath = op_dir / "handoffs" / task_id / f"{leaf_id}.yaml"
        else:
            filepath = op_dir / f"{rtype}s" / f"{rid}.yaml"

        if not filepath.exists():
            raise AdminError(
                "unsafe_enrollment", f"YAML projection missing for {rtype} {rid}: {filepath}"
            )

        try:
            with open(filepath, "r") as f:
                yaml_payload = yaml.safe_load(f)
        except Exception as exc:
            raise AdminError("unsafe_enrollment", f"Failed to load YAML for {rtype} {rid}: {exc}")

        if broker.canonical_json(yaml_payload) != broker.canonical_json(expected_fields):
            raise AdminError(
                "unsafe_enrollment",
                f"Durable ledger mismatch for {rtype} {rid}: YAML projection differs from database",
            )

    for label, path in (("repository", repo_path), ("operator", op_dir), ("ledger", ledger_db)):
        after = path.lstat()
        before = identities[label]
        if (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino):
            raise AdminError("unsafe_enrollment", f"{label} path changed during preflight")

    anchors = [
        {
            "record_type": record_type,
            "record_id": record_id,
            "version": version,
            "event_hash": event_hash,
        }
        for (record_type, record_id), (version, event_hash) in sorted(chain_state.items())
    ]
    return {
        "repository_identity": {
            "repository_path": str(repo_path),
            "repository_device": identities["repository"].st_dev,
            "repository_inode": identities["repository"].st_ino,
            "operator_device": identities["operator"].st_dev,
            "operator_inode": identities["operator"].st_ino,
            "ledger_device": identities["ledger"].st_dev,
            "ledger_inode": identities["ledger"].st_ino,
        },
        "anchor_records": anchors,
        "legacy_anchor_sha256": broker.sha256_text(broker.canonical_json(anchors)),
    }


def read_registry_file_safely(
    path: Path,
    expected_uid: int,
    anchor: Path,
    expected_gid: int = 0,
    expected_mode: int = 0o644,
) -> dict:
    with open_admin_directory(path.parent, anchor, expected_uid) as parent_fd:
        try:
            fd, data, metadata = open_regular_at(parent_fd, path.name, MAX_ADMIN_FILE_BYTES)
        except OSError as exc:
            raise AdminError("registry_unavailable", f"could not read registry: {exc}")
        try:
            if (
                metadata.st_uid != expected_uid
                or metadata.st_gid != expected_gid
                or stat.S_IMODE(metadata.st_mode) != expected_mode
            ):
                raise AdminError("unsafe_registry", "registry file has unsafe owner or permissions")
            registry = broker.decode_json(data)
            if not isinstance(registry, dict):
                raise AdminError("unsafe_registry", "registry is not an object")
            require_exact_keys(registry, {"schema_version", "registrations"}, "registry")
            if registry["schema_version"] != 1 or not isinstance(registry["registrations"], list):
                raise AdminError("unsafe_registry", "registry schema is invalid")
            return registry
        finally:
            os.close(fd)


def write_registry_file_safely(
    path: Path,
    data: bytes,
    expected_mode: int = 0o644,
    *,
    replace: bool = False,
    expected_uid: int = 0,
    expected_gid: int = 0,
    anchor: Path = Path("/"),
) -> None:
    with open_admin_directory(path.parent, anchor, expected_uid) as parent_fd:
        try:
            fd, existing, metadata = open_regular_at(parent_fd, path.name, len(data) + 1)
        except FileNotFoundError:
            fd = -1
            existing = None
            metadata = None

        if metadata is not None and (
            metadata.st_uid != expected_uid
            or metadata.st_gid != expected_gid
            or stat.S_IMODE(metadata.st_mode) != expected_mode
            or metadata.st_nlink != 1
        ):
            if fd >= 0:
                os.close(fd)
            raise AdminError("unsafe_registry", f"registry file metadata differs: {path}")

        if existing is not None and not replace:
            try:
                if (
                    existing != data
                    or metadata is None
                    or metadata.st_uid != expected_uid
                    or stat.S_IMODE(metadata.st_mode) != expected_mode
                ):
                    raise AdminError("protected_file_conflict", f"registry file differs: {path}")
                os.fsync(fd)
                os.fsync(parent_fd)
            finally:
                os.close(fd)
            return

        if fd >= 0:
            os.close(fd)

        pending = f".{path.name}.pending"
        remove_stale_pending(
            parent_fd,
            pending,
            data,
            expected_uid,
            expected_gid,
            expected_mode,
        )

        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        temp_fd = os.open(pending, flags, expected_mode, dir_fd=parent_fd)
        try:
            os.fchown(temp_fd, expected_uid, expected_gid)
            os.fchmod(temp_fd, expected_mode)
            write_all(temp_fd, data)
            os.fsync(temp_fd)
        finally:
            os.close(temp_fd)

        try:
            if replace:
                os.replace(pending, path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            else:
                rename_noreplace(parent_fd, pending, path.name)
            os.fsync(parent_fd)
        except FileExistsError:
            os.unlink(pending, dir_fd=parent_fd)
            os.fsync(parent_fd)
            fd, existing, metadata = open_regular_at(parent_fd, path.name, len(data) + 1)
            try:
                if (
                    existing != data
                    or metadata.st_uid != expected_uid
                    or stat.S_IMODE(metadata.st_mode) != expected_mode
                ):
                    raise AdminError("protected_file_conflict", f"registry file differs: {path}")
                os.fsync(fd)
                os.fsync(parent_fd)
            finally:
                os.close(fd)


def enroll_repository(
    registry_path: Path,
    repo_path: Path,
    ledger_id: str,
    socket_path: Path,
    *,
    registry_owner_uid: int = 0,
    registry_owner_gid: int = 0,
    registry_anchor: Path = Path("/"),
    request_sender: Callable[[Path, object], dict] = broker.send_request,
) -> dict:
    if repo_path.is_symlink():
        raise AdminError("unsafe_enrollment", "repository path must not be a symlink")
    canonical_repo = repo_path.resolve(strict=True)
    migration = validate_local_ledger(canonical_repo)
    registry_data = {"schema_version": 1, "registrations": []}
    if registry_path.exists():
        try:
            registry_data = read_registry_file_safely(
                registry_path,
                registry_owner_uid,
                registry_anchor,
                registry_owner_gid,
            )
        except Exception as exc:
            raise AdminError("registry_corrupt", f"Existing registry file is corrupt: {exc}")

    operation = {"kind": "ledger.enroll", **migration}
    operation_digest = broker.sha256_text(
        broker.canonical_json({"ledger_id": ledger_id, "operation": operation})
    )
    request = {
        "protocol_version": broker.PROTOCOL_VERSION,
        "action": "commit",
        "ledger_id": ledger_id,
        "operation_key": f"enroll-{operation_digest[:48]}",
        "operation": operation,
        "expected": [],
        "blob": None,
    }
    try:
        response = request_sender(socket_path, request)
    except (broker.BrokerError, OSError, TimeoutError) as exc:
        raise AdminError("broker_unavailable", f"Enrollment broker request failed: {exc}")
    if not isinstance(response, dict):
        raise AdminError("invalid_broker_receipt", "Broker enrollment response is not an object")
    if not response.get("ok") or not isinstance(response.get("receipt"), dict):
        error = response.get("error", {})
        raise AdminError(
            "enrollment_rejected",
            f"Broker rejected enrollment: {error.get('code', 'invalid_response')}",
        )
    receipt = response["receipt"]
    policy = receipt.get("policy")
    if (
        receipt.get("ledger_id") != ledger_id
        or receipt.get("operation") != "ledger.enroll"
        or receipt.get("operation_key") != request["operation_key"]
        or receipt.get("commit_sequence") != 1
        or not isinstance(policy, dict)
        or set(policy) != {"id", "generation", "sha256"}
        or not isinstance(policy["id"], str)
        or not policy["id"]
        or not isinstance(policy["generation"], int)
        or isinstance(policy["generation"], bool)
        or policy["generation"] < 1
        or not isinstance(policy["sha256"], str)
        or not broker.VALID_SHA256.fullmatch(policy["sha256"])
        or not isinstance(receipt.get("receipt_hash"), str)
        or not broker.VALID_SHA256.fullmatch(receipt["receipt_hash"])
    ):
        raise AdminError("invalid_broker_receipt", "Broker enrollment receipt is inconsistent")

    registration = {
        "repository_path": str(canonical_repo),
        "ledger_id": ledger_id,
        "socket_path": str(socket_path),
        **migration,
        "policy_binding": receipt["policy"],
        "first_broker_sequence": receipt["commit_sequence"],
        "enrollment_receipt_hash": receipt["receipt_hash"],
    }
    registrations = []
    matched = False
    for existing in registry_data["registrations"]:
        if not isinstance(existing, dict) or "repository_path" not in existing:
            raise AdminError("unsafe_registry", "registry contains a malformed registration")
        if Path(existing["repository_path"]).resolve() == canonical_repo:
            if existing != registration:
                raise AdminError("enrollment_conflict", "repository is enrolled differently")
            matched = True
        registrations.append(existing)
    if not matched:
        registrations.append(registration)
    registry_data["registrations"] = registrations
    content_bytes = (broker.canonical_json(registry_data) + "\n").encode("utf-8")
    try:
        write_registry_file_safely(
            registry_path,
            content_bytes,
            expected_mode=0o644,
            replace=True,
            expected_uid=registry_owner_uid,
            expected_gid=registry_owner_gid,
            anchor=registry_anchor,
        )
    except Exception as exc:
        raise AdminError(
            "registry_publication_pending",
            f"Broker committed enrollment but registry publication failed: {exc}",
            receipt_hash=receipt["receipt_hash"],
        )

    return {
        "ok": True,
        "enrolled_path": str(canonical_repo),
        "ledger_id": ledger_id,
        "anchor_records_count": len(migration["anchor_records"]),
        "legacy_anchor_sha256": migration["legacy_anchor_sha256"],
        "first_broker_sequence": receipt["commit_sequence"],
        "policy_binding": receipt["policy"],
        "idempotent_replay": response.get("idempotent_replay", False) or matched,
    }


def absolute_path(value: str, field: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise AdminError("invalid_path", f"{field} must be an absolute path")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Root-managed Operator authority policy lifecycle")
    commands = parser.add_subparsers(dest="command", required=True)
    install = commands.add_parser("install")
    install.add_argument("--policy", required=True)
    install.add_argument("--source-dir", default=str(Path(__file__).resolve().parent))
    install.add_argument("--broker-user", default=DEFAULT_BROKER_USER)
    install.add_argument("--socket-group", default=DEFAULT_SOCKET_GROUP)
    rotate = commands.add_parser("rotate")
    rotate.add_argument("--policy", required=True)
    revoke = commands.add_parser("revoke")
    revoke.add_argument("--ledger-id", required=True)
    revoke.add_argument("--expected-policy-sha256", required=True)
    commands.add_parser("audit")
    commands.add_parser("preflight")
    commands.add_parser("collect-evidence")

    enroll = commands.add_parser("enroll")
    enroll.add_argument("--repository-path", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        require_root()
        layout = InstallLayout.production()
        if args.command == "install":
            policy_file = absolute_path(args.policy, "policy")
            source_dir = absolute_path(args.source_dir, "source-dir")
            policy = read_policy_file(policy_file, 0)
            identity = resolve_identity(policy, args.broker_user, args.socket_group)
            result = install_deployment(
                layout,
                source_dir,
                policy_file,
                identity,
                validate_accounts=True,
            )
        elif args.command == "rotate":
            result = rotate_deployment(
                layout,
                absolute_path(args.policy, "policy"),
                0,
                0,
                validate_accounts=True,
            )
        elif args.command == "revoke":
            result = revoke_deployment(
                layout,
                args.ledger_id,
                args.expected_policy_sha256,
                0,
                0,
            )
        elif args.command == "audit":
            result = audit_deployment(layout, 0, 0)
        elif args.command == "collect-evidence":
            result = collect_evidence_deployment(layout, 0, 0)
        elif args.command == "enroll":
            repo_path = absolute_path(args.repository_path, "repository-path")
            deployment = audit_deployment(layout, 0, 0)
            if deployment["current"]["state"] != "active":
                raise AdminError("policy_revoked", "cannot enroll under a revoked policy")
            boundary = privilege_preflight(layout, 0, 0)
            if not boundary["boundary_ready"]:
                unresolved = [
                    check["id"]
                    for check in boundary["checks"]
                    if check["status"] not in {"pass", "not_applicable"}
                ]
                raise AdminError(
                    "privilege_precondition_unproven",
                    "enrollment is blocked until every privilege precondition passes",
                    unresolved_checks=unresolved,
                )
            result = enroll_repository(
                REGISTRY_PATH,
                repo_path,
                deployment["ledger_id"],
                layout.socket_path,
            )
        else:
            result = privilege_preflight(layout, 0, 0)
        print(broker.canonical_json(result))
        return 0
    except (AdminError, broker.BrokerError, OSError, sqlite3.Error) as exc:
        if isinstance(exc, AdminError):
            error = exc.as_dict()
        elif isinstance(exc, broker.BrokerError):
            error = {"code": exc.code, "message": exc.message}
        else:
            error = {"code": "admin_io_error", "message": str(exc)}
        print(broker.canonical_json({"ok": False, "error": error}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
