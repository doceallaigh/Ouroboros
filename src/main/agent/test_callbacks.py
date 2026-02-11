"""
Unit tests for agent callback mechanism.

Tests callback handler setup and raise_callback method.
"""

import unittest
from unittest.mock import Mock
from conftest import MockedNetworkTestCase

from main import Agent


class TestCallbackMechanism(MockedNetworkTestCase):
    """Test cases for agent callback mechanism."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            "role": "developer",
            "system_prompt": "You are a developer",
            "model_endpoints": [
                {"model": "gpt-3.5", "endpoint": "http://localhost:8000/api"}
            ],
            "temperature": 0.7,
            "max_tokens": 1000,
        }
        self.mock_channel_factory = Mock()
        self.mock_filesystem = Mock()
        self.mock_channel = Mock()
        self.mock_channel_factory.create_channel.return_value = self.mock_channel

    def test_raise_callback_method_exists(self):
        """Should have raise_callback method on Agent class."""
        agent = Agent(self.config, self.mock_channel_factory, self.mock_filesystem, instance_number=1)
        self.assertTrue(hasattr(agent, 'raise_callback'))
        self.assertTrue(callable(agent.raise_callback))

    def test_raise_callback_without_handler(self):
        """Should handle raise_callback gracefully when no handler set."""
        agent = Agent(self.config, self.mock_channel_factory, self.mock_filesystem, instance_number=1)
        # Should return None and not raise exception
        result = agent.raise_callback("Test message", "query")
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
