# Guia de Migrations - Sistema de Gestão Imobiliária

## 📋 Ordem de Execução

### ✅ Migrations via SQL Editor

Execute estas migrations **no SQL Editor do Supabase** na ordem:

1. **001_create_tables.sql** ✅
   - Cria todas as tabelas do sistema
   - Cria enums, índices e triggers
   - **Execução**: Copie e cole no SQL Editor

2. **002_row_level_security.sql** ✅
   - Configura todas as políticas RLS
   - Cria funções auxiliares de segurança
   - **Execução**: Copie e cole no SQL Editor

3. **004_seed_data.sql** ✅ (Opcional - apenas dev)
   - Insere dados de exemplo
   - Cria empreendimento e lotes de teste
   - **Execução**: Copie e cole no SQL Editor

---

### ⚠️ Configuração Manual via Dashboard

4. **003_storage_buckets_MANUAL.md** 🔧
   - **NÃO é uma migration SQL!**
   - Guia para criar buckets de storage
   - **Execução**: Siga o guia passo a passo no Dashboard

5. **003_storage_policies_DASHBOARD.md** 🔧
   - **NÃO é uma migration SQL!**
   - Guia para criar políticas RLS de storage
   - **Execução**: Crie políticas manualmente no Dashboard

---

## ⚠️ IMPORTANTE: Storage Configuration

### Por que não posso executar 003_storage_buckets.sql?

O Supabase **não permite** criar buckets e políticas de storage via SQL direto por questões de segurança. O schema `storage` tem permissões especiais.

**Erro comum**:
```
ERROR: 42501: permission denied for schema storage
```

### Solução

1. **Criar Buckets**: Use a interface do Dashboard (Storage > New Bucket)
2. **Criar Políticas**: Use a interface do Dashboard (Storage > [Bucket] > Policies)

Siga os guias detalhados:
- `003_storage_buckets_MANUAL.md` - Como criar os 4 buckets
- `003_storage_policies_DASHBOARD.md` - Como criar as 9 políticas RLS

---

## 🔍 Verificação

### Após executar migrations 001 e 002:

```sql
-- Verificar tabelas criadas
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;

-- Verificar políticas RLS
SELECT tablename, policyname 
FROM pg_policies 
WHERE schemaname = 'public';
```

### Após configurar storage:

```sql
-- Verificar buckets criados
SELECT * FROM storage.buckets;

-- Verificar políticas de storage
SELECT policyname, cmd 
FROM pg_policies 
WHERE tablename = 'objects' 
AND schemaname = 'storage';
```

---

## 📝 Checklist de Setup

- [ ] 1. Executar `001_create_tables.sql` no SQL Editor
- [ ] 2. Executar `002_row_level_security.sql` no SQL Editor
- [ ] 3. Criar 4 buckets manualmente no Dashboard (seguir `003_storage_buckets_MANUAL.md`)
- [ ] 4. Criar 9 políticas RLS de storage no Dashboard (seguir `003_storage_policies_DASHBOARD.md`)
- [ ] 5. (Opcional) Executar `004_seed_data.sql` no SQL Editor
- [ ] 6. Verificar que tudo está funcionando

---

## 🆘 Troubleshooting

### "permission denied for schema storage"
- **Causa**: Tentou executar SQL direto no schema storage
- **Solução**: Use o Dashboard para configurar storage

### "relation does not exist"
- **Causa**: Migration 001 não foi executada
- **Solução**: Execute `001_create_tables.sql` primeiro

### "function is_admin() does not exist"
- **Causa**: Migration 002 não foi executada
- **Solução**: Execute `002_row_level_security.sql`

### "new row violates row-level security policy"
- **Causa**: RLS não configurado ou usuário sem permissão
- **Solução**: Verifique se migration 002 foi executada e se o role do usuário está correto

---

## 📚 Estrutura das Migrations

```
migrations/
├── README.md                           # Este arquivo
├── 001_create_tables.sql               # ✅ Execute no SQL Editor
├── 002_row_level_security.sql          # ✅ Execute no SQL Editor
├── 003_storage_buckets.sql             # ❌ NÃO EXECUTE (apenas referência)
├── 003_storage_buckets_MANUAL.md       # 🔧 Guia para Dashboard
├── 003_storage_policies_DASHBOARD.md   # 🔧 Guia para Dashboard
└── 004_seed_data.sql                   # ✅ Execute no SQL Editor (opcional)
```

---

## 🎯 Resumo Rápido

1. **SQL Editor**: Execute migrations 001, 002 e opcionalmente 004
2. **Dashboard**: Configure storage manualmente (buckets + políticas)
3. **Verificação**: Teste que tudo está funcionando
4. **Backend**: Configure `.env` e inicie a aplicação

Para guia completo de setup, consulte: `../SETUP_GUIDE.md`
