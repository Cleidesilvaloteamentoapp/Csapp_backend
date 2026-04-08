# Frontend Instructions — Client Adjustments & Financial Management Enhancement

> **Backend version**: migration `007_company_financial_settings`
> **Date**: March 2026 (updated 2026-03-24)

This document describes all new backend endpoints, schemas, and behavioral changes that the frontend team needs to implement.

---

## Table of Contents

1. [New Admin Endpoints](#1-new-admin-endpoints)
2. [New Client Endpoints](#2-new-client-endpoints)
3. [Modified Endpoints](#3-modified-endpoints)
4. [Schema Changes (Response Fields)](#4-schema-changes)
5. [UI/UX Requirements](#5-uiux-requirements)
6. [Permission Changes](#6-permission-changes)
7. [Notification Types](#7-notification-types)
8. [PWA Considerations](#8-pwa-considerations)
9. [Per-Client Financial Rules & Global Defaults](#9-per-client-financial-rules--global-defaults)

---

## 1. New Admin Endpoints

### 1.1 Economic Indices (Manual Index Management)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/admin/economic-indices` | List indices (filter by `index_type`, `state_code`, `start_month`, `end_month`) |
| `POST` | `/api/v1/admin/economic-indices` | Create manual index entry |
| `PATCH` | `/api/v1/admin/economic-indices/{id}` | Update index value |
| `DELETE` | `/api/v1/admin/economic-indices/{id}` | Delete index entry |

**UI needed**: Admin page "Índices Econômicos" with:
- Table listing all indices (columns: Tipo, Mês Referência, UF, Valor %, Fonte, Data Criação)
- Filters: dropdown for tipo (IPCA, IGPM, CUB, INPC), text for UF, date range
- Modal/form to add new index (tipo, mês referência, UF for CUB, valor)
- CUB requires `state_code` (2-letter UF) — show UF dropdown only when tipo = CUB
- Inline edit for value

### 1.2 Cycle Approvals (12-Installment Cycle Management)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/admin/cycle-approvals` | List approvals (filter by `status`: PENDING, APPROVED, REJECTED) |
| `GET` | `/api/v1/admin/cycle-approvals/{id}` | Get approval details |
| `POST` | `/api/v1/admin/cycle-approvals/{id}/approve` | Approve cycle with new installment value |
| `POST` | `/api/v1/admin/cycle-approvals/{id}/reject` | Reject cycle with reason |

**UI needed**: Admin page "Aprovação de Ciclos" with:
- Badge/counter for PENDING approvals in the sidebar
- Table: Cliente, Lote, Ciclo #, Valor Anterior, Status, Data Solicitação
- Detail view with adjustment breakdown
- Approve form: new installment value (required), adjustment details JSON (optional), admin notes
- Reject form: admin notes (required, min 5 chars)
- When approved, backend auto-generates next 12 invoices

### 1.3 Contract Transfers

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/admin/transfers` | List transfers (filter by `status`) |
| `POST` | `/api/v1/admin/transfers` | Create transfer request |
| `GET` | `/api/v1/admin/transfers/{id}` | Transfer details |
| `POST` | `/api/v1/admin/transfers/{id}/approve` | Approve transfer (**SUPER_ADMIN only**) |
| `POST` | `/api/v1/admin/transfers/{id}/complete` | Complete transfer — migrates data (**SUPER_ADMIN only**) |
| `POST` | `/api/v1/admin/transfers/{id}/cancel` | Cancel transfer |

**Workflow**:
1. Admin creates transfer (selects source client, target client, lot)
2. SUPER_ADMIN approves
3. SUPER_ADMIN completes → lot, pending invoices, and pending boletos migrate to new client

**UI needed**: Admin page "Transferências de Contrato" with:
- Table: De (cliente), Para (cliente), Lote, Status, Taxa, Data
- Create form: select lot → auto-fills `from_client_id`; select target client; optional fee and reason
- Status flow badges: PENDING → APPROVED → COMPLETED (or CANCELLED)
- Approve/Complete buttons only visible for SUPER_ADMIN

### 1.4 Early Payoff Requests (Admin Side)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/admin/early-payoff-requests` | List requests (filter by `status`) |
| `GET` | `/api/v1/admin/early-payoff-requests/{id}` | Request details |
| `PATCH` | `/api/v1/admin/early-payoff-requests/{id}` | Update status (CONTACTED, COMPLETED, CANCELLED) |

**UI needed**: Admin page "Solicitações de Antecipação" with:
- Table: Cliente, Lote, Status, Mensagem, Data
- Status update dropdown + admin notes

### 1.5 Manual Boleto Writeoff

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/admin/boletos/{id}/baixa-manual` | Manual writeoff (**SUPER_ADMIN only**) |

**Payload**: `{ "reason": "string (min 5)", "valor_liquidacao": optional, "data_liquidacao": optional }`

**UI needed**:
- Button "Baixa Manual" on boleto detail page — **only visible for SUPER_ADMIN**
- Modal: reason (required), optional value and date overrides
- After writeoff, boleto shows badge "BAIXA MANUAL" in red/orange

### 1.6 Dashboard Defaulters Drill-Down

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/admin/dashboard/defaulters` | List defaulters with overdue details |

**Response fields**: `client_id`, `client_name`, `cpf_cnpj`, `phone`, `overdue_invoices`, `overdue_amount`, `oldest_due_date`, `days_overdue`

**UI needed**: Clicking the "Inadimplentes" card on the dashboard opens a drill-down table with the above data. Sort by `days_overdue` desc.

### 1.7 Bank Statement Upload (Stub)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/admin/bank-statements/upload` | Upload francesinha file |
| `GET` | `/api/v1/admin/bank-statements/supported-banks` | List supported banks |

**Status**: Stub — returns 501 until per-bank parsing is implemented. Show a "coming soon" badge in the UI.

---

## 2. New Client Endpoints

### 2.1 Early Payoff Request (Client Side)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/client/early-payoff` | Request early payoff for a lot |
| `GET` | `/api/v1/client/early-payoff` | List own requests |

**UI needed**: "Antecipar Pagamento" button on the client's lot detail page. Opens a form:
- Select lot (if client has multiple)
- Optional message to admin
- After submission, show status tracker (PENDING → CONTACTED → COMPLETED)

---

## 3. Modified Endpoints

### 3.1 Boleto Listing (Admin)

`GET /api/v1/admin/boletos` now accepts an additional query parameter:
- `tag` — filter by `ENTRADA_PARCELADA`, `PARCELA_CONTRATO`, `SERVICO_AVULSO`, `SEGUNDA_VIA`, `RENEGOCIACAO`

**UI needed**: Add a "Tag" dropdown filter to the boleto listing page.

### 3.2 Boleto Update (Admin)

`PATCH /api/v1/admin/boletos/{id}` now accepts:
- `tag` — set/change the boleto tag
- `status` — **no longer allows LIQUIDADO** via this endpoint (use baixa-manual or webhook)

### 3.3 Boleto Responses

All boleto response schemas now include:
- `tag` — string or null
- `installment_label` — e.g. "Parcela 5/120"
- `writeoff_type` — "AUTOMATICA_BANCO" or "MANUAL_ADMIN" or null
- `writeoff_by` — UUID of admin who did manual writeoff
- `writeoff_reason` — text reason for manual writeoff

**UI needed**:
- Show tag as a colored badge on boleto cards/table rows
- Show `installment_label` prominently on boleto detail
- Show writeoff info (type badge + reason) when present

---

## 4. Schema Changes

### 4.1 BoletoResponse (new fields)

```typescript
interface BoletoResponse {
  // ... existing fields ...
  tag: 'ENTRADA_PARCELADA' | 'PARCELA_CONTRATO' | 'SERVICO_AVULSO' | 'SEGUNDA_VIA' | 'RENEGOCIACAO' | null;
  installment_label: string | null;
  writeoff_type: 'AUTOMATICA_BANCO' | 'MANUAL_ADMIN' | null;
  writeoff_by: string | null; // UUID
  writeoff_reason: string | null;
}
```

### 4.2 Tag Color Mapping (Suggested)

| Tag | Color | Label PT-BR |
|-----|-------|-------------|
| `ENTRADA_PARCELADA` | Blue | Entrada Parcelada |
| `PARCELA_CONTRATO` | Green | Parcela de Contrato |
| `SERVICO_AVULSO` | Orange | Serviço Avulso |
| `SEGUNDA_VIA` | Yellow | Segunda Via |
| `RENEGOCIACAO` | Purple | Renegociação |

### 4.3 New TypeScript Interfaces

```typescript
interface EconomicIndexResponse {
  id: string;
  company_id: string;
  index_type: 'IPCA' | 'IGPM' | 'CUB' | 'INPC';
  state_code: string | null;
  reference_month: string; // date
  value: number;
  source: 'MANUAL' | 'BCB_API';
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

interface CycleApprovalResponse {
  id: string;
  company_id: string;
  client_lot_id: string;
  cycle_number: number;
  status: 'PENDING' | 'APPROVED' | 'REJECTED';
  previous_installment_value: number;
  new_installment_value: number | null;
  adjustment_details: object | null;
  requested_at: string;
  approved_at: string | null;
  approved_by: string | null;
  admin_notes: string | null;
  client_name: string | null;
  lot_identifier: string | null;
  total_installments: number | null;
}

interface ContractTransferResponse {
  id: string;
  company_id: string;
  client_lot_id: string;
  from_client_id: string;
  to_client_id: string;
  status: 'PENDING' | 'APPROVED' | 'COMPLETED' | 'CANCELLED';
  transfer_fee: number | null;
  transfer_date: string | null;
  reason: string | null;
  admin_notes: string | null;
  from_client_name: string | null;
  to_client_name: string | null;
  lot_identifier: string | null;
}

interface EarlyPayoffResponse {
  id: string;
  company_id: string;
  client_id: string;
  client_lot_id: string;
  status: 'PENDING' | 'CONTACTED' | 'COMPLETED' | 'CANCELLED';
  requested_at: string;
  admin_notes: string | null;
  client_message: string | null;
}

interface DefaulterDetail {
  client_id: string;
  client_name: string;
  cpf_cnpj: string;
  phone: string;
  overdue_invoices: number;
  overdue_amount: number;
  oldest_due_date: string | null;
  days_overdue: number;
}
```

---

## 5. UI/UX Requirements

### 5.1 Sidebar Navigation (Admin)

Add new items under "Financeiro" section:
- **Índices Econômicos** → `/admin/economic-indices`
- **Aprovação de Ciclos** → `/admin/cycle-approvals` (with pending count badge)
- **Transferências** → `/admin/transfers`
- **Antecipações** → `/admin/early-payoff-requests`
- **Extratos Bancários** → `/admin/bank-statements` (with "em breve" badge)

### 5.2 Boleto Tag Display

- All boleto lists and detail views should show the `tag` as a colored badge
- All boleto lists should show `installment_label` (e.g., "Parcela 5/120")
- Filter dropdown for tags on admin boleto listing

### 5.3 Writeoff Indicators

- Boletos with `writeoff_type = 'MANUAL_ADMIN'` should show a distinct badge "Baixa Manual" in orange/red
- Boletos with `writeoff_type = 'AUTOMATICA_BANCO'` show "Baixa Automática" in green
- Writeoff reason should be visible on hover or in detail view

### 5.4 Dashboard Enhancements

- "Inadimplentes" card should be clickable → drill-down table via `/admin/dashboard/defaulters`
- Show `days_overdue` with color coding: 30-59 yellow, 60-89 orange, 90+ red
- Show phone number for quick contact

### 5.5 Client Portal

- "Antecipar Pagamento" button on lot detail page
- Status tracker showing request progress
- "Pagar Agora" button on pending boletos (links to linha digitável or Pix QR)

### 5.6 Color Scheme

Follow the existing design system. Suggested status colors:
- **PENDING**: `yellow-500`
- **APPROVED**: `green-500`
- **REJECTED**: `red-500`
- **COMPLETED**: `blue-500`
- **CANCELLED**: `gray-400`

---

## 6. Permission Changes

| Action | Required Role |
|--------|---------------|
| Manual boleto writeoff (`baixa-manual`) | `SUPER_ADMIN` only |
| Approve/complete contract transfer | `SUPER_ADMIN` only |
| Create economic index | `COMPANY_ADMIN` or `SUPER_ADMIN` |
| Approve/reject cycle | `COMPANY_ADMIN` or `SUPER_ADMIN` |
| Request early payoff | `CLIENT` |
| View own early payoff requests | `CLIENT` |

**Frontend must**:
- Hide "Baixa Manual" button from non-SUPER_ADMIN users
- Hide "Aprovar/Concluir Transferência" buttons from non-SUPER_ADMIN users
- Show appropriate error message if a restricted action is attempted

---

## 7. Notification Types

New notification types the client portal should handle:

| Type | Message Template |
|------|-----------------|
| `CICLO_PENDENTE` | "Seu ciclo de parcelas foi concluído. Aguardando aprovação do novo ciclo." |
| `TRANSFERENCIA_CONTRATO` | "Seu contrato foi transferido." |
| `ANTECIPACAO_SOLICITADA` | "Sua solicitação de antecipação foi recebida." |
| `DISTRATO_AUTOMATICO` | "Seu contrato foi rescindido por inadimplência." |

---

## 8. PWA Considerations

- All new pages should work offline-first where possible (cache list data)
- Push notifications should be triggered for:
  - Cycle approval status changes
  - Transfer completion
  - Early payoff status updates
  - Overdue escalation alerts (30/60/90 days)
- Service worker should cache API responses for dashboard stats and boleto lists
- "Pagar Agora" button should work with deep links to banking apps when on mobile

---

## 9. Per-Client Financial Rules & Global Defaults

This is the **core financial customization feature**. It allows the admin to:
1. Set **global defaults** for the entire company (e.g., penalty 2%, interest 0.033%/day, IPCA index)
2. **Override any rate per client-lot** ("ficha do cliente") — when set, it takes priority over the global default
3. When neither is set, the system uses **hardcoded constants** as last resort

**Fallback chain**: `Per-Lot Override → Company Default → Hardcoded Constant`

### 9.1 Global Company Financial Defaults

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/admin/financial-settings/` | Get current global defaults (auto-creates with system defaults if first access) |
| `PUT` | `/api/v1/admin/financial-settings/` | Update global defaults (only send fields you want to change) |

**Request body** (`PUT`):
```json
{
  "penalty_rate": 0.02,
  "daily_interest_rate": 0.00033,
  "adjustment_index": "IPCA",
  "adjustment_frequency": "ANNUAL",
  "adjustment_custom_rate": 0.05
}
```

**Response** (`GET` and `PUT`):
```typescript
interface CompanyFinancialSettingsResponse {
  id: string;
  company_id: string;
  penalty_rate: number;          // e.g. 0.02 = 2%
  daily_interest_rate: number;   // e.g. 0.00033 = 0.033%/day
  adjustment_index: 'IPCA' | 'IGPM' | 'CUB' | 'INPC';
  adjustment_frequency: 'MONTHLY' | 'QUARTERLY' | 'SEMIANNUAL' | 'ANNUAL';
  adjustment_custom_rate: number; // e.g. 0.05 = 5% fixed rate on top of index
  created_at: string;
  updated_at: string;
}
```

**UI needed**: Admin page "Configurações Financeiras" (or a tab inside Settings):
- Form with 5 fields: multa (%), juros diários (%), índice de reajuste (dropdown), frequência (dropdown), taxa fixa (%)
- Show current values on load (GET)
- Save button calls PUT
- Explain to the user: "Estes valores são usados como padrão para todos os clientes. Você pode sobrescrever individualmente na ficha de cada cliente."

### 9.2 Per-Client-Lot Financial Rules (Override)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/admin/lots/client-lots/{id}` | Get client-lot details with all financial fields |
| `PATCH` | `/api/v1/admin/lots/client-lots/{id}/financial-rules` | Update financial rules for this client-lot |

**Request body** (`PATCH`):
```json
{
  "penalty_rate": 0.03,
  "daily_interest_rate": 0.0005,
  "adjustment_index": "IGPM",
  "adjustment_frequency": "SEMIANNUAL",
  "adjustment_custom_rate": 0.08,
  "annual_adjustment_rate": 0.05
}
```
All fields are **optional**. Only send what you want to change. Send `null` to clear an override (falls back to company default).

**Response**: Full `ClientLotResponse` (see 9.3).

**UI needed**: On the "Ficha do Cliente" (client detail / client-lot detail page), add a **"Regras Financeiras"** section or tab:
- Show current effective values for each field
- Show whether each value is "Custom" (green badge) or "Padrão da empresa" (gray badge)
- Edit button opens a form with the 6 fields
- "Limpar" button next to each field to reset to company default (sends `null`)

### 9.3 Updated ClientLotResponse

The `ClientLotResponse` now includes all financial fields:

```typescript
interface ClientLotResponse {
  id: string;
  company_id: string;
  client_id: string;
  lot_id: string;
  purchase_date: string;
  total_value: number;
  down_payment: number | null;
  total_installments: number;
  current_cycle: number;
  current_installment_value: number | null;
  annual_adjustment_rate: number | null;
  last_adjustment_date: string | null;
  last_cycle_paid_at: string | null;
  // --- NEW FINANCIAL FIELDS ---
  penalty_rate: number | null;          // null = using company default
  daily_interest_rate: number | null;   // null = using company default
  adjustment_index: 'IPCA' | 'IGPM' | 'CUB' | 'INPC' | null; // null = using company default
  adjustment_frequency: 'MONTHLY' | 'QUARTERLY' | 'SEMIANNUAL' | 'ANNUAL' | null;
  adjustment_custom_rate: number | null; // null = using company default
  previous_client_id: string | null;    // filled after contract transfer
  transfer_date: string | null;
  // ---
  payment_plan: object | null;
  status: string;
  created_at: string;
  updated_at: string;
}
```

**Important**: A `null` value means "no per-client override — using company default". The frontend should:
1. Load company defaults via `GET /admin/financial-settings/`
2. For each field, if client-lot value is `null`, display the company default with a "(padrão)" label
3. If client-lot value is set, display it with a "(customizado)" label

### 9.4 Assign Lot with Financial Rules

`POST /api/v1/admin/lots/assign` now accepts optional financial fields:

```json
{
  "client_id": "uuid",
  "lot_id": "uuid",
  "purchase_date": "2026-01-15",
  "total_value": 150000.00,
  "down_payment": 15000.00,
  "total_installments": 228,
  "annual_adjustment_rate": 0.05,
  "penalty_rate": 0.03,
  "daily_interest_rate": 0.0005,
  "adjustment_index": "IGPM",
  "adjustment_frequency": "ANNUAL",
  "adjustment_custom_rate": 0.06,
  "payment_plan": { "first_due": "2026-02-15" }
}
```

If financial fields are **omitted**, the backend automatically loads the company's global defaults. If no company defaults exist, hardcoded system constants are used.

**UI needed**: On the "Atribuir Lote" form, add an expandable "Regras Financeiras" section:
- Collapsed by default with text: "Usando regras padrão da empresa"
- When expanded, shows the 5 financial fields pre-filled with company defaults
- Admin can override any field for this specific client

### 9.5 How the Fallback Works (Visual)

```
┌─────────────────────────────────────────────────────────┐
│                    RATE RESOLUTION                       │
│                                                         │
│  1. Check client_lot.penalty_rate  ──► Has value? USE IT│
│                    │                                    │
│                    ▼ (null)                              │
│  2. Check company_financial_settings.penalty_rate ► USE  │
│                    │                                    │
│                    ▼ (no company settings)               │
│  3. Use hardcoded constant: 0.02 (2%)            ► USE  │
│                                                         │
│  Same logic for: daily_interest_rate,                   │
│  adjustment_index, adjustment_frequency,                │
│  adjustment_custom_rate                                 │
└─────────────────────────────────────────────────────────┘
```

### 9.6 Hardcoded System Constants (Last Resort)

| Field | Hardcoded Value | Description |
|-------|----------------|-------------|
| `penalty_rate` | `0.02` | 2% flat penalty |
| `daily_interest_rate` | `0.00033` | ~1% per month (0.033%/day) |
| `adjustment_index` | `IPCA` | Brazilian consumer price index |
| `adjustment_frequency` | `ANNUAL` | Once per year |
| `adjustment_custom_rate` | `0.05` | 5% fixed rate on top of index |

### 9.7 Complete Frontend Flow

**1. Admin configures company defaults (one-time setup):**
```
GET  /api/v1/admin/financial-settings/     → shows current defaults
PUT  /api/v1/admin/financial-settings/     → updates defaults
```

**2. Admin assigns a lot to a client:**
```
POST /api/v1/admin/lots/assign
  → Send financial fields to override, or omit to use company defaults
  → Backend saves per-lot values (or null if using defaults)
```

**3. Admin edits a client's financial rules later:**
```
GET   /api/v1/admin/lots/client-lots/{id}                    → view current rules
PATCH /api/v1/admin/lots/client-lots/{id}/financial-rules    → update rules
```

**4. System uses rules automatically:**
- Segunda via (penalty + interest calculation)
- Annual adjustments (index + fixed rate)
- Cycle generation (installment value recalculation)

---

## 10. WhatsApp Multi-Provider Integration

> **Migration**: `008_whatsapp_credentials` | **SQL**: `sql/014_whatsapp_credentials.sql`

O sistema suporta dois provedores de WhatsApp por empresa, configurados via painel admin. Ambos podem estar ativos simultaneamente. Apenas um é marcado como `is_default`.

| Provedor | Tipo de mensagem | Gerenciamento de templates |
|----------|-----------------|---------------------------|
| **UAZAPI** | Texto livre | Não |
| **Meta Cloud API** | Apenas templates aprovados | Sim (via admin) |

---

### 10.1 Endpoints de Credenciais

**Base**: `/api/v1/admin/whatsapp`

| Method | Path | Descrição |
|--------|------|-----------|
| `GET` | `/credentials/` | Listar credenciais da empresa |
| `POST` | `/credentials/` | Criar credencial (UAZAPI ou META) |
| `PATCH` | `/credentials/{id}` | Atualizar credencial |
| `DELETE` | `/credentials/{id}` | Desativar credencial (soft delete) |
| `POST` | `/credentials/{id}/set-default` | Definir como provedor padrão |
| `GET` | `/credentials/{id}/status` | Verificar status de conexão |
| `POST` | `/test-message` | Enviar mensagem de teste |

---

### 10.2 Endpoints de Templates (Meta Cloud API apenas)

| Method | Path | Descrição |
|--------|------|-----------|
| `GET` | `/templates/` | Listar templates do WABA |
| `POST` | `/templates/` | Criar novo template |
| `GET` | `/templates/{name}` | Detalhes de um template |
| `DELETE` | `/templates/{name}` | Deletar template |

> Para todos os endpoints de template, pode-se passar `?credential_id=UUID` para especificar qual credencial Meta usar. Se omitido, usa a credencial META ativa da empresa.

---

### 10.3 Schemas

#### Criar Credencial UAZAPI

```typescript
interface CreateUAZAPICredential {
  provider: "UAZAPI";
  uazapi_base_url: string;       // Ex: "https://api.uazapi.com"
  uazapi_instance_token: string; // Token da instância
  is_default?: boolean;
}
```

#### Criar Credencial Meta Cloud API

```typescript
interface CreateMetaCredential {
  provider: "META";
  meta_waba_id: string;           // ID do WhatsApp Business Account
  meta_phone_number_id: string;   // ID do número de telefone
  meta_access_token: string;      // System User Access Token (permanente)
  is_default?: boolean;
}
```

#### Response: Credencial (tokens NUNCA expostos)

```typescript
interface WhatsAppCredentialResponse {
  id: string;                      // UUID
  company_id: string;
  provider: "UAZAPI" | "META";
  is_active: boolean;
  is_default: boolean;

  // UAZAPI: mostra base_url, nunca o token
  uazapi_base_url?: string;

  // Meta: mostra IDs, nunca o access_token
  meta_waba_id?: string;
  meta_phone_number_id?: string;

  connection_status?: "connected" | "disconnected" | "connecting" | "unknown" | "error";
  last_status_check?: string;      // ISO datetime
  created_at: string;
  updated_at: string;
}
```

#### Response: Status de Conexão

```typescript
interface ConnectionStatusResponse {
  connected: boolean;
  status: string;               // "connected" | "disconnected" | "error" | "unknown"
  profile_name?: string;        // Nome do perfil WhatsApp
  phone_number?: string;        // Número conectado
  error?: string;               // Descrição do erro, se houver
}
```

#### Mensagem de Teste

```typescript
interface TestMessageRequest {
  to: string;           // Número no formato internacional: "5511999999999"
  body: string;         // Texto da mensagem (máx 4096 chars)
  credential_id?: string; // UUID. Se omitido, usa o provedor padrão da empresa
}
```

#### Criar Template (Meta)

```typescript
interface CreateTemplateRequest {
  name: string;         // Apenas letras minúsculas, números e underscores
  language: string;     // Ex: "pt_BR"
  category: "UTILITY" | "MARKETING" | "AUTHENTICATION";
  components: TemplateComponent[]; // Formato Meta API
}

interface TemplateResponse {
  id?: string;
  name: string;
  status: "APPROVED" | "PENDING" | "REJECTED";
  category: string;
  language: string;
  components: TemplateComponent[];
}
```

---

### 10.4 UI/UX Recomendado

#### Página Admin — "Configurações WhatsApp" (`/admin/settings/whatsapp`)

**Seção: Provedores Configurados**

- Lista cards, um por credencial criada
- Card mostra: ícone do provedor, status badge (Conectado / Desconectado / Desconhecido), badge "Padrão" se `is_default=true`, `base_url` (UAZAPI) ou `WABA ID` (Meta)
- Botões no card: **Verificar Status**, **Definir como Padrão**, **Editar**, **Desativar**
- Botão principal: **+ Adicionar Provedor**

**Modal: Adicionar Provedor**

1. Selecionar tipo: UAZAPI ou Meta Cloud API
2. Se UAZAPI: campos `URL Base` + `Token da Instância` (input type=password)
3. Se Meta: campos `WABA ID` + `Phone Number ID` + `Access Token` (input type=password)
4. Toggle: "Definir como padrão"

**Ação: Verificar Status**

```
GET /api/v1/admin/whatsapp/credentials/{id}/status
```

Exibir resultado em tempo real:
- ✅ **Conectado** — mostrar nome do perfil e número
- ❌ **Desconectado** — mostrar mensagem de erro
- 🔄 **Verificando...** — loading state enquanto aguarda resposta

**Ação: Enviar Mensagem de Teste**

- Pequeno formulário inline no card: campo número + campo mensagem
- Botão **Enviar Teste** → `POST /api/v1/admin/whatsapp/test-message`
- Exibir toast de sucesso/erro

---

#### Página Admin — "Templates WhatsApp" (`/admin/settings/whatsapp/templates`)

> Visível apenas se houver credencial META ativa.

- Tabela: Nome, Categoria, Idioma, Status (badge colorido), Ações
- Status badges: `APPROVED` = verde, `PENDING` = amarelo, `REJECTED` = vermelho
- Botão **+ Criar Template**
- Botão **Deletar** com confirmação

**Modal: Criar Template**

```
Campos:
- Nome (snake_case, validação regex ^[a-z0-9_]+$)
- Idioma (dropdown: pt_BR, en_US, es_MX...)
- Categoria (UTILITY | MARKETING | AUTHENTICATION)
- Componentes (editor JSON ou builder visual)
```

> **Nota**: Após criar, o template entra em status `PENDING` e precisa de aprovação da Meta (pode levar até 24h). Só templates com status `APPROVED` podem ser enviados.

---

### 10.5 Fluxo de Configuração

```
1. Admin abre "Configurações WhatsApp"
2. Clica em "+ Adicionar Provedor" → seleciona UAZAPI ou META
3. Preenche as credenciais (base_url+token ou waba_id+phone_id+token)
4. Salva → POST /api/v1/admin/whatsapp/credentials/
5. Clica em "Verificar Status" → GET /credentials/{id}/status
   - UAZAPI: mostra se a instância está conectada ao WhatsApp
   - META: valida o access token e mostra o número verificado
6. Clica "Definir como Padrão" se quiser que este provedor seja usado para notificações
7. (META apenas) Vai em "Templates WhatsApp" e cria/gerencia templates
```

---

### 10.6 Considerações de Segurança

- **Tokens nunca são retornados** pela API — o response omite `uazapi_instance_token` e `meta_access_token`
- Ao editar, enviar apenas o campo que mudou (PATCH parcial)
- O campo `is_active` pode ser usado para desabilitar sem deletar
- Máximo de **1 credencial por tipo** por empresa (ex: não é possível ter 2 credenciais UAZAPI na mesma empresa)

---

---

## 11. Gestão de Ciclo de Boletos (12 em 12)

> **Backend version**: migration `009_add_paid_installments`

Esta seção descreve a lógica de criação de boletos em ciclos de 12, o alerta de renovação de ciclo para o admin e o fluxo de reajuste anual.

---

### 11.1 Lógica de Negócio

O fluxo de boletos segue este padrão:

```
1. Cliente compra lote → contrato de N parcelas (ex: 220)
2. Admin gera os primeiros 12 boletos (1° ciclo)
3. Cliente paga as 12 parcelas → ciclo completo
4. Sistema envia notificação ao admin: "Ciclo completo - gerar próximo lote"
5. Admin define o percentual de reajuste e confirma
6. Sistema gera mais 12 boletos com o novo valor reajustado (2° ciclo)
7. Repete até zerar ou cancelar o contrato
```

**Regras importantes:**
- Máximo **12 boletos por lote** (1 ciclo = 12 meses)
- Sempre respeitar o total de parcelas restantes (nunca ultrapassar)
- Cada ciclo pode ter um valor diferente (reajuste anual)

---

### 11.2 Novos Endpoints

| Method | Path | Descrição |
|--------|------|-----------|
| `GET` | `/api/v1/admin/lots/client-lots/{id}/installments` | Info de parcelas (total, pagas, restantes) |
| `POST` | `/api/v1/admin/lots/client-lots/{id}/generate-next-batch?adjustment_rate=0.05` | Prepara próximo ciclo com reajuste |
| `POST` | `/api/v1/admin/sicredi/boletos/batch` | Cria boletos (max 12 por chamada) |

---

### 11.3 Resposta — GET /installments

```json
{
  "client_lot_id": "uuid",
  "total_installments": 220,
  "paid_installments": 12,
  "remaining_installments": 208,
  "current_cycle": 1,
  "next_cycle_number": 2,
  "installments_in_current_cycle": 12,
  "is_legacy_client": false,
  "current_installment_value": 850.00
}
```

**Campos:**
- `total_installments`: Total de parcelas do contrato
- `paid_installments`: Quantas já foram pagas
- `remaining_installments`: Quantas faltam
- `current_cycle`: Ciclo atual (1, 2, 3...)
- `installments_in_current_cycle`: Pagas no ciclo atual (de 0 a 12)
- `is_legacy_client`: `true` se o cliente foi cadastrado manualmente (antes do sistema)

---

### 11.4 Resposta — POST /generate-next-batch

```json
{
  "status": "ready_for_batch",
  "client_lot_id": "uuid",
  "current_cycle": 2,
  "previous_installment_value": 850.00,
  "new_installment_value": 892.50,
  "adjustment_rate": 0.05,
  "remaining_installments": 208,
  "message": "Ciclo 2 preparado. Valor atualizado para R$ 892.50. Use o endpoint de criação de lotes para gerar os 12 boletos."
}
```

---

### 11.5 TypeScript Interfaces

```typescript
interface InstallmentInfo {
  client_lot_id: string;
  total_installments: number;
  paid_installments: number;
  remaining_installments: number;
  current_cycle: number;
  next_cycle_number: number;
  installments_in_current_cycle: number;
  is_legacy_client: boolean;
  current_installment_value: number | null;
}

interface GenerateNextBatchResponse {
  status: 'ready_for_batch';
  client_lot_id: string;
  current_cycle: number;
  previous_installment_value: number;
  new_installment_value: number;
  adjustment_rate: number;
  remaining_installments: number;
  message: string;
}

// Notificação de ciclo completo recebida via notificações
interface CyclePendingNotification {
  type: 'CICLO_PENDENTE';
  data: {
    client_lot_id: string;
    client_id: string;
    current_cycle: number;
    next_cycle: number;
    remaining_installments: number;
    action: 'generate_next_batch';
  };
}
```

---

### 11.6 UI/UX — Cadastro de Cliente (Modal de Atribuição de Lote)

No modal de atribuição de lote ao cliente, adicionar campo:

```
[ ] Cliente já tinha parcelas pagas antes do sistema
    Se marcado:
    → Número de parcelas já pagas: [___]
```

**Campos obrigatórios:**
- `total_installments`: Total de parcelas do contrato
- `paid_installments` *(condicional)*: Parcelas pagas antes do sistema (somente para clientes antigos)

**Regra de validação:**
- `paid_installments` < `total_installments`
- `paid_installments` mínimo 0

---

### 11.7 UI/UX — Card de Informações de Parcelas

Exibir no card/detalhe do contrato do cliente:

```
┌─────────────────────────────────────────────────────┐
│  Parcelas do Contrato                                │
│                                                     │
│  Total: 220        Pagas: 12       Restantes: 208   │
│                                                     │
│  Progresso: [████░░░░░░░░░░░░░░░░░░] 5.5%           │
│                                                     │
│  Ciclo atual: 1     Valor atual: R$ 850,00          │
│  Parcelas no ciclo: 12/12  ✅ Ciclo completo        │
└─────────────────────────────────────────────────────┘
```

**Indicadores:**
- Progresso visual: `paid / total * 100`
- Badge "Ciclo completo" quando `installments_in_current_cycle == 12`
- Badge "Próximo lote pronto" quando `remaining_installments > 0 && installments_in_current_cycle == 12`

---

### 11.8 UI/UX — Notificação de Ciclo Completo (Admin)

Quando o admin receber uma notificação do tipo `CICLO_PENDENTE`:

1. **No sino de notificações:** mostrar badge com contador
2. **Ao clicar na notificação:** abrir modal "Renovar Ciclo"

**Modal "Renovar Ciclo":**

```
┌───────────────────────────────────────────────────────┐
│  🔔 Ciclo 1 Completo — João Silva                     │
│                                                       │
│  Parcelas restantes: 208 de 220                       │
│  Valor atual:  R$ 850,00                              │
│                                                       │
│  Reajuste para o ciclo 2:                             │
│  [  5.00  ] %    ← input numérico (casas decimais)    │
│                                                       │
│  Novo valor estimado: R$ 892,50                       │  ← atualiza em tempo real
│                                                       │
│  [Cancelar]              [Confirmar e Gerar Lote]     │
└───────────────────────────────────────────────────────┘
```

**Ao clicar "Confirmar e Gerar Lote":**

```typescript
// Passo 1: Preparar o próximo ciclo com reajuste
const prepare = await api.post(
  `/admin/lots/client-lots/${clientLotId}/generate-next-batch`,
  null,
  { params: { adjustment_rate: adjustmentRate / 100 } }
);

// Passo 2: Criar os 12 boletos via batch
const batch = await api.post('/admin/sicredi/boletos/batch', {
  client_id: clientId,
  pagador: pagadorData,
  valor: prepare.new_installment_value,
  frequency: 'MENSAL',
  duration_months: Math.min(12, prepare.remaining_installments),
  data_primeiro_vencimento: nextDueDate,
  // ... outros campos financeiros
});
```

**Estados da UI:**
- Loading durante as chamadas
- Sucesso: "✅ 12 boletos gerados para o ciclo 2"
- Erro: mostrar mensagem do backend (ex: "Ciclo ainda não está completo")

---

### 11.9 UI/UX — Limitação Visual de 12 Boletos

No formulário de criação de lote de boletos:

- Campo `duration_months` com `max=12`
- Aviso fixo: "⚠️ Máximo de 12 boletos por lote (1 ciclo)"
- Se o cliente tiver menos de 12 parcelas restantes, sugerir o número exato:

```typescript
const suggestedDuration = Math.min(12, remainingInstallments);
```

---

### 11.10 Verificação Automática de Lote Disponível (Polling / Notificação)

A notificação `CICLO_PENDENTE` é criada automaticamente pela task Celery que roda diariamente. O frontend pode:

**Opção A — Notificações push (recomendada):** Escutar a notificação via polling no endpoint:
```
GET /api/v1/client/notifications/
```
Filtrar por `type = CICLO_PENDENTE` e `is_read = false`.

**Opção B — Badge no card do cliente:**
```typescript
// Verificar se ciclo está completo ao carregar detalhe do contrato
const info = await api.get(`/admin/lots/client-lots/${id}/installments`);
const cycleComplete = info.installments_in_current_cycle >= 12 && info.remaining_installments > 0;
```
Se `cycleComplete`, mostrar botão "Gerar Próximo Lote" no card.

---

## API Base URL

All endpoints are prefixed with `/api/v1/`.

- **Admin endpoints**: `/api/v1/admin/...`
- **Client endpoints**: `/api/v1/client/...`
- **Auth**: `/api/v1/auth/...`
