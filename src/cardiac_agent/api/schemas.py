"""Request and response models.

Typed at the boundary so a malformed request fails with a clear 422 rather than
somewhere inside the scoring engine, and so the OpenAPI schema at ``/docs`` is
accurate enough to be the API documentation.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Level = Literal[
    "segment",
    "sub_segment",
    "molecule_class",
    "molecule_combination",
    "treatment_archetype",
    "anchor_molecule",
]

RankBy = Literal[
    "cipla_priority_score", "market_opportunity_index", "value_t2", "value_yoy"
]


class AskRequest(BaseModel):
    """A question for the agent."""

    question: str = Field(..., min_length=3, max_length=2000)
    include_evidence: bool = Field(
        default=False, description="Return the raw tool results alongside the answer."
    )
    include_trace: bool = Field(
        default=True, description="Return the execution trace for auditing."
    )


class Citation(BaseModel):
    id: str
    title: str
    publisher: str
    source: str
    url: str
    published: str
    accessed: str
    confidence: str
    type: str


class AskResponse(BaseModel):
    """The agent's answer plus its audit trail."""

    answer: str
    citations: list[Citation] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    deterministic: bool = Field(
        default=False,
        description="True when the answer was rendered without a language model.",
    )
    warnings: list[str] = Field(default_factory=list)
    trace: dict[str, Any] | None = None
    evidence: dict[str, Any] | None = None


class RankRequest(BaseModel):
    level: Level = "molecule_combination"
    rank_by: RankBy = "cipla_priority_score"
    top_n: int = Field(default=10, ge=1, le=50)
    min_value_cr: float | None = Field(default=None, ge=0)


class ForecastRequest(BaseModel):
    space: str = Field(..., min_length=2)
    level: Level | None = None
    horizon_years: int = Field(default=5, ge=1, le=10)


class SensitivityRequest(BaseModel):
    level: Level = "molecule_combination"
    top_k: int = Field(default=5, ge=3, le=10)
    iterations: int | None = Field(default=None, ge=50, le=2000)


class SignalSearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)
    top_k: int = Field(default=5, ge=1, le=10)


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    warehouse_built: bool
    spaces_scored: int
    signals_loaded: int
    llm_provider: str
    llm_available: bool
    market_value_cr: float | None = None
    as_of: str | None = None
    detail: str | None = None


__all__ = [
    "AskRequest",
    "AskResponse",
    "Citation",
    "ForecastRequest",
    "HealthResponse",
    "Level",
    "RankBy",
    "RankRequest",
    "SensitivityRequest",
    "SignalSearchRequest",
]
