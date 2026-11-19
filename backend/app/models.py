from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CreatedCampaign(Base):
    """Журнал кампаний, созданных через обёртку."""

    __tablename__ = "created_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keitaro_campaign_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    alias: Mapped[str] = mapped_column(String(64))
    url: Mapped[str] = mapped_column(String(512))
    geo: Mapped[list[str]] = mapped_column(JSON)
    offer_id: Mapped[int] = mapped_column(Integer)
    domain_id: Mapped[int] = mapped_column(Integer)
    group_id: Mapped[int] = mapped_column(Integer)
    traffic_source_id: Mapped[int] = mapped_column(Integer)
    geo_stream_id: Mapped[int] = mapped_column(Integer)
    offer_stream_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RemovedOffer(Base):
    """Офферы, удалённые из потока через редактор: их можно вернуть позже."""

    __tablename__ = "removed_offers"
    __table_args__ = (UniqueConstraint("stream_id", "offer_id", name="uq_removed_offer_stream_offer"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(Integer, index=True)
    stream_id: Mapped[int] = mapped_column(Integer, index=True)
    offer_id: Mapped[int] = mapped_column(Integer)
    offer_name: Mapped[str] = mapped_column(String(512), default="")
    share: Mapped[int] = mapped_column(Integer, default=0)  # доля на момент удаления
    removed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PinnedOffer(Base):
    """Пин блокирует пересчёт доли оффера в потоке."""

    __tablename__ = "pinned_offers"
    __table_args__ = (UniqueConstraint("stream_id", "offer_id", name="uq_pinned_offer_stream_offer"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stream_id: Mapped[int] = mapped_column(Integer, index=True)
    offer_id: Mapped[int] = mapped_column(Integer)
