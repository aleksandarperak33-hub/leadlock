"""
Tests for record_lead_signal() in src/services/learning.py.

Verifies that lead lifecycle signals (qualified, booked, cold, reengaged)
are recorded with correct value polarity and that metadata is merged into
dimensions alongside lead_id.
"""

import pytest
from unittest.mock import AsyncMock, patch

from src.services.learning import record_lead_signal


@pytest.mark.asyncio
@patch("src.services.learning.record_signal", new_callable=AsyncMock)
async def test_qualified_signal_has_positive_value(mock_record: AsyncMock) -> None:
    """lead_qualified should record value=1.0 (positive outcome)."""
    await record_lead_signal(
        lead_id="abc-123",
        signal_type="lead_qualified",
        metadata={"qualify_variant": "B", "source": "google_lsa"},
    )
    mock_record.assert_called_once_with(
        signal_type="lead_qualified",
        dimensions={"lead_id": "abc-123", "qualify_variant": "B", "source": "google_lsa"},
        value=1.0,
    )


@pytest.mark.asyncio
@patch("src.services.learning.record_signal", new_callable=AsyncMock)
async def test_booked_signal_has_positive_value(mock_record: AsyncMock) -> None:
    """lead_booked should record value=1.0 (positive outcome)."""
    await record_lead_signal(
        lead_id="def-456",
        signal_type="lead_booked",
        metadata={"time_to_book_seconds": 120, "crm": "servicetitan"},
    )
    mock_record.assert_called_once_with(
        signal_type="lead_booked",
        dimensions={"lead_id": "def-456", "time_to_book_seconds": 120, "crm": "servicetitan"},
        value=1.0,
    )


@pytest.mark.asyncio
@patch("src.services.learning.record_signal", new_callable=AsyncMock)
async def test_cold_signal_has_zero_value(mock_record: AsyncMock) -> None:
    """lead_went_cold should record value=0.0 (negative outcome)."""
    await record_lead_signal(
        lead_id="ghi-789",
        signal_type="lead_went_cold",
        metadata={"response_count": 0, "source": "yelp"},
    )
    mock_record.assert_called_once_with(
        signal_type="lead_went_cold",
        dimensions={"lead_id": "ghi-789", "response_count": 0, "source": "yelp"},
        value=0.0,
    )


@pytest.mark.asyncio
@patch("src.services.learning.record_signal", new_callable=AsyncMock)
async def test_reengaged_signal_has_positive_value(mock_record: AsyncMock) -> None:
    """lead_reengaged should record value=1.0 (positive outcome)."""
    await record_lead_signal(
        lead_id="jkl-012",
        signal_type="lead_reengaged",
        metadata={"days_cold": 5, "reengage_method": "follow_up_sms"},
    )
    mock_record.assert_called_once_with(
        signal_type="lead_reengaged",
        dimensions={"lead_id": "jkl-012", "days_cold": 5, "reengage_method": "follow_up_sms"},
        value=1.0,
    )


@pytest.mark.asyncio
@patch("src.services.learning.record_signal", new_callable=AsyncMock)
async def test_metadata_merged_into_dimensions_with_lead_id(mock_record: AsyncMock) -> None:
    """Dimensions dict must contain lead_id plus all metadata keys."""
    metadata = {
        "trade": "hvac",
        "state": "TX",
        "response_count": 3,
        "time_to_qualify_seconds": 45,
    }
    await record_lead_signal(
        lead_id="mno-345",
        signal_type="lead_qualified",
        metadata=metadata,
    )
    call_kwargs = mock_record.call_args.kwargs
    dimensions = call_kwargs["dimensions"]

    assert dimensions["lead_id"] == "mno-345"
    assert dimensions["trade"] == "hvac"
    assert dimensions["state"] == "TX"
    assert dimensions["response_count"] == 3
    assert dimensions["time_to_qualify_seconds"] == 45
    assert len(dimensions) == 5  # lead_id + 4 metadata keys


@pytest.mark.asyncio
@patch("src.services.learning.record_signal", new_callable=AsyncMock)
async def test_record_signal_called_with_correct_kwargs(mock_record: AsyncMock) -> None:
    """record_signal receives exactly signal_type, dimensions, and value."""
    await record_lead_signal(
        lead_id="pqr-678",
        signal_type="lead_booked",
        metadata={"source": "facebook"},
    )
    mock_record.assert_called_once()
    call_kwargs = mock_record.call_args.kwargs

    assert set(call_kwargs.keys()) == {"signal_type", "dimensions", "value"}
    assert call_kwargs["signal_type"] == "lead_booked"
    assert call_kwargs["value"] == 1.0
    assert call_kwargs["dimensions"] == {"lead_id": "pqr-678", "source": "facebook"}


@pytest.mark.asyncio
@patch("src.services.learning.record_signal", new_callable=AsyncMock)
async def test_empty_metadata_produces_dimensions_with_only_lead_id(mock_record: AsyncMock) -> None:
    """When metadata is empty, dimensions should contain only lead_id."""
    await record_lead_signal(
        lead_id="stu-901",
        signal_type="lead_qualified",
        metadata={},
    )
    call_kwargs = mock_record.call_args.kwargs
    assert call_kwargs["dimensions"] == {"lead_id": "stu-901"}


@pytest.mark.asyncio
@patch("src.services.learning.record_signal", new_callable=AsyncMock)
async def test_original_metadata_dict_is_not_mutated(mock_record: AsyncMock) -> None:
    """Caller's metadata dict must not be modified by the function."""
    metadata = {"source": "google_lsa"}
    original_copy = metadata.copy()

    await record_lead_signal(
        lead_id="vwx-234",
        signal_type="lead_qualified",
        metadata=metadata,
    )

    assert metadata == original_copy, "metadata dict was mutated by record_lead_signal"
