from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.keitaro.client import KeitaroClient, get_keitaro
from app.models import CreatedCampaign
from app.schemas import CampaignCreate, CampaignCreated, DraftIn, DraftOut, EditorState, OfferStreamInfo, Option
from app.services import campaign_creator, offer_editor

router = APIRouter(prefix="/api")


def _options(items: list[dict], *, active_only: bool = True) -> list[Option]:
    out = []
    for it in items:
        if active_only and it.get("state") not in (None, "active"):
            continue
        out.append(Option(id=it["id"], name=it.get("name") or f"#{it['id']}"))
    return sorted(out, key=lambda o: o.name.lower())


@router.get("/domains", response_model=list[Option])
async def domains(keitaro: KeitaroClient = Depends(get_keitaro)):
    return _options(await keitaro.list_domains())


@router.get("/groups", response_model=list[Option])
async def groups(keitaro: KeitaroClient = Depends(get_keitaro)):
    return _options(await keitaro.list_groups("campaigns"))


@router.get("/traffic-sources", response_model=list[Option])
async def traffic_sources(keitaro: KeitaroClient = Depends(get_keitaro)):
    return _options(await keitaro.list_traffic_sources())


@router.get("/offers", response_model=list[Option])
async def offers(
    q: str = Query("", description="Поиск по названию или ID"),
    limit: int = Query(20, ge=1, le=100),
    keitaro: KeitaroClient = Depends(get_keitaro),
):
    items = _options(await keitaro.list_offers())
    q = q.strip().lower()
    if q:
        items = [o for o in items if q in o.name.lower() or q == str(o.id)]
    return items[:limit]


@router.post("/campaigns", response_model=CampaignCreated, status_code=201)
async def create_campaign(
    data: CampaignCreate,
    keitaro: KeitaroClient = Depends(get_keitaro),
    session: AsyncSession = Depends(get_session),
):
    return await campaign_creator.create_campaign(data, keitaro, session)


@router.get("/campaigns/created", response_model=list[CampaignCreated])
async def created_campaigns(session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(CreatedCampaign).order_by(CreatedCampaign.id.desc()))
    return res.scalars().all()


# ---------- редактор офферов ----------


@router.get("/campaigns", response_model=list[Option])
async def campaigns(
    q: str = Query("", description="Поиск по названию или ID"),
    limit: int = Query(30, ge=1, le=200),
    keitaro: KeitaroClient = Depends(get_keitaro),
):
    items = [Option(id=c["id"], name=c.get("name") or f"#{c['id']}") for c in await keitaro.list_campaigns()]
    items.sort(key=lambda o: o.id, reverse=True)
    q = q.strip().lower()
    if q:
        items = [o for o in items if q in o.name.lower() or q == str(o.id)]
    return items[:limit]


@router.get("/campaigns/{campaign_id}/offer-streams", response_model=list[OfferStreamInfo])
async def offer_streams(campaign_id: int, keitaro: KeitaroClient = Depends(get_keitaro)):
    return await offer_editor.list_offer_streams(campaign_id, keitaro)


@router.get("/streams/{stream_id}/editor", response_model=EditorState)
async def editor_state(
    stream_id: int,
    refresh: bool = Query(False, description="Перечитать справочники Keitaro в обход кэша"),
    keitaro: KeitaroClient = Depends(get_keitaro),
    session: AsyncSession = Depends(get_session),
):
    if refresh:
        keitaro.invalidate("offers")
        keitaro.invalidate("campaigns")
    return await offer_editor.load_editor(stream_id, keitaro, session)


@router.post("/streams/{stream_id}/rebalance", response_model=DraftOut)
async def rebalance(stream_id: int, draft: DraftIn):
    return offer_editor.rebalance(draft.items)


@router.post("/streams/{stream_id}/apply", response_model=EditorState)
async def apply(
    stream_id: int,
    draft: DraftIn,
    keitaro: KeitaroClient = Depends(get_keitaro),
    session: AsyncSession = Depends(get_session),
):
    return await offer_editor.apply_draft(stream_id, draft.items, keitaro, session)
