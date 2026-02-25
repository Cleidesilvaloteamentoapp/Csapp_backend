# Sicredi Cobranca API Module

Modulo reutilizavel para integracao com a API de Cobranca do Sicredi.
Suporta autenticacao OAuth2, CRUD de boletos, geracao de PDF e gerenciamento de webhooks.

## Arquitetura

```
app/services/sicredi/
├── __init__.py        # Exports publicos do modulo
├── auth.py            # OAuth2 token lifecycle (password + refresh_token)
├── boletos.py         # Operacoes de boleto (criar, consultar, editar, baixar, PDF)
├── client.py          # HTTP client com auto-auth e retry em 401
├── config.py          # Credenciais, URLs por ambiente, constantes
├── exceptions.py      # Hierarquia de excecoes do modulo
├── schemas.py         # Pydantic models para request/response da API Sicredi
├── webhooks.py        # Gerenciamento de contratos de webhook
└── README.md          # Este arquivo
```

## Uso Standalone (Reutilizavel)

O modulo `app/services/sicredi/` e completamente desacoplado do banco de dados
e pode ser copiado para qualquer projeto Python 3.11+ com `httpx` e `pydantic`.

```python
from app.services.sicredi import SicrediClient, SicrediCredentials, SicrediEnvironment

# 1. Configurar credenciais
creds = SicrediCredentials(
    x_api_key="seu-uuid-token",
    username="codigo_beneficiario + cooperativa",
    password="codigo-acesso-internet-banking",
    cooperativa="0100",
    posto="01",
    codigo_beneficiario="12345",
    environment=SicrediEnvironment.SANDBOX,  # ou PRODUCTION
)

# 2. Criar o client (autenticacao automatica)
client = SicrediClient(credentials=creds)

# 3. Criar um boleto
from app.services.sicredi.schemas import CriarBoletoRequest, Pagador

boleto = await client.boletos.criar(CriarBoletoRequest(
    tipoCobranca="NORMAL",  # ou "HIBRIDO" para Pix QR Code
    codigoBeneficiario="12345",
    pagador=Pagador(
        tipoPessoa="PESSOA_FISICA",
        documento="12345678901",
        nome="Joao da Silva",
        endereco="Rua Exemplo, 100",
        cidade="Porto Alegre",
        uf="RS",
        cep="90000000",
    ),
    especieDocumento="DUPLICATA_MERCANTIL_INDICACAO",
    dataVencimento=date(2026, 3, 15),
    valor=Decimal("150.00"),
    seuNumero="INV-001",
))

print(boleto.linhaDigitavel)
print(boleto.codigoBarras)
print(boleto.nossoNumero)
# Para boletos HIBRIDO:
print(boleto.txid)
print(boleto.qrCode)
```

## Consultas

```python
# Por nossoNumero
boleto = await client.boletos.consultar_por_nosso_numero("211001293")

# Por seuNumero (numero interno)
resultado = await client.boletos.consultar_por_seu_numero("INV-001")

# Liquidados por dia
liquidados = await client.boletos.consultar_liquidados_dia("15/03/2026")

# Gerar PDF (2a via)
pdf_bytes = await client.boletos.gerar_pdf("00000000000000000000000000000000000000000000000")
with open("boleto.pdf", "wb") as f:
    f.write(pdf_bytes)
```

## Instrucoes (Edicao)

```python
from app.services.sicredi.schemas import (
    AlterarVencimentoRequest,
    AlterarSeuNumeroRequest,
    AlterarDescontoRequest,
    AlterarJurosRequest,
    ConcederAbatimentoRequest,
)

# Baixar (cancelar) boleto
await client.boletos.baixar("211001293")

# Alterar vencimento
await client.boletos.alterar_vencimento("211001293", AlterarVencimentoRequest(
    dataVencimento=date(2026, 4, 15),
))

# Alterar seuNumero
await client.boletos.alterar_seu_numero("211001293", AlterarSeuNumeroRequest(
    seuNumero="INV-002",
))

# Alterar desconto
await client.boletos.alterar_desconto("211001293", AlterarDescontoRequest(
    valorDesconto1=Decimal("10.00"),
))

# Alterar juros
await client.boletos.alterar_juros("211001293", AlterarJurosRequest(
    valorOuPercentual="2.00",
))

# Conceder abatimento
await client.boletos.conceder_abatimento("211001293", ConcederAbatimentoRequest(
    valorAbatimento=Decimal("5.00"),
))

# Cancelar abatimento
await client.boletos.cancelar_abatimento("211001293")
```

## Webhooks

```python
from app.services.sicredi.schemas import WebhookContratoRequest

# Criar contrato
contrato = await client.webhooks.criar_contrato(WebhookContratoRequest(
    cooperativa="0100",
    posto="01",
    codBeneficiario="12345",
    eventos=["LIQUIDACAO"],
    url="https://sua-api.com/api/v1/webhooks/sicredi",
    urlStatus="ATIVO",
    contratoStatus="ATIVO",
    nomeResponsavel="Admin",
    email="admin@empresa.com",
))

# Consultar contratos
contratos = await client.webhooks.consultar_contratos()

# Alterar contrato
await client.webhooks.alterar_contrato("id-contrato", updated_payload)
```

