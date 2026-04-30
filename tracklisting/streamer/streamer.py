"""
HTTP audio stream reader.

Connects to an Icecast/Airtime stream URL and yields fixed-size byte chunks
of raw audio (MP3). Reconnects automatically on transient network errors so
the tracklisting bot can run indefinitely.
"""
import logging

import requests

logger = logging.getLogger(__name__)

_HTTP_READ_SIZE = 4096  # bytes per iter_content call


class StreamReader:
    """Consumes an HTTP audio stream and yields fixed-size MP3 byte chunks."""

    def __init__(self, stream_url: str, chunk_bytes: int = 163840):
        """
        Args:
            stream_url:  URL of the HTTP audio stream.
            chunk_bytes: Bytes to accumulate before yielding each chunk.
                         At 128 kbps, 163840 bytes ≈ 10 seconds of audio.
        """
        self._stream_url = stream_url
        self._chunk_bytes = chunk_bytes

    def iter_chunks(self):
        """
        Yield audio chunks as bytes indefinitely.

        Reconnects on any network error so callers do not need to handle
        connection failures themselves.
        """
        while True:
            try:
                yield from self._stream_once()
            except Exception as exc:
                logger.warning("Stream interrupted (%s), reconnecting…", exc)

    def _stream_once(self):
        with requests.get(self._stream_url, stream=True, timeout=30) as response:
            response.raise_for_status()
            logger.info("Connected to stream: %s", self._stream_url)
            buffer = b""
            for raw_chunk in response.iter_content(_HTTP_READ_SIZE):
                buffer += raw_chunk
                if len(buffer) >= self._chunk_bytes:
                    yield buffer[: self._chunk_bytes]
                    buffer = buffer[self._chunk_bytes :]
