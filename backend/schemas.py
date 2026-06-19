from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class JDRecord(BaseModel):
    source_type: str = "job_platform"
    source_name: str
    job_title: str
    company_name: Optional[str] = None
    industry: Optional[str] = None
    location: Optional[str] = None
    salary_min: Optional[str] = None
    salary_max: Optional[str] = None
    experience: Optional[str] = None
    education: Optional[str] = None
    publish_date: Optional[str] = None
    jd_text: str = ""
    responsibilities: List[str] = Field(default_factory=list)
    requirements: List[str] = Field(default_factory=list)
    skills_raw: List[str] = Field(default_factory=list)
    skills_norm: List[str] = Field(default_factory=list)
    url: Optional[str] = None
    scrape_time: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class ResumeRecord(BaseModel):
    education: Optional[str] = None
    experience_years: Optional[int] = None
    skills: List[str] = Field(default_factory=list)
    projects: List[dict] = Field(default_factory=list)


class MatchResult(BaseModel):
    match_score: float
    matched_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    explanation: str
