"""
Integration tests for the communications module.

Tests the complete communications stack with all components working together:
- Connection pooling + rate limiting + circuit breaker + metrics
- Shared infrastructure across multiple channels
- End-to-end failure scenarios
- Concurrent request handling
"""

import asyncio
import time
import unittest
from unittest.mock import Mock, AsyncMock

from comms import APIChannel, ChannelFactory, APIError
from comms.resilience import (
    ConnectionPool,
    RateLimiter,
    CircuitBreaker,
    MessageBus,
)
from comms.observability import CorrelationContext, MessageMetrics
from httpx import Response as HTTPXResponse


class TestAPIChannelFullStack(unittest.TestCase):
    """Test APIChannel with all components integrated."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Clear any correlation context from previous tests
        CorrelationContext.clear()
        
        self.config = {
            "name": "test_agent",
            "endpoint": "http://localhost:8000/api",
            "timeout": 30,
        }
        self.pool = ConnectionPool()
        self.limiter = RateLimiter(requests_per_second=10.0)
        self.breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=1)
        self.metrics = MessageMetrics()
        
        self.channel = APIChannel(
            self.config,
            connection_pool=self.pool,
            rate_limiter=self.limiter,
            circuit_breaker=self.breaker,
            metrics=self.metrics,
        )
    
    def test_successful_request_flow(self):
        """Should handle complete successful request flow."""
        # Setup mock
        mock_client = AsyncMock()
        mock_response = Mock(spec=HTTPXResponse)
        mock_response.status_code = 200
        
        async def mock_post(*args, **kwargs):
            await asyncio.sleep(0.01)
            return mock_response
        
        mock_client.post = mock_post
        self.pool.get_client = AsyncMock(return_value=mock_client)
        
        # Execute request
        message = {
            "messages": [{"role": "user", "content": "Hello"}],
            "model": "gpt-3.5"
        }
        self.channel.send_message(message)
        result = asyncio.run(self.channel.receive_message())
        
        # Verify all components updated correctly
        self.assertEqual(result, mock_response)
        self.assertEqual(self.metrics.requests_total, 1)
        self.assertEqual(self.metrics.requests_success, 1)
        self.assertEqual(self.breaker.failure_count, 0)
        self.assertEqual(self.breaker.success_count, 1)
        self.assertGreater(len(self.metrics.response_times), 0)
    
    def test_failure_updates_all_components(self):
        """Should record failures across all components."""
        # Setup failing mock
        mock_client = AsyncMock()
        
        async def mock_post(*args, **kwargs):
            raise Exception("Connection failed")
        
        mock_client.post = mock_post
        self.pool.get_client = AsyncMock(return_value=mock_client)
        
        # Execute failing request
        message = {
            "messages": [{"role": "user", "content": "Hello"}],
            "model": "gpt-3.5"
        }
        self.channel.send_message(message)
        
        with self.assertRaises(APIError):
            asyncio.run(self.channel.receive_message())
        
        # Verify failure recorded everywhere
        self.assertEqual(self.metrics.requests_failed, 1)
        self.assertEqual(self.breaker.failure_count, 1)
        self.assertIn("Exception", self.metrics.errors_by_type)
    
    def test_circuit_breaker_prevents_requests(self):
        """Should reject requests when circuit opens."""
        # Setup always-failing mock
        mock_client = AsyncMock()
        
        async def mock_post(*args, **kwargs):
            raise Exception("Always fails")
        
        mock_client.post = mock_post
        self.pool.get_client = AsyncMock(return_value=mock_client)
        
        message = {
            "messages": [{"role": "user", "content": "Hello"}],
            "model": "gpt-3.5"
        }
        
        # Fail threshold times to open circuit
        for _ in range(3):
            self.channel.send_message(message)
            with self.assertRaises(APIError):
                asyncio.run(self.channel.receive_message())
        
        # Circuit should be open
        self.assertEqual(self.breaker.state, "open")
        
        # Next request should be rejected by circuit breaker
        self.channel.send_message(message)
        with self.assertRaises(APIError) as context:
            asyncio.run(self.channel.receive_message())
        
        self.assertIn("Circuit breaker is open", str(context.exception))
        self.assertIn("CircuitBreakerOpen", self.metrics.errors_by_type)
    
    def test_rate_limiting_works(self):
        """Should enforce rate limits."""
        # Use slow rate for testing
        slow_limiter = RateLimiter(requests_per_second=2.0)
        pool = ConnectionPool()
        channel = APIChannel(
            self.config,
            connection_pool=pool,
            rate_limiter=slow_limiter,
        )
        
        # Setup fast mock
        mock_client = AsyncMock()
        mock_response = Mock(spec=HTTPXResponse)
        mock_response.status_code = 200
        mock_client.post = AsyncMock(return_value=mock_response)
        pool.get_client = AsyncMock(return_value=mock_client)
        
        message = {
            "messages": [{"role": "user", "content": "Hello"}],
            "model": "gpt-3.5"
        }
        
        # Send 3 requests and measure time
        async def send_three():
            for _ in range(3):
                channel.send_message(message)
                await channel.receive_message()
        
        start = time.time()
        asyncio.run(send_three())
        elapsed = time.time() - start
        
        # Should take at least 0.5 seconds due to rate limiting
        self.assertGreater(elapsed, 0.4)
    
    def test_correlation_ids_created_and_cleared(self):
        """Should create and clear correlation IDs."""
        # Setup mock
        mock_client = AsyncMock()
        mock_response = Mock(spec=HTTPXResponse)
        mock_response.status_code = 200
        mock_client.post = AsyncMock(return_value=mock_response)
        self.pool.get_client = AsyncMock(return_value=mock_client)
        
        # Before request - no correlation
        self.assertIsNone(CorrelationContext.get())
        
        # Execute request
        message = {
            "messages": [{"role": "user", "content": "Hello"}],
            "model": "gpt-3.5"
        }
        self.channel.send_message(message)
        asyncio.run(self.channel.receive_message())
        
        # After request - should be cleared
        self.assertIsNone(CorrelationContext.get())


class TestSharedInfrastructure(unittest.TestCase):
    """Test shared components across multiple channels."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config1 = {
            "name": "agent1",
            "endpoint": "http://localhost:8000/api",
            "timeout": 30,
        }
        self.config2 = {
            "name": "agent2",
            "endpoint": "http://localhost:8000/api",
            "timeout": 30,
        }
    
    def test_shared_circuit_breaker(self):
        """Should share circuit breaker state across channels."""
        # Create shared breaker
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=1)
        
        # Setup failing mocks
        mock_client1 = AsyncMock()
        mock_client2 = AsyncMock()
        
        async def mock_post(*args, **kwargs):
            raise Exception("Connection failed")
        
        mock_client1.post = mock_post
        mock_client2.post = mock_post
        
        pool1 = ConnectionPool()
        pool2 = ConnectionPool()
        pool1.get_client = AsyncMock(return_value=mock_client1)
        pool2.get_client = AsyncMock(return_value=mock_client2)
        
        # Create channels sharing breaker
        channel1 = APIChannel(self.config1, connection_pool=pool1, circuit_breaker=breaker)
        channel2 = APIChannel(self.config2, connection_pool=pool2, circuit_breaker=breaker)
        
        message = {
            "messages": [{"role": "user", "content": "Hello"}],
            "model": "gpt-3.5"
        }
        
        # Channel1 fails twice - opens circuit
        for _ in range(2):
            channel1.send_message(message)
            with self.assertRaises(APIError):
                asyncio.run(channel1.receive_message())
        
        self.assertEqual(breaker.state, "open")
        
        # Channel2 should also be blocked
        channel2.send_message(message)
        with self.assertRaises(APIError) as context:
            asyncio.run(channel2.receive_message())
        
        self.assertIn("Circuit breaker is open", str(context.exception))
    
    def test_shared_metrics(self):
        """Should aggregate metrics across channels."""
        # Create shared metrics
        metrics = MessageMetrics()
        
        # Setup mocks
        mock_client1 = AsyncMock()
        mock_client2 = AsyncMock()
        mock_response = Mock(spec=HTTPXResponse)
        mock_response.status_code = 200
        mock_client1.post = AsyncMock(return_value=mock_response)
        mock_client2.post = AsyncMock(return_value=mock_response)
        
        pool1 = ConnectionPool()
        pool2 = ConnectionPool()
        pool1.get_client = AsyncMock(return_value=mock_client1)
        pool2.get_client = AsyncMock(return_value=mock_client2)
        
        # Create channels sharing metrics
        channel1 = APIChannel(self.config1, connection_pool=pool1, metrics=metrics)
        channel2 = APIChannel(self.config2, connection_pool=pool2, metrics=metrics)
        
        message = {
            "messages": [{"role": "user", "content": "Hello"}],
            "model": "gpt-3.5"
        }
        
        # Send from both channels
        channel1.send_message(message)
        asyncio.run(channel1.receive_message())
        
        channel2.send_message(message)
        asyncio.run(channel2.receive_message())
        
        # Should aggregate
        self.assertEqual(metrics.requests_total, 2)
        self.assertEqual(metrics.requests_success, 2)
    
    def test_shared_rate_limiter(self):
        """Should rate limit across all channels."""
        # Setup mock
        mock_client = AsyncMock()
        mock_response = Mock(spec=HTTPXResponse)
        mock_response.status_code = 200
        mock_client.post = AsyncMock(return_value=mock_response)
        
        # Create shared limiter (very slow for reliable testing)
        limiter = RateLimiter(requests_per_second=2.0)
        
        # Use factory to create channels
        factory = ChannelFactory(
            replay_mode=False,
            rate_limiter=limiter,
        )
        
        channel1 = factory.create_channel(self.config1)
        channel2 = factory.create_channel(self.config2)
        
        # Mock their pools
        channel1.connection_pool.get_client = AsyncMock(return_value=mock_client)
        channel2.connection_pool.get_client = AsyncMock(return_value=mock_client)
        
        message = {
            "messages": [{"role": "user", "content": "Hello"}],
            "model": "gpt-3.5"
        }
        
        # Exhaust initial tokens first
        limiter.tokens = 0
        
        # Send 3 requests sequentially to ensure rate limiting
        async def send_three():
            for channel in [channel1, channel2, channel1]:
                channel.send_message(message)
                await channel.receive_message()
        
        start = time.time()
        asyncio.run(send_three())
        elapsed = time.time() - start
        
        # With 2 req/sec and 0 starting tokens, 3 requests need at least 1.5s
        # (0.5s for first, 0.5s for second, 0.5s for third)
        self.assertGreater(elapsed, 1.0)


