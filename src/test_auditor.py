"""
Test auditor role integration.

Verifies auditor role can be created and has proper tool access.
"""

import unittest
from unittest.mock import patch, Mock
import json


class TestAuditorRole(unittest.TestCase):
    """Test auditor role configuration and behavior."""
    
    @patch('builtins.open')
    def test_auditor_role_exists_in_config(self, mock_open):
        """Verify auditor role is present in roles.json."""
        from main import CentralCoordinator
        
        config = {
            "manager": {"role": "manager", "system_prompt": "Manage"},
            "developer": {"role": "developer", "system_prompt": "Develop"},
            "auditor": {"role": "auditor", "system_prompt": "Audit"}
        }
        
        with patch('main.json.load', return_value=config):
            mock_filesystem = Mock()
            coordinator = CentralCoordinator("/tmp/roles.json", mock_filesystem)
            
            # Verify auditor can be found
            auditor_config = coordinator._find_agent_config("auditor")
            self.assertIsNotNone(auditor_config)
            self.assertEqual(auditor_config["role"], "auditor")
    
    @patch('builtins.open')
    def test_auditor_gets_tools_injected(self, mock_open):
        """Verify auditor role gets file tools injected."""
        from main import Agent
        
        auditor_config = {
            "role": "auditor",
            "system_prompt": "Review code quality",
            "model": "test-model",
            "temperature": 0.3,
            "max_tokens": 1000
        }
        
        mock_channel_factory = Mock()
        mock_filesystem = Mock()
        mock_channel = Mock()
        mock_channel_factory.create_channel.return_value = mock_channel
        
        agent = Agent(auditor_config, mock_channel_factory, mock_filesystem, instance_number=1)
        
        # Verify agent was created with correct name
        self.assertEqual(agent.name, "auditor01")
        self.assertEqual(agent.role, "auditor")
        
        # Verify tools were injected into the config
        called_config = mock_channel_factory.create_channel.call_args[0][0]
        self.assertIn("Available tools", called_config["system_prompt"])
        self.assertIn("read_file", called_config["system_prompt"])
        self.assertIn("list_all_files", called_config["system_prompt"])
    
    def test_manager_knows_about_auditor(self):
        """Verify manager's prompt mentions auditor role."""
        # Load actual roles.json to verify manager prompt
        import os
        roles_path = os.path.join(os.path.dirname(__file__), "roles.json")
        
        if os.path.exists(roles_path):
            with open(roles_path, 'r') as f:
                config = json.load(f)
            
            manager_prompt = config["manager"]["system_prompt"]
            
            # Verify auditor is mentioned as available role
            self.assertIn("'auditor'", manager_prompt)
            self.assertIn("AFTER development work completes", manager_prompt)
    
    def test_auditor_sequence_number(self):
        """Verify auditor example shows higher sequence number."""
        import os
        roles_path = os.path.join(os.path.dirname(__file__), "roles.json")
        
        if os.path.exists(roles_path):
            with open(roles_path, 'r') as f:
                config = json.load(f)
            
            manager_prompt = config["manager"]["system_prompt"]
            
            # Verify example shows auditor with sequence 3 (after developers)
            self.assertIn('sequence": 3', manager_prompt)
            self.assertIn('"role": "auditor"', manager_prompt)


if __name__ == '__main__':
    unittest.main()
