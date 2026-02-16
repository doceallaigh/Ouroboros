"""
Tools package.

Exports agent tools and code runner utilities.
The canonical definitions now live in ``main.agent.tool_runner``;
this package re-exports them for backward compatibility.
"""

from .code_runner import (
    CodeRunner,
    CodeRunError,
)

# ---------------------------------------------------------------------------
# Lazy re-exports from main.agent.tool_runner to avoid circular imports.
# The main package also imports from tools, so eager top-level imports
# would create a cycle.
# ---------------------------------------------------------------------------

_TOOL_RUNNER_EXPORTS = {
    "AgentTools", "ToolError", "PathError", "FileSizeError",
    "PackageError", "GitError", "get_tools",
}


def __getattr__(name):
    if name in _TOOL_RUNNER_EXPORTS:
        from main.agent.tool_runner import (
            AgentTools, ToolError, PathError,
            FileSizeError, PackageError, GitError, get_tools,
        )
        _cache = {
            "AgentTools": AgentTools,
            "ToolError": ToolError,
            "PathError": PathError,
            "FileSizeError": FileSizeError,
            "PackageError": PackageError,
            "GitError": GitError,
            "get_tools": get_tools,
        }
        globals().update(_cache)
        return _cache[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Backward-compatible re-exports (now live in main.agent.tool_runner)
def get_tools_description(allowed_tools=None):
    from main.agent.tool_runner import get_tools_description as _get
    return _get(allowed_tools)

def get_manager_tools_description(allowed_tools=None):
    from main.agent.tool_runner import get_manager_tools_description as _get
    return _get(allowed_tools)

__all__ = [
    # Agent Tools
    "AgentTools",
    "ToolError",
    "PathError",
    "FileSizeError",
    "PackageError",
    "GitError",
    "get_tools",
    "get_tools_description",
    "get_manager_tools_description",
    # Code Runner
    "CodeRunner",
    "CodeRunError",
]
