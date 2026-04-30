# Community Radio Tools

A toolbox built to assist the running of community radio stations with tasks such as automated track uploading, scheduling, and track listing.

## Tracklisting

`tracklisting` is a headless Python bot that streams a live radio station, identifies tracks in real time using the Shazam API, and saves them to a CSV file grouped by show slot.

It connects to an Icecast/Airtime audio stream, queries the Airtime schedule API to determine the current show, and appends each newly identified track (title, artist, show name, UTC timestamp, Shazam URL) to `tracklist.csv`. Duplicate detections are suppressed so each song appears once per play.

See [tracklisting/README.md](tracklisting/README.md) for full setup and configuration details.


## Recording Uploader

`recording-uploader` is a Python automation tool for publishing recorded shows to SoundCloud. It watches a local folder or polls a Google Drive folder for new audio files, matches each file to show metadata in Google Sheets, uploads the track to SoundCloud, records the upload in a local state database to avoid duplicates, and sends email alerts if any stage fails.

### How it works

The uploader expects each audio filename to contain a broadcast date and time, for example `2026-04-28 14-30.mp3`. That timestamp is parsed using the format defined in `recording-uploader/config/config.yaml`, then matched against a row in a Google Sheet within a configurable tolerance window. The matched row supplies the show title, description, artwork URL, and secondary artist metadata used for the SoundCloud upload.

### Requirements

- Python 3.11+
- A SoundCloud app and account credentials
- A Google service account with read access to the target Google Sheet
- SMTP credentials if email alerts are enabled

Install dependencies from the tool directory:

```bash
cd recording-uploader
pip install -r requirements.txt
```

### Configuration

1. Copy `recording-uploader/config/.env.example` to `recording-uploader/config/.env`.
2. Set the environment values for:
	- `GOOGLE_CREDENTIALS_PATH`
	- `SOUNDCLOUD_CLIENT_ID`
	- `SOUNDCLOUD_CLIENT_SECRET`
	- `SOUNDCLOUD_USERNAME`
	- `SOUNDCLOUD_PASSWORD`
	- `SMTP_USERNAME`
	- `SMTP_PASSWORD`
3. Update `recording-uploader/config/config.yaml` for your station:
	- `source_mode`: `local` to watch a folder, or `drive` to poll Google Drive
	- `local.watch_folder` or `drive.folder_id`
	- `filename.datetime_format` to match your recording filenames
	- `google_sheets` column mappings and spreadsheet details
	- `soundcloud` defaults such as genre and sharing mode
	- `alerts` recipients and SMTP host settings
	- `state.db_path` for the local SQLite tracking database

### Running the uploader

Start the pipeline from the tool directory:

```bash
cd recording-uploader
python run.py
```

In `local` mode, the uploader processes any existing files in the watch folder and then continues watching for new ones. In `drive` mode, it polls the configured Google Drive folder on the interval set in `config.yaml`, downloads new files temporarily, uploads them, and removes the temporary copies afterwards.

### Metadata expected in Google Sheets

The sheet should contain columns for:

- `datetime`
- `show_name`
- `description`
- `image_url`
- `secondary_artist`

Column names are configurable in `config.yaml`, but the values should map to the same concepts. Datetime values should use a consistent format such as `2026-04-28 14:30`.

### Testing

Run the test suite from the tool directory:

```bash
cd recording-uploader
pytest
```
