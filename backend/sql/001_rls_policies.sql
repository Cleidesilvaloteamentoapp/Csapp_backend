-- =============================================================================
-- Row Level Security (RLS) Policies for Multi-Tenant Isolation
-- Run this AFTER Alembic migrations create the tables.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Enable RLS on all tenant-aware tables
-- ---------------------------------------------------------------------------
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE developments ENABLE ROW LEVEL SECURITY;
ALTER TABLE lots ENABLE ROW LEVEL SECURITY;
ALTER TABLE client_lots ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE service_types ENABLE ROW LEVEL SECURITY;
ALTER TABLE service_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE referrals ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- PROFILES
-- ---------------------------------------------------------------------------

-- Super admin: full access
CREATE POLICY "profiles_super_admin_all" ON profiles
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role = 'super_admin'
    )
  );

-- Company isolation: users see only their company's profiles
CREATE POLICY "profiles_company_isolation" ON profiles
  FOR ALL
  USING (
    company_id IN (
      SELECT p.company_id FROM profiles p
      WHERE p.id = auth.uid()
    )
  );

-- ---------------------------------------------------------------------------
-- CLIENTS
-- ---------------------------------------------------------------------------

CREATE POLICY "clients_super_admin_all" ON clients
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role = 'super_admin'
    )
  );

CREATE POLICY "clients_company_isolation" ON clients
  FOR ALL
  USING (
    company_id IN (
      SELECT p.company_id FROM profiles p
      WHERE p.id = auth.uid()
    )
  );

-- Client role: only own data
CREATE POLICY "clients_own_data" ON clients
  FOR SELECT
  USING (
    profile_id = auth.uid()
  );

-- ---------------------------------------------------------------------------
-- DEVELOPMENTS
-- ---------------------------------------------------------------------------

CREATE POLICY "developments_super_admin_all" ON developments
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role = 'super_admin'
    )
  );

CREATE POLICY "developments_company_isolation" ON developments
  FOR ALL
  USING (
    company_id IN (
      SELECT p.company_id FROM profiles p
      WHERE p.id = auth.uid()
    )
  );

-- ---------------------------------------------------------------------------
-- LOTS
-- ---------------------------------------------------------------------------

CREATE POLICY "lots_super_admin_all" ON lots
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role = 'super_admin'
    )
  );

CREATE POLICY "lots_company_isolation" ON lots
  FOR ALL
  USING (
    company_id IN (
      SELECT p.company_id FROM profiles p
      WHERE p.id = auth.uid()
    )
  );

-- ---------------------------------------------------------------------------
-- CLIENT_LOTS
-- ---------------------------------------------------------------------------

CREATE POLICY "client_lots_super_admin_all" ON client_lots
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role = 'super_admin'
    )
  );

CREATE POLICY "client_lots_company_isolation" ON client_lots
  FOR ALL
  USING (
    company_id IN (
      SELECT p.company_id FROM profiles p
      WHERE p.id = auth.uid()
    )
  );

-- Client: only own lots
CREATE POLICY "client_lots_own_data" ON client_lots
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM clients c
      WHERE c.id = client_lots.client_id
      AND c.profile_id = auth.uid()
    )
  );

-- ---------------------------------------------------------------------------
-- INVOICES
-- ---------------------------------------------------------------------------

CREATE POLICY "invoices_super_admin_all" ON invoices
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role = 'super_admin'
    )
  );

CREATE POLICY "invoices_company_isolation" ON invoices
  FOR ALL
  USING (
    company_id IN (
      SELECT p.company_id FROM profiles p
      WHERE p.id = auth.uid()
    )
  );

-- Client: only own invoices
CREATE POLICY "invoices_client_own_data" ON invoices
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM client_lots cl
      JOIN clients c ON c.id = cl.client_id
      WHERE cl.id = invoices.client_lot_id
      AND c.profile_id = auth.uid()
    )
  );

-- ---------------------------------------------------------------------------
-- SERVICE_TYPES
-- ---------------------------------------------------------------------------

CREATE POLICY "service_types_super_admin_all" ON service_types
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role = 'super_admin'
    )
  );

CREATE POLICY "service_types_company_isolation" ON service_types
  FOR ALL
  USING (
    company_id IN (
      SELECT p.company_id FROM profiles p
      WHERE p.id = auth.uid()
    )
  );

-- ---------------------------------------------------------------------------
-- SERVICE_ORDERS
-- ---------------------------------------------------------------------------

CREATE POLICY "service_orders_super_admin_all" ON service_orders
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role = 'super_admin'
    )
  );

CREATE POLICY "service_orders_company_isolation" ON service_orders
  FOR ALL
  USING (
    company_id IN (
      SELECT p.company_id FROM profiles p
      WHERE p.id = auth.uid()
    )
  );

-- Client: only own service orders
CREATE POLICY "service_orders_client_own" ON service_orders
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM clients c
      WHERE c.id = service_orders.client_id
      AND c.profile_id = auth.uid()
    )
  );

-- ---------------------------------------------------------------------------
-- REFERRALS
-- ---------------------------------------------------------------------------

CREATE POLICY "referrals_super_admin_all" ON referrals
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role = 'super_admin'
    )
  );

CREATE POLICY "referrals_company_isolation" ON referrals
  FOR ALL
  USING (
    company_id IN (
      SELECT p.company_id FROM profiles p
      WHERE p.id = auth.uid()
    )
  );

-- Client: only own referrals
CREATE POLICY "referrals_client_own" ON referrals
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM clients c
      WHERE c.id = referrals.referrer_client_id
      AND c.profile_id = auth.uid()
    )
  );

-- ---------------------------------------------------------------------------
-- AUDIT_LOGS – only super_admin can read
-- ---------------------------------------------------------------------------

CREATE POLICY "audit_logs_super_admin_only" ON audit_logs
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role = 'super_admin'
    )
  );

-- Insert allowed for all authenticated users (the app writes audit logs)
CREATE POLICY "audit_logs_insert" ON audit_logs
  FOR INSERT
  WITH CHECK (auth.uid() IS NOT NULL);

-- ---------------------------------------------------------------------------
-- Indexes to support RLS performance
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_profiles_company_role ON profiles (company_id, role);
CREATE INDEX IF NOT EXISTS idx_clients_company_profile ON clients (company_id, profile_id);
CREATE INDEX IF NOT EXISTS idx_client_lots_company_client ON client_lots (company_id, client_id);
CREATE INDEX IF NOT EXISTS idx_invoices_company_status ON invoices (company_id, status);
CREATE INDEX IF NOT EXISTS idx_invoices_asaas_payment ON invoices (asaas_payment_id);
CREATE INDEX IF NOT EXISTS idx_service_orders_company_status ON service_orders (company_id, status);
CREATE INDEX IF NOT EXISTS idx_referrals_company_referrer ON referrals (company_id, referrer_client_id);
