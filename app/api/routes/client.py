from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from typing import Annotated, Optional, List
from datetime import date, datetime
from decimal import Decimal
from supabase import Client

from app.api.deps import (
    get_db,
    require_client_role,
    get_current_user_profile,
    get_client_id_from_profile
)
from app.schemas.lot import LotResponse, ClientLotResponse
from app.schemas.invoice import InvoiceResponse, InvoiceListResponse, InvoiceStatus
from app.schemas.service import (
    ServiceTypeResponse,
    ServiceOrderCreate,
    ServiceOrderResponse,
    ServiceOrderStatus
)
from app.schemas.dashboard import ClientDashboardResponse
from app.services.storage import StorageService
from app.models.enums import LotStatus as LotStatusEnum, InvoiceStatus as InvoiceStatusEnum

router = APIRouter(prefix="/client", tags=["Client"])


# ============== DASHBOARD ==============

@router.get("/dashboard", response_model=ClientDashboardResponse)
async def get_client_dashboard(
    profile: Annotated[dict, Depends(require_client_role)],
    db: Annotated[Client, Depends(get_db)]
):
    """Get client dashboard summary"""
    client = db.table("clients").select("id").eq("profile_id", profile["id"]).single().execute()
    
    if not client.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client profile not found"
        )
    
    client_id = client.data["id"]
    
    client_lots = db.table("client_lots").select(
        "*, lots(lot_number, area_m2, developments(name))"
    ).eq("client_id", client_id).eq("status", "active").execute()
    
    lots_data = []
    for cl in (client_lots.data or []):
        lot = cl.get("lots", {}) or {}
        development = lot.get("developments", {}) or {}
        lots_data.append({
            "client_lot_id": cl["id"],
            "lot_number": lot.get("lot_number"),
            "area_m2": lot.get("area_m2"),
            "development_name": development.get("name"),
            "total_value": cl["total_value"],
            "status": cl["status"]
        })
    
    client_lot_ids = [cl["id"] for cl in (client_lots.data or [])]
    
    pending_invoices = []
    total_pending = Decimal("0")
    next_due = None
    
    if client_lot_ids:
        invoices = db.table("invoices").select("*").in_(
            "client_lot_id", client_lot_ids
        ).in_("status", ["pending", "overdue"]).order("due_date").execute()
        
        pending_invoices = invoices.data or []
        total_pending = sum(Decimal(str(inv["amount"])) for inv in pending_invoices)
        
        if pending_invoices:
            next_due = pending_invoices[0]["due_date"]
    
    open_orders = db.table("service_orders").select("id", count="exact").eq(
        "client_id", client_id
    ).in_("status", ["requested", "approved", "in_progress"]).execute()
    
    notifications = db.table("notifications").select("*").eq(
        "user_id", profile["id"]
    ).eq("is_read", False).order("created_at", desc=True).limit(5).execute()
    
    return ClientDashboardResponse(
        client_name=profile.get("full_name", ""),
        total_lots=len(lots_data),
        lots=lots_data,
        pending_invoices=len(pending_invoices),
        total_pending_amount=total_pending,
        next_due_date=next_due,
        open_service_orders=open_orders.count or 0,
        recent_notifications=[
            {
                "id": n["id"],
                "type": n["type"],
                "title": n["title"],
                "message": n["message"],
                "created_at": n["created_at"]
            }
            for n in (notifications.data or [])
        ]
    )


# ============== INVOICES ==============

