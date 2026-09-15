#!/usr/bin/env python3
"""Safe, local text operations for a shared Markdown blackboard (POSIX)."""

import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time


def apply_patch(original, patch_text):
    # Git parses and applies the diff. We only constrain its target and effects.
    with tempfile.TemporaryDirectory(prefix="blackboard-patch-") as directory:
        root = Path(directory).resolve()
        target = root / "BLACKBOARD.md"
        target.write_bytes(original)
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        env.update({
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CEILING_DIRECTORIES": str(root.parent), "GIT_ATTR_NOSYSTEM": "1",
        })
        for options in (("--numstat", "-z"), ("--summary",), ()):
            try:
                result = subprocess.run(
                    ["git", "-c", "core.attributesFile=" + os.devnull,
                     "apply", "--whitespace=nowarn", "-p1", *options, "-"],
                    input=patch_text.encode("utf-8"), cwd=root, env=env,
                    capture_output=True, timeout=10,
                )
            except FileNotFoundError:
                raise ValueError("patch requires Git installed and available on PATH") from None
            except subprocess.TimeoutExpired:
                raise TimeoutError("git apply timeout; original board unchanged") from None
            if result.returncode:
                raise ValueError("git apply rejected patch: " + result.stderr.decode("utf-8", errors="replace").strip())
            if options == ("--numstat", "-z"):
                fields = result.stdout.split(b"\t")
                if (len(fields) != 3 or not fields[0].isdigit() or not fields[1].isdigit()
                        or fields[2] != b"BLACKBOARD.md\0"):
                    raise ValueError("patch must modify only the text file BLACKBOARD.md")
            elif options == ("--summary",) and result.stdout.strip():
                raise ValueError("patch cannot create, delete, rename, copy, or change file modes")
        if target.is_symlink() or not target.is_file() or set(root.iterdir()) != {target}:
            raise ValueError("patch changed unexpected files; original board unchanged")
        data = target.read_bytes()
        data.decode("utf-8")
        return data


def write_board(board, operation, payload, expected_sha256=None, lock_timeout=5):
    if not math.isfinite(lock_timeout) or lock_timeout < 0:
        raise ValueError("lock timeout must be finite and nonnegative")
    if operation not in {"init", "append", "patch", "save"}:
        raise ValueError("unknown write operation")
    if not isinstance(payload, str):
        raise ValueError("text input required")
    if operation in {"patch", "save"} and not expected_sha256:
        raise ValueError("patch and save require expected_sha256 from read")
    # Validate encoding before creating any filesystem artifacts.
    if isinstance(payload, str):
        payload.encode("utf-8")
    if operation == "init":
        board.parent.mkdir(parents=True, exist_ok=True)
    lock_path = board.parent / ".blackboard.lock"
    with lock_path.open("a+b") as lock:
        deadline = time.monotonic() + lock_timeout
        while True:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("blackboard lock timeout; nothing saved")
                time.sleep(min(0.05, remaining))
        try:
            if operation == "init":
                if board.exists():
                    raise ValueError("board already exists; init never overwrites")
                data = payload.encode("utf-8")
                mode = 0o600
            else:
                original = board.read_bytes()
                digest = hashlib.sha256(original).hexdigest()
                if expected_sha256 is not None and digest != expected_sha256:
                    raise ValueError("board digest changed; reread and reconsider the edit")
                text = original.decode("utf-8")
                if operation == "patch":
                    data = apply_patch(original, payload)
                elif operation == "save":
                    data = payload.encode("utf-8")
                else:
                    data = (text + payload).encode("utf-8")
                mode = stat.S_IMODE(board.stat().st_mode)
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    dir=board.parent, prefix=".blackboard-", suffix=".tmp", delete=False
                ) as temporary:
                    temp_path = Path(temporary.name)
                    os.fchmod(temporary.fileno(), mode)
                    temporary.write(data)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                os.replace(temp_path, board)
            finally:
                if temp_path is not None:
                    temp_path.unlink(missing_ok=True)
            return {"path": str(board), "sha256": hashlib.sha256(data).hexdigest()}
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    for name in ("init", "read", "append", "patch", "save"):
        command = commands.add_parser(name)
        command.add_argument("board", help="absolute path to BLACKBOARD.md")
        if name != "read":
            command.add_argument("--input", default="-", help="UTF-8 input file, or - for stdin")
            command.add_argument("--lock-timeout", type=float, default=5)
            if name != "init":
                command.add_argument("--expected-sha256", required=name in {"patch", "save"})
    args = parser.parse_args()
    try:
        board = Path(args.board)
        if not board.is_absolute():
            raise ValueError("board path must be absolute")
        board = board.resolve()
        if args.operation == "read":
            data = board.read_bytes()
            result = {
                "path": str(board),
                "sha256": hashlib.sha256(data).hexdigest(),
                "text": data.decode("utf-8"),
            }
        else:
            raw = sys.stdin.buffer.read() if args.input == "-" else Path(args.input).read_bytes()
            payload = raw.decode("utf-8")
            result = write_board(
                board, args.operation, payload,
                getattr(args, "expected_sha256", None), args.lock_timeout,
            )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
