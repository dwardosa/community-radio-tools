"""
Unit tests for metadata.sheets — SheetsClient.

The Google API client is fully mocked so no network calls or credentials
are needed. Only the logic inside SheetsClient is exercised.
"""
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# Patch heavy Google imports before the module is loaded.
_GOOGLE_PATCHES = [
    patch("google.oauth2.service_account.Credentials.from_service_account_file"),
    patch("googleapiclient.discovery.build"),
]


@pytest.fixture(autouse=True)
def stub_google_auth(monkeypatch):
    """Prevent any real Google auth/API calls across all tests in this file."""
    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", "fake/credentials.json")
    for p in _GOOGLE_PATCHES:
        p.start()
    yield
    for p in _GOOGLE_PATCHES:
        p.stop()


def _make_client(rows: list[list], tolerance_minutes: int = 5):
    """
    Build a SheetsClient whose internal _fetch_all_rows returns `rows`.
    `rows[0]` should be the header row.
    """
    from metadata.sheets import SheetsClient

    config = {
        "spreadsheet_id": "SHEET_ID",
        "sheet_name": "Sheet1",
        "match_tolerance_minutes": tolerance_minutes,
        "datetime_column": "datetime",
        "show_name_column": "show_name",
        "description_column": "description",
        "image_url_column": "image_url",
        "secondary_artist_column": "secondary_artist",
    }
    client = SheetsClient(config)
    client._fetch_all_rows = MagicMock(return_value=rows)
    return client


# ---------------------------------------------------------------------------
# _parse_row_datetime (static)
# ---------------------------------------------------------------------------

class TestParseRowDatetime:
    def _parse(self, value):
        from metadata.sheets import SheetsClient
        return SheetsClient._parse_row_datetime(value, row_num=2)

    def test_parses_iso_datetime_with_space(self):
        # Arrange
        value = "2026-04-28 14:30"

        # Act
        result = self._parse(value)

        # Assert
        assert result == datetime(2026, 4, 28, 14, 30, tzinfo=timezone.utc)

    def test_parses_iso_datetime_with_T_separator(self):
        # Arrange
        value = "2026-04-28T14:30:00"

        # Act
        result = self._parse(value)

        # Assert
        assert result == datetime(2026, 4, 28, 14, 30, 0, tzinfo=timezone.utc)

    def test_parses_uk_date_format(self):
        # Arrange
        value = "28/04/2026 14:30"

        # Act
        result = self._parse(value)

        # Assert
        assert result == datetime(2026, 4, 28, 14, 30, tzinfo=timezone.utc)

    def test_returns_none_for_unparseable_value(self):
        # Arrange
        value = "not-a-date"

        # Act
        result = self._parse(value)

        # Assert
        assert result is None

    def test_returns_none_for_empty_string(self):
        # Arrange
        value = ""

        # Act
        result = self._parse(value)

        # Assert
        assert result is None


# ---------------------------------------------------------------------------
# SheetsClient.lookup_by_datetime
# ---------------------------------------------------------------------------

_HEADERS = ["datetime", "show_name", "description", "image_url", "secondary_artist"]
_SHOW_ROW = [
    "2026-04-28 14:30",
    "The Morning Mix",
    "Weekly show with DJ Jane",
    "https://example.com/art.jpg",
    "DJ Jane",
]


class TestLookupByDatetime:
    def test_returns_metadata_for_exact_match(self):
        # Arrange
        client = _make_client([_HEADERS, _SHOW_ROW])
        target = datetime(2026, 4, 28, 14, 30, tzinfo=timezone.utc)

        # Act
        result = client.lookup_by_datetime(target)

        # Assert
        assert result["show_name"] == "The Morning Mix"
        assert result["description"] == "Weekly show with DJ Jane"
        assert result["image_url"] == "https://example.com/art.jpg"
        assert result["secondary_artist"] == "DJ Jane"

    def test_matches_within_tolerance(self):
        # Arrange — target is 3 minutes after sheet row, within 5-min tolerance
        client = _make_client([_HEADERS, _SHOW_ROW], tolerance_minutes=5)
        target = datetime(2026, 4, 28, 14, 33, tzinfo=timezone.utc)

        # Act
        result = client.lookup_by_datetime(target)

        # Assert
        assert result["show_name"] == "The Morning Mix"

    def test_raises_lookup_error_when_outside_tolerance(self):
        # Arrange — target is 10 minutes after sheet row, outside 5-min tolerance
        client = _make_client([_HEADERS, _SHOW_ROW], tolerance_minutes=5)
        target = datetime(2026, 4, 28, 14, 40, tzinfo=timezone.utc)

        # Act / Assert
        with pytest.raises(LookupError, match="No sheet row found"):
            client.lookup_by_datetime(target)

    def test_raises_value_error_when_sheet_is_empty(self):
        # Arrange
        client = _make_client([])
        target = datetime(2026, 4, 28, 14, 30, tzinfo=timezone.utc)

        # Act / Assert
        with pytest.raises(ValueError, match="no data"):
            client.lookup_by_datetime(target)

    def test_raises_value_error_when_required_column_missing(self):
        # Arrange — headers missing 'secondary_artist'
        bad_headers = ["datetime", "show_name", "description", "image_url"]
        bad_row = ["2026-04-28 14:30", "Show", "Desc", "http://img"]
        client = _make_client([bad_headers, bad_row])
        target = datetime(2026, 4, 28, 14, 30, tzinfo=timezone.utc)

        # Act / Assert
        with pytest.raises(ValueError, match="secondary_artist"):
            client.lookup_by_datetime(target)

    def test_picks_closest_row_when_multiple_rows_in_tolerance(self):
        # Arrange — two rows, both within 5 mins; second is closer
        row_far = ["2026-04-28 14:26", "Far Show", "Desc A", "", ""]
        row_close = ["2026-04-28 14:29", "Close Show", "Desc B", "", ""]
        client = _make_client([_HEADERS, row_far, row_close], tolerance_minutes=5)
        target = datetime(2026, 4, 28, 14, 30, tzinfo=timezone.utc)

        # Act
        result = client.lookup_by_datetime(target)

        # Assert
        assert result["show_name"] == "Close Show"

    def test_skips_rows_with_empty_datetime_cell(self):
        # Arrange — first data row has blank datetime, second is valid
        blank_row = ["", "Ghost Show", "Desc", "", ""]
        client = _make_client([_HEADERS, blank_row, _SHOW_ROW])
        target = datetime(2026, 4, 28, 14, 30, tzinfo=timezone.utc)

        # Act
        result = client.lookup_by_datetime(target)

        # Assert
        assert result["show_name"] == "The Morning Mix"

    def test_naive_target_datetime_is_treated_as_utc(self):
        # Arrange — pass a naive datetime (no tzinfo)
        client = _make_client([_HEADERS, _SHOW_ROW])
        naive_target = datetime(2026, 4, 28, 14, 30)  # no tzinfo

        # Act
        result = client.lookup_by_datetime(naive_target)

        # Assert — should still match without raising
        assert result["show_name"] == "The Morning Mix"
