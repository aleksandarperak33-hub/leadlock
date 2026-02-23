"""
Dashboard API — thin router that includes sub-module routers.

Split into focused modules:
- dash_auth.py:    Auth, signup, password reset, email verification, JWT dependencies
- dash_phone.py:   Phone provisioning, business registration, 10DLC status
- dash_leads.py:   Leads CRUD, export, conversations, lead actions
- dash_reports.py: Metrics, activity, settings, compliance, bookings, reports
"""
from fastapi import APIRouter

from src.api.dash_auth import router as auth_router
from src.api.dash_phone import router as phone_router
from src.api.dash_leads import router as leads_router
from src.api.dash_reports import router as reports_router

router = APIRouter(tags=["dashboard"])

router.include_router(auth_router)
router.include_router(phone_router)
router.include_router(leads_router)
router.include_router(reports_router)


# === Backward-compatible re-exports ===
# All symbols are re-exported so existing imports like
#   from src.api.dashboard import get_current_client
# continue to work without changes to tests or other modules.

from src.api.dash_auth import (  # noqa: F401, E402
    _check_auth_rate_limit,
    bearer_scheme,
    forgot_password,
    get_current_admin,
    get_current_client,
    login,
    resend_verification,
    reset_password,
    signup,
    verify_email,
)
from src.api.dash_phone import (  # noqa: F401, E402
    _check_is_tollfree,
    _get_registration_status_info,
    _mask_ein,
    get_registration_status,
    provision_number,
    search_available_numbers,
    submit_business_registration,
)
from src.api.dash_leads import (  # noqa: F401, E402
    archive_lead,
    export_leads_csv,
    get_conversations,
    get_lead_detail,
    get_leads,
    update_lead_notes,
    update_lead_status,
    update_lead_tags,
)
from src.api.dash_reports import (  # noqa: F401, E402
    complete_onboarding,
    get_activity,
    get_bookings,
    get_compliance_summary,
    get_custom_report,
    get_metrics,
    get_settings,
    get_weekly_report,
    update_settings,
)
