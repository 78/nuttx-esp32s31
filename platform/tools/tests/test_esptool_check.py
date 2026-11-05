#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded CLI regressions for the esptool version check (no hardware)."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


CHECK = (Path(__file__).resolve().parents[3] / "nuttx" / "tools" /
         "espressif" / "check_esptool.py")


class EsptoolCheckTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def tool(self, name, version, status=0):
        path = self.root / name
        path.write_text(
            '#!/bin/sh\n[ "$1" = version ] || exit 99\n'
            f"printf '%s\\n' '{version}'\nexit {status}\n")
        path.chmod(0o755)
        return path

    def check(self, *arguments, minimum="4.8.0"):
        return subprocess.run(
            [sys.executable, str(CHECK), "-v", minimum, *map(str, arguments)],
            env={**os.environ, "PATH": str(self.root)},
            text=True, capture_output=True, timeout=10)

    def test_modern_command_without_legacy_alias(self):
        self.tool("esptool", "esptool v5.6.0")
        self.assertEqual(self.check().returncode, 0)

    def test_legacy_command(self):
        self.tool("esptool.py", "esptool.py v4.8")
        self.assertEqual(self.check().returncode, 0)

    def test_explicit_executable_overrides_path_and_handles_spaces(self):
        self.tool("esptool", "esptool v3.0.0")
        selected = self.tool("selected esptool", "esptool v5.6.0")
        self.assertEqual(self.check("--esptool", selected).returncode, 0)

    def test_explicit_old_executable_is_not_hidden_by_path(self):
        self.tool("esptool", "esptool v5.6.0")
        selected = self.tool("selected", "esptool v4.7.0")
        self.assertEqual(self.check("--esptool", selected).returncode, 1)

    def test_patch_version_is_enforced(self):
        self.tool("esptool", "esptool v4.8.0")
        self.assertEqual(self.check(minimum="4.8.1").returncode, 1)

    def test_invalid_version_is_rejected(self):
        self.tool("esptool", "unknown")
        self.assertEqual(self.check().returncode, 1)

    def test_failed_command_is_rejected(self):
        self.tool("esptool", "esptool v5.6.0", status=1)
        self.assertEqual(self.check().returncode, 1)

    def test_missing_command_is_rejected(self):
        self.assertEqual(self.check().returncode, 1)
        self.assertEqual(self.check("--esptool", self.root / "missing").returncode,
                         1)


if __name__ == "__main__":
    unittest.main()
