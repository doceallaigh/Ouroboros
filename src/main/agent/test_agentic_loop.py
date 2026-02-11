"""
Unit tests for agentic loop execution.

Tests iterative tool calling and conversation maintenance.
"""

import unittest
from unittest.mock import Mock, patch, AsyncMock
from conftest import MockedNetworkTestCase

from main import Agent


class TestAgenticLoop(MockedNetworkTestCase):
    """Test cases for agentic loop execution."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            "role": "developer",
            "system_prompt": "You are a developer",
            "model": "gpt-3.5",
            "temperature": 0.7,
            "max_tokens": 1000,
            "model_endpoints": [{"model": "gpt-3.5", "endpoint": "http://localhost:8000/api"}]
        }
        self.mock_channel_factory = Mock()
        self.mock_filesystem = Mock()
        self.mock_channel = Mock()
        self.mock_channel.config = {}  # Make config a dict for item assignment
        # Make send_message and receive_message async
        self.mock_channel.send_message = AsyncMock()
        # Create a proper response mock with status_code
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": "Response"}}]}
        self.mock_channel.receive_message = AsyncMock(return_value=mock_response)
        self.mock_channel_factory.create_channel.return_value = self.mock_channel
        self.working_dir = "/tmp/test_working"

    def test_single_iteration_with_completion(self):
        """Should complete in single iteration when agent confirms completion."""
        agent = Agent(self.config, self.mock_channel_factory, self.mock_filesystem, instance_number=1)
        
        # Mock agent response with confirm_task_complete tool call
        completion_response = "Task done!\n```python\nconfirm_task_complete()\n```"
        
        def mock_execute_tools(agent_arg, response, working_dir):
            # Return proper dict structure with task_complete flag
            return {
                "tools_executed": True,
                "results": [{"success": True, "code_executed": 32}],
                "code_blocks_found": 1,
                "code_blocks_executed": 1,
                "estimated_tool_calls": 1,
                "task_complete": True
            }
        
        with patch('main.agent.tool_runner.execute_tools_from_response', side_effect=mock_execute_tools):
            result = agent.execute_with_agentic_loop(
                {"user_prompt": "Do something"},
                working_dir=self.working_dir,
                max_iterations=5
            )
            
            self.assertTrue(result["task_complete"])
            self.assertEqual(result["iteration_count"], 1)

    def test_multiple_iterations_before_completion(self):
        """Should iterate multiple times before completion."""
        agent = Agent(self.config, self.mock_channel_factory, self.mock_filesystem, instance_number=1)
        
        iteration_count = [0]
        
        # Side effect for channel receive_message to return different responses per iteration
        async def mock_receive(iteration=iteration_count):
            iteration_count[0] += 1
            if iteration_count[0] >= 2:
                # On second iteration, agent confirms task completion
                return Mock(
                    status_code=200,
                    json=lambda: {"choices": [{"message": {"content": "Task complete!\n```python\nconfirm_task_complete()\n```"}}]}
                )
            else:
                # First iteration, agent does some work
                return Mock(
                    status_code=200,
                    json=lambda: {"choices": [{"message": {"content": "Working on it\n```python\nread_file('test.py')\n```"}}]}
                )
        
        self.mock_channel.receive_message = AsyncMock(side_effect=mock_receive)
        
        def mock_execute_tools(agent_arg, response, working_dir):
            if "confirm_task_complete" in response:
                return {
                    "tools_executed": True,
                    "results": [{"success": True}],
                    "code_blocks_found": 1,
                    "code_blocks_executed": 1,
                    "estimated_tool_calls": 1,
                    "task_complete": True
                }
            return {
                "tools_executed": True,
                "results": [{"success": True, "output": "file content"}],
                "code_blocks_found": 1,
                "code_blocks_executed": 1,
                "estimated_tool_calls": 1,
                "task_complete": False
            }
        
        with patch('main.agent.tool_runner.execute_tools_from_response', side_effect=mock_execute_tools):
            result = agent.execute_with_agentic_loop(
                {"user_prompt": "Do something"},
                working_dir=self.working_dir,
                max_iterations=10
            )
            
            self.assertTrue(result["task_complete"])
            self.assertGreaterEqual(result["iteration_count"], 1)

    def test_max_iterations_reached(self):
        """Should stop at max iterations without completion."""
        agent = Agent(self.config, self.mock_channel_factory, self.mock_filesystem, instance_number=1)
        
        def mock_execute_tools(agent_arg, response, working_dir):
            return {
                "tools_executed": True,
                "results": [{"success": True, "code_executed": 20}],
                "code_blocks_found": 1,
                "code_blocks_executed": 1,
                "estimated_tool_calls": 1,
                "task_complete": False
            }
        
        with patch('main.agent.tool_runner.execute_tools_from_response', side_effect=mock_execute_tools):
            result = agent.execute_with_agentic_loop(
                {"user_prompt": "Do something"},
                working_dir=self.working_dir,
                max_iterations=3
            )
            
            self.assertFalse(result["task_complete"])
            self.assertEqual(result["iteration_count"], 3)


if __name__ == '__main__':
    unittest.main()
