"""
Event sourcing decorator for cross-cutting concern of recording function calls.

This module provides a decorator that automatically records function calls
to the event sourcing log, including function signature, parameters, and timestamp.
"""

import datetime
import inspect
import logging
from functools import wraps
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def event_sourced(event_type: Optional[str] = None, include_result: bool = False, record_exceptions: bool = True):
    """
    Decorator to automatically record function calls to event sourcing log.
    
    When a decorated function is called, records:
    - Function signature (name, module, and parameters)
    - Supplied parameters (args and kwargs)
    - Timestamp of the call
    - Optionally, the return value
    - Optionally, exceptions raised
    
    The decorator expects the decorated function to be a method on an object
    that has a 'filesystem' attribute with a 'record_event' method.
    
    Args:
        event_type: Optional event type string. If None, uses function name as event type.
        include_result: If True, includes the function's return value in the event data.
        record_exceptions: If True, records events even when function raises an exception.
    
    Example:
        @event_sourced("task_completed")
        def execute_task(self, task_id, options=None):
            return do_work(task_id, options)
    
    Returns:
        Decorated function that records events on invocation
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Try to extract filesystem from the first argument (self/cls)
            filesystem = None
            if args and hasattr(args[0], 'filesystem'):
                filesystem = args[0].filesystem
            
            # Get function signature details and build parameter mapping
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
            
            # Convert arguments to a serializable format
            # Skip 'self' or 'cls' parameter
            param_dict = {}
            for param_name, param_value in bound_args.arguments.items():
                if param_name not in ('self', 'cls'):
                    # Try to convert to a simple representation
                    try:
                        if hasattr(param_value, '__dict__'):
                            # For objects, just record the class name
                            param_dict[param_name] = f"<{type(param_value).__name__} instance>"
                        elif isinstance(param_value, (str, int, float, bool, type(None))):
                            param_dict[param_name] = param_value
                        elif isinstance(param_value, (list, tuple)):
                            # For small collections, record actual values; for large ones, just count
                            if len(param_value) <= 10:
                                param_dict[param_name] = list(param_value) if isinstance(param_value, tuple) else param_value
                            else:
                                param_dict[param_name] = f"<{type(param_value).__name__} with {len(param_value)} items>"
                        elif isinstance(param_value, dict):
                            # For small dicts, record actual values; for large ones, just count
                            if len(param_value) <= 10:
                                param_dict[param_name] = param_value
                            else:
                                param_dict[param_name] = f"<dict with {len(param_value)} items>"
                        else:
                            param_dict[param_name] = str(param_value)
                    except Exception:
                        param_dict[param_name] = f"<{type(param_value).__name__}>"
            
            # Prepare common event data
            event_data = {
                "function": func.__name__,
                "module": func.__module__,
                "parameters": param_dict,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            
            # Determine event type
            evt_type = event_type if event_type else func.__name__
            
            # Execute the function and handle exceptions
            exception_raised = None
            result = None
            try:
                result = func(*args, **kwargs)
            except Exception as e:
                exception_raised = e
                if record_exceptions and filesystem and hasattr(filesystem, 'record_event'):
                    # Record the exception event
                    exception_data = event_data.copy()
                    exception_data["status"] = "failed"
                    exception_data["exception"] = {
                        "type": type(e).__name__,
                        "message": str(e),
                    }
                    try:
                        filesystem.record_event(f"{evt_type}_failed", exception_data)
                    except Exception as log_error:
                        logger.warning(f"Failed to record exception event for {func.__name__}: {log_error}")
                # Re-raise the original exception
                raise
            
            # Record success event if we have a filesystem
            if filesystem and hasattr(filesystem, 'record_event'):
                # Include result if requested
                if include_result:
                    try:
                        if hasattr(result, '__dict__'):
                            event_data["result"] = f"<{type(result).__name__} instance>"
                        elif isinstance(result, (str, int, float, bool, type(None))):
                            event_data["result"] = result
                        elif isinstance(result, (list, tuple)):
                            if len(result) <= 10:
                                event_data["result"] = list(result) if isinstance(result, tuple) else result
                            else:
                                event_data["result"] = f"<{type(result).__name__} with {len(result)} items>"
                        elif isinstance(result, dict):
                            if len(result) <= 10:
                                event_data["result"] = result
                            else:
                                event_data["result"] = f"<dict with {len(result)} items>"
                        else:
                            event_data["result"] = str(result)
                    except Exception:
                        event_data["result"] = f"<{type(result).__name__}>"
                
                event_data["status"] = "success"
                
                # Record the success event
                try:
                    filesystem.record_event(evt_type, event_data)
                except Exception as e:
                    logger.warning(f"Failed to record event for {func.__name__}: {e}")
            
            return result
        
        return wrapper
    return decorator
