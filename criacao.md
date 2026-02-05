# Prompt para Implementação do Backend - Sistema de Gestão Imobiliária Multi-Tenant

## Visão Geral do Projeto

Você deve implementar o backend completo de um sistema de gestão imobiliária especializado em loteamentos. O sistema possui **arquitetura multi-tenant em dois níveis**:

1. **Nível Empresa**: Diferentes empresas imobiliárias usando o sistema
2. **Nível Cliente**: Clientes finais de cada empresa

O backend será uma **API REST** construída com **FastAPI** que será consumida por um frontend PWA separado.

## Requisitos de Arquitetura

### Multi-Tenancy

- Implementar **isolamento total de dados entre empresas** usando `company_id` como tenant key
- **TODAS as tabelas** (exceto `companies` e `auth.users`) devem ter `company_id` como chave estrangeira
- Criar middleware de contexto de tenant que:
  - Identifica a empresa do usuário autenticado
  - Aplica filtros automáticos em todas as queries
  - Permite super_admin acessar todas as empresas
  - Bloqueia acesso entre empresas diferentes para outros roles
- Implementar Row Level Security (RLS) no Supabase para garantia adicional de isolamento

### Sistema de Roles e Permissões

Implementar **3 níveis de acesso**:

1. **super_admin**: 
   - Gerencia múltiplas empresas
   - Cria e configura empresas
   - Acesso total ao sistema

2. **company_admin**:
   - Gerencia apenas sua empresa
   - CRUD completo de clientes, lotes, serviços
   - Visualiza dashboards e relatórios
   - Não pode acessar outras empresas

3. **client**:
   - Acesso apenas aos próprios dados
   - Visualiza boletos, lotes, documentos
   - Solicita serviços
   - Faz indicações

### Segurança

- Utilizar **Supabase Auth** com as **novas API keys** (formato `sb_publishable_...` e `sb_secret_...`)
- Suportar JWT no **novo formato ES256** do Supabase
- Implementar autenticação dupla:
  - Tokens internos (HS256) para operações do sistema
  - Tokens Supabase (ES256) para integração com frontend
- Aplicar validações rigorosas com **Pydantic v2**
- Implementar **rate limiting** em endpoints sensíveis
- Sanitizar inputs para prevenir SQL injection e XSS
- Criptografar senhas com **bcrypt**

## Stack Tecnológica Obrigatória

### Core
- **FastAPI** 0.104+ (framework web)
- **Python** 3.11+
- **Supabase** (PostgreSQL + Auth + Storage)
- **SQLAlchemy** 2.0 (ORM)
- **Alembic** (migrations)
- **Pydantic** v2 (validação)

### Integrações Externas
- **Asaas API** (gateway de pagamento para boletos)
- **Supabase Storage** (armazenamento de arquivos)
- **Resend** ou **SendGrid** (envio de emails)
- **Twilio** ou **Evolution API** (WhatsApp)

### Infraestrutura
- **Celery** (tarefas assíncronas)
- **Redis** (broker do Celery e cache)
- **Docker** (containerização)

## Estrutura de Diretórios Requerida

```
backend/
├── app/
│   ├── core/                # Configurações centrais
│   │   ├── config.py       # Settings com Pydantic
│   │   ├── database.py     # Conexão Supabase/SQLAlchemy
│   │   ├── security.py     # JWT, hashing, permissões
│   │   ├── deps.py         # Dependencies FastAPI
│   │   └── tenant.py       # Middleware multi-tenant
│   │
│   ├── models/             # SQLAlchemy models
│   │   ├── company.py
│   │   ├── user.py
│   │   ├── client.py
│   │   ├── lot.py
│   │   ├── development.py
│   │   ├── invoice.py
│   │   ├── service.py
│   │   └── referral.py
│   │
│   ├── schemas/            # Pydantic schemas
│   │   └── [mesmo padrão de models]
│   │
│   ├── api/v1/            # Rotas da API
│   │   ├── auth.py
│   │   ├── companies.py   # Super admin only
│   │   ├── admin/         # Company admin routes
│   │   │   ├── dashboard.py
│   │   │   ├── clients.py
│   │   │   ├── lots.py
│   │   │   ├── financial.py
│   │   │   └── services.py
│   │   └── client/        # Client routes
│   │       ├── dashboard.py
│   │       ├── invoices.py
│   │       ├── services.py
│   │       └── documents.py
│   │
│   ├── services/          # Lógica de negócio
│   │   ├── auth_service.py
│   │   ├── client_service.py
│   │   ├── asaas_service.py
│   │   ├── storage_service.py
│   │   ├── email_service.py
│   │   └── whatsapp_service.py
│   │
│   └── tasks/             # Celery tasks
│       ├── invoice_tasks.py
│       └── notification_tasks.py
│
├── alembic/               # Database migrations
├── tests/                 # Testes
└── requirements.txt
```

