-- 020: add BAIXA_EXTERNA to the writeoff_type enum.
-- Mirrors alembic revision 017_writeoff_type_baixa_externa.
--
-- writeoff_type was created in 011_client_adjustments_ddl.sql with only
-- ('AUTOMATICA_BANCO', 'MANUAL_ADMIN'). The Sicredi reconciliation writes
-- BAIXA_EXTERNA when the bank reports situação BAIXADO / BAIXADO POR
-- SOLICITACAO, which failed with:
--   invalid input value for enum writeoff_type: "BAIXA_EXTERNA"
--
-- Run this on its own (ALTER TYPE ... ADD VALUE cannot share a transaction with
-- a statement that uses the new label).

ALTER TYPE writeoff_type ADD VALUE IF NOT EXISTS 'BAIXA_EXTERNA';
