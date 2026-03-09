# Integração Frontend - Funcionalidades de Contrato

Este documento detalha os novos endpoints e fluxos para integrar as funcionalidades de gestão de contratos no frontend.

---

## 📋 Índice

1. [Histórico de Contrato](#1-histórico-de-contrato-contract-history)
2. [Renegociações](#2-renegociações)
3. [Rescisões/Distratos](#3-rescisõesdistratos)
4. [Segunda Via de Boleto](#4-segunda-via-de-boleto)
5. [Relatórios Mensais](#5-relatórios-mensais-admin)

---

## 1. Histórico de Contrato (Contract History)

### 1.1 Listar Histórico do Cliente

**Endpoint:** `GET /api/v1/admin/contract-history/client/{client_id}`

**Headers:**
```http
Authorization: Bearer {access_token}
```

**Response 200:**
```json
[
  {
    "id": "uuid",
    "company_id": "uuid",
    "client_id": "uuid",
    "client_lot_id": "uuid",
    "invoice_id": "uuid",
    "boleto_id": "uuid",
    "event_type": "PAYMENT",
    "description": "Pagamento da parcela 5 realizado",
    "amount": "1250.00",
    "previous_value": null,
    "new_value": null,
    "metadata_json": {},
    "performed_by": "uuid",
    "ip_address": "192.168.1.1",
    "created_at": "2024-03-09T14:30:00Z"
  }
]
```

**Event Types:**
- `PAYMENT` - Pagamento realizado
- `OVERDUE` - Parcela vencida
- `RENEGOTIATION` - Renegociação criada/aplicada
- `ADJUSTMENT` - Reajuste anual aplicado
- `MANUAL_WRITEOFF` - Baixa manual
- `DISCOUNT_APPLIED` - Desconto concedido
- `PENALTY_REMOVED` - Multa removida
- `BOLETO_ISSUED` - Boleto emitido
- `BOLETO_CANCELLED` - Boleto cancelado
- `SECOND_COPY` - Segunda via emitida
- `RESCISSION_STARTED` - Rescisão iniciada
- `RESCISSION_COMPLETED` - Rescisão finalizada
- `STATUS_CHANGE` - Mudança de status
- `NOTE` - Nota/observação adicionada

### 1.2 Registrar Evento Manualmente

**Endpoint:** `POST /api/v1/admin/contract-history/`

**Payload:**
```json
{
  "client_id": "uuid",
  "client_lot_id": "uuid",
  "event_type": "NOTE",
  "description": "Cliente solicitou prorrogação de vencimento",
  "amount": null,
  "metadata_json": {
    "requested_date": "2024-04-15",
    "reason": "dificuldade financeira temporária"
  }
}
```

**Response 201:** Retorna o evento criado

---

## 2. Renegociações

### 2.1 Consultar Resumo de Dívida

**Endpoint:** `GET /api/v1/admin/renegotiations/debt-summary/{client_id}/{client_lot_id}`

**Response 200:**
```json
{
  "client_id": "uuid",
  "client_lot_id": "uuid",
  "overdue_invoices_count": 5,
  "original_debt": "6250.00",
  "penalty_total": "125.00",
  "interest_total": "206.25",
  "total_debt": "6581.25",
  "overdue_invoices": [
    {
      "id": "uuid",
      "installment_number": 8,
      "due_date": "2023-10-15",
      "amount": "1250.00",
      "days_overdue": 146,
      "penalty": "25.00",
      "interest": "41.25",
      "total_with_fees": "1316.25"
    }
  ]
}
```

### 2.2 Listar Renegociações

**Endpoint:** `GET /api/v1/admin/renegotiations/?status=PENDING_APPROVAL&page=1&per_page=20`

**Query Params:**
- `status` (opcional): `DRAFT`, `PENDING_APPROVAL`, `APPROVED`, `REJECTED`, `APPLIED`, `CANCELLED`
- `client_id` (opcional): Filtrar por cliente
- `page`, `per_page`: Paginação

**Response 200:**
```json
{
  "items": [
    {
      "id": "uuid",
      "company_id": "uuid",
      "client_id": "uuid",
      "client_lot_id": "uuid",
      "status": "PENDING_APPROVAL",
      "original_debt_amount": "6250.00",
      "overdue_invoices_count": 5,
      "penalty_amount": "125.00",
      "interest_amount": "206.25",
      "discount_amount": "0.00",
      "penalty_waived": "62.50",
      "interest_waived": "103.12",
      "final_amount": "6415.63",
      "new_installments": 12,
      "first_due_date": "2024-04-15",
      "reason": "Cliente solicitou parcelamento",
      "admin_notes": null,
      "approved_by": null,
      "approved_at": null,
      "applied_at": null,
      "created_by": "uuid",
      "created_at": "2024-03-09T10:00:00Z",
      "updated_at": "2024-03-09T10:00:00Z"
    }
  ],
  "total": 3,
  "page": 1,
  "per_page": 20,
  "pages": 1
}
```

### 2.3 Criar Renegociação

**Endpoint:** `POST /api/v1/admin/renegotiations/`

**Payload:**
```json
{
  "client_id": "uuid",
  "client_lot_id": "uuid",
  "new_installments": 12,
  "first_due_date": "2024-04-15",
  "discount_amount": 0,
  "penalty_waived": 62.50,
  "interest_waived": 103.12,
  "reason": "Cliente com dificuldades financeiras, mas quer regularizar"
}
```

**Response 201:** Retorna a renegociação criada com status `DRAFT`

### 2.4 Aprovar Renegociação

**Endpoint:** `POST /api/v1/admin/renegotiations/{renego_id}/approve`

**Payload:**
```json
{
  "admin_notes": "Aprovado conforme política de recuperação de crédito"
}
```

**Response 200:** Retorna renegociação com status `APPROVED`

### 2.5 Aplicar Renegociação

**Endpoint:** `POST /api/v1/admin/renegotiations/{renego_id}/apply`

**Response 200:**
```json
{
  "id": "uuid",
  "status": "APPLIED",
  "applied_at": "2024-03-09T14:30:00Z",
  "cancelled_invoice_ids": ["uuid1", "uuid2", "uuid3"],
  "new_invoice_ids": ["uuid4", "uuid5", "uuid6"]
}
```

**Fluxo Completo:**
1. Consultar dívida → `debt-summary`
2. Criar renegociação → `POST /renegotiations/` (status=DRAFT)
3. Aprovar → `POST /{id}/approve` (status=APPROVED)
4. Aplicar → `POST /{id}/apply` (status=APPLIED, cancela boletos antigos, cria novos)

---

## 3. Rescisões/Distratos

### 3.1 Listar Rescisões

**Endpoint:** `GET /api/v1/admin/rescissions/?status=REQUESTED&page=1&per_page=20`

**Query Params:**
- `status` (opcional): `REQUESTED`, `PENDING_APPROVAL`, `APPROVED`, `COMPLETED`, `CANCELLED`
- `client_id` (opcional)
- `page`, `per_page`

**Response 200:**
```json
{
  "items": [
    {
      "id": "uuid",
      "company_id": "uuid",
      "client_id": "uuid",
      "client_lot_id": "uuid",
      "status": "REQUESTED",
      "reason": "Cliente deseja desistir da compra por mudança de cidade",
      "total_paid": "15000.00",
      "total_debt": "2500.00",
      "refund_amount": "12500.00",
      "penalty_amount": "0.00",
      "request_date": "2024-03-05",
      "approval_date": null,
      "completion_date": null,
      "admin_notes": null,
      "document_path": null,
      "requested_by": "uuid",
      "approved_by": null,
      "created_at": "2024-03-05T09:00:00Z",
      "updated_at": "2024-03-05T09:00:00Z"
    }
  ],
  "total": 2,
  "page": 1,
  "per_page": 20,
  "pages": 1
}
```

### 3.2 Criar Rescisão

**Endpoint:** `POST /api/v1/admin/rescissions/`

**Payload:**
```json
{
  "client_id": "uuid",
  "client_lot_id": "uuid",
  "reason": "Cliente solicitou cancelamento por motivos pessoais",
  "penalty_amount": 0,
  "refund_amount": 12500.00,
  "request_date": "2024-03-05"
}
```

**Response 201:** Retorna rescisão criada com status `REQUESTED`

### 3.3 Aprovar Rescisão

**Endpoint:** `POST /api/v1/admin/rescissions/{rescission_id}/approve`

**Payload:**
```json
{
  "admin_notes": "Aprovado conforme análise jurídica",
  "approval_date": "2024-03-09"
}
```

**Response 200:** Status muda para `APPROVED`

### 3.4 Completar Rescisão

**Endpoint:** `POST /api/v1/admin/rescissions/{rescission_id}/complete`

**Payload:**
```json
{
  "completion_date": "2024-03-15",
  "document_path": "rescissions/2024/distrato_cliente_xyz.pdf"
}
```

**Response 200:**
```json
{
  "id": "uuid",
  "status": "COMPLETED",
  "completion_date": "2024-03-15",
  "lot_released": true
}
```

**Obs:** Ao completar, automaticamente:
- Cancela todos os boletos pendentes do cliente
- Marca `client_lot.status = RESCINDED`
- Libera o lote (`lot.status = AVAILABLE`)
- Registra evento no contract_history

---

## 4. Segunda Via de Boleto

### 4.1 Preview de Correção (Admin)

**Endpoint:** `GET /api/v1/admin/segunda-via/preview/{invoice_id}`

**Response 200:**
```json
{
  "invoice_id": "uuid",
  "installment_number": 8,
  "original_amount": "1250.00",
  "penalty": "25.00",
  "interest": "103.12",
  "corrected_amount": "1378.12",
  "days_overdue": 93,
  "new_due_date": "2024-03-09"
}
```

**Cálculo:**
- Multa: 2% sobre valor original
- Juros: 0.033% por dia sobre valor original

### 4.2 Emitir Segunda Via (Admin)

**Endpoint:** `POST /api/v1/admin/segunda-via/issue`

**Payload:**
```json
{
  "invoice_id": "uuid"
}
```

**Response 200:** Retorna preview + gera novo boleto com valor corrigido

### 4.3 Preview Segunda Via (Cliente)

**Endpoint:** `GET /api/v1/client/boletos/segunda-via/preview/{invoice_id}`

**Headers:**
```http
Authorization: Bearer {client_access_token}
```

**Response 200:** Mesmo formato do preview admin, mas cliente só vê suas próprias faturas

### 4.4 Solicitar Segunda Via (Cliente)

**Endpoint:** `POST /api/v1/client/boletos/segunda-via/issue/{invoice_id}`

**Response 200:** Cliente pode auto-emitir segunda via (se configurado)

**Fluxo no Frontend:**
1. Cliente visualiza fatura vencida
2. Exibe botão "Gerar 2ª Via"
3. Chama preview para mostrar valor corrigido
4. Cliente confirma → chama `issue`
5. Redireciona para novo boleto ou exibe código de barras

---

## 5. Relatórios Mensais (Admin)

### 5.1 Fechamento Mensal (JSON)

**Endpoint:** `GET /api/v1/admin/reports/monthly-closure?year=2024&month=3`

**Response 200:**
```json
{
  "period": "2024-03",
  "total_invoices": 145,
  "total_amount_due": "181250.00",
  "paid_invoices": 127,
  "paid_amount": "158750.00",
  "pending_invoices": 15,
  "pending_amount": "18750.00",
  "overdue_invoices": 3,
  "overdue_amount": "3750.00",
  "collection_rate": 87.59,
  "total_clients": 52,
  "active_lots": 48
}
```

### 5.2 Exportar Pagamentos (CSV)

**Endpoint:** `GET /api/v1/admin/reports/monthly-closure/csv?year=2024&month=3`

**Response 200:** CSV file download
```csv
Parcela,Cliente,CPF,Lote,Vencimento,Pagamento,Valor,Status
8,João Silva,123.456.789-00,Lote 15 - Quadra A,2024-03-05,2024-03-04,1250.00,PAID
9,Maria Santos,987.654.321-00,Lote 22 - Quadra B,2024-03-10,2024-03-10,1450.00,PAID
```

### 5.3 Exportar Cancelamentos (CSV)

**Endpoint:** `GET /api/v1/admin/reports/cancellations/csv?year=2024&month=3`

**Response 200:** CSV file download
```csv
Data,Cliente,CPF,Lote,Motivo,Valor_Pago,Valor_Devolver,Status
2024-03-05,João Silva,123.456.789-00,Lote 15,Rescisão amigável,15000.00,12500.00,COMPLETED
```

---

## 📊 Componentes Sugeridos para o Frontend

### 1. Timeline de Histórico
```typescript
interface ContractEvent {
  id: string;
  event_type: string;
  description: string;
  amount?: number;
  created_at: string;
  performed_by?: string;
}

// Componente: <ContractHistoryTimeline events={events} />
```

### 2. Card de Renegociação
```typescript
interface RenegotiationCard {
  status: 'DRAFT' | 'PENDING_APPROVAL' | 'APPROVED' | 'APPLIED';
  original_debt: number;
  final_amount: number;
  waived_amount: number;
  new_installments: number;
  actions: {
    canApprove: boolean;
    canApply: boolean;
    canCancel: boolean;
  };
}
```

### 3. Modal de Segunda Via
```typescript
interface SecondCopyModal {
  invoice: Invoice;
  correction: {
    penalty: number;
    interest: number;
    total: number;
    days_overdue: number;
  };
  onConfirm: () => Promise<void>;
}
```

### 4. Dashboard de Rescisões
```typescript
interface RescissionDashboard {
  pending: Rescission[];
  approved: Rescission[];
  completed: Rescission[];
  stats: {
    total_requests: number;
    total_refunded: number;
    lots_released: number;
  };
}
```

---

## 🔒 Permissões e Roles

| Funcionalidade | SUPER_ADMIN | COMPANY_ADMIN | CLIENT |
|---|---|---|---|
| Ver histórico de contrato | ✅ Todos | ✅ Sua empresa | ❌ |
| Criar renegociação | ✅ | ✅ | ❌ |
| Aprovar renegociação | ✅ | ✅ | ❌ |
| Aplicar renegociação | ✅ | ✅ | ❌ |
| Criar rescisão | ✅ | ✅ | ❌ |
| Aprovar/completar rescisão | ✅ | ✅ | ❌ |
| Preview segunda via | ✅ | ✅ | ✅ Suas faturas |
| Emitir segunda via | ✅ | ✅ | ✅ Suas faturas |
| Relatórios | ✅ | ✅ | ❌ |

---

## ⚠️ Tratamento de Erros

### Erros Comuns

**400 Bad Request:**
```json
{
  "detail": "Invoice is not overdue"
}
```

**403 Forbidden:**
```json
{
  "detail": "You don't have permission to access this resource"
}
```

**404 Not Found:**
```json
{
  "detail": "Invoice not found"
}
```

**422 Unprocessable Entity:**
```json
{
  "detail": "Renegotiation can only be applied when status is APPROVED"
}
```

---

## 🎨 Sugestões de UX

### Renegociação
1. Mostrar calculadora de dívida antes de criar
2. Exibir comparativo: "De R$ 6.581,25 por R$ 6.415,63 em 12x"
3. Timeline de aprovação: DRAFT → PENDING → APPROVED → APPLIED
4. Botão "Aplicar" só aparece após aprovação

### Segunda Via
1. Badge "Vencido há X dias" na lista de faturas
2. Tooltip mostrando cálculo: "Multa 2% + Juros 0,033%/dia"
3. Confirmação antes de emitir: "Novo valor: R$ 1.378,12"

### Rescisão
1. Wizard de 3 etapas: Dados → Revisão → Confirmação
2. Calcular automaticamente total pago vs total a devolver
3. Upload de documento de distrato assinado
4. Status visual: Solicitado → Aprovado → Finalizado

---

## 📝 Notas Importantes

1. **Auditoria:** Todas as operações críticas (criar/aprovar renegociação, rescisão, etc.) são automaticamente registradas no `contract_history` e na tabela `audit_logs`

2. **Notificações:** O backend envia emails automáticos para:
   - Cliente quando renegociação é aprovada
   - Admin quando há clientes com 90+ dias de atraso
   - Admin quando um ciclo de 12 parcelas é completamente pago

3. **Reajuste Anual:** Task do Celery roda todo dia 1º do mês às 02:00 aplicando IPCA + taxa fixa aos contratos

4. **Ciclo de Parcelas:** Novas parcelas só são geradas após o ciclo anterior (12 parcelas) estar totalmente pago

5. **RLS Ativo:** Todos os endpoints respeitam isolamento multi-tenant via Row Level Security
