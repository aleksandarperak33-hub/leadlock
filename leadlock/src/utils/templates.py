"""
SMS template engine - all message templates with A/B variants.
CRITICAL: First messages MUST include "Reply STOP to opt out" and business name.
Templates use {variable} substitution. Never use URL shorteners.
"""
import logging
import random
from typing import Optional

logger = logging.getLogger(__name__)

# === INTAKE TEMPLATES (first response) ===
# Every first message includes business name + STOP language

INTAKE_TEMPLATES = {
    "standard": {
        "A": (
            "Hi {first_name}, this is {rep_name} from {business_name}. "
            "We got your request for {service_type} and want to help. "
            "What's going on with it? "
            "Reply STOP to opt out."
        ),
        "B": (
            "Hey {first_name}, {rep_name} here from {business_name}. "
            "Got your message about {service_type}. "
            "What can we do for you? "
            "Reply STOP to opt out."
        ),
    },
    "missed_call": {
        "A": (
            "Hi {first_name}, this is {rep_name} from {business_name}. "
            "Sorry we missed your call. How can we help? "
            "Reply STOP to opt out."
        ),
        "B": (
            "Hey {first_name}, {rep_name} at {business_name} here. "
            "Missed your call - what can we do for you? "
            "Reply STOP to opt out."
        ),
    },
    "text_in": {
        "A": (
            "Hi, this is {rep_name} from {business_name}. "
            "Thanks for texting. How can we help? "
            "Reply STOP to opt out."
        ),
        "B": (
            "Hey, {rep_name} from {business_name} here. "
            "Got your message - what do you need help with? "
            "Reply STOP to opt out."
        ),
    },
    "emergency": {
        "A": (
            "Hi {first_name}, this is {rep_name} from {business_name}. "
            "We understand you have an urgent {service_type} situation. "
            "We're prioritizing your request right now. "
            "Can you confirm your address so we can get someone to you ASAP? "
            "Reply STOP to opt out."
        ),
        "B": (
            "{first_name}, {rep_name} from {business_name} here. "
            "We see this is an emergency {service_type} situation - "
            "we're on it! Please confirm your address and we'll dispatch help immediately. "
            "Reply STOP to opt out."
        ),
    },
    "after_hours": {
        "A": (
            "Hi {first_name}! This is {rep_name} from {business_name}. "
            "We got your request for {service_type}. We're currently outside business hours "
            "but I can get you scheduled for the next available time. "
            "When would work best for you? "
            "Reply STOP to opt out."
        ),
        "B": (
            "Hey {first_name}, {rep_name} at {business_name}. "
            "Thanks for reaching out about {service_type}! We're closed right now "
            "but I'd love to get you on the schedule. "
            "What day and time window works for you? "
            "Reply STOP to opt out."
        ),
    },
}

# === QUALIFY TEMPLATES (follow-up questions) ===
QUALIFY_TEMPLATES = {
    "ask_service": "What type of service do you need? (repair, installation, maintenance, etc.)",
    "ask_urgency": "How urgent is this? Do you need someone today, this week, or are you flexible?",
    "ask_property": "Is this for a residential home or commercial property?",
    "ask_address": "What's the address where the service is needed?",
}

# === BOOKING TEMPLATES ===
BOOKING_TEMPLATES = {
    "confirm": {
        "A": (
            "Great news, {first_name}! You're all set. "
            "Here are your appointment details:\n"
            "Date: {date}\n"
            "Time: {time_window}\n"
            "Service: {service_type}\n"
            "Tech: {tech_name}\n\n"
            "We'll send you a reminder the day before. "
            "Reply if you need to make any changes!"
        ),
        "B": (
            "You're booked, {first_name}! Here's what's confirmed:\n"
            "{date} between {time_window}\n"
            "{service_type} with {tech_name}\n\n"
            "You'll get a reminder tomorrow. "
            "Just reply here if anything changes!"
        ),
    },
    "no_availability": (
        "I want to get you scheduled, {first_name}, but our earliest opening is {next_date}. "
        "Would {next_date} between {time_window} work for you?"
    ),
}

# === FOLLOW-UP TEMPLATES ===
FOLLOWUP_TEMPLATES = {
    "cold_nurture_1": {
        "A": (
            "Hi {first_name}, just checking in from {business_name}! "
            "Are you still looking for help with {service_type}? "
            "We'd love to get you taken care of."
        ),
        "B": (
            "Hey {first_name}, {rep_name} from {business_name} here. "
            "Wanted to follow up on your {service_type} request. "
            "Still need help?"
        ),
    },
    "cold_nurture_2": {
        "A": (
            "Hi {first_name}, this is {business_name} following up one more time. "
            "We're ready to help whenever you are. "
            "Just reply and we'll get you scheduled!"
        ),
        "B": (
            "{first_name}, quick follow-up from {business_name}. "
            "If you're still interested in {service_type}, "
            "just say the word and we'll set everything up."
        ),
    },
    "cold_nurture_3": {
        "A": (
            "Last check-in, {first_name}! {business_name} is here whenever you're ready "
            "for {service_type}. No pressure - just reply anytime."
        ),
        "B": (
            "Hi {first_name}, final follow-up from {business_name}. "
            "We're here if you need {service_type} help. Take care!"
        ),
    },
    "day_before_reminder": {
        "A": (
            "Reminder: Your {service_type} appointment with {business_name} "
            "is tomorrow, {date}, between {time_window}. "
            "Reply to confirm or reschedule!"
        ),
        "B": (
            "Hi {first_name}! Just a friendly reminder - "
            "{tech_name} from {business_name} will be there tomorrow "
            "({date}) between {time_window} for your {service_type}. See you then!"
        ),
    },
    "review_request": {
        "A": (
            "Hi {first_name}! How did everything go with your {service_type}? "
            "We'd love to hear your feedback. "
            "If you had a great experience, a Google review would mean the world to us!"
        ),
        "B": (
            "Hey {first_name}, {business_name} here! "
            "Hope your {service_type} went well. "
            "If you have a moment, we'd appreciate a quick review. Thank you!"
        ),
    },
}

# === AI DISCLOSURE (California SB 1001) ===
AI_DISCLOSURE = "This is an AI assistant helping schedule your appointment."


def render_template(
    template_key: str,
    category: str = "intake",
    variant: Optional[str] = None,
    **kwargs,
) -> str:
    """
    Render an SMS template with variable substitution.
    If no variant specified, randomly selects A or B for A/B testing.
    """
    templates = {
        "intake": INTAKE_TEMPLATES,
        "booking": BOOKING_TEMPLATES,
        "followup": FOLLOWUP_TEMPLATES,
    }

    category_templates = templates.get(category, {})
    template = category_templates.get(template_key)

    if template is None:
        # Return a safe fallback
        return kwargs.get("fallback", "Thank you for contacting us. How can we help?")

    # Handle dict templates (A/B variants)
    if isinstance(template, dict):
        if variant and variant in template:
            text = template[variant]
        else:
            variant = random.choice(list(template.keys()))
            text = template[variant]
    else:
        text = template

    # Substitute variables, using empty string for missing vars
    try:
        return text.format_map(SafeDict(kwargs))
    except Exception as e:
        logger.debug("Template rendering failed for key substitution: %s", str(e))
        return text


class SafeDict(dict):
    """Dict that returns '{key}' for missing keys instead of raising KeyError."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"
