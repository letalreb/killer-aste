"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from __future__ import annotations

from alembic import op

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE propertytype AS ENUM
                ('apartment','villa','commercial','land','industrial','garage','other');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;

        DO $$ BEGIN
            CREATE TYPE auctionstatus AS ENUM
                ('scheduled','ongoing','completed','suspended','failed','cancelled');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;

        DO $$ BEGIN
            CREATE TYPE auctiontype AS ENUM
                ('asincrona_telematica','sincrona_telematica','mista',
                 'tradizionale','senza_incanto');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;

        DO $$ BEGIN
            CREATE TYPE riskseverity AS ENUM ('low','medium','high','critical');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;

        DO $$ BEGIN
            CREATE TYPE ingestionstatus AS ENUM
                ('running','completed','failed','dry_run');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;

        CREATE TABLE IF NOT EXISTS properties (
            id          UUID            NOT NULL DEFAULT gen_random_uuid(),
            external_id VARCHAR(128)    NOT NULL,
            source      VARCHAR(64)     NOT NULL DEFAULT 'pvp',
            address     TEXT,
            city        VARCHAR(128),
            province    VARCHAR(4),
            region      VARCHAR(64),
            postal_code VARCHAR(10),
            latitude    NUMERIC(10,7),
            longitude   NUMERIC(10,7),
            property_type   propertytype NOT NULL DEFAULT 'other',
            area_sqm    NUMERIC(10,2),
            floor       INTEGER,
            total_floors INTEGER,
            rooms       INTEGER,
            bathrooms   INTEGER,
            has_elevator    BOOLEAN,
            has_parking     BOOLEAN,
            has_garden      BOOLEAN,
            condition_notes TEXT,
            cadastral_reference VARCHAR(128),
            encumbrances    TEXT,
            market_value_estimate NUMERIC(14,2),
            description TEXT,
            extra       JSONB,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id),
            CONSTRAINT uq_property_external_source UNIQUE (external_id, source)
        );
        CREATE INDEX IF NOT EXISTS ix_properties_city        ON properties (city);
        CREATE INDEX IF NOT EXISTS ix_properties_province    ON properties (province);
        CREATE INDEX IF NOT EXISTS ix_properties_type        ON properties (property_type);
        CREATE INDEX IF NOT EXISTS ix_properties_updated_at  ON properties (updated_at);

        CREATE TABLE IF NOT EXISTS auctions (
            id              UUID        NOT NULL DEFAULT gen_random_uuid(),
            property_id     UUID        NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
            external_id     VARCHAR(128) NOT NULL,
            source          VARCHAR(64)  NOT NULL DEFAULT 'pvp',
            court           VARCHAR(256),
            court_code      VARCHAR(32),
            procedure_number VARCHAR(64),
            judge           VARCHAR(256),
            delegate        VARCHAR(256),
            auction_type    auctiontype  NOT NULL DEFAULT 'asincrona_telematica',
            status          auctionstatus NOT NULL DEFAULT 'scheduled',
            base_price      NUMERIC(14,2),
            minimum_bid     NUMERIC(14,2),
            bid_increment   NUMERIC(14,2),
            deposit_required NUMERIC(14,2),
            winning_bid     NUMERIC(14,2),
            auction_date    TIMESTAMPTZ,
            auction_deadline TIMESTAMPTZ,
            publication_date TIMESTAMPTZ,
            source_url      TEXT,
            legal_notes     TEXT,
            expert_report_url TEXT,
            extra           JSONB,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id),
            CONSTRAINT uq_auction_external_source UNIQUE (external_id, source)
        );
        CREATE INDEX IF NOT EXISTS ix_auctions_property_id  ON auctions (property_id);
        CREATE INDEX IF NOT EXISTS ix_auctions_status       ON auctions (status);
        CREATE INDEX IF NOT EXISTS ix_auctions_auction_date ON auctions (auction_date);
        CREATE INDEX IF NOT EXISTS ix_auctions_court        ON auctions (court);
        CREATE INDEX IF NOT EXISTS ix_auctions_updated_at   ON auctions (updated_at);

        CREATE TABLE IF NOT EXISTS valuations (
            id                      UUID NOT NULL DEFAULT gen_random_uuid(),
            auction_id              UUID NOT NULL REFERENCES auctions(id) ON DELETE CASCADE,
            market_value            NUMERIC(14,2),
            purchase_price          NUMERIC(14,2),
            estimated_renovation_cost NUMERIC(14,2),
            estimated_legal_cost    NUMERIC(14,2),
            estimated_tax_cost      NUMERIC(14,2),
            estimated_notary_cost   NUMERIC(14,2),
            total_acquisition_cost  NUMERIC(14,2),
            gross_profit_estimate   NUMERIC(14,2),
            net_profit_estimate     NUMERIC(14,2),
            roi_percentage          NUMERIC(8,4),
            payback_years           NUMERIC(6,2),
            methodology             VARCHAR(64) DEFAULT 'standard_v1',
            assumptions             JSONB,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id)
        );
        CREATE INDEX IF NOT EXISTS ix_valuations_auction_id ON valuations (auction_id);
        CREATE INDEX IF NOT EXISTS ix_valuations_roi        ON valuations (roi_percentage);

        CREATE TABLE IF NOT EXISTS risk_flags (
            id                  UUID NOT NULL DEFAULT gen_random_uuid(),
            auction_id          UUID NOT NULL REFERENCES auctions(id) ON DELETE CASCADE,
            flag_type           VARCHAR(64) NOT NULL,
            severity            riskseverity NOT NULL DEFAULT 'low',
            score_contribution  NUMERIC(6,2),
            description         TEXT NOT NULL,
            extra               JSONB,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id)
        );
        CREATE INDEX IF NOT EXISTS ix_risk_flags_auction_id ON risk_flags (auction_id);
        CREATE INDEX IF NOT EXISTS ix_risk_flags_severity   ON risk_flags (severity);
        CREATE INDEX IF NOT EXISTS ix_risk_flags_type       ON risk_flags (flag_type);

        CREATE TABLE IF NOT EXISTS ingestion_log (
            id              UUID NOT NULL DEFAULT gen_random_uuid(),
            run_id          VARCHAR(64) NOT NULL,
            source          VARCHAR(64) NOT NULL,
            mode            VARCHAR(32) NOT NULL,
            started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at    TIMESTAMPTZ,
            status          ingestionstatus NOT NULL DEFAULT 'running',
            pages_fetched   INTEGER DEFAULT 0,
            records_found   INTEGER DEFAULT 0,
            records_inserted INTEGER DEFAULT 0,
            records_updated INTEGER DEFAULT 0,
            errors_count    INTEGER DEFAULT 0,
            requests_made   INTEGER DEFAULT 0,
            error_detail    TEXT,
            extra           JSONB,
            PRIMARY KEY (id)
        );
        CREATE INDEX IF NOT EXISTS ix_ingestion_log_run_id     ON ingestion_log (run_id);
        CREATE INDEX IF NOT EXISTS ix_ingestion_log_source     ON ingestion_log (source);
        CREATE INDEX IF NOT EXISTS ix_ingestion_log_started_at ON ingestion_log (started_at);
        CREATE INDEX IF NOT EXISTS ix_ingestion_log_status     ON ingestion_log (status);
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS ingestion_log;
        DROP TABLE IF EXISTS risk_flags;
        DROP TABLE IF EXISTS valuations;
        DROP TABLE IF EXISTS auctions;
        DROP TABLE IF EXISTS properties;
        DROP TYPE IF EXISTS propertytype;
        DROP TYPE IF EXISTS auctionstatus;
        DROP TYPE IF EXISTS auctiontype;
        DROP TYPE IF EXISTS riskseverity;
        DROP TYPE IF EXISTS ingestionstatus;
    """)
