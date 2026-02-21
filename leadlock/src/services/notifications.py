"""
Notification service - owner alerts for emergencies and important events.
"""
import logging
from typing import Optional
from src.services.sms import send_sms, mask_phone

logger = logging.getLogger(__name__)


async def notify_owner_emergency(
    owner_phone: str,
    business_name: str,
    lead_phone: str,
    emergency_type: str,
    message_preview: str,
) -> bool:
    """
    Send emergency alert to business owner.
    Used when a lead reports a life-safety emergency.
    """
    masked_lead = mask_phone(lead_phone)
    alert_text = (
        f"EMERGENCY ALERT - {business_name}\n"
        f"Type: {emergency_type}\n"
        f"Lead: {masked_lead}\n"
        f"Message: {message_preview[:100]}\n"
        f"Action: Lead is being prioritized. Check your dashboard."
    )

    try:
        result = await send_sms(to=owner_phone, body=alert_text)
        if result.get("error"):
            logger.error("Failed to send owner emergency alert: %s", result["error"])
            return False
        logger.info("Emergency alert sent to owner %s", mask_phone(owner_phone))
        return True
    except Exception as e:
        logger.error("Exception sending owner emergency alert: %s", str(e))
        return False


async def notify_owner_booking(
    owner_phone: str,
    business_name: str,
    lead_name: str,
    service_type: str,
    appointment_date: str,
    time_window: str,
) -> bool:
    """Send booking confirmation notification to business owner."""
    text = (
        f"New Booking - {business_name}\n"
        f"Customer: {lead_name}\n"
        f"Service: {service_type}\n"
        f"Date: {appointment_date}\n"
        f"Time: {time_window}"
    )

    try:
        result = await send_sms(to=owner_phone, body=text)
        return not result.get("error")
    except Exception as e:
        logger.error("Failed to send booking notification: %s", str(e))
        return False
