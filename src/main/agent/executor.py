"""
Agent task executor with retry logic.

Handles task execution with timeout retry and endpoint failover.
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any

from comms import APIError, extract_content_from_response, extract_full_response
from main.agent.tool_definitions import get_tools_for_role

logger = logging.getLogger(__name__)

# Persistent event loop for async operations
_event_loop: asyncio.AbstractEventLoop = None


def get_event_loop() -> asyncio.AbstractEventLoop:
    """
    Get or create a persistent event loop for the application.
    
    Python's asyncio.run() creates and closes a new loop each time,
    which causes issues on Windows. We use a persistent loop instead.
    
    Returns:
        The application's event loop
    """
    global _event_loop
    
    if _event_loop is None or _event_loop.is_closed():
        # Create new event loop (handle Windows where the default policy may be different)
        try:
            _event_loop = asyncio.get_event_loop()
            if _event_loop.is_closed():
                _event_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(_event_loop)
        except RuntimeError:
            _event_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_event_loop)
    
    return _event_loop


def run_async(coro):
    """
    Run an async coroutine using the persistent event loop.
    
    Args:
        coro: Coroutine to run
        
    Returns:
        Result from the coroutine
    """
    loop = get_event_loop()
    if loop.is_running():
        temp_loop = asyncio.new_event_loop()
        try:
            return temp_loop.run_until_complete(coro)
        finally:
            temp_loop.close()
    return loop.run_until_complete(coro)


def _convert_tool_calls_to_text(tool_calls: list, content: str = "") -> str:
    """
    Convert structured tool_calls from OpenAI API to text representation.
    
    Tool calls come back as structured JSON in the API response. This function
    converts them to a text format that looks like function calls for compatibility
    with existing parsing code.
    
    Args:
        tool_calls: List of tool call objects from API response
        content: Optional message content to include
        
    Returns:
        Text representation of the tool calls
    """
    lines = []
    
    # Include message content if present
    if content:
        lines.append(content)
        lines.append("")  # Blank line separator
    
    # Convert each tool call to function call syntax
    for tool_call in tool_calls:
        if tool_call.get("type") == "function":
            func = tool_call.get("function", {})
            func_name = func.get("name", "unknown")
            arguments_str = func.get("arguments", "{}")
            
            # Parse arguments if it's a JSON string
            if isinstance(arguments_str, str):
                try:
                    arguments = json.loads(arguments_str)
                except json.JSONDecodeError:
                    arguments = {}
            else:
                arguments = arguments_str
            
            # Format as function call
            lines.append(_format_function_call(func_name, arguments))
    
    return "\n".join(lines)


def _format_function_call(func_name: str, arguments: dict) -> str:
    """
    Format a function call in Python-like syntax.
    
    Args:
        func_name: Name of the function
        arguments: Arguments dict
        
    Returns:
        Formatted function call like: func('arg1', 'arg2', key=value)
    """
    if not arguments:
        return f"{func_name}()"
    
    args = []
    kwargs = []
    
    # Separate positional and keyword arguments
    # For known functions, we know their positional argument order
    positional_params = {
        "assign_task": ["role", "task", "sequence"],
        "assign_tasks": ["assignments"],
        "write_file": ["path", "content"],
        "read_file": ["path"],
        "append_file": ["path", "content"],
        "edit_file": ["path", "diff"],
        "list_directory": ["path"],
        "list_all_files": ["path", "extensions"],
        "search_files": ["pattern", "path"],
        "delete_file": ["path"],
        "get_file_info": ["path"],
        "clone_repo": ["repo_url", "dest_dir", "branch", "depth"],
        "checkout_branch": ["repo_dir", "branch_name", "create"],
        "run_python": ["code", "timeout", "log_path"],
        "raise_callback": ["message", "callback_type"],
        "audit_files": ["file_paths", "description", "focus_areas"],
        "search_package": ["name", "language"],
        "install_package": ["name", "version", "language"],
        "check_package_installed": ["name", "language"],
        "list_installed_packages": ["language"]
    }
    
    pos_params = positional_params.get(func_name, [])
    
    # Build positional arguments
    for param in pos_params:
        if param in arguments:
            args.append(_format_value(arguments[param]))
    
    # Build keyword arguments (for remaining or optional args)
    for key, value in arguments.items():
        if key not in pos_params:
            kwargs.append(f"{key}={_format_value(value)}")
    
    # Combine args and kwargs
    all_args = args + kwargs
    return f"{func_name}({', '.join(all_args)})"


def _format_value(value: Any) -> str:
    """
    Format a Python value as a string for display.
    
    Args:
        value: The value to format
        
    Returns:
        Formatted string representation
    """
    if isinstance(value, str):
        # Escape quotes and newlines
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        # Use triple quotes for multiline strings
        if "\n" in escaped:
            return f"'''{value}'''"
        return f"'{escaped}'"
    elif isinstance(value, bool):
        return str(value)
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, list):
        items = [_format_value(item) for item in value]
        return f"[{', '.join(items)}]"
    elif isinstance(value, dict):
        items = [f"'{k}': {_format_value(v)}" for k, v in value.items()]
        return "{" + ", ".join(items) + "}"
    else:
        return str(value)


def execute_task(agent, task: Dict[str, Any]) -> str:
    """
    Execute a task using the agent with retry logic for timeouts.
    
    Records timeout retry events for event sourcing.
    
    Args:
        agent: Agent instance
        task: Task dict with 'user_prompt' and optionally other fields
        
    Returns:
        Agent's response as string
        
    Raises:
        OrganizationError: If task execution fails after retries
    """
    from main.exceptions import OrganizationError
    
    base_timeout = agent.config.get("timeout", 120)
    
    # Parse model_endpoints configuration (supports both old and new formats)
    model_endpoints = agent.config.get("model_endpoints", [])
    if not model_endpoints:
        # Fallback to old separate model/endpoint format for backward compatibility
        model = agent.config.get("model", "qwen/qwen2-7b")
        endpoint = agent.config.get("endpoint", "http://localhost:12345/v1/chat/completions")
        if isinstance(model, str):
            model = [model]
        if isinstance(endpoint, str):
            endpoint = [endpoint]
        if not model:
            model = ["qwen/qwen2-7b"]
        if not endpoint:
            endpoint = ["http://localhost:12345/v1/chat/completions"]
        # Convert old format to model_endpoints
        model_endpoints = [{"model": m, "endpoint": e} for m, e in zip(model, endpoint)]
    
    if not model_endpoints:
        model_endpoints = [{"model": "qwen/qwen2-7b", "endpoint": "http://localhost:12345/v1/chat/completions"}]
    
    backoff_delay = 1.0
    last_error = None
    ticks = None
    response_recorded = False  # Flag to ensure we only record response once
    
    for attempt in range(agent.MAX_RETRIES):
        try:
            # Increase timeout with each retry
            current_timeout = base_timeout * (agent.INITIAL_TIMEOUT_MULTIPLIER ** attempt)
            
            # Select model/endpoint pair for this attempt (failover to next pair on retry)
            pair_index = min(attempt, len(model_endpoints) - 1)
            selected_pair = model_endpoints[pair_index]
            selected_model = selected_pair["model"]
            selected_endpoint = selected_pair["endpoint"]

            # Build the message payload
            payload = {
                "messages": [
                    {
                        "role": "system",
                        "content": agent.config.get("system_prompt", "")
                    },
                    {
                        "role": "user",
                        "content": task.get("user_prompt", "")
                    }
                ],
                "model": selected_model,
                "temperature": float(agent.config.get("temperature", 0.7)),
                "max_tokens": int(agent.config.get("max_tokens", -1)),
            }
            
            # Add tool definitions if this agent has allowed_tools
            allowed_tools = agent.config.get("allowed_tools", [])
            if allowed_tools:
                tools = get_tools_for_role(allowed_tools)
                if tools:
                    payload["tools"] = tools
                    # Use auto mode for tool choice to let the model decide
                    payload["tool_choice"] = "auto"
            
            # Update endpoint per attempt for failover
            agent.channel.config["endpoint"] = selected_endpoint

            logger.debug(
                f"Agent {agent.name} executing task (attempt {attempt + 1}/{agent.MAX_RETRIES}, "
                f"timeout={current_timeout}s, model={selected_model}, endpoint={selected_endpoint})"
            )
            
            # Send message and get ticks id for this query (generate on first attempt only)
            if ticks is None:
                ticks = agent.channel.send_message(payload)
            else:
                # On retry, send with same ticks but don't overwrite it
                agent.channel.send_message(payload)

            # Record query file with timestamp and payload (only on first attempt)
            if attempt == 0:
                query_ts = __import__("datetime").datetime.now().isoformat()
                try:
                    agent.filesystem.create_query_file(agent.name, ticks, query_ts, payload)
                except Exception:
                    logger.exception("Failed to create query file")

            # Receive response (channel may return response or set channel.last_ticks)
            resp_result = run_async(agent.channel.receive_message())
            if isinstance(resp_result, tuple):
                response, returned_ticks = resp_result
            else:
                response = resp_result
                returned_ticks = getattr(agent.channel, 'last_ticks', None)
            if returned_ticks is None:
                returned_ticks = ticks

            # Extract full response including tool_calls if present
            message = extract_full_response(response)
            
            # Check if we have structured tool calls
            if "tool_calls" in message and message["tool_calls"]:
                # Convert tool_calls to function call format for parsing
                result = _convert_tool_calls_to_text(message["tool_calls"], message.get("content", ""))
            else:
                # Fall back to extracting just the content
                if "content" in message:
                    result = message["content"]
                else:
                    result = extract_content_from_response(response, agent.post_processor)

            # Append response timestamp and content to the per-query file (only once)
            if not response_recorded:
                resp_ts = __import__("datetime").datetime.now().isoformat()
                try:
                    # Log the raw JSON message (includes tool_calls when present)
                    raw_response_str = json.dumps(message, indent=2) if isinstance(message, dict) else str(message)
                    agent.filesystem.append_response_file(
                        agent.name, returned_ticks, resp_ts, 
                        f"RAW_MESSAGE:\n{raw_response_str}\n\nPARSED_RESULT:\n{result}"
                    )
                    response_recorded = True
                except Exception:
                    logger.exception("Failed to append response to query file")

            # (Removed write_data; replay now uses per-query files in order)
            
            logger.info(f"Agent {agent.name} completed task")
            return result
            
        except APIError as e:
            # Check if it's a timeout error
            if "timed out" in str(e).lower():
                last_error = e
                if attempt < agent.MAX_RETRIES - 1:
                    # Record timeout retry event
                    agent.filesystem.record_event(
                        agent.filesystem.EVENT_TIMEOUT_RETRY,
                        {
                            "agent": agent.name,
                            "attempt": attempt + 1,
                            "timeout_seconds": base_timeout * (agent.INITIAL_TIMEOUT_MULTIPLIER ** attempt),
                            "next_timeout_seconds": base_timeout * (agent.INITIAL_TIMEOUT_MULTIPLIER ** (attempt + 1)),
                        }
                    )
                    
                    logger.warning(
                        f"Agent {agent.name} timeout (attempt {attempt + 1}/{agent.MAX_RETRIES}), "
                        f"retrying in {backoff_delay}s with increased timeout"
                    )
                    time.sleep(backoff_delay)
                    backoff_delay *= agent.BACKOFF_MULTIPLIER
                    continue
                else:
                    error_msg = f"Agent {agent.name} task execution failed after {agent.MAX_RETRIES} retries: {str(e)}"
                    logger.error(error_msg)
                    raise OrganizationError(error_msg)
            else:
                # Non-timeout API error, don't retry
                error_msg = f"Agent {agent.name} task execution failed: {str(e)}"
                logger.error(error_msg)
                raise OrganizationError(error_msg)
        
        except Exception as e:
            error_msg = f"Agent {agent.name} task execution failed: {str(e)}"
            logger.error(error_msg)
            raise OrganizationError(error_msg)
    
    # Should not reach here, but handle just in case
    error_msg = f"Agent {agent.name} task execution failed after {agent.MAX_RETRIES} retries: {str(last_error)}"
    logger.error(error_msg)
    raise OrganizationError(error_msg)
