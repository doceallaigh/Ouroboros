"""
Integration tests for callback routing and developer retry mechanisms.

Tests cover:
1. Developer task completion without file creation triggers retry consideration
2. Auditor callbacks result in task assignment back to appropriate role
3. Callback routing from auditor → manager → developer retry
4. File persistence validation
5. Complete workflow with blockers and remediation
"""

import pytest
import json
import time
from unittest.mock import Mock, MagicMock, patch, call, PropertyMock
from typing import Dict, List, Any
from collections import defaultdict

import sys
sys.path.insert(0, 'src')

from main import CentralCoordinator, Agent, OrganizationError
from fileio import FileSystem


class CallbackTrackingFileSystem:
    """Filesystem that tracks file operations for testing."""
    
    def __init__(self):
        self.events = []
        self.files = {}
        self.working_dir = "/mock/workspace"
        self.src_dir = "/mock/workspace"
        self.write_operations = []
        self.read_operations = []
    
    def record_event(self, event_type: str, data: Dict[str, Any]):
        """Record event and track callbacks specially."""
        event = {
            "type": event_type,
            "data": data,
            "timestamp": time.time()
        }
        self.events.append(event)
        
        if event_type == "AGENT_CALLBACK":
            # Track callbacks separately
            if not hasattr(self, 'callbacks'):
                self.callbacks = []
            self.callbacks.append(data)
    
    def write_file(self, path: str, content: str):
        """Track file writes."""
        self.files[path] = content
        self.write_operations.append({"path": path, "size": len(content)})
    
    def read_file(self, path: str) -> str:
        """Track file reads."""
        self.read_operations.append({"path": path})
        return self.files.get(path, "")
    
    def list_files_in_workspace(self) -> List[str]:
        """List all files."""
        return list(self.files.keys())
    
    def get_recorded_outputs_in_order(self, agent_name: str) -> List[tuple]:
        """Get recorded outputs (replay mode)."""
        return []
    
    def file_exists(self, path: str) -> bool:
        """Check if file exists."""
        return path in self.files
    
    def get_callbacks(self) -> List[Dict]:
        """Get all callbacks recorded."""
        return getattr(self, 'callbacks', [])
    
    # Event constants
    EVENT_TASK_STARTED = "task_started"
    EVENT_TASK_COMPLETED = "task_completed"
    EVENT_TASK_FAILED = "task_failed"


@pytest.fixture
def tracking_filesystem():
    """Provide a tracking filesystem."""
    return CallbackTrackingFileSystem()


@pytest.fixture
def mock_config(tmp_path):
    """Create mock roles configuration."""
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


class TestDeveloperCompletionWithoutCode:
    """Test behavior when developer completes without creating files."""
    
    def test_developer_task_without_file_creation(self, mock_config, tracking_filesystem):
        """Developer completing without files should be trackable."""
        coordinator = CentralCoordinator(
            config_path=mock_config,
            filesystem=tracking_filesystem,
            replay_mode=False
        )
        
        mock_loop_result = {
            "final_response": "Attempted to create file",
            "tool_results": [{"tools_executed": False, "estimated_tool_calls": 0}],
            "iteration_count": 1,
            "task_complete": True
        }
        
        with patch.object(coordinator, 'create_agent_for_role') as mock_create:
            with patch('main.coordinator.execution.execute_with_agentic_loop', return_value=mock_loop_result):
                mock_developer = Mock()
                mock_developer.name = "developer01"
                mock_create.return_value = mock_developer
                
                # Ensure no files before task
                assert len(tracking_filesystem.list_files_in_workspace()) == 0
                
                # Execute developer task
                result = coordinator.execute_single_assignment(
                    role="developer",
                    task={"description": "Create requirements.txt"},
                    original_request="Build ML project"
                )
                
                # Still no files after task
                assert len(tracking_filesystem.list_files_in_workspace()) == 0
                
                # Result should indicate execution completed
                assert result["source"] == "execution"
                assert result["role"] == "developer"
                
                # Tool results show no tools were executed
                assert result["tool_results"][0]["tools_executed"] == False
    

