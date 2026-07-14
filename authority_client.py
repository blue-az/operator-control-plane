from __future__ import annotations

import array
import json
import os
import socket
import stat
import struct
from dataclasses import dataclass
from pathlib import Path

REGISTRY_PATH = Path("/etc/operator-control-plane-registry.json")
REGISTRY_OWNER_UID = 0
REQUIRE_TRUSTED_ANCESTORS = True


FRAME_HEADER_BYTES = 4
MAX_REQUEST_BYTES = 1 * 1024 * 1024  # 1 MiB
MAX_RESPONSE_BYTES = 16 * 1024 * 1024  # 16 MiB


class BrokerClientError(Exception):
    pass


class EnrollmentError(RuntimeError):
    pass


@dataclass(frozen=True)
class Enrollment:
    ledger_id: str
    socket_path: str
    repository_path: Path


def _validate_registry_path(path: Path) -> None:
    if path != REGISTRY_PATH:
        raise EnrollmentError("authority registry path is not the fixed production path")
    if not REQUIRE_TRUSTED_ANCESTORS:
        return
    current = Path(path.anchor)
    for part in path.parts[1:-1]:
        current /= part
        metadata = current.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise EnrollmentError(f"authority registry ancestor is unsafe: {current}")
        if metadata.st_uid != REGISTRY_OWNER_UID or metadata.st_mode & 0o022:
            raise EnrollmentError(f"authority registry ancestor is writable by an agent: {current}")


