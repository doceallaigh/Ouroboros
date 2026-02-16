"""
Unit tests for audit_log module.

Tests the AuditLogManager class for tracking file edits and audits.
"""

import unittest
import tempfile
import shutil
import json
import os
from datetime import datetime, timezone, timedelta

from fileio.audit_log import AuditLogManager


class TestAuditLogManager(unittest.TestCase):
    """Tests for AuditLogManager."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.manager = AuditLogManager(working_dir=self.tmpdir)
    
    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.tmpdir, ignore_errors=True)
    
    def test_init_creates_empty_logs(self):
        """Should initialize with empty logs."""
        self.assertEqual(len(self.manager.edit_log), 0)
        self.assertEqual(len(self.manager.audit_log), 0)
    
    def test_record_edit_adds_to_log(self):
        """Should add file to edit_log with timestamp."""
        self.manager.record_edit("test.py")
        self.assertIn("test.py", self.manager.edit_log)
        self.assertTrue(self.manager.edit_log["test.py"])  # Has timestamp
    
    def test_record_edit_with_custom_timestamp(self):
        """Should record edit with provided timestamp."""
        timestamp = "2024-01-01T12:00:00+00:00"
        self.manager.record_edit("test.py", timestamp)
        self.assertEqual(self.manager.edit_log["test.py"], timestamp)
    
    def test_record_edit_saves_to_disk(self):
        """Should persist edit_log to disk."""
        self.manager.record_edit("test.py")
        
        # Load from disk
        edit_log_path = os.path.join(self.tmpdir, "edit_log.json")
        with open(edit_log_path, 'r') as f:
            loaded = json.load(f)
        
        self.assertIn("test.py", loaded)
    
    def test_record_audit_adds_to_log(self):
        """Should add files to audit_log with timestamp."""
        self.manager.record_audit(["test.py", "app.py"])
        self.assertIn("test.py", self.manager.audit_log)
        self.assertIn("app.py", self.manager.audit_log)
    
    def test_record_audit_with_custom_timestamp(self):
        """Should record audit with provided timestamp."""
        timestamp = "2024-01-01T13:00:00+00:00"
        self.manager.record_audit(["test.py"], timestamp)
        self.assertEqual(self.manager.audit_log["test.py"], timestamp)
    
    def test_record_audit_saves_to_disk(self):
        """Should persist audit_log to disk."""
        self.manager.record_audit(["test.py"])
        
        # Load from disk
        audit_log_path = os.path.join(self.tmpdir, "audit_log.json")
        with open(audit_log_path, 'r') as f:
            loaded = json.load(f)
        
        self.assertIn("test.py", loaded)
    
    def test_is_task_complete_with_no_edits(self):
        """Should return True when no files have been edited."""
        self.assertTrue(self.manager.is_task_complete())
    
    def test_is_task_complete_with_unaudited_files(self):
        """Should return False when edited files are not audited."""
        self.manager.record_edit("test.py")
        self.assertFalse(self.manager.is_task_complete())
    
    def test_is_task_complete_with_audited_files(self):
        """Should return True when all edited files are audited with later timestamps."""
        edit_time = "2024-01-01T12:00:00+00:00"
        audit_time = "2024-01-01T13:00:00+00:00"
        
        self.manager.record_edit("test.py", edit_time)
        self.manager.record_audit(["test.py"], audit_time)
        
        self.assertTrue(self.manager.is_task_complete())
    
    def test_is_task_complete_with_earlier_audit(self):
        """Should return False when audit timestamp is not later than edit timestamp."""
        edit_time = "2024-01-01T13:00:00+00:00"
        audit_time = "2024-01-01T12:00:00+00:00"
        
        self.manager.record_edit("test.py", edit_time)
        self.manager.record_audit(["test.py"], audit_time)
        
        self.assertFalse(self.manager.is_task_complete())
    
    def test_is_task_complete_with_same_timestamp(self):
        """Should return False when audit and edit timestamps are the same."""
        timestamp = "2024-01-01T12:00:00+00:00"
        
        self.manager.record_edit("test.py", timestamp)
        self.manager.record_audit(["test.py"], timestamp)
        
        self.assertFalse(self.manager.is_task_complete())
    
    def test_is_task_complete_with_multiple_files(self):
        """Should check all files for task completion."""
        edit_time = "2024-01-01T12:00:00+00:00"
        audit_time = "2024-01-01T13:00:00+00:00"
        
        self.manager.record_edit("test1.py", edit_time)
        self.manager.record_edit("test2.py", edit_time)
        self.manager.record_audit(["test1.py"], audit_time)
        
        # One file unaudited
        self.assertFalse(self.manager.is_task_complete())
        
        # All files audited
        self.manager.record_audit(["test2.py"], audit_time)
        self.assertTrue(self.manager.is_task_complete())
    
    def test_get_unaudited_files(self):
        """Should return list of files that need auditing."""
        edit_time = "2024-01-01T12:00:00+00:00"
        audit_time = "2024-01-01T13:00:00+00:00"
        
        self.manager.record_edit("test1.py", edit_time)
        self.manager.record_edit("test2.py", edit_time)
        self.manager.record_audit(["test1.py"], audit_time)
        
        unaudited = self.manager.get_unaudited_files()
        self.assertEqual(len(unaudited), 1)
        self.assertIn("test2.py", unaudited)
        self.assertNotIn("test1.py", unaudited)
    
    def test_get_unaudited_files_with_early_audit(self):
        """Should include files where audit timestamp is not later than edit."""
        edit_time = "2024-01-01T13:00:00+00:00"
        early_audit_time = "2024-01-01T12:00:00+00:00"
        
        self.manager.record_edit("test.py", edit_time)
        self.manager.record_audit(["test.py"], early_audit_time)
        
        unaudited = self.manager.get_unaudited_files()
        self.assertIn("test.py", unaudited)
    
    def test_get_status(self):
        """Should return comprehensive status information."""
        edit_time = "2024-01-01T12:00:00+00:00"
        audit_time = "2024-01-01T13:00:00+00:00"
        
        self.manager.record_edit("test1.py", edit_time)
        self.manager.record_edit("test2.py", edit_time)
        self.manager.record_audit(["test1.py"], audit_time)
        
        status = self.manager.get_status()
        
        self.assertEqual(status["total_edits"], 2)
        self.assertEqual(status["total_audits"], 1)
        self.assertEqual(len(status["unaudited_files"]), 1)
        self.assertFalse(status["task_complete"])
        self.assertIn("test1.py", status["edit_log"])
        self.assertIn("test1.py", status["audit_log"])
    
    def test_load_existing_logs(self):
        """Should load existing logs from disk on initialization."""
        # Create logs
        edit_time = "2024-01-01T12:00:00+00:00"
        self.manager.record_edit("test.py", edit_time)
        self.manager.record_audit(["other.py"], edit_time)
        
        # Create new manager instance
        new_manager = AuditLogManager(working_dir=self.tmpdir)
        
        # Should have loaded existing logs
        self.assertIn("test.py", new_manager.edit_log)
        self.assertIn("other.py", new_manager.audit_log)
    
    def test_multiple_edits_updates_timestamp(self):
        """Should update timestamp when file is edited multiple times."""
        early_time = "2024-01-01T12:00:00+00:00"
        later_time = "2024-01-01T13:00:00+00:00"
        
        self.manager.record_edit("test.py", early_time)
        self.assertEqual(self.manager.edit_log["test.py"], early_time)
        
        self.manager.record_edit("test.py", later_time)
        self.assertEqual(self.manager.edit_log["test.py"], later_time)


if __name__ == '__main__':
    unittest.main()
