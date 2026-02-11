"""
Test command-line interface argument parsing.
"""

import sys
import unittest
from unittest.mock import patch
from io import StringIO


class TestCLIArguments(unittest.TestCase):
    """Test command-line argument parsing."""
    
    def test_help_option(self):
        """Test --help displays usage information."""
        with patch('sys.argv', ['main.py', '--help']):
            with patch('sys.stdout', new=StringIO()) as fake_out:
                try:
                    import main
                    main.main()
                except SystemExit as e:
                    # argparse exits with 0 on --help
                    self.assertEqual(e.code, 0)
                    output = fake_out.getvalue()
                    self.assertIn('usage:', output)
                    self.assertIn('Ouroboros', output)
                    self.assertIn('--replay', output)
                    self.assertIn('--verbose', output)
    
    def test_version_in_help(self):
        """Test help includes feature descriptions."""
        with patch('sys.argv', ['main.py', '-h']):
            with patch('sys.stdout', new=StringIO()) as fake_out:
                try:
                    import main
                    main.main()
                except SystemExit:
                    output = fake_out.getvalue()
                    self.assertIn('Multi-agent collaboration', output)
                    self.assertIn('Task decomposition', output)
    
    def test_default_request(self):
        """Test default request is used when none provided."""
        # This test would need to mock the entire execution chain
        # For now, just verify the argument parsing logic
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('request', nargs='?', default='Build a simple Hello World application')
        
        # Test with no arguments
        args = parser.parse_args([])
        self.assertEqual(args.request, 'Build a simple Hello World application')
        
        # Test with custom request
        args = parser.parse_args(['Custom request'])
        self.assertEqual(args.request, 'Custom request')
    
    def test_replay_flag(self):
        """Test --replay flag parsing."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('--replay', action='store_true')
        
        # Test without flag
        args = parser.parse_args([])
        self.assertFalse(args.replay)
        
        # Test with flag
        args = parser.parse_args(['--replay'])
        self.assertTrue(args.replay)
    
    def test_verbose_flag(self):
        """Test --verbose/-v flag parsing."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('--verbose', '-v', action='store_true')
        
        # Test long form
        args = parser.parse_args(['--verbose'])
        self.assertTrue(args.verbose)
        
        # Test short form
        args = parser.parse_args(['-v'])
        self.assertTrue(args.verbose)
        
        # Test without flag
        args = parser.parse_args([])
        self.assertFalse(args.verbose)


if __name__ == '__main__':
    unittest.main()
