"""users and login audit tables

Revision ID: 002_users_audit
Revises: 001_initial
Create Date: 2026-05-08 00:00:00.000000
"""
from __future__ import annotations

from alembic import op

revision = "002_users_audit"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE userrole AS ENUM ('standard', 'premium', 'admin');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;

        CREATE TABLE IF NOT EXISTS users (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            google_sub      VARCHAR(128) NOT NULL UNIQUE,
            email           VARCHAR(256) NOT NULL,
            name            VARCHAR(256) NOT NULL,
            picture         TEXT,
            role            userrole NOT NULL DEFAULT 'standard',
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            max_favorites   INTEGER NOT NULL DEFAULT 3,
            preferences     JSONB,
            last_login_at   TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS ix_users_email  ON users (email);
        CREATE INDEX IF NOT EXISTS ix_users_role   ON users (role);

        CREATE TABLE IF NOT EXISTS login_audits (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            logged_in_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ip_address    VARCHAR(64),
            user_agent    TEXT,
            extra         JSONB
        );

        CREATE INDEX IF NOT EXISTS ix_login_audits_user_id      ON login_audits (user_id);
        CREATE INDEX IF NOT EXISTS ix_login_audits_logged_in_at ON login_audits (logged_in_at);
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS login_audits;
        DROP TABLE IF EXISTS users;
        DROP TYPE IF EXISTS userrole;
    """)
