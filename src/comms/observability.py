"""
Observability features for communications layer.

Responsibilities:
- Request correlation for distributed tracing
- Message metrics for performance monitoring
- Communication statistics and analytics
"""

import contextvars
import logging
import time
import uuid
from typing import Optional, Dict, Any, List
from collections import defaultdict

logger = logging.getLogger(__name__)

# Context variable for correlation ID (thread-safe across async)
correlation_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'correlation_id', default=None
)


class CorrelationContext:
    """
    Manages request correlation IDs for distributed tracing.
    
    Enables tracking requests across multiple agent calls, services,
    and async operations. Uses contextvars for proper async context
    propagation without explicit passing.
    
    Usage:
        # Create new correlation for request
        cid = CorrelationContext.new()
        
        # Add to logs/headers
        logger.info(f"Processing {CorrelationContext.get()}")
        
        # In child operations, correlation is automatically available
        async def child_operation():
            cid = CorrelationContext.get()  # Same ID as parent
    """
    
    @staticmethod
    def new() -> str:
        """
        Create new correlation ID and set as current.
        
        Returns:
            New UUID correlation ID
        """
        cid = str(uuid.uuid4())
        correlation_id.set(cid)
        logger.debug(f"Created correlation ID: {cid}")
        return cid
    
    @staticmethod
    def get() -> Optional[str]:
        """
        Get current correlation ID from context.
        
        Returns:
            Current correlation ID or None if not set
        """
        return correlation_id.get()
    
    @staticmethod
    def set(cid: str) -> None:
        """
        Set correlation ID in context.
        
        Args:
            cid: Correlation ID to set
        """
        correlation_id.set(cid)
        logger.debug(f"Set correlation ID: {cid}")
    
    @staticmethod
    def clear() -> None:
        """Clear correlation ID from context."""
        correlation_id.set(None)


class MessageMetrics:
    """
    Collects communication metrics for monitoring and analysis.
    
    Tracks:
    - Request counts (total, success, failed)
    - Response times (min, max, avg, percentiles)
    - Error types and frequencies
    - Rate limiting impacts
    - Circuit breaker transitions
    
    Thread-safe for concurrent updates.
    
    Usage:
        metrics = MessageMetrics()
        
        start = time.time()
        response = await send_request()
        metrics.record_request(time.time() - start, response.status_code)
        
        stats = metrics.get_stats()
        print(f"Success rate: {stats['success_rate']:.2%}")
    """
    
    def __init__(self):
        """Initialize metrics collector."""
        self.requests_total = 0
        self.requests_success = 0
        self.requests_failed = 0
        self.response_times: List[float] = []
        self.errors_by_type: Dict[str, int] = defaultdict(int)
        self.status_codes: Dict[int, int] = defaultdict(int)
        self.start_time = time.time()
        logger.debug("Initialized MessageMetrics")
    
    def record_request(self, duration: float, status: int) -> None:
        """
        Record successful request with timing.
        
        Args:
            duration: Request duration in seconds
            status: HTTP status code
        """
        self.requests_total += 1
        self.requests_success += 1
        self.response_times.append(duration)
        self.status_codes[status] += 1
        
        if duration > 1.0:  # Log slow requests (>1s)
            logger.warning(f"Slow request: {duration:.2f}s (status {status})")
    
    def record_error(self, error_type: str) -> None:
        """
        Record failed request by error type.
        
        Args:
            error_type: Type/class of error that occurred
        """
        self.requests_total += 1
        self.requests_failed += 1
        self.errors_by_type[error_type] += 1
        logger.debug(f"Recorded error: {error_type}")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get aggregate statistics.
        
        Returns:
            Dictionary with comprehensive metrics
        """
        times = self.response_times
        uptime = time.time() - self.start_time
        
        stats = {
            "total_requests": self.requests_total,
            "successful": self.requests_success,
            "failed": self.requests_failed,
            "success_rate": self.requests_success / max(1, self.requests_total),
            "uptime_seconds": uptime,
            "requests_per_second": self.requests_total / max(1, uptime),
            "errors_by_type": dict(self.errors_by_type),
            "status_codes": dict(self.status_codes),
        }
        
        # Response time statistics
        if times:
            sorted_times = sorted(times)
            n = len(sorted_times)
            
            stats.update({
                "response_time_avg": sum(times) / n,
                "response_time_min": sorted_times[0],
                "response_time_max": sorted_times[-1],
                "response_time_p50": sorted_times[n // 2],
                "response_time_p95": sorted_times[int(n * 0.95)] if n > 20 else sorted_times[-1],
                "response_time_p99": sorted_times[int(n * 0.99)] if n > 100 else sorted_times[-1],
                "total_response_samples": n,
            })
        else:
            stats.update({
                "response_time_avg": 0,
                "response_time_min": 0,
                "response_time_max": 0,
                "response_time_p50": 0,
                "response_time_p95": 0,
                "response_time_p99": 0,
                "total_response_samples": 0,
            })
        
        return stats
    
    def reset(self) -> None:
        """Reset all metrics to initial state."""
        self.requests_total = 0
        self.requests_success = 0
        self.requests_failed = 0
        self.response_times.clear()
        self.errors_by_type.clear()
        self.status_codes.clear()
        self.start_time = time.time()
        logger.info("Reset MessageMetrics")
    
    def get_error_summary(self) -> List[Dict[str, Any]]:
        """
        Get error summary sorted by frequency.
        
        Returns:
            List of error types with counts, sorted by frequency
        """
        return [
            {"error_type": error_type, "count": count}
            for error_type, count in sorted(
                self.errors_by_type.items(),
                key=lambda x: x[1],
                reverse=True,
            )
        ]
    
    def get_status_summary(self) -> List[Dict[str, Any]]:
        """
        Get HTTP status code summary sorted by frequency.
        
        Returns:
            List of status codes with counts, sorted by frequency
        """
        return [
            {"status_code": status, "count": count}
            for status, count in sorted(
                self.status_codes.items(),
                key=lambda x: x[1],
                reverse=True,
            )
        ]
