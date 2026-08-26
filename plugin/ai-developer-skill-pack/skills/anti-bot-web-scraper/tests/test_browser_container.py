"""Tests for isolated browser container profiles."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from browser_session import BrowserSession  # noqa: E402


def test_browser_session_auto_container_is_isolated_and_cleaned() -> None:
    session = BrowserSession(container=True, headless=True)
    assert session.user_data_dir is not None
    assert session.user_data_dir.exists()
    container_path = session.user_data_dir
    session.close()
    assert not container_path.exists()


def test_browser_session_container_dir_is_reused() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        container_dir = Path(tmp) / "container"
        session = BrowserSession(
            container=True,
            container_dir=container_dir,
            headless=True,
        )
        assert session.user_data_dir == container_dir
        assert container_dir.exists()
        session.close()
        assert container_dir.exists()
