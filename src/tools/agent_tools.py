"""
Agent tools module – backward-compatibility shim.

The canonical implementation now lives in ``main.agent.tool_runner``.
This module re-exports all public symbols so that existing imports
(``from tools.agent_tools import ...``) continue to work.

Lazy imports via ``__getattr__`` are used to avoid circular-import
issues with the ``main`` package.
"""

# Re-export stdlib modules so that mock.patch("tools.agent_tools.subprocess")
# still works for tests that haven't been updated yet.
import subprocess  # noqa: F401
import os           # noqa: F401
import json         # noqa: F401
import sys          # noqa: F401
import re           # noqa: F401

_TOOL_RUNNER_EXPORTS = {
    # Constants
    "DEFAULT_MAX_FILE_SIZE", "DEFAULT_PAGE_LINES",
    "DEFAULT_MAX_SEARCH_RESULTS", "DEFAULT_WORKING_DIR",
    "ALLOWED_PACKAGE_PREFIXES",
    # Exceptions
    "ToolError", "PathError", "FileSizeError", "PackageError", "GitError",
    # Class & factory
    "AgentTools", "get_tools",
}


def __getattr__(name):
    if name in _TOOL_RUNNER_EXPORTS:
        from main.agent.tool_runner import (
            DEFAULT_MAX_FILE_SIZE, DEFAULT_PAGE_LINES,
            DEFAULT_MAX_SEARCH_RESULTS, DEFAULT_WORKING_DIR,
            ALLOWED_PACKAGE_PREFIXES,
            ToolError, PathError, FileSizeError, PackageError, GitError,
            AgentTools, get_tools,
        )
        _cache = {
            "DEFAULT_MAX_FILE_SIZE": DEFAULT_MAX_FILE_SIZE,
            "DEFAULT_PAGE_LINES": DEFAULT_PAGE_LINES,
            "DEFAULT_MAX_SEARCH_RESULTS": DEFAULT_MAX_SEARCH_RESULTS,
            "DEFAULT_WORKING_DIR": DEFAULT_WORKING_DIR,
            "ALLOWED_PACKAGE_PREFIXES": ALLOWED_PACKAGE_PREFIXES,
            "ToolError": ToolError,
            "PathError": PathError,
            "FileSizeError": FileSizeError,
            "PackageError": PackageError,
            "GitError": GitError,
            "AgentTools": AgentTools,
            "get_tools": get_tools,
        }
        globals().update(_cache)
        return _cache[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