## Modelos de Dados Obrigatórios

### Tabela: companies
**Propósito**: Armazena empresas que usam o sistema

Campos obrigatórios:
- `id` (UUID, PK)
- `name` (string, nome da empresa)
- `slug` (string, unique, URL-friendly)
- `settings` (JSONB, configurações customizadas)
- `status` (enum: active, suspended, inactive)
- `created_at`, `updated_at` (timestamps)

### Tabela: profiles
**Propósito**: Estende auth.users do Supabase com dados adicionais

Campos obrigatórios:
- `id` (UUID, PK, FK para auth.users)
- `company_id` (UUID, FK para companies) **← TENANT KEY**
- `role` (enum: super_admin, company_admin, client)
- `full_name` (string)
- `cpf_cnpj` (string, unique)
- `phone` (string)
- `created_at`, `updated_at`

### Tabela: clients
**Propósito**: Dados completos dos clientes finais

Campos obrigatórios:
- `id` (UUID, PK)
- `company_id` (UUID, FK) **← TENANT KEY**
- `profile_id` (UUID, FK para profiles, nullable)
- `email` (string)
- `full_name` (string)
- `cpf_cnpj` (string)
- `phone` (string)
- `address` (JSONB)
- `documents` (JSONB array de URLs)
- `status` (enum: active, inactive, defaulter)
- `asaas_customer_id` (string, integração)
- `created_by` (UUID, FK para profiles)
- `created_at`, `updated_at`

### Tabela: developments
**Propósito**: Empreendimentos/loteamentos

Campos obrigatórios:
- `id` (UUID, PK)
- `company_id` (UUID, FK) **← TENANT KEY**
- `name` (string)
- `description` (text)
- `location` (string)
- `documents` (JSONB)
- `created_at`, `updated_at`

### Tabela: lots
**Propósito**: Lotes individuais dentro de empreendimentos

Campos obrigatórios:
- `id` (UUID, PK)
- `company_id` (UUID, FK) **← TENANT KEY**
- `development_id` (UUID, FK para developments)
- `lot_number` (string)
- `block` (string, nullable)
- `area_m2` (numeric)
- `price` (numeric)
- `status` (enum: available, reserved, sold)
- `documents` (JSONB)
- `created_at`, `updated_at`

### Tabela: client_lots
**Propósito**: Relacionamento entre clientes e lotes (compras)

Campos obrigatórios:
- `id` (UUID, PK)
- `company_id` (UUID, FK) **← TENANT KEY**
- `client_id` (UUID, FK)
- `lot_id` (UUID, FK)
- `purchase_date` (date)
- `total_value` (numeric)
- `payment_plan` (JSONB com detalhes do parcelamento)
- `status` (enum: active, completed, cancelled)
- `created_at`, `updated_at`

### Tabela: invoices
**Propósito**: Boletos/faturas de pagamento

Campos obrigatórios:
- `id` (UUID, PK)
- `company_id` (UUID, FK) **← TENANT KEY**
- `client_lot_id` (UUID, FK)
- `due_date` (date)
- `amount` (numeric)
- `installment_number` (integer)
- `status` (enum: pending, paid, overdue, cancelled)
- `asaas_payment_id` (string)
- `barcode` (string)
- `payment_url` (string)
- `paid_at` (timestamp, nullable)
- `created_at`, `updated_at`

### Tabela: service_types
**Propósito**: Tipos de serviços oferecidos

Campos obrigatórios:
- `id` (UUID, PK)
- `company_id` (UUID, FK) **← TENANT KEY**
- `name` (string)
- `description` (text)
- `base_price` (numeric)
- `is_active` (boolean)
- `created_at`, `updated_at`

