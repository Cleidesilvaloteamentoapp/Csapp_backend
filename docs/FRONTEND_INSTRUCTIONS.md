# Frontend Instructions — Client Adjustments & Financial Management Enhancement

> **Backend version**: migration `006_client_adjustments`
> **Date**: March 2026

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

## API Base URL

All endpoints are prefixed with `/api/v1/`.

- **Admin endpoints**: `/api/v1/admin/...`
- **Client endpoints**: `/api/v1/client/...`
- **Auth**: `/api/v1/auth/...`
