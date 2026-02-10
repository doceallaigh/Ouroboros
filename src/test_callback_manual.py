#!/usr/bin/env python3
"""
Manual test for callback mechanism.

Tests that:
1. Tasks with 'caller' field set callback_handler
2. Agents can call raise_callback
3. Callbacks are logged to events
"""

import sys
import os
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from main import CentralCoordinator
from filesystem import FileSystem


def test_callback_mechanism():
    """Test the callback mechanism with a simple scenario."""
    print("=" * 60)
    print("CALLBACK MECHANISM TEST")
    print("=" * 60)
    
    # Create filesystem for test
    fs = FileSystem(replay_mode=False)
    print(f"\n✓ Created test session: {fs.session_id}")
    print(f"  Working directory: {fs.working_dir}")
    
    # Create coordinator
    coordinator = CentralCoordinator("src/roles.json", fs)
    print(f"\n✓ Created coordinator with {len(coordinator.role_instance_counts)} roles")
    
    # Create a test task with caller field
    test_task = {
        "description": "Test callback functionality",
        "caller": "manager"
    }
    
    print("\n" + "-" * 60)
    print("TEST: Executing task with caller field")
    print("-" * 60)
    
    # Execute the task (this should set callback_handler)
    try:
        result = coordinator._execute_single_assignment(
            role="developer",
            task=test_task,
            original_request="Test callback mechanism"
        )
        
        print(f"\n✓ Task executed successfully")
        print(f"  Role: {result['role']}")
        print(f"  Status: {result['status']}")
        print(f"  Output length: {len(result['output'])} chars")
        
    except Exception as e:
        print(f"\n✗ Task execution failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Check events for callback handler setup
    print("\n" + "-" * 60)
    print("EVENTS LOG")
    print("-" * 60)
    
    events_file = os.path.join(fs.working_dir, "_events.jsonl")
    if os.path.exists(events_file):
        with open(events_file, 'r') as f:
            events = [json.loads(line) for line in f]
        
        print(f"\n✓ Found {len(events)} events:")
        for i, event in enumerate(events, 1):
            print(f"  {i}. {event['event_type']}")
            if event['event_type'] == 'TASK_STARTED':
                caller = event.get('data', {}).get('caller')
                print(f"     → Caller: {caller}")
            if event['event_type'] == 'AGENT_CALLBACK':
                from_agent = event.get('data', {}).get('from')
                to_agent = event.get('data', {}).get('to')
                cb_type = event.get('data', {}).get('type')
                print(f"     → From: {from_agent}, To: {to_agent}, Type: {cb_type}")
    else:
        print("\n✗ No events file found")
        return False
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = test_callback_mechanism()
    sys.exit(0 if success else 1)
