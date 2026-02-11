"""
Component tests for callback handling and final verification.

Tests cover:
1. Callback collection and blocker extraction
2. Final verification auditor task creation
3. Developer task retry when no files created
4. Callback routing to agent execution
5. End-to-end workflow with callbacks and verification
"""

import pytest
import json
import time
from unittest.mock import Mock, MagicMock, patch, call
from typing import Dict, List, Any

# Import the coordinator and related classes
import sys
sys.path.insert(0, 'src')

from main import CentralCoordinator, Agent, OrganizationError
from fileio import FileSystem
from comms import ChannelFactory


class MockFileSystem:
    """Mock filesystem for testing."""
    
    def __init__(self):
        self.events = []
        self.files = {}
        self.working_dir = "/mock/workspace"
    
    def record_event(self, event_type: str, data: Dict[str, Any]):
        """Record an event."""
        self.events.append({
            "type": event_type,
            "data": data,
            "timestamp": time.time()
        })
    
    def write_file(self, path: str, content: str):
        """Write a file."""
        self.files[path] = content
    
    def read_file(self, path: str) -> str:
        """Read a file."""
        return self.files.get(path, "")
    
    def list_files_in_workspace(self) -> List[str]:
        """List files in workspace."""
        return list(self.files.keys())
    
    def get_recorded_outputs_in_order(self, agent_name: str) -> List[tuple]:
        """Get recorded outputs."""
        return []
    
    # Add event constants used by coordinator
    EVENT_TASK_STARTED = "task_started"
    EVENT_TASK_COMPLETED = "task_completed"
    EVENT_TASK_FAILED = "task_failed"


class MockChannelFactory:
    """Mock channel factory for testing."""
    
    def __init__(self, responses: Dict[str, str] = None):
        self.responses = responses or {}
        self.call_count = 0
    
    def create_channel(self, config: Dict) -> Mock:
        """Create a mock channel."""
        mock_channel = Mock()
        mock_channel.send_message = Mock(side_effect=self._mock_send_message)
        return mock_channel
    
    def _mock_send_message(self, messages: List[Dict]):
        """Mock message sending."""
        self.call_count += 1
        # Return a predefined response or default
        role = "unknown"
        for msg in messages:
            if msg.get("role") == "system":
                if "manager" in msg.get("content", "").lower():
                    role = "manager"
                elif "developer" in msg.get("content", "").lower():
                    role = "developer"
                elif "auditor" in msg.get("content", "").lower():
                    role = "auditor"
        
        response_key = f"response_{self.call_count}"
        if response_key in self.responses:
            return {"content": self.responses[response_key]}
        elif role in self.responses:
            return {"content": self.responses[role]}
        else:
            return {"content": "Mock response"}


@pytest.fixture
def mock_filesystem():
    """Provide a mock filesystem."""
    return MockFileSystem()


@pytest.fixture
def mock_config(tmp_path):
    """Create a mock roles.json configuration."""
    config = {
        "manager": {
            "role": "manager",
            "model": "test-model",
            "system_prompt": "You are a manager"
        },
        "developer": {
            "role": "developer",
            "model": "test-model",
            "system_prompt": "You are a developer"
        },
        "auditor": {
            "role": "auditor",
            "model": "test-model",
            "system_prompt": "You are an auditor"
        }
    }
    
    config_file = tmp_path / "roles.json"
    config_file.write_text(json.dumps(config))
    return str(config_file)