@router.get("/invoices", response_model=InvoiceListResponse)
async def list_client_invoices(
    profile: Annotated[dict, Depends(require_client_role)],
    db: Annotated[Client, Depends(get_db)],
    client_lot_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
):
    """List invoices for the authenticated client"""
    client = db.table("clients").select("id").eq("profile_id", profile["id"]).single().execute()
    
    if not client.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client profile not found"
        )
    
    client_id = client.data["id"]
    
    client_lots = db.table("client_lots").select("id").eq("client_id", client_id).execute()
    client_lot_ids = [cl["id"] for cl in (client_lots.data or [])]
    
    if not client_lot_ids:
        return InvoiceListResponse(
            items=[],
            total=0,
            total_pending=Decimal("0"),
            total_paid=Decimal("0"),
            total_overdue=Decimal("0")
        )
    
    query = db.table("invoices").select(
        "*, client_lots(lot_id, lots(lot_number, developments(name)))",
        count="exact"
    ).in_("client_lot_id", client_lot_ids)
    
    if client_lot_id:
        if client_lot_id not in client_lot_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this lot"
            )
        query = query.eq("client_lot_id", client_lot_id)
    
    if status:
        query = query.eq("status", status)
    
    offset = (page - 1) * page_size
    query = query.range(offset, offset + page_size - 1).order("due_date", desc=True)
    
    result = query.execute()
    
    all_invoices = db.table("invoices").select("amount, status").in_(
        "client_lot_id", client_lot_ids
    ).execute()
    
    total_pending = Decimal("0")
    total_paid = Decimal("0")
    total_overdue = Decimal("0")
    
    for inv in (all_invoices.data or []):
        amount = Decimal(str(inv["amount"]))
        if inv["status"] == "pending":
            total_pending += amount
        elif inv["status"] == "paid":
            total_paid += amount
        elif inv["status"] == "overdue":
            total_overdue += amount
    
    items = []
    for inv in (result.data or []):
        client_lot = inv.get("client_lots", {}) or {}
        lot = client_lot.get("lots", {}) or {}
        development = lot.get("developments", {}) or {}
        
        items.append(InvoiceResponse(
            id=inv["id"],
            client_lot_id=inv["client_lot_id"],
            asaas_payment_id=inv.get("asaas_payment_id"),
            due_date=inv["due_date"],
            amount=Decimal(str(inv["amount"])),
            status=InvoiceStatusEnum(inv["status"]),
            installment_number=inv["installment_number"],
            barcode=inv.get("barcode"),
            payment_url=inv.get("payment_url"),
            paid_at=inv.get("paid_at"),
            created_at=inv["created_at"],
            lot_number=lot.get("lot_number"),
            development_name=development.get("name")
        ))
    
    return InvoiceListResponse(
        items=items,
        total=result.count or 0,
        total_pending=total_pending,
        total_paid=total_paid,
        total_overdue=total_overdue
    )


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice_details(
    invoice_id: str,
    profile: Annotated[dict, Depends(require_client_role)],
    db: Annotated[Client, Depends(get_db)]
):
    """Get invoice details"""
    client = db.table("clients").select("id").eq("profile_id", profile["id"]).single().execute()
    
    if not client.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client profile not found"
        )
    
    client_id = client.data["id"]
    
    invoice = db.table("invoices").select(
        "*, client_lots(client_id, lot_id, lots(lot_number, developments(name)))"
    ).eq("id", invoice_id).single().execute()
    
    if not invoice.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )
    
    client_lot = invoice.data.get("client_lots", {}) or {}
    if client_lot.get("client_id") != client_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    lot = client_lot.get("lots", {}) or {}
    development = lot.get("developments", {}) or {}
    
    return InvoiceResponse(
        id=invoice.data["id"],
        client_lot_id=invoice.data["client_lot_id"],
        asaas_payment_id=invoice.data.get("asaas_payment_id"),
        due_date=invoice.data["due_date"],
        amount=Decimal(str(invoice.data["amount"])),
        status=InvoiceStatusEnum(invoice.data["status"]),
        installment_number=invoice.data["installment_number"],
        barcode=invoice.data.get("barcode"),
        payment_url=invoice.data.get("payment_url"),
        paid_at=invoice.data.get("paid_at"),
        created_at=invoice.data["created_at"],
        lot_number=lot.get("lot_number"),
        development_name=development.get("name")
    )


# ============== LOTS ==============

@router.get("/lots", response_model=List[ClientLotResponse])
async def list_client_lots(
    profile: Annotated[dict, Depends(require_client_role)],
    db: Annotated[Client, Depends(get_db)]
):
    """List lots owned by the authenticated client"""
    client = db.table("clients").select("id").eq("profile_id", profile["id"]).single().execute()
    
    if not client.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client profile not found"
        )
    
    client_id = client.data["id"]
    
    result = db.table("client_lots").select(
        "*, lots(lot_number, developments(name))"
    ).eq("client_id", client_id).order("created_at", desc=True).execute()
    
    return [
        ClientLotResponse(
            id=cl["id"],
            client_id=cl["client_id"],
            client_name=profile.get("full_name"),
            lot_id=cl["lot_id"],
            lot_number=cl.get("lots", {}).get("lot_number") if cl.get("lots") else None,
            development_name=cl.get("lots", {}).get("developments", {}).get("name") if cl.get("lots") else None,
            purchase_date=cl["purchase_date"],
            total_value=Decimal(str(cl["total_value"])),
            payment_plan=cl["payment_plan"],
            status=cl["status"],
            created_at=cl["created_at"]
        )
        for cl in (result.data or [])
    ]


