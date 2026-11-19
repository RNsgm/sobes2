"""Тонкий асинхронный клиент Keitaro Admin API v1."""

import asyncio
import time
from typing import Any

import httpx

from app.config import get_settings


class KeitaroError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class KeitaroClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
        cache_ttl: float = 0,
    ):
        # кэш справочников: поиск в автокомплите дёргает их на каждый ввод, а Keitaro отвечает 0.2-0.8 с
        self._cache_ttl = cache_ttl
        self._cache: dict[str, tuple[float, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._bg_tasks: set[asyncio.Task] = set()
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

    async def _cached_get(self, path: str, params: dict | None = None) -> Any:
        if self._cache_ttl <= 0:
            return await self._request("GET", path, params=params)
        key = path + "?" + "&".join(f"{k}={v}" for k, v in sorted((params or {}).items()))
        hit = self._cache.get(key)
        if hit:
            # устаревшие данные отдаём сразу, а обновляем в фоне (stale-while-revalidate)
            if hit[0] <= time.monotonic() and not self._locks.setdefault(key, asyncio.Lock()).locked():
                task = asyncio.create_task(self._refresh(key, path, params))
                self._bg_tasks.add(task)
                task.add_done_callback(self._bg_tasks.discard)
            return hit[1]
        return await self._refresh(key, path, params)

    async def _refresh(self, key: str, path: str, params: dict | None) -> Any:
        # один запрос в Keitaro на ключ, даже если пришло несколько поисков одновременно
        async with self._locks.setdefault(key, asyncio.Lock()):
            hit = self._cache.get(key)
            if hit and hit[0] > time.monotonic():
                return hit[1]
            try:
                data = await self._request("GET", path, params=params)
            except KeitaroError:
                if hit:  # фоновое обновление не удалось — оставляем старые данные
                    return hit[1]
                raise
            self._cache[key] = (time.monotonic() + self._cache_ttl, data)
            return data

    def invalidate(self, path: str) -> None:
        for key in [k for k in self._cache if k.startswith(path + "?")]:
            del self._cache[key]

    # --- справочники (кэшируются) ---
    async def list_domains(self) -> list[dict]:
        return await self._cached_get("domains")

    async def list_groups(self, type_: str = "campaigns") -> list[dict]:
        return await self._cached_get("groups", {"type": type_})

    async def list_traffic_sources(self) -> list[dict]:
        return await self._cached_get("traffic_sources")

    async def list_offers(self) -> list[dict]:
        return await self._cached_get("offers")

    # --- кампании ---
    async def list_campaigns(self) -> list[dict]:
        return await self._cached_get("campaigns")

    async def get_campaign(self, campaign_id: int) -> dict:
        return await self._request("GET", f"campaigns/{campaign_id}")

    async def create_campaign(self, payload: dict) -> dict:
        try:
            return await self._request("POST", "campaigns", json=payload)
        finally:
            self.invalidate("campaigns")

    async def delete_campaign(self, campaign_id: int) -> None:
        try:
            await self._request("DELETE", f"campaigns/{campaign_id}")
        finally:
            self.invalidate("campaigns")

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
        _client = KeitaroClient(s.keitaro_url, s.keitaro_api_key, s.keitaro_timeout, cache_ttl=s.keitaro_cache_ttl)
    return _client


async def close_keitaro() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
