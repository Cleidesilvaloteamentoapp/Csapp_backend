-- =============================================================================
-- RLS Policies for Client Portal tables
-- Run AFTER migration 005_client_portal
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Enable RLS
-- ---------------------------------------------------------------------------
ALTER TABLE client_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE service_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE service_request_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- CLIENT_DOCUMENTS
-- ---------------------------------------------------------------------------

-- Super admin: full access
CREATE POLICY "client_documents_super_admin_all" ON client_documents
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role = 'SUPER_ADMIN'
    )
  );

-- Company admin: full access within company
CREATE POLICY "client_documents_company_admin" ON client_documents
  FOR ALL
  USING (
    company_id IN (
      SELECT p.company_id FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role IN ('SUPER_ADMIN', 'COMPANY_ADMIN')
    )
  );

-- Client: view own documents
CREATE POLICY "client_documents_client_read" ON client_documents
  FOR SELECT
  USING (
    client_id IN (
      SELECT c.id FROM clients c
      WHERE c.profile_id = auth.uid()
    )
  );

-- Client: insert own documents
CREATE POLICY "client_documents_client_insert" ON client_documents
  FOR INSERT
  WITH CHECK (
    client_id IN (
      SELECT c.id FROM clients c
      WHERE c.profile_id = auth.uid()
    )
  );

-- Client: delete own PENDING_REVIEW documents only
CREATE POLICY "client_documents_client_delete" ON client_documents
  FOR DELETE
  USING (
    status = 'PENDING_REVIEW'
    AND client_id IN (
      SELECT c.id FROM clients c
      WHERE c.profile_id = auth.uid()
    )
  );

-- ---------------------------------------------------------------------------
-- SERVICE_REQUESTS
-- ---------------------------------------------------------------------------

-- Super admin: full access
CREATE POLICY "service_requests_super_admin_all" ON service_requests
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role = 'SUPER_ADMIN'
    )
  );

-- Company admin: full access within company
CREATE POLICY "service_requests_company_admin" ON service_requests
  FOR ALL
  USING (
    company_id IN (
      SELECT p.company_id FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role IN ('SUPER_ADMIN', 'COMPANY_ADMIN')
    )
  );

-- Client: view own requests
CREATE POLICY "service_requests_client_read" ON service_requests
  FOR SELECT
  USING (
    client_id IN (
      SELECT c.id FROM clients c
      WHERE c.profile_id = auth.uid()
    )
  );

-- Client: create own requests
CREATE POLICY "service_requests_client_insert" ON service_requests
  FOR INSERT
  WITH CHECK (
    client_id IN (
      SELECT c.id FROM clients c
      WHERE c.profile_id = auth.uid()
    )
  );

-- ---------------------------------------------------------------------------
-- SERVICE_REQUEST_MESSAGES
-- ---------------------------------------------------------------------------

-- Super admin: full access
CREATE POLICY "sr_messages_super_admin_all" ON service_request_messages
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role = 'SUPER_ADMIN'
    )
  );

-- Company admin: full access within company
CREATE POLICY "sr_messages_company_admin" ON service_request_messages
  FOR ALL
  USING (
    request_id IN (
      SELECT sr.id FROM service_requests sr
      WHERE sr.company_id IN (
        SELECT p.company_id FROM profiles p
        WHERE p.id = auth.uid()
        AND p.role IN ('SUPER_ADMIN', 'COMPANY_ADMIN')
      )
    )
  );

-- Client: view non-internal messages on own requests
CREATE POLICY "sr_messages_client_read" ON service_request_messages
  FOR SELECT
  USING (
    is_internal = false
    AND request_id IN (
      SELECT sr.id FROM service_requests sr
      WHERE sr.client_id IN (
        SELECT c.id FROM clients c
        WHERE c.profile_id = auth.uid()
      )
    )
  );

-- Client: insert messages on own requests
CREATE POLICY "sr_messages_client_insert" ON service_request_messages
  FOR INSERT
  WITH CHECK (
    is_internal = false
    AND request_id IN (
      SELECT sr.id FROM service_requests sr
      WHERE sr.client_id IN (
        SELECT c.id FROM clients c
        WHERE c.profile_id = auth.uid()
      )
    )
  );

-- ---------------------------------------------------------------------------
-- NOTIFICATIONS
-- ---------------------------------------------------------------------------

-- Super admin: full access
CREATE POLICY "notifications_super_admin_all" ON notifications
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role = 'SUPER_ADMIN'
    )
  );

-- Company admin: read within company
CREATE POLICY "notifications_company_admin_read" ON notifications
  FOR SELECT
  USING (
    company_id IN (
      SELECT p.company_id FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role IN ('SUPER_ADMIN', 'COMPANY_ADMIN')
    )
  );

-- User: view own notifications
CREATE POLICY "notifications_user_read" ON notifications
  FOR SELECT
  USING (user_id = auth.uid());

-- User: update own notifications (mark as read)
CREATE POLICY "notifications_user_update" ON notifications
  FOR UPDATE
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- System insert (any authenticated user – app creates via backend)
CREATE POLICY "notifications_system_insert" ON notifications
  FOR INSERT
  WITH CHECK (auth.uid() IS NOT NULL);

-- ---------------------------------------------------------------------------
-- Performance indexes
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_client_documents_company_client ON client_documents (company_id, client_id);
CREATE INDEX IF NOT EXISTS idx_service_requests_company_client ON service_requests (company_id, client_id);
CREATE INDEX IF NOT EXISTS idx_sr_messages_request_internal ON service_request_messages (request_id, is_internal);
CREATE INDEX IF NOT EXISTS idx_notifications_user_company ON notifications (user_id, company_id);
