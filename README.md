# Community Radio Tools

A toolbox built to assist the running of community radio stations with tasks such as automated track uploading, scheduling, and track listing.

## Recording Uploader

`recording-uploader` is a Python automation tool for publishing recorded shows to SoundCloud. It watches a local folder or polls a Google Drive folder for new audio files, matches each file to show metadata in Google Sheets, uploads the track to SoundCloud, records the upload in a local state database to avoid duplicates, and sends email alerts if any stage fails.

### How it works

The uploader expects each audio filename to contain a broadcast date and time, for example `2026-04-28 14-30.mp3`. This colon-free format is safe across macOS, Windows, and Linux filesystems. That timestamp is parsed using the format defined in `recording-uploader/config/config.yaml`, then matched against a row in a Google Sheet within a configurable tolerance window. The matched row supplies the show title, description, artwork URL, and secondary artist metadata used for the SoundCloud upload. After a successful upload, the artist receives an email containing the show URL and description.

### Requirements

- Python 3.11+
- A SoundCloud app and account credentials
- A Google service account with read access to the target Google Sheet
- SMTP credentials if email alerts are enabled

Install dependencies from the tool directory:

```bash
cd uploader
pip install -r requirements.txt
```

### Configuration

1. Copy `recording-uploader/config/.env.example` to `recording-uploader/config/.env`.
2. Set the environment values for:
	- `GOOGLE_CREDENTIALS_PATH`
	- `SOUNDCLOUD_CLIENT_ID`
	- `SOUNDCLOUD_CLIENT_SECRET`
	- `SOUNDCLOUD_REFRESH_TOKEN`
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
cd uploader
python run.py
```

In `local` mode, the uploader processes any existing files in the watch folder and then continues watching for new ones. In `drive` mode, it polls the configured Google Drive folder on the interval set in `config.yaml`, downloads new files temporarily, uploads them, and removes the temporary copies afterwards.

### SoundCloud authentication

SoundCloud uploads require a user-scoped OAuth token. This project now expects a token obtained through the Authorization Code + PKCE flow, then reused via `SOUNDCLOUD_REFRESH_TOKEN` in `config/.env`.

For a first-time token exchange, provide these environment variables before running the uploader:

- `SOUNDCLOUD_AUTHORIZATION_CODE`
- `SOUNDCLOUD_CODE_VERIFIER`
- `SOUNDCLOUD_REDIRECT_URI`

After the first successful exchange, keep the returned refresh token and configure `SOUNDCLOUD_REFRESH_TOKEN` for normal unattended runs.

For a one-time bootstrap, run:

```bash
cd uploader
python src/soundcloud_auth.py authorize-url --redirect-uri https://localhost/callback
python src/soundcloud_auth.py exchange-code --code eyJlbmMiOiJBMTI4Q0JDLUhTMjU2IiwiYWxnIjoiQTI1NktXIn0.JWBjMDSfgN9mvy66MBHq6DTSM0-Dg1j-m8lSyZY31bObk9xFu81zmQ.ABNrKqBrOYvzd8usfpa85w.2NSgAfn9MdDtZ3V4ulKDc8rpgG6RkX23L1w9a0spsx3q3n5sWLl-qXx9lMZBJ-VRq4fvKyyl3U3EqfI3J4vRUA-reSLuwUADJQuau-nfkK-EjjqCC9WLEGTn0sXRxVP08Lm4sAaRghu8I5F-veS7BmG30IZUK5cTGE9rXJq4P1VmMpn9Hzi-dxTrq0Bfhy_qYtETABFCBMZzdfOyS2vztroItGN1fRjhZzUgJIH-Av0G8Afj99Oj5LKXXQ3d2pVA.IUHDh1BehS6cgOXrFXHMNw --code-verifier yX6WI-ZoPL9c_fQioDTRRAuu6abkcB_x1nPR2z_zlu8wl-1S_WXutPOzkldtCmOQT6vaO1LthUjxirgCYT1pzw --redirect-uri https://localhost/callback
```

### Metadata expected in Google Sheets

The sheet should contain columns for:

- `datetime`
- `show_name`
- `description`
- `image_url`
- `secondary_artist`
- `artist_email`

Column names are configurable in `config.yaml`, but the values should map to the same concepts. Datetime values should use a consistent format such as `2026-04-28 14-30`.

### Testing

Run the test suite from the tool directory:

```bash
cd recording-uploader
pytest
```
