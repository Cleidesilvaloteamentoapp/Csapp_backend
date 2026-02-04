from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Annotated, Optional, List
from datetime import date, datetime
from decimal import Decimal
from supabase import Client

from app.api.deps import get_db, get_admin_db, require_admin_role
from app.schemas.client import (
    ClientCreate,
    ClientUpdate,
    ClientResponse,
    ClientListResponse,
    ClientStatus
)
from app.schemas.lot import (
    DevelopmentCreate,
    DevelopmentUpdate,
    DevelopmentResponse,
    LotCreate,
    LotUpdate,
    LotResponse,
    ClientLotCreate,
    ClientLotResponse,
    LotStatus
)
from app.schemas.invoice import InvoiceResponse, InvoiceStatus
from app.schemas.service import (
    ServiceTypeCreate,
    ServiceTypeUpdate,
    ServiceTypeResponse,
    ServiceOrderUpdate,
    ServiceOrderResponse,
    ServiceOrderStatus,
    ServiceAnalytics
)
from app.schemas.dashboard import AdminDashboardStats, AdminFinancialDashboard, DefaulterInfo
from app.services.asaas import get_asaas_service, AsaasService
from app.models.enums import ClientStatus as ClientStatusEnum, LotStatus as LotStatusEnum

router = APIRouter(prefix="/admin", tags=["Admin"])


# ============== DASHBOARD ==============

@router.get("/dashboard/stats", response_model=AdminDashboardStats)
async def get_dashboard_stats(
    admin: Annotated[dict, Depends(require_admin_role)],
    db: Annotated[Client, Depends(get_admin_db)]
):
    """Get admin dashboard statistics"""
    clients = db.table("clients").select("status", count="exact").execute()
    total_clients = clients.count or 0
    
    active_clients = db.table("clients").select("id", count="exact").eq("status", "active").execute()
    active_count = active_clients.count or 0
    
    defaulters = db.table("clients").select("id", count="exact").eq("status", "defaulter").execute()
    defaulter_count = defaulters.count or 0
    
    lots = db.table("lots").select("status", count="exact").execute()
    total_lots = lots.count or 0
    
    available_lots = db.table("lots").select("id", count="exact").eq("status", "available").execute()
    available_count = available_lots.count or 0
    
    sold_lots = db.table("lots").select("id", count="exact").eq("status", "sold").execute()
    sold_count = sold_lots.count or 0
    
    open_orders = db.table("service_orders").select("id", count="exact").in_(
        "status", ["requested", "approved", "in_progress"]
    ).execute()
    open_orders_count = open_orders.count or 0
    
    completed_orders = db.table("service_orders").select("id", count="exact").eq(
        "status", "completed"
    ).execute()
    completed_count = completed_orders.count or 0
    
    return AdminDashboardStats(
        total_clients=total_clients,
        active_clients=active_count,
        defaulter_clients=defaulter_count,
        total_lots=total_lots,
        available_lots=available_count,
        sold_lots=sold_count,
        open_service_orders=open_orders_count,
        completed_service_orders=completed_count
    )


