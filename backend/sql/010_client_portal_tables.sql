-- =============================================================================
-- Client Portal Tables Migration
-- Creates: client_documents, service_requests, service_request_messages, notifications
-- Run AFTER 004_add_contract_features migration
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. CREATE ENUM TYPES
-- ---------------------------------------------------------------------------

DO $$ BEGIN
    CREATE TYPE document_type AS ENUM (
        'RG', 'CPF', 'COMPROVANTE_RESIDENCIA', 'CNH', 'CONTRATO', 'OUTROS'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE document_status AS ENUM (
        'PENDING_REVIEW', 'APPROVED', 'REJECTED', 'EXPIRED'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE service_request_type AS ENUM (
        'MANUTENCAO', 'SUPORTE', 'FINANCEIRO', 'DOCUMENTACAO', 'OUTROS'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE service_request_status AS ENUM (
        'OPEN', 'IN_PROGRESS', 'WAITING_CLIENT', 'RESOLVED', 'CLOSED'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE service_request_priority AS ENUM (
        'LOW', 'MEDIUM', 'HIGH', 'URGENT'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE notification_type AS ENUM (
        'BOLETO_EMITIDO', 
        'BOLETO_VENCIDO', 
        'PAGAMENTO_CONFIRMADO',
        'DOCUMENTO_APROVADO', 
        'DOCUMENTO_REJEITADO',
        'SOLICITACAO_ATUALIZADA', 
        'GERAL'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ---------------------------------------------------------------------------
-- 2. CREATE TABLE: client_documents
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS client_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    document_type document_type NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_size INTEGER NOT NULL,
    description TEXT,
    status document_status NOT NULL DEFAULT 'PENDING_REVIEW',
    rejection_reason TEXT,
    reviewed_at TIMESTAMPTZ,
    reviewed_by UUID REFERENCES profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_client_documents_client ON client_documents(client_id);
CREATE INDEX IF NOT EXISTS idx_client_documents_company ON client_documents(company_id);
CREATE INDEX IF NOT EXISTS idx_client_documents_status ON client_documents(status);
CREATE INDEX IF NOT EXISTS idx_client_documents_type ON client_documents(document_type);

-- ---------------------------------------------------------------------------
-- 3. CREATE TABLE: service_requests
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS service_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    ticket_number VARCHAR(50) UNIQUE NOT NULL,
    service_type service_request_type NOT NULL,
    subject VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    status service_request_status NOT NULL DEFAULT 'OPEN',
    priority service_request_priority NOT NULL DEFAULT 'MEDIUM',
    assigned_to UUID REFERENCES profiles(id) ON DELETE SET NULL,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_service_requests_client ON service_requests(client_id);
CREATE INDEX IF NOT EXISTS idx_service_requests_company ON service_requests(company_id);
CREATE INDEX IF NOT EXISTS idx_service_requests_status ON service_requests(status);
CREATE INDEX IF NOT EXISTS idx_service_requests_ticket ON service_requests(ticket_number);
CREATE INDEX IF NOT EXISTS idx_service_requests_priority ON service_requests(priority);

-- ---------------------------------------------------------------------------
-- 4. CREATE TABLE: service_request_messages
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS service_request_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL REFERENCES service_requests(id) ON DELETE CASCADE,
    author_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    author_type VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    is_internal BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_sr_messages_request ON service_request_messages(request_id);

-- ---------------------------------------------------------------------------
-- 5. CREATE TABLE: notifications
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    type notification_type NOT NULL DEFAULT 'GERAL',
    is_read BOOLEAN NOT NULL DEFAULT false,
    data JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_company ON notifications(company_id);
CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(is_read);
CREATE INDEX IF NOT EXISTS idx_notifications_type ON notifications(type);
CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications(user_id, is_read);

-- ---------------------------------------------------------------------------
-- DONE
-- ---------------------------------------------------------------------------
-- After running this migration, execute sql/009_client_portal_rls.sql
-- to enable Row Level Security policies
