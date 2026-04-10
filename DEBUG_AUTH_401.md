# 🔍 DEBUG: 401 nos endpoints /admin/clients, /admin/developments, /admin/lots

## Status das Correções Aplicadas

### ✅ 1. Código do `require_permission` está CORRETO

`@/Users/nicksonaleixo/Documents/GitHub/Csapp_backend/backend/app/core/deps.py:149-160`

```python
# SUPER_ADMIN e COMPANY_ADMIN têm acesso total sem verificar permissões
if user_role in (UserRole.SUPER_ADMIN.value, UserRole.COMPANY_ADMIN.value):
    logger.info(f"[PERMISSION] BYPASS granted for {user_role}")
    return current_user
```

O bypass está implementado corretamente ANTES de tentar carregar staff_permissions.

### ✅ 2. Endpoints estão usando a dependência correta

`@/Users/nicksonaleixo/Documents/GitHub/Csapp_backend/backend/app/api/v1/admin/clients.py:35`

```python
admin: Profile = Depends(require_permission("view_clients"))
```

Todos os endpoints de clients, developments, lots usam `require_permission()`.

### ✅ 3. Logs de debug adicionados

Três pontos de log foram adicionados para rastrear o fluxo de autenticação:

#### A. DebugHTTPBearer (linha 24-30)
```python
[BEARER] Raw auth header: Bearer eyJhbG...
[BEARER] Parsed credentials: True/False
```

#### B. get_current_user (linha 60-62)
```python
[AUTH] Path: /api/v1/admin/clients
[AUTH] Authorization header: Bearer eyJhbG...
[AUTH] Credentials from bearer_scheme: True/False
```

#### C. require_permission (linha 155-159)
```python
[PERMISSION] Checking 'view_clients' for user <uuid> with role: SUPER_ADMIN
[PERMISSION] BYPASS granted for SUPER_ADMIN
```

### ✅ 4. Ordem dos Middlewares corrigida

**Antes:**
```python
SecurityHeadersMiddleware
GZipMiddleware
TenantMiddleware       ← Estava ANTES do CORS
CORSMiddleware
ProxyHeadersMiddleware
```

**Depois:**
```python
SecurityHeadersMiddleware
GZipMiddleware
CORSMiddleware         ← Movido para ANTES do TenantMiddleware
TenantMiddleware
ProxyHeadersMiddleware
```

### ✅ 5. CORS configurado para aceitar todos os headers (temporário)

```python
allow_headers=["*"],  # Permite qualquer header
expose_headers=["*"],
```

## O que verificar nos logs após deploy

Quando o frontend fizer uma request para `/api/v1/admin/clients`, você deve ver nos logs do Railway:

### Fluxo esperado CORRETO (200 OK):

```
[BEARER] Raw auth header: Bearer eyJhbGciOiJIUz...
[BEARER] Parsed credentials: True
[AUTH] Path: /api/v1/admin/clients
[AUTH] Authorization header: Bearer eyJhbGciOiJIUz...
[AUTH] Credentials from bearer_scheme: True
[PERMISSION] Checking 'view_clients' for user <uuid> with role: SUPER_ADMIN
[PERMISSION] BYPASS granted for SUPER_ADMIN
```

### Fluxo com PROBLEMA (401):

#### Caso 1: Header não está chegando
```
[BEARER] Raw auth header: NONE...
[BEARER] Parsed credentials: False
[AUTH] Path: /api/v1/admin/clients
[AUTH] Authorization header: NOT PRESENT
[AUTH] Credentials from bearer_scheme: False
[AUTH] Missing credentials for path: /api/v1/admin/clients
```
**→ Solução:** Problema no proxy/frontend enviando o header

#### Caso 2: Bearer não está parseando
```
[BEARER] Raw auth header: Bearer eyJhbGciOiJIUz...
[BEARER] Parsed credentials: False
[AUTH] Credentials from bearer_scheme: False
```
**→ Solução:** Formato do header está incorreto

#### Caso 3: Token inválido
```
[BEARER] Parsed credentials: True
[AUTH] Credentials from bearer_scheme: True
token_invalid: <erro>
```
**→ Solução:** Token expirado ou assinado com chave diferente

## Testes Manuais

### 1. Verificar header no Railway

Execute este comando no container do Railway:

```bash
curl -v https://csappbackend-production.up.railway.app/api/v1/admin/clients \
  -H "Authorization: Bearer SEU_TOKEN_AQUI"
```

Deve retornar os logs acima.

### 2. Teste local

```bash
cd backend
uvicorn app.main:app --reload --log-level debug
```

Abra outro terminal:

```bash
# Login para pegar token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@company.com","password":"senha123"}'

# Copie o access_token e teste
curl http://localhost:8000/api/v1/admin/clients \
  -H "Authorization: Bearer <access_token>"
```

Você deve ver os logs `[BEARER]`, `[AUTH]`, `[PERMISSION]` no terminal.

## Próximos Passos

1. **Fazer commit e push** do código atualizado
2. **Aguardar deploy** no Railway
3. **Testar novamente** no frontend
4. **Copiar os logs** do Railway e enviar para análise
5. Se ainda falhar, **compartilhar os logs completos** para debug

## Arquivos Modificados nesta Correção

- `backend/app/core/deps.py` — Logs de debug + DebugHTTPBearer
- `backend/app/main.py` — Reordenação de middlewares + CORS com headers=["*"]

## Reversão (se necessário)

Se os logs poluírem muito em produção, remover depois:

```python
# Em deps.py, remover linhas 24-30 (DebugHTTPBearer)
bearer_scheme = HTTPBearer(auto_error=False)

# Remover linhas 60-62, 155, 159 (logs de debug)
```

E reverter CORS headers para lista específica:

```python
allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
```
