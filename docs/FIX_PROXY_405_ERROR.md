# Fix: Erro 405 Method Not Allowed no POST /api/proxy/admin/clients

## 🔴 Problema Identificado

O frontend está usando um proxy interno em `/api/proxy/*` que:
- ✅ **Aceita GET** → Funciona
- ❌ **Rejeita POST** → Retorna 405 Method Not Allowed

**Evidência:**
```
Request URL: https://csappfrontend-production.up.railway.app/api/proxy/admin/clients
Method: POST
Status: 405 Method Not Allowed
```

## 🎯 Causa Raiz

O arquivo de proxy no frontend (provavelmente Next.js API Route ou similar) está configurado para aceitar **apenas GET**, ou não está configurado para aceitar todos os métodos HTTP.

## ✅ Solução

### Opção 1: Configurar Proxy para Aceitar Todos os Métodos (Recomendado)

Se o frontend está usando **Next.js API Routes**, o arquivo deve estar em algo como:

```
frontend/pages/api/proxy/[...path].ts
OU
frontend/app/api/proxy/[...path]/route.ts (App Router)
```

**Código correto para Next.js (App Router):**

```typescript
// frontend/app/api/proxy/[...path]/route.ts

import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'https://csappbackend-production.up.railway.app';

// ✅ Função genérica para proxy de qualquer método HTTP
async function proxyRequest(request: NextRequest, method: string) {
  // Extrai o path após /api/proxy/
  const pathname = request.nextUrl.pathname.replace('/api/proxy', '');
  const searchParams = request.nextUrl.searchParams.toString();
  const url = `${BACKEND_URL}/api/v1${pathname}${searchParams ? `?${searchParams}` : ''}`;

  // Pega o token do cookie
  const cookieStore = cookies();
  const accessToken = cookieStore.get('access_token')?.value;

  // Prepara os headers
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };

  if (accessToken) {
    headers['Authorization'] = `Bearer ${accessToken}`;
  }

  // Copia outros headers relevantes do request original
  request.headers.forEach((value, key) => {
    if (
      key.toLowerCase() !== 'host' &&
      key.toLowerCase() !== 'connection' &&
      key.toLowerCase() !== 'content-length' &&
      !key.startsWith(':')
    ) {
      headers[key] = value;
    }
  });

  try {
    // Prepara o body para métodos que aceitam body
    let body: string | undefined;
    if (['POST', 'PUT', 'PATCH'].includes(method)) {
      const requestBody = await request.text();
      body = requestBody || undefined;
    }

    // Faz a requisição para o backend
    const response = await fetch(url, {
      method,
      headers,
      body,
      credentials: 'include',
    });

    // Lê a resposta
    const data = await response.text();
    
    // Retorna a resposta com o mesmo status code
    return new NextResponse(data, {
      status: response.status,
      headers: {
        'Content-Type': 'application/json',
      },
    });
  } catch (error) {
    console.error('Proxy error:', error);
    return NextResponse.json(
      { detail: 'Proxy error: Unable to reach backend' },
      { status: 502 }
    );
  }
}

// ✅ CRITICAL: Exportar handlers para TODOS os métodos HTTP
export async function GET(request: NextRequest) {
  return proxyRequest(request, 'GET');
}

export async function POST(request: NextRequest) {
  return proxyRequest(request, 'POST');
}

export async function PUT(request: NextRequest) {
  return proxyRequest(request, 'PUT');
}

export async function PATCH(request: NextRequest) {
  return proxyRequest(request, 'PATCH');
}

export async function DELETE(request: NextRequest) {
  return proxyRequest(request, 'DELETE');
}

// Configuração para evitar cache
export const dynamic = 'force-dynamic';
export const revalidate = 0;
```

**Para Next.js Pages Router:**

```typescript
// frontend/pages/api/proxy/[...path].ts

import type { NextApiRequest, NextApiResponse } from 'next';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'https://csappbackend-production.up.railway.app';

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  const { path } = req.query;
  const pathname = Array.isArray(path) ? path.join('/') : path;
  
  // Constrói a URL completa
  const queryString = new URLSearchParams(req.query as Record<string, string>).toString();
  const url = `${BACKEND_URL}/api/v1/${pathname}${queryString ? `?${queryString}` : ''}`;

  // Pega o token do cookie
  const accessToken = req.cookies.access_token;

  // Prepara headers
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };

  if (accessToken) {
    headers['Authorization'] = `Bearer ${accessToken}`;
  }

  try {
    // Faz a requisição para o backend com o MESMO método
    const response = await fetch(url, {
      method: req.method, // ✅ CRITICAL: Usa o mesmo método da requisição original
      headers,
      body: ['POST', 'PUT', 'PATCH'].includes(req.method || '') 
        ? JSON.stringify(req.body)
        : undefined,
    });

    const data = await response.json();
    
    // Retorna com o mesmo status code
    res.status(response.status).json(data);
  } catch (error) {
    console.error('Proxy error:', error);
    res.status(502).json({ detail: 'Proxy error: Unable to reach backend' });
  }
}
```

