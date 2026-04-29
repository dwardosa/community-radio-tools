"""
Unit tests for alerts.email — EmailAlerter.

SMTP is fully mocked so no real mail server or credentials are needed.
"""
import smtplib
from unittest.mock import MagicMock, patch

import pytest

from alerts.email import EmailAlerter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_BASE_CONFIG = {
    "enabled": True,
    "smtp_host": "smtp.office365.com",
    "smtp_port": 587,
    "from_address": "alerts@station.com",
    "to_addresses": ["admin@station.com"],
    "subject_prefix": "[RadioUploader]",
}


@pytest.fixture(autouse=True)
def smtp_env(monkeypatch):
    monkeypatch.setenv("SMTP_USERNAME", "alerts@station.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")


@pytest.fixture
def alerter():
    return EmailAlerter(_BASE_CONFIG)


@pytest.fixture
def disabled_alerter():
    config = {**_BASE_CONFIG, "enabled": False}
    return EmailAlerter(config)


# ---------------------------------------------------------------------------
# EmailAlerter.send_error — when alerts are enabled
# ---------------------------------------------------------------------------

class TestSendErrorEnabled:
    def test_calls_smtp_sendmail(self, alerter, mocker):
        # Arrange
        mock_smtp = mocker.MagicMock()
        mocker.patch("alerts.email.smtplib.SMTP", return_value=mock_smtp)
        mock_smtp.__enter__ = mocker.MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = mocker.MagicMock(return_value=False)
        exc = ValueError("Sheet not found")

        # Act
        alerter.send_error("SHEETS_LOOKUP", "2026-04-28 14-30.mp3", exc)

        # Assert
        mock_smtp.sendmail.assert_called_once()

    def test_email_subject_contains_step_and_filename(self, alerter, mocker):
        # Arrange
        captured_messages = []

        def fake_sendmail(from_addr, to_addrs, msg_string):
            captured_messages.append(msg_string)

        mock_smtp = mocker.MagicMock()
        mock_smtp.sendmail.side_effect = fake_sendmail
        mock_smtp.__enter__ = mocker.MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = mocker.MagicMock(return_value=False)
        mocker.patch("alerts.email.smtplib.SMTP", return_value=mock_smtp)
        exc = RuntimeError("upload failed")

        # Act
        alerter.send_error("SOUNDCLOUD_UPLOAD", "2026-04-28 14-30.mp3", exc)

        # Assert
        subject_line = next(
            line for line in captured_messages[0].splitlines()
            if line.lower().startswith("subject:")
        )
        assert "SOUNDCLOUD_UPLOAD" in subject_line
        assert "2026-04-28 14-30.mp3" in subject_line
        assert "[RadioUploader]" in subject_line

    def test_email_body_contains_exception_details(self, alerter, mocker):
        # Arrange
        captured_messages = []

        def fake_sendmail(from_addr, to_addrs, msg_string):
            captured_messages.append(msg_string)

        mock_smtp = mocker.MagicMock()
        mock_smtp.sendmail.side_effect = fake_sendmail
        mock_smtp.__enter__ = mocker.MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = mocker.MagicMock(return_value=False)
        mocker.patch("alerts.email.smtplib.SMTP", return_value=mock_smtp)
        exc = LookupError("Row not found in sheet")

        # Act
        alerter.send_error("SHEETS_LOOKUP", "file.mp3", exc)

        # Assert
        full_message = captured_messages[0]
        assert "LookupError" in full_message
        assert "Row not found in sheet" in full_message

    def test_connects_to_configured_smtp_host_and_port(self, alerter, mocker):
        # Arrange
        mock_smtp_class = mocker.patch("alerts.email.smtplib.SMTP")
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)
        mock_smtp_class.return_value = mock_smtp

        # Act
        alerter.send_error("STEP", "file.mp3", Exception("err"))

        # Assert
        mock_smtp_class.assert_called_once_with(
            "smtp.office365.com", 587, timeout=30
        )

    def test_does_not_raise_if_smtp_connection_fails(self, alerter, mocker):
        # Arrange — SMTP raises, but send_error should swallow it
        mocker.patch(
            "alerts.email.smtplib.SMTP",
            side_effect=smtplib.SMTPConnectError(421, b"Service unavailable"),
        )

        # Act / Assert — must not propagate the SMTP error
        alerter.send_error("STEP", "file.mp3", Exception("original error"))


# ---------------------------------------------------------------------------
# EmailAlerter.send_error — when alerts are disabled
# ---------------------------------------------------------------------------

class TestSendErrorDisabled:
    def test_does_not_call_smtp_when_disabled(self, disabled_alerter, mocker):
        # Arrange
        mock_smtp_class = mocker.patch("alerts.email.smtplib.SMTP")

        # Act
        disabled_alerter.send_error("STEP", "file.mp3", Exception("err"))

        # Assert
        mock_smtp_class.assert_not_called()
