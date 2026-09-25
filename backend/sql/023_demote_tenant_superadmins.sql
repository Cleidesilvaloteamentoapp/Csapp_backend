-- =============================================================================
-- Rebaixar super admins de empresa para COMPANY_ADMIN
--
-- RODE ISTO ANTES de subir a versão que dá alcance entre empresas ao SUPER_ADMIN.
--
-- POR QUE
-- Nada no sistema criava COMPANY_ADMIN: o cadastro público e /admin/superadmins
-- criavam SUPER_ADMIN. Ou seja, o administrador de CADA empresa hoje tem o papel
-- de plataforma. No momento em que SUPER_ADMIN passa a enxergar outras empresas,
-- todo cliente passaria a ver os dados de todos os outros.
--
-- SUPER_ADMIN  = plataforma (cria empresas e o administrador delas)
-- COMPANY_ADMIN = manda em tudo DENTRO da própria empresa, e só nela
--
-- ORDEM: PARTE 1 (ver) -> editar a lista da PARTE 2 -> PARTE 2 (aplicar) -> PARTE 3
-- =============================================================================


-- =============================================================================
-- PARTE 1 — Quem é SUPER_ADMIN hoje (somente leitura)
--
-- Anote os e-mails que devem CONTINUAR sendo plataforma (normalmente só os
-- seus). Todo o resto vira administrador da própria empresa.
-- =============================================================================

SELECT p.email,
       p.full_name,
       c.name        AS empresa,
       p.is_active,
       p.created_at
FROM profiles p
JOIN companies c ON c.id = p.company_id
WHERE p.role = 'SUPER_ADMIN'
ORDER BY c.name, p.created_at;


-- =============================================================================
-- PARTE 2 — APLICAR
--
-- Edite keep_emails com os e-mails que continuam SUPER_ADMIN, em minúsculas.
-- O bloco se recusa a rodar se a lista não bater com ninguém — demover todo
-- mundo deixaria a plataforma sem quem crie empresas.
-- Remova os marcadores de comentario das linhas abaixo para executar.
-- =============================================================================
/*
DO $$
DECLARE
    -- >>> EDITE AQUI <<<
    keep_emails text[] := ARRAY[
        'troque-por-seu-email@exemplo.com'
    ];
    mantidos    int;
    rebaixados  int;
BEGIN
    SELECT count(*) INTO mantidos
    FROM profiles
    WHERE role = 'SUPER_ADMIN'
      AND lower(email) = ANY (keep_emails);

    IF mantidos = 0 THEN
        RAISE EXCEPTION
            'Nenhum SUPER_ADMIN corresponde a keep_emails. Confira a lista da PARTE 1: '
            'sem nenhum super admin de plataforma, ninguem consegue criar empresas.';
    END IF;

    UPDATE profiles
    SET role = 'COMPANY_ADMIN'
    WHERE role = 'SUPER_ADMIN'
      AND lower(email) <> ALL (keep_emails);

    GET DIAGNOSTICS rebaixados = ROW_COUNT;

    RAISE NOTICE 'Mantidos como plataforma: %. Rebaixados a COMPANY_ADMIN: %.',
                 mantidos, rebaixados;
    RAISE NOTICE 'Os rebaixados precisam sair e entrar de novo: o papel vai no token.';
END $$;
*/


-- =============================================================================
-- PARTE 3 — CONFERÊNCIA
-- =============================================================================
/*
SELECT p.role, c.name AS empresa, p.email
FROM profiles p
JOIN companies c ON c.id = p.company_id
WHERE p.role IN ('SUPER_ADMIN', 'COMPANY_ADMIN')
ORDER BY p.role, c.name, p.email;

-- Toda empresa precisa ter ao menos um administrador, ou ninguem entra nela:
SELECT c.name AS empresa_sem_administrador
FROM companies c
WHERE NOT EXISTS (
    SELECT 1 FROM profiles p
    WHERE p.company_id = c.id
      AND p.role IN ('SUPER_ADMIN', 'COMPANY_ADMIN')
      AND p.is_active
);
-- Se aparecer alguma, crie o administrador em /admin/empresas (console do super admin).
*/
