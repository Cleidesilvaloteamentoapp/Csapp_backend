-- ============================================
-- Real Estate Management System - Database Schema
-- Migration 001: Create Tables
-- ============================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- ENUM TYPES
-- ============================================

CREATE TYPE user_role AS ENUM ('admin', 'client');
CREATE TYPE client_status AS ENUM ('active', 'inactive', 'defaulter');
CREATE TYPE lot_status AS ENUM ('available', 'reserved', 'sold');
CREATE TYPE client_lot_status AS ENUM ('active', 'completed', 'cancelled');
CREATE TYPE invoice_status AS ENUM ('pending', 'paid', 'overdue', 'cancelled');
CREATE TYPE service_order_status AS ENUM ('requested', 'approved', 'in_progress', 'completed', 'cancelled');
CREATE TYPE referral_status AS ENUM ('pending', 'contacted', 'converted', 'lost');
CREATE TYPE notification_type AS ENUM ('payment_overdue', 'service_update', 'general');

-- ============================================
-- PROFILES TABLE (extends auth.users)
-- ============================================

CREATE TABLE profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    role user_role NOT NULL DEFAULT 'client',
    full_name TEXT NOT NULL,
    cpf_cnpj TEXT UNIQUE NOT NULL,
    phone TEXT,
    asaas_customer_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_profiles_role ON profiles(role);
CREATE INDEX idx_profiles_cpf_cnpj ON profiles(cpf_cnpj);

-- ============================================
-- CLIENTS TABLE
-- ============================================

CREATE TABLE clients (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    profile_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    address JSONB,
    documents JSONB DEFAULT '[]'::jsonb,
    status client_status NOT NULL DEFAULT 'active',
    created_by UUID REFERENCES profiles(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_clients_profile_id ON clients(profile_id);
CREATE INDEX idx_clients_status ON clients(status);
CREATE INDEX idx_clients_created_by ON clients(created_by);

-- ============================================
-- DEVELOPMENTS TABLE (Empreendimentos/Loteamentos)
-- ============================================

CREATE TABLE developments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    description TEXT,
    location TEXT NOT NULL,
    documents JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_developments_name ON developments(name);

-- ============================================
-- LOTS TABLE (Lotes)
-- ============================================

CREATE TABLE lots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    development_id UUID NOT NULL REFERENCES developments(id) ON DELETE CASCADE,
    lot_number TEXT NOT NULL,
    block TEXT,
    area_m2 DECIMAL(10, 2) NOT NULL CHECK (area_m2 > 0),
    price DECIMAL(15, 2) NOT NULL CHECK (price > 0),
    status lot_status NOT NULL DEFAULT 'available',
    documents JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE(development_id, lot_number, block)
);

CREATE INDEX idx_lots_development_id ON lots(development_id);
CREATE INDEX idx_lots_status ON lots(status);

-- ============================================
-- CLIENT_LOTS TABLE (Relacionamento Cliente-Lote)
-- ============================================

CREATE TABLE client_lots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    lot_id UUID NOT NULL REFERENCES lots(id) ON DELETE CASCADE,
    purchase_date DATE NOT NULL,
    total_value DECIMAL(15, 2) NOT NULL CHECK (total_value > 0),
    payment_plan JSONB NOT NULL,
    status client_lot_status NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE(lot_id)
);

CREATE INDEX idx_client_lots_client_id ON client_lots(client_id);
CREATE INDEX idx_client_lots_lot_id ON client_lots(lot_id);
CREATE INDEX idx_client_lots_status ON client_lots(status);

-- ============================================
-- INVOICES TABLE (Boletos/Faturas)
-- ============================================

