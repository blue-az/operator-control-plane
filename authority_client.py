from __future__ import annotations

import array
import json
import os
import socket
import stat
import struct
from pathlib import Path

def get_registry_path() -> Path:
    return Path(
        os.environ.get("OPERATOR_REGISTRY_PATH", "/etc/operator-control-plane-registry.json")
    )


FRAME_HEADER_BYTES = 4
MAX_REQUEST_BYTES = 1 * 1024 * 1024  # 1 MiB
MAX_RESPONSE_BYTES = 16 * 1024 * 1024  # 16 MiB


class BrokerClientError(Exception):
    pass


def verify_registry_file(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            return False
        is_test = "OPERATOR_REGISTRY_PATH" in os.environ
        if not is_test and metadata.st_uid != 0:
            return False
        if metadata.st_mode & 0o022:  # group or other writable
            return False
        return True
    except Exception:
        return False


def resolve_enrollment(cwd: Path | None = None) -> tuple[str, str] | None:
    reg_path = get_registry_path()
    if not verify_registry_file(reg_path):
        return None

    if cwd is None:
        cwd = Path.cwd()
    resolved_cwd = cwd.resolve()

    # Walk upward to find the repository containing .operator
    repo_root = resolved_cwd
    for parent in [resolved_cwd] + list(resolved_cwd.parents):
        if (parent / ".operator").is_dir():
            repo_root = parent
            break

    repo_root_str = str(repo_root)

    try:
        with open(reg_path, "r") as f:
            registry = json.load(f)
        for reg in registry.get("registrations", []):
            reg_repo_path = os.path.realpath(os.path.expanduser(reg.get("repository_path", "")))
            if reg_repo_path == repo_root_str:
                return reg.get("ledger_id"), reg.get("socket_path")
    except Exception:
        return None
    return None


def canonical_json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


class AuthorityClient:
    def __init__(self, socket_path: str):
        self.socket_path = socket_path

    def send_request(self, request: dict, evidence_path: str | None = None) -> dict:
        request["protocol_version"] = 1
        data = canonical_json(request).encode("utf-8")
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
