"""Test configuration and shared fixtures."""
from __future__ import annotations

import os
import pytest

# Disable Docling in test environment — DLL ordering conflict with pytest
# causes fatal crash when onnxruntime is loaded after other packages.
# pdfplumber fallback is used instead.
os.environ["DOCLING_DISABLED"] = "1"

# Default: mock provider for unit tests (fast, no LLM)
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ["COVENANT_ROOT"] = "D:\\covenant"


@pytest.fixture(autouse=True)
def set_test_env(monkeypatch):
    monkeypatch.setenv("COVENANT_ROOT", "D:\\covenant")
    monkeypatch.setenv("DOCLING_DISABLED", "1")
    # Don't override LLM_PROVIDER here — let individual tests set it
