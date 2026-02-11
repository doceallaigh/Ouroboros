"""
Agentic loop execution for agents.

Allows agents to iteratively call tools and see results until task completion.
"""

import json
import logging
from typing import Dict, Any, List

from comms import APIError, extract_content_from_response, extract_full_response
from main.agent.executor import run_async, _convert_tool_calls_to_text
from main.agent.tool_definitions import get_tools_for_role

logger = logging.getLogger(__name__)


def execute_with_agentic_loop(agent, task: Dict[str, Any], working_dir: str = ".", max_iterations: int = 15) -> Dict[str, Any]:
    """
    Execute a task with an agentic loop: agent can make tool calls, see results, and iterate.
    
    The loop continues until:
    - Agent calls confirm_task_complete()
    - Agent stops making tool calls
    - Max iterations reached
    
    Args:
        agent: Agent instance
        task: Task dict with 'user_prompt'
        working_dir: Working directory for tool operations
        max_iterations: Maximum number of agent-tool iterations (default: 15)
        
    Returns:
        Dict with final response, tool results, and iteration count
    """
    from main.agent.tool_runner import execute_tools_from_response
    
    logger.info(f"Agent {agent.name} starting agentic loop (max_iterations={max_iterations})")
    
    # Initialize conversation history
    conversation_history = [
        {
            "role": "system",
            "content": agent.config.get("system_prompt", "")
        },
        {
            "role": "user",
            "content": task.get("user_prompt", "")
        }
    ]
    
    all_tool_results = []
    iteration_count = 0
    task_complete = False
    
    for iteration in range(max_iterations):
        iteration_count = iteration + 1
        logger.debug(f"Agent {agent.name} iteration {iteration_count}/{max_iterations}")
        
        # Execute task with current conversation history
        response_bundle = _execute_with_conversation_history(agent, conversation_history)
        response = response_bundle.get("response", "")
        message = response_bundle.get("message")
        
        # Add assistant response to history
        conversation_history.append({
            "role": "assistant",
            "content": response
        })
        
        # Execute tools from response
        tool_results = execute_tools_from_response(
            agent,
            response,
            working_dir=working_dir,
            message=message
        )
        all_tool_results.append(tool_results)
        
        # Check if tools were executed
        if not tool_results.get("tools_executed"):
            logger.info(f"Agent {agent.name} made no tool calls, ending loop")
            break
        
        # Check for task completion signal
        if _check_task_completion(tool_results):
            logger.info(f"Agent {agent.name} signaled task completion")
            task_complete = True
            break
        
        # Format tool results and add to conversation as user message
        tool_summary = _format_tool_results(tool_results)
        conversation_history.append({
            "role": "user",
            "content": f"Tool execution results:\n\n{tool_summary}\n\nContinue working or call confirm_task_complete() when done."
        })
    
    # Check if we hit max iterations
    if iteration_count >= max_iterations and not task_complete:
        logger.warning(f"Agent {agent.name} reached max iterations ({max_iterations}) without completing")
    
    logger.info(f"Agent {agent.name} agentic loop complete: {iteration_count} iterations")
    
    return {
        "final_response": response,
        "conversation_history": conversation_history,
        "tool_results": all_tool_results,
        "iteration_count": iteration_count,
        "task_complete": task_complete,
    }


