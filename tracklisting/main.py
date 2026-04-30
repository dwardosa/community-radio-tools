
"""
Tracklisting bot pipeline.

Streams a live radio station, identifies tracks using the Shazam API, and
appends each newly identified track to a CSV file tagged with the current
show slot from the Airtime schedule.

Run via:
    python run.py
"""
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from definitions import CONFIG_PATH, ROOT_DIR
from recognizer import Recognizer
from schedule import AirtimeSchedule
from song import Song
from streamer import StreamReader
from util.csv_utils import append_song_to_csv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("tracklisting")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    config = load_config()

    reader = StreamReader(
        stream_url=config["stream_url"],
        chunk_bytes=config.get("recognition_chunk_bytes", 163840),
    )
    schedule = AirtimeSchedule(config["stream_info_url"])
    output_csv = str(Path(ROOT_DIR) / config.get("output_csv", "tracklist.csv"))
    min_interval = config.get("recognition_interval_seconds", 30)

    last_song: Song | None = None
    last_recognition_time = 0.0

    logger.info("Tracklisting bot started.")

    for audio_chunk in reader.iter_chunks():
        now = time.monotonic()
        if now - last_recognition_time < min_interval:
            continue

        last_recognition_time = now
        show_name = schedule.current_show_name()
        song = Recognizer.recognize(audio_chunk, show_name=show_name)

        if song is None:
            logger.info("Track not identified.")
            continue

        if last_song and song.title == last_song.title and song.artist == last_song.artist:
            logger.debug("Same track still playing: %s", song.full_title)
            continue

        song.identified_at = datetime.now(timezone.utc).isoformat()
        last_song = song

        logger.info("Identified: %s  —  Show: %s", song.full_title, show_name)
        append_song_to_csv(output_csv, song)


if __name__ == "__main__":
    main()
