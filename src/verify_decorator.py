"""
Verification script for event sourcing decorator.

This script verifies that:
1. The decorator can be applied to functions
2. Events are recorded when decorated functions are called
3. The decorator captures function name, parameters, and timestamp
"""

import json
import os
import sys
import tempfile

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crosscutting import event_sourced
from fileio import FileSystem


def main():
    """Run verification tests."""
    print("=" * 60)
    print("Event Sourcing Decorator Verification")
    print("=" * 60)
    
    # Create a temporary filesystem
    temp_dir = tempfile.mkdtemp()
    shared_dir = os.path.join(temp_dir, "shared")
    os.makedirs(shared_dir, exist_ok=True)
    fs = FileSystem(shared_dir=shared_dir, replay_mode=False)
    
    print(f"\n✓ Created temporary filesystem at: {shared_dir}")
    
    # Test 1: Basic decorator application
    print("\nTest 1: Applying decorator to a function")
    
    class TestObject:
        def __init__(self):
            self.filesystem = fs
        
        @event_sourced("test_event")
        def test_function(self, param1, param2="default"):
            return f"Result: {param1}, {param2}"
    
    obj = TestObject()
    result = obj.test_function("value1", param2="value2")
    
    print(f"  Function result: {result}")
    assert result == "Result: value1, value2", "Function should return expected result"
    print("  ✓ Function executed correctly")
    
    # Test 2: Event recording
    print("\nTest 2: Verifying event was recorded")
    
    events = fs.get_events(event_type="test_event")
    assert len(events) == 1, "Should have recorded 1 event"
    print(f"  ✓ Found {len(events)} event(s)")
    
    event = events[0]
    print(f"  Event type: {event['type']}")
    print(f"  Function name: {event['data']['function']}")
    print(f"  Timestamp: {event['data']['timestamp']}")
    
    # Test 3: Parameter capture
    print("\nTest 3: Verifying parameters were captured")
    
    params = event['data']['parameters']
    print(f"  Parameters: {json.dumps(params, indent=4)}")
    
    assert 'param1' in params, "Should capture param1"
    assert 'param2' in params, "Should capture param2"
    assert params['param1'] == 'value1', "param1 should be 'value1'"
    assert params['param2'] == 'value2', "param2 should be 'value2'"
    print("  ✓ All parameters captured correctly")
    
    # Test 4: Multiple function calls
    print("\nTest 4: Testing multiple function calls")
    
    obj.test_function("call2")
    obj.test_function("call3", param2="custom")
    
    events = fs.get_events(event_type="test_event")
    assert len(events) == 3, "Should have recorded 3 events"
    print(f"  ✓ Recorded {len(events)} events total")
    
    # Test 5: Using function name as event type
    print("\nTest 5: Using function name as default event type")
    
    class TestObject2:
        def __init__(self):
            self.filesystem = fs
        
        @event_sourced()  # No event type specified
        def my_custom_function(self, x):
            return x * 2
    
    obj2 = TestObject2()
    result = obj2.my_custom_function(5)
    
    events = fs.get_events(event_type="my_custom_function")
    assert len(events) == 1, "Should record event with function name"
    assert events[0]['data']['function'] == 'my_custom_function'
    print("  ✓ Function name used as event type")
    
    # Test 6: Graceful handling when no filesystem
    print("\nTest 6: Graceful handling without filesystem")
    
    class TestObject3:
        # No filesystem attribute
        @event_sourced("no_fs_event")
        def safe_function(self):
            return "Still works"
    
    obj3 = TestObject3()
    result = obj3.safe_function()
    assert result == "Still works", "Should work without filesystem"
    print("  ✓ Function works even without filesystem")
    
    # Cleanup
    import shutil
    shutil.rmtree(temp_dir)
    
    print("\n" + "=" * 60)
    print("✓ All verification tests passed!")
    print("=" * 60)
    print("\nSummary:")
    print("  • Decorator successfully applies to functions")
    print("  • Events are recorded with function signature")
    print("  • Parameters are captured correctly")
    print("  • Timestamps are included in events")
    print("  • Multiple calls are tracked independently")
    print("  • Gracefully handles missing filesystem")
    print("\nThe event sourcing decorator is working correctly!")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n✗ Verification failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