### Tabela: service_orders
**Propósito**: Ordens de serviço solicitadas

Campos obrigatórios:
- `id` (UUID, PK)
- `company_id` (UUID, FK) **← TENANT KEY**
- `client_id` (UUID, FK)
- `lot_id` (UUID, FK, nullable)
- `service_type_id` (UUID, FK)
- `requested_date` (date)
- `execution_date` (date, nullable)
- `status` (enum: requested, approved, in_progress, completed, cancelled)
- `cost` (numeric, custo da empresa)
- `revenue` (numeric, valor cobrado do cliente)
- `notes` (text)
- `created_at`, `updated_at`

### Tabela: referrals
**Propósito**: Sistema de indicações

Campos obrigatórios:
- `id` (UUID, PK)
- `company_id` (UUID, FK) **← TENANT KEY**
- `referrer_client_id` (UUID, FK para clients)
- `referred_name` (string)
- `referred_phone` (string)
- `referred_email` (string, nullable)
- `status` (enum: pending, contacted, converted, lost)
- `created_at`, `updated_at`

## Implementação de Row Level Security (RLS)

Para **CADA TABELA** (exceto `companies`), você deve criar policies no Supabase:

### Policy 1: super_admin - acesso total
```sql
-- Super admin vê e manipula tudo
CREATE POLICY "super_admin_all_access"
ON table_name
FOR ALL
USING (
  EXISTS (
    SELECT 1 FROM profiles
    WHERE profiles.id = auth.uid()
    AND profiles.role = 'super_admin'
  )
);
```

### Policy 2: company_admin e client - apenas da própria empresa
```sql
-- Usuários veem apenas dados da própria empresa
CREATE POLICY "company_isolation"
ON table_name
FOR ALL
USING (
  company_id IN (
    SELECT company_id FROM profiles
    WHERE profiles.id = auth.uid()
  )
);
```

### Policy 3: client - apenas próprios dados
Para tabelas específicas de cliente (como `invoices`):
```sql
-- Clientes veem apenas seus próprios dados
CREATE POLICY "client_own_data"
ON invoices
FOR SELECT
USING (
  EXISTS (
    SELECT 1 FROM client_lots cl
    JOIN clients c ON c.id = cl.client_id
    WHERE cl.id = invoices.client_lot_id
    AND c.profile_id = auth.uid()
  )
);
```

## Autenticação com Novas API Keys do Supabase

### Configuração
- Use `SUPABASE_PUBLISHABLE_KEY` (formato `sb_publishable_...`) para operações client-side
- Use `SUPABASE_SECRET_KEY` (formato `sb_secret_...`) para operações server-side
- Configure suporte para JWT ES256 (novo formato com curvas elípticas)

### Formato do JWT Secret (ES256)
```json
{
  "x": "RE8hlSuSU3bwUzGaXouDx1L1RxMEqiAlgxewv1YTzaI",
  "y": "5ldndPRNz5UzWHbXIrp2HF3RseZaFGnCEFRGZuNKPR8",
  "alg": "ES256",
  "crv": "P-256",
  "ext": true,
  "kid": "9ded7aa3-8552-4722-9f17-996140beeb67",
  "kty": "EC",
  "key_ops": ["verify"]
}
```

### Implementação Obrigatória
- Criar função para verificar tokens ES256 usando a biblioteca `python-jose`
- Suportar tanto tokens internos (HS256) quanto tokens Supabase (ES256)
- Extrair `user_id`, `company_id` e `role` do payload do token
- Implementar refresh token automático

## Endpoints da API Requeridos

### Autenticação (`/api/v1/auth`)
- `POST /signup` - Registrar empresa e super admin (público)
- `POST /login` - Login com email/senha
- `POST /logout` - Logout
- `GET /me` - Dados do usuário atual
- `POST /refresh` - Refresh token

### Super Admin - Empresas (`/api/v1/companies`)
- `GET /` - Listar empresas (paginado, com filtros)
- `POST /` - Criar nova empresa
- `GET /{id}` - Detalhes de empresa
- `PUT /{id}` - Atualizar empresa
- `PATCH /{id}/status` - Ativar/suspender empresa

