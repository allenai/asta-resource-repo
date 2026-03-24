"""Paperstore export for Theorizer BYOPDF."""

from __future__ import annotations

import logging
import sys

from ..model import DocumentMetadata
from .ocr import MistralOCRStore
from .s2_client import S2Client

logger = logging.getLogger(__name__)


class PaperstoreExporter:
    """Builds a Theorizer-compatible paperstore from asta documents.

    Each document is matched on Semantic Scholar by title, then OCR'd to
    markdown. Documents without an S2 match are excluded.
    """

    def __init__(self, ocr: MistralOCRStore, s2: S2Client):
        self._ocr = ocr
        self._s2 = s2

    def export(
        self,
        documents: list[DocumentMetadata],
        max_pages: int = 20,
        quiet: bool = False,
    ) -> dict:
        """Export documents to paperstore JSON.

        Returns {"paperstore": {"<corpus_id>": {...}, ...}}.
        """
        paperstore: dict[str, dict] = {}
        total = len(documents)

        for i, doc in enumerate(documents, 1):
            title = doc.name or "(untitled)"
            if not quiet:
                print(f"[{i}/{total}] Processing: {title}", file=sys.stderr)

            matched_paper = self._match_on_s2(title)
            if matched_paper is None:
                if not quiet:
                    print("  -> Not found on S2, skipping", file=sys.stderr)
                continue

            corpus_id = str(matched_paper.get("corpusId", ""))
            if not corpus_id:
                continue

            markdown = self._ocr.process_pdf(doc.url, max_pages=max_pages) if doc.url else None
            status = "full_text" if markdown else "metadata_only"

            if not quiet:
                print(f"  -> S2 match (corpus: {corpus_id}), status: {status}", file=sys.stderr)

            paperstore[corpus_id] = self._build_entry(
                doc, matched_paper, corpus_id, markdown, status
            )

        return {"paperstore": paperstore}

    def _match_on_s2(self, title: str) -> dict | None:
        """Look up a paper by title on S2, returning the first match."""
        s2_response = self._s2.find_paper_by_title(title)
        if s2_response is None:
            return None
        if "data" in s2_response:
            data = s2_response["data"]
            return data[0] if data else None
        return s2_response

    @staticmethod
    def _build_entry(
        doc: DocumentMetadata,
        paper: dict,
        corpus_id: str,
        markdown: str | None,
        status: str,
    ) -> dict:
        open_access_pdf = paper.get("openAccessPdf")
        is_open_access = paper.get("isOpenAccess", False)

        paper_urls = [doc.url] if doc.url else []
        if isinstance(open_access_pdf, dict):
            oa_url = open_access_pdf.get("url")
            if oa_url and oa_url not in paper_urls:
                paper_urls.append(oa_url)

        return {
            "title": paper.get("title", doc.name),
            "corpus_id": corpus_id,
            "publication_year": paper.get("year"),
            "is_open_access": is_open_access,
            "s2_metadata": {
                "paperId": paper.get("paperId"),
                "corpusId": paper.get("corpusId"),
                "title": paper.get("title"),
                "year": paper.get("year"),
                "authors": paper.get("authors", []),
                "citationCount": paper.get("citationCount"),
                "url": paper.get("url"),
                "isOpenAccess": is_open_access,
                "openAccessPdf": open_access_pdf,
            },
            "paper_markdown": markdown or "",
            "paper_urls": paper_urls,
            "status": status,
        }
