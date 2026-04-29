"""
Unit tests for uploader.soundcloud — SoundCloudUploader.

All HTTP calls are mocked via pytest-mock so no real network or
SoundCloud credentials are needed.
"""
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
    monkeypatch.setenv("SOUNDCLOUD_USERNAME", "test_user")
    monkeypatch.setenv("SOUNDCLOUD_PASSWORD", "test_pass")


@pytest.fixture
def uploader():
    config = {"genre": "Radio", "sharing": "public", "license": "all-rights-reserved"}
    return SoundCloudUploader(config)


def _mock_token_response(mocker, token: str = "fake_token"):
    """Return a mock that simulates a successful OAuth token response."""
    resp = mocker.MagicMock()
    resp.json.return_value = {"access_token": token}
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
    def test_posts_to_token_url_with_password_grant(self, uploader, mocker):
        # Arrange
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
        assert call_data[1]["data"]["grant_type"] == "password"
        assert token == "fake_token"

    def test_raises_on_http_error(self, uploader, mocker):
        # Arrange
        error_resp = mocker.MagicMock()
        error_resp.raise_for_status.side_effect = requests.HTTPError("401 Unauthorized")
        mocker.patch("uploader.soundcloud.requests.post", return_value=error_resp)

        # Act / Assert
        with pytest.raises(requests.HTTPError):
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
        assert data["track[label_name]"] == "DJ Jane"
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
