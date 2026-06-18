"""Backward-compatible schema exports for older imports."""

from __future__ import annotations

from backend.app.schemas.evolution import EmergingJobRequest, PositionUpdateRequest as JobCompareRequest, SourceDocumentRequest
from backend.app.schemas.graph import FlexibleResponse, JobGraphDocumentRequest, PanoramaGraphRequest
from backend.app.schemas.jd import JDParseRequest, JDParseResponse
from backend.app.schemas.match import MatchRequest, MatchResponse
from backend.app.schemas.resume import ResumeDocumentParseRequest, ResumeDocumentParseResponse, ResumeParseRequest, ResumeParseResponse

__all__ = [
    "EmergingJobRequest",
    "FlexibleResponse",
    "JDParseRequest",
    "JDParseResponse",
    "JobCompareRequest",
    "JobGraphDocumentRequest",
    "MatchRequest",
    "MatchResponse",
    "PanoramaGraphRequest",
    "ResumeDocumentParseRequest",
    "ResumeDocumentParseResponse",
    "ResumeParseRequest",
    "ResumeParseResponse",
    "SourceDocumentRequest",
]
