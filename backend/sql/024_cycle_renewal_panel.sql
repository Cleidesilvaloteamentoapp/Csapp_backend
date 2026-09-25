-- =============================================================================
-- Painel de renovação de ciclos — ALTERAÇÃO DE SCHEMA
--
-- ESTE É O SCRIPT QUE FALTAVA. Rode-o ANTES de 022 (reconciliação).
-- Sem ele o backend quebra com 500 e a mensagem:
--     column cycle_approvals.is_final_cycle does not exist
--
-- O QUE FAZ
--   1. Novas colunas em cycle_approvals (retrato de quitação, último ciclo,
--      renovação forçada)
--   2. Unicidade de (client_lot_id, cycle_number)
--   3. Tabela deed_checklists (checklist de escrituração) + RLS
--   4. Novo valor ESCRITURACAO_PENDENTE no enum notification_type
--
-- É IDEMPOTENTE: pode rodar de novo sem quebrar.
--
-- ATENÇÃO: o passo 4 (ALTER TYPE ... ADD VALUE) precisa ser executado
-- SOZINHO, fora de transação. No SQL Editor do Supabase, rode a PARTE A
-- inteira primeiro e, depois, a PARTE B separadamente.
-- =============================================================================


-- =============================================================================
-- PARTE A — colunas, constraint e tabela
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. cycle_approvals: retrato de quitação + último ciclo + renovação forçada
-- ---------------------------------------------------------------------------
ALTER TABLE cycle_approvals
    ADD COLUMN IF NOT EXISTS is_final_cycle  boolean       NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS unpaid_count    integer       NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS overdue_amount  numeric(14,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS forced          boolean       NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS forced_reason   text,
    ADD COLUMN IF NOT EXISTS forced_by       uuid;

COMMENT ON COLUMN cycle_approvals.is_final_cycle IS
    'Último ciclo do contrato; dispara o alerta de escrituração';
COMMENT ON COLUMN cycle_approvals.unpaid_count IS
    'Parcelas do ciclo que fecha ainda não liquidadas via boleto';

DO $$ BEGIN
    ALTER TABLE cycle_approvals
        ADD CONSTRAINT cycle_approvals_forced_by_fkey
        FOREIGN KEY (forced_by) REFERENCES profiles(id) ON DELETE SET NULL;
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- ---------------------------------------------------------------------------
-- 2. Unicidade (client_lot_id, cycle_number)
--    Remove duplicatas antigas antes, senão a constraint não é criável.
-- ---------------------------------------------------------------------------
DELETE FROM cycle_approvals a
USING cycle_approvals b
WHERE a.client_lot_id = b.client_lot_id
  AND a.cycle_number  = b.cycle_number
  AND a.ctid > b.ctid;

DO $$ BEGIN
    ALTER TABLE cycle_approvals
        ADD CONSTRAINT uq_cycle_approvals_lot_cycle
        UNIQUE (client_lot_id, cycle_number);
EXCEPTION
    WHEN duplicate_table THEN NULL;
    WHEN duplicate_object THEN NULL;
END $$;

-- ---------------------------------------------------------------------------
-- 3. deed_checklists — checklist de escrituração do último ciclo
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS deed_checklists (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id    uuid NOT NULL REFERENCES companies(id)   ON DELETE CASCADE,
    client_lot_id uuid NOT NULL UNIQUE
                       REFERENCES client_lots(id) ON DELETE CASCADE,
    items         jsonb NOT NULL DEFAULT '[]'::jsonb,
    notes         text,
    completed_at  timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

COMMENT ON COLUMN deed_checklists.items IS
    '[{document_type, label, done, note, updated_at}]';

CREATE INDEX IF NOT EXISTS ix_deed_checklists_company_id
    ON deed_checklists (company_id);
CREATE INDEX IF NOT EXISTS ix_deed_checklists_client_lot_id
    ON deed_checklists (client_lot_id);

-- RLS no mesmo padrão das demais tabelas do tenant
ALTER TABLE deed_checklists ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "deed_checklists_super_admin_all" ON deed_checklists;
CREATE POLICY "deed_checklists_super_admin_all" ON deed_checklists
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
        AND p.role = 'SUPER_ADMIN'
    )
  );

DROP POLICY IF EXISTS "deed_checklists_company_admin" ON deed_checklists;
CREATE POLICY "deed_checklists_company_admin" ON deed_checklists
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.id = auth.uid()
        AND p.role IN ('COMPANY_ADMIN', 'STAFF')
        AND p.company_id = deed_checklists.company_id
    )
  );


-- =============================================================================
-- PARTE B — novo valor de enum (RODE SEPARADO, sozinho)
--
-- O Postgres não deixa usar um valor de enum na mesma transação em que ele é
-- criado, e o SQL Editor envolve o lote todo em uma transação. Execute só
-- esta linha, em uma segunda rodada.
-- =============================================================================

ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'ESCRITURACAO_PENDENTE';


-- =============================================================================
-- CONFERÊNCIA — depois de rodar A e B
-- =============================================================================
/*
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'cycle_approvals'
  AND column_name IN ('is_final_cycle','unpaid_count','overdue_amount',
                      'forced','forced_reason','forced_by')
ORDER BY column_name;
-- Esperado: 6 linhas.

SELECT to_regclass('public.deed_checklists') AS tabela_escrituracao;
-- Esperado: deed_checklists (não nulo).

SELECT 'ESCRITURACAO_PENDENTE' = ANY (enum_range(NULL::notification_type)::text[])
       AS enum_ok;
-- Esperado: t

SELECT conname FROM pg_constraint WHERE conname = 'uq_cycle_approvals_lot_cycle';
-- Esperado: 1 linha.
*/
