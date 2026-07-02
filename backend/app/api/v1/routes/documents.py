"""Document resource endpoints; document text never appears in responses."""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status

from backend.app.api.v1.dependencies import get_facade
from backend.app.api.v1.errors import success
from backend.app.api.v1.schemas.common import SuccessEnvelope
from backend.app.api.v1.schemas.resources import DocumentCreateRequest
from backend.app.application.use_cases.contract_facade import ContractFacade
from backend.app.domain.entities import DocumentType
from backend.app.domain.errors import InvalidInputError


router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("", response_model=SuccessEnvelope, status_code=status.HTTP_201_CREATED)
def create_document(
    payload: DocumentCreateRequest,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    document = facade.create_document(
        document_type=payload.document_type,
        text=payload.text,
        source=payload.source.model_dump(exclude_none=True),
        metadata=payload.metadata,
    )
    return success(request, {"document": document})


@router.post("/ocr", response_model=SuccessEnvelope, status_code=status.HTTP_201_CREATED)
async def create_document_from_ocr(
    request: Request,
    document_type: DocumentType = Form(...),
    file: UploadFile = File(...),
    lang: str = Form(default="ch"),
    source_system: str = Form(default="ocr_upload"),
    external_id: Optional[str] = Form(default=None),
    uri: Optional[str] = Form(default=None),
    published_at: Optional[str] = Form(default=None),
    metadata_json: Optional[str] = Form(default=None),
    use_doc_orientation_classify: Optional[bool] = Form(default=None),
    use_doc_unwarping: Optional[bool] = Form(default=None),
    use_textline_orientation: Optional[bool] = Form(default=None),
    text_det_limit_side_len: Optional[int] = Form(default=None),
    text_det_limit_type: Optional[str] = Form(default=None),
    text_det_thresh: Optional[float] = Form(default=None),
    text_det_box_thresh: Optional[float] = Form(default=None),
    text_det_unclip_ratio: Optional[float] = Form(default=None),
    text_rec_score_thresh: Optional[float] = Form(default=None),
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    payload = await file.read()
    result = facade.create_document_from_ocr(
        document_type=document_type,
        file_name=file.filename or "upload",
        content=payload,
        content_type=file.content_type,
        source=_document_source(source_system, external_id, uri, published_at),
        metadata=_metadata_from_json(metadata_json),
        lang=lang,
        options=_ocr_options(
            use_doc_orientation_classify=use_doc_orientation_classify,
            use_doc_unwarping=use_doc_unwarping,
            use_textline_orientation=use_textline_orientation,
            text_det_limit_side_len=text_det_limit_side_len,
            text_det_limit_type=text_det_limit_type,
            text_det_thresh=text_det_thresh,
            text_det_box_thresh=text_det_box_thresh,
            text_det_unclip_ratio=text_det_unclip_ratio,
            text_rec_score_thresh=text_rec_score_thresh,
        ),
    )
    return success(request, result)


@router.get("/{document_id}", response_model=SuccessEnvelope)
def get_document(
    document_id: str,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    return success(request, {"document": facade.get_document(document_id)})


def _metadata_from_json(value: Optional[str]) -> dict[str, Any]:
    if not value:
        return {}
    try:
        metadata = json.loads(value)
    except json.JSONDecodeError as exc:
        raise InvalidInputError("metadata_json must be valid JSON") from exc
    if not isinstance(metadata, dict):
        raise InvalidInputError("metadata_json must decode to a JSON object")
    return metadata


def _document_source(
    source_system: str,
    external_id: Optional[str],
    uri: Optional[str],
    published_at: Optional[str],
) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "source_system": source_system.strip() or "ocr_upload",
            "external_id": external_id,
            "uri": uri,
            "published_at": published_at,
        }.items()
        if value is not None
    }


def _ocr_options(**values: Any) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}
