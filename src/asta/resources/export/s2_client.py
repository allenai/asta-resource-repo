"""Semantic Scholar API client for paper lookup."""

from __future__ import annotations

import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

_S2_MATCH_ENDPOINT = "https://api.semanticscholar.org/graph/v1/paper/search/match"

_S2_FIELDS = (
    "paperId,corpusId,externalIds,url,title,abstract,venue,publicationVenue,"
    "year,referenceCount,citationCount,influentialCitationCount,isOpenAccess,"
    "openAccessPdf,fieldsOfStudy,s2FieldsOfStudy,publicationTypes,"
    "publicationDate,journal,authors"
)

_MAX_RETRIES = 3


class S2Client:
    """Semantic Scholar client for title-based paper matching."""

    def __init__(self, api_key: str | None = None):
        if api_key is None:
            api_key = os.environ.get(
                "SEMANTIC_SCHOLAR_API_KEY", os.environ.get("S2_API_KEY")
            )
        self._api_key = api_key

    def _request_headers(self) -> dict:
        if self._api_key:
            return {"x-api-key": self._api_key}
        return {}

    def find_paper_by_title(self, title: str) -> dict | None:
        """Match a paper by title via the S2 /paper/search/match endpoint.

        Returns the API response dict on success, None if not found or on error.
        """
        params = {"query": title, "fields": _S2_FIELDS}

        for attempt in range(_MAX_RETRIES):
            time.sleep(1)
            try:
                response = requests.get(
                    _S2_MATCH_ENDPOINT,
                    params=params,
                    headers=self._request_headers(),
                    timeout=30,
                )
                if response.status_code == 200:
                    return response.json()
                if response.status_code == 404:
                    return None
                if response.status_code in (429, 500, 502, 503):
                    delay = 5 * (attempt + 1)
                    logger.warning(
                        "S2 returned %d, retrying in %ds", response.status_code, delay
                    )
                    time.sleep(delay)
                    continue
                logger.error("S2 error %d: %s", response.status_code, response.text)
                return None
            except requests.RequestException:
                logger.exception("S2 request failed (attempt %d/%d)", attempt + 1, _MAX_RETRIES)
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(5 * (attempt + 1))
                    continue
                return None

        return None