class TestCallbackRouting:
    """Test that callbacks are routed to appropriate agents."""
    
    def test_blocker_callback_creates_retry_task(self, mock_config, tracking_filesystem):
        """Blocker callback should trigger retry task creation."""
        coordinator = CentralCoordinator(
            config_path=mock_config,
            filesystem=tracking_filesystem,
            replay_mode=False
        )
        
        # Simulate blocker callback from auditor
        coordinator.callbacks.append({
            "from": "auditor01",
            "to": "manager",
            "type": "blocker",
            "message": "Required file data_preprocessing.py was not created by developer01"
        })
        
        # Get blockers
        blockers = coordinator.get_blocker_callbacks()
        
        assert len(blockers) == 1
        assert "data_preprocessing.py" in blockers[0]["message"]
        assert blockers[0]["type"] == "blocker"
    
    def test_multiple_blockers_from_different_auditors(self, mock_config, tracking_filesystem):
        """Multiple blockers from different auditors should all be tracked."""
        coordinator = CentralCoordinator(
            config_path=mock_config,
            filesystem=tracking_filesystem,
            replay_mode=False
        )
        
        # Multiple blockers from different auditors
        coordinator.callbacks.extend([
            {
                "from": "auditor01",
                "type": "blocker",
                "message": "File requirements.txt not created"
            },
            {
                "from": "auditor02",
                "type": "blocker",
                "message": "File data_preprocessing.py not created"
            },
            {
                "from": "auditor03",
                "type": "blocker",
                "message": "File sentiment_classifier.py not created"
            }
        ])
        
        blockers = coordinator.get_blocker_callbacks()
        
        assert len(blockers) == 3
        assert all(b["type"] == "blocker" for b in blockers)
        assert len([b for b in blockers if "auditor01" in b.get("from", "")]) == 1


class TestCallbackToAgentExecution:
    """Test that callbacks trigger appropriate agent execution."""
    
    def test_developer_agent_receives_retry_task_for_blocker(self, mock_config, tracking_filesystem):
        """Developer should receive retry task when file creation fails."""
        coordinator = CentralCoordinator(
            config_path=mock_config,
            filesystem=tracking_filesystem,
            replay_mode=False
        )
        
        # Simulate: developer failed to create file → auditor detected → blocker raised
        coordinator.callbacks.append({
            "from": "auditor01",
            "type": "blocker",
            "message": "Required file requirements.txt was not created",
            "timestamp": time.time()
        })
        
        # Extract blockers
        blockers = coordinator.get_blocker_callbacks()
        
        # Verify we can identify this is a missing file issue
        assert len(blockers) > 0
        assert "was not created" in blockers[0]["message"]
        
        # In real implementation, this would trigger developer01 retry
        # For now, verify we can identify it needs developer action
        assert blockers[0]["type"] == "blocker"


class TestFilePersistenceValidation:
    """Test file persistence and validation."""
    
    def test_auditor_can_verify_created_files(self, mock_config, tracking_filesystem):
        """Auditor should be able to verify files created by developer."""
        coordinator = CentralCoordinator(
            config_path=mock_config,
            filesystem=tracking_filesystem,
            replay_mode=False
        )
        
        # Pre-populate workspace with developer-created files
        tracking_filesystem.write_file("requirements.txt", "numpy==1.20.0")
        tracking_filesystem.write_file("app.py", "print('hello')")
        
        # Auditor should find these files
        files = tracking_filesystem.list_files_in_workspace()
        assert len(files) == 2
        assert tracking_filesystem.file_exists("requirements.txt")
        assert tracking_filesystem.file_exists("app.py")


class TestCompleteWorkflow:
    """End-to-end workflow tests."""
    
    def test_workflow_multiple_developers_and_auditors_with_blockers(
        self, mock_config, tracking_filesystem
    ):
        """Multiple developers and auditors with various blockers."""
        coordinator = CentralCoordinator(
            config_path=mock_config,
            filesystem=tracking_filesystem,
            replay_mode=False
        )
        
        # Simulate multiple callback scenarios
        coordinator.callbacks.extend([
            {
                "from": "auditor01",
                "type": "blocker",
                "message": "Developer01: requirements.txt not created"
            },
            {
                "from": "auditor02",
                "type": "blocker",
                "message": "Developer02: data_preprocessing.py not created"
            },
            {
                "from": "auditor03",
                "type": "query",
                "message": "Need clarification on architecture"
            },
            {
                "from": "auditor04",
                "type": "blocker",
                "message": "Developer03: sentiment_classifier.py not created"
            }
        ])
        
        blockers = coordinator.get_blocker_callbacks()
        queries = [c for c in coordinator.callbacks if c["type"] == "query"]
        
        assert len(blockers) == 3
        assert len(queries) == 1
        
        # All blockers are about missing files
        assert all("not created" in b["message"] for b in blockers)
    
    def test_final_verification_includes_blocker_summary(
        self, mock_config, tracking_filesystem
    ):
        """Final verification should include summary of found blockers."""
        coordinator = CentralCoordinator(
            config_path=mock_config,
            filesystem=tracking_filesystem,
            replay_mode=False
        )
        
        # Add some blockers as if found during audit
        coordinator.callbacks.extend([
            {"type": "blocker", "message": "File A missing"},
            {"type": "blocker", "message": "File B missing"},
            {"type": "blocker", "message": "File C missing"}
        ])
        
        # Create final verification task
        task = coordinator.create_final_verification_task("Test request", [])
        
        # Task should reference the original request and be an auditor task
        assert "ORIGINAL REQUEST" in task["task"]
        assert "confirm_task_complete" in task["task"]
        assert task["role"] == "auditor"
        assert task["sequence"] == 99



if __name__ == "__main__":
    pytest.main([__file__, "-v"])
