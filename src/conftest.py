"""
Pytest configuration for test discovery and imports.

Adds src directory to sys.path so tests can import source modules.
"""

import sys
from pathlib import Path

# Add src directory to Python path
src_dir = Path(__file__).parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
