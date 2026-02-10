"""
Code execution module for compiling, interpreting, and running code.

Currently supports Python execution. Designed to expand for additional languages.
"""

import os
import subprocess
import sys
import tempfile
import time
from typing import Dict, Optional


class CodeRunError(Exception):
    """Raised when code execution fails due to invalid inputs or runtime issues."""
    pass


class CodeRunner:
    """
    Executes code snippets in a controlled manner.

    Notes:
    - Uses the current Python interpreter for execution.
    - Writes code to a temporary file in the working directory.
    """

    def run_tests(
        self,
        command: list,
        cwd: str,
        timeout: int = 300,
        log_path: Optional[str] = None,
    ) -> Dict[str, object]:
        """
        Execute a test command and return stdout/stderr and exit status.

        Args:
            command: List of command arguments to execute
            cwd: Working directory for execution
            timeout: Execution timeout in seconds
            log_path: Optional absolute path to log file

        Returns:
            Dict with stdout, stderr, exit_code, timed_out, duration_ms, log_path
        """
        if not isinstance(command, list) or not command or not all(isinstance(arg, str) for arg in command):
            raise CodeRunError("Command must be a non-empty list of strings")
        if not isinstance(timeout, int) or timeout <= 0:
            raise CodeRunError("Timeout must be a positive integer")
        if not os.path.isdir(cwd):
            raise CodeRunError(f"Working directory not found: {cwd}")

        start_time = time.time()
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            duration_ms = int((time.time() - start_time) * 1000)
            output = {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "timed_out": False,
                "duration_ms": duration_ms,
                "log_path": log_path,
            }

            if log_path:
                log_dir = os.path.dirname(log_path)
                if log_dir:
                    os.makedirs(log_dir, exist_ok=True)
                with open(log_path, "w", encoding="utf-8") as log_file:
                    log_file.write("STDOUT:\n")
                    log_file.write(result.stdout)
                    log_file.write("\nSTDERR:\n")
                    log_file.write(result.stderr)
                    log_file.write(f"\nEXIT_CODE: {result.returncode}\n")

            return output

        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.time() - start_time) * 1000)
            output = {
                "stdout": exc.stdout or "",
                "stderr": exc.stderr or "",
                "exit_code": None,
                "timed_out": True,
                "duration_ms": duration_ms,
                "log_path": log_path,
            }
            if log_path:
                log_dir = os.path.dirname(log_path)
                if log_dir:
                    os.makedirs(log_dir, exist_ok=True)
                with open(log_path, "w", encoding="utf-8") as log_file:
                    log_file.write("STDOUT:\n")
                    log_file.write(output["stdout"])
                    log_file.write("\nSTDERR:\n")
                    log_file.write(output["stderr"])
                    log_file.write("\nEXIT_CODE: timeout\n")
            return output
        except Exception as exc:
            raise CodeRunError(f"Failed to run tests: {exc}")

    def run_python(
        self,
        code: str,
        cwd: str,
        timeout: int = 30,
        log_path: Optional[str] = None,
    ) -> Dict[str, object]:
        """
        Execute Python code and return stdout/stderr and exit status.

        Args:
            code: Python source code to execute
            cwd: Working directory for execution
            timeout: Execution timeout in seconds
            log_path: Optional absolute path to log file

        Returns:
            Dict with stdout, stderr, exit_code, timed_out, duration_ms, log_path
        """
        if not isinstance(code, str) or not code.strip():
            raise CodeRunError("Code must be a non-empty string")
        if not isinstance(timeout, int) or timeout <= 0:
            raise CodeRunError("Timeout must be a positive integer")
        if not os.path.isdir(cwd):
            raise CodeRunError(f"Working directory not found: {cwd}")

        temp_file = None
        start_time = time.time()
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".py",
                delete=False,
                dir=cwd,
                encoding="utf-8",
            ) as handle:
                handle.write(code)
                temp_file = handle.name

            result = subprocess.run(
                [sys.executable, temp_file],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            duration_ms = int((time.time() - start_time) * 1000)
            output = {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "timed_out": False,
                "duration_ms": duration_ms,
                "log_path": log_path,
            }

            if log_path:
                log_dir = os.path.dirname(log_path)
                if log_dir:
                    os.makedirs(log_dir, exist_ok=True)
                with open(log_path, "w", encoding="utf-8") as log_file:
                    log_file.write("STDOUT:\n")
                    log_file.write(result.stdout)
                    log_file.write("\nSTDERR:\n")
                    log_file.write(result.stderr)
                    log_file.write(f"\nEXIT_CODE: {result.returncode}\n")

            return output

        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.time() - start_time) * 1000)
            output = {
                "stdout": exc.stdout or "",
                "stderr": exc.stderr or "",
                "exit_code": None,
                "timed_out": True,
                "duration_ms": duration_ms,
                "log_path": log_path,
            }
            if log_path:
                log_dir = os.path.dirname(log_path)
                if log_dir:
                    os.makedirs(log_dir, exist_ok=True)
                with open(log_path, "w", encoding="utf-8") as log_file:
                    log_file.write("STDOUT:\n")
                    log_file.write(output["stdout"])
                    log_file.write("\nSTDERR:\n")
                    log_file.write(output["stderr"])
                    log_file.write("\nEXIT_CODE: timeout\n")
            return output
        except Exception as exc:
            raise CodeRunError(f"Failed to run Python code: {exc}")
        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError:
                    pass
