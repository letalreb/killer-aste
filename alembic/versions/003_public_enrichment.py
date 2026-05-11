"""public enrichment layer — opportunities, property links, enrichment signals

Revision ID: 003_public_enrichment
Revises: 002_users_audit
Create Date: 2026-05-11 00:00:00.000000
"""
from __future__ import annotations

from alembic import op

revision = "003_public_enrichment"
down_revision = "002_users_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE opportunitytype AS ENUM (
                'piano_urbanistico',
                'alienazione_pubblica',
                'rigenerazione_urbana',
                'investimento_infrastrutturale',
                'piano_recupero',
                'pnrr_progetto',
                'dismissione_pubblica',
                'valorizzazione_immobiliare',
                'altro'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;

        DO $$ BEGIN
            CREATE TYPE opportunitystatus AS ENUM (
                'active', 'completed', 'cancelled', 'unknown'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;

        CREATE TABLE IF NOT EXISTS public_opportunities (
            id                  UUID            NOT NULL DEFAULT gen_random_uuid(),
            title               TEXT            NOT NULL,
            opportunity_type    opportunitytype NOT NULL DEFAULT 'altro',
            status              opportunitystatus NOT NULL DEFAULT 'active',
            source              VARCHAR(256),
            source_url          TEXT,
            province            VARCHAR(4),
            city                VARCHAR(128),
            latitude            NUMERIC(10,7),
            longitude           NUMERIC(10,7),
            description         TEXT,
            budget_amount       NUMERIC(14,2),
            expected_completion VARCHAR(64),
            document_url        TEXT,
            raw_text            TEXT,
            extra               JSONB,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id)
        );
        CREATE INDEX IF NOT EXISTS ix_pub_opp_province ON public_opportunities (province);
        CREATE INDEX IF NOT EXISTS ix_pub_opp_city     ON public_opportunities (city);
        CREATE INDEX IF NOT EXISTS ix_pub_opp_type     ON public_opportunities (opportunity_type);
        CREATE INDEX IF NOT EXISTS ix_pub_opp_status   ON public_opportunities (status);

        CREATE TABLE IF NOT EXISTS property_opportunity_links (
            id              UUID NOT NULL DEFAULT gen_random_uuid(),
            property_id     UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
            opportunity_id  UUID NOT NULL REFERENCES public_opportunities(id) ON DELETE CASCADE,
            distance_km     NUMERIC(6,3),
            relevance_score NUMERIC(5,2),
            extra           JSONB,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id),
            CONSTRAINT uq_prop_opp_link UNIQUE (property_id, opportunity_id)
        );
        CREATE INDEX IF NOT EXISTS ix_prop_opp_links_property_id
            ON property_opportunity_links (property_id);
        CREATE INDEX IF NOT EXISTS ix_prop_opp_links_opportunity_id
            ON property_opportunity_links (opportunity_id);

        CREATE TABLE IF NOT EXISTS enrichment_signals (
            id          UUID        NOT NULL DEFAULT gen_random_uuid(),
            property_id UUID        NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
            signal_type VARCHAR(64) NOT NULL,
            value       TEXT,
            confidence  NUMERIC(4,3),
            source      VARCHAR(256),
            extra       JSONB,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id)
        );
        CREATE INDEX IF NOT EXISTS ix_enrichment_signals_property_id
            ON enrichment_signals (property_id);
        CREATE INDEX IF NOT EXISTS ix_enrichment_signals_type
            ON enrichment_signals (signal_type);
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS enrichment_signals;
        DROP TABLE IF EXISTS property_opportunity_links;
        DROP TABLE IF EXISTS public_opportunities;
        DROP TYPE IF EXISTS opportunitystatus;
        DROP TYPE IF EXISTS opportunitytype;
    """)