### Admin - Dashboard (`/api/v1/admin/dashboard`)
- `GET /stats` - Estatísticas gerais (clientes ativos, inadimplentes, OS abertas/concluídas)
- `GET /financial-overview` - Visão financeira (contas a receber, recebido, em atraso)
- `GET /recent-activities` - Atividades recentes
- `GET /charts/revenue` - Dados para gráfico de receitas (últimos 6 meses)
- `GET /charts/services` - Serviços mais solicitados

### Admin - Clientes (`/api/v1/admin/clients`)
- `GET /` - Listar clientes (paginação, filtros: status, busca por nome/CPF)
- `POST /` - Criar cliente (+ criar customer no Asaas + opcionalmente criar acesso)
- `GET /{id}` - Detalhes do cliente
- `PUT /{id}` - Atualizar cliente
- `DELETE /{id}` - Desativar cliente
- `GET /{id}/lots` - Lotes do cliente
- `GET /{id}/invoices` - Faturas do cliente
- `GET /{id}/documents` - Documentos do cliente
- `POST /{id}/documents` - Upload documento

### Admin - Lotes (`/api/v1/admin/lots`)
- `GET /` - Listar lotes (filtros: empreendimento, status)
- `POST /` - Criar lote
- `GET /{id}` - Detalhes do lote
- `PUT /{id}` - Atualizar lote
- `POST /assign` - Vincular lote a cliente (criar client_lot + gerar boletos)

### Admin - Empreendimentos (`/api/v1/admin/developments`)
- `GET /` - Listar empreendimentos
- `POST /` - Criar empreendimento
- `GET /{id}` - Detalhes
- `PUT /{id}` - Atualizar

### Admin - Financeiro (`/api/v1/admin/financial`)
- `GET /summary` - Resumo financeiro
- `GET /receivables` - Contas a receber (filtros, paginação)
- `GET /defaulters` - Lista de inadimplentes (com tempo de atraso)
- `GET /revenue-by-services` - Receita por tipo de serviço

### Admin - Serviços (`/api/v1/admin/services`)
- `GET /types` - Listar tipos de serviço
- `POST /types` - Criar tipo de serviço
- `PUT /types/{id}` - Atualizar tipo
- `GET /orders` - Listar ordens de serviço (filtros: status, cliente, data)
- `GET /orders/{id}` - Detalhes da OS
- `PATCH /orders/{id}/status` - Atualizar status da OS
- `PATCH /orders/{id}/financial` - Atualizar custo/receita da OS
- `GET /analytics` - Análise custo vs receita

### Cliente - Dashboard (`/api/v1/client/dashboard`)
- `GET /summary` - Resumo (quantidade de lotes, próximo vencimento, status)
- `GET /my-lots` - Meus lotes
- `GET /recent-activity` - Atividades recentes

### Cliente - Lotes (`/api/v1/client/lots`)
- `GET /` - Meus lotes
- `GET /{id}` - Detalhes do lote
- `GET /{id}/documents` - Documentos do lote

### Cliente - Faturas (`/api/v1/client/invoices`)
- `GET /` - Listar boletos (filtro por lote)
- `GET /{id}` - Detalhes do boleto (com código de barras, URL pagamento)
- `GET /{id}/pdf` - Download PDF do boleto

### Cliente - Serviços (`/api/v1/client/services`)
- `GET /types` - Listar serviços disponíveis
- `POST /orders` - Solicitar serviço
- `GET /orders` - Minhas solicitações
- `GET /orders/{id}` - Status da solicitação

### Cliente - Documentos (`/api/v1/client/documents`)
- `GET /` - Meus documentos
- `POST /` - Upload documento
- `DELETE /{id}` - Remover documento

### Cliente - Indicações (`/api/v1/client/referrals`)
- `POST /` - Cadastrar indicação
- `GET /` - Minhas indicações

## Integração com Asaas (Pagamentos)

### Funcionalidades Obrigatórias

#### 1. Criar Customer ao cadastrar cliente
Quando criar um cliente, fazer chamada para:
```
POST https://sandbox.asaas.com/api/v3/customers
```
Armazenar `asaas_customer_id` no banco.

