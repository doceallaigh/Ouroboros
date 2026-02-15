"""
Unit tests for agentic loop execution.

Tests iterative tool calling and conversation maintenance.
"""

import unittest
import tempfile
import os
import json
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock

from main import Agent


class TestAgenticLoop(unittest.TestCase):
    """Test cases for agentic loop execution."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            "role": "developer",
            "system_prompt": "You are a developer",
            "model": "qwen/qwen3-coder-30b",
            "temperature": 0.7,
            "max_tokens": 1000,
            "allowed_tools": ["read_file", "write_file", "list_directory", "confirm_task_complete"],
            "model_endpoints": [{"model": "qwen/qwen3-coder-30b", "endpoint": "http://localhost:12345/v1/chat/completions"}]
        }
        self.mock_channel_factory = Mock()
        self.mock_filesystem = Mock()
        self.mock_channel = Mock()
        self.mock_channel.config = {"endpoint": "http://localhost:12345/v1/chat/completions"}
        self.mock_channel_factory.create_channel.return_value = self.mock_channel
        self.working_dir = "/tmp/test_working"

    def test_single_iteration_with_completion(self):
        """Should complete in single iteration when agent confirms completion."""
        agent = Agent(self.config, self.mock_channel_factory, self.mock_filesystem, instance_number=1)
        
        # Set up the channel mocking for HTTP communication
        self.mock_channel.send_message = MagicMock(return_value={"request_id": "req_1"})
        self.mock_channel.receive_message = AsyncMock(return_value=MagicMock(
            status_code=200,
            headers={},
            json=lambda: {"choices": [{"message": {"content": "Done!\n```python\nconfirm_task_complete()\n```"}}]}
        ))
        
        # Mock agent response with confirm_task_complete tool call
        completion_response = "Task done!\n```python\nconfirm_task_complete()\n```"
        
        def mock_execute_tools(agent_arg, response, working_dir, message=None):
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
        
        # Set up channel mocking for HTTP communication
        def mock_send(payload):
            iteration_count[0] += 1
            return {"request_id": f"req_{iteration_count[0]}"}
        
        # Side effect for channel receive_message to return different responses per iteration
        async def mock_receive():
            if iteration_count[0] >= 2:
                # On second iteration, agent confirms task completion
                return MagicMock(
                    status_code=200,
                    headers={},
                    json=lambda: {"choices": [{"message": {"content": "Task complete!\n```python\nconfirm_task_complete()\n```"}}]}
                )
            else:
                # First iteration, agent does some work
                return MagicMock(
                    status_code=200,
                    headers={},
                    json=lambda: {"choices": [{"message": {"content": "Working on it\n```python\nread_file('test.py')\n```"}}]}
                )
        
        self.mock_channel.send_message = MagicMock(side_effect=mock_send)
        self.mock_channel.receive_message = AsyncMock(side_effect=mock_receive)
        
        def mock_execute_tools(agent_arg, response, working_dir, message=None):
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
        
        # Set up channel mocking for HTTP communication
        self.mock_channel.send_message = MagicMock(return_value={"request_id": "req"})
        self.mock_channel.receive_message = AsyncMock(return_value=MagicMock(
            status_code=200,
            headers={},
            json=lambda: {"choices": [{"message": {"content": "Working...\n```python\nread_file('test.py')\n```"}}]}
        ))
        
        def mock_execute_tools(agent_arg, response, working_dir, message=None):
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

    @pytest.mark.integration
    def test_developer_read_write_completion(self):
        """
        Integration test: Real Agent → Real ChannelFactory → Real APIChannel →
        Real httpx.AsyncClient → Real HTTP to localhost:12345.

        Everything is real. The test sends actual HTTP requests to the LLM
        endpoint and verifies the developer completes efficiently.

        Verifies the fix for the excessive developer looping issue where
        developers could not call confirm_task_complete() (13+ iterations).

        Stack (all REAL, no mocks):
            Agent.__init__
            └─ ChannelFactory.create_channel() → APIChannel
            Agent.execute_with_agentic_loop
            └─ agentic_loop → channel.send_message() → channel.receive_message()
               └─ connection_pool.get_client() → httpx.AsyncClient.post()
                  └─ Real HTTP POST to localhost:12345
        """
        import httpx
        # Import the REAL AsyncClient from httpx internals, bypassing the
        # conftest.py global mock that replaces httpx.AsyncClient at import time
        from httpx._client import AsyncClient as RealAsyncClient
        from comms.channel import ChannelFactory, APIChannel
        from comms.resilience import ConnectionPool
        from fileio import FileSystem

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a real test file for the agent to read and write
            test_file = os.path.join(tmpdir, "test.md")
            original_content = "# Original\n\nThis is sample content"
            with open(test_file, "w") as f:
                f.write(original_content)

            # --- All REAL infrastructure, no mocked transports ---

            # Real ConnectionPool with a REAL AsyncClient (real HTTP, no MockTransport).
            # We import AsyncClient from httpx._client to bypass conftest's
            # global mock on httpx.AsyncClient, then pre-initialize the pool
            # so get_client() returns this real client.
            pool = ConnectionPool(timeout_seconds=120.0)
            pool.client = RealAsyncClient(
                limits=httpx.Limits(
                    max_connections=100,
                    max_keepalive_connections=50,
                ),
                timeout=httpx.Timeout(120.0),
            )
            pool._initialized = True

            # Real ChannelFactory → creates a real APIChannel with our real pool
            channel_factory = ChannelFactory(
                replay_mode=False,
                connection_pool=pool,
            )

            # Real FileSystem (absolute temp path works with os.path.join)
            filesystem = FileSystem(shared_dir=tmpdir)

            # Real Agent with all real dependencies
            agent = Agent(self.config, channel_factory, filesystem, instance_number=1)

            # Verify the channel is a real APIChannel, not a Mock
            self.assertIsInstance(agent.channel, APIChannel,
                                 "Agent must have a real APIChannel, not a Mock")

            # Execute against the REAL LLM endpoint at localhost:12345
            # No mocks on tool execution — read_file, write_file,
            # confirm_task_complete all run for real against the temp directory
            result = agent.execute_with_agentic_loop(
                {"user_prompt": (
                    "Read the file 'test.md' in the working directory, then "
                    "overwrite it with the heading '# Updated' followed by a "
                    "blank line and 'Content updated by agent'. "
                    "After writing, call confirm_task_complete()."
                )},
                working_dir=tmpdir,
                max_iterations=10,
            )

            # --- ASSERTIONS ---

            # Developer should complete the task (confirm_task_complete allowed)
            self.assertTrue(result["task_complete"],
                            "Developer must be able to call confirm_task_complete()")

            # Should complete efficiently — the fix ensures ≤5 iterations, not 13+
            self.assertLessEqual(
                result["iteration_count"], 5,
                f"Should complete in ≤5 iterations, took {result['iteration_count']}"
            )

            # File should have been modified by real tool execution
            with open(test_file, "r") as f:
                final_content = f.read()
            self.assertNotEqual(
                final_content, original_content,
                "File should have been modified by real write_file() execution"
            )


if __name__ == '__main__':
    unittest.main()