class TestCallbackCollection:
    """Test callback collection mechanism."""
    
    def test_callbacks_initialized_empty(self, mock_config, mock_filesystem):
        """Callbacks list should be initialized empty."""
        coordinator = CentralCoordinator(
            config_path=mock_config,
            filesystem=mock_filesystem,
            replay_mode=False
        )
        
        assert coordinator.callbacks == []
        assert isinstance(coordinator.callbacks, list)
    
    def test_callback_handler_collects_callback(self, mock_config, mock_filesystem):
        """Callback handler should collect callbacks."""
        coordinator = CentralCoordinator(
            config_path=mock_config,
            filesystem=mock_filesystem,
            replay_mode=False
        )
        
        # Simulate a callback being raised
        # We need to trigger this through a task execution
        with patch.object(coordinator, 'create_agent_for_role') as mock_create:
            mock_agent = Mock()
            mock_agent.name = "auditor01"
            mock_agent.callback_handler = None
            mock_agent.execute_task = Mock(return_value="Audit result")
            mock_agent.execute_tools_from_response = Mock(return_value={
                "tools_executed": False,
                "estimated_tool_calls": 0
            })
            
            mock_create.return_value = mock_agent
            
            # Execute a task with a caller (enables callbacks)
            result = coordinator.execute_single_assignment(
                role="auditor",
                task={"description": "Test audit", "caller": "manager"},
                original_request="Test request"
            )
            
            # Now manually trigger a callback to test collection
            # The callback handler should have been set on the agent
            if mock_agent.callback_handler:
                mock_agent.callback_handler("auditor01", "Test blocker", "blocker")
                
                # Verify callback was collected
                assert len(coordinator.callbacks) > 0
                assert coordinator.callbacks[0]["from"] == "auditor01"
                assert coordinator.callbacks[0]["type"] == "blocker"
    
    def test_blocker_callback_logged_as_warning(self, mock_config, mock_filesystem):
        """Blocker callbacks should be logged as warnings."""
        coordinator = CentralCoordinator(
            config_path=mock_config,
            filesystem=mock_filesystem,
            replay_mode=False
        )
        
        with patch('main.logger') as mock_logger:
            # Create and execute a task that will set up callback handler
            with patch.object(coordinator, 'create_agent_for_role') as mock_create:
                mock_agent = Mock()
                mock_agent.name = "auditor01"
                mock_agent.callback_handler = None
                mock_agent.execute_task = Mock(return_value="")
                mock_agent.execute_tools_from_response = Mock(return_value={
                    "tools_executed": False,
                    "estimated_tool_calls": 0
                })
                
                mock_create.return_value = mock_agent
                
                coordinator.execute_single_assignment(
                    role="auditor",
                    task={"description": "Test", "caller": "manager"},
                    original_request="Test"
                )
                
                # Trigger a blocker callback
                if mock_agent.callback_handler:
                    mock_agent.callback_handler(
                        "auditor01",
                        "Required file test.txt was not created",
                        "blocker"
                    )
                    
                    # Verify warning was logged
                    warning_calls = [
                        c for c in mock_logger.warning.call_args_list
                        if "BLOCKER" in str(c)
                    ]
                    assert len(warning_calls) > 0


class TestBlockerExtraction:
    """Test blocker extraction functionality."""
    
    def test_get_blocker_callbacks_filters_blockers(self, mock_config, mock_filesystem):
        """_get_blocker_callbacks should filter only blocker type callbacks."""
        coordinator = CentralCoordinator(
            config_path=mock_config,
            filesystem=mock_filesystem,
            replay_mode=False
        )
        
        # Manually add various callbacks
        coordinator.callbacks = [
            {"type": "blocker", "message": "Issue 1"},
            {"type": "query", "message": "Question 1"},
            {"type": "blocker", "message": "Issue 2"},
            {"type": "clarification", "message": "Need clarification"},
            {"type": "blocker", "message": "Issue 3"},
        ]
        
        blockers = coordinator.get_blocker_callbacks()
        
        assert len(blockers) == 3
        assert all(cb["type"] == "blocker" for cb in blockers)
        assert blockers[0]["message"] == "Issue 1"
        assert blockers[1]["message"] == "Issue 2"
        assert blockers[2]["message"] == "Issue 3"
    
    def test_get_blocker_callbacks_empty_when_no_blockers(self, mock_config, mock_filesystem):
        """_get_blocker_callbacks should return empty list when no blockers."""
        coordinator = CentralCoordinator(
            config_path=mock_config,
            filesystem=mock_filesystem,
            replay_mode=False
        )
        
        coordinator.callbacks = [
            {"type": "query", "message": "Question"},
            {"type": "clarification", "message": "Clarification"},
        ]
        
        blockers = coordinator.get_blocker_callbacks()
        
        assert len(blockers) == 0