@router.get("/dashboard/financial", response_model=AdminFinancialDashboard)
async def get_financial_dashboard(
    admin: Annotated[dict, Depends(require_admin_role)],
    db: Annotated[Client, Depends(get_admin_db)]
):
    """Get financial analysis dashboard"""
    pending_invoices = db.table("invoices").select("amount").eq("status", "pending").execute()
    total_receivables = sum(Decimal(str(inv["amount"])) for inv in (pending_invoices.data or []))
    
    paid_invoices = db.table("invoices").select("amount").eq("status", "paid").execute()
    total_received = sum(Decimal(str(inv["amount"])) for inv in (paid_invoices.data or []))
    
    overdue_invoices = db.table("invoices").select(
        "amount, due_date, client_lot_id"
    ).eq("status", "overdue").execute()
    total_overdue = sum(Decimal(str(inv["amount"])) for inv in (overdue_invoices.data or []))
    
    defaulters = []
    if overdue_invoices.data:
        client_lot_ids = list(set(inv["client_lot_id"] for inv in overdue_invoices.data))
        
        for cl_id in client_lot_ids[:10]:
            client_lot = db.table("client_lots").select(
                "client_id, clients(id, profile_id, profiles(full_name, cpf_cnpj, phone))"
            ).eq("id", cl_id).single().execute()
            
            if client_lot.data:
                client_overdue = [inv for inv in overdue_invoices.data if inv["client_lot_id"] == cl_id]
                client_data = client_lot.data.get("clients", {})
                profile_data = client_data.get("profiles", {}) if client_data else {}
                
                defaulters.append(DefaulterInfo(
                    client_id=client_data.get("id", ""),
                    client_name=profile_data.get("full_name", ""),
                    cpf_cnpj=profile_data.get("cpf_cnpj", ""),
                    phone=profile_data.get("phone", ""),
                    overdue_amount=sum(Decimal(str(inv["amount"])) for inv in client_overdue),
                    overdue_invoices_count=len(client_overdue),
                    oldest_overdue_date=min(inv["due_date"] for inv in client_overdue)
                ))
    
    services = db.table("service_orders").select("cost, revenue").eq("status", "completed").execute()
    service_costs = sum(Decimal(str(s.get("cost", 0) or 0)) for s in (services.data or []))
    service_revenue = sum(Decimal(str(s.get("revenue", 0) or 0)) for s in (services.data or []))
    
    return AdminFinancialDashboard(
        total_receivables=total_receivables,
        total_received=total_received,
        total_overdue=total_overdue,
        defaulters=defaulters,
        revenue_from_services=service_revenue,
        service_costs=service_costs,
        service_profit=service_revenue - service_costs
    )


# ============== CLIENTS ==============

