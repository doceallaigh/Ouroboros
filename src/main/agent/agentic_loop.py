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
    recent_tool_calls = []  # Track recent tool calls to detect loops
    files_already_read = {}  # Cache: path -> content (for blocking duplicate reads)
    force_text_next = False  # Force text response after read-only tool calls
    restrict_to_write_tools = False  # After reads, only offer write/action tools
    
    # Read-only tools that don't modify state
    READ_ONLY_TOOLS = {"read_file", "list_directory", "list_all_files", "search_files", "get_file_info", "check_package_installed", "list_installed_packages", "search_package"}
    
    # Maximum context size (in chars) before trimming old messages
    MAX_CONTEXT_CHARS = 40000
    
    for iteration in range(max_iterations):
        iteration_count = iteration + 1
        logger.debug(f"Agent {agent.name} iteration {iteration_count}/{max_iterations}")
        
        # Manage context window: trim old messages if conversation is getting too large
        _trim_conversation_history(conversation_history, MAX_CONTEXT_CHARS, files_already_read)
        
        # Execute task with current conversation history
        was_forced_text = force_text_next  # Track if THIS iteration was forced text
        
        # Build tool restriction override if needed
        tool_override = None
        if restrict_to_write_tools:
            allowed_tools = agent.config.get("allowed_tools", [])
            write_only = [t for t in allowed_tools if t not in READ_ONLY_TOOLS]
            if write_only:
                tool_override = write_only
                logger.info(f"Agent {agent.name} restricted to write-only tools: {write_only}")
            restrict_to_write_tools = False
        
        response_bundle = _execute_with_conversation_history(
            agent, conversation_history, 
            force_text_response=force_text_next,
            tool_override=tool_override
        )
        force_text_next = False  # Reset after use
        response = response_bundle.get("response", "")
        message = response_bundle.get("message")
        
        # Determine if this response contains structured tool_calls
        structured_tool_calls = []
        if isinstance(message, dict):
            structured_tool_calls = message.get("tool_calls") or []
        
        # Intercept duplicate read_file calls: replace with cached content
        if structured_tool_calls:
            deduplicated_calls = []
            cached_outputs = []
            for tc in structured_tool_calls:
                if tc.get("type") == "function":
                    func = tc.get("function", {})
                    if func.get("name") == "read_file":
                        try:
                            args = json.loads(func.get("arguments", "{}"))
                        except json.JSONDecodeError:
                            args = {}
                        file_path = args.get("path", "")
                        if file_path in files_already_read:
                            logger.info(f"Agent {agent.name} attempted to re-read '{file_path}' - returning cached content")
                            cached_outputs.append({
                                "tool_call": tc,
                                "content": files_already_read[file_path],
                            })
                            continue
                deduplicated_calls.append(tc)
            
            # If ALL calls were cached duplicates, inject cached results directly
            # and skip tool execution entirely
            if not deduplicated_calls and cached_outputs:
                # Add assistant message to history
                assistant_msg = {
                    "role": "assistant",
                    "content": message.get("content") or "",
                    "tool_calls": structured_tool_calls,
                }
                conversation_history.append(assistant_msg)
                
                # Add cached tool responses
                current_endpoint = agent.channel.config.get("endpoint", "")
                use_responses_api = "/v1/responses" in current_endpoint
                
                cached_file_names = []
                for cached in cached_outputs:
                    tc = cached["tool_call"]
                    content = cached["content"]
                    line_count = len(content.splitlines())
                    content_with_meta = f"[CACHED - Already read, {line_count} lines]\n\n{content}"
                    
                    try:
                        args = json.loads(tc.get("function", {}).get("arguments", "{}"))
                    except json.JSONDecodeError:
                        args = {}
                    cached_file_names.append(args.get("path", "unknown"))
                    
                    if use_responses_api:
                        conversation_history.append({
                            "type": "function_call_output",
                            "call_id": tc.get("id", ""),
                            "output": content_with_meta,
                        })
                    else:
                        conversation_history.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "content": content_with_meta,
                        })
                
                # Add strong reminder
                file_list = "', '".join(cached_file_names)
                conversation_history.append({
                    "role": "system",
                    "content": f"WARNING: You have already read '{file_list}' in a previous iteration. The cached contents were returned above. DO NOT read these files again. You must now take ACTION: use write_file(), edit_file(), or another tool to implement your changes. Reading the same file repeatedly is not productive."
                })
                
                all_tool_results.append({
                    "tools_executed": True,
                    "tool_outputs": [{
                        "tool": "read_file",
                        "args": [],
                        "kwargs": {"path": name},
                        "page": 1,
                        "total_pages": 1,
                        "page_lines": 500,
                        "content": cached["content"],
                    } for cached, name in zip(cached_outputs, cached_file_names)],
                })
                continue  # Skip to next iteration
            
            # If some calls were deduplicated, update structured_tool_calls
            if cached_outputs:
                # We have a mix: some cached, some new
                # Update the message's tool_calls to only include new ones
                structured_tool_calls = deduplicated_calls
                if isinstance(message, dict):
                    message = dict(message)
                    message["tool_calls"] = deduplicated_calls
        
        # Add assistant response to history - preserve tool_calls for API compliance
        if structured_tool_calls:
            # OpenAI API standard: assistant message MUST include tool_calls field
            assistant_msg = {
                "role": "assistant",
                "content": message.get("content") or "",
                "tool_calls": structured_tool_calls,
            }
            conversation_history.append(assistant_msg)
        else:
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
        
        # Detect repeated identical tool calls
        tool_outputs = tool_results.get("tool_outputs", [])
        if tool_outputs:
            # Create signature of current tool calls
            current_signature = _get_tool_call_signature(tool_outputs)
            recent_tool_calls.append(current_signature)
            
            # Keep only last 3 calls
            if len(recent_tool_calls) > 3:
                recent_tool_calls.pop(0)
            
            # Check if last 3 calls are identical
            if len(recent_tool_calls) == 3 and recent_tool_calls[0] == recent_tool_calls[1] == recent_tool_calls[2]:
                error_msg = f"Agent {agent.name} is stuck in a loop: called the same tool(s) with identical arguments 3 times consecutively. Tool signature: {current_signature}"
                logger.error(error_msg)
                from main.exceptions import OrganizationError
                raise OrganizationError(error_msg)
        
        # Check for task completion signal
        if _check_task_completion(tool_results):
            logger.info(f"Agent {agent.name} signaled task completion")
            task_complete = True
            break
        
        # Inject tool results into conversation using correct message roles
        tool_outputs = tool_results.get("tool_outputs", [])
        
        if structured_tool_calls:
            # Detect endpoint format to use correct message structure
            current_endpoint = agent.channel.config.get("endpoint", "")
            use_responses_api = "/v1/responses" in current_endpoint
            
            # Track files that were read for explicit reminder and caching
            files_read = []
            
            for i, tc in enumerate(structured_tool_calls):
                # Match output by position (tool_outputs are populated in order)
                if i < len(tool_outputs):
                    output_data = tool_outputs[i]
                    content = output_data.get("content", "")
                    tool_name = output_data.get("tool", "")
                    tool_kwargs = output_data.get("kwargs", {})
                    
                    # Cache read_file results and track for reminder
                    if tool_name == "read_file":
                        file_path = tool_kwargs.get("path", "")
                        if file_path and content:
                            files_read.append(file_path)
                            files_already_read[file_path] = content
                    
                    # Cache list_directory and list_all_files results too
                    if tool_name in ("list_directory", "list_all_files"):
                        cache_key = f"__{tool_name}__{tool_kwargs}"
                        files_already_read[cache_key] = content
                    
                    # Add pagination metadata if present
                    page = output_data.get("page", 1)
                    total_pages = output_data.get("total_pages", 1)
                    page_lines = output_data.get("page_lines", 500)
                    
                    if total_pages > 1:
                        content = f"[Page {page} of {total_pages}, {page_lines} lines per page. Use page={page+1} to see next page]\n\n{content}"
                    elif page == 1 and total_pages == 1:
                        content = f"[Complete output, {len(content.splitlines())} lines]\n\n{content}"
                else:
                    content = "Success"
                
                # Use appropriate format based on endpoint
                if use_responses_api:
                    # Responses API format: type=function_call_output with call_id and output
                    conversation_history.append({
                        "type": "function_call_output",
                        "call_id": tc.get("id", ""),
                        "output": content or "Success",
                    })
                else:
                    # Chat Completions format: role=tool with tool_call_id and content
                    conversation_history.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": content or "Success",
                    })
            
            # Add explicit reminder about files already read (as system message for higher priority)
            if files_read:
                if len(files_read) == 1:
                    reminder = f"IMPORTANT: You have just received the COMPLETE contents of {files_read[0]} in the message above. DO NOT call read_file('{files_read[0]}') again. You already have all the file data. Your next action must be to ANALYZE or IMPLEMENT based on what you learned, NOT to re-read."
                else:
                    file_list = "', '".join(files_read)
                    reminder = f"IMPORTANT: You have just received the COMPLETE contents of these files in the messages above: '{file_list}'. DO NOT call read_file() for any of these files again. You already have all the data. Your next action must be to ANALYZE or IMPLEMENT based on what you learned, NOT to re-read."
                
                conversation_history.append({
                    "role": "system",
                    "content": reminder
                })
            
            # If ALL executed tools were read-only, force text response next iteration
            # AND restrict to write-only tools to prevent re-reading
            executed_tool_names = {out.get("tool", "") for out in tool_outputs}
            if executed_tool_names and executed_tool_names.issubset(READ_ONLY_TOOLS):
                restrict_to_write_tools = True
                logger.debug(f"Agent {agent.name} executed only read-only tools, restricting to write tools next iteration")
        else:
            # No structured tool_calls: use user message with formatted outputs
            tool_output_context = _format_tool_outputs_for_context(tool_results)
            if tool_output_context:
                conversation_history.append({
                    "role": "user",
                    "content": f"Tool outputs:\n\n{tool_output_context}"
                })
            # Add summary as user message for non-structured calls
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


