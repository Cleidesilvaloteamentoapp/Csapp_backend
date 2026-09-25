-- =============================================================================
-- Reconciliação: vincular boletos antigos às faturas que eles cobram
--
-- POR QUE ISTO EXISTE
-- A criação de boletos em lote gravava o boleto SEM invoice_id. Com isso o
-- pagamento nunca baixava a parcela, o ciclo de 12 nunca era reconhecido como
-- quitado e a tela de Aprovação de Ciclos ficava permanentemente vazia, por
-- mais que o cliente pagasse. O código já foi corrigido; este script conserta
-- os boletos emitidos ANTES da correção.
--
-- COMO USAR NO SUPABASE (SQL Editor)
--   PARTE 1  -> diagnóstico. Só lê. Rode primeiro.
--   PARTE 2  -> detalhe linha a linha (o que casa, o que está ambíguo).
--   PARTE 3  -> aplica. Só rode depois de conferir a PARTE 1.
--   PARTE 4  -> conferência pós-aplicação.
--
-- CRITÉRIO DE CASAMENTO (conservador de propósito)
-- Mesmo cliente + mesma empresa + mesmo vencimento + mesmo valor, e o par tem
-- de ser 1-para-1 nos dois sentidos. Qualquer ambiguidade é deixada de fora e
-- reportada, em vez de ser adivinhada.
-- =============================================================================


-- =============================================================================
-- PARTE 1 — DIAGNÓSTICO (somente leitura)
-- =============================================================================

WITH orphan_boletos AS (
    SELECT b.id, b.company_id, b.client_id, b.data_vencimento, b.valor,
           b.status, b.nosso_numero, b.data_liquidacao
    FROM boletos b
    WHERE b.invoice_id IS NULL
      AND b.status <> 'CANCELADO'
      -- Para limitar a uma empresa, descomente:
      -- AND b.company_id = '00000000-0000-0000-0000-000000000000'
),
available_invoices AS (
    SELECT i.id, i.company_id, cl.client_id, i.due_date, i.amount,
           i.installment_number, i.status
    FROM invoices i
    JOIN client_lots cl ON cl.id = i.client_lot_id
    WHERE i.status <> 'CANCELLED'
      AND NOT EXISTS (SELECT 1 FROM boletos b2 WHERE b2.invoice_id = i.id)
),
pairs AS (
    SELECT ob.id AS boleto_id,
           ai.id AS invoice_id,
           COUNT(*) OVER (PARTITION BY ob.id) AS candidatas_por_boleto,
           COUNT(*) OVER (PARTITION BY ai.id) AS boletos_por_fatura
    FROM orphan_boletos ob
    JOIN available_invoices ai
      ON ai.company_id      = ob.company_id
     AND ai.client_id       = ob.client_id
     AND ai.due_date        = ob.data_vencimento
     AND ai.amount          = ob.valor
),
classificacao AS (
    SELECT ob.id AS boleto_id,
           CASE
               WHEN p.boleto_id IS NULL THEN 'SEM CORRESPONDENCIA'
               WHEN p.candidatas_por_boleto = 1 AND p.boletos_por_fatura = 1 THEN 'VINCULAVEL'
               ELSE 'AMBIGUO'
           END AS situacao
    FROM orphan_boletos ob
    LEFT JOIN pairs p ON p.boleto_id = ob.id
    GROUP BY ob.id, p.boleto_id, p.candidatas_por_boleto, p.boletos_por_fatura
)
SELECT situacao,
       COUNT(*) AS boletos
FROM classificacao
GROUP BY situacao
ORDER BY situacao;

-- Esperado: a maioria em VINCULAVEL. AMBIGUO = duas parcelas idênticas
-- (mesmo vencimento e valor) no mesmo cliente; resolva essas à mão.


-- =============================================================================
-- PARTE 2 — DETALHE LINHA A LINHA (somente leitura)
-- =============================================================================
/*
WITH orphan_boletos AS (
    SELECT b.id, b.company_id, b.client_id, b.data_vencimento, b.valor,
           b.status, b.nosso_numero
    FROM boletos b
    WHERE b.invoice_id IS NULL
      AND b.status <> 'CANCELADO'
),
available_invoices AS (
    SELECT i.id, i.company_id, cl.client_id, i.due_date, i.amount,
           i.installment_number, i.status
    FROM invoices i
    JOIN client_lots cl ON cl.id = i.client_lot_id
    WHERE i.status <> 'CANCELLED'
      AND NOT EXISTS (SELECT 1 FROM boletos b2 WHERE b2.invoice_id = i.id)
),
pairs AS (
    SELECT ob.id AS boleto_id,
           ai.id AS invoice_id,
           ai.installment_number,
           COUNT(*) OVER (PARTITION BY ob.id) AS candidatas_por_boleto,
           COUNT(*) OVER (PARTITION BY ai.id) AS boletos_por_fatura
    FROM orphan_boletos ob
    JOIN available_invoices ai
      ON ai.company_id = ob.company_id
     AND ai.client_id  = ob.client_id
     AND ai.due_date   = ob.data_vencimento
     AND ai.amount     = ob.valor
)
SELECT ob.nosso_numero,
       c.full_name                AS cliente,
       ob.data_vencimento,
       ob.valor,
       ob.status                  AS status_boleto,
       p.installment_number       AS parcela,
       CASE
           WHEN p.boleto_id IS NULL THEN 'SEM CORRESPONDENCIA'
           WHEN p.candidatas_por_boleto = 1 AND p.boletos_por_fatura = 1 THEN 'VINCULAVEL'
           ELSE 'AMBIGUO'
       END AS situacao
FROM orphan_boletos ob
JOIN clients c ON c.id = ob.client_id
LEFT JOIN pairs p ON p.boleto_id = ob.id
ORDER BY situacao, c.full_name, ob.data_vencimento;
*/


