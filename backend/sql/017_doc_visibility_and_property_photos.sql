-- ============================================================================
-- 017 — Visibilidade de documentos ao cliente + fotos de empreendimentos/lotes
--
-- - client_documents.visible_to_client: expõe (ou não) o documento no portal
--   do cliente. Padrão FALSE (oculto) — admin marca a "chave" para expor.
-- - developments.photos / lots.photos: galeria de fotos (JSONB) com foto
--   principal e flag de visibilidade ao cliente por foto.
--
-- Cada item de photos tem o formato:
--   { "id": "<uuid hex>", "path": "<storage path>",
--     "is_primary": bool, "visible_to_client": bool, "caption": text|null }
--
-- Seguro para rodar várias vezes (idempotente).
-- ============================================================================

-- 1. Documentos: chave de exposição ao cliente -------------------------------
ALTER TABLE client_documents
    ADD COLUMN IF NOT EXISTS visible_to_client BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN client_documents.visible_to_client
    IS 'Quando TRUE, o documento aparece para o cliente no portal. Padrão oculto.';

CREATE INDEX IF NOT EXISTS ix_client_documents_visible_to_client
    ON client_documents (visible_to_client);

-- 2. Fotos de empreendimentos e lotes ---------------------------------------
ALTER TABLE developments
    ADD COLUMN IF NOT EXISTS photos JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE lots
    ADD COLUMN IF NOT EXISTS photos JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN developments.photos
    IS 'Galeria de fotos: [{id, path, is_primary, visible_to_client, caption}]';
COMMENT ON COLUMN lots.photos
    IS 'Galeria de fotos: [{id, path, is_primary, visible_to_client, caption}]';
