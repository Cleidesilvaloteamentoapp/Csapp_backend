# JWT no Sistema de Gestão Imobiliária

## 🔑 Como Funciona JWT Neste Projeto

### Nós NÃO Usamos JWT Customizado

Este projeto **não implementa** um sistema JWT customizado. Em vez disso, delegamos toda a gestão de JWT ao **Supabase Auth**.

### Fluxo de Autenticação

1. **Login**:
   ```python
   # Cliente faz login
   response = supabase.auth.sign_in_with_password({
       "email": email,
       "password": password
   })
   
   # Supabase retorna JWT
   access_token = response.session.access_token
   ```

2. **Verificação**:
   ```python
   # Verificar token em cada request
   user_response = supabase.auth.get_user(access_token)
   ```

3. **RLS**:
   - O JWT contém o `user_id`
   - RLS usa `auth.uid()` para isolar dados
   - Tudo gerenciado pelo Supabase

## 🚫 Por Que Não Usar JWT Customizado?

| Aspecto | JWT Customizado | Supabase Auth |
|---------|----------------|---------------|
| **Implementação** | Complexa (sign, verify, refresh) | Pronta |
| **Segurança** | Você é responsável | Gerenciada pelo Supabase |
| **Refresh Tokens** | Implementar manualmente | Automático |
| **Password Reset** | Implementar manualmente | Pronto |
| **RLS Integration** | Manual | Nativa |
| **Email Verification** | Implementar | Pronto |

## 📋 O Que Você Precisa Configurar

### ✅ O Que Precisa

```env
# Supabase Configuration
SUPABASE_URL=https://seu-projeto.supabase.co
SUPABASE_ANON_KEY=eyJ...sua-chave-anon
SUPABASE_SERVICE_ROLE_KEY=eyJ...sua-chave-service-role
```

### ❌ O Que Não Precisa

```env
# NÃO PRECISA DISSO
JWT_SECRET=your-jwt-secret  # ❌ NOT USED
```

## 🔧 Como o Código Funciona

### 1. Login Route
```python
@router.post("/auth/login")
async def login(request: LoginRequest, db: Client):
    response = db.auth.sign_in_with_password({
        "email": request.email,
        "password": request.password
    })
    
    return LoginResponse(
        access_token=response.session.access_token,
        refresh_token=response.session.refresh_token,
        user={...}
    )
```

### 2. Middleware de Verificação
```python
async def verify_token(supabase: Client, token: str):
    try:
        user_response = supabase.auth.get_user(token)
        if not user_response.user:
            raise HTTPException(401, "Invalid token")
        return user_response.user
    except Exception:
        raise HTTPException(401, "Token verification failed")
```

### 3. Dependência FastAPI
```python
async def get_current_user(
    credentials: HTTPBearer,
    db: Client = Depends(get_db)
):
    token = credentials.credentials
    return await verify_token(db, token)
```

## 🎯 Vantagens Desta Abordagem

1. **Simplicidade**: Menos código para manter
2. **Segurança**: Supabase cuida da segurança JWT
3. **Features**: Refresh tokens, password reset, etc. prontos
4. **RLS**: Integração nativa com Row Level Security
5. **Escalabilidade**: Infraestrutura do Supabase

## 📚 Referências

- [Supabase Auth Documentation](https://supabase.com/docs/guides/auth)
- [JWT vs Supabase Auth](https://supabase.com/docs/guides/auth/auth-helpers)
- [Row Level Security](https://supabase.com/docs/guides/auth/row-level-security)

## 🚨 Importante

**Nunca implemente JWT customizado** neste projeto a menos que você tenha um motivo muito específico. O Supabase Auth já resolve 99% dos casos de uso de forma mais segura e eficiente.

Se precisar de features adicionais:
- Use hooks do Supabase Auth
- Implemente middleware customizado
- Use Edge Functions do Supabase

Mas mantenha sempre o JWT gerenciado pelo Supabase.
