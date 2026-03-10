# API Portal do Cliente – Documentação para Frontend

> **Base URL**: `/api/v1/client`
> **Autenticação**: Bearer JWT em todas as rotas (header `Authorization: Bearer <token>`)
> **Role mínimo**: `CLIENT` (aceita também `COMPANY_ADMIN` e `SUPER_ADMIN`)

---

## Índice

1. [Autenticação](#1-autenticação)
2. [Perfil do Cliente](#2-perfil-do-cliente)
3. [Boletos (Sicredi)](#3-boletos-sicredi)
4. [Invoices (Parcelas Asaas)](#4-invoices-parcelas-asaas)
5. [Documentos](#5-documentos)
6. [Solicitações de Serviço (Tickets)](#6-solicitações-de-serviço-tickets)
7. [Ordens de Serviço](#7-ordens-de-serviço)
8. [Notificações](#8-notificações)
9. [Dashboard](#9-dashboard)
10. [Indicações (Referrals)](#10-indicações-referrals)
11. [Enums e Tipos](#11-enums-e-tipos)
12. [Notas para Integração](#12-notas-para-integração)

---

## 1. Autenticação

### `POST /api/v1/auth/login`

```json
// Request
{
  "email": "cliente@email.com",
  "password": "senha123"
}

// Response 200
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "role": "CLIENT",
    "full_name": "João Silva",
    "email": "cliente@email.com",
    "company_id": "uuid"
  }
}
```

### `POST /api/v1/auth/refresh`

```json
// Request
{ "refresh_token": "eyJ..." }

// Response 200
{ "access_token": "eyJ...", "token_type": "bearer" }
```

---

## 2. Perfil do Cliente

### `GET /api/v1/client/profile/`

Retorna os dados do perfil do cliente autenticado.

```json
// Response 200
{
  "id": "uuid",
  "profile_id": "uuid",
  "full_name": "João Silva",
  "cpf_cnpj": "123.456.789-00",
  "email": "cliente@email.com",
  "phone": "(11) 99999-0000",
  "contract_number": "CTR-2024-001",
  "matricula": "MAT-001",
  "address": {
    "street": "Rua das Flores",
    "number": "100",
    "city": "São Paulo",
    "state": "SP",
    "zip": "01234-567"
  },
  "status": "ACTIVE",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### `PATCH /api/v1/client/profile/`

Atualiza campos limitados do perfil. **Apenas `email`, `phone` e `address` são editáveis.**

```json
// Request (todos opcionais)
{
  "email": "novo@email.com",
  "phone": "(11) 98888-0000",
  "address": {
    "street": "Rua Nova",
    "number": "200",
    "city": "São Paulo",
    "state": "SP",
    "zip": "01234-567"
  }
}

// Response 200 – mesmo formato do GET
```

---

## 3. Boletos (Sicredi)

### `GET /api/v1/client/boletos/`

Lista todos os boletos do cliente no banco local.

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|-----------|
| `status`  | string | Não | Filtro: `NORMAL`, `LIQUIDADO`, `VENCIDO`, `CANCELADO`, `NEGATIVADO`, `PENDING_APPROVAL` |

```json
// Response 200
[
  {
    "id": "uuid",
    "client_id": "uuid",
    "nosso_numero": "2412345",
    "seu_numero": "INV-001",
    "linha_digitavel": "104...",
    "tipo_cobranca": "NORMAL",
    "data_vencimento": "2024-03-15",
    "data_emissao": "2024-02-15",
    "data_liquidacao": null,
    "valor": 1500.00,
    "valor_liquidacao": null,
    "status": "NORMAL",
    "pagador_data": { "nome": "João", "cpfCnpj": "123..." },
    "created_at": "2024-02-15T10:00:00Z"
  }
]
```

### `GET /api/v1/client/boletos/{nosso_numero}`

Consulta boleto em tempo real na API Sicredi.

```json
// Response 200
{
  "nosso_numero": "2412345",
  "codigo_barras": "10491...",
  "linha_digitavel": "10491...",
  "situacao": "EM ABERTO",
  "data_vencimento": "2024-03-15",
  "valor": 1500.00,
  "pagador": { "nome": "João", "cpfCnpj": "123..." },
  "tipo_cobranca": "NORMAL",
  "txid": null,
  "qr_code": null,
  "seu_numero": "INV-001"
}
```

### `GET /api/v1/client/boletos/{nosso_numero}/pdf`

Download do PDF do boleto. Retorna `application/pdf`.

### `GET /api/v1/client/boletos/segunda-via/preview/{invoice_id}`

Preview da segunda via com multa e juros calculados.

```json
// Response 200
{
  "invoice_id": "uuid",
  "installment_number": 5,
  "original_amount": 1500.00,
  "penalty": 30.00,
  "interest": 15.00,
  "corrected_amount": 1545.00,
  "days_overdue": 30,
  "new_due_date": "2024-04-15"
}
```

### `POST /api/v1/client/boletos/segunda-via/issue/{invoice_id}`

Emite a segunda via efetivamente. Mesmo formato de resposta do preview.

---

## 4. Invoices (Parcelas Asaas)

### `GET /api/v1/client/invoices/`

Lista parcelas do cliente.

| Parâmetro | Tipo | Obrigatório |
|-----------|------|-------------|
| `status`  | string | Não |

```json
// Response 200
[
  {
    "id": "uuid",
    "company_id": "uuid",
    "client_lot_id": "uuid",
    "due_date": "2024-03-15",
    "amount": 1500.00,
    "installment_number": 5,
    "status": "PENDING",
    "asaas_payment_id": "pay_123",
    "barcode": "10491...",
    "payment_url": "https://asaas.com/pay/...",
    "paid_at": null,
    "created_at": "2024-02-01T10:00:00Z",
    "updated_at": "2024-02-01T10:00:00Z"
  }
]
```

### `GET /api/v1/client/invoices/{invoice_id}`

Detalhes de uma parcela específica.

### `GET /api/v1/client/invoices/{invoice_id}/pdf`

Redireciona para URL de pagamento Asaas (`302 Redirect`).

---

## 5. Documentos

### `GET /api/v1/client/documents/`

Lista documentos estruturados do cliente.

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|-----------|
| `document_type` | string | Não | `RG`, `CPF`, `COMPROVANTE_RESIDENCIA`, `CNH`, `CONTRATO`, `OUTROS` |
| `doc_status` | string | Não | `PENDING_REVIEW`, `APPROVED`, `REJECTED`, `EXPIRED` |

```json
// Response 200
[
  {
    "id": "uuid",
    "company_id": "uuid",
    "client_id": "uuid",
    "document_type": "RG",
    "file_name": "rg_frente.pdf",
    "file_path": "companies/uuid/clients/uuid/documents/rg_frente.pdf",
    "file_url": "https://supabase.co/storage/v1/object/public/...",
    "file_size": 245000,
    "description": "RG - frente e verso",
    "status": "PENDING_REVIEW",
    "rejection_reason": null,
    "reviewed_at": null,
    "reviewed_by": null,
    "created_at": "2024-03-01T10:00:00Z",
    "updated_at": "2024-03-01T10:00:00Z"
  }
]
```

### `POST /api/v1/client/documents/upload`

Upload de documento. Usa `multipart/form-data`.

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `file` | File | Sim | PDF, JPG, PNG (max 10MB) |
| `document_type` | string | Sim | `RG`, `CPF`, `COMPROVANTE_RESIDENCIA`, `CNH`, `CONTRATO`, `OUTROS` |
| `description` | string | Não | Descrição livre (max 500 chars) |

```json
// Response 201
{
  "id": "uuid",
  "document_type": "RG",
  "file_name": "rg_frente.pdf",
  "file_url": "https://...",
  "file_size": 245000,
  "status": "PENDING_REVIEW",
  "created_at": "2024-03-01T10:00:00Z"
  // ... demais campos
}
```

### `GET /api/v1/client/documents/{document_id}`

Detalhes de um documento específico.

### `GET /api/v1/client/documents/{document_id}/download`

Redirect (`302`) para URL pública do arquivo.

### `DELETE /api/v1/client/documents/{document_id}`

Remove um documento. **Apenas documentos com status `PENDING_REVIEW` podem ser deletados.**

```
// Response 204 No Content
```

---

## 6. Solicitações de Serviço (Tickets)

Sistema de tickets para o cliente abrir solicitações e acompanhar respostas.

### `POST /api/v1/client/service-requests/`

Cria uma nova solicitação.

```json
// Request
{
  "service_type": "FINANCEIRO",
  "subject": "Dúvida sobre parcela",
  "description": "Gostaria de saber sobre o desconto para pagamento antecipado.",
  "priority": "MEDIUM"
}

// Response 201
{
  "id": "uuid",
  "company_id": "uuid",
  "client_id": "uuid",
  "ticket_number": "REQ-2024-0001",
  "service_type": "FINANCEIRO",
  "subject": "Dúvida sobre parcela",
  "description": "Gostaria de saber...",
  "status": "OPEN",
  "priority": "MEDIUM",
  "assigned_to": null,
  "assignee_name": null,
  "resolved_at": null,
  "created_at": "2024-03-01T10:00:00Z",
  "updated_at": "2024-03-01T10:00:00Z"
}
```

### `GET /api/v1/client/service-requests/`

Lista solicitações do cliente.

| Parâmetro | Tipo | Obrigatório |
|-----------|------|-------------|
| `status` | string | Não |
| `service_type` | string | Não |
| `page` | int | Não (default 1) |
| `per_page` | int | Não (default 20, max 100) |

```json
// Response 200
{
  "items": [ /* ServiceRequestResponse[] */ ],
  "total": 15,
  "page": 1,
  "per_page": 20
}
```

### `GET /api/v1/client/service-requests/{request_id}`

Detalhes com mensagens (exclui mensagens internas do admin).

```json
// Response 200
{
  "id": "uuid",
  "ticket_number": "REQ-2024-0001",
  "service_type": "FINANCEIRO",
  "subject": "Dúvida sobre parcela",
  "status": "IN_PROGRESS",
  "priority": "MEDIUM",
  "assigned_to": "uuid",
  "assignee_name": "Maria Admin",
  "messages": [
    {
      "id": "uuid",
      "request_id": "uuid",
      "author_id": "uuid",
      "author_type": "client",
      "author_name": "João Silva",
      "message": "Gostaria de saber...",
      "is_internal": false,
      "created_at": "2024-03-01T10:00:00Z"
    },
    {
      "id": "uuid",
      "author_type": "admin",
      "author_name": "Maria Admin",
      "message": "Olá João, o desconto é de 5%...",
      "is_internal": false,
      "created_at": "2024-03-01T11:00:00Z"
    }
  ],
  "created_at": "2024-03-01T10:00:00Z",
  "updated_at": "2024-03-01T11:00:00Z"
}
```

### `POST /api/v1/client/service-requests/{request_id}/messages`

Adiciona mensagem a uma solicitação. Não permite em tickets `CLOSED` ou `RESOLVED`.

```json
// Request
{ "message": "Obrigado! E para a próxima parcela?" }

// Response 201
{
  "id": "uuid",
  "request_id": "uuid",
  "author_id": "uuid",
  "author_type": "client",
  "author_name": "João Silva",
  "message": "Obrigado! E para a próxima parcela?",
  "is_internal": false,
  "created_at": "2024-03-01T12:00:00Z"
}
```

---

## 7. Ordens de Serviço

Sistema existente de ordens de serviço (com custo/receita). Diferente dos tickets.

### `GET /api/v1/client/services/types`

Lista tipos de serviço disponíveis.

### `POST /api/v1/client/services/orders`

Solicita uma ordem de serviço.

### `GET /api/v1/client/services/orders`

Lista ordens do cliente.

### `GET /api/v1/client/services/orders/{order_id}`

Detalhes de uma ordem.

---

## 8. Notificações

### `GET /api/v1/client/notifications/`

Lista notificações do usuário.

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|-----------|
| `is_read` | bool | Não | `true` ou `false` |
| `notification_type` | string | Não | Ver enum abaixo |
| `page` | int | Não | default 1 |
| `per_page` | int | Não | default 20, max 100 |

```json
// Response 200
[
  {
    "id": "uuid",
    "company_id": "uuid",
    "user_id": "uuid",
    "title": "Novo boleto emitido",
    "message": "Boleto 2412345 no valor de R$ 1.500,00 com vencimento em 15/03/2024.",
    "type": "BOLETO_EMITIDO",
    "is_read": false,
    "data": {
      "nosso_numero": "2412345",
      "valor": "1500.00",
      "data_vencimento": "2024-03-15"
    },
    "created_at": "2024-03-01T10:00:00Z"
  }
]
```

### `GET /api/v1/client/notifications/unread-count`

```json
// Response 200
{ "unread_count": 3 }
```

### `PATCH /api/v1/client/notifications/{notification_id}/read`

Marca uma notificação como lida.

```json
// Response 200 – NotificationResponse completo
```

### `PATCH /api/v1/client/notifications/read-all`

Marca todas como lidas.

```json
// Response 200
{ "detail": "All notifications marked as read" }
```

---

## 9. Dashboard

### `GET /api/v1/client/dashboard/summary`

```json
// Response 200
{
  "total_lots": 2,
  "next_due_date": "2024-03-15",
  "next_due_amount": 1500.00,
  "pending_invoices": 3,
  "overdue_invoices": 1
}
```

### `GET /api/v1/client/dashboard/my-lots`

Lista lotes vinculados ao cliente.

---

## 10. Indicações (Referrals)

### `POST /api/v1/client/referrals/`

```json
// Request
{
  "referred_name": "Pedro Santos",
  "referred_phone": "(11) 97777-0000",
  "referred_email": "pedro@email.com"
}
```

### `GET /api/v1/client/referrals/`

Lista indicações feitas pelo cliente.

---

## 11. Enums e Tipos

### Status de Documentos (`DocumentStatus`)
| Valor | Descrição |
|-------|-----------|
| `PENDING_REVIEW` | Aguardando análise do admin |
| `APPROVED` | Aprovado |
| `REJECTED` | Rejeitado (ver `rejection_reason`) |
| `EXPIRED` | Expirado |

### Tipo de Documento (`DocumentType`)
| Valor | Descrição |
|-------|-----------|
| `RG` | Documento de identidade |
| `CPF` | CPF |
| `COMPROVANTE_RESIDENCIA` | Comprovante de residência |
| `CNH` | CNH |
| `CONTRATO` | Contrato assinado |
| `OUTROS` | Outros documentos |

### Status de Solicitação (`ServiceRequestStatus`)
| Valor | Descrição |
|-------|-----------|
| `OPEN` | Aberta (aguardando atendimento) |
| `IN_PROGRESS` | Em andamento |
| `WAITING_CLIENT` | Aguardando resposta do cliente |
| `RESOLVED` | Resolvida |
| `CLOSED` | Encerrada |

### Prioridade de Solicitação (`ServiceRequestPriority`)
`LOW` | `MEDIUM` | `HIGH` | `URGENT`

### Tipo de Solicitação (`ServiceRequestType`)
| Valor | Descrição |
|-------|-----------|
| `MANUTENCAO` | Manutenção |
| `SUPORTE` | Suporte geral |
| `FINANCEIRO` | Questões financeiras |
| `DOCUMENTACAO` | Documentação |
| `OUTROS` | Outros |

### Tipo de Notificação (`NotificationType`)
| Valor | Descrição |
|-------|-----------|
| `BOLETO_EMITIDO` | Novo boleto disponível |
| `BOLETO_VENCIDO` | Boleto venceu |
| `PAGAMENTO_CONFIRMADO` | Pagamento confirmado |
| `DOCUMENTO_APROVADO` | Documento aprovado pelo admin |
| `DOCUMENTO_REJEITADO` | Documento rejeitado |
| `SOLICITACAO_ATUALIZADA` | Status de ticket alterado |
| `GERAL` | Notificação geral |

### Status de Boleto (`BoletoStatus`)
`NORMAL` | `LIQUIDADO` | `VENCIDO` | `CANCELADO` | `NEGATIVADO` | `PENDING_APPROVAL`

### Status de Invoice (`InvoiceStatus`)
`PENDING` | `PAID` | `OVERDUE` | `CANCELLED`

### Status do Cliente (`ClientStatus`)
`ACTIVE` | `INACTIVE` | `DEFAULTER` | `RESCINDED`

---

## 12. Notas para Integração

### Autenticação
- Todas as rotas `/client/*` requerem JWT no header `Authorization: Bearer <token>`
- O token é obtido via `POST /api/v1/auth/login`
- Refresh via `POST /api/v1/auth/refresh`
- O backend filtra automaticamente dados pelo `profile_id` do JWT + `company_id`

### Multi-tenancy
- O cliente só vê dados da empresa a que está vinculado
- Não é necessário enviar `company_id` — é extraído do JWT

### Upload de Documentos
- Use `multipart/form-data` (não JSON)
- Formatos aceitos: PDF, JPG, PNG
- Tamanho máximo: 10MB
- O campo `document_type` é obrigatório no form

### Tickets vs Ordens de Serviço
- **Tickets** (`/service-requests`): Sistema de suporte/comunicação com mensagens
- **Ordens de Serviço** (`/services/orders`): Solicitações de serviço com custo associado
- São funcionalidades separadas

### Notificações
- Poll `GET /notifications/unread-count` periodicamente (sugestão: 30s)
- Ou implemente long-polling/WebSocket futuramente
- Notificações são criadas automaticamente pelo backend em eventos relevantes

### Paginação
- Endpoints paginados usam `page` (1-indexed) e `per_page`
- Response inclui `total`, `page`, `per_page` para controle do frontend

### Erros Comuns
| HTTP | Significado |
|------|-------------|
| `400` | Dados inválidos / Violação de regra de negócio |
| `401` | Token ausente ou inválido |
| `403` | Role insuficiente |
| `404` | Recurso não encontrado ou não pertence ao cliente |
| `422` | Validação Pydantic falhou |

---

## Endpoints Admin (para referência do painel administrativo)

### Documentos
- `GET /api/v1/admin/documents/` — Lista documentos (filtros: client_id, status, type)
- `GET /api/v1/admin/documents/pending-count` — Contagem de pendentes
- `GET /api/v1/admin/documents/{id}` — Detalhes
- `PATCH /api/v1/admin/documents/{id}/review` — Aprovar/Rejeitar

```json
// PATCH Request
{ "status": "APPROVED" }
// ou
{ "status": "REJECTED", "rejection_reason": "Documento ilegível" }
```

### Solicitações
- `GET /api/v1/admin/service-requests/` — Lista todas (filtros: client_id, status, type, priority)
- `GET /api/v1/admin/service-requests/stats` — Contagem por status
- `GET /api/v1/admin/service-requests/{id}` — Detalhes com TODAS as mensagens (incluindo internas)
- `PATCH /api/v1/admin/service-requests/{id}` — Atualizar status/priority/assigned_to
- `POST /api/v1/admin/service-requests/{id}/messages?is_internal=false` — Responder (flag `is_internal`)
