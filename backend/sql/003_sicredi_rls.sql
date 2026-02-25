-- =============================================================================
-- Row Level Security (RLS) for sicredi_credentials table
-- CRITICAL: Contains API credentials and OAuth tokens – strict isolation required.
-- =============================================================================

ALTER TABLE sicredi_credentials ENABLE ROW LEVEL SECURITY;

-- Super admin: full access
CREATE POLICY "sicredi_creds_super_admin_all" ON sicredi_credentials
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role = 'SUPER_ADMIN'
    )
  );

-- Company admin: only own company's credentials
CREATE POLICY "sicredi_creds_company_isolation" ON sicredi_credentials
  FOR ALL
  USING (
    company_id IN (
      SELECT p.company_id FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role IN ('SUPER_ADMIN', 'COMPANY_ADMIN')
    )
  );

-- Performance index
CREATE INDEX IF NOT EXISTS idx_sicredi_creds_company_active
  ON sicredi_credentials (company_id, is_active);
