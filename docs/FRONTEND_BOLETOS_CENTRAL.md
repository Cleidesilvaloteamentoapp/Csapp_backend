# Central de Boletos — Documentação de Integração Frontend

Este documento consolida **todos** os endpoints disponíveis para a Central de Boletos, organizados por categoria.

**Base URL:** `/api/v1`

---

## 📋 Índice

1. [CRUD Local (Banco de Dados)](#1-crud-local-banco-de-dados)
2. [Criação de Boleto (Sicredi)](#2-criação-de-boleto-sicredi)
3. [Consultas Sicredi (API Bancária)](#3-consultas-sicredi-api-bancária)
4. [Instruções de Boleto (Operações Sicredi)](#4-instruções-de-boleto-operações-sicredi)
5. [Segunda Via (com Multa/Juros)](#5-segunda-via-com-multajuros)
6. [Endpoints do Cliente](#6-endpoints-do-cliente)
7. [Status e Fluxos](#7-status-e-fluxos)
8. [Tratamento de Erros](#8-tratamento-de-erros)

---

## 1. CRUD Local (Banco de Dados)

Endpoints para gerenciar boletos persistidos no banco local. Todos exigem role `COMPANY_ADMIN` ou `SUPER_ADMIN`.

### 1.1 Listar Boletos (com filtros)

**`GET /admin/boletos`**

| Query Param | Tipo | Descrição |
|---|---|---|
| `client_id` | UUID | Filtrar por cliente |
| `status` | string | `NORMAL`, `LIQUIDADO`, `VENCIDO`, `CANCELADO`, `NEGATIVADO` |
| `data_vencimento_inicio` | date | Início do período (YYYY-MM-DD) |
| `data_vencimento_fim` | date | Fim do período (YYYY-MM-DD) |
| `seu_numero` | string | Busca parcial por número interno |
| `limit` | int | Máximo de resultados (1-200, default 50) |
| `offset` | int | Paginação |

**Response 200:**
```json
[
  {
    "id": "uuid",
    "nosso_numero": "123456789",
    "seu_numero": "INV-001",
    "linha_digitavel": "74891...",
    "codigo_barras": "74891...",
    "tipo_cobranca": "NORMAL",
    "data_vencimento": "2024-04-15",
    "data_emissao": "2024-03-01",
    "data_liquidacao": null,
    "valor": "1250.00",
    "valor_liquidacao": null,
    "status": "NORMAL",
    "txid": null,
    "qr_code": null,
    "created_at": "2024-03-01T10:00:00Z",
    "updated_at": "2024-03-01T10:00:00Z",
    "client": {
      "id": "uuid",
      "full_name": "João Silva",
      "cpf_cnpj": "12345678900",
      "email": "joao@email.com",
      "phone": "51999998888"
    }
  }
]
```

---

### 1.2 Dashboard de Estatísticas

**`GET /admin/boletos/stats`**

**Response 200:**
```json
{
  "by_status": [
    { "status": "NORMAL", "count": 45, "total_value": 56250.00 },
    { "status": "LIQUIDADO", "count": 120, "total_value": 150000.00 },
    { "status": "VENCIDO", "count": 8, "total_value": 10000.00 },
    { "status": "CANCELADO", "count": 3, "total_value": 3750.00 },
    { "status": "NEGATIVADO", "count": 2, "total_value": 2500.00 }
  ],
  "overdue_count": 8
}
```

---

### 1.3 Detalhe por ID

**`GET /admin/boletos/id/{boleto_id}`**

**Response 200:** Objeto completo do boleto (mesmo schema da listagem, sem `client` aninhado).

---

### 1.4 Detalhe por Nosso Número

**`GET /admin/boletos/nosso-numero/{nosso_numero}`**

**Response 200:** Objeto completo do boleto.

---

### 1.5 Boletos por Cliente

**`GET /admin/boletos/client/{client_id}?status=VENCIDO`**

**Response 200:** Lista de boletos do cliente (filtro opcional por status).

---

### 1.6 Atualizar Boleto

**`PATCH /admin/boletos/{boleto_id}`**

**Payload:**
```json
{
  "status": "LIQUIDADO",
  "data_liquidacao": "2024-04-10",
  "valor_liquidacao": "1250.00"
}
```

---

### 1.7 Cancelar Boleto (soft delete)

**`DELETE /admin/boletos/{boleto_id}`**

**Response 204:** Marca status como `CANCELADO`.

---

## 2. Criação de Boleto (Sicredi)

### 2.1 Criar Boleto

**`POST /admin/sicredi/boletos`**

Cria o boleto na API Sicredi e persiste no banco local.

**Payload:**
```json
{
  "tipo_cobranca": "NORMAL",
  "pagador": {
    "tipo_pessoa": "PESSOA_FISICA",
    "documento": "12345678900",
    "nome": "João Silva",
    "endereco": "Rua das Flores 123",
    "cidade": "Porto Alegre",
    "uf": "RS",
    "cep": "90000000",
    "email": "joao@email.com",
    "telefone": "51999998888"
  },
  "especie_documento": "DUPLICATA_MERCANTIL_INDICACAO",
  "data_vencimento": "2024-04-15",
  "valor": 1250.00,
  "seu_numero": "INV-001",
  "client_id": "uuid",
  "invoice_id": "uuid",
  "tipo_juros": "VALOR_DIA",
  "juros": 0.41,
  "tipo_multa": "PERCENTUAL",
  "multa": 2.00,
  "dias_negativacao_auto": 60,
  "informativos": ["Parcela 5 de 120"],
  "mensagens": ["Após vencimento cobrar multa de 2%"]
}
```

**Response 201:**
```json
{
  "boleto_id": "uuid",
  "client_id": "uuid",
  "linha_digitavel": "74891.12345 67890.123456 78901.234567 1 90000000125000",
  "codigo_barras": "74891900000001250012345678901234567890123456",
  "nosso_numero": "123456789",
  "txid": null,
  "qr_code": null
}
```

**Obs:** Para boleto híbrido (com Pix), use `tipo_cobranca: "HIBRIDO"` — retornará `txid` e `qr_code`.

---

## 3. Consultas Sicredi (API Bancária)

Consultas em tempo real diretamente na API Sicredi. Retornam a situação atualizada do boleto no banco.

### 3.1 Consultar por Nosso Número

**`GET /admin/sicredi/boletos/{nosso_numero}`**

**Response 200:**
```json
{
  "nosso_numero": "123456789",
  "codigo_barras": "74891...",
  "linha_digitavel": "74891...",
  "situacao": "EM CARTEIRA",
  "data_vencimento": "2024-04-15",
  "valor": "1250.00",
  "pagador": {
    "nome": "João Silva",
    "documento": "12345678900"
  },
  "tipo_cobranca": "NORMAL",
  "txid": null,
  "qr_code": null,
  "seu_numero": "INV-001",
  "raw_data": {}
}
```

**Situações possíveis:** `EM CARTEIRA`, `VENCIDO`, `LIQUIDADO`, `BAIXADO POR SOLICITACAO`, `PROTESTADO`, `NEGATIVADO`

---

### 3.2 Consultar por Seu Número

**`GET /admin/sicredi/boletos/busca/seu-numero/{seu_numero}`**

**Response 200:** Dados brutos da API Sicredi.

---

### 3.3 Consultar Liquidados por Dia

**`GET /admin/sicredi/boletos/liquidados/{dia}`**

- `dia` no formato `DD/MM/YYYY`

**Response 200:** Lista de boletos liquidados naquela data.

---

### 3.4 Gerar PDF (2ª via bancária)

**`GET /admin/sicredi/boletos/pdf/{linha_digitavel}`**

**Response 200:** Arquivo PDF (`application/pdf`) — retorna bytes do boleto para download.

---

## 4. Instruções de Boleto (Operações Sicredi)

Comandos enviados à API Sicredi para alterar o estado ou condições de um boleto. Todas as operações que alteram status (baixa, negativação, sustar) **atualizam automaticamente** o boleto no banco local.

### 4.1 Pedido de Baixa (Cancelar)

**`PATCH /admin/sicredi/boletos/{nosso_numero}/baixa`**

Cancela o boleto na carteira do Sicredi. **Body vazio.**

**Response 200:**
```json
{
  "status": "ok",
  "detail": "Boleto cancelled",
  "response": {
    "transactionId": "uuid",
    "statusComando": "MOVIMENTO_ENVIADO",
    "tipoMensagem": "BAIXA",
    "dataHoraRegistro": "2024-03-09T14:30:00"
  }
}
```

**Efeito local:** Status do boleto atualizado para `CANCELADO`.

---

### 4.2 Alterar Vencimento

**`PATCH /admin/sicredi/boletos/{nosso_numero}/data-vencimento`**

**Payload:**
```json
{
  "data_vencimento": "2024-05-15"
}
```

**Response 200:**
```json
{
  "status": "ok",
  "detail": "Due date updated",
  "response": {
    "transactionId": "uuid",
    "statusComando": "MOVIMENTO_ENVIADO",
    "tipoMensagem": "ALTERA_VENCIMENTO"
  }
}
```

---

### 4.3 Alterar Juros

**`PATCH /admin/sicredi/boletos/{nosso_numero}/juros`**

**Payload:**
```json
{
  "valor_ou_percentual": "0.50"
}
```

**Response 200:**
```json
{
  "status": "ok",
  "detail": "Interest updated",
  "response": {
    "transactionId": "uuid",
    "statusComando": "MOVIMENTO_ENVIADO",
    "tipoMensagem": "ALTERA_JUROS"
  }
}
```

---

### 4.4 Alterar Desconto

**`PATCH /admin/sicredi/boletos/{nosso_numero}/desconto`**

**Payload:**
```json
{
  "valor_desconto_1": "50.00",
  "valor_desconto_2": "25.00",
  "valor_desconto_3": null
}
```

---

### 4.5 Conceder Abatimento

**`PATCH /admin/sicredi/boletos/{nosso_numero}/conceder-abatimento`**

**Payload:**
```json
{
  "valor_abatimento": "100.00"
}
```

**Response 200:**
```json
{
  "status": "ok",
  "detail": "Abatement granted",
  "response": {
    "transactionId": "uuid",
    "statusComando": "MOVIMENTO_ENVIADO",
    "tipoMensagem": "PEDIDO_ABATIMENTO"
  }
}
```

---

### 4.6 Cancelar Abatimento

**`PATCH /admin/sicredi/boletos/{nosso_numero}/cancelar-abatimento`**

**Body vazio.** Cancela um abatimento concedido anteriormente.

---

### 4.7 Alterar Seu Número

**`PATCH /admin/sicredi/boletos/{nosso_numero}/seu-numero`**

**Payload:**
```json
{
  "seu_numero": "INV-002"
}
```

---

### 4.8 Incluir Negativação

**`PATCH /admin/sicredi/boletos/{nosso_numero}/negativacao`**

Solicita a negativação de um boleto **vencido**. **Body vazio.**

**Response 200:**
```json
{
  "status": "ok",
  "detail": "Negativation requested",
  "response": {
    "transactionId": "uuid",
    "statusComando": "MOVIMENTO_ENVIADO",
    "tipoMensagem": "PEDIDO_NEGATIVACAO",
    "dataHoraRegistro": "2024-03-09T14:30:00"
  }
}
```

**Efeito local:** Status do boleto atualizado para `NEGATIVADO`.

**Regras de negócio:**
- Título precisa estar **vencido**
- Não pode estar liquidado, baixado ou em carteira descontada
- Não pode estar aguardando confirmação de registro

---

### 4.9 Excluir Negativação e Baixar Título

**`PATCH /admin/sicredi/boletos/{nosso_numero}/sustar-negativacao-baixar-titulo`**

Cancela a negativação ativa e simultaneamente realiza a baixa do boleto. **Body vazio.**

**Response 200:**
```json
{
  "status": "ok",
  "detail": "Negativation cancelled and boleto baixado",
  "response": {
    "transactionId": "uuid",
    "statusComando": "MOVIMENTO_ENVIADO",
    "tipoMensagem": "PEDIDO_SUSTAR_BAIXAR_NEGATIVACAO",
    "dataHoraRegistro": "2024-03-09T14:30:00"
  }
}
```

**Efeito local:** Status do boleto atualizado para `CANCELADO`.

**Regras de negócio:**
- Título precisa ter uma negativação ativa
- Não pode estar em carteira descontada
- Não pode estar já liquidado ou baixado

---

## 5. Segunda Via (com Multa/Juros)

### 5.1 Preview de Correção (Admin)

**`GET /admin/segunda-via/preview/{invoice_id}`**

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

**Cálculo:** Multa 2% + Juros 0,033%/dia sobre o valor original.

### 5.2 Emitir Segunda Via (Admin)

**`POST /admin/segunda-via/issue`**

**Payload:**
```json
{
  "invoice_id": "uuid"
}
```

---

## 6. Endpoints do Cliente

Endpoints acessíveis com role `CLIENT`. Dados filtrados automaticamente pelo RLS.

### 6.1 Consultar Boleto

**`GET /client/boletos/{nosso_numero}`**

### 6.2 Download PDF

**`GET /client/boletos/{nosso_numero}/pdf`**

### 6.3 Preview Segunda Via

**`GET /client/boletos/segunda-via/preview/{invoice_id}`**

### 6.4 Solicitar Segunda Via

**`POST /client/boletos/segunda-via/issue/{invoice_id}`**

---

## 7. Status e Fluxos

### 7.1 Status do Boleto (BoletoStatus)

| Status | Descrição | Cor sugerida |
|---|---|---|
| `NORMAL` | Boleto ativo, em carteira | 🟢 Verde |
| `LIQUIDADO` | Pagamento confirmado | 🔵 Azul |
| `VENCIDO` | Passou da data de vencimento sem pagamento | 🟡 Amarelo |
| `CANCELADO` | Baixado/cancelado | ⚫ Cinza |
| `NEGATIVADO` | Em processo de negativação (Serasa/SPC) | 🔴 Vermelho |
| `PENDING_APPROVAL` | Aguardando aprovação administrativa | 🟠 Laranja |

### 7.2 Fluxo de Vida do Boleto

```
CRIAÇÃO → NORMAL → LIQUIDADO (pagamento confirmado via webhook)
                  → VENCIDO (data passou, task automática)
                       → NEGATIVADO (admin solicita negativação)
                            → CANCELADO (admin susta negativação + baixa)
                       → CANCELADO (admin solicita baixa)
                  → CANCELADO (admin cancela antes do vencimento)
```

### 7.3 Mapa de Ações por Status

| Status Atual | Ações Disponíveis |
|---|---|
| `NORMAL` | Baixa, Alterar Vencimento, Alterar Juros, Alterar Desconto, Conceder Abatimento, Cancelar Abatimento, Alterar Seu Número, Gerar PDF |
| `VENCIDO` | Baixa, Negativação, Alterar Vencimento, Alterar Juros, Conceder Abatimento, Segunda Via, Gerar PDF |
| `NEGATIVADO` | Sustar Negativação + Baixar, Gerar PDF |
| `LIQUIDADO` | Gerar PDF (apenas consulta) |
| `CANCELADO` | Nenhuma (apenas consulta) |

---

## 8. Tratamento de Erros

### 8.1 Erros da API Sicredi

| Status | Causa | Ação no Frontend |
|---|---|---|
| **401** | Token expirado ou credenciais inválidas | Solicitar recadastro das credenciais Sicredi |
| **422** | Regra de negócio violada (título já baixado, já liquidado, etc.) | Exibir mensagem detalhada ao admin |
| **429** | Rate limit excedido | Aguardar e tentar novamente (exponential backoff) |
| **502** | Erro de comunicação com Sicredi | Exibir erro temporário, tentar novamente |

### 8.2 Erros Locais

| Status | Causa |
|---|---|
| **400** | Status inválido ou parâmetros incorretos |
| **403** | Sem permissão (role insuficiente) |
| **404** | Boleto ou cliente não encontrado |

### 8.3 Formato de Erro

```json
{
  "detail": "Título já baixado, liquidado ou em fluxo de negativação/protesto."
}
```

---

## 📊 Componentes Sugeridos para o Frontend

### Central de Boletos — Layout

```
┌─────────────────────────────────────────────────────┐
│  📊 Dashboard de Estatísticas (GET /boletos/stats)  │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────────┐  │
│  │Normal│ │Liquid│ │Venc. │ │Cancel│ │Negativado│  │
│  │  45  │ │ 120  │ │  8   │ │  3   │ │    2     │  │
│  └──────┘ └──────┘ └──────┘ └──────┘ └──────────┘  │
├─────────────────────────────────────────────────────┤
│  🔍 Filtros: [Cliente▾] [Status▾] [Data▾] [Buscar] │
├─────────────────────────────────────────────────────┤
│  📋 Lista de Boletos (GET /boletos)                 │
│  ┌─────────┬──────────┬────────┬────────┬────────┐  │
│  │NN       │ Cliente  │ Valor  │ Venc.  │ Status │  │
│  ├─────────┼──────────┼────────┼────────┼────────┤  │
│  │123456789│ João S.  │1250.00 │15/04/24│ 🟢NORM │  │
│  │123456790│ Maria S. │1450.00 │10/03/24│ 🟡VENC │  │
│  │123456791│ Pedro C. │ 980.00 │01/02/24│ 🔴NEG  │  │
│  └─────────┴──────────┴────────┴────────┴────────┘  │
├─────────────────────────────────────────────────────┤
│  ⚡ Ações do Boleto (ao clicar em um boleto):       │
│  [Consultar Sicredi] [PDF] [Baixa] [Alt.Venc]      │
│  [Alt.Juros] [Abatimento] [Negativar] [2ªVia]      │
└─────────────────────────────────────────────────────┘
```

### Tipos TypeScript

```typescript
interface BoletoStatus {
  NORMAL: 'NORMAL';
  LIQUIDADO: 'LIQUIDADO';
  VENCIDO: 'VENCIDO';
  CANCELADO: 'CANCELADO';
  NEGATIVADO: 'NEGATIVADO';
  PENDING_APPROVAL: 'PENDING_APPROVAL';
}

interface Boleto {
  id: string;
  nosso_numero: string;
  seu_numero: string;
  linha_digitavel: string;
  codigo_barras: string;
  tipo_cobranca: 'NORMAL' | 'HIBRIDO';
  data_vencimento: string;
  data_emissao: string;
  data_liquidacao?: string;
  valor: number;
  valor_liquidacao?: number;
  status: keyof BoletoStatus;
  txid?: string;
  qr_code?: string;
  created_at: string;
  updated_at: string;
  client?: BoletoClient;
}

interface BoletoClient {
  id: string;
  full_name: string;
  cpf_cnpj: string;
  email: string;
  phone: string;
}

interface BoletoStats {
  by_status: Array<{
    status: string;
    count: number;
    total_value: number;
  }>;
  overdue_count: number;
}

// Map de ações disponíveis por status
const ACTIONS_BY_STATUS: Record<string, string[]> = {
  NORMAL: ['baixa', 'data-vencimento', 'juros', 'desconto', 'conceder-abatimento', 'cancelar-abatimento', 'seu-numero', 'pdf'],
  VENCIDO: ['baixa', 'negativacao', 'data-vencimento', 'juros', 'conceder-abatimento', 'segunda-via', 'pdf'],
  NEGATIVADO: ['sustar-negativacao-baixar-titulo', 'pdf'],
  LIQUIDADO: ['pdf'],
  CANCELADO: [],
  PENDING_APPROVAL: [],
};
```

---

## 🔒 Permissões

| Funcionalidade | SUPER_ADMIN | COMPANY_ADMIN | CLIENT |
|---|---|---|---|
| CRUD boletos (local) | ✅ | ✅ | ❌ |
| Criar boleto (Sicredi) | ✅ | ✅ | ❌ |
| Consultar Sicredi | ✅ | ✅ | ✅ (próprios) |
| Instruções (baixa, venc., juros, etc.) | ✅ | ✅ | ❌ |
| Negativação | ✅ | ✅ | ❌ |
| Sustar Negativação | ✅ | ✅ | ❌ |
| PDF | ✅ | ✅ | ✅ (próprios) |
| Segunda Via | ✅ | ✅ | ✅ (próprios) |
| Dashboard / Stats | ✅ | ✅ | ❌ |

---

## 📝 SQL para Supabase

Antes de usar o status `NEGATIVADO`, execute no SQL Editor do Supabase:

```sql
ALTER TYPE boleto_status ADD VALUE IF NOT EXISTS 'NEGATIVADO';
```

---

## 🔗 Resumo de Endpoints

### Admin — CRUD Local (`/admin/boletos`)
| Método | Endpoint | Descrição |
|---|---|---|
| GET | `/admin/boletos` | Listar com filtros |
| GET | `/admin/boletos/stats` | Dashboard estatísticas |
| GET | `/admin/boletos/id/{id}` | Detalhe por ID |
| GET | `/admin/boletos/nosso-numero/{nn}` | Detalhe por nossoNumero |
| GET | `/admin/boletos/client/{client_id}` | Listar por cliente |
| PATCH | `/admin/boletos/{id}` | Atualizar dados |
| DELETE | `/admin/boletos/{id}` | Soft delete |

### Admin — Sicredi API (`/admin/sicredi`)
| Método | Endpoint | Descrição |
|---|---|---|
| POST | `/admin/sicredi/boletos` | Criar boleto |
| GET | `/admin/sicredi/boletos/{nn}` | Consultar no Sicredi |
| GET | `/admin/sicredi/boletos/busca/seu-numero/{sn}` | Consultar por seuNumero |
| GET | `/admin/sicredi/boletos/liquidados/{dia}` | Liquidados por dia |
| GET | `/admin/sicredi/boletos/pdf/{ld}` | Gerar PDF |
| PATCH | `/admin/sicredi/boletos/{nn}/baixa` | Cancelar boleto |
| PATCH | `/admin/sicredi/boletos/{nn}/data-vencimento` | Alterar vencimento |
| PATCH | `/admin/sicredi/boletos/{nn}/juros` | Alterar juros |
| PATCH | `/admin/sicredi/boletos/{nn}/desconto` | Alterar desconto |
| PATCH | `/admin/sicredi/boletos/{nn}/conceder-abatimento` | Conceder abatimento |
| PATCH | `/admin/sicredi/boletos/{nn}/cancelar-abatimento` | Cancelar abatimento |
| PATCH | `/admin/sicredi/boletos/{nn}/seu-numero` | Alterar seuNumero |
| PATCH | `/admin/sicredi/boletos/{nn}/negativacao` | Incluir negativação |
| PATCH | `/admin/sicredi/boletos/{nn}/sustar-negativacao-baixar-titulo` | Sustar negativação + baixa |

### Admin — Segunda Via (`/admin/segunda-via`)
| Método | Endpoint | Descrição |
|---|---|---|
| GET | `/admin/segunda-via/preview/{invoice_id}` | Preview com correção |
| POST | `/admin/segunda-via/issue` | Emitir segunda via |

### Cliente (`/client/boletos`)
| Método | Endpoint | Descrição |
|---|---|---|
| GET | `/client/boletos/{nn}` | Consultar boleto |
| GET | `/client/boletos/{nn}/pdf` | Download PDF |
| GET | `/client/boletos/segunda-via/preview/{invoice_id}` | Preview segunda via |
| POST | `/client/boletos/segunda-via/issue/{invoice_id}` | Solicitar segunda via |

### Credenciais Sicredi (`/admin/sicredi/credentials`)
| Método | Endpoint | Descrição |
|---|---|---|
| POST | `/admin/sicredi/credentials` | Cadastrar credenciais |
| GET | `/admin/sicredi/credentials` | Consultar credenciais |
| PUT | `/admin/sicredi/credentials/{id}` | Atualizar credenciais |
| DELETE | `/admin/sicredi/credentials/{id}` | Desativar credenciais |

### Webhooks (`/admin/sicredi/webhook`)
| Método | Endpoint | Descrição |
|---|---|---|
| POST | `/admin/sicredi/webhook/contrato` | Registrar webhook |
| GET | `/admin/sicredi/webhook/contratos` | Listar webhooks |
| PUT | `/admin/sicredi/webhook/contrato/{id}` | Alterar webhook |

**Total: 31 endpoints** disponíveis na Central de Boletos.
