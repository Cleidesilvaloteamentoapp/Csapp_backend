# CSApp Backend – Sistema de Gestão Imobiliária Multi-Tenant

API REST construída com **FastAPI** para gestão de loteamentos, com arquitetura multi-tenant, integração com Asaas (pagamentos) e Supabase (auth + storage).

## Stack

- **FastAPI** 0.104+ / **Python** 3.11+
- **SQLAlchemy** 2.0 (async) + **Alembic** (migrations)
- **Supabase** (PostgreSQL, Auth, Storage)
- **Celery** + **Redis** (tarefas assíncronas)
- **Pydantic** v2 (validação)
- **Docker** (containerização)

## Configuração Local

### 1. Clone e variáveis de ambiente

```bash
cp .env.example .env
# Edite .env com suas credenciais (Supabase, Asaas, Redis, etc.)
```

### 2. Virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Banco de dados e migrations

```bash
# Certifique-se que DATABASE_URL aponta para seu PostgreSQL
alembic revision --autogenerate -m "initial"
alembic upgrade head

# Aplique as políticas RLS (requer acesso admin ao Supabase)
psql $DATABASE_URL -f sql/001_rls_policies.sql
```

### 4. Executar servidor

```bash
uvicorn app.main:app --reload --port 8000
```

### 5. Celery (em outro terminal)

```bash
celery -A app.tasks.celery_app worker --loglevel=info
celery -A app.tasks.celery_app beat --loglevel=info
```

## Docker

```bash
docker-compose up --build
```

Serviços: `app` (8000), `redis` (6379), `celery-worker`, `celery-beat`.

## Testes

```bash
# Crie o banco de teste antes
createdb csapp_test

pytest -v --cov=app
```

## Documentação da API

Com o servidor rodando, acesse:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Estrutura

```
backend/
├── app/
│   ├── core/           # config, database, security, deps, tenant
│   ├── models/         # SQLAlchemy models
│   ├── schemas/        # Pydantic v2 schemas
│   ├── api/v1/         # Rotas (auth, companies, admin/*, client/*, webhooks)
│   ├── services/       # Lógica de negócio (auth, client, asaas, storage, email, whatsapp)
│   ├── tasks/          # Celery tasks (invoice, notification)
│   ├── utils/          # Exceptions, logging
│   └── main.py         # Entry point
├── alembic/            # Migrations
├── sql/                # RLS policies
├── tests/              # Pytest
├── Dockerfile
└── requirements.txt
```

## Roles

| Role | Acesso |
|------|--------|
| `super_admin` | Gerencia todas as empresas |
| `company_admin` | CRUD completo na própria empresa |
| `client` | Acesso somente aos próprios dados |

## Endpoints Principais

| Prefixo | Descrição |
|---------|-----------|
| `/api/v1/auth` | Signup, login, logout, me, refresh |
| `/api/v1/companies` | CRUD de empresas (super_admin) |
| `/api/v1/admin/dashboard` | Estatísticas e gráficos |
| `/api/v1/admin/clients` | Gestão de clientes |
| `/api/v1/admin/lots` | Lotes e empreendimentos |
| `/api/v1/admin/financial` | Financeiro e inadimplentes |
| `/api/v1/admin/services` | Tipos de serviço e OS |
| `/api/v1/client/dashboard` | Portal do cliente |
| `/api/v1/client/invoices` | Boletos |
| `/api/v1/client/services` | Solicitação de serviços |
| `/api/v1/client/documents` | Upload de documentos |
| `/api/v1/client/referrals` | Indicações |
| `/api/v1/webhooks/asaas` | Webhook de pagamentos |
