#!/usr/bin/python3 -I
"""Wait for the broker socket and expose it to the fixed client group."""

from __future__ import annotations

import argparse
import os
import stat
import sys
import time
from pathlib import Path

RUNTIME_MODE = 0o2750
SOCKET_MODE = 0o660


def open_runtime(socket_path: Path, expected_gid: int) -> int:
    if not socket_path.is_absolute() or socket_path.name in {"", ".", ".."}:
        raise RuntimeError("socket path must be an absolute file path")
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    parent_fd = os.open(socket_path.parent, flags)
    parent = os.fstat(parent_fd)
    if (
        not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != os.geteuid()
        or parent.st_gid != expected_gid
        or stat.S_IMODE(parent.st_mode) != RUNTIME_MODE
    ):
        os.close(parent_fd)
        raise RuntimeError("runtime directory metadata differs")
    return parent_fd


def remove_stale_socket(socket_path: Path, expected_gid: int) -> None:
    parent_fd = open_runtime(socket_path, expected_gid)
    try:
        try:
            before = os.stat(socket_path.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        if (
            not stat.S_ISSOCK(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid != os.geteuid()
            or before.st_gid != expected_gid
            or stat.S_IMODE(before.st_mode) not in {0o600, SOCKET_MODE}
        ):
            raise RuntimeError("stale broker socket metadata differs")
        os.unlink(socket_path.name, dir_fd=parent_fd)
        os.fsync(parent_fd)
        try:
            os.stat(socket_path.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        raise RuntimeError("stale broker socket changed during removal")
    finally:
        os.close(parent_fd)


def prepare_socket(socket_path: Path, expected_gid: int, timeout: float = 10.0) -> None:
    parent_fd = open_runtime(socket_path, expected_gid)
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                before = os.stat(socket_path.name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("broker socket did not become ready")
                time.sleep(0.02)
                continue
            if (
                not stat.S_ISSOCK(before.st_mode)
                or before.st_nlink != 1
                or before.st_uid != os.geteuid()
                or before.st_gid != expected_gid
                or stat.S_IMODE(before.st_mode) not in {0o600, SOCKET_MODE}
            ):
                raise RuntimeError("broker socket metadata differs")
            os.chmod(
                socket_path.name,
                SOCKET_MODE,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
            after = os.stat(socket_path.name, dir_fd=parent_fd, follow_symlinks=False)
            if (
                (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino)
                or not stat.S_ISSOCK(after.st_mode)
                or after.st_uid != os.geteuid()
                or after.st_gid != expected_gid
                or stat.S_IMODE(after.st_mode) != SOCKET_MODE
            ):
                raise RuntimeError("broker socket changed while permissions were applied")
            return
    finally:
        os.close(parent_fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", required=True, type=Path)
    parser.add_argument("--expected-gid", required=True, type=int)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--remove-stale", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.remove_stale:
            remove_stale_socket(args.socket, args.expected_gid)
        else:
            prepare_socket(args.socket, args.expected_gid, args.timeout)
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