---

### Opção 2: Remover o Proxy e Chamar Backend Diretamente (Mais Simples)

Em vez de usar proxy, configure o frontend para chamar o backend diretamente:

**1. Configure a variável de ambiente no frontend:**

```bash
# frontend/.env.production
NEXT_PUBLIC_BACKEND_URL=https://csappbackend-production.up.railway.app
```

**2. Atualize o código de API do frontend:**

```typescript
// frontend/lib/api.ts ou similar

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'https://csappbackend-production.up.railway.app';

export async function apiRequest(endpoint: string, options: RequestInit = {}) {
  const token = typeof window !== 'undefined' 
    ? localStorage.getItem('access_token') || document.cookie.match(/access_token=([^;]+)/)?.[1]
    : null;

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const url = `${BACKEND_URL}/api/v1${endpoint}`;

  const response = await fetch(url, {
    ...options,
    headers,
    credentials: 'include',
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Request failed');
  }

  return response.json();
}

// Uso:
// import { apiRequest } from '@/lib/api';
//
// // Criar cliente
// const newClient = await apiRequest('/admin/clients', {
//   method: 'POST',
//   body: JSON.stringify(clientData),
// });
```

**3. Atualize os componentes:**

```typescript
// ❌ ANTES (usando proxy)
const response = await fetch('/api/proxy/admin/clients', {
  method: 'POST',
  body: JSON.stringify(data),
});

// ✅ DEPOIS (chamada direta)
import { apiRequest } from '@/lib/api';

const newClient = await apiRequest('/admin/clients', {
  method: 'POST',
  body: JSON.stringify(data),
});
```

---

## 🧪 Como Testar

### Teste 1: Verificar se o proxy aceita POST

```bash
# No terminal
curl -X POST https://csappfrontend-production.up.railway.app/api/proxy/admin/clients \
  -H "Content-Type: application/json" \
  -H "Cookie: access_token=SEU_TOKEN_AQUI" \
  -d '{
    "email": "teste@exemplo.com",
    "full_name": "Teste",
    "cpf_cnpj": "12345678901",
    "phone": "11999999999",
    "create_access": false
  }'
```

**Resultado esperado:** Status 201 (criado) ou 400/422 (validação), **NÃO 405**.

### Teste 2: Testar backend diretamente (para confirmar que funciona)

```bash
curl -X POST https://csappbackend-production.up.railway.app/api/v1/admin/clients \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer SEU_TOKEN_AQUI" \
  -d '{
    "email": "teste@exemplo.com",
    "full_name": "Teste",
    "cpf_cnpj": "12345678901",
    "phone": "11999999999",
    "create_access": false
  }'
```

**Resultado esperado:** Status 201 (criado).

---

## 📋 Checklist de Correção

- [ ] Localizar arquivo de proxy no frontend (procure por `api/proxy` ou `[...path]`)
- [ ] Verificar se exporta `export async function POST`
- [ ] Se não exportar POST, adicionar handler para POST (e PUT, PATCH, DELETE)
- [ ] Verificar se o handler usa `req.method` ao fazer fetch para o backend
- [ ] Deploy do frontend
- [ ] Testar POST /api/proxy/admin/clients
- [ ] Verificar se retorna 201 (não 405)

---

## 🔍 Como Encontrar o Arquivo de Proxy no Frontend

```bash
# No repositório do frontend
cd /path/to/frontend

# Procurar arquivos de proxy
find . -name "*proxy*" -o -name "[...path]*" | grep -v node_modules

# Ou procurar por padrão de API routes
find . -path "*/api/*" -name "*.ts" -o -name "*.js" | grep -v node_modules
```

Locais comuns:
- `pages/api/proxy/[...path].ts` (Pages Router)
- `app/api/proxy/[...path]/route.ts` (App Router)
- `src/pages/api/proxy/[...path].ts`
- `src/app/api/proxy/[...path]/route.ts`

---

## 💡 Dica: Por Que Usar Proxy?

**Vantagens do proxy:**
- ✅ Tokens ficam em cookies httpOnly (mais seguro)
- ✅ Evita problemas de CORS
- ✅ Backend URL não fica exposta no frontend

**Desvantagens:**
- ❌ Adiciona latência extra
- ❌ Mais complexo de configurar
- ❌ Pode causar problemas como este (405)

**Recomendação:** Use proxy apenas se precisa de httpOnly cookies. Caso contrário, chamadas diretas são mais simples e confiáveis.

---

## 📞 Suporte

Se o problema persistir após aplicar as correções:

1. Verifique os logs do Railway (frontend)
2. Capture o request completo no Network tab
3. Teste o backend diretamente (bypass proxy)
4. Verifique se há middleware bloqueando POST no frontend

**Problema confirmado:** Backend funciona corretamente. O erro está no proxy do frontend.
