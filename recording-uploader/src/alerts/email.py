"""
Email alerting via SMTP (TLS).

Sends a structured error email whenever a pipeline step fails.
Supports Gmail App Passwords and Office 365 SMTP relay.

Credentials:
    SMTP_USERNAME  — the SMTP login / from address
    SMTP_PASSWORD  — SMTP password or app-specific password
"""
import logging
import os
import smtplib
import traceback
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


class EmailAlerter:
    """
    Sends error alert emails.  Call send_error() from any pipeline step that
    raises an exception.

    Set alerts.enabled: false in config.yaml to silence all alerts (useful
    during local development).
    """

    def __init__(self, config: dict):
        self._enabled: bool = config.get("enabled", True)
        self._smtp_host: str = config["smtp_host"]
        self._smtp_port: int = config["smtp_port"]
        self._from_address: str = config["from_address"]
        self._to_addresses: list[str] = config["to_addresses"]
        self._subject_prefix: str = config.get("subject_prefix", "[RadioUploader]")
        self._username: str = os.environ["SMTP_USERNAME"]
        self._password: str = os.environ["SMTP_PASSWORD"]

    def send_error(self, step: str, filename: str, exc: Exception) -> None:
        """
        Send an alert email describing a pipeline failure.

        Args:
            step:     Name of the pipeline step that failed, e.g. "SHEETS_LOOKUP".
            filename: Audio filename being processed when the error occurred.
            exc:      The exception that was raised.
        """
        if not self._enabled:
            logger.debug("Alerts disabled — skipping email for %s / %s", step, filename)
            return

        subject = f"{self._subject_prefix} ERROR in {step} — {filename}"
        body = (
            f"Timestamp : {datetime.now(timezone.utc).isoformat()}\n"
            f"File      : {filename}\n"
            f"Step      : {step}\n"
            f"Error     : {type(exc).__name__}: {exc}\n"
            "\n"
            "Full traceback:\n"
            "---------------\n"
            f"{traceback.format_exc()}"
        )

        msg = MIMEMultipart()
        msg["From"] = self._from_address
        msg["To"] = ", ".join(self._to_addresses)
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        try:
            with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.login(self._username, self._password)
                server.sendmail(
                    self._from_address,
                    self._to_addresses,
                    msg.as_string(),
                )
            logger.info("Alert email sent for %s / %s", step, filename)
        except Exception as mail_exc:
            # Never let alert sending crash the main process.
            logger.error(
                "Failed to send alert email for %s / %s: %s", step, filename, mail_exc
            )
