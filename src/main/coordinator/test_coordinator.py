"""
Unit tests for CentralCoordinator class.

Tests coordinator initialization, request decomposition, and multi-agent orchestration.
"""

import unittest
import json
from unittest.mock import Mock, patch
from conftest import MockedNetworkTestCase

from main import CentralCoordinator, OrganizationError


class TestCentralCoordinator(MockedNetworkTestCase):
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
            },
            "auditor": {
                "role": "auditor",
                "system_prompt": "Review code",
            }
        }
        self.mock_filesystem = Mock()
        self.config_path = "/tmp/roles.json"

    @patch('builtins.open')
    def test_initialization(self, mock_open):
        """Should initialize with config file."""
        with patch('main.coordinator.coordinator.json.load', return_value=self.config):
            coordinator = CentralCoordinator(self.config_path, self.mock_filesystem)
            
            self.assertEqual(len(coordinator.config), 3)  # manager, developer, auditor
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
        with patch('main.coordinator.coordinator.json.load', return_value=self.config):
            coordinator = CentralCoordinator(self.config_path, self.mock_filesystem)
            
            config = coordinator.find_agent_config("developer")
            
            self.assertIsNotNone(config)
            self.assertEqual(config["role"], "developer")

    @patch('builtins.open')
    def test_find_agent_config_not_found(self, mock_open):
        """Should return None if agent role not found."""
        with patch('main.coordinator.coordinator.json.load', return_value=self.config):
            coordinator = CentralCoordinator(self.config_path, self.mock_filesystem)
            
            config = coordinator.find_agent_config("nonexistent")
            
            self.assertIsNone(config)

    @patch('builtins.open')
    def test_create_agent_for_role(self, mock_open):
        """Should create agent for specified role."""
        with patch('main.coordinator.coordinator.json.load', return_value=self.config):
            with patch('main.agent.agent_factory.Agent') as mock_agent_class:
                coordinator = CentralCoordinator(self.config_path, self.mock_filesystem)
                
                agent = coordinator.create_agent_for_role("developer")
                
                # Verify Agent was instantiated
                mock_agent_class.assert_called_once()

    @patch('builtins.open')
    def test_create_agent_filters_git_tools_when_disabled(self, mock_open):
        """Should remove git tools from allowed_tools when repo is not provided."""
        config_with_tools = {
            **self.config,
            "developer": {
                "role": "developer",
                "system_prompt": "Write code",
                "allowed_tools": ["read_file", "clone_repo", "checkout_branch"],
            }
        }
        
        with patch('main.coordinator.coordinator.json.load', return_value=config_with_tools):
            coordinator = CentralCoordinator(
                self.config_path,
                self.mock_filesystem,
                allow_git_tools=False
            )
            
            self.assertFalse(coordinator.allow_git_tools)
            
            # Verify git tools are actually stripped when creating an agent
            with patch('main.agent.agent_factory.Agent') as mock_agent_class:
                agent = coordinator.create_agent_for_role("developer")
                call_config = mock_agent_class.call_args[0][0]
                allowed = call_config.get("allowed_tools", [])
                self.assertIn("read_file", allowed)
                self.assertNotIn("clone_repo", allowed)
                self.assertNotIn("checkout_branch", allowed)

    @patch('builtins.open')
    def test_create_agent_for_missing_role(self, mock_open):
        """Should raise OrganizationError for missing role."""
        with patch('main.coordinator.coordinator.json.load', return_value=self.config):
            coordinator = CentralCoordinator(self.config_path, self.mock_filesystem)
            
            with self.assertRaises(OrganizationError):
                coordinator.create_agent_for_role("nonexistent")

    @patch('builtins.open')
    def test_decompose_request(self, mock_open):
        """Should decompose request using manager agent with valid JSON."""
        with patch('main.coordinator.coordinator.json.load', return_value=self.config):
            coordinator = CentralCoordinator(self.config_path, self.mock_filesystem)
            
            with patch.object(coordinator, 'create_agent_for_role') as mock_create:
                mock_agent = Mock()
                mock_agent.execute_task.return_value = json.dumps([
                    {"role": "developer", "task": "Task 1", "sequence": 1}
                ])
                mock_create.return_value = mock_agent
                
                result = coordinator.decompose_request("Complex request")
                
                # Result should be valid JSON
                parsed = json.loads(result)
                self.assertIsInstance(parsed, list)

    @patch('builtins.open')
    def test_assign_and_execute_success(self, mock_open):
        """Should execute request successfully."""
        with patch('main.coordinator.coordinator.json.load', return_value=self.config):
            coordinator = CentralCoordinator(self.config_path, self.mock_filesystem)
            
            # Mock the orchestration methods
            with patch.object(coordinator, 'decompose_request', return_value=json.dumps([])):
                with patch.object(coordinator, 'execute_all_assignments', return_value=[]):
                    with patch.object(coordinator, 'create_final_verification_task', return_value={
                        "role": "auditor", "task": "Review"
                    }):
                        with patch.object(coordinator, 'execute_single_assignment', return_value={
                            "role": "auditor", "status": "completed"
                        }):
                            with patch.object(coordinator, 'validate_assignment_roles', return_value=[]):
                                results = coordinator.assign_and_execute("Build something")
                                
                                self.assertIsInstance(results, list)
                                self.assertEqual(len(results), 1)  # Final verification result
                                self.assertEqual(results[0]["role"], "auditor")
                                self.assertEqual(results[0]["status"], "completed")

    @patch('builtins.open')
    def test_execute_assignments_with_sequence(self, mock_open):
        """Should respect sequence ordering for parallel execution."""
        with patch('main.coordinator.coordinator.json.load', return_value=self.config):
            coordinator = CentralCoordinator(self.config_path, self.mock_filesystem)
            
            # Two tasks in sequence 1, one task in sequence 2
            assignments = [
                {"role": "developer", "task": "Task 1a", "sequence": 1},
                {"role": "developer", "task": "Task 1b", "sequence": 1},
                {"role": "developer", "task": "Task 2", "sequence": 2},
            ]
            
            with patch.object(coordinator, 'execute_single_assignment', return_value={"status": "completed"}):
                results = coordinator.execute_all_assignments(assignments, "Original request")
                
                # Should execute all 3 tasks
                self.assertEqual(len(results), 3)

    @patch('builtins.open')
    def test_execute_assignments_default_sequence(self, mock_open):
        """Should default to sequence 1 if not specified."""
        with patch('main.coordinator.coordinator.json.load', return_value=self.config):
            coordinator = CentralCoordinator(self.config_path, self.mock_filesystem)
            
            assignments = [
                {"role": "developer", "task": "Task 1"},  # No sequence specified
                {"role": "developer", "task": "Task 2", "sequence": 2},
            ]
            
            with patch.object(coordinator, 'execute_single_assignment', return_value={"status": "completed"}):
                results = coordinator.execute_all_assignments(assignments, "Original request")
                
                self.assertEqual(len(results), 2)

    @patch('builtins.open')
    def test_execute_assignments_empty(self, mock_open):
        """Should handle empty assignments."""
        with patch('main.coordinator.coordinator.json.load', return_value=self.config):
            coordinator = CentralCoordinator(self.config_path, self.mock_filesystem)
            
            results = coordinator.execute_all_assignments([], "Original request")
            
            self.assertEqual(results, [])

    @patch('builtins.open')
    def test_execute_single_assignment_success(self, mock_open):
        """Should execute single assignment successfully."""
        with patch('main.coordinator.coordinator.json.load', return_value=self.config):
            coordinator = CentralCoordinator(self.config_path, self.mock_filesystem)
            
            mock_loop_result = {
                "final_response": "Task output",
                "tool_results": [],
                "iteration_count": 1,
                "task_complete": True
            }
            
            with patch.object(coordinator, 'create_agent_for_role') as mock_create:
                with patch('main.coordinator.execution.execute_with_agentic_loop', return_value=mock_loop_result):
                    mock_agent = Mock()
                    mock_agent.name = "developer01"
                    mock_create.return_value = mock_agent
                    
                    result = coordinator.execute_single_assignment(
                        "developer",
                        {"description": "Write a function"},
                        "Original request"
                    )
                    
                    self.assertEqual(result["role"], "developer")
                    self.assertEqual(result["source"], "execution")

    @patch('builtins.open')
    def test_execute_single_assignment_failure(self, mock_open):
        """Should handle assignment failure gracefully."""
        with patch('main.coordinator.coordinator.json.load', return_value=self.config):
            coordinator = CentralCoordinator(self.config_path, self.mock_filesystem)
            
            with self.assertRaises(OrganizationError):
                coordinator.execute_single_assignment(
                    "nonexistent_role",
                    {"description": "Task"},
                    "Request"
                )


class TestCoordinatorWithReplayMode(MockedNetworkTestCase):
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
        with patch('main.coordinator.coordinator.json.load', return_value=self.config):
            coordinator = CentralCoordinator(
                self.config_path,
                self.mock_filesystem,
                replay_mode=True
            )
            
            self.assertTrue(coordinator.replay_mode)

    @patch('builtins.open')
    def test_load_replay_data(self, mock_open):
        """Should load replay data."""
        with patch('main.coordinator.coordinator.json.load', return_value=self.config):
            # Mock get_recorded_outputs_in_order to return a list of tuples
            self.mock_filesystem.get_recorded_outputs_in_order.return_value = [
                ("2026-02-08T10:00:00", "Recorded output 1"),
                ("2026-02-08T10:01:00", "Recorded output 2")
            ]
            
            coordinator = CentralCoordinator(
                self.config_path,
                self.mock_filesystem,
                replay_mode=True
            )
            
            data = coordinator._load_replay_data("test_agent")
            
            self.assertEqual(data, "Recorded output 1")
            self.mock_filesystem.get_recorded_outputs_in_order.assert_called_once_with("test_agent")


if __name__ == '__main__':
    unittest.main()
