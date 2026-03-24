-- =============================================================================
-- DDL + RLS for whatsapp_credentials
-- Per-company WhatsApp provider credentials (UAZAPI or Meta Cloud API)
-- Corresponds to Alembic migration: 008_whatsapp_credentials
-- Run this in the Supabase SQL Editor
-- =============================================================================

-- 1. Enum type
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'whatsapp_provider_type') THEN
        CREATE TYPE whatsapp_provider_type AS ENUM ('UAZAPI', 'META');
    END IF;
END$$;

-- 2. Table
CREATE TABLE IF NOT EXISTS whatsapp_credentials (
    id                   UUID                    PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id           UUID                    NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    provider             whatsapp_provider_type  NOT NULL,

    is_active            BOOLEAN                 NOT NULL DEFAULT true,
    is_default           BOOLEAN                 NOT NULL DEFAULT false,

    -- UAZAPI fields (CONFIDENTIAL)
    uazapi_base_url      VARCHAR(500),
    uazapi_instance_token TEXT,

    -- Meta Cloud API fields (CRITICAL)
    meta_waba_id         VARCHAR(100),
    meta_phone_number_id VARCHAR(100),
    meta_access_token    TEXT,

    -- Connection status cache
    connection_status    VARCHAR(20)             DEFAULT 'unknown',
    last_status_check    TIMESTAMPTZ,

    -- Timestamps
    created_at           TIMESTAMPTZ             NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ             NOT NULL DEFAULT now(),

    -- One credential per provider per company
    CONSTRAINT uq_whatsapp_company_provider UNIQUE (company_id, provider)
);

-- 3. Index
CREATE INDEX IF NOT EXISTS ix_whatsapp_credentials_company
    ON whatsapp_credentials (company_id);

-- 4. updated_at trigger (reuses existing trigger function)
CREATE TRIGGER set_updated_at
    BEFORE UPDATE ON whatsapp_credentials
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- =============================================================================
-- Row Level Security
-- =============================================================================

ALTER TABLE whatsapp_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE whatsapp_credentials FORCE ROW LEVEL SECURITY;

-- SUPER_ADMIN: full access across all companies
CREATE POLICY "super_admin_full_whatsapp_credentials"
    ON whatsapp_credentials
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM profiles
            WHERE profiles.id = auth.uid()
              AND profiles.role = 'SUPER_ADMIN'
        )
    );

-- COMPANY_ADMIN: manage own company credentials
CREATE POLICY "company_admin_manage_whatsapp_credentials"
    ON whatsapp_credentials
    FOR ALL
    USING (
        company_id IN (
            SELECT p.company_id FROM profiles p
            WHERE p.id = auth.uid()
              AND p.role = 'COMPANY_ADMIN'
        )
    )
    WITH CHECK (
        company_id IN (
            SELECT p.company_id FROM profiles p
            WHERE p.id = auth.uid()
              AND p.role = 'COMPANY_ADMIN'
        )
    );

-- CLIENT: no access (tokens are internal, never exposed to clients)
-- (no policy = deny by default when RLS is active)