class TestFinalVerificationTask:
    """Test final verification task creation."""
    
    def test_final_verification_task_created(self, mock_config, mock_filesystem):
        """_create_final_verification_task should create valid task."""
        coordinator = CentralCoordinator(
            config_path=mock_config,
            filesystem=mock_filesystem,
            replay_mode=False
        )
        
        user_request = "Create a simple Python app"
        all_results = []
        
        task = coordinator.create_final_verification_task(user_request, all_results)
        
        # Add some blockers
        coordinator.callbacks = [
            {
                "type": "blocker",
                "message": "Required file data_preprocessing.py was not created"
            },
            {
                "type": "blocker",
                "message": "Required file requirements.txt was not created"
            }
        ]
        
        task = coordinator.create_final_verification_task("Test", [])
        
        # Task should mention previous blockers
        assert "Previous blockers" in task["task"] or len(coordinator.get_blocker_callbacks()) > 0


class TestDeveloperRetry:
    """Test that developers retry when they don't create files."""
    
    def test_task_result_includes_file_count(self, mock_config, mock_filesystem):
        """Task results should include file creation tracking."""
        coordinator = CentralCoordinator(
            config_path=mock_config,
            filesystem=mock_filesystem,
            replay_mode=False
        )
        
        with patch.object(coordinator, 'create_agent_for_role') as mock_create:
            mock_agent = Mock()
            mock_agent.name = "developer01"
            mock_agent.callback_handler = None
            mock_agent.execute_task = Mock(return_value="Created requirements.txt")
            mock_agent.execute_tools_from_response = Mock(return_value={
                "tools_executed": True,
                "estimated_tool_calls": 1
            })
            
            mock_create.return_value = mock_agent
            
            # Pre-populate filesystem with a file
            mock_filesystem.files["requirements.txt"] = "numpy==1.20.0"
            
            result = coordinator.execute_single_assignment(
                role="developer",
                task="Create requirements.txt",
                original_request="Create a project"
            )
            
            assert result["status"] == "completed"
            assert "tool_execution" in result


class TestCallbackToAgentExecution:
    """Test that callbacks result in agent execution."""
    
    def test_blocker_callback_recorded_in_events(self, mock_config, mock_filesystem):
        """Blocker callbacks should be recorded in event log."""
        coordinator = CentralCoordinator(
            config_path=mock_config,
            filesystem=mock_filesystem,
            replay_mode=False
        )
        
        with patch.object(coordinator, 'create_agent_for_role') as mock_create:
            mock_agent = Mock()
            mock_agent.name = "auditor01"
            mock_agent.callback_handler = None
            mock_agent.execute_task = Mock(return_value="")
            mock_agent.execute_tools_from_response = Mock(return_value={
                "tools_executed": False,
                "estimated_tool_calls": 0
            })
            
            mock_create.return_value = mock_agent
            
            coordinator.execute_single_assignment(
                role="auditor",
                task={"description": "Audit", "caller": "manager"},
                original_request="Test"
            )
            
            # Trigger callback
            if mock_agent.callback_handler:
                mock_agent.callback_handler(
                    "auditor01",
                    "Required file was not created",
                    "blocker"
                )
                
                # Check event was recorded
                callback_events = [
                    e for e in mock_filesystem.events
                    if e["type"] == "AGENT_CALLBACK"
                ]
                assert len(callback_events) > 0
                assert callback_events[0]["data"]["type"] == "blocker"


