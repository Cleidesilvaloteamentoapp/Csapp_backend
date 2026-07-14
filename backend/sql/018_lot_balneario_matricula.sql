-- ============================================================================
-- 018 — Balneário e matrícula nos lotes
--
-- Campos coletados obrigatoriamente no cadastro de lotes (wizard e tradicional):
--   - lots.balneario: balneário / localidade do terreno.
--   - lots.registration_number: número de matrícula (registro de cartório).
--
-- A matrícula é ÚNICA por empresa: impede o cadastro duplicado do mesmo terreno.
-- O índice é PARCIAL (WHERE registration_number IS NOT NULL) para não conflitar
-- com lotes legados que ainda não têm matrícula preenchida.
--
-- Obrigatoriedade é garantida na API/validação — as colunas ficam NULLABLE no
-- banco para não quebrar lotes já existentes.
--
-- Seguro para rodar várias vezes (idempotente).
-- ============================================================================

ALTER TABLE lots
    ADD COLUMN IF NOT EXISTS balneario VARCHAR(120);

ALTER TABLE lots
    ADD COLUMN IF NOT EXISTS registration_number VARCHAR(60);

COMMENT ON COLUMN lots.balneario
    IS 'Balneário / localidade do terreno';
COMMENT ON COLUMN lots.registration_number
    IS 'Número de matrícula do imóvel (registro de cartório). Único por empresa.';

CREATE UNIQUE INDEX IF NOT EXISTS uq_lots_company_registration
    ON lots (company_id, registration_number)
    WHERE registration_number IS NOT NULL;
