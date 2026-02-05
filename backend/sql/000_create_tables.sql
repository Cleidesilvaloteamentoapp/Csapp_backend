-- =============================================================================
-- CSApp Backend – Criação de tabelas no Supabase
-- Execute no SQL Editor do Supabase Dashboard
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. ENUM TYPES
-- ---------------------------------------------------------------------------

CREATE TYPE company_status AS ENUM ('active', 'suspended', 'inactive');
CREATE TYPE user_role AS ENUM ('super_admin', 'company_admin', 'client');
CREATE TYPE client_status AS ENUM ('active', 'inactive', 'defaulter');
CREATE TYPE lot_status AS ENUM ('available', 'reserved', 'sold');
CREATE TYPE client_lot_status AS ENUM ('active', 'completed', 'cancelled');
CREATE TYPE invoice_status AS ENUM ('pending', 'paid', 'overdue', 'cancelled');
CREATE TYPE service_order_status AS ENUM ('requested', 'approved', 'in_progress', 'completed', 'cancelled');
CREATE TYPE referral_status AS ENUM ('pending', 'contacted', 'converted', 'lost');

-- ---------------------------------------------------------------------------
-- 2. TABELAS
-- ---------------------------------------------------------------------------

-- companies (tenant raiz)
CREATE TABLE companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL,
    settings JSONB DEFAULT '{}'::jsonb,
    status company_status NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX ix_companies_slug ON companies (slug);
CREATE INDEX ix_companies_status ON companies (status);

-- profiles (estende auth.users do Supabase)
CREATE TABLE profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    role user_role NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    cpf_cnpj VARCHAR(20) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    email VARCHAR(255) NOT NULL,
    hashed_password VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_profiles_company_id ON profiles (company_id);
CREATE INDEX ix_profiles_role ON profiles (role);
CREATE UNIQUE INDEX ix_profiles_cpf_cnpj ON profiles (cpf_cnpj);
CREATE INDEX ix_profiles_email ON profiles (email);

-- clients
CREATE TABLE clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    profile_id UUID REFERENCES profiles(id) ON DELETE SET NULL,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    cpf_cnpj VARCHAR(20) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    address JSONB DEFAULT '{}'::jsonb,
    documents JSONB DEFAULT '[]'::jsonb,
    status client_status NOT NULL DEFAULT 'active',
    asaas_customer_id VARCHAR(255),
    created_by UUID REFERENCES profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_clients_company_id ON clients (company_id);
CREATE INDEX ix_clients_email ON clients (email);
CREATE INDEX ix_clients_cpf_cnpj ON clients (cpf_cnpj);
CREATE INDEX ix_clients_status ON clients (status);

-- developments (loteamentos/empreendimentos)
CREATE TABLE developments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    location VARCHAR(500),
    documents JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_developments_company_id ON developments (company_id);

-- lots (lotes individuais)
CREATE TABLE lots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    development_id UUID NOT NULL REFERENCES developments(id) ON DELETE CASCADE,
    lot_number VARCHAR(50) NOT NULL,
    block VARCHAR(50),
    area_m2 NUMERIC(12, 2) NOT NULL,
    price NUMERIC(14, 2) NOT NULL,
    status lot_status NOT NULL DEFAULT 'available',
    documents JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_lots_company_id ON lots (company_id);
CREATE INDEX ix_lots_status ON lots (status);

-- client_lots (compra de lote por cliente)
CREATE TABLE client_lots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    lot_id UUID NOT NULL REFERENCES lots(id) ON DELETE CASCADE,
    purchase_date DATE NOT NULL,
    total_value NUMERIC(14, 2) NOT NULL,
    payment_plan JSONB DEFAULT '{}'::jsonb,
    status client_lot_status NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_client_lots_company_id ON client_lots (company_id);
CREATE INDEX ix_client_lots_status ON client_lots (status);

-- invoices (boletos/parcelas)
CREATE TABLE invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    client_lot_id UUID NOT NULL REFERENCES client_lots(id) ON DELETE CASCADE,
    due_date DATE NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    installment_number INTEGER NOT NULL,
    status invoice_status NOT NULL DEFAULT 'pending',
    asaas_payment_id VARCHAR(255),
    barcode VARCHAR(255),
    payment_url VARCHAR(500),
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_invoices_company_id ON invoices (company_id);
CREATE INDEX ix_invoices_due_date ON invoices (due_date);
CREATE INDEX ix_invoices_status ON invoices (status);

-- service_types (catálogo de serviços)
CREATE TABLE service_types (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    base_price NUMERIC(14, 2) NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_service_types_company_id ON service_types (company_id);

-- service_orders (ordens de serviço)
CREATE TABLE service_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    lot_id UUID REFERENCES lots(id) ON DELETE SET NULL,
    service_type_id UUID NOT NULL REFERENCES service_types(id) ON DELETE CASCADE,
    requested_date DATE NOT NULL,
    execution_date DATE,
    status service_order_status NOT NULL DEFAULT 'requested',
    cost NUMERIC(14, 2) NOT NULL DEFAULT 0,
    revenue NUMERIC(14, 2) NOT NULL DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_service_orders_company_id ON service_orders (company_id);
CREATE INDEX ix_service_orders_status ON service_orders (status);

-- referrals (indicações de clientes)
CREATE TABLE referrals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    referrer_client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    referred_name VARCHAR(255) NOT NULL,
    referred_phone VARCHAR(20) NOT NULL,
    referred_email VARCHAR(255),
    status referral_status NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_referrals_company_id ON referrals (company_id);
CREATE INDEX ix_referrals_status ON referrals (status);

-- audit_logs (trilha de auditoria)
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID,
    company_id UUID,
    table_name VARCHAR(100) NOT NULL,
    operation VARCHAR(20) NOT NULL,
    resource_id VARCHAR(255),
    detail TEXT,
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 3. TRIGGER updated_at AUTOMÁTICO
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_companies_updated_at
    BEFORE UPDATE ON companies FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_profiles_updated_at
    BEFORE UPDATE ON profiles FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_clients_updated_at
    BEFORE UPDATE ON clients FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_developments_updated_at
    BEFORE UPDATE ON developments FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_lots_updated_at
    BEFORE UPDATE ON lots FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_client_lots_updated_at
    BEFORE UPDATE ON client_lots FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_invoices_updated_at
    BEFORE UPDATE ON invoices FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_service_types_updated_at
    BEFORE UPDATE ON service_types FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_service_orders_updated_at
    BEFORE UPDATE ON service_orders FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_referrals_updated_at
    BEFORE UPDATE ON referrals FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ---------------------------------------------------------------------------
-- 4. INDEXES COMPOSTOS PARA PERFORMANCE
-- ---------------------------------------------------------------------------

CREATE INDEX ix_profiles_company_role ON profiles (company_id, role);
CREATE INDEX ix_clients_company_profile ON clients (company_id, profile_id);
CREATE INDEX ix_client_lots_company_client ON client_lots (company_id, client_id);
CREATE INDEX ix_invoices_company_status ON invoices (company_id, status);
CREATE INDEX ix_invoices_asaas_payment ON invoices (asaas_payment_id);
CREATE INDEX ix_service_orders_company_status ON service_orders (company_id, status);
CREATE INDEX ix_referrals_company_referrer ON referrals (company_id, referrer_client_id);
