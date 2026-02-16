"""
Tests for event sourcing decorator.
"""

import datetime
import json
import os
import tempfile
import unittest
from unittest.mock import Mock, MagicMock

from crosscutting import event_sourced
from fileio import FileSystem


class TestEventSourcingDecorator(unittest.TestCase):
    """Test suite for event_sourced decorator."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.shared_dir = os.path.join(self.temp_dir, "shared")
        os.makedirs(self.shared_dir, exist_ok=True)
    
    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_decorator_records_function_call(self):
        """Should record function call to event log."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        
        class TestClass:
            def __init__(self):
                self.filesystem = fs
            
            @event_sourced("test_event")
            def test_method(self, arg1, arg2="default"):
                return "result"
        
        obj = TestClass()
        result = obj.test_method("value1", arg2="value2")
        
        # Verify function still works
        self.assertEqual(result, "result")
        
        # Verify event was recorded
        events = fs.get_events(event_type="test_event")
        self.assertEqual(len(events), 1)
        
        event = events[0]
        self.assertEqual(event["type"], "test_event")
        self.assertEqual(event["data"]["function"], "test_method")
        self.assertIn("parameters", event["data"])
        self.assertEqual(event["data"]["parameters"]["arg1"], "value1")
        self.assertEqual(event["data"]["parameters"]["arg2"], "value2")
    
    def test_decorator_records_timestamp(self):
        """Should record timestamp in event data."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        
        class TestClass:
            def __init__(self):
                self.filesystem = fs
            
            @event_sourced("test_event")
            def test_method(self):
                return "result"
        
        obj = TestClass()
        obj.test_method()
        
        events = fs.get_events(event_type="test_event")
        self.assertEqual(len(events), 1)
        
        event = events[0]
        # Check both outer timestamp (added by filesystem.record_event)
        self.assertIn("timestamp", event)
        self.assertIn("T", event["timestamp"])
        
        # And inner timestamp (added by decorator)
        self.assertIn("timestamp", event["data"])
        self.assertIn("T", event["data"]["timestamp"])
    
    def test_decorator_uses_function_name_as_default_event_type(self):
        """Should use function name as event type if not specified."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        
        class TestClass:
            def __init__(self):
                self.filesystem = fs
            
            @event_sourced()
            def my_function(self):
                return "result"
        
        obj = TestClass()
        obj.my_function()
        
        events = fs.get_events(event_type="my_function")
        self.assertEqual(len(events), 1)
    
    def test_decorator_records_module_name(self):
        """Should record the module where function is defined."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        
        class TestClass:
            def __init__(self):
                self.filesystem = fs
            
            @event_sourced("test_event")
            def test_method(self):
                return "result"
        
        obj = TestClass()
        obj.test_method()
        
        events = fs.get_events(event_type="test_event")
        event = events[0]
        
        self.assertIn("module", event["data"])
        self.assertEqual(event["data"]["module"], "crosscutting.test_event_sourcing")
    
    def test_decorator_handles_complex_parameters(self):
        """Should handle complex parameter types gracefully."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        
        class TestClass:
            def __init__(self):
                self.filesystem = fs
            
            @event_sourced("test_event")
            def test_method(self, obj_param, list_param, dict_param):
                return "result"
        
        obj = TestClass()
        obj.test_method(
            obj_param=TestClass(),
            list_param=[1, 2, 3],
            dict_param={"key": "value"}
        )
        
        events = fs.get_events(event_type="test_event")
        event = events[0]
        
        # Object should be summarized
        self.assertIn("TestClass", event["data"]["parameters"]["obj_param"])
        # Small collections should have actual values
        self.assertEqual(event["data"]["parameters"]["list_param"], [1, 2, 3])
        self.assertEqual(event["data"]["parameters"]["dict_param"], {"key": "value"})
    
    def test_decorator_works_without_filesystem(self):
        """Should gracefully handle objects without filesystem attribute."""
        class TestClass:
            @event_sourced("test_event")
            def test_method(self):
                return "result"
        
        obj = TestClass()
        # Should not raise an error
        result = obj.test_method()
        self.assertEqual(result, "result")
    
    def test_decorator_preserves_function_metadata(self):
        """Should preserve function name and docstring."""
        def original_function():
            """Original docstring."""
            pass
        
        decorated = event_sourced("test_event")(original_function)
        
        self.assertEqual(decorated.__name__, "original_function")
        self.assertEqual(decorated.__doc__, "Original docstring.")
    
    def test_decorator_with_include_result(self):
        """Should include result in event data when requested."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        
        class TestClass:
            def __init__(self):
                self.filesystem = fs
            
            @event_sourced("test_event", include_result=True)
            def test_method(self):
                return "my_result"
        
        obj = TestClass()
        obj.test_method()
        
        events = fs.get_events(event_type="test_event")
        event = events[0]
        
        self.assertIn("result", event["data"])
        self.assertEqual(event["data"]["result"], "my_result")
    
    def test_decorator_with_default_parameters(self):
        """Should record default parameter values."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        
        class TestClass:
            def __init__(self):
                self.filesystem = fs
            
            @event_sourced("test_event")
            def test_method(self, required, optional="default_value"):
                return "result"
        
        obj = TestClass()
        obj.test_method("required_value")
        
        events = fs.get_events(event_type="test_event")
        event = events[0]
        
        self.assertEqual(event["data"]["parameters"]["required"], "required_value")
        self.assertEqual(event["data"]["parameters"]["optional"], "default_value")
    
    def test_decorator_handles_record_event_failure(self):
        """Should handle errors in record_event gracefully."""
        mock_fs = Mock()
        mock_fs.record_event.side_effect = Exception("Recording failed")
        
        class TestClass:
            def __init__(self):
                self.filesystem = mock_fs
            
            @event_sourced("test_event")
            def test_method(self):
                return "result"
        
        obj = TestClass()
        # Should not raise, just log warning
        result = obj.test_method()
        self.assertEqual(result, "result")
    
    def test_decorator_skips_self_parameter(self):
        """Should not record 'self' in parameters."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        
        class TestClass:
            def __init__(self):
                self.filesystem = fs
            
            @event_sourced("test_event")
            def test_method(self, arg1):
                return "result"
        
        obj = TestClass()
        obj.test_method("value1")
        
        events = fs.get_events(event_type="test_event")
        event = events[0]
        
        # Should not have 'self' in parameters
        self.assertNotIn("self", event["data"]["parameters"])
        self.assertIn("arg1", event["data"]["parameters"])
    
    def test_decorator_with_class_methods(self):
        """Should work with class methods."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        
        class TestClass:
            filesystem = fs
            
            @classmethod
            @event_sourced("test_event")
            def test_classmethod(cls, arg1):
                return "result"
        
        result = TestClass.test_classmethod("value1")
        
        self.assertEqual(result, "result")
        events = fs.get_events(event_type="test_event")
        self.assertEqual(len(events), 1)
        
        # Should not have 'cls' in parameters
        event = events[0]
        self.assertNotIn("cls", event["data"]["parameters"])
        self.assertIn("arg1", event["data"]["parameters"])
    
    def test_decorator_records_exceptions(self):
        """Should record exception events when function raises."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        
        class TestClass:
            def __init__(self):
                self.filesystem = fs
            
            @event_sourced("test_event")
            def failing_method(self):
                raise ValueError("Something went wrong")
        
        obj = TestClass()
        
        # Should raise the exception
        with self.assertRaises(ValueError):
            obj.failing_method()
        
        # Should have recorded a failure event
        events = fs.get_events(event_type="test_event_failed")
        self.assertEqual(len(events), 1)
        
        event = events[0]
        self.assertEqual(event["data"]["status"], "failed")
        self.assertIn("exception", event["data"])
        self.assertEqual(event["data"]["exception"]["type"], "ValueError")
        self.assertIn("Something went wrong", event["data"]["exception"]["message"])
    
    def test_decorator_with_small_collections(self):
        """Should record actual values for small collections."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        
        class TestClass:
            def __init__(self):
                self.filesystem = fs
            
            @event_sourced("test_event")
            def test_method(self, small_list, small_dict):
                return "result"
        
        obj = TestClass()
        obj.test_method([1, 2, 3], {"key": "value"})
        
        events = fs.get_events(event_type="test_event")
        event = events[0]
        
        # Should record actual values, not summaries
        self.assertEqual(event["data"]["parameters"]["small_list"], [1, 2, 3])
        self.assertEqual(event["data"]["parameters"]["small_dict"], {"key": "value"})
    
    def test_decorator_with_large_collections(self):
        """Should summarize large collections."""
        fs = FileSystem(shared_dir=self.shared_dir, replay_mode=False)
        
        class TestClass:
            def __init__(self):
                self.filesystem = fs
            
            @event_sourced("test_event")
            def test_method(self, large_list):
                return "result"
        
        obj = TestClass()
        obj.test_method(list(range(100)))
        
        events = fs.get_events(event_type="test_event")
        event = events[0]
        
        # Should record summary, not full list
        param_value = event["data"]["parameters"]["large_list"]
        self.assertIsInstance(param_value, str)
        self.assertIn("100", param_value)


if __name__ == '__main__':
    unittest.main()
