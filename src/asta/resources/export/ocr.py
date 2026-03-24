"""Mistral OCR integration for PDF-to-markdown conversion with file-based caching."""

import base64
import os
import time
from urllib.parse import unquote, urlparse

from mistralai.client import Mistral


class MistralOCRStore:
    """Extract full-text from PDFs using Mistral OCR API, with file-based caching.

    Adapted from asta-theorizer-internal/src/MistralOCRStore.py.
    Supports both remote URLs (https://) and local files (file:// or absolute paths).
    """

    def __init__(self, api_key: str | None = None, cache_dir: str | None = None):
        if api_key is None:
            api_key = os.environ.get("MISTRAL_API_KEY")
        if api_key is None:
            raise ValueError(
                "Mistral API key is required. Set MISTRAL_API_KEY environment variable."
            )
        self.client = Mistral(api_key=api_key)
        self.cache_dir = cache_dir or os.path.join(".asta", "ocr-cache")
        os.makedirs(self.cache_dir, exist_ok=True)

    def _sanitize_url(self, url: str) -> str:
        for prefix in ("http://", "https://", "file://"):
            if url.startswith(prefix):
                url = url[len(prefix):]
        return "".join(c if c.isalnum() or c == "_" else "_" for c in url).strip("_")

    def _cache_path(self, url: str) -> str:
        sanitized = self._sanitize_url(url)
        return os.path.join(self.cache_dir, sanitized, "ocr_response.md")

    def _load_cache(self, url: str) -> str | None:
        path = self._cache_path(url)
        if os.path.exists(path):
            with open(path, "r") as f:
                return f.read()
        return None

    def _save_cache(self, url: str, markdown: str) -> None:
        path = self._cache_path(url)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(markdown)

    @staticmethod
    def _extract_markdown(ocr_response_dict: dict) -> str:
        parts = []
        for page in ocr_response_dict.get("pages", []):
            md = page.get("markdown", "")
            if md:
                parts.append(md)
        return "\n\n".join(parts).strip()

    @staticmethod
    def _resolve_local_path(url: str) -> str | None:
        """Convert file:// URL or absolute path to a local filesystem path.
        Returns None if the URL is not local."""
        if url.startswith("file://"):
            parsed = urlparse(url)
            return unquote(parsed.path)
        if os.path.isabs(url) and os.path.exists(url):
            return url
        return None

    @staticmethod
    def _encode_pdf_base64(file_path: str) -> str:
        """Read a local PDF and return a base64 data URI."""
        with open(file_path, "rb") as f:
            data = f.read()
        b64 = base64.b64encode(data).decode("utf-8")
        return f"data:application/pdf;base64,{b64}"

    def _build_document_param(self, pdf_url: str) -> dict:
        """Build the document parameter for the Mistral OCR API.
        Local files are sent as base64; remote URLs are sent directly."""
        local_path = self._resolve_local_path(pdf_url)
        if local_path and os.path.exists(local_path):
            data_uri = self._encode_pdf_base64(local_path)
            return {
                "type": "document_url",
                "document_url": data_uri,
            }
        else:
            return {
                "type": "document_url",
                "document_url": pdf_url,
            }

    def process_pdf(self, pdf_url: str, max_pages: int = 20) -> str | None:
        """Process a PDF URL and return its content as markdown.

        Returns None on error. Uses file-based cache to avoid re-processing.
        Supports local files (file:// URLs) by uploading them as base64.
        """
        cached = self._load_cache(pdf_url)
        if cached is not None:
            return cached

        # Rate limit
        time.sleep(3)

        try:
            doc_param = self._build_document_param(pdf_url)
            ocr_response = self.client.ocr.process(
                model="mistral-ocr-latest",
                document=doc_param,
                include_image_base64=False,
                pages=list(range(0, max_pages + 1)),
            )
            markdown = self._extract_markdown(ocr_response.dict())
            self._save_cache(pdf_url, markdown)
            return markdown
        except Exception as e:
            print(f"OCR error for {pdf_url}: {e}")
            return None
