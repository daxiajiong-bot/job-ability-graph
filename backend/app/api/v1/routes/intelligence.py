"""Resource endpoints that expose future intelligence seams as explicit mocks."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, Request, status

from backend.app.api.v1.dependencies import get_facade
from backend.app.api.v1.errors import success
from backend.app.api.v1.schemas.common import SuccessEnvelope
from backend.app.api.v1.schemas.resources import (
    AutoMatchRequest,
    DocumentRetrievalRequest,
    GraphRetrievalRequest,
    KnowledgeGraphCreateRequest,
    LearningAdviceRequest,
    MatchCreateRequest,
    PositionDeltaRequest,
    PositionDiscoveryRequest,
    ReportCreateRequest,
)
from backend.app.application.use_cases.contract_facade import ContractFacade


router = APIRouter(tags=["Intelligence contracts"])


@router.post("/document-retrievals", response_model=SuccessEnvelope)
def retrieve_document_evidence(
    payload: DocumentRetrievalRequest,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    result = facade.retrieve_document_evidence(payload.query, payload.document_ids, payload.filters)
    return success(request, {"retrieval": result})


@router.post("/knowledge-graphs", response_model=SuccessEnvelope, status_code=status.HTTP_201_CREATED)
def create_knowledge_graph(
    payload: KnowledgeGraphCreateRequest,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    graph = facade.create_knowledge_graph(payload.document_ids, payload.candidate_profile_ids, payload.job_profile_ids)
    return success(request, {"knowledge_graph": graph})


@router.get("/knowledge-graphs/{graph_id}", response_model=SuccessEnvelope)
def get_knowledge_graph(
    graph_id: str,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    return success(request, {"knowledge_graph": facade.get_knowledge_graph(graph_id)})


@router.post("/graph-retrievals", response_model=SuccessEnvelope)
def retrieve_graph_evidence(
    graph_id: str,
    payload: GraphRetrievalRequest,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    result = facade.retrieve_graph_evidence(graph_id, payload.query, payload.seed_entity_ids, payload.relation_types)
    return success(request, {"retrieval": result})


@router.post("/position-discoveries", response_model=SuccessEnvelope)
def discover_positions(
    payload: PositionDiscoveryRequest,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    return success(request, {"discovery": facade.discover_positions(payload.document_ids, payload.options)})


@router.post("/position-deltas", response_model=SuccessEnvelope)
def compare_positions(
    payload: PositionDeltaRequest,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    result = facade.compare_positions(
        payload.baseline_job_profile_id,
        payload.current_job_profile_id,
        payload.supporting_document_ids,
    )
    return success(request, {"delta": result})


@router.post("/matches", response_model=SuccessEnvelope, status_code=status.HTTP_201_CREATED)
def create_match(
    payload: MatchCreateRequest,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    match = facade.create_match(
        payload.candidate_profile_id,
        payload.job_profile_id,
        payload.options.model_dump(),
    )
    return success(request, {"match": match})


@router.get("/matches/{match_id}", response_model=SuccessEnvelope)
def get_match(
    match_id: str,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    return success(request, {"match": facade.get_match(match_id)})


@router.post("/reports", response_model=SuccessEnvelope, status_code=status.HTTP_201_CREATED)
def create_report(
    payload: ReportCreateRequest,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    return success(request, {"report": facade.create_report(payload.match_id, payload.language)})


@router.post("/learning-advice", response_model=SuccessEnvelope, status_code=status.HTTP_200_OK)
def generate_learning_advice(
    payload: LearningAdviceRequest,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    advice = facade.generate_learning_advice(payload.match_id)
    return success(request, {"advice": advice})


@router.post("/auto-match", response_model=SuccessEnvelope, status_code=status.HTTP_200_OK)
def auto_match(
    payload: AutoMatchRequest,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
    x_user_id: Optional[str] = Header(default=None),
) -> dict:
    result = facade.auto_match(
        payload.document_id,
        payload.top_n,
        user_id=x_user_id,
        filters=payload.filters,
        max_per_company=payload.max_per_company,
    )
    return success(request, result)
