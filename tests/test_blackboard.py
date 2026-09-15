import concurrent.futures
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "skills/blackboard/scripts/blackboard.py"
spec = importlib.util.spec_from_file_location("blackboard", SCRIPT)
bb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bb)


class BlackboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.board = Path(self.temp.name) / "BLACKBOARD.md"

    def cli(self, operation, content=None, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), operation, str(self.board), *args],
            input=content, capture_output=True, timeout=15,
        )

    def test_cli_roundtrip_and_input_file(self):
        source = Path(self.temp.name) / "input.md"
        original = "# 调查\r\n\r\n```sql\r\nSELECT 1;\r\n```\r\n".encode()
        source.write_bytes(original)
        result = self.cli("init", None, "--input", str(source))
        self.assertEqual(result.returncode, 0, result.stderr)
        read = self.cli("read")
        self.assertEqual(read.returncode, 0, read.stderr)
        value = json.loads(read.stdout)
        self.assertEqual(value["text"].encode(), original)
        self.assertEqual(value["sha256"], hashlib.sha256(original).hexdigest())
        result = self.cli("append", "日志：已验证。\r\n".encode())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.board.read_bytes(), original + "日志：已验证。\r\n".encode())
        original = self.board.read_bytes()
        result = self.cli("init", b"overwrite")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.board.read_bytes(), original)

    def test_parallel_appends(self):
        bb.write_board(self.board, "init", "# board\n")
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda i: self.cli("append", f"agent-{i}\n".encode()), range(24)))
        for result in results:
            self.assertEqual(result.returncode, 0, result.stderr)
        lines = self.board.read_text().splitlines()
        self.assertEqual(len(lines), 25)
        self.assertEqual(set(lines[1:]), {f"agent-{i}" for i in range(24)})

    def diff(self, old, new):
        return "".join(difflib.unified_diff(
            old.splitlines(keepends=True), new.splitlines(keepends=True),
            fromfile="a/BLACKBOARD.md", tofile="b/BLACKBOARD.md",
        ))

    def test_patch_without_repository_and_save(self):
        old = "# 调查\n\n状态：等待\n证据：无\n"
        new = "# 调查\n\n状态：完成\n证据：trace.log\n"
        digest = bb.write_board(self.board, "init", old)["sha256"]
        result = self.cli("patch", self.diff(old, new).encode(), "--expected-sha256", digest)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.board.read_text(), new)
        source = self.board.parent / "new.md"
        source.write_bytes("# 重组\r\n完整内容，无末尾换行".encode())
        result = self.cli("save", None, "--input", str(source), "--expected-sha256", json.loads(result.stdout)["sha256"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.board.read_bytes(), source.read_bytes())

    def test_patch_and_save_compete_for_same_version(self):
        digest = bb.write_board(self.board, "init", "pending\n")["sha256"]
        requests = [("patch", self.diff("pending\n", "patched\n").encode()), ("save", b"saved\n")]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(
                lambda request: self.cli(*request, "--expected-sha256", digest), requests,
            ))
        self.assertEqual(sorted(r.returncode for r in results), [0, 1])
        self.assertIn(self.board.read_text(), {"patched\n", "saved\n"})

    def test_both_require_digest_and_reject_stale_digest(self):
        digest = bb.write_board(self.board, "init", "pending\n")["sha256"]
        bb.write_board(self.board, "append", "other agent\n")
        before = self.board.read_bytes()
        for operation, body in (("patch", self.diff("pending\n", "done\n")), ("save", "done\n")):
            with self.subTest(operation=operation):
                self.assertNotEqual(self.cli(operation, body.encode()).returncode, 0)
                with self.assertRaises(ValueError):
                    bb.write_board(self.board, operation, body)
                result = self.cli(operation, body.encode(), "--expected-sha256", digest)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.board.read_bytes(), before)
        self.assertNotEqual(self.cli("replace", b"[]").returncode, 0)

    def test_patch_multiple_hunks_and_failure_is_atomic(self):
        old = "".join(f"line {i}\n" for i in range(20))
        new = old.replace("line 1\n", "changed 1\n").replace("line 18\n", "changed 18\n")
        digest = bb.write_board(self.board, "init", old)["sha256"]
        delta = self.diff(old, new)
        broken = delta.replace("-line 18", "-does not exist")
        result = self.cli("patch", broken.encode(), "--expected-sha256", digest)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.board.read_text(), old)
        result = self.cli("patch", delta.encode(), "--expected-sha256", digest)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.board.read_text(), new)

    def test_patch_rejects_paths_and_metadata(self):
        digest = bb.write_board(self.board, "init", "old\n")["sha256"]
        normal = self.diff("old\n", "new\n")
        for delta in (
            normal.replace("BLACKBOARD.md", "../outside.md"),
            normal.replace("BLACKBOARD.md", "/tmp/outside.md"),
            normal + normal.replace("BLACKBOARD.md", "other.md"),
            "diff --git a/BLACKBOARD.md b/BLACKBOARD.md\nold mode 100644\nnew mode 100755\n" + normal,
            "diff --git a/BLACKBOARD.md b/BLACKBOARD.md\ndeleted file mode 100644\n--- a/BLACKBOARD.md\n+++ /dev/null\n@@ -1 +0,0 @@\n-old\n",
            "diff --git a/BLACKBOARD.md b/BLACKBOARD.md\nnew file mode 100644\n--- /dev/null\n+++ b/BLACKBOARD.md\n@@ -0,0 +1 @@\n+new\n",
            "diff --git a/BLACKBOARD.md b/other.md\nsimilarity index 100%\nrename from BLACKBOARD.md\nrename to other.md\n",
            "diff --git a/BLACKBOARD.md b/BLACKBOARD.md\nold mode 100644\nnew mode 120000\n" + normal,
            "diff --git a/BLACKBOARD.md b/BLACKBOARD.md\nBinary files a/BLACKBOARD.md and b/BLACKBOARD.md differ\n",
            "", "not a patch", normal + normal,
        ):
            with self.subTest(delta=delta):
                result = self.cli("patch", delta.encode(), "--expected-sha256", digest)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertEqual(self.board.read_text(), "old\n")

    def test_git_missing_timeout_and_inherited_environment(self):
        original = b"old\n"
        delta = self.diff("old\n", "new\n")
        with patch.object(bb.subprocess, "run", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(ValueError, "requires Git"):
                bb.apply_patch(original, delta)
        with patch.object(bb.subprocess, "run", side_effect=subprocess.TimeoutExpired("git", 10)):
            with self.assertRaisesRegex(TimeoutError, "timeout"):
                bb.apply_patch(original, delta)
        with patch.dict(bb.os.environ, {"GIT_DIR": "/not/a/repository", "GIT_WORK_TREE": str(self.board.parent), "GIT_CONFIG_COUNT": "9"}):
            self.assertEqual(bb.apply_patch(original, delta), b"new\n")

    def test_lock_timeout_and_recovery_after_process_exit(self):
        bb.write_board(self.board, "init", "before")
        code = (
            "import fcntl,sys,time; f=open(sys.argv[1],'a+b'); "
            "fcntl.flock(f,fcntl.LOCK_EX); print('locked',flush=True); time.sleep(30)"
        )
        process = subprocess.Popen(
            [sys.executable, "-c", code, str(self.board.parent / ".blackboard.lock")],
            stdout=subprocess.PIPE, text=True,
        )
        try:
            self.assertEqual(process.stdout.readline().strip(), "locked")
            result = self.cli("append", b"after", "--lock-timeout", "0.1")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"lock timeout", result.stderr)
            self.assertEqual(self.board.read_text(), "before")
        finally:
            process.kill()
            process.wait(timeout=5)
            process.stdout.close()
        self.assertEqual(self.cli("append", b"after").returncode, 0)
        self.assertEqual(self.board.read_text(), "beforeafter")

    def test_publication_failure_preserves_original(self):
        bb.write_board(self.board, "init", "original")
        with patch.object(bb.os, "replace", side_effect=OSError("simulated publication failure")):
            with self.assertRaises(OSError):
                bb.write_board(self.board, "append", "new")
        self.assertEqual(self.board.read_text(), "original")
        self.assertFalse(list(self.board.parent.glob(".blackboard-*.tmp")))
        bb.write_board(self.board, "append", "new")
        self.assertEqual(self.board.read_text(), "originalnew")

    def test_crash_before_publication(self):
        bb.write_board(self.board, "init", "original")
        code = (
            "import importlib.util,os,sys,pathlib; "
            "s=importlib.util.spec_from_file_location('bb',sys.argv[1]); "
            "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
            "m.os.replace=lambda *args: os._exit(9); "
            "m.write_board(pathlib.Path(sys.argv[2]),'append','new')"
        )
        result = subprocess.run([sys.executable, "-c", code, str(SCRIPT), str(self.board)], timeout=10)
        self.assertEqual(result.returncode, 9)
        self.assertEqual(self.board.read_text(), "original")
        self.assertTrue(list(self.board.parent.glob(".blackboard-*.tmp")))
        read = self.cli("read")
        self.assertEqual(json.loads(read.stdout)["text"], "original")
        self.assertEqual(self.cli("append", b"new").returncode, 0)

    def test_invalid_cli_and_missing_board(self):
        for value in ("nan", "inf", "-1"):
            self.assertNotEqual(self.cli("init", b"X", "--lock-timeout", value).returncode, 0)
            self.assertFalse(self.board.exists())
        self.assertNotEqual(self.cli("append", b"X").returncode, 0)
        self.assertFalse(self.board.exists())
        bb.write_board(self.board, "init", "original")
        digest = hashlib.sha256(self.board.read_bytes()).hexdigest()
        for operation in ("patch", "save"):
            result = self.cli(operation, b"\xff", "--expected-sha256", digest)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self.board.read_text(), "original")

    def test_canonical_alias_and_permissions(self):
        bb.write_board(self.board, "init", "original")
        self.board.chmod(0o640)
        alias = self.board.parent / "alias.md"
        alias.symlink_to(self.board)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "append", str(alias)],
            input=b"new", capture_output=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(alias.is_symlink())
        self.assertEqual(self.board.read_text(), "originalnew")
        self.assertEqual(self.board.stat().st_mode & 0o777, 0o640)


if __name__ == "__main__":
    unittest.main()