@router.get("/clients", response_model=ClientListResponse)
async def list_clients(
    admin: Annotated[dict, Depends(require_admin_role)],
    db: Annotated[Client, Depends(get_admin_db)],
    status: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
):
    """List all clients with filters and pagination"""
    query = db.table("clients").select(
        "*, profiles(full_name, cpf_cnpj, phone, asaas_customer_id)",
        count="exact"
    )
    
    if status:
        query = query.eq("status", status)
    
    if search:
        query = query.or_(f"email.ilike.%{search}%,profiles.full_name.ilike.%{search}%")
    
    offset = (page - 1) * page_size
    query = query.range(offset, offset + page_size - 1).order("created_at", desc=True)
    
    result = query.execute()
    
    items = []
    for client in (result.data or []):
        profile = client.get("profiles", {}) or {}
        items.append(ClientResponse(
            id=client["id"],
            profile_id=client["profile_id"],
            email=client["email"],
            full_name=profile.get("full_name", ""),
            cpf_cnpj=profile.get("cpf_cnpj", ""),
            phone=profile.get("phone", ""),
            address=client.get("address"),
            documents=client.get("documents"),
            status=ClientStatusEnum(client["status"]),
            asaas_customer_id=profile.get("asaas_customer_id"),
            created_at=client["created_at"],
            updated_at=client["updated_at"]
        ))
    
    total = result.count or 0
    total_pages = (total + page_size - 1) // page_size
    
    return ClientListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.post("/clients", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    request: ClientCreate,
    admin: Annotated[dict, Depends(require_admin_role)],
    db: Annotated[Client, Depends(get_admin_db)],
    asaas: Annotated[AsaasService, Depends(get_asaas_service)]
):
    """
    Create new client with:
    1. Supabase Auth user
    2. Profile record
    3. Client record
    4. Asaas customer
    """
    try:
        auth_response = db.auth.admin.create_user({
            "email": request.email,
            "password": request.password,
            "email_confirm": True,
            "user_metadata": {
                "full_name": request.full_name,
                "role": "client"
            }
        })
        
        if not auth_response.user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create user account"
            )
        
        user_id = auth_response.user.id
        
        try:
            asaas_customer = await asaas.create_customer(
                name=request.full_name,
                cpf_cnpj=request.cpf_cnpj,
                email=request.email,
                phone=request.phone,
                address=request.address.model_dump() if request.address else None
            )
            asaas_customer_id = asaas_customer.get("id")
        except Exception as e:
            print(f"Asaas customer creation failed: {e}")
            asaas_customer_id = None
        
        profile_data = {
            "id": user_id,
            "full_name": request.full_name,
            "cpf_cnpj": request.cpf_cnpj,
            "phone": request.phone,
            "role": "client",
            "asaas_customer_id": asaas_customer_id
        }
        
        profile = db.table("profiles").insert(profile_data).execute()
        
        if not profile.data:
            db.auth.admin.delete_user(user_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create profile"
            )
        
        client_data = {
            "profile_id": user_id,
            "email": request.email,
            "address": request.address.model_dump() if request.address else None,
            "status": "active",
            "created_by": admin["id"]
        }
        
        client = db.table("clients").insert(client_data).execute()
        
        if not client.data:
            db.table("profiles").delete().eq("id", user_id).execute()
            db.auth.admin.delete_user(user_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create client"
            )
        
        client_record = client.data[0]
        
        return ClientResponse(
            id=client_record["id"],
            profile_id=user_id,
            email=request.email,
            full_name=request.full_name,
            cpf_cnpj=request.cpf_cnpj,
            phone=request.phone,
            address=client_record.get("address"),
            documents=None,
            status=ClientStatusEnum.ACTIVE,
            asaas_customer_id=asaas_customer_id,
            created_at=client_record["created_at"],
            updated_at=client_record["updated_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create client: {str(e)}"
        )


@router.get("/clients/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: str,
    admin: Annotated[dict, Depends(require_admin_role)],
    db: Annotated[Client, Depends(get_admin_db)]
):
    """Get client details by ID"""
    result = db.table("clients").select(
        "*, profiles(full_name, cpf_cnpj, phone, asaas_customer_id)"
    ).eq("id", client_id).single().execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    client = result.data
    profile = client.get("profiles", {}) or {}
    
    return ClientResponse(
        id=client["id"],
        profile_id=client["profile_id"],
        email=client["email"],
        full_name=profile.get("full_name", ""),
        cpf_cnpj=profile.get("cpf_cnpj", ""),
        phone=profile.get("phone", ""),
        address=client.get("address"),
        documents=client.get("documents"),
        status=ClientStatusEnum(client["status"]),
        asaas_customer_id=profile.get("asaas_customer_id"),
        created_at=client["created_at"],
        updated_at=client["updated_at"]
    )


@router.put("/clients/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: str,
    request: ClientUpdate,
    admin: Annotated[dict, Depends(require_admin_role)],
    db: Annotated[Client, Depends(get_admin_db)]
):
    """Update client data"""
    existing = db.table("clients").select("*, profiles(*)").eq("id", client_id).single().execute()
    
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    client_updates = {"updated_at": datetime.utcnow().isoformat()}
    profile_updates = {"updated_at": datetime.utcnow().isoformat()}
    
    if request.address is not None:
        client_updates["address"] = request.address.model_dump()
    if request.status is not None:
        client_updates["status"] = request.status.value
    
    if request.full_name is not None:
        profile_updates["full_name"] = request.full_name
    if request.phone is not None:
        profile_updates["phone"] = request.phone
    
    if len(client_updates) > 1:
        db.table("clients").update(client_updates).eq("id", client_id).execute()
    
    if len(profile_updates) > 1:
        db.table("profiles").update(profile_updates).eq(
            "id", existing.data["profile_id"]
        ).execute()
    
    return await get_client(client_id, admin, db)


@router.delete("/clients/{client_id}")
async def deactivate_client(
    client_id: str,
    admin: Annotated[dict, Depends(require_admin_role)],
    db: Annotated[Client, Depends(get_admin_db)]
):
    """Deactivate client (soft delete)"""
    result = db.table("clients").update({
        "status": "inactive",
        "updated_at": datetime.utcnow().isoformat()
    }).eq("id", client_id).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    return {"message": "Client deactivated successfully"}


# ============== DEVELOPMENTS ==============

@router.get("/developments", response_model=List[DevelopmentResponse])
async def list_developments(
    admin: Annotated[dict, Depends(require_admin_role)],
    db: Annotated[Client, Depends(get_admin_db)]
):
    """List all developments"""
    result = db.table("developments").select("*").order("created_at", desc=True).execute()
    
    return [
        DevelopmentResponse(
            id=dev["id"],
            name=dev["name"],
            description=dev.get("description"),
            location=dev["location"],
            documents=dev.get("documents"),
            created_at=dev["created_at"],
            updated_at=dev["updated_at"]
        )
        for dev in (result.data or [])
    ]


@router.post("/developments", response_model=DevelopmentResponse, status_code=status.HTTP_201_CREATED)
async def create_development(
    request: DevelopmentCreate,
    admin: Annotated[dict, Depends(require_admin_role)],
    db: Annotated[Client, Depends(get_admin_db)]
):
    """Create new development/loteamento"""
    data = {
        "name": request.name,
        "description": request.description,
        "location": request.location
    }
    
    result = db.table("developments").insert(data).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create development"
        )
    
    dev = result.data[0]
    return DevelopmentResponse(
        id=dev["id"],
        name=dev["name"],
        description=dev.get("description"),
        location=dev["location"],
        documents=dev.get("documents"),
        created_at=dev["created_at"],
        updated_at=dev["updated_at"]
    )


