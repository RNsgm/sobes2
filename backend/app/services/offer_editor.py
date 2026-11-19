"""Редактор офферов в потоке кампании.

Сценарий: пользователь правит черновик (добавляет / помечает на удаление / возвращает офферы,
ставит пины), после каждого действия доли пересчитываются, затем «Применить» отправляет
результат в Keitaro, а «Отменить» сбрасывает черновик к состоянию из Keitaro.

Правила пересчёта (rebalance):
  * офферы, помеченные на удаление, в расчёте не участвуют;
  * запиненные офферы сохраняют свою долю как есть;
  * остаток (100 - сумма запиненных) делится поровну между незапиненными,
    целыми процентами; лишние единицы получают первые по порядку офферы.
"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.keitaro.client import KeitaroClient, KeitaroError
from app.models import PinnedOffer, RemovedOffer
from app.schemas import DraftOut, EditorItem, EditorState, OfferStreamInfo, RemovedOfferOut

TOTAL = 100


def rebalance(items: list[EditorItem]) -> DraftOut:
    items = [it.model_copy() for it in items]
    errors: list[str] = []

    active = [it for it in items if not it.removed]
    ids = [it.offer_id for it in items]
    if len(ids) != len(set(ids)):
        errors.append("Оффер добавлен в поток дважды")

    if not active:
        errors.append("В потоке должен остаться хотя бы один оффер")
        return DraftOut(items=items, total=0, errors=errors)

    pinned = [it for it in active if it.pinned]
    free = [it for it in active if not it.pinned]
    pinned_sum = sum(it.share for it in pinned)

    if pinned_sum > TOTAL:
        errors.append(f"Сумма запиненных долей {pinned_sum}% больше {TOTAL}%")
        for it in free:
            it.share = 0
    elif free:
        base, extra = divmod(TOTAL - pinned_sum, len(free))
        for i, it in enumerate(free):
            it.share = base + (1 if i < extra else 0)
    elif pinned_sum != TOTAL:
        errors.append(
            f"Все офферы запинены, сумма {pinned_sum}% вместо {TOTAL}%: снимите пин или поправьте доли"
        )

    total = sum(it.share for it in active)
    return DraftOut(items=items, total=total, errors=errors)


async def list_offer_streams(campaign_id: int, keitaro: KeitaroClient) -> list[OfferStreamInfo]:
    streams = await keitaro.list_streams(campaign_id)
    return [
        OfferStreamInfo(id=s["id"], name=s.get("name") or f"Flow #{s['id']}", offers_count=len(s.get("offers") or []))
        for s in streams
        if s.get("schema") == "landings" and s.get("state", "active") != "deleted"
    ]


async def _offer_names(keitaro: KeitaroClient) -> dict[int, str]:
    return {o["id"]: o.get("name") or f"#{o['id']}" for o in await keitaro.list_offers()}


async def load_editor(stream_id: int, keitaro: KeitaroClient, session: AsyncSession) -> EditorState:
    stream = await keitaro.get_stream(stream_id)
    names = await _offer_names(keitaro)

    pinned_ids = set(
        (await session.execute(select(PinnedOffer.offer_id).where(PinnedOffer.stream_id == stream_id))).scalars()
    )

    items = [
        EditorItem(
            offer_id=o["offer_id"],
            name=names.get(o["offer_id"], f"#{o['offer_id']}"),
            share=int(o.get("share") or 0),
            pinned=o["offer_id"] in pinned_ids,
            original_share=int(o.get("share") or 0),
            state=o.get("state") or "active",
        )
        for o in stream.get("offers") or []
    ]
    current_ids = {it.offer_id for it in items}

    removed_rows = (
        await session.execute(
            select(RemovedOffer).where(RemovedOffer.stream_id == stream_id).order_by(RemovedOffer.removed_at.desc())
        )
    ).scalars()
    removed = [RemovedOfferOut.model_validate(r) for r in removed_rows if r.offer_id not in current_ids]

    total = sum(it.share for it in items)
    errors = [] if total == TOTAL or not items else [f"Сейчас в Keitaro сумма долей {total}%"]
    return EditorState(
        campaign_id=stream["campaign_id"],
        stream_id=stream_id,
        stream_name=stream.get("name") or f"Flow #{stream_id}",
        items=items,
        total=total,
        errors=errors,
        removed=removed,
    )


async def apply_draft(
    stream_id: int, items: list[EditorItem], keitaro: KeitaroClient, session: AsyncSession
) -> EditorState:
    draft = rebalance(items)
    if draft.errors:
        raise KeitaroError(422, "; ".join(draft.errors))

    stream = await keitaro.get_stream(stream_id)
    campaign_id = stream["campaign_id"]
    current = {o["offer_id"]: int(o.get("share") or 0) for o in stream.get("offers") or []}
    names = {it.offer_id: it.name for it in draft.items}

    active = [it for it in draft.items if not it.removed]
    active_ids = {it.offer_id for it in active}

    # всё, что сейчас есть в Keitaro, но не осталось в черновике, — удаляем и запоминаем
    to_remember = {oid: share for oid, share in current.items() if oid not in active_ids}

    await keitaro.update_stream(
        stream_id,
        {"offers": [{"offer_id": it.offer_id, "share": it.share, "state": it.state or "active"} for it in active]},
    )

    # Keitaro обновлён — синхронизируем локальную БД
    if to_remember:
        await session.execute(
            delete(RemovedOffer).where(
                RemovedOffer.stream_id == stream_id, RemovedOffer.offer_id.in_(to_remember.keys())
            )
        )
        session.add_all(
            RemovedOffer(
                campaign_id=campaign_id,
                stream_id=stream_id,
                offer_id=oid,
                offer_name=names.get(oid) or f"#{oid}",
                share=share,
            )
            for oid, share in to_remember.items()
        )
    # вернувшиеся офферы больше не числятся удалёнными
    await session.execute(
        delete(RemovedOffer).where(RemovedOffer.stream_id == stream_id, RemovedOffer.offer_id.in_(active_ids))
    )
    await session.execute(delete(PinnedOffer).where(PinnedOffer.stream_id == stream_id))
    session.add_all(PinnedOffer(stream_id=stream_id, offer_id=it.offer_id) for it in active if it.pinned)
    await session.commit()

    return await load_editor(stream_id, keitaro, session)
