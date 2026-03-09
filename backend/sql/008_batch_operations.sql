-- ============================================================
-- 008_batch_operations.sql
-- Table and RLS policies for batch boleto operations
-- ============================================================

-- 1. Create table
CREATE TABLE IF NOT EXISTS batch_operations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,

    type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',

    client_id UUID REFERENCES clients(id) ON DELETE SET NULL,
    frequency VARCHAR(20),
    duration_months INTEGER,

    total_items INTEGER NOT NULL DEFAULT 0,
    completed_items INTEGER NOT NULL DEFAULT 0,
    failed_items INTEGER NOT NULL DEFAULT 0,

    input_data JSONB DEFAULT '{}',
    results JSONB DEFAULT '[]',
    error_summary TEXT,

    created_by UUID REFERENCES profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Indexes
CREATE INDEX IF NOT EXISTS idx_batch_operations_company ON batch_operations(company_id);
CREATE INDEX IF NOT EXISTS idx_batch_operations_status ON batch_operations(status);
CREATE INDEX IF NOT EXISTS idx_batch_operations_type ON batch_operations(type);
CREATE INDEX IF NOT EXISTS idx_batch_operations_created_at ON batch_operations(created_at DESC);

-- 3. RLS
ALTER TABLE batch_operations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "batch_ops_select_own_company" ON batch_operations
    FOR SELECT
    USING (company_id = auth.uid()::uuid OR company_id IN (
        SELECT p.company_id FROM profiles p WHERE p.id = auth.uid()
    ));

CREATE POLICY "batch_ops_insert_own_company" ON batch_operations
    FOR INSERT
    WITH CHECK (company_id IN (
        SELECT p.company_id FROM profiles p WHERE p.id = auth.uid()
    ));

CREATE POLICY "batch_ops_update_own_company" ON batch_operations
    FOR UPDATE
    USING (company_id IN (
        SELECT p.company_id FROM profiles p WHERE p.id = auth.uid()
    ));

-- 4. Add NEGATIVADO to boleto_status enum (if not already done)
ALTER TYPE boleto_status ADD VALUE IF NOT EXISTS 'NEGATIVADO';

-- 5. Updated_at trigger
CREATE OR REPLACE FUNCTION update_batch_operations_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_batch_operations_updated_at
    BEFORE UPDATE ON batch_operations
    FOR EACH ROW
    EXECUTE FUNCTION update_batch_operations_updated_at();
