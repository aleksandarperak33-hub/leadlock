"""
Tests for email quality gate service.
Covers: subject length, body word count, personalization, forbidden words.
"""
import pytest

from src.services.email_quality_gate import check_email_quality


class TestSubjectLength:
    def test_short_subject_passes(self):
        result = check_email_quality(
            subject="Quick question for Mike",
            body_text="Hey Mike, " + "word " * 60 + "\nAlek",
            prospect_name="Mike",
        )
        assert result["passed"] is True

    def test_long_subject_fails(self):
        result = check_email_quality(
            subject="A" * 61,
            body_text="Hey Mike, " + "word " * 60 + "\nAlek",
            prospect_name="Mike",
        )
        assert result["passed"] is False
        assert any("Subject too long" in issue for issue in result["issues"])

    def test_exactly_60_chars_passes(self):
        result = check_email_quality(
            subject="A" * 60,
            body_text="Hey Mike, " + "word " * 60 + "\nAlek",
            prospect_name="Mike",
        )
        assert all("Subject too long" not in issue for issue in result["issues"])


class TestBodyWordCount:
    def test_too_short_body_fails(self):
        result = check_email_quality(
            subject="Hi Mike",
            body_text="Hey Mike, short email.",
            prospect_name="Mike",
        )
        assert result["passed"] is False
        assert any("Body too short" in issue for issue in result["issues"])

    def test_too_long_body_fails(self):
        result = check_email_quality(
            subject="Hi Mike",
            body_text="Hey Mike, " + "word " * 210 + "\nAlek",
            prospect_name="Mike",
        )
        assert result["passed"] is False
        assert any("Body too long" in issue for issue in result["issues"])

    def test_good_word_count_passes(self):
        result = check_email_quality(
            subject="Hi Mike",
            body_text="Hey Mike, " + "word " * 80 + "\nAlek",
            prospect_name="Mike",
        )
        word_issues = [i for i in result["issues"] if "Body too" in i]
        assert len(word_issues) == 0


class TestPersonalization:
    def test_body_with_prospect_name_passes(self):
        result = check_email_quality(
            subject="Hi",
            body_text="Hey Mike, " + "word " * 60 + "\nAlek",
            prospect_name="Mike",
            company_name="HVAC Pro",
        )
        assert all("doesn't mention" not in issue for issue in result["issues"])

    def test_body_with_company_name_passes(self):
        result = check_email_quality(
            subject="Hi",
            body_text="Hey there at HVAC Pro, " + "word " * 60 + "\nAlek",
            prospect_name="Someone",
            company_name="HVAC Pro",
        )
        assert all("doesn't mention" not in issue for issue in result["issues"])

    def test_body_without_either_name_fails(self):
        result = check_email_quality(
            subject="Hi",
            body_text="Hey there, " + "word " * 60 + "\nAlek",
            prospect_name="Mike",
            company_name="HVAC Pro",
        )
        assert any("doesn't mention" in issue for issue in result["issues"])

    def test_no_names_provided_skips_check(self):
        result = check_email_quality(
            subject="Hi",
            body_text="Hey there, " + "word " * 60 + "\nAlek",
        )
        assert all("doesn't mention" not in issue for issue in result["issues"])


class TestForbiddenWords:
    def test_game_changer_fails(self):
        result = check_email_quality(
            subject="Hi Mike",
            body_text="Hey Mike, this is a game-changer for your business. " + "word " * 55 + "\nAlek",
            prospect_name="Mike",
        )
        assert any("forbidden word" in issue for issue in result["issues"])

    def test_revolutionary_in_subject_fails(self):
        result = check_email_quality(
            subject="Revolutionary approach for Mike",
            body_text="Hey Mike, " + "word " * 60 + "\nAlek",
            prospect_name="Mike",
        )
        assert any("forbidden word" in issue for issue in result["issues"])

    def test_clean_email_passes(self):
        result = check_email_quality(
            subject="Saw your reviews, Mike",
            body_text="Hey Mike, your HVAC shop has great reviews. " + "word " * 55 + "\nAlek",
            prospect_name="Mike",
        )
        assert all("forbidden word" not in issue for issue in result["issues"])

    def test_transform_fails(self):
        result = check_email_quality(
            subject="Hi Mike",
            body_text="Hey Mike, we can transform your lead response. " + "word " * 55 + "\nAlek",
            prospect_name="Mike",
        )
        assert any("forbidden word" in issue for issue in result["issues"])

    def test_solution_fails(self):
        result = check_email_quality(
            subject="Hi Mike",
            body_text="Hey Mike, we have a solution for your HVAC business. " + "word " * 55 + "\nAlek",
            prospect_name="Mike",
        )
        assert any("forbidden word" in issue for issue in result["issues"])

    def test_platform_fails(self):
        result = check_email_quality(
            subject="Hi Mike",
            body_text="Hey Mike, our platform helps HVAC shops respond faster. " + "word " * 55 + "\nAlek",
            prospect_name="Mike",
        )
        assert any("forbidden word" in issue for issue in result["issues"])

    def test_i_noticed_fails(self):
        result = check_email_quality(
            subject="Hi Mike",
            body_text="Hey Mike, i noticed your HVAC shop in Austin. " + "word " * 55 + "\nAlek",
            prospect_name="Mike",
        )
        assert any("forbidden word" in issue for issue in result["issues"])

    def test_i_came_across_fails(self):
        result = check_email_quality(
            subject="Hi Mike",
            body_text="Hey Mike, i came across your website recently. " + "word " * 55 + "\nAlek",
            prospect_name="Mike",
        )
        assert any("forbidden word" in issue for issue in result["issues"])

    def test_pain_point_fails(self):
        result = check_email_quality(
            subject="Hi Mike",
            body_text="Hey Mike, slow response is a pain point for contractors. " + "word " * 55 + "\nAlek",
            prospect_name="Mike",
        )
        assert any("forbidden word" in issue for issue in result["issues"])


class TestOverallResult:
    def test_perfect_email_passes(self):
        result = check_email_quality(
            subject="Saw your 4.5 rating, Mike",
            body_text=(
                "Hey Mike,\n\n"
                "I work with a handful of HVAC shops in Austin and noticed your team "
                "has a solid 4.5 rating. Most contractors I talk to are losing "
                "$2,400 a month because they take too long to respond to leads. "
                "78% of homeowners go with the first contractor who calls back.\n\n"
                "How fast does your team usually get back to new leads?\n\n"
                "Alek"
            ),
            prospect_name="Mike",
            company_name="Cool Air HVAC",
        )
        assert result["passed"] is True
        assert result["issues"] == []

    def test_multiple_issues_collected(self):
        result = check_email_quality(
            subject="A" * 70,  # Too long
            body_text="Short.",  # Too short + no name
            prospect_name="Mike",
            company_name="HVAC Pro",
        )
        assert result["passed"] is False
        assert len(result["issues"]) >= 2


class TestAdvancedGuardrails:
    def test_subject_needs_personalization_token(self):
        result = check_email_quality(
            subject="Quick question",
            body_text="Hey Mike, " + "word " * 65 + "\nAlek",
            prospect_name="Mike",
            company_name="Cool Air HVAC",
            city="Austin",
            trade_type="hvac",
        )
        assert any("Subject lacks personalization" in issue for issue in result["issues"])

    def test_generic_hey_there_is_flagged(self):
        result = check_email_quality(
            subject="Question for Mike",
            body_text="Hey there, " + "word " * 65 + "\nAlek",
            prospect_name="Mike",
            company_name="Cool Air HVAC",
        )
        assert any("generic greeting" in issue.lower() for issue in result["issues"])
