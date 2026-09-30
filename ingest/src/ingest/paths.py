from pathlib import Path

INGEST_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = INGEST_ROOT.parent

# Raw downloads; never committed.
CSV_DIR = INGEST_ROOT / ".cache" / "csv"

# Build output is baked into the backend's Docker image.
OUTPUT_DIR = REPO_ROOT / "backend" / "data"
