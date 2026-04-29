"""
Google Drive collector.

Uses the Drive Changes API (incremental page tokens) for efficient change
detection — avoids re-scanning the full folder on every poll.

Authentication: Google service account JSON key (GOOGLE_CREDENTIALS_PATH env var).
"""
import io
import logging
import os
import tempfile
import time
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# MIME types treated as audio files in Drive.
_AUDIO_MIME_TYPES = frozenset(
    [
        "audio/mpeg",
        "audio/wav",
        "audio/x-wav",
        "audio/flac",
        "audio/mp4",
        "audio/x-m4a",
        "audio/aac",
        "audio/ogg",
    ]
)


class DriveCollector:
    """
    Polls Google Drive for new audio files in a specific folder.

    On first run, processes all existing files in the folder.
    On subsequent polls, uses the Drive Changes API to find only new files.

    Usage:
        collector = DriveCollector(config["drive"], callback, state_tracker)
        collector.run_polling_loop()   # blocks; call stop() from another thread to exit
    """

    def __init__(self, config: dict, callback, state_tracker):
        self._folder_id = config["folder_id"]
        self._poll_interval = config.get("poll_interval_seconds", 60)
        self._callback = callback
        self._state = state_tracker
        self._running = False

        creds = service_account.Credentials.from_service_account_file(
            os.environ["GOOGLE_CREDENTIALS_PATH"], scopes=_SCOPES
        )
        self._service = build("drive", "v3", credentials=creds)
        self._page_token: str = self._fetch_start_token()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_polling_loop(self):
        """Block and continuously poll for new files. Call stop() to exit."""
        self._running = True

        # Process files already in the folder before entering the poll loop.
        logger.info("Scanning existing Drive files in folder %s …", self._folder_id)
        for file_meta in self._list_existing_audio():
            source_id = f"drive:{file_meta['id']}"
            if not self._state.is_processed(source_id):
                self._callback(file_meta["id"], file_meta["name"])

        logger.info(
            "Drive polling started (interval: %ds).", self._poll_interval
        )
        while self._running:
            time.sleep(self._poll_interval)
            for file_meta in self._poll_changes():
                source_id = f"drive:{file_meta['id']}"
                if not self._state.is_processed(source_id):
                    self._callback(file_meta["id"], file_meta["name"])

    def stop(self):
        self._running = False

    def download_file(self, file_id: str, filename: str) -> str:
        """
        Download a Drive file to a temporary local path.
        Caller is responsible for deleting the temp file when done.
        Returns the absolute path to the downloaded file.
        """
        request = self._service.files().get_media(fileId=file_id)
        suffix = Path(filename).suffix or ".mp3"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="radio_")
        try:
            downloader = MediaIoBaseDownload(tmp, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    logger.debug(
                        "Downloading %s: %d%%", filename, int(status.progress() * 100)
                    )
        finally:
            tmp.close()
        return tmp.name

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_start_token(self) -> str:
        return (
            self._service.changes()
            .getStartPageToken()
            .execute()["startPageToken"]
        )

    def _list_existing_audio(self):
        """List all audio files currently in the watched folder."""
        page_token = None
        while True:
            resp = (
                self._service.files()
                .list(
                    q=(
                        f"'{self._folder_id}' in parents"
                        " and trashed=false"
                    ),
                    fields="nextPageToken, files(id, name, mimeType)",
                    pageToken=page_token,
                )
                .execute()
            )
            for f in resp.get("files", []):
                if f.get("mimeType") in _AUDIO_MIME_TYPES:
                    yield f
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    def _poll_changes(self):
        """Return new audio files added since the last poll."""
        new_files = []
        page_token = self._page_token
        while page_token:
            resp = (
                self._service.changes()
                .list(
                    pageToken=page_token,
                    fields=(
                        "nextPageToken, newStartPageToken,"
                        " changes(fileId, file(id, name, mimeType, parents))"
                    ),
                    spaces="drive",
                )
                .execute()
            )
            for change in resp.get("changes", []):
                f = change.get("file") or {}
                if (
                    f.get("mimeType") in _AUDIO_MIME_TYPES
                    and self._folder_id in (f.get("parents") or [])
                ):
                    new_files.append(f)
            page_token = resp.get("nextPageToken")
            if "newStartPageToken" in resp:
                self._page_token = resp["newStartPageToken"]
        return new_files
