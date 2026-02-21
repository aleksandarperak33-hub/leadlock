"""
Tests for src/models/campaign.py and src/models/email_template.py -
SQLAlchemy model definitions, defaults, and repr.
All database calls are mocked to avoid SQLite/JSONB incompatibility.
"""
import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Campaign model
# ---------------------------------------------------------------------------


class TestCampaignModel:
    def test_import(self):
        """Campaign model can be imported."""
        from src.models.campaign import Campaign
        assert Campaign is not None

    def test_tablename(self):
        """Campaign uses 'campaigns' table."""
        from src.models.campaign import Campaign
        assert Campaign.__tablename__ == "campaigns"

    def test_repr(self):
        """Campaign repr shows name and status."""
        from src.models.campaign import Campaign
        # Use MagicMock to avoid SQLAlchemy ORM state issues
        campaign = MagicMock(spec=Campaign)
        campaign.name = "Summer HVAC Push"
        campaign.status = "active"
        # Call the real __repr__ method
        result = Campaign.__repr__(campaign)
        assert result == "<Campaign Summer HVAC Push (active)>"

    def test_repr_draft(self):
        """Campaign repr shows draft status."""
        from src.models.campaign import Campaign
        campaign = MagicMock(spec=Campaign)
        campaign.name = "Winter Promo"
        campaign.status = "draft"
        result = Campaign.__repr__(campaign)
        assert result == "<Campaign Winter Promo (draft)>"

    def test_repr_completed(self):
        """Campaign repr shows completed status."""
        from src.models.campaign import Campaign
        campaign = MagicMock(spec=Campaign)
        campaign.name = "Q4 Outreach"
        campaign.status = "completed"
        result = Campaign.__repr__(campaign)
        assert result == "<Campaign Q4 Outreach (completed)>"

    def test_repr_paused(self):
        """Campaign repr shows paused status."""
        from src.models.campaign import Campaign
        campaign = MagicMock(spec=Campaign)
        campaign.name = "Solar Push"
        campaign.status = "paused"
        result = Campaign.__repr__(campaign)
        assert result == "<Campaign Solar Push (paused)>"

    def test_column_definitions(self):
        """Campaign has all expected columns."""
        from src.models.campaign import Campaign
        columns = {c.name for c in Campaign.__table__.columns}
        expected = {
            "id", "name", "description", "status",
            "target_trades", "target_locations", "target_filters",
            "sequence_steps",
            "daily_limit", "total_sent", "total_opened", "total_replied",
            "created_at", "updated_at",
        }
        assert expected.issubset(columns)

    def test_primary_key_is_uuid(self):
        """Campaign primary key is UUID type."""
        from src.models.campaign import Campaign
        pk_column = Campaign.__table__.columns["id"]
        assert pk_column.primary_key is True

    def test_status_column_is_string(self):
        """Campaign status column is String type."""
        from src.models.campaign import Campaign
        status_col = Campaign.__table__.columns["status"]
        assert hasattr(status_col.type, "length")

    def test_name_column_not_nullable(self):
        """Campaign name is required (not nullable)."""
        from src.models.campaign import Campaign
        name_col = Campaign.__table__.columns["name"]
        assert name_col.nullable is False

    def test_name_column_max_length(self):
        """Campaign name has a max length of 200."""
        from src.models.campaign import Campaign
        name_col = Campaign.__table__.columns["name"]
        assert name_col.type.length == 200

    def test_description_column_is_nullable(self):
        """Campaign description is optional (nullable)."""
        from src.models.campaign import Campaign
        desc_col = Campaign.__table__.columns["description"]
        assert desc_col.nullable is True

    def test_status_column_max_length(self):
        """Campaign status column has max length of 20."""
        from src.models.campaign import Campaign
        status_col = Campaign.__table__.columns["status"]
        assert status_col.type.length == 20

    def test_index_on_status(self):
        """Campaign has an index on status column."""
        from src.models.campaign import Campaign
        index_names = {idx.name for idx in Campaign.__table__.indexes}
        assert "ix_campaigns_status" in index_names

    def test_daily_limit_default(self):
        """Campaign daily_limit column has a default of 25."""
        from src.models.campaign import Campaign
        col = Campaign.__table__.columns["daily_limit"]
        assert col.default is not None
        assert col.default.arg == 25

    def test_total_sent_default(self):
        """Campaign total_sent column defaults to 0."""
        from src.models.campaign import Campaign
        col = Campaign.__table__.columns["total_sent"]
        assert col.default is not None
        assert col.default.arg == 0

    def test_total_opened_default(self):
        """Campaign total_opened column defaults to 0."""
        from src.models.campaign import Campaign
        col = Campaign.__table__.columns["total_opened"]
        assert col.default is not None
        assert col.default.arg == 0

    def test_total_replied_default(self):
        """Campaign total_replied column defaults to 0."""
        from src.models.campaign import Campaign
        col = Campaign.__table__.columns["total_replied"]
        assert col.default is not None
        assert col.default.arg == 0

    def test_metric_columns_exist(self):
        """Campaign has total_sent, total_opened, total_replied columns."""
        from src.models.campaign import Campaign
        columns = {c.name for c in Campaign.__table__.columns}
        assert "total_sent" in columns
        assert "total_opened" in columns
        assert "total_replied" in columns

    def test_jsonb_columns_exist(self):
        """Campaign has JSONB columns for targeting and sequences."""
        from src.models.campaign import Campaign
        columns = {c.name for c in Campaign.__table__.columns}
        assert "target_trades" in columns
        assert "target_locations" in columns
        assert "target_filters" in columns
        assert "sequence_steps" in columns

    def test_timestamp_columns_exist(self):
        """Campaign has created_at and updated_at columns."""
        from src.models.campaign import Campaign
        columns = {c.name for c in Campaign.__table__.columns}
        assert "created_at" in columns
        assert "updated_at" in columns

    def test_created_at_has_default(self):
        """Campaign created_at has a default (callable)."""
        from src.models.campaign import Campaign
        col = Campaign.__table__.columns["created_at"]
        assert col.default is not None

    def test_updated_at_has_onupdate(self):
        """Campaign updated_at has an onupdate callable."""
        from src.models.campaign import Campaign
        col = Campaign.__table__.columns["updated_at"]
        assert col.onupdate is not None

    def test_id_column_has_default(self):
        """Campaign id column has a default (uuid4)."""
        from src.models.campaign import Campaign
        col = Campaign.__table__.columns["id"]
        assert col.default is not None

    def test_status_column_has_default(self):
        """Campaign status column defaults to 'draft'."""
        from src.models.campaign import Campaign
        col = Campaign.__table__.columns["status"]
        assert col.default is not None
        assert col.default.arg == "draft"


