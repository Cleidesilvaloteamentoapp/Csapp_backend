# 🚨 FRONTEND: Header Authorization NÃO está chegando no backend

## Diagnóstico Confirmado

Os logs do backend mostram:
```
[BEARER] Raw auth header: NONE...
[AUTH] Authorization header: NOT PRESENT...
```

O header `Authorization` **NÃO ESTÁ SENDO RECEBIDO** pelo backend, mesmo que o frontend diga que está enviando.

## O que o frontend precisa verificar URGENTEMENTE

### 1. Console do navegador

Abra DevTools → Network → Clique na request para `/api/v1/admin/clients`:

**Request Headers (o que VOCÊ está enviando):**
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response Headers (o que o BACKEND está vendo):**
- Verifique se há algum erro de CORS no console
- Verifique se a request é OPTIONS (preflight) ou GET

### 2. Código do fetch/axios

O header precisa ser enviado EXATAMENTE assim:

```typescript
// ✅ CORRETO
fetch('https://csappbackend-production.up.railway.app/api/v1/admin/clients', {
  method: 'GET',
  headers: {
    'Authorization': `Bearer ${token}`,  // Primeira letra MAIÚSCULA
    'Content-Type': 'application/json',
  },
  credentials: 'include',  // IMPORTANTE para CORS
})

// ❌ ERRADO - header pode estar sendo bloqueado
fetch('url', {
  headers: {
    'authorization': token,  // Minúsculo + sem Bearer
  }
})
```

### 3. Proxy do Vite/Next.js

Se você está usando proxy local (localhost:3000 → backend):

```typescript
// vite.config.ts ou next.config.js
export default {
  server: {
    proxy: {
      '/api': {
        target: 'https://csappbackend-production.up.railway.app',
        changeOrigin: true,
        // ⚠️ CRÍTICO: Não remover headers
        headers: {
          // Não adicione nada aqui que possa sobrescrever Authorization
        },
        // ⚠️ Verifique se há onProxyReq que modifica headers
      }
    }
  }
}
```

### 4. Interceptor do Axios

Se usa Axios, verifique interceptors:

```typescript
// ✅ CORRETO
axios.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ❌ ERRADO - pode estar removendo o header
axios.interceptors.request.use(config => {
  config.headers = {  // ⚠️ SOBRESCREVE todos os headers!
    'Content-Type': 'application/json'
  };
  return config;
});
```

### 5. Teste DIRETO no navegador

Abra o Console do DevTools e rode:

```javascript
fetch('https://csappbackend-production.up.railway.app/api/v1/admin/clients', {
  method: 'GET',
  headers: {
    'Authorization': 'Bearer SEU_TOKEN_AQUI',
  },
  credentials: 'include',
})
  .then(r => r.json())
  .then(data => console.log('SUCCESS:', data))
  .catch(err => console.error('ERROR:', err));
```

**Se isso funcionar:** O problema está no código do frontend.
**Se isso NÃO funcionar:** O problema está no CORS/Railway.

### 6. Verificar URL do backend

Certifique-se que está apontando para:
```
https://csappbackend-production.up.railway.app
```

E NÃO para:
```
http://csappbackend-production.up.railway.app  (sem HTTPS)
csappbackend-production.up.railway.app  (sem https://)
```

### 7. Middleware do Service Worker / PWA

Se você tem Service Worker ativo:

```javascript
// Verifique se há código que modifica requests
self.addEventListener('fetch', (event) => {
  // ⚠️ Cuidado aqui - pode estar removendo headers
  const request = event.request;
  console.log('SW Headers:', request.headers);
});
```

## Teste com CURL

Do seu terminal local:

```bash
# Pegue o token atual do localStorage
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

# Teste direto no backend
curl -v https://csappbackend-production.up.railway.app/api/v1/admin/clients \
  -H "Authorization: Bearer $TOKEN"
```

Você deve ver:
```
< HTTP/2 200
< content-type: application/json
```

Se retornar 401, o token está inválido/expirado.

## Próximos Logs do Backend

Após o próximo deploy, os logs vão mostrar:

```
[DEBUG HEADERS] Path: /api/v1/admin/clients/
[DEBUG HEADERS] Method: GET
[DEBUG HEADERS] All headers:
  host: csappbackend-production.up.railway.app
  user-agent: Mozilla/5.0...
  accept: */*
  origin: https://csappfrontend-production.up.railway.app
  authorization: Bearer eyJhbGci... [FOUND AUTHORIZATION]  ← DEVE APARECER
```

Se `authorization` NÃO aparecer nessa lista, o problema é:
1. Proxy/Railway removendo o header
2. CORS bloqueando
3. Frontend não está enviando

## Checklist Frontend

- [ ] Verificar Request Headers no DevTools
- [ ] Confirmar formato: `Authorization: Bearer <token>`
- [ ] Adicionar `credentials: 'include'` no fetch
- [ ] Verificar se proxy local não está removendo headers
- [ ] Testar request direta no console do navegador
- [ ] Verificar se Service Worker não está interferindo
- [ ] Confirmar que está usando HTTPS na URL
- [ ] Verificar interceptors do Axios
- [ ] Testar com CURL do terminal

## Backend já está pronto

O backend está configurado corretamente:
- ✅ CORS permitindo todos os headers
- ✅ `allow_credentials: true`
- ✅ Middleware de debug logando tudo
- ✅ `require_permission` com bypass para SUPER_ADMIN

O problema está na **entrega do header** do frontend para o backend.
