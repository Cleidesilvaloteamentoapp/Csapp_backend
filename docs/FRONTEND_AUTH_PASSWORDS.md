# Frontend Instructions — Autenticação, Senhas e Criação de Superadmin

> **Backend version**: Auth + Password Management
> **Date**: Abril 2026

Este documento descreve **todos os novos endpoints de autenticação** implementados, incluindo recuperação/alteração de senha e criação de contas superadmin adicionais.

---

## Índice

1. [Resumo das Alterações](#1-resumo-das-alterações)
2. [Novos Endpoints de Senha](#2-novos-endpoints-de-senha)
3. [Endpoint de Superadmin](#3-endpoint-de-superadmin)
4. [Schemas TypeScript](#4-schemas-typescript)
5. [Fluxo de Recuperação de Senha](#5-fluxo-de-recuperação-de-senha)
6. [UI/UX — Telas Necessárias](#6-uiux--telas-necessárias)
7. [Validação de Senha](#7-validação-de-senha)
8. [Segurança e Rate Limiting](#8-segurança-e-rate-limiting)
9. [Tratamento de Erros](#9-tratamento-de-erros)
10. [Checklist de Implementação](#10-checklist-de-implementação)

---

## 1. Resumo das Alterações

### Novos Endpoints Implementados

| Endpoint | Método | Descrição | Autenticação |
|----------|--------|-----------|--------------|
| `/auth/forgot-password` | POST | Solicita email de recuperação de senha | ⚪ Não requerida |
| `/auth/reset-password` | POST | Redefine senha com token do email | ⚪ Não requerida |
| `/auth/change-password` | POST | Altera senha (usuário logado) | 🟢 Requerida |
| `/admin/superadmins` | POST | Cria superadmin adicional na mesma empresa | 🔴 SUPER_ADMIN |

### Arquivos Criados no Backend

- `app/schemas/superadmin.py` — Schemas para criação de superadmin
- `app/services/superadmin_service.py` — Lógica de criação com validações
- `app/api/v1/admin/superadmins.py` — Endpoint protegido

### Arquivos Modificados no Backend

- `app/schemas/auth.py` — Adicionados schemas de senha
- `app/services/auth_service.py` — Funções `forgot_password`, `reset_password`, `change_password`
- `app/services/email_service.py` — Template de email de recuperação
- `app/api/v1/auth.py` — 3 novos endpoints de senha
- `app/core/config.py` — Adicionado `FRONTEND_URL`

---

## 2. Novos Endpoints de Senha

### 2.1 Esqueci Minha Senha — `POST /auth/forgot-password`

**Não requer autenticação**

Envia email com link de recuperação (válido por 15 minutos).

**Request:**
```json
{
  "email": "usuario@empresa.com"
}
```

**Response 200 (SEMPRE):**
```json
{
  "message": "If this email is registered, you will receive a password reset link"
}
```

**⚠️ IMPORTANTE:**
- **Sempre retorna 200**, mesmo se o email não existir (previne enumeração de emails)
- Rate limit: **3 requests/minuto** por IP
- Se o email existir, usuário recebe email com link: `{FRONTEND_URL}/reset-password?token={JWT}`

**Erros possíveis:**
- `429 Too Many Requests` — Excedeu rate limit

---

### 2.2 Redefinir Senha — `POST /auth/reset-password`

**Não requer autenticação** (usa token do email)

Redefine a senha usando o token recebido por email.

**Request:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "new_password": "NovaSenha123!"
}
```

**Response 200:**
```json
{
  "message": "Password has been reset successfully"
}
```

**Validação de senha:**
- Mínimo 8 caracteres
- Máximo 128 caracteres
- Pelo menos 1 letra maiúscula
- Pelo menos 1 letra minúscula
- Pelo menos 1 dígito
- Pelo menos 1 caractere especial

**Erros possíveis:**
- `400 Bad Request` — Token inválido/expirado ou senha fraca
- `404 Not Found` — Usuário não encontrado
- `422 Unprocessable Entity` — Validação de senha falhou

**Mensagens de erro de validação:**
```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "new_password"],
      "msg": "Password must contain at least one uppercase letter",
      "input": "senha123"
    }
  ]
}
```

---

### 2.3 Alterar Senha (Logado) — `POST /auth/change-password`

**Requer autenticação** (Bearer token)

Usuário logado altera sua própria senha. **Requer senha atual** para confirmar.

**Request:**
```json
{
  "current_password": "SenhaAtual123!",
  "new_password": "NovaSenha456#"
}
```

**Response 200:**
```json
{
  "message": "Password changed successfully"
}
```

**Erros possíveis:**
- `400 Bad Request` — Senha atual incorreta
- `401 Unauthorized` — Token inválido/expirado
- `404 Not Found` — Usuário não encontrado
- `422 Unprocessable Entity` — Nova senha não atende requisitos

**Mensagem de erro comum:**
```json
{
  "detail": "Current password is incorrect"
}
```

---

## 3. Endpoint de Superadmin

### 3.1 Criar Superadmin Adicional — `POST /admin/superadmins`

**Requer autenticação:** `SUPER_ADMIN` apenas

Cria uma nova conta de superadmin **para a mesma empresa** do usuário logado.

**Request:**
```json
{
  "full_name": "Gabriel Sabadini",
  "email": "gabrielsabadini.cursos@gmail.com",
  "cpf_cnpj": "12345678901",
  "phone": "47999918394",
  "password": "SenhaForte123!"
}
```

**Response 201:**
```json
{
  "id": "6856890e-0842-4277-9c60-55964c743515",
  "company_id": "a1b2c3d4-0001-4000-8000-000000000001",
  "full_name": "Gabriel Sabadini",
  "email": "gabrielsabadini.cursos@gmail.com",
  "cpf_cnpj": "12345678901",
  "phone": "47999918394",
  "role": "SUPER_ADMIN",
  "is_active": true
}
```

**Validações:**
- Email único (não pode existir em outra conta)
- CPF/CNPJ único (não pode existir em outra conta)
- Senha forte (mesmas regras de `reset-password`)
- Telefone: mínimo 10 caracteres
- Nome completo: mínimo 2 caracteres

**Erros possíveis:**
- `401 Unauthorized` — Usuário não autenticado
- `403 Forbidden` — Usuário não é SUPER_ADMIN
- `409 Conflict` — Email ou CPF/CNPJ já cadastrado
- `422 Unprocessable Entity` — Validação falhou

**Mensagens de erro:**
```json
// Email duplicado
{
  "detail": "Registration failed: email already exists"
}

// CPF/CNPJ duplicado
{
  "detail": "Registration failed: CPF/CNPJ already exists"
}

// Senha fraca
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "password"],
      "msg": "Password must contain at least one special character"
    }
  ]
}
```

---

## 4. Schemas TypeScript

```typescript
// ========== Recuperação de Senha ==========

interface ForgotPasswordRequest {
  email: string; // EmailStr válido
}

interface PasswordResetResponse {
  message: string;
}

interface ResetPasswordRequest {
  token: string; // JWT recebido por email
  new_password: string; // min 8, max 128, força validada
}

interface PasswordChangeRequest {
  current_password: string;
  new_password: string; // min 8, max 128, força validada
}

// ========== Superadmin ==========

interface SuperadminCreateRequest {
  full_name: string; // min 2, max 255
  email: string; // EmailStr válido
  cpf_cnpj: string; // min 11, max 20
  phone: string; // min 10, max 20
  password: string; // min 8, max 128, força validada
}

interface SuperadminResponse {
  id: string; // UUID
  company_id: string; // UUID
  full_name: string;
  email: string;
  cpf_cnpj: string;
  phone: string;
  role: "SUPER_ADMIN";
  is_active: boolean;
}

// ========== Validação de Senha ==========

interface PasswordValidationRules {
  minLength: 8;
  maxLength: 128;
  requireUppercase: boolean;
  requireLowercase: boolean;
  requireDigit: boolean;
  requireSpecialChar: boolean;
}

// Helper de validação frontend
function validatePasswordStrength(password: string): string[] {
  const errors: string[] = [];
  
  if (password.length < 8) errors.push("Mínimo 8 caracteres");
  if (password.length > 128) errors.push("Máximo 128 caracteres");
  if (!/[A-Z]/.test(password)) errors.push("Pelo menos 1 letra maiúscula");
  if (!/[a-z]/.test(password)) errors.push("Pelo menos 1 letra minúscula");
  if (!/\d/.test(password)) errors.push("Pelo menos 1 número");
  if (!/[^A-Za-z0-9]/.test(password)) errors.push("Pelo menos 1 caractere especial (!@#$%&*)");
  
  return errors;
}
```

---

## 5. Fluxo de Recuperação de Senha

### Fluxo Completo (Frontend + Backend)

```
┌─────────────┐                                         
│   Usuário   │                                         
│ clica em    │                                         
│ "Esqueci a  │                                         
│   senha"    │                                         
└──────┬──────┘                                         
       │                                                
       ▼                                                
┌──────────────────────────────────────────┐           
│ 1. Tela "Esqueci minha senha"            │           
│    Input: Email                          │           
│    Botão: Enviar link de recuperação     │           
└──────┬───────────────────────────────────┘           
       │ POST /auth/forgot-password                    
       │ { "email": "user@example.com" }               
       ▼                                                
┌──────────────────────────────────────────┐           
│ Backend:                                 │           
│ - Valida email                           │           
│ - Gera JWT token (exp: 15 min)           │           
│ - Envia email com link                   │           
│ - SEMPRE retorna 200 OK                  │           
└──────┬───────────────────────────────────┘           
       │                                                
       ▼                                                
┌──────────────────────────────────────────┐           
│ 2. Tela de confirmação (frontend)        │           
│    "Se o email existir, você receberá    │           
│     um link de recuperação"              │           
└──────────────────────────────────────────┘           
       │                                                
       │ [Usuário verifica email]                      
       │                                                
       ▼                                                
┌──────────────────────────────────────────┐           
│ Email recebido:                          │           
│ Link: {FRONTEND_URL}/reset-password?     │           
│       token=eyJhbGc...                   │           
│ Expira em: 15 minutos                    │           
└──────┬───────────────────────────────────┘           
       │ [Usuário clica no link]                       
       ▼                                                
┌──────────────────────────────────────────┐           
│ 3. Tela "Redefinir senha"                │           
│    - URL já contém ?token=...            │           
│    - Input: Nova senha                   │           
│    - Input: Confirmar nova senha         │           
│    - Validação em tempo real (frontend)  │           
│    - Botão: Redefinir senha              │           
└──────┬───────────────────────────────────┘           
       │ POST /auth/reset-password                     
       │ { "token": "eyJ...", "new_password": "..." }  
       ▼                                                
┌──────────────────────────────────────────┐           
│ Backend:                                 │           
│ - Valida token JWT (exp, role)           │           
│ - Valida força da senha                  │           
│ - Atualiza hashed_password               │           
│ - Retorna 200 OK                         │           
└──────┬───────────────────────────────────┘           
       │                                                
       ▼                                                
┌──────────────────────────────────────────┐           
│ 4. Tela de sucesso                       │           
│    "Senha redefinida com sucesso!"       │           
│    Botão: Ir para login                  │           
└──────────────────────────────────────────┘           
```

---

## 6. UI/UX — Telas Necessárias

### 6.1 Tela: Esqueci Minha Senha

**Rota sugerida:** `/forgot-password`

**Componentes:**
- Título: "Recuperar senha"
- Input email (obrigatório, validação de formato)
- Botão "Enviar link de recuperação" (loading state durante request)
- Link "Voltar para login"

**Comportamento:**
- Ao enviar, **sempre** exibir mensagem genérica (mesmo se email não existir)
- Mensagem: "Se o email estiver cadastrado, você receberá um link de recuperação"
- Desabilitar botão durante loading
- Após sucesso, mostrar mensagem por 5s e redirecionar para `/login`

**Validação frontend:**
```typescript
const handleForgotPassword = async (email: string) => {
  if (!isValidEmail(email)) {
    showError("Email inválido");
    return;
  }
  
  setLoading(true);
  try {
    await api.post('/auth/forgot-password', { email });
    showSuccess("Se o email estiver cadastrado, você receberá um link");
    setTimeout(() => router.push('/login'), 5000);
  } catch (error) {
    if (error.response?.status === 429) {
      showError("Muitas tentativas. Aguarde alguns minutos.");
    } else {
      showError("Erro ao enviar email. Tente novamente.");
    }
  } finally {
    setLoading(false);
  }
};
```

---

### 6.2 Tela: Redefinir Senha

**Rota sugerida:** `/reset-password?token=...`

**Componentes:**
- Título: "Criar nova senha"
- Input "Nova senha" (type password, com toggle visibility)
- Input "Confirmar senha" (type password)
- Indicador de força da senha (barra de progresso + lista de requisitos)
- Botão "Redefinir senha"
- Link "Voltar para login"

**Validação em tempo real:**

```typescript
interface PasswordStrength {
  hasMinLength: boolean;
  hasUppercase: boolean;
  hasLowercase: boolean;
  hasDigit: boolean;
  hasSpecial: boolean;
}

const checkPasswordStrength = (password: string): PasswordStrength => ({
  hasMinLength: password.length >= 8,
  hasUppercase: /[A-Z]/.test(password),
  hasLowercase: /[a-z]/.test(password),
  hasDigit: /\d/.test(password),
  hasSpecial: /[^A-Za-z0-9]/.test(password),
});

// Componente visual
<div className="password-requirements">
  <div className={strength.hasMinLength ? 'valid' : 'invalid'}>
    ✓ Mínimo 8 caracteres
  </div>
  <div className={strength.hasUppercase ? 'valid' : 'invalid'}>
    ✓ Pelo menos 1 letra maiúscula
  </div>
  <div className={strength.hasLowercase ? 'valid' : 'invalid'}>
    ✓ Pelo menos 1 letra minúscula
  </div>
  <div className={strength.hasDigit ? 'valid' : 'invalid'}>
    ✓ Pelo menos 1 número
  </div>
  <div className={strength.hasSpecial ? 'valid' : 'invalid'}>
    ✓ Pelo menos 1 caractere especial (!@#$%&*)
  </div>
</div>
```

**Tratamento de erros:**

```typescript
const handleResetPassword = async (token: string, newPassword: string) => {
  setLoading(true);
  try {
    await api.post('/auth/reset-password', { token, new_password: newPassword });
    showSuccess("Senha redefinida com sucesso!");
    router.push('/login');
  } catch (error) {
    if (error.response?.status === 400) {
      showError("Link expirado ou inválido. Solicite um novo.");
    } else if (error.response?.status === 422) {
      showError("Senha não atende aos requisitos de segurança.");
    } else {
      showError("Erro ao redefinir senha. Tente novamente.");
    }
  } finally {
    setLoading(false);
  }
};
```

---

### 6.3 Tela: Alterar Senha (Usuário Logado)

**Rota sugerida:** `/configuracoes/senha` ou `/perfil/senha`

**Componentes:**
- Título: "Alterar senha"
- Input "Senha atual" (type password)
- Input "Nova senha" (type password, com validação em tempo real)
- Input "Confirmar nova senha" (type password)
- Indicador de força da senha (mesmo componente da tela de reset)
- Botão "Salvar alterações"
- Botão "Cancelar"

**Validação:**
```typescript
const handleChangePassword = async (currentPassword: string, newPassword: string) => {
  if (newPassword === currentPassword) {
    showError("A nova senha deve ser diferente da atual");
    return;
  }
  
  if (!isPasswordStrong(newPassword)) {
    showError("Senha não atende aos requisitos de segurança");
    return;
  }
  
  setLoading(true);
  try {
    await api.post('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    }, {
      headers: { Authorization: `Bearer ${token}` }
    });
    
    showSuccess("Senha alterada com sucesso!");
    // Limpar formulário
    resetForm();
  } catch (error) {
    if (error.response?.status === 400) {
      showError("Senha atual incorreta");
    } else if (error.response?.status === 422) {
      showError("Nova senha não atende aos requisitos");
    } else {
      showError("Erro ao alterar senha. Tente novamente.");
    }
  } finally {
    setLoading(false);
  }
};
```

---

### 6.4 Tela: Gerenciamento de Funcionários (com opção Superadmin)

**Rota sugerida:** `/admin/funcionarios`

**IMPORTANTE:** Esta tela já existe para STAFF. Adicione a opção de criar **SUPER_ADMIN**.

**Alterações necessárias:**

1. **Adicionar dropdown/select de tipo de conta** ao criar funcionário:

```tsx
<FormField label="Tipo de Conta">
  <Select
    value={accountType}
    onChange={(value) => setAccountType(value)}
    disabled={currentUser.role !== 'SUPER_ADMIN'}
  >
    <Option value="STAFF">Funcionário (permissões limitadas)</Option>
    <Option value="SUPER_ADMIN">
      Superadmin (acesso total) {/* Só visível se currentUser.role === SUPER_ADMIN */}
    </Option>
  </Select>
</FormField>
```

2. **Condicionar campos de permissões:**

```typescript
// Se accountType === 'SUPER_ADMIN', esconder seção de permissões granulares
// Superadmin tem acesso total, não precisa de checkboxes

{accountType === 'STAFF' && (
  <PermissionsSection>
    <Checkbox name="view_clients" label="Visualizar clientes" />
    <Checkbox name="manage_clients" label="Gerenciar clientes" />
    {/* ... outras permissões */}
  </PermissionsSection>
)}

{accountType === 'SUPER_ADMIN' && (
  <Alert type="info">
    Superadmins têm acesso total a todas as funcionalidades da empresa.
  </Alert>
)}
```

3. **Endpoint diferente para cada tipo:**

```typescript
const handleCreateAccount = async (data: FormData) => {
  const endpoint = data.accountType === 'SUPER_ADMIN' 
    ? '/admin/superadmins' 
    : '/admin/staff';
  
  const payload = data.accountType === 'SUPER_ADMIN'
    ? {
        full_name: data.full_name,
        email: data.email,
        cpf_cnpj: data.cpf_cnpj,
        phone: data.phone,
        password: data.password,
      }
    : {
        full_name: data.full_name,
        email: data.email,
        cpf_cnpj: data.cpf_cnpj,
        phone: data.phone,
        password: data.password,
        permissions: data.permissions, // Só para STAFF
      };
  
  try {
    await api.post(endpoint, payload);
    showSuccess(`${data.accountType === 'SUPER_ADMIN' ? 'Superadmin' : 'Funcionário'} criado com sucesso!`);
    refreshList();
  } catch (error) {
    handleError(error);
  }
};
```

4. **Badge visual na listagem:**

```tsx
<Table>
  {users.map(user => (
    <TableRow key={user.id}>
      <TableCell>{user.full_name}</TableCell>
      <TableCell>{user.email}</TableCell>
      <TableCell>
        <Badge variant={user.role === 'SUPER_ADMIN' ? 'red' : 'blue'}>
          {user.role === 'SUPER_ADMIN' ? 'Superadmin' : 'Funcionário'}
        </Badge>
      </TableCell>
      <TableCell>{/* Ações */}</TableCell>
    </TableRow>
  ))}
</Table>
```

---

### 6.5 Botão "Recuperar Senha" em Telas de Admin

**Onde adicionar:**

1. **Listagem de Funcionários** (`/admin/funcionarios`)
2. **Listagem de Clientes** (`/admin/clientes`)
3. **Detalhes de Funcionário/Cliente**

**Componente sugerido:**

```tsx
interface SendPasswordResetProps {
  userEmail: string;
  userName: string;
}

const SendPasswordResetButton: React.FC<SendPasswordResetProps> = ({ userEmail, userName }) => {
  const [loading, setLoading] = useState(false);
  
  const handleSendReset = async () => {
    const confirmed = window.confirm(
      `Enviar email de recuperação de senha para ${userName} (${userEmail})?`
    );
    
    if (!confirmed) return;
    
    setLoading(true);
    try {
      // Admin dispara forgot-password em nome do usuário
      await api.post('/auth/forgot-password', { email: userEmail });
      showSuccess(`Email de recuperação enviado para ${userEmail}`);
    } catch (error) {
      if (error.response?.status === 429) {
        showError("Limite de envios excedido. Aguarde alguns minutos.");
      } else {
        showError("Erro ao enviar email. Tente novamente.");
      }
    } finally {
      setLoading(false);
    }
  };
  
  return (
    <Button
      variant="outline"
      size="sm"
      onClick={handleSendReset}
      loading={loading}
      icon={<KeyIcon />}
    >
      Recuperar senha
    </Button>
  );
};
```

**Posicionamento:**

```tsx
// Na listagem (coluna de ações)
<TableCell>
  <ButtonGroup>
    <Button variant="ghost" icon={<EditIcon />}>Editar</Button>
    <SendPasswordResetButton userEmail={user.email} userName={user.full_name} />
    <Button variant="ghost" icon={<TrashIcon />}>Excluir</Button>
  </ButtonGroup>
</TableCell>

// Ou na página de detalhes (menu de ações)
<DropdownMenu>
  <DropdownItem onClick={handleEdit}>Editar informações</DropdownItem>
  <DropdownItem onClick={() => handleSendPasswordReset(user)}>
    Enviar recuperação de senha
  </DropdownItem>
  <DropdownItem onClick={handleToggleActive}>
    {user.is_active ? 'Desativar' : 'Ativar'} conta
  </DropdownItem>
</DropdownMenu>
```

---

## 7. Validação de Senha

### Regras de Validação (Backend)

Todas as senhas devem atender aos seguintes critérios:

| Regra | Validação |
|-------|-----------|
| **Comprimento** | 8-128 caracteres |
| **Letra maiúscula** | Pelo menos 1 (A-Z) |
| **Letra minúscula** | Pelo menos 1 (a-z) |
| **Dígito** | Pelo menos 1 (0-9) |
| **Caractere especial** | Pelo menos 1 (!@#$%^&*()-_=+[]{}|;:',.<>?/) |

### Regex de Validação

```typescript
// Frontend validation helper
const PASSWORD_RULES = {
  minLength: 8,
  maxLength: 128,
  uppercase: /[A-Z]/,
  lowercase: /[a-z]/,
  digit: /\d/,
  special: /[^A-Za-z0-9]/,
};

function validatePassword(password: string): { valid: boolean; errors: string[] } {
  const errors: string[] = [];
  
  if (password.length < PASSWORD_RULES.minLength) {
    errors.push(`Mínimo ${PASSWORD_RULES.minLength} caracteres`);
  }
  if (password.length > PASSWORD_RULES.maxLength) {
    errors.push(`Máximo ${PASSWORD_RULES.maxLength} caracteres`);
  }
  if (!PASSWORD_RULES.uppercase.test(password)) {
    errors.push("Pelo menos 1 letra maiúscula");
  }
  if (!PASSWORD_RULES.lowercase.test(password)) {
    errors.push("Pelo menos 1 letra minúscula");
  }
  if (!PASSWORD_RULES.digit.test(password)) {
    errors.push("Pelo menos 1 número");
  }
  if (!PASSWORD_RULES.special.test(password)) {
    errors.push("Pelo menos 1 caractere especial");
  }
  
  return {
    valid: errors.length === 0,
    errors,
  };
}
```

### Indicador Visual de Força

```tsx
interface PasswordStrengthIndicatorProps {
  password: string;
}

const PasswordStrengthIndicator: React.FC<PasswordStrengthIndicatorProps> = ({ password }) => {
  const strength = {
    hasMinLength: password.length >= 8,
    hasUppercase: /[A-Z]/.test(password),
    hasLowercase: /[a-z]/.test(password),
    hasDigit: /\d/.test(password),
    hasSpecial: /[^A-Za-z0-9]/.test(password),
  };
  
  const score = Object.values(strength).filter(Boolean).length;
  const strengthLevel = score === 5 ? 'strong' : score >= 3 ? 'medium' : 'weak';
  const strengthColor = strengthLevel === 'strong' ? 'green' : strengthLevel === 'medium' ? 'yellow' : 'red';
  
  return (
    <div className="password-strength">
      <div className="strength-bar">
        <div 
          className={`strength-fill strength-${strengthColor}`}
          style={{ width: `${(score / 5) * 100}%` }}
        />
      </div>
      
      <ul className="requirements-list">
        <li className={strength.hasMinLength ? 'valid' : 'invalid'}>
          <CheckIcon /> Mínimo 8 caracteres
        </li>
        <li className={strength.hasUppercase ? 'valid' : 'invalid'}>
          <CheckIcon /> Letra maiúscula (A-Z)
        </li>
        <li className={strength.hasLowercase ? 'valid' : 'invalid'}>
          <CheckIcon /> Letra minúscula (a-z)
        </li>
        <li className={strength.hasDigit ? 'valid' : 'invalid'}>
          <CheckIcon /> Número (0-9)
        </li>
        <li className={strength.hasSpecial ? 'valid' : 'invalid'}>
          <CheckIcon /> Caractere especial (!@#$%*)
        </li>
      </ul>
    </div>
  );
};
```

---

## 8. Segurança e Rate Limiting

### Rate Limits por Endpoint

| Endpoint | Limite | Período | Escopo |
|----------|--------|---------|--------|
| `/auth/forgot-password` | 3 requests | 1 minuto | Por IP |
| `/auth/reset-password` | 5 requests | 1 minuto | Por IP |
| `/auth/change-password` | 5 requests | 1 minuto | Por IP |
| `/admin/superadmins` | 60 requests | 1 minuto | Por IP (limite global da API) |

### Resposta de Rate Limit Excedido

```json
{
  "detail": "Rate limit exceeded: 3 per 1 minute"
}
```

**Status Code:** `429 Too Many Requests`

**Retry-After header:** Indica quando a limitação expira (em segundos)

### Tratamento no Frontend

```typescript
const handleRateLimitError = (error: AxiosError) => {
  if (error.response?.status === 429) {
    const retryAfter = error.response.headers['retry-after'];
    const message = retryAfter 
      ? `Muitas tentativas. Tente novamente em ${retryAfter} segundos.`
      : 'Muitas tentativas. Aguarde alguns minutos.';
    
    showError(message);
    
    // Desabilitar botão temporariamente
    if (retryAfter) {
      setDisabledUntil(Date.now() + parseInt(retryAfter) * 1000);
    }
  }
};
```

### Segurança Anti-Enumeração

⚠️ **IMPORTANTE:** O endpoint `/auth/forgot-password` **sempre retorna 200**, mesmo se o email não existir.

**Por quê?**
- Previne atacantes de descobrirem quais emails estão cadastrados no sistema
- Mensagem genérica: "Se o email estiver cadastrado, você receberá um link"

**Implementação correta no frontend:**

```typescript
// ❌ ERRADO - Revela se email existe
if (response.status === 200) {
  showSuccess("Email de recuperação enviado!");
} else {
  showError("Email não encontrado");
}

// ✅ CORRETO - Mensagem genérica sempre
showSuccess("Se o email estiver cadastrado, você receberá um link de recuperação");
```

### Token de Reset

- **Tipo:** JWT HS256 (gerado pelo backend)
- **Validade:** 15 minutos
- **Payload:**
  ```json
  {
    "sub": "user_uuid",
    "role": "password_reset",
    "company_id": "company_uuid",
    "exp": 1713049466
  }
  ```
- **Uso único:** Backend valida que `role === "password_reset"`
- **Expira após uso:** Não (JWT é stateless), mas recomenda-se invalidar na prática

---

## 9. Tratamento de Erros

### Mapeamento de Erros HTTP

| Status | Contexto | Mensagem para Usuário |
|--------|----------|----------------------|
| `400 Bad Request` | Token inválido/expirado | "Link de recuperação inválido ou expirado. Solicite um novo." |
| `400 Bad Request` | Senha atual incorreta | "Senha atual incorreta. Verifique e tente novamente." |
| `401 Unauthorized` | Token de autenticação inválido | "Sessão expirada. Faça login novamente." |
| `403 Forbidden` | Usuário não é SUPER_ADMIN | "Você não tem permissão para criar superadmins." |
| `404 Not Found` | Usuário não encontrado | "Usuário não encontrado no sistema." |
| `409 Conflict` | Email ou CPF duplicado | "Email ou CPF/CNPJ já cadastrado." |
| `422 Unprocessable Entity` | Validação de senha falhou | "Senha não atende aos requisitos de segurança." |
| `429 Too Many Requests` | Rate limit excedido | "Muitas tentativas. Aguarde alguns minutos." |
| `500 Internal Server Error` | Erro no servidor | "Erro no servidor. Tente novamente mais tarde." |

### Componente de Tratamento de Erros

```typescript
interface ApiError {
  response?: {
    status: number;
    data: {
      detail: string | Array<{ msg: string; loc: string[] }>;
    };
  };
}

function handleApiError(error: ApiError, context: string): string {
  const status = error.response?.status;
  const detail = error.response?.data?.detail;
  
  // Validação Pydantic (422)
  if (status === 422 && Array.isArray(detail)) {
    const messages = detail.map(err => err.msg).join(', ');
    return `Erro de validação: ${messages}`;
  }
  
  // Mapeamento por status
  switch (status) {
    case 400:
      if (context === 'reset-password') {
        return 'Link de recuperação inválido ou expirado. Solicite um novo.';
      }
      if (context === 'change-password') {
        return 'Senha atual incorreta.';
      }
      return typeof detail === 'string' ? detail : 'Requisição inválida.';
    
    case 401:
      return 'Sessão expirada. Faça login novamente.';
    
    case 403:
      return 'Você não tem permissão para realizar esta ação.';
    
    case 404:
      return 'Recurso não encontrado.';
    
    case 409:
      return typeof detail === 'string' ? detail : 'Dados duplicados.';
    
    case 422:
      return 'Dados inválidos. Verifique os campos e tente novamente.';
    
    case 429:
      return 'Muitas tentativas. Aguarde alguns minutos.';
    
    case 500:
      return 'Erro no servidor. Tente novamente mais tarde.';
    
    default:
      return 'Erro inesperado. Tente novamente.';
  }
}

// Uso
try {
  await api.post('/auth/reset-password', data);
} catch (error) {
  const message = handleApiError(error as ApiError, 'reset-password');
  showError(message);
}
```

---

## 10. Checklist de Implementação

### Frontend

#### Telas

- [ ] **Página "Esqueci minha senha"** (`/forgot-password`)
  - [ ] Input de email com validação
  - [ ] Botão de enviar com loading state
  - [ ] Mensagem de sucesso genérica
  - [ ] Link para voltar ao login
  - [ ] Tratamento de rate limit (429)

- [ ] **Página "Redefinir senha"** (`/reset-password?token=...`)
  - [ ] Extrair token da query string
  - [ ] Inputs de nova senha e confirmação
  - [ ] Indicador de força da senha
  - [ ] Validação em tempo real
  - [ ] Tratamento de token expirado
  - [ ] Redirecionamento para login após sucesso

- [ ] **Seção "Alterar senha"** (em configurações/perfil)
  - [ ] Input de senha atual
  - [ ] Inputs de nova senha e confirmação
  - [ ] Indicador de força da senha
  - [ ] Validação em tempo real
  - [ ] Tratamento de "senha atual incorreta"
  - [ ] Limpar formulário após sucesso

- [ ] **Atualizar "Gerenciamento de Funcionários"**
  - [ ] Adicionar dropdown de tipo de conta (STAFF/SUPER_ADMIN)
  - [ ] Condicionar permissões granulares apenas para STAFF
  - [ ] Endpoint diferente por tipo
  - [ ] Badge visual na listagem (Superadmin vs Funcionário)
  - [ ] Botão "Recuperar senha" em cada linha
  - [ ] Validação de permissão (só SUPER_ADMIN cria SUPER_ADMIN)

- [ ] **Adicionar botão "Recuperar senha"** nas telas:
  - [ ] Listagem de funcionários
  - [ ] Listagem de clientes
  - [ ] Detalhes de funcionário
  - [ ] Detalhes de cliente

#### Componentes

- [ ] **PasswordStrengthIndicator**
  - [ ] Barra de progresso colorida
  - [ ] Lista de requisitos com ícones check
  - [ ] Atualização em tempo real

- [ ] **PasswordInput**
  - [ ] Toggle de visibilidade (olho)
  - [ ] Validação integrada
  - [ ] Estados: default, error, success

- [ ] **SendPasswordResetButton**
  - [ ] Confirmação antes de enviar
  - [ ] Loading state
  - [ ] Tratamento de erros

#### Serviços/API

- [ ] **Criar helpers de validação**
  - [ ] `validatePassword(password: string)`
  - [ ] `validateEmail(email: string)`
  - [ ] `checkPasswordStrength(password: string)`

- [ ] **Criar funções de API**
  - [ ] `forgotPassword(email: string)`
  - [ ] `resetPassword(token: string, newPassword: string)`
  - [ ] `changePassword(currentPassword: string, newPassword: string)`
  - [ ] `createSuperadmin(data: SuperadminCreateRequest)`

- [ ] **Atualizar interceptor de erros**
  - [ ] Mapear status 429 (rate limit)
  - [ ] Mapear status 422 (validação Pydantic)
  - [ ] Extrair mensagens de erro do backend

#### Tipos TypeScript

- [ ] Criar interfaces:
  - [ ] `ForgotPasswordRequest`
  - [ ] `ResetPasswordRequest`
  - [ ] `PasswordChangeRequest`
  - [ ] `PasswordResetResponse`
  - [ ] `SuperadminCreateRequest`
  - [ ] `SuperadminResponse`

#### Testes

- [ ] Testar fluxo completo de recuperação de senha
- [ ] Testar validação de senha fraca
- [ ] Testar token expirado
- [ ] Testar senha atual incorreta
- [ ] Testar criação de superadmin (403 se não for SUPER_ADMIN)
- [ ] Testar email duplicado
- [ ] Testar rate limiting

### Backend (Já Implementado ✅)

- [x] Schemas de senha (`auth.py`)
- [x] Schemas de superadmin (`superadmin.py`)
- [x] Service de criação de superadmin (`superadmin_service.py`)
- [x] Endpoints de senha (`/auth/forgot-password`, `/reset-password`, `/change-password`)
- [x] Endpoint de superadmin (`/admin/superadmins`)
- [x] Template de email de recuperação (`email_service.py`)
- [x] Rate limiting configurado
- [x] Validação de força de senha
- [x] **FIX:** `SuperadminResponse` usar `uuid.UUID` ao invés de `str` ✅

### Documentação

- [ ] Atualizar README do frontend com novos fluxos
- [ ] Documentar variável de ambiente `FRONTEND_URL` no backend
- [ ] Criar guia de troubleshooting para erros comuns

---

## Notas Finais

### Variáveis de Ambiente

**Backend (`.env`):**
```env
FRONTEND_URL=http://localhost:5173  # URL do frontend para link de reset
```

**Frontend (`.env.local`):**
```env
VITE_API_URL=http://localhost:8000/api/v1  # URL da API
```

### Deploy

- **Backend:** Atualizar `FRONTEND_URL` para URL de produção
- **Frontend:** Garantir que `VITE_API_URL` aponte para backend de produção

### Email de Recuperação

O email enviado contém:
- Link: `{FRONTEND_URL}/reset-password?token={JWT}`
- Validade: 15 minutos
- Template HTML com botão estilizado
- Aviso de expiração

**Exemplo de link:**
```
https://app.exemplo.com/reset-password?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Observações de Segurança

1. **Nunca** logue senhas em plain text
2. **Sempre** use HTTPS em produção
3. **Nunca** exponha tokens em URLs de logs/analytics
4. **Sempre** valide senha no backend (não confie apenas no frontend)
5. **Considere** implementar CAPTCHA para prevenir abuso de `/forgot-password`

---

**Documento criado em:** Abril 2026  
**Última atualização:** 13/04/2026  
**Versão:** 1.0
