"""Unit tests for cardinality tracker."""

import pytest
from prometheus_client import REGISTRY

from f5xc_exporter.cardinality import CardinalityTracker


@pytest.fixture
def tracker():
    """Create a CardinalityTracker instance for testing."""
    return CardinalityTracker(
        max_namespaces=3,
        max_load_balancers_per_namespace=2,
        max_dns_zones=3,
        warn_cardinality_threshold=100,
    )


@pytest.fixture
def tracker_unregistered():
    """Create a tracker that doesn't auto-register with global registry."""
    # Create a tracker with custom settings
    tracker = CardinalityTracker(
        max_namespaces=3,
        max_load_balancers_per_namespace=2,
        max_dns_zones=3,
        warn_cardinality_threshold=100,
    )
    # Unregister from global registry to avoid conflicts
    try:
        REGISTRY.unregister(tracker.metric_cardinality)
        REGISTRY.unregister(tracker.cardinality_limit_exceeded)
        REGISTRY.unregister(tracker.total_tracked_namespaces)
        REGISTRY.unregister(tracker.total_tracked_load_balancers)
        REGISTRY.unregister(tracker.total_tracked_dns_zones)
    except Exception:
        pass
    return tracker


class TestCardinalityTracker:
    """Tests for CardinalityTracker class."""

    def test_init_default_values(self):
        """Test tracker initialization with default values."""
        tracker = CardinalityTracker()
        assert tracker.max_namespaces == 100
        assert tracker.max_load_balancers_per_namespace == 50
        assert tracker.max_dns_zones == 100
        assert tracker.warn_cardinality_threshold == 10000

    def test_init_custom_values(self, tracker_unregistered):
        """Test tracker initialization with custom values."""
        assert tracker_unregistered.max_namespaces == 3
        assert tracker_unregistered.max_load_balancers_per_namespace == 2
        assert tracker_unregistered.max_dns_zones == 3
        assert tracker_unregistered.warn_cardinality_threshold == 100

    def test_check_namespace_limit_within_limit(self, tracker_unregistered):
        """Test namespace check when within limit."""
        assert tracker_unregistered.check_namespace_limit("ns1", "test") is True
        assert tracker_unregistered.check_namespace_limit("ns2", "test") is True
        assert tracker_unregistered.check_namespace_limit("ns3", "test") is True
        assert len(tracker_unregistered.tracked_namespaces) == 3

    def test_check_namespace_limit_exceeds_limit(self, tracker_unregistered):
        """Test namespace check when limit is exceeded."""
        tracker_unregistered.check_namespace_limit("ns1", "test")
        tracker_unregistered.check_namespace_limit("ns2", "test")
        tracker_unregistered.check_namespace_limit("ns3", "test")

        # 4th namespace should fail
        assert tracker_unregistered.check_namespace_limit("ns4", "test") is False
        assert len(tracker_unregistered.tracked_namespaces) == 3
        assert "test_namespace" in tracker_unregistered.limits_exceeded

    def test_check_namespace_limit_same_namespace(self, tracker_unregistered):
        """Test that same namespace can be checked multiple times."""
        assert tracker_unregistered.check_namespace_limit("ns1", "test") is True
        assert tracker_unregistered.check_namespace_limit("ns1", "test") is True
        assert len(tracker_unregistered.tracked_namespaces) == 1

    def test_check_load_balancer_limit_within_limit(self, tracker_unregistered):
        """Test load balancer check when within limit."""
        assert tracker_unregistered.check_load_balancer_limit("ns1", "lb1", "test") is True
        assert tracker_unregistered.check_load_balancer_limit("ns1", "lb2", "test") is True
        assert len(tracker_unregistered.tracked_load_balancers["ns1"]) == 2

    def test_check_load_balancer_limit_exceeds_limit(self, tracker_unregistered):
        """Test load balancer check when limit is exceeded."""
        tracker_unregistered.check_load_balancer_limit("ns1", "lb1", "test")
        tracker_unregistered.check_load_balancer_limit("ns1", "lb2", "test")

        # 3rd LB should fail
        assert tracker_unregistered.check_load_balancer_limit("ns1", "lb3", "test") is False
        assert len(tracker_unregistered.tracked_load_balancers["ns1"]) == 2
        assert "test_load_balancer" in tracker_unregistered.limits_exceeded

    def test_check_load_balancer_limit_different_namespaces(self, tracker_unregistered):
        """Test load balancer limits are per-namespace."""
        tracker_unregistered.check_load_balancer_limit("ns1", "lb1", "test")
        tracker_unregistered.check_load_balancer_limit("ns1", "lb2", "test")
        tracker_unregistered.check_load_balancer_limit("ns2", "lb1", "test")
        tracker_unregistered.check_load_balancer_limit("ns2", "lb2", "test")

        assert len(tracker_unregistered.tracked_load_balancers["ns1"]) == 2
        assert len(tracker_unregistered.tracked_load_balancers["ns2"]) == 2

    def test_check_dns_zone_limit_within_limit(self, tracker_unregistered):
        """Test DNS zone check when within limit."""
        assert tracker_unregistered.check_dns_zone_limit("zone1.com", "test") is True
        assert tracker_unregistered.check_dns_zone_limit("zone2.com", "test") is True
        assert tracker_unregistered.check_dns_zone_limit("zone3.com", "test") is True
        assert len(tracker_unregistered.tracked_dns_zones) == 3

    def test_check_dns_zone_limit_exceeds_limit(self, tracker_unregistered):
        """Test DNS zone check when limit is exceeded."""
        tracker_unregistered.check_dns_zone_limit("zone1.com", "test")
        tracker_unregistered.check_dns_zone_limit("zone2.com", "test")
        tracker_unregistered.check_dns_zone_limit("zone3.com", "test")

        # 4th zone should fail
        assert tracker_unregistered.check_dns_zone_limit("zone4.com", "test") is False
        assert len(tracker_unregistered.tracked_dns_zones) == 3
        assert "test_dns_zone" in tracker_unregistered.limits_exceeded

    def test_update_metric_cardinality(self, tracker_unregistered):
        """Test metric cardinality tracking."""
        tracker_unregistered.update_metric_cardinality("collector1", "metric1", 10)
        tracker_unregistered.update_metric_cardinality("collector1", "metric2", 20)
        tracker_unregistered.update_metric_cardinality("collector2", "metric1", 15)

        assert tracker_unregistered.get_collector_cardinality("collector1") == 30
        assert tracker_unregistered.get_collector_cardinality("collector2") == 15

    def test_get_total_cardinality(self, tracker_unregistered):
        """Test total cardinality calculation."""
        tracker_unregistered.update_metric_cardinality("collector1", "metric1", 10)
        tracker_unregistered.update_metric_cardinality("collector2", "metric1", 20)

        assert tracker_unregistered.get_total_cardinality() == 30

    def test_reset_tracking(self, tracker_unregistered):
        """Test reset functionality."""
        # Add some tracking data
        tracker_unregistered.check_namespace_limit("ns1", "test")
        tracker_unregistered.check_load_balancer_limit("ns1", "lb1", "test")
        tracker_unregistered.check_dns_zone_limit("zone1.com", "test")
        tracker_unregistered.update_metric_cardinality("collector1", "metric1", 10)

        # Reset
        tracker_unregistered.reset_tracking()

        # Verify everything is cleared
        assert len(tracker_unregistered.tracked_namespaces) == 0
        assert len(tracker_unregistered.tracked_load_balancers) == 0
        assert len(tracker_unregistered.tracked_dns_zones) == 0
        assert len(tracker_unregistered.cardinality_per_collector) == 0
        assert len(tracker_unregistered.cardinality_per_metric) == 0
        assert len(tracker_unregistered.limits_exceeded) == 0

    def test_get_stats(self, tracker_unregistered):
        """Test statistics retrieval."""
        tracker_unregistered.check_namespace_limit("ns1", "test")
        tracker_unregistered.check_namespace_limit("ns2", "test")
        tracker_unregistered.check_load_balancer_limit("ns1", "lb1", "test")
        tracker_unregistered.check_dns_zone_limit("zone1.com", "test")
        tracker_unregistered.update_metric_cardinality("collector1", "metric1", 50)

        stats = tracker_unregistered.get_stats()

        assert stats["namespaces_tracked"] == 2
        assert stats["max_namespaces"] == 3
        assert stats["load_balancers_tracked"] == 1
        assert stats["max_load_balancers_per_namespace"] == 2
        assert stats["dns_zones_tracked"] == 1
        assert stats["max_dns_zones"] == 3
        assert stats["total_cardinality"] == 50
        assert stats["warn_threshold"] == 100


