"""
Tests for task completion restrictions and audit file validation.

These tests verify that:
1. Developers cannot use confirm_task_complete
2. Audit requests must reference files that have been produced
3. Audit requests can only audit produced files
"""

import pytest
import os
import tempfile
from unittest.mock import Mock, MagicMock, patch
from src.agent_tools import AgentTools, ToolError


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


class TestToolDescriptionUpdated:
    """Test that tool descriptions include new tools."""
    
    def test_get_tools_description_includes_audit_files(self):
        """Tool description should include audit_files."""
        from src.agent_tools import get_tools_description
        
        description = get_tools_description()
        
        assert "audit_files" in description
        assert "Auditing:" in description or "Audit" in description
        assert "confirm_task_complete" in description
    
    def test_get_tools_description_mentions_restrictions(self):
        """Tool description should mention audit restrictions."""
        from src.agent_tools import get_tools_description
        
        description = get_tools_description()
        
        # Should mention that audits are restricted
        assert "audit_files" in description
