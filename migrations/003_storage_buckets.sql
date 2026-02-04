-- ============================================
-- Real Estate Management System - Storage Buckets
-- Migration 003: Supabase Storage Configuration
-- ============================================

-- Note: This SQL should be run in the Supabase Dashboard SQL Editor
-- as storage bucket creation requires specific permissions

-- ============================================
-- CREATE STORAGE BUCKETS
-- ============================================

-- Client documents bucket
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'client-documents',
    'client-documents',
    false,
    10485760, -- 10MB
    ARRAY['application/pdf', 'image/jpeg', 'image/png', 'image/jpg', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
) ON CONFLICT (id) DO NOTHING;

-- Lot documents bucket
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'lot-documents',
    'lot-documents',
    false,
    10485760,
    ARRAY['application/pdf', 'image/jpeg', 'image/png', 'image/jpg', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
) ON CONFLICT (id) DO NOTHING;

-- Development documents bucket
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'development-documents',
    'development-documents',
    false,
    10485760,
    ARRAY['application/pdf', 'image/jpeg', 'image/png', 'image/jpg']
) ON CONFLICT (id) DO NOTHING;

-- Service documents bucket
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'service-documents',
    'service-documents',
    false,
    10485760,
    ARRAY['application/pdf', 'image/jpeg', 'image/png', 'image/jpg']
) ON CONFLICT (id) DO NOTHING;

-- ============================================
-- STORAGE RLS POLICIES
-- ============================================

-- Helper function to check admin status for storage
CREATE OR REPLACE FUNCTION storage.is_admin()
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM public.profiles
        WHERE id = auth.uid()
        AND role = 'admin'
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================
-- CLIENT-DOCUMENTS BUCKET POLICIES
-- ============================================

-- Admin can do everything
CREATE POLICY "admin_all_client_documents" ON storage.objects
    FOR ALL
    USING (bucket_id = 'client-documents' AND storage.is_admin())
    WITH CHECK (bucket_id = 'client-documents' AND storage.is_admin());

-- Clients can read their own documents
CREATE POLICY "clients_read_own_documents" ON storage.objects
    FOR SELECT
    USING (
        bucket_id = 'client-documents'
        AND (storage.foldername(name))[1] IN (
            SELECT c.id::text FROM public.clients c
            WHERE c.profile_id = auth.uid()
        )
    );

-- Clients can upload their own documents
CREATE POLICY "clients_upload_own_documents" ON storage.objects
    FOR INSERT
    WITH CHECK (
        bucket_id = 'client-documents'
        AND (storage.foldername(name))[1] IN (
            SELECT c.id::text FROM public.clients c
            WHERE c.profile_id = auth.uid()
        )
    );

-- ============================================
-- LOT-DOCUMENTS BUCKET POLICIES
-- ============================================

-- Admin can do everything
CREATE POLICY "admin_all_lot_documents" ON storage.objects
    FOR ALL
    USING (bucket_id = 'lot-documents' AND storage.is_admin())
    WITH CHECK (bucket_id = 'lot-documents' AND storage.is_admin());

-- Clients can read documents for lots they own
CREATE POLICY "clients_read_lot_documents" ON storage.objects
    FOR SELECT
    USING (
        bucket_id = 'lot-documents'
        AND (storage.foldername(name))[1] IN (
            SELECT cl.lot_id::text 
            FROM public.client_lots cl
            JOIN public.clients c ON c.id = cl.client_id
            WHERE c.profile_id = auth.uid()
        )
    );

-- ============================================
-- DEVELOPMENT-DOCUMENTS BUCKET POLICIES
-- ============================================

-- Admin can do everything
CREATE POLICY "admin_all_development_documents" ON storage.objects
    FOR ALL
    USING (bucket_id = 'development-documents' AND storage.is_admin())
    WITH CHECK (bucket_id = 'development-documents' AND storage.is_admin());

-- All authenticated users can read development documents
CREATE POLICY "authenticated_read_development_documents" ON storage.objects
    FOR SELECT
    USING (bucket_id = 'development-documents' AND auth.role() = 'authenticated');

-- ============================================
-- SERVICE-DOCUMENTS BUCKET POLICIES
-- ============================================

-- Admin can do everything
CREATE POLICY "admin_all_service_documents" ON storage.objects
    FOR ALL
    USING (bucket_id = 'service-documents' AND storage.is_admin())
    WITH CHECK (bucket_id = 'service-documents' AND storage.is_admin());

-- Clients can read documents for their service orders
CREATE POLICY "clients_read_service_documents" ON storage.objects
    FOR SELECT
    USING (
        bucket_id = 'service-documents'
        AND (storage.foldername(name))[1] IN (
            SELECT so.id::text 
            FROM public.service_orders so
            JOIN public.clients c ON c.id = so.client_id
            WHERE c.profile_id = auth.uid()
        )
    );