@router.get("/lots/{lot_id}/documents")
async def get_lot_documents(
    lot_id: str,
    profile: Annotated[dict, Depends(require_client_role)],
    db: Annotated[Client, Depends(get_db)]
):
    """Get documents for a specific lot"""
    client = db.table("clients").select("id").eq("profile_id", profile["id"]).single().execute()
    
    if not client.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client profile not found"
        )
    
    client_id = client.data["id"]
    
    client_lot = db.table("client_lots").select("id").eq(
        "client_id", client_id
    ).eq("lot_id", lot_id).single().execute()
    
    if not client_lot.data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this lot"
        )
    
    lot = db.table("lots").select("documents").eq("id", lot_id).single().execute()
    
    if not lot.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lot not found"
        )
    
    storage = StorageService(db)
    documents = lot.data.get("documents") or []
    
    return {
        "lot_id": lot_id,
        "documents": [
            {
                "path": doc,
                "url": storage.get_signed_url("lots", doc)
            }
            for doc in documents
        ]
    }


# ============== SERVICES ==============

@router.get("/service-types", response_model=List[ServiceTypeResponse])
async def list_available_services(
    profile: Annotated[dict, Depends(require_client_role)],
    db: Annotated[Client, Depends(get_db)]
):
    """List available service types"""
    result = db.table("service_types").select("*").eq("is_active", True).order("name").execute()
    
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


@router.post("/service-orders", response_model=ServiceOrderResponse, status_code=status.HTTP_201_CREATED)
async def create_service_order(
    request: ServiceOrderCreate,
    profile: Annotated[dict, Depends(require_client_role)],
    db: Annotated[Client, Depends(get_db)]
):
    """Request a new service"""
    client = db.table("clients").select("id").eq("profile_id", profile["id"]).single().execute()
    
    if not client.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client profile not found"
        )
    
    client_id = client.data["id"]
    
    if request.lot_id:
        client_lot = db.table("client_lots").select("id").eq(
            "client_id", client_id
        ).eq("lot_id", request.lot_id).single().execute()
        
        if not client_lot.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this lot"
            )
    
    service_type = db.table("service_types").select("*").eq(
        "id", request.service_type_id
    ).eq("is_active", True).single().execute()
    
    if not service_type.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service type not found or inactive"
        )
    
    order_data = {
        "client_id": client_id,
        "lot_id": request.lot_id,
        "service_type_id": request.service_type_id,
        "requested_date": request.requested_date.isoformat(),
        "status": "requested",
        "cost": float(service_type.data["base_price"]),
        "notes": request.notes
    }
    
    result = db.table("service_orders").insert(order_data).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create service order"
        )
    
    so = result.data[0]
    
    lot_number = None
    if request.lot_id:
        lot = db.table("lots").select("lot_number").eq("id", request.lot_id).single().execute()
        lot_number = lot.data.get("lot_number") if lot.data else None
    
    return ServiceOrderResponse(
        id=so["id"],
        client_id=so["client_id"],
        client_name=profile.get("full_name"),
        lot_id=so.get("lot_id"),
        lot_number=lot_number,
        service_type_id=so["service_type_id"],
        service_type_name=service_type.data["name"],
        requested_date=so["requested_date"],
        execution_date=so.get("execution_date"),
        status=ServiceOrderStatus(so["status"]),
        cost=Decimal(str(so.get("cost", 0) or 0)),
        revenue=None,
        notes=so.get("notes"),
        created_at=so["created_at"],
        updated_at=so["updated_at"]
    )


