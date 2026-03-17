"""Unit tests for NodeRegistry."""
from __future__ import annotations

import threading

import pytest

from src.graph.node_registry import Node, NodeRegistry, NodeType

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def registry() -> NodeRegistry:
    return NodeRegistry()


# ---------------------------------------------------------------------------
# get_or_create
# ---------------------------------------------------------------------------


class TestGetOrCreate:
    def test_creates_new_node(self, registry: NodeRegistry) -> None:
        node = registry.get_or_create(NodeType.HOST, "10.0.0.1")
        assert isinstance(node, Node)
        assert node.node_id == 0
        assert node.node_type == NodeType.HOST
        assert node.entity_key == "10.0.0.1"

    def test_returns_same_node_on_second_call(self, registry: NodeRegistry) -> None:
        n1 = registry.get_or_create(NodeType.HOST, "10.0.0.1")
        n2 = registry.get_or_create(NodeType.HOST, "10.0.0.1")
        assert n1 is n2

    def test_different_types_same_key_are_distinct(self, registry: NodeRegistry) -> None:
        n_host = registry.get_or_create(NodeType.HOST, "10.0.0.1")
        n_ext  = registry.get_or_create(NodeType.EXTERNAL_IP, "10.0.0.1")
        assert n_host.node_id != n_ext.node_id

    def test_ids_are_sequential(self, registry: NodeRegistry) -> None:
        ids = [registry.get_or_create(NodeType.HOST, f"10.0.0.{i}").node_id for i in range(5)]
        assert ids == list(range(5))

    def test_total_nodes_increments(self, registry: NodeRegistry) -> None:
        for i in range(3):
            registry.get_or_create(NodeType.HOST, f"10.0.0.{i}")
        assert registry.total_nodes == 3


# ---------------------------------------------------------------------------
# IP classification
# ---------------------------------------------------------------------------


class TestIPClassification:
    @pytest.mark.parametrize("ip,expected", [
        ("10.0.0.1",       NodeType.HOST),
        ("10.255.255.255",  NodeType.HOST),
        ("192.168.1.100",  NodeType.HOST),
        ("172.16.0.1",     NodeType.HOST),
        ("172.31.255.255", NodeType.HOST),
        ("127.0.0.1",      NodeType.HOST),
        ("8.8.8.8",        NodeType.EXTERNAL_IP),
        ("1.1.1.1",        NodeType.EXTERNAL_IP),
        ("203.0.113.1",    NodeType.EXTERNAL_IP),
    ])
    def test_classify_ip(self, ip: str, expected: NodeType) -> None:
        reg = NodeRegistry()
        node = reg.get_or_create_ip(ip)
        assert node.node_type == expected

    def test_external_ip_172_32(self) -> None:
        reg = NodeRegistry()
        node = reg.get_or_create_ip("172.32.0.1")
        assert node.node_type == NodeType.EXTERNAL_IP


# ---------------------------------------------------------------------------
# Service nodes
# ---------------------------------------------------------------------------


class TestServiceNodes:
    def test_creates_service_node(self, registry: NodeRegistry) -> None:
        node = registry.get_or_create_service(80, "TCP")
        assert node.node_type == NodeType.SERVICE
        assert "80" in node.entity_key
        assert "TCP" in node.entity_key

    def test_well_known_port_has_name(self, registry: NodeRegistry) -> None:
        node = registry.get_or_create_service(443, "TCP")
        assert "https" in node.entity_key.lower()

    def test_unknown_port_uses_port_prefix(self, registry: NodeRegistry) -> None:
        node = registry.get_or_create_service(12345, "TCP")
        assert "port-12345" in node.entity_key

    def test_same_port_protocol_returns_same_node(self, registry: NodeRegistry) -> None:
        n1 = registry.get_or_create_service(22, "TCP")
        n2 = registry.get_or_create_service(22, "TCP")
        assert n1 is n2

    def test_same_port_different_protocol_is_distinct(self, registry: NodeRegistry) -> None:
        n_tcp = registry.get_or_create_service(53, "TCP")
        n_udp = registry.get_or_create_service(53, "UDP")
        assert n_tcp.node_id != n_udp.node_id


# ---------------------------------------------------------------------------
# Domain and User nodes
# ---------------------------------------------------------------------------


class TestDomainUserNodes:
    def test_domain_lowercased(self, registry: NodeRegistry) -> None:
        node = registry.get_or_create_domain("Example.COM")
        assert node.entity_key == "example.com"

    def test_domain_trailing_dot_stripped(self, registry: NodeRegistry) -> None:
        node = registry.get_or_create_domain("example.com.")
        assert node.entity_key == "example.com"

    def test_user_lowercased(self, registry: NodeRegistry) -> None:
        node = registry.get_or_create_user("  Admin  ")
        assert node.entity_key == "admin"


# ---------------------------------------------------------------------------
# Bulk retrieval
# ---------------------------------------------------------------------------


class TestBulkRetrieval:
    def test_nodes_of_type(self, registry: NodeRegistry) -> None:
        registry.get_or_create_ip("10.0.0.1")
        registry.get_or_create_ip("10.0.0.2")
        registry.get_or_create_ip("8.8.8.8")
        hosts = registry.nodes_of_type(NodeType.HOST)
        assert len(hosts) == 2

    def test_all_nodes(self, registry: NodeRegistry) -> None:
        registry.get_or_create_ip("10.0.0.1")
        registry.get_or_create_service(80, "TCP")
        assert len(registry.all_nodes()) == 2

    def test_counts_by_type(self, registry: NodeRegistry) -> None:
        registry.get_or_create_ip("10.0.0.1")
        registry.get_or_create_ip("10.0.0.2")
        registry.get_or_create_ip("8.8.8.8")
        counts = registry.counts_by_type()
        assert counts["host"] == 2
        assert counts["external_ip"] == 1


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


class TestReset:
    def test_reset_clears_all(self, registry: NodeRegistry) -> None:
        registry.get_or_create_ip("10.0.0.1")
        registry.reset()
        assert registry.total_nodes == 0
        assert registry.all_nodes() == []

    def test_reset_resets_id_counter(self, registry: NodeRegistry) -> None:
        registry.get_or_create_ip("10.0.0.1")
        registry.reset()
        node = registry.get_or_create_ip("10.0.0.2")
        assert node.node_id == 0


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_inserts_no_duplicates(self) -> None:
        reg = NodeRegistry()
        results: list[int] = []
        lock = threading.Lock()

        def insert(i: int) -> None:
            node = reg.get_or_create(NodeType.HOST, f"10.0.0.{i % 5}")
            with lock:
                results.append(node.node_id)

        threads = [threading.Thread(target=insert, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should only have 5 unique nodes (10.0.0.0 .. 10.0.0.4)
        assert reg.total_nodes == 5
