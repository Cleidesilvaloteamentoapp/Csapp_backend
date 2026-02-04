# Configuração Manual dos Storage Buckets no Supabase

## ⚠️ IMPORTANTE
Os buckets de storage **NÃO PODEM** ser criados via SQL direto. 
Você deve criá-los através do Dashboard do Supabase.

## Passo a Passo

### 1. Acesse o Supabase Dashboard
1. Vá para https://app.supabase.com
2. Selecione seu projeto
3. No menu lateral, clique em **Storage**

### 2. Crie os Buckets

Crie **4 buckets** com as seguintes configurações:

#### Bucket 1: client-documents
- **Name**: `client-documents`
- **Public**: ❌ Desmarque (privado)
- **File size limit**: 10 MB (10485760 bytes)
- **Allowed MIME types**: 
  - `application/pdf`
  - `image/jpeg`
  - `image/png`
  - `image/jpg`
  - `application/msword`
  - `application/vnd.openxmlformats-officedocument.wordprocessingml.document`

#### Bucket 2: lot-documents
- **Name**: `lot-documents`
- **Public**: ❌ Desmarque (privado)
- **File size limit**: 10 MB
- **Allowed MIME types**: (mesmos do client-documents)

#### Bucket 3: development-documents
- **Name**: `development-documents`
- **Public**: ❌ Desmarque (privado)
- **File size limit**: 10 MB
- **Allowed MIME types**:
  - `application/pdf`
  - `image/jpeg`
  - `image/png`
  - `image/jpg`

#### Bucket 4: service-documents
- **Name**: `service-documents`
- **Public**: ❌ Desmarque (privado)
- **File size limit**: 10 MB
- **Allowed MIME types**:
  - `application/pdf`
  - `image/jpeg`
  - `image/png`
  - `image/jpg`

### 3. Configure as Políticas RLS

Após criar os buckets, execute o SQL abaixo no **SQL Editor** do Supabase:

```sql
-- ============================================
-- STORAGE RLS POLICIES
-- Execute este SQL APÓS criar os buckets manualmente
-- ============================================

-- Helper function to check admin status for storage
CREATE OR REPLACE FUNCTION storage.is_admin()
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM public.profiles
        WHERE id = auth.uid()
        AND role = 'admin'
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================
-- CLIENT-DOCUMENTS BUCKET POLICIES
-- ============================================

-- Admin can do everything
CREATE POLICY "admin_all_client_documents" ON storage.objects
    FOR ALL
    USING (bucket_id = 'client-documents' AND storage.is_admin())
    WITH CHECK (bucket_id = 'client-documents' AND storage.is_admin());

-- Clients can read their own documents
CREATE POLICY "clients_read_own_documents" ON storage.objects
    FOR SELECT
    USING (
        bucket_id = 'client-documents'
        AND (storage.foldername(name))[1] IN (
            SELECT c.id::text FROM public.clients c
            WHERE c.profile_id = auth.uid()
        )
    );

-- Clients can upload their own documents
CREATE POLICY "clients_upload_own_documents" ON storage.objects
    FOR INSERT
    WITH CHECK (
        bucket_id = 'client-documents'
        AND (storage.foldername(name))[1] IN (
            SELECT c.id::text FROM public.clients c
            WHERE c.profile_id = auth.uid()
        )
    );

-- ============================================
-- LOT-DOCUMENTS BUCKET POLICIES
-- ============================================

CREATE POLICY "admin_all_lot_documents" ON storage.objects
    FOR ALL
    USING (bucket_id = 'lot-documents' AND storage.is_admin())
    WITH CHECK (bucket_id = 'lot-documents' AND storage.is_admin());

CREATE POLICY "clients_read_lot_documents" ON storage.objects
    FOR SELECT
    USING (
        bucket_id = 'lot-documents'
        AND (storage.foldername(name))[1] IN (
            SELECT cl.lot_id::text 
            FROM public.client_lots cl
            JOIN public.clients c ON c.id = cl.client_id
            WHERE c.profile_id = auth.uid()
        )
    );

-- ============================================
-- DEVELOPMENT-DOCUMENTS BUCKET POLICIES
-- ============================================

CREATE POLICY "admin_all_development_documents" ON storage.objects
    FOR ALL
    USING (bucket_id = 'development-documents' AND storage.is_admin())
    WITH CHECK (bucket_id = 'development-documents' AND storage.is_admin());

CREATE POLICY "authenticated_read_development_documents" ON storage.objects
    FOR SELECT
    USING (bucket_id = 'development-documents' AND auth.role() = 'authenticated');

-- ============================================
-- SERVICE-DOCUMENTS BUCKET POLICIES
-- ============================================

CREATE POLICY "admin_all_service_documents" ON storage.objects
    FOR ALL
    USING (bucket_id = 'service-documents' AND storage.is_admin())
    WITH CHECK (bucket_id = 'service-documents' AND storage.is_admin());

CREATE POLICY "clients_read_service_documents" ON storage.objects
    FOR SELECT
    USING (
        bucket_id = 'service-documents'
        AND (storage.foldername(name))[1] IN (
            SELECT so.id::text 
            FROM public.service_orders so
            JOIN public.clients c ON c.id = so.client_id
            WHERE c.profile_id = auth.uid()
        )
    );
```

### 4. Verificação

Para verificar se os buckets foram criados corretamente:

```sql
SELECT * FROM storage.buckets;
```

Você deve ver os 4 buckets listados.

### 5. Testar Upload

Teste o upload através da API do backend:
- Endpoint: `POST /api/v1/client/documents`
- Envie um arquivo PDF ou imagem
- Verifique se o arquivo aparece no bucket correspondente

## Troubleshooting

### Erro: "new row violates row-level security policy"
- Verifique se as políticas RLS foram criadas corretamente
- Confirme que o usuário está autenticado
- Para admin: verifique se o role está correto na tabela `profiles`

### Erro: "File type not allowed"
- Verifique os MIME types permitidos no bucket
- Adicione o tipo necessário nas configurações do bucket

### Erro: "File size exceeds limit"
- Aumente o limite no bucket (máximo recomendado: 50MB)
- Ou reduza o tamanho do arquivo antes do upload