class TestChannelFactoryIntegration(unittest.TestCase):
    """Test ChannelFactory creates properly configured channels."""
    
    def test_factory_injects_all_components(self):
        """Should inject all provided components."""
        pool = ConnectionPool()
        limiter = RateLimiter(requests_per_second=10.0)
        breaker = CircuitBreaker()
        metrics = MessageMetrics()
        
        factory = ChannelFactory(
            replay_mode=False,
            connection_pool=pool,
            rate_limiter=limiter,
            circuit_breaker=breaker,
            metrics=metrics,
        )
        
        config = {"name": "agent", "endpoint": "http://localhost:8000/api"}
        channel = factory.create_channel(config)
        
        # Verify injection
        self.assertIs(channel.connection_pool, pool)
        self.assertIs(channel.rate_limiter, limiter)
        self.assertIs(channel.circuit_breaker, breaker)
        self.assertIs(channel.metrics, metrics)
    
    def test_factory_creates_defaults(self):
        """Should create default components when none provided."""
        factory = ChannelFactory(replay_mode=False)
        
        config = {"name": "agent", "endpoint": "http://localhost:8000/api"}
        channel = factory.create_channel(config)
        
        # Should have components
        self.assertIsNotNone(channel.connection_pool)
        self.assertIsNotNone(channel.rate_limiter)
        self.assertIsNotNone(channel.circuit_breaker)
        self.assertIsNotNone(channel.metrics)
    
    def test_multiple_channels_share_factory_components(self):
        """Should create multiple channels sharing factory components."""
        factory = ChannelFactory(replay_mode=False)
        
        config1 = {"name": "agent1", "endpoint": "http://localhost:8000/api"}
        config2 = {"name": "agent2", "endpoint": "http://localhost:8000/api"}
        
        channel1 = factory.create_channel(config1)
        channel2 = factory.create_channel(config2)
        
        # Should share components
        self.assertIs(channel1.connection_pool, channel2.connection_pool)
        self.assertIs(channel1.rate_limiter, channel2.rate_limiter)
        self.assertIs(channel1.circuit_breaker, channel2.circuit_breaker)
        self.assertIs(channel1.metrics, channel2.metrics)


