"""
Communications package for agent interaction.

This package provides the communication layer for interacting with agents
and external APIs, including resilience features and observability.

Main Components:
- Channels: APIChannel, ReplayChannel, ChannelFactory
- Resilience: ConnectionPool, RateLimiter, CircuitBreaker, MessageBus
- Observability: CorrelationContext, MessageMetrics
- Protocols: OutputPostProcessingStrategy, InputPreProcessingStrategy
"""

from comms.channel import (
    # Channels
    Channel,
    APIChannel,
    ReplayChannel,
    ChannelFactory,
    
    # Protocols
    OutputPostProcessingStrategy,
    InputPreProcessingStrategy,
    
    # Strategies
    DefaultOutputSanitizationStrategy,
    DefaultInputSanitizationStrategy,
    
    # Exceptions
    CommunicationError,
    APIError,
    ValidationError,
    
    # Utilities
    extract_content_from_response,
    extract_full_response,
    sanitize_output,
    sanitize_input,
)

from comms.resilience import (
    ConnectionPool,
    RateLimiter,
    CircuitBreaker,
    MessageBus,
    RetryPolicy,
    ExponentialBackoffRetry,
    CircuitBreakerState,
)

from comms.observability import (
    CorrelationContext,
    MessageMetrics,
    correlation_id,
)

__all__ = [
    # Channels
    "Channel",
    "APIChannel",
    "ReplayChannel",
    "ChannelFactory",
    
    # Protocols
    "OutputPostProcessingStrategy",
    "InputPreProcessingStrategy",
    
    # Strategies
    "DefaultOutputSanitizationStrategy",
    "DefaultInputSanitizationStrategy",
    
    # Exceptions
    "CommunicationError",
    "APIError",
    "ValidationError",
    
    # Utilities
    "extract_content_from_response",
    "extract_full_response",
    "sanitize_output",
    "sanitize_input",
    
    # Resilience
    "ConnectionPool",
    "RateLimiter",
    "CircuitBreaker",
    "MessageBus",
    "RetryPolicy",
    "ExponentialBackoffRetry",
    "CircuitBreakerState",
    
    # Observability
    "CorrelationContext",
    "MessageMetrics",
    "correlation_id",
]
