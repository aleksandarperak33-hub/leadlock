"""
Simulate an inbound lead via the web form webhook.

Usage:
    python scripts/simulate_lead.py
    python scripts/simulate_lead.py --source missed_call
    python scripts/simulate_lead.py --phone "+15125559999" --name "Jane Doe"
"""
import argparse
import asyncio
import logging

import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:8000"


async def simulate_web_form(phone: str, name: str, service: str, client_slug: str):
    """Send a test lead through the web form webhook."""
    payload = {
        "client_id": client_slug,
        "first_name": name.split()[0],
        "last_name": name.split()[-1] if len(name.split()) > 1 else "",
        "phone": phone,
        "email": f"{name.split()[0].lower()}@example.com",
        "service_type": service,
        "message": f"I need help with {service.lower()}. Can someone come out this week?",
        "source": "website",
        "consent_text": "I agree to receive text messages from this business.",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{BASE_URL}/api/webhooks/form", json=payload)
        logger.info("Web form response: %s %s", resp.status_code, resp.json())
        return resp


async def simulate_missed_call(phone: str, client_slug: str):
    """Send a test missed call webhook."""
    payload = {
        "client_id": client_slug,
        "caller_phone": phone,
        "caller_name": "Unknown Caller",
        "call_duration": 0,
        "timestamp": "2026-02-14T10:30:00Z",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{BASE_URL}/api/webhooks/missed-call", json=payload)
        logger.info("Missed call response: %s %s", resp.status_code, resp.json())
        return resp


async def simulate_sms_reply(phone: str, body: str, to_phone: str):
    """Simulate an inbound SMS (Twilio webhook format)."""
    payload = {
        "From": phone,
        "To": to_phone,
        "Body": body,
        "MessageSid": "SM_TEST_00000000000000000000000000",
        "NumMedia": "0",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BASE_URL}/api/webhooks/twilio/sms",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        logger.info("SMS reply response: %s %s", resp.status_code, resp.text)
        return resp


async def main():
    parser = argparse.ArgumentParser(description="Simulate inbound leads")
    parser.add_argument("--source", default="web_form", choices=["web_form", "missed_call", "sms_reply"])
    parser.add_argument("--phone", default="+15125559876")
    parser.add_argument("--name", default="John Smith")
    parser.add_argument("--service", default="AC Repair")
    parser.add_argument("--client", default="austin-comfort-hvac")
    parser.add_argument("--body", default="Yes, I need AC repair ASAP")
    parser.add_argument("--to-phone", default="+15125550199")
    args = parser.parse_args()

    logger.info("Simulating %s lead from %s...", args.source, args.phone)

    if args.source == "web_form":
        await simulate_web_form(args.phone, args.name, args.service, args.client)
    elif args.source == "missed_call":
        await simulate_missed_call(args.phone, args.client)
    elif args.source == "sms_reply":
        await simulate_sms_reply(args.phone, args.body, args.to_phone)


if __name__ == "__main__":
    asyncio.run(main())
