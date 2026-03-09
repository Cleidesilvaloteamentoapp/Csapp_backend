-- ============================================================================
-- MIGRATION: Create boletos table
-- Execute this FIRST in Supabase SQL Editor
-- ============================================================================

-- Step 1: Create ENUM type for boleto status
CREATE TYPE boleto_status AS ENUM (
    'NORMAL',
    'LIQUIDADO',
    'VENCIDO',
    'CANCELADO'
);

-- Step 2: Create boletos table
CREATE TABLE boletos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    
    -- Sicredi identifiers
    nosso_numero VARCHAR(50) NOT NULL UNIQUE,
    seu_numero VARCHAR(50) NOT NULL,
    linha_digitavel VARCHAR(100),
    codigo_barras VARCHAR(100),
    
    -- Boleto type and document
    tipo_cobranca VARCHAR(20) NOT NULL,
    especie_documento VARCHAR(50) NOT NULL,
    
    -- Dates
    data_vencimento DATE NOT NULL,
    data_emissao DATE NOT NULL,
    data_liquidacao DATE,
    
    -- Values
    valor NUMERIC(12, 2) NOT NULL,
    valor_liquidacao NUMERIC(12, 2),
    
    -- Status
    status boleto_status NOT NULL DEFAULT 'NORMAL',
    
    -- Pix (for HIBRIDO type)
    txid VARCHAR(100),
    qr_code TEXT,
    
    -- Optional link to invoice
    invoice_id UUID REFERENCES invoices(id) ON DELETE SET NULL,
    
    -- Store pagador data and full API response
    pagador_data JSONB,
    raw_response JSONB,
    
    -- Audit
    created_by UUID REFERENCES profiles(id) ON DELETE SET NULL,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Step 3: Create indexes for performance (multi-tenant queries)
CREATE INDEX idx_boletos_company_id ON boletos(company_id);
CREATE INDEX idx_boletos_client_id ON boletos(client_id);
CREATE INDEX idx_boletos_nosso_numero ON boletos(nosso_numero);
CREATE INDEX idx_boletos_seu_numero ON boletos(seu_numero);
CREATE INDEX idx_boletos_data_vencimento ON boletos(data_vencimento);
CREATE INDEX idx_boletos_data_emissao ON boletos(data_emissao);
CREATE INDEX idx_boletos_status ON boletos(status);

-- Composite indexes for common queries
CREATE INDEX idx_boletos_company_client ON boletos(company_id, client_id);
CREATE INDEX idx_boletos_company_status ON boletos(company_id, status);
CREATE INDEX idx_boletos_company_vencimento ON boletos(company_id, data_vencimento);
CREATE INDEX idx_boletos_seu_numero_company ON boletos(seu_numero, company_id);

-- Step 4: Create trigger for updated_at
CREATE TRIGGER update_boletos_updated_at
    BEFORE UPDATE ON boletos
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- Verificação: Deve retornar a estrutura da tabela
-- ============================================================================
-- SELECT column_name, data_type, is_nullable, column_default
-- FROM information_schema.columns
-- WHERE table_name = 'boletos'
-- ORDER BY ordinal_position;
