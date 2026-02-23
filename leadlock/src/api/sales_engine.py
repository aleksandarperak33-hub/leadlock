"""
Sales Engine API — thin router that includes sub-module routers.

Split into focused modules:
- sales_webhooks.py:  Inbound email, email events, unsubscribe (public)
- sales_prospects.py: Prospect CRUD, bulk ops, email threads
- sales_config.py:    Config, metrics, worker controls, templates, insights
- sales_scraper.py:   Scrape job management
- sales_dashboard.py: Campaigns, command center
"""
from fastapi import APIRouter

from src.api.sales_webhooks import router as webhooks_router
from src.api.sales_prospects import router as prospects_router
from src.api.sales_config import router as config_router
from src.api.sales_scraper import router as scraper_router
from src.api.sales_dashboard import router as dashboard_router

router = APIRouter(prefix="/api/v1/sales", tags=["sales-engine"])

router.include_router(webhooks_router)
router.include_router(prospects_router)
router.include_router(config_router)
router.include_router(scraper_router)
router.include_router(dashboard_router)


# === Backward-compatible re-exports ===
# All symbols are re-exported so existing imports like
#   from src.api.sales_engine import _serialize_prospect
# continue to work without changes to tests or other modules.

from src.api.sales_webhooks import (  # noqa: F401, E402
    _PROTECTED_DOMAINS,
    _record_email_signal,
    _send_booking_reply,
    _trigger_sms_followup,
    _verify_sendgrid_webhook,
    inbound_email_webhook,
    email_events_webhook,
    unsubscribe,
)
from src.api.sales_prospects import (  # noqa: F401, E402
    _serialize_prospect,
    list_prospects,
    get_prospect,
    update_prospect,
    delete_prospect,
    create_prospect,
    blacklist_prospect,
    get_prospect_emails,
    bulk_update_prospects,
)
from src.api.sales_config import (  # noqa: F401, E402
    get_sales_config,
    update_sales_config,
    get_sales_metrics,
    get_worker_status,
    pause_worker,
    resume_worker,
    list_templates,
    create_template,
    update_template,
    delete_template,
    get_insights,
)
from src.api.sales_scraper import (  # noqa: F401, E402
    list_scrape_jobs,
    trigger_scrape_job,
    _run_scrape_background,
)
from src.api.sales_dashboard import (  # noqa: F401, E402
    list_campaigns,
    create_campaign,
    update_campaign,
    pause_campaign,
    resume_campaign,
    _compute_send_window_label,
    _build_activity_feed,
    _compute_alerts,
    get_command_center,
)
