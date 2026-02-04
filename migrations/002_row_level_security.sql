-- ============================================
-- Real Estate Management System - Row Level Security
-- Migration 002: RLS Policies
-- CRITICAL: This ensures data isolation between tenants
-- ============================================

-- ============================================
-- HELPER FUNCTIONS
-- ============================================

-- Function to check if current user is admin
CREATE OR REPLACE FUNCTION is_admin()
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM profiles
        WHERE id = auth.uid()
        AND role = 'admin'
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to get client_id for current user
CREATE OR REPLACE FUNCTION get_client_id()
RETURNS UUID AS $$
BEGIN
    RETURN (
        SELECT id FROM clients
        WHERE profile_id = auth.uid()
        LIMIT 1
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================
-- PROFILES TABLE RLS
-- ============================================

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

-- Admin can see all profiles
CREATE POLICY "admin_select_all_profiles" ON profiles
    FOR SELECT
    USING (is_admin());

-- Users can see their own profile
CREATE POLICY "users_select_own_profile" ON profiles
    FOR SELECT
    USING (auth.uid() = id);

-- Admin can insert profiles
CREATE POLICY "admin_insert_profiles" ON profiles
    FOR INSERT
    WITH CHECK (is_admin());

-- Admin can update all profiles
CREATE POLICY "admin_update_profiles" ON profiles
    FOR UPDATE
    USING (is_admin());

-- Users can update their own profile (limited fields handled by API)
CREATE POLICY "users_update_own_profile" ON profiles
    FOR UPDATE
    USING (auth.uid() = id);

-- ============================================
-- CLIENTS TABLE RLS
-- ============================================

ALTER TABLE clients ENABLE ROW LEVEL SECURITY;

-- Admin can see all clients
CREATE POLICY "admin_select_all_clients" ON clients
    FOR SELECT
    USING (is_admin());

-- Clients can see their own record
CREATE POLICY "clients_select_own" ON clients
    FOR SELECT
    USING (profile_id = auth.uid());

-- Admin can insert clients
CREATE POLICY "admin_insert_clients" ON clients
    FOR INSERT
    WITH CHECK (is_admin());

-- Admin can update clients
CREATE POLICY "admin_update_clients" ON clients
    FOR UPDATE
    USING (is_admin());

-- Clients can update their own record (limited fields)
CREATE POLICY "clients_update_own" ON clients
    FOR UPDATE
    USING (profile_id = auth.uid());

-- Admin can delete (soft delete) clients
CREATE POLICY "admin_delete_clients" ON clients
    FOR DELETE
    USING (is_admin());

-- ============================================
-- DEVELOPMENTS TABLE RLS
-- ============================================

ALTER TABLE developments ENABLE ROW LEVEL SECURITY;

-- Everyone authenticated can see developments
CREATE POLICY "authenticated_select_developments" ON developments
    FOR SELECT
    USING (auth.role() = 'authenticated');

-- Only admin can insert developments
CREATE POLICY "admin_insert_developments" ON developments
    FOR INSERT
    WITH CHECK (is_admin());

-- Only admin can update developments
CREATE POLICY "admin_update_developments" ON developments
    FOR UPDATE
    USING (is_admin());

-- Only admin can delete developments
CREATE POLICY "admin_delete_developments" ON developments
    FOR DELETE
    USING (is_admin());

-- ============================================
-- LOTS TABLE RLS
-- ============================================

ALTER TABLE lots ENABLE ROW LEVEL SECURITY;

-- Everyone authenticated can see lots
CREATE POLICY "authenticated_select_lots" ON lots
    FOR SELECT
    USING (auth.role() = 'authenticated');

-- Only admin can insert lots
CREATE POLICY "admin_insert_lots" ON lots
    FOR INSERT
    WITH CHECK (is_admin());

-- Only admin can update lots
CREATE POLICY "admin_update_lots" ON lots
    FOR UPDATE
    USING (is_admin());

-- Only admin can delete lots
CREATE POLICY "admin_delete_lots" ON lots
    FOR DELETE
    USING (is_admin());

-- ============================================
-- CLIENT_LOTS TABLE RLS
-- ============================================

ALTER TABLE client_lots ENABLE ROW LEVEL SECURITY;

-- Admin can see all client_lots
CREATE POLICY "admin_select_all_client_lots" ON client_lots
    FOR SELECT
    USING (is_admin());

-- Clients can see their own client_lots
CREATE POLICY "clients_select_own_client_lots" ON client_lots
    FOR SELECT
    USING (client_id = get_client_id());

-- Only admin can insert client_lots
CREATE POLICY "admin_insert_client_lots" ON client_lots
    FOR INSERT
    WITH CHECK (is_admin());

-- Only admin can update client_lots
CREATE POLICY "admin_update_client_lots" ON client_lots
    FOR UPDATE
    USING (is_admin());

-- ============================================
-- INVOICES TABLE RLS
-- ============================================

ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;

-- Admin can see all invoices
CREATE POLICY "admin_select_all_invoices" ON invoices
    FOR SELECT
    USING (is_admin());

-- Clients can see their own invoices (through client_lots)
CREATE POLICY "clients_select_own_invoices" ON invoices
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM client_lots cl
            WHERE cl.id = invoices.client_lot_id
            AND cl.client_id = get_client_id()
        )
    );

