"""Pre-fetch all ML model weights to D:\covenant\models\.

Run once before first engagement to avoid network hits on the critical path.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Set model cache dirs before importing anything
os.environ["HF_HOME"] = r"D:\covenant\models\hf"
os.environ["TRANSFORMERS_CACHE"] = r"D:\covenant\models\hf"
os.environ["TORCH_HOME"] = r"D:\covenant\models\torch"

sys.path.insert(0, str(Path(__file__).parent.parent))


def prefetch_sentence_transformers():
    print("Downloading bge-small-en-v1.5...")
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("BAAI/bge-small-en-v1.5")
        # Test encode
        model.encode(["test"], show_progress_bar=False)
        print("  ✓ bge-small-en-v1.5 ready")
    except Exception as e:
        print(f"  ✗ bge-small-en-v1.5 failed: {e}")


def prefetch_gliner():
    print("Downloading GLiNER multi-v2.1...")
    try:
        from gliner import GLiNER
        model = GLiNER.from_pretrained("urchade/gliner_multi-v2.1")
        print("  ✓ GLiNER multi-v2.1 ready")
    except Exception as e:
        print(f"  ✗ GLiNER failed: {e}")


def prefetch_easyocr():
    print("Downloading EasyOCR English models...")
    try:
        import easyocr
        reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        print("  ✓ EasyOCR English ready")
    except Exception as e:
        print(f"  ✗ EasyOCR failed: {e}")


if __name__ == "__main__":
    print(f"Prefetching models to D:\\covenant\\models\\")
    Path(r"D:\covenant\models\hf").mkdir(parents=True, exist_ok=True)
    Path(r"D:\covenant\models\torch").mkdir(parents=True, exist_ok=True)

    prefetch_sentence_transformers()
    prefetch_gliner()
    # EasyOCR is large — skip unless explicitly requested
    # prefetch_easyocr()

    print("\nDone. Models cached at D:\\covenant\\models\\")
