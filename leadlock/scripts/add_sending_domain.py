"""
Add a new sending domain/mailbox to a tenant's sender_mailboxes config.

Usage:
    # Dry run (show what would change):
    python scripts/add_sending_domain.py --domain getleadlock.com --name "Alek" --tenant 069d4198

    # Commit the change:
    python scripts/add_sending_domain.py --domain getleadlock.com --name "Alek" --tenant 069d4198 --commit

    # Custom from_email and reply_to:
    python scripts/add_sending_domain.py \\
        --domain getleadlock.com \\
        --from-email outreach@getleadlock.com \\
        --reply-to reply@parse.getleadlock.com \\
        --name "Alek" \\
        --daily-limit 150 \\
        --tenant 069d4198 \\
        --commit

This script:
1. Adds a new mailbox entry to sender_mailboxes JSONB array
2. Initializes warmup tracking in Redis (day 0)
3. Prints DNS records needed for SendGrid domain authentication
"""
import argparse
import asyncio
import copy
import json
import sys
from datetime import datetime, timezone

from sqlalchemy import select, and_


async def main():
    parser = argparse.ArgumentParser(description="Add a sending domain to a tenant")
    parser.add_argument("--domain", required=True, help="New sending domain (e.g. getleadlock.com)")
    parser.add_argument("--tenant", required=True, help="Tenant ID prefix (first 8 chars ok)")
    parser.add_argument("--name", default="Alek", help="Sender first name for email copy")
    parser.add_argument("--from-email", help="From address (default: outreach@domain)")
    parser.add_argument("--reply-to", help="Reply-to address (default: reply@parse.domain)")
    parser.add_argument("--daily-limit", type=int, default=150, help="Per-mailbox daily limit")
    parser.add_argument("--commit", action="store_true", help="Actually write changes")
    args = parser.parse_args()

    domain = args.domain.lower().strip()
    from_email = args.from_email or f"outreach@{domain}"
    reply_to = args.reply_to or f"reply@parse.{domain}"
    from_name = f"{args.name} from LeadLock"

    from src.database import async_session_factory
    from src.models.sales_config import SalesEngineConfig

    async with async_session_factory() as db:
        # Find the tenant config
        result = await db.execute(
            select(SalesEngineConfig).where(
                and_(
                    SalesEngineConfig.is_active == True,  # noqa: E712
                    SalesEngineConfig.tenant_id.isnot(None),
                    SalesEngineConfig.tenant_id.cast(db.bind.dialect.type_descriptor(
                        SalesEngineConfig.tenant_id.type
                    )).like(f"{args.tenant}%") if len(args.tenant) < 36 else
                    SalesEngineConfig.tenant_id == args.tenant,
                )
            )
        )
        configs = result.scalars().all()

        if not configs:
            # Fallback: search by string cast
            from sqlalchemy import text
            r2 = await db.execute(text(
                "SELECT id, tenant_id, sender_mailboxes FROM sales_engine_config "
                "WHERE is_active = true AND tenant_id::text LIKE :prefix"
            ), {"prefix": f"{args.tenant}%"})
            rows = r2.fetchall()
            if not rows:
                print(f"ERROR: No active tenant config found matching '{args.tenant}'")
                sys.exit(1)

            # Use raw SQL path
            row = rows[0]
            config_id = row[0]
            tenant_id = str(row[1])
            current_mailboxes = row[2] or []

            print(f"Tenant: {tenant_id}")
            print(f"Current mailboxes: {json.dumps(current_mailboxes, indent=2)}")

            # Check for duplicates
            existing_emails = {
                mb.get("from_email", "").lower()
                for mb in current_mailboxes
                if isinstance(mb, dict)
            }
            if from_email.lower() in existing_emails:
                print(f"\nERROR: {from_email} already exists in sender_mailboxes")
                sys.exit(1)

            new_mailbox = {
                "from_email": from_email,
                "from_name": from_name,
                "reply_to_email": reply_to,
                "sender_name": args.name,
                "daily_limit": args.daily_limit,
                "is_active": True,
            }

            updated_mailboxes = copy.deepcopy(current_mailboxes)
            updated_mailboxes.append(new_mailbox)

            print(f"\nNew mailbox to add:")
            print(json.dumps(new_mailbox, indent=2))
            print(f"\nUpdated mailboxes ({len(updated_mailboxes)} total):")
            print(json.dumps(updated_mailboxes, indent=2))

            # DNS records needed
            print(f"\n{'='*60}")
            print(f"DNS RECORDS NEEDED FOR {domain}")
            print(f"{'='*60}")
            print(f"1. Authenticate domain in SendGrid:")
            print(f"   Use: SENDGRID_FULL_ACCESS_KEY to call the API")
            print(f"   POST https://api.sendgrid.com/v3/whitelabel/domains")
            print(f"   Body: {{\"domain\": \"{domain}\", \"automatic_security\": true}}")
            print(f"")
            print(f"2. Add CNAME records returned by SendGrid to your DNS:")
            print(f"   - em1234.{domain} -> u1234.wl.sendgrid.net (DKIM)")
            print(f"   - s1._domainkey.{domain} -> s1.domainkey.u1234.wl.sendgrid.net (DKIM)")
            print(f"   - s2._domainkey.{domain} -> s2.domainkey.u1234.wl.sendgrid.net (DKIM)")
            print(f"")
            print(f"3. Add DMARC record:")
            print(f"   _dmarc.{domain} TXT \"v=DMARC1; p=quarantine; rua=mailto:dmarc@{domain}\"")
            print(f"")
            print(f"4. Add SPF (if not using SendGrid automatic_security):")
            print(f"   {domain} TXT \"v=spf1 include:sendgrid.net ~all\"")

            if args.commit:
                # Update DB
                await db.execute(text(
                    "UPDATE sales_engine_config SET sender_mailboxes = :mailboxes::jsonb "
                    "WHERE id = :config_id"
                ), {"mailboxes": json.dumps(updated_mailboxes), "config_id": config_id})
                await db.commit()
                print(f"\nDB updated: {from_email} added to tenant {tenant_id[:8]}")

                # Initialize warmup in Redis
                try:
                    from src.utils.dedup import get_redis
                    redis = await get_redis()
                    warmup_key = f"leadlock:email_warmup:{tenant_id}:{domain}"
                    warmup_start = datetime.now(timezone.utc).isoformat()
                    await redis.set(warmup_key, warmup_start)
                    print(f"Warmup initialized: {warmup_key} = {warmup_start}")
                    print(f"Warmup schedule: 10/d (d0-3) → 20/d (d4-7) → 40/d (d8-14) → 75/d (d15-21) → 120/d (d22-28) → full")
                except Exception as e:
                    print(f"WARNING: Redis warmup init failed: {e}")
                    print(f"Set manually: SET {warmup_key} {datetime.now(timezone.utc).isoformat()}")
            else:
                print(f"\nDRY RUN — add --commit to apply changes")

        else:
            config = configs[0]
            print(f"Found config via ORM — use raw SQL path for now")
            # This path is a fallback; the raw SQL path above handles it


asyncio.run(main())