def _load_registry() -> dict | None:
    if not REGISTRY_PATH.exists():
        return None
    try:
        _validate_registry_path(REGISTRY_PATH)
        before = REGISTRY_PATH.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or before.st_uid != REGISTRY_OWNER_UID
            or before.st_mode & 0o022
            or before.st_nlink != 1
        ):
            raise EnrollmentError(f"authority registry file is unsafe: {REGISTRY_PATH}")
        fd = os.open(REGISTRY_PATH, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            opened = os.fstat(fd)
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise EnrollmentError("authority registry changed while it was opened")
            with os.fdopen(fd, "r", encoding="utf-8") as handle:
                fd = -1
                registry = json.load(handle)
        finally:
            if fd >= 0:
                os.close(fd)
    except EnrollmentError:
        raise
    except (OSError, ValueError, TypeError) as exc:
        raise EnrollmentError(f"cannot safely read authority registry: {exc}") from exc
    if not isinstance(registry, dict) or registry.get("schema_version") != 1:
        raise EnrollmentError("authority registry has an unsupported schema")
    registrations = registry.get("registrations")
    if not isinstance(registrations, list):
        raise EnrollmentError("authority registry registrations must be a list")
    return registry


def resolve_enrollment(cwd: Path | None = None) -> Enrollment | None:
    registry = _load_registry()
    if registry is None:
        return None
    if cwd is None:
        cwd = Path.cwd()
    resolved_cwd = cwd.resolve(strict=True)
    matches: list[Enrollment] = []
    for registration in registry["registrations"]:
        if not isinstance(registration, dict):
            raise EnrollmentError("authority registry contains a malformed registration")
        try:
            repository = Path(registration["repository_path"])
            ledger_id = registration["ledger_id"]
            socket_path = registration["socket_path"]
        except KeyError as exc:
            raise EnrollmentError(f"authority registration is missing {exc.args[0]}") from exc
        if not repository.is_absolute() or not isinstance(ledger_id, str) or not ledger_id:
            raise EnrollmentError(
                "authority registration has invalid repository or ledger identity"
            )
        if not isinstance(socket_path, str) or not os.path.isabs(socket_path):
            raise EnrollmentError("authority registration socket path must be absolute")
        try:
            resolved_repository = repository.resolve(strict=True)
        except FileNotFoundError:
            # A registration whose repository no longer exists on disk cannot
            # contain the (existing, strictly-resolved) cwd. Skip it instead
            # of letting one stale entry crash every command for every repo.
            continue
        if resolved_cwd == resolved_repository or resolved_repository in resolved_cwd.parents:
            matches.append(Enrollment(ledger_id, socket_path, resolved_repository))
    if not matches:
        return None
    matches.sort(key=lambda item: len(item.repository_path.parts), reverse=True)
    if len(matches) > 1 and matches[0].repository_path == matches[1].repository_path:
        raise EnrollmentError("authority registry contains duplicate repository registrations")
    return matches[0]


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


class AuthorityClient:
    def __init__(self, socket_path: str):
        self.socket_path = socket_path

    def send_request(self, request: dict, evidence_path: str | None = None) -> dict:
        wire_request = dict(request)
        if wire_request.get("protocol_version", 1) != 1:
            raise BrokerClientError("unsupported protocol_version")
        wire_request["protocol_version"] = 1
        data = canonical_json(wire_request).encode("utf-8")
        if len(data) > MAX_REQUEST_BYTES:
            raise BrokerClientError(f"Request too large: {len(data)} bytes")

        frame = struct.pack("!I", len(data)) + data
        ancillary = []
        evidence_fd = None
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

        try:
            connection.connect(self.socket_path)

            if evidence_path is not None:
                evidence_fd = os.open(evidence_path, os.O_RDONLY)
                descriptors = array.array("i", [evidence_fd])
                ancillary.append((socket.SOL_SOCKET, socket.SCM_RIGHTS, descriptors))

            sent = connection.sendmsg([frame], ancillary)
            if sent == 0:
                raise BrokerClientError("Connection closed before request could be written")
            if sent < len(frame):
                connection.sendall(frame[sent:])

            # Read response frame
            descriptor_size = array.array("i").itemsize
            receive_flags = getattr(socket, "MSG_CMSG_CLOEXEC", 0)
            first_chunk, ancillary_recv, flags, _ = connection.recvmsg(
                min(65536, MAX_RESPONSE_BYTES + FRAME_HEADER_BYTES),
                socket.CMSG_SPACE(descriptor_size * 2),
                receive_flags,
            )

            received_fds = []
            try:
                if not first_chunk:
                    raise BrokerClientError(
                        "Connection closed by server before response was received"
                    )
                for level, kind, payload in ancillary_recv:
                    if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                        descriptors = array.array("i")
                        descriptors.frombytes(
                            payload[: len(payload) - (len(payload) % descriptor_size)]
                        )
                        received_fds.extend(descriptors)

                if received_fds:
                    for fd in received_fds:
                        try:
                            os.close(fd)
                        except Exception:
                            pass

                if flags & getattr(socket, "MSG_CTRUNC", 0):
                    raise BrokerClientError("Ancillary socket data was truncated")

                framed = bytearray(first_chunk)
                while len(framed) < FRAME_HEADER_BYTES:
                    chunk = connection.recv(FRAME_HEADER_BYTES - len(framed))
                    if not chunk:
                        raise BrokerClientError("Connection closed during frame header")
                    framed.extend(chunk)

                payload_size = struct.unpack("!I", framed[:FRAME_HEADER_BYTES])[0]
                if payload_size == 0:
                    raise BrokerClientError("JSON frame is empty")
                if payload_size > MAX_RESPONSE_BYTES:
                    raise BrokerClientError(f"Response frame too large: {payload_size} bytes")

                frame_size = FRAME_HEADER_BYTES + payload_size
                if len(framed) > frame_size:
                    raise BrokerClientError("Connection sent extra bytes after the frame")

                while len(framed) < frame_size:
                    chunk = connection.recv(min(65536, frame_size - len(framed)))
                    if not chunk:
                        raise BrokerClientError("Connection closed during JSON frame")
                    framed.extend(chunk)

                response_data = json.loads(bytes(framed[FRAME_HEADER_BYTES:]).decode("utf-8"))
                return response_data
            except Exception:
                raise
        finally:
            if evidence_fd is not None:
                try:
                    os.close(evidence_fd)
                except Exception:
                    pass
            try:
                connection.close()
            except Exception:
                pass
