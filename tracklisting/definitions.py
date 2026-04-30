import os

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(ROOT_DIR, "config.yaml")

# ---------------------------------------------------------------------------
# Legacy constants — used by main_old.py and recorder/recorder.py only.
# New bot code reads all settings from config.yaml.
# ---------------------------------------------------------------------------

LOGFILE_PATH = os.path.join(ROOT_DIR, "app.log")
HISTORY_FILE_PATH = os.path.join(ROOT_DIR, "history.csv")
STYLES_FILE_PATH = os.path.join(ROOT_DIR, "gui/style.qss")

RES_PATH = os.path.join(ROOT_DIR, "resources")
NO_IMAGE_ICON = os.path.join(RES_PATH, "no_image_icon.png")
ICO_PATH = os.path.join(RES_PATH, "app_logo_v2_2.ico")

MIN_IMAGE_SIZE = 250

DEFAULT_FRAMES = 512
CHUNK = 1024
RATE = 48000
RECORD_SECONDS = 9
EXCERPT_PATH = os.path.join(ROOT_DIR, "excerpt.wav")

UPDATE_RATE = 10
WAITING_TIME = 25

RECORD_TIMEOUT = 10
RECOGNIZE_TIMEOUT = 15

ITEM_SELECTION_CODE = 200

HOST = "http://2.56.240.213:4000"
API_LINK = HOST + "/api/v1"