CREATE TABLE invoices (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_lot_id UUID NOT NULL REFERENCES client_lots(id) ON DELETE CASCADE,
    asaas_payment_id TEXT,
    due_date DATE NOT NULL,
    amount DECIMAL(15, 2) NOT NULL CHECK (amount > 0),
    status invoice_status NOT NULL DEFAULT 'pending',
    installment_number INTEGER NOT NULL CHECK (installment_number > 0),
    barcode TEXT,
    payment_url TEXT,
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_invoices_client_lot_id ON invoices(client_lot_id);
CREATE INDEX idx_invoices_status ON invoices(status);
CREATE INDEX idx_invoices_due_date ON invoices(due_date);
CREATE INDEX idx_invoices_asaas_payment_id ON invoices(asaas_payment_id);

-- ============================================
-- SERVICE_TYPES TABLE (Tipos de Serviços)
-- ============================================

CREATE TABLE service_types (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    description TEXT,
    base_price DECIMAL(15, 2) NOT NULL DEFAULT 0 CHECK (base_price >= 0),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_service_types_is_active ON service_types(is_active);

-- ============================================
-- SERVICE_ORDERS TABLE (Ordens de Serviço)
-- ============================================

CREATE TABLE service_orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    lot_id UUID REFERENCES lots(id) ON DELETE SET NULL,
    service_type_id UUID NOT NULL REFERENCES service_types(id) ON DELETE CASCADE,
    requested_date DATE NOT NULL,
    execution_date DATE,
    status service_order_status NOT NULL DEFAULT 'requested',
    cost DECIMAL(15, 2) NOT NULL DEFAULT 0 CHECK (cost >= 0),
    revenue DECIMAL(15, 2) CHECK (revenue >= 0),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_service_orders_client_id ON service_orders(client_id);
CREATE INDEX idx_service_orders_status ON service_orders(status);
CREATE INDEX idx_service_orders_service_type_id ON service_orders(service_type_id);

-- ============================================
-- REFERRALS TABLE (Indicações)
-- ============================================

CREATE TABLE referrals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    referrer_client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    referred_name TEXT NOT NULL,
    referred_phone TEXT NOT NULL,
    referred_email TEXT,
    status referral_status NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_referrals_referrer_client_id ON referrals(referrer_client_id);
CREATE INDEX idx_referrals_status ON referrals(status);

-- ============================================
-- NOTIFICATIONS TABLE (Notificações/Alertas)
-- ============================================

CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    type notification_type NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_notifications_user_id ON notifications(user_id);
CREATE INDEX idx_notifications_is_read ON notifications(is_read);
CREATE INDEX idx_notifications_created_at ON notifications(created_at DESC);

-- ============================================
-- AUDIT_LOGS TABLE (Logs de Auditoria)
-- ============================================

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES profiles(id),
    table_name TEXT NOT NULL,
    operation TEXT NOT NULL,
    record_id UUID,
    old_data JSONB,
    new_data JSONB,
    ip_address INET,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_table_name ON audit_logs(table_name);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at DESC);

-- ============================================
-- TRIGGERS FOR updated_at
-- ============================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_profiles_updated_at
    BEFORE UPDATE ON profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_clients_updated_at
    BEFORE UPDATE ON clients
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_developments_updated_at
    BEFORE UPDATE ON developments
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_lots_updated_at
    BEFORE UPDATE ON lots
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_invoices_updated_at
    BEFORE UPDATE ON invoices
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_service_orders_updated_at
    BEFORE UPDATE ON service_orders
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- FUNCTION TO CREATE PROFILE ON USER SIGNUP
-- ============================================

CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO profiles (id, full_name, cpf_cnpj, role)
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data->>'full_name', 'New User'),
        COALESCE(NEW.raw_user_meta_data->>'cpf_cnpj', ''),
        COALESCE((NEW.raw_user_meta_data->>'role')::user_role, 'client')
    );
    RETURN NEW;
END;
$$ language 'plpgsql' SECURITY DEFINER;

-- Note: This trigger should be created in Supabase Dashboard
-- as it requires access to auth.users
-- CREATE TRIGGER on_auth_user_created
--     AFTER INSERT ON auth.users
--     FOR EACH ROW EXECUTE FUNCTION handle_new_user();
