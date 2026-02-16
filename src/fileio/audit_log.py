"""
Audit and edit log management for tracking file changes and audits.

This module provides functionality to track when files are edited/deleted and
when they are audited. A task is complete only when all edited files have been
audited with a timestamp later than their edit timestamp.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set, Optional

logger = logging.getLogger(__name__)


class AuditLogManager:
    """
    Manages edit_log and audit_log for tracking file changes and audits.
    
    The edit_log records all files that are edited, deleted, or otherwise changed.
    The audit_log records all files that have been audited.
    A task is complete when all files in edit_log also appear in audit_log
    with a later timestamp.
    """
    
    def __init__(self, working_dir: str = "."):
        """
        Initialize the audit log manager.
        
        Args:
            working_dir: Working directory for log files
        """
        self.working_dir = Path(working_dir)
        self.edit_log_path = self.working_dir / "edit_log.json"
        self.audit_log_path = self.working_dir / "audit_log.json"
        
        # In-memory tracking: filepath -> timestamp
        self.edit_log: Dict[str, str] = {}
        self.audit_log: Dict[str, str] = {}
        
        # Load existing logs if they exist
        self._load_logs()
    
    def _load_logs(self):
        """Load existing logs from disk."""
        if self.edit_log_path.exists():
            try:
                with open(self.edit_log_path, 'r') as f:
                    self.edit_log = json.load(f)
                logger.info(f"Loaded {len(self.edit_log)} entries from edit_log")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load edit_log: {e}")
                self.edit_log = {}
        
        if self.audit_log_path.exists():
            try:
                with open(self.audit_log_path, 'r') as f:
                    self.audit_log = json.load(f)
                logger.info(f"Loaded {len(self.audit_log)} entries from audit_log")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load audit_log: {e}")
                self.audit_log = {}
    
    def _save_edit_log(self):
        """Save edit_log to disk."""
        try:
            with open(self.edit_log_path, 'w') as f:
                json.dump(self.edit_log, f, indent=2)
            logger.debug(f"Saved edit_log with {len(self.edit_log)} entries")
        except IOError as e:
            logger.error(f"Failed to save edit_log: {e}")
    
    def _save_audit_log(self):
        """Save audit_log to disk."""
        try:
            with open(self.audit_log_path, 'w') as f:
                json.dump(self.audit_log, f, indent=2)
            logger.debug(f"Saved audit_log with {len(self.audit_log)} entries")
        except IOError as e:
            logger.error(f"Failed to save audit_log: {e}")
    
    def record_edit(self, file_path: str, timestamp: Optional[str] = None):
        """
        Record that a file was edited, deleted, or otherwise changed.
        
        Args:
            file_path: Path to the file that was edited
            timestamp: ISO 8601 timestamp (defaults to current time)
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()
        
        self.edit_log[file_path] = timestamp
        self._save_edit_log()
        logger.info(f"Recorded edit for {file_path} at {timestamp}")
    
    def record_audit(self, file_paths: List[str], timestamp: Optional[str] = None):
        """
        Record that files have been audited.
        
        Args:
            file_paths: List of file paths that were audited
            timestamp: ISO 8601 timestamp (defaults to current time)
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()
        
        for file_path in file_paths:
            self.audit_log[file_path] = timestamp
            logger.info(f"Recorded audit for {file_path} at {timestamp}")
        
        self._save_audit_log()
    
    def is_task_complete(self) -> bool:
        """
        Check if the task is complete.
        
        A task is complete when all files in edit_log also appear in audit_log
        with a timestamp later than the edit timestamp.
        
        Returns:
            True if all edited files have been audited with later timestamps
        """
        if not self.edit_log:
            # No files were edited, task is complete
            return True
        
        for file_path, edit_time in self.edit_log.items():
            if file_path not in self.audit_log:
                logger.debug(f"File {file_path} not audited yet")
                return False
            
            audit_time = self.audit_log[file_path]
            if audit_time <= edit_time:
                logger.debug(f"File {file_path} audit time ({audit_time}) not later than edit time ({edit_time})")
                return False
        
        logger.info("All edited files have been audited with later timestamps")
        return True
    
    def get_unaudited_files(self) -> List[str]:
        """
        Get list of files that have been edited but not audited (or not audited with later timestamp).
        
        Returns:
            List of file paths that need auditing
        """
        unaudited = []
        for file_path, edit_time in self.edit_log.items():
            if file_path not in self.audit_log:
                unaudited.append(file_path)
            elif self.audit_log[file_path] <= edit_time:
                unaudited.append(file_path)
        
        return unaudited
    
    def get_status(self) -> Dict:
        """
        Get the current status of edits and audits.
        
        Returns:
            Dictionary with status information
        """
        unaudited = self.get_unaudited_files()
        return {
            "edit_log": self.edit_log.copy(),
            "audit_log": self.audit_log.copy(),
            "total_edits": len(self.edit_log),
            "total_audits": len(self.audit_log),
            "unaudited_files": unaudited,
            "task_complete": self.is_task_complete(),
        }
