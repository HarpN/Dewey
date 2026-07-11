from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MandateMetadata(BaseModel):
    issuer_id: str = Field(..., min_length=1, max_length=128)
    key_id: str = Field(..., min_length=1, max_length=128)
    issued_at: str = Field(..., min_length=1, max_length=64)
    expires_at: str = Field(..., min_length=1, max_length=64)
    nonce: str = Field(..., min_length=8, max_length=128)
    correlation_id: str = Field(..., min_length=1, max_length=128)


class MandatedAction(BaseModel):
    target_table: str = Field(..., min_length=1, max_length=128)
    action_type: str = Field(..., min_length=1, max_length=128)
    entity_id: str = Field(..., min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)


class ExecutionMandate(BaseModel):
    mandate_metadata: MandateMetadata
    council_verdict: str = Field(..., min_length=1, max_length=64)
    mandated_action: MandatedAction
    rationale: str = Field(default="", max_length=2000)
