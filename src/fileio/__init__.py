"""
File I/O package.

Exports:
- FileSystem
- ReadOnlyFileSystem
- FileSystemError
"""

from .filesystem import (
    FileSystem,
    ReadOnlyFileSystem,
    FileSystemError,
)

__all__ = [
    "FileSystem",
    "ReadOnlyFileSystem",
    "FileSystemError",
]
