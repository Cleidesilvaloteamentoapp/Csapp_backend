-- =============================================================================
-- Sicredi Credentials Table - Execute no Supabase SQL Editor
-- =============================================================================

-- Criar tabela sicredi_credentials
CREATE TABLE IF NOT EXISTS sicredi_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    
    -- Sicredi API credentials (CONFIDENCIAL - nunca expor no frontend)
    x_api_key VARCHAR(100) NOT NULL,
    username VARCHAR(50) NOT NULL,
    password VARCHAR(255) NOT NULL,
    
    -- Cooperativa / Posto / Beneficiário
    cooperativa VARCHAR(10) NOT NULL,
    posto VARCHAR(10) NOT NULL,
    codigo_beneficiario VARCHAR(20) NOT NULL,
    
    -- Environment: "sandbox" ou "production"
    environment VARCHAR(20) NOT NULL DEFAULT 'production',
    
    -- Cached OAuth2 tokens (CRÍTICO - nunca expor)
    access_token TEXT,
    refresh_token TEXT,
    token_expires_at TIMESTAMPTZ,
    refresh_expires_at TIMESTAMPTZ,
    
    -- Webhook contract ID (se registrado)
    webhook_contract_id VARCHAR(100),
    
    -- Active flag
    is_active BOOLEAN NOT NULL DEFAULT true,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_sicredi_creds_company_id 
    ON sicredi_credentials(company_id);

CREATE INDEX IF NOT EXISTS idx_sicredi_creds_company_active 
    ON sicredi_credentials(company_id, is_active);

-- Comentários na tabela
COMMENT ON TABLE sicredi_credentials IS 'Credenciais da API Sicredi Cobrança por empresa (tenant)';
COMMENT ON COLUMN sicredi_credentials.x_api_key IS 'UUID token do portal de desenvolvedor Sicredi';
COMMENT ON COLUMN sicredi_credentials.username IS 'Código beneficiário + cooperativa';
COMMENT ON COLUMN sicredi_credentials.password IS 'Código de acesso do Internet Banking';
COMMENT ON COLUMN sicredi_credentials.access_token IS 'Token OAuth2 em cache (renovado automaticamente)';
COMMENT ON COLUMN sicredi_credentials.refresh_token IS 'Refresh token OAuth2';

-- =============================================================================
-- Row Level Security (RLS) - CRÍTICO para multi-tenancy
-- =============================================================================

-- Ativar RLS na tabela
ALTER TABLE sicredi_credentials ENABLE ROW LEVEL SECURITY;

-- Super admin: acesso total
CREATE POLICY "sicredi_creds_super_admin_all" ON sicredi_credentials
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role = 'SUPER_ADMIN'
    )
  );

-- Company admin: apenas credenciais da própria empresa
CREATE POLICY "sicredi_creds_company_isolation" ON sicredi_credentials
  FOR ALL
  USING (
    company_id IN (
      SELECT p.company_id FROM profiles p
      WHERE p.id = auth.uid()
      AND p.role IN ('SUPER_ADMIN', 'COMPANY_ADMIN')
    )
  );

-- =============================================================================
-- Trigger para atualizar updated_at automaticamente
-- =============================================================================

-- Criar função de trigger se não existir
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Aplicar trigger
DROP TRIGGER IF EXISTS update_sicredi_credentials_updated_at ON sicredi_credentials;

CREATE TRIGGER update_sicredi_credentials_updated_at
    BEFORE UPDATE ON sicredi_credentials
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- Concluído!
-- =============================================================================

-- Verificar se a tabela foi criada corretamente
SELECT 
    'Tabela sicredi_credentials criada com sucesso!' as status,
    COUNT(*) as total_registros
FROM sicredi_credentials;
