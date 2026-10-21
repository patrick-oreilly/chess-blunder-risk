"""Project paths and constants shared across the notebooks."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
REPORTS_DIR = REPO_ROOT / "reports"

# --- Chess.com Published-Data API -------------------------------------------
# Public and read-only, no authentication. The API's fair-use guidance asks for
# a descriptive User-Agent so traffic can be identified.
USERNAME = "patrickoreilly2"
API_BASE = "https://api.chess.com/pub/player"
USER_AGENT = "chess-blunder-risk/0.1 (CT4101 student project; patrickoreilly2)"

# --- dataset scope ----------------------------------------------------------
# Every value below is justified in data/README.md. Changing one changes the
# dataset, so they live here rather than being scattered through the notebooks.
TIME_CLASSES = ("rapid",)
RULES = ("chess",)
RATED_ONLY = True
# The last calendar month in the dataset, as "YYYY-MM". The current month's
# archive grows with every game played, so without a fixed end the dataset
# would depend on the day the notebook was run.
END_MONTH = "2026-09"
