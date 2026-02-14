"""
Unit tests for comms.resilience module.

Tests connection pooling, retry policies, and resilience features.
"""

import asyncio
import time
import unittest
from unittest.mock import Mock, patch, AsyncMock, MagicMock

from comms.resilience import (
    ConnectionPool,
    ExponentialBackoffRetry,
    RetryPolicy,
    RateLimiter,
    CircuitBreaker,
    CircuitBreakerState,
    MessageBus,
)


class TestConnectionPool(unittest.TestCase):
    """Test cases for ConnectionPool class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.pool = ConnectionPool(
            max_connections=50,
            max_keepalive_connections=25,
            timeout_seconds=30.0,
        )
    
    def tearDown(self):
        """Clean up after tests."""
        # Note: asyncio cleanup would happen in async teardown
        pass
    
    def test_initialization(self):
        """Should initialize with provided configuration."""
        self.assertEqual(self.pool.max_connections, 50)
        self.assertEqual(self.pool.max_keepalive_connections, 25)
        self.assertEqual(self.pool.timeout_seconds, 30.0)
        self.assertFalse(self.pool._initialized)
        self.assertIsNone(self.pool.client)
    
    def test_default_values(self):
        """Should use sensible defaults when not specified."""
        pool = ConnectionPool()
        self.assertEqual(pool.max_connections, 100)
        self.assertEqual(pool.max_keepalive_connections, 50)
        self.assertEqual(pool.timeout_seconds, 120.0)
    
    @patch('comms.resilience.AsyncClient')
    def test_get_client_initialization(self, mock_async_client):
        """Should initialize client on first get_client call."""
        async def run_test():
            mock_instance = AsyncMock()
            mock_async_client.return_value = mock_instance
            
            client = await self.pool.get_client()
            
            self.assertTrue(self.pool._initialized)
            self.assertIsNotNone(self.pool.client)
            mock_async_client.assert_called_once()
        
        asyncio.run(run_test())
    
    @patch('comms.resilience.AsyncClient')
    def test_get_client_reuses_instance(self, mock_async_client):
        """Should return same client instance on subsequent calls."""
        async def run_test():
            mock_instance = AsyncMock()
            mock_async_client.return_value = mock_instance
            
            client1 = await self.pool.get_client()
            client2 = await self.pool.get_client()
            
            self.assertIs(client1, client2)
            # Should only be called once due to caching
            mock_async_client.assert_called_once()
        
        asyncio.run(run_test())
    
    @patch('comms.resilience.AsyncClient')
    def test_close(self, mock_async_client):
        """Should properly close the client."""
        async def run_test():
            mock_instance = AsyncMock()
            mock_async_client.return_value = mock_instance
            
            await self.pool.get_client()
            self.assertTrue(self.pool._initialized)
            
            await self.pool.close()
            
            self.assertFalse(self.pool._initialized)
            mock_instance.aclose.assert_called_once()
        
        asyncio.run(run_test())
    
    @patch('comms.resilience.AsyncClient')
    def test_close_without_initialization(self, mock_async_client):
        """Should handle close gracefully if never initialized."""
        async def run_test():
            # Should not raise
            await self.pool.close()
            mock_async_client.assert_not_called()
        
        asyncio.run(run_test())


class TestExponentialBackoffRetry(unittest.TestCase):
    """Test cases for ExponentialBackoffRetry class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.policy = ExponentialBackoffRetry(
            base_delay=0.1,  # Smaller for testing
            max_delay=1.0,
            max_attempts=5,
        )
    
    def test_initialization(self):
        """Should initialize with provided values."""
        self.assertEqual(self.policy.base_delay, 0.1)
        self.assertEqual(self.policy.max_delay, 1.0)
        self.assertEqual(self.policy.max_attempts, 5)
    
    def test_max_attempts_property(self):
        """Should expose max_attempts as property."""
        self.assertEqual(self.policy.max_attempts, 5)
    
    def test_should_retry_transient_error(self):
        """Should retry on transient errors."""
        exc = asyncio.TimeoutError("Connection timeout")
        self.assertTrue(self.policy.should_retry(0, exc))
        self.assertTrue(self.policy.should_retry(1, exc))
    
    def test_should_not_retry_non_transient_error(self):
        """Should not retry on non-transient errors."""
        exc = ValueError("Invalid value")
        self.assertFalse(self.policy.should_retry(0, exc))
    
    def test_should_not_retry_after_max_attempts(self):
        """Should not retry after max attempts exceeded."""
        exc = asyncio.TimeoutError("Connection timeout")
        # At max_attempts - 1, still allow one more
        self.assertFalse(self.policy.should_retry(4, exc))  # 5th attempt
    
    def test_should_retry_connection_errors(self):
        """Should retry on various connection errors."""
        errors = [
            ConnectionError("Connection failed"),
            ConnectionRefusedError("Connection refused"),
            ConnectionResetError("Connection reset"),
            TimeoutError("Timeout"),
        ]
        for exc in errors:
            self.assertTrue(self.policy.should_retry(0, exc))
    
    def test_get_delay_exponential(self):
        """Should calculate exponential delays."""
        delays = [self.policy.get_delay(i) for i in range(4)]
        # 0.1, 0.2, 0.4, 0.8 (capped at 1.0)
        self.assertAlmostEqual(delays[0], 0.1)
        self.assertAlmostEqual(delays[1], 0.2)
        self.assertAlmostEqual(delays[2], 0.4)
        self.assertAlmostEqual(delays[3], 0.8)
    
    def test_get_delay_capped_at_max(self):
        """Should cap delay at max_delay."""
        # Force large exponent to exceed max_delay
        large_delay = self.policy.get_delay(10)
        self.assertLessEqual(large_delay, self.policy.max_delay)
    
    def test_implements_retry_policy_protocol(self):
        """Should implement RetryPolicy protocol."""
        self.assertIsInstance(self.policy, RetryPolicy)
    
    def test_default_values(self):
        """Should use sensible defaults."""
        policy = ExponentialBackoffRetry()
        self.assertEqual(policy.base_delay, 1.0)
        self.assertEqual(policy.max_delay, 60.0)
        self.assertEqual(policy.max_attempts, 5)
    
    def test_realistic_retry_scenario(self):
        """Should handle realistic retry scenario."""
        policy = ExponentialBackoffRetry(base_delay=0.5, max_attempts=3)
        
        exc = asyncio.TimeoutError("Timeout")
        
        # Attempt 1: Should retry with delay
        self.assertTrue(policy.should_retry(0, exc))
        self.assertAlmostEqual(policy.get_delay(0), 0.5)
        
        # Attempt 2: Should retry with longer delay
        self.assertTrue(policy.should_retry(1, exc))
        self.assertAlmostEqual(policy.get_delay(1), 1.0)
        
        # Attempt 3: Should not retry
        self.assertFalse(policy.should_retry(2, exc))


