"""
SoundCloud uploader.

Uses the SoundCloud REST API v2 with OAuth 2.1 user authorization.
The uploader expects one of these token sources:

1. A pre-fetched access token in SOUNDCLOUD_ACCESS_TOKEN
2. A refresh token in SOUNDCLOUD_REFRESH_TOKEN
3. A one-time authorization code + PKCE verifier for first exchange:
   SOUNDCLOUD_AUTHORIZATION_CODE
   SOUNDCLOUD_CODE_VERIFIER
   SOUNDCLOUD_REDIRECT_URI

Register an app and obtain credentials at:
    https://soundcloud.com/you/apps
"""
import logging
import os
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile

import requests

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://secure.soundcloud.com/oauth/token"
_TRACKS_URL = "https://api.soundcloud.com/tracks"
_JSON_ACCEPT_HEADER = "application/json; charset=utf-8"

# SoundCloud upload can be slow for large audio files.
_UPLOAD_TIMEOUT_SECONDS = 600


@dataclass(frozen=True)
class UploadResult:
    """Identifiers returned by a successful SoundCloud upload."""

    track_id: str
    url: str


class SoundCloudUploader:
    """
    Authenticates with SoundCloud and uploads audio tracks with full metadata.

    Access tokens are reused until near expiry and refreshed with the
    SoundCloud OAuth token endpoint when possible.
    """

    def __init__(self, config: dict):
        self._client_id = os.environ["SOUNDCLOUD_CLIENT_ID"]
        self._client_secret = os.environ["SOUNDCLOUD_CLIENT_SECRET"]
        self._env_path = Path(__file__).resolve().parents[2] / "config" / ".env"
        self._access_token = os.environ.get("SOUNDCLOUD_ACCESS_TOKEN", "").strip()
        self._refresh_token = os.environ.get("SOUNDCLOUD_REFRESH_TOKEN", "").strip()
        self._authorization_code = os.environ.get("SOUNDCLOUD_AUTHORIZATION_CODE", "").strip()
        self._code_verifier = os.environ.get("SOUNDCLOUD_CODE_VERIFIER", "").strip()
        self._redirect_uri = os.environ.get("SOUNDCLOUD_REDIRECT_URI", "").strip()
        self._access_token_expires_at: datetime | None = None
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
    ) -> UploadResult:
        """
        Upload an audio file to SoundCloud with the provided metadata.

        Args:
            audio_path:        Absolute path to the audio file.
            show_name:         Track title (mapped from sheet show_name).
            description:       Track description (mapped from sheet description).
            secondary_artist:  Label/secondary artist name.
            artwork_path:      Optional absolute path to a JPEG/PNG artwork image.

        Returns:
            The new SoundCloud track ID and public permalink URL.

        Raises:
            requests.HTTPError on API failure.
        """
        token = self._fetch_token()
        headers = {
            "Authorization": f"OAuth {token}",
            "Accept": _JSON_ACCEPT_HEADER,
        }
        data = {
            "track[title]": show_name,
            "track[description]": description,
            "track[metadata_artist]": secondary_artist,
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
            try:
                resp = requests.post(
                    _TRACKS_URL,
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=_UPLOAD_TIMEOUT_SECONDS,
                )
            except requests.ConnectionError as exc:
                raise RuntimeError(
                    "SoundCloud closed the upload connection before sending a response. "
                    "Check whether the track was created before retrying; if not, rerun "
                    "the upload and inspect network/proxy issues."
                ) from exc
            resp.raise_for_status()

        result = resp.json()
        track_id = str(result["id"])
        track_url = result["permalink_url"]
        logger.info("Upload complete — SoundCloud track ID: %s", track_id)
        return UploadResult(track_id=track_id, url=track_url)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_token(self) -> str:
        """Return a valid OAuth access token for user-scoped upload requests."""
        if self._access_token and not self._is_access_token_stale():
            return self._access_token

        if self._refresh_token:
            return self._refresh_access_token()

        if self._authorization_code and self._code_verifier and self._redirect_uri:
            return self._exchange_authorization_code()

        raise RuntimeError(
            "Missing SoundCloud user token configuration. Set SOUNDCLOUD_REFRESH_TOKEN "
            "or provide SOUNDCLOUD_AUTHORIZATION_CODE, SOUNDCLOUD_CODE_VERIFIER, "
            "and SOUNDCLOUD_REDIRECT_URI."
        )

    def _is_access_token_stale(self) -> bool:
        if not self._access_token:
            return True
        if self._access_token_expires_at is None:
            return False
        return datetime.now(timezone.utc) >= self._access_token_expires_at

    def _exchange_authorization_code(self) -> str:
        """Exchange an authorization code and PKCE verifier for user tokens."""
        resp = requests.post(
            _TOKEN_URL,
            headers={"Accept": _JSON_ACCEPT_HEADER},
            data={
                "grant_type": "authorization_code",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uri": self._redirect_uri,
                "code_verifier": self._code_verifier,
                "code": self._authorization_code,
            },
            timeout=30,
        )
        resp.raise_for_status()
        self._store_token_response(resp.json())
        return self._access_token

    def _refresh_access_token(self) -> str:
        """Refresh an access token using the current refresh token."""
        resp = requests.post(
            _TOKEN_URL,
            headers={"Accept": _JSON_ACCEPT_HEADER},
            data={
                "grant_type": "refresh_token",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": self._refresh_token,
            },
            timeout=30,
        )
        resp.raise_for_status()
        self._store_token_response(resp.json())
        return self._access_token

    def _store_token_response(self, payload: dict) -> None:
        self._access_token = payload["access_token"]
        os.environ["SOUNDCLOUD_ACCESS_TOKEN"] = self._access_token

        refresh_token = payload.get("refresh_token", "").strip()
        if refresh_token:
            self._refresh_token = refresh_token
            os.environ["SOUNDCLOUD_REFRESH_TOKEN"] = refresh_token
            self._persist_refresh_token(refresh_token)

        expires_in = payload.get("expires_in")
        if expires_in is None:
            self._access_token_expires_at = None
            return

        self._access_token_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=max(int(expires_in) - 60, 0)
        )

    def _persist_refresh_token(self, refresh_token: str) -> None:
        try:
            existing = self._env_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            existing = ""

        lines = existing.splitlines()
        updated = False
        for index, line in enumerate(lines):
            if line.startswith("SOUNDCLOUD_REFRESH_TOKEN="):
                lines[index] = f"SOUNDCLOUD_REFRESH_TOKEN={refresh_token}"
                updated = True
                break

        if not updated:
            lines.append(f"SOUNDCLOUD_REFRESH_TOKEN={refresh_token}")

        new_content = "\n".join(lines)
        if existing.endswith("\n") or not new_content:
            new_content += "\n"

        self._env_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self._env_path.parent,
            delete=False,
        ) as handle:
            handle.write(new_content)
            temp_path = Path(handle.name)

        temp_path.replace(self._env_path)
