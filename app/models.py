from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MandateMetadata(BaseModel):
    issuer_id: str = Field(..., min_length=1)
    key_id: str = Field(..., min_length=1)
    issued_at: str = Field(..., min_length=1)
    expires_at: str = Field(..., min_length=1)
    nonce: str = Field(..., min_length=8)
    correlation_id: str = Field(..., min_length=1)


class MandatedAction(BaseModel):
    target_table: str = Field(..., min_length=1)
    action_type: str = Field(..., min_length=1)
    entity_id: str = Field(..., min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class ExecutionMandate(BaseModel):
    mandate_metadata: MandateMetadata
    council_verdict: str = Field(..., min_length=1)
    mandated_action: MandatedAction
    rationale: str = Field(default="")