@router.put("/developments/{development_id}", response_model=DevelopmentResponse)
async def update_development(
    development_id: str,
    request: DevelopmentUpdate,
    admin: Annotated[dict, Depends(require_admin_role)],
    db: Annotated[Client, Depends(get_admin_db)]
):
    """Update development"""
    updates = {"updated_at": datetime.utcnow().isoformat()}
    
    if request.name is not None:
        updates["name"] = request.name
    if request.description is not None:
        updates["description"] = request.description
    if request.location is not None:
        updates["location"] = request.location
    
    result = db.table("developments").update(updates).eq("id", development_id).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Development not found"
        )
    
    dev = result.data[0]
    return DevelopmentResponse(
        id=dev["id"],
        name=dev["name"],
        description=dev.get("description"),
        location=dev["location"],
        documents=dev.get("documents"),
        created_at=dev["created_at"],
        updated_at=dev["updated_at"]
    )


# ============== LOTS ==============

@router.get("/lots", response_model=List[LotResponse])
async def list_lots(
    admin: Annotated[dict, Depends(require_admin_role)],
    db: Annotated[Client, Depends(get_admin_db)],
    development_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100)
):
    """List lots with filters"""
    query = db.table("lots").select("*, developments(name)")
    
    if development_id:
        query = query.eq("development_id", development_id)
    if status:
        query = query.eq("status", status)
    
    offset = (page - 1) * page_size
    query = query.range(offset, offset + page_size - 1).order("lot_number")
    
    result = query.execute()
    
    return [
        LotResponse(
            id=lot["id"],
            development_id=lot["development_id"],
            development_name=lot.get("developments", {}).get("name") if lot.get("developments") else None,
            lot_number=lot["lot_number"],
            block=lot.get("block"),
            area_m2=Decimal(str(lot["area_m2"])),
            price=Decimal(str(lot["price"])),
            status=LotStatusEnum(lot["status"]),
            documents=lot.get("documents"),
            created_at=lot["created_at"],
            updated_at=lot["updated_at"]
        )
        for lot in (result.data or [])
    ]


