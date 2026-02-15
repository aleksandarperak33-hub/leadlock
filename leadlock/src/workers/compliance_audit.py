"""
Compliance audit worker — periodic check for violations.
"""
import asyncio
import logging
from datetime import datetime
from sqlalchemy import select, func, and_

from src.database import async_session_factory
from src.models.lead import Lead
from src.models.consent import ConsentRecord

logger = logging.getLogger(__name__)


async def run_compliance_audit():
    """Periodic compliance audit. Runs daily at 2 AM."""
    logger.info("Compliance audit worker started")

    while True:
        now = datetime.utcnow()
        if now.hour == 2:
            try:
                await audit_compliance()
            except Exception as e:
                logger.error("Compliance audit error: %s", str(e))
        await asyncio.sleep(3600)


async def audit_compliance():
    """Run compliance audit checks."""
    async with async_session_factory() as db:
        # Check for leads without consent
        no_consent = await db.execute(
            select(func.count(Lead.id)).where(Lead.consent_id.is_(None))
        )
        count = no_consent.scalar() or 0
        if count > 0:
            logger.warning("COMPLIANCE AUDIT: %d leads without consent records", count)

        # Check for expired consent records
        expired = await db.execute(
            select(func.count(ConsentRecord.id)).where(
                and_(
                    ConsentRecord.expires_at.isnot(None),
                    ConsentRecord.expires_at < datetime.utcnow(),
                    ConsentRecord.is_active == True,
                )
            )
        )
        expired_count = expired.scalar() or 0
        if expired_count > 0:
            logger.warning("COMPLIANCE AUDIT: %d expired consent records still active", expired_count)

        logger.info("Compliance audit completed")
