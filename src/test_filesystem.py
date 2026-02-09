"""
Unit tests for filesystem module.

Tests file storage, retrieval, and session management.
"""

import unittest
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch

from filesystem import (
    FileSystem,
    ReadOnlyFileSystem,
    FileSystemError,
)


class TestFileSystem(unittest.TestCase):
    """Test cases for FileSystem class."""

    def setUp(self):
        """Set up test fixtures with temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.shared_dir = os.path.join(self.temp_dir, "shared_repo")
        os.makedirs(self.shared_dir, exist_ok=True)

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_initialization_new_session(self):
        """Should create new session when not in replay mode."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        self.assertIsNotNone(fs.session_id)
        self.assertTrue(os.path.exists(fs.working_dir))
        self.assertIsNotNone(fs.events_file)

    def test_session_id_format(self):
        """Session ID should be timestamp-based."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        self.assertRegex(fs.session_id, r'^\d{8}_\d{9}$')
        self.assertEqual(len(fs.session_id), 18)

    def test_working_directory_created(self):
        """Should create working directory."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        self.assertTrue(os.path.isdir(fs.working_dir))

    def test_events_file_initialized(self):
        """Should initialize events file path."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        self.assertTrue(fs.events_file.endswith("_events.jsonl"))

    def test_write_data_creates_file(self):
        """Should write data to file."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        fs.write_data("test_agent", "Test output data")
        
        file_path = os.path.join(fs.working_dir, "test_agent.txt")
        self.assertTrue(os.path.exists(file_path))
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertEqual(content, "Test output data")

    def test_write_data_overwrites(self):
        """Should overwrite existing data."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        fs.write_data("test_agent", "First data")
        fs.write_data("test_agent", "Second data")
        
        file_path = os.path.join(fs.working_dir, "test_agent.txt")
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertEqual(content, "Second data")

    def test_write_structured_data(self):
        """Should write JSON structured data."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        data = {"key": "value", "number": 42}
        fs.write_structured_data("test_agent", data)
        
        file_path = os.path.join(fs.working_dir, "test_agent_structured.json")
        self.assertTrue(os.path.exists(file_path))
        
        with open(file_path, 'r', encoding='utf-8') as f:
            loaded_data = json.load(f)
        self.assertEqual(loaded_data, data)

    def test_save_conversation_history(self):
        """Should save conversation history."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"}
        ]
        fs.save_conversation_history("test_agent", history)
        
        file_path = os.path.join(fs.working_dir, "test_agent_history.json")
        self.assertTrue(os.path.exists(file_path))
        
        with open(file_path, 'r', encoding='utf-8') as f:
            loaded_history = json.load(f)
        self.assertEqual(loaded_history, history)

    def test_get_recorded_output_found(self):
        """Should retrieve recorded output."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        fs.write_data("test_agent", "Recorded output")
        
        output = fs.get_recorded_output("test_agent")
        self.assertEqual(output, "Recorded output")

    def test_get_recorded_output_not_found(self):
        """Should return None when output not found."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        output = fs.get_recorded_output("nonexistent_agent")
        self.assertIsNone(output)

    def test_get_session_metadata(self):
        """Should return session metadata."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        metadata = fs.get_session_metadata()
        
        self.assertIn("session_id", metadata)
        self.assertIn("working_dir", metadata)
        self.assertIn("created_at", metadata)
        self.assertEqual(metadata["session_id"], fs.session_id)

    def test_utf8_encoding(self):
        """Should use UTF-8 encoding for file I/O."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        
        # Write Unicode characters
        unicode_content = "Hello 世界 مرحبا мир"
        fs.write_data("test_agent", unicode_content)
        
        output = fs.get_recorded_output("test_agent")
        self.assertEqual(output, unicode_content)


class TestReadOnlyFileSystem(unittest.TestCase):
    """Test cases for ReadOnlyFileSystem class."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.shared_dir = os.path.join(self.temp_dir, "shared_repo")
        os.makedirs(self.shared_dir, exist_ok=True)

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_initialization_replay_session(self):
        """Should load latest session in replay mode."""
        # Create a session directory
        session_dir = os.path.join(self.shared_dir, "20260207_163220333")
        os.makedirs(session_dir, exist_ok=True)
        
        # ReadOnlyFileSystem should find it
        fs = ReadOnlyFileSystem(shared_dir=self.shared_dir, replay_mode=True)
        self.assertIsNotNone(fs.session_id)
        self.assertTrue(os.path.isdir(fs.working_dir))

    def test_write_data_noop(self):
        """Should not write data in read-only mode."""
        # Create temp session for readonly fs
        session_dir = os.path.join(self.shared_dir, "20260207_000000000")
        os.makedirs(session_dir, exist_ok=True)
        
        fs = ReadOnlyFileSystem(shared_dir=self.shared_dir, replay_mode=False)
        
        # Should not raise error, just no-op
        fs.write_data("test_agent", "Should not be written")
        
        # Verify file was not created
        file_path = os.path.join(fs.working_dir, "test_agent.txt")
        self.assertFalse(os.path.exists(file_path))

    def test_write_structured_data_noop(self):
        """Should not write structured data in read-only mode."""
        session_dir = os.path.join(self.shared_dir, "20260207_000000000")
        os.makedirs(session_dir, exist_ok=True)
        
        fs = ReadOnlyFileSystem(shared_dir=self.shared_dir, replay_mode=False)
        
        # Should not raise error, just no-op
        fs.write_structured_data("test_agent", {"key": "value"})
        
        # Verify file was not created
        file_path = os.path.join(fs.working_dir, "test_agent_structured.json")
        self.assertFalse(os.path.exists(file_path))

    def test_save_conversation_history_noop(self):
        """Should not save conversation history in read-only mode."""
        session_dir = os.path.join(self.shared_dir, "20260207_000000000")
        os.makedirs(session_dir, exist_ok=True)
        
        fs = ReadOnlyFileSystem(shared_dir=self.shared_dir, replay_mode=False)
        
        # Should not raise error, just no-op
        fs.save_conversation_history("test_agent", [{"role": "user", "content": "Hello"}])
        
        # Verify file was not created
        file_path = os.path.join(fs.working_dir, "test_agent_history.json")
        self.assertFalse(os.path.exists(file_path))

    def test_get_recorded_output_read_only_mode(self):
        """Should still be able to read recorded output in read-only mode."""
        # Create session directory and write initial data
        session_id = "20260207_000000000"
        session_dir = os.path.join(self.shared_dir, session_id)
        os.makedirs(session_dir, exist_ok=True)
        
        # Write agent data in .txt format (what write_data creates)
        agent_file = os.path.join(session_dir, "test_agent.txt")
        with open(agent_file, 'w', encoding='utf-8') as f:
            f.write("Recorded output data")
        
        # Access with ReadOnlyFileSystem
        fs = ReadOnlyFileSystem(shared_dir=self.shared_dir, replay_mode=True)
        
        # Manually set working_dir to use our session
        fs.working_dir = session_dir
        
        # Should still be able to read
        output = fs.get_recorded_output("test_agent")
        self.assertEqual(output, "Recorded output data")

    def test_record_event_noop(self):
        """Should not record events in read-only mode."""
        session_dir = os.path.join(self.shared_dir, "20260207_000000000")
        os.makedirs(session_dir, exist_ok=True)
        
        fs = ReadOnlyFileSystem(shared_dir=self.shared_dir, replay_mode=False)
        
        # Should not raise error, just no-op
        fs.record_event("test_event", {"data": "value"})
        
        # Verify events file was not created
        self.assertFalse(os.path.exists(fs.events_file))


