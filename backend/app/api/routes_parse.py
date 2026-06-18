"""Parsing API routes."""

from __future__ import annotations

import base64
import binascii
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from backend.app.input_adapters.document_text import DocumentExtractionError, extract_text_from_bytes
from backend.app.schemas.jd import JDParseRequest, JDParseResponse
from backend.app.schemas.resume import ResumeDocumentParseRequest, ResumeDocumentParseResponse, ResumeParseRequest, ResumeParseResponse
from backend.app.services.ingest_service import load_samples
from backend.app.services.parse_service import parse_jd_profile, parse_resume_profile


router = APIRouter()


def _payload_text(payload: Any, legacy_field: str) -> str:
    text = (getattr(payload, "text", None) or getattr(payload, legacy_field, None) or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail=f"text or {legacy_field} must not be empty")
    return text


@router.get("/samples")
def samples() -> Dict[str, Any]:
    try:
        return load_samples()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="sample data not found") from exc


@router.post("/parse/jd", response_model=JDParseResponse)
def parse_jd_endpoint(payload: JDParseRequest) -> JDParseResponse:
    try:
        result = parse_jd_profile(_payload_text(payload, "jd_text"), use_llm=payload.use_llm)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="failed to parse jd") from exc
    return JDParseResponse(**result)


@router.post("/parse/resume", response_model=ResumeParseResponse)
def parse_resume_endpoint(payload: ResumeParseRequest) -> ResumeParseResponse:
    try:
        result = parse_resume_profile(_payload_text(payload, "resume_text"), use_llm=payload.use_llm)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="failed to parse resume") from exc
    return ResumeParseResponse(**result)


@router.post("/parse/resume-document", response_model=ResumeDocumentParseResponse)
def parse_resume_document_endpoint(payload: ResumeDocumentParseRequest) -> ResumeDocumentParseResponse:
    try:
        content = base64.b64decode(payload.content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="content_base64 must be valid base64") from exc

    try:
        document_text = extract_text_from_bytes(content, filename=payload.filename)
        result = parse_resume_profile(document_text.text, use_llm=payload.use_llm)
    except DocumentExtractionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="failed to parse resume document") from exc

    return ResumeDocumentParseResponse(
        document={**document_text.metadata, "text_preview": document_text.text[:500]},
        resume_parse=result.get("resume_parse", {}),
        resume_profile=result.get("resume_profile", {}),
        llm=result.get("llm", {}),
        competition_hooks=result.get("competition_hooks", {}),
    )
