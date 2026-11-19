"""Тонкий асинхронный клиент Keitaro Admin API v1."""

from typing import Any

import httpx

from app.config import get_settings


class KeitaroError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class KeitaroClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 30.0, transport: httpx.AsyncBaseTransport | None = None):
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            headers={"Api-Key": api_key, "Accept": "application/json"},
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            resp = await self._http.request(method, path.lstrip("/"), **kwargs)
        except httpx.HTTPError as e:
            raise KeitaroError(502, f"Keitaro недоступен: {e}") from e
        if resp.status_code >= 400:
            try:
                body = resp.json()
                msg = body.get("error") or body.get("message") or str(body) if isinstance(body, dict) else str(body)
            except ValueError:
                msg = resp.text[:500]
            raise KeitaroError(resp.status_code, f"Keitaro {method} /{path.lstrip('/')}: {msg}")
        if not resp.content:
            return None
        return resp.json()

    # --- справочники ---
    async def list_domains(self) -> list[dict]:
        return await self._request("GET", "domains")

    async def list_groups(self, type_: str = "campaigns") -> list[dict]:
        return await self._request("GET", "groups", params={"type": type_})

    async def list_traffic_sources(self) -> list[dict]:
        return await self._request("GET", "traffic_sources")

    async def list_offers(self) -> list[dict]:
        return await self._request("GET", "offers")

    # --- кампании ---
    async def list_campaigns(self) -> list[dict]:
        return await self._request("GET", "campaigns")

    async def get_campaign(self, campaign_id: int) -> dict:
        return await self._request("GET", f"campaigns/{campaign_id}")

    async def create_campaign(self, payload: dict) -> dict:
        return await self._request("POST", "campaigns", json=payload)

    async def delete_campaign(self, campaign_id: int) -> None:
        await self._request("DELETE", f"campaigns/{campaign_id}")

    # --- потоки ---
    async def list_streams(self, campaign_id: int) -> list[dict]:
        return await self._request("GET", f"campaigns/{campaign_id}/streams")

    async def get_stream(self, stream_id: int) -> dict:
        return await self._request("GET", f"streams/{stream_id}")

    async def create_stream(self, payload: dict) -> dict:
        return await self._request("POST", "streams", json=payload)

    async def update_stream(self, stream_id: int, payload: dict) -> dict:
        return await self._request("PUT", f"streams/{stream_id}", json=payload)

    async def delete_stream(self, stream_id: int) -> None:
        await self._request("DELETE", f"streams/{stream_id}")


_client: KeitaroClient | None = None


def get_keitaro() -> KeitaroClient:
    global _client
    if _client is None:
        s = get_settings()
        _client = KeitaroClient(s.keitaro_url, s.keitaro_api_key, s.keitaro_timeout)
    return _client


async def close_keitaro() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