@router.post("/lots", response_model=LotResponse, status_code=status.HTTP_201_CREATED)
async def create_lot(
    request: LotCreate,
    admin: Annotated[dict, Depends(require_admin_role)],
    db: Annotated[Client, Depends(get_admin_db)]
):
    """Create new lot"""
    dev_check = db.table("developments").select("id").eq("id", request.development_id).single().execute()
    if not dev_check.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Development not found"
        )
    
    data = {
        "development_id": request.development_id,
        "lot_number": request.lot_number,
        "block": request.block,
        "area_m2": float(request.area_m2),
        "price": float(request.price),
        "status": request.status.value
    }
    
    result = db.table("lots").insert(data).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create lot"
        )
    
    lot = result.data[0]
    dev = db.table("developments").select("name").eq("id", lot["development_id"]).single().execute()
    
    return LotResponse(
        id=lot["id"],
        development_id=lot["development_id"],
        development_name=dev.data.get("name") if dev.data else None,
        lot_number=lot["lot_number"],
        block=lot.get("block"),
        area_m2=Decimal(str(lot["area_m2"])),
        price=Decimal(str(lot["price"])),
        status=LotStatusEnum(lot["status"]),
        documents=lot.get("documents"),
        created_at=lot["created_at"],
        updated_at=lot["updated_at"]
    )


@router.put("/lots/{lot_id}", response_model=LotResponse)
async def update_lot(
    lot_id: str,
    request: LotUpdate,
    admin: Annotated[dict, Depends(require_admin_role)],
    db: Annotated[Client, Depends(get_admin_db)]
):
    """Update lot"""
    updates = {"updated_at": datetime.utcnow().isoformat()}
    
    if request.lot_number is not None:
        updates["lot_number"] = request.lot_number
    if request.block is not None:
        updates["block"] = request.block
    if request.area_m2 is not None:
        updates["area_m2"] = float(request.area_m2)
    if request.price is not None:
        updates["price"] = float(request.price)
    if request.status is not None:
        updates["status"] = request.status.value
    
    result = db.table("lots").update(updates).eq("id", lot_id).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lot not found"
        )
    
    lot = result.data[0]
    dev = db.table("developments").select("name").eq("id", lot["development_id"]).single().execute()
    
    return LotResponse(
        id=lot["id"],
        development_id=lot["development_id"],
        development_name=dev.data.get("name") if dev.data else None,
        lot_number=lot["lot_number"],
        block=lot.get("block"),
        area_m2=Decimal(str(lot["area_m2"])),
        price=Decimal(str(lot["price"])),
        status=LotStatusEnum(lot["status"]),
        documents=lot.get("documents"),
        created_at=lot["created_at"],
        updated_at=lot["updated_at"]
    )


# ============== CLIENT-LOTS ==============

@router.post("/client-lots", response_model=ClientLotResponse, status_code=status.HTTP_201_CREATED)
async def create_client_lot(
    request: ClientLotCreate,
    admin: Annotated[dict, Depends(require_admin_role)],
    db: Annotated[Client, Depends(get_admin_db)],
    asaas: Annotated[AsaasService, Depends(get_asaas_service)]
):
    """
    Link a lot to a client and generate payment installments
    """
    client = db.table("clients").select(
        "id, profile_id, profiles(full_name, asaas_customer_id)"
    ).eq("id", request.client_id).single().execute()
    
    if not client.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    lot = db.table("lots").select("*, developments(name)").eq("id", request.lot_id).single().execute()
    
    if not lot.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lot not found"
        )
    
    if lot.data["status"] != "available":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lot is not available for sale"
        )
    
    client_lot_data = {
        "client_id": request.client_id,
        "lot_id": request.lot_id,
        "purchase_date": request.purchase_date.isoformat(),
        "total_value": float(request.total_value),
        "payment_plan": request.payment_plan.model_dump(mode="json"),
        "status": "active"
    }
    
    client_lot = db.table("client_lots").insert(client_lot_data).execute()
    
    if not client_lot.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create client-lot relationship"
        )
    
    db.table("lots").update({"status": "sold", "updated_at": datetime.utcnow().isoformat()}).eq(
        "id", request.lot_id
    ).execute()
    
    client_lot_record = client_lot.data[0]
    asaas_customer_id = client.data.get("profiles", {}).get("asaas_customer_id")
    
    if asaas_customer_id:
        try:
            payment_plan = request.payment_plan
            development_name = lot.data.get("developments", {}).get("name", "")
            lot_number = lot.data.get("lot_number", "")
            
            from datetime import timedelta
            from dateutil.relativedelta import relativedelta
            
            for i in range(payment_plan.total_installments):
                due_date = payment_plan.first_due_date + relativedelta(months=i)
                
                payment = await asaas.create_payment(
                    customer_id=asaas_customer_id,
                    value=payment_plan.installment_value,
                    due_date=due_date,
                    description=f"{development_name} - Lote {lot_number} - Parcela {i + 1}/{payment_plan.total_installments}",
                    external_reference=client_lot_record["id"]
                )
                
                invoice_data = {
                    "client_lot_id": client_lot_record["id"],
                    "asaas_payment_id": payment.get("id"),
                    "due_date": due_date.isoformat(),
                    "amount": float(payment_plan.installment_value),
                    "status": "pending",
                    "installment_number": i + 1,
                    "barcode": payment.get("bankSlipUrl"),
                    "payment_url": payment.get("invoiceUrl")
                }
                
                db.table("invoices").insert(invoice_data).execute()
                
        except Exception as e:
            print(f"Failed to create Asaas payments: {e}")
    
    profile = client.data.get("profiles", {})
    development = lot.data.get("developments", {})
    
    return ClientLotResponse(
        id=client_lot_record["id"],
        client_id=request.client_id,
        client_name=profile.get("full_name"),
        lot_id=request.lot_id,
        lot_number=lot.data.get("lot_number"),
        development_name=development.get("name") if development else None,
        purchase_date=request.purchase_date,
        total_value=request.total_value,
        payment_plan=client_lot_record["payment_plan"],
        status=client_lot_record["status"],
        created_at=client_lot_record["created_at"]
    )


