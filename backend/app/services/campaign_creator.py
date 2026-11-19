"""«Создаватор» кампаний.

Создаёт в Keitaro кампанию с привязанными доменом, группой и источником и два потока:
  1. гео-поток: страны из запроса -> редирект на GEO_REDIRECT_URL (google.com);
  2. оффер-поток: весь остальной трафик -> выбранный оффер (100%).
Если создание потоков падает, кампания отправляется в архив, чтобы не оставлять полуфабрикат.
"""

import secrets
import string

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.keitaro.client import KeitaroClient, KeitaroError
from app.models import CreatedCampaign
from app.schemas import CampaignCreate

_ALIAS_ALPHABET = string.ascii_letters + string.digits


def generate_alias(length: int = 8) -> str:
    return "".join(secrets.choice(_ALIAS_ALPHABET) for _ in range(length))


def build_campaign_url(domain_name: str, alias: str) -> str:
    domain = domain_name.strip().rstrip("/")
    if not domain.startswith(("http://", "https://")):
        domain = f"https://{domain}"
    return f"{domain}/{alias}"


def geo_stream_payload(campaign_id: int, geo: list[str], redirect_url: str) -> dict:
    return {
        "campaign_id": campaign_id,
        "type": "regular",
        "name": f"Geo {','.join(geo)} -> redirect",
        "position": 1,
        "state": "active",
        "schema": "redirect",
        "action_type": "http",
        "action_payload": redirect_url,
        "filters": [{"name": "country", "mode": "accept", "payload": geo}],
    }


def offer_stream_payload(campaign_id: int, offer_id: int) -> dict:
    return {
        "campaign_id": campaign_id,
        "type": "regular",
        "name": "Offers",
        "position": 2,
        "state": "active",
        "schema": "landings",
        "action_type": "http",
        "offers": [{"offer_id": offer_id, "share": 100, "state": "active"}],
    }


async def create_campaign(data: CampaignCreate, keitaro: KeitaroClient, session: AsyncSession) -> CreatedCampaign:
    settings = get_settings()

    domains = {d["id"]: d for d in await keitaro.list_domains()}
    domain = domains.get(data.domain_id)
    if domain is None:
        raise KeitaroError(422, f"Домен id={data.domain_id} не найден в Keitaro")

    alias = generate_alias()
    campaign = await keitaro.create_campaign(
        {
            "name": data.name,
            "alias": alias,
            "type": "position",
            "state": "active",
            "domain_id": data.domain_id,
            "group_id": data.group_id,
            "traffic_source_id": data.traffic_source_id,
        }
    )
    campaign_id = campaign["id"]
    alias = campaign.get("alias") or alias

    try:
        geo_stream = await keitaro.create_stream(geo_stream_payload(campaign_id, data.geo, settings.geo_redirect_url))
        offer_stream = await keitaro.create_stream(offer_stream_payload(campaign_id, data.offer_id))
    except KeitaroError:
        try:
            await keitaro.delete_campaign(campaign_id)
        except KeitaroError:
            pass
        raise

    record = CreatedCampaign(
        keitaro_campaign_id=campaign_id,
        name=campaign.get("name", data.name),
        alias=alias,
        url=build_campaign_url(domain["name"], alias),
        geo=data.geo,
        offer_id=data.offer_id,
        domain_id=data.domain_id,
        group_id=data.group_id,
        traffic_source_id=data.traffic_source_id,
        geo_stream_id=geo_stream["id"],
        offer_stream_id=offer_stream["id"],
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record
