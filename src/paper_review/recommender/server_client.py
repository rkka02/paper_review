from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from paper_review.schemas import PaperEmbeddingsUpsert, RecommendationRunCreate, RecommendationRunOut


def _headers(api_key: str | None) -> dict[str, str]:
    k = (api_key or "").strip()
    if not k:
        return {}
    return {"X-API-Key": k}


def _url(base_url: str, path: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise ValueError("base_url is required.")
    if not path.startswith("/"):
        path = "/" + path
    return base + path


@dataclass(slots=True)
class ServerClient:
    base_url: str
    api_key: str | None = None
    web_username: str | None = None
    web_password: str | None = None
    timeout_seconds: float = 60.0

    _client: httpx.Client = field(init=False, repr=False)

    def __enter__(self) -> "ServerClient":
        headers = _headers(self.api_key)
        self._client = httpx.Client(timeout=self.timeout_seconds, headers=headers)
        if self.web_username or self.web_password:
            if not (self.web_username and self.web_password):
                raise ValueError("Both web_username and web_password are required.")
            self.login(self.web_username, self.web_password)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        self._client.close()

    def login(self, username: str, password: str) -> None:
        r = self._client.post(
            _url(self.base_url, "/api/session"),
            headers={"Content-Type": "application/json"},
            json={"username": username, "password": password},
        )
        r.raise_for_status()
        s = self._client.get(_url(self.base_url, "/api/session"))
        s.raise_for_status()
        data = s.json()
        authenticated = bool(isinstance(data, dict) and data.get("authenticated") is True)
        if not authenticated:
            raise RuntimeError(
                "Web login did not persist (session cookie not being sent). "
                "If the server has COOKIE_HTTPS_ONLY=true, use an https SERVER_BASE_URL."
            )

    def fetch_folders(self) -> list[dict]:
        r = self._client.get(_url(self.base_url, "/api/folders"))
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            raise RuntimeError("Unexpected /api/folders response.")
        return data

    def fetch_papers_summary(self) -> list[dict]:
        r = self._client.get(_url(self.base_url, "/api/papers/summary"))
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            raise RuntimeError("Unexpected /api/papers/summary response.")
        return data

    def fetch_missing_paper_embeddings(self, *, provider: str, model: str) -> list[str]:
        prov = (provider or "").strip()
        mdl = (model or "").strip()
        r = self._client.get(
            _url(self.base_url, "/api/paper-embeddings/missing"),
            params={"provider": prov, "model": mdl},
        )
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            raise RuntimeError("Unexpected /api/paper-embeddings/missing response.")
        return [str(x) for x in data if str(x).strip()]

    def upsert_paper_embeddings(self, payload: PaperEmbeddingsUpsert) -> dict:
        r = self._client.post(
            _url(self.base_url, "/api/paper-embeddings/batch"),
            headers={"Content-Type": "application/json"},
            json=payload.model_dump(mode="json"),
        )
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            raise RuntimeError("Unexpected /api/paper-embeddings/batch response.")
        return data

    def upload_recommendations(self, payload: RecommendationRunCreate) -> RecommendationRunOut:
        r = self._client.post(
            _url(self.base_url, "/api/recommendations"),
            headers={"Content-Type": "application/json"},
            json=payload.model_dump(mode="json"),
        )
        r.raise_for_status()
        data = r.json()
        return RecommendationRunOut.model_validate(data)


def fetch_folders(*, base_url: str, api_key: str | None) -> list[dict]:
    with ServerClient(base_url=base_url, api_key=api_key, timeout_seconds=30.0) as client:
        return client.fetch_folders()


def fetch_papers_summary(*, base_url: str, api_key: str | None) -> list[dict]:
    with ServerClient(base_url=base_url, api_key=api_key, timeout_seconds=60.0) as client:
        return client.fetch_papers_summary()


def upload_recommendations(
    *,
    base_url: str,
    api_key: str | None,
    payload: RecommendationRunCreate,
) -> RecommendationRunOut:
    with ServerClient(base_url=base_url, api_key=api_key, timeout_seconds=60.0) as client:
        return client.upload_recommendations(payload)
