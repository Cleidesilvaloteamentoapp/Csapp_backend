# CSApp Backend – Guia de Integração Frontend

> Documento de orientação para o frontend consumir a API sem erros.

---

## Sumário

1. [Configuração Base](#1-configuração-base)
2. [Autenticação](#2-autenticação)
3. [Padrões de Request/Response](#3-padrões-de-requestresponse)
4. [Endpoints por Módulo](#4-endpoints-por-módulo)
5. [Schemas de Dados (TypeScript)](#5-schemas-de-dados-typescript)
6. [Paginação](#6-paginação)
7. [Tratamento de Erros](#7-tratamento-de-erros)
8. [Roles e Permissões](#8-roles-e-permissões)
9. [Exemplos Práticos](#9-exemplos-práticos)
10. [Checklist de Integração](#10-checklist-de-integração)

---

## 1. Configuração Base

### URL Base

```
{SUPABASE_URL_OU_SERVER}/api/v1
```

Em desenvolvimento local:

```
http://localhost:8000/api/v1
```

### Headers obrigatórios

```http
Content-Type: application/json
Authorization: Bearer {access_token}
```

### CORS

O backend aceita origens configuradas (padrão: `http://localhost:3000` e `http://localhost:5173`).

### Rate Limiting

- **60 requests/minuto** por IP (padrão)
- Ao exceder, retorna `429 Too Many Requests`

### Health Check (sem auth)

```
GET /health
→ { "status": "ok", "app": "CSApp Backend", "env": "development" }
```

### Documentação Interativa

- **Swagger UI**: `/docs`
- **ReDoc**: `/redoc`

---

## 2. Autenticação

### Fluxo de Auth

```
┌─────────┐    POST /auth/login     ┌─────────┐
│ Frontend │ ──────────────────────► │ Backend │
│          │ ◄────────────────────── │         │
│          │   { access_token,       │         │
│          │     refresh_token }     │         │
└─────────┘                         └─────────┘
     │
     │  Armazena tokens (httpOnly cookie ou memória)
     │
     ▼  Toda request autenticada:
     Authorization: Bearer {access_token}
```

### 2.1 Signup (criar empresa + admin)

```http
POST /api/v1/auth/signup
Content-Type: application/json
```

```json
{
  "company_name": "Minha Empresa",
  "company_slug": "minha-empresa",
  "full_name": "Nome Completo",
  "email": "admin@empresa.com",
  "password": "minhasenha123",
  "cpf_cnpj": "12345678900",
  "phone": "11999990000"
}
```

**Resposta (201):**

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

**Validações:**
- `company_slug`: apenas `a-z`, `0-9`, `-` (regex: `^[a-z0-9-]+$`)
- `password`: 8-128 caracteres
- `cpf_cnpj`: 11-20 caracteres
- `phone`: 10-20 caracteres

### 2.2 Login

```http
POST /api/v1/auth/login
```

```json
{
  "email": "admin@empresa.com",
  "password": "minhasenha123"
}
```

**Resposta (200):** mesmo formato de `TokenResponse`

**Erros:**
- `401` – credenciais inválidas

### 2.3 Obter usuário atual

```http
GET /api/v1/auth/me
Authorization: Bearer {access_token}
```

**Resposta (200):**

```json
{
  "id": "db79fbda-8ecd-49ae-b590-0dea1a5f26ad",
  "company_id": "a1b2c3d4-0001-4000-8000-000000000001",
  "role": "super_admin",
  "full_name": "Nickson Aleixo",
  "email": "nacs.promoter@gmail.com",
  "phone": "11999990000",
  "cpf_cnpj": "12345678900"
}
```

### 2.4 Refresh Token

```http
POST /api/v1/auth/refresh
```

```json
{
  "refresh_token": "eyJ..."
}
```

**Resposta (200):** novo par `access_token` + `refresh_token`

### 2.5 Logout

```http
POST /api/v1/auth/logout
Authorization: Bearer {access_token}
→ 204 No Content
```

> **IMPORTANTE:** O logout é client-side. Descarte os tokens armazenados.

### Armazenamento de Tokens

| Método | Segurança | Recomendação |
|--------|-----------|--------------|
| `httpOnly cookie` | Alta | Preferido para produção |
| `localStorage` | Baixa (XSS) | NÃO recomendado |
| Variável em memória (React state/context) | Média | Ok para desenvolvimento |

---

## 3. Padrões de Request/Response

### 3.1 IDs

Todos os IDs são **UUID v4** no formato: `xxxxxxxx-xxxx-4xxx-xxxx-xxxxxxxxxxxx`

### 3.2 Datas

| Campo | Formato | Exemplo |
|-------|---------|---------|
| `date` | ISO 8601 date | `"2025-06-15"` |
| `datetime` / `timestamptz` | ISO 8601 com timezone | `"2025-06-15T10:00:00+00:00"` |

### 3.3 Valores monetários

Retornados como **string decimal** (Decimal). No frontend, parse com `parseFloat()` ou biblioteca de precisão.

```json
{
  "amount": "6250.00",
  "total_value": "85000.00"
}
```

### 3.4 Status (Enums)

| Entidade | Valores possíveis |
|----------|-------------------|
| **Company** | `active`, `suspended`, `inactive` |
| **User Role** | `super_admin`, `company_admin`, `client` |
| **Client** | `active`, `inactive`, `defaulter` |
| **Lot** | `available`, `reserved`, `sold` |
| **ClientLot** | `active`, `completed`, `cancelled` |
| **Invoice** | `pending`, `paid`, `overdue`, `cancelled` |
| **ServiceOrder** | `requested`, `approved`, `in_progress`, `completed`, `cancelled` |
| **Referral** | `pending`, `contacted`, `converted`, `lost` |

---

## 4. Endpoints por Módulo

### Legenda de Roles

| Símbolo | Role | Descrição |
|---------|------|-----------|
| 🔴 | `super_admin` | Acesso total |
| 🟠 | `company_admin` | Admin da empresa (inclui super_admin) |
| 🟢 | `client` | Cliente (inclui admin e super_admin) |
| ⚪ | Público | Sem autenticação |

---

### 4.1 Auth

| Método | Endpoint | Role | Descrição |
|--------|----------|------|-----------|
| `POST` | `/auth/signup` | ⚪ | Criar empresa + admin |
| `POST` | `/auth/login` | ⚪ | Login |
| `POST` | `/auth/logout` | 🟢 | Logout |
| `GET` | `/auth/me` | 🟢 | Dados do usuário atual |
| `POST` | `/auth/refresh` | ⚪ | Renovar tokens |

---

### 4.2 Companies (super_admin)

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/companies/?page=1&per_page=20&status=active&search=texto` | Listar empresas |
| `POST` | `/companies/` | Criar empresa |
| `GET` | `/companies/{company_id}` | Detalhes da empresa |
| `PUT` | `/companies/{company_id}` | Atualizar empresa |
| `PATCH` | `/companies/{company_id}/status` | Alterar status |

**Query Params (GET list):**
- `page` (int, default 1)
- `per_page` (int, default 20, max 50)
- `status` (string, optional): `active`, `suspended`, `inactive`
- `search` (string, optional): busca por nome

**Body PATCH status:**

```json
{ "status": "suspended" }
```

---

### 4.3 Admin Dashboard 🟠

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/admin/dashboard/stats` | Estatísticas gerais |
| `GET` | `/admin/dashboard/financial-overview` | Resumo financeiro |
| `GET` | `/admin/dashboard/recent-activities?limit=10` | Atividades recentes |
| `GET` | `/admin/dashboard/charts/revenue?months=6` | Gráfico de receita mensal |
| `GET` | `/admin/dashboard/charts/services` | Gráfico de serviços populares |

**Response `/stats`:**

```json
{
  "total_clients": 5,
  "active_clients": 3,
  "defaulter_clients": 1,
  "open_service_orders": 3,
  "completed_service_orders": 2,
  "total_lots": 14,
  "available_lots": 9,
  "sold_lots": 4
}
```

**Response `/financial-overview`:**

```json
{
  "total_receivable": "29166.62",
  "total_received": "49249.99",
  "total_overdue": "22083.33",
  "overdue_count": 6
}
```

**Response `/charts/revenue`:**

```json
[
  { "month": "2025-07", "amount": "12916.66" },
  { "month": "2025-08", "amount": "9583.33" }
]
```

---

### 4.4 Admin Clients 🟠

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/admin/clients/?page=1&per_page=20&status=active&search=nome` | Listar clientes |
| `POST` | `/admin/clients/` | Criar cliente |
| `GET` | `/admin/clients/{client_id}` | Detalhes do cliente |
| `PUT` | `/admin/clients/{client_id}` | Atualizar cliente |
| `DELETE` | `/admin/clients/{client_id}` | Desativar (soft delete) |
| `GET` | `/admin/clients/{client_id}/lots` | Lotes do cliente |
| `GET` | `/admin/clients/{client_id}/invoices` | Faturas do cliente |
| `GET` | `/admin/clients/{client_id}/documents` | Documentos do cliente |
| `POST` | `/admin/clients/{client_id}/documents` | Upload de documento |

**Body POST (criar cliente):**

```json
{
  "email": "cliente@email.com",
  "full_name": "Nome do Cliente",
  "cpf_cnpj": "12345678900",
  "phone": "11999990000",
  "address": {
    "street": "Rua das Flores",
    "number": "123",
    "city": "São Paulo",
    "state": "SP",
    "zip": "01001-000"
  },
  "create_access": false,
  "password": null
}
```

> Se `create_access: true`, envie também `password` (min 8 chars) para criar credenciais de login.

**Upload de documento:**

```http
POST /admin/clients/{client_id}/documents
Content-Type: multipart/form-data

file: (arquivo binário)
```

**Response:**

```json
{ "path": "companies/.../file.pdf", "url": "https://..." }
```

---

### 4.5 Admin Developments 🟠

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/admin/developments/` | Listar empreendimentos |
| `POST` | `/admin/developments/` | Criar empreendimento |
| `GET` | `/admin/developments/{dev_id}` | Detalhes |
| `PUT` | `/admin/developments/{dev_id}` | Atualizar |

**Body POST:**

```json
{
  "name": "Residencial Parque",
  "description": "Loteamento com infraestrutura completa",
  "location": "Rodovia SP-100, km 25",
  "documents": {}
}
```

---

### 4.6 Admin Lots 🟠

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/admin/lots/?page=1&per_page=20&development_id=uuid&status=available` | Listar lotes |
| `POST` | `/admin/lots/` | Criar lote |
| `GET` | `/admin/lots/{lot_id}` | Detalhes do lote |
| `PUT` | `/admin/lots/{lot_id}` | Atualizar lote |
| `POST` | `/admin/lots/assign` | Vender lote a cliente |

**Body POST (criar lote):**

```json
{
  "development_id": "00000000-0000-4000-b000-00000000bb01",
  "lot_number": "07",
  "block": "C",
  "area_m2": 300.00,
  "price": 95000.00,
  "documents": {}
}
```

**Body POST `/assign` (vender lote):**

```json
{
  "client_id": "00000000-0000-4000-a000-00000000aa01",
  "lot_id": "00000000-0000-4000-c000-00000000cc04",
  "purchase_date": "2025-11-01",
  "total_value": 105000.00,
  "payment_plan": {
    "installments": 24,
    "first_due": "2025-12-01"
  }
}
```

> **Efeitos colaterais:** Muda status do lote para `sold`, cria `client_lot`, gera `invoices` automaticamente (e boletos Asaas se integrado).

---

### 4.7 Admin Financial 🟠

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/admin/financial/summary` | Resumo financeiro |
| `GET` | `/admin/financial/receivables?page=1&per_page=20&status=overdue` | Contas a receber |
| `GET` | `/admin/financial/defaulters` | Lista de inadimplentes |
| `GET` | `/admin/financial/revenue-by-services` | Receita por tipo de serviço |

**Response `/defaulters`:**

```json
[
  {
    "client_id": "00000000-0000-4000-a000-00000000aa04",
    "client_name": "Carlos Oliveira",
    "overdue_months": 5,
    "overdue_amount": "18750.00"
  }
]
```

---

### 4.8 Admin Services 🟠

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/admin/services/types` | Listar tipos de serviço |
| `POST` | `/admin/services/types` | Criar tipo de serviço |
| `PUT` | `/admin/services/types/{type_id}` | Atualizar tipo |
| `GET` | `/admin/services/orders?page=1&per_page=20&status=requested&client_id=uuid` | Listar ordens |
| `GET` | `/admin/services/orders/{order_id}` | Detalhes da ordem |
| `PATCH` | `/admin/services/orders/{order_id}/status` | Alterar status |
| `PATCH` | `/admin/services/orders/{order_id}/financial` | Alterar custo/receita |
| `GET` | `/admin/services/analytics` | Análise custo vs receita |

**Body PATCH status:**

```json
{ "status": "completed" }
```

**Body PATCH financial:**

```json
{ "cost": 800.00, "revenue": 1200.00 }
```

---

### 4.9 Client Dashboard 🟢

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/client/dashboard/summary` | Resumo do cliente |
| `GET` | `/client/dashboard/my-lots` | Meus lotes |
| `GET` | `/client/dashboard/recent-activity?limit=10` | Atividades recentes |

**Response `/summary`:**

```json
{
  "total_lots": 1,
  "next_due_date": "2025-11-15",
  "next_due_amount": "6250.00",
  "pending_invoices": 2,
  "overdue_invoices": 0
}
```

---

### 4.10 Client Invoices 🟢

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/client/invoices/?lot_id=uuid` | Listar faturas |
| `GET` | `/client/invoices/{invoice_id}` | Detalhes da fatura |
| `GET` | `/client/invoices/{invoice_id}/pdf` | Redirect para URL de pagamento |

> O endpoint `/pdf` retorna **302 Redirect** para a URL do Asaas.

---

### 4.11 Client Services 🟢

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/client/services/types` | Tipos de serviço disponíveis |
| `POST` | `/client/services/orders` | Solicitar serviço |
| `GET` | `/client/services/orders` | Minhas ordens |
| `GET` | `/client/services/orders/{order_id}` | Detalhes da ordem |

**Body POST (solicitar serviço):**

```json
{
  "service_type_id": "00000000-0000-4000-f000-00000000ff01",
  "lot_id": "00000000-0000-4000-c000-00000000cc01",
  "notes": "Gostaria de agendar para próxima semana"
}
```

---

### 4.12 Client Documents 🟢

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/client/documents/` | Listar documentos |
| `POST` | `/client/documents/` | Upload de documento |
| `DELETE` | `/client/documents/{doc_index}` | Remover documento por índice |

**Upload:**

```http
POST /client/documents/
Content-Type: multipart/form-data

file: (arquivo binário)
```

> O `doc_index` para DELETE é o índice (0-based) no array de documentos.

---

### 4.13 Client Referrals 🟢

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `POST` | `/client/referrals/` | Criar indicação |
| `GET` | `/client/referrals/` | Listar minhas indicações |

**Body POST:**

```json
{
  "referred_name": "Amigo da Silva",
  "referred_phone": "11988887777",
  "referred_email": "amigo@email.com"
}
```

---

## 5. Schemas de Dados (TypeScript)

```typescript
// ===================== Auth =====================
interface SignupRequest {
  company_name: string;       // min 2, max 255
  company_slug: string;       // regex: /^[a-z0-9-]+$/
  full_name: string;          // min 2, max 255
  email: string;              // email válido
  password: string;           // min 8, max 128
  cpf_cnpj: string;           // min 11, max 20
  phone: string;              // min 10, max 20
}

interface LoginRequest {
  email: string;
  password: string;
}

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
}

interface MeResponse {
  id: string;                 // UUID
  company_id: string | null;  // UUID
  role: "super_admin" | "company_admin" | "client";
  full_name: string;
  email: string;
  phone: string;
  cpf_cnpj: string;
}

// ===================== Company =====================
interface CompanyCreate {
  name: string;
  slug: string;               // regex: /^[a-z0-9-]+$/
  settings?: Record<string, any>;
}

interface CompanyUpdate {
  name?: string;
  slug?: string;
  settings?: Record<string, any>;
}

interface CompanyResponse {
  id: string;
  name: string;
  slug: string;
  settings: Record<string, any> | null;
  status: "active" | "suspended" | "inactive";
  created_at: string;
  updated_at: string;
}

// ===================== Client =====================
interface ClientCreate {
  email: string;
  full_name: string;
  cpf_cnpj: string;
  phone: string;
  address?: Record<string, any>;
  create_access?: boolean;
  password?: string;           // obrigatório se create_access = true
}

interface ClientUpdate {
  email?: string;
  full_name?: string;
  cpf_cnpj?: string;
  phone?: string;
  address?: Record<string, any>;
  status?: "active" | "inactive" | "defaulter";
}

interface ClientResponse {
  id: string;
  company_id: string;
  profile_id: string | null;
  email: string;
  full_name: string;
  cpf_cnpj: string;
  phone: string;
  address: Record<string, any> | null;
  documents: any[] | null;
  status: "active" | "inactive" | "defaulter";
  asaas_customer_id: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

// ===================== Development =====================
interface DevelopmentCreate {
  name: string;
  description?: string;
  location?: string;
  documents?: Record<string, any>;
}

interface DevelopmentResponse {
  id: string;
  company_id: string;
  name: string;
  description: string | null;
  location: string | null;
  documents: Record<string, any> | null;
  created_at: string;
  updated_at: string;
}

// ===================== Lot =====================
interface LotCreate {
  development_id: string;     // UUID
  lot_number: string;
  block?: string;
  area_m2: number;            // > 0
  price: number;              // > 0
  documents?: Record<string, any>;
}

interface LotUpdate {
  lot_number?: string;
  block?: string;
  area_m2?: number;
  price?: number;
  status?: "available" | "reserved" | "sold";
  documents?: Record<string, any>;
}

interface LotResponse {
  id: string;
  company_id: string;
  development_id: string;
  lot_number: string;
  block: string | null;
  area_m2: string;            // Decimal como string
  price: string;
  status: "available" | "reserved" | "sold";
  documents: Record<string, any> | null;
  created_at: string;
  updated_at: string;
}

// ===================== Lot Assignment =====================
interface LotAssignRequest {
  client_id: string;
  lot_id: string;
  purchase_date: string;       // "YYYY-MM-DD"
  total_value: number;
  payment_plan?: {
    installments?: number;
    first_due?: string;        // "YYYY-MM-DD"
    down_payment?: number;
    monthly_value?: number;
  };
}

interface ClientLotResponse {
  id: string;
  company_id: string;
  client_id: string;
  lot_id: string;
  purchase_date: string;
  total_value: string;         // Decimal como string
  payment_plan: Record<string, any> | null;
  status: "active" | "completed" | "cancelled";
  created_at: string;
  updated_at: string;
}

// ===================== Invoice =====================
interface InvoiceResponse {
  id: string;
  company_id: string;
  client_lot_id: string;
  due_date: string;            // "YYYY-MM-DD"
  amount: string;              // Decimal como string
  installment_number: number;
  status: "pending" | "paid" | "overdue" | "cancelled";
  asaas_payment_id: string | null;
  barcode: string | null;
  payment_url: string | null;
  paid_at: string | null;
  created_at: string;
  updated_at: string;
}

// ===================== Service =====================
interface ServiceTypeCreate {
  name: string;
  description?: string;
  base_price?: number;         // >= 0
  is_active?: boolean;
}

interface ServiceTypeResponse {
  id: string;
  company_id: string;
  name: string;
  description: string | null;
  base_price: string;          // Decimal como string
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface ServiceOrderCreate {
  service_type_id: string;     // UUID
  lot_id?: string;             // UUID, opcional
  notes?: string;
}

interface ServiceOrderResponse {
  id: string;
  company_id: string;
  client_id: string;
  lot_id: string | null;
  service_type_id: string;
  requested_date: string;
  execution_date: string | null;
  status: "requested" | "approved" | "in_progress" | "completed" | "cancelled";
  cost: string;
  revenue: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

// ===================== Referral =====================
interface ReferralCreate {
  referred_name: string;
  referred_phone: string;
  referred_email?: string;
}

interface ReferralResponse {
  id: string;
  company_id: string;
  referrer_client_id: string;
  referred_name: string;
  referred_phone: string;
  referred_email: string | null;
  status: "pending" | "contacted" | "converted" | "lost";
  created_at: string;
  updated_at: string;
}

// ===================== Dashboard =====================
interface AdminStats {
  total_clients: number;
  active_clients: number;
  defaulter_clients: number;
  open_service_orders: number;
  completed_service_orders: number;
  total_lots: number;
  available_lots: number;
  sold_lots: number;
}

interface FinancialOverview {
  total_receivable: string;
  total_received: string;
  total_overdue: string;
  overdue_count: number;
}

interface ClientSummary {
  total_lots: number;
  next_due_date: string | null;
  next_due_amount: string | null;
  pending_invoices: number;
  overdue_invoices: number;
}

// ===================== Paginação =====================
interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}
```

---

## 6. Paginação

Endpoints paginados retornam:

```json
{
  "items": [...],
  "total": 50,
  "page": 1,
  "per_page": 20,
  "pages": 3
}
```

**Query params:**

| Param | Tipo | Default | Limites |
|-------|------|---------|---------|
| `page` | int | 1 | >= 1 |
| `per_page` | int | 20 | 1-50 |

**Endpoints paginados:**
- `GET /companies/`
- `GET /admin/clients/`
- `GET /admin/lots/`
- `GET /admin/financial/receivables`
- `GET /admin/services/orders`

**Endpoints NÃO paginados (retornam array direto):**
- `GET /admin/developments/`
- `GET /admin/services/types`
- `GET /admin/clients/{id}/lots`
- `GET /admin/clients/{id}/invoices`
- `GET /client/invoices/`
- `GET /client/services/orders`
- `GET /client/referrals/`

---

## 7. Tratamento de Erros

### Formato padrão de erro

```json
{
  "detail": "Mensagem descritiva do erro"
}
```

### Códigos HTTP

| Código | Significado | Quando |
|--------|-------------|--------|
| `400` | Bad Request | Validação falhou, upload inválido |
| `401` | Unauthorized | Token ausente, expirado ou inválido |
| `403` | Forbidden | Role insuficiente ou isolamento de tenant |
| `404` | Not Found | Recurso não encontrado |
| `409` | Conflict | Duplicata (email, slug, cpf_cnpj) |
| `422` | Validation Error | Pydantic validation (corpo inválido) |
| `429` | Too Many Requests | Rate limit excedido |
| `502` | Bad Gateway | Falha em integração externa (Asaas) |

### Erro de Validação (422)

```json
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "value is not a valid email address",
      "type": "value_error"
    }
  ]
}
```

### Implementação sugerida (Axios)

```typescript
import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1',
  headers: { 'Content-Type': 'application/json' },
});

// Interceptor para adicionar token
api.interceptors.request.use((config) => {
  const token = getAccessToken(); // sua função de armazenamento
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Interceptor para refresh automático
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        const refreshToken = getRefreshToken();
        const { data } = await axios.post(
          `${api.defaults.baseURL}/auth/refresh`,
          { refresh_token: refreshToken }
        );

        setAccessToken(data.access_token);
        setRefreshToken(data.refresh_token);

        originalRequest.headers.Authorization = `Bearer ${data.access_token}`;
        return api(originalRequest);
      } catch (refreshError) {
        // Refresh falhou → redirecionar para login
        clearTokens();
        window.location.href = '/login';
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

export default api;
```

---

## 8. Roles e Permissões

### Matriz de acesso

| Endpoint Group | `super_admin` | `company_admin` | `client` |
|---------------|:-------------:|:----------------:|:--------:|
| `/auth/*` | ✅ | ✅ | ✅ |
| `/companies/*` | ✅ | ❌ | ❌ |
| `/admin/dashboard/*` | ✅ | ✅ | ❌ |
| `/admin/clients/*` | ✅ | ✅ | ❌ |
| `/admin/lots/*` | ✅ | ✅ | ❌ |
| `/admin/developments/*` | ✅ | ✅ | ❌ |
| `/admin/financial/*` | ✅ | ✅ | ❌ |
| `/admin/services/*` | ✅ | ✅ | ❌ |
| `/client/dashboard/*` | ✅ | ✅ | ✅ |
| `/client/invoices/*` | ✅ | ✅ | ✅ |
| `/client/services/*` | ✅ | ✅ | ✅ |
| `/client/documents/*` | ✅ | ✅ | ✅ |
| `/client/referrals/*` | ✅ | ✅ | ✅ |

### Roteamento no frontend

```typescript
const ADMIN_ROLES = ['super_admin', 'company_admin'];
const CLIENT_ROLES = ['client'];

function canAccessAdmin(role: string): boolean {
  return ADMIN_ROLES.includes(role);
}

function canAccessSuperAdmin(role: string): boolean {
  return role === 'super_admin';
}
```

### Multi-tenancy

Cada usuário vê **APENAS dados da sua empresa**. O backend filtra automaticamente por `company_id` via JWT. O frontend **NÃO precisa** enviar `company_id` nas requests — ele é extraído do token.

---

## 9. Exemplos Práticos

### 9.1 Fluxo completo: Login → Dashboard

```typescript
// 1. Login
const { data: auth } = await api.post('/auth/login', {
  email: 'nacs.promoter@gmail.com',
  password: 'suasenha',
});
setAccessToken(auth.access_token);
setRefreshToken(auth.refresh_token);

// 2. Obter perfil
const { data: me } = await api.get('/auth/me');
// me.role === 'super_admin'

// 3. Carregar dashboard (admin)
if (canAccessAdmin(me.role)) {
  const { data: stats } = await api.get('/admin/dashboard/stats');
  const { data: financial } = await api.get('/admin/dashboard/financial-overview');
  const { data: revenue } = await api.get('/admin/dashboard/charts/revenue?months=6');
}
```

### 9.2 Vender um lote

```typescript
// 1. Listar lotes disponíveis
const { data: lots } = await api.get('/admin/lots/', {
  params: { status: 'available', development_id: 'uuid-do-empreendimento' },
});

// 2. Escolher cliente
const { data: clients } = await api.get('/admin/clients/', {
  params: { status: 'active', search: 'João' },
});

// 3. Atribuir lote
const { data: clientLot } = await api.post('/admin/lots/assign', {
  client_id: clients.items[0].id,
  lot_id: lots.items[0].id,
  purchase_date: '2025-11-01',
  total_value: 105000.00,
  payment_plan: {
    installments: 24,
    first_due: '2025-12-01',
  },
});
// Invoices são criadas automaticamente!

// 4. Verificar faturas geradas
const { data: invoices } = await api.get(`/admin/clients/${clients.items[0].id}/invoices`);
```

### 9.3 Portal do cliente

```typescript
// 1. Login como cliente
const { data: auth } = await api.post('/auth/login', {
  email: 'testecliente@teste.com',
  password: 'senhadocliente',
});

// 2. Dashboard
const { data: summary } = await api.get('/client/dashboard/summary');
const { data: myLots } = await api.get('/client/dashboard/my-lots');

// 3. Faturas
const { data: invoices } = await api.get('/client/invoices/');

// 4. Solicitar serviço
const { data: serviceTypes } = await api.get('/client/services/types');
const { data: order } = await api.post('/client/services/orders', {
  service_type_id: serviceTypes[0].id,
  lot_id: myLots[0].lot_id,
  notes: 'Preciso de limpeza no terreno',
});

// 5. Fazer indicação
const { data: referral } = await api.post('/client/referrals/', {
  referred_name: 'Amigo da Silva',
  referred_phone: '11988887777',
  referred_email: 'amigo@email.com',
});
```

---

## 10. Checklist de Integração

### Setup inicial

- [ ] Configurar URL base da API (`VITE_API_URL`)
- [ ] Criar módulo HTTP com interceptors (auth + refresh)
- [ ] Implementar armazenamento seguro de tokens
- [ ] Implementar guard de rotas por role

### Páginas Admin

- [ ] Login / Signup
- [ ] Dashboard (stats + financial + gráficos)
- [ ] Gestão de Clientes (CRUD + documentos)
- [ ] Gestão de Empreendimentos (CRUD)
- [ ] Gestão de Lotes (CRUD + venda/assign)
- [ ] Financeiro (resumo + contas a receber + inadimplentes)
- [ ] Serviços (tipos + ordens + análise)

### Páginas Cliente

- [ ] Dashboard (resumo + meus lotes)
- [ ] Faturas (listagem + detalhes + PDF/pagamento)
- [ ] Serviços (solicitar + acompanhar)
- [ ] Documentos (listar + upload + remover)
- [ ] Indicações (criar + listar)

### Tratamento

- [ ] Loading states em todas as chamadas
- [ ] Tratamento de erros 401 (refresh automático)
- [ ] Tratamento de erros 403 (redirecionamento)
- [ ] Tratamento de erros 422 (exibir validação)
- [ ] Tratamento de erros 429 (rate limit)
- [ ] Paginação nos listagens
- [ ] Filtros e busca

---

## IDs dos dados de teste (Seed)

Para facilitar testes durante o desenvolvimento:

| Entidade | ID |
|----------|----|
| **Company** | `a1b2c3d4-0001-4000-8000-000000000001` |
| **Admin (super_admin)** | `db79fbda-8ecd-49ae-b590-0dea1a5f26ad` |
| **Cliente Teste** | `00df9257-e938-4105-86a1-8bfb98d2ab67` |
| **Client record (teste)** | `00000000-0000-4000-a000-00000000aa01` |
| **Dev: Parque das Águas** | `00000000-0000-4000-b000-00000000bb01` |
| **Dev: Jardim dos Ipês** | `00000000-0000-4000-b000-00000000bb02` |
| **Dev: Vila Verde** | `00000000-0000-4000-b000-00000000bb03` |
| **Lote disponível (ex)** | `00000000-0000-4000-c000-00000000cc04` |
