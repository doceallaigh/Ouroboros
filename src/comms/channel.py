"""
Communications module for agent interaction.

Responsibilities:
- Communication with agents and external APIs
- Input/output sanitization and validation
- Error handling and retry logic
- Message formatting and parsing
"""

from abc import ABC, abstractmethod
import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, Optional, Protocol, runtime_checkable
from httpx import AsyncClient, Response as HTTPXResponse

from comms.resilience import ConnectionPool, RateLimiter, CircuitBreaker
from comms.observability import CorrelationContext, MessageMetrics

logger = logging.getLogger(__name__)


@runtime_checkable
class OutputPostProcessingStrategy(Protocol):
    """Protocol for post-processing response content.
    
    Allows injection of application-specific transformations
    without coupling the communication layer to business logic.
    
    Implementations:
    - DefaultOutputSanitizationStrategy: Built-in safety sanitization
    - LLMPostProcessor (response_processing module): Application-specific LLM processing
    """
    
    def process(self, content: str) -> str:
        """Process and transform response content.
        
        Args:
            content: Raw content to process
            
        Returns:
            Processed content
        """
        ...


@runtime_checkable
class InputPreProcessingStrategy(Protocol):
    """Protocol for pre-processing input messages.
    
    Allows validation and sanitization of messages before transmission.
    
    Implementations:
    - DefaultInputSanitizationStrategy: Built-in message validation
    """
    
    def process(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and process input message.
        
        Args:
            message: Raw message dictionary
            
        Returns:
            Validated and processed message
            
        Raises:
            ValidationError: If message validation fails
        """
        ...


class CommunicationError(Exception):
    """Base exception for communication-related errors."""
    pass


class ValidationError(CommunicationError):
    """Raised when message validation fails."""
    pass


class APIError(CommunicationError):
    """Raised when API communication fails."""
    pass


class DefaultOutputSanitizationStrategy(OutputPostProcessingStrategy):
    """
    Default output sanitization strategy for communication safety.
    
    Implements: OutputPostProcessingStrategy
    
    Enforces baseline safety requirements:
    - Type validation (must be string)
    - Length truncation (prevents memory issues)
    - Null byte removal (prevents string corruption)
    - Whitespace trimming (consistent output)
    
    This is always applied by the comms layer to guarantee content safety.
    Delegates to sanitize_output() to maintain single source of truth.
    """
    
    def __init__(self, max_length: int = 50000):
        """Initialize with configurable max length.
        
        Args:
            max_length: Maximum allowed content length
        """
        self.max_length = max_length
    
    def process(self, content: str) -> str:
        """Apply sanitization to content.
        
        Args:
            content: Raw content to sanitize
            
        Returns:
            Sanitized content
            
        Raises:
            ValidationError: If content fails validation
        """
        return sanitize_output(content, max_length=self.max_length)


def sanitize_output(content: str, max_length: int = 50000) -> str:
    """
    Sanitize API output for consistency and safety.
    
    Args:
        content: Raw content from API response
        max_length: Maximum allowed content length
        
    Returns:
        Sanitized content string
        
    Raises:
        ValidationError: If content fails validation
    """
    if not isinstance(content, str):
        raise ValidationError(f"Expected string content, got {type(content)}")
    
    # Truncate if too long
    if len(content) > max_length:
        logger.warning(f"Content truncated from {len(content)} to {max_length} chars")
        content = content[:max_length]
    
    # Remove null bytes and other problematic characters
    content = content.replace('\x00', '')
    
    return content.strip()


def sanitize_input(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and sanitize input message structure.
    
    Args:
        message: Message dictionary to validate
        
    Returns:
        Validated and sanitized message
        
    Raises:
        ValidationError: If message structure is invalid
    """
    if not isinstance(message, dict):
        raise ValidationError(f"Message must be dict, got {type(message)}")
    
    if "messages" not in message:
        raise ValidationError("Message must contain 'messages' field")
    
    messages = message.get("messages", [])
    if not isinstance(messages, list) or not messages:
        raise ValidationError("'messages' must be non-empty list")
    
    # Sanitize each message in the list
    for msg in messages:
        if not isinstance(msg, dict):
            raise ValidationError("Each message must be a dict")
        if "role" not in msg or "content" not in msg:
            raise ValidationError("Each message must have 'role' and 'content'")
        # Sanitize content
        msg["content"] = sanitize_output(msg["content"], max_length=10000)
    
    return message


class DefaultInputSanitizationStrategy(InputPreProcessingStrategy):
    """
    Default input sanitization strategy for message validation.
    
    Implements: InputPreProcessingStrategy
    
    Enforces message structure requirements:
    - Valid dictionary with 'messages' field
    - Non-empty list of messages
    - Each message has 'role' and 'content'
    - Content sanitization applied to each message
    
    This is the standard pre-processing applied before sending messages.
    Delegates to sanitize_input() to maintain single source of truth.
    """
    
    def process(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and sanitize input message.
        
        Args:
            message: Raw message dictionary
            
        Returns:
            Validated and sanitized message
            
        Raises:
            ValidationError: If message validation fails
        """
        return sanitize_input(message)


def extract_content_from_response(
    response: HTTPXResponse,
    post_processor: Optional[OutputPostProcessingStrategy] = None
) -> str:
    """
    Extract content from various API response formats.
    
    Applies a composition of strategies:
    1. Application-specific post-processing (if provided)
    2. Default sanitization (always applied for safety)
    
    Args:
        response: HTTPXResponse object from API
        post_processor: Optional strategy for post-processing content
        
    Returns:
        Extracted and sanitized content string
        
    Raises:
        APIError: If response format is invalid
    """
    if response.status_code != 200:
        raise APIError(f"API returned status {response.status_code}")
    
    try:
        # Try standard OpenAI-style response structure
        result = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError):
        # Fallback to raw body
        try:
            result = response.text
        except Exception:
            result = response.content.decode(errors="replace")
    
    # Apply post-processing if strategy provided
    if post_processor:
        result = post_processor.process(result)
    
    # Always apply default sanitization for safety
    default_sanitizer = DefaultOutputSanitizationStrategy()
    return default_sanitizer.process(result)


class Channel(ABC):
    """Abstract base class for communication channels."""
    
    def __init__(self, config: Dict[str, str]):
        """Initialize channel with configuration."""
        self.config = config
        self.agent_name = config.get("name", "unknown")
    
    @abstractmethod
    def send_message(self, message: Dict[str, Any]) -> None:
        """
        Send a message through this channel.
        
        Args:
            message: Message payload to send
            
        Raises:
            CommunicationError: If send fails
        """
        pass
    
    @abstractmethod
    async def receive_message(self) -> HTTPXResponse:
        """
        Receive a message response through this channel.
        
        Returns:
            HTTPXResponse object
            
        Raises:
            CommunicationError: If receive fails
        """
        pass


class APIChannel(Channel):
    """Channel for live API communication."""
    
    def __init__(
        self,
        config: Dict[str, str],
        connection_pool: Optional[ConnectionPool] = None,
        rate_limiter: Optional[RateLimiter] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        metrics: Optional[MessageMetrics] = None,
    ):
        super().__init__(config)
        self.pending_replies = []
        self.timeout = config.get("timeout", 120)
        # Use provided pool or create default
        self.connection_pool = connection_pool or ConnectionPool(
            timeout_seconds=float(self.timeout)
        )
        # Use provided rate limiter or create default (10 req/sec)
        self.rate_limiter = rate_limiter or RateLimiter(requests_per_second=10.0)
        # Use provided circuit breaker or create default
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        # Use provided metrics or create default
        self.metrics = metrics or MessageMetrics()
        logger.debug(
            f"Initialized APIChannel for {self.agent_name} with connection pool, "
            f"rate limiter, circuit breaker, and metrics"
        )
    
    def send_message(self, message: Dict[str, Any]) -> int:
        """Queue message for sending and return ticks identifier."""
        try:
            input_sanitizer = DefaultInputSanitizationStrategy()
            validated_msg = input_sanitizer.process(message)
            ticks = int(time.time() * 1000)
            # store tuple of (payload, ticks)
            self.pending_replies.append((validated_msg, ticks))
            logger.debug(f"Queued message for {self.agent_name} with ticks={ticks}")
            return ticks
        except ValidationError as e:
            raise CommunicationError(f"Invalid message: {e}")
    
    async def receive_message(self) -> HTTPXResponse:
        """Send queued message and receive response. Stores `last_ticks` attribute on the channel."""
        if not self.pending_replies:
            raise APIError("No pending messages to send")

        # Create correlation ID for request tracing
        correlation_id = CorrelationContext.new()

        # Check circuit breaker before attempting request
        if self.circuit_breaker.is_open():
            error_msg = (
                f"Circuit breaker is open - refusing requests to "
                f"prevent cascading failures"
            )
            logger.warning(f"[{correlation_id}] {error_msg}")
            self.metrics.record_error("CircuitBreakerOpen")
            raise APIError(error_msg)

        payload, ticks = self.pending_replies.pop(0)
        endpoint = self.config.get("endpoint", "http://localhost:12345/v1/chat/completions")

        # Apply rate limiting before sending
        await self.rate_limiter.acquire()
        
        client = await self.connection_pool.get_client()
        start_time = time.time()
        try:
            logger.debug(f"[{correlation_id}] Sending request to {endpoint} (ticks={ticks})")
            response = await client.post(
                url=endpoint,
                json=payload,
                timeout=self.timeout,
            )
            # store ticks for caller to retrieve if needed
            self.last_ticks = ticks
            
            # Record metrics
            duration = time.time() - start_time
            self.metrics.record_request(duration, response.status_code)
            
            logger.debug(
                f"[{correlation_id}] Received response with status {response.status_code} "
                f"(ticks={ticks}, duration={duration:.3f}s)"
            )
            
            # Record success in circuit breaker
            self.circuit_breaker.record_success()
            return response
        except asyncio.TimeoutError:
            duration = time.time() - start_time
            self.metrics.record_error("TimeoutError")
            self.circuit_breaker.record_failure()
            logger.error(
                f"[{correlation_id}] API request timed out after {self.timeout}s "
                f"(duration={duration:.3f}s)"
            )
            raise APIError(f"API request timed out after {self.timeout}s")
        except Exception as e:
            duration = time.time() - start_time
            error_type = type(e).__name__
            self.metrics.record_error(error_type)
            self.circuit_breaker.record_failure()
            logger.error(
                f"[{correlation_id}] API request failed: {str(e)} "
                f"(duration={duration:.3f}s)"
            )
            raise APIError(f"API request failed: {str(e)}")
        finally:
            # Clear correlation context after request completes
            CorrelationContext.clear()



class ReplayChannel(Channel):
    """Channel for replay mode - retrieves previously recorded responses."""
    
    def __init__(self, config: Dict[str, str], replay_data_loader):
        """
        Initialize replay channel.
        
        Args:
            config: Agent configuration
            replay_data_loader: Callable that retrieves recorded output
        """
        super().__init__(config)
        self.replay_data_loader = replay_data_loader
        # keep pending_replies for ticks tracking similar to APIChannel
        self.pending_replies = []
    
    def send_message(self, message: Dict[str, Any]) -> int:
        """Register a send in replay mode and return ticks."""
        input_sanitizer = DefaultInputSanitizationStrategy()
        validated_msg = input_sanitizer.process(message)
        ticks = int(time.time() * 1000)
        self.pending_replies.append((validated_msg, ticks))
        logger.debug(f"Replay mode - registered send for {self.agent_name} with ticks={ticks}")
        return ticks
    
    async def receive_message(self) -> HTTPXResponse:
        """Retrieve recorded response. Stores `last_ticks` on the channel if available."""
        try:
            raw = self.replay_data_loader(self.agent_name) or ""
            raw = sanitize_output(raw)
            resp = HTTPXResponse(
                status_code=200,
                headers={"Content-Type": "application/json"},
                content=raw.encode("utf-8") if isinstance(raw, str) else raw,
            )
            # Pop ticks if available
            ticks = None
            if self.pending_replies:
                _, ticks = self.pending_replies.pop(0)
            self.last_ticks = ticks
            logger.debug(f"Loaded replay data for {self.agent_name} (ticks={ticks})")
            return resp
        except Exception as e:
            raise APIError(f"Failed to load replay data: {e}")


class ChannelFactory:
    """Factory for creating appropriate communication channels."""
    
    def __init__(
        self,
        replay_mode: bool,
        replay_data_loader=None,
        connection_pool: Optional[ConnectionPool] = None,
        rate_limiter: Optional[RateLimiter] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        metrics: Optional[MessageMetrics] = None,
    ):
        """
        Initialize factory.
        
        Args:
            replay_mode: Whether to use replay mode
            replay_data_loader: Callable for loading replay data
            connection_pool: Optional connection pool for API channels
            rate_limiter: Optional rate limiter for API channels
            circuit_breaker: Optional circuit breaker for API channels
            metrics: Optional metrics collector for API channels
        """
        self.replay_mode = replay_mode
        self.replay_data_loader = replay_data_loader
        self.connection_pool = connection_pool or ConnectionPool()
        self.rate_limiter = rate_limiter or RateLimiter()
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.metrics = metrics or MessageMetrics()
    
    def create_channel(self, agent_config: Dict[str, str]) -> Channel:
        """
        Create appropriate channel for agent.
        
        Args:
            agent_config: Agent configuration dict
            
        Returns:
            Channel instance
        """
        if self.replay_mode:
            if not self.replay_data_loader:
                raise CommunicationError("Replay mode requires data loader")
            return ReplayChannel(agent_config, self.replay_data_loader)
        else:
            return APIChannel(
                agent_config,
                self.connection_pool,
                self.rate_limiter,
                self.circuit_breaker,
                self.metrics,
            )

