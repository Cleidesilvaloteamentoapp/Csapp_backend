# Guia de Configuração - Sistema de Gestão Imobiliária

## 📋 Ordem de Execução das Migrations

### ⚠️ IMPORTANTE: Siga esta ordem exatamente

1. ✅ **001_create_tables.sql** - Cria todas as tabelas
2. ✅ **002_row_level_security.sql** - Configura RLS (segurança crítica)
3. ⚠️ **003_storage_buckets.sql** - **REQUER CONFIGURAÇÃO MANUAL**
4. ✅ **004_seed_data.sql** - Dados de exemplo (opcional, apenas dev)

---

## 🔧 Passo a Passo Completo

### 1. Configure o Projeto Supabase

1. Acesse https://app.supabase.com
2. Crie um novo projeto
3. Aguarde a criação do banco de dados

### 2. Execute as Migrations SQL

No **SQL Editor** do Supabase, execute na ordem:

#### Migration 001 - Criar Tabelas
```bash
# Copie e cole todo o conteúdo de migrations/001_create_tables.sql
```

Resultado esperado: ✅ Todas as tabelas criadas

#### Migration 002 - Row Level Security
```bash
# Copie e cole todo o conteúdo de migrations/002_row_level_security.sql
```

Resultado esperado: ✅ Políticas RLS criadas

### 3. Configure Storage Buckets (MANUAL)

⚠️ **ATENÇÃO: Storage buckets e suas políticas RLS devem ser configurados via Dashboard, NÃO via SQL!**

#### 3.1. Criar Buckets no Dashboard

1. No Supabase Dashboard, vá em **Storage** (menu lateral)
2. Clique em **New Bucket**
3. Crie os seguintes buckets:

| Nome | Público | Tamanho Máx | MIME Types Permitidos |
|------|---------|-------------|----------------------|
| `client-documents` | ❌ Não | 10 MB | PDF, JPG, PNG, DOC, DOCX |
| `lot-documents` | ❌ Não | 10 MB | PDF, JPG, PNG, DOC, DOCX |
| `development-documents` | ❌ Não | 10 MB | PDF, JPG, PNG |
| `service-documents` | ❌ Não | 10 MB | PDF, JPG, PNG |

**Detalhes dos MIME types:**
```
application/pdf
image/jpeg
image/png
image/jpg
application/msword
application/vnd.openxmlformats-officedocument.wordprocessingml.document
```

#### 3.2. Configurar Políticas RLS dos Buckets

⚠️ **As políticas RLS de storage também devem ser criadas via Dashboard!**

**Siga o guia detalhado**: `migrations/003_storage_policies_DASHBOARD.md`

Para cada bucket, você precisa:
1. Clicar no bucket
2. Ir na aba **Policies**
3. Criar as políticas manualmente usando as definições SQL do guia

**Total de políticas a criar**: 9 políticas (distribuídas entre os 4 buckets)

Resultado esperado: ✅ Todas as políticas RLS de storage criadas via Dashboard

### 4. (Opcional) Dados de Exemplo

Para ambiente de desenvolvimento:
```bash
# Copie e cole todo o conteúdo de migrations/004_seed_data.sql
```

Resultado esperado: ✅ Empreendimento e lotes de exemplo criados

### 5. Configure as Variáveis de Ambiente

```bash
cp .env.example .env
```

Edite o arquivo `.env` com suas credenciais:

```env
# Supabase (obtenha no Dashboard > Settings > API)
SUPABASE_URL=https://seu-projeto.supabase.co
SUPABASE_ANON_KEY=sua-anon-key-aqui
SUPABASE_SERVICE_ROLE_KEY=sua-service-role-key-aqui

# Asaas (obtenha em https://www.asaas.com)
ASAAS_API_KEY=sua-asaas-api-key
ASAAS_ENVIRONMENT=sandbox  # ou production

# Email (opcional para Fase 1)
EMAIL_PROVIDER_API_KEY=
EMAIL_FROM_ADDRESS=noreply@seudominio.com

# WhatsApp (opcional para Fase 1)
WHATSAPP_API_KEY=
WHATSAPP_PHONE_NUMBER_ID=

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

### 6. Instale as Dependências

```bash
# Criar ambiente virtual
python -m venv venv

