"""
Local folder collector.

Uses watchdog to receive real-time FileSystem events for new audio files.
Also exposes scan_existing() for catch-up on startup.
"""
import logging
import time
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger(__name__)

# Seconds to wait after a file creation event before processing,
# giving the OS time to finish writing the file.
_WRITE_SETTLE_SECONDS = 3


class _AudioHandler(FileSystemEventHandler):
    def __init__(self, extensions: list[str], callback):
        self._extensions = {e.lower() for e in extensions}
        self._callback = callback

    def _is_audio(self, path: str) -> bool:
        return Path(path).suffix.lower() in self._extensions

    def on_created(self, event):
        if not event.is_directory and self._is_audio(event.src_path):
            time.sleep(_WRITE_SETTLE_SECONDS)
            self._callback(event.src_path)

    def on_moved(self, event):
        # Handles files moved/renamed into the watched folder.
        if not event.is_directory and self._is_audio(event.dest_path):
            self._callback(event.dest_path)


class LocalCollector:
    """
    Watches a local folder for new audio files and calls callback(path)
    for each one.

    Usage:
        collector = LocalCollector(config["local"], on_new_file)
        for path in collector.scan_existing():
            on_new_file(str(path))
        collector.start()
        ...
        collector.stop()
    """

    def __init__(self, config: dict, callback):
        self._watch_folder = config["watch_folder"]
        self._extensions = config.get(
            "audio_extensions", [".mp3", ".wav", ".flac", ".m4a"]
        )
        self._callback = callback
        self._observer: Observer | None = None

    def scan_existing(self):
        """Yield Path objects for audio files already present in the folder."""
        folder = Path(self._watch_folder)
        for ext in self._extensions:
            yield from folder.glob(f"*{ext}")

    def start(self):
        handler = _AudioHandler(self._extensions, self._callback)
        self._observer = Observer()
        self._observer.schedule(handler, self._watch_folder, recursive=False)
        self._observer.start()
        logger.info("Watching local folder: %s", self._watch_folder)

    def stop(self):
        if self._observer:
            self._observer.stop()
            self._observer.join()
            logger.info("Local folder watcher stopped.")
