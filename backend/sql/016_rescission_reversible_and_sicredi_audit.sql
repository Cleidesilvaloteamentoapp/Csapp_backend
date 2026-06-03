-- ============================================================================
-- 016 — Reversible rescission + Sicredi audit log
--
-- Etapa 4: supports the reversible (admin-gated) rescission workflow and the
-- permanent Sicredi interaction audit trail.
-- Safe to run multiple times (idempotent guards).
-- ============================================================================

-- 1. New enum value: contracts pending rescission (billing suspended, reversible).
DO $$ BEGIN
    ALTER TYPE client_lot_status ADD VALUE IF NOT EXISTS 'IN_RESCISSION';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- 2. New contract event for reversal/auditing.
DO $$ BEGIN
    ALTER TYPE contract_event_type ADD VALUE IF NOT EXISTS 'RESCISSION_REVERSED';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- 3. Allow system-initiated rescissions (no admin yet).
ALTER TABLE rescissions ALTER COLUMN requested_by DROP NOT NULL;

-- 4. Sicredi audit log — stores every request we send and response/webhook we
--    receive, forever, for admin auditing.
CREATE TABLE IF NOT EXISTS sicredi_events (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id    UUID REFERENCES companies(id) ON DELETE SET NULL,
    direction     VARCHAR(10) NOT NULL,          -- INBOUND | OUTBOUND
    event_type    VARCHAR(80) NOT NULL,
    nosso_numero  VARCHAR(50),
    boleto_id     UUID REFERENCES boletos(id) ON DELETE SET NULL,
    invoice_id    UUID REFERENCES invoices(id) ON DELETE SET NULL,
    http_status   INTEGER,
    success       BOOLEAN,
    payload       JSONB DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_sicredi_events_company ON sicredi_events (company_id);
CREATE INDEX IF NOT EXISTS ix_sicredi_events_event_type ON sicredi_events (event_type);
CREATE INDEX IF NOT EXISTS ix_sicredi_events_nosso_numero ON sicredi_events (nosso_numero);
CREATE INDEX IF NOT EXISTS ix_sicredi_events_created_at ON sicredi_events (created_at DESC);

-- 5. RLS: company isolation for reads (backend service role bypasses RLS on insert).
ALTER TABLE sicredi_events ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    CREATE POLICY "sicredi_events_super_admin_all" ON sicredi_events
      FOR ALL
      USING (
        EXISTS (
          SELECT 1 FROM profiles p
          WHERE p.id = auth.uid() AND p.role = 'SUPER_ADMIN'
        )
      );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE POLICY "sicredi_events_company_isolation" ON sicredi_events
      FOR ALL
      USING (
        company_id IN (
          SELECT p.company_id FROM profiles p
          WHERE p.id = auth.uid()
          AND p.role IN ('SUPER_ADMIN', 'COMPANY_ADMIN')
        )
      );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
