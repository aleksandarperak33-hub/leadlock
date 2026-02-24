"""
Humanizer prompt fragments -- injected into AI generation prompts to make
outreach emails and SMS messages sound authentically human-written.

Distilled from 24 AI writing anti-patterns. Two variants:
- EMAIL_HUMANIZER: Cold outreach emails (most detailed)
- SMS_HUMANIZER: Conversational SMS messages (lighter)

Usage:
    from src.prompts.humanizer import EMAIL_HUMANIZER, SMS_HUMANIZER
    system_prompt = f"{base_prompt}\n\n{EMAIL_HUMANIZER}"
"""

# ── Banned AI vocabulary (the single biggest tell) ──────────────────────────
# These words appear 10-50x more in AI text than human text.
# Sorted by severity -- the first dozen are dead giveaways.
BANNED_WORDS = (
    "leverage, delve, robust, nuanced, streamline, elevate, embark, "
    "foster, intricate, pivotal, testament, multifaceted, cornerstone, "
    "paramount, beacon, unprecedented, meticulous, tapestry, landscape, "
    "realm, harness, spearhead, underscore, commendable, shed light, "
    "navigating, holistic, synergy, endeavor, resonate, empower, "
    "comprehensive, facilitate, optimize, utilize, solution, platform, "
    "opportunity, pain point, I noticed, I came across, I found your"
)


# ── Email humanizer (cold outreach) ─────────────────────────────────────────
EMAIL_HUMANIZER = f"""SOUND HUMAN (critical):
- BANNED WORDS (never use): {BANNED_WORDS}
- No "not just X, but Y" or "it's not about X; it's about Y" constructions
- No lists of exactly three items (rule-of-three is an AI pattern)
- Don't dance around "is" - just say "this is", not "this represents" or "this serves as"
- No filler: skip "it's important to note", "it's worth mentioning", "at the end of the day"
- No hedging: skip "it's important to remember that", "one could argue"
- Use contractions naturally (don't, won't, it's, we're, you're, that's)
- Vary sentence length - mix short punchy lines with longer ones
- Start an occasional sentence with "And" or "But" (humans do this constantly)
- Write like you talk. Read it out loud. If it sounds like a press release, rewrite it."""


# ── SMS humanizer (conversational) ──────────────────────────────────────────
SMS_HUMANIZER = f"""SOUND HUMAN (critical):
- BANNED WORDS: {BANNED_WORDS}
- Use contractions (don't, won't, it's, we're, you'd)
- No filler phrases ("it's important to note", "at the end of the day")
- Never open with "Absolutely!" or "Great question!" - just answer directly
- Don't repeat what the customer just said back to them - move the conversation forward
- Write like you'd actually text someone. Short, direct, natural."""