class TestCardinalityLimitEnforcement:
    """Tests for cardinality limit enforcement across collectors."""

    def test_namespace_limit_increments_exceeded_count(self, tracker_unregistered):
        """Test that exceeding namespace limit increments counter."""
        # Fill up to limit
        for i in range(3):
            tracker_unregistered.check_namespace_limit(f"ns{i}", "test")

        # Exceed limit multiple times
        tracker_unregistered.check_namespace_limit("ns3", "test")
        tracker_unregistered.check_namespace_limit("ns4", "test")

        assert tracker_unregistered.limits_exceeded["test_namespace"] == 2

    def test_load_balancer_limit_increments_exceeded_count(self, tracker_unregistered):
        """Test that exceeding LB limit increments counter."""
        # Fill up to limit
        tracker_unregistered.check_load_balancer_limit("ns1", "lb1", "test")
        tracker_unregistered.check_load_balancer_limit("ns1", "lb2", "test")

        # Exceed limit multiple times
        tracker_unregistered.check_load_balancer_limit("ns1", "lb3", "test")
        tracker_unregistered.check_load_balancer_limit("ns1", "lb4", "test")

        assert tracker_unregistered.limits_exceeded["test_load_balancer"] == 2

    def test_dns_zone_limit_increments_exceeded_count(self, tracker_unregistered):
        """Test that exceeding DNS zone limit increments counter."""
        # Fill up to limit
        for i in range(3):
            tracker_unregistered.check_dns_zone_limit(f"zone{i}.com", "test")

        # Exceed limit multiple times
        tracker_unregistered.check_dns_zone_limit("zone3.com", "test")
        tracker_unregistered.check_dns_zone_limit("zone4.com", "test")

        assert tracker_unregistered.limits_exceeded["test_dns_zone"] == 2

    def test_metrics_are_updated_on_limit_checks(self, tracker_unregistered):
        """Test that Prometheus metrics are updated when limits are checked."""
        # Check namespace limit
        tracker_unregistered.check_namespace_limit("ns1", "test")

        # Verify metrics are updated
        assert tracker_unregistered.total_tracked_namespaces._value.get() == 1

        # Check load balancer limit
        tracker_unregistered.check_load_balancer_limit("ns1", "lb1", "test")

        # Verify metrics are updated
        assert tracker_unregistered.total_tracked_load_balancers._value.get() == 1

        # Check DNS zone limit
        tracker_unregistered.check_dns_zone_limit("zone1.com", "test")

        # Verify metrics are updated
        assert tracker_unregistered.total_tracked_dns_zones._value.get() == 1
