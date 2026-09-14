
"""Per-company branding (white-label) endpoints.

Only the *seed* values of a visual identity are stored: five brand colours, a
base radius, three asset paths and two wording overrides. The remaining design
tokens are derived from those seeds on the client, so adding a component never
means adding a colour to configure here.

Read access is open to any authenticated role — portal clients must be able to
see their company's brand — which is why this module lives at the ``v1`` root
instead of under ``admin/``.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.database import get_db
from app.core.deps import get_company_admin, get_current_user, get_super_admin
from app.models.company import Company
from app.models.company_branding import CompanyBranding
from app.models.user import Profile
from app.schemas.branding import BrandingResponse, BrandingUpdate
from app.services.storage_service import delete_file, get_public_url, upload_file
from app.utils.exceptions import ResourceNotFoundError, StorageError
from app.utils.logging import get_logger

router = APIRouter(prefix="/branding", tags=["Branding"])

logger = get_logger(__name__)

# Asset kinds and what each one accepts. SVG is deliberately excluded: it can
# carry script and would be served from our own domain.
ASSET_KINDS: dict[str, set[str]] = {
    "logo": {"image/png", "image/jpeg", "image/jpg", "image/webp"},
    "favicon": {"image/png", "image/x-icon", "image/vnd.microsoft.icon"},
    "app_icon": {"image/png"},
}
MAX_ASSET_SIZE = 2 * 1024 * 1024  # 2 MB — a logo has no business being bigger


def _path_field(kind: str) -> str:
    return f"{kind}_path"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_or_create_branding(db: AsyncSession, company_id) -> CompanyBranding:
    """Return the company's branding row, creating an empty one on demand.

    An empty row means "no override": every field is NULL and the frontend
    falls back to the platform defaults in ``globals.css``.
    """
    row = await db.execute(
        select(CompanyBranding).where(CompanyBranding.company_id == company_id)
    )
    branding = row.scalar_one_or_none()
    if branding is None:
        branding = CompanyBranding(company_id=company_id)
        db.add(branding)
        await db.flush()
    return branding


async def _get_company(db: AsyncSession, company_id) -> Company:
    row = await db.execute(select(Company).where(Company.id == company_id))
    company = row.scalar_one_or_none()
    if company is None:
        raise ResourceNotFoundError("Empresa não encontrada")
    return company


def _serialize(branding: CompanyBranding, company: Company) -> dict:
    """Build the API payload, swapping storage paths for stable public paths.

    Asset values are returned as API-relative paths (``/branding/public/...``)
    rather than signed URLs: signed URLs expire in an hour, which would break
    the favicon and the PWA icons that browsers cache for much longer. The
    frontend prefixes these with its API origin.
    """
    payload = {
        field: getattr(branding, field)
        for field in (
            "company_id",
            "primary_color",
            "accent_color",
            "sidebar_color",
            "background_color",
            "success_color",
            "radius",
            "display_name",
            "tagline",
        )
    }
    payload["company_slug"] = company.slug
    # None on a transient row (public endpoint, company never configured yet).
    payload["updated_at"] = getattr(branding, "updated_at", None)
    for kind in ASSET_KINDS:
        stored = getattr(branding, _path_field(kind), None)
        payload[f"{kind}_url"] = (
            f"/branding/public/{company.slug}/{kind}" if stored else None
        )
    return BrandingResponse(**payload).model_dump()


async def _apply_update(
    db: AsyncSession,
    branding: CompanyBranding,
    data: BrandingUpdate,
    *,
    actor: Profile,
    request: Request,
) -> None:
    """Apply a partial update and record it in the audit log."""
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(branding, field, value)
    await db.flush()

    await log_audit(
        db,
        user_id=actor.id,
        company_id=branding.company_id,
        table_name="company_branding",
        operation="UPDATE",
        resource_id=str(branding.id),
        detail=f"Branding updated: {list(updates.keys())}",
        ip_address=request.client.host if request.client else None,
    )


# ---------------------------------------------------------------------------
# Own company
# ---------------------------------------------------------------------------

@router.get("/me", response_model=BrandingResponse)
async def get_my_branding(
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_current_user),
):
    """Return the branding of the caller's company.

    Open to every authenticated role: the client portal is branded too.
    """
    branding = await _get_or_create_branding(db, user.company_id)
    company = await _get_company(db, user.company_id)
    return _serialize(branding, company)


@router.put("/me", response_model=BrandingResponse)
async def update_my_branding(
    data: BrandingUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Update the caller's company branding.

    Only provided fields change. Sending an explicit ``null`` clears that
    override and restores the platform default for it.
    """
    branding = await _get_or_create_branding(db, admin.company_id)
    await _apply_update(db, branding, data, actor=admin, request=request)
    company = await _get_company(db, admin.company_id)
    return _serialize(branding, company)


