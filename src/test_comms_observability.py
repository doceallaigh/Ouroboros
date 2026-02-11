"""
Unit tests for comms_observability module.

Tests request correlation and message metrics.
"""

import time
import unittest
from unittest.mock import patch

from comms_observability import (
    CorrelationContext,
    MessageMetrics,
    correlation_id,
)


class TestCorrelationContext(unittest.TestCase):
    """Test cases for CorrelationContext class."""
    
    def setUp(self):
        """Clear correlation context before each test."""
        CorrelationContext.clear()
    
    def test_new_creates_correlation_id(self):
        """Should create new UUID correlation ID."""
        cid = CorrelationContext.new()
        self.assertIsNotNone(cid)
        self.assertIsInstance(cid, str)
        self.assertEqual(len(cid), 36)  # UUID format
    
    def test_new_sets_context(self):
        """Should set correlation ID in context."""
        cid = CorrelationContext.new()
        self.assertEqual(CorrelationContext.get(), cid)
    
    def test_get_returns_none_initially(self):
        """Should return None when no correlation set."""
        self.assertIsNone(CorrelationContext.get())
    
    def test_set_correlation_id(self):
        """Should set explicit correlation ID."""
        test_id = "test-correlation-123"
        CorrelationContext.set(test_id)
        self.assertEqual(CorrelationContext.get(), test_id)
    
    def test_clear_removes_correlation(self):
        """Should clear correlation ID from context."""
        CorrelationContext.new()
        self.assertIsNotNone(CorrelationContext.get())
        
        CorrelationContext.clear()
        self.assertIsNone(CorrelationContext.get())
    
    def test_multiple_new_overwrites(self):
        """Should overwrite with new correlation ID."""
        cid1 = CorrelationContext.new()
        cid2 = CorrelationContext.new()
        
        self.assertNotEqual(cid1, cid2)
        self.assertEqual(CorrelationContext.get(), cid2)
    
    def test_correlation_persists_across_gets(self):
        """Should maintain correlation across multiple get calls."""
        cid = CorrelationContext.new()
        
        self.assertEqual(CorrelationContext.get(), cid)
        self.assertEqual(CorrelationContext.get(), cid)
        self.assertEqual(CorrelationContext.get(), cid)