#### 2. Gerar Boletos
Ao vincular lote a cliente, criar boletos para cada parcela:
```
POST https://sandbox.asaas.com/api/v3/payments
```
Salvar `asaas_payment_id`, `barcode`, `payment_url`.

#### 3. Webhook para Status de Pagamento
Implementar endpoint:
```
POST /api/v1/webhooks/asaas
```
Processar eventos:
- `PAYMENT_RECEIVED` - Marcar fatura como paga
- `PAYMENT_OVERDUE` - Marcar como vencida
- `PAYMENT_CONFIRMED` - Confirmar pagamento

#### 4. Consultar Pagamentos em Atraso
Criar task Celery que diariamente:
- Consulta API Asaas por pagamentos vencidos
- Atualiza status no banco
- Identifica inadimplentes (3+ meses)

## Upload e Gestão de Arquivos (Supabase Storage)

### Implementação Requerida

#### 1. Criar Buckets no Supabase
- `documents` (documentos de clientes e lotes)
- `photos` (fotos de lotes, empreendimentos)

#### 2. Service de Storage
Criar `storage_service.py` com funções:
- `upload_file(file, bucket, folder)` - Upload com validação de tipo/tamanho
- `get_public_url(bucket, path)` - Obter URL pública
- `delete_file(bucket, path)` - Remover arquivo
- `list_files(bucket, folder)` - Listar arquivos

#### 3. Validações Obrigatórias
- Tipos permitidos: PDF, JPG, PNG, DOC, DOCX
- Tamanho máximo: 10MB por arquivo
- Sanitizar nomes de arquivo
- Gerar nomes únicos (UUID)

#### 4. Organização de Pastas
```
documents/
  ├── companies/{company_id}/
  │   ├── clients/{client_id}/
  │   │   ├── documents/
  │   │   └── photos/
  │   └── lots/{lot_id}/
  │       ├── documents/
  │       └── photos/
```

## Celery Tasks (Tarefas Assíncronas)

### Tasks Obrigatórias

#### 1. Verificação de Inadimplência (Diária)
```python
@celery.task
def check_overdue_invoices():
    """
    - Buscar faturas vencidas não pagas
    - Atualizar status para 'overdue'
    - Identificar clientes com 3+ meses de atraso
    - Marcar cliente como 'defaulter'
    - Criar notificação de alerta de rescisão
    """
```

#### 2. Geração de Boletos Mensais
```python
@celery.task
def generate_monthly_invoices():
    """
    - Buscar client_lots ativos
    - Verificar plano de pagamento
    - Gerar próximo boleto na Asaas
    - Salvar no banco
    - Enviar email com boleto
    """
```

#### 3. Envio de Lembretes de Vencimento
```python
@celery.task
def send_payment_reminders():
    """
    - 7 dias antes: lembrete
    - No dia: lembrete
    - 1 dia após vencimento: alerta
    """
```

#### 4. Notificação de OS
```python
@celery.task
def notify_service_order_update(order_id, status):
    """
    - Enviar email ao cliente
    - Enviar WhatsApp (opcional)
    """
```

#### 5. Sincronização com Asaas
```python
@celery.task
def sync_payment_status():
    """
    - Consultar pagamentos pendentes na Asaas
    - Atualizar status no banco
    """
```

### Configuração do Celery
- Beat schedule para tasks periódicas
- Redis como broker
- Retry automático em caso de falha
- Logging de todas as tasks

## Sistema de Notificações

### Email (Resend ou SendGrid)

Templates obrigatórios:
1. **Boas-vindas** - Quando cliente é criado
2. **Credenciais de acesso** - Quando acesso é criado
3. **Boleto disponível** - Quando boleto é gerado
4. **Lembrete de vencimento** - 7 dias antes, no dia
5. **Alerta de atraso** - Após vencimento
6. **Alerta de rescisão** - 3+ meses de atraso
7. **OS atualizada** - Mudança de status de serviço

### WhatsApp (Twilio ou Evolution)

Notificações importantes:
1. Boleto próximo do vencimento
2. Boleto vencido
3. OS aprovada/concluída

## Tratamento de Erros