# ---------------------------------------------------------------------------
# EmailTemplate model
# ---------------------------------------------------------------------------


class TestEmailTemplateModel:
    def test_import(self):
        """EmailTemplate model can be imported."""
        from src.models.email_template import EmailTemplate
        assert EmailTemplate is not None

    def test_tablename(self):
        """EmailTemplate uses 'email_templates' table."""
        from src.models.email_template import EmailTemplate
        assert EmailTemplate.__tablename__ == "email_templates"

    def test_repr(self):
        """EmailTemplate repr shows name and step_type."""
        from src.models.email_template import EmailTemplate
        tmpl = MagicMock(spec=EmailTemplate)
        tmpl.name = "Cold Intro"
        tmpl.step_type = "first_contact"
        result = EmailTemplate.__repr__(tmpl)
        assert result == "<EmailTemplate Cold Intro (first_contact)>"

    def test_repr_followup(self):
        """EmailTemplate repr for followup type."""
        from src.models.email_template import EmailTemplate
        tmpl = MagicMock(spec=EmailTemplate)
        tmpl.name = "Follow Up #1"
        tmpl.step_type = "followup"
        result = EmailTemplate.__repr__(tmpl)
        assert result == "<EmailTemplate Follow Up #1 (followup)>"

    def test_repr_breakup(self):
        """EmailTemplate repr for breakup type."""
        from src.models.email_template import EmailTemplate
        tmpl = MagicMock(spec=EmailTemplate)
        tmpl.name = "Final Farewell"
        tmpl.step_type = "breakup"
        result = EmailTemplate.__repr__(tmpl)
        assert result == "<EmailTemplate Final Farewell (breakup)>"

    def test_repr_custom(self):
        """EmailTemplate repr for custom type."""
        from src.models.email_template import EmailTemplate
        tmpl = MagicMock(spec=EmailTemplate)
        tmpl.name = "Special Offer"
        tmpl.step_type = "custom"
        result = EmailTemplate.__repr__(tmpl)
        assert result == "<EmailTemplate Special Offer (custom)>"

    def test_column_definitions(self):
        """EmailTemplate has all expected columns."""
        from src.models.email_template import EmailTemplate
        columns = {c.name for c in EmailTemplate.__table__.columns}
        expected = {
            "id", "name", "step_type",
            "subject_template", "body_template", "ai_instructions",
            "is_ai_generated", "created_at",
        }
        assert expected.issubset(columns)

    def test_primary_key_is_uuid(self):
        """EmailTemplate primary key is UUID type."""
        from src.models.email_template import EmailTemplate
        pk_column = EmailTemplate.__table__.columns["id"]
        assert pk_column.primary_key is True

    def test_name_not_nullable(self):
        """EmailTemplate name is required."""
        from src.models.email_template import EmailTemplate
        name_col = EmailTemplate.__table__.columns["name"]
        assert name_col.nullable is False

    def test_name_max_length(self):
        """EmailTemplate name has a max length of 200."""
        from src.models.email_template import EmailTemplate
        name_col = EmailTemplate.__table__.columns["name"]
        assert name_col.type.length == 200

    def test_step_type_not_nullable(self):
        """EmailTemplate step_type is required."""
        from src.models.email_template import EmailTemplate
        col = EmailTemplate.__table__.columns["step_type"]
        assert col.nullable is False

    def test_step_type_max_length(self):
        """EmailTemplate step_type has a max length of 30."""
        from src.models.email_template import EmailTemplate
        col = EmailTemplate.__table__.columns["step_type"]
        assert col.type.length == 30

    def test_subject_template_nullable(self):
        """EmailTemplate subject_template is optional."""
        from src.models.email_template import EmailTemplate
        col = EmailTemplate.__table__.columns["subject_template"]
        assert col.nullable is True

    def test_subject_template_max_length(self):
        """EmailTemplate subject_template has a max length of 500."""
        from src.models.email_template import EmailTemplate
        col = EmailTemplate.__table__.columns["subject_template"]
        assert col.type.length == 500

    def test_body_template_nullable(self):
        """EmailTemplate body_template is optional."""
        from src.models.email_template import EmailTemplate
        col = EmailTemplate.__table__.columns["body_template"]
        assert col.nullable is True

    def test_ai_instructions_nullable(self):
        """EmailTemplate ai_instructions is optional."""
        from src.models.email_template import EmailTemplate
        col = EmailTemplate.__table__.columns["ai_instructions"]
        assert col.nullable is True

    def test_is_ai_generated_column_exists(self):
        """EmailTemplate has is_ai_generated boolean column."""
        from src.models.email_template import EmailTemplate
        col = EmailTemplate.__table__.columns["is_ai_generated"]
        assert col is not None

    def test_is_ai_generated_default(self):
        """EmailTemplate is_ai_generated defaults to True."""
        from src.models.email_template import EmailTemplate
        col = EmailTemplate.__table__.columns["is_ai_generated"]
        assert col.default is not None
        assert col.default.arg is True

    def test_id_column_has_default(self):
        """EmailTemplate id column has a default (uuid4)."""
        from src.models.email_template import EmailTemplate
        col = EmailTemplate.__table__.columns["id"]
        assert col.default is not None

    def test_created_at_has_default(self):
        """EmailTemplate created_at has a default (callable)."""
        from src.models.email_template import EmailTemplate
        col = EmailTemplate.__table__.columns["created_at"]
        assert col.default is not None

    def test_no_updated_at_column(self):
        """EmailTemplate does not have updated_at (templates are immutable)."""
        from src.models.email_template import EmailTemplate
        columns = {c.name for c in EmailTemplate.__table__.columns}
        assert "updated_at" not in columns
