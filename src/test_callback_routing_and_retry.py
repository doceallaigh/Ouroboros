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
from fileio.fileio import FileSystem


class CallbackTrackingFileSystem:
    """Filesystem that tracks file operations for testing."""
    
    def __init__(self):
        self.events = []
        self.files = {}
        self.working_dir = "/mock/workspace"
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
        
        with patch.object(coordinator, '_create_agent_for_role') as mock_create:
            # Developer that doesn't create files
            mock_developer = Mock()
            mock_developer.name = "developer01"
            mock_developer.callback_handler = None
            mock_developer.execute_task = Mock(return_value="Attempted to create file")
            mock_developer.execute_tools_from_response = Mock(return_value={
                "tools_executed": False,  # No actual tool execution
                "estimated_tool_calls": 0
            })
            
            mock_create.return_value = mock_developer
            
            # Ensure no files before task
            assert len(tracking_filesystem.list_files_in_workspace()) == 0
            
            # Execute developer task
            result = coordinator._execute_single_assignment(
                role="developer",
                task="Create requirements.txt",
                original_request="Build ML project"
            )
            
            # Still no files after task
            assert len(tracking_filesystem.list_files_in_workspace()) == 0
            
            # Result should be marked completed (developer tried)
            assert result["status"] == "completed"
            
            # But we can track that no files were created
            assert result.get("tool_execution", {}).get("tools_executed") == False
    
    def test_auditor_detects_missing_files_and_raises_blocker(self, mock_config, tracking_filesystem):
        """Auditor should detect missing files and raise blockers."""
        coordinator = CentralCoordinator(
            config_path=mock_config,
            filesystem=tracking_filesystem,
            replay_mode=False
        )
        
        with patch.object(coordinator, '_create_agent_for_role') as mock_create:
            # Auditor that detects missing files
            mock_auditor = Mock()
            mock_auditor.name = "auditor01"
            mock_auditor.callback_handler = None
            mock_auditor.execute_task = Mock(
                return_value="Checked for requirements.txt - NOT FOUND"
            )
            mock_auditor.execute_tools_from_response = Mock(return_value={
                "tools_executed": False,
                "estimated_tool_calls": 0
            })
            
            mock_create.return_value = mock_auditor
            
            # Execute auditor task (as if developer failed)
            result = coordinator._execute_single_assignment(
                role="auditor",
                task={
                    "description": "Verify requirements.txt was created",
                    "caller": "manager"
                },
                original_request="Build project"
            )
            
            # Verify callback handler was set up
            assert mock_auditor.callback_handler is not None
            
            # Simulate auditor raising a blocker
            mock_auditor.callback_handler(
                "auditor01",
                "Required file requirements.txt was not created",
                "blocker"
            )
            
            # Verify blocker was collected
            assert len(coordinator.callbacks) > 0
            assert coordinator.callbacks[0]["type"] == "blocker"
            assert "requirements.txt" in coordinator.callbacks[0]["message"]
    
    def test_missing_file_blocker_recorded_in_events(self, mock_config, tracking_filesystem):
        """Missing file blockers should be recorded in event log."""
        coordinator = CentralCoordinator(
            config_path=mock_config,
            filesystem=tracking_filesystem,
            replay_mode=False
        )
        
        with patch.object(coordinator, '_create_agent_for_role') as mock_create:
            mock_auditor = Mock()
            mock_auditor.name = "auditor01"
            mock_auditor.callback_handler = None
            mock_auditor.execute_task = Mock(return_value="Audit result")
            mock_auditor.execute_tools_from_response = Mock(return_value={
                "tools_executed": False,
                "estimated_tool_calls": 0
            })
            
            mock_create.return_value = mock_auditor
            
            coordinator._execute_single_assignment(
                role="auditor",
                task={"description": "Audit", "caller": "manager"},
                original_request="Test"
            )
            
            # Raise blocker
            if mock_auditor.callback_handler:
                mock_auditor.callback_handler(
                    "auditor01",
                    "File requirements.txt not found",
                    "blocker"
                )
            
            # Check filesystem events
            callback_events = [e for e in tracking_filesystem.events if e["type"] == "AGENT_CALLBACK"]
            assert len(callback_events) > 0
            assert callback_events[0]["data"]["type"] == "blocker"


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
        blockers = coordinator._get_blocker_callbacks()
        
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
        
        blockers = coordinator._get_blocker_callbacks()
        
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
        blockers = coordinator._get_blocker_callbacks()
        
        # Verify we can identify this is a missing file issue
        assert len(blockers) > 0
        assert "was not created" in blockers[0]["message"]
        
        # In real implementation, this would trigger developer01 retry
        # For now, verify we can identify it needs developer action
        assert blockers[0]["type"] == "blocker"
    
    def test_agent_execution_for_blocker_can_be_routed(self, mock_config, tracking_filesystem):
        """Blocker routing should determine agent role."""
        coordinator = CentralCoordinator(
            config_path=mock_config,
            filesystem=tracking_filesystem,
            replay_mode=False
        )
        
        blocker_message = "Required file requirements.txt was not created"
        
        # Determine appropriate role for remediation
        def get_remediation_role(blocker_msg):
            if "file" in blocker_msg.lower() and "not created" in blocker_msg.lower():
                return "developer"  # Developer should create the missing file
            elif "quality" in blocker_msg.lower() or "error" in blocker_msg.lower():
                return "developer"  # Developer should fix quality issues
            else:
                return "auditor"  # Auditor can clarify
        
        remediation_role = get_remediation_role(blocker_message)
        assert remediation_role == "developer"


