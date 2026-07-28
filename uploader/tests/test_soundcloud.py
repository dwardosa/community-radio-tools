"""
Unit tests for uploader.soundcloud — SoundCloudUploader.

All HTTP calls are mocked via pytest-mock so no real network or
SoundCloud credentials are needed.
"""
from datetime import datetime, timedelta, timezone

import pytest
import requests

from uploader.soundcloud import SoundCloudUploader, _TOKEN_URL, _TRACKS_URL


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def soundcloud_env(monkeypatch):
    """Inject dummy SoundCloud credentials into the environment."""
    monkeypatch.setenv("SOUNDCLOUD_CLIENT_ID", "test_client_id")
    monkeypatch.setenv("SOUNDCLOUD_CLIENT_SECRET", "test_client_secret")
    monkeypatch.delenv("SOUNDCLOUD_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("SOUNDCLOUD_REFRESH_TOKEN", raising=False)
    monkeypatch.delenv("SOUNDCLOUD_AUTHORIZATION_CODE", raising=False)
    monkeypatch.delenv("SOUNDCLOUD_CODE_VERIFIER", raising=False)
    monkeypatch.delenv("SOUNDCLOUD_REDIRECT_URI", raising=False)


@pytest.fixture
def uploader():
    config = {"genre": "Radio", "sharing": "public", "license": "all-rights-reserved"}
    instance = SoundCloudUploader(config)
    instance._refresh_token = "refresh_token"
    return instance


def _mock_token_response(mocker, token: str = "fake_token"):
    """Return a mock that simulates a successful OAuth token response."""
    resp = mocker.MagicMock()
    resp.json.return_value = {
        "access_token": token,
        "refresh_token": "new_refresh_token",
        "expires_in": 3600,
    }
    resp.raise_for_status.return_value = None
    return resp


def _mock_upload_response(mocker, track_id: str = "987654"):
    """Return a mock that simulates a successful SoundCloud track upload."""
    resp = mocker.MagicMock()
    resp.json.return_value = {"id": int(track_id)}
    resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# _fetch_token
# ---------------------------------------------------------------------------

class TestFetchToken:
    def test_returns_existing_access_token_when_present(self, uploader, monkeypatch):
        # Arrange
        monkeypatch.setenv("SOUNDCLOUD_ACCESS_TOKEN", "cached_token")
        uploader = SoundCloudUploader({"genre": "Radio", "sharing": "public", "license": "all-rights-reserved"})

        # Act
        token = uploader._fetch_token()

        # Assert
        assert token == "cached_token"

    def test_posts_to_token_url_with_authorization_code_grant(self, mocker, monkeypatch):
        # Arrange
        monkeypatch.setenv("SOUNDCLOUD_AUTHORIZATION_CODE", "auth_code")
        monkeypatch.setenv("SOUNDCLOUD_CODE_VERIFIER", "code_verifier")
        monkeypatch.setenv("SOUNDCLOUD_REDIRECT_URI", "https://example.com/callback")
        uploader = SoundCloudUploader({"genre": "Radio", "sharing": "public", "license": "all-rights-reserved"})

        mock_post = mocker.patch(
            "uploader.soundcloud.requests.post",
            return_value=_mock_token_response(mocker),
        )

        # Act
        token = uploader._fetch_token()

        # Assert
        mock_post.assert_called_once()
        call_data = mock_post.call_args
        assert call_data[0][0] == _TOKEN_URL
        assert call_data[1]["data"]["grant_type"] == "authorization_code"
        assert call_data[1]["data"]["code"] == "auth_code"
        assert token == "fake_token"

    def test_refreshes_when_access_token_is_stale(self, uploader, mocker, monkeypatch):
        # Arrange
        monkeypatch.setenv("SOUNDCLOUD_REFRESH_TOKEN", "refresh_token")
        uploader = SoundCloudUploader({"genre": "Radio", "sharing": "public", "license": "all-rights-reserved"})
        uploader._access_token = "stale_token"
        uploader._access_token_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

        mock_post = mocker.patch(
            "uploader.soundcloud.requests.post",
            return_value=_mock_token_response(mocker, "refreshed_token"),
        )

        # Act
        token = uploader._fetch_token()

        # Assert
        assert token == "refreshed_token"
        assert mock_post.call_args[1]["data"]["grant_type"] == "refresh_token"

    def test_persists_rotated_refresh_token_to_env_file(self, uploader, mocker, tmp_path):
        # Arrange
        env_file = tmp_path / ".env"
        env_file.write_text(
            "SOUNDCLOUD_CLIENT_ID=test_client_id\n"
            "SOUNDCLOUD_CLIENT_SECRET=test_client_secret\n"
            "SOUNDCLOUD_REFRESH_TOKEN=old_refresh_token\n",
            encoding="utf-8",
        )
        uploader._env_path = env_file

        mocker.patch(
            "uploader.soundcloud.requests.post",
            return_value=_mock_token_response(mocker, "refreshed_token"),
        )

        # Act
        token = uploader._refresh_access_token()

        # Assert
        assert token == "refreshed_token"
        assert uploader._refresh_token == "new_refresh_token"
        assert "SOUNDCLOUD_REFRESH_TOKEN=new_refresh_token" in env_file.read_text(encoding="utf-8")

    def test_raises_on_http_error(self, uploader, mocker):
        # Arrange
        error_resp = mocker.MagicMock()
        error_resp.raise_for_status.side_effect = requests.HTTPError("401 Unauthorized")
        mocker.patch("uploader.soundcloud.requests.post", return_value=error_resp)
        uploader._refresh_token = "refresh_token"

        # Act / Assert
        with pytest.raises(requests.HTTPError):
            uploader._fetch_token()

    def test_raises_when_no_user_token_source_is_configured(self, uploader):
        uploader._refresh_token = ""
        # Act / Assert
        with pytest.raises(RuntimeError, match="Missing SoundCloud user token configuration"):
            uploader._fetch_token()


# ---------------------------------------------------------------------------
# SoundCloudUploader.upload
# ---------------------------------------------------------------------------

class TestUpload:
    def test_returns_track_id_on_success(self, uploader, mocker, tmp_path):
        # Arrange
        audio_file = tmp_path / "2026-04-28 14-30.mp3"
        audio_file.write_bytes(b"fake audio data")

        mock_post = mocker.patch(
            "uploader.soundcloud.requests.post",
            side_effect=[
                _mock_token_response(mocker, "tok123"),
                _mock_upload_response(mocker, "987654"),
            ],
        )

        # Act
        track_id = uploader.upload(
            audio_path=str(audio_file),
            show_name="The Morning Mix",
            description="Weekly show",
            secondary_artist="DJ Jane",
        )

        # Assert
        assert track_id == "987654"

    def test_includes_metadata_fields_in_upload_payload(self, uploader, mocker, tmp_path):
        # Arrange
        audio_file = tmp_path / "2026-04-28 14-30.mp3"
        audio_file.write_bytes(b"fake audio data")

        mock_post = mocker.patch(
            "uploader.soundcloud.requests.post",
            side_effect=[
                _mock_token_response(mocker),
                _mock_upload_response(mocker),
            ],
        )

        # Act
        uploader.upload(
            audio_path=str(audio_file),
            show_name="The Morning Mix",
            description="Weekly show",
            secondary_artist="DJ Jane",
        )

        # Assert — second call is the track upload
        upload_call = mock_post.call_args_list[1]
        data = upload_call[1]["data"]
        assert data["track[title]"] == "The Morning Mix"
        assert data["track[description]"] == "Weekly show"
        assert data["track[artist]"] == "DJ Jane"
        assert data["track[genre]"] == "Radio"
        assert data["track[sharing]"] == "public"

    def test_includes_artwork_in_upload_when_provided(self, uploader, mocker, tmp_path):
        # Arrange
        audio_file = tmp_path / "2026-04-28 14-30.mp3"
        audio_file.write_bytes(b"fake audio data")
        artwork_file = tmp_path / "cover.jpg"
        artwork_file.write_bytes(b"fake image data")

        mock_post = mocker.patch(
            "uploader.soundcloud.requests.post",
            side_effect=[
                _mock_token_response(mocker),
                _mock_upload_response(mocker),
            ],
        )

        # Act
        uploader.upload(
            audio_path=str(audio_file),
            show_name="Show",
            description="Desc",
            secondary_artist="Artist",
            artwork_path=str(artwork_file),
        )

        # Assert — artwork file key is present in the multipart payload
        upload_call = mock_post.call_args_list[1]
        files = upload_call[1]["files"]
        assert "track[artwork_data]" in files

    def test_raises_on_upload_http_error(self, uploader, mocker, tmp_path):
        # Arrange
        audio_file = tmp_path / "2026-04-28 14-30.mp3"
        audio_file.write_bytes(b"fake audio data")

        error_resp = mocker.MagicMock()
        error_resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")

        mocker.patch(
            "uploader.soundcloud.requests.post",
            side_effect=[
                _mock_token_response(mocker),
                error_resp,
            ],
        )

        # Act / Assert
        with pytest.raises(requests.HTTPError):
            uploader.upload(
                audio_path=str(audio_file),
                show_name="Show",
                description="Desc",
                secondary_artist="Artist",
            )

    def test_uses_bearer_token_in_upload_header(self, uploader, mocker, tmp_path):
        # Arrange
        audio_file = tmp_path / "2026-04-28 14-30.mp3"
        audio_file.write_bytes(b"fake audio data")

        mock_post = mocker.patch(
            "uploader.soundcloud.requests.post",
            side_effect=[
                _mock_token_response(mocker, "mytoken"),
                _mock_upload_response(mocker),
            ],
        )

        # Act
        uploader.upload(
            audio_path=str(audio_file),
            show_name="Show",
            description="Desc",
            secondary_artist="Artist",
        )

        # Assert
        upload_call = mock_post.call_args_list[1]
        headers = upload_call[1]["headers"]
        assert headers["Authorization"] == "OAuth mytoken"
        assert headers["Accept"] == "application/json; charset=utf-8"

    def test_surfaces_connection_abort_with_retry_guidance(self, uploader, mocker, tmp_path):
        # Arrange
        audio_file = tmp_path / "2026-04-28 14-30.mp3"
        audio_file.write_bytes(b"fake audio data")

        mocker.patch(
            "uploader.soundcloud.requests.post",
            side_effect=[
                _mock_token_response(mocker, "tok123"),
                requests.ConnectionError("Connection aborted."),
            ],
        )

        # Act / Assert
        with pytest.raises(RuntimeError, match="closed the upload connection"):
            uploader.upload(
                audio_path=str(audio_file),
                show_name="Show",
                description="Desc",
                secondary_artist="Artist",
            )