def _execute_with_conversation_history(agent, conversation_history: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Execute agent with full conversation history (maintains context across iterations).
    
    Args:
        agent: Agent instance
        conversation_history: List of message dicts with 'role' and 'content'
        
    Returns:
        Dict with 'response' string and raw 'message' dict
    """
    import asyncio
    import time
    from main.exceptions import OrganizationError
    
    base_timeout = agent.config.get("timeout", 120)
    
    # Parse model_endpoints configuration
    model_endpoints = agent.config.get("model_endpoints", [])
    if not model_endpoints:
        model_endpoints = [{"model": "qwen/qwen2-7b", "endpoint": "http://localhost:12345/v1/chat/completions"}]
    
    backoff_delay = 1.0
    
    for attempt in range(agent.MAX_RETRIES):
        try:
            current_timeout = base_timeout * (agent.INITIAL_TIMEOUT_MULTIPLIER ** attempt)
            
            pair_index = min(attempt, len(model_endpoints) - 1)
            selected_pair = model_endpoints[pair_index]
            selected_model = selected_pair["model"]
            selected_endpoint = selected_pair["endpoint"]
            
            # Build payload with full conversation history
            payload = {
                "messages": conversation_history,
                "model": selected_model,
                "temperature": float(agent.config.get("temperature", 0.7)),
                "max_tokens": int(agent.config.get("max_tokens", -1)),
            }

            # Add tool definitions if allowed
            allowed_tools = agent.config.get("allowed_tools", [])
            if allowed_tools:
                tools = get_tools_for_role(allowed_tools)
                if tools:
                    payload["tools"] = tools
                    payload["tool_choice"] = "auto"
            
            agent.channel.config["endpoint"] = selected_endpoint
            
            ticks = agent.channel.send_message(payload)

            # Record query file for this iteration
            query_ts = __import__("datetime").datetime.now().isoformat()
            try:
                agent.filesystem.create_query_file(agent.name, ticks, query_ts, payload)
            except Exception:
                logger.exception("Failed to create query file")
            
            resp_result = run_async(agent.channel.receive_message())
            if isinstance(resp_result, tuple):
                response, _ = resp_result
            else:
                response = resp_result
            
            # Extract full response including tool_calls if present
            message = extract_full_response(response)

            if "tool_calls" in message and message["tool_calls"]:
                result = _convert_tool_calls_to_text(message["tool_calls"], message.get("content", ""))
            else:
                if "content" in message:
                    result = message["content"]
                else:
                    result = extract_content_from_response(response, agent.post_processor)

            # Append raw and parsed response to the per-query file
            resp_ts = __import__("datetime").datetime.now().isoformat()
            try:
                raw_response_str = json.dumps(message, indent=2) if isinstance(message, dict) else str(message)
                agent.filesystem.append_response_file(
                    agent.name, ticks, resp_ts,
                    f"RAW_MESSAGE:\n{raw_response_str}\n\nPARSED_RESULT:\n{result}"
                )
            except Exception:
                logger.exception("Failed to append response to query file")

            return {
                "response": result,
                "message": message,
            }
            
        except APIError as e:
            if "timed out" in str(e).lower() and attempt < agent.MAX_RETRIES - 1:
                logger.warning(f"Agent {agent.name} timeout, retrying...")
                time.sleep(backoff_delay)
                backoff_delay *= agent.BACKOFF_MULTIPLIER
                continue
            else:
                raise OrganizationError(f"Agent {agent.name} failed: {e}")
        except Exception as e:
            raise OrganizationError(f"Agent {agent.name} failed: {e}")
    
    raise OrganizationError(f"Agent {agent.name} failed after {agent.MAX_RETRIES} retries")


def _check_task_completion(tool_results: Dict[str, Any]) -> bool:
    """
    Check if agent has signaled task completion.
    
    Args:
        tool_results: Tool execution results dict
        
    Returns:
        True if task is complete, False otherwise
    """
    # Check for task_complete flag set by execute_tools_from_response
    return tool_results.get("task_complete", False)


def _format_tool_results(tool_results: Dict[str, Any]) -> str:
    """
    Format tool execution results into a readable summary for the agent.
    
    Args:
        tool_results: Tool execution results dict
        
    Returns:
        Formatted summary string
    """
    if not tool_results.get("tools_executed"):
        return "No tools were executed."
    
    summary_parts = []
    summary_parts.append(f"Executed {tool_results.get('code_blocks_executed', 0)} code blocks successfully.")
    summary_parts.append(f"Estimated {tool_results.get('estimated_tool_calls', 0)} tool calls made.")
    
    # Add results details
    results = tool_results.get("results", [])
    if results:
        for i, result in enumerate(results, 1):
            if result.get("success"):
                summary_parts.append(f"✓ Code block {i}: Success")
            else:
                error = result.get("error", "Unknown error")
                summary_parts.append(f"✗ Code block {i}: Failed - {error}")
    
    # Add file tracking for developer role
    if tool_results.get("files_produced"):
        files = tool_results["files_produced"]
        summary_parts.append(f"\nFiles created/modified: {', '.join(files)}")
    
    return "\n".join(summary_parts)
