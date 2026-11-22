"""user favorites (server-side, limit enforced by the API)

Revision ID: 004_user_favorites
Revises: 003_public_enrichment
Create Date: 2026-11-22 00:00:00.000000
"""
from __future__ import annotations

from alembic import op

revision = "004_user_favorites"
down_revision = "003_public_enrichment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_favorites (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            auction_id  UUID NOT NULL REFERENCES auctions (id) ON DELETE CASCADE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_user_favorites_user_auction UNIQUE (user_id, auction_id)
        );
        CREATE INDEX IF NOT EXISTS ix_user_favorites_user_id ON user_favorites (user_id);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_favorites;")