class TestConcurrentRequests(unittest.TestCase):
    """Test concurrent request scenarios."""
    
    def test_concurrent_requests_isolated_correlation(self):
        """Should maintain separate correlation IDs per request."""
        mock_client = AsyncMock()
        mock_response = Mock(spec=HTTPXResponse)
        mock_response.status_code = 200
        
        correlation_ids = []
        
        async def mock_post(*args, **kwargs):
            # Capture correlation ID during request
            cid = CorrelationContext.get()
            correlation_ids.append(cid)
            await asyncio.sleep(0.01)
            return mock_response
        
        mock_client.post = mock_post
        
        # Create multiple channels
        channels = []
        for i in range(3):
            config = {
                "name": f"agent_{i}",
                "endpoint": "http://localhost:8000/api",
                "timeout": 30,
            }
            pool = ConnectionPool()
            pool.get_client = AsyncMock(return_value=mock_client)
            channel = APIChannel(config, connection_pool=pool)
            channels.append(channel)
        
        # Send concurrent requests
        message = {
            "messages": [{"role": "user", "content": "Hello"}],
            "model": "gpt-3.5"
        }
        
        async def send_all():
            tasks = []
            for channel in channels:
                channel.send_message(message)
                tasks.append(channel.receive_message())
            return await asyncio.gather(*tasks)
        
        asyncio.run(send_all())
        
        # Each should have unique correlation ID
        self.assertEqual(len(correlation_ids), 3)
        self.assertEqual(len(set(correlation_ids)), 3)