# ============== SERVICE TYPES ==============

@router.get("/service-types", response_model=List[ServiceTypeResponse])
async def list_service_types(
    admin: Annotated[dict, Depends(require_admin_role)],
    db: Annotated[Client, Depends(get_admin_db)]
):
    """List all service types"""
    result = db.table("service_types").select("*").order("name").execute()
    
    return [
        ServiceTypeResponse(
            id=st["id"],
            name=st["name"],
            description=st.get("description"),
            base_price=Decimal(str(st["base_price"])),
            is_active=st["is_active"],
            created_at=st["created_at"]
        )
        for st in (result.data or [])
    ]


@router.post("/service-types", response_model=ServiceTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_service_type(
    request: ServiceTypeCreate,
    admin: Annotated[dict, Depends(require_admin_role)],
    db: Annotated[Client, Depends(get_admin_db)]
):
    """Create new service type"""
    data = {
        "name": request.name,
        "description": request.description,
        "base_price": float(request.base_price),
        "is_active": request.is_active
    }
    
    result = db.table("service_types").insert(data).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create service type"
        )
    
    st = result.data[0]
    return ServiceTypeResponse(
        id=st["id"],
        name=st["name"],
        description=st.get("description"),
        base_price=Decimal(str(st["base_price"])),
        is_active=st["is_active"],
        created_at=st["created_at"]
    )


# ============== SERVICE ORDERS ==============

@router.get("/service-orders", response_model=List[ServiceOrderResponse])
async def list_service_orders(
    admin: Annotated[dict, Depends(require_admin_role)],
    db: Annotated[Client, Depends(get_admin_db)],
    status: Optional[str] = None,
    client_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
):
    """List service orders with filters"""
    query = db.table("service_orders").select(
        "*, clients(profile_id, profiles(full_name)), lots(lot_number), service_types(name)"
    )
    
    if status:
        query = query.eq("status", status)
    if client_id:
        query = query.eq("client_id", client_id)
    
    offset = (page - 1) * page_size
    query = query.range(offset, offset + page_size - 1).order("created_at", desc=True)
    
    result = query.execute()
    
    return [
        ServiceOrderResponse(
            id=so["id"],
            client_id=so["client_id"],
            client_name=so.get("clients", {}).get("profiles", {}).get("full_name") if so.get("clients") else None,
            lot_id=so.get("lot_id"),
            lot_number=so.get("lots", {}).get("lot_number") if so.get("lots") else None,
            service_type_id=so["service_type_id"],
            service_type_name=so.get("service_types", {}).get("name") if so.get("service_types") else None,
            requested_date=so["requested_date"],
            execution_date=so.get("execution_date"),
            status=ServiceOrderStatus(so["status"]),
            cost=Decimal(str(so.get("cost", 0) or 0)),
            revenue=Decimal(str(so.get("revenue", 0))) if so.get("revenue") else None,
            notes=so.get("notes"),
            created_at=so["created_at"],
            updated_at=so["updated_at"]
        )
        for so in (result.data or [])
    ]


