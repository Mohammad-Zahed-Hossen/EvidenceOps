"""FastAPI routes exposing safe, bounded LiteBridge endpoints under /v1/litebridge."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from evidenceops.bridge.contracts import (
    CompressionPolicy,
    ExecutionProfile,
    GenerationPolicy,
    ProviderLocation,
    RetrievalPolicy,
    SourceKind,
    SourcePolicy,
    WebRetrievalPolicy,
)
from evidenceops.bridge.package_store import InterfacePackageStore
from evidenceops.bridge.sdk import LiteBridgeSDK
from evidenceops.settings import Settings, get_settings

router = APIRouter(prefix="/litebridge", tags=["litebridge"])


class PrepareContextApiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1)
    execution_profile: ExecutionProfile = ExecutionProfile.LOCAL_ONLY
    source_id: str | None = None
    max_evidence_items: int = Field(default=6, ge=1, le=20)
    max_context_chars: int = Field(default=24000, ge=1, le=100000)
    max_estimated_tokens: int = Field(default=6000, ge=1, le=25000)
    allow_external_query: bool = False


class CompressContextApiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_max_context_chars: int | None = Field(default=None, ge=1)
    target_max_estimated_tokens: int | None = Field(default=None, ge=1)
    max_sentences_per_evidence: int | None = Field(default=None, ge=1)
    deduplicate_exact_retrieval_copies: bool = True
    allow_evidence_drop: bool = True


class AnswerApiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(..., min_length=1)
    max_output_tokens: int = Field(default=512, ge=1, le=4096)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    allow_external_generation: bool = False
    allow_private_evidence_export: bool = False


def _get_settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_settings()


def _get_sdk(request: Request) -> LiteBridgeSDK:
    sdk = getattr(request.app.state, "litebridge_sdk", None)
    if sdk is None:
        from evidenceops.bridge.factory import build_litebridge

        bridge = build_litebridge()
        sdk = LiteBridgeSDK(bridge)
        request.app.state.litebridge_sdk = sdk
    return sdk


def _get_package_store(request: Request) -> InterfacePackageStore:
    store = getattr(request.app.state, "litebridge_package_store", None)
    if store is None:
        settings = _get_settings(request)
        store = InterfacePackageStore(
            ttl_seconds=settings.litebridge_interface_package_ttl_seconds,
            max_entries=settings.litebridge_interface_package_max_entries,
        )
        request.app.state.litebridge_package_store = store
    return store


SettingsDep = Annotated[Settings, Depends(_get_settings)]
SdkDep = Annotated[LiteBridgeSDK, Depends(_get_sdk)]
StoreDep = Annotated[InterfacePackageStore, Depends(_get_package_store)]


@router.post("/context", status_code=status.HTTP_200_OK)
async def prepare_context_endpoint(
    body: PrepareContextApiRequest,
    settings: SettingsDep,
    sdk: SdkDep,
    store: StoreDep,
) -> dict[str, Any]:
    """Prepare grounded context package and return an opaque context handle."""
    if body.allow_external_query or body.execution_profile == ExecutionProfile.HYBRID:
        if not settings.litebridge_interface_allow_external_retrieval:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="External web retrieval is disabled on this server.",
            )

    web_policy = None
    if body.allow_external_query and body.execution_profile == ExecutionProfile.HYBRID:
        web_policy = WebRetrievalPolicy(allow_external_query=True)

    policy = RetrievalPolicy(
        execution_profile=body.execution_profile,
        max_evidence_items=body.max_evidence_items,
        max_context_chars=body.max_context_chars,
        max_estimated_tokens=body.max_estimated_tokens,
        web=web_policy,
    )
    source_policy = SourcePolicy(allowed_source_ids=(body.source_id,)) if body.source_id else None

    package = sdk.prepare_context(
        body.query,
        policy=policy,
        source_policy=source_policy,
    )
    handle = store.put(package)
    return {
        "context_handle": handle,
        "package": package.model_dump(),
    }


@router.get("/context/{context_handle}", status_code=status.HTTP_200_OK)
async def get_context_endpoint(
    context_handle: str,
    store: StoreDep,
) -> dict[str, Any]:
    """Retrieve an active context package by its opaque server handle."""
    package = store.get(context_handle)
    return package.model_dump()


@router.post("/context/{context_handle}/compress", status_code=status.HTTP_200_OK)
async def compress_context_endpoint(
    context_handle: str,
    body: CompressContextApiRequest,
    sdk: SdkDep,
    store: StoreDep,
) -> dict[str, Any]:
    """Compress an active context package, returning a new opaque handle."""
    parent_package = store.get(context_handle)
    policy_kwargs: dict[str, Any] = {
        "deduplicate_exact_retrieval_copies": body.deduplicate_exact_retrieval_copies,
        "allow_evidence_drop": body.allow_evidence_drop,
    }
    if body.target_max_context_chars is not None:
        policy_kwargs["target_max_context_chars"] = body.target_max_context_chars
    if body.target_max_estimated_tokens is not None:
        policy_kwargs["target_max_estimated_tokens"] = body.target_max_estimated_tokens
    if body.max_sentences_per_evidence is not None:
        policy_kwargs["max_sentences_per_evidence"] = body.max_sentences_per_evidence

    compression_policy = CompressionPolicy(**policy_kwargs)
    compressed_package = sdk.compress_context(
        parent_package,
        compression_policy=compression_policy,
    )
    new_handle = store.put(compressed_package)
    return {
        "context_handle": new_handle,
        "package": compressed_package.model_dump(),
    }


@router.post("/context/{context_handle}/answer", status_code=status.HTTP_200_OK)
async def answer_endpoint(
    context_handle: str,
    body: AnswerApiRequest,
    settings: SettingsDep,
    sdk: SdkDep,
    store: StoreDep,
) -> dict[str, Any]:
    """Synthesize a grounded answer from an active context package."""
    package = store.get(context_handle)
    capabilities = sdk.list_capabilities()
    prov_cap = next(
        (p for p in capabilities.providers if p.provider_id == body.provider_id),
        None,
    )

    if prov_cap is not None and prov_cap.location == ProviderLocation.HOSTED:
        if not settings.litebridge_interface_allow_external_generation:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="External generation is disabled on this server.",
            )
        has_private = any(rec.source_kind == SourceKind.LOCAL_DOCUMENT for rec in package.evidence)
        if has_private:
            if not settings.litebridge_interface_allow_private_evidence_export:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Private evidence export is disabled on this server.",
                )
            if not body.allow_private_evidence_export:
                msg = "Private evidence export requires client allow_private_evidence_export=True."
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=msg,
                )
        if not body.allow_external_generation:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="External generation requires client allow_external_generation=True.",
            )

    generation_policy = GenerationPolicy(
        provider_id=body.provider_id,
        max_output_tokens=body.max_output_tokens,
        temperature=body.temperature,
        allow_external_generation=body.allow_external_generation,
        allow_private_evidence_export=body.allow_private_evidence_export,
    )
    answer_obj = sdk.answer(
        package,
        generation_policy=generation_policy,
    )
    return answer_obj.model_dump()


@router.get("/capabilities", status_code=status.HTTP_200_OK)
async def list_capabilities_endpoint(
    sdk: SdkDep,
) -> dict[str, Any]:
    """List sanitized capability metadata for registered sources and generation providers."""
    caps = sdk.list_capabilities()
    return {
        "sources": [
            {
                "source_id": s.source_id,
                "display_name": s.display_name,
                "source_kind": (
                    s.source_kind.value if hasattr(s.source_kind, "value") else str(s.source_kind)
                ),
                "enabled": s.enabled,
                "privacy_classification": (
                    s.privacy_classification.value
                    if hasattr(s.privacy_classification, "value")
                    else str(s.privacy_classification)
                ),
                "freshness": (
                    s.freshness.value if hasattr(s.freshness, "value") else str(s.freshness)
                ),
                "supported_execution_profiles": [
                    p.value if hasattr(p, "value") else str(p)
                    for p in s.supported_execution_profiles
                ],
            }
            for s in caps.sources
        ],
        "providers": [
            {
                "provider_id": p.provider_id,
                "display_name": p.display_name,
                "location": (p.location.value if hasattr(p.location, "value") else str(p.location)),
                "model_id": p.model_id,
                "supports_citations": p.supports_citations,
                "max_output_tokens": p.max_output_tokens,
                "enabled": p.enabled,
            }
            for p in caps.providers
        ],
    }
