"""
Integration tests for event sourcing decorator with actual coordinator functions.
"""

import json
import os
import tempfile
import unittest
from unittest.mock import Mock, MagicMock, patch

from crosscutting import event_sourced
from fileio import FileSystem


class TestEventSourcingIntegration(unittest.TestCase):
    """Test event sourcing decorator integration with coordinator functions."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.shared_dir = os.path.join(self.temp_dir, "shared")
        os.makedirs(self.shared_dir, exist_ok=True)
        self.fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
    
    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_execute_single_assignment_decorated(self):
        """Should record event when execute_single_assignment is called."""
        # Import the actual function
        from main.coordinator.execution import execute_single_assignment
        
        # Create a mock coordinator
        mock_coordinator = Mock()
        mock_coordinator.filesystem = self.fs
        mock_coordinator.replay_mode = False
        mock_coordinator.create_agent_for_role = Mock()
        
        # Create a mock agent
        mock_agent = Mock()
        mock_agent.name = "test_agent"
        mock_agent.execute_task = Mock(return_value="Task completed")
        mock_coordinator.create_agent_for_role.return_value = mock_agent
        
        # Mock the agentic loop
        with patch('main.coordinator.execution.execute_with_agentic_loop') as mock_loop:
            mock_loop.return_value = {
                "final_response": "Test response",
                "tool_results": [],
                "iteration_count": 1,
                "task_complete": True,
            }
            
            # Execute the function
            result = execute_single_assignment(
                mock_coordinator,
                role="developer",
                task={"description": "Test task"},
                original_request="Test request"
            )
        
        # Verify function executed correctly
        self.assertIsNotNone(result)
        self.assertEqual(result["role"], "developer")
        
        # Verify event was recorded by decorator
        events = self.fs.get_events(event_type="task_completed")
        self.assertEqual(len(events), 1)
        
        event = events[0]
        self.assertEqual(event["type"], "task_completed")
        self.assertEqual(event["data"]["function"], "execute_single_assignment")
        self.assertIn("parameters", event["data"])
        self.assertEqual(event["data"]["parameters"]["role"], "developer")
        self.assertIn("Test task", event["data"]["parameters"]["task"])
    
    def test_decompose_request_decorated(self):
        """Should record event when decompose_request is called."""
        # Import the actual function
        from main.coordinator.decomposer import decompose_request
        
        # Create a mock coordinator
        mock_coordinator = Mock()
        mock_coordinator.filesystem = self.fs
        mock_coordinator.config = {"developer": {}, "manager": {}}
        mock_coordinator.create_agent_for_role = Mock()
        
        # Create a mock manager agent
        mock_manager = Mock()
        mock_manager.name = "manager"
        mock_manager.execute_task = Mock(return_value='[{"role": "developer", "task": "Test task", "sequence": 1}]')
        mock_coordinator.create_agent_for_role.return_value = mock_manager
        
        # Mock the validator
        with patch('main.coordinator.decomposer.validate_assignment_roles') as mock_validator:
            mock_validator.return_value = []  # No invalid roles
            
            # Execute the function
            result = decompose_request(mock_coordinator, "Build a test app")
        
        # Verify function executed correctly
        self.assertIsNotNone(result)
        assignments = json.loads(result)
        self.assertEqual(len(assignments), 1)
        
        # Verify event was recorded by decorator
        events = self.fs.get_events(event_type="request_decomposed")
        self.assertEqual(len(events), 1)
        
        event = events[0]
        self.assertEqual(event["type"], "request_decomposed")
        self.assertEqual(event["data"]["function"], "decompose_request")
        self.assertIn("parameters", event["data"])
        self.assertEqual(event["data"]["parameters"]["user_request"], "Build a test app")
    
    def test_execute_task_decorated(self):
        """Should record event when execute_task is called."""
        # Import the actual function
        from main.agent.executor import execute_task
        
        # Create a mock agent
        mock_agent = Mock()
        mock_agent.name = "test_agent"
        mock_agent.filesystem = self.fs
        mock_agent.MAX_RETRIES = 3
        mock_agent.INITIAL_TIMEOUT_MULTIPLIER = 2
        mock_agent.BACKOFF_MULTIPLIER = 2
        mock_agent.config = {
            "timeout": 10,
            "system_prompt": "Test prompt",
            "temperature": 0.7,
            "max_tokens": 100,
            "model": "test-model",
            "endpoint": "http://test"
        }
        
        # Mock the send_llm_request function
        with patch('main.agent.executor.send_llm_request') as mock_send:
            mock_send.return_value = {"response": "Task executed"}
            
            # Mock parse_model_endpoints
            with patch('main.agent.executor.parse_model_endpoints') as mock_parse:
                mock_parse.return_value = [{"model": "test-model", "endpoint": "http://test"}]
                
                # Execute the function
                result = execute_task(mock_agent, {"user_prompt": "Do something"})
        
        # Verify function executed correctly
        self.assertEqual(result, "Task executed")
        
        # Verify event was recorded by decorator
        events = self.fs.get_events(event_type="task_execution")
        self.assertEqual(len(events), 1)
        
        event = events[0]
        self.assertEqual(event["type"], "task_execution")
        self.assertEqual(event["data"]["function"], "execute_task")
        self.assertIn("parameters", event["data"])
        self.assertIn("task", event["data"]["parameters"])


if __name__ == '__main__':
    unittest.main()
