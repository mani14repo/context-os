from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(UTC)


class MemoryType(StrEnum):
    WORKING = "working"
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    OPERATIONAL = "operational"
    PROCEDURAL = "procedural"
    ARTIFACT = "artifact"


class StorageTier(StrEnum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"
    ARCHIVE = "archive"


class CompressionLevel(StrEnum):
    METADATA = "metadata"
    ONE_LINE = "one_line"
    COMPACT = "compact"
    DETAILED = "detailed"
    FULL = "full"
    ORIGINAL = "original"


class Classification(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class ContextRepresentation(BaseModel):
    level: CompressionLevel
    content: str | None = None
    content_pointer: str | None = None
    token_count: int | None = None
    tokens_saved: int | None = Field(
        default=None,
        description="Tokens this representation omits relative to the node's "
        "original content, if the Compactor computed one; 0 for levels that don't "
        "actually compact (FULL/ORIGINAL).",
    )
    created_at: datetime = Field(default_factory=utcnow)


class ContextNode(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    node_type: str
    memory_type: MemoryType
    title: str | None = None
    summary: str | None = None
    content: str | None = None
    content_pointer: str | None = None
    storage_tier: StorageTier = StorageTier.WARM
    importance: float = Field(default=0.5, ge=0, le=1)
    confidence: float = Field(default=1.0, ge=0, le=1)
    source_authority: float = Field(default=0.5, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    representations: list[ContextRepresentation] = Field(default_factory=list)
    valid_from: datetime = Field(default_factory=utcnow)
    valid_to: datetime | None = None
    version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    classification: Classification = Classification.INTERNAL
    retention_until: datetime | None = Field(
        default=None, description="Eligible for deletion by apply_retention_policy() after this instant."
    )
    legal_hold: bool = Field(
        default=False, description="Blocks delete_node() regardless of retention_until."
    )


class ContextEdge(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    source_node_id: UUID
    target_node_id: UUID
    relationship: str
    confidence: float = Field(default=1.0, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    valid_from: datetime = Field(default_factory=utcnow)
    valid_to: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class ContextQuery(BaseModel):
    tenant_id: str
    query: str
    memory_types: set[MemoryType] = Field(default_factory=set)
    tiers: set[StorageTier] = Field(default_factory=set)
    node_types: set[str] = Field(default_factory=set)
    entity_ids: set[UUID] = Field(default_factory=set)
    max_results: int = Field(default=20, ge=1, le=200)
    minimum_confidence: float = Field(default=0.0, ge=0, le=1)
    graph_depth: int = Field(default=1, ge=0, le=5)
    as_of: datetime | None = Field(
        default=None,
        description="Only match nodes valid at this instant; defaults to now.",
    )


class ContextRequest(BaseModel):
    tenant_id: str
    task: str
    agent: str
    memory_scopes: set[MemoryType] = Field(default_factory=set)
    token_budget: int = Field(default=6000, ge=256)
    minimum_confidence: float = Field(default=0.0, ge=0, le=1)
    graph_depth: int = Field(default=1, ge=0, le=5)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RankedContext(BaseModel):
    node: ContextNode
    score: float
    reasons: list[str] = Field(default_factory=list)


class ContextPackage(BaseModel):
    request: ContextRequest
    items: list[RankedContext]
    token_count: int
    tokens_saved: int = Field(
        default=0,
        description="Sum of tokens_saved across the compacted representations "
        "actually used in this package, vs. each item's original content.",
    )
    missing_context: list[str] = Field(default_factory=list)
    provenance: list[UUID] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utcnow)