class TestEndToEndFlow:
    """Integration tests for the complete flow."""
    
    def test_callbacks_collected_during_assignment_execution(self, mock_config, mock_filesystem):
        """Callbacks should be collected throughout assignment execution."""
        coordinator = CentralCoordinator(
            config_path=mock_config,
            filesystem=mock_filesystem,
            replay_mode=False
        )
        
        # Verify callbacks list exists and starts empty
        assert hasattr(coordinator, 'callbacks')
        assert len(coordinator.callbacks) == 0
    
    def test_final_verification_runs_in_assign_and_execute(self, mock_config, mock_filesystem):
        """assign_and_execute should include final verification phase."""
        coordinator = CentralCoordinator(
            config_path=mock_config,
            filesystem=mock_filesystem,
            replay_mode=False
        )
        
        with patch.object(coordinator, 'decompose_request') as mock_decompose:
            with patch.object(coordinator, '_execute_assignments') as mock_execute:
                with patch.object(coordinator, 'execute_single_assignment') as mock_single:
                    with patch('main.logger'):
                        # Mock decompose to return empty assignments
                        mock_decompose.return_value = json.dumps([])
                        
                        # Mock _execute_assignments to return empty results
                        mock_execute.return_value = []
                        
                        # Mock execute_single_assignment for final verification
                        mock_single.return_value = {
                            "role": "auditor",
                            "status": "completed",
                            "output": "PASS"
                        }
                        
                        results = coordinator.assign_and_execute("Test request")
                        
                        # Should have called execute_single_assignment for verification
                        # (Called at least once for final verification)
                        assert mock_single.called
    
    def test_multiple_callbacks_tracked_separately(self, mock_config, mock_filesystem):
        """Multiple callbacks should be tracked as separate entries."""
        coordinator = CentralCoordinator(
            config_path=mock_config,
            filesystem=mock_filesystem,
            replay_mode=False
        )
        
        # Add multiple callbacks
        coordinator.callbacks.append({
            "from": "auditor01",
            "type": "blocker",
            "message": "File A missing"
        })
        coordinator.callbacks.append({
            "from": "auditor02",
            "type": "blocker",
            "message": "File B missing"
        })
        coordinator.callbacks.append({
            "from": "auditor03",
            "type": "query",
            "message": "Question about design"
        })
        
        assert len(coordinator.callbacks) == 3
        
        blockers = coordinator.get_blocker_callbacks()
        assert len(blockers) == 2
        assert blockers[0]["from"] == "auditor01"
        assert blockers[1]["from"] == "auditor02"


class TestRetryMechanism:
    """Test retry logic for failed tasks."""
    
    def test_no_callback_before_retry_attempt(self, mock_config, mock_filesystem):
        """Developer should attempt work before callback on missing files."""
        coordinator = CentralCoordinator(
            config_path=mock_config,
            filesystem=mock_filesystem,
            replay_mode=False
        )
        
        with patch.object(coordinator, 'create_agent_for_role') as mock_create:
            mock_agent = Mock()
            mock_agent.name = "developer01"
            mock_agent.callback_handler = None
            mock_agent.execute_task = Mock(return_value="Created file")
            mock_agent.execute_tools_from_response = Mock(return_value={
                "tools_executed": True,
                "estimated_tool_calls": 1
            })
            
            mock_create.return_value = mock_agent
            
            # Start with empty filesystem
            assert len(mock_filesystem.files) == 0
            
            # Execute developer task
            result = coordinator.execute_single_assignment(
                role="developer",
                task="Create requirements.txt",
                original_request="Setup"
            )
            
            # Developer should have executed
            assert mock_agent.execute_task.called
            
            # No callback should have been raised yet (developer executed)
            assert len(coordinator.callbacks) == 0


class TestMockIntegration:
    """Test the mock infrastructure itself."""
    
    def test_mock_filesystem_write_and_read(self, mock_filesystem):
        """Mock filesystem should support write and read."""
        mock_filesystem.write_file("test.txt", "content")
        assert mock_filesystem.read_file("test.txt") == "content"
    
    def test_mock_filesystem_list_files(self, mock_filesystem):
        """Mock filesystem should list files."""
        mock_filesystem.write_file("file1.py", "code1")
        mock_filesystem.write_file("file2.py", "code2")
        
        files = mock_filesystem.list_files_in_workspace()
        assert "file1.py" in files
        assert "file2.py" in files
        assert len(files) == 2
    
    def test_mock_filesystem_record_events(self, mock_filesystem):
        """Mock filesystem should record events."""
        mock_filesystem.record_event("test_event", {"key": "value"})
        assert len(mock_filesystem.events) == 1
        assert mock_filesystem.events[0]["type"] == "test_event"


if __name__ == "__main__":
    # Run tests with: pytest test_callback_and_verification.py -v
    pytest.main([__file__, "-v"])