class TestEventSourcing(unittest.TestCase):
    """Test cases for event sourcing functionality."""

    def setUp(self):
        """Set up test fixtures with temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.shared_dir = os.path.join(self.temp_dir, "shared_repo")
        os.makedirs(self.shared_dir, exist_ok=True)

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_record_event_creates_jsonl_file(self):
        """Should create JSONL event log file."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        fs.record_event("test_event", {"key": "value"})
        
        self.assertTrue(os.path.exists(fs.events_file))

    def test_record_event_jsonl_format(self):
        """Should write events in JSONL format (one JSON object per line)."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        fs.record_event("event1", {"data": "first"})
        fs.record_event("event2", {"data": "second"})
        
        with open(fs.events_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        self.assertEqual(len(lines), 2)
        
        # Each line should be valid JSON
        for line in lines:
            event = json.loads(line)
            self.assertIn("timestamp", event)
            self.assertIn("type", event)
            self.assertIn("data", event)

    def test_record_event_includes_timestamp(self):
        """Should include ISO format timestamp in events."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        fs.record_event("test_event", {"data": "value"})
        
        with open(fs.events_file, 'r', encoding='utf-8') as f:
            event = json.loads(f.readline())
        
        self.assertIn("timestamp", event)
        # Verify ISO format (contains 'T')
        self.assertIn("T", event["timestamp"])

    def test_get_events_all(self):
        """Should retrieve all events."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        fs.record_event("event1", {"num": 1})
        fs.record_event("event2", {"num": 2})
        fs.record_event("event3", {"num": 3})
        
        events = fs.get_events()
        
        self.assertEqual(len(events), 3)

    def test_get_events_filtered_by_type(self):
        """Should retrieve events filtered by type."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        fs.record_event("request_decomposed", {"data": "a"})
        fs.record_event("task_started", {"data": "b"})
        fs.record_event("request_decomposed", {"data": "c"})
        
        events = fs.get_events(event_type="request_decomposed")
        
        self.assertEqual(len(events), 2)
        for event in events:
            self.assertEqual(event["type"], "request_decomposed")

    def test_get_events_nonexistent_file(self):
        """Should return empty list if events file doesn't exist."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        
        # Don't record any events, so events_file won't exist
        events = fs.get_events()
        
        self.assertEqual(events, [])

    def test_event_constants_defined(self):
        """Should have all required event type constants."""
        required_events = [
            "EVENT_REQUEST_DECOMPOSED",
            "EVENT_TASK_ASSIGNED",
            "EVENT_TASK_STARTED",
            "EVENT_TASK_COMPLETED",
            "EVENT_TASK_FAILED",
            "EVENT_ROLE_VALIDATION_FAILED",
            "EVENT_TIMEOUT_RETRY",
            "EVENT_ROLE_RETRY",
        ]
        
        for event_const in required_events:
            self.assertTrue(hasattr(FileSystem, event_const))


class TestFileSystemError(unittest.TestCase):
    """Test cases for FileSystemError exception."""

    def test_filesystem_error_inheritance(self):
        """FileSystemError should inherit from Exception."""
        error = FileSystemError("test error")
        self.assertIsInstance(error, Exception)

    def test_filesystem_error_message(self):
        """Should include meaningful error message."""
        error_msg = "Failed to initialize filesystem: Permission denied"
        error = FileSystemError(error_msg)
        self.assertEqual(str(error), error_msg)


if __name__ == "__main__":
    unittest.main()
