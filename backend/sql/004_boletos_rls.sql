-- ============================================================================
-- Row Level Security Policies for Boletos Table
-- ============================================================================
-- CRITICAL: Enforce multi-tenant isolation and data protection
-- Every boleto must be isolated by company_id to prevent cross-tenant access
-- ============================================================================

-- Enable RLS on boletos table
ALTER TABLE boletos ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- Policy 1: Company Isolation (SELECT)
-- ============================================================================
-- Users can only view boletos from their own company
CREATE POLICY "boletos_company_isolation_select" ON boletos
  FOR SELECT
  USING (
    company_id IN (
      SELECT company_id 
      FROM profiles 
      WHERE id = auth.uid()
    )
  );

-- ============================================================================
-- Policy 2: Admin/Company Admin Can Insert (INSERT)
-- ============================================================================
-- Only SUPER_ADMIN and COMPANY_ADMIN can create boletos
CREATE POLICY "boletos_admin_insert" ON boletos
  FOR INSERT
  WITH CHECK (
    company_id IN (
      SELECT company_id 
      FROM profiles 
      WHERE id = auth.uid() 
        AND role IN ('SUPER_ADMIN', 'COMPANY_ADMIN')
    )
  );

-- ============================================================================
-- Policy 3: Admin/Company Admin Can Update (UPDATE)
-- ============================================================================
-- Only SUPER_ADMIN and COMPANY_ADMIN can update boletos from their company
CREATE POLICY "boletos_admin_update" ON boletos
  FOR UPDATE
  USING (
    company_id IN (
      SELECT company_id 
      FROM profiles 
      WHERE id = auth.uid() 
        AND role IN ('SUPER_ADMIN', 'COMPANY_ADMIN')
    )
  )
  WITH CHECK (
    company_id IN (
      SELECT company_id 
      FROM profiles 
      WHERE id = auth.uid() 
        AND role IN ('SUPER_ADMIN', 'COMPANY_ADMIN')
    )
  );

-- ============================================================================
-- Policy 4: Only SUPER_ADMIN Can Delete (DELETE)
-- ============================================================================
-- Deletion restricted to SUPER_ADMIN only for audit purposes
CREATE POLICY "boletos_super_admin_delete" ON boletos
  FOR DELETE
  USING (
    EXISTS (
      SELECT 1 
      FROM profiles 
      WHERE id = auth.uid() 
        AND role = 'SUPER_ADMIN'
    )
  );

-- ============================================================================
-- Performance Indexes for RLS (already created in migration)
-- ============================================================================
-- idx_boletos_company_client
-- idx_boletos_company_status
-- idx_boletos_company_vencimento
-- idx_boletos_seu_numero_company

-- ============================================================================
-- Audit: Enable updated_at trigger
-- ============================================================================
CREATE TRIGGER update_boletos_updated_at
  BEFORE UPDATE ON boletos
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();
