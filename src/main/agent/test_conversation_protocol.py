"""
Test conversation protocol to identify why manual curl works but agentic loop loops.

This test replicates the exact scenario from manual curl testing:
1. User asks agent to read a file and report contents
2. Agent makes tool call to read_file
3. Tool responds with contents
4. Agent should acknowledge contents and stop (not re-read)
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from main.agent.agentic_loop import execute_with_agentic_loop, _execute_with_conversation_history


class TestConversationProtocol:
    """Test that conversation history is properly maintained and models respond correctly."""
    
    def test_manual_curl_scenario_single_read(self):
        """
        Replicate the successful manual curl test by directly testing
        the conversation history building logic.
        """
        from main.agent.agentic_loop import execute_with_agentic_loop
        
        # Track what messages are being sent
        captured_conversations = []
        call_count = [0]
        
        # Mock the entire _execute_with_conversation_history function
        def mock_execute_with_history(agent, conversation_history, force_text_response=False, tool_override=None):
            call_count[0] += 1
            captured_conversations.append(list(conversation_history))  # Deep copy
            
            print(f"\n=== LLM Call {call_count[0]} (tool_override={tool_override}) ===")
            print(f"Message count: {len(conversation_history)}")
            for i, msg in enumerate(conversation_history):
                role = msg.get("role") or msg.get("type")
                content_preview = str(msg.get("content", msg.get("output", "")))[:80]
                has_tool_calls = "tool_calls" in msg
                has_tool_call_id = "tool_call_id" in msg or "call_id" in msg
                print(f"  [{i}] {role}: {content_preview}... (tool_calls={has_tool_calls}, tool_call_id={has_tool_call_id})")
            
            # First call: return tool call to read_file
            if call_count[0] == 1:
                return {
                    "response": "I'll read the file",
                    "message": {
                        "role": "assistant",
                        "content": "I'll read the file test.txt",
                        "tool_calls": [{
                            "id": "call_001",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": '{"path":"test.txt"}'
                            }
                        }]
                    }
                }
            
            # Second call: tool_override removes read tools, model reports result (no tools available)
            elif call_count[0] == 2:
                has_tool_response = any(
                    msg.get("role") == "tool" or msg.get("type") == "function_call_output"
                    for msg in conversation_history
                )
                print(f"Has tool response in conversation: {has_tool_response}")
                
                return {
                    "response": "The file test.txt contains: Hello world",
                    "message": {
                        "role": "assistant",
                        "content": "The file test.txt contains: Hello world",
                        "tool_calls": []
                    }
                }
            
            # Should not reach here
            else:
                print(f"ERROR: Call {call_count[0]} - Agent is looping!")
                return {
                    "response": "Still going",
                    "message": {
                        "role": "assistant",
                        "content": "Still going",
                        "tool_calls": []
                    }
                }
        
        # Mock tool execution
        def mock_execute_tools(agent, response, **kwargs):
            message = kwargs.get("message", {})
            tool_calls = message.get("tool_calls", []) if isinstance(message, dict) else []
            
            # If no tool calls, return tools_executed=False (like real implementation)
            if not tool_calls:
                return {
                    "tools_executed": False,
                    "message": "No tool calls found in response"
                }
            
            # Otherwise return tool execution results
            return {
                "tools_executed": True,
                "tool_outputs": [{
                    "tool": "read_file",
                    "args": [],
                    "kwargs": {"path": "test.txt"},
                    "page": 1,
                    "total_pages": 1,
                    "page_lines": 500,
                    "content": "Hello world"
                }],
                "success": True
            }
        
        # Create mock agent
        agent = Mock()
        agent.name = "developer01"
        agent.config = {
            "system_prompt": "You are a developer. Use tools to complete tasks.",
            "temperature": 0.5,
            "max_tokens": -1,
            "timeout": 120,
            "allowed_tools": ["read_file"]
        }
        agent.channel = Mock()
        agent.channel.config = {"endpoint": "http://localhost:12345/v1/chat/completions"}
        
        task = {"user_prompt": "Please read the file test.txt and tell me its contents."}
        
        # Patch and execute
        with patch('main.agent.agentic_loop._execute_with_conversation_history', side_effect=mock_execute_with_history):
            with patch('main.agent.tool_runner.execute_tools_from_response', side_effect=mock_execute_tools):
                result = execute_with_agentic_loop(agent, task, working_dir=".", max_iterations=15)
        
        # Analyze results
        print(f"\n=== Test Results ===")
        print(f"Total LLM calls: {call_count[0]}")
        print(f"Iterations: {result.get('iteration_count')}")
        
        # Check second conversation (after tool execution and forced text)
        if len(captured_conversations) >= 2:
            print(f"\n=== Second Conversation Analysis ===")
            second_conv = captured_conversations[1]
            
            # Find assistant message with tool_calls
            assistant_msgs = [msg for msg in second_conv if msg.get("role") == "assistant"]
            tool_response_msgs = [msg for msg in second_conv if msg.get("role") == "tool" or msg.get("type") == "function_call_output"]
            
            print(f"Assistant messages in conversation: {len(assistant_msgs)}")
            print(f"Tool response messages in conversation: {len(tool_response_msgs)}")
            
            if tool_response_msgs:
                tool_msg = tool_response_msgs[0]
                print(f"Tool response content preview: {str(tool_msg.get('content', tool_msg.get('output', '')))[:100]}")
            else:
                print("ERROR: No tool response found in second conversation!")
        
        # With tool restriction: read(1) -> restricted/no-tools(2) -> stop = 2 calls
        assert call_count[0] == 2, f"Expected 2 LLM calls (read->report), got {call_count[0]}"
        print("\n[PASS] Test passed")
    
    
    def test_conversation_history_structure(self):
        """
        Test that conversation history maintains proper structure after tool responses.
        This test inspects the actual messages being sent to verify protocol compliance.
        """
        # Track what conversations are passed to _execute_with_conversation_history
        captured_conversations = []
        call_count = [0]
        
        def mock_execute_with_history(agent, conversation_history, force_text_response=False, tool_override=None):
            """Capture conversation history and return mock LLM responses."""
            call_count[0] += 1
            captured_conversations.append([dict(m) for m in conversation_history])  # Deep copy
            
            if call_count[0] == 1:
                # First call: return a tool call
                return {
                    "response": "Reading file",
                    "message": {
                        "role": "assistant",
                        "content": "Reading file",
                        "tool_calls": [{
                            "id": "call_001",
                            "type": "function",
                            "function": {"name": "read_file", "arguments": '{"path":"test.txt"}'}
                        }]
                    }
                }
            else:
                # Second call: should have tool response, return completion
                return {
                    "response": "File contains: Hello world",
                    "message": {
                        "role": "assistant",
                        "content": "File contains: Hello world",
                        "tool_calls": []
                    }
                }
        
        def mock_execute_tools(agent, response, **kwargs):
            message = kwargs.get("message", {})
            tool_calls = message.get("tool_calls", []) if isinstance(message, dict) else []
            if not tool_calls:
                return {"tools_executed": False, "message": "No tool calls"}
            return {
                "tools_executed": True,
                "tool_outputs": [{
                    "tool": "read_file",
                    "content": "Hello world",
                    "page": 1,
                    "total_pages": 1,
                    "page_lines": 500
                }],
                "success": True
            }
        
        agent = Mock()
        agent.name = "test_agent"
        agent.config = {
            "system_prompt": "Test system prompt",
            "temperature": 0.5,
            "max_tokens": -1,
            "timeout": 120,
            "allowed_tools": ["read_file"],
        }
        agent.channel = Mock()
        agent.channel.config = {"endpoint": "http://localhost:12345/v1/chat/completions"}
        
        task = {"user_prompt": "Read test.txt"}
        
        with patch('main.agent.agentic_loop._execute_with_conversation_history', side_effect=mock_execute_with_history):
            with patch('main.agent.tool_runner.execute_tools_from_response', side_effect=mock_execute_tools):
                result = execute_with_agentic_loop(agent, task, working_dir=".", max_iterations=15)
        
        # Should have 2 calls
        assert len(captured_conversations) >= 2, f"Expected at least 2 API calls, got {len(captured_conversations)}"
        
        # Inspect second conversation (after tool execution)
        second_conv = captured_conversations[1]
        
        print(f"\n=== Second API Call Message Structure ===")
        for i, msg in enumerate(second_conv):
            role = msg.get("role") or msg.get("type")
            has_tool_calls = "tool_calls" in msg
            has_tool_call_id = "tool_call_id" in msg or "call_id" in msg
            print(f"[{i}] role={role}, has_tool_calls={has_tool_calls}, has_tool_call_id={has_tool_call_id}")
        
        # Find assistant message with tool_calls
        assistant_with_tools = None
        tool_response = None
        
        for msg in second_conv:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                assistant_with_tools = msg
            elif msg.get("role") == "tool" or msg.get("type") == "function_call_output":
                tool_response = msg
        
        # Verify structure
        assert assistant_with_tools is not None, "Should have assistant message with tool_calls preserved"
        assert tool_response is not None, "Should have tool response message"
        
        # Verify tool_calls structure
        assert "tool_calls" in assistant_with_tools, "Assistant message should preserve tool_calls field"
        assert len(assistant_with_tools["tool_calls"]) > 0, "tool_calls should not be empty"
        
        # Verify tool response structure
        if tool_response.get("role") == "tool":
            assert "tool_call_id" in tool_response, "Tool response should have tool_call_id"
            assert "content" in tool_response, "Tool response should have content"
            tool_call_id = assistant_with_tools["tool_calls"][0]["id"]
            assert tool_response["tool_call_id"] == tool_call_id, "tool_call_id should match"
        
        print("\n[PASS] Conversation history structure is correct")

    def test_force_text_after_read_only_tools(self):
        """
        Test that after read-only tool calls, write-only tools are used
        on the next iteration (tool restriction).
        """
        captured_tool_overrides = []
        call_count = [0]
        
        def mock_execute_with_history(agent, conversation_history, force_text_response=False, tool_override=None):
            call_count[0] += 1
            captured_tool_overrides.append(tool_override)
            
            if call_count[0] == 1:
                # First call: return a read_file tool call
                return {
                    "response": "I'll read the file",
                    "message": {
                        "role": "assistant",
                        "content": "I'll read the file",
                        "tool_calls": [{
                            "id": "call_001",
                            "type": "function",
                            "function": {"name": "read_file", "arguments": '{"path":"test.txt"}'}
                        }]
                    }
                }
            elif call_count[0] == 2:
                # Second call: tool_override should restrict to write-only tools
                # Model can only call write_file, so it writes
                return {
                    "response": "Writing summary",
                    "message": {
                        "role": "assistant",
                        "content": "Writing summary file",
                        "tool_calls": [{
                            "id": "call_002",
                            "type": "function",
                            "function": {"name": "write_file", "arguments": '{"path":"summary.txt","content":"Summary: Hello world"}'}
                        }]
                    }
                }
            else:
                # Third call: task complete, no more tools
                return {
                    "response": "Done",
                    "message": {
                        "role": "assistant",
                        "content": "Task complete.",
                        "tool_calls": []
                    }
                }
        
        def mock_execute_tools(agent, response, **kwargs):
            message = kwargs.get("message", {})
            tool_calls = message.get("tool_calls", []) if isinstance(message, dict) else []
            if not tool_calls:
                return {"tools_executed": False, "message": "No tool calls"}
            
            tool_name = tool_calls[0]["function"]["name"]
            return {
                "tools_executed": True,
                "tool_outputs": [{
                    "tool": tool_name,
                    "content": "Hello world" if tool_name == "read_file" else "File written",
                    "page": 1,
                    "total_pages": 1,
                    "page_lines": 500
                }],
                "success": True
            }
        
        agent = Mock()
        agent.name = "developer01"
        agent.config = {
            "system_prompt": "You are a developer.",
            "temperature": 0.5,
            "max_tokens": -1,
            "timeout": 120,
            "allowed_tools": ["read_file", "write_file"]
        }
        agent.channel = Mock()
        agent.channel.config = {"endpoint": "http://localhost:12345/v1/chat/completions"}
        
        task = {"user_prompt": "Read test.txt and write a summary"}
        
        with patch('main.agent.agentic_loop._execute_with_conversation_history', side_effect=mock_execute_with_history):
            with patch('main.agent.tool_runner.execute_tools_from_response', side_effect=mock_execute_tools):
                result = execute_with_agentic_loop(agent, task, working_dir=".", max_iterations=15)
        
        print(f"\n=== Tool Restriction Results ===")
        print(f"Total LLM calls: {call_count[0]}")
        print(f"tool_override per call: {captured_tool_overrides}")
        
        # Verify:
        # Call 1: tool_override=None (initial call, all tools available)
        # Call 2: tool_override=['write_file'] (after read_file, restricted to write-only)
        # Call 3: tool_override=None (after write, back to all tools)
        assert captured_tool_overrides[0] is None, "First call should have no tool override"
        assert captured_tool_overrides[1] is not None, "Second call should have tool override (write-only)"
        assert "read_file" not in captured_tool_overrides[1], "Second call should not include read_file"
        assert "write_file" in captured_tool_overrides[1], "Second call should include write_file"
        
        print("\n[PASS] Tool restriction after read-only ops works correctly")


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])
