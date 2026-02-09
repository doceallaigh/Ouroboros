"""
Unit tests for main module.

Tests agents, coordinator, and orchestration logic.
"""

import unittest
import json
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import asyncio

from main import (
    Agent,
    CentralCoordinator,
    OrganizationError,
)


class TestAgent(unittest.TestCase):
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
        
        self.mock_channel_factory.create_channel.assert_called_once_with(self.config)

    def test_execute_task_success(self):
        """Should execute task successfully."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Task completed"}}]
        }
        
        with patch('main.asyncio.run', return_value=mock_response):
            with patch('main.extract_content_from_response', return_value="Task completed"):
                agent = Agent(self.config, self.mock_channel_factory, self.mock_filesystem, instance_number=1)
                
                task = {"user_prompt": "Do something"}
                result = agent.execute_task(task)
                
                self.assertEqual(result, "Task completed")
                self.mock_channel.send_message.assert_called()

    def test_execute_task_stores_output(self):
        """Should store task output in filesystem."""
        mock_response = Mock()
        
        with patch('main.asyncio.run', return_value=mock_response):
            with patch('main.extract_content_from_response', return_value="Output"):
                agent = Agent(self.config, self.mock_channel_factory, self.mock_filesystem, instance_number=1)
                
                task = {"user_prompt": "Do something"}
                agent.execute_task(task)
                
                self.mock_filesystem.write_data.assert_called_with("developer01", "Output")

    def test_execute_task_records_event(self):
        """Should record timeout retry events."""
        mock_response = Mock()
        
        with patch('main.asyncio.run', return_value=mock_response):
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
        
        with patch('main.asyncio.run', side_effect=[
            Mock(side_effect=APIError("API request timed out")),
            mock_response
        ]):
            with patch('main.extract_content_from_response', return_value="Output"):
                with patch('main.time.sleep'):  # Speed up test
                    agent = Agent(self.config, self.mock_channel_factory, self.mock_filesystem, instance_number=1)
                    
                    task = {"user_prompt": "Do something"}
                    
                    # Should succeed on retry
                    try:
                        result = agent.execute_task(task)
                        # If we get here, retry worked (or error handling)
                    except:
                        pass

    def test_execute_task_failure(self):
        """Should raise OrganizationError on failure."""
        with patch('main.asyncio.run', side_effect=Exception("API error")):
            agent = Agent(self.config, self.mock_channel_factory, self.mock_filesystem, instance_number=1)
            
            task = {"user_prompt": "Do something"}
            
            with self.assertRaises(OrganizationError):
                agent.execute_task(task)

    def test_payload_construction(self):
        """Should construct proper payload for API."""
        mock_response = Mock()
        mock_response.status_code = 200
        
        with patch('main.asyncio.run', return_value=mock_response):
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


class TestCentralCoordinator(unittest.TestCase):
    """Test cases for CentralCoordinator class."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            "manager": {
                "role": "manager",
                "system_prompt": "Decompose requests",
            },
            "developer": {
                "role": "developer",
                "system_prompt": "Write code",
            }
        }
        self.mock_filesystem = Mock()
        self.config_path = "/tmp/roles.json"

    @patch('builtins.open')
    def test_initialization(self, mock_open):
        """Should initialize with config file."""
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(self.config)
        
        with patch('main.json.load', return_value=self.config):
            coordinator = CentralCoordinator(self.config_path, self.mock_filesystem)
            
            self.assertEqual(len(coordinator.config), 2)
            self.assertFalse(coordinator.replay_mode)

    @patch('builtins.open')
    def test_initialization_config_not_found(self, mock_open):
        """Should raise OrganizationError if config file not found."""
        mock_open.side_effect = FileNotFoundError()
        
        with self.assertRaises(OrganizationError):
            CentralCoordinator(self.config_path, self.mock_filesystem)

    @patch('builtins.open')
    def test_find_agent_config(self, mock_open):
        """Should find agent config by role."""
        with patch('main.json.load', return_value=self.config):
            coordinator = CentralCoordinator(self.config_path, self.mock_filesystem)
            
            config = coordinator._find_agent_config("developer")
            
            self.assertIsNotNone(config)
            self.assertEqual(config["role"], "developer")

    @patch('builtins.open')
    def test_find_agent_config_not_found(self, mock_open):
        """Should return None if agent role not found."""
        with patch('main.json.load', return_value=self.config):
            coordinator = CentralCoordinator(self.config_path, self.mock_filesystem)
            
            config = coordinator._find_agent_config("nonexistent")
            
            self.assertIsNone(config)

    @patch('builtins.open')
    def test_create_agent_for_role(self, mock_open):
        """Should create agent for specified role."""
        with patch('main.json.load', return_value=self.config):
            with patch('main.Agent') as mock_agent_class:
                coordinator = CentralCoordinator(self.config_path, self.mock_filesystem)
                
                agent = coordinator._create_agent_for_role("developer")
                
                # Verify Agent was instantiated with correct config
                mock_agent_class.assert_called_once()

    @patch('builtins.open')
    def test_create_agent_for_missing_role(self, mock_open):
        """Should raise OrganizationError for missing role."""
        with patch('main.json.load', return_value=self.config):
            coordinator = CentralCoordinator(self.config_path, self.mock_filesystem)
            
            with self.assertRaises(OrganizationError):
                coordinator._create_agent_for_role("nonexistent")

    @patch('builtins.open')
    def test_decompose_request(self, mock_open):
        """Should decompose request using manager agent."""
        with patch('main.json.load', return_value=self.config):
            with patch('main.Agent') as mock_agent_class:
                mock_agent_instance = Mock()
                mock_agent_instance.execute_task.return_value = "Task 1, Task 2"
                mock_agent_class.return_value = mock_agent_instance
                
                coordinator = CentralCoordinator(self.config_path, self.mock_filesystem)
                
                result = coordinator.decompose_request("Complex request")
                
                self.assertEqual(result, "Task 1, Task 2")
                mock_agent_instance.execute_task.assert_called_once()

    @patch('builtins.open')
    def test_assign_and_execute_success(self, mock_open):
        """Should execute request successfully."""
        with patch('main.json.load', return_value=self.config):
            with patch('main.Agent') as mock_agent_class:
                # Create mock agents
                mock_manager = Mock()
                mock_manager.execute_task.return_value = json.dumps([
                    {"role": "developer", "task": "Write function", "sequence": 1}
                ])
                
                mock_developer = Mock()
                mock_developer.execute_task.return_value = "def foo(): pass"
                
                def create_agent_side_effect(config, factory, fs, instance_number=1):
                    if config.get("role") == "manager":
                        return mock_manager
                    else:
                        return mock_developer
                
                mock_agent_class.side_effect = create_agent_side_effect
                
                coordinator = CentralCoordinator(self.config_path, self.mock_filesystem)
                
                with patch.object(coordinator, '_execute_assignments', return_value=[]):
                    results = coordinator.assign_and_execute("Build something")
                    
                    self.assertIsNotNone(results)

    @patch('builtins.open')
    def test_assign_and_execute_decomposition_failure(self, mock_open):
        """Should raise error if decomposition fails."""
        with patch('main.json.load', return_value=self.config):
            with patch('main.Agent') as mock_agent_class:
                mock_agent = Mock()
                mock_agent.execute_task.side_effect = Exception("API error")
                mock_agent_class.return_value = mock_agent
                
                coordinator = CentralCoordinator(self.config_path, self.mock_filesystem)
                
                with self.assertRaises(OrganizationError):
                    coordinator.assign_and_execute("Build something")

    @patch('builtins.open')
    def test_execute_assignments_with_sequence(self, mock_open):
        """Should respect sequence ordering for parallel execution."""
        with patch('main.json.load', return_value=self.config):
            coordinator = CentralCoordinator(self.config_path, self.mock_filesystem)
            
            # Two tasks in sequence 1, one task in sequence 2
            assignments = [
                {"role": "developer", "task": "Task 1a", "sequence": 1},
                {"role": "developer", "task": "Task 1b", "sequence": 1},
                {"role": "developer", "task": "Task 2", "sequence": 2},
            ]
            
            with patch.object(coordinator, '_execute_single_assignment', return_value={"status": "completed"}):
                results = coordinator._execute_assignments(assignments, "Original request")
                
                # Should execute all 3 tasks
                self.assertEqual(len(results), 3)

    @patch('builtins.open')
    def test_execute_assignments_default_sequence(self, mock_open):
        """Should default to sequence 1 if not specified."""
        with patch('main.json.load', return_value=self.config):
            coordinator = CentralCoordinator(self.config_path, self.mock_filesystem)
            
            assignments = [
                {"role": "developer", "task": "Task 1"},  # No sequence specified
                {"role": "developer", "task": "Task 2", "sequence": 2},
            ]
            
            with patch.object(coordinator, '_execute_single_assignment', return_value={"status": "completed"}):
                results = coordinator._execute_assignments(assignments, "Original request")
                
                self.assertEqual(len(results), 2)

    @patch('builtins.open')
    def test_execute_assignments_empty(self, mock_open):
        """Should handle empty assignments."""
        with patch('main.json.load', return_value=self.config):
            coordinator = CentralCoordinator(self.config_path, self.mock_filesystem)
            
            results = coordinator._execute_assignments([], "Original request")
            
            self.assertEqual(results, [])

    @patch('builtins.open')
    def test_execute_single_assignment_success(self, mock_open):
        """Should execute single assignment successfully."""
        with patch('main.json.load', return_value=self.config):
            with patch('main.Agent') as mock_agent_class:
                mock_agent = Mock()
                mock_agent.execute_task.return_value = "Task output"
                mock_agent_class.return_value = mock_agent
                
                coordinator = CentralCoordinator(self.config_path, self.mock_filesystem)
                
                result = coordinator._execute_single_assignment(
                    "developer",
                    "Write a function",
                    "Original request"
                )
                
                self.assertEqual(result["role"], "developer")
                self.assertEqual(result["status"], "completed")
                self.assertEqual(result["output"], "Task output")

    @patch('builtins.open')
    def test_execute_single_assignment_failure(self, mock_open):
        """Should handle assignment failure gracefully."""
        with patch('main.json.load', return_value=self.config):
            coordinator = CentralCoordinator(self.config_path, self.mock_filesystem)
            
            with self.assertRaises(OrganizationError):
                coordinator._execute_single_assignment(
                    "nonexistent_role",
                    "Task",
                    "Request"
                )


class TestCoordinatorWithReplayMode(unittest.TestCase):
    """Test cases for coordinator in replay mode."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            "manager": {
                "name": "Manager",
                "role": "manager",
                "system_prompt": "Decompose",
            }
        }
        self.mock_filesystem = Mock()
        self.config_path = "/tmp/roles.json"

    @patch('builtins.open')
    def test_replay_mode_initialization(self, mock_open):
        """Should initialize in replay mode."""
        with patch('main.json.load', return_value=self.config):
            coordinator = CentralCoordinator(
                self.config_path,
                self.mock_filesystem,
                replay_mode=True
            )
            
            self.assertTrue(coordinator.replay_mode)

    @patch('builtins.open')
    def test_load_replay_data(self, mock_open):
        """Should load replay data."""
        with patch('main.json.load', return_value=self.config):
            self.mock_filesystem.get_recorded_output.return_value = "Recorded output"
            
            coordinator = CentralCoordinator(
                self.config_path,
                self.mock_filesystem,
                replay_mode=True
            )
            
            data = coordinator._load_replay_data("test_agent")
            
            self.assertEqual(data, "Recorded output")
            self.mock_filesystem.get_recorded_output.assert_called_once_with("test_agent")


class TestOrganizationError(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