### Exceções Customizadas
Criar em `utils/exceptions.py`:
- `TenantIsolationError` - Tentativa de acesso entre empresas
- `InsufficientPermissionsError` - Permissões insuficientes
- `ResourceNotFoundError` - Recurso não encontrado
- `AsaasIntegrationError` - Erro na API Asaas
- `StorageError` - Erro no upload/download

### Error Handlers Globais
```python
@app.exception_handler(TenantIsolationError)
async def tenant_error_handler(request, exc):
    return JSONResponse(
        status_code=403,
        content={"detail": "Access denied: tenant isolation"}
    )
```

### Validações com Pydantic
- Validar todos os inputs
- Retornar erros claros e específicos
- Sanitizar dados antes de salvar

## Logging e Monitoramento

### Logs Obrigatórios
- Todas as autenticações (sucesso e falha)
- Operações CRUD em recursos sensíveis
- Tentativas de acesso entre empresas
- Erros de integração (Asaas, Storage)
- Tasks Celery

### Formato de Log
```python
{
  "timestamp": "2024-02-05T10:30:00Z",
  "level": "INFO",
  "user_id": "uuid",
  "company_id": "uuid",
  "action": "create_client",
  "resource_id": "uuid",
  "ip": "192.168.1.1",
  "user_agent": "..."
}
```

## Migrations com Alembic

### Estrutura
1. Criar migration inicial com todas as tabelas
2. Adicionar índices necessários
3. Criar enums
4. Popular dados iniciais (se necessário)

### Índices Obrigatórios
- `company_id` em TODAS as tabelas (para queries multi-tenant)
- `email` na tabela `clients`
- `cpf_cnpj` nas tabelas `profiles` e `clients`
- `status` nas tabelas com status
- `due_date` na tabela `invoices`
- Índices compostos onde necessário

## Testes

### Testes Obrigatórios

#### 1. Testes de Multi-Tenancy
- Verificar isolamento de dados entre empresas
- Testar que company_admin não acessa outra empresa
- Testar que super_admin acessa todas empresas
- Testar que client acessa apenas próprios dados

#### 2. Testes de Autenticação
- Login com credenciais válidas/inválidas
- Tokens ES256 do Supabase
- Tokens internos HS256
- Refresh token
- Logout

#### 3. Testes de Permissões
- Cada role acessando endpoints permitidos/negados
- Operações CRUD com diferentes roles

#### 4. Testes de Integração
- Mock da API Asaas
- Testar criação de customer
- Testar geração de boleto
- Testar webhook

#### 5. Testes de Upload
- Upload de arquivo válido
- Rejeição de tipos inválidos
- Rejeição de arquivos grandes

## Variáveis de Ambiente Obrigatórias

```env
# App
APP_NAME=
APP_ENV=development
DEBUG=True
API_V1_PREFIX=/api/v1
SECRET_KEY=
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Supabase - NOVAS API KEYS
SUPABASE_URL=
SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
SUPABASE_SECRET_KEY=sb_secret_...
SUPABASE_JWT_SECRET={"x":"...","y":"...","alg":"ES256",...}

# Database
DATABASE_URL=postgresql://...

# Redis
REDIS_URL=redis://localhost:6379/0

# Asaas
ASAAS_API_KEY=
ASAAS_ENVIRONMENT=sandbox
ASAAS_BASE_URL=https://sandbox.asaas.com/api/v3

# Email
EMAIL_PROVIDER=resend
RESEND_API_KEY=
SMTP_FROM_EMAIL=
SMTP_FROM_NAME=

# WhatsApp
WHATSAPP_PROVIDER=twilio
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_WHATSAPP_NUMBER=

# Storage
SUPABASE_STORAGE_BUCKET=documents

# CORS
CORS_ORIGINS=["http://localhost:3000"]

# Rate Limiting
RATE_LIMIT_PER_MINUTE=60
```

## Documentação da API

### Swagger/OpenAPI
- Ativar documentação automática do FastAPI
- Adicionar descrições em todos os endpoints
- Documentar schemas de request/response
- Incluir exemplos de uso
- Documentar códigos de status HTTP

### README.md
Incluir:
- Descrição do projeto
- Como configurar ambiente local
- Como rodar migrations
- Como rodar testes
- Como fazer deploy
- Variáveis de ambiente
- Exemplos de uso da API

## Considerações de Performance

