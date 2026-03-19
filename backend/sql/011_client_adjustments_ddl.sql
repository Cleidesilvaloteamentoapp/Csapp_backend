-- =============================================================================
-- DDL para Client Adjustments (migração 006)
-- Executar ANTES do RLS (010_client_adjustments_rls.sql)
-- =============================================================================

-- =========================================================================
-- 1. NOVOS TIPOS ENUM
-- =========================================================================

DO $$ BEGIN
    CREATE TYPE boleto_tag AS ENUM (
        'ENTRADA_PARCELADA', 'PARCELA_CONTRATO', 'SERVICO_AVULSO',
        'SEGUNDA_VIA', 'RENEGOCIACAO'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE writeoff_type AS ENUM ('AUTOMATICA_BANCO', 'MANUAL_ADMIN');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE adjustment_index AS ENUM ('IPCA', 'IGPM', 'CUB', 'INPC');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE adjustment_frequency AS ENUM (
        'MONTHLY', 'QUARTERLY', 'SEMIANNUAL', 'ANNUAL'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE cycle_approval_status AS ENUM ('PENDING', 'APPROVED', 'REJECTED');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE transfer_status AS ENUM (
        'PENDING', 'APPROVED', 'COMPLETED', 'CANCELLED'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE early_payoff_status AS ENUM (
        'PENDING', 'CONTACTED', 'COMPLETED', 'CANCELLED'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE index_source AS ENUM ('MANUAL', 'BCB_API');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- =========================================================================
-- 2. VALORES NOVOS EM ENUMS EXISTENTES
-- =========================================================================

-- boleto_status
DO $$ BEGIN
    ALTER TYPE boleto_status ADD VALUE IF NOT EXISTS 'BAIXA_MANUAL';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- notification_type
DO $$ BEGIN
    ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'CICLO_PENDENTE';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'TRANSFERENCIA_CONTRATO';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'ANTECIPACAO_SOLICITADA';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'DISTRATO_AUTOMATICO';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- contract_event_type
DO $$ BEGIN
    ALTER TYPE contract_event_type ADD VALUE IF NOT EXISTS 'TRANSFER';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TYPE contract_event_type ADD VALUE IF NOT EXISTS 'AUTO_RESCISSION';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TYPE contract_event_type ADD VALUE IF NOT EXISTS 'CYCLE_APPROVED';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TYPE contract_event_type ADD VALUE IF NOT EXISTS 'EARLY_PAYOFF_REQUEST';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- =========================================================================
-- 3. ALTER TABLE boletos — novas colunas
-- =========================================================================

ALTER TABLE boletos
    ADD COLUMN IF NOT EXISTS tag              boleto_tag     DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS installment_label VARCHAR(50)   DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS writeoff_type    writeoff_type  DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS writeoff_by      UUID           DEFAULT NULL
        REFERENCES profiles(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS writeoff_reason  TEXT           DEFAULT NULL;

CREATE INDEX IF NOT EXISTS ix_boletos_tag ON boletos (tag);

-- =========================================================================
-- 4. ALTER TABLE client_lots — regras financeiras por lote + transferência
-- =========================================================================

ALTER TABLE client_lots
    ADD COLUMN IF NOT EXISTS penalty_rate            NUMERIC(6,4)          DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS daily_interest_rate     NUMERIC(8,6)          DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS adjustment_index        adjustment_index      DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS adjustment_frequency    adjustment_frequency  DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS adjustment_custom_rate  NUMERIC(6,4)          DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS previous_client_id      UUID                  DEFAULT NULL
        REFERENCES clients(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS transfer_date           DATE                  DEFAULT NULL;

COMMENT ON COLUMN client_lots.penalty_rate           IS 'Taxa de multa customizada (padrão sistema: 0.02 = 2%)';
COMMENT ON COLUMN client_lots.daily_interest_rate    IS 'Taxa de juros diária customizada (padrão: 0.00033)';
COMMENT ON COLUMN client_lots.adjustment_index       IS 'Índice de reajuste: IPCA, IGPM, CUB ou INPC';
COMMENT ON COLUMN client_lots.adjustment_frequency   IS 'Frequência do reajuste';
COMMENT ON COLUMN client_lots.adjustment_custom_rate IS 'Taxa fixa de reajuste customizada (padrão: 5% = 0.05)';
COMMENT ON COLUMN client_lots.previous_client_id     IS 'Cliente anterior após transferência de contrato';
COMMENT ON COLUMN client_lots.transfer_date          IS 'Data da última transferência de titularidade';

-- =========================================================================
-- 5. NOVA TABELA: economic_indices (índices econômicos manuais)
-- =========================================================================

CREATE TABLE IF NOT EXISTS economic_indices (
    id               UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       UUID            NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    index_type       adjustment_index NOT NULL,
    state_code       VARCHAR(2)      DEFAULT NULL,         -- UF, obrigatório para CUB
    reference_month  DATE            NOT NULL,             -- sempre dia 1 do mês
    value            NUMERIC(10,6)   NOT NULL,             -- ex: 0.45 = 0.45%
    source           index_source    NOT NULL DEFAULT 'MANUAL',
    created_by       UUID            DEFAULT NULL REFERENCES profiles(id) ON DELETE SET NULL,
    created_at       TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_economic_indices_company   ON economic_indices (company_id);
CREATE INDEX IF NOT EXISTS ix_economic_indices_type      ON economic_indices (index_type);
CREATE INDEX IF NOT EXISTS ix_economic_indices_ref_month ON economic_indices (reference_month);
CREATE INDEX IF NOT EXISTS ix_economic_indices_state     ON economic_indices (state_code);

-- =========================================================================
-- 6. NOVA TABELA: cycle_approvals (aprovação de ciclos de 12 parcelas)
-- =========================================================================

CREATE TABLE IF NOT EXISTS cycle_approvals (
    id                          UUID                    PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id                  UUID                    NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    client_lot_id               UUID                    NOT NULL REFERENCES client_lots(id) ON DELETE CASCADE,
    cycle_number                INTEGER                 NOT NULL,
    status                      cycle_approval_status   NOT NULL DEFAULT 'PENDING',
    previous_installment_value  NUMERIC(14,2)           NOT NULL,
    new_installment_value       NUMERIC(14,2)           DEFAULT NULL,
    adjustment_details          JSONB                   DEFAULT NULL,
    requested_at                TIMESTAMPTZ             NOT NULL DEFAULT now(),
    approved_at                 TIMESTAMPTZ             DEFAULT NULL,
    approved_by                 UUID                    DEFAULT NULL REFERENCES profiles(id) ON DELETE SET NULL,
    admin_notes                 TEXT                    DEFAULT NULL,
    created_at                  TIMESTAMPTZ             NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ             NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_cycle_approvals_company  ON cycle_approvals (company_id);
CREATE INDEX IF NOT EXISTS ix_cycle_approvals_cl       ON cycle_approvals (client_lot_id);
CREATE INDEX IF NOT EXISTS ix_cycle_approvals_status   ON cycle_approvals (status);

-- =========================================================================
-- 7. NOVA TABELA: contract_transfers (transferência de contrato)
-- =========================================================================

CREATE TABLE IF NOT EXISTS contract_transfers (
    id              UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID             NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    client_lot_id   UUID             NOT NULL REFERENCES client_lots(id) ON DELETE CASCADE,
    from_client_id  UUID             NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    to_client_id    UUID             NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    status          transfer_status  NOT NULL DEFAULT 'PENDING',
    transfer_fee    NUMERIC(14,2)    DEFAULT 0,
    transfer_date   DATE             DEFAULT NULL,
    reason          TEXT             DEFAULT NULL,
    admin_notes     TEXT             DEFAULT NULL,
    documents       JSONB            DEFAULT NULL,
    requested_by    UUID             NOT NULL REFERENCES profiles(id) ON DELETE SET NULL,
    approved_by     UUID             DEFAULT NULL REFERENCES profiles(id) ON DELETE SET NULL,
    approved_at     TIMESTAMPTZ      DEFAULT NULL,
    completed_at    TIMESTAMPTZ      DEFAULT NULL,
    created_at      TIMESTAMPTZ      NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ      NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_contract_transfers_company  ON contract_transfers (company_id);
CREATE INDEX IF NOT EXISTS ix_contract_transfers_cl       ON contract_transfers (client_lot_id);
CREATE INDEX IF NOT EXISTS ix_contract_transfers_from     ON contract_transfers (from_client_id);
CREATE INDEX IF NOT EXISTS ix_contract_transfers_to       ON contract_transfers (to_client_id);
CREATE INDEX IF NOT EXISTS ix_contract_transfers_status   ON contract_transfers (status);

-- =========================================================================
-- 8. NOVA TABELA: early_payoff_requests (solicitação de antecipação)
-- =========================================================================

CREATE TABLE IF NOT EXISTS early_payoff_requests (
    id              UUID                 PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID                 NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    client_id       UUID                 NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    client_lot_id   UUID                 NOT NULL REFERENCES client_lots(id) ON DELETE CASCADE,
    status          early_payoff_status  NOT NULL DEFAULT 'PENDING',
    requested_at    TIMESTAMPTZ          NOT NULL DEFAULT now(),
    admin_notes     TEXT                 DEFAULT NULL,
    client_message  TEXT                 DEFAULT NULL,
    created_at      TIMESTAMPTZ          NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ          NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_early_payoff_company  ON early_payoff_requests (company_id);
CREATE INDEX IF NOT EXISTS ix_early_payoff_client   ON early_payoff_requests (client_id);
CREATE INDEX IF NOT EXISTS ix_early_payoff_cl       ON early_payoff_requests (client_lot_id);
CREATE INDEX IF NOT EXISTS ix_early_payoff_status   ON early_payoff_requests (status);

-- =========================================================================
-- 9. TRIGGER updated_at automático para novas tabelas
-- =========================================================================

-- Reutiliza a function trigger_set_updated_at que já existe no banco.
-- Se não existir, crie:
CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_updated_at BEFORE UPDATE ON economic_indices
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER set_updated_at BEFORE UPDATE ON cycle_approvals
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER set_updated_at BEFORE UPDATE ON contract_transfers
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER set_updated_at BEFORE UPDATE ON early_payoff_requests
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
