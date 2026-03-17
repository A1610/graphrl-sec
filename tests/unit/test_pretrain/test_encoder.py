"""Unit tests for HeteroGraphEncoder."""

from __future__ import annotations

import torch
from torch_geometric.data import HeteroData

from src.models.pretrain.config import PretrainConfig
from src.models.pretrain.encoder import HeteroGraphEncoder

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph(
    n_host: int = 6,
    n_svc: int = 3,
    n_edges: int = 4,
) -> HeteroData:
    data = HeteroData()
    data["host"].x    = torch.randn(n_host, 8)
    data["service"].x = torch.randn(n_svc, 4)
    data["host", "connects_to", "host"].edge_index = torch.tensor(
        [[0, 1, 2, 3], [1, 2, 3, 4]], dtype=torch.long
    )[:, :n_edges]
    data["host", "uses_service", "service"].edge_index = torch.tensor(
        [[0, 1], [0, 1]], dtype=torch.long
    )
    return data


def _cfg(hidden: int = 32, layers: int = 2) -> PretrainConfig:
    return PretrainConfig(hidden_dim=hidden, num_layers=layers, projection_dim=16)


def _encoder(hidden: int = 32, layers: int = 2) -> HeteroGraphEncoder:
    data = _make_graph()
    return HeteroGraphEncoder(data.metadata(), _cfg(hidden, layers))


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestHeteroGraphEncoderInit:
    def test_builds_without_error(self) -> None:
        _encoder()

    def test_from_heterodata(self) -> None:
        data = _make_graph()
        enc  = HeteroGraphEncoder.from_heterodata(data, _cfg())
        assert isinstance(enc, HeteroGraphEncoder)

    def test_correct_number_of_conv_layers(self) -> None:
        enc = _encoder(layers=3)
        assert len(enc.convs) == 3

    def test_projection_head_exists(self) -> None:
        enc = _encoder()
        assert enc.proj_head is not None


# ---------------------------------------------------------------------------
# forward()
# ---------------------------------------------------------------------------


class TestHeteroGraphEncoderForward:
    def test_forward_returns_dict(self) -> None:
        data = _make_graph()
        enc  = _encoder()
        out  = enc(data.x_dict, data.edge_index_dict)
        assert isinstance(out, dict)

    def test_output_node_types_match_input(self) -> None:
        data = _make_graph()
        enc  = _encoder()
        out  = enc(data.x_dict, data.edge_index_dict)
        assert set(out.keys()) == set(data.x_dict.keys())

    def test_output_shape_matches_hidden_dim(self) -> None:
        data   = _make_graph(n_host=6, n_svc=3)
        hidden = 32
        enc    = _encoder(hidden=hidden)
        out    = enc(data.x_dict, data.edge_index_dict)
        assert out["host"].shape    == (6, hidden)
        assert out["service"].shape == (3, hidden)

    def test_output_is_float32(self) -> None:
        data = _make_graph()
        enc  = _encoder()
        out  = enc(data.x_dict, data.edge_index_dict)
        for h in out.values():
            assert h.dtype == torch.float32

    def test_no_nan_in_output(self) -> None:
        data = _make_graph()
        enc  = _encoder()
        out  = enc(data.x_dict, data.edge_index_dict)
        for h in out.values():
            assert not torch.isnan(h).any()

    def test_single_layer_works(self) -> None:
        data = _make_graph()
        enc  = _encoder(layers=1)
        out  = enc(data.x_dict, data.edge_index_dict)
        assert "host" in out


# ---------------------------------------------------------------------------
# project()
# ---------------------------------------------------------------------------


class TestHeteroGraphEncoderProject:
    def test_project_returns_dict(self) -> None:
        data = _make_graph()
        enc  = _encoder()
        out  = enc.project(data.x_dict, data.edge_index_dict)
        assert isinstance(out, dict)

    def test_project_output_shape_matches_proj_dim(self) -> None:
        data     = _make_graph(n_host=6, n_svc=3)
        proj_dim = 16
        enc      = _encoder()
        out      = enc.project(data.x_dict, data.edge_index_dict)
        assert out["host"].shape    == (6, proj_dim)
        assert out["service"].shape == (3, proj_dim)

    def test_projections_are_unit_norm(self) -> None:
        data = _make_graph()
        enc  = _encoder()
        out  = enc.project(data.x_dict, data.edge_index_dict)
        for h in out.values():
            norms = h.norm(dim=-1)
            assert torch.allclose(norms, torch.ones_like(norms), atol=1e-5)

    def test_no_nan_in_projections(self) -> None:
        data = _make_graph()
        enc  = _encoder()
        out  = enc.project(data.x_dict, data.edge_index_dict)
        for h in out.values():
            assert not torch.isnan(h).any()


# ---------------------------------------------------------------------------
# reset_parameters
# ---------------------------------------------------------------------------


class TestResetParameters:
    def test_reset_does_not_crash(self) -> None:
        enc = _encoder()
        enc.reset_parameters()
