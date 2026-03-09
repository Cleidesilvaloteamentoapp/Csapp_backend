-- =============================================================================
-- RLS Policies for contract_history, renegotiations, rescissions tables
-- Run AFTER migration 004_add_contract_features
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Enable RLS
-- ---------------------------------------------------------------------------
ALTER TABLE contract_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE renegotiations ENABLE ROW LEVEL SECURITY;
ALTER TABLE rescissions ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- CONTRACT_HISTORY
-- ---------------------------------------------------------------------------

CREATE POLICY "contract_history_super_admin_all" ON contract_history
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role = 'SUPER_ADMIN'
    )
  );

CREATE POLICY "contract_history_company_isolation" ON contract_history
  FOR ALL
  USING (
    company_id IN (
      SELECT p.company_id FROM profiles p
      WHERE p.id = auth.uid()
    )
  );

CREATE POLICY "contract_history_client_read" ON contract_history
  FOR SELECT
  USING (
    client_id IN (
      SELECT c.id FROM clients c
      WHERE c.profile_id = auth.uid()
    )
  );

-- ---------------------------------------------------------------------------
-- RENEGOTIATIONS
-- ---------------------------------------------------------------------------

CREATE POLICY "renegotiations_super_admin_all" ON renegotiations
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role = 'SUPER_ADMIN'
    )
  );

CREATE POLICY "renegotiations_company_isolation" ON renegotiations
  FOR ALL
  USING (
    company_id IN (
      SELECT p.company_id FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role IN ('SUPER_ADMIN', 'COMPANY_ADMIN')
    )
  );

CREATE POLICY "renegotiations_client_read" ON renegotiations
  FOR SELECT
  USING (
    client_id IN (
      SELECT c.id FROM clients c
      WHERE c.profile_id = auth.uid()
    )
  );

-- ---------------------------------------------------------------------------
-- RESCISSIONS
-- ---------------------------------------------------------------------------

CREATE POLICY "rescissions_super_admin_all" ON rescissions
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role = 'SUPER_ADMIN'
    )
  );

CREATE POLICY "rescissions_company_isolation" ON rescissions
  FOR ALL
  USING (
    company_id IN (
      SELECT p.company_id FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role IN ('SUPER_ADMIN', 'COMPANY_ADMIN')
    )
  );

CREATE POLICY "rescissions_client_read" ON rescissions
  FOR SELECT
  USING (
    client_id IN (
      SELECT c.id FROM clients c
      WHERE c.profile_id = auth.uid()
    )
  );
