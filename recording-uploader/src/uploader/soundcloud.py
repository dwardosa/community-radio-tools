"""
SoundCloud uploader.

Uses the SoundCloud REST API v2 with the Resource Owner Password Credentials
(ROPC) OAuth 2.0 flow — suitable for server-side automation where no browser
redirect is possible.

Credentials required in environment:
    SOUNDCLOUD_CLIENT_ID
    SOUNDCLOUD_CLIENT_SECRET
    SOUNDCLOUD_USERNAME
    SOUNDCLOUD_PASSWORD

Register an app and obtain credentials at:
    https://soundcloud.com/you/apps
"""
import logging
import os
from contextlib import ExitStack
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://api.soundcloud.com/oauth2/token"
_TRACKS_URL = "https://api.soundcloud.com/tracks"

# SoundCloud upload can be slow for large audio files.
_UPLOAD_TIMEOUT_SECONDS = 600


class SoundCloudUploader:
    """
    Authenticates with SoundCloud and uploads audio tracks with full metadata.

    A fresh OAuth token is fetched for every upload call to avoid expiry issues
    on long-running processes.
    """

    def __init__(self, config: dict):
        self._client_id = os.environ["SOUNDCLOUD_CLIENT_ID"]
        self._client_secret = os.environ["SOUNDCLOUD_CLIENT_SECRET"]
        self._username = os.environ["SOUNDCLOUD_USERNAME"]
        self._password = os.environ["SOUNDCLOUD_PASSWORD"]
        self._genre = config.get("genre", "Radio")
        self._sharing = config.get("sharing", "public")
        self._license = config.get("license", "all-rights-reserved")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upload(
        self,
        audio_path: str,
        show_name: str,
        description: str,
        secondary_artist: str,
        artwork_path: str | None = None,
    ) -> str:
        """
        Upload an audio file to SoundCloud with the provided metadata.

        Args:
            audio_path:        Absolute path to the audio file.
            show_name:         Track title (mapped from sheet show_name).
            description:       Track description (mapped from sheet description).
            secondary_artist:  Label/secondary artist name.
            artwork_path:      Optional absolute path to a JPEG/PNG artwork image.

        Returns:
            The SoundCloud track ID (as a string) of the newly created track.

        Raises:
            requests.HTTPError on API failure.
        """
        token = self._fetch_token()
        headers = {"Authorization": f"OAuth {token}"}
        data = {
            "track[title]": show_name,
            "track[description]": description,
            "track[label_name]": secondary_artist,
            "track[genre]": self._genre,
            "track[sharing]": self._sharing,
            "track[license]": self._license,
        }

        # ExitStack ensures every opened file handle is closed, even on error.
        with ExitStack() as stack:
            audio_handle = stack.enter_context(open(audio_path, "rb"))
            files = {
                "track[asset_data]": (
                    Path(audio_path).name,
                    audio_handle,
                    "application/octet-stream",
                ),
            }
            if artwork_path:
                artwork_handle = stack.enter_context(open(artwork_path, "rb"))
                mime = "image/png" if Path(artwork_path).suffix.lower() == ".png" else "image/jpeg"
                files["track[artwork_data]"] = (Path(artwork_path).name, artwork_handle, mime)

            logger.info("Uploading '%s' to SoundCloud …", show_name)
            resp = requests.post(
                _TRACKS_URL,
                headers=headers,
                files=files,
                data=data,
                timeout=_UPLOAD_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()

        track_id = str(resp.json()["id"])
        logger.info("Upload complete — SoundCloud track ID: %s", track_id)
        return track_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_token(self) -> str:
        """Request a fresh OAuth access token using ROPC flow."""
        resp = requests.post(
            _TOKEN_URL,
            data={
                "grant_type": "password",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "username": self._username,
                "password": self._password,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]
