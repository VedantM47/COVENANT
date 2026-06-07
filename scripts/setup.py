"""One-time project setup: install deps, create dirs, download models."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
DIRS = ["cache", "logs", "tmp", "models/hf", "models/torch"]


def create_dirs():
    for d in DIRS:
        (ROOT / d).mkdir(parents=True, exist_ok=True)
        print(f"  ✓ {d}/")


def install_deps():
    print("Installing Python dependencies...")
    req = ROOT / "requirements.txt"
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-r", str(req)]
    )
    print("  ✓ Done")


def prefetch():
    print("Prefetching ML models...")
    from prefetch_models import (
        prefetch_gliner,
        prefetch_sentence_transformers,
    )
    prefetch_sentence_transformers()
    prefetch_gliner()


if __name__ == "__main__":
    print(f"Setting up {ROOT.name}...\n")
    create_dirs()
    install_deps()
    prefetch()
    print(f"\nAll set. Run the app with:\n  uvicorn app.main:app --reload")
