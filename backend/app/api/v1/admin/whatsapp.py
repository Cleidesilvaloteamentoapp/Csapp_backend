
"""Admin endpoints for WhatsApp provider management.

Provides:
- Credential CRUD (UAZAPI and/or Meta Cloud API per company)
- Connection status check
- Test message sending
- Template management (Meta Cloud API only)
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.database import get_db
from app.core.deps import get_company_admin, require_permission
from app.models.enums import WhatsAppProviderType
from app.models.user import Profile
from app.schemas.whatsapp import (
    ConnectionStatusResponse,
    WhatsAppCredentialCreate,
    WhatsAppCredentialResponse,
    WhatsAppCredentialUpdate,
    WhatsAppTemplateCreate,
    WhatsAppTemplateList,
    WhatsAppTemplateResponse,
    WhatsAppTestMessage,
)
from app.services import whatsapp_credential_service as cred_svc
from app.services.whatsapp_credential_service import get_provider_by_credential
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])


# ---------------------------------------------------------------------------
# Credential CRUD
# ---------------------------------------------------------------------------

@router.get("/credentials/", response_model=list[WhatsAppCredentialResponse])
async def list_credentials(
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(require_permission("manage_whatsapp")),
):
    """List all WhatsApp credentials for the current company."""
    return await cred_svc.list_credentials(db, current_user.company_id)


@router.post(
    "/credentials/",
    response_model=WhatsAppCredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_credential(
    payload: WhatsAppCredentialCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(require_permission("manage_whatsapp")),
):
    """Create a new WhatsApp credential (UAZAPI or META)."""
    try:
        provider_type = WhatsAppProviderType(payload.provider)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid provider: {payload.provider}. Must be UAZAPI or META.",
        )

    try:
        cred = await cred_svc.create_credential(
            db,
            current_user.company_id,
            provider=provider_type,
            uazapi_base_url=payload.uazapi_base_url,
            uazapi_instance_token=payload.uazapi_instance_token,
            meta_waba_id=payload.meta_waba_id,
            meta_phone_number_id=payload.meta_phone_number_id,
            meta_access_token=payload.meta_access_token,
            is_default=payload.is_default,
        )
        await db.commit()

        await log_audit(
            db,
            user_id=current_user.id,
            company_id=current_user.company_id,
            table_name="whatsapp_credentials",
            operation="CREATE",
            resource_id=str(cred.id),
            detail=f"provider={payload.provider}",
        )

        return cred
    except Exception as exc:
        await db.rollback()
        logger.error("create_whatsapp_credential_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.patch("/credentials/{credential_id}", response_model=WhatsAppCredentialResponse)
async def update_credential(
    credential_id: UUID,
    payload: WhatsAppCredentialUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(require_permission("manage_whatsapp")),
):
    """Update an existing WhatsApp credential."""
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    try:
        cred = await cred_svc.update_credential(
            db, credential_id, current_user.company_id, **updates
        )
        await db.commit()

        await log_audit(
            db,
            user_id=current_user.id,
            company_id=current_user.company_id,
            table_name="whatsapp_credentials",
            operation="UPDATE",
            resource_id=str(credential_id),
            detail=f"updated_fields={list(updates.keys())}",
        )

        return cred
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.delete("/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential(
    credential_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(require_permission("manage_whatsapp")),
):
    """Deactivate (soft delete) a WhatsApp credential."""
    try:
        await cred_svc.delete_credential(db, credential_id, current_user.company_id)
        await db.commit()

        await log_audit(
            db,
            user_id=current_user.id,
            company_id=current_user.company_id,
            table_name="whatsapp_credentials",
            operation="DELETE",
            resource_id=str(credential_id),
        )
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/credentials/{credential_id}/set-default", response_model=WhatsAppCredentialResponse)
async def set_default_credential(
    credential_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(require_permission("manage_whatsapp")),
):
    """Set a credential as the default WhatsApp provider for the company."""
    try:
        cred = await cred_svc.set_default(db, credential_id, current_user.company_id)
        await db.commit()
        return cred
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ---------------------------------------------------------------------------
# Connection status
# ---------------------------------------------------------------------------

@router.get("/credentials/{credential_id}/status", response_model=ConnectionStatusResponse)
async def check_connection_status(
    credential_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(require_permission("manage_whatsapp")),
):
    """Check the connection status of a WhatsApp provider."""
    try:
        provider = await get_provider_by_credential(
            db, credential_id, current_user.company_id
        )
        conn_status = await provider.check_connection()

        # Cache the result
        await cred_svc.update_connection_status(
            db, credential_id, current_user.company_id, conn_status.status
        )
        await db.commit()

        return ConnectionStatusResponse(
            connected=conn_status.connected,
            status=conn_status.status,
            profile_name=conn_status.profile_name,
            phone_number=conn_status.phone_number,
            error=conn_status.error,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ---------------------------------------------------------------------------
# Test message
# ---------------------------------------------------------------------------

@router.post("/test-message", status_code=status.HTTP_200_OK)
async def send_test_message(
    payload: WhatsAppTestMessage,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(require_permission("manage_whatsapp")),
):
    """Send a test WhatsApp message via the company's configured provider."""
    try:
        if payload.credential_id:
            provider = await get_provider_by_credential(
                db, payload.credential_id, current_user.company_id
            )
        else:
            from app.services.whatsapp_credential_service import get_provider
            provider = await get_provider(db, current_user.company_id)

        result = await provider.send_text(to=payload.to, body=payload.body)

        if result.success:
            return {"status": "sent", "message_id": result.message_id, "provider": result.provider}

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Message sending failed: {result.error}",
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ---------------------------------------------------------------------------
# Template management (Meta Cloud API only)
# ---------------------------------------------------------------------------

