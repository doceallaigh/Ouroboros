"""
Test auditor role integration.

Verifies auditor role can be created and has proper tool access.
"""

import unittest
from unittest.mock import patch, Mock
import json
import pytest
import os
import tempfile
from tools.agent_tools import AgentTools, ToolError


class TestAuditFilesValidation:
    """Test that audit_files only audits produced files."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.tools = AgentTools(working_dir=self.temp_dir)
    
    def test_audit_files_requires_produced_files(self):
        """audit_files should reject files not in produced_files list."""
        # Create a file first
        test_file = os.path.join(self.temp_dir, "test.py")
        with open(test_file, 'w') as f:
            f.write("print('hello')")
        
        # Try to audit a file that wasn't in produced_files
        with pytest.raises(ToolError) as exc_info:
            self.tools.audit_files(
                ["test.py"],
                description="Review code",
                produced_files=[]  # Empty list means no files were produced
            )
        
        assert "haven't been produced" in str(exc_info.value)
    
    def test_audit_files_succeeds_for_produced_files(self):
        """audit_files should succeed for files in produced_files list."""
        # Create a file
        test_file = os.path.join(self.temp_dir, "test.py")
        with open(test_file, 'w') as f:
            f.write("print('hello')")
        
        # Audit the file with it in produced_files
        result = self.tools.audit_files(
            ["test.py"],
            description="Review code",
            produced_files=["test.py"]  # File is in produced list
        )
        
        assert result["status"] == "audit_requested"
        assert "test.py" in result["files"]
        assert len(result["invalid_files"]) == 0
    
    def test_audit_files_partial_validation(self):
        """audit_files with mixed produced/non-produced files should fail."""
        # Create files
        test_file1 = os.path.join(self.temp_dir, "produced.py")
        test_file2 = os.path.join(self.temp_dir, "not_produced.py")
        with open(test_file1, 'w') as f:
            f.write("# produced")
        with open(test_file2, 'w') as f:
            f.write("# not produced")
        
        # Try to audit both but only one is in produced_files
        with pytest.raises(ToolError) as exc_info:
            self.tools.audit_files(
                ["produced.py", "not_produced.py"],
                description="Review code",
                produced_files=["produced.py"]  # Only one file
            )
        
        assert "not_produced.py" in str(exc_info.value)
    
    def test_audit_files_empty_produced_list_fails(self):
        """audit_files should fail when produced_files is empty but files are provided."""
        # Create a file
        test_file = os.path.join(self.temp_dir, "test.py")
        with open(test_file, 'w') as f:
            f.write("print('hello')")
        
        # Try to audit with empty produced list
        with pytest.raises(ToolError):
            self.tools.audit_files(
                ["test.py"],
                description="Review code",
                produced_files=[]
            )


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
            auditor_config = coordinator.find_agent_config("auditor")
            self.assertIsNotNone(auditor_config)
            self.assertEqual(auditor_config["role"], "auditor")
    
    @patch('builtins.open')
    def test_auditor_gets_tools_injected(self, mock_open):
        """Verify auditor role gets file tools injected."""
        from main import Agent
        
        auditor_config = {
            "role": "auditor",
            "system_prompt": "Review code quality",
            "model_endpoints": [
                {"model": "test-model", "endpoint": "http://localhost:8000/api"}
            ],
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
            self.assertIn("auditor", manager_prompt.lower())
    
    def test_auditor_sequence_number(self):
        """Verify auditor example shows auditor role with a sequence number."""
        import os
        roles_path = os.path.join(os.path.dirname(__file__), "roles.json")
        
        if os.path.exists(roles_path):
            with open(roles_path, 'r') as f:
                config = json.load(f)
            
            manager_prompt = config["manager"]["system_prompt"]
            
            # Verify example references auditor role and sequence ordering
            self.assertIn("auditor", manager_prompt.lower())
            self.assertIn("sequence", manager_prompt)


if __name__ == '__main__':
    unittest.main()