-- =============================================================================
-- PARTE 3 — APLICAR
--
-- Uma única instrução, atômica: vincula o boleto à fatura e, quando o boleto
-- já está LIQUIDADO, fecha a parcela como PAGA — que é justamente o estado que
-- faltava para o ciclo ser reconhecido como quitado.
-- Remova os marcadores de comentario das linhas abaixo para executar.
-- =============================================================================
/*
BEGIN;

WITH orphan_boletos AS (
    SELECT b.id, b.company_id, b.client_id, b.data_vencimento, b.valor,
           b.status, b.data_liquidacao
    FROM boletos b
    WHERE b.invoice_id IS NULL
      AND b.status <> 'CANCELADO'
),
available_invoices AS (
    SELECT i.id, i.company_id, cl.client_id, i.due_date, i.amount
    FROM invoices i
    JOIN client_lots cl ON cl.id = i.client_lot_id
    WHERE i.status <> 'CANCELLED'
      AND NOT EXISTS (SELECT 1 FROM boletos b2 WHERE b2.invoice_id = i.id)
),
pairs AS (
    SELECT ob.id AS boleto_id,
           ai.id AS invoice_id,
           COUNT(*) OVER (PARTITION BY ob.id) AS candidatas_por_boleto,
           COUNT(*) OVER (PARTITION BY ai.id) AS boletos_por_fatura
    FROM orphan_boletos ob
    JOIN available_invoices ai
      ON ai.company_id = ob.company_id
     AND ai.client_id  = ob.client_id
     AND ai.due_date   = ob.data_vencimento
     AND ai.amount     = ob.valor
),
unique_pairs AS (
    SELECT boleto_id, invoice_id
    FROM pairs
    WHERE candidatas_por_boleto = 1
      AND boletos_por_fatura    = 1
),
bound AS (
    UPDATE boletos b
    SET invoice_id = up.invoice_id,
        -- Boleto órfão de lote é parcela de contrato; segunda via e
        -- renegociação já gravam invoice_id na origem.
        tag = COALESCE(b.tag, 'PARCELA_CONTRATO'::boleto_tag)
    FROM unique_pairs up
    WHERE b.id = up.boleto_id
    RETURNING b.id            AS boleto_id,
              up.invoice_id   AS invoice_id,
              b.status        AS boleto_status,
              b.data_liquidacao
)
UPDATE invoices i
SET status  = 'PAID',
    paid_at = COALESCE(
        i.paid_at,
        bound.data_liquidacao::timestamptz,
        now()
    )
FROM bound
WHERE i.id = bound.invoice_id
  AND bound.boleto_status = 'LIQUIDADO'
  AND i.status <> 'PAID';

-- Confira os números da PARTE 4 ANTES de confirmar.
-- COMMIT;
-- ROLLBACK;
*/


-- =============================================================================
-- PARTE 4 — CONFERÊNCIA (rode depois do COMMIT)
-- =============================================================================
/*
SELECT
    (SELECT COUNT(*) FROM boletos
      WHERE invoice_id IS NULL AND status <> 'CANCELADO')        AS boletos_ainda_orfaos,
    (SELECT COUNT(*) FROM boletos WHERE invoice_id IS NOT NULL)  AS boletos_vinculados,
    (SELECT COUNT(*) FROM invoices i
       JOIN boletos b ON b.invoice_id = i.id
      WHERE b.status = 'LIQUIDADO' AND i.status <> 'PAID')       AS liquidados_sem_parcela_paga;

-- boletos_ainda_orfaos  -> só os AMBIGUO/SEM CORRESPONDENCIA da PARTE 1
-- liquidados_sem_parcela_paga -> tem de ser 0

-- Contratos que passam a ter ciclo completo e devem gerar renovação no próximo
-- ciclo da tarefa diária (04:00):
SELECT cl.id                       AS client_lot_id,
       c.full_name                 AS cliente,
       cl.current_cycle,
       COUNT(*) FILTER (
           WHERE i.status = 'PAID' AND b.status = 'LIQUIDADO'
       )                           AS parcelas_liquidadas_no_ciclo
FROM client_lots cl
JOIN clients  c ON c.id = cl.client_id
JOIN invoices i ON i.client_lot_id = cl.id
LEFT JOIN boletos b ON b.invoice_id = i.id
WHERE cl.status = 'ACTIVE'
  AND i.installment_number >  (cl.current_cycle - 1) * 12
  AND i.installment_number <=  cl.current_cycle      * 12
GROUP BY cl.id, c.full_name, cl.current_cycle
HAVING COUNT(*) FILTER (WHERE i.status = 'PAID' AND b.status = 'LIQUIDADO') >= 12
ORDER BY c.full_name;
*/
