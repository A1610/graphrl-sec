"""Unit tests for Neo4j SchemaManager.

All tests use MagicMock to avoid requiring a live Neo4j instance.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.graph.neo4j_schema import (
    _CONSTRAINTS,
    _NODE_INDEXES,
    _REL_INDEXES,
    SchemaManager,
    SchemaStatus,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_driver() -> MagicMock:
    """A MagicMock neo4j driver whose session context manager works."""
    driver = MagicMock()
    session = MagicMock()
    driver.session.return_value.__enter__ = MagicMock(return_value=session)
    driver.session.return_value.__exit__  = MagicMock(return_value=False)
    return driver


@pytest.fixture()
def manager(mock_driver: MagicMock) -> SchemaManager:
    """SchemaManager with a patched neo4j driver."""
    with patch("src.graph.neo4j_schema.GraphDatabase.driver", return_value=mock_driver):
        mgr = SchemaManager()
    mgr._driver = mock_driver
    return mgr


# ---------------------------------------------------------------------------
# Constant integrity
# ---------------------------------------------------------------------------


class TestSchemaConstants:
    def test_constraints_not_empty(self) -> None:
        assert len(_CONSTRAINTS) > 0

    def test_node_indexes_not_empty(self) -> None:
        assert len(_NODE_INDEXES) > 0

    def test_rel_indexes_not_empty(self) -> None:
        assert len(_REL_INDEXES) > 0

    def test_constraint_names_unique(self) -> None:
        names = [c[0] for c in _CONSTRAINTS]
        assert len(names) == len(set(names)), "Duplicate constraint names"

    def test_index_names_unique(self) -> None:
        all_names = [ix[0] for ix in _NODE_INDEXES + _REL_INDEXES]
        assert len(all_names) == len(set(all_names)), "Duplicate index names"

    def test_all_node_types_have_constraint(self) -> None:
        labels = {c[1] for c in _CONSTRAINTS}
        expected = {"Host", "ExternalIP", "Service", "Domain", "User"}
        assert expected == labels

    def test_constraint_property_is_entity_key(self) -> None:
        for _, _, prop in _CONSTRAINTS:
            assert prop == "entity_key", f"Constraint property should be entity_key, got {prop!r}"


# ---------------------------------------------------------------------------
# SchemaStatus
# ---------------------------------------------------------------------------


class TestSchemaStatus:
    def test_total_applied(self) -> None:
        s = SchemaStatus(
            constraints_applied=5,
            node_indexes_applied=7,
            rel_indexes_applied=2,
            errors=0,
        )
        assert s.total_applied == 14

    def test_frozen(self) -> None:
        s = SchemaStatus(constraints_applied=1, node_indexes_applied=1, rel_indexes_applied=1, errors=0)
        with pytest.raises(AttributeError):
            s.constraints_applied = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SchemaManager.ping
# ---------------------------------------------------------------------------


class TestSchemaManagerPing:
    def test_ping_success(self, manager: SchemaManager, mock_driver: MagicMock) -> None:
        assert manager.ping() is True

    def test_ping_failure(self, manager: SchemaManager, mock_driver: MagicMock) -> None:
        from neo4j.exceptions import ServiceUnavailable
        mock_driver.session.side_effect = ServiceUnavailable("down")
        assert manager.ping() is False


# ---------------------------------------------------------------------------
# SchemaManager.setup
# ---------------------------------------------------------------------------


class TestSchemaManagerSetup:
    def test_setup_returns_schema_status(self, manager: SchemaManager) -> None:
        result = manager.setup()
        assert isinstance(result, SchemaStatus)

    def test_setup_applies_all_constraints(self, manager: SchemaManager) -> None:
        result = manager.setup()
        assert result.constraints_applied == len(_CONSTRAINTS)

    def test_setup_applies_all_node_indexes(self, manager: SchemaManager) -> None:
        result = manager.setup()
        assert result.node_indexes_applied == len(_NODE_INDEXES)

    def test_setup_applies_all_rel_indexes(self, manager: SchemaManager) -> None:
        result = manager.setup()
        assert result.rel_indexes_applied == len(_REL_INDEXES)

    def test_setup_zero_errors_on_success(self, manager: SchemaManager) -> None:
        result = manager.setup()
        assert result.errors == 0

    def test_setup_session_run_called_for_each_ddl(
        self,
        manager: SchemaManager,
        mock_driver: MagicMock,
    ) -> None:
        manager.setup()
        session = mock_driver.session.return_value.__enter__.return_value
        expected_calls = len(_CONSTRAINTS) + len(_NODE_INDEXES) + len(_REL_INDEXES)
        assert session.run.call_count == expected_calls

    def test_setup_already_exists_not_counted_as_error(
        self,
        manager: SchemaManager,
        mock_driver: MagicMock,
    ) -> None:
        from neo4j.exceptions import ClientError
        session = mock_driver.session.return_value.__enter__.return_value
        # All DDL raises "already exists" ClientError
        session.run.side_effect = ClientError("already exists")
        result = manager.setup()
        # Should NOT count already-exists as errors
        assert result.errors == 0

    def test_setup_unexpected_error_counted(
        self,
        manager: SchemaManager,
        mock_driver: MagicMock,
    ) -> None:
        from neo4j.exceptions import ClientError
        session = mock_driver.session.return_value.__enter__.return_value
        # All DDL raises an unexpected error
        session.run.side_effect = ClientError("some unexpected error from Neo4j")
        result = manager.setup()
        assert result.errors > 0


# ---------------------------------------------------------------------------
# SchemaManager.drop_all
# ---------------------------------------------------------------------------


class TestSchemaManagerDropAll:
    def test_drop_all_runs_without_error(self, manager: SchemaManager) -> None:
        manager.drop_all()   # should not raise

    def test_drop_all_calls_drop_for_each_object(
        self,
        manager: SchemaManager,
        mock_driver: MagicMock,
    ) -> None:
        manager.drop_all()
        session = mock_driver.session.return_value.__enter__.return_value
        total = len(_CONSTRAINTS) + len(_NODE_INDEXES) + len(_REL_INDEXES)
        assert session.run.call_count == total


# ---------------------------------------------------------------------------
# SchemaManager lifecycle
# ---------------------------------------------------------------------------


class TestSchemaManagerLifecycle:
    def test_context_manager_calls_close(self, mock_driver: MagicMock) -> None:
        with patch("src.graph.neo4j_schema.GraphDatabase.driver", return_value=mock_driver), SchemaManager():
            pass
        mock_driver.close.assert_called_once()

    def test_close_closes_driver(self, manager: SchemaManager, mock_driver: MagicMock) -> None:
        manager.close()
        mock_driver.close.assert_called_once()