def _execute_with_conversation_history(agent, conversation_history: List[Dict[str, str]], force_text_response: bool = False, tool_override: List[str] = None) -> Dict[str, Any]:
    """
    Execute agent with full conversation history (maintains context across iterations).
    
    Args:
        agent: Agent instance
        conversation_history: List of message dicts with 'role' and 'content'
        force_text_response: If True, set tool_choice="none" to force text-only response
        tool_override: If provided, override the allowed_tools list (e.g., write-only tools)
        
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
            allowed_tools = tool_override if tool_override else agent.config.get("allowed_tools", [])
            if allowed_tools:
                tools = get_tools_for_role(allowed_tools)
                if tools:
                    payload["tools"] = tools
                    if force_text_response:
                        # Force text-only response (no tool calls)
                        # Used after read-only operations to make the model process results
                        payload["tool_choice"] = "none"
                        logger.info(f"Agent {agent.name} forced text response (tool_choice=none)")
                    else:
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


def _trim_conversation_history(conversation_history: List[Dict[str, str]], max_chars: int, files_already_read: Dict[str, str]) -> None:
    """
    Trim conversation history to keep context within size limits.
    
    Preserves:
    - First message (system prompt) always
    - Second message (user prompt) always  
    - Recent messages (last N that fit within budget)
    
    Never splits assistant+tool_calls from corresponding tool responses.
    Adds a summary of trimmed content as a system message.
    """
    # Calculate total size
    total_size = sum(len(str(msg.get("content", msg.get("output", "")))) for msg in conversation_history)
    
    if total_size <= max_chars:
        return  # No trimming needed
    
    if len(conversation_history) <= 3:
        return  # Can't trim further
    
    logger.info(f"Context too large ({total_size} chars > {max_chars}), trimming conversation history")
    
    # Keep system prompt (index 0) and user prompt (index 1) always
    preserved_start = conversation_history[:2]
    remaining = conversation_history[2:]
    
    # Work backwards to find how many recent messages fit
    budget = max_chars - sum(len(str(msg.get("content", ""))) for msg in preserved_start)
    kept_messages = []
    i = len(remaining) - 1
    
    while i >= 0 and budget > 0:
        msg = remaining[i]
        msg_size = len(str(msg.get("content", msg.get("output", ""))))
        
        # Don't split tool responses from their assistant+tool_calls message
        if msg.get("role") == "tool" or msg.get("type") == "function_call_output":
            # Must keep the preceding assistant message too
            if i > 0 and remaining[i-1].get("role") == "assistant":
                assistant_size = len(str(remaining[i-1].get("content", "")))
                if msg_size + assistant_size <= budget:
                    kept_messages.insert(0, remaining[i])
                    kept_messages.insert(0, remaining[i-1])
                    budget -= msg_size + assistant_size
                    i -= 2
                    continue
                else:
                    break  # Can't fit the pair
            else:
                if msg_size <= budget:
                    kept_messages.insert(0, msg)
                    budget -= msg_size
        elif msg.get("role") == "assistant" and msg.get("tool_calls"):
            # Assistant with tool_calls: check if next message is a tool response
            # If so, both were already handled. If we're here, the tool response
            # was already included. Skip this to avoid orphaned tool_calls.
            if i + 1 < len(remaining) and (remaining[i+1].get("role") == "tool" or remaining[i+1].get("type") == "function_call_output"):
                # This pair would have been handled when processing the tool message
                i -= 1
                continue
            # Standalone assistant with tool_calls (shouldn't happen, but handle it)
            if msg_size <= budget:
                kept_messages.insert(0, msg)
                budget -= msg_size
        else:
            if msg_size <= budget:
                kept_messages.insert(0, msg)
                budget -= msg_size
        
        i -= 1
    
    # Build summary of what was trimmed
    trimmed_count = len(remaining) - len(kept_messages)
    if trimmed_count > 0:
        files_summary = ""
        if files_already_read:
            file_names = list(files_already_read.keys())
            files_summary = f" Files you have already read: {', '.join(file_names)}. Their contents are available in your working memory."
        
        summary_msg = {
            "role": "system",
            "content": f"[Context trimmed: {trimmed_count} earlier messages removed to stay within context limits.{files_summary} Focus on completing the task with the information you have.]"
        }
        
        # Rebuild conversation history in-place
        conversation_history.clear()
        conversation_history.extend(preserved_start)
        conversation_history.append(summary_msg)
        conversation_history.extend(kept_messages)
        
        logger.info(f"Trimmed {trimmed_count} messages, kept {len(kept_messages)} recent messages")


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


def _format_tool_outputs_for_context(tool_results: Dict[str, Any]) -> str:
    tool_outputs = tool_results.get("tool_outputs", [])
    if not tool_outputs:
        return ""

    output_parts = []
    for output in tool_outputs:
        tool_name = output.get("tool", "tool")
        page = output.get("page", 1)
        total_pages = output.get("total_pages", 1)
        page_lines = output.get("page_lines", 0)
        args = output.get("args", [])
        kwargs = output.get("kwargs", {})
        output_parts.append(
            f"--- {tool_name} page {page}/{total_pages} (lines per page: {page_lines}) ---"
        )
        if args or kwargs:
            output_parts.append(f"Args: {args}, Kwargs: {kwargs}")
        content = output.get("content", "")
        if content:
            output_parts.append(content)
        if total_pages > page:
            output_parts.append(
                f"To view next page, call {tool_name} with page={page + 1} (max page {total_pages})."
            )

    return "\n".join(output_parts)


def _get_tool_call_signature(tool_outputs: List[Dict[str, Any]]) -> str:
    """
    Create a signature string from tool outputs to detect repeated identical calls.
    
    Args:
        tool_outputs: List of tool output dictionaries
        
    Returns:
        String signature representing the tool calls
    """
    signature_parts = []
    for output in tool_outputs:
        tool_name = output.get("tool", "unknown")
        args = output.get("args", [])
        kwargs = output.get("kwargs", {})
        # Create a deterministic signature from tool name and arguments
        signature_parts.append(f"{tool_name}({args},{sorted(kwargs.items())})")
    return "|".join(signature_parts)