class TestRetryPolicyProtocol(unittest.TestCase):
    """Test that implementations properly follow RetryPolicy protocol."""
    
    def test_exponential_backoff_is_retry_policy(self):
        """Should verify instance is RetryPolicy."""
        policy = ExponentialBackoffRetry()
        self.assertIsInstance(policy, RetryPolicy)


class TestRateLimiter(unittest.TestCase):
    """Test cases for RateLimiter class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.limiter = RateLimiter(requests_per_second=10.0)
    
    def test_initialization(self):
        """Should initialize with correct rate."""
        self.assertEqual(self.limiter.rate, 10.0)
        self.assertEqual(self.limiter.tokens, 10.0)
    
    def test_invalid_rate_raises_error(self):
        """Should reject non-positive rates."""
        with self.assertRaises(ValueError):
            RateLimiter(requests_per_second=0.0)
        with self.assertRaises(ValueError):
            RateLimiter(requests_per_second=-1.0)
    
    def test_available_tokens_initial(self):
        """Should start with full tokens."""
        tokens = self.limiter.available_tokens()
        self.assertEqual(tokens, 10.0)
    
    def test_available_tokens_accumulation(self):
        """Should accumulate tokens over time."""
        # Use initial tokens
        self.limiter.tokens = 0
        self.limiter.last_update = time.monotonic()
        
        # Simulate 0.1 seconds elapsed
        self.limiter.last_update -= 0.1
        tokens = self.limiter.available_tokens()
        
        # Should have accumulated 1.0 token (10.0 * 0.1 = 1.0)
        self.assertAlmostEqual(tokens, 1.0, places=1)
    
    def test_available_tokens_capped_at_rate(self):
        """Should cap tokens at rate (no burst above rate)."""
        # Simulate long elapsed time
        self.limiter.last_update -= 100.0
        tokens = self.limiter.available_tokens()
        
        # Should be capped at rate, not 1000+ tokens
        self.assertLessEqual(tokens, self.limiter.rate)
        self.assertAlmostEqual(tokens, self.limiter.rate, places=1)
    
    def test_acquire_single_token_no_wait(self):
        """Should acquire token immediately if available."""
        async def run_test():
            wait_time = await self.limiter.acquire(1)
            self.assertAlmostEqual(wait_time, 0.0, places=2)
            self.assertAlmostEqual(self.limiter.tokens, 9.0, places=1)
        
        asyncio.run(run_test())
    
    def test_acquire_multiple_tokens(self):
        """Should acquire multiple tokens."""
        async def run_test():
            await self.limiter.acquire(5)
            self.assertAlmostEqual(self.limiter.tokens, 5.0, places=1)
        
        asyncio.run(run_test())
    
    def test_acquire_zero_tokens_raises_error(self):
        """Should reject acquiring zero tokens."""
        async def run_test():
            with self.assertRaises(ValueError):
                await self.limiter.acquire(0)
        
        asyncio.run(run_test())
    
    def test_acquire_more_than_rate_raises_error(self):
        """Should reject acquiring more tokens than rate allows."""
        async def run_test():
            with self.assertRaises(ValueError):
                await self.limiter.acquire(100)
        
        asyncio.run(run_test())
    
    def test_acquire_waits_for_tokens(self):
        """Should wait when tokens exhausted."""
        async def run_test():
            limiter = RateLimiter(requests_per_second=10.0)
            
            # Use all initial tokens
            limiter.tokens = 0
            
            # Set last update to 0.05 seconds ago
            # At 10 req/s, should have 0.5 tokens available
            limiter.last_update = time.monotonic() - 0.05
            
            start = time.monotonic()
            # Try to acquire 1 token - might need to wait
            await limiter.acquire(1)
            elapsed = time.monotonic() - start
            
            # Should have taken some time (at least a few ms)
            # Because we need more tokens than available
            self.assertGreater(elapsed, 0.0)
        
        asyncio.run(run_test())
    
    def test_acquire_returns_wait_time(self):
        """Should return actual wait time."""
        async def run_test():
            limiter = RateLimiter(requests_per_second=100.0)
            
            # It should respond quickly with plenty of tokens
            wait_time = await limiter.acquire(1)
            self.assertGreaterEqual(wait_time, 0.0)
            self.assertLess(wait_time, 0.1)
        
        asyncio.run(run_test())
    
    def test_concurrent_acquire_not_exceeding_rate(self):
        """Should handle concurrent requests without exceeding rate."""
        async def run_test():
            limiter = RateLimiter(requests_per_second=5.0)
            
            # Try to acquire 5 tokens concurrently
            tasks = [limiter.acquire(1) for _ in range(5)]
            start = time.monotonic()
            await asyncio.gather(*tasks)
            elapsed = time.monotonic() - start
            
            # Should have completed in reasonable time (< 100ms)
            self.assertLess(elapsed, 0.1)
            # All tokens should be consumed
            self.assertAlmostEqual(limiter.tokens, 0.0, places=1)
        
        asyncio.run(run_test())
    
    def test_get_stats(self):
        """Should provide statistics."""
        stats = self.limiter.get_stats()
        
        self.assertEqual(stats["rate"], 10.0)
        self.assertEqual(stats["available_tokens"], 10.0)
        self.assertIn("epoch", stats)
    
    def test_rate_limiter_with_low_rate(self):
        """Should work correctly with low rates (e.g., 1 per second)."""
        limiter = RateLimiter(requests_per_second=1.0)
        self.assertEqual(limiter.rate, 1.0)
        self.assertEqual(limiter.tokens, 1.0)


class TestCircuitBreaker(unittest.TestCase):
    """Test cases for CircuitBreaker class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=1.0)
    
    def test_initialization(self):
        """Should initialize with correct state."""
        self.assertEqual(self.breaker.state, CircuitBreakerState.CLOSED)
        self.assertEqual(self.breaker.failure_count, 0)
        self.assertEqual(self.breaker.success_count, 0)
        self.assertEqual(self.breaker.failure_threshold, 3)
        self.assertEqual(self.breaker.recovery_timeout, 1.0)
    
    def test_invalid_threshold_raises_error(self):
        """Should reject non-positive thresholds."""
        with self.assertRaises(ValueError):
            CircuitBreaker(failure_threshold=0)
        with self.assertRaises(ValueError):
            CircuitBreaker(failure_threshold=-1)
    
    def test_invalid_timeout_raises_error(self):
        """Should reject non-positive timeouts."""
        with self.assertRaises(ValueError):
            CircuitBreaker(recovery_timeout=0)
        with self.assertRaises(ValueError):
            CircuitBreaker(recovery_timeout=-1)
    
    def test_is_open_closed_state(self):
        """Circuit should not be open when closed."""
        self.assertFalse(self.breaker.is_open())
    
    def test_record_single_failure(self):
        """Should record single failure without opening."""
        self.breaker.record_failure()
        self.assertEqual(self.breaker.failure_count, 1)
        self.assertFalse(self.breaker.is_open())
    
    def test_open_after_threshold(self):
        """Should open circuit after threshold failures."""
        for _ in range(3):
            self.breaker.record_failure()
        
        self.assertEqual(self.breaker.failure_count, 3)
        self.assertTrue(self.breaker.is_open())
        self.assertEqual(self.breaker.state, CircuitBreakerState.OPEN)
    
    def test_reject_after_threshold_exceeded(self):
        """Should keep rejecting after threshold exceeded."""
        for _ in range(5):
            self.breaker.record_failure()
        
        self.assertTrue(self.breaker.is_open())
        self.assertEqual(self.breaker.failure_count, 5)
    
    def test_record_success_resets_and_closes(self):
        """Should reset failures and close on success."""
        self.breaker.record_failure()
        self.breaker.record_failure()
        self.assertEqual(self.breaker.failure_count, 2)
        
        self.breaker.record_success()
        self.assertEqual(self.breaker.failure_count, 0)
        self.assertEqual(self.breaker.state, CircuitBreakerState.CLOSED)
        self.assertFalse(self.breaker.is_open())
    
    def test_success_increments_count(self):
        """Should track successful requests."""
        self.assertEqual(self.breaker.success_count, 0)
        self.breaker.record_success()
        self.assertEqual(self.breaker.success_count, 1)
        self.breaker.record_success()
        self.assertEqual(self.breaker.success_count, 2)
    
    def test_recovery_transition_half_open(self):
        """Circuit should transition OPEN → HALF_OPEN after timeout."""
        # Open circuit
        for _ in range(3):
            self.breaker.record_failure()
        self.assertTrue(self.breaker.is_open())
        self.assertEqual(self.breaker.state, CircuitBreakerState.OPEN)
        
        # Simulate timeout elapsed
        self.breaker.last_failure_time -= 2.0  # Move back 2 seconds
        
        # is_open should return False and transition to HALF_OPEN
        result = self.breaker.is_open()
        self.assertFalse(result)
        self.assertEqual(self.breaker.state, CircuitBreakerState.HALF_OPEN)
    
    def test_half_open_state_allows_request(self):
        """Circuit in HALF_OPEN state should allow request (is_open returns False)."""
        # Open and immediately transition
        for _ in range(3):
            self.breaker.record_failure()
        self.breaker.last_failure_time -= 2.0
        self.assertFalse(self.breaker.is_open())
        
        # Should be in HALF_OPEN state
        self.assertEqual(self.breaker.state, CircuitBreakerState.HALF_OPEN)
    
    def test_get_state(self):
        """Should return current state."""
        self.assertEqual(self.breaker.get_state(), CircuitBreakerState.CLOSED)
        
        for _ in range(3):
            self.breaker.record_failure()
        self.assertEqual(self.breaker.get_state(), CircuitBreakerState.OPEN)
    
    def test_get_stats(self):
        """Should provide comprehensive statistics."""
        self.breaker.record_failure()
        stats = self.breaker.get_stats()
        
        self.assertEqual(stats["state"], CircuitBreakerState.CLOSED)
        self.assertEqual(stats["failure_count"], 1)
        self.assertEqual(stats["success_count"], 0)
        self.assertEqual(stats["failure_threshold"], 3)
        self.assertEqual(stats["recovery_timeout"], 1.0)
        self.assertIsNotNone(stats["last_failure_time"])
    
    def test_stats_when_closed(self):
        """Stats should reflect closed state."""
        stats = self.breaker.get_stats()
        self.assertEqual(stats["state"], CircuitBreakerState.CLOSED)
        self.assertEqual(stats["failure_count"], 0)
        self.assertIsNone(stats["last_failure_time"])
    
    def test_last_failure_time_updated(self):
        """Should track last failure timestamp."""
        self.assertIsNone(self.breaker.last_failure_time)
        
        before = time.monotonic()
        self.breaker.record_failure()
        after = time.monotonic()
        
        self.assertIsNotNone(self.breaker.last_failure_time)
        self.assertGreaterEqual(self.breaker.last_failure_time, before)
        self.assertLessEqual(self.breaker.last_failure_time, after)
    
    def test_default_threshold(self):
        """Should use sensible default threshold."""
        breaker = CircuitBreaker()
        self.assertEqual(breaker.failure_threshold, 5)
        self.assertEqual(breaker.recovery_timeout, 60.0)
    
    def test_recovery_scenario(self):
        """Should handle full recovery scenario."""
        # Phase 1: Normal operation
        self.breaker.record_success()
        self.assertEqual(self.breaker.state, CircuitBreakerState.CLOSED)
        
        # Phase 2: Failures accumulate
        for _ in range(3):
            self.breaker.record_failure()
        self.assertTrue(self.breaker.is_open())
        
        # Phase 3: Timeout expires, transition to HALF_OPEN
        self.breaker.last_failure_time -= 2.0
        self.assertFalse(self.breaker.is_open())
        self.assertEqual(self.breaker.state, CircuitBreakerState.HALF_OPEN)
        
        # Phase 4: Test succeeds, return to CLOSED
        self.breaker.record_success()
        self.assertEqual(self.breaker.state, CircuitBreakerState.CLOSED)
        self.assertEqual(self.breaker.failure_count, 0)


