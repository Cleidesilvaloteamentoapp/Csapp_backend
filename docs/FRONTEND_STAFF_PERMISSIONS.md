# Frontend Instructions — Sistema de Staff com Permissões Granulares

> **Backend version**: migration `011_staff_permissions`
> **Date**: Abril 2026

Este documento descreve todos os endpoints, schemas, regras de autorização e requisitos de UI para implementar o **gerenciamento de contas de Staff** e a **exibição condicional de funcionalidades** baseada em permissões granulares.

---

## Índice

1. [Visão Geral do Sistema de Roles](#1-visão-geral-do-sistema-de-roles)
2. [Endpoints de Gerenciamento de Staff (Admin)](#2-endpoints-de-gerenciamento-de-staff-admin)
3. [Schemas TypeScript](#3-schemas-typescript)
4. [Mapa de Permissões por Módulo](#4-mapa-de-permissões-por-módulo)
5. [Autenticação e Login de Staff](#5-autenticação-e-login-de-staff)
6. [Controle de Acesso no Frontend](#6-controle-de-acesso-no-frontend)
7. [UI/UX — Página de Gerenciamento de Staff](#7-uiux--página-de-gerenciamento-de-staff)
8. [UI/UX — Sidebar e Navegação Condicional](#8-uiux--sidebar-e-navegação-condicional)
9. [Tratamento de Erros HTTP](#9-tratamento-de-erros-http)
10. [Checklist de Implementação](#10-checklist-de-implementação)

---

## 1. Visão Geral do Sistema de Roles

O backend agora suporta **quatro roles de usuário**:

| Role | Descrição | Acesso |
|------|-----------|--------|
| `SUPER_ADMIN` | Administrador global da plataforma | Tudo |
| `COMPANY_ADMIN` | Dono/gestor da empresa | Todos os módulos da empresa |
| `STAFF` | Funcionário com permissões limitadas | Somente o que foi liberado |
| `CLIENT` | Cliente final | Portal do cliente |

### Regras críticas

- **`COMPANY_ADMIN`** tem acesso total a **todos** os endpoints da empresa, independente de permissões.
- **`STAFF`** só acessa o que estiver explicitamente liberado na sua linha da tabela `staff_permissions`.
- Conta `STAFF` com `is_active = false` **não consegue fazer login** (retorna `400 Inactive user`).
- Apenas `COMPANY_ADMIN` pode criar, editar e desativar contas de `STAFF`.
- `STAFF` **não pode** gerenciar outros staffs.

---

## 2. Endpoints de Gerenciamento de Staff (Admin)

> **Todos requerem role `COMPANY_ADMIN` ou `SUPER_ADMIN`.**

| Método | Path | Descrição |
|--------|------|-----------|
| `GET` | `/api/v1/admin/staff/` | Listar todos os staffs da empresa |
| `POST` | `/api/v1/admin/staff/` | Criar nova conta de staff |
| `GET` | `/api/v1/admin/staff/{staff_id}` | Detalhes + permissões de um staff |
| `PATCH` | `/api/v1/admin/staff/{staff_id}` | Atualizar dados e/ou permissões |
| `PATCH` | `/api/v1/admin/staff/{staff_id}/toggle-active` | Ativar / desativar conta |
| `DELETE` | `/api/v1/admin/staff/{staff_id}` | Excluir permanentemente |

### 2.1 Criar Staff — `POST /api/v1/admin/staff/`

**Request body:**
```json
{
  "full_name": "João Silva",
  "email": "joao@empresa.com",
  "cpf_cnpj": "12345678901",
  "phone": "51999998888",
  "password": "SenhaForte123",
  "permissions": {
    "view_clients": true,
    "manage_clients": false,
    "view_lots": true,
    "manage_lots": false,
    "view_financial": true,
    "manage_financial": false,
    "view_renegotiations": false,
    "manage_renegotiations": false,
    "view_rescissions": false,
    "manage_rescissions": false,
    "view_reports": true,
    "view_service_requests": true,
    "manage_service_requests": false,
    "view_documents": true,
    "manage_documents": false,
    "view_sicredi": false,
    "manage_sicredi": false,
    "view_whatsapp": false,
    "manage_whatsapp": false,
    "view_financial_settings": false,
    "manage_financial_settings": false
  }
}
```

> **Nota**: O campo `permissions` é opcional. Se omitido, todas as flags serão `false` (sem acesso a nada).

**Erros possíveis:**
- `409 Conflict` — Email ou CPF/CNPJ já cadastrado.

---

### 2.2 Atualizar Staff — `PATCH /api/v1/admin/staff/{staff_id}`

Todos os campos são opcionais. Envie apenas o que deseja alterar.

```json
{
  "full_name": "João da Silva Atualizado",
  "phone": "51988887777",
  "password": "NovaSenha456",
  "permissions": {
    "view_clients": true,
    "manage_clients": true
  }
}
```

> **Importante**: ao enviar `permissions`, **todas as 20 flags** são substituídas. Envie o objeto completo ou o backend sobrescreverá as não enviadas como `false`.

---

### 2.3 Toggle Ativo — `PATCH /api/v1/admin/staff/{staff_id}/toggle-active`

Sem body. Inverte o estado atual de `is_active`.

**Response:**
```json
{
  "id": "uuid",
  "is_active": false,
  "message": "Staff account deactivated successfully"
}
```

---

## 3. Schemas TypeScript

```typescript
interface StaffPermissions {
  view_clients: boolean;
  manage_clients: boolean;
  view_lots: boolean;
  manage_lots: boolean;
  view_financial: boolean;
  manage_financial: boolean;
  view_renegotiations: boolean;
  manage_renegotiations: boolean;
  view_rescissions: boolean;
  manage_rescissions: boolean;
  view_reports: boolean;
  view_service_requests: boolean;
  manage_service_requests: boolean;
  view_documents: boolean;
  manage_documents: boolean;
  view_sicredi: boolean;
  manage_sicredi: boolean;
  view_whatsapp: boolean;
  manage_whatsapp: boolean;
  view_financial_settings: boolean;
  manage_financial_settings: boolean;
}

interface StaffResponse {
  id: string;           // UUID
  company_id: string;   // UUID
  full_name: string;
  email: string;
  cpf_cnpj: string;
  phone: string;
  is_active: boolean;
  permissions: StaffPermissions | null;
}

interface StaffCreateRequest {
  full_name: string;         // min 2, max 255
  email: string;             // valid email
  cpf_cnpj: string;          // min 11, max 20
  phone: string;             // min 8, max 20
  password: string;          // min 8
  permissions?: StaffPermissions;
}

interface StaffUpdateRequest {
  full_name?: string;
  phone?: string;
  password?: string;
  permissions?: StaffPermissions;
}

interface StaffToggleResponse {
  id: string;
  is_active: boolean;
  message: string;
}

// Dados do usuário autenticado (retornado pelo /api/v1/auth/me)
interface AuthenticatedUser {
  id: string;
  company_id: string;
  role: 'SUPER_ADMIN' | 'COMPANY_ADMIN' | 'CLIENT' | 'STAFF';
  full_name: string;
  email: string;
  is_active: boolean;
  // Para STAFF, as permissões devem ser carregadas via GET /admin/staff/{id}
}
```

---

## 4. Mapa de Permissões por Módulo

A tabela abaixo mostra qual flag de permissão protege cada grupo de endpoints.

| Módulo | Ver (leitura) | Gerenciar (escrita) |
|--------|--------------|---------------------|
| Clientes | `view_clients` | `manage_clients` |
| Lotes / Empreendimentos | `view_lots` | `manage_lots` |
| Financeiro / Boletos | `view_financial` | `manage_financial` |
| Renegociações | `view_renegotiations` | `manage_renegotiations` |
| Distratos (Rescisões) | `view_rescissions` | `manage_rescissions` |
| Relatórios | `view_reports` | *(somente leitura)* |
| Solicitações de Serviço | `view_service_requests` | `manage_service_requests` |
| Documentos | `view_documents` | `manage_documents` |
| Sicredi | `manage_sicredi` | `manage_sicredi` |
| WhatsApp | `manage_whatsapp` | `manage_whatsapp` |
| Conf. Financeiras | `view_financial_settings` | `manage_financial_settings` |
| Dashboard | `view_financial` | *(somente leitura)* |
| Ordens de Serviço | `view_financial` | `manage_financial` |
| Ciclos de Aprovação | `manage_financial` | `manage_financial` |
| Segunda Via de Boleto | `manage_financial` | `manage_financial` |
| Antecipação de Pagamento | `manage_financial` | `manage_financial` |
| Transferências de Contrato | `manage_clients` | `manage_clients` |
| Histórico de Contrato | `view_clients` | `manage_clients` |
| Índices Econômicos | `view_financial_settings` | `manage_financial_settings` |
| Extratos Bancários | `view_financial` | `view_financial` |

### Regra geral para o frontend

```
SUPER_ADMIN → acesso total (sem verificação de flags)
COMPANY_ADMIN → acesso total à sua empresa (sem verificação de flags)
STAFF → verificar flag correspondente antes de exibir botão/página
CLIENT → portal do cliente apenas
```

---

## 5. Autenticação e Login de Staff

O endpoint de login é o **mesmo** para todos os roles:

```
POST /api/v1/auth/login
```

```json
{
  "email": "joao@empresa.com",
  "password": "SenhaForte123"
}
```

**Comportamento esperado:**

- Se `is_active = false` → servidor retorna `400 Bad Request: "Inactive user"`. Exibir mensagem: *"Conta desativada. Contate o administrador."*
- Login bem-sucedido retorna JWT e dados do perfil (incluindo `role`).
- Após o login de um `STAFF`, o frontend deve carregar as permissões via `GET /api/v1/admin/staff/{id}` e armazená-las no estado global.

### Armazenamento de permissões no estado global

```typescript
// Exemplo com Zustand / Context
interface AuthState {
  user: AuthenticatedUser | null;
  staffPermissions: StaffPermissions | null;
  isAdmin: () => boolean;       // role === SUPER_ADMIN || COMPANY_ADMIN
  can: (perm: keyof StaffPermissions) => boolean;
}

// Implementação sugerida de can()
can: (perm) => {
  if (!user) return false;
  if (user.role === 'SUPER_ADMIN' || user.role === 'COMPANY_ADMIN') return true;
  if (user.role !== 'STAFF') return false;
  return staffPermissions?.[perm] === true;
}
```

---

## 6. Controle de Acesso no Frontend

### 6.1 Componente de guarda de permissão

Crie um componente reutilizável que oculta UI baseado na permissão:

```tsx
// Exemplo React
interface PermissionGuardProps {
  permission: keyof StaffPermissions;
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

function PermissionGuard({ permission, children, fallback = null }: PermissionGuardProps) {
  const { can } = useAuth();
  return can(permission) ? <>{children}</> : <>{fallback}</>;
}

// Uso
<PermissionGuard permission="manage_clients">
  <Button onClick={handleCreate}>Novo Cliente</Button>
</PermissionGuard>
```

### 6.2 Hook de permissão para rotas

```typescript
function useRequirePermission(permission: keyof StaffPermissions) {
  const { can } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!can(permission)) {
      navigate('/admin/sem-permissao', { replace: true });
    }
  }, [permission]);
}

// Uso na página
export default function ClientesPage() {
  useRequirePermission('view_clients');
  // ...
}
```

### 6.3 Regras por tipo de ação

| Ação | Permissão necessária |
|------|---------------------|
| Acessar rota de listagem | `view_*` correspondente |
| Exibir botão "Novo / Criar" | `manage_*` correspondente |
| Exibir botão "Editar / Salvar" | `manage_*` correspondente |
| Exibir botão "Excluir / Cancelar" | `manage_*` correspondente |
| Exibir botão "Aprovar / Rejeitar" | `manage_*` correspondente |
| Exibir página de configurações | `view_financial_settings` |
| Salvar configurações | `manage_financial_settings` |

---

## 7. UI/UX — Página de Gerenciamento de Staff

> **Rota sugerida**: `/admin/staff`
> **Visibilidade**: Somente `COMPANY_ADMIN` e `SUPER_ADMIN` veem este item no menu.

### 7.1 Lista de Staff

**Tabela com as colunas:**
- Nome completo
- E-mail
- Telefone
- Status (badge `Ativo` verde / `Inativo` cinza)
- Permissões (ícones resumidos ou contador "X de 11 módulos")
- Ações: Editar | Ativar/Desativar | Excluir

**Comportamentos:**
- Staffs inativos exibidos com opacidade reduzida.
- Botão "Novo Staff" no topo direito.
- Confirmação modal antes de excluir.

### 7.2 Modal de Criação / Edição

**Campos básicos:**

| Campo | Tipo | Validação |
|-------|------|-----------|
| Nome completo | text | min 2 chars |
| E-mail | email | formato válido |
| CPF/CNPJ | text | min 11 chars |
| Telefone | text | min 8 chars |
| Senha | password | min 8 chars (obrigatório na criação, opcional na edição) |

**Seção de Permissões — exibir como tabela de toggles:**

```
Módulo                   | Ver  | Gerenciar
─────────────────────────|──────|──────────
Clientes                 | [ ]  | [ ]
Lotes                    | [ ]  | [ ]
Financeiro / Boletos     | [ ]  | [ ]
Renegociações            | [ ]  | [ ]
Distratos                | [ ]  | [ ]
Relatórios               | [ ]  | —
Solicitações de Serviço  | [ ]  | [ ]
Documentos               | [ ]  | [ ]
Sicredi                  | —    | [ ]
WhatsApp                 | —    | [ ]
Configurações Financeiras| [ ]  | [ ]
```

**Regras de UX para os toggles:**
- Se "Gerenciar" for ativado, **ative automaticamente "Ver"** também (quem gerencia precisa ver).
- Se "Ver" for desativado, **desative automaticamente "Gerenciar"** também.
- Sicredi e WhatsApp têm apenas "Gerenciar" (não há distinção ver/gerenciar nesses módulos).
- Relatórios tem apenas "Ver" (sem opção de gerenciar).

**Botões do modal:**
- "Salvar" → POST ou PATCH conforme caso
- "Cancelar" → fecha sem salvar
- Spinner no botão durante request

### 7.3 Ação de Toggle Ativo

- Ao desativar: exibir modal de confirmação: *"Deseja desativar a conta de [Nome]? O usuário não conseguirá mais fazer login."*
- Ao ativar: sem confirmação, apenas feedback toast.
- Botão no card/linha do staff: texto muda entre "Desativar" e "Ativar".

### 7.4 Página de Erro — Sem Permissão

Criar rota `/admin/sem-permissao` com mensagem amigável:

> *"Você não tem permissão para acessar esta área. Solicite ao administrador que ajuste as suas permissões."*

---

## 8. UI/UX — Sidebar e Navegação Condicional

A sidebar do painel admin deve exibir/ocultar itens baseado no role e nas permissões do usuário logado.

### 8.1 Regras de exibição

| Item do Menu | Exibir para |
|---|---|
| **Gerenciar Staff** | `COMPANY_ADMIN`, `SUPER_ADMIN` |
| **Dashboard** | Todos os admins (`COMPANY_ADMIN`, `SUPER_ADMIN`, STAFF com `view_financial`) |
| **Clientes** | `can('view_clients')` |
| **Lotes** | `can('view_lots')` |
| **Financeiro / Boletos** | `can('view_financial')` |
| **Renegociações** | `can('view_renegotiations')` |
| **Distratos** | `can('view_rescissions')` |
| **Relatórios** | `can('view_reports')` |
| **Solicitações de Serviço** | `can('view_service_requests')` |
| **Documentos** | `can('view_documents')` |
| **Sicredi** | `can('manage_sicredi')` |
| **WhatsApp** | `can('manage_whatsapp')` |
| **Configurações Financeiras** | `can('view_financial_settings')` |
| **Índices Econômicos** | `can('view_financial_settings')` |
| **Ciclos de Aprovação** | `can('manage_financial')` |
| **Transferências** | `can('manage_clients')` |
| **Antecipações** | `can('manage_financial')` |
| **Extratos Bancários** | `can('view_financial')` |

### 8.2 Indicador de usuário logado

No header ou rodapé da sidebar, exibir o nome do usuário e seu role:

```
João Silva
[STAFF]  ●  Ativo
```

Para `COMPANY_ADMIN`, exibir `[ADMINISTRADOR]`.

---

## 9. Tratamento de Erros HTTP

| Status | Quando ocorre | Mensagem para o usuário |
|--------|--------------|------------------------|
| `400 Inactive user` | Login com conta desativada | "Conta desativada. Contate o administrador." |
| `401 Unauthorized` | Token expirado ou inválido | "Sessão expirada. Faça login novamente." |
| `403 Access denied` | Role sem acesso à rota | "Você não tem permissão para esta ação." |
| `403 Missing permission: X` | STAFF sem a flag específica | "Permissão insuficiente: [nome do módulo]." |
| `409 Conflict` | E-mail ou CPF duplicado na criação de staff | "E-mail ou CPF/CNPJ já cadastrado." |
| `404 Not Found` | Staff não existe ou não pertence à empresa | "Funcionário não encontrado." |

---

## 10. Checklist de Implementação

### Backend (já implementado ✅)
- [x] Role `STAFF` adicionado ao enum
- [x] Campo `is_active` na tabela `profiles`
- [x] Tabela `staff_permissions` com 20 flags booleanas
- [x] Verificação de `is_active` no login
- [x] Dependency `require_permission()` aplicada em todos os endpoints admin
- [x] CRUD de staff em `/api/v1/admin/staff/`
- [x] Migração `011_staff_permissions` + SQL `015_staff_permissions.sql`

### Frontend (a implementar)
- [ ] Atualizar interface `AuthenticatedUser` para incluir `role: 'STAFF'` e `is_active`
- [ ] Implementar função `can(permission)` no estado global de autenticação
- [ ] Carregar e armazenar `StaffPermissions` após login de usuário STAFF
- [ ] Criar componente `<PermissionGuard permission="..." />`
- [ ] Criar hook `useRequirePermission(permission)`
- [ ] Aplicar guards em todas as rotas admin (ver tabela seção 8.1)
- [ ] Ocultar botões de escrita para STAFF sem a permissão `manage_*`
- [ ] Criar página `/admin/staff` — lista de funcionários
- [ ] Criar modal de criação de staff (com tabela de toggles de permissão)
- [ ] Criar modal de edição de staff
- [ ] Implementar toggle ativo/inativo com confirmação
- [ ] Implementar confirmação de exclusão
- [ ] Criar página `/admin/sem-permissao`
- [ ] Tratar erro `400 Inactive user` no login
- [ ] Tratar erro `403 Missing permission` em todas as chamadas
- [ ] Atualizar sidebar para ocultar itens sem permissão
- [ ] Exibir badge de role no header/sidebar

---

## Exemplo de Fluxo Completo

```
1. COMPANY_ADMIN faz login → role = 'COMPANY_ADMIN' → acesso total
2. COMPANY_ADMIN cria staff com view_clients=true, manage_clients=false
3. Staff faz login → role = 'STAFF', is_active = true
4. Frontend busca GET /admin/staff/{id} → carrega permissões
5. Sidebar exibe apenas "Clientes" (pois view_clients=true)
6. Na página de clientes: lista carrega normalmente
7. Botão "Novo Cliente" está OCULTO (manage_clients=false)
8. Staff tenta acessar /admin/lotes → redireciona para /admin/sem-permissao
9. COMPANY_ADMIN desativa a conta do staff via toggle
10. Staff tenta fazer login → 400 "Inactive user" → mensagem de conta desativada
```
