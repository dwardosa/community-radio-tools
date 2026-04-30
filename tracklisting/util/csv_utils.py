"""
CSV utilities for the tracklisting bot.

Provides append-on-write access so identified tracks are persisted
immediately rather than held in memory until the process exits.
"""
import csv
from pathlib import Path

from song import Song

_FIELDS = ["title", "artist", "show_name", "identified_at", "shazam_url", "thumbnail_url"]


def append_song_to_csv(path: str, song: Song) -> None:
    """
    Append a single song to the CSV at *path*.

    A header row is written automatically when the file does not yet exist.
    """
    write_header = not Path(path).exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow({
            "title": song.title,
            "artist": song.artist,
            "show_name": song.show_name,
            "identified_at": song.identified_at,
            "shazam_url": song.shazam_url or "",
            "thumbnail_url": song.thumbnail_url or "",
        })


def read_songs_from_csv(path: str) -> list[Song]:
    """Read all songs from a CSV file and return them as a list of Song objects."""
    songs = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            songs.append(Song(
                title=row["title"],
                artist=row["artist"],
                show_name=row.get("show_name", ""),
                identified_at=row.get("identified_at", ""),
                shazam_url=row.get("shazam_url") or None,
                thumbnail_url=row.get("thumbnail_url") or None,
            ))
    return songs
