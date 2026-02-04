# Configuração de Políticas RLS para Storage - Via Dashboard

## ⚠️ IMPORTANTE
As políticas RLS de storage **DEVEM** ser criadas através do Dashboard do Supabase, não via SQL direto.

## Passo a Passo

### 1. Acesse as Políticas de Storage

1. Vá para https://app.supabase.com
2. Selecione seu projeto
3. No menu lateral, clique em **Storage**
4. Clique no bucket que deseja configurar
5. Clique na aba **Policies**

---

## 2. Configurar Políticas para Cada Bucket

### 📁 Bucket: `client-documents`

#### Política 1: Admin Full Access
- **Policy Name**: `admin_all_client_documents`
- **Allowed operation**: `SELECT`, `INSERT`, `UPDATE`, `DELETE` (marque todos)
- **Policy definition**:
```sql
(bucket_id = 'client-documents'::text) AND 
(EXISTS ( SELECT 1
   FROM profiles
  WHERE ((profiles.id = auth.uid()) AND (profiles.role = 'admin'::user_role))))
```

#### Política 2: Clients Read Own Documents
- **Policy Name**: `clients_read_own_documents`
- **Allowed operation**: `SELECT`
- **Policy definition**:
```sql
(bucket_id = 'client-documents'::text) AND 
((storage.foldername(name))[1] IN ( SELECT c.id::text
   FROM clients c
  WHERE (c.profile_id = auth.uid())))
```

#### Política 3: Clients Upload Own Documents
- **Policy Name**: `clients_upload_own_documents`
- **Allowed operation**: `INSERT`
- **Policy definition**:
```sql
(bucket_id = 'client-documents'::text) AND 
((storage.foldername(name))[1] IN ( SELECT c.id::text
   FROM clients c
  WHERE (c.profile_id = auth.uid())))
```

---

### 📁 Bucket: `lot-documents`

#### Política 1: Admin Full Access
- **Policy Name**: `admin_all_lot_documents`
- **Allowed operation**: `SELECT`, `INSERT`, `UPDATE`, `DELETE`
- **Policy definition**:
```sql
(bucket_id = 'lot-documents'::text) AND 
(EXISTS ( SELECT 1
   FROM profiles
  WHERE ((profiles.id = auth.uid()) AND (profiles.role = 'admin'::user_role))))
```

#### Política 2: Clients Read Lot Documents
- **Policy Name**: `clients_read_lot_documents`
- **Allowed operation**: `SELECT`
- **Policy definition**:
```sql
(bucket_id = 'lot-documents'::text) AND 
((storage.foldername(name))[1] IN ( SELECT cl.lot_id::text
   FROM (client_lots cl
     JOIN clients c ON ((c.id = cl.client_id)))
  WHERE (c.profile_id = auth.uid())))
```

---

### 📁 Bucket: `development-documents`

#### Política 1: Admin Full Access
- **Policy Name**: `admin_all_development_documents`
- **Allowed operation**: `SELECT`, `INSERT`, `UPDATE`, `DELETE`
- **Policy definition**:
```sql
(bucket_id = 'development-documents'::text) AND 
(EXISTS ( SELECT 1
   FROM profiles
  WHERE ((profiles.id = auth.uid()) AND (profiles.role = 'admin'::user_role))))
```

#### Política 2: Authenticated Users Read
- **Policy Name**: `authenticated_read_development_documents`
- **Allowed operation**: `SELECT`
- **Policy definition**:
```sql
(bucket_id = 'development-documents'::text) AND 
(auth.role() = 'authenticated'::text)
```

---

### 📁 Bucket: `service-documents`

#### Política 1: Admin Full Access
- **Policy Name**: `admin_all_service_documents`
- **Allowed operation**: `SELECT`, `INSERT`, `UPDATE`, `DELETE`
- **Policy definition**:
```sql
(bucket_id = 'service-documents'::text) AND 
(EXISTS ( SELECT 1
   FROM profiles
  WHERE ((profiles.id = auth.uid()) AND (profiles.role = 'admin'::user_role))))
```

#### Política 2: Clients Read Service Documents
- **Policy Name**: `clients_read_service_documents`
- **Allowed operation**: `SELECT`
- **Policy definition**:
```sql
(bucket_id = 'service-documents'::text) AND 
((storage.foldername(name))[1] IN ( SELECT so.id::text
   FROM (service_orders so
     JOIN clients c ON ((c.id = so.client_id)))
  WHERE (c.profile_id = auth.uid())))
```

---

## 3. Verificação

Após criar todas as políticas, teste:

### Teste 1: Verificar Políticas Criadas
```sql
SELECT 
    schemaname,
    tablename,
    policyname,
    permissive,
    roles,
    cmd
FROM pg_policies 
WHERE tablename = 'objects' 
AND schemaname = 'storage';
```

### Teste 2: Testar Upload via API
Use o endpoint do backend:
```bash
POST http://localhost:8000/api/v1/client/documents
Authorization: Bearer {client-token}
Content-Type: multipart/form-data

file: [seu-arquivo.pdf]
```

---

## 🎯 Resumo da Configuração

Para cada bucket, você precisa criar:

| Bucket | Políticas Necessárias |
|--------|----------------------|
| `client-documents` | 3 políticas (admin all, client read, client upload) |
| `lot-documents` | 2 políticas (admin all, client read) |
| `development-documents` | 2 políticas (admin all, authenticated read) |
| `service-documents` | 2 políticas (admin all, client read) |

**Total**: 9 políticas RLS

---

## ⚠️ Troubleshooting

### Erro: "new row violates row-level security policy"
1. Verifique se todas as políticas foram criadas
2. Confirme que o usuário está autenticado
3. Para testes de admin, verifique se o role está correto:
```sql
SELECT id, role FROM profiles WHERE id = auth.uid();
```

### Erro: "Policy already exists"
- Ignore, a política já foi criada anteriormente
- Ou delete a política existente e recrie

### Política não está funcionando
1. Verifique a sintaxe SQL da política
2. Teste a query isoladamente no SQL Editor
3. Confirme que as tabelas referenciadas existem (profiles, clients, etc.)

---

## 📝 Notas Importantes

1. **Ordem de criação**: Crie os buckets ANTES das políticas
2. **Nomenclatura**: Use exatamente os nomes especificados
3. **Operações**: Marque apenas as operações necessárias para cada política
4. **Testes**: Sempre teste após criar cada política
5. **Segurança**: Nunca crie políticas que retornam `true` para todos (exceto para admin)
