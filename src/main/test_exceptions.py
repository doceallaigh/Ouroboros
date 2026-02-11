"""
Unit tests for Ouroboros exceptions.

Tests the exception hierarchy.
"""

import unittest
from conftest import MockedNetworkTestCase

from main import OrganizationError


class TestOrganizationError(MockedNetworkTestCase):
    """Test cases for OrganizationError exception."""

    def test_organization_error_raised(self):
        """Should raise OrganizationError for coordination failures."""
        with self.assertRaises(OrganizationError):
            raise OrganizationError("Coordination failed")

    def test_organization_error_message(self):
        """Should include meaningful error message."""
        try:
            raise OrganizationError("Agent not found")
        except OrganizationError as e:
            self.assertIn("Agent not found", str(e))


if __name__ == '__main__':
    unittest.main()
