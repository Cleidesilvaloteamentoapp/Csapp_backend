# Instruções Backend - Portal do Cliente

## 📋 Índice
1. [Visão Geral](#visão-geral)
2. [Endpoints Necessários](#endpoints-necessários)
3. [Segurança e RLS](#segurança-e-rls)
4. [Modelos de Dados](#modelos-de-dados)
5. [Exemplos de Implementação](#exemplos-de-implementação)

---

## Visão Geral

O portal do cliente permite que clientes autenticados:
- **Visualizem** todos os seus boletos
- **Baixem** PDFs dos boletos
- **Solicitem** segunda via com juros/multa
- **Façam upload** de documentos
- **Acompanhem** status de serviços/solicitações

**Princípio de Segurança:** SEMPRE filtrar dados pelo `client_id` vinculado ao `profile_id` do usuário autenticado.

---

## Endpoints Necessários

### 1. Boletos do Cliente

#### 1.1 Listar Todos os Boletos
```
GET /api/v1/client/boletos
```

**Autenticação:** Bearer Token (role: `CLIENT`)

**Lógica:**
1. Obter `profile_id` do token JWT
2. Buscar `client_id` vinculado ao `profile_id` na tabela `clients`
3. Retornar todos os boletos onde `client_id` = cliente autenticado

**Response 200:**
```json
[
  {
    "id": "uuid",
    "nosso_numero": "600000078",
    "seu_numero": "BATa78c006",
    "linha_digitavel": "74891...",
    "codigo_barras": "74895...",
    "tipo_cobranca": "NORMAL",
    "data_vencimento": "2026-08-13",
    "data_emissao": "2026-03-10",
    "data_liquidacao": null,
    "valor": "100.00",
    "valor_liquidacao": null,
    "status": "NORMAL",
    "txid": null,
    "qr_code": null,
    "client": {
      "id": "uuid",
      "full_name": "Nickson Ferreira Aleixo",
      "cpf_cnpj": "14835515714",
      "email": "nicksonferreira94@gmail.com",
      "phone": "27988491255"
    },
    "created_at": "2026-03-10T13:41:25.084766Z",
    "updated_at": "2026-03-10T13:41:25.084770Z"
  }
]
```

**SQL (PostgreSQL com RLS):**
```sql
-- Política RLS para tabela boletos
CREATE POLICY "client_own_boletos" ON boletos
  FOR SELECT
  USING (
    client_id IN (
      SELECT id FROM clients 
      WHERE profile_id = auth.uid()
    )
  );
```

**Exemplo Python (FastAPI):**
```python
from fastapi import APIRouter, Depends, HTTPException
from typing import List

router = APIRouter(prefix="/client", tags=["Client Portal"])

@router.get("/boletos", response_model=List[BoletoResponse])
async def list_client_boletos(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lista todos os boletos do cliente autenticado."""
    
    # 1. Validar que user tem role CLIENT
    if current_user.role != "client":
        raise HTTPException(403, "Acesso negado")
    
    # 2. Buscar client_id vinculado ao profile_id
    client = db.query(Client).filter(
        Client.profile_id == current_user.id
    ).first()
    
    if not client:
        raise HTTPException(404, "Cliente não encontrado para este perfil")
    
    # 3. Buscar boletos do cliente com dados aninhados
    boletos = db.query(Boleto).options(
        joinedload(Boleto.client)
    ).filter(
        Boleto.client_id == client.id
    ).order_by(
        Boleto.data_vencimento.desc()
    ).all()
    
    return boletos
```

---

#### 1.2 Detalhes de um Boleto Específico
```
GET /api/v1/client/boletos/{nosso_numero}
```

**Autenticação:** Bearer Token (role: `CLIENT`)

**Validação:** Verificar que o boleto pertence ao cliente autenticado

**Response 200:** Objeto `BoletoDetails` completo

---

#### 1.3 Download PDF do Boleto
```
GET /api/v1/client/boletos/{nosso_numero}/pdf
```

**Autenticação:** Bearer Token (role: `CLIENT`)

**Lógica:**
1. Validar que boleto pertence ao cliente
2. Buscar PDF do Sicredi ou gerar localmente
3. Retornar blob do PDF

**Response 200:** `application/pdf`

---

### 2. Segunda Via

#### 2.1 Preview Segunda Via
```
GET /api/v1/client/boletos/segunda-via/preview/{invoice_id}
```

**Autenticação:** Bearer Token (role: `CLIENT`)

**Response 200:**
```json
{
  "invoice_id": "uuid",
  "original_boleto": {
    "nosso_numero": "600000001",
    "valor_original": "1000.00",
    "data_vencimento_original": "2026-01-15",
    "status": "VENCIDO"
  },
  "segunda_via": {
    "data_vencimento_nova": "2026-03-20",
    "valor_principal": "1000.00",
    "juros": "50.00",
    "multa": "20.00",
    "valor_total": "1070.00",
    "dias_atraso": 64
  }
}
```

---

#### 2.2 Solicitar Segunda Via
```
POST /api/v1/client/boletos/segunda-via/issue/{invoice_id}
```

**Autenticação:** Bearer Token (role: `CLIENT`)

**Request Body:**
```json
{
  "data_vencimento": "2026-03-20"
}
```

**Response 201:**
```json
{
  "boleto_id": "uuid",
  "nosso_numero": "600000099",
  "linha_digitavel": "74891...",
  "codigo_barras": "74895...",
  "valor_total": "1070.00",
  "qr_code": "...",
  "txid": "..."
}
```

---

### 3. Perfil do Cliente

#### 3.1 Dados do Perfil
```
GET /api/v1/client/profile
```

**Autenticação:** Bearer Token (role: `CLIENT`)

**Response 200:**
```json
{
  "id": "1487c119-26bb-4e56-9f6b-1479ac7076b3",
  "profile_id": "de009358-6031-40ef-88e9-dfa9e73e0af6",
  "full_name": "Nickson Ferreira Aleixo",
  "cpf_cnpj": "14835515714",
  "email": "nicksonferreira94@gmail.com",
  "phone": "27988491255",
  "address": {
    "zip": "29230000",
    "city": "Anchieta",
    "state": "ES",
    "street": "Rua fernando vianna",
    "number": "0"
  },
  "status": "ACTIVE",
  "created_at": "2026-03-10T13:21:36.942621Z"
}
```

---

### 4. Documentos e Uploads

#### 4.1 Listar Documentos do Cliente
```
GET /api/v1/client/documents
```

**Autenticação:** Bearer Token (role: `CLIENT`)

**Response 200:**
```json
[
  {
    "id": "uuid",
    "client_id": "uuid",
    "document_type": "RG",
    "file_name": "rg_frente.pdf",
    "file_url": "https://storage.../rg_frente.pdf",
    "file_size": 245678,
    "uploaded_at": "2026-03-10T14:30:00Z",
    "status": "APPROVED"
  }
]
```

---

#### 4.2 Upload de Documento
```
POST /api/v1/client/documents/upload
```

**Autenticação:** Bearer Token (role: `CLIENT`)

**Content-Type:** `multipart/form-data`

**Request:**
```
document_type: "RG" | "CPF" | "COMPROVANTE_RESIDENCIA" | "OUTROS"
file: arquivo (PDF, JPG, PNG)
description: string (opcional)
```

**Response 201:**
```json
{
  "id": "uuid",
  "document_type": "RG",
  "file_name": "rg_frente.pdf",
  "file_url": "https://storage.../rg_frente.pdf",
  "status": "PENDING_REVIEW",
  "uploaded_at": "2026-03-10T14:30:00Z"
}
```

**Validações:**
- Tamanho máximo: 10MB
- Formatos aceitos: PDF, JPG, JPEG, PNG
- Nome do arquivo sanitizado
- Upload para storage seguro (S3, Google Cloud Storage, etc)

**Exemplo Python:**
```python
from fastapi import UploadFile, File

@router.post("/documents/upload")
async def upload_document(
    document_type: str,
    file: UploadFile = File(...),
    description: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload de documento do cliente."""
    
    # 1. Validar tipo de arquivo
    allowed_types = ["application/pdf", "image/jpeg", "image/png"]
    if file.content_type not in allowed_types:
        raise HTTPException(400, "Tipo de arquivo não permitido")
    
    # 2. Validar tamanho (10MB)
    file_size = 0
    contents = await file.read()
    file_size = len(contents)
    
    if file_size > 10 * 1024 * 1024:
        raise HTTPException(400, "Arquivo muito grande (máx 10MB)")
    
    # 3. Buscar client_id
    client = db.query(Client).filter(
        Client.profile_id == current_user.id
    ).first()
    
    # 4. Upload para storage
    file_name = f"{client.id}/{document_type}_{uuid4()}.{file.filename.split('.')[-1]}"
    file_url = await upload_to_storage(file_name, contents)
    
    # 5. Registrar no banco
    document = ClientDocument(
        client_id=client.id,
        document_type=document_type,
        file_name=file.filename,
        file_url=file_url,
        file_size=file_size,
        description=description,
        status="PENDING_REVIEW"
    )
    db.add(document)
    db.commit()
    
    return document
```

---

#### 4.3 Download de Documento
```
GET /api/v1/client/documents/{document_id}/download
```

**Autenticação:** Bearer Token (role: `CLIENT`)

**Validação:** Documento pertence ao cliente autenticado

**Response 200:** Redirect ou blob do arquivo

---

### 5. Solicitações de Serviço

#### 5.1 Criar Solicitação
```
POST /api/v1/client/service-requests
```

**Autenticação:** Bearer Token (role: `CLIENT`)

**Request Body:**
```json
{
  "service_type": "MANUTENCAO" | "SUPORTE" | "FINANCEIRO" | "OUTROS",
  "subject": "Solicitação de manutenção no lote 123",
  "description": "Descrição detalhada...",
  "priority": "LOW" | "MEDIUM" | "HIGH",
  "attachments": ["document_id_1", "document_id_2"]
}
```

**Response 201:**
```json
{
  "id": "uuid",
  "client_id": "uuid",
  "ticket_number": "REQ-2026-0001",
  "service_type": "MANUTENCAO",
  "subject": "Solicitação de manutenção no lote 123",
  "status": "OPEN",
  "priority": "MEDIUM",
  "created_at": "2026-03-10T15:00:00Z"
}
```

---

#### 5.2 Listar Solicitações
```
GET /api/v1/client/service-requests
```

**Query params:**
- `status`: OPEN | IN_PROGRESS | RESOLVED | CLOSED
- `service_type`: filtro por tipo
- `page`, `per_page`: paginação

**Response 200:** Lista paginada de solicitações

---

#### 5.3 Detalhes de uma Solicitação
```
GET /api/v1/client/service-requests/{request_id}
```

**Response 200:**
```json
{
  "id": "uuid",
  "ticket_number": "REQ-2026-0001",
  "service_type": "MANUTENCAO",
  "subject": "...",
  "description": "...",
  "status": "IN_PROGRESS",
  "priority": "MEDIUM",
  "created_at": "2026-03-10T15:00:00Z",
  "updated_at": "2026-03-10T16:30:00Z",
  "assigned_to": {
    "id": "uuid",
    "full_name": "Técnico Responsável"
  },
  "messages": [
    {
      "id": "uuid",
      "author": "client",
      "author_name": "Nickson Ferreira Aleixo",
      "message": "Mensagem do cliente",
      "created_at": "2026-03-10T15:00:00Z"
    },
    {
      "id": "uuid",
      "author": "admin",
      "author_name": "Atendente",
      "message": "Resposta do atendente",
      "created_at": "2026-03-10T16:30:00Z"
    }
  ],
  "attachments": [...]
}
```

---

#### 5.4 Adicionar Mensagem/Comentário
```
POST /api/v1/client/service-requests/{request_id}/messages
```

**Request Body:**
```json
{
  "message": "Mensagem do cliente...",
  "attachments": ["document_id"]
}
```

**Response 201:** Objeto da mensagem criada

---

## Segurança e RLS

### Row Level Security (PostgreSQL)

**CRÍTICO:** Todas as tabelas que contêm dados de clientes DEVEM ter RLS ativo.

#### Tabela: `boletos`
```sql
ALTER TABLE boletos ENABLE ROW LEVEL SECURITY;

-- Cliente vê apenas seus boletos
CREATE POLICY "client_view_own_boletos" ON boletos
  FOR SELECT
  USING (
    client_id IN (
      SELECT id FROM clients WHERE profile_id = auth.uid()
    )
  );

-- Cliente não pode modificar boletos
CREATE POLICY "client_no_modify_boletos" ON boletos
  FOR ALL
  USING (false)
  WITH CHECK (false);
```

#### Tabela: `clients`
```sql
ALTER TABLE clients ENABLE ROW LEVEL SECURITY;

-- Cliente vê apenas seu próprio perfil
CREATE POLICY "client_view_own_profile" ON clients
  FOR SELECT
  USING (profile_id = auth.uid());

-- Cliente pode atualizar dados limitados
CREATE POLICY "client_update_own_profile" ON clients
  FOR UPDATE
  USING (profile_id = auth.uid())
  WITH CHECK (
    profile_id = auth.uid() 
    AND role = OLD.role  -- Não pode mudar a role
    AND id = OLD.id      -- Não pode mudar o ID
  );
```

#### Tabela: `client_documents`
```sql
ALTER TABLE client_documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY "client_own_documents" ON client_documents
  FOR ALL
  USING (
    client_id IN (
      SELECT id FROM clients WHERE profile_id = auth.uid()
    )
  );
```

#### Tabela: `service_requests`
```sql
ALTER TABLE service_requests ENABLE ROW LEVEL SECURITY;

CREATE POLICY "client_own_requests" ON service_requests
  FOR ALL
  USING (
    client_id IN (
      SELECT id FROM clients WHERE profile_id = auth.uid()
    )
  );
```

---

### Validação de Autenticação

**Middleware de Autenticação:**
```python
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(get_db)
) -> User:
    """Valida token JWT e retorna usuário autenticado."""
    
    token = credentials.credentials
    
    try:
        # Decodificar JWT
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("sub")
        
        if not user_id:
            raise HTTPException(401, "Token inválido")
        
        # Buscar usuário
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise HTTPException(401, "Usuário não encontrado")
        
        return user
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expirado")
    except jwt.JWTError:
        raise HTTPException(401, "Token inválido")
```

**Validação de Role:**
```python
def require_client_role(current_user: User = Depends(get_current_user)):
    """Requer que usuário tenha role CLIENT."""
    if current_user.role != "client":
        raise HTTPException(403, "Acesso negado. Apenas clientes podem acessar.")
    return current_user
```

---

## Modelos de Dados

### Tabela: `client_documents`
```sql
CREATE TABLE client_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  document_type VARCHAR(50) NOT NULL,
  file_name VARCHAR(255) NOT NULL,
  file_url TEXT NOT NULL,
  file_size INTEGER NOT NULL,
  description TEXT,
  status VARCHAR(20) DEFAULT 'PENDING_REVIEW',
  uploaded_at TIMESTAMPTZ DEFAULT NOW(),
  reviewed_at TIMESTAMPTZ,
  reviewed_by UUID REFERENCES auth.users(id),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_client_documents_client ON client_documents(client_id);
CREATE INDEX idx_client_documents_status ON client_documents(status);
```

**Document Types:**
- `RG` - Registro Geral
- `CPF` - Cadastro de Pessoa Física
- `COMPROVANTE_RESIDENCIA` - Comprovante de endereço
- `CNH` - Carteira de Habilitação
- `CONTRATO` - Contrato assinado
- `OUTROS` - Outros documentos

**Status:**
- `PENDING_REVIEW` - Aguardando revisão
- `APPROVED` - Aprovado
- `REJECTED` - Rejeitado
- `EXPIRED` - Expirado

---

### Tabela: `service_requests`
```sql
CREATE TABLE service_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  ticket_number VARCHAR(50) UNIQUE NOT NULL,
  service_type VARCHAR(50) NOT NULL,
  subject VARCHAR(255) NOT NULL,
  description TEXT NOT NULL,
  status VARCHAR(20) DEFAULT 'OPEN',
  priority VARCHAR(20) DEFAULT 'MEDIUM',
  assigned_to UUID REFERENCES auth.users(id),
  resolved_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_service_requests_client ON service_requests(client_id);
CREATE INDEX idx_service_requests_status ON service_requests(status);
CREATE INDEX idx_service_requests_ticket ON service_requests(ticket_number);
```

**Service Types:**
- `MANUTENCAO` - Manutenção
- `SUPORTE` - Suporte técnico
- `FINANCEIRO` - Questões financeiras
- `DOCUMENTACAO` - Documentação
- `OUTROS` - Outros

**Status:**
- `OPEN` - Aberto
- `IN_PROGRESS` - Em andamento
- `WAITING_CLIENT` - Aguardando cliente
- `RESOLVED` - Resolvido
- `CLOSED` - Fechado

**Priority:**
- `LOW` - Baixa
- `MEDIUM` - Média
- `HIGH` - Alta
- `URGENT` - Urgente

---

### Tabela: `service_request_messages`
```sql
CREATE TABLE service_request_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id UUID NOT NULL REFERENCES service_requests(id) ON DELETE CASCADE,
  author_id UUID NOT NULL REFERENCES auth.users(id),
  author_type VARCHAR(20) NOT NULL, -- 'client' | 'admin'
  message TEXT NOT NULL,
  is_internal BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_messages_request ON service_request_messages(request_id);
```

---

## Exemplos de Implementação

### FastAPI - Router Completo

```python
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
import uuid

router = APIRouter(prefix="/client", tags=["Client Portal"])

# ==================== BOLETOS ====================

@router.get("/boletos", response_model=List[BoletoResponse])
async def list_client_boletos(
    current_user: User = Depends(require_client_role),
    db: Session = Depends(get_db)
):
    """Lista todos os boletos do cliente autenticado."""
    client = get_client_by_profile(db, current_user.id)
    
    boletos = db.query(Boleto).options(
        joinedload(Boleto.client)
    ).filter(
        Boleto.client_id == client.id
    ).order_by(
        Boleto.data_vencimento.desc()
    ).all()
    
    return boletos


@router.get("/boletos/{nosso_numero}", response_model=BoletoDetailsResponse)
async def get_client_boleto(
    nosso_numero: str,
    current_user: User = Depends(require_client_role),
    db: Session = Depends(get_db)
):
    """Detalhes de um boleto específico."""
    client = get_client_by_profile(db, current_user.id)
    
    boleto = db.query(Boleto).filter(
        Boleto.nosso_numero == nosso_numero,
        Boleto.client_id == client.id
    ).first()
    
    if not boleto:
        raise HTTPException(404, "Boleto não encontrado")
    
    return boleto


@router.get("/boletos/{nosso_numero}/pdf")
async def download_boleto_pdf(
    nosso_numero: str,
    current_user: User = Depends(require_client_role),
    db: Session = Depends(get_db)
):
    """Download do PDF do boleto."""
    client = get_client_by_profile(db, current_user.id)
    
    boleto = db.query(Boleto).filter(
        Boleto.nosso_numero == nosso_numero,
        Boleto.client_id == client.id
    ).first()
    
    if not boleto:
        raise HTTPException(404, "Boleto não encontrado")
    
    # Buscar PDF do Sicredi ou gerar localmente
    pdf_blob = await fetch_boleto_pdf_from_sicredi(nosso_numero)
    
    return Response(
        content=pdf_blob,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=boleto_{nosso_numero}.pdf"
        }
    )


# ==================== PERFIL ====================

@router.get("/profile", response_model=ClientProfileResponse)
async def get_client_profile(
    current_user: User = Depends(require_client_role),
    db: Session = Depends(get_db)
):
    """Retorna dados do perfil do cliente."""
    client = get_client_by_profile(db, current_user.id)
    return client


@router.patch("/profile", response_model=ClientProfileResponse)
async def update_client_profile(
    updates: ClientProfileUpdate,
    current_user: User = Depends(require_client_role),
    db: Session = Depends(get_db)
):
    """Atualiza dados do perfil do cliente."""
    client = get_client_by_profile(db, current_user.id)
    
    # Apenas campos permitidos
    allowed_fields = ["phone", "email", "address"]
    
    for field, value in updates.dict(exclude_unset=True).items():
        if field in allowed_fields:
            setattr(client, field, value)
    
    client.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(client)
    
    return client


# ==================== DOCUMENTOS ====================

@router.get("/documents", response_model=List[ClientDocumentResponse])
async def list_client_documents(
    current_user: User = Depends(require_client_role),
    db: Session = Depends(get_db)
):
    """Lista documentos do cliente."""
    client = get_client_by_profile(db, current_user.id)
    
    documents = db.query(ClientDocument).filter(
        ClientDocument.client_id == client.id
    ).order_by(
        ClientDocument.uploaded_at.desc()
    ).all()
    
    return documents


@router.post("/documents/upload", response_model=ClientDocumentResponse, status_code=201)
async def upload_document(
    document_type: str,
    file: UploadFile = File(...),
    description: Optional[str] = None,
    current_user: User = Depends(require_client_role),
    db: Session = Depends(get_db)
):
    """Upload de documento."""
    client = get_client_by_profile(db, current_user.id)
    
    # Validações
    validate_file_upload(file)
    
    # Upload para storage
    contents = await file.read()
    file_name = f"{client.id}/{document_type}_{uuid.uuid4()}.{get_file_extension(file.filename)}"
    file_url = await upload_to_storage(file_name, contents)
    
    # Registrar no banco
    document = ClientDocument(
        client_id=client.id,
        document_type=document_type,
        file_name=file.filename,
        file_url=file_url,
        file_size=len(contents),
        description=description,
        status="PENDING_REVIEW"
    )
    
    db.add(document)
    db.commit()
    db.refresh(document)
    
    return document


# ==================== SOLICITAÇÕES DE SERVIÇO ====================

@router.post("/service-requests", response_model=ServiceRequestResponse, status_code=201)
async def create_service_request(
    request_data: ServiceRequestCreate,
    current_user: User = Depends(require_client_role),
    db: Session = Depends(get_db)
):
    """Cria nova solicitação de serviço."""
    client = get_client_by_profile(db, current_user.id)
    
    # Gerar ticket number
    ticket_number = generate_ticket_number(db)
    
    service_request = ServiceRequest(
        client_id=client.id,
        ticket_number=ticket_number,
        service_type=request_data.service_type,
        subject=request_data.subject,
        description=request_data.description,
        priority=request_data.priority or "MEDIUM",
        status="OPEN"
    )
    
    db.add(service_request)
    db.commit()
    db.refresh(service_request)
    
    # Criar mensagem inicial
    message = ServiceRequestMessage(
        request_id=service_request.id,
        author_id=current_user.id,
        author_type="client",
        message=request_data.description
    )
    db.add(message)
    db.commit()
    
    return service_request


@router.get("/service-requests", response_model=List[ServiceRequestResponse])
async def list_service_requests(
    status: Optional[str] = None,
    service_type: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    current_user: User = Depends(require_client_role),
    db: Session = Depends(get_db)
):
    """Lista solicitações de serviço do cliente."""
    client = get_client_by_profile(db, current_user.id)
    
    query = db.query(ServiceRequest).filter(
        ServiceRequest.client_id == client.id
    )
    
    if status:
        query = query.filter(ServiceRequest.status == status)
    if service_type:
        query = query.filter(ServiceRequest.service_type == service_type)
    
    query = query.order_by(ServiceRequest.created_at.desc())
    
    # Paginação
    offset = (page - 1) * per_page
    requests = query.offset(offset).limit(per_page).all()
    
    return requests


# ==================== HELPERS ====================

def get_client_by_profile(db: Session, profile_id: str) -> Client:
    """Busca cliente vinculado ao profile_id."""
    client = db.query(Client).filter(
        Client.profile_id == profile_id
    ).first()
    
    if not client:
        raise HTTPException(404, "Cliente não encontrado para este perfil")
    
    return client


def validate_file_upload(file: UploadFile):
    """Valida arquivo de upload."""
    allowed_types = ["application/pdf", "image/jpeg", "image/png", "image/jpg"]
    
    if file.content_type not in allowed_types:
        raise HTTPException(400, "Tipo de arquivo não permitido")
    
    # Validar extensão também
    allowed_extensions = [".pdf", ".jpg", ".jpeg", ".png"]
    ext = os.path.splitext(file.filename)[1].lower()
    
    if ext not in allowed_extensions:
        raise HTTPException(400, "Extensão de arquivo não permitida")


def generate_ticket_number(db: Session) -> str:
    """Gera número único para ticket."""
    year = datetime.utcnow().year
    
    # Contar tickets do ano
    count = db.query(ServiceRequest).filter(
        ServiceRequest.ticket_number.like(f"REQ-{year}-%")
    ).count()
    
    return f"REQ-{year}-{str(count + 1).zfill(4)}"
```

---

## Checklist de Implementação

### Endpoints Essenciais (Prioridade ALTA)
- [ ] `GET /client/boletos` - Listar boletos
- [ ] `GET /client/boletos/{nosso_numero}` - Detalhes do boleto
- [ ] `GET /client/boletos/{nosso_numero}/pdf` - Download PDF
- [ ] `GET /client/profile` - Dados do perfil
- [ ] `PATCH /client/profile` - Atualizar perfil

### Documentos (Prioridade MÉDIA)
- [ ] `GET /client/documents` - Listar documentos
- [ ] `POST /client/documents/upload` - Upload
- [ ] `GET /client/documents/{id}/download` - Download
- [ ] `DELETE /client/documents/{id}` - Excluir

### Solicitações (Prioridade MÉDIA)
- [ ] `POST /client/service-requests` - Criar solicitação
- [ ] `GET /client/service-requests` - Listar
- [ ] `GET /client/service-requests/{id}` - Detalhes
- [ ] `POST /client/service-requests/{id}/messages` - Adicionar mensagem

### Segunda Via (Prioridade BAIXA)
- [ ] `GET /client/boletos/segunda-via/preview/{invoice_id}`
- [ ] `POST /client/boletos/segunda-via/issue/{invoice_id}`

### Segurança
- [ ] RLS ativo em todas as tabelas de cliente
- [ ] Validação de role CLIENT em todos os endpoints
- [ ] Validação de ownership (cliente só acessa seus dados)
- [ ] Rate limiting por IP/usuário
- [ ] Logs de auditoria para ações sensíveis

### Storage
- [ ] Configurar bucket para uploads (S3, GCS, etc)
- [ ] URLs assinadas com expiração para downloads
- [ ] Scan de vírus em uploads
- [ ] Backup automático de documentos

---

## Testes Recomendados

### Casos de Teste

1. **Autenticação:**
   - Cliente consegue fazer login
   - Token JWT válido por 24h
   - Refresh token funciona

2. **Boletos:**
   - Cliente vê apenas seus boletos
   - Cliente não vê boletos de outros
   - Filtros funcionam corretamente
   - PDF download funciona

3. **Upload:**
   - Aceita PDF, JPG, PNG
   - Rejeita arquivos > 10MB
   - Rejeita tipos não permitidos
   - Sanitiza nomes de arquivo

4. **Segurança:**
   - RLS bloqueia acesso a dados de outros
   - Cliente não pode modificar role
   - Cliente não acessa endpoints admin

---

## Observações Finais

1. **Use sempre RLS** - É a primeira linha de defesa
2. **Valide no backend** - Nunca confie no frontend
3. **Logs de auditoria** - Registre acessos sensíveis
4. **HTTPS obrigatório** - Nunca HTTP em produção
5. **Rate limiting** - Proteja contra abuso
6. **Backup** - Documentos e dados críticos
7. **LGPD** - Permita que cliente exclua seus dados

---

**Dúvidas?** Consulte a documentação completa em `/docs/FRONTEND_BOLETOS_CENTRAL.md`
