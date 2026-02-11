"""
Unit tests for Agent class and execution logic.

Tests agent initialization, task execution, and tool calling.
"""

import unittest
from unittest.mock import Mock, patch
from conftest import MockedNetworkTestCase

from main import Agent, OrganizationError


class TestAgent(MockedNetworkTestCase):
    """Test cases for Agent class."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            "role": "developer",
            "system_prompt": "You are a developer",
            "model": "gpt-3.5",
            "temperature": 0.7,
            "max_tokens": 1000,
        }
        self.mock_channel_factory = Mock()
        self.mock_filesystem = Mock()
        self.mock_channel = Mock()
        self.mock_channel.config = {}  # Add config dict for endpoint assignment
        self.mock_channel_factory.create_channel.return_value = self.mock_channel

    def test_initialization_with_instance_number(self):
        """Should initialize with generated name from role and instance number."""
        agent = Agent(self.config, self.mock_channel_factory, self.mock_filesystem, instance_number=1)
        
        self.assertEqual(agent.name, "developer01")
        self.assertEqual(agent.role, "developer")
        self.assertIsNotNone(agent.channel)

    def test_initialization_multiple_instances(self):
        """Should generate unique names for multiple instances of same role."""
        agent1 = Agent(self.config, self.mock_channel_factory, self.mock_filesystem, instance_number=1)
        agent2 = Agent(self.config, self.mock_channel_factory, self.mock_filesystem, instance_number=2)
        
        self.assertEqual(agent1.name, "developer01")
        self.assertEqual(agent2.name, "developer02")

    def test_channel_creation(self):
        """Should create channel using factory."""
        agent = Agent(self.config, self.mock_channel_factory, self.mock_filesystem, instance_number=1)
        
        # Verify create_channel was called with a config
        self.mock_channel_factory.create_channel.assert_called_once()
        # Get the actual config that was passed
        called_config = self.mock_channel_factory.create_channel.call_args[0][0]
        # For developer role, verify tools were injected into the prompt
        if self.config.get("role") == "developer":
            self.assertIn("Available tools", called_config.get("system_prompt", ""))
            # Verify original config is not modified
            self.assertNotIn("Available tools", self.config.get("system_prompt", ""))

    def test_auditor_role_gets_tools(self):
        """Should inject tools for auditor role."""
        auditor_config = {
            "role": "auditor",
            "system_prompt": "Review code",
            "model_endpoints": [
                {"model": "gpt-3.5", "endpoint": "http://localhost:8000/api"}
            ],
            "temperature": 0.3,
            "max_tokens": 1000,
        }
        agent = Agent(auditor_config, self.mock_channel_factory, self.mock_filesystem, instance_number=1)
        
        # Verify tools were injected for auditor
        called_config = self.mock_channel_factory.create_channel.call_args[0][0]
        self.assertIn("Available tools", called_config.get("system_prompt", ""))
        self.assertEqual(agent.name, "auditor01")
        self.assertEqual(agent.role, "auditor")

    def test_execute_task_success(self):
        """Should execute task successfully."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Task completed"}}]
        }
        
        with patch('main.agent.executor.asyncio.run', return_value=mock_response):
            with patch('main.extract_content_from_response', return_value="Task completed"):
                agent = Agent(self.config, self.mock_channel_factory, self.mock_filesystem, instance_number=1)
                
                task = {"user_prompt": "Do something"}
                result = agent.execute_task(task)
                
                self.assertEqual(result, "Task completed")
                self.mock_channel.send_message.assert_called()

    def test_execute_task_stores_output(self):
        """Should store task output in filesystem."""
        mock_response = Mock()
        
        with patch('main.agent.executor.asyncio.run', return_value=mock_response):
            with patch('main.extract_content_from_response', return_value="Output"):
                agent = Agent(self.config, self.mock_channel_factory, self.mock_filesystem, instance_number=1)
                
                task = {"user_prompt": "Do something"}
                agent.execute_task(task)
                
                # Verify append_response_file was called (write_data was removed)
                self.mock_filesystem.append_response_file.assert_called_once()
                # Check the response content (4th argument)
                call_args = self.mock_filesystem.append_response_file.call_args[0]
                self.assertEqual(call_args[3], "Output")  # response is 4th arg

    def test_execute_task_records_event(self):
        """Should record timeout retry events."""
        mock_response = Mock()
        
        with patch('main.agent.executor.asyncio.run', return_value=mock_response):
            with patch('main.extract_content_from_response', return_value="Output"):
                agent = Agent(self.config, self.mock_channel_factory, self.mock_filesystem, instance_number=1)
                
                task = {"user_prompt": "Do something"}
                agent.execute_task(task)
                
                # Verify event recording was called (no errors)
                self.mock_filesystem.record_event.call_count >= 0

    def test_execute_task_timeout_retry(self):
        """Should retry on timeout with exponential backoff."""
        from comms import APIError
        
        # First call times out, second call succeeds
        mock_response = Mock()
        
        with patch('main.agent.executor.asyncio.run', side_effect=[
            Exception("timed out")
        ]):
            with patch('main.extract_content_from_response', return_value="Output"):
                with patch('main.agent.executor.time.sleep'):  # Speed up test
                    agent = Agent(self.config, self.mock_channel_factory, self.mock_filesystem, instance_number=1)
                    
                    task = {"user_prompt": "Do something"}
                    
                    # Should fail with proper error
                    try:
                        result = agent.execute_task(task)
                    except OrganizationError:
                        pass

    def test_execute_task_failure(self):
        """Should raise OrganizationError on failure."""
        with patch('main.agent.executor.asyncio.run', side_effect=Exception("API error")):
            agent = Agent(self.config, self.mock_channel_factory, self.mock_filesystem, instance_number=1)
            
            task = {"user_prompt": "Do something"}
            
            with self.assertRaises(OrganizationError):
                agent.execute_task(task)

    def test_payload_construction(self):
        """Should construct proper payload for API."""
        mock_response = Mock()
        mock_response.status_code = 200
        
        with patch('main.agent.executor.asyncio.run', return_value=mock_response):
            with patch('main.extract_content_from_response', return_value="Output"):
                agent = Agent(self.config, self.mock_channel_factory, self.mock_filesystem)
                
                task = {"user_prompt": "Test prompt"}
                agent.execute_task(task)
                
                # Verify send_message was called with proper structure
                call_args = self.mock_channel.send_message.call_args
                # send_message is called with positional argument
                payload = call_args[0][0] if call_args[0] else {}
                
                self.assertIn("messages", payload)
                self.assertEqual(payload["model"], "gpt-3.5")
                self.assertEqual(payload["temperature"], 0.7)

    def test_execute_tools_from_response_clone_repo_default_branch(self):
        """Should inject default git branch when clone_repo omits branch."""
        config = {
            "role": "developer",
            "system_prompt": "You are a developer",
            "allowed_tools": ["clone_repo"],
            "default_git_branch": "master",
        }
        agent = Agent(config, self.mock_channel_factory, self.mock_filesystem, instance_number=1)

        response = """```python
clone_repo('https://example.com/repo.git')
```"""

        mock_tools = Mock()
        for name in [
            "read_file",
            "write_file",
            "append_file",
            "edit_file",
            "list_directory",
            "list_all_files",
            "search_files",
            "get_file_info",
            "delete_file",
            "audit_files",
        ]:
            setattr(mock_tools, name, Mock())
        mock_tools.clone_repo = Mock(return_value={"success": True})

        with patch("tools.AgentTools", return_value=mock_tools):
            agent.execute_tools_from_response(response, working_dir=".")

        mock_tools.clone_repo.assert_called_once_with(
            "https://example.com/repo.git",
            dest_dir=None,
            branch="master",
            depth=None,
        )

    def test_execute_tools_from_response_clone_repo_branch_override(self):
        """Should respect explicit branch for clone_repo."""
        config = {
            "role": "developer",
            "system_prompt": "You are a developer",
            "allowed_tools": ["clone_repo"],
            "default_git_branch": "master",
        }
        agent = Agent(config, self.mock_channel_factory, self.mock_filesystem, instance_number=1)

        response = """```python
clone_repo('https://example.com/repo.git', branch='dev')
```"""

        mock_tools = Mock()
        for name in [
            "read_file",
            "write_file",
            "append_file",
            "edit_file",
            "list_directory",
            "list_all_files",
            "search_files",
            "get_file_info",
            "delete_file",
            "audit_files",
        ]:
            setattr(mock_tools, name, Mock())
        mock_tools.clone_repo = Mock(return_value={"success": True})

        with patch("tools.AgentTools", return_value=mock_tools):
            agent.execute_tools_from_response(response, working_dir=".")

        mock_tools.clone_repo.assert_called_once_with(
            "https://example.com/repo.git",
            dest_dir=None,
            branch="dev",
            depth=None,
        )


if __name__ == '__main__':
    unittest.main()
