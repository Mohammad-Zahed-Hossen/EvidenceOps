"""Tests for LiteBridge composition factory."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from evidenceops.bridge.contracts import (
    ExecutionProfile,
    PrivacyClassification,
    SourceFreshness,
    SourceKind,
)
from evidenceops.bridge.factory import build_litebridge
from evidenceops.bridge.service import LiteBridge
from evidenceops.settings import Settings


def test_build_litebridge_wires_registry_and_default_source() -> None:
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

        assert bridge._source_registry is not None
        descriptor, retriever = bridge._source_registry.resolve(None, ExecutionProfile.LOCAL_ONLY)

        assert descriptor.source_id == "evidenceops_local_docs"
        assert descriptor.adapter_id == "evidenceops_local"
        assert descriptor.display_name == "EvidenceOps Local Documentation"
        assert descriptor.source_kind == SourceKind.LOCAL_DOCUMENT
        assert descriptor.enabled is True
        assert descriptor.privacy_classification == PrivacyClassification.PRIVATE
        assert descriptor.freshness == SourceFreshness.SNAPSHOT
        assert descriptor.citation_required is True
        assert descriptor.max_response_chars == 24000
        assert descriptor.timeout_ms == 5000
        assert descriptor.max_retries == 0
        assert descriptor.source_version is None


def test_build_litebridge_web_disabled_by_default() -> None:
    settings = Settings(
        processed_data_dir=Path("data/processed"),
        bm25_data_dir=Path("data/bm25"),
        bm25_index_id="test_bm25_index",
        litebridge_enable_tavily_web=False,
    )
    with patch("evidenceops.bridge.factory.build_documentation_service"):
        bridge = build_litebridge(settings)
        assert bridge._source_registry is not None
        assert "tavily_web_search" not in bridge._source_registry._registrations


def test_build_litebridge_web_enabled_missing_key_raises() -> None:
    from evidenceops.bridge.errors import LiteBridgeSourceError

    settings = Settings(
        processed_data_dir=Path("data/processed"),
        bm25_data_dir=Path("data/bm25"),
        bm25_index_id="test_bm25_index",
        litebridge_enable_tavily_web=True,
        tavily_api_key=None,
    )
    with patch("evidenceops.bridge.factory.build_documentation_service"):
        import pytest

        with pytest.raises(LiteBridgeSourceError) as exc_info:
            build_litebridge(settings)
        assert "TAVILY_API_KEY is missing or empty" in str(exc_info.value)


def test_build_litebridge_web_enabled_wires_web_source() -> None:
    from pydantic import SecretStr

    from evidenceops.bridge.contracts import SourcePolicy

    settings = Settings(
        processed_data_dir=Path("data/processed"),
        bm25_data_dir=Path("data/bm25"),
        bm25_index_id="test_bm25_index",
        litebridge_enable_tavily_web=True,
        tavily_api_key=SecretStr("tvly_valid_test_key"),
        litebridge_web_allowed_fetch_domains="docs.python.org,fastapi.tiangolo.com",
    )
    with patch("evidenceops.bridge.factory.build_documentation_service"):
        bridge = build_litebridge(settings)
        assert bridge._source_registry is not None
        desc, retriever = bridge._source_registry.resolve(
            SourcePolicy(allowed_source_ids=("tavily_web_search",)),
            ExecutionProfile.HYBRID,
        )
        assert desc.source_id == "tavily_web_search"
        assert desc.source_kind == SourceKind.WEB_SEARCH_SNIPPET
        assert desc.privacy_classification == PrivacyClassification.PUBLIC_WEB
        assert desc.freshness == SourceFreshness.LIVE
        assert desc.supported_execution_profiles == (ExecutionProfile.HYBRID,)
