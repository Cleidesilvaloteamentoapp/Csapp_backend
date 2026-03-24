-- =============================================================================
-- DDL + RLS for company_financial_settings
-- One row per company with global financial defaults
-- =============================================================================

CREATE TABLE IF NOT EXISTS company_financial_settings (
    id               UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       UUID            NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    penalty_rate     NUMERIC(6,4)    NOT NULL DEFAULT 0.02,
    daily_interest_rate NUMERIC(8,6) NOT NULL DEFAULT 0.000330,
    adjustment_index adjustment_index NOT NULL DEFAULT 'IPCA',
    adjustment_frequency adjustment_frequency NOT NULL DEFAULT 'ANNUAL',
    adjustment_custom_rate NUMERIC(6,4) NOT NULL DEFAULT 0.05,
    created_at       TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ     NOT NULL DEFAULT now(),
    CONSTRAINT uq_company_financial_settings_company UNIQUE (company_id)
);

CREATE INDEX IF NOT EXISTS ix_cfs_company ON company_financial_settings (company_id);

-- Trigger updated_at
CREATE TRIGGER set_updated_at BEFORE UPDATE ON company_financial_settings
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- =============================================================================
-- RLS Policies
-- =============================================================================

ALTER TABLE company_financial_settings ENABLE ROW LEVEL SECURITY;

-- SUPER_ADMIN: full access
CREATE POLICY "super_admin_full_access_cfs" ON company_financial_settings
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM profiles
            WHERE profiles.id = auth.uid()
              AND profiles.role = 'SUPER_ADMIN'
        )
    );

-- COMPANY_ADMIN: read/write own company settings
CREATE POLICY "company_admin_manage_cfs" ON company_financial_settings
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

-- CLIENT: read-only own company settings (to display effective rates)
CREATE POLICY "client_read_cfs" ON company_financial_settings
    FOR SELECT
    USING (
        company_id IN (
            SELECT c.company_id FROM clients c
            JOIN profiles p ON p.id = auth.uid()
            WHERE c.profile_id = p.id
        )
    );