# Ativar ambiente virtual
source venv/bin/activate  # Linux/Mac
# ou
.\venv\Scripts\activate  # Windows

# Instalar dependências
pip install -r requirements.txt
```

### 7. Execute a Aplicação

```bash
# Desenvolvimento (com reload automático)
uvicorn app.main:app --reload --port 8000

# Produção
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 8. Acesse a Documentação

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

---

## 🔐 Criar Primeiro Usuário Admin

### Opção 1: Via Supabase Dashboard

1. Vá em **Authentication** > **Users**
2. Clique em **Add User**
3. Preencha:
   - Email: `admin@seudominio.com`
   - Password: `SenhaSegura123!`
   - Auto Confirm User: ✅ Marque
4. Após criar, vá no **SQL Editor** e execute:

```sql
-- Atualizar o usuário para admin
UPDATE profiles 
SET role = 'admin', 
    full_name = 'Administrador',
    cpf_cnpj = '00000000000',
    phone = '11999999999'
WHERE id = 'UUID-DO-USUARIO-CRIADO';
```

### Opção 2: Via API (requer admin existente)

```bash
POST http://localhost:8000/api/v1/auth/signup
Authorization: Bearer {admin-token}
Content-Type: application/json

{
  "email": "novoadmin@exemplo.com",
  "password": "SenhaSegura123!",
  "full_name": "Novo Admin",
  "cpf_cnpj": "12345678901",
  "phone": "11999999999",
  "role": "admin"
}
```

---

## 🧪 Testar a API

### 1. Login
```bash
POST http://localhost:8000/api/v1/auth/login
Content-Type: application/json

{
  "email": "admin@seudominio.com",
  "password": "SenhaSegura123!"
}
```

Resposta:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "...",
  "token_type": "bearer",
  "user": {...}
}
```

### 2. Usar o Token

Adicione o header em todas as requisições:
```
Authorization: Bearer eyJ...seu-token-aqui
```

### 3. Testar Dashboard Admin
```bash
GET http://localhost:8000/api/v1/admin/dashboard/stats
Authorization: Bearer {seu-token}
```

---

## ⚠️ Troubleshooting

### Erro: "permission denied for schema storage"
- **Causa**: Tentou criar buckets via SQL
- **Solução**: Crie os buckets manualmente no Dashboard (veja seção 3)

### Erro: "relation does not exist"
- **Causa**: Migrations não foram executadas
- **Solução**: Execute migrations 001 e 002 na ordem

### Erro: "new row violates row-level security policy"
- **Causa**: RLS não configurado ou usuário sem permissão
- **Solução**: Execute migration 002 e verifique role do usuário

### Erro: "Invalid or expired token"
- **Causa**: Token JWT inválido ou expirado
- **Solução**: Faça login novamente para obter novo token

### Erro ao criar cliente: "Failed to create Asaas customer"
- **Causa**: API Key do Asaas inválida ou ambiente incorreto
- **Solução**: Verifique `ASAAS_API_KEY` e `ASAAS_ENVIRONMENT` no `.env`

---

## 📚 Próximos Passos

1. ✅ Configure o Supabase e execute migrations
2. ✅ Crie buckets de storage manualmente
3. ✅ Configure variáveis de ambiente
4. ✅ Crie primeiro usuário admin
5. ✅ Teste a API via Swagger
6. 🔄 Integre com frontend
7. 🔄 Configure webhooks do Asaas
8. 🔄 Implemente Fase 2 (notificações, cron jobs)

---

## 📞 Suporte

Para dúvidas ou problemas:
1. Verifique os logs da aplicação
2. Consulte a documentação do Supabase
3. Revise as políticas RLS no Dashboard
4. Teste endpoints no Swagger UI