class TestMessageBus(unittest.TestCase):
    """Test cases for MessageBus class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.bus = MessageBus()
        self.received_messages = []
    
    def handler(self, message):
        """Simple sync handler for testing."""
        self.received_messages.append(message)
    
    async def async_handler(self, message):
        """Simple async handler for testing."""
        await asyncio.sleep(0.001)
        self.received_messages.append(message)
    
    def test_initialization(self):
        """Should initialize with correct defaults."""
        self.assertEqual(self.bus.max_history, 1000)
        self.assertEqual(self.bus.total_published, 0)
        self.assertEqual(self.bus.total_errors, 0)
    
    def test_subscribe_handler(self):
        """Should subscribe handler to topic."""
        self.bus.subscribe("test_topic", self.handler)
        self.assertEqual(self.bus.get_subscriber_count("test_topic"), 1)
    
    def test_subscribe_non_callable_raises_error(self):
        """Should reject non-callable handlers."""
        with self.assertRaises(TypeError):
            self.bus.subscribe("test_topic", "not_callable")
    
    def test_publish_sync_handler(self):
        """Should invoke sync handler on publish."""
        self.bus.subscribe("test_topic", self.handler)
        
        message = {"data": "test"}
        self.bus.publish("test_topic", message)
        
        self.assertEqual(len(self.received_messages), 1)
        self.assertEqual(self.received_messages[0], message)
    
    def test_publish_async_handler(self):
        """Should invoke async handler on publish."""
        async def run_test():
            self.bus.subscribe("test_topic", self.async_handler)
            
            message = {"data": "test"}
            self.bus.publish("test_topic", message)
            
            # Give async task time to complete
            await asyncio.sleep(0.1)
            
            self.assertEqual(len(self.received_messages), 1)
            self.assertEqual(self.received_messages[0], message)
        
        asyncio.run(run_test())
    
    def test_publish_multiple_subscribers(self):
        """Should invoke all subscribers."""
        messages2 = []
        
        def handler2(message):
            messages2.append(message)
        
        self.bus.subscribe("topic", self.handler)
        self.bus.subscribe("topic", handler2)
        
        message = {"data": "test"}
        self.bus.publish("topic", message)
        
        self.assertEqual(len(self.received_messages), 1)
        self.assertEqual(len(messages2), 1)
    
    def test_broadcast_to_default_topic(self):
        """Should publish to DEFAULT_TOPIC handlers on any publish."""
        self.bus.subscribe(MessageBus.DEFAULT_TOPIC, self.handler)
        
        self.bus.publish("specific_topic", {"data": "1"})
        self.bus.publish("other_topic", {"data": "2"})
        
        # Should receive both messages
        self.assertEqual(len(self.received_messages), 2)
    
    def test_unsubscribe_handler(self):
        """Should remove handler from topic."""
        self.bus.subscribe("topic", self.handler)
        self.assertEqual(self.bus.get_subscriber_count("topic"), 1)
        
        self.bus.unsubscribe("topic", self.handler)
        self.assertEqual(self.bus.get_subscriber_count("topic"), 0)
    
    def test_unsubscribe_non_existent_raises_error(self):
        """Should error if handler not subscribed."""
        with self.assertRaises(ValueError):
            self.bus.unsubscribe("topic", self.handler)
    
    def test_event_history(self):
        """Should record published events."""
        self.bus.publish("topic1", {"data": "1"})
        self.bus.publish("topic2", {"data": "2"})
        
        history = self.bus.get_history()
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["topic"], "topic1")
        self.assertEqual(history[1]["topic"], "topic2")
    
    def test_history_filtered_by_topic(self):
        """Should filter history by topic."""
        self.bus.publish("topic1", {"data": "a"})
        self.bus.publish("topic2", {"data": "b"})
        self.bus.publish("topic1", {"data": "c"})
        
        history = self.bus.get_history("topic1")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["message"]["data"], "a")
        self.assertEqual(history[1]["message"]["data"], "c")
    
    def test_history_max_size(self):
        """Should cap history at max_history."""
        bus = MessageBus(max_history=5)
        
        for i in range(10):
            bus.publish("topic", {"n": i})
        
        self.assertEqual(len(bus.event_history), 5)
        # Should have last 5 events
        self.assertEqual(bus.event_history[0]["message"]["n"], 5)
        self.assertEqual(bus.event_history[4]["message"]["n"], 9)
    
    def test_clear_history(self):
        """Should clear event history."""
        self.bus.publish("topic", {"data": "1"})
        self.assertEqual(len(self.bus.get_history()), 1)
        
        self.bus.clear_history()
        self.assertEqual(len(self.bus.get_history()), 0)
    
    def test_get_subscriber_count_no_topic(self):
        """Should count all subscribers when topic not specified."""
        self.bus.subscribe("topic1", self.handler)
        self.bus.subscribe("topic2", self.handler)
        self.bus.subscribe("topic2", self.handler)
        
        self.assertEqual(self.bus.get_subscriber_count(), 3)
    
    def test_handler_error_logged_not_raised(self):
        """Should log handler errors but not propagate."""
        def bad_handler(message):
            raise ValueError("Handler error")
        
        self.bus.subscribe("topic", bad_handler)
        self.bus.subscribe("topic", self.handler)
        
        # Should not raise, but log error
        self.bus.publish("topic", {"data": "test"})
        
        # Handler after bad one should still execute
        self.assertEqual(len(self.received_messages), 1)
        self.assertEqual(self.bus.total_errors, 1)
    
    def test_get_stats(self):
        """Should provide comprehensive statistics."""
        self.bus.subscribe("topic1", self.handler)
        self.bus.subscribe("topic2", self.handler)
        self.bus.publish("topic1", {"data": "1"})
        self.bus.publish("topic2", {"data": "2"})
        
        stats = self.bus.get_stats()
        
        self.assertEqual(stats["total_published"], 2)
        self.assertEqual(stats["total_errors"], 0)
        self.assertEqual(stats["topics"], 2)
        self.assertEqual(stats["subscribers"], 2)
        self.assertEqual(stats["history_size"], 2)
        self.assertEqual(stats["max_history"], 1000)
    
    def test_multiple_subscribe_receive_all(self):
        """Should receive all messages from multiple publishes."""
        self.bus.subscribe("topic", self.handler)
        
        for i in range(5):
            self.bus.publish("topic", {"n": i})
        
        self.assertEqual(len(self.received_messages), 5)
    
    def test_subscriber_receives_any_message_type(self):
        """Should handle any message type."""
        self.bus.subscribe("topic", self.handler)
        
        # String
        self.bus.publish("topic", "string")
        # Dict
        self.bus.publish("topic", {"key": "value"})
        # List
        self.bus.publish("topic", [1, 2, 3])
        # Number
        self.bus.publish("topic", 42)
        
        self.assertEqual(len(self.received_messages), 4)
        self.assertEqual(self.received_messages[0], "string")
        self.assertEqual(self.received_messages[1], {"key": "value"})
        self.assertEqual(self.received_messages[2], [1, 2, 3])
        self.assertEqual(self.received_messages[3], 42)
    
    def test_topic_isolation(self):
        """Should not cross-subscribe between different topics."""
        topic1_messages = []
        topic2_messages = []
        
        def handler1(m):
            topic1_messages.append(m)
        
        def handler2(m):
            topic2_messages.append(m)
        
        self.bus.subscribe("topic1", handler1)
        self.bus.subscribe("topic2", handler2)
        
        self.bus.publish("topic1", "msg1")
        self.bus.publish("topic2", "msg2")
        
        self.assertEqual(topic1_messages, ["msg1"])
        self.assertEqual(topic2_messages, ["msg2"])


if __name__ == "__main__":
    unittest.main()




