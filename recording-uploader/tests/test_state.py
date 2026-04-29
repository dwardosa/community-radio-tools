"""
Unit tests for tracker.state — StateTracker and local_file_id helper.

All tests use an in-memory SQLite database (:memory:) so no files are created
on disk and tests are fully isolated from each other.
"""
import pytest

from tracker.state import StateTracker, local_file_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tracker(tmp_path):
    """A fresh StateTracker backed by a real (but temporary) SQLite DB."""
    db = tracker = StateTracker(str(tmp_path / "state.db"))
    yield tracker
    tracker.close()


# ---------------------------------------------------------------------------
# StateTracker.is_processed
# ---------------------------------------------------------------------------

class TestIsProcessed:
    def test_returns_false_for_unknown_file(self, tracker):
        # Arrange
        file_id = "local:/recordings/2026-04-28 14-30.mp3:1745843400"

        # Act
        result = tracker.is_processed(file_id)

        # Assert
        assert result is False

    def test_returns_true_after_marking_processed(self, tracker):
        # Arrange
        file_id = "local:/recordings/2026-04-28 14-30.mp3:1745843400"
        tracker.mark_processed(file_id, source="local", soundcloud_track_id="99")

        # Act
        result = tracker.is_processed(file_id)

        # Assert
        assert result is True

    def test_different_ids_are_independent(self, tracker):
        # Arrange
        id_a = "local:/recordings/2026-04-28 14-30.mp3:111"
        id_b = "local:/recordings/2026-04-28 15-30.mp3:222"
        tracker.mark_processed(id_a, source="local")

        # Act
        result_a = tracker.is_processed(id_a)
        result_b = tracker.is_processed(id_b)

        # Assert
        assert result_a is True
        assert result_b is False


# ---------------------------------------------------------------------------
# StateTracker.mark_processed
# ---------------------------------------------------------------------------

class TestMarkProcessed:
    def test_stores_soundcloud_track_id(self, tracker):
        # Arrange
        file_id = "drive:abc123"

        # Act
        tracker.mark_processed(file_id, source="drive", soundcloud_track_id="SC-456")

        # Assert
        row = tracker._conn.execute(
            "SELECT soundcloud_track_id FROM processed_files WHERE id = ?", (file_id,)
        ).fetchone()
        assert row is not None
        assert row[0] == "SC-456"

    def test_stores_source_label(self, tracker):
        # Arrange
        file_id = "drive:xyz789"

        # Act
        tracker.mark_processed(file_id, source="drive")

        # Assert
        row = tracker._conn.execute(
            "SELECT source FROM processed_files WHERE id = ?", (file_id,)
        ).fetchone()
        assert row[0] == "drive"

    def test_is_idempotent_on_duplicate_id(self, tracker):
        # Arrange
        file_id = "local:/recordings/2026-04-28 14-30.mp3:111"
        tracker.mark_processed(file_id, source="local", soundcloud_track_id="OLD")

        # Act — call again with a different track ID (should replace, not error)
        tracker.mark_processed(file_id, source="local", soundcloud_track_id="NEW")

        # Assert — only one row, with the latest track ID
        rows = tracker._conn.execute(
            "SELECT soundcloud_track_id FROM processed_files WHERE id = ?", (file_id,)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "NEW"

    def test_stores_without_track_id(self, tracker):
        # Arrange
        file_id = "local:/recordings/2026-04-28 14-30.mp3:333"

        # Act
        tracker.mark_processed(file_id, source="local")

        # Assert
        assert tracker.is_processed(file_id) is True


# ---------------------------------------------------------------------------
# local_file_id helper
# ---------------------------------------------------------------------------

class TestLocalFileId:
    def test_includes_local_prefix(self, tmp_path):
        # Arrange
        audio = tmp_path / "2026-04-28 14-30.mp3"
        audio.write_bytes(b"fake audio")

        # Act
        result = local_file_id(str(audio))

        # Assert
        assert result.startswith("local:")

    def test_includes_mtime_component(self, tmp_path):
        # Arrange
        audio = tmp_path / "2026-04-28 14-30.mp3"
        audio.write_bytes(b"fake audio")
        expected_mtime = int(audio.stat().st_mtime)

        # Act
        result = local_file_id(str(audio))

        # Assert
        assert str(expected_mtime) in result

    def test_two_files_with_different_mtime_produce_different_ids(self, tmp_path):
        # Arrange
        audio = tmp_path / "2026-04-28 14-30.mp3"
        audio.write_bytes(b"version one")
        id_v1 = local_file_id(str(audio))

        import time
        time.sleep(0.05)  # ensure mtime differs
        audio.write_bytes(b"version two")

        # Act
        id_v2 = local_file_id(str(audio))

        # Assert
        assert id_v1 != id_v2
