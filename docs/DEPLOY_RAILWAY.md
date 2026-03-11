# Deploy no Railway – CSApp Backend

Guia completo para deploy da API FastAPI + Redis + Celery Worker + Celery Beat no Railway.

---

## Arquitetura no Railway

```
┌─────────────┐   ┌─────────────┐   ┌──────────────┐   ┌─────────────┐
│   API Web   │   │   Redis     │   │ Celery       │   │ Celery      │
│  (FastAPI)  │◄──│  (Plugin)   │──►│ Worker       │   │ Beat        │
│  Port $PORT │   │  Port 6379  │   │              │   │             │
└─────────────┘   └─────────────┘   └──────────────┘   └─────────────┘
       │                                    │                  │
       └──────────┬─────────────────────────┘                  │
                  ▼                                            │
        ┌─────────────────┐                                    │
        │  Supabase       │◄───────────────────────────────────┘
        │  (PostgreSQL +  │
        │   Storage)      │
        └─────────────────┘
```

## Passo a Passo

### 1. Criar Projeto no Railway

1. Acesse [railway.app](https://railway.app) e faça login
2. Clique em **"New Project"** → **"Deploy from GitHub Repo"**
3. Selecione o repositório `Csapp_backend`

### 2. Provisionar Redis

1. No projeto, clique em **"+ New"** → **"Database"** → **"Add Redis"**
2. O Railway criará automaticamente a variável `REDIS_URL`
3. Copie o valor de `REDIS_URL` (formato: `redis://default:password@host:port`)

### 3. Configurar Serviço API (Web)

**Settings:**
- **Builder**: Dockerfile
- **Dockerfile Path**: `backend/Dockerfile`
- **Start Command**: (deixar vazio, usa o CMD do Dockerfile)

⚠️ **IMPORTANTE**: Configure TODAS as variáveis abaixo ANTES de fazer o primeiro deploy. O container vai falhar no healthcheck se variáveis obrigatórias estiverem faltando.

**Variables (obrigatórias):**

```env
# App
APP_ENV=production
DEBUG=false
SECRET_KEY=<gerar-com-openssl-rand-hex-32>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Supabase
SUPABASE_URL=https://seu-projeto.supabase.co
SUPABASE_PUBLISHABLE_KEY=eyJ...
SUPABASE_SECRET_KEY=eyJ...(service_role)
SUPABASE_JWT_SECRET={"x":"...","y":"...","alg":"ES256",...}
SUPABASE_STORAGE_BUCKET=documents

# Database (Supabase PostgreSQL)
DATABASE_URL=postgresql+asyncpg://postgres:senha@host:5432/postgres

# Redis (usar referência interna do Railway)
REDIS_URL=${{Redis.REDIS_URL}}

# CORS (domínios do frontend)
CORS_ORIGINS=["https://seu-frontend.vercel.app","https://seu-dominio.com.br"]

# Security
ALLOWED_HOSTS=["seu-app.up.railway.app","api.seu-dominio.com.br"]
RATE_LIMIT_PER_MINUTE=60
AUTH_RATE_LIMIT=5/minute

# Asaas
ASAAS_API_KEY=sua-chave-asaas
ASAAS_ENVIRONMENT=production
ASAAS_BASE_URL=https://api.asaas.com/v3
ASAAS_WEBHOOK_TOKEN=token-configurado-no-painel-asaas

# Email
RESEND_API_KEY=re_xxx
SMTP_FROM_EMAIL=noreply@seu-dominio.com.br

# WhatsApp (opcional)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_WHATSAPP_NUMBER=

# Webhook IP Whitelist (opcional, IPs separados por vírgula)
WEBHOOK_IP_WHITELIST=
```

### 4. Configurar Celery Worker

1. No projeto, clique em **"+ New"** → **"Service"** → **"GitHub Repo"**
2. Selecione o mesmo repositório

**Settings:**
- **Root Directory**: `backend`
- **Builder**: Dockerfile
- **Start Command**: `celery -A app.tasks.celery_app worker --loglevel=info --concurrency=2`

**Variables:** Mesmas do serviço API (pode usar "Shared Variables" do Railway)

### 5. Configurar Celery Beat

1. Repita o passo 4 para criar outro serviço

**Settings:**
- **Root Directory**: `backend`
- **Builder**: Dockerfile
- **Start Command**: `celery -A app.tasks.celery_app beat --loglevel=info`

**Variables:** Mesmas do serviço API

### 6. Domínio Customizado (Opcional)

1. No serviço API, vá em **Settings** → **Networking**
2. Clique em **"Generate Domain"** para obter `*.up.railway.app`
3. Ou clique em **"Custom Domain"** e configure:
   - Adicione `api.seu-dominio.com.br`
   - Configure o DNS com CNAME apontando para o Railway

---

## Gerar SECRET_KEY Segura

```bash
openssl rand -hex 32
```

Use o output como valor de `SECRET_KEY`.

---

## Checklist Pré-Deploy

- [ ] `APP_ENV=production` (desabilita Swagger/docs)
- [ ] `DEBUG=false` (desabilita SQL echo)
- [ ] `SECRET_KEY` com pelo menos 32 caracteres aleatórios
- [ ] `CORS_ORIGINS` restrito aos domínios do frontend
- [ ] `ALLOWED_HOSTS` configurado com os domínios permitidos
- [ ] `ASAAS_WEBHOOK_TOKEN` configurado (se usando Asaas)
- [ ] Bucket `documents` criado no Supabase Storage
- [ ] RLS ativo em todas as tabelas (executar scripts SQL)
- [ ] Migrations executadas no banco de produção

---

## Executar Migrations no Banco de Produção

Opção 1 – Via SQL Editor do Supabase:
- Execute os arquivos em `sql/` na ordem:
  1. `001_rls_policies.sql`
  2. `003_sicredi_rls.sql`
  3. `004_boletos_rls.sql`
  4. `005_create_boletos_table.sql`
  5. `007_new_tables_rls.sql`
  6. `008_batch_operations.sql`
  7. `009_client_portal_rls.sql`
  8. `010_client_portal_tables.sql`

Opção 2 – Via Railway CLI:
```bash
railway run alembic upgrade head
```

---

## Monitoramento

- **Logs**: Railway Dashboard → Serviço → Logs
- **Health Check**: `GET /health` retorna `{"status": "ok"}`
- **Métricas**: Railway Dashboard → Serviço → Metrics (CPU, RAM, Network)

---

## Troubleshooting

| Problema | Solução |
|----------|---------|
| `502 Bad Gateway` | Verificar se `PORT` está sendo usado pelo uvicorn |
| `CORS error` | Adicionar domínio do frontend em `CORS_ORIGINS` |
| `Invalid API key` (Storage) | Verificar `SUPABASE_SECRET_KEY` (deve ser service_role) |
| Celery não processa | Verificar `REDIS_URL` com referência interna `${{Redis.REDIS_URL}}` |
| `Trusted host` error | Adicionar domínio em `ALLOWED_HOSTS` |