@router.post("/me/asset/{kind}", response_model=BrandingResponse)
async def upload_my_asset(
    kind: str,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Upload the company logo, favicon or app icon.

    Replaces the previous file of that kind, deleting it from storage.
    """
    allowed = ASSET_KINDS.get(kind)
    if allowed is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de asset inválido. Use: {', '.join(ASSET_KINDS)}",
        )
    if file.content_type not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Formato não permitido para '{kind}'. Aceitos: {', '.join(sorted(allowed))}",
        )

    contents = await file.read()
    if len(contents) > MAX_ASSET_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Arquivo excede o tamanho máximo de {MAX_ASSET_SIZE // (1024 * 1024)} MB",
        )

    branding = await _get_or_create_branding(db, admin.company_id)
    previous = getattr(branding, _path_field(kind))

    try:
        path = await upload_file(
            file_bytes=contents,
            original_filename=file.filename or f"{kind}.png",
            company_id=str(admin.company_id),
            subfolder="branding",
        )
    except StorageError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.detail) from exc

    setattr(branding, _path_field(kind), path)
    await db.flush()

    # Best-effort cleanup: a stale file must never fail the upload that replaced it.
    if previous:
        try:
            await delete_file(previous)
        except StorageError as exc:
            logger.warning("branding_old_asset_delete_failed", path=previous, error=str(exc))

    await log_audit(
        db,
        user_id=admin.id,
        company_id=admin.company_id,
        table_name="company_branding",
        operation="UPDATE",
        resource_id=str(branding.id),
        detail=f"Branding asset uploaded: {kind}",
        ip_address=request.client.host if request.client else None,
    )

    company = await _get_company(db, admin.company_id)
    return _serialize(branding, company)


@router.delete("/me/asset/{kind}", response_model=BrandingResponse)
async def delete_my_asset(
    kind: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Remove an asset, falling back to the platform default."""
    if kind not in ASSET_KINDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de asset inválido. Use: {', '.join(ASSET_KINDS)}",
        )

    branding = await _get_or_create_branding(db, admin.company_id)
    previous = getattr(branding, _path_field(kind))
    setattr(branding, _path_field(kind), None)
    await db.flush()

    if previous:
        try:
            await delete_file(previous)
        except StorageError as exc:
            logger.warning("branding_asset_delete_failed", path=previous, error=str(exc))

    await log_audit(
        db,
        user_id=admin.id,
        company_id=admin.company_id,
        table_name="company_branding",
        operation="UPDATE",
        resource_id=str(branding.id),
        detail=f"Branding asset removed: {kind}",
        ip_address=request.client.host if request.client else None,
    )

    company = await _get_company(db, admin.company_id)
    return _serialize(branding, company)


# ---------------------------------------------------------------------------
# Any company (super admin)
# ---------------------------------------------------------------------------

@router.get("/companies/{company_id}", response_model=BrandingResponse)
async def get_company_branding(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    _admin: Profile = Depends(get_super_admin),
):
    """Read any company's branding (super_admin only)."""
    company = await _get_company(db, company_id)
    branding = await _get_or_create_branding(db, company_id)
    return _serialize(branding, company)


@router.put("/companies/{company_id}", response_model=BrandingResponse)
async def update_company_branding(
    company_id: UUID,
    data: BrandingUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_super_admin),
):
    """Update any company's branding (super_admin only)."""
    company = await _get_company(db, company_id)
    branding = await _get_or_create_branding(db, company_id)
    await _apply_update(db, branding, data, actor=admin, request=request)
    return _serialize(branding, company)


# ---------------------------------------------------------------------------
# Public (no auth) — needed by the login screen, the favicon and the manifest
# ---------------------------------------------------------------------------

@router.get("/public/{slug}", response_model=BrandingResponse)
async def get_public_branding(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    """Return a company's branding by slug, without authentication.

    Brand colours, a logo and a company name are public information — they are
    on every page the company shows its own clients. Nothing tenant-sensitive
    is exposed here.
    """
    row = await db.execute(select(Company).where(Company.slug == slug))
    company = row.scalar_one_or_none()
    if company is None:
        raise ResourceNotFoundError("Empresa não encontrada")

    row = await db.execute(
        select(CompanyBranding).where(CompanyBranding.company_id == company.id)
    )
    branding = row.scalar_one_or_none()
    if branding is None:
        # Never write on a public endpoint — return the empty (default) shape.
        branding = CompanyBranding(company_id=company.id)
    return _serialize(branding, company)


@router.get("/public/{slug}/{kind}")
async def get_public_asset(
    slug: str,
    kind: str,
    db: AsyncSession = Depends(get_db),
):
    """Redirect to a freshly signed URL for a branding asset.

    This indirection is what makes the favicon and the PWA icons work: the URL
    the browser stores is this stable one, while the signed Supabase URL behind
    it is regenerated on every request.
    """
    if kind not in ASSET_KINDS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset não encontrado")

    row = await db.execute(select(Company).where(Company.slug == slug))
    company = row.scalar_one_or_none()
    if company is None:
        raise ResourceNotFoundError("Empresa não encontrada")

    row = await db.execute(
        select(CompanyBranding).where(CompanyBranding.company_id == company.id)
    )
    branding = row.scalar_one_or_none()
    stored: Optional[str] = getattr(branding, _path_field(kind), None) if branding else None
    if not stored:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset não configurado")

    try:
        signed = get_public_url(stored, expires_in=3600)
    except StorageError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=exc.detail) from exc

    return RedirectResponse(
        url=signed,
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        headers={"Cache-Control": "public, max-age=300"},
    )
