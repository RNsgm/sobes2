import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

_GEO_RE = re.compile(r"^[A-Z]{2}$")


class Option(BaseModel):
    """Элемент выпадающего списка (домен / группа / источник / оффер)."""

    id: int
    name: str


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    geo: list[str] = Field(min_length=1, description="ISO-коды стран, напр. ['MX','AU']")
    offer_id: int
    domain_id: int
    group_id: int
    traffic_source_id: int

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Название не может быть пустым")
        return v

    @field_validator("geo", mode="before")
    @classmethod
    def parse_geo(cls, v):
        # принимаем и строку "MX, au,RO", и список
        if isinstance(v, str):
            v = re.split(r"[\s,;]+", v)
        codes: list[str] = []
        for item in v:
            code = str(item).strip().upper()
            if not code:
                continue
            if not _GEO_RE.match(code):
                raise ValueError(f"Некорректный гео-код: {item!r} (нужен 2-буквенный ISO-код)")
            if code not in codes:
                codes.append(code)
        if not codes:
            raise ValueError("Укажите хотя бы одну страну")
        return codes


class CampaignCreated(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    keitaro_campaign_id: int
    name: str
    alias: str
    url: str
    geo: list[str]
    offer_id: int
    domain_id: int
    group_id: int
    traffic_source_id: int
    geo_stream_id: int
    offer_stream_id: int
    created_at: datetime


# ---------- редактор офферов ----------


class OfferStreamInfo(BaseModel):
    id: int
    name: str
    offers_count: int


class EditorItem(BaseModel):
    """Строка черновика редактора."""

    offer_id: int
    name: str = ""
    share: int = Field(0, ge=0, le=100)
    pinned: bool = False
    removed: bool = False  # помечен на удаление (ещё не применено)
    original_share: int | None = None  # доля в Keitaro до правок; None — оффер новый в потоке
    state: str = "active"


class RemovedOfferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    offer_id: int
    offer_name: str
    share: int
    removed_at: datetime


class DraftIn(BaseModel):
    items: list[EditorItem]


class DraftOut(BaseModel):
    items: list[EditorItem]
    total: int
    errors: list[str]


class EditorState(DraftOut):
    campaign_id: int
    stream_id: int
    stream_name: str
    removed: list[RemovedOfferOut]
