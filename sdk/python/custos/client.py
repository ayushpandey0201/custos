"""Thin HTTP client: timeout handling + fail-open logic.

See docs/adr/0001-fail-open-default.md.
"""


class CustosClient:
    def __init__(self, base_url: str, api_key: str, timeout_ms: int = 50):
        self.base_url = base_url
        self.api_key = api_key
        self.timeout_ms = timeout_ms

    def evaluate(self, payload: dict) -> dict:
        raise NotImplementedError

