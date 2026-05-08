"""
SQLAlchemy 2.0 ORM models.

Design decisions:
- UUID primary keys (no sequential enumeration via API)
- external_id  = stable identifier from the source portal
- All tables carry created_at / updated_at for incremental sync
- JSONB columns for flexible data that varies per auction type
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

_CASCADE = "all, delete-orphan"
_ENUM_VALS = {"values_callable": lambda obj: [e.value for e in obj]}


class Base(DeclarativeBase):
    pass


class PropertyType(str, PyEnum):
    APARTMENT = "apartment"
    VILLA = "villa"
    COMMERCIAL = "commercial"
    LAND = "land"
    INDUSTRIAL = "industrial"
    GARAGE = "garage"
    OTHER = "other"


class AuctionStatus(str, PyEnum):
    SCHEDULED = "scheduled"
    ONGOING = "ongoing"
    COMPLETED = "completed"
    SUSPENDED = "suspended"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AuctionType(str, PyEnum):
    ASINCRONA_TELEMATICA = "asincrona_telematica"
    SINCRONA_TELEMATICA = "sincrona_telematica"
    MISTA = "mista"
    TRADIZIONALE = "tradizionale"
    SENZA_INCANTO = "senza_incanto"


class RiskSeverity(str, PyEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IngestionStatus(str, PyEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DRY_RUN = "dry_run"


class UserRole(str, PyEnum):
    STANDARD = "standard"
    PREMIUM = "premium"
    ADMIN = "admin"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Property(TimestampMixin, Base):
    __tablename__ = "properties"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="pvp")

    address: Mapped[Optional[str]] = mapped_column(Text)
    city: Mapped[Optional[str]] = mapped_column(String(128))
    province: Mapped[Optional[str]] = mapped_column(String(4))
    region: Mapped[Optional[str]] = mapped_column(String(64))
    postal_code: Mapped[Optional[str]] = mapped_column(String(10))
    latitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 7))

    property_type: Mapped[PropertyType] = mapped_column(
        Enum(PropertyType, **_ENUM_VALS), nullable=False, default=PropertyType.OTHER
    )
    area_sqm: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    floor: Mapped[Optional[int]] = mapped_column(Integer)
    total_floors: Mapped[Optional[int]] = mapped_column(Integer)
    rooms: Mapped[Optional[int]] = mapped_column(Integer)
    bathrooms: Mapped[Optional[int]] = mapped_column(Integer)
    has_elevator: Mapped[Optional[bool]] = mapped_column(Boolean)
    has_parking: Mapped[Optional[bool]] = mapped_column(Boolean)
    has_garden: Mapped[Optional[bool]] = mapped_column(Boolean)
    condition_notes: Mapped[Optional[str]] = mapped_column(Text)

    cadastral_reference: Mapped[Optional[str]] = mapped_column(String(128))
    encumbrances: Mapped[Optional[str]] = mapped_column(Text)

    market_value_estimate: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    description: Mapped[Optional[str]] = mapped_column(Text)
    extra: Mapped[Optional[dict]] = mapped_column(JSONB)

    auctions: Mapped[list["Auction"]] = relationship(
        "Auction", back_populates="property", cascade=_CASCADE
    )

    __table_args__ = (
        UniqueConstraint("external_id", "source", name="uq_property_external_source"),
        Index("ix_properties_city", "city"),
        Index("ix_properties_province", "province"),
        Index("ix_properties_type", "property_type"),
        Index("ix_properties_updated_at", "updated_at"),
    )


class Auction(TimestampMixin, Base):
    __tablename__ = "auctions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="pvp")

    court: Mapped[Optional[str]] = mapped_column(String(256))
    court_code: Mapped[Optional[str]] = mapped_column(String(32))
    procedure_number: Mapped[Optional[str]] = mapped_column(String(64))
    judge: Mapped[Optional[str]] = mapped_column(String(256))
    delegate: Mapped[Optional[str]] = mapped_column(String(256))

    auction_type: Mapped[AuctionType] = mapped_column(
        Enum(AuctionType, **_ENUM_VALS), nullable=False, default=AuctionType.ASINCRONA_TELEMATICA
    )
    status: Mapped[AuctionStatus] = mapped_column(
        Enum(AuctionStatus, **_ENUM_VALS), nullable=False, default=AuctionStatus.SCHEDULED
    )

    base_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    minimum_bid: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    bid_increment: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    deposit_required: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    winning_bid: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))

    auction_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    auction_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    publication_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    source_url: Mapped[Optional[str]] = mapped_column(Text)
    legal_notes: Mapped[Optional[str]] = mapped_column(Text)
    expert_report_url: Mapped[Optional[str]] = mapped_column(Text)
    extra: Mapped[Optional[dict]] = mapped_column(JSONB)

    property: Mapped["Property"] = relationship("Property", back_populates="auctions")
    valuations: Mapped[list["Valuation"]] = relationship(
        "Valuation", back_populates="auction", cascade=_CASCADE
    )
    risk_flags: Mapped[list["RiskFlag"]] = relationship(
        "RiskFlag", back_populates="auction", cascade=_CASCADE
    )

    __table_args__ = (
        UniqueConstraint("external_id", "source", name="uq_auction_external_source"),
        Index("ix_auctions_property_id", "property_id"),
        Index("ix_auctions_status", "status"),
        Index("ix_auctions_auction_date", "auction_date"),
        Index("ix_auctions_court", "court"),
        Index("ix_auctions_updated_at", "updated_at"),
    )


class Valuation(TimestampMixin, Base):
    __tablename__ = "valuations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    auction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auctions.id"), nullable=False
    )

    market_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    purchase_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))

    estimated_renovation_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    estimated_legal_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    estimated_tax_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    estimated_notary_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    total_acquisition_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))

    gross_profit_estimate: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    net_profit_estimate: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    roi_percentage: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    payback_years: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))

    methodology: Mapped[str] = mapped_column(String(64), default="standard_v1")
    assumptions: Mapped[Optional[dict]] = mapped_column(JSONB)

    auction: Mapped["Auction"] = relationship("Auction", back_populates="valuations")

    __table_args__ = (
        Index("ix_valuations_auction_id", "auction_id"),
        Index("ix_valuations_roi", "roi_percentage"),
    )


class RiskFlag(TimestampMixin, Base):
    __tablename__ = "risk_flags"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    auction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auctions.id"), nullable=False
    )

    flag_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[RiskSeverity] = mapped_column(
        Enum(RiskSeverity, **_ENUM_VALS), nullable=False, default=RiskSeverity.LOW
    )
    score_contribution: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    extra: Mapped[Optional[dict]] = mapped_column(JSONB)

    auction: Mapped["Auction"] = relationship("Auction", back_populates="risk_flags")

    __table_args__ = (
        Index("ix_risk_flags_auction_id", "auction_id"),
        Index("ix_risk_flags_severity", "severity"),
        Index("ix_risk_flags_type", "flag_type"),
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    google_sub: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(256), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    picture: Mapped[Optional[str]] = mapped_column(Text)

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, **_ENUM_VALS), nullable=False, default=UserRole.STANDARD
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_favorites: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    preferences: Mapped[Optional[dict]] = mapped_column(JSONB)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    login_audits: Mapped[list["LoginAudit"]] = relationship(
        "LoginAudit", back_populates="user", cascade=_CASCADE
    )

    __table_args__ = (
        Index("ix_users_email", "email"),
        Index("ix_users_role", "role"),
    )


class LoginAudit(Base):
    __tablename__ = "login_audits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    logged_in_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    extra: Mapped[Optional[dict]] = mapped_column(JSONB)

    user: Mapped["User"] = relationship("User", back_populates="login_audits")

    __table_args__ = (
        Index("ix_login_audits_user_id", "user_id"),
        Index("ix_login_audits_logged_in_at", "logged_in_at"),
    )


class IngestionLog(Base):
    __tablename__ = "ingestion_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    status: Mapped[IngestionStatus] = mapped_column(
        Enum(IngestionStatus, **_ENUM_VALS), nullable=False, default=IngestionStatus.RUNNING
    )

    pages_fetched: Mapped[int] = mapped_column(Integer, default=0)
    records_found: Mapped[int] = mapped_column(Integer, default=0)
    records_inserted: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    errors_count: Mapped[int] = mapped_column(Integer, default=0)
    requests_made: Mapped[int] = mapped_column(Integer, default=0)

    error_detail: Mapped[Optional[str]] = mapped_column(Text)
    extra: Mapped[Optional[dict]] = mapped_column(JSONB)

    __table_args__ = (
        Index("ix_ingestion_log_source", "source"),
        Index("ix_ingestion_log_started_at", "started_at"),
        Index("ix_ingestion_log_status", "status"),
    )