-- Only admin can insert invoices
CREATE POLICY "admin_insert_invoices" ON invoices
    FOR INSERT
    WITH CHECK (is_admin());

-- Only admin can update invoices
CREATE POLICY "admin_update_invoices" ON invoices
    FOR UPDATE
    USING (is_admin());

-- ============================================
-- SERVICE_TYPES TABLE RLS
-- ============================================

ALTER TABLE service_types ENABLE ROW LEVEL SECURITY;

-- Everyone authenticated can see active service types
CREATE POLICY "authenticated_select_service_types" ON service_types
    FOR SELECT
    USING (auth.role() = 'authenticated' AND (is_active = true OR is_admin()));

-- Only admin can insert service types
CREATE POLICY "admin_insert_service_types" ON service_types
    FOR INSERT
    WITH CHECK (is_admin());

-- Only admin can update service types
CREATE POLICY "admin_update_service_types" ON service_types
    FOR UPDATE
    USING (is_admin());

-- ============================================
-- SERVICE_ORDERS TABLE RLS
-- ============================================

ALTER TABLE service_orders ENABLE ROW LEVEL SECURITY;

-- Admin can see all service orders
CREATE POLICY "admin_select_all_service_orders" ON service_orders
    FOR SELECT
    USING (is_admin());

-- Clients can see their own service orders
CREATE POLICY "clients_select_own_service_orders" ON service_orders
    FOR SELECT
    USING (client_id = get_client_id());

-- Clients can insert their own service orders
CREATE POLICY "clients_insert_service_orders" ON service_orders
    FOR INSERT
    WITH CHECK (client_id = get_client_id());

-- Admin can insert service orders
CREATE POLICY "admin_insert_service_orders" ON service_orders
    FOR INSERT
    WITH CHECK (is_admin());

-- Only admin can update service orders
CREATE POLICY "admin_update_service_orders" ON service_orders
    FOR UPDATE
    USING (is_admin());

-- ============================================
-- REFERRALS TABLE RLS
-- ============================================

ALTER TABLE referrals ENABLE ROW LEVEL SECURITY;

-- Admin can see all referrals
CREATE POLICY "admin_select_all_referrals" ON referrals
    FOR SELECT
    USING (is_admin());

-- Clients can see their own referrals
CREATE POLICY "clients_select_own_referrals" ON referrals
    FOR SELECT
    USING (referrer_client_id = get_client_id());

-- Clients can insert their own referrals
CREATE POLICY "clients_insert_referrals" ON referrals
    FOR INSERT
    WITH CHECK (referrer_client_id = get_client_id());

-- Only admin can update referrals
CREATE POLICY "admin_update_referrals" ON referrals
    FOR UPDATE
    USING (is_admin());

-- ============================================
-- NOTIFICATIONS TABLE RLS
-- ============================================

ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;

-- Admin can see all notifications
CREATE POLICY "admin_select_all_notifications" ON notifications
    FOR SELECT
    USING (is_admin());

-- Users can see their own notifications
CREATE POLICY "users_select_own_notifications" ON notifications
    FOR SELECT
    USING (user_id = auth.uid());

-- Admin can insert notifications
CREATE POLICY "admin_insert_notifications" ON notifications
    FOR INSERT
    WITH CHECK (is_admin());

-- Users can update their own notifications (mark as read)
CREATE POLICY "users_update_own_notifications" ON notifications
    FOR UPDATE
    USING (user_id = auth.uid());

-- ============================================
-- AUDIT_LOGS TABLE RLS
-- ============================================

ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

-- Only admin can see audit logs
CREATE POLICY "admin_select_audit_logs" ON audit_logs
    FOR SELECT
    USING (is_admin());

-- System can insert audit logs (using service role)
CREATE POLICY "system_insert_audit_logs" ON audit_logs
    FOR INSERT
    WITH CHECK (true);

-- ============================================
-- GRANT PERMISSIONS
-- ============================================

-- Grant usage on schema
GRANT USAGE ON SCHEMA public TO authenticated;
GRANT USAGE ON SCHEMA public TO anon;

-- Grant select on necessary tables for authenticated users
GRANT SELECT ON profiles TO authenticated;
GRANT SELECT ON clients TO authenticated;
GRANT SELECT ON developments TO authenticated;
GRANT SELECT ON lots TO authenticated;
GRANT SELECT ON client_lots TO authenticated;
GRANT SELECT ON invoices TO authenticated;
GRANT SELECT ON service_types TO authenticated;
GRANT SELECT ON service_orders TO authenticated;
GRANT SELECT ON referrals TO authenticated;
GRANT SELECT ON notifications TO authenticated;

-- Grant insert/update where needed
GRANT INSERT ON service_orders TO authenticated;
GRANT INSERT ON referrals TO authenticated;
GRANT UPDATE ON notifications TO authenticated;
GRANT UPDATE ON profiles TO authenticated;
GRANT UPDATE ON clients TO authenticated;
