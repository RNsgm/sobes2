import json

import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.keitaro.client import KeitaroClient, KeitaroError
from app.models import PinnedOffer, RemovedOffer
from app.schemas import EditorItem
from app.services.offer_editor import apply_draft, load_editor, rebalance

BASE = "https://k.test/admin_api/v1"


def it(oid, share=0, pinned=False, removed=False, original=None):
    return EditorItem(offer_id=oid, name=f"o{oid}", share=share, pinned=pinned, removed=removed, original_share=original)


def shares(draft):
    return {i.offer_id: i.share for i in draft.items}


# ---------- rebalance ----------


def test_equal_split_with_remainder():
    d = rebalance([it(1), it(2), it(3)])
    assert shares(d) == {1: 34, 2: 33, 3: 33}
    assert d.total == 100 and d.errors == []


def test_add_offer_recalculates():
    d = rebalance([it(1, 50), it(2, 50), it(3)])  # 3-й только что добавлен
    assert shares(d) == {1: 34, 2: 33, 3: 33}


def test_removed_offer_excluded_but_keeps_share_for_display():
    d = rebalance([it(1, 34), it(2, 33, removed=True), it(3, 33)])
    assert shares(d) == {1: 50, 2: 33, 3: 50}
    assert d.total == 100


def test_pinned_share_is_kept():
    d = rebalance([it(1, 70, pinned=True), it(2), it(3), it(4)])
    assert shares(d) == {1: 70, 2: 10, 3: 10, 4: 10}


def test_pinned_with_remainder():
    d = rebalance([it(1, 25, pinned=True), it(2), it(3)])
    assert shares(d) == {1: 25, 2: 38, 3: 37}


def test_removing_pinned_offer_frees_its_share():
    d = rebalance([it(1, 70, pinned=True, removed=True), it(2, 15), it(3, 15)])
    assert shares(d)[2] + shares(d)[3] == 100


def test_pinned_over_100_is_error():
    d = rebalance([it(1, 60, pinned=True), it(2, 50, pinned=True), it(3)])
    assert d.errors and shares(d)[3] == 0


def test_all_pinned_must_sum_to_100():
    assert rebalance([it(1, 60, pinned=True), it(2, 40, pinned=True)]).errors == []
    assert rebalance([it(1, 60, pinned=True), it(2, 30, pinned=True)]).errors


def test_all_removed_is_error():
    assert rebalance([it(1, 100, removed=True)]).errors


def test_duplicate_is_error():
    assert rebalance([it(1), it(1)]).errors


# ---------- apply ----------


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


def mock_keitaro(stream_offers):
    state = {"offers": stream_offers}

    def get_stream(request):
        return respx.MockResponse(200, json={"id": 10, "campaign_id": 5, "name": "Offers", "offers": state["offers"]})

    def put_stream(request):
        state["offers"] = json.loads(request.content)["offers"]
        return respx.MockResponse(200, json={"id": 10})

    respx.get(f"{BASE}/streams/10").mock(side_effect=get_stream)
    put = respx.put(f"{BASE}/streams/10").mock(side_effect=put_stream)
    respx.get(f"{BASE}/offers").respond(json=[{"id": i, "name": f"o{i}"} for i in (1, 2, 3)])
    return put


@respx.mock
async def test_apply_removes_remembers_and_restores(session):
    put = mock_keitaro([{"offer_id": 1, "share": 50, "state": "active"}, {"offer_id": 2, "share": 50, "state": "active"}])
    k = KeitaroClient(BASE, "key")

    # удаляем оффер 2, добавляем 3, пиним 1 на 70
    state = await apply_draft(
        10, [it(1, 70, pinned=True, original=50), it(2, 50, removed=True, original=50), it(3)], k, session
    )
    sent = json.loads(put.calls[-1].request.content)["offers"]
    assert sent == [{"offer_id": 1, "share": 70, "state": "active"}, {"offer_id": 3, "share": 30, "state": "active"}]
    assert [r.offer_id for r in state.removed] == [2] and state.removed[0].share == 50
    assert [(i.offer_id, i.pinned) for i in state.items] == [(1, True), (3, False)]

    # возвращаем оффер 2
    state = await apply_draft(10, [*state.items, it(2)], k, session)
    assert state.removed == []
    assert {i.offer_id: i.share for i in state.items} == {1: 70, 3: 15, 2: 15}

    pins = (await session.execute(select(PinnedOffer.offer_id))).scalars().all()
    assert pins == [1]
    assert (await session.execute(select(RemovedOffer))).scalars().all() == []


@respx.mock
async def test_apply_rejects_invalid_draft_without_touching_keitaro(session):
    put = mock_keitaro([{"offer_id": 1, "share": 100, "state": "active"}])
    with pytest.raises(KeitaroError):
        await apply_draft(10, [it(1, 100, removed=True)], KeitaroClient(BASE, "key"), session)
    assert not put.called


@respx.mock
async def test_load_editor_marks_pins(session):
    mock_keitaro([{"offer_id": 1, "share": 100, "state": "active"}])
    session.add(PinnedOffer(stream_id=10, offer_id=1))
    await session.commit()
    state = await load_editor(10, KeitaroClient(BASE, "key"), session)
    assert state.items[0].pinned and state.items[0].name == "o1" and state.total == 100


@respx.mock
async def test_apply_rejects_stale_draft(session):
    # черновик строился от 1:100, а в Keitaro за это время добавили оффер 2
    put = mock_keitaro([{"offer_id": 1, "share": 50, "state": "active"}, {"offer_id": 2, "share": 50, "state": "active"}])
    with pytest.raises(KeitaroError, match="изменились в Keitaro") as exc:
        await apply_draft(10, [it(1, 0, original=100), it(3)], KeitaroClient(BASE, "key"), session)
    assert exc.value.status_code == 409
    assert not put.called


@respx.mock
async def test_refresh_bypasses_offer_cache(session):
    mock_keitaro([{"offer_id": 1, "share": 100, "state": "active"}])
    offers = respx.get(f"{BASE}/offers").mock(
        side_effect=[
            respx.MockResponse(200, json=[{"id": 1, "name": "old"}]),
            respx.MockResponse(200, json=[{"id": 1, "name": "renamed"}]),
        ]
    )
    k = KeitaroClient(BASE, "key", cache_ttl=60)
    assert (await load_editor(10, k, session)).items[0].name == "old"
    assert (await load_editor(10, k, session)).items[0].name == "old"  # из кэша
    k.invalidate("offers")  # то же делает ?refresh=true
    assert (await load_editor(10, k, session)).items[0].name == "renamed"
    assert offers.call_count == 2
