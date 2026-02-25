# Sicredi - Troubleshooting de Autenticação

## ⚠️ Erro HTTP 403: "Access denied for this environment"

### Causa Raiz
Este erro indica que as credenciais fornecidas **não são válidas** ou **não estão autorizadas** para o ambiente especificado (sandbox ou production).

---

## 🔍 Checklist de Validação

### 1. Verificar Credenciais no Portal Sicredi

#### x_api_key (Token UUID)
- **Onde obter:** Portal do Desenvolvedor Sicredi → Minhas Aplicações → API Key
- **Formato:** UUID (ex: `3221c1b4-5678-90ab-cdef-1234567890ab`)
- **Importante:** 
  - ✅ Cada ambiente (sandbox/production) tem uma API Key **diferente**
  - ✅ Verifique se a API Key está **ativa** no portal
  - ✅ Confirme que a API está habilitada para **Cobrança**

#### username (Código Beneficiário + Cooperativa)
- **Formato correto:** Concatenação de `codigo_beneficiario` + `cooperativa`
- **Exemplo:** 
  - Se `codigo_beneficiario = "12345"` e `cooperativa = "0100"`
  - Então `username = "123450100"` OU apenas `"12345"` (depende da configuração)

**⚠️ ATENÇÃO:** A documentação Sicredi não é clara sobre isso. Teste as duas opções:
1. Apenas o `codigo_beneficiario` (ex: `"12345"`)
2. `codigo_beneficiario` + `cooperativa` (ex: `"123450100"`)

#### password (Código de Acesso)
- **Onde obter:** Internet Banking Sicredi → Configurações → API Cobrança → Gerar Código de Acesso
- **Importante:**
  - ❌ **NÃO** é a senha do Internet Banking
  - ✅ É um código específico gerado para API
  - ✅ Código pode expirar - regenere se necessário
  - ✅ Sandbox pode ter código diferente de produção

#### cooperativa e posto
- **Formato:** Numérico, geralmente 4 dígitos (cooperativa) e 2 dígitos (posto)
- **Exemplo:** `cooperativa = "0100"`, `posto = "01"`
- **Onde obter:** Contrato com Sicredi ou Internet Banking

#### codigo_beneficiario
- **Formato:** Numérico, geralmente 5-10 dígitos
- **Onde obter:** Contrato de cobrança com Sicredi

---

## 🧪 Validando Credenciais Sandbox

### Passo 1: Confirmar Acesso ao Sandbox
1. Acesse o **Portal do Desenvolvedor Sicredi**
2. Verifique se há uma seção **Sandbox/Homologação**
3. Confirme que você tem **credenciais de teste** específicas para sandbox

**⚠️ IMPORTANTE:** Muitas instituições financeiras brasileiras **não fornecem credenciais sandbox publicamente**. Você precisa:
- Ser cliente Sicredi corporativo
- Ter um contrato de API ativo
- Solicitar credenciais sandbox via suporte técnico

### Passo 2: Verificar Ambiente
```sql
-- Verificar qual ambiente está configurado
SELECT environment, x_api_key, username, cooperativa, posto 
FROM sicredi_credentials 
WHERE company_id = 'seu-company-id';
```

Se `environment = 'sandbox'`, mas suas credenciais são de **produção**, você terá erro 403.

### Passo 3: Testar Autenticação Manualmente

Use o cURL para testar diretamente:

```bash
# Sandbox
curl -X POST 'https://api-parceiro.sicredi.com.br/sb/auth/openapi/token' \
  -H 'x-api-key: SEU-X-API-KEY' \
  -H 'context: COBRANCA' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'grant_type=password&username=SEU-USERNAME&password=SUA-SENHA&scope=cobranca'

# Produção
curl -X POST 'https://api-parceiro.sicredi.com.br/auth/openapi/token' \
  -H 'x-api-key: SEU-X-API-KEY' \
  -H 'context: COBRANCA' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'grant_type=password&username=SEU-USERNAME&password=SUA-SENHA&scope=cobranca'
```