class TestMessageMetrics(unittest.TestCase):
    """Test cases for MessageMetrics class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.metrics = MessageMetrics()
    
    def test_initialization(self):
        """Should initialize with zero metrics."""
        self.assertEqual(self.metrics.requests_total, 0)
        self.assertEqual(self.metrics.requests_success, 0)
        self.assertEqual(self.metrics.requests_failed, 0)
        self.assertEqual(len(self.metrics.response_times), 0)
    
    def test_record_single_request(self):
        """Should record successful request."""
        self.metrics.record_request(0.5, 200)
        
        self.assertEqual(self.metrics.requests_total, 1)
        self.assertEqual(self.metrics.requests_success, 1)
        self.assertEqual(self.metrics.requests_failed, 0)
        self.assertEqual(len(self.metrics.response_times), 1)
    
    def test_record_request_captures_duration(self):
        """Should capture response time."""
        self.metrics.record_request(0.123, 200)
        self.assertEqual(self.metrics.response_times[0], 0.123)
    
    def test_record_request_captures_status_code(self):
        """Should track status code counts."""
        self.metrics.record_request(0.1, 200)
        self.metrics.record_request(0.2, 200)
        self.metrics.record_request(0.3, 404)
        
        self.assertEqual(self.metrics.status_codes[200], 2)
        self.assertEqual(self.metrics.status_codes[404], 1)
    
    def test_record_error(self):
        """Should record failed request."""
        self.metrics.record_error("TimeoutError")
        
        self.assertEqual(self.metrics.requests_total, 1)
        self.assertEqual(self.metrics.requests_success, 0)
        self.assertEqual(self.metrics.requests_failed, 1)
        self.assertEqual(self.metrics.errors_by_type["TimeoutError"], 1)
    
    def test_record_multiple_errors(self):
        """Should track error types and counts."""
        self.metrics.record_error("TimeoutError")
        self.metrics.record_error("ConnectionError")
        self.metrics.record_error("TimeoutError")
        
        self.assertEqual(self.metrics.errors_by_type["TimeoutError"], 2)
        self.assertEqual(self.metrics.errors_by_type["ConnectionError"], 1)
    
    def test_get_stats_basic(self):
        """Should return basic statistics."""
        self.metrics.record_request(0.1, 200)
        self.metrics.record_error("TestError")
        
        stats = self.metrics.get_stats()
        
        self.assertEqual(stats["total_requests"], 2)
        self.assertEqual(stats["successful"], 1)
        self.assertEqual(stats["failed"], 1)
        self.assertEqual(stats["success_rate"], 0.5)
    
    def test_get_stats_response_times(self):
        """Should calculate response time statistics."""
        times = [0.1, 0.2, 0.3, 0.4, 0.5]
        for t in times:
            self.metrics.record_request(t, 200)
        
        stats = self.metrics.get_stats()
        
        self.assertEqual(stats["response_time_min"], 0.1)
        self.assertEqual(stats["response_time_max"], 0.5)
        self.assertAlmostEqual(stats["response_time_avg"], 0.3, places=2)
        self.assertEqual(stats["response_time_p50"], 0.3)
    
    def test_get_stats_empty_metrics(self):
        """Should handle empty metrics gracefully."""
        stats = self.metrics.get_stats()
        
        self.assertEqual(stats["total_requests"], 0)
        self.assertEqual(stats["response_time_avg"], 0)
        self.assertEqual(stats["response_time_min"], 0)
    
    def test_get_stats_uptime(self):
        """Should track uptime."""
        time.sleep(0.01)  # Small delay
        stats = self.metrics.get_stats()
        
        self.assertGreater(stats["uptime_seconds"], 0)
        self.assertIn("requests_per_second", stats)
    
    def test_reset_clears_metrics(self):
        """Should reset all metrics to zero."""
        self.metrics.record_request(0.1, 200)
        self.metrics.record_error("TestError")
        
        self.metrics.reset()
        
        self.assertEqual(self.metrics.requests_total, 0)
        self.assertEqual(self.metrics.requests_success, 0)
        self.assertEqual(self.metrics.requests_failed, 0)
        self.assertEqual(len(self.metrics.response_times), 0)
        self.assertEqual(len(self.metrics.errors_by_type), 0)
    
    def test_get_error_summary(self):
        """Should return sorted error summary."""
        self.metrics.record_error("ErrorA")
        self.metrics.record_error("ErrorB")
        self.metrics.record_error("ErrorA")
        self.metrics.record_error("ErrorA")
        
        summary = self.metrics.get_error_summary()
        
        self.assertEqual(len(summary), 2)
        self.assertEqual(summary[0]["error_type"], "ErrorA")
        self.assertEqual(summary[0]["count"], 3)
        self.assertEqual(summary[1]["error_type"], "ErrorB")
        self.assertEqual(summary[1]["count"], 1)
    
    def test_get_status_summary(self):
        """Should return sorted status code summary."""
        self.metrics.record_request(0.1, 200)
        self.metrics.record_request(0.1, 200)
        self.metrics.record_request(0.1, 404)
        self.metrics.record_request(0.1, 500)
        self.metrics.record_request(0.1, 500)
        self.metrics.record_request(0.1, 500)
        
        summary = self.metrics.get_status_summary()
        
        self.assertEqual(len(summary), 3)
        self.assertEqual(summary[0]["status_code"], 500)
        self.assertEqual(summary[0]["count"], 3)
        self.assertEqual(summary[1]["status_code"], 200)
        self.assertEqual(summary[1]["count"], 2)
    
    def test_percentile_calculation(self):
        """Should calculate percentiles correctly."""
        # Create 100 samples for accurate percentile testing
        for i in range(100):
            self.metrics.record_request(i / 100.0, 200)
        
        stats = self.metrics.get_stats()
        
        # P50 should be around 0.5
        self.assertAlmostEqual(stats["response_time_p50"], 0.5, delta=0.1)
        # P95 should be around 0.95
        self.assertAlmostEqual(stats["response_time_p95"], 0.95, delta=0.05)
        # P99 should be around 0.99
        self.assertAlmostEqual(stats["response_time_p99"], 0.99, delta=0.02)
    
    def test_success_rate_calculation(self):
        """Should calculate success rate correctly."""
        for _ in range(7):
            self.metrics.record_request(0.1, 200)
        for _ in range(3):
            self.metrics.record_error("TestError")
        
        stats = self.metrics.get_stats()
        self.assertAlmostEqual(stats["success_rate"], 0.7, places=2)
    
    def test_requests_per_second(self):
        """Should calculate request rate."""
        time.sleep(0.1)
        for _ in range(10):
            self.metrics.record_request(0.01, 200)
        
        stats = self.metrics.get_stats()
        self.assertGreater(stats["requests_per_second"], 0)


if __name__ == "__main__":
    unittest.main()