### Otimizações Obrigatórias
- Implementar paginação em TODAS as listagens
- Usar eager loading (joinedload) para evitar N+1 queries
- Criar índices apropriados
- Implementar cache Redis para:
  - Dados de empresa (raramente mudam)
  - Configurações do sistema
  - Estatísticas de dashboard
- Connection pooling no SQLAlchemy
- Compressão de responses (gzip)

### Limites
- Paginação: 50 itens por página (padrão 20)
- Upload: 10MB por arquivo
- Rate limit: 60 requisições/minuto por usuário

## Docker

### Dockerfile
Criar imagem otimizada para produção:
- Python 3.11 slim
- Multi-stage build
- Non-root user
- Health check

### docker-compose.yml
Services necessários:
- app (FastAPI)
- db (PostgreSQL - pode usar Supabase externo)
- redis (Celery broker)
- celery-worker
- celery-beat

## Checklist de Implementação

### Fase 1 - Setup e Auth (Prioridade MÁXIMA)
- [ ] Configuração do projeto (FastAPI, SQLAlchemy, Alembic)
- [ ] Conexão com Supabase (novas API keys)
- [ ] Modelos: Company, Profile
- [ ] Sistema de autenticação (ES256 + HS256)
- [ ] Middleware de tenant
- [ ] RLS policies básicas
- [ ] Endpoints de auth
- [ ] Testes de autenticação e multi-tenancy

### Fase 2 - Core Business (Prioridade ALTA)
- [ ] Modelos: Client, Development, Lot, ClientLot
- [ ] CRUD de clientes
- [ ] CRUD de lotes
- [ ] Vincular lote a cliente
- [ ] Integração Asaas (criar customer, gerar boleto)
- [ ] Storage service (upload documentos)
- [ ] Endpoints admin e client básicos
- [ ] Testes de CRUD e integrações

### Fase 3 - Financeiro e Serviços (Prioridade MÉDIA)
- [ ] Modelos: Invoice, ServiceType, ServiceOrder
- [ ] Endpoints financeiros (dashboard, relatórios)
- [ ] Sistema de ordens de serviço
- [ ] Webhook Asaas
- [ ] Celery tasks (inadimplência, boletos)
- [ ] Sistema de notificações (email)

### Fase 4 - Features Complementares (Prioridade BAIXA)
- [ ] Sistema de indicações
- [ ] WhatsApp notifications
- [ ] Relatórios avançados
- [ ] Otimizações de performance
- [ ] Documentação completa

## Instruções para a IDE (Windsurf)

Ao implementar este projeto:

1. **Comece pela Fase 1** - Não pule para funcionalidades avançadas sem ter base sólida
2. **Teste multi-tenancy desde o início** - Crie 2 empresas de teste e garanta isolamento
3. **Valide tokens ES256** - Teste com tokens reais do Supabase
4. **Use type hints** - Python é tipado, aproveite
5. **Docstrings em tudo** - Cada função deve ter docstring
6. **Commits atômicos** - Um commit por feature
7. **Migrations incrementais** - Não uma migration gigante
8. **Testes junto com código** - Não deixe testes para depois
9. **Mock em testes** - Não chame APIs externas reais em testes
10. **Environment-aware** - Código deve funcionar em dev, staging e prod

## Critérios de Sucesso

O backend estará completo quando:

✅ Super admin pode criar empresas
✅ Company admin pode gerenciar apenas sua empresa
✅ Cliente pode acessar apenas seus próprios dados
✅ Não há vazamento de dados entre empresas
✅ Tokens ES256 e HS256 funcionam
✅ Cliente criado gera customer no Asaas
✅ Lote vinculado gera boletos no Asaas
✅ Webhook Asaas atualiza status corretamente
✅ Upload de arquivos funciona com validações
✅ Tasks Celery executam conforme agendado
✅ Emails são enviados corretamente
✅ Todos os testes passam
✅ Documentação Swagger está completa
✅ Sistema pode ser deployado com Docker

---

**Importante**: Este sistema lida com dados financeiros sensíveis. Segurança e isolamento de dados não são opcionais - são OBRIGATÓRIOS. Valide cada query, cada acesso, cada operação. Multi-tenancy deve ser à prova de falhas.