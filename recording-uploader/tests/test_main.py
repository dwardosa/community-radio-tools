"""
Unit tests for main.py — parse_datetime_from_filename, download_image,
and the process_file orchestrator.

All external dependencies (Sheets, SoundCloud, alerter, state) are replaced
with MagicMocks so tests are fast and fully isolated.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

# main.py triggers load_dotenv at import time; suppress it.
with patch("dotenv.load_dotenv"):
    import main
    from main import (
        download_image,
        parse_datetime_from_filename,
        process_file,
    )


# ---------------------------------------------------------------------------
# Shared config fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def pipeline_config():
    return {
        "filename": {"datetime_format": "%Y-%m-%d %H-%M"},
        "google_sheets": {},
        "soundcloud": {},
        "alerts": {"enabled": False},
        "state": {"db_path": ":memory:"},
    }


# ---------------------------------------------------------------------------
# Helpers — shared mock factories
# ---------------------------------------------------------------------------

def _mock_state(already_processed: bool = False) -> MagicMock:
    state = MagicMock()
    state.is_processed.return_value = already_processed
    return state


def _mock_sheets(meta: dict | None = None) -> MagicMock:
    sheets = MagicMock()
    if meta is None:
        meta = {
            "show_name": "The Morning Mix",
            "description": "Weekly show",
            "image_url": "https://example.com/art.jpg",
            "secondary_artist": "DJ Jane",
        }
    sheets.lookup_by_datetime.return_value = meta
    return sheets


def _mock_uploader(track_id: str = "123456") -> MagicMock:
    uploader = MagicMock()
    uploader.upload.return_value = track_id
    return uploader


def _mock_alerter() -> MagicMock:
    return MagicMock()


# ---------------------------------------------------------------------------
# parse_datetime_from_filename
# ---------------------------------------------------------------------------

class TestParseDatetimeFromFilename:
    def test_parses_valid_filename_correctly(self):
        # Arrange
        filename = "2026-04-28 14-30.mp3"
        fmt = "%Y-%m-%d %H-%M"

        # Act
        result = parse_datetime_from_filename(filename, fmt)

        # Assert
        assert result == datetime(2026, 4, 28, 14, 30, tzinfo=timezone.utc)

    def test_result_is_utc_aware(self):
        # Arrange
        filename = "2026-04-28 14-30.mp3"
        fmt = "%Y-%m-%d %H-%M"

        # Act
        result = parse_datetime_from_filename(filename, fmt)

        # Assert
        assert result.tzinfo is not None
        assert result.tzinfo == timezone.utc

    def test_raises_value_error_for_wrong_format(self):
        # Arrange
        filename = "not-a-date.mp3"
        fmt = "%Y-%m-%d %H-%M"

        # Act / Assert
        with pytest.raises(ValueError):
            parse_datetime_from_filename(filename, fmt)

    def test_ignores_file_extension(self):
        # Arrange
        filename = "2026-04-28 14-30.wav"
        fmt = "%Y-%m-%d %H-%M"

        # Act
        result = parse_datetime_from_filename(filename, fmt)

        # Assert
        assert result.hour == 14
        assert result.minute == 30


# ---------------------------------------------------------------------------
# download_image
# ---------------------------------------------------------------------------

class TestDownloadImage:
    def test_returns_none_for_empty_url(self):
        # Arrange
        url = ""

        # Act
        result = download_image(url)

        # Assert
        assert result is None

    def test_returns_temp_file_path_on_success(self, mocker):
        # Arrange
        mock_resp = mocker.MagicMock()
        mock_resp.content = b"\xff\xd8\xff\xe0"  # minimal JPEG header
        mock_resp.headers = {"Content-Type": "image/jpeg"}
        mock_resp.raise_for_status.return_value = None
        mocker.patch("main.requests.get", return_value=mock_resp)

        # Act
        result = download_image("https://example.com/art.jpg")

        # Assert
        assert result is not None
        path = Path(result)
        assert path.exists()
        path.unlink()  # clean up

    def test_saves_png_with_correct_extension(self, mocker):
        # Arrange
        mock_resp = mocker.MagicMock()
        mock_resp.content = b"\x89PNG"
        mock_resp.headers = {"Content-Type": "image/png"}
        mock_resp.raise_for_status.return_value = None
        mocker.patch("main.requests.get", return_value=mock_resp)

        # Act
        result = download_image("https://example.com/art.png")

        # Assert
        assert result.endswith(".png")
        Path(result).unlink(missing_ok=True)

    def test_returns_none_on_http_error(self, mocker):
        # Arrange
        mock_resp = mocker.MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("404")
        mocker.patch("main.requests.get", return_value=mock_resp)

        # Act
        result = download_image("https://example.com/missing.jpg")

        # Assert
        assert result is None


# ---------------------------------------------------------------------------
# process_file — happy path
# ---------------------------------------------------------------------------

class TestProcessFileHappyPath:
    def test_calls_sheets_lookup_with_parsed_datetime(
        self, pipeline_config, tmp_path
    ):
        # Arrange
        audio = tmp_path / "2026-04-28 14-30.mp3"
        audio.write_bytes(b"audio")
        sheets = _mock_sheets()

        with patch("main.download_image", return_value=None):
            # Act
            process_file(
                str(audio), audio.name, "local:id:1",
                pipeline_config, _mock_state(), sheets,
                _mock_uploader(), _mock_alerter(),
            )

        # Assert
        sheets.lookup_by_datetime.assert_called_once_with(
            datetime(2026, 4, 28, 14, 30, tzinfo=timezone.utc)
        )

    def test_calls_uploader_with_sheet_metadata(self, pipeline_config, tmp_path):
        # Arrange
        audio = tmp_path / "2026-04-28 14-30.mp3"
        audio.write_bytes(b"audio")
        uploader = _mock_uploader()

        with patch("main.download_image", return_value=None):
            # Act
            process_file(
                str(audio), audio.name, "local:id:1",
                pipeline_config, _mock_state(), _mock_sheets(),
                uploader, _mock_alerter(),
            )

        # Assert
        uploader.upload.assert_called_once_with(
            audio_path=str(audio),
            show_name="The Morning Mix",
            description="Weekly show",
            secondary_artist="DJ Jane",
            artwork_path=None,
        )

    def test_marks_file_as_processed_after_upload(self, pipeline_config, tmp_path):
        # Arrange
        audio = tmp_path / "2026-04-28 14-30.mp3"
        audio.write_bytes(b"audio")
        state = _mock_state()

        with patch("main.download_image", return_value=None):
            # Act
            process_file(
                str(audio), audio.name, "local:id:1",
                pipeline_config, state, _mock_sheets(),
                _mock_uploader("SC-789"), _mock_alerter(),
            )

        # Assert
        state.mark_processed.assert_called_once_with(
            "local:id:1", source="local", soundcloud_track_id="SC-789"
        )


# ---------------------------------------------------------------------------
# process_file — error paths
# ---------------------------------------------------------------------------

class TestProcessFileErrors:
    def test_sends_alert_and_returns_early_on_bad_filename(
        self, pipeline_config, tmp_path
    ):
        # Arrange
        audio = tmp_path / "not-a-date.mp3"
        audio.write_bytes(b"audio")
        alerter = _mock_alerter()
        sheets = _mock_sheets()

        # Act
        process_file(
            str(audio), audio.name, "local:id:1",
            pipeline_config, _mock_state(), sheets,
            _mock_uploader(), alerter,
        )

        # Assert
        alerter.send_error.assert_called_once()
        assert alerter.send_error.call_args[0][0] == "FILENAME_PARSE"
        sheets.lookup_by_datetime.assert_not_called()

    def test_sends_alert_and_returns_early_on_sheets_failure(
        self, pipeline_config, tmp_path
    ):
        # Arrange
        audio = tmp_path / "2026-04-28 14-30.mp3"
        audio.write_bytes(b"audio")
        alerter = _mock_alerter()
        sheets = MagicMock()
        sheets.lookup_by_datetime.side_effect = LookupError("No row found")
        uploader = _mock_uploader()

        with patch("main.download_image", return_value=None):
            # Act
            process_file(
                str(audio), audio.name, "local:id:1",
                pipeline_config, _mock_state(), sheets,
                uploader, alerter,
            )

        # Assert
        alerter.send_error.assert_called_once()
        assert alerter.send_error.call_args[0][0] == "SHEETS_LOOKUP"
        uploader.upload.assert_not_called()

    def test_sends_alert_on_upload_failure_and_does_not_mark_processed(
        self, pipeline_config, tmp_path
    ):
        # Arrange
        audio = tmp_path / "2026-04-28 14-30.mp3"
        audio.write_bytes(b"audio")
        alerter = _mock_alerter()
        uploader = MagicMock()
        uploader.upload.side_effect = requests.HTTPError("500")
        state = _mock_state()

        with patch("main.download_image", return_value=None):
            # Act
            process_file(
                str(audio), audio.name, "local:id:1",
                pipeline_config, state, _mock_sheets(),
                uploader, alerter,
            )

        # Assert
        alerter.send_error.assert_called_once()
        assert alerter.send_error.call_args[0][0] == "SOUNDCLOUD_UPLOAD"
        state.mark_processed.assert_not_called()

    def test_continues_without_artwork_when_image_download_fails(
        self, pipeline_config, tmp_path
    ):
        # Arrange
        audio = tmp_path / "2026-04-28 14-30.mp3"
        audio.write_bytes(b"audio")
        uploader = _mock_uploader()

        with patch("main.download_image", return_value=None):
            # Act — no artwork available; upload should still be called
            process_file(
                str(audio), audio.name, "local:id:1",
                pipeline_config, _mock_state(), _mock_sheets(),
                uploader, _mock_alerter(),
            )

        # Assert
        uploader.upload.assert_called_once()
        assert uploader.upload.call_args[1]["artwork_path"] is None
