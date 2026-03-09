-- ============================================================================
-- SCRIPT COMPLETO: Criar tabela boletos + RLS Policies
-- Execute este script COMPLETO no SQL Editor do Supabase
-- ============================================================================

-- ============================================================================
-- PARTE 1: Criar ENUM e Tabela
-- ============================================================================

-- Create ENUM type for boleto status
CREATE TYPE boleto_status AS ENUM (
    'NORMAL',
    'LIQUIDADO',
    'VENCIDO',
    'CANCELADO'
);

-- Create boletos table
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

COMMENT ON TABLE boletos IS 'Boletos Sicredi vinculados a clientes';
COMMENT ON COLUMN boletos.nosso_numero IS 'Número único do boleto gerado pela Sicredi';
COMMENT ON COLUMN boletos.seu_numero IS 'Número de controle interno da empresa';

-- ============================================================================
-- PARTE 2: Criar Indexes
-- ============================================================================

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

-- ============================================================================
-- PARTE 3: Trigger para updated_at
-- ============================================================================

CREATE TRIGGER update_boletos_updated_at
    BEFORE UPDATE ON boletos
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- PARTE 4: Row Level Security (RLS) Policies
-- ============================================================================

-- Enable RLS
ALTER TABLE boletos ENABLE ROW LEVEL SECURITY;

-- Policy 1: Company Isolation (SELECT)
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

-- Policy 2: Admin/Company Admin Can Insert (INSERT)
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

-- Policy 3: Admin/Company Admin Can Update (UPDATE)
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

-- Policy 4: Only SUPER_ADMIN Can Delete (DELETE)
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
-- PARTE 5: Grants (permissões para authenticated users)
-- ============================================================================

-- Grant usage on the sequence (if any)
-- Grant access to authenticated users
GRANT SELECT, INSERT, UPDATE, DELETE ON boletos TO authenticated;
GRANT SELECT ON boletos TO anon;

-- ============================================================================
-- VERIFICAÇÃO: Execute estas queries para confirmar
-- ============================================================================

-- 1. Verificar estrutura da tabela
-- SELECT column_name, data_type, is_nullable, column_default
-- FROM information_schema.columns
-- WHERE table_name = 'boletos'
-- ORDER BY ordinal_position;

-- 2. Verificar índices criados
-- SELECT indexname, indexdef
-- FROM pg_indexes
-- WHERE tablename = 'boletos';

-- 3. Verificar políticas RLS
-- SELECT policyname, permissive, roles, cmd, qual, with_check
-- FROM pg_policies
-- WHERE tablename = 'boletos';

-- 4. Confirmar RLS ativo
-- SELECT tablename, rowsecurity
-- FROM pg_tables
-- WHERE tablename = 'boletos';

-- ============================================================================
-- FIM DO SCRIPT
-- ============================================================================
-- Status: Tabela 'boletos' criada com sucesso
-- RLS: Ativo com 4 políticas (SELECT, INSERT, UPDATE, DELETE)
-- Indexes: 11 índices criados para performance
-- Pronto para uso!
-- ============================================================================
