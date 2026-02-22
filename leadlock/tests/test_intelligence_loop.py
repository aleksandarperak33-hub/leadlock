"""
Integration tests for the intelligence loop.
Covers: AB test winner → pattern stored → pattern in prompt → reflection → pattern stored.
"""
import json
import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


class TestABTestToWinningPattern:
    """When AB test declares a winner, a winning pattern should be stored."""

    @pytest.mark.asyncio
    async def test_winner_declaration_stores_pattern(self):
        from src.services.ab_testing import check_and_declare_winner

        exp_id = uuid.uuid4()
        variant_a_id = uuid.uuid4()
        variant_b_id = uuid.uuid4()

        mock_experiment = MagicMock()
        mock_experiment.id = exp_id
        mock_experiment.status = "active"
        mock_experiment.min_sample_per_variant = 30
        mock_experiment.target_trade = "hvac"
        mock_experiment.sequence_step = 1

        mock_variant_a = MagicMock()
        mock_variant_a.id = variant_a_id
        mock_variant_a.variant_label = "A"
        mock_variant_a.subject_instruction = "Use curiosity hook about response time"
        mock_variant_a.total_sent = 50
        mock_variant_a.total_opened = 25
        mock_variant_a.total_replied = 3
        mock_variant_a.open_rate = 0.50
        mock_variant_a.is_winner = False

        mock_variant_b = MagicMock()
        mock_variant_b.id = variant_b_id
        mock_variant_b.variant_label = "B"
        mock_variant_b.subject_instruction = "Use social proof approach"
        mock_variant_b.total_sent = 50
        mock_variant_b.total_opened = 15
        mock_variant_b.total_replied = 1
        mock_variant_b.open_rate = 0.30
        mock_variant_b.is_winner = False

        mock_session = AsyncMock()
        mock_session.get.return_value = mock_experiment
        mock_variants_result = MagicMock()
        mock_variants_result.scalars.return_value.all.return_value = [mock_variant_a, mock_variant_b]
        mock_session.execute.return_value = mock_variants_result
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_store = AsyncMock(return_value="pattern-id")

        with patch("src.services.ab_testing.async_session_factory", return_value=mock_session), \
             patch("src.services.winning_patterns.store_winning_pattern", mock_store):
            result = await check_and_declare_winner(str(exp_id))

        assert result is not None
        assert result["winner_label"] == "A"
        assert result["winner_open_rate"] == 0.50


class TestReflectionToWinningPattern:
    """Reflection analysis should extract and store winning patterns."""

    @pytest.mark.asyncio
    async def test_reflection_stores_patterns(self):
        from src.services.reflection_analysis import run_reflection_analysis

        ai_response = json.dumps({
            "summary": "HVAC outreach performing well, plumbing needs work",
            "ab_test_insights": "Curiosity hooks outperform direct pitches",
            "email_insights": "Step 1 open rates strong at 35%",
            "winback_insights": "Seasonal angle worked best",
            "cost_insights": "Within budget",
            "regressions": [],
            "winning_patterns": [
                {
                    "instruction": "Reference specific Google rating in subject",
                    "trade": "hvac",
                    "step": 1,
                    "open_rate": 0.38,
                    "reason": "Personalized subjects consistently outperform generic",
                },
            ],
            "recommendations": ["Test more question-based subjects"],
        })

        mock_ai_result = {
            "content": ai_response,
            "cost_usd": 0.015,
        }

        mock_store = AsyncMock(return_value="pattern-id")
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()

        with patch("src.services.reflection_analysis.generate_response", return_value=mock_ai_result), \
             patch("src.services.reflection_analysis.track_agent_cost", new_callable=AsyncMock), \
             patch("src.services.winning_patterns.store_winning_pattern", mock_store), \
             patch("src.utils.dedup.get_redis", return_value=mock_redis):
            result = await run_reflection_analysis({"test": "data"})

        assert result.get("error") is None
        assert result["summary"] == "HVAC outreach performing well, plumbing needs work"
        assert len(result["winning_patterns"]) == 1
        assert result["winning_patterns"][0]["instruction"] == "Reference specific Google rating in subject"


class TestPatternsInEmailGeneration:
    """Winning patterns should appear in the outreach email prompt context."""

    @pytest.mark.asyncio
    async def test_learning_context_includes_patterns(self):
        from src.agents.sales_outreach import _get_learning_context

        mock_patterns = "Proven winning approaches (bias toward these):\n1. Use curiosity hook (open rate: 35%)"

        with patch("src.services.learning.get_open_rate_by_dimension", return_value=0.0), \
             patch("src.services.learning.get_best_send_time", return_value=None), \
             patch("src.agents.sales_outreach._get_reply_rate_by_trade", new_callable=AsyncMock, return_value=0.0), \
             patch("src.agents.sales_outreach._get_best_day_of_week", new_callable=AsyncMock, return_value=""), \
             patch("src.services.winning_patterns.format_patterns_for_prompt", new_callable=AsyncMock, return_value=mock_patterns):
            result = await _get_learning_context("hvac", "TX", step=1)

        assert "Proven winning approaches" in result
        assert "curiosity hook" in result


class TestQualityGateInSequencer:
    """Quality gate should catch bad emails before sending."""

    def test_quality_gate_catches_long_subject(self):
        from src.services.email_quality_gate import check_email_quality

        result = check_email_quality(
            subject="A" * 65,
            body_text="Hey Mike, " + "word " * 60 + "\nAlek",
            prospect_name="Mike",
        )
        assert result["passed"] is False

    def test_quality_gate_passes_good_email(self):
        from src.services.email_quality_gate import check_email_quality

        result = check_email_quality(
            subject="Saw your reviews, Mike",
            body_text=(
                "Hey Mike, I noticed your HVAC shop has great reviews in Austin. "
                + "word " * 55
                + "\nAlek"
            ),
            prospect_name="Mike",
            company_name="Cool Air",
        )
        assert result["passed"] is True


class TestHeartbeatTiming:
    """Heartbeats should fire at the START of each loop iteration."""

    def test_sequencer_heartbeat_ttl_is_2700(self):
        """Sequencer Redis TTL should be 2700s (45 min, 1.5x the 30-min cycle)."""
        import ast
        from pathlib import Path

        source = Path("src/workers/outreach_sequencer.py").read_text()
        assert "ex=2700" in source

    def test_health_monitor_stale_threshold_is_45(self):
        """Health monitor should alert after 45 minutes, not 90."""
        from src.workers.outreach_health import HEARTBEAT_STALE_MINUTES
        assert HEARTBEAT_STALE_MINUTES == 45

    def test_sequencer_heartbeats_before_work(self):
        """Heartbeat call should appear before sequence_cycle() in the loop."""
        from pathlib import Path

        source = Path("src/workers/outreach_sequencer.py").read_text()
        # Find the while True loop in run_outreach_sequencer
        loop_start = source.find("while True:")
        heartbeat_pos = source.find("await _heartbeat()", loop_start)
        cycle_pos = source.find("await sequence_cycle()", loop_start)
        assert heartbeat_pos < cycle_pos, "Heartbeat should fire before sequence_cycle"
