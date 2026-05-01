"""
Pipeline orchestrator.

Ties together all components:
    1. Collector    — detects new audio files (local or Google Drive)
    2. Sheets       — looks up show metadata by datetime parsed from filename
    3. Uploader     — posts audio + metadata to SoundCloud
    4. StateTracker — prevents duplicate uploads
    5. Alerter      — sends email on any step failure

Run via:
    python run.py
"""
import logging
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

from alerts.email import EmailAlerter
from collector.drive import DriveCollector
from collector.local import LocalCollector
from metadata.sheets import SheetsClient
from tracker.state import StateTracker, local_file_id
from uploader.soundcloud import SoundCloudUploader

_PROJECT_ROOT = Path(__file__).parent.parent

load_dotenv(dotenv_path=_PROJECT_ROOT / "config" / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


# ------------------------------------------------------------------
# Config loader
# ------------------------------------------------------------------

def load_config() -> dict:
    config_path = _PROJECT_ROOT / "config" / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def parse_datetime_from_filename(filename: str, fmt: str) -> datetime:
    """
    Strip the file extension and parse a datetime prefix from the stem using fmt.
    Tries the full stem first, then progressively shorter space-separated prefixes,
    to support stems like '20260427 1100 Recording'.
    Returns a UTC-aware datetime. Raises ValueError if parsing fails.
    """
    stem = Path(filename).stem
    parts = stem.split(" ")
    for i in range(len(parts), 0, -1):
        candidate = " ".join(parts[:i])
        try:
            dt = datetime.strptime(candidate, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime from '{stem}' using format '{fmt}'")


def download_image(url: str) -> str | None:
    """
    Download artwork from a URL to a temp file.
    Returns the temp file path, or None if the URL is empty or download fails.
    Caller must delete the file when done.
    """
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("Could not download artwork from '%s': %s", url, exc)
        return None

    ext = ".png" if "png" in resp.headers.get("Content-Type", "") else ".jpg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext, prefix="radio_art_")
    tmp.write(resp.content)
    tmp.close()
    return tmp.name


# ------------------------------------------------------------------
# Core pipeline step
# ------------------------------------------------------------------

def process_file(
    audio_path: str,
    filename: str,
    source_id: str,
    config: dict,
    state,
    sheets,
    uploader,
    alerter,
):
    """
    Run the full pipeline for a single audio file:
        parse datetime → sheet lookup → download artwork → upload → mark processed

    Failures at each step are caught, logged, and emailed. The function returns
    without raising so the event loop / watcher can continue with the next file.
    """
    logger.info("Processing: %s", filename)

    # 1. Parse datetime from filename
    try:
        target_dt = parse_datetime_from_filename(
            filename, config["filename"]["datetime_format"]
        )
    except Exception as exc:
        logger.error("Cannot parse datetime from '%s': %s", filename, exc)
        alerter.send_error("FILENAME_PARSE", filename, exc)
        return

    # 2. Google Sheets lookup
    try:
        meta = sheets.lookup_by_datetime(target_dt)
    except Exception as exc:
        logger.error("Sheets lookup failed for '%s': %s", filename, exc)
        alerter.send_error("SHEETS_LOOKUP", filename, exc)
        return

    # 3. Download artwork (non-fatal — download_image returns None on failure)
    artwork_path = download_image(meta.get("image_url", ""))

    # 4. SoundCloud upload
    try:
        track_id = uploader.upload(
            audio_path=audio_path,
            show_name=meta["show_name"],
            description=meta["description"],
            secondary_artist=meta["secondary_artist"],
            artwork_path=artwork_path,
        )
    except Exception as exc:
        logger.error("SoundCloud upload failed for '%s': %s", filename, exc)
        alerter.send_error("SOUNDCLOUD_UPLOAD", filename, exc)
        return
    finally:
        if artwork_path:
            Path(artwork_path).unlink(missing_ok=True)

    # 5. Mark as processed
    source_label = "drive" if source_id.startswith("drive:") else "local"
    state.mark_processed(source_id, source=source_label, soundcloud_track_id=track_id)
    logger.info("Finished '%s' → SoundCloud track ID %s", filename, track_id)


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def main():
    config = load_config()

    state = StateTracker(config["state"]["db_path"])
    alerter = EmailAlerter(config["alerts"])
    # Merge filename config into sheets config so tolerance is accessible.
    sheets = SheetsClient({**config["google_sheets"], **config["filename"]})
    uploader = SoundCloudUploader(config["soundcloud"])

    mode = config.get("source_mode", "local")
    logger.info("Starting radio-uploader in '%s' mode.", mode)

    try:
        if mode == "local":
            _run_local(config, state, sheets, uploader, alerter)
        elif mode == "drive":
            _run_drive(config, state, sheets, uploader, alerter)
        else:
            raise ValueError(f"Unknown source_mode '{mode}'. Expected 'local' or 'drive'.")
    finally:
        state.close()


def _run_local(config, state, sheets, uploader, alerter):
    def on_new_file(path: str):
        fid = local_file_id(path)
        if state.is_processed(fid):
            logger.debug("Already processed, skipping: %s", Path(path).name)
            return
        process_file(
            path, Path(path).name, fid, config, state, sheets, uploader, alerter
        )

    collector = LocalCollector(config["local"], on_new_file)

    # Catch up on files already in the folder, then watch for new ones.
    for existing_path in collector.scan_existing():
        on_new_file(str(existing_path))

    collector.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Interrupted — shutting down.")
    finally:
        collector.stop()


def _run_drive(config, state, sheets, uploader, alerter):
    collector: DriveCollector  # bound below; referenced inside the callback

    def on_drive_file(file_id: str, filename: str):
        source_id = f"drive:{file_id}"
        if state.is_processed(source_id):
            logger.debug("Already processed, skipping: %s", filename)
            return

        tmp_path = collector.download_file(file_id, filename)
        try:
            process_file(
                tmp_path, filename, source_id, config, state, sheets, uploader, alerter
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    collector = DriveCollector(config["drive"], on_drive_file, state)
    try:
        collector.run_polling_loop()
    except KeyboardInterrupt:
        logger.info("Interrupted — shutting down.")
    finally:
        collector.stop()


if __name__ == "__main__":
    main()
