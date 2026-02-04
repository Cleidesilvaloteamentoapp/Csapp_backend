from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from typing import Annotated, Optional
from datetime import datetime
from supabase import Client

from app.api.deps import get_admin_db
from app.schemas.invoice import AsaasWebhookPayload
from app.services.notification import get_email_service, EmailService

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/asaas")
async def handle_asaas_webhook(
    request: Request,
    db: Annotated[Client, Depends(get_admin_db)],
    asaas_access_token: Optional[str] = Header(None, alias="asaas-access-token")
):
    """
    Handle Asaas payment webhooks
    Updates invoice status based on payment events
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )
    
    event = payload.get("event")
    payment = payload.get("payment", {})
    
    if not event or not payment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing event or payment data"
        )
    
    asaas_payment_id = payment.get("id")
    
    if not asaas_payment_id:
        return {"status": "ignored", "reason": "No payment ID"}
    
    invoice = db.table("invoices").select("*").eq(
        "asaas_payment_id", asaas_payment_id
    ).single().execute()
    
    if not invoice.data:
        return {"status": "ignored", "reason": "Invoice not found"}
    
    status_mapping = {
        "PAYMENT_RECEIVED": "paid",
        "PAYMENT_CONFIRMED": "paid",
        "PAYMENT_OVERDUE": "overdue",
        "PAYMENT_DELETED": "cancelled",
        "PAYMENT_RESTORED": "pending",
        "PAYMENT_REFUNDED": "cancelled",
        "PAYMENT_RECEIVED_IN_CASH_UNDONE": "pending",
        "PAYMENT_CHARGEBACK_REQUESTED": "overdue",
        "PAYMENT_CHARGEBACK_DISPUTE": "overdue",
        "PAYMENT_AWAITING_CHARGEBACK_REVERSAL": "overdue",
        "PAYMENT_DUNNING_RECEIVED": "paid",
        "PAYMENT_DUNNING_REQUESTED": "overdue",
    }
    
    new_status = status_mapping.get(event)
    
    if not new_status:
        return {"status": "ignored", "reason": f"Unhandled event: {event}"}
    
    update_data = {
        "status": new_status,
        "updated_at": datetime.utcnow().isoformat()
    }
    
    if new_status == "paid":
        update_data["paid_at"] = payment.get("paymentDate") or datetime.utcnow().isoformat()
    
    if payment.get("bankSlipUrl"):
        update_data["barcode"] = payment.get("bankSlipUrl")
    if payment.get("invoiceUrl"):
        update_data["payment_url"] = payment.get("invoiceUrl")
    
    db.table("invoices").update(update_data).eq("id", invoice.data["id"]).execute()
    
    if new_status == "overdue":
        client_lot = db.table("client_lots").select(
            "client_id, clients(profile_id, profiles(full_name), email)"
        ).eq("id", invoice.data["client_lot_id"]).single().execute()
        
        if client_lot.data:
            client = client_lot.data.get("clients", {})
            profile = client.get("profiles", {}) if client else {}
            
            notification_data = {
                "user_id": client.get("profile_id"),
                "type": "payment_overdue",
                "title": "Pagamento em Atraso",
                "message": f"Seu boleto no valor de R$ {invoice.data['amount']:.2f} está em atraso.",
                "is_read": False
            }
            
            db.table("notifications").insert(notification_data).execute()
    
    return {
        "status": "processed",
        "event": event,
        "invoice_id": invoice.data["id"],
        "new_status": new_status
    }


@router.post("/asaas/billing")
async def handle_asaas_billing_webhook(
    request: Request,
    db: Annotated[Client, Depends(get_admin_db)]
):
    """Handle Asaas billing/subscription webhooks"""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )
    
    return {"status": "received", "event": payload.get("event")}