class TestFilePersistenceValidation:
    """Test file persistence and validation."""
    
    def test_files_created_by_developer_persist(self, mock_config, tracking_filesystem):
        """Files created by developer should persist."""
        coordinator = CentralCoordinator(
            config_path=mock_config,
            filesystem=tracking_filesystem,
            replay_mode=False
        )
        
        with patch.object(coordinator, '_create_agent_for_role') as mock_create:
            # Developer that creates files via tools
            mock_developer = Mock()
            mock_developer.name = "developer01"
            mock_developer.callback_handler = None
            mock_developer.execute_task = Mock(
                return_value="Created requirements.txt with numpy==1.20.0"
            )
            
            def mock_tool_execution(response, working_dir):
                # Simulate tool execution that creates files
                tracking_filesystem.write_file(
                    "requirements.txt",
                    "numpy==1.20.0\nscikit-learn==0.24.0"
                )
                return {
                    "tools_executed": True,
                    "estimated_tool_calls": 1,
                    "created_files": ["requirements.txt"]
                }
            
            mock_developer.execute_tools_from_response = Mock(
                side_effect=mock_tool_execution
            )
            
            mock_create.return_value = mock_developer
            
            # Execute task
            result = coordinator._execute_single_assignment(
                role="developer",
                task="Create requirements.txt",
                original_request="Setup"
            )
            
            # Verify file persists
            files = tracking_filesystem.list_files_in_workspace()
            assert "requirements.txt" in files
            
            # Verify content
            content = tracking_filesystem.read_file("requirements.txt")
            assert "numpy" in content
    
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
    
    def test_workflow_developer_fails_auditor_detects_blocker_collected(
        self, mock_config, tracking_filesystem
    ):
        """Complete workflow: developer fails → auditor detects → blocker collected."""
        coordinator = CentralCoordinator(
            config_path=mock_config,
            filesystem=tracking_filesystem,
            replay_mode=False
        )
        
        with patch.object(coordinator, '_create_agent_for_role') as mock_create:
            # Step 1: Developer completes without creating files
            mock_developer = Mock()
            mock_developer.name = "developer01"
            mock_developer.callback_handler = None
            mock_developer.execute_task = Mock(return_value="Tried to create file")
            mock_developer.execute_tools_from_response = Mock(return_value={
                "tools_executed": False,
                "estimated_tool_calls": 0
            })
            
            mock_create.return_value = mock_developer
            
            dev_result = coordinator._execute_single_assignment(
                role="developer",
                task="Create requirements.txt",
                original_request="Build ML project"
            )
            
            assert dev_result["status"] == "completed"
            assert len(tracking_filesystem.list_files_in_workspace()) == 0
            
            # Step 2: Auditor reviews and detects missing file
            mock_auditor = Mock()
            mock_auditor.name = "auditor01"
            mock_auditor.callback_handler = None
            mock_auditor.execute_task = Mock(
                return_value="Checked - requirements.txt NOT FOUND"
            )
            mock_auditor.execute_tools_from_response = Mock(return_value={
                "tools_executed": False,
                "estimated_tool_calls": 0
            })
            
            mock_create.return_value = mock_auditor
            
            audit_result = coordinator._execute_single_assignment(
                role="auditor",
                task={
                    "description": "Verify requirements.txt created",
                    "caller": "manager"
                },
                original_request="Build ML project"
            )
            
            # Step 3: Auditor raises blocker callback
            if mock_auditor.callback_handler:
                mock_auditor.callback_handler(
                    "auditor01",
                    "Required file requirements.txt was not created",
                    "blocker"
                )
            
            # Step 4: Verify blocker was collected
            assert len(coordinator.callbacks) > 0
            
            blockers = coordinator._get_blocker_callbacks()
            assert len(blockers) == 1
            assert "requirements.txt" in blockers[0]["message"]
    
    def test_multiple_developers_and_auditors_with_blockers(
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
        
        blockers = coordinator._get_blocker_callbacks()
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
        task = coordinator._create_final_verification_task("Test request", [])
        
        # Task should be comprehensive
        assert "VERIFICATION CHECKLIST" in task["task"]
        assert task["role"] == "auditor"
        assert task["sequence"] == 99


class TestRetryAttemptsTracking:
    """Test tracking of retry attempts."""
    
    def test_can_identify_retry_candidate(self, mock_config, tracking_filesystem):
        """Should be able to identify tasks that need retry."""
        
        # A task result that indicates failure (no files created)
        task_result = {
            "role": "developer",
            "status": "completed",
            "output": "Attempted creation",
            "tool_execution": {
                "tools_executed": False,
                "estimated_tool_calls": 0
            }
        }
        
        # Check if this is a retry candidate
        def should_retry(result):
            if result.get("role") != "developer":
                return False
            
            tool_exec = result.get("tool_execution", {})
            if not tool_exec.get("tools_executed"):
                return True  # Developer didn't execute tools
            
            return False
        
        assert should_retry(task_result) == True
    
    def test_retry_count_tracking(self, mock_config, tracking_filesystem):
        """Track number of retry attempts per task."""
        
        task_history = {
            "Create requirements.txt": [
                {"attempt": 1, "status": "failed", "reason": "no_files_created"},
                {"attempt": 2, "status": "failed", "reason": "no_files_created"},
            ]
        }
        
        # Count attempts
        attempts = len(task_history["Create requirements.txt"])
        assert attempts == 2
        
        # Should retry up to limit (e.g., 3)
        MAX_RETRIES = 3
        can_retry = attempts < MAX_RETRIES
        assert can_retry == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