class TestMessageBusIntegration(unittest.TestCase):
    """Test MessageBus integration with communications."""
    
    def test_publish_request_completion_events(self):
        """Should publish events on request completion."""
        # Setup mock
        mock_client = AsyncMock()
        mock_response = Mock(spec=HTTPXResponse)
        mock_response.status_code = 200
        mock_client.post = AsyncMock(return_value=mock_response)
        
        # Create components
        bus = MessageBus()
        events_received = []
        
        def on_request_complete(event):
            events_received.append(event)
        
        bus.subscribe("request.complete", on_request_complete)
        
        config = {
            "name": "test_agent",
            "endpoint": "http://localhost:8000/api",
            "timeout": 30,
        }
        metrics = MessageMetrics()
        pool = ConnectionPool()
        pool.get_client = AsyncMock(return_value=mock_client)
        channel = APIChannel(config, connection_pool=pool, metrics=metrics)
        
        # Send request
        message = {
            "messages": [{"role": "user", "content": "Hello"}],
            "model": "gpt-3.5"
        }
        channel.send_message(message)
        asyncio.run(channel.receive_message())
        
        # Publish event (in real system, this would be automatic)
        stats = metrics.get_stats()
        bus.publish("request.complete", {
            "agent": "test_agent",
            "status": 200,
            "duration": stats["response_time_avg"],
        })
        
        # Verify
        self.assertEqual(len(events_received), 1)
        self.assertEqual(events_received[0]["agent"], "test_agent")
        self.assertEqual(events_received[0]["status"], 200)


class TestEndToEndScenarios(unittest.TestCase):
    """Test realistic end-to-end scenarios."""
    
    def test_recovery_after_circuit_open(self):
        """Should recover after circuit breaker opens and recovers."""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.5)
        pool = ConnectionPool()
        config = {
            "name": "test_agent",
            "endpoint": "http://localhost:8000/api",
            "timeout": 30,
        }
        channel = APIChannel(config, connection_pool=pool, circuit_breaker=breaker)
        
        # Phase 1: Fail twice to open circuit
        mock_client = AsyncMock()
        
        async def failing_post(*args, **kwargs):
            raise Exception("Connection failed")
        
        mock_client.post = failing_post
        pool.get_client = AsyncMock(return_value=mock_client)
        
        message = {
            "messages": [{"role": "user", "content": "Hello"}],
            "model": "gpt-3.5"
        }
        
        for _ in range(2):
            channel.send_message(message)
            with self.assertRaises(APIError):
                asyncio.run(channel.receive_message())
        
        self.assertEqual(breaker.state, "open")
        
        # Phase 2: Wait for recovery timeout
        time.sleep(0.6)
        
        # Phase 3: Request should now succeed (half-open → closed)
        mock_response = Mock(spec=HTTPXResponse)
        mock_response.status_code = 200
        
        async def success_post(*args, **kwargs):
            return mock_response
        
        mock_client.post = success_post
        
        channel.send_message(message)
        result = asyncio.run(channel.receive_message())
        
        # Should succeed and close circuit
        self.assertEqual(result, mock_response)
        self.assertEqual(breaker.state, "closed")
        self.assertEqual(breaker.failure_count, 0)
    
    def test_mixed_success_and_failure_tracking(self):
        """Should accurately track mixed successes and failures."""
        metrics = MessageMetrics()
        pool = ConnectionPool()
        config = {
            "name": "test_agent",
            "endpoint": "http://localhost:8000/api",
            "timeout": 30,
        }
        channel = APIChannel(config, connection_pool=pool, metrics=metrics)
        
        # Setup mock with alternating responses
        mock_client = AsyncMock()
        
        success_response = Mock(spec=HTTPXResponse)
        success_response.status_code = 200
        
        error_response = Mock(spec=HTTPXResponse)
        error_response.status_code = 500
        
        responses = [
            success_response,
            error_response,
            success_response,
            success_response,
            error_response,
        ]
        mock_client.post = AsyncMock(side_effect=responses)
        pool.get_client = AsyncMock(return_value=mock_client)
        
        message = {
            "messages": [{"role": "user", "content": "Hello"}],
            "model": "gpt-3.5"
        }
        
        # Send 5 requests
        for _ in range(5):
            channel.send_message(message)
            asyncio.run(channel.receive_message())
        
        # Verify metrics
        stats = metrics.get_stats()
        self.assertEqual(stats["total_requests"], 5)
        self.assertEqual(stats["successful"], 5)  # All HTTP responses count as success
        self.assertEqual(metrics.status_codes[200], 3)
        self.assertEqual(metrics.status_codes[500], 2)
        self.assertAlmostEqual(stats["success_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
