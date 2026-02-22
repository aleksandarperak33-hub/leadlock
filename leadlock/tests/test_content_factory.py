"""
Tests for content factory - generation service and worker.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestGenerateContentPiece:
    @pytest.mark.asyncio
    async def test_generates_blog_post(self):
        from src.services.content_generation import generate_content_piece

        ai_response = {
            "content": '{"title": "Speed to Lead in HVAC", "body": "## Introduction\\nContent here...", "seo_meta": "Learn about speed to lead", "word_count": 1000}',
            "cost_usd": 0.025,
            "model": "claude-sonnet-4-5-20250929",
            "error": None,
        }

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        class _FakeCtx:
            async def __aenter__(self):
                return mock_db
            async def __aexit__(self, *a):
                pass

        with (
            patch("src.services.content_generation.generate_response", new_callable=AsyncMock, return_value=ai_response),
            patch("src.services.content_generation.async_session_factory", return_value=_FakeCtx()),
            patch("src.services.content_generation._track_agent_cost", new_callable=AsyncMock),
        ):
            result = await generate_content_piece(
                content_type="blog_post",
                target_trade="hvac",
            )

        assert result["title"] == "Speed to Lead in HVAC"
        assert result["word_count"] == 1000
        assert result["ai_cost_usd"] == 0.025
        assert "content_id" in result

    @pytest.mark.asyncio
    async def test_generates_twitter_post(self):
        from src.services.content_generation import generate_content_piece

        ai_response = {
            "content": '{"title": "tweet", "body": "The average contractor takes 4 hours to respond to a lead.", "word_count": 12}',
            "cost_usd": 0.001,
            "model": "claude-haiku-4-5-20251001",
            "error": None,
        }

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        class _FakeCtx:
            async def __aenter__(self):
                return mock_db
            async def __aexit__(self, *a):
                pass

        with (
            patch("src.services.content_generation.generate_response", new_callable=AsyncMock, return_value=ai_response),
            patch("src.services.content_generation.async_session_factory", return_value=_FakeCtx()),
            patch("src.services.content_generation._track_agent_cost", new_callable=AsyncMock),
        ):
            result = await generate_content_piece(content_type="twitter", topic="test topic")

        assert "content_id" in result
        assert result["word_count"] == 12

    @pytest.mark.asyncio
    async def test_returns_error_on_ai_failure(self):
        from src.services.content_generation import generate_content_piece

        ai_response = {"content": "", "cost_usd": 0.0, "error": "rate limit"}

        with patch("src.services.content_generation.generate_response", new_callable=AsyncMock, return_value=ai_response):
            result = await generate_content_piece(content_type="blog_post")

        assert result.get("error") == "rate limit"

    @pytest.mark.asyncio
    async def test_returns_error_on_unknown_type(self):
        from src.services.content_generation import generate_content_piece

        result = await generate_content_piece(content_type="unknown_type")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_returns_error_on_empty_body(self):
        from src.services.content_generation import generate_content_piece

        ai_response = {
            "content": '{"title": "Test", "body": "", "word_count": 0}',
            "cost_usd": 0.001,
            "error": None,
        }

        with (
            patch("src.services.content_generation.generate_response", new_callable=AsyncMock, return_value=ai_response),
            patch("src.services.content_generation._track_agent_cost", new_callable=AsyncMock),
        ):
            result = await generate_content_piece(content_type="twitter", topic="test")

        assert "error" in result


class TestPickKeyword:
    def test_returns_string(self):
        from src.services.content_generation import _pick_keyword

        keyword = _pick_keyword("hvac")
        assert isinstance(keyword, str)
        assert len(keyword) > 0

    def test_general_fallback(self):
        from src.services.content_generation import _pick_keyword

        keyword = _pick_keyword("nonexistent")
        assert isinstance(keyword, str)
