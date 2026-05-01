"""
Google Sheets metadata lookup.

Reads all rows from the configured sheet and finds the row whose
datetime column is within `match_tolerance_minutes` of the target datetime
parsed from the audio filename.

Authentication: Google service account JSON key (GOOGLE_CREDENTIALS_PATH env var).
"""
import logging
import os
from datetime import datetime, timedelta, timezone

from google.oauth2 import service_account
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


class SheetsClient:
    """
    Looks up show metadata from a Google Sheet by matching a datetime value.

    Expected sheet columns (names configurable in config.yaml):
        datetime | show_name | description | image_url | secondary_artist

    The datetime column should contain ISO-8601 strings, e.g. "2026-04-28 14:30".
    """

    def __init__(self, config: dict):
        self._spreadsheet_id: str = config["spreadsheet_id"]
        self._sheet_name: str = config["sheet_name"]
        self._tolerance = timedelta(
            minutes=config.get("match_tolerance_minutes", 5)
        )
        # Column name mappings
        self._col_datetime: str = config["datetime_column"]
        self._col_show_name: str = config["show_name_column"]
        self._col_description: str = config["description_column"]
        self._col_image_url: str = config["image_url_column"]
        self._col_secondary_artist: str = config["secondary_artist_column"]

        creds = service_account.Credentials.from_service_account_file(
            os.environ["GOOGLE_CREDENTIALS_PATH"], scopes=_SCOPES
        )
        self._service = build("sheets", "v4", credentials=creds)

    def lookup_by_datetime(self, target_dt: datetime) -> dict:
        """
        Find the sheet row whose datetime column is within tolerance of target_dt.

        Returns a dict with keys:
            show_name, description, image_url, secondary_artist

        Raises:
            LookupError  — no matching row found within the tolerance window.
            ValueError   — sheet is empty or a required column is missing.
        """
        if target_dt.tzinfo is None:
            target_dt = target_dt.replace(tzinfo=timezone.utc)

        values = self._fetch_all_rows()
        if not values:
            raise ValueError("Google Sheet returned no data.")

        headers = [h.strip().lower() for h in values[0]]

        def col_idx(col_name: str) -> int:
            key = col_name.strip().lower()
            try:
                return headers.index(key)
            except ValueError:
                raise ValueError(
                    f"Column '{col_name}' not found in sheet. "
                    f"Available columns: {headers}"
                )

        dt_idx = col_idx(self._col_datetime)
        show_idx = col_idx(self._col_show_name)
        desc_idx = col_idx(self._col_description)
        img_idx = col_idx(self._col_image_url)
        artist_idx = col_idx(self._col_secondary_artist)

        best_match = None
        best_delta = None

        for row_num, row in enumerate(values[1:], start=2):
            if len(row) <= dt_idx or not row[dt_idx]:
                continue
            row_dt = self._parse_row_datetime(row[dt_idx], row_num)
            if row_dt is None:
                continue
            delta = abs(row_dt - target_dt)
            if delta <= self._tolerance:
                if best_delta is None or delta < best_delta:
                    best_match = row
                    best_delta = delta

        if best_match is None:
            raise LookupError(
                f"No sheet row found within {self._tolerance} of "
                f"{target_dt.isoformat()}. "
                "Check the datetime column format and tolerance setting."
            )

        def safe_get(row, idx):
            return row[idx].strip() if len(row) > idx else ""

        result = {
            "show_name": safe_get(best_match, show_idx),
            "description": safe_get(best_match, desc_idx),
            "image_url": safe_get(best_match, img_idx),
            "secondary_artist": safe_get(best_match, artist_idx),
        }
        logger.info(
            "Matched sheet row for %s → show: '%s'",
            target_dt.isoformat(),
            result["show_name"],
        )
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_all_rows(self) -> list[list]:
        result = (
            self._service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self._spreadsheet_id,
                range=self._sheet_name,
            )
            .execute()
        )
        return result.get("values", [])

    @staticmethod
    def _parse_row_datetime(value: str, row_num: int) -> datetime | None:
        """
        Attempt to parse an ISO-8601 or common datetime string.
        Returns None (with a warning) if unparseable.
        """
        # Try ISO format first (handles both "2026-04-28T14:30" and "2026-04-28 14:30")
        for fmt in (
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d/%m/%Y %H:%M",
        ):
            try:
                dt = datetime.strptime(value.strip(), fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        logger.warning("Row %d: cannot parse datetime value '%s' — skipping.", row_num, value)
        return None
