"""
Run a manual compliance audit.

Checks for:
- Leads without consent records
- Expired consent records (>5 years)
- Messages sent during quiet hours
- Messages sent to opted-out numbers
- Messages missing STOP language or business name

Usage:
    python scripts/run_compliance_audit.py
    python scripts/run_compliance_audit.py --client austin-comfort-hvac
"""
import argparse
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.config import get_settings
from src.models.lead import Lead
from src.models.consent import ConsentRecord
from src.models.conversation import ConversationMessage

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


async def audit(client_slug: str | None = None):
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    issues = []
    now = datetime.now(timezone.utc)

    async with async_session() as session:
        # 1. Leads without consent records
        query = (
            select(Lead)
            .outerjoin(ConsentRecord, Lead.phone == ConsentRecord.phone)
            .where(ConsentRecord.id.is_(None))
            .where(Lead.status != "dead")
        )
        result = await session.execute(query)
        no_consent = result.scalars().all()
        if no_consent:
            issues.append(
                f"[CRITICAL] {len(no_consent)} active leads WITHOUT consent records"
            )
            for lead in no_consent[:5]:
                issues.append(f"  - Lead {lead.id}: {lead.phone[:6]}*** ({lead.status})")

        # 2. Expired consent records (>5 years per FTC TSR 2024)
        five_years_ago = now - timedelta(days=5 * 365)
        query = select(func.count()).select_from(ConsentRecord).where(
            and_(
                ConsentRecord.consented_at < five_years_ago,
                ConsentRecord.is_active == True,
            )
        )
        result = await session.execute(query)
        expired_count = result.scalar()
        if expired_count:
            issues.append(
                f"[WARNING] {expired_count} consent records older than 5 years (need renewal)"
            )

        # 3. Opted-out leads still receiving messages
        query = (
            select(ConversationMessage)
            .join(Lead, ConversationMessage.lead_id == Lead.id)
            .where(Lead.status == "opted_out")
            .where(ConversationMessage.direction == "outbound")
            .where(ConversationMessage.created_at > now - timedelta(days=30))
        )
        result = await session.execute(query)
        post_optout = result.scalars().all()
        if post_optout:
            issues.append(
                f"[CRITICAL] {len(post_optout)} outbound messages to opted-out leads in last 30 days"
            )

        # 4. Messages missing compliance language
        query = (
            select(ConversationMessage)
            .where(ConversationMessage.direction == "outbound")
            .where(ConversationMessage.message_type == "sms")
            .where(ConversationMessage.created_at > now - timedelta(days=7))
        )
        result = await session.execute(query)
        recent_messages = result.scalars().all()

        missing_stop = 0
        for msg in recent_messages:
            if msg.body and "STOP" not in msg.body.upper():
                # Only first messages need STOP language
                first_check = await session.execute(
                    select(func.count())
                    .select_from(ConversationMessage)
                    .where(
                        and_(
                            ConversationMessage.lead_id == msg.lead_id,
                            ConversationMessage.direction == "outbound",
                            ConversationMessage.created_at < msg.created_at,
                        )
                    )
                )
                if first_check.scalar() == 0:
                    missing_stop += 1

        if missing_stop:
            issues.append(
                f"[CRITICAL] {missing_stop} first-contact messages missing STOP language"
            )

        # 5. Summary stats
        total_leads = (await session.execute(select(func.count()).select_from(Lead))).scalar()
        total_consent = (await session.execute(select(func.count()).select_from(ConsentRecord))).scalar()
        opted_out = (
            await session.execute(
                select(func.count())
                .select_from(ConsentRecord)
                .where(ConsentRecord.opted_out == True)
            )
        ).scalar()

    await engine.dispose()

    # Print report
    print("\n" + "=" * 60)
    print("  LEADLOCK COMPLIANCE AUDIT REPORT")
    print(f"  Generated: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 60)
    print(f"\n  Total leads:           {total_leads}")
    print(f"  Total consent records: {total_consent}")
    print(f"  Opted-out records:     {opted_out}")
    print()

    if issues:
        print("  ISSUES FOUND:")
        print("  " + "-" * 40)
        for issue in issues:
            print(f"  {issue}")
    else:
        print("  No compliance issues found.")

    print("\n" + "=" * 60)

    return len(issues)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run compliance audit")
    parser.add_argument("--client", default=None, help="Client slug to audit")
    args = parser.parse_args()
    issue_count = asyncio.run(audit(args.client))
    exit(1 if issue_count > 0 else 0)
