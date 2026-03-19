-- =============================================================================
-- RLS Policies for Client Adjustments tables
-- Run AFTER migration 006_client_adjustments
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Enable RLS
-- ---------------------------------------------------------------------------
ALTER TABLE economic_indices ENABLE ROW LEVEL SECURITY;
ALTER TABLE cycle_approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE contract_transfers ENABLE ROW LEVEL SECURITY;
ALTER TABLE early_payoff_requests ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- ECONOMIC_INDICES
-- ---------------------------------------------------------------------------

CREATE POLICY "economic_indices_super_admin_all" ON economic_indices
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role = 'SUPER_ADMIN'
    )
  );

CREATE POLICY "economic_indices_company_admin" ON economic_indices
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role = 'COMPANY_ADMIN'
      AND p.company_id = economic_indices.company_id
    )
  );

-- ---------------------------------------------------------------------------
-- CYCLE_APPROVALS
-- ---------------------------------------------------------------------------

CREATE POLICY "cycle_approvals_super_admin_all" ON cycle_approvals
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role = 'SUPER_ADMIN'
    )
  );

CREATE POLICY "cycle_approvals_company_admin" ON cycle_approvals
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role = 'COMPANY_ADMIN'
      AND p.company_id = cycle_approvals.company_id
    )
  );

-- ---------------------------------------------------------------------------
-- CONTRACT_TRANSFERS
-- ---------------------------------------------------------------------------

CREATE POLICY "contract_transfers_super_admin_all" ON contract_transfers
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role = 'SUPER_ADMIN'
    )
  );

CREATE POLICY "contract_transfers_company_admin" ON contract_transfers
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role = 'COMPANY_ADMIN'
      AND p.company_id = contract_transfers.company_id
    )
  );

-- Clients can see transfers involving them (read-only)
CREATE POLICY "contract_transfers_client_select" ON contract_transfers
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      JOIN clients c ON c.profile_id = p.id
      WHERE p.id = auth.uid()
      AND p.role = 'CLIENT'
      AND (c.id = contract_transfers.from_client_id OR c.id = contract_transfers.to_client_id)
    )
  );

-- ---------------------------------------------------------------------------
-- EARLY_PAYOFF_REQUESTS
-- ---------------------------------------------------------------------------

CREATE POLICY "early_payoff_requests_super_admin_all" ON early_payoff_requests
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role = 'SUPER_ADMIN'
    )
  );

CREATE POLICY "early_payoff_requests_company_admin" ON early_payoff_requests
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role = 'COMPANY_ADMIN'
      AND p.company_id = early_payoff_requests.company_id
    )
  );

-- Clients can create and view their own requests
CREATE POLICY "early_payoff_requests_client_select" ON early_payoff_requests
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      JOIN clients c ON c.profile_id = p.id
      WHERE p.id = auth.uid()
      AND p.role = 'CLIENT'
      AND c.id = early_payoff_requests.client_id
    )
  );

CREATE POLICY "early_payoff_requests_client_insert" ON early_payoff_requests
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM profiles p
      JOIN clients c ON c.profile_id = p.id
      WHERE p.id = auth.uid()
      AND p.role = 'CLIENT'
      AND c.id = early_payoff_requests.client_id
    )
  );
