"""Unit tests for Drive change detection and Shared Drive support."""
from unittest.mock import MagicMock

import pytest

from collector.drive import DriveCollector


@pytest.fixture
def make_collector(mocker, monkeypatch):
    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", "fake/credentials.json")
    service = MagicMock()
    start_token_request = MagicMock()
    start_token_request.execute.return_value = {
        "startPageToken": "initial-token"
    }
    service.changes().getStartPageToken.return_value = start_token_request
    mocker.patch(
        "collector.drive.service_account.Credentials.from_service_account_file"
    )
    mocker.patch("collector.drive.build", return_value=service)

    def factory(config: dict):
        return DriveCollector(config, MagicMock(), MagicMock()), service

    return factory


def test_poll_changes_accepts_configured_extension_with_generic_mime_type(
    make_collector,
):
    # Arrange
    collector, service = make_collector(
        {
            "folder_id": "folder-123",
            "audio_extensions": [".mp3"],
        }
    )
    service.changes().list().execute.return_value = {
        "changes": [
            {
                "fileId": "file-123",
                "file": {
                    "id": "file-123",
                    "name": "Show.MP3",
                    "mimeType": "application/octet-stream",
                    "parents": ["folder-123"],
                },
            }
        ],
        "newStartPageToken": "next-token",
    }

    # Act
    result = collector._poll_changes()

    # Assert
    assert result == [
        {
            "id": "file-123",
            "name": "Show.MP3",
            "mimeType": "application/octet-stream",
            "parents": ["folder-123"],
        }
    ]
    assert collector._page_token == "next-token"


def test_shared_drive_requests_include_shared_drive_options(make_collector):
    # Arrange
    collector, service = make_collector(
        {
            "folder_id": "folder-123",
            "shared_drive_id": "shared-drive-123",
        }
    )
    service.changes().list().execute.return_value = {
        "changes": [],
        "newStartPageToken": "next-token",
    }

    # Act
    collector._poll_changes()

    # Assert
    service.changes().getStartPageToken.assert_called_once_with(
        supportsAllDrives=True,
        driveId="shared-drive-123",
    )
    change_options = service.changes().list.call_args.kwargs
    assert change_options["driveId"] == "shared-drive-123"
    assert change_options["supportsAllDrives"] is True
    assert change_options["includeItemsFromAllDrives"] is True


def test_list_existing_audio_accepts_configured_extension_with_generic_mime_type(
    make_collector,
):
    # Arrange
    collector, service = make_collector(
        {
            "folder_id": "folder-123",
            "audio_extensions": [".mp3"],
        }
    )
    service.files().list().execute.return_value = {
        "files": [
            {
                "id": "file-123",
                "name": "Show.MP3",
                "mimeType": "application/octet-stream",
            }
        ]
    }

    # Act
    result = list(collector._list_existing_audio())

    # Assert
    assert result == [
        {
            "id": "file-123",
            "name": "Show.MP3",
            "mimeType": "application/octet-stream",
        }
    ]


def test_poll_changes_ignores_unconfigured_file_extension(make_collector):
    # Arrange
    collector, service = make_collector(
        {
            "folder_id": "folder-123",
            "audio_extensions": [".mp3"],
        }
    )
    service.changes().list().execute.return_value = {
        "changes": [
            {
                "fileId": "file-123",
                "file": {
                    "id": "file-123",
                    "name": "not-a-show.txt",
                    "mimeType": "application/octet-stream",
                    "parents": ["folder-123"],
                },
            }
        ],
        "newStartPageToken": "next-token",
    }

    # Act
    result = collector._poll_changes()

    # Assert
    assert result == []


def test_poll_changes_stores_the_final_page_token_after_pagination(make_collector):
    # Arrange
    collector, service = make_collector({"folder_id": "folder-123"})
    changes_list = service.changes().list
    changes_list.return_value.execute.side_effect = [
        {"changes": [], "nextPageToken": "second-page"},
        {"changes": [], "newStartPageToken": "next-token"},
    ]

    # Act
    collector._poll_changes()

    # Assert
    assert collector._page_token == "next-token"
    assert changes_list.call_args_list[0].kwargs["pageToken"] == "initial-token"
    assert changes_list.call_args_list[1].kwargs["pageToken"] == "second-page"


def test_shared_drive_initial_scan_uses_shared_drive_corpus(make_collector):
    # Arrange
    collector, service = make_collector(
        {
            "folder_id": "folder-123",
            "shared_drive_id": "shared-drive-123",
        }
    )
    service.files().list().execute.return_value = {"files": []}

    # Act
    list(collector._list_existing_audio())

    # Assert
    list_options = service.files().list.call_args.kwargs
    assert list_options["corpora"] == "drive"
    assert list_options["driveId"] == "shared-drive-123"
    assert list_options["supportsAllDrives"] is True
    assert list_options["includeItemsFromAllDrives"] is True