-- Migration 021: company_branding table + RLS
-- Mirrors alembic/versions/018_company_branding.py
-- Run after 020_writeoff_type_baixa_externa.sql
-- Safe to re-run in the Supabase SQL Editor (idempotent).

-- 1. Table
CREATE TABLE IF NOT EXISTS company_branding (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id        UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,

    -- Seed colours (#RRGGBB). NULL means "use the platform default".
    primary_color     VARCHAR(7),
    accent_color      VARCHAR(7),
    sidebar_color     VARCHAR(7),
    background_color  VARCHAR(7),
    success_color     VARCHAR(7),

    -- Base border radius, e.g. '0.625rem'
    radius            VARCHAR(16),

    -- Supabase Storage paths (never URLs)
    logo_path         TEXT,
    favicon_path      TEXT,
    app_icon_path     TEXT,

    -- Wording overrides
    display_name      VARCHAR(60),
    tagline           VARCHAR(80),

    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_company_branding_company UNIQUE (company_id)
);

CREATE INDEX IF NOT EXISTS ix_company_branding_company_id
    ON company_branding (company_id);

-- 2. RLS
ALTER TABLE company_branding ENABLE ROW LEVEL SECURITY;

-- COMPANY_ADMIN / SUPER_ADMIN: full CRUD on their company's branding
DROP POLICY IF EXISTS company_branding_admin_all ON company_branding;
CREATE POLICY company_branding_admin_all ON company_branding
    FOR ALL
    USING (
        company_id IN (
            SELECT company_id FROM profiles
            WHERE id = auth.uid()
              AND role IN ('COMPANY_ADMIN', 'SUPER_ADMIN')
        )
    )
    WITH CHECK (
        company_id IN (
            SELECT company_id FROM profiles
            WHERE id = auth.uid()
              AND role IN ('COMPANY_ADMIN', 'SUPER_ADMIN')
        )
    );

-- Every member of the company can read it: the client portal is branded too.
DROP POLICY IF EXISTS company_branding_member_select ON company_branding;
CREATE POLICY company_branding_member_select ON company_branding
    FOR SELECT
    USING (
        company_id IN (
            SELECT company_id FROM profiles WHERE id = auth.uid()
        )
    );

-- 3. updated_at auto-update trigger
CREATE OR REPLACE FUNCTION update_company_branding_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_company_branding_updated_at ON company_branding;
CREATE TRIGGER trg_company_branding_updated_at
    BEFORE UPDATE ON company_branding
    FOR EACH ROW EXECUTE FUNCTION update_company_branding_updated_at();
