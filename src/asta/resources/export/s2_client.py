"""Semantic Scholar API client for paper lookup by title.

Adapted from asta-theorizer-internal/src/SemanticScholar.py.
"""

import os
import time

import requests


S2_FIELDS = (
    "paperId,corpusId,externalIds,url,title,abstract,venue,publicationVenue,"
    "year,referenceCount,citationCount,influentialCitationCount,isOpenAccess,"
    "openAccessPdf,fieldsOfStudy,s2FieldsOfStudy,publicationTypes,"
    "publicationDate,journal,authors"
)


class S2Client:
    """Minimal Semantic Scholar client focused on title-based paper matching."""

    def __init__(self, api_key: str | None = None):
        if api_key is None:
            api_key = os.environ.get(
                "SEMANTIC_SCHOLAR_API_KEY", os.environ.get("S2_API_KEY")
            )
        self.api_key = api_key

    def _headers(self) -> dict:
        headers = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    def find_paper_by_title(self, title: str) -> dict | None:
        """Look up a paper on Semantic Scholar using the /paper/search/match endpoint.

        Returns the paper data dict if found, None if not found or on error.
        """
        url = "https://api.semanticscholar.org/graph/v1/paper/search/match"
        params = {"query": title, "fields": S2_FIELDS}

        max_retries = 3
        for attempt in range(max_retries):
            time.sleep(1)
            try:
                response = requests.get(
                    url, params=params, headers=self._headers(), timeout=30
                )
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    return None
                elif response.status_code == 429:
                    delay = 5 * (attempt + 1)
                    print(f"S2 rate limited, retrying in {delay}s...")
                    time.sleep(delay)
                    continue
                elif response.status_code >= 500:
                    delay = 5 * (attempt + 1)
                    print(f"S2 server error {response.status_code}, retrying in {delay}s...")
                    time.sleep(delay)
                    continue
                else:
                    print(f"S2 error {response.status_code}: {response.text}")
                    return None
            except requests.RequestException as e:
                print(f"S2 request error: {e}")
                if attempt < max_retries - 1:
                    time.sleep(5 * (attempt + 1))
                    continue
                return None

        return None
