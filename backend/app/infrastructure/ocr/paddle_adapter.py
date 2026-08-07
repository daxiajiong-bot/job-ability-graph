"""PaddleOCR-backed OCR adapter (compatible with PaddleOCR 2.x + PaddlePaddle 3.0.x)."""

from __future__ import annotations

import os
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

# PaddlePaddle + torch DLL loading fix for Windows
if hasattr(os, "add_dll_directory"):
    import sys
    _candidates = [
        Path(sys.prefix) / "Lib" / "site-packages" / "torch" / "lib",
        Path(sys.prefix) / "Library" / "bin",
    ]
    for _d in _candidates:
        if _d.is_dir():
            os.add_dll_directory(str(_d))


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
            # PaddleOCR 2.x API: ocr.ocr(image_path, cls=...)
            raw_results = self._client(language).ocr(
                str(temp_path),
                cls=options.get("use_angle_cls", False),
            )
        except OcrUnavailableError:
            raise
        except Exception as exc:
            raise OcrProcessingError(f"OCR failed for '{file_name}': {exc}") from exc
        finally:
            temp_path.unlink(missing_ok=True)

        # PaddleOCR 2.x returns: [[box, (text, confidence)], ...] per page
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
                import torch  # noqa: F401 — must load before paddleocr to register DLLs
                from paddleocr import PaddleOCR
            except Exception as exc:
                raise OcrUnavailableError(
                    "PaddleOCR is not installed. Install paddlepaddle and paddleocr first."
                ) from exc
            try:
                # PaddleOCR 2.x init parameters
                lang_map = {"ch": "ch", "en": "en", "chinese": "ch", "english": "en"}
                ocr_lang = lang_map.get(lang, lang)
                client = PaddleOCR(
                    lang=ocr_lang,
                    use_angle_cls=False,
                    use_gpu=(self.device == "gpu"),
                    enable_mkldnn=False,
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
        """Normalize PaddleOCR 2.x result: [[box, (text, confidence)], ...]"""
        lines = []
        if not result:
            return {"index": index, "line_count": 0, "lines": []}

        for line_index, item in enumerate(result):
            if not item or len(item) < 2:
                continue
            box, text_conf = item[0], item[1]
            if isinstance(text_conf, (list, tuple)) and len(text_conf) >= 2:
                text = str(text_conf[0]).strip()
                confidence = self._safe_float(text_conf[1])
            else:
                text = str(text_conf).strip()
                confidence = None
            if not text:
                continue
            lines.append({
                "index": line_index,
                "text": text,
                "confidence": confidence,
                "box": box,
            })

        return {
            "index": index,
            "line_count": len(lines),
            "lines": lines,
        }

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return round(float(value), 4)
        except (TypeError, ValueError):
            return None
