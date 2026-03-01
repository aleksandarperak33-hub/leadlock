"""
Shared email constants — single source of truth for generic prefix detection.

Used by:
- outreach_sending.py (send-time blocklist)
- email_discovery.py (confidence downgrade)
- outreach_sequencer.py (ordering deprioritization)
"""

# Generic email prefixes that are NOT personal contacts.
# These addresses (info@, support@, etc.) frequently bounce on SMB domains
# because they're role-based addresses that many small businesses never set up.
GENERIC_EMAIL_PREFIXES: frozenset[str] = frozenset({
    # Common contact aliases
    "info", "contact", "hello", "service", "support",
    "office", "team", "admin", "help", "general",
    "enquiry", "inquiry", "mail", "email",
    # Sales / marketing roles
    "sales", "marketing", "careers", "jobs", "hiring",
    "recruiting", "recruitment",
    # Legal / compliance roles
    "privacy", "legal", "compliance", "gdpr",
    # Technical / infrastructure roles
    "webmaster", "hostmaster", "postmaster", "abuse",
    # Finance roles
    "accounts", "accounting", "billing",
    # No-reply addresses
    "noreply", "no-reply",
})
