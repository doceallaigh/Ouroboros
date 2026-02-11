"""
Git control package.

Exports git repository management functions.
"""

from .git_control import is_git_repository, get_current_git_branch, finalize_git_workflow

__all__ = [
    "is_git_repository",
    "get_current_git_branch",
    "finalize_git_workflow",
]
