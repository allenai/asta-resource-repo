"""Mistral OCR client for PDF-to-markdown conversion."""

from __future__ import annotations

import base64
import logging
import os
import time
from urllib.parse import unquote, urlparse

from mistralai.client import Mistral

logger = logging.getLogger(__name__)


class MistralOCRStore:
    """Converts PDFs to markdown via Mistral OCR API with file-based caching.

    Local files (file:// URLs or absolute paths) are uploaded as base64.
    Remote URLs are passed directly to the API.
    """

    def __init__(self, api_key: str | None = None, cache_dir: str | None = None):
        if api_key is None:
            api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            raise ValueError(
                "Mistral API key is required. Set MISTRAL_API_KEY environment variable."
            )
        self._client = Mistral(api_key=api_key)
        self._cache_dir = cache_dir or os.path.join(".asta", "ocr-cache")
        os.makedirs(self._cache_dir, exist_ok=True)

    def process_pdf(self, pdf_url: str, max_pages: int = 20) -> str | None:
        """Convert a PDF to markdown. Returns None on error."""
        cached_markdown = self._read_cache(pdf_url)
        if cached_markdown is not None:
            return cached_markdown

        time.sleep(3)  # rate limit

        try:
            document_param = self._document_param_for(pdf_url)
            ocr_response = self._client.ocr.process(
                model="mistral-ocr-latest",
                document=document_param,
                include_image_base64=False,
                pages=list(range(0, max_pages + 1)),
            )
            markdown = self._pages_to_markdown(ocr_response.dict())
            self._write_cache(pdf_url, markdown)
            return markdown
        except Exception:
            logger.exception("OCR failed for %s", pdf_url)
            return None

    # --- Cache ---

    def _cache_path_for(self, url: str) -> str:
        stripped = url
        for prefix in ("http://", "https://", "file://"):
            if stripped.startswith(prefix):
                stripped = stripped[len(prefix):]
        sanitized = "".join(
            c if c.isalnum() or c == "_" else "_" for c in stripped
        ).strip("_")
        return os.path.join(self._cache_dir, sanitized, "ocr_response.md")

    def _read_cache(self, url: str) -> str | None:
        path = self._cache_path_for(url)
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return f.read()

    def _write_cache(self, url: str, markdown: str) -> None:
        path = self._cache_path_for(url)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(markdown)

    # --- Document preparation ---

    def _document_param_for(self, pdf_url: str) -> dict:
        """Build the Mistral API document parameter, encoding local files as base64."""
        local_path = self._resolve_local_path(pdf_url)
        if local_path and os.path.exists(local_path):
            data_uri = self._encode_as_base64_data_uri(local_path)
            return {"type": "document_url", "document_url": data_uri}
        return {"type": "document_url", "document_url": pdf_url}

    @staticmethod
    def _resolve_local_path(url: str) -> str | None:
        if url.startswith("file://"):
            return unquote(urlparse(url).path)
        if os.path.isabs(url) and os.path.exists(url):
            return url
        return None

    @staticmethod
    def _encode_as_base64_data_uri(file_path: str) -> str:
        with open(file_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
        return f"data:application/pdf;base64,{encoded}"

    @staticmethod
    def _pages_to_markdown(ocr_response: dict) -> str:
        page_texts = [
            page["markdown"]
            for page in ocr_response.get("pages", [])
            if page.get("markdown")
        ]
        return "\n\n".join(page_texts).strip()
