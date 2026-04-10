-- Migration 015: STAFF role, is_active on profiles, staff_permissions table + RLS
-- Run after 014_whatsapp_credentials.sql

-- 1. Extend user_role enum
ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'STAFF';

-- 2. Add is_active to profiles
ALTER TABLE profiles
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

-- 3. staff_permissions table
CREATE TABLE IF NOT EXISTS staff_permissions (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id                UUID NOT NULL UNIQUE REFERENCES profiles(id) ON DELETE CASCADE,
    company_id                UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,

    -- Clients
    view_clients              BOOLEAN NOT NULL DEFAULT FALSE,
    manage_clients            BOOLEAN NOT NULL DEFAULT FALSE,

    -- Lots / Developments
    view_lots                 BOOLEAN NOT NULL DEFAULT FALSE,
    manage_lots               BOOLEAN NOT NULL DEFAULT FALSE,

    -- Financial / Boletos
    view_financial            BOOLEAN NOT NULL DEFAULT FALSE,
    manage_financial          BOOLEAN NOT NULL DEFAULT FALSE,

    -- Renegotiations
    view_renegotiations       BOOLEAN NOT NULL DEFAULT FALSE,
    manage_renegotiations     BOOLEAN NOT NULL DEFAULT FALSE,

    -- Rescissions
    view_rescissions          BOOLEAN NOT NULL DEFAULT FALSE,
    manage_rescissions        BOOLEAN NOT NULL DEFAULT FALSE,

    -- Reports (read-only)
    view_reports              BOOLEAN NOT NULL DEFAULT FALSE,

    -- Service Requests
    view_service_requests     BOOLEAN NOT NULL DEFAULT FALSE,
    manage_service_requests   BOOLEAN NOT NULL DEFAULT FALSE,

    -- Documents
    view_documents            BOOLEAN NOT NULL DEFAULT FALSE,
    manage_documents          BOOLEAN NOT NULL DEFAULT FALSE,

    -- Sicredi integration
    view_sicredi              BOOLEAN NOT NULL DEFAULT FALSE,
    manage_sicredi            BOOLEAN NOT NULL DEFAULT FALSE,

    -- WhatsApp integration
    view_whatsapp             BOOLEAN NOT NULL DEFAULT FALSE,
    manage_whatsapp           BOOLEAN NOT NULL DEFAULT FALSE,

    -- Company financial settings
    view_financial_settings   BOOLEAN NOT NULL DEFAULT FALSE,
    manage_financial_settings BOOLEAN NOT NULL DEFAULT FALSE,

    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_staff_permissions_company ON staff_permissions(company_id);
CREATE INDEX IF NOT EXISTS idx_staff_permissions_profile ON staff_permissions(profile_id);

-- 4. Enable RLS
ALTER TABLE staff_permissions ENABLE ROW LEVEL SECURITY;

-- COMPANY_ADMIN: full CRUD on their company's staff permissions
CREATE POLICY staff_permissions_admin_all ON staff_permissions
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

-- STAFF: can only read their own permissions row
CREATE POLICY staff_permissions_self_select ON staff_permissions
    FOR SELECT
    USING (profile_id = auth.uid());

-- 5. updated_at auto-update trigger
CREATE OR REPLACE FUNCTION update_staff_permissions_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_staff_permissions_updated_at ON staff_permissions;
CREATE TRIGGER trg_staff_permissions_updated_at
    BEFORE UPDATE ON staff_permissions
    FOR EACH ROW EXECUTE FUNCTION update_staff_permissions_updated_at();
