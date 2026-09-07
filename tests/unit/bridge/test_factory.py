"""Tests for LiteBridge composition factory."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from evidenceops.bridge.factory import build_litebridge
from evidenceops.bridge.service import LiteBridge
from evidenceops.settings import Settings


def test_build_litebridge_wires_instance() -> None:
    settings = Settings(
        processed_data_dir=Path("data/processed"),
        bm25_data_dir=Path("data/bm25"),
        bm25_index_id="test_bm25_index",
    )
    with patch("evidenceops.bridge.factory.build_documentation_service") as mock_build_service:
        mock_service = MagicMock()
        mock_build_service.return_value = mock_service

        bridge = build_litebridge(settings)
        assert isinstance(bridge, LiteBridge)
        mock_build_service.assert_called_once_with(settings)
