"""
CRM integrations API - test connections, check status, and manage CRM settings.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.api.dashboard import get_current_client
from src.models.client import Client
from src.services.plan_limits import get_crm_integration_limit

logger = logging.getLogger(__name__)
router = APIRouter(tags=["integrations"])

SUPPORTED_CRMS = {"housecallpro", "jobber", "gohighlevel", "servicetitan", "google_sheets"}


def _get_crm_instance(crm_type: str, api_key: str, tenant_id: str = ""):
    """Factory to create a CRM instance by type."""
    if crm_type == "housecallpro":
        from src.integrations.housecallpro import HousecallProCRM
        return HousecallProCRM(api_key=api_key)
    elif crm_type == "jobber":
        from src.integrations.jobber import JobberCRM
        return JobberCRM(api_key=api_key)
    elif crm_type == "gohighlevel":
        from src.integrations.gohighlevel import GoHighLevelCRM
        return GoHighLevelCRM(api_key=api_key, location_id=tenant_id)
    else:
        return None


@router.post("/api/v1/integrations/test")
async def test_integration(
    request: Request,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Test a CRM connection with provided credentials."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    crm_type = (payload.get("crm_type") or "").strip().lower()
    api_key = (payload.get("api_key") or "").strip()
    tenant_id = (payload.get("tenant_id") or "").strip()

    if crm_type not in SUPPORTED_CRMS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported CRM. Must be one of: {', '.join(sorted(SUPPORTED_CRMS))}",
        )

    if crm_type == "google_sheets":
        return {"connected": True, "message": "Google Sheets is always available"}

    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required")

    crm = _get_crm_instance(crm_type, api_key, tenant_id)
    if not crm:
        raise HTTPException(status_code=400, detail="CRM type not supported for testing")

    try:
        # Test by fetching technicians - lightweight call supported by all CRMs
        techs = await crm.get_technicians()
        return {
            "connected": True,
            "message": f"Successfully connected to {crm_type}",
            "technicians_found": len(techs),
        }
    except Exception as e:
        logger.warning("CRM test failed for %s: %s", crm_type, str(e))
        return {
            "connected": False,
            "message": f"Connection failed: {str(e)}",
            "technicians_found": 0,
        }


@router.post("/api/v1/integrations/connect")
async def connect_integration(
    request: Request,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Save CRM credentials and mark as connected."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    crm_type = (payload.get("crm_type") or "").strip().lower()
    api_key = (payload.get("api_key") or "").strip()
    tenant_id = (payload.get("tenant_id") or "").strip()

    if crm_type not in SUPPORTED_CRMS:
        raise HTTPException(status_code=400, detail="Unsupported CRM type")

    # Enforce CRM integration limit based on plan tier
    crm_limit = get_crm_integration_limit(client.tier)
    if crm_limit is not None and crm_limit <= 1:
        # Starter tier: only 1 CRM integration allowed
        has_existing_crm = (
            client.crm_type
            and client.crm_type != "google_sheets"
            and client.crm_type != crm_type
        )
        if has_existing_crm:
            raise HTTPException(
                status_code=403,
                detail="Starter plan allows 1 CRM integration. Upgrade to Professional for unlimited CRMs.",
            )

    client.crm_type = crm_type
    if api_key:
        client.crm_api_key_encrypted = api_key
    if tenant_id:
        client.crm_tenant_id = tenant_id

    await db.flush()
    logger.info("CRM connected: %s for %s", crm_type, client.business_name)

    return {"status": "connected", "crm_type": crm_type}


@router.get("/api/v1/integrations/status")
async def integration_status(
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Get current CRM integration status."""
    has_key = bool(client.crm_api_key_encrypted)

    return {
        "crm_type": client.crm_type,
        "connected": has_key or client.crm_type == "google_sheets",
        "tenant_id": client.crm_tenant_id,
        "has_api_key": has_key,
    }
