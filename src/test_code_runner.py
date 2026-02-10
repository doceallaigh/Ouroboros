"""
Unit tests for code_runner module.

Tests command execution and error handling for run_tests.
"""

import os
import tempfile
import unittest
import subprocess
from unittest import mock

from code_runner import CodeRunner, CodeRunError


class TestCodeRunnerRunTests(unittest.TestCase):
    """Test CodeRunner.run_tests behavior."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.runner = CodeRunner()

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_run_tests_success(self):
        """Should run tests and write logs when log_path is provided."""
        completed = subprocess.CompletedProcess(
            args=["python", "-m", "pytest"],
            returncode=0,
            stdout="ok\n",
            stderr="",
        )
        log_path = os.path.join(self.temp_dir, "logs", "output.txt")

        with mock.patch("code_runner.subprocess.run", return_value=completed):
            result = self.runner.run_tests(
                command=["python", "-m", "pytest"],
                cwd=self.temp_dir,
                timeout=10,
                log_path=log_path,
            )

        self.assertEqual(result["exit_code"], 0)
        self.assertFalse(result["timed_out"])
        self.assertEqual(result["stdout"], "ok\n")
        self.assertTrue(os.path.exists(log_path))

        with open(log_path, "r", encoding="utf-8") as handle:
            content = handle.read()
        self.assertIn("STDOUT:", content)
        self.assertIn("ok", content)
        self.assertIn("EXIT_CODE: 0", content)

    def test_run_tests_timeout(self):
        """Should return timed_out=True on timeout."""
        timeout_exc = subprocess.TimeoutExpired(cmd=["python"], timeout=1, output="out", stderr="err")

        with mock.patch("code_runner.subprocess.run", side_effect=timeout_exc):
            result = self.runner.run_tests(
                command=["python", "-m", "pytest"],
                cwd=self.temp_dir,
                timeout=1,
            )

        self.assertTrue(result["timed_out"])
        self.assertIsNone(result["exit_code"])
        self.assertEqual(result["stdout"], "out")
        self.assertEqual(result["stderr"], "err")

    def test_run_tests_invalid_command(self):
        """Should reject invalid commands."""
        with self.assertRaises(CodeRunError):
            self.runner.run_tests(command=[], cwd=self.temp_dir)

        with self.assertRaises(CodeRunError):
            self.runner.run_tests(command=["python", 123], cwd=self.temp_dir)

    def test_run_tests_invalid_cwd(self):
        """Should reject invalid working directory."""
        with self.assertRaises(CodeRunError):
            self.runner.run_tests(command=["python", "-m", "pytest"], cwd="/nope")


if __name__ == "__main__":
    unittest.main()
