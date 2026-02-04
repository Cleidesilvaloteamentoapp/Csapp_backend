# Guia de Migração: JWT Keys → Publishable/Secret Keys

## 📋 Contexto

O Supabase está migrando de chaves JWT (`anon`, `service_role`) para um novo sistema (`sb_publishable_...`, `sb_secret_...`).

**Status atual do projeto**: Usando JWT keys (anon + service_role)

## ⚠️ Quando Migrar?

**NÃO migre agora se:**
- ❌ Projeto ainda em desenvolvimento inicial
- ❌ Não tem necessidade de rotação de chaves
- ❌ Não tem múltiplos backends

**Migre quando:**
- ✅ Projeto em produção estável
- ✅ Precisa rotacionar chaves sem downtime
- ✅ Quer melhor controle de segurança por componente
- ✅ Tem múltiplos serviços backend

## 🔑 Comparação de Chaves

| Aspecto | JWT Keys (Atual) | Publishable/Secret Keys (Novo) |
|---------|------------------|--------------------------------|
| **Formato** | JWT longo | `sb_publishable_...` / `sb_secret_...` |
| **Validade** | 10 anos | Sem expiração (até deletar) |
| **Rotação** | Requer rotação do JWT secret (downtime) | Rotação individual sem downtime |
| **Múltiplas chaves** | Não | Sim (múltiplos secrets) |
| **CLI/Self-hosting** | ✅ Suportado | ❌ Não suportado ainda |
| **Edge Functions** | ✅ Verificação JWT nativa | ⚠️ Requer `--no-verify-jwt` |
| **Realtime público** | Ilimitado | Limitado a 24h sem auth |

## 📝 Passo a Passo da Migração

### Fase 1: Preparação (Sem Downtime)

1. **Criar novas chaves no Dashboard**
   - Vá em Settings > API Keys
   - Clique em "Create new API Keys"
   - Copie a `Publishable key` (substitui anon)
   - Copie a `Secret key` (substitui service_role)

2. **Adicionar novas chaves ao .env**
   ```env
   # Chaves antigas (manter por enquanto)
   SUPABASE_ANON_KEY=eyJ...
   SUPABASE_SERVICE_ROLE_KEY=eyJ...
   
   # Novas chaves (adicionar)
   SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
   SUPABASE_SECRET_KEY=sb_secret_...
   ```

### Fase 2: Atualizar Código (Gradual)

#### 2.1. Atualizar `app/core/config.py`

```python
class Settings(BaseSettings):
    # ... outras configs
    
    # Chaves antigas (deprecated)
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    
    # Novas chaves (preferir estas)
    SUPABASE_PUBLISHABLE_KEY: Optional[str] = None
    SUPABASE_SECRET_KEY: Optional[str] = None
    
    @property
    def supabase_client_key(self) -> str:
        """Retorna publishable key se disponível, senão anon"""
        return self.SUPABASE_PUBLISHABLE_KEY or self.SUPABASE_ANON_KEY
    
    @property
    def supabase_admin_key(self) -> str:
        """Retorna secret key se disponível, senão service_role"""
        return self.SUPABASE_SECRET_KEY or self.SUPABASE_SERVICE_ROLE_KEY
```

#### 2.2. Atualizar `app/database.py`

```python
@lru_cache()
def get_supabase_client() -> Client:
    """Get Supabase client (respects RLS)"""
    settings = get_settings()
    return create_client(
        settings.SUPABASE_URL, 
        settings.supabase_client_key  # Usa publishable ou anon
    )

@lru_cache()
def get_supabase_admin_client() -> Client:
    """Get Supabase admin client (bypasses RLS)"""
    settings = get_settings()
    return create_client(
        settings.SUPABASE_URL, 
        settings.supabase_admin_key  # Usa secret ou service_role
    )
```

### Fase 3: Testar com Novas Chaves

1. **Configurar .env com novas chaves**
2. **Testar todos os endpoints**:
   - Login/Signup
   - Operações de admin
   - Operações de cliente
   - Upload de arquivos
3. **Verificar logs** para erros de autenticação

### Fase 4: Desativar Chaves Antigas

1. **Verificar uso no Dashboard**
   - Settings > API Keys
   - Veja "Last used" para anon e service_role
   - Confirme que não estão sendo usadas

2. **Desativar (não deletar) chaves antigas**
   - Mantenha desativadas por 30 dias
   - Se tudo funcionar, pode deletar depois

3. **Remover do .env**
   ```env
   # Remover estas linhas
   # SUPABASE_ANON_KEY=...
   # SUPABASE_SERVICE_ROLE_KEY=...
   ```

## ⚠️ Considerações Importantes

### Edge Functions
Se usar Edge Functions, você precisará:
```typescript
// Antes (com JWT keys)
const supabaseClient = createClient(
  Deno.env.get('SUPABASE_URL')!,
  Deno.env.get('SUPABASE_ANON_KEY')!
)

// Depois (com publishable/secret keys)
const supabaseClient = createClient(
  Deno.env.get('SUPABASE_URL')!,
  Deno.env.get('SUPABASE_PUBLISHABLE_KEY')!,
  {
    global: {
      headers: { Authorization: req.headers.get('Authorization')! },
    },
  }
)
```

E executar com: `supabase functions serve --no-verify-jwt`

### Realtime Connections
Conexões públicas de Realtime são limitadas a 24h com publishable key. Se precisar de conexões mais longas, implemente autenticação de usuário via Supabase Auth.

### CLI e Self-hosting
Se você usa CLI local ou self-hosting, **não migre ainda**. As novas chaves só funcionam na plataforma hospedada do Supabase.

## 🔄 Rollback

Se algo der errado:

1. **Reativar chaves antigas** no Dashboard
2. **Reverter código** para usar anon/service_role
3. **Investigar** o problema antes de tentar novamente

## 📊 Checklist de Migração

- [ ] Criar publishable e secret keys no Dashboard
- [ ] Adicionar novas chaves ao .env
- [ ] Atualizar config.py com fallback
- [ ] Atualizar database.py
- [ ] Testar autenticação
- [ ] Testar operações admin
- [ ] Testar operações cliente
- [ ] Testar upload de arquivos
- [ ] Verificar logs por 7 dias
- [ ] Desativar chaves antigas
- [ ] Aguardar 30 dias
- [ ] Remover chaves antigas do código

## 🎯 Recomendação Final

**Para este projeto em desenvolvimento:**
- ✅ Continue usando `anon` e `service_role` por enquanto
- ✅ Implemente a migração quando estiver em produção
- ✅ Use este guia quando decidir migrar
- ✅ Teste em staging antes de produção

**Vantagens de migrar depois:**
- Zero pressão durante desenvolvimento
- Código estável antes da mudança
- Melhor compreensão das necessidades do projeto
- Documentação e ferramentas mais maduras
