# Tracklisting

A headless bot that streams a live radio station, identifies tracks using the Shazam API, and saves each new track to a CSV file tagged with the current show slot.

## How it works

1. **Stream** — `StreamReader` connects to the station's Icecast/Airtime HTTP audio stream and yields fixed-size MP3 chunks.
2. **Schedule** — `AirtimeSchedule` queries the Airtime live-info API to find the name of the currently broadcasting show.
3. **Recognise** — `Recognizer` converts each chunk to WAV and submits it to the Shazam API. Consecutive attempts are throttled by `recognition_interval_seconds`.
4. **Deduplicate** — if the same track is returned again, it is silently skipped so each song appears only once per play.
5. **Save** — newly identified tracks are appended immediately to `tracklist.csv` with the show name and a UTC timestamp.

## Requirements

- Python 3.11+
- [ffmpeg](https://ffmpeg.org/download.html) installed and on `PATH` (required by pydub for MP3 decoding)

Install Python dependencies:

```bash
cd tracklisting
pip install -r requirements.txt
```

## Configuration

Edit `config.yaml` before running:

| Key | Description | Default |
|---|---|---|
| `stream_url` | Icecast/Airtime audio stream URL | Netil Radio |
| `stream_info_url` | Airtime live-info API URL | Netil Radio |
| `recognition_chunk_bytes` | MP3 bytes to buffer before each attempt (~10 s at 128 kbps) | `163840` |
| `recognition_interval_seconds` | Minimum gap between attempts | `30` |
| `output_csv` | Output file path (relative to this directory) | `tracklist.csv` |

## Running the bot

```bash
cd tracklisting
python run.py
```

The bot runs indefinitely and reconnects automatically if the stream drops. Stop it with `Ctrl+C`.

## Output format

Each identified track is appended to `tracklist.csv`:

| Column | Description |
|---|---|
| `title` | Track title |
| `artist` | Artist name |
| `show_name` | Broadcast slot at time of identification |
| `identified_at` | ISO-8601 UTC timestamp |
| `shazam_url` | Shazam track page URL |
| `thumbnail_url` | Artwork URL from Shazam |

## Project structure

```
tracklisting/
├── run.py                  # Entry point
├── main.py                 # Pipeline orchestrator
├── config.yaml             # Configuration
├── definitions.py          # Shared path constants
├── schedule/
│   └── airtime.py          # Fetches current show from Airtime API
├── streamer/
│   └── streamer.py         # StreamReader — HTTP audio stream consumer
├── recognizer/
│   └── recognizer.py       # Recognizer — Shazam-based track identification
├── song/
│   └── song.py             # Song dataclass
└── util/
    └── csv_utils.py        # append_song_to_csv / read_songs_from_csv
```

> **Legacy GUI application** — `main_old.py` contains the original PySide6 desktop app for microphone/speaker-based recognition. It is no longer maintained. Additional dependencies (PySide6, PyAudio, numpy) are listed at the bottom of `requirements.txt` if you need to run it.

