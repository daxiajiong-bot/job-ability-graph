"""Parsing API routes."""

from __future__ import annotations

import base64
import binascii
import json
import os
from datetime import datetime
from typing import Any, Dict, List
from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.app.input_adapters.document_text import DocumentExtractionError, extract_text_from_bytes
from backend.app.schemas.jd import JDParseRequest, JDParseResponse
from backend.app.schemas.resume import ResumeDocumentParseRequest, ResumeDocumentParseResponse, ResumeParseRequest, ResumeParseResponse
from backend.app.services.ingest_service import load_samples
from backend.app.services.parse_service import parse_jd_profile, parse_resume_profile


router = APIRouter()

# 数据目录路径（从 routes_parse.py 往上4级到项目根目录）
DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
JD_PROFILES_DIR = DATA_DIR / "parsed" / "jd_profiles"
RESUME_PROFILES_DIR = DATA_DIR / "parsed" / "resume_profiles"


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


@router.get("/parse/jd/list")
def get_parsed_jd_list() -> List[Dict[str, Any]]:
    """获取所有已解析的JD记录列表"""
    try:
        if not JD_PROFILES_DIR.exists():
            return []

        jd_list = []
        for file_path in sorted(JD_PROFILES_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # 提取关键信息用于列表展示
                profile = data.get("profile", {})
                jd_parse = profile.get("jd_parse", {})

                job_title = jd_parse.get("job_title", "未知岗位")
                job_category = jd_parse.get("job_category", "未分类")

                # 统计技能数量
                skills = profile.get("skills", [])
                skill_count = len(skills)

                # 获取创建时间
                created_at = data.get("created_at", "")
                if created_at:
                    try:
                        dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        created_time = dt.strftime("%Y-%m-%d %H:%M")
                    except:
                        created_time = created_at[:16]
                else:
                    created_time = "未知时间"

                jd_list.append({
                    "doc_id": data.get("doc_id", ""),
                    "file_name": file_path.name,
                    "job_title": job_title,
                    "job_category": job_category,
                    "skill_count": skill_count,
                    "created_at": created_at,
                    "created_at_raw": created_at,
                    # 保存完整数据供后续使用
                    "full_data": profile
                })

            except Exception as e:
                print(f"Error reading {file_path}: {e}")
                continue

        return jd_list

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load JD list: {str(e)}")


@router.get("/parse/resume/list")
def get_parsed_resume_list() -> List[Dict[str, Any]]:
    """获取所有已解析的简历记录列表"""
    try:
        if not RESUME_PROFILES_DIR.exists():
            return []

        resume_list = []
        for file_path in sorted(RESUME_PROFILES_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # 提取关键信息用于列表展示
                profile = data.get("profile", {})
                resume_parse = profile.get("resume_parse", {})

                candidate_id = resume_parse.get("candidate_id", "未知候选人")
                education = resume_parse.get("education", "未知学历")
                experience_years = resume_parse.get("experience_years")

                # 统计技能数量
                skills = profile.get("skills", [])
                skill_count = len(skills)

                # 获取创建时间
                created_at = data.get("created_at", "")
                if created_at:
                    try:
                        dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        created_time = dt.strftime("%Y-%m-%d %H:%M")
                    except:
                        created_time = created_at[:16]
                else:
                    created_time = "未知时间"

                resume_list.append({
                    "doc_id": data.get("doc_id", ""),
                    "file_name": file_path.name,
                    "candidate_id": candidate_id,
                    "education": education,
                    "experience_years": experience_years,
                    "skill_count": skill_count,
                    "created_at": created_time,
                    "created_at_raw": created_at,
                    # 保存完整数据供后续使用
                    "full_data": profile
                })

            except Exception as e:
                print(f"Error reading {file_path}: {e}")
                continue

        return resume_list

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load resume list: {str(e)}")


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
