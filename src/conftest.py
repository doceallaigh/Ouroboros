"""
Pytest configuration for test discovery and imports.

Adds src directory to sys.path so tests can import source modules.
Provides shared test base classes and fixtures.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Add src directory to Python path
src_dir = Path(__file__).parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

# IMPORTANT: Mock httpx at module import time to prevent any accidental network calls
# This ensures no actual HTTP requests can be made during tests
from unittest.mock import patch as mock_patch
_asyncclient_patcher = mock_patch('httpx.AsyncClient')
_asyncclient_patcher.start()


class MockedNetworkTestCase(unittest.TestCase):
    """
    Base test case that ensures all network calls are mocked.
    
    This prevents accidental API calls during testing and ensures tests are
    isolated from external dependencies.
    """
    
    @classmethod
    def setUpClass(cls):
        """Set up class-level mocks for network calls."""
        # These are in addition to the module-level AsyncClient mock
        cls.patcher_httpx = patch('comms.channel.AsyncClient')
        cls.mock_httpx = cls.patcher_httpx.start()
    
    @classmethod
    def tearDownClass(cls):
        """Clean up class-level mocks."""
        cls.patcher_httpx.stop()
    
    def setUp(self):
        """Ensure network mocks are active for each test."""
        # Double-check that mocks are in place
        self.addCleanup(self._verify_no_real_network_calls)
    
    def _verify_no_real_network_calls(self):
        """
        Cleanup helper that could be extended to verify no unmocked network calls occurred.
        """
        pass

