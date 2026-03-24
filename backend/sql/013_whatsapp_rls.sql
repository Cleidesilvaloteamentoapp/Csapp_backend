-- =============================================================================
-- WhatsApp Credentials – Row Level Security policies
-- =============================================================================
-- Table: whatsapp_credentials
-- Classification: CRITICAL (contains API tokens and secrets)
-- Isolation: company_id via user_organizations membership
-- =============================================================================

-- Enable RLS
ALTER TABLE whatsapp_credentials ENABLE ROW LEVEL SECURITY;

-- Force RLS for table owner too
ALTER TABLE whatsapp_credentials FORCE ROW LEVEL SECURITY;

-- SELECT: users can only see credentials for their own company
CREATE POLICY "whatsapp_credentials_select_own_company"
  ON whatsapp_credentials
  FOR SELECT
  USING (
    company_id IN (
      SELECT company_id FROM profiles WHERE id = auth.uid()
    )
  );

-- INSERT: users can only insert credentials for their own company
CREATE POLICY "whatsapp_credentials_insert_own_company"
  ON whatsapp_credentials
  FOR INSERT
  WITH CHECK (
    company_id IN (
      SELECT company_id FROM profiles WHERE id = auth.uid()
    )
  );

-- UPDATE: users can only update credentials for their own company
CREATE POLICY "whatsapp_credentials_update_own_company"
  ON whatsapp_credentials
  FOR UPDATE
  USING (
    company_id IN (
      SELECT company_id FROM profiles WHERE id = auth.uid()
    )
  );

-- DELETE: users can only delete credentials for their own company
CREATE POLICY "whatsapp_credentials_delete_own_company"
  ON whatsapp_credentials
  FOR DELETE
  USING (
    company_id IN (
      SELECT company_id FROM profiles WHERE id = auth.uid()
    )
  );
