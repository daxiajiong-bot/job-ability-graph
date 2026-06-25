"""PaddleOCR-backed OCR adapter."""

from __future__ import annotations

from pathlib import Path
from statistics import fmean
from tempfile import NamedTemporaryFile
from threading import Lock
from typing import Any, Optional

from backend.app.domain.errors import (
    InvalidInputError,
    OcrProcessingError,
    OcrUnavailableError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
)


SUPPORTED_CONTENT_TYPES = {
    "application/pdf": ".pdf",
    "image/bmp": ".bmp",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/tiff": ".tiff",
    "image/webp": ".webp",
}
SUPPORTED_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".pdf", ".png", ".tif", ".tiff", ".webp"}


class PaddleOcrAdapter:
    """Runs PaddleOCR locally and normalizes results for the application layer."""

    def __init__(
        self,
        *,
        default_lang: str = "ch",
        device: str = "cpu",
        max_upload_bytes: int = 20 * 1024 * 1024,
    ) -> None:
        self.default_lang = default_lang
        self.device = device
        self.max_upload_bytes = max_upload_bytes
        self._clients: dict[str, Any] = {}
        self._lock = Lock()

    def extract_text(
        self,
        *,
        file_name: str,
        content: bytes,
        content_type: Optional[str],
        lang: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        suffix = self._validate_upload(file_name, content, content_type)
        language = (lang or self.default_lang).strip() or self.default_lang
        temp_path = self._write_temp_file(content, suffix)
        try:
            raw_results = self._client(language).predict(
                input=str(temp_path),
                use_doc_orientation_classify=options.get("use_doc_orientation_classify"),
                use_doc_unwarping=options.get("use_doc_unwarping"),
                use_textline_orientation=options.get("use_textline_orientation"),
                text_det_limit_side_len=options.get("text_det_limit_side_len"),
                text_det_limit_type=options.get("text_det_limit_type"),
                text_det_thresh=options.get("text_det_thresh"),
                text_det_box_thresh=options.get("text_det_box_thresh"),
                text_det_unclip_ratio=options.get("text_det_unclip_ratio"),
                text_rec_score_thresh=options.get("text_rec_score_thresh"),
            )
        except OcrUnavailableError:
            raise
        except Exception as exc:
            raise OcrProcessingError(f"OCR failed for '{file_name}': {exc}") from exc
        finally:
            temp_path.unlink(missing_ok=True)

        pages = [self._normalize_page(result, index) for index, result in enumerate(raw_results)]
        lines = [line for page in pages for line in page["lines"]]
        text = "\n".join(line["text"] for line in lines if line["text"]).strip()
        if not text:
            raise OcrProcessingError(f"OCR did not extract text from '{file_name}'")

        confidences = [line["confidence"] for line in lines if line["confidence"] is not None]
        return {
            "state": "available",
            "implementation": "paddleocr",
            "lang": language,
            "text": text,
            "page_count": len(pages),
            "line_count": len(lines),
            "average_confidence": round(fmean(confidences), 4) if confidences else None,
            "pages": pages,
            "warnings": [],
        }

    def _client(self, lang: str) -> Any:
        with self._lock:
            client = self._clients.get(lang)
            if client is not None:
                return client
            try:
                from paddleocr import PaddleOCR
            except Exception as exc:
                raise OcrUnavailableError(
                    "PaddleOCR is not installed. Install paddlepaddle and paddleocr first."
                ) from exc
            try:
                client = PaddleOCR(
                    lang=lang,
                    device=self.device,
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                )
            except Exception as exc:
                raise OcrUnavailableError(f"PaddleOCR could not be initialized: {exc}") from exc
            self._clients[lang] = client
            return client

    def _validate_upload(self, file_name: str, content: bytes, content_type: Optional[str]) -> str:
        if not content:
            raise InvalidInputError("uploaded file must not be empty")
        if len(content) > self.max_upload_bytes:
            max_mb = self.max_upload_bytes // (1024 * 1024)
            raise PayloadTooLargeError(f"uploaded file is larger than {max_mb} MB")

        suffix = Path(file_name or "").suffix.lower()
        if content_type in SUPPORTED_CONTENT_TYPES:
            return SUPPORTED_CONTENT_TYPES[content_type]
        if suffix in SUPPORTED_SUFFIXES:
            return suffix
        supported = ", ".join(sorted(SUPPORTED_SUFFIXES))
        raise UnsupportedMediaTypeError(
            f"OCR supports PDF and image uploads only ({supported})",
            details=[{"content_type": content_type or "unknown", "file_name": file_name}],
        )

    @staticmethod
    def _write_temp_file(content: bytes, suffix: str) -> Path:
        with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(content)
            return Path(temp_file.name)

    def _normalize_page(self, result: Any, index: int) -> dict[str, Any]:
        payload = self._result_payload(result)
        texts = [str(text).strip() for text in payload.get("rec_texts", [])]
        scores = payload.get("rec_scores", [])
        boxes = payload.get("rec_boxes", [])

        lines = []
        for line_index, text in enumerate(texts):
            if not text:
                continue
            lines.append(
                {
                    "index": line_index,
                    "text": text,
                    "confidence": self._safe_score(scores, line_index),
                    "box": self._safe_item(boxes, line_index),
                }
            )
        return {
            "index": int(payload.get("page_index", index) or 0),
            "line_count": len(lines),
            "lines": lines,
        }

    @staticmethod
    def _result_payload(result: Any) -> dict[str, Any]:
        if isinstance(result, dict):
            return result
        json_payload = getattr(result, "json", None)
        if isinstance(json_payload, dict):
            inner = json_payload.get("res")
            if isinstance(inner, dict):
                return inner
        if hasattr(result, "get"):
            return {
                "page_index": result.get("page_index", 0),
                "rec_texts": result.get("rec_texts", []),
                "rec_scores": result.get("rec_scores", []),
                "rec_boxes": result.get("rec_boxes", []),
            }
        return {}

    @staticmethod
    def _safe_score(scores: Any, index: int) -> Optional[float]:
        value = PaddleOcrAdapter._safe_item(scores, index)
        if value is None:
            return None
        try:
            return round(float(value), 4)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_item(items: Any, index: int) -> Any:
        try:
            value = items[index]
        except (IndexError, KeyError, TypeError):
            return None
        if hasattr(value, "tolist"):
            return value.tolist()
        return value
