"""
Track recognizer.

Converts a raw MP3 byte chunk to WAV and submits it to the Shazam API via the
ShazamAPI package. Returns a Song on success or None when the track cannot be
identified.
"""
import logging
from io import BytesIO

from pydub import AudioSegment
from ShazamAPI import Shazam

from song import Song

logger = logging.getLogger(__name__)


class Recognizer:
    @staticmethod
    def recognize(audio_bytes: bytes, show_name: str = "") -> Song | None:
        """
        Identify a track from raw MP3 audio bytes.

        Converts to WAV internally before querying Shazam.

        Args:
            audio_bytes: Raw MP3 bytes from the HTTP audio stream.
            show_name:   Name of the currently broadcasting show (for tagging).

        Returns:
            A Song instance on success, or None if recognition fails.
        """
        try:
            wav_bytes = _mp3_to_wav(audio_bytes)
            shazam = Shazam(wav_bytes)
            _, result = next(shazam.recognizeSong())

            if "track" not in result:
                return None

            track = result["track"]
            return Song(
                title=track["title"],
                artist=track["subtitle"],
                show_name=show_name,
                shazam_url=track.get("url"),
                thumbnail_url=track.get("share", {}).get("image"),
            )
        except StopIteration:
            return None
        except Exception as exc:
            logger.warning("Recognition error: %s", exc)
            return None


def _mp3_to_wav(mp3_bytes: bytes) -> bytes:
    """Convert MP3 bytes to WAV bytes for the Shazam API."""
    segment = AudioSegment.from_mp3(BytesIO(mp3_bytes))
    out = BytesIO()
    segment.export(out, format="wav")
    return out.getvalue()
