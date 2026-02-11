"""
Agent task executor with retry logic.

Handles task execution with timeout retry and endpoint failover.
"""

import asyncio
import logging
import time
from typing import Dict, Any

from comms import APIError, extract_content_from_response

logger = logging.getLogger(__name__)


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
            resp_result = asyncio.run(agent.channel.receive_message())
            if isinstance(resp_result, tuple):
                response, returned_ticks = resp_result
            else:
                response = resp_result
                returned_ticks = getattr(agent.channel, 'last_ticks', None)
            if returned_ticks is None:
                returned_ticks = ticks

            # Extract and store result
            result = extract_content_from_response(response, agent.post_processor)

            # Append response timestamp and content to the per-query file (only once)
            if not response_recorded:
                resp_ts = __import__("datetime").datetime.now().isoformat()
                try:
                    agent.filesystem.append_response_file(agent.name, returned_ticks, resp_ts, result)
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