@router.get("/service-orders", response_model=List[ServiceOrderResponse])
async def list_client_service_orders(
    profile: Annotated[dict, Depends(require_client_role)],
    db: Annotated[Client, Depends(get_db)],
    status: Optional[str] = None
):
    """List service orders for the authenticated client"""
    client = db.table("clients").select("id").eq("profile_id", profile["id"]).single().execute()
    
    if not client.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client profile not found"
        )
    
    client_id = client.data["id"]
    
    query = db.table("service_orders").select(
        "*, lots(lot_number), service_types(name)"
    ).eq("client_id", client_id)
    
    if status:
        query = query.eq("status", status)
    
    result = query.order("created_at", desc=True).execute()
    
    return [
        ServiceOrderResponse(
            id=so["id"],
            client_id=so["client_id"],
            client_name=profile.get("full_name"),
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


@router.get("/service-orders/{order_id}", response_model=ServiceOrderResponse)
async def get_service_order_details(
    order_id: str,
    profile: Annotated[dict, Depends(require_client_role)],
    db: Annotated[Client, Depends(get_db)]
):
    """Get service order details"""
    client = db.table("clients").select("id").eq("profile_id", profile["id"]).single().execute()
    
    if not client.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client profile not found"
        )
    
    client_id = client.data["id"]
    
    result = db.table("service_orders").select(
        "*, lots(lot_number), service_types(name)"
    ).eq("id", order_id).single().execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service order not found"
        )
    
    if result.data["client_id"] != client_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    so = result.data
    
    return ServiceOrderResponse(
        id=so["id"],
        client_id=so["client_id"],
        client_name=profile.get("full_name"),
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


# ============== DOCUMENTS ==============

@router.get("/documents")
async def list_client_documents(
    profile: Annotated[dict, Depends(require_client_role)],
    db: Annotated[Client, Depends(get_db)]
):
    """List all documents for the authenticated client"""
    client = db.table("clients").select("id, documents").eq(
        "profile_id", profile["id"]
    ).single().execute()
    
    if not client.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client profile not found"
        )
    
    storage = StorageService(db)
    client_docs = client.data.get("documents") or []
    
    client_id = client.data["id"]
    client_lots = db.table("client_lots").select("lot_id, lots(documents)").eq(
        "client_id", client_id
    ).execute()
    
    lot_docs = []
    for cl in (client_lots.data or []):
        lot = cl.get("lots", {}) or {}
        for doc in (lot.get("documents") or []):
            lot_docs.append({
                "path": doc,
                "type": "lot",
                "lot_id": cl["lot_id"]
            })
    
    return {
        "client_documents": [
            {
                "path": doc,
                "url": storage.get_signed_url("clients", doc),
                "type": "client"
            }
            for doc in client_docs
        ],
        "lot_documents": [
            {
                **doc,
                "url": storage.get_signed_url("lots", doc["path"])
            }
            for doc in lot_docs
        ]
    }


@router.post("/documents")
async def upload_client_document(
    file: UploadFile = File(...),
    profile: Annotated[dict, Depends(require_client_role)] = None,
    db: Annotated[Client, Depends(get_db)] = None
):
    """Upload a document for the authenticated client"""
    client = db.table("clients").select("id, documents").eq(
        "profile_id", profile["id"]
    ).single().execute()
    
    if not client.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client profile not found"
        )
    
    client_id = client.data["id"]
    storage = StorageService(db)
    
    file_path = await storage.upload_file(file, "clients", client_id)
    
    current_docs = client.data.get("documents") or []
    current_docs.append(file_path)
    
    db.table("clients").update({
        "documents": current_docs,
        "updated_at": datetime.utcnow().isoformat()
    }).eq("id", client_id).execute()
    
    return {
        "message": "Document uploaded successfully",
        "path": file_path,
        "url": storage.get_signed_url("clients", file_path)
    }


# ============== REFERRALS ==============

@router.post("/referrals", status_code=status.HTTP_201_CREATED)
async def create_referral(
    referred_name: str,
    referred_phone: str,
    referred_email: Optional[str] = None,
    profile: Annotated[dict, Depends(require_client_role)] = None,
    db: Annotated[Client, Depends(get_db)] = None
):
    """Create a new referral"""
    client = db.table("clients").select("id").eq("profile_id", profile["id"]).single().execute()
    
    if not client.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client profile not found"
        )
    
    referral_data = {
        "referrer_client_id": client.data["id"],
        "referred_name": referred_name,
        "referred_phone": referred_phone,
        "referred_email": referred_email,
        "status": "pending"
    }
    
    result = db.table("referrals").insert(referral_data).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create referral"
        )
    
    return {
        "message": "Referral created successfully",
        "referral": result.data[0]
    }


@router.get("/referrals")
async def list_client_referrals(
    profile: Annotated[dict, Depends(require_client_role)],
    db: Annotated[Client, Depends(get_db)]
):
    """List referrals made by the authenticated client"""
    client = db.table("clients").select("id").eq("profile_id", profile["id"]).single().execute()
    
    if not client.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client profile not found"
        )
    
    result = db.table("referrals").select("*").eq(
        "referrer_client_id", client.data["id"]
    ).order("created_at", desc=True).execute()
    
    return {
        "referrals": result.data or [],
        "total": len(result.data or [])
    }
