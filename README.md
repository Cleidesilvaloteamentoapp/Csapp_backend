# Sistema de Gestão Imobiliária - Backend API

API RESTful para sistema de gestão imobiliária multi-tenant, desenvolvida com FastAPI e Supabase.

## 📋 Funcionalidades

### Fase 1 (MVP) - Implementado
- ✅ Autenticação e autorização com Supabase Auth
- ✅ CRUD completo de clientes
- ✅ CRUD de empreendimentos e lotes
- ✅ Vinculação de lotes a clientes com planos de pagamento
- ✅ Integração com Asaas para geração de boletos
- ✅ Dashboard administrativo com estatísticas
- ✅ Dashboard do cliente
- ✅ Row Level Security (RLS) para isolamento de dados

### Fase 2 (Planejado)
- ⏳ Ordens de serviço completas
- ⏳ Sistema de notificações (Email/WhatsApp)
- ⏳ Upload de documentos
- ⏳ Cron jobs para inadimplência

### Fase 3 (Planejado)
- ⏳ Sistema de indicações
- ⏳ Relatórios avançados
- ⏳ Otimizações

## 🛠️ Stack Tecnológica

- **Framework**: FastAPI
- **Banco de Dados**: Supabase (PostgreSQL)
- **Autenticação**: Supabase Auth + JWT
- **Pagamentos**: Asaas API
- **Validação**: Pydantic v2

## 📁 Estrutura do Projeto

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # Aplicação FastAPI
│   ├── database.py          # Conexão Supabase
│   ├── core/
│   │   ├── config.py        # Configurações
│   │   └── security.py      # Funções de segurança
│   ├── models/
│   │   └── enums.py         # Enums do sistema
│   ├── schemas/
│   │   ├── auth.py          # Schemas de autenticação
│   │   ├── client.py        # Schemas de clientes
│   │   ├── lot.py           # Schemas de lotes
│   │   ├── invoice.py       # Schemas de faturas
│   │   ├── service.py       # Schemas de serviços
│   │   └── dashboard.py     # Schemas de dashboard
│   ├── api/
│   │   ├── deps.py          # Dependências da API
│   │   └── routes/
│   │       ├── auth.py      # Rotas de autenticação
│   │       ├── admin.py     # Rotas administrativas
│   │       ├── client.py    # Rotas do cliente
│   │       └── webhooks.py  # Webhooks (Asaas)
│   ├── services/
│   │   ├── asaas.py         # Integração Asaas
│   │   ├── storage.py       # Upload de arquivos
│   │   └── notification.py  # Email/WhatsApp
│   └── utils/
│       └── helpers.py       # Funções auxiliares
├── migrations/
│   ├── 001_create_tables.sql
│   ├── 002_row_level_security.sql
│   ├── 003_storage_buckets.sql
│   └── 004_seed_data.sql
├── requirements.txt
├── .env.example
└── README.md
```

## 🚀 Instalação

### 1. Clone o repositório

```bash
git clone <repository-url>
cd Csapp_backend
```

### 2. Crie e ative o ambiente virtual

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
.\venv\Scripts\activate  # Windows
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

### 4. Configure as variáveis de ambiente

```bash
cp .env.example .env
# Edite o arquivo .env com suas credenciais
```

### 5. Configure o Supabase

1. Crie um projeto no [Supabase](https://supabase.com)
2. Execute as migrations na ordem:
   ```
   migrations/001_create_tables.sql
   migrations/002_row_level_security.sql
   migrations/003_storage_buckets.sql
   migrations/004_seed_data.sql (opcional, apenas dev)
   ```
3. Copie as credenciais para o `.env`

### 6. Configure o Asaas

1. Crie uma conta no [Asaas](https://www.asaas.com)
2. Gere uma API Key no painel
3. Configure o webhook para receber notificações de pagamento

### 7. Execute a aplicação

```bash
# Desenvolvimento
uvicorn app.main:app --reload --port 8000

# Produção
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 📚 Documentação da API

Com a aplicação rodando, acesse:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 🔐 Autenticação

A API utiliza JWT via Supabase Auth. Para autenticar:

1. Faça login via `POST /api/v1/auth/login`
2. Use o `access_token` retornado no header `Authorization: Bearer <token>`

### Roles

- **admin**: Acesso total ao sistema
- **client**: Acesso apenas aos próprios dados

## 📌 Endpoints Principais

### Autenticação
| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/api/v1/auth/login` | Login |
| POST | `/api/v1/auth/signup` | Criar usuário (admin only) |
| POST | `/api/v1/auth/logout` | Logout |
| GET | `/api/v1/auth/me` | Dados do usuário |

### Admin
| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/api/v1/admin/dashboard/stats` | Estatísticas |
| GET | `/api/v1/admin/dashboard/financial` | Análise financeira |
| GET | `/api/v1/admin/clients` | Listar clientes |
| POST | `/api/v1/admin/clients` | Criar cliente |
| GET | `/api/v1/admin/developments` | Listar empreendimentos |
| POST | `/api/v1/admin/developments` | Criar empreendimento |
| GET | `/api/v1/admin/lots` | Listar lotes |
| POST | `/api/v1/admin/lots` | Criar lote |
| POST | `/api/v1/admin/client-lots` | Vincular lote ao cliente |

### Cliente
| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/api/v1/client/dashboard` | Dashboard do cliente |
| GET | `/api/v1/client/invoices` | Listar boletos |
| GET | `/api/v1/client/lots` | Listar lotes |
| POST | `/api/v1/client/service-orders` | Solicitar serviço |
| POST | `/api/v1/client/referrals` | Cadastrar indicação |

### Webhooks
| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/api/v1/webhooks/asaas` | Webhook de pagamentos Asaas |

## 🔒 Segurança

### Row Level Security (RLS)

O sistema implementa RLS rigoroso no Supabase:

- **Admin**: Acesso total a todos os dados
- **Cliente**: Acesso apenas aos próprios dados
- **Isolamento**: Dados são isolados por cliente

### Boas Práticas Implementadas

- ✅ Validação de entrada com Pydantic
- ✅ Sanitização de dados
- ✅ JWT para autenticação
- ✅ RLS para isolamento de dados
- ✅ Variáveis de ambiente para secrets
- ✅ CORS configurável
- ✅ Rate limiting (a implementar)

## 🧪 Testes

```bash
# Instalar dependências de teste
pip install pytest pytest-asyncio httpx

# Executar testes
pytest tests/ -v
```

## 📝 Variáveis de Ambiente

| Variável | Descrição | Obrigatório |
|----------|-----------|-------------|
| `SUPABASE_URL` | URL do projeto Supabase | Sim |
| `SUPABASE_ANON_KEY` | Chave anônima do Supabase | Sim |
| `SUPABASE_SERVICE_ROLE_KEY` | Chave de serviço (admin) | Sim |
| `ASAAS_API_KEY` | API Key do Asaas | Sim |
| `ASAAS_ENVIRONMENT` | `sandbox` ou `production` | Sim |
| `EMAIL_PROVIDER_API_KEY` | API Key do provedor de email | Não |
| `WHATSAPP_API_KEY` | API Key do WhatsApp Business | Não |
| `CORS_ORIGINS` | Origens permitidas (separadas por vírgula) | Não |

## 🤝 Contribuição

1. Fork o projeto
2. Crie uma branch (`git checkout -b feature/nova-feature`)
3. Commit suas mudanças (`git commit -m 'Add nova feature'`)
4. Push para a branch (`git push origin feature/nova-feature`)
5. Abra um Pull Request

## 📄 Licença

Este projeto está sob a licença MIT.