async def _get_meta_provider(db: AsyncSession, company_id: UUID, credential_id: UUID | None = None):
    """Helper: resolve Meta provider for template operations."""
    if credential_id:
        provider = await get_provider_by_credential(db, credential_id, company_id)
    else:
        from app.services.whatsapp_credential_service import get_provider
        provider = await get_provider(db, company_id, WhatsAppProviderType.META)

    if provider.provider_name != "meta":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Template management is only available for Meta Cloud API credentials.",
        )
    return provider


@router.get("/templates/", response_model=WhatsAppTemplateList)
async def list_templates(
    credential_id: UUID | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(require_permission("manage_whatsapp")),
):
    """List WhatsApp message templates from Meta Cloud API."""
    try:
        provider = await _get_meta_provider(db, current_user.company_id, credential_id)
        templates = await provider.list_templates(limit=limit)
        return WhatsAppTemplateList(
            templates=[
                WhatsAppTemplateResponse(
                    id=t.id,
                    name=t.name,
                    status=t.status,
                    category=t.category,
                    language=t.language,
                    components=t.components,
                )
                for t in templates
            ],
            count=len(templates),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/templates/",
    response_model=WhatsAppTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_template(
    payload: WhatsAppTemplateCreate,
    credential_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(require_permission("manage_whatsapp")),
):
    """Create a new WhatsApp message template in Meta Cloud API."""
    try:
        provider = await _get_meta_provider(db, current_user.company_id, credential_id)

        template_data = {
            "name": payload.name,
            "language": payload.language,
            "category": payload.category,
            "components": payload.components,
        }
        result = await provider.create_template(template_data)

        return WhatsAppTemplateResponse(
            id=result.id,
            name=result.name,
            status=result.status,
            category=result.category,
            language=result.language,
            components=result.components,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/templates/{template_name}", response_model=WhatsAppTemplateResponse)
async def get_template(
    template_name: str,
    credential_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(require_permission("manage_whatsapp")),
):
    """Get details of a specific WhatsApp message template."""
    try:
        provider = await _get_meta_provider(db, current_user.company_id, credential_id)
        result = await provider.get_template(template_name)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Template '{template_name}' not found",
            )

        return WhatsAppTemplateResponse(
            id=result.id,
            name=result.name,
            status=result.status,
            category=result.category,
            language=result.language,
            components=result.components,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.delete("/templates/{template_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_name: str,
    credential_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(require_permission("manage_whatsapp")),
):
    """Delete a WhatsApp message template from Meta Cloud API."""
    try:
        provider = await _get_meta_provider(db, current_user.company_id, credential_id)
        success = await provider.delete_template(template_name)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to delete template '{template_name}'",
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
