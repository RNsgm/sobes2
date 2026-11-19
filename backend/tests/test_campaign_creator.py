import json

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.keitaro.client import KeitaroClient, KeitaroError
from app.schemas import CampaignCreate
from app.services.campaign_creator import build_campaign_url, create_campaign

BASE = "https://k.test/admin_api/v1"


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


def payload(**kw):
    data = dict(name="Test", geo="mx, au", offer_id=7, domain_id=1, group_id=2, traffic_source_id=3)
    data.update(kw)
    return CampaignCreate(**data)


def test_geo_parsing():
    assert payload(geo="mx, AU;ro mx").geo == ["MX", "AU", "RO"]
    with pytest.raises(ValueError):
        payload(geo="MEX")
    with pytest.raises(ValueError):
        payload(geo=" , ")


def test_build_url():
    assert build_campaign_url("https://in.posdk.xyz/", "abc") == "https://in.posdk.xyz/abc"
    assert build_campaign_url("in.posdk.xyz", "abc") == "https://in.posdk.xyz/abc"


@respx.mock
async def test_create_campaign_two_streams(session):
    respx.get(f"{BASE}/domains").respond(json=[{"id": 1, "name": "https://in.posdk.xyz/"}])
    camp = respx.post(f"{BASE}/campaigns").respond(json={"id": 50, "alias": "AbC123", "name": "Test"})
    streams = respx.post(f"{BASE}/streams").mock(
        side_effect=[httpx.Response(200, json={"id": 501}), httpx.Response(200, json={"id": 502})]
    )
    client = KeitaroClient(BASE, "key")

    rec = await create_campaign(payload(), client, session)

    body = json.loads(camp.calls[0].request.content)
    assert (body["domain_id"], body["group_id"], body["traffic_source_id"]) == (1, 2, 3)
    assert camp.calls[0].request.headers["Api-Key"] == "key"

    geo = json.loads(streams.calls[0].request.content)
    assert geo["position"] == 1 and geo["schema"] == "redirect"
    assert geo["action_payload"] == "https://google.com"
    assert geo["filters"] == [{"name": "country", "mode": "accept", "payload": ["MX", "AU"]}]

    offer = json.loads(streams.calls[1].request.content)
    assert offer["position"] == 2
    assert offer["offers"] == [{"offer_id": 7, "share": 100, "state": "active"}]

    assert rec.url == "https://in.posdk.xyz/AbC123"
    assert (rec.geo_stream_id, rec.offer_stream_id) == (501, 502)


@respx.mock
async def test_rollback_when_stream_fails(session):
    respx.get(f"{BASE}/domains").respond(json=[{"id": 1, "name": "d.xyz"}])
    respx.post(f"{BASE}/campaigns").respond(json={"id": 50, "alias": "x"})
    respx.post(f"{BASE}/streams").respond(status_code=400, json={"error": "bad filter"})
    archived = respx.delete(f"{BASE}/campaigns/50").respond(json={})

    with pytest.raises(KeitaroError, match="bad filter"):
        await create_campaign(payload(), KeitaroClient(BASE, "key"), session)
    assert archived.called
