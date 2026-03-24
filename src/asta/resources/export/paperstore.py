"""Export asta documents to Theorizer paperstore JSON format."""

from __future__ import annotations

import sys

from ..model import DocumentMetadata
from .ocr import MistralOCRStore
from .s2_client import S2Client


class PaperstoreExporter:
    """Converts asta documents into a Theorizer-compatible paperstore.

    For each document:
    1. OCR the PDF to markdown via Mistral OCR
    2. Look up the paper on Semantic Scholar by title
    3. If S2 match found, include in paperstore; otherwise skip
    """

    def __init__(self, ocr: MistralOCRStore, s2: S2Client):
        self.ocr = ocr
        self.s2 = s2

    def export(
        self,
        documents: list[DocumentMetadata],
        max_pages: int = 20,
        quiet: bool = False,
    ) -> dict:
        """Export documents to paperstore format.

        Returns a dict matching the Theorizer paperstore schema:
        {"paperstore": {"<corpus_id>": {...}, ...}}
        """
        paperstore: dict[str, dict] = {}
        total = len(documents)

        for i, doc in enumerate(documents, 1):
            title = doc.name or "(untitled)"
            if not quiet:
                print(
                    f"[{i}/{total}] Processing: {title}",
                    file=sys.stderr,
                )

            # Step 1: Look up on Semantic Scholar
            s2_data = self.s2.find_paper_by_title(title)
            if s2_data is None:
                if not quiet:
                    print(f"  -> Not found on S2, skipping", file=sys.stderr)
                continue

            # Extract the matched paper (first result from /search/match)
            paper = s2_data.get("data", [s2_data])[0] if "data" in s2_data else s2_data
            corpus_id = str(paper.get("corpusId", ""))
            if not corpus_id:
                if not quiet:
                    print(f"  -> No corpus ID, skipping", file=sys.stderr)
                continue

            # Step 2: OCR the PDF
            markdown = None
            if doc.url:
                markdown = self.ocr.process_pdf(doc.url, max_pages=max_pages)

            status = "full_text" if markdown else "metadata_only"
            if not quiet:
                print(f"  -> S2 match (corpus: {corpus_id}), status: {status}", file=sys.stderr)

            # Step 3: Build paperstore entry
            is_open_access = paper.get("isOpenAccess", False)
            open_access_pdf = paper.get("openAccessPdf")

            s2_metadata = {
                "paperId": paper.get("paperId"),
                "corpusId": paper.get("corpusId"),
                "title": paper.get("title"),
                "year": paper.get("year"),
                "authors": paper.get("authors", []),
                "citationCount": paper.get("citationCount"),
                "url": paper.get("url"),
                "isOpenAccess": is_open_access,
                "openAccessPdf": open_access_pdf,
            }

            paper_urls = [doc.url] if doc.url else []
            if open_access_pdf and isinstance(open_access_pdf, dict):
                oa_url = open_access_pdf.get("url")
                if oa_url and oa_url not in paper_urls:
                    paper_urls.append(oa_url)

            paperstore[corpus_id] = {
                "title": paper.get("title", title),
                "corpus_id": corpus_id,
                "publication_year": paper.get("year"),
                "is_open_access": is_open_access,
                "s2_metadata": s2_metadata,
                "paper_markdown": markdown or "",
                "paper_urls": paper_urls,
                "status": status,
            }

        return {"paperstore": paperstore}