## Tratamento de Erros

```python
from app.services.sicredi.exceptions import (
    SicrediError,           # Base - qualquer erro
    SicrediAuthError,       # Falha de autenticacao
    SicrediValidationError, # Dados invalidos (4xx)
    SicrediNotFoundError,   # Recurso nao encontrado (404/422)
    SicrediRateLimitError,  # Rate limit (429)
    SicrediTimeoutError,    # Timeout de rede
)

try:
    boleto = await client.boletos.criar(payload)
except SicrediAuthError:
    # Token expirado e refresh tambem falhou
    pass
except SicrediValidationError as e:
    # Dados invalidos - ver e.detail e e.raw_response
    pass
except SicrediNotFoundError:
    # Boleto nao encontrado
    pass
except SicrediError as e:
    # Qualquer outro erro da API
    print(e.detail, e.status_code, e.raw_response)
```

## Autenticacao

O modulo gerencia o ciclo de vida do token automaticamente:

1. **Primeiro request**: autentica via `grant_type=password`
2. **Requests subsequentes**: reutiliza o `access_token` em cache
3. **Token expirando**: renova via `grant_type=refresh_token` (com margem de seguranca de 30s)
4. **Refresh expirado**: re-autentica via password automaticamente
5. **401 inesperado**: invalida tokens e faz retry automatico (1x)

Tokens ficam em memoria no objeto `SicrediCredentials`. Em aplicacoes multi-tenant,
o `sicredi_service.py` persiste os tokens no banco para evitar re-autenticacao
entre reinicializacoes.

## Dependencias

- `httpx` >= 0.24 (HTTP async client)
- `pydantic` >= 2.0 (schemas)
- `structlog` (logging - pode ser removido para uso standalone)

## Integracao neste Projeto (CSApp)

Neste projeto, o modulo e integrado via:

- **`app/services/sicredi_service.py`**: Bridge entre DB (credenciais por empresa) e o SicrediClient
- **`app/models/sicredi_credential.py`**: Model SQLAlchemy para credenciais por tenant
- **`app/schemas/sicredi.py`**: Schemas Pydantic para os endpoints da API
- **`app/api/v1/admin/sicredi.py`**: Endpoints admin (CRUD completo de boletos + credenciais + webhooks)
- **`app/api/v1/client/boletos.py`**: Endpoints cliente (consulta + PDF)
- **`app/api/v1/webhooks_sicredi.py`**: Receptor de webhooks do Sicredi
- **`sql/003_sicredi_rls.sql`**: Politicas RLS para isolamento multi-tenant
- **`alembic/versions/002_add_sicredi_credentials.py`**: Migracao da tabela

### Endpoints Disponiveis

**Admin** (`/api/v1/admin/sicredi/`):
| Metodo | Rota | Descricao |
|--------|------|-----------|
| POST | `/credentials` | Cadastrar credenciais Sicredi |
| GET | `/credentials` | Consultar credenciais ativas |
| PUT | `/credentials/{id}` | Atualizar credenciais |
| DELETE | `/credentials/{id}` | Desativar credenciais |
| POST | `/boletos` | Criar boleto |
| GET | `/boletos/busca/seu-numero/{seuNumero}` | Consultar por seuNumero |
| GET | `/boletos/liquidados/{dia}` | Consultar liquidados por dia |
| GET | `/boletos/pdf/{linhaDigitavel}` | Gerar PDF (2a via) |
| GET | `/boletos/{nossoNumero}` | Consultar por nossoNumero |
| PATCH | `/boletos/{nossoNumero}/baixa` | Cancelar boleto |
| PATCH | `/boletos/{nossoNumero}/data-vencimento` | Alterar vencimento |
| PATCH | `/boletos/{nossoNumero}/seu-numero` | Alterar seuNumero |
| PATCH | `/boletos/{nossoNumero}/desconto` | Alterar desconto |
| PATCH | `/boletos/{nossoNumero}/juros` | Alterar juros |
| PATCH | `/boletos/{nossoNumero}/conceder-abatimento` | Conceder abatimento |
| PATCH | `/boletos/{nossoNumero}/cancelar-abatimento` | Cancelar abatimento |
| POST | `/webhook/contrato` | Criar contrato webhook |
| GET | `/webhook/contratos` | Consultar contratos |
| PUT | `/webhook/contrato/{id}` | Alterar contrato |

**Cliente** (`/api/v1/client/boletos/`):
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/{nossoNumero}` | Consultar boleto |
| GET | `/{nossoNumero}/pdf` | Baixar PDF do boleto |

**Webhook** (`/api/v1/webhooks/`):
| Metodo | Rota | Descricao |
|--------|------|-----------|
| POST | `/sicredi` | Receptor de eventos do Sicredi |