**Resposta esperada (sucesso):**
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "scope": "cobranca",
  "token_type": "Bearer",
  "expires_in": 600
}
```

**Respostas de erro:**
- **403 Forbidden:** Credenciais inválidas ou API Key não autorizada
- **401 Unauthorized:** Username/password incorretos
- **400 Bad Request:** Formato de request inválido

---

## 🛠️ Soluções Comuns

### Solução 1: Validar API Key no Portal
1. Acesse o Portal do Desenvolvedor Sicredi
2. Vá em **Minhas Aplicações**
3. Clique na aplicação
4. Verifique se a **API Key está ativa**
5. Confirme que o ambiente (sandbox/prod) está correto
6. Se necessário, **regenere a API Key**

### Solução 2: Regenerar Código de Acesso (Password)
1. Acesse o Internet Banking Sicredi
2. Menu **Empresas** → **API Cobrança** (ou similar)
3. Clique em **Gerar Novo Código de Acesso**
4. Copie o código e atualize no banco:

```sql
UPDATE sicredi_credentials 
SET password = 'NOVO-CODIGO-GERADO',
    updated_at = NOW()
WHERE company_id = 'seu-company-id';
```

### Solução 3: Corrigir Username
Se o erro persistir, tente **apenas o código do beneficiário** como username:

```sql
UPDATE sicredi_credentials 
SET username = '12345',  -- Apenas codigo_beneficiario
    updated_at = NOW()
WHERE company_id = 'seu-company-id';
```

OU tente a **concatenação**:

```sql
UPDATE sicredi_credentials 
SET username = '123450100',  -- codigo_beneficiario + cooperativa
    updated_at = NOW()
WHERE company_id = 'seu-company-id';
```

### Solução 4: Mudar para Ambiente de Produção (se aplicável)
Se você **não tem credenciais sandbox**, use as credenciais de **produção**:

```sql
UPDATE sicredi_credentials 
SET environment = 'production',
    x_api_key = 'API-KEY-DE-PRODUCAO',
    username = 'USERNAME-DE-PRODUCAO',
    password = 'SENHA-DE-PRODUCAO',
    updated_at = NOW()
WHERE company_id = 'seu-company-id';
```

⚠️ **CUIDADO:** Ambiente de produção gera boletos **reais**. Use apenas para testes finais.

---

## 📞 Suporte Sicredi

Se nenhuma solução acima funcionar:

1. **Portal do Desenvolvedor:** Abra um ticket de suporte
2. **Email:** Verifique o email de suporte técnico no portal
3. **Telefone:** Entre em contato com o gerente de conta Sicredi

**Informações para fornecer ao suporte:**
- Número do contrato de API
- Ambiente que está tentando usar (sandbox/prod)
- Mensagem de erro completa
- Timestamp da tentativa
- Código HTTP (403)

---

## 🔐 Validação de Dados

### Dados que você informou:
```
username: 128072602
password: teste123
cooperativa: 6789
posto: 03
codigo_beneficiario: 12345
environment: sandbox
```

### Possíveis problemas:
1. **password = "teste123"** - Parece senha genérica. O código de acesso Sicredi é geralmente alfanumérico complexo
2. **username = "128072602"** - Não parece seguir o padrão `codigo_beneficiario` (12345). Pode estar errado.
3. **cooperativa = "6789"** - Geralmente tem 4 dígitos com zeros à esquerda (ex: "0100", "6789" está ok)

### Recomendações:
1. ✅ Confirme que o **password** é o código de acesso gerado no Internet Banking (não a senha de login)
2. ✅ Verifique se **username** deve ser apenas `"12345"` ou `"12345"` + `"6789"` = `"123456789"`
3. ✅ Certifique-se de que você tem **acesso autorizado ao ambiente sandbox**

---

## 🧪 Script de Teste Rápido

Crie um arquivo `test_sicredi_auth.py`:

```python
import httpx
import asyncio

async def test_auth():
    url = "https://api-parceiro.sicredi.com.br/sb/auth/openapi/token"
    headers = {
        "x-api-key": "SEU-X-API-KEY-AQUI",
        "context": "COBRANCA",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "password",
        "username": "SEU-USERNAME-AQUI",
        "password": "SUA-SENHA-AQUI",
        "scope": "cobranca",
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, data=data)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")
        
        if resp.status_code == 200:
            print("✅ Autenticação bem-sucedida!")
            token_data = resp.json()
            print(f"Access Token: {token_data['access_token'][:50]}...")
        else:
            print("❌ Falha na autenticação")

asyncio.run(test_auth())
```

Execute:
```bash
cd backend
python test_sicredi_auth.py
```

---

## ✅ Próximos Passos

1. **Validar credenciais** via cURL ou script Python acima
2. **Corrigir username/password** se necessário
3. **Atualizar no banco** com as credenciais corretas
4. **Testar novamente** via API: `POST /api/v1/admin/sicredi/boletos`

Se o teste manual funcionar mas a API continuar falhando, pode ser um bug no código de integração. Caso contrário, o problema está nas **credenciais fornecidas pelo Sicredi**.
