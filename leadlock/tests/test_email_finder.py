"""
Tests for email finder worker — discovers real emails for unverified prospects.

Covers:
- run_email_finder main loop (startup delay, heartbeat, error handling)
- _process_batch (query filters, discovery calls, email replacement logic)
- Retry-window gating (email_discovery_attempted_at)
- Cost tracking
"""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_mock_session(total_count: int, due_count: int, prospects: list):
    """Build a mock async session that returns total, due, and fetch results."""
    mock_total = MagicMock()
    mock_total.scalar.return_value = total_count

    mock_due = MagicMock()
    mock_due.scalar.return_value = due_count

    mock_fetch = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = prospects
    mock_fetch.scalars.return_value = mock_scalars

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        side_effect=[mock_total, mock_due, mock_fetch]
    )
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


def _make_prospect(**overrides) -> MagicMock:
    """Build a mock Outreach prospect with sensible defaults."""
    prospect = MagicMock()
    defaults = {
        "prospect_name": "HVAC Pro",
        "prospect_email": "info@hvacpro.com",
        "prospect_company": "HVAC Pro Inc",
        "website": "https://hvacpro.com",
        "enrichment_data": None,
        "email_source": "pattern_guess",
        "email_verified": False,
        "total_cost_usd": 0.0,
        "email_discovery_attempted_at": None,
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(prospect, k, v)
    return prospect


# ---------------------------------------------------------------------------
# _process_batch — core batch processing logic
# ---------------------------------------------------------------------------
class TestProcessBatch:
    """Test the batch processor that finds emails for unverified prospects."""

    @pytest.mark.asyncio
    async def test_skips_when_no_eligible_prospects(self):
        """No unverified pattern-guessed prospects -> no work."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.workers.email_finder.async_session_factory",
            return_value=mock_session,
        ):
            from src.workers.email_finder import _process_batch
            await _process_batch()

        # Should not call commit when there's nothing to process
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_all_recently_attempted(self):
        """All prospects attempted within retry window -> no work."""
        # total=10 but due=0
        mock_total = MagicMock()
        mock_total.scalar.return_value = 10

        mock_due = MagicMock()
        mock_due.scalar.return_value = 0

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[mock_total, mock_due]
        )
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.workers.email_finder.async_session_factory",
            return_value=mock_session,
        ):
            from src.workers.email_finder import _process_batch
            await _process_batch()

        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_replaces_email_from_better_source(self):
        """Discovery finds a better email -> replaces the pattern guess."""
        prospect = _make_prospect()
        mock_session = _make_mock_session(1, 1, [prospect])

        discovery_result = {
            "email": "owner@hvacpro.com",
            "source": "website_deep_scrape",
            "confidence": "high",
            "cost_usd": 0.0,
        }

        with patch(
            "src.workers.email_finder.async_session_factory",
            return_value=mock_session,
        ), patch(
            "src.workers.email_finder.discover_email",
            new_callable=AsyncMock,
            return_value=discovery_result,
        ):
            from src.workers.email_finder import _process_batch
            await _process_batch()

        # Email should be replaced
        assert prospect.prospect_email == "owner@hvacpro.com"
        assert prospect.email_source == "website_deep_scrape"
        assert prospect.email_verified is True
        # Attempt timestamp should be set
        assert prospect.email_discovery_attempted_at is not None

    @pytest.mark.asyncio
    async def test_keeps_current_when_only_pattern_guess(self):
        """Discovery only returns pattern_guess -> keep current email, stamp attempt."""
        prospect = _make_prospect()
        mock_session = _make_mock_session(1, 1, [prospect])

        discovery_result = {
            "email": "info@hvacpro.com",
            "source": "pattern_guess",
            "confidence": "low",
            "cost_usd": 0.0,
        }

        with patch(
            "src.workers.email_finder.async_session_factory",
            return_value=mock_session,
        ), patch(
            "src.workers.email_finder.discover_email",
            new_callable=AsyncMock,
            return_value=discovery_result,
        ):
            from src.workers.email_finder import _process_batch
            await _process_batch()

        # Email should NOT be changed
        assert prospect.prospect_email == "info@hvacpro.com"
        # But attempt timestamp SHOULD be stamped (this is the key fix)
        assert prospect.email_discovery_attempted_at is not None

    @pytest.mark.asyncio
    async def test_upgrades_source_when_same_email_better_source(self):
        """Same email but from better source -> upgrades source attribution."""
        prospect = _make_prospect()
        mock_session = _make_mock_session(1, 1, [prospect])

        # Same email, but discovered via deep scrape (higher confidence)
        discovery_result = {
            "email": "info@hvacpro.com",
            "source": "website_deep_scrape",
            "confidence": "high",
            "cost_usd": 0.0,
        }

        with patch(
            "src.workers.email_finder.async_session_factory",
            return_value=mock_session,
        ), patch(
            "src.workers.email_finder.discover_email",
            new_callable=AsyncMock,
            return_value=discovery_result,
        ):
            from src.workers.email_finder import _process_batch
            await _process_batch()

        # Source should be upgraded, email unchanged
        assert prospect.prospect_email == "info@hvacpro.com"
        assert prospect.email_source == "website_deep_scrape"
        assert prospect.email_verified is True

    @pytest.mark.asyncio
    async def test_handles_discovery_exception(self):
        """Exception during discovery -> stamps attempt and continues."""
        prospect = _make_prospect()
        mock_session = _make_mock_session(1, 1, [prospect])

        with patch(
            "src.workers.email_finder.async_session_factory",
            return_value=mock_session,
        ), patch(
            "src.workers.email_finder.discover_email",
            new_callable=AsyncMock,
            side_effect=Exception("discovery exploded"),
        ):
            from src.workers.email_finder import _process_batch
            # Should not raise
            await _process_batch()

        # Attempt should still be stamped even on exception
        assert prospect.email_discovery_attempted_at is not None

    @pytest.mark.asyncio
    async def test_tracks_discovery_cost(self):
        """Discovery cost is accumulated on prospect's total_cost_usd."""
        prospect = _make_prospect(total_cost_usd=0.10)
        mock_session = _make_mock_session(1, 1, [prospect])

        discovery_result = {
            "email": "owner@hvacpro.com",
            "source": "brave_search",
            "confidence": "medium",
            "cost_usd": 0.005,
        }

        with patch(
            "src.workers.email_finder.async_session_factory",
            return_value=mock_session,
        ), patch(
            "src.workers.email_finder.discover_email",
            new_callable=AsyncMock,
            return_value=discovery_result,
        ):
            from src.workers.email_finder import _process_batch
            await _process_batch()

        assert prospect.total_cost_usd == pytest.approx(0.105)

    @pytest.mark.asyncio
    async def test_handles_no_email_from_discovery(self):
        """Discovery returns no email -> counted as failed, attempt stamped."""
        prospect = _make_prospect(
            prospect_name="Unknown Co",
            prospect_email="info@unknownco.com",
            prospect_company="Unknown Co",
            website="https://unknownco.com",
        )
        mock_session = _make_mock_session(1, 1, [prospect])

        discovery_result = {
            "email": None,
            "source": None,
            "confidence": None,
            "cost_usd": 0.0,
        }

        with patch(
            "src.workers.email_finder.async_session_factory",
            return_value=mock_session,
        ), patch(
            "src.workers.email_finder.discover_email",
            new_callable=AsyncMock,
            return_value=discovery_result,
        ):
            from src.workers.email_finder import _process_batch
            await _process_batch()

        # Email should remain unchanged
        assert prospect.prospect_email == "info@unknownco.com"
        # Attempt should be stamped
        assert prospect.email_discovery_attempted_at is not None
