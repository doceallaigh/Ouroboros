"""
File I/O package.

Exports:
- FileSystem
- ReadOnlyFileSystem
- FileSystemError
"""

from .fileio import (
    FileSystem,
    ReadOnlyFileSystem,
    FileSystemError,
)

__all__ = [
    "FileSystem",
    "ReadOnlyFileSystem",
    "FileSystemError",
]
