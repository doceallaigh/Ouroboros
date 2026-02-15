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

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
_DEFAULT_MODEL = "qwen/qwen2-7b"
_DEFAULT_ENDPOINT = "http://localhost:12345/v1/chat/completions"

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
        "edit_file": ["path", "diff"],
        "list_directory": ["path", "depth"],
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


# ---------------------------------------------------------------------------
# Shared utilities – used by both execute_task and agentic_loop
# ---------------------------------------------------------------------------

def parse_model_endpoints(config: dict) -> list:
    """
    Parse ``model_endpoints`` from an agent config dict.

    Supports both the current ``model_endpoints`` list-of-dicts format and
    the legacy ``model`` / ``endpoint`` string-or-list format.

    Returns:
        Non-empty list of ``{"model": ..., "endpoint": ...}`` dicts.
    """
    endpoints = config.get("model_endpoints", [])
    if endpoints:
        return endpoints

    # Legacy: separate model / endpoint keys (string or list)
    model = config.get("model", _DEFAULT_MODEL)
    endpoint = config.get("endpoint", _DEFAULT_ENDPOINT)
    if isinstance(model, str):
        model = [model]
    if isinstance(endpoint, str):
        endpoint = [endpoint]
    if not model:
        model = [_DEFAULT_MODEL]
    if not endpoint:
        endpoint = [_DEFAULT_ENDPOINT]
    endpoints = [{"model": m, "endpoint": e} for m, e in zip(model, endpoint)]

    return endpoints or [{"model": _DEFAULT_MODEL, "endpoint": _DEFAULT_ENDPOINT}]


def send_llm_request(agent, payload: dict, selected_endpoint: str) -> dict:
    """
    Execute a single LLM request cycle: send → receive → extract → record.

    This is deliberately *one attempt* – callers manage their own retry loops
    so they can attach domain-specific behaviour (event-sourcing, timeout
    recording, force-text flags, etc.).

    Raises whatever ``run_async`` / ``receive_message`` raises (typically
    ``APIError``).

    Returns:
        ``{"response": str, "message": dict}``
    """
    import datetime as _dt

    # Point the channel at the right endpoint for this attempt
    agent.channel.config["endpoint"] = selected_endpoint

    # --- send ---
    ticks = agent.channel.send_message(payload)

    # Record the outgoing query
    try:
        agent.filesystem.create_query_file(
            agent.name, ticks, _dt.datetime.now().isoformat(), payload,
        )
    except Exception:
        logger.exception("Failed to create query file")

    # --- receive ---
    resp_result = run_async(agent.channel.receive_message())
    if isinstance(resp_result, tuple):
        response, returned_ticks = resp_result
    else:
        response = resp_result
        returned_ticks = getattr(agent.channel, "last_ticks", None)
    if returned_ticks is None:
        returned_ticks = ticks

    # --- extract content / tool-calls ---
    message = extract_full_response(response)

    if message.get("tool_calls"):
        result = _convert_tool_calls_to_text(
            message["tool_calls"], message.get("content", ""),
        )
    elif "content" in message:
        result = message["content"]
    else:
        result = extract_content_from_response(response, agent.post_processor)

    # --- record the response ---
    try:
        raw = json.dumps(message, indent=2) if isinstance(message, dict) else str(message)
        agent.filesystem.append_response_file(
            agent.name, returned_ticks, _dt.datetime.now().isoformat(),
            f"RAW_MESSAGE:\n{raw}\n\nPARSED_RESULT:\n{result}",
        )
    except Exception:
        logger.exception("Failed to append response to query file")

    return {"response": result, "message": message}


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
    model_endpoints = parse_model_endpoints(agent.config)
    
    # Build the message payload (single-shot: system + user)
    payload = {
        "messages": [
            {"role": "system", "content": agent.config.get("system_prompt", "")},
            {"role": "user", "content": task.get("user_prompt", "")},
        ],
        "model": model_endpoints[0]["model"],
        "temperature": float(agent.config.get("temperature", 0.7)),
        "max_tokens": int(agent.config.get("max_tokens", -1)),
    }
    
    # Add tool definitions if this agent has allowed_tools
    allowed_tools = agent.config.get("allowed_tools", [])
    if allowed_tools:
        tools = get_tools_for_role(allowed_tools)
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
    
    backoff_delay = 1.0
    last_error = None
    
    for attempt in range(agent.MAX_RETRIES):
        try:
            current_timeout = base_timeout * (agent.INITIAL_TIMEOUT_MULTIPLIER ** attempt)
            
            # Select endpoint pair for this attempt (failover)
            pair_index = min(attempt, len(model_endpoints) - 1)
            selected_pair = model_endpoints[pair_index]
            payload["model"] = selected_pair["model"]

            logger.debug(
                f"Agent {agent.name} executing task (attempt {attempt + 1}/{agent.MAX_RETRIES}, "
                f"timeout={current_timeout}s, model={selected_pair['model']}, "
                f"endpoint={selected_pair['endpoint']})"
            )
            
            bundle = send_llm_request(agent, payload, selected_pair["endpoint"])
            
            logger.info(f"Agent {agent.name} completed task")
            return bundle["response"]
            
        except APIError as e:
            if "timed out" in str(e).lower():
                last_error = e
                if attempt < agent.MAX_RETRIES - 1:
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
                error_msg = f"Agent {agent.name} task execution failed: {str(e)}"
                logger.error(error_msg)
                raise OrganizationError(error_msg)
        
        except Exception as e:
            error_msg = f"Agent {agent.name} task execution failed: {str(e)}"
            logger.error(error_msg)
            raise OrganizationError(error_msg)
    
    error_msg = f"Agent {agent.name} task execution failed after {agent.MAX_RETRIES} retries: {str(last_error)}"
    logger.error(error_msg)
    raise OrganizationError(error_msg)