@router.put("/service-orders/{order_id}", response_model=ServiceOrderResponse)
async def update_service_order(
    order_id: str,
    request: ServiceOrderUpdate,
    admin: Annotated[dict, Depends(require_admin_role)],
    db: Annotated[Client, Depends(get_admin_db)]
):
    """Update service order status and details"""
    updates = {"updated_at": datetime.utcnow().isoformat()}
    
    if request.execution_date is not None:
        updates["execution_date"] = request.execution_date.isoformat()
    if request.status is not None:
        updates["status"] = request.status.value
    if request.cost is not None:
        updates["cost"] = float(request.cost)
    if request.revenue is not None:
        updates["revenue"] = float(request.revenue)
    if request.notes is not None:
        updates["notes"] = request.notes
    
    result = db.table("service_orders").update(updates).eq("id", order_id).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service order not found"
        )
    
    so = result.data[0]
    
    client = db.table("clients").select("profiles(full_name)").eq("id", so["client_id"]).single().execute()
    lot = db.table("lots").select("lot_number").eq("id", so["lot_id"]).single().execute() if so.get("lot_id") else None
    service_type = db.table("service_types").select("name").eq("id", so["service_type_id"]).single().execute()
    
    return ServiceOrderResponse(
        id=so["id"],
        client_id=so["client_id"],
        client_name=client.data.get("profiles", {}).get("full_name") if client.data else None,
        lot_id=so.get("lot_id"),
        lot_number=lot.data.get("lot_number") if lot and lot.data else None,
        service_type_id=so["service_type_id"],
        service_type_name=service_type.data.get("name") if service_type.data else None,
        requested_date=so["requested_date"],
        execution_date=so.get("execution_date"),
        status=ServiceOrderStatus(so["status"]),
        cost=Decimal(str(so.get("cost", 0) or 0)),
        revenue=Decimal(str(so.get("revenue", 0))) if so.get("revenue") else None,
        notes=so.get("notes"),
        created_at=so["created_at"],
        updated_at=so["updated_at"]
    )


@router.get("/service-orders/analytics", response_model=ServiceAnalytics)
async def get_service_analytics(
    admin: Annotated[dict, Depends(require_admin_role)],
    db: Annotated[Client, Depends(get_admin_db)],
    date_from: Optional[date] = None,
    date_to: Optional[date] = None
):
    """Get service orders analytics (cost/revenue)"""
    query = db.table("service_orders").select("status, cost, revenue, service_type_id, service_types(name)")
    
    if date_from:
        query = query.gte("created_at", date_from.isoformat())
    if date_to:
        query = query.lte("created_at", date_to.isoformat())
    
    result = query.execute()
    orders = result.data or []
    
    total_cost = sum(Decimal(str(o.get("cost", 0) or 0)) for o in orders)
    total_revenue = sum(Decimal(str(o.get("revenue", 0) or 0)) for o in orders)
    
    orders_by_status = {}
    for o in orders:
        status = o["status"]
        orders_by_status[status] = orders_by_status.get(status, 0) + 1
    
    orders_by_type = {}
    for o in orders:
        type_name = o.get("service_types", {}).get("name", "Unknown") if o.get("service_types") else "Unknown"
        orders_by_type[type_name] = orders_by_type.get(type_name, 0) + 1
    
    return ServiceAnalytics(
        total_orders=len(orders),
        total_cost=total_cost,
        total_revenue=total_revenue,
        profit=total_revenue - total_cost,
        orders_by_status=orders_by_status,
        orders_by_type=orders_by_type
    )
